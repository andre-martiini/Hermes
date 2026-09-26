"""Imagens geradas pelo Hermes: `gerar_imagem` e `editar_imagem`.

Fluxo de uma chamada: valida os parâmetros, confere o teto diário em dólar,
chama o provedor (OpenAI por padrão; Google como opção e plano B quando a OpenAI
cai), e para cada imagem grava:

- o original no Cloud Storage (`imagens_geradas/AAAA-MM/`), com URL pública de
  download — é o `link_download`, que o Claude baixa para slides e páginas;
- uma prévia JPEG pequena ao lado, que o servidor MCP anexa como bloco de imagem
  ao resultado de `consultar_job`, para o Claude VER a imagem sem baixar nada;
- uma cópia no Drive (`Imagens geradas/AAAA-MM`, sob a raiz do Hermes), com
  leitura por link;
- com `task_id`, o vínculo com a ação (pool + diário FILE::JSON);
- um registro em `imagens_geradas/{id}` (prompt, modelo, custo...) e o uso do dia
  em `system_usage/imagens/daily/{dia}`, lido pelo relatório das 19h.

Se o Drive ou o vínculo falharem, a imagem (já paga) continua entregue pelo
Storage, com aviso na resposta.

Canal MCP recebe texto JSON (o `resultado` de `consultar_job` é string); web e
Telegram recebem o Markdown de sempre, `![...](url)`, que o Telegram transforma
em foto.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from llm_providers import openai_images as oi

TZ = ZoneInfo("America/Sao_Paulo")
COLECAO = "imagens_geradas"
PASTA_DRIVE = "Imagens geradas"
PREFIXO_STORAGE = "imagens_geradas/"
TOOLS = ("gerar_imagem", "editar_imagem")

QUALIDADES = ("low", "medium", "high", "xhigh", "max", "auto")
FORMATOS = ("png", "jpeg", "webp")
FUNDOS = {"auto": "auto", "transparente": "transparent", "opaco": "opaque"}
PROVEDORES = ("openai", "google")
MAX_QUANTIDADE = 4
MAX_REFERENCIAS = 8
LADO_PREVIA = 1024

MODELO_GOOGLE = "gemini-3.1-flash-image-preview"
# Sem `usage` de imagem no retorno do Gemini: preço de tabela por imagem 1K.
USD_POR_IMAGEM_GOOGLE = 0.039

_MIME = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}


class Recusa(Exception):
    """Pedido recusado antes de gastar (parâmetro inválido, teto, ação inexistente)."""


# --------------------------------------------------------------------------
# Parâmetros
# --------------------------------------------------------------------------

def _escolha(args: dict, campo: str, validos, padrao: str) -> str:
    valor = str(args.get(campo) or padrao).strip().lower()
    if valor not in validos:
        raise Recusa(f"`{campo}` inválido: {valor!r}. Use um de: {', '.join(validos)}.")
    return valor


def normalizar(args: dict, *, modo: str) -> dict:
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        raise Recusa("`prompt` é obrigatório.")
    provedor = _escolha(args, "provedor", PROVEDORES, "openai")
    padrao_modelo = "sunburst" if modo == "editar" else "flare"
    modelo_curto = _escolha(args, "modelo", oi.MODELOS_CURTOS, padrao_modelo)
    fundo = FUNDOS[_escolha(args, "fundo", tuple(FUNDOS), "auto")]
    formato = _escolha(args, "formato", FORMATOS, "png")
    if fundo == "transparent" and formato == "jpeg":
        raise Recusa("Fundo transparente precisa de formato png ou webp (jpeg não tem transparência).")
    try:
        quantidade = int(args.get("quantidade") or 1)
    except (TypeError, ValueError):
        raise Recusa("`quantidade` precisa ser um número de 1 a 4.")
    if not 1 <= quantidade <= MAX_QUANTIDADE:
        raise Recusa("`quantidade` precisa ser de 1 a 4.")
    proporcao = str(args.get("proporcao") or "1:1").strip()
    if proporcao not in oi.PROPORCOES:
        raise Recusa(f"`proporcao` inválida: {proporcao!r}. Use um de: {', '.join(oi.PROPORCOES)}.")

    modelo = oi.id_do_modelo(modelo_curto)
    return {
        "modo": modo,
        "prompt": prompt,
        "provedor": provedor,
        "modelo": modelo,
        "proporcao": proporcao,
        "tamanho": oi.tamanho_para(proporcao, modelo),
        "qualidade": _escolha(args, "qualidade", QUALIDADES, "medium"),
        "fundo": fundo,
        "formato": formato,
        "quantidade": quantidade,
        "task_id": str(args.get("task_id") or "").strip() or None,
        "nome_arquivo": str(args.get("nome_arquivo") or "").strip() or None,
    }


def _slug(texto: str, palavras: int = 6) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    partes = re.findall(r"[a-zA-Z0-9]+", texto.lower())[:palavras]
    return "-".join(partes) or "imagem"


def _nomes(p: dict, ext: str, total: int, agora: datetime) -> list[str]:
    base = p["nome_arquivo"] or f"{_slug(p['prompt'])}-{agora.astimezone(TZ):%Y%m%d-%H%M}"
    base = re.sub(r"\.(png|jpe?g|webp)$", "", base, flags=re.I)
    if total == 1:
        return [f"{base}.{ext}"]
    return [f"{base}-{i}.{ext}" for i in range(1, total + 1)]


# --------------------------------------------------------------------------
# Teto diário e uso
# --------------------------------------------------------------------------

def _dia(agora: datetime | None = None) -> str:
    return (agora or datetime.now(timezone.utc)).astimezone(TZ).date().isoformat()


def _ref_uso(db, dia: str):
    return db.collection("system_usage").document("imagens").collection("daily").document(dia)


def teto_diario_usd(db) -> float:
    """`config/imagens.teto_diario_usd` no Firestore vence a env `HERMES_IMAGE_DAILY_USD_CAP` (padrão US$ 2)."""
    try:
        snap = db.collection("config").document("imagens").get()
        if snap.exists:
            valor = (snap.to_dict() or {}).get("teto_diario_usd")
            if valor is not None:
                return float(valor)
    except Exception as exc:  # noqa: BLE001
        print(f"[imagens] Falha ao ler config/imagens: {exc}")
    try:
        return float(os.environ.get("HERMES_IMAGE_DAILY_USD_CAP", "2"))
    except ValueError:
        return 2.0


def gasto_hoje_usd(db, dia: str) -> float:
    try:
        snap = _ref_uso(db, dia).get()
        return float((snap.to_dict() or {}).get("estimated_usd") or 0.0) if snap.exists else 0.0
    except Exception as exc:  # noqa: BLE001
        print(f"[imagens] Falha ao ler uso do dia: {exc}")
        return 0.0


def conferir_teto(db, estimativa: float, dia: str) -> None:
    teto = teto_diario_usd(db)
    gasto = gasto_hoje_usd(db, dia)
    if gasto + estimativa > teto:
        raise Recusa(
            f"Teto diário de imagens atingido: já foram US$ {gasto:.2f} hoje, este pedido custaria até "
            f"US$ {estimativa:.2f} e o teto é US$ {teto:.2f}. Para liberar, peça com qualidade menor ou "
            "menos imagens, ou aumente `teto_diario_usd` no documento config/imagens do Firestore."
        )


def registrar_uso(db, *, dia: str, provedor: str, modelo: str, feature: str, n: int,
                  tokens: dict[str, int], custo: float) -> None:
    from firebase_admin import firestore

    chave_modelo = re.sub(r"[^A-Za-z0-9_]+", "_", modelo)
    try:
        _ref_uso(db, dia).set({
            "date": dia,
            "calls": firestore.Increment(1),
            "imagens": firestore.Increment(n),
            "estimated_usd": firestore.Increment(round(custo, 6)),
            "provedores": {provedor: {"imagens": firestore.Increment(n),
                                      "estimated_usd": firestore.Increment(round(custo, 6))}},
            "models": {chave_modelo: {"calls": firestore.Increment(1), "imagens": firestore.Increment(n)}},
            "features": {feature: {"calls": firestore.Increment(1), "imagens": firestore.Increment(n)}},
            "tokens": {faixa: firestore.Increment(int(valor)) for faixa, valor in tokens.items()},
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
    except Exception as exc:  # noqa: BLE001 — telemetria nunca derruba a entrega
        print(f"[imagens] Falha ao registrar uso: {exc}")
    print(f"[ImagensUsage] {json.dumps({'feature': feature, 'provedor': provedor, 'modelo': modelo, 'n': n, 'tokens': tokens, 'usd': custo})}")


# --------------------------------------------------------------------------
# Imagens de referência (editar_imagem)
# --------------------------------------------------------------------------

_ORIGENS = ("drive_file_id", "upload_token", "url", "gmail_message_id")


def _como_imagem_de_entrada(dados: bytes, nome: str, *, exigir_alfa: bool = False) -> tuple[str, bytes, str]:
    """Aceita o que o Pillow abrir; PNG/JPEG/WebP seguem como vieram, o resto vira PNG."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise Recusa(f"'{nome}' não é uma imagem legível ({exc}).")
    fmt = (img.format or "").lower()
    if exigir_alfa:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        saida = io.BytesIO()
        img.save(saida, "PNG")
        return (_trocar_ext(nome, "png"), saida.getvalue(), "image/png")
    if fmt in ("png", "jpeg", "webp"):
        return (nome, dados, _MIME[fmt])
    saida = io.BytesIO()
    img.convert("RGBA" if "A" in img.mode else "RGB").save(saida, "PNG")
    return (_trocar_ext(nome, "png"), saida.getvalue(), "image/png")


def _trocar_ext(nome: str, ext: str) -> str:
    return re.sub(r"\.[A-Za-z0-9]+$", "", nome or "imagem") + f".{ext}"


def resolver_referencias(ctx, origens, mascara) -> tuple[list[tuple[str, bytes, str]], tuple | None]:
    from tools.anexar_arquivo import _resolver_conteudo

    if not isinstance(origens, list) or not origens:
        raise Recusa("`imagens` precisa ser uma lista com ao menos uma origem (drive_file_id, upload_token, url ou gmail_message_id).")
    if len(origens) > MAX_REFERENCIAS:
        raise Recusa(f"No máximo {MAX_REFERENCIAS} imagens de referência por pedido.")

    def _uma(origem) -> tuple[bytes, str]:
        if isinstance(origem, str):
            origem = {"url": origem} if origem.startswith("http") else {"drive_file_id": origem}
        if not isinstance(origem, dict) or sum(1 for k in _ORIGENS if origem.get(k)) != 1:
            raise Recusa("Cada imagem precisa de exatamente uma origem: drive_file_id, upload_token, url ou gmail_message_id.")
        if origem.get("conteudo_base64"):
            raise Recusa("conteudo_base64 não é aceito aqui; use drive_file_id, url ou preparar_upload.")
        try:
            return _resolver_conteudo(ctx, origem)
        except ValueError as exc:
            raise Recusa(str(exc))

    referencias = [_como_imagem_de_entrada(*_uma(o)) for o in origens]
    masc = None
    if mascara:
        dados, nome = _uma(mascara)
        masc = _como_imagem_de_entrada(dados, nome, exigir_alfa=True)
    return referencias, masc


# --------------------------------------------------------------------------
# Provedores
# --------------------------------------------------------------------------

def _gerar_google(ctx, p: dict, referencias=None) -> oi.Resultado:
    from google.genai import types

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio=p["proporcao"], image_size="1K"),
        thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
    )
    conteudo = [p["prompt"]] + [types.Part.from_bytes(data=d, mime_type=m) for _, d, m in (referencias or [])]
    imagens = []
    for _ in range(p["quantidade"]):
        resp = ctx.genai_client.models.generate_content(model=MODELO_GOOGLE, contents=conteudo, config=config)
        for cand in getattr(resp, "candidates", None) or []:
            for parte in getattr(getattr(cand, "content", None), "parts", None) or []:
                dados = getattr(getattr(parte, "inline_data", None), "data", None)
                if dados:
                    imagens.append(dados)
                    break
            break
    if not imagens:
        raise oi.ErroImagem("resposta", "Gemini não devolveu imagem")
    return oi.Resultado(modelo=MODELO_GOOGLE, imagens=imagens, prompts_revisados=[None] * len(imagens),
                        tokens={}, custo_usd=round(USD_POR_IMAGEM_GOOGLE * len(imagens), 6))


def _chamar(ctx, p: dict, referencias, mascara) -> tuple[oi.Resultado, list[str]]:
    avisos: list[str] = []
    if p["provedor"] == "google":
        if mascara is not None:
            avisos.append("O provedor Google não usa máscara; a instrução vale para a imagem toda.")
        return _gerar_google(ctx, p, referencias), avisos
    try:
        client = oi.cliente(ctx.db)
        comuns = dict(modelo=p["modelo"], prompt=p["prompt"], tamanho=p["tamanho"], qualidade=p["qualidade"],
                      fundo=p["fundo"], formato=p["formato"], n=p["quantidade"])
        if p["modo"] == "editar":
            return oi.editar(client, imagens=referencias, mascara=mascara, **comuns), avisos
        return oi.gerar(client, **comuns), avisos
    except oi.ErroImagem as erro:
        # Plano B só quando a OpenAI está fora; recusa, crédito e verificação vão ao usuário.
        if erro.tipo not in ("indisponivel", "timeout"):
            raise
        print(f"[imagens] OpenAI indisponível ({erro.detalhe}); caindo para o Google.")
        avisos.append(f"{erro} Gerada pelo plano B (Google Gemini), em 1K e sem as opções da OpenAI.")
        p["provedor"] = "google"
        return _gerar_google(ctx, p, referencias), avisos


# --------------------------------------------------------------------------
# Onde a imagem fica
# --------------------------------------------------------------------------

def _info(dados: bytes) -> tuple[str, int, int]:
    from PIL import Image

    img = Image.open(io.BytesIO(dados))
    fmt = (img.format or "png").lower()
    return ("jpeg" if fmt == "jpg" else fmt), img.width, img.height


def _previa(dados: bytes) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(dados))
    img.thumbnail((LADO_PREVIA, LADO_PREVIA))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fundo = Image.new("RGB", img.size, (255, 255, 255))
        fundo.paste(img, mask=img.split()[-1])
        img = fundo
    elif img.mode != "RGB":
        img = img.convert("RGB")
    saida = io.BytesIO()
    img.save(saida, "JPEG", quality=82, optimize=True)
    return saida.getvalue()


def _pasta_drive(service, db, mes: str) -> str | None:
    raiz = None
    try:
        snap = db.collection("system").document("config").get()
        if snap.exists:
            raiz = (snap.to_dict() or {}).get("googleDriveFolderId")
    except Exception as exc:  # noqa: BLE001
        print(f"[imagens] Não foi possível ler system/config: {exc}")

    def _garantir(nome: str, pai: str | None) -> str:
        consulta = f"mimeType='application/vnd.google-apps.folder' and trashed=false and name='{nome}'"
        if pai:
            consulta += f" and '{pai}' in parents"
        achadas = service.files().list(q=consulta, fields="files(id)", pageSize=1).execute().get("files", [])
        if achadas:
            return achadas[0]["id"]
        corpo = {"name": nome, "mimeType": "application/vnd.google-apps.folder"}
        if pai:
            corpo["parents"] = [pai]
        return service.files().create(body=corpo, fields="id").execute()["id"]

    return _garantir(mes, _garantir(PASTA_DRIVE, raiz))


def _publicar_drive(service, pasta: str | None, nome: str, dados: bytes, mime: str) -> tuple[str, str]:
    from googleapiclient.http import MediaIoBaseUpload

    corpo = {"name": nome}
    if pasta:
        corpo["parents"] = [pasta]
    arquivo = service.files().create(
        body=corpo, media_body=MediaIoBaseUpload(io.BytesIO(dados), mimetype=mime, resumable=True),
        fields="id, webViewLink",
    ).execute()
    try:
        service.permissions().create(fileId=arquivo["id"], body={"type": "anyone", "role": "reader"}).execute()
    except Exception as exc:  # noqa: BLE001
        print(f"[imagens] Falha ao liberar leitura de {arquivo['id']}: {exc}")
    return arquivo["id"], arquivo.get("webViewLink") or f"https://drive.google.com/file/d/{arquivo['id']}/view"


def _drive_service():
    from main import get_drive_service

    return get_drive_service()


def _bucket():
    from hermes_core_logic import _get_hermes_storage_bucket

    return _get_hermes_storage_bucket()


def _url_publica(blob) -> str:
    from hermes_core_logic import _blob_public_url

    return _blob_public_url(blob)


# --------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------

def executar(ctx, args: dict, *, modo: str) -> str | dict:
    feature = "editar_imagem" if modo == "editar" else "gerar_imagem"
    agora = datetime.now(timezone.utc)
    dia = _dia(agora)
    try:
        p = normalizar(args or {}, modo=modo)
        if p["task_id"] and not ctx.db.collection("tarefas").document(p["task_id"]).get().exists:
            raise Recusa(f"Ação '{p['task_id']}' não encontrada; nada foi gerado.")
        referencias, mascara = ([], None)
        if modo == "editar":
            referencias, mascara = resolver_referencias(ctx, args.get("imagens"), args.get("mascara"))
        if p["provedor"] == "openai":
            estimativa = oi.estimar_usd(modelo=p["modelo"], tamanho=p["tamanho"], qualidade=p["qualidade"],
                                        n=p["quantidade"], referencias=len(referencias))
        else:
            estimativa = USD_POR_IMAGEM_GOOGLE * p["quantidade"]
        conferir_teto(ctx.db, estimativa, dia)
        resultado, avisos = _chamar(ctx, p, referencias, mascara)
    except Recusa as exc:
        return _falha(ctx, str(exc))
    except oi.ErroImagem as exc:
        return _falha(ctx, str(exc))
    except Exception as exc:  # noqa: BLE001
        import traceback

        print(f"[imagens] Erro inesperado: {exc}\n{traceback.format_exc()}")
        return _falha(ctx, f"Erro ao gerar imagem: {exc}")

    # Daqui para baixo a imagem já foi paga: registrar o uso primeiro e, de
    # resto, entregar o que der, com aviso, em vez de falhar.
    registrar_uso(ctx.db, dia=dia, provedor=p["provedor"], modelo=resultado.modelo, feature=feature,
                  n=len(resultado.imagens), tokens=resultado.tokens, custo=resultado.custo_usd)
    entregues = _entregar(ctx, p, resultado, agora, avisos)
    return _resposta(ctx, p, resultado, entregues, avisos)


def _falha(ctx, mensagem: str) -> str | dict:
    # No MCP, dict com `erro` vira job em erro (`mcp_jobs`), com a mensagem intacta.
    if getattr(ctx, "canal", "") == "mcp":
        return {"erro": mensagem}
    return f"ERRO|{mensagem}"


def _entregar(ctx, p: dict, resultado: oi.Resultado, agora: datetime, avisos: list[str]) -> list[dict]:
    from firebase_admin import firestore

    mes = f"{agora.astimezone(TZ):%Y-%m}"
    bucket = _bucket()
    infos = [_info(d) for d in resultado.imagens]
    nomes = _nomes(p, infos[0][0].replace("jpeg", "jpg"), len(resultado.imagens), agora)
    custo_por_imagem = round(resultado.custo_usd / len(resultado.imagens), 6)

    service = pasta = None
    try:
        service = _drive_service()
        pasta = _pasta_drive(service, ctx.db, mes)
    except Exception as exc:  # noqa: BLE001
        print(f"[imagens] Drive indisponível: {exc}")
        avisos.append(f"Não gravei no Drive ({exc}); a imagem está no link de download.")
        service = None

    entregues = []
    for i, (dados, (fmt, largura, altura), nome) in enumerate(zip(resultado.imagens, infos, nomes)):
        img_id = uuid.uuid4().hex[:12]
        mime = _MIME.get(fmt, "image/png")
        caminho = f"{PREFIXO_STORAGE}{mes}/{img_id}.{'jpg' if fmt == 'jpeg' else fmt}"
        blob = bucket.blob(caminho)
        blob.upload_from_string(dados, content_type=mime)
        link_download = _url_publica(blob)

        caminho_previa = f"{PREFIXO_STORAGE}{mes}/{img_id}_previa.jpg"
        try:
            bucket.blob(caminho_previa).upload_from_string(_previa(dados), content_type="image/jpeg")
        except Exception as exc:  # noqa: BLE001
            print(f"[imagens] Falha na prévia de {img_id}: {exc}")
            caminho_previa = None

        drive_id = link_drive = None
        if service is not None:
            try:
                drive_id, link_drive = _publicar_drive(service, pasta, nome, dados, mime)
            except Exception as exc:  # noqa: BLE001
                print(f"[imagens] Falha ao gravar {nome} no Drive: {exc}")
                avisos.append(f"'{nome}' não foi para o Drive ({exc}); está no link de download.")

        pool_item_id = None
        if p["task_id"]:
            try:
                pool_item_id = _anexar_na_acao(ctx.db, p["task_id"], nome=nome,
                                               link=link_drive or link_download, drive_id=drive_id, prompt=p["prompt"])
            except Exception as exc:  # noqa: BLE001
                print(f"[imagens] Falha ao anexar {nome} na ação {p['task_id']}: {exc}")
                avisos.append(f"'{nome}' não foi anexada à ação ({exc}).")

        revisado = resultado.prompts_revisados[i] if i < len(resultado.prompts_revisados) else None
        registro = {
            "id": img_id,
            "tool": "editar_imagem" if p["modo"] == "editar" else "gerar_imagem",
            "uid": getattr(ctx, "user_uid", None),
            "canal": getattr(ctx, "canal", None),
            "prompt": p["prompt"],
            "prompt_revisado": revisado,
            "provedor": p["provedor"],
            "modelo": resultado.modelo,
            "proporcao": p["proporcao"],
            "tamanho": f"{largura}x{altura}",
            "qualidade": p["qualidade"] if p["provedor"] == "openai" else None,
            "formato": fmt,
            "fundo": p["fundo"],
            "custo_estimado_usd": custo_por_imagem,
            "tokens": resultado.tokens,
            "nome": nome,
            "storage_path": caminho,
            "previa_path": caminho_previa,
            "link_download": link_download,
            "drive_file_id": drive_id,
            "link_visualizacao": link_drive,
            "task_id": p["task_id"],
            "pool_item_id": pool_item_id,
            "criado_em": firestore.SERVER_TIMESTAMP,
        }
        try:
            ctx.db.collection(COLECAO).document(img_id).set(registro)
        except Exception as exc:  # noqa: BLE001
            print(f"[imagens] Falha ao registrar {img_id}: {exc}")
        registro.pop("criado_em")
        entregues.append(registro)
    return entregues


def _anexar_na_acao(db, task_id: str, *, nome: str, link: str, drive_id: str | None, prompt: str) -> str:
    """Mesmo formato de `tools/anexar_arquivo.py`: item no pool + arquivo e nota no diário."""
    from firebase_admin import firestore

    agora = datetime.now(timezone.utc).isoformat()
    item = {"id": str(uuid.uuid4())[:8], "tipo": "arquivo", "valor": link, "nome": nome, "data_criacao": agora}
    if drive_id:
        item["drive_file_id"] = drive_id
    arquivo = "FILE::JSON::" + json.dumps({"n": nome, "v": link}, ensure_ascii=False)
    nota = f"Imagem gerada pelo Hermes: {prompt[:300]}"
    db.collection("tarefas").document(task_id).update({
        "pool_dados": firestore.ArrayUnion([item]),
        "acompanhamento": firestore.ArrayUnion([{"data": agora, "nota": arquivo}, {"data": agora, "nota": nota}]),
    })
    return item["id"]


def _resposta(ctx, p: dict, resultado: oi.Resultado, entregues: list[dict], avisos: list[str]) -> str:
    markdown = "\n\n".join(f"![{_alt(p['prompt'])}]({e['link_download']})" for e in entregues)
    if getattr(ctx, "canal", "") != "mcp":
        # Web e Telegram: o Markdown de sempre (o Telegram vira foto a partir dele).
        extra = "".join(f"\n\n⚠️ {a}" for a in avisos)
        drive = [e["link_visualizacao"] for e in entregues if e.get("link_visualizacao")]
        rodape = f"\n\n*(Gerada via {resultado.modelo}." + (f" Drive: {drive[0]}" if len(drive) == 1 else "") + ")*"
        return markdown + rodape + extra

    campos = ("id", "nome", "drive_file_id", "link_visualizacao", "link_download", "tamanho", "formato",
              "prompt_revisado", "custo_estimado_usd", "task_id", "pool_item_id", "previa_path")
    return json.dumps({
        "status": "ok",
        "imagens": [{**{c: e.get(c) for c in campos}, "markdown": f"![{_alt(p['prompt'])}]({e['link_download']})"}
                    for e in entregues],
        "provedor": p["provedor"],
        "modelo": resultado.modelo,
        "qualidade": p["qualidade"] if p["provedor"] == "openai" else None,
        "tokens": resultado.tokens,
        "custo_estimado_usd": resultado.custo_usd,
        "avisos": avisos,
        "como_usar": (
            "As prévias vêm anexadas a este resultado como imagem: olhe-as antes de responder. "
            "O arquivo original em resolução cheia está em link_download (URL pública, baixa direto) — "
            "use-o em slides, páginas e documentos; link_visualizacao abre no Drive."
        ),
    }, ensure_ascii=False)


def _alt(prompt: str) -> str:
    texto = re.sub(r"[\[\]\n]+", " ", prompt).strip()
    return texto[:80] or "Imagem gerada"


# --------------------------------------------------------------------------
# Prévia visível no MCP
# --------------------------------------------------------------------------

def blocos_de_previa(resultado_texto, *, limite: int = MAX_QUANTIDADE) -> list[dict]:
    """Blocos MCP `image` com as prévias de um resultado de `gerar_imagem`/`editar_imagem`.

    Chamado pelo servidor MCP ao montar a resposta de `consultar_job`. Nunca
    levanta: sem prévia, o resultado continua com os links em texto.
    """
    try:
        dados = json.loads(resultado_texto) if isinstance(resultado_texto, str) else resultado_texto
        caminhos = [i.get("previa_path") for i in (dados or {}).get("imagens") or []]
        caminhos = [c for c in caminhos if isinstance(c, str) and c.startswith(PREFIXO_STORAGE)][:limite]
        if not caminhos:
            return []
        bucket = _bucket()
        return [{"type": "image", "mimeType": "image/jpeg",
                 "data": base64.b64encode(bucket.blob(c).download_as_bytes()).decode("ascii")}
                for c in caminhos]
    except Exception as exc:  # noqa: BLE001
        print(f"[imagens] Falha ao montar prévia para o MCP: {exc}")
        return []
