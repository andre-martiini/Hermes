"""Ingestao de arquivo: do binario ate o anexo vinculado a acao, numa chamada.

O diario de bordo so aceita texto. Arquivo entra por referencia, no formato
`FILE::JSON::{"n": nome, "v": link}`, e o link precisa ser de um arquivo que ja
esta no Drive. Ou seja: o arquivo tinha de estar hospedado ANTES de chegar ao
Hermes.

Quando o arquivo nasce fora do Drive — print de cartao de embarque, foto de nota
fiscal, PDF recebido no WhatsApp, documento gerado pelo proprio agente — nao
havia caminho. O agente lia o conteudo e transcrevia para o diario, mas o
comprovante ficava orfao: ou o usuario subia a mao no Drive e voltava para colar
o link, ou o arquivo simplesmente nao era anexado.

Isso quebrava justamente o caso mais comum de anexo, que e comprovacao
documental — prestacao de contas, processo SEI, recibo. Nesses casos o dado
transcrito nao substitui o documento: e o arquivo que tem valor probatorio. E o
custo caia sobre o usuario exatamente quando ele delegou a tarefa para nao ter
esse trabalho.

Este modulo faz o caminho inteiro: recebe o arquivo, grava no Drive, registra em
`pool_dados` da acao e escreve a entrada de diario no formato que a UI ja le.

## Por que `conteudo_base64` exige checksum

A primeira versao aceitava base64 solto. Um cartao de embarque de 11 KB chegou
com 1,2 KB, gravou no Drive e devolveu `status: ok`. O arquivo entrou numa
prestacao de contas como comprovante e nao servia para nada.

A causa nao e o transporte: e que base64 e ruido de alta entropia e um LLM nao
reproduz milhares de caracteres aleatorios verbatim — ele encurta e produz algo
plausivel. O corte calhou de cair em multiplo de 4 e de terminar em `FF D9`, o
marcador de fim de JPEG, entao passou por validacao sintatica.

Inspecao de conteudo tambem nao salva: testado no arquivo corrompido real,
`PIL.Image.verify()` E `load()` aceitaram os 1,2 KB como JPEG valido de 230x468.
O corte formou uma imagem decodificavel, menor. Nao ha como um validador
distinguir "imagem pequena" de "imagem truncada" sem saber o que era esperado.

Por isso `tamanho_bytes` e `sha256` sao **obrigatorios** com `conteudo_base64`.
Eles vem do arquivo de origem, calculados por quem tem o arquivo — nao pelo
modelo lendo o conteudo. Se o payload chegar truncado, o tamanho nao bate; se
chegar alterado, o digest nao bate. Um modelo que alucine tambem o checksum
falha, porque a chance de o digest inventado casar com o base64 inventado e
nula. O ganho nao e impedir o erro: e faze-lo alto em vez de silencioso.

## As vias sem bytes pelo modelo

`drive_file_id`, `url`, `gmail_message_id` e `upload_token` nao passam o arquivo
pela conversa — o Hermes busca por conta propria. Sao sempre preferiveis.
`preparar_upload` devolve uma URL assinada para o cliente subir o arquivo direto,
fora da conversa, e funciona para qualquer tamanho.

## `drive_file_id`: o arquivo que ja esta no Drive

Adicionada em 26/08/2026, a pedido do dono do sistema, como caminho padrao para
quando o agente nao consegue fazer o upload ele mesmo: **quem tem os bytes poe no
Drive** — o celular pelo app, o Gmail, o proprio usuario — e o agente so acha e
vincula.

A tentacao aqui era o agente subir o arquivo ao Drive pelo conector do Google.
Nao serve: aquele `create_file` recebe `base64Content`, ou seja, os bytes voltam
a passar pelo modelo, e o conector do Drive nao confere tamanho nem checksum.
Seria trocar a rota que verifica pela que nao verifica nada — o mesmo defeito que
corrompeu o cartao de embarque, de novo e sem rede.

Nesta via a integridade e ancorada no `md5Checksum` que o Drive guarda do
arquivo: um valor que o modelo nunca toca e nao tem como inventar.
"""

from __future__ import annotations

import base64
import hashlib
import io
import mimetypes
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

# Teto das vias que NAO passam o arquivo pela conversa (upload_token, url,
# gmail). Nao ha razao tecnica para ser baixo: o binario vai direto ao storage e
# a funcao so o carrega uma vez para mover ao Drive, com 1 GB de memoria
# disponivel. 50 MB cobre foto de celular, PDF escaneado e video curto.
#
# Ressalva de rota: pela URL do Hosting (Cowork, Desktop, celular) o corte e de
# 60s, entao arquivo perto do teto pode estourar tempo antes de estourar
# tamanho. Pela funcao direta ha 300s.
MAX_BYTES = 50 * 1024 * 1024

# Teto especifico do base64. O parametro e cortado em torno de 16 KiB de string
# antes de chegar aqui — o limite anunciado de 6 MB era inalcancavel por essa
# via, e anunciar limite que nao existe empurra o usuario para o caminho que
# corrompe. 100 KB de binario ja excede o corte de transporte com folga, e serve
# so para a mensagem de erro sair antes de qualquer escrita.
MAX_BYTES_BASE64 = 100 * 1024

# Janela da URL assinada de upload. Curta porque quem sobe e o cliente, na hora.
UPLOAD_TTL_MIN = 15
COL_UPLOADS = "uploads_pendentes"

PASTA_ANEXOS = "Anexos do Copiloto"

# Mesma origem que serve o MCP — a unica garantidamente alcancavel pelo cliente.
ORIGEM_MCP = "https://gestao-hermes.firebaseapp.com"


def _mime_de(nome: str) -> str:
    return mimetypes.guess_type(nome or "")[0] or "application/octet-stream"


def _pasta_de_anexos(service, db) -> str | None:
    """Garante a pasta de anexos sob a raiz configurada em `system/config`."""
    raiz = None
    try:
        snap = db.collection("system").document("config").get()
        if snap.exists:
            raiz = (snap.to_dict() or {}).get("googleDriveFolderId")
    except Exception as exc:
        print(f"[anexar_arquivo] Nao foi possivel ler system/config: {exc}")

    consulta = ("mimeType='application/vnd.google-apps.folder' and trashed=false "
                f"and name='{PASTA_ANEXOS}'")
    if raiz:
        consulta += f" and '{raiz}' in parents"

    achadas = service.files().list(
        q=consulta, fields="files(id)", pageSize=1).execute().get("files", [])
    if achadas:
        return achadas[0]["id"]

    corpo = {"name": PASTA_ANEXOS, "mimeType": "application/vnd.google-apps.folder"}
    if raiz:
        corpo["parents"] = [raiz]
    return service.files().create(body=corpo, fields="id").execute().get("id")


# --------------------------------------------------------------------------
# Fontes do binario
# --------------------------------------------------------------------------

def _de_base64(args: dict) -> tuple[bytes, str]:
    # `strip()` antes de tudo: um `\n` no fim disparava
    # "Only base64 data is allowed", erro que nao diz o que fazer.
    bruto = "".join((args.get("conteudo_base64") or "").split())
    nome = str(args.get("nome") or "").strip()
    if not nome:
        raise ValueError("`nome` e obrigatorio quando o arquivo vem em conteudo_base64.")

    esperado_bytes = args.get("tamanho_bytes")
    esperado_hash = str(args.get("sha256") or "").strip().lower()
    if esperado_bytes in (None, "") or not esperado_hash:
        raise ValueError(
            "`tamanho_bytes` e `sha256` sao obrigatorios com conteudo_base64. "
            "Calcule-os do arquivo de origem (ex.: `sha256sum` e `stat`), nunca "
            "a partir do texto base64. Sem eles nao ha como distinguir o arquivo "
            "inteiro de um truncado — e um truncado grava sem erro. "
            "Para arquivo real, prefira `url`, `gmail_message_id` ou "
            "`preparar_upload`, que nao passam o conteudo pela conversa."
        )

    try:
        dados = base64.b64decode(bruto, validate=True)
    except Exception as exc:
        raise ValueError(f"conteudo_base64 invalido: {exc}") from exc
    if not dados:
        raise ValueError("conteudo_base64 vazio.")

    # Estas duas checagens sao a unica defesa real. `validate=True` so pega
    # truncamento que quebra alfabeto ou padding; um corte limpo em multiplo de 4
    # passa. Foi assim que 11 KB viraram 1,2 KB com `status: ok`.
    try:
        esperado_bytes = int(esperado_bytes)
    except (TypeError, ValueError):
        raise ValueError(f"`tamanho_bytes` precisa ser um inteiro, veio {esperado_bytes!r}")

    if len(dados) != esperado_bytes:
        raise ValueError(
            f"payload truncado: chegaram {len(dados)} bytes, esperados "
            f"{esperado_bytes}. O conteudo foi cortado no caminho — base64 acima "
            "de poucos KB nao atravessa a conversa intacto. Use `preparar_upload`."
        )

    obtido = hashlib.sha256(dados).hexdigest()
    if obtido != esperado_hash:
        raise ValueError(
            f"checksum nao confere: sha256 recebido {esperado_hash[:16]}..., "
            f"calculado {obtido[:16]}.... O conteudo chegou alterado."
        )
    return dados, nome


# --------------------------------------------------------------------------
# Google Drive
# --------------------------------------------------------------------------

# Formatos de link que o Drive produz, mais o `?id=` das URLs de download.
_PADRAO_DRIVE_PATH = re.compile(
    r"(?:drive|docs)\.google\.com/.*?/d/([A-Za-z0-9_-]{10,})")
_PADRAO_DRIVE_QUERY = re.compile(
    r"(?:drive|docs)\.google\.com/[^ ]*[?&]id=([A-Za-z0-9_-]{10,})")

# Nativos do Google nao tem bytes proprios: precisam ser exportados.
_EXPORTAVEIS = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}


def id_do_drive(texto) -> str | None:
    """ID do arquivo a partir de um link do Drive, ou do proprio ID.

    Existe porque link de compartilhamento do Drive **nao devolve o arquivo**:
    `drive.google.com/file/d/<id>/view` responde uma pagina HTML. Baixar esse
    link por GET e gravar o resultado como anexo produziria um arquivo que
    parece existir, abre no navegador e nao e o documento — a mesma falha
    silenciosa que corrompeu o cartao de embarque em 26/08/2026, com outro
    disfarce. Reconhecer o link aqui e o que impede isso.
    """
    bruto = str(texto or "").strip()
    if not bruto:
        return None
    for padrao in (_PADRAO_DRIVE_PATH, _PADRAO_DRIVE_QUERY):
        achado = padrao.search(bruto)
        if achado:
            return achado.group(1)
    # ID solto: sem barra, sem espaco, no formato que o Drive usa.
    if "/" not in bruto and " " not in bruto and re.fullmatch(r"[A-Za-z0-9_-]{20,}", bruto):
        return bruto
    return None


def _do_drive(args: dict) -> tuple[bytes, str]:
    """Baixa pela API do Drive, conferindo contra os metadados do proprio Drive.

    Nenhum byte passa pelo modelo: ele informa um ID, o Hermes busca o arquivo.
    A integridade e ancorada no `md5Checksum` que o Drive guarda do arquivo —
    um valor que o modelo nunca toca e nao tem como inventar.
    """
    import hashlib
    import io as _io

    from googleapiclient.http import MediaIoBaseDownload

    from main import get_drive_service

    file_id = id_do_drive(args.get("drive_file_id") or args.get("url"))
    if not file_id:
        raise ValueError(
            "Nao reconheci um arquivo do Drive. Passe `drive_file_id` com o ID, "
            "ou uma URL no formato drive.google.com/file/d/<id>/view.")

    service = get_drive_service()
    try:
        meta = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, md5Checksum, trashed",
            supportsAllDrives=True,
        ).execute()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"Nao consegui abrir o arquivo '{file_id}' no Drive: {exc}. "
            "Confira se ele existe e se a conta do Hermes tem acesso."
        ) from exc

    if meta.get("trashed"):
        raise ValueError(
            f"'{meta.get('name')}' esta na lixeira do Drive. Restaure antes de anexar.")

    mime = str(meta.get("mimeType") or "")
    nome = str(args.get("nome") or meta.get("name") or "arquivo").strip()
    tamanho_declarado = int(meta.get("size") or 0)

    if tamanho_declarado > MAX_BYTES:
        raise ValueError(
            f"'{nome}' tem {tamanho_declarado // 1024 // 1024} MB e excede o teto "
            f"de {MAX_BYTES // 1024 // 1024} MB.")

    buffer = _io.BytesIO()
    if mime in _EXPORTAVEIS:
        # Documento nativo do Google nao tem arquivo: e exportado na hora, e por
        # isso nao ha checksum guardado com que comparar.
        destino, extensao = _EXPORTAVEIS[mime]
        pedido = service.files().export_media(fileId=file_id, mimeType=destino)
        if not nome.lower().endswith(extensao):
            nome = f"{nome}{extensao}"
    elif mime.startswith("application/vnd.google-apps."):
        raise ValueError(
            f"'{nome}' e um item nativo do Google ({mime}) que nao pode ser "
            "baixado nem exportado. Anexe um arquivo de verdade.")
    else:
        pedido = service.files().get_media(fileId=file_id, supportsAllDrives=True)

    baixador = MediaIoBaseDownload(buffer, pedido, chunksize=5 * 1024 * 1024)
    concluido = False
    while not concluido:
        _, concluido = baixador.next_chunk()
    dados = buffer.getvalue()

    if not dados:
        raise ValueError(f"'{nome}' veio vazio do Drive.")

    # Confere contra o que o Drive diz do arquivo. Nao e paranoia com o modelo,
    # que aqui nem toca nos bytes: e o download que pode truncar.
    if tamanho_declarado and len(dados) != tamanho_declarado:
        raise ValueError(
            f"Download incompleto de '{nome}': chegaram {len(dados)} bytes, "
            f"{tamanho_declarado} declarados pelo Drive.")

    md5_drive = str(meta.get("md5Checksum") or "")
    if md5_drive:
        obtido = hashlib.md5(dados).hexdigest()
        if obtido != md5_drive:
            raise ValueError(
                f"Checksum de '{nome}' nao confere com o do Drive "
                f"({obtido[:12]}... contra {md5_drive[:12]}...).")

    return dados, nome


def _de_url(args: dict) -> tuple[bytes, str]:
    import urllib.parse
    import urllib.request

    url = str(args.get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("`url` precisa comecar com http:// ou https://")

    requisicao = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        dados = resposta.read(MAX_BYTES + 1)
        cabecalho = resposta.headers.get("Content-Disposition", "")

    nome = str(args.get("nome") or "").strip()
    if not nome and "filename=" in cabecalho:
        nome = cabecalho.split("filename=")[-1].strip('"; ')
    if not nome:
        nome = urllib.parse.unquote(url.rstrip("/").split("/")[-1].split("?")[0]) or "arquivo"
    return dados, nome


def _do_gmail(args: dict) -> tuple[bytes, str]:
    """Puxa o anexo direto do Gmail — nenhum byte passa pelo modelo."""
    from main import get_gmail_service

    msg_id = str(args.get("gmail_message_id") or "").strip()
    if not msg_id:
        raise ValueError("`gmail_message_id` vazio.")

    service = get_gmail_service()
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    procurado = str(args.get("nome_anexo") or "").strip().lower()
    attachment_id = str(args.get("attachment_id") or "").strip()
    candidatos: list[tuple[str, str]] = []

    def _varrer(partes):
        for parte in partes or []:
            _varrer(parte.get("parts"))
            nome_parte = parte.get("filename") or ""
            corpo = parte.get("body") or {}
            if not nome_parte or not corpo.get("attachmentId"):
                continue
            candidatos.append((str(corpo["attachmentId"]), nome_parte))

    _varrer([msg.get("payload", {})])
    if attachment_id:
        chosen = next((item for item in candidatos if item[0] == attachment_id), None)
        if not chosen:
            raise ValueError(f"attachment_id '{attachment_id}' não existe na mensagem {msg_id}.")
        if procurado and procurado not in chosen[1].lower():
            raise ValueError("attachment_id e nome_anexo apontam para anexos diferentes.")
    else:
        selected = [item for item in candidatos if not procurado or procurado in item[1].lower()]
        if len(selected) == 1:
            chosen = selected[0]
        elif not selected:
            alvo = f" com nome contendo '{procurado}'" if procurado else ""
            raise ValueError(f"Nenhum anexo{alvo} na mensagem {msg_id}.")
        else:
            raise ValueError("A mensagem tem mais de um anexo; informe attachment_id ou nome_anexo.")
    anexo = service.users().messages().attachments().get(
        userId="me", messageId=msg_id, id=chosen[0]).execute()
    if not anexo.get("data"):
        raise ValueError(f"Anexo '{chosen[1]}' veio sem bytes da API Gmail.")
    return base64.urlsafe_b64decode(anexo["data"]), chosen[1]


def resolver_anexo_por_referencia(ctx, reference: dict) -> tuple[bytes, str]:
    """Resolve uma referência segura para uma mensagem, reutilizando o pipeline.

    A ferramenta de rascunho deliberadamente não aceita bytes inline: cada item
    precisa escolher exatamente uma fonte que o Hermes busca por conta própria.
    """
    if not isinstance(reference, dict) or reference.get("conteudo_base64"):
        raise ValueError("conteudo_base64 não é aceito; use preparar_upload e upload_token.")
    sources = [key for key in ("drive_file_id", "upload_token", "gmail_message_id") if reference.get(key)]
    if len(sources) != 1:
        raise ValueError("Cada anexo precisa ter exatamente uma referência: drive_file_id, gmail_message_id ou upload_token.")
    if reference.get("attachment_id") and not reference.get("gmail_message_id"):
        raise ValueError("attachment_id só pode ser usado junto com gmail_message_id.")
    if reference.get("nome_anexo") and not reference.get("gmail_message_id"):
        raise ValueError("nome_anexo só pode ser usado junto com gmail_message_id.")
    return _resolver_conteudo(ctx, reference)


def _do_upload_token(ctx, args: dict) -> tuple[bytes, str]:
    """Le o arquivo que o cliente subiu pela URL assinada de `preparar_upload`.

    O binario foi de PUT direto ao Storage, fora da conversa. Aqui so se confere
    tamanho e digest contra o que foi declarado na preparacao, e se le.
    """
    token = str(args.get("upload_token") or "").strip()
    snap = ctx.db.collection(COL_UPLOADS).document(token).get() if token else None
    if not snap or not snap.exists:
        raise ValueError(f"upload_token '{token}' desconhecido ou ja consumido.")

    reserva = snap.to_dict() or {}
    if reserva.get("uid") != ctx.user_uid:
        raise ValueError(f"upload_token '{token}' desconhecido ou ja consumido.")
    if reserva.get("consumed_at"):
        raise ValueError(f"upload_token '{token}' desconhecido ou ja consumido.")
    if reserva.get("expira_em", "") < datetime.now(timezone.utc).isoformat():
        raise ValueError("upload_token expirado. Chame preparar_upload de novo.")

    blob = _bucket().blob(reserva["caminho"])
    if not blob.exists():
        raise ValueError(
            "Nada foi enviado para a URL assinada ainda. Faca o PUT do arquivo "
            "antes de chamar anexar_arquivo com este upload_token."
        )
    dados = blob.download_as_bytes()

    # Mesma conferencia da via base64: o que chegou tem de ser o que foi
    # declarado. Aqui o transporte e confiavel, mas a checagem custa nada e pega
    # upload parcial ou arquivo trocado.
    if len(dados) != reserva["tamanho_bytes"]:
        raise ValueError(
            f"upload incompleto: {len(dados)} bytes no storage, "
            f"{reserva['tamanho_bytes']} declarados em preparar_upload.")
    obtido = hashlib.sha256(dados).hexdigest()
    if obtido != reserva["sha256"]:
        raise ValueError(
            f"checksum nao confere: declarado {reserva['sha256'][:16]}..., "
            f"calculado {obtido[:16]}...")

    return dados, reserva["nome"]


def consumir_upload_token(ctx, token: str) -> None:
    """Invalida o staging somente depois de a operação externa ter sucesso."""
    token = str(token or "").strip()
    snap = ctx.db.collection(COL_UPLOADS).document(token).get() if token else None
    if not snap or not snap.exists:
        return
    reserva = snap.to_dict() or {}
    if reserva.get("uid") != ctx.user_uid or reserva.get("consumed_at"):
        return
    # Marcar primeiro evita um novo uso mesmo se a limpeza do blob falhar.
    try:
        snap.reference.update({"consumed_at": datetime.now(timezone.utc).isoformat()})
    except Exception as exc:
        print(f"[anexar_arquivo] Falha ao consumir upload {token}: {exc}")
        return
    try:
        _bucket().blob(reserva["caminho"]).delete()
    except Exception as exc:
        print(f"[anexar_arquivo] Falha ao limpar staging {reserva['caminho']}: {exc}")
    try:
        snap.reference.delete()
    except Exception as exc:
        print(f"[anexar_arquivo] Falha ao remover reserva {token}: {exc}")


def _resolver_conteudo(ctx, args: dict) -> tuple[bytes, str]:
    if args.get("upload_token"):
        dados, nome = _do_upload_token(ctx, args)
    elif args.get("conteudo_base64"):
        dados, nome = _de_base64(args)
        if len(dados) > MAX_BYTES_BASE64:
            raise ValueError(
                f"Arquivo de {len(dados) // 1024} KB e grande demais para a via "
                f"base64 (teto de {MAX_BYTES_BASE64 // 1024} KB). Use "
                "`preparar_upload`, `url` ou `gmail_message_id`.")
    elif args.get("drive_file_id"):
        dados, nome = _do_drive(args)
    elif args.get("url"):
        # Link do Drive nao vai por GET: ele responde uma pagina HTML, e gravar
        # essa pagina como anexo daria `status: ok` num arquivo que nao e o
        # documento. Reconhecer aqui e o que fecha essa porta.
        dados, nome = (_do_drive(args) if id_do_drive(args["url"]) else _de_url(args))
    elif args.get("gmail_message_id"):
        dados, nome = _do_gmail(args)
    else:
        raise ValueError(
            "Informe uma origem: drive_file_id (arquivo ja no Drive), "
            "upload_token (via preparar_upload, para arquivo local), url, "
            "gmail_message_id, ou conteudo_base64 (+nome, tamanho_bytes e "
            "sha256; so para arquivo pequeno).")

    if len(dados) > MAX_BYTES:
        raise ValueError(
            f"Arquivo com {len(dados) // 1024} KB excede o limite de "
            f"{MAX_BYTES // 1024 // 1024} MB desta via. Use `url` ou "
            "`gmail_message_id`, que buscam o arquivo sem passa-lo pela conversa."
        )
    return dados, nome


# --------------------------------------------------------------------------
# Execucao
# --------------------------------------------------------------------------

def anexar(ctx, args: dict) -> dict:
    """Sobe o arquivo, vincula a acao e escreve a entrada de diario."""
    from googleapiclient.http import MediaIoBaseUpload

    from main import get_drive_service

    task_id = str(args.get("task_id") or ctx.task_id or "").strip()
    if not task_id:
        return {"erro": "Informe task_id: o anexo precisa de uma acao a que se vincular."}

    task_ref = ctx.db.collection("tarefas").document(task_id)
    if not task_ref.get().exists:
        return {"erro": f"Acao '{task_id}' nao encontrada."}

    try:
        dados, nome = _resolver_conteudo(ctx, args)
    except ValueError as exc:
        return {"erro": str(exc)}

    try:
        service = get_drive_service()
        metadados = {"name": nome}
        pasta = _pasta_de_anexos(service, ctx.db)
        if pasta:
            metadados["parents"] = [pasta]

        arquivo = service.files().create(
            body=metadados,
            media_body=MediaIoBaseUpload(
                io.BytesIO(dados), mimetype=_mime_de(nome), resumable=True),
            fields="id, webViewLink",
        ).execute()

        # A UI monta a miniatura buscando o arquivo direto; sem leitura publica
        # o preview quebra com 403. Mesmo tratamento do `upload_to_drive`.
        try:
            service.permissions().create(
                fileId=arquivo["id"], body={"type": "anyone", "role": "reader"}).execute()
        except Exception as exc:
            print(f"[anexar_arquivo] Falha ao liberar leitura de {arquivo['id']}: {exc}")
    except Exception as exc:  # noqa: BLE001
        return {"erro": f"Falha ao gravar no Drive: {exc}"}

    link = arquivo.get("webViewLink") or f"https://drive.google.com/file/d/{arquivo['id']}/view"
    agora = datetime.now(timezone.utc).isoformat()

    import json as _json

    from firebase_admin import firestore

    item = {
        "id": str(uuid.uuid4())[:8],
        "tipo": "arquivo",
        "valor": link,
        "nome": nome,
        "data_criacao": agora,
        "drive_file_id": arquivo["id"],
    }
    nota = "FILE::JSON::" + _json.dumps({"n": nome, "v": link}, ensure_ascii=False)

    entradas = [{"data": agora, "nota": nota}]
    descricao = str(args.get("descricao") or "").strip()
    if descricao:
        entradas.append({"data": agora, "nota": descricao})

    try:
        task_ref.update({
            "pool_dados": firestore.ArrayUnion([item]),
            "acompanhamento": firestore.ArrayUnion(entradas),
        })
    except Exception as exc:  # noqa: BLE001
        # Sem isto o arquivo ficaria no Drive sem estar vinculado a nada —
        # invisivel na acao e impossivel de achar depois.
        try:
            service.files().update(fileId=arquivo["id"], body={"trashed": True}).execute()
        except Exception as limpeza:
            print(f"[anexar_arquivo] Orfao em {arquivo['id']}, limpeza falhou: {limpeza}")
        return {"erro": f"Falha ao vincular a acao (upload revertido): {exc}"}

    if args.get("upload_token"):
        consumir_upload_token(ctx, str(args["upload_token"]))

    return {
        "status": "ok",
        "task_id": task_id,
        "nome": nome,
        "drive_file_id": arquivo["id"],
        "link": link,
        "tamanho_kb": round(len(dados) / 1024, 1),
        "nota_diario": nota,
        "pool_item_id": item["id"],
    }


# --------------------------------------------------------------------------
# Upload sem passar o arquivo pela conversa
# --------------------------------------------------------------------------

def _bucket():
    """Reusa o resolvedor de bucket ja testado do projeto.

    O nome varia entre `.firebasestorage.app` e `.appspot.com` conforme a idade
    do projeto, e `hermes_core_logic` ja carrega essa lista de candidatos.
    """
    from hermes_core_logic import _get_hermes_storage_bucket

    return _get_hermes_storage_bucket()


# Teto da rota que passa pelo Hermes. O corpo da requisicao atravessa o Hosting
# e a Cloud Function, que tem limite proprio; acima disto so a URL assinada
# direta ao GCS serve.
MAX_BYTES_VIA_HERMES = 30 * 1024 * 1024


def receber_upload(ctx_db, uid_esperado, token: str, corpo: bytes) -> dict:
    """Recebe o PUT do arquivo na propria origem do MCP.

    Existe porque a URL assinada aponta para `storage.googleapis.com`, e ha
    ambiente de cliente que bloqueia egresso para esse host — o PUT morre num
    filtro de rede antes de sair. A origem do Hermes, essa, e necessariamente
    alcancavel: e por ela que o MCP conversa.

    O `token` e a credencial: 128 bits de entropia, uso unico, 15 minutos de
    validade, preso a um uid e a um arquivo ja declarado (tamanho e digest).
    E o mesmo modelo de seguranca de uma URL assinada, entao nao afrouxa nada —
    e nao pode exigir o Bearer do MCP, porque com `headersHelper` o token nem
    chega ao modelo, que e quem monta o comando de upload.
    """
    snap = ctx_db.collection(COL_UPLOADS).document(token).get() if token else None
    if not snap or not snap.exists:
        return {"erro": "upload_token desconhecido ou ja consumido.", "status": 404}

    reserva = snap.to_dict() or {}
    if uid_esperado and reserva.get("uid") != uid_esperado:
        return {"erro": "upload_token desconhecido ou ja consumido.", "status": 404}
    if reserva.get("expira_em", "") < datetime.now(timezone.utc).isoformat():
        return {"erro": "upload_token expirado; chame preparar_upload de novo.", "status": 410}

    if len(corpo) != reserva["tamanho_bytes"]:
        return {"erro": f"corpo com {len(corpo)} bytes, "
                        f"{reserva['tamanho_bytes']} declarados.", "status": 400}
    obtido = hashlib.sha256(corpo).hexdigest()
    if obtido != reserva["sha256"]:
        return {"erro": f"checksum nao confere: declarado "
                        f"{reserva['sha256'][:16]}..., recebido {obtido[:16]}...",
                "status": 400}

    _bucket().blob(reserva["caminho"]).upload_from_string(
        corpo, content_type=reserva.get("mime") or "application/octet-stream")
    return {"status": 200, "ok": True, "bytes": len(corpo), "nome": reserva["nome"],
            "proximo_passo": f"anexar_arquivo(task_id=..., upload_token='{token}')"}


def _assinar_upload(caminho: str, mime: str) -> str:
    """URL assinada de PUT, funcionando dentro da Cloud Function.

    Assinar exige uma chave privada. Localmente ela vem do arquivo de service
    account, mas no runtime do Cloud Functions as credenciais chegam pelo
    metadata server e NAO tem chave — `generate_signed_url` falharia com
    "you need a private key to sign credentials".

    A saida e delegar a assinatura ao IAM: passando `service_account_email` e um
    `access_token`, a biblioteca usa a API SignBlob em vez de assinar local. Isso
    exige que a service account do runtime tenha permissao de assinar em si
    mesma (`roles/iam.serviceAccountTokenCreator`).
    """
    blob = _bucket().blob(caminho)
    comum = dict(version="v4", expiration=timedelta(minutes=UPLOAD_TTL_MIN),
                 method="PUT", content_type=mime)
    try:
        return blob.generate_signed_url(**comum)
    except Exception as sem_chave:
        import google.auth
        from google.auth.transport import requests as greq

        try:
            cred, _ = google.auth.default()
            cred.refresh(greq.Request())
            return blob.generate_signed_url(
                **comum,
                service_account_email=getattr(cred, "service_account_email", None),
                access_token=cred.token,
            )
        except Exception as via_iam:
            raise ValueError(
                "Nao foi possivel gerar a URL assinada de upload. Assinatura "
                f"local falhou ({sem_chave}) e a via IAM tambem ({via_iam}). "
                "Confira se a service account do runtime tem "
                "roles/iam.serviceAccountTokenCreator sobre si mesma."
            ) from via_iam

def preparar_upload(ctx, args: dict) -> dict:
    """Devolve uma URL assinada para o cliente subir o arquivo direto.

    Este e o caminho certo para arquivo local. O binario vai de PUT ao Storage,
    fora da conversa: nao gasta token, nao tem teto de mensagem e nao depende de
    o modelo reproduzir milhares de caracteres verbatim — que e onde a via
    base64 quebra.

    `tamanho_bytes` e `sha256` sao registrados agora e conferidos depois, quando
    `anexar_arquivo` for chamada com o `upload_token`.
    """
    nome = str(args.get("nome") or "").strip()
    if not nome:
        raise ValueError("`nome` e obrigatorio.")
    try:
        tamanho = int(args.get("tamanho_bytes"))
    except (TypeError, ValueError):
        raise ValueError("`tamanho_bytes` e obrigatorio e precisa ser inteiro.")
    sha = str(args.get("sha256") or "").strip().lower()
    if len(sha) != 64:
        raise ValueError("`sha256` e obrigatorio: hex digest de 64 caracteres do arquivo.")
    if tamanho > MAX_BYTES:
        raise ValueError(f"Arquivo excede o teto de {MAX_BYTES // 1024 // 1024} MB.")

    token = f"upl-{secrets.token_urlsafe(16)}"
    caminho = f"uploads_mcp/{ctx.user_uid}/{token}/{nome}"
    mime = _mime_de(nome)

    # Assinar pode falhar (permissao de IAM ausente, por exemplo) e nao pode
    # derrubar a preparacao: a rota pelo Hermes nao depende disso.
    try:
        url_gcs = _assinar_upload(caminho, mime)
    except Exception as exc:
        url_gcs = None
        print(f"[anexar_arquivo] URL assinada indisponivel: {exc}")

    expira = (datetime.now(timezone.utc) + timedelta(minutes=UPLOAD_TTL_MIN)).isoformat()
    ctx.db.collection(COL_UPLOADS).document(token).set({
        "uid": ctx.user_uid,
        "nome": nome,
        "caminho": caminho,
        "tamanho_bytes": tamanho,
        "sha256": sha,
        "mime": mime,
        "criado_em": datetime.now(timezone.utc).isoformat(),
        "expira_em": expira,
    })

    url_hermes = f"{ORIGEM_MCP}/mcp/upload/{token}"
    cabe_no_hermes = tamanho <= MAX_BYTES_VIA_HERMES
    return {
        "upload_token": token,
        # Rota padrao: mesma origem do MCP, logo alcancavel por qualquer cliente
        # que ja fale com o servidor. Ambientes com allowlist de egresso costumam
        # bloquear `storage.googleapis.com`, e o PUT morreria no filtro de rede.
        "upload_url": url_hermes if cabe_no_hermes else url_gcs,
        "upload_url_alternativa": url_gcs if cabe_no_hermes else None,
        "metodo": "PUT",
        "content_type": mime,
        "expira_em": expira,
        "instrucao": (
            f"curl -X PUT -H 'Content-Type: {mime}' --data-binary @ARQUIVO "
            f"'{url_hermes if cabe_no_hermes else url_gcs}'  "
            f"Depois: anexar_arquivo(task_id=..., upload_token='{token}'). "
            + ("" if cabe_no_hermes else
               f"Arquivo acima de {MAX_BYTES_VIA_HERMES // 1024 // 1024} MB so sobe "
               "pela URL assinada direta, que exige egresso para storage.googleapis.com.")
        ),
    }


def remover_anexo(ctx, args: dict) -> dict:
    """Remove um anexo da acao e manda o arquivo para a lixeira do Drive.

    A entrada original do diario NAO e apagada: numa prestacao de contas ela e
    trilha de auditoria, e sumir com ela esconde que houve um erro. Entra uma
    nota de retificacao ao lado, dizendo o que foi removido e por que.

    O arquivo vai para a lixeira, nao para exclusao definitiva — anexo removido
    por engano ainda da para recuperar por 30 dias.
    """
    from firebase_admin import firestore

    from main import get_drive_service

    task_id = str(args.get("task_id") or ctx.task_id or "").strip()
    pool_item_id = str(args.get("pool_item_id") or "").strip()
    motivo = str(args.get("motivo") or "").strip()
    if not task_id or not pool_item_id:
        return {"erro": "Informe task_id e pool_item_id."}
    if not motivo:
        return {"erro": "Informe o `motivo` da remocao: ele vai para a trilha de auditoria."}

    task_ref = ctx.db.collection("tarefas").document(task_id)
    snap = task_ref.get()
    if not snap.exists:
        return {"erro": f"Acao '{task_id}' nao encontrada."}

    item = next((i for i in (snap.to_dict() or {}).get("pool_dados") or []
                 if i.get("id") == pool_item_id), None)
    if not item:
        return {"erro": f"Anexo '{pool_item_id}' nao esta no pool da acao {task_id}."}

    drive_id = item.get("drive_file_id")
    lixeira = None
    if drive_id:
        try:
            get_drive_service().files().update(
                fileId=drive_id, body={"trashed": True}).execute()
            lixeira = True
        except Exception as exc:  # noqa: BLE001
            lixeira = False
            print(f"[anexar_arquivo] Falha ao mandar {drive_id} para a lixeira: {exc}")

    agora = datetime.now(timezone.utc).isoformat()
    task_ref.update({
        "pool_dados": firestore.ArrayRemove([item]),
        "acompanhamento": firestore.ArrayUnion([{
            "data": agora,
            "nota": (f"RETIFICAÇÃO — anexo '{item.get('nome')}' removido em "
                     f"{agora[:10]}. Motivo: {motivo}"),
        }]),
    })
    return {
        "status": "ok",
        "task_id": task_id,
        "removido": item.get("nome"),
        "pool_item_id": pool_item_id,
        "drive_para_lixeira": lixeira,
        "observacao": "A entrada original do diario foi mantida, com nota de retificacao ao lado.",
    }
