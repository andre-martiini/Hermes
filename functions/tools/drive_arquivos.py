"""Atualiza o conteudo de um arquivo que JA existe no Drive, no mesmo ID.

O conector do Drive so sabe criar arquivo (`update_file` mexe apenas em titulo e
pasta). Atualizar um documento virava criar outro: ID e link novos, versao antiga
solta e toda referencia ao endereco original quebrada. Aqui o Hermes usa a
credencial do dono (`files().update` com midia) e o arquivo continua sendo o
mesmo; a versao anterior fica no historico de versoes dele.

Escopo estreito de proposito: Google Docs e arquivos de texto. Importar CSV numa
Planilha existente substitui o arquivo inteiro e apaga as outras abas;
Apresentacao, PDF, imagem e .docx nao tem como ser reescritos a partir de texto.

Comportamento comprovado contra o Drive real em 20/09/2026: Doc atualizado com
`text/html`, `text/markdown` e `text/plain` mantem ID, link e tipo (a conversao
gera titulos, listas, tabelas e negrito); arquivo de texto comum mantem ID, nome
e tipo, e o `md5Checksum` devolvido bate com o dos bytes enviados.
"""

from __future__ import annotations

import hashlib
import re

MAX_BYTES = 2 * 1024 * 1024
MIME_DOC = "application/vnd.google-apps.document"
TIPOS_CONTEUDO_DOC = ("text/html", "text/markdown", "text/plain")

_CAMPOS = "id,name,mimeType,trashed,capabilities(canEdit)"
_CAMPOS_ATUALIZADO = "id,name,mimeType,modifiedTime,webViewLink,md5Checksum"

_MOTIVO_TIPO_GOOGLE = {
    "application/vnd.google-apps.folder": "Pasta nao tem conteudo para atualizar.",
    "application/vnd.google-apps.spreadsheet": (
        "Planilhas nao sao suportadas: importar texto substituiria o arquivo inteiro e "
        "apagaria as outras abas. Edite pela interface do Google Sheets."),
    "application/vnd.google-apps.presentation": (
        "Apresentacoes nao sao suportadas: nao ha como reescreve-las a partir de texto."),
}


def _servico_drive():
    from main import get_drive_service

    return get_drive_service()


def _midia(dados: bytes, mime: str):
    from googleapiclient.http import MediaInMemoryUpload

    return MediaInMemoryUpload(dados, mimetype=mime, resumable=False)


def _extrair_id(valor: str) -> str:
    """Aceita o ID puro ou um link do Drive/Docs."""
    valor = valor.strip()
    achado = re.search(r"/d/([A-Za-z0-9_-]{10,})", valor) or re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", valor)
    return achado.group(1) if achado else valor


def _eh_texto(mime: str) -> bool:
    return mime.startswith("text/") or mime == "application/json"


def _erro_do_drive(exc: Exception) -> str:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 404:
        return "Arquivo nao encontrado no Drive (ou o Hermes nao tem acesso a ele)."
    if status == 403:
        return "O Hermes nao tem permissao para editar este arquivo."
    return str(exc)


def atualizar_conteudo(ctx, args: dict) -> dict:
    """Substitui o conteudo de um arquivo do Drive, mantendo ID, link e permissoes."""
    file_id = _extrair_id(str(args.get("file_id") or ""))
    if not file_id:
        return {"erro": "Informe file_id: o ID (ou o link) do arquivo que ja existe no Drive."}

    conteudo = args.get("conteudo")
    if not isinstance(conteudo, str) or not conteudo.strip():
        return {"erro": "conteudo vazio: nada foi alterado. Envie o conteudo COMPLETO novo do arquivo."}
    dados = conteudo.encode("utf-8")
    if len(dados) > MAX_BYTES:
        return {"erro": f"Conteudo com {len(dados) // 1024} KB excede o limite de "
                        f"{MAX_BYTES // 1024 // 1024} MB desta ferramenta. Nada foi alterado."}

    try:
        service = _servico_drive()
        meta = service.files().get(fileId=file_id, fields=_CAMPOS, supportsAllDrives=True).execute()
    except Exception as exc:  # noqa: BLE001
        return {"erro": _erro_do_drive(exc)}

    if meta.get("trashed"):
        return {"erro": "O arquivo esta na lixeira: restaure-o antes de atualizar. Nada foi alterado."}
    if not (meta.get("capabilities") or {}).get("canEdit"):
        return {"erro": "O Hermes nao tem permissao para editar este arquivo. Nada foi alterado."}

    mime = meta.get("mimeType") or ""
    if mime == MIME_DOC:
        tipo = str(args.get("tipo_conteudo") or "text/html")
        if tipo not in TIPOS_CONTEUDO_DOC:
            return {"erro": f"tipo_conteudo '{tipo}' invalido para um Google Doc: use um de "
                            f"{', '.join(TIPOS_CONTEUDO_DOC)}. Nada foi alterado."}
    elif mime.startswith("application/vnd.google-apps."):
        return {"erro": _MOTIVO_TIPO_GOOGLE.get(mime, f"Tipo do Google '{mime}' nao suportado.")
                        + " Nada foi alterado."}
    elif _eh_texto(mime):
        tipo = mime  # arquivo de texto comum mantem o proprio tipo
    else:
        return {"erro": f"Tipo '{mime}' nao suportado: so Google Docs e arquivos de texto "
                        "(text/*, JSON) podem ser reescritos a partir de texto. Nada foi alterado."}

    try:
        atualizado = service.files().update(
            fileId=file_id, media_body=_midia(dados, tipo),
            fields=_CAMPOS_ATUALIZADO, supportsAllDrives=True,
        ).execute()
    except Exception as exc:  # noqa: BLE001
        return {"erro": f"Falha ao atualizar no Drive: {_erro_do_drive(exc)}"}

    verificado = _verificar(service, file_id, mime, dados, atualizado)
    if verificado is False:
        return {"erro": "O Drive gravou um conteudo diferente do enviado (ou o Doc ficou vazio apos a "
                        "conversao). O arquivo FOI alterado: restaure a versao anterior em Arquivo > "
                        "Historico de versoes.", "file_id": file_id}

    try:
        versoes = len(service.revisions().list(fileId=file_id, fields="revisions(id)").execute()
                      .get("revisions", []))
    except Exception:  # noqa: BLE001 — so informativo
        versoes = None

    return {
        "status": "ok",
        "file_id": atualizado.get("id") or file_id,
        "nome": atualizado.get("name") or meta.get("name"),
        "tipo": atualizado.get("mimeType") or mime,
        "link": atualizado.get("webViewLink"),
        "modificado_em": atualizado.get("modifiedTime"),
        "bytes_enviados": len(dados),
        "versoes_no_historico": versoes,
        "verificado": verificado is True,
        "aviso": ("Mesmo arquivo e mesmo link: nada foi criado. A versao anterior continua no "
                  "historico de versoes do Drive (Arquivo > Historico de versoes)."),
    }


def _verificar(service, file_id: str, mime: str, dados: bytes, atualizado: dict):
    """True = confere; False = nao confere; None = nao deu para verificar.

    Texto comum: o md5 que o Drive devolveu tem de ser o dos bytes enviados. Google
    Doc nao tem md5: confere que o texto exportado nao ficou vazio (conversao que
    falha silenciosamente deixaria o documento em branco).
    """
    try:
        if mime == MIME_DOC:
            exportado = service.files().export(fileId=file_id, mimeType="text/plain").execute()
            texto = exportado.decode("utf-8", "replace") if isinstance(exportado, bytes) else str(exportado)
            return bool(texto.replace("\ufeff", "").strip())
        md5 = atualizado.get("md5Checksum")
        if not md5:
            return None
        return md5 == hashlib.md5(dados).hexdigest()
    except Exception:  # noqa: BLE001 — a verificacao nao pode derrubar uma gravacao que ja aconteceu
        return None
