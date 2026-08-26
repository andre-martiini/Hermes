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

## Sobre de onde o binario vem

`conteudo_base64` funciona em qualquer cliente, mas o binario atravessa a
conversa: e caro em token e limitado pelo tamanho da mensagem. Por isso existem
as fontes por referencia — `url` e `gmail_message_id` —, em que o Hermes busca o
arquivo por conta propria e nenhum byte passa pelo modelo. Quando a origem ja e
alcancavel pelo backend, essa e sempre a via melhor.
"""

from __future__ import annotations

import base64
import io
import mimetypes
import uuid
from datetime import datetime, timezone

# O corpo de uma requisicao a Cloud Function tem teto, e base64 infla o binario
# em ~33%. Acima disto a via correta e `url` ou `gmail_message_id`, que nao
# passam o arquivo pelo modelo.
MAX_BYTES = 6 * 1024 * 1024

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
    bruto = args.get("conteudo_base64") or ""
    nome = str(args.get("nome") or "").strip()
    if not nome:
        raise ValueError("`nome` e obrigatorio quando o arquivo vem em conteudo_base64.")
    try:
        # `validate=True`: base64 truncado pela mensagem falha aqui, alto e claro,
        # em vez de virar um arquivo corrompido no Drive.
        dados = base64.b64decode(bruto, validate=True)
    except Exception as exc:
        raise ValueError(f"conteudo_base64 invalido ou truncado: {exc}") from exc
    if not dados:
        raise ValueError("conteudo_base64 vazio.")
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


def _resolver_conteudo(args: dict) -> tuple[bytes, str]:
    if args.get("conteudo_base64"):
        dados, nome = _de_base64(args)
    elif args.get("url"):
        dados, nome = _de_url(args)
    elif args.get("gmail_message_id"):
        dados, nome = _do_gmail(args)
    else:
        raise ValueError(
            "Informe uma origem: conteudo_base64 (+nome), url ou gmail_message_id.")

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
        dados, nome = _resolver_conteudo(args)
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

    atualizacao = {"pool_dados": firestore.ArrayUnion([item])}
    entradas = [{"data": agora, "nota": nota}]
    descricao = str(args.get("descricao") or "").strip()
    if descricao:
        entradas.append({"data": agora, "nota": descricao})
    atualizacao["acompanhamento"] = firestore.ArrayUnion(entradas)
    task_ref.update(atualizacao)

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
