"""Atualiza o conteudo de um arquivo que JA existe no Drive, no mesmo ID.

O conector do Drive so sabe criar arquivo (`update_file` mexe apenas em titulo e
pasta). Atualizar um documento virava criar outro: ID e link novos, versao antiga
solta e toda referencia ao endereco original quebrada. Aqui o Hermes usa a
credencial do dono (`files().update` com midia) e o arquivo continua sendo o
mesmo; a versao anterior fica no historico de versoes dele.

Escopo estreito de proposito: Google Docs e arquivos de texto. Importar CSV numa
Planilha existente substitui o arquivo inteiro e apaga as outras abas;
Apresentacao, PDF, imagem e .docx nao tem como ser reescritos a partir de texto.

Salvaguardas (alem de recusar vazio, lixeira, sem permissao e tipo nao suportado):
so atualiza arquivo que e do dono (`ownedByMe`), para uma injecao de prompt nao
conseguir reescrever documento de colega ou de Drive compartilhado; e recusa um
conteudo muito menor que o atual (`LIMITE_REDUCAO`), que e o jeito mais provavel
de perder texto sem ninguem ver: a ferramenta exige o documento COMPLETO, e um
envio incompleto apagaria o resto. `permitir_reducao=true` libera o encurtamento
de proposito.

Concorrencia otimista: quem le o arquivo antes de reescreve-lo passa o `modifiedTime` que
viu em `esperado_modificado_em`; se o dono editou nesse meio tempo, a gravacao e recusada
em vez de sobrescrever a edicao dele. O Drive nao tem escrita condicional para arquivo:
conferimos o `modifiedTime` logo antes do `update`, entao resta uma janela de milissegundos.
Sem o parametro, o comportamento e o de antes (a ferramenta so avisa para reler).

Comportamento comprovado contra o Drive real em 20/09/2026: Doc atualizado com
`text/html`, `text/markdown` e `text/plain` mantem ID, link e tipo (a conversao
gera titulos, listas, tabelas e negrito); arquivo de texto comum mantem ID, nome
e tipo, e o `md5Checksum` devolvido bate com o dos bytes enviados.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from html.parser import HTMLParser

MAX_BYTES = 2 * 1024 * 1024
MIME_DOC = "application/vnd.google-apps.document"
TIPOS_CONTEUDO_DOC = ("text/html", "text/markdown", "text/plain")
LIMITE_REDUCAO = 0.4
MIN_TAMANHO_PARA_GUARDA = 500  # abaixo disso, encurtar nao e sinal de truncamento

_CAMPOS = "id,name,mimeType,trashed,ownedByMe,driveId,size,capabilities(canEdit)"
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


class _ExtratorTexto(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._ignorar:
            self._ignorar -= 1

    def handle_data(self, data):
        if not self._ignorar:
            self.partes.append(data)


def _colapsar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.replace("\ufeff", "")).strip()


def _texto_visivel(conteudo: str, tipo: str) -> str:
    """Estimativa do texto que o Doc mostrara, para comparar com o atual."""
    if tipo == "text/html":
        extrator = _ExtratorTexto()
        try:
            extrator.feed(conteudo)
            extrator.close()
        except Exception:  # noqa: BLE001 — HTML quebrado: melhor medir o bruto do que falhar
            return _colapsar(conteudo)
        return _colapsar(" ".join(extrator.partes))
    if tipo == "text/markdown":
        sem_links = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", conteudo)
        return _colapsar(re.sub(r"[#*_`>|~-]+", " ", sem_links))
    return _colapsar(conteudo)


def _tamanhos_para_a_guarda(service, file_id, mime, meta, conteudo, tipo, dados):
    """(tamanho atual, tamanho novo) na mesma unidade, ou (None, None) se nao deu para medir."""
    try:
        if mime == MIME_DOC:
            exportado = service.files().export(fileId=file_id, mimeType="text/plain").execute()
            texto = exportado.decode("utf-8", "replace") if isinstance(exportado, bytes) else str(exportado)
            return len(_colapsar(texto)), len(_texto_visivel(conteudo, tipo))
        return int(meta.get("size") or 0), len(dados)
    except Exception:  # noqa: BLE001 — sem medir, a guarda nao bloqueia
        return None, None


def _instante(valor) -> datetime | None:
    """`modifiedTime` (RFC 3339) -> instante com fuso, ou None se nao der para ler."""
    try:
        instante = datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return instante if instante.tzinfo else None


def _modified_time(service, file_id: str):
    return service.files().get(fileId=file_id, fields="modifiedTime",
                               supportsAllDrives=True).execute().get("modifiedTime")


def _versao_mudou(service, file_id: str, esperado_txt: str, esperado: datetime) -> str | None:
    """Erro se o arquivo mudou desde a leitura de quem chama; None se pode gravar.

    Sem conseguir conferir, recusa: quem pediu a checagem nao quer gravar no escuro.
    """
    try:
        atual_txt = _modified_time(service, file_id)
    except Exception as exc:  # noqa: BLE001
        return ("Nao consegui conferir se o arquivo mudou desde a leitura "
                f"({_erro_do_drive(exc)}). Nada foi alterado.")
    atual = _instante(atual_txt)
    if atual is None:
        return "Nao consegui conferir se o arquivo mudou desde a leitura. Nada foi alterado."
    if atual == esperado:
        return None
    return (f"O arquivo foi modificado depois da sua leitura (esperado_modificado_em={esperado_txt}, "
            f"modifiedTime atual={atual_txt}): gravar agora apagaria a edicao do dono. Nada foi alterado. "
            "Releia o arquivo (get_file_metadata e depois read_file_content), incorpore o que mudou e "
            "reenvie o arquivo COMPLETO com o novo modifiedTime em esperado_modificado_em.")


def _modificado_em_assentado(service, file_id: str, do_update):
    """`modifiedTime` depois que o Drive terminou de gravar.

    Num Google Doc o Drive re-carimba o arquivo logo apos o `update` (medido em 20/09/2026:
    o valor devolvido pelo update fica 0,3 a 0,8 s atras do que `files.get` mostra dai em
    diante). Quem reusar o valor devolvido em `esperado_modificado_em` tomaria conflito
    falso, entao le de novo aqui, depois da verificacao. Arquivo de texto nao tem a diferenca.
    """
    try:
        return _modified_time(service, file_id) or do_update
    except Exception:  # noqa: BLE001 — so informativo; cai no valor do update
        return do_update


def _erro_do_drive(exc: Exception) -> str:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 404:
        return "Arquivo nao encontrado no Drive (ou o Gaspar nao tem acesso a ele)."
    if status == 403:
        return "O Gaspar nao tem permissao para editar este arquivo."
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

    esperado_txt = args.get("esperado_modificado_em")
    esperado = None
    if esperado_txt is not None:
        esperado_txt = str(esperado_txt).strip()
        esperado = _instante(esperado_txt)
        if esperado is None:
            return {"erro": f"esperado_modificado_em '{esperado_txt}' invalido: use o `modifiedTime` exato "
                            "que o get_file_metadata devolveu (RFC 3339 com fuso, ex.: "
                            "2026-09-20T15:36:42.677Z). Nada foi alterado."}

    try:
        service = _servico_drive()
        meta = service.files().get(fileId=file_id, fields=_CAMPOS, supportsAllDrives=True).execute()
    except Exception as exc:  # noqa: BLE001
        return {"erro": _erro_do_drive(exc)}

    if meta.get("trashed"):
        return {"erro": "O arquivo esta na lixeira: restaure-o antes de atualizar. Nada foi alterado."}
    if not (meta.get("capabilities") or {}).get("canEdit"):
        return {"erro": "O Gaspar nao tem permissao para editar este arquivo. Nada foi alterado."}

    # `ownedByMe` NAO vem preenchido em item de Drive compartilhado: la o sinal e o `driveId`.
    if meta.get("ownedByMe") is False or meta.get("driveId"):
        return {"erro": "O arquivo pertence a outra pessoa (ou a um Drive compartilhado): por seguranca o "
                        "Gaspar so atualiza arquivos do proprio dono. Edite pela interface do Google. "
                        "Nada foi alterado."}

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

    if not args.get("permitir_reducao"):
        atual, novo = _tamanhos_para_a_guarda(service, file_id, mime, meta, conteudo, tipo, dados)
        if atual is not None and atual >= MIN_TAMANHO_PARA_GUARDA and novo < atual * LIMITE_REDUCAO:
            unidade = "caracteres" if mime == MIME_DOC else "bytes"
            return {"erro": f"O conteudo novo tem {novo} {unidade} e o atual tem {atual} "
                            f"({100 * novo // atual}% do tamanho): parece uma reescrita incompleta e "
                            "apagaria o resto. Reenvie o arquivo COMPLETO; se encurtar e intencional, "
                            "chame de novo com permitir_reducao=true. Nada foi alterado."}

    if esperado is not None:
        conflito = _versao_mudou(service, file_id, esperado_txt, esperado)
        if conflito:
            return {"erro": conflito}

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

    modificado_em = _modificado_em_assentado(service, file_id, atualizado.get("modifiedTime"))

    return {
        "status": "ok",
        "file_id": atualizado.get("id") or file_id,
        "nome": atualizado.get("name") or meta.get("name"),
        "tipo": atualizado.get("mimeType") or mime,
        "link": atualizado.get("webViewLink"),
        "modificado_em": modificado_em,
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
