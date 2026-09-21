"""Sinal de resposta esperada - nivel 1, modo sombra.

Quando uma etapa fica `aguardando_terceiro`, ninguem percebe sozinho que quem se
aguarda mandou mensagem: hoje o dono precisa avisar o Claude. Este modulo so
OBSERVA. A cada mensagem recebida ele registra em `sinais_resposta_sombra` se ela
veio de alguem que alguma etapa aguarda, para medir volume e acerto antes de
qualquer aviso. Nao cria item na fila de atencao, nao notifica e nao grava o
texto da mensagem: so o id, o chat e a confianca do casamento.

Duas metades:
- `reconstruir_indice` roda na sincronizacao horaria, com as tarefas que ela ja
  leu, e grava `system/esperas_index` (uma linha por etapa aguardando terceiro).
- `processar_mensagem` roda no gatilho de cada mensagem nova e so le esse indice
  (cache de 5 min), nunca a colecao `tarefas`.

Atras de `system/settings.atencao.resposta_esperada.enabled` (padrao desligado).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from firebase_admin import firestore

import atencao

INDICE_DOC = "esperas_index"
SOMBRA_COLLECTION = "sinais_resposta_sombra"
CONTADORES_COLLECTION = "sinais_resposta_contadores"
MAX_MATCHES_POR_MENSAGEM = 10
_CACHE_TTL_SEG = 300
_ESTADO_AGUARDANDO = "aguardando_terceiro"
_ORDEM_CONFIANCA = {"alta": 0, "media": 1, "baixa": 2}

_STOPWORDS = {"de", "da", "do", "das", "dos", "com", "para", "por", "em", "no", "na", "que"}
# Palavras de coletivo e de instituicao nao identificam quem escreveu: "Ifes" casaria com
# qualquer contato do instituto.
_GENERICOS = {
    "equipe", "time", "setor", "gestao", "colegas", "pessoal", "diretoria", "direcao", "reitoria",
    "ifes", "campus", "proen", "proad", "sigex", "sispnaes", "cgu", "tjes", "fapes", "mec",
    "analistas", "tecnicos", "senior", "grupo", "whatsapp",
}

_CACHE: dict = {"expira_em": 0.0, "habilitado": False, "entradas": []}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _tokens(texto) -> list[str]:
    palavras = re.findall(r"[a-z0-9]+", _sem_acento(str(texto or "")).lower())
    return [p for p in palavras if len(p) >= 3 and p not in _STOPWORDS]


def _fora_dos_parenteses(texto: str) -> str:
    fora = re.sub(r"\([^()]*\)", " ", texto)
    return re.split(r"\s[—–-]\s", fora)[0]


def e_espera_do_dono_ou_ia(aguardando_de) -> bool:
    """Etapa que espera o proprio dono ou uma IA nao e resposta de terceiro."""
    palavras = re.findall(r"[a-z0-9]+", _sem_acento(_fora_dos_parenteses(str(aguardando_de or ""))).lower())
    if not palavras:
        return False
    if palavras[0] in {"desenvolvedor", "claude"}:
        return True
    return palavras[0] == "andre" and (len(palavras) == 1 or palavras[1] in {"e", "ou", "araujo"})


def _parece_nome_proprio(trecho: str) -> bool:
    palavras = trecho.split()
    return 2 <= len(palavras) <= 4 and all(p[0].isupper() for p in palavras)


def extrair_nomes(aguardando_de) -> list[dict]:
    """Nomes citados em `aguardando_de` (texto livre), do mais especifico ao ambiguo."""
    texto = str(aguardando_de or "").strip()
    if not texto:
        return []
    partes = re.split(r"\s*(?:/|,|;|\se\s|\sou\s)\s*", _fora_dos_parenteses(texto))
    partes += [p for p in re.findall(r"\(([^()]*)\)", texto) if _parece_nome_proprio(p.strip())]
    vistos: set = set()
    nomes = []
    for parte in partes:
        if parte.strip().isupper():
            continue  # sigla de orgao (PROAD, TJES), nao nome de pessoa
        uteis = tuple(t for t in _tokens(parte) if t not in _GENERICOS)
        if not uteis or uteis in vistos:
            continue
        vistos.add(uteis)
        nomes.append({"texto": parte.strip()[:60], "tokens": list(uteis), "ambiguo": len(uteis) == 1})
    return nomes[:6]


def _tarefa_ativa(tarefa: dict) -> bool:
    status = str(tarefa.get("status") or "").strip().lower()
    return status in atencao._ACTIVE_STATUS_ALIASES or status in atencao._STANDBY_STATUS_ALIASES


def construir_indice(tarefas: list[dict], anterior: list[dict] | None, agora: datetime) -> tuple[list[dict], int]:
    """Uma entrada por etapa `aguardando_terceiro` de acao ativa. `desde` e o
    primeiro instante em que o indice viu essa espera (nao ha carimbo de entrada
    no plano); mensagens anteriores a ele nao contam."""
    desde_anterior = {
        (e.get("acao_id"), e.get("etapa_id"), e.get("aguardando_de")): e.get("desde")
        for e in (anterior or [])
    }
    entradas: list[dict] = []
    esperas_do_dono = 0
    for tarefa in tarefas:
        if not _tarefa_ativa(tarefa):
            continue
        vinculos = [v for v in (tarefa.get("whatsapp_vinculos") or []) if isinstance(v, dict) and v.get("chat_id")]
        chat_ids = [str(v["chat_id"]) for v in vinculos]
        grupos = [str(v["chat_id"]) for v in vinculos if v.get("is_group")]
        for etapa in tarefa.get("plano_acao") or []:
            if not isinstance(etapa, dict) or etapa.get("estado") != _ESTADO_AGUARDANDO:
                continue
            de = str(etapa.get("aguardando_de") or "").strip()[:200]
            if de and e_espera_do_dono_ou_ia(de):
                esperas_do_dono += 1
                continue
            chave = (tarefa["id"], etapa.get("id"), de)
            entradas.append({
                "acao_id": tarefa["id"],
                "acao_titulo": str(tarefa.get("titulo") or "")[:70],
                "etapa_id": etapa.get("id"),
                "aguardando_de": de,
                "nomes": extrair_nomes(de),
                "chat_ids": chat_ids,
                "grupos": grupos,
                "desde": desde_anterior.get(chave) or agora.isoformat(),
            })
    entradas.sort(key=lambda e: (str(e["acao_id"]), str(e["etapa_id"])))
    return entradas, esperas_do_dono


def _como_datetime(valor) -> datetime | None:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, str):
        try:
            parsed = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _melhor_nome(nomes: list[dict], remetente: list[str]) -> dict | None:
    """Candidato cujos tokens estao todos no nome do remetente; o mais longo vence."""
    presentes = set(remetente)
    casados = [n for n in nomes if n["tokens"] and set(n["tokens"]) <= presentes]
    return max(casados, key=lambda n: len(n["tokens"])) if casados else None


def casar_mensagem(mensagem: dict, entradas: list[dict]) -> dict:
    """Quais esperas esta mensagem recebida pode estar respondendo.

    Em grupo so conta o AUTOR: mensagem de outra pessoa num grupo vinculado nao
    e resposta de quem se aguarda (fica so no contador de suprimidas)."""
    resultado = {"considerada": False, "matches": [], "truncados": 0, "suprimidas_grupo_sem_autor": 0}
    chat_id = str(mensagem.get("chat_id") or "")
    if mensagem.get("from_me") or not chat_id or chat_id.endswith(("@broadcast", "@newsletter")):
        return resultado
    grupo = bool(mensagem.get("is_group")) or chat_id.endswith("@g.us")
    quando = _como_datetime(mensagem.get("timestamp"))
    resultado.update(considerada=True, grupo=grupo, chat_id=chat_id, quando=quando.isoformat() if quando else None)
    if grupo:
        remetente = _tokens(mensagem.get("author_name"))
    else:
        remetente = _tokens(mensagem.get("contact_name") or mensagem.get("author_name") or mensagem.get("chat_name"))

    matches = []
    for entrada in entradas:
        desde = _como_datetime(entrada.get("desde"))
        if quando and desde and quando < desde:
            continue
        vinculado = chat_id in (entrada.get("chat_ids") or [])
        nome = _melhor_nome(entrada.get("nomes") or [], remetente)
        if grupo:
            if vinculado and nome:
                origem, confianca = "grupo_vinculado_autor", ("media" if nome["ambiguo"] else "alta")
            elif vinculado:
                resultado["suprimidas_grupo_sem_autor"] += 1
                continue
            elif nome:
                origem, confianca = "autor_em_grupo_nao_vinculado", "baixa"
            else:
                continue
        else:
            if vinculado and (nome or not entrada.get("nomes")):
                origem, confianca = "chat_vinculado", "alta"
            elif vinculado:
                origem, confianca = "chat_vinculado_sem_nome", "media"
            elif nome:
                origem, confianca = "nome_do_contato", ("baixa" if nome["ambiguo"] else "media")
            else:
                continue
        matches.append({
            "acao_id": entrada["acao_id"],
            "etapa_id": entrada["etapa_id"],
            "aguardando_de": str(entrada.get("aguardando_de") or "")[:80],
            "origem": origem,
            "confianca": confianca,
        })
    matches.sort(key=lambda m: _ORDEM_CONFIANCA[m["confianca"]])
    resultado["truncados"] = max(0, len(matches) - MAX_MATCHES_POR_MENSAGEM)
    resultado["matches"] = matches[:MAX_MATCHES_POR_MENSAGEM]
    return resultado


def _flag_habilitada(db) -> bool:
    doc = db.collection("system").document("settings").get()
    settings = doc.to_dict() if doc.exists else {}
    cfg = ((settings or {}).get("atencao") or {}).get("resposta_esperada") or {}
    return bool(cfg.get("enabled", False))


def _ler_indice(db) -> list[dict]:
    doc = db.collection("system").document(INDICE_DOC).get()
    return list((doc.to_dict() or {}).get("entradas") or []) if doc.exists else []


def _limpar_cache() -> None:
    _CACHE.update(expira_em=0.0, habilitado=False, entradas=[])


def _estado(db) -> tuple[bool, list[dict]]:
    agora = datetime.now(timezone.utc).timestamp()
    if agora >= _CACHE["expira_em"]:
        habilitado = _flag_habilitada(db)
        _CACHE.update(
            expira_em=agora + _CACHE_TTL_SEG,
            habilitado=habilitado,
            entradas=_ler_indice(db) if habilitado else [],
        )
    return _CACHE["habilitado"], _CACHE["entradas"]


def reconstruir_indice(db, tarefas_snapshot, agora: datetime | None = None) -> dict:
    """Chamada pela sincronizacao horaria com as tarefas que ela ja leu."""
    if not _flag_habilitada(db):
        return {"desligado": True, "gravado": False}
    agora = agora or datetime.now(timezone.utc)
    tarefas = []
    for snap in tarefas_snapshot:
        dados = snap.to_dict() or {}
        dados["id"] = snap.id
        tarefas.append(dados)
    anterior = _ler_indice(db)
    entradas, esperas_do_dono = construir_indice(tarefas, anterior, agora)
    stats = {"esperas_terceiros": len(entradas), "esperas_dono_ou_ia": esperas_do_dono}
    if entradas == anterior:
        return {**stats, "gravado": False}
    db.collection("system").document(INDICE_DOC).set({**stats, "entradas": entradas, "atualizado_em": agora.isoformat()})
    return {**stats, "gravado": True}


def processar_mensagem(db, mensagem: dict, agora: datetime | None = None) -> dict | None:
    """Gatilho de cada mensagem nova. Grava so o id e o casamento, nunca o texto."""
    habilitado, entradas = _estado(db)
    if not habilitado or not entradas:
        return None
    resultado = casar_mensagem(mensagem, entradas)
    if not resultado["considerada"]:
        return None
    agora = agora or datetime.now(timezone.utc)
    contadores = {"avaliadas": firestore.Increment(1)}
    if resultado["suprimidas_grupo_sem_autor"]:
        contadores["suprimidas_grupo_sem_autor"] = firestore.Increment(resultado["suprimidas_grupo_sem_autor"])
    if resultado["matches"]:
        contadores["com_match"] = firestore.Increment(1)
        for confianca in {m["confianca"] for m in resultado["matches"]}:
            contadores[f"conf_{confianca}"] = firestore.Increment(1)
        doc_id = str(mensagem.get("id") or mensagem.get("wa_message_id") or "")
        if doc_id:
            db.collection(SOMBRA_COLLECTION).document(doc_id).set({
                "message_doc_id": doc_id,
                "chat_id": resultado["chat_id"],
                "is_group": resultado["grupo"],
                "message_type": str(mensagem.get("message_type") or ""),
                "message_ts": resultado["quando"],
                "matches": resultado["matches"],
                "truncados": resultado["truncados"],
                "modo": "sombra",
                "criado_em": agora.isoformat(),
            })
    db.collection(CONTADORES_COLLECTION).document(agora.strftime("%Y-%m-%d")).set(contadores, merge=True)
    return resultado
