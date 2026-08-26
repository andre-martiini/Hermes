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

`url`, `gmail_message_id` e `upload_token` nao passam o arquivo pela conversa —
o Hermes busca por conta propria. Sao sempre preferiveis. `preparar_upload`
devolve uma URL assinada para o cliente subir o arquivo direto, fora da conversa,
e funciona para qualquer tamanho.
"""

from __future__ import annotations

import base64
import hashlib
import io
import mimetypes
import secrets
import uuid
from datetime import datetime, timedelta, timezone

# Teto do que o backend aceita por qualquer via.
MAX_BYTES = 6 * 1024 * 1024

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

    encontrado: list[tuple[bytes, str]] = []

    def _varrer(partes):
        for parte in partes or []:
            if encontrado:
                return
            _varrer(parte.get("parts"))
            nome_parte = parte.get("filename") or ""
            corpo = parte.get("body") or {}
            if not nome_parte or not corpo.get("attachmentId"):
                continue
            if procurado and procurado not in nome_parte.lower():
                continue
            anexo = service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=corpo["attachmentId"]).execute()
            encontrado.append((base64.urlsafe_b64decode(anexo["data"]), nome_parte))

    _varrer([msg.get("payload", {})])
    if not encontrado:
        alvo = f" com nome contendo '{procurado}'" if procurado else ""
        raise ValueError(f"Nenhum anexo{alvo} na mensagem {msg_id}.")
    return encontrado[0]


def _do_upload_token(ctx, args: dict) -> tuple[bytes, str]:
    """Le o arquivo que o cliente subiu pela URL assinada de `preparar_upload`.

    O binario foi de PUT direto ao Storage, fora da conversa. Aqui so se confere
    tamanho e digest contra o que foi declarado na preparacao, e se le.
    """
    from firebase_admin import storage

    token = str(args.get("upload_token") or "").strip()
    snap = ctx.db.collection(COL_UPLOADS).document(token).get() if token else None
    if not snap or not snap.exists:
        raise ValueError(f"upload_token '{token}' desconhecido ou ja consumido.")

    reserva = snap.to_dict() or {}
    if reserva.get("uid") != ctx.user_uid:
        raise ValueError(f"upload_token '{token}' desconhecido ou ja consumido.")
    if reserva.get("expira_em", "") < datetime.now(timezone.utc).isoformat():
        raise ValueError("upload_token expirado. Chame preparar_upload de novo.")

    blob = storage.bucket().blob(reserva["caminho"])
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

    # Some da area de espera: o token e de uso unico.
    try:
        blob.delete()
    except Exception as exc:
        print(f"[anexar_arquivo] Falha ao limpar staging {reserva['caminho']}: {exc}")
    snap.reference.delete()
    return dados, reserva["nome"]


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
    elif args.get("url"):
        dados, nome = _de_url(args)
    elif args.get("gmail_message_id"):
        dados, nome = _do_gmail(args)
    else:
        raise ValueError(
            "Informe uma origem: upload_token (via preparar_upload, a melhor para "
            "arquivo local), url, gmail_message_id, ou conteudo_base64 "
            "(+nome, tamanho_bytes e sha256; so para arquivo pequeno).")

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

def preparar_upload(ctx, args: dict) -> dict:
    """Devolve uma URL assinada para o cliente subir o arquivo direto.

    Este e o caminho certo para arquivo local. O binario vai de PUT ao Storage,
    fora da conversa: nao gasta token, nao tem teto de mensagem e nao depende de
    o modelo reproduzir milhares de caracteres verbatim — que e onde a via
    base64 quebra.

    `tamanho_bytes` e `sha256` sao registrados agora e conferidos depois, quando
    `anexar_arquivo` for chamada com o `upload_token`.
    """
    from firebase_admin import storage

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

    url = storage.bucket().blob(caminho).generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=UPLOAD_TTL_MIN),
        method="PUT",
        content_type=mime,
    )

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

    return {
        "upload_token": token,
        "upload_url": url,
        "metodo": "PUT",
        "content_type": mime,
        "expira_em": expira,
        "instrucao": (
            f"Suba o arquivo com: curl -X PUT -H 'Content-Type: {mime}' "
            f"--data-binary @ARQUIVO '<upload_url>'. Depois chame anexar_arquivo "
            f"com upload_token='{token}' e o task_id."
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
