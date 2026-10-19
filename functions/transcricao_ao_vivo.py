"""Transcrição ao vivo gravada aos poucos, para o Claude ler durante a reunião.

A ferramenta "Reuniões em Tempo Real" (src/hooks/useMeetingRecordingEngine.ts)
transcreve no navegador (Deepgram) e, sem isto, só gravava a reunião inteira ao
clicar em Parar. Agora ela manda os trechos finais a cada ~10 s pela callable
`transcricaoAoVivo`, e o servidor os acrescenta em:

    transcricoes_ao_vivo/{sessao_id}
        id, uid, titulo, fonte, url, estado ("ao_vivo" | "encerrada"),
        iniciada_em, atualizada_em, ultimo_trecho_em, encerrada_em,
        ultimo_seq (0 = nenhum trecho), ultimo_lote, total_caracteres,
        terceiros_presentes, reuniao_id (o doc de `reunioes` salvo no fim)
    transcricoes_ao_vivo/{sessao_id}/trechos/{seq:08d}
        seq (1, 2, 3... sem buraco), t_inicio, t_fim (segundos desde o início),
        falante ("Você" = microfone, "Reunião" = áudio da tela), texto,
        criado_em, lote_id

Só acrescenta: o seq é dado aqui, numa transação que confere o `base_seq` do
navegador, e nenhum trecho gravado muda depois. O navegador manda um lote por
vez e, se a resposta se perder, reenvia o mesmo `lote_id`: o servidor reconhece
o lote já gravado e não duplica. A coleção é fechada ao cliente nas regras
(firestore.rules); só esta callable e as tools de leitura a tocam. Sem IA.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from firebase_admin import firestore
from firebase_functions import https_fn, options

COLECAO = "transcricoes_ao_vivo"
SUBCOLECAO = "trechos"
FONTE_REUNIOES = "reunioes_gaspar"
AO_VIVO = "ao_vivo"
ENCERRADA = "encerrada"

MAX_TRECHOS_POR_LOTE = 100
MAX_TEXTO_TRECHO = 4000
MAX_CARACTERES_LOTE = 60000
MAX_FALANTE = 40
MAX_TITULO = 200
MAX_URL = 500
MAX_SEGUNDOS = 48 * 3600  # uma sessão não passa de dois dias

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ErroTranscricao(Exception):
    """Pedido recusado; `codigo` é o FunctionsErrorCode e `mensagem` vai ao navegador."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def id_trecho(seq: int) -> str:
    """Id do documento do trecho: o seq com zeros à esquerda (ordena como texto também)."""
    return f"{int(seq):08d}"


def _id_valido(valor, campo: str) -> str:
    texto = str(valor or "").strip()
    if not _ID_RE.match(texto):
        raise ErroTranscricao("invalid-argument", f"{campo} inválido")
    return texto


def _texto_curto(valor, limite: int) -> str | None:
    if valor is None:
        return None
    texto = " ".join(str(valor).split())
    return texto[:limite] or None


def _url(valor) -> str | None:
    texto = _texto_curto(valor, MAX_URL)
    if texto and not re.match(r"^https?://", texto, re.IGNORECASE):
        return None
    return texto


def _segundos(valor) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return 0.0
    if valor != valor:  # NaN
        return 0.0
    return round(min(max(float(valor), 0.0), MAX_SEGUNDOS), 2)


def _base_seq(valor) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise ErroTranscricao("invalid-argument", "base_seq inválido")
    return valor


def normalizar_trechos(brutos) -> list[dict]:
    """Valida e limpa os trechos de um lote, na ordem em que vieram.

    Trecho sem texto é descartado (não ocupa seq). Recusa o lote inteiro se
    vier fora do formato ou grande demais: aceitar pela metade abriria buraco.
    """
    if brutos is None:
        return []
    if not isinstance(brutos, list):
        raise ErroTranscricao("invalid-argument", "trechos precisa ser uma lista")
    if len(brutos) > MAX_TRECHOS_POR_LOTE:
        raise ErroTranscricao("invalid-argument", f"no máximo {MAX_TRECHOS_POR_LOTE} trechos por lote")
    saida, total = [], 0
    for bruto in brutos:
        if not isinstance(bruto, dict):
            raise ErroTranscricao("invalid-argument", "trecho fora do formato")
        texto = bruto.get("texto")
        if not isinstance(texto, str):
            raise ErroTranscricao("invalid-argument", "trecho sem texto")
        texto = " ".join(texto.split())
        if not texto:
            continue
        if len(texto) > MAX_TEXTO_TRECHO:
            raise ErroTranscricao("invalid-argument", f"trecho acima de {MAX_TEXTO_TRECHO} caracteres")
        total += len(texto)
        inicio, fim = _segundos(bruto.get("t_inicio")), _segundos(bruto.get("t_fim"))
        saida.append({
            "t_inicio": min(inicio, fim),
            "t_fim": max(inicio, fim),
            "falante": _texto_curto(bruto.get("falante"), MAX_FALANTE),
            "texto": texto,
        })
    if total > MAX_CARACTERES_LOTE:
        raise ErroTranscricao("invalid-argument", f"lote acima de {MAX_CARACTERES_LOTE} caracteres")
    return saida


def _ref_sessao(db, sessao_id: str):
    return db.collection(COLECAO).document(sessao_id)


def _em_transacao(db, corpo):
    """Roda `corpo(tx)` numa transação do Firestore (os testes trocam esta função)."""
    return firestore.transactional(corpo)(db.transaction())


def iniciar(db, uid: str | None, dados: dict) -> dict:
    """Cria a sessão com o id que o navegador escolheu. Repetir não cria outra."""
    sessao_id = _id_valido(dados.get("sessao_id"), "sessao_id")
    ref = _ref_sessao(db, sessao_id)
    agora = _agora()

    def corpo(tx):
        snap = ref.get(transaction=tx)
        if snap.exists:
            atual = snap.to_dict() or {}
            return {"status": "ja_existia", "sessao_id": sessao_id,
                    "ultimo_seq": int(atual.get("ultimo_seq") or 0), "estado": atual.get("estado")}
        tx.set(ref, {
            "id": sessao_id,
            "uid": uid,
            "titulo": _texto_curto(dados.get("titulo"), MAX_TITULO) or "Reunião sem título",
            "fonte": FONTE_REUNIOES,
            "url": _url(dados.get("url")),
            "estado": AO_VIVO,
            "iniciada_em": agora,
            "atualizada_em": agora,
            "ultimo_trecho_em": None,
            "encerrada_em": None,
            "ultimo_seq": 0,
            "ultimo_lote": None,
            "total_caracteres": 0,
            "terceiros_presentes": bool(dados.get("terceiros_presentes")),
            "reuniao_id": None,
        })
        return {"status": "criada", "sessao_id": sessao_id, "ultimo_seq": 0, "estado": AO_VIVO}

    return _em_transacao(db, corpo)


def anexar(db, dados: dict) -> dict:
    """Acrescenta um lote depois de `base_seq`. Sem trechos, só marca que a sessão segue viva.

    Respostas: `gravado` (seq novos), `ja_gravado` (o mesmo lote já entrou),
    `conflito` (o servidor está em outro seq: o navegador reenvia a partir dele),
    `vivo` (sinal de vida sem texto novo).
    """
    sessao_id = _id_valido(dados.get("sessao_id"), "sessao_id")
    trechos = normalizar_trechos(dados.get("trechos"))
    lote_id = _id_valido(dados.get("lote_id"), "lote_id") if trechos else None
    base = _base_seq(dados.get("base_seq", 0)) if trechos else 0
    ref = _ref_sessao(db, sessao_id)
    agora = _agora()

    def corpo(tx):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise ErroTranscricao("not-found", "sessão de transcrição não encontrada")
        atual = snap.to_dict() or {}
        ultimo = int(atual.get("ultimo_seq") or 0)
        if not trechos:
            if atual.get("estado") == AO_VIVO:
                tx.update(ref, {"atualizada_em": agora})
            return {"status": "vivo", "ultimo_seq": ultimo, "estado": atual.get("estado")}
        if atual.get("ultimo_lote") == lote_id:
            return {"status": "ja_gravado", "ultimo_seq": ultimo}
        if atual.get("estado") != AO_VIVO:
            raise ErroTranscricao("failed-precondition", "a sessão já foi encerrada")
        if base != ultimo:
            return {"status": "conflito", "ultimo_seq": ultimo}
        seq, caracteres = ultimo, 0
        for trecho in trechos:
            seq += 1
            caracteres += len(trecho["texto"])
            tx.set(ref.collection(SUBCOLECAO).document(id_trecho(seq)),
                   {"seq": seq, **trecho, "criado_em": agora, "lote_id": lote_id})
        tx.update(ref, {
            "ultimo_seq": seq,
            "ultimo_lote": lote_id,
            "atualizada_em": agora,
            "ultimo_trecho_em": agora,
            "total_caracteres": int(atual.get("total_caracteres") or 0) + caracteres,
        })
        return {"status": "gravado", "ultimo_seq": seq}

    return _em_transacao(db, corpo)


def encerrar(db, dados: dict) -> dict:
    """Marca a sessão como encerrada. Repetir não muda nada; os trechos continuam legíveis."""
    sessao_id = _id_valido(dados.get("sessao_id"), "sessao_id")
    ref = _ref_sessao(db, sessao_id)
    agora = _agora()

    def corpo(tx):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise ErroTranscricao("not-found", "sessão de transcrição não encontrada")
        atual = snap.to_dict() or {}
        if atual.get("estado") == ENCERRADA:
            return {"status": "ja_encerrada", "ultimo_seq": int(atual.get("ultimo_seq") or 0)}
        tx.update(ref, {"estado": ENCERRADA, "encerrada_em": agora, "atualizada_em": agora})
        return {"status": "encerrada", "ultimo_seq": int(atual.get("ultimo_seq") or 0)}

    return _em_transacao(db, corpo)


def vincular(db, dados: dict) -> dict:
    """Depois de salvar a reunião: título definitivo e o id do doc em `reunioes`."""
    sessao_id = _id_valido(dados.get("sessao_id"), "sessao_id")
    mudancas = {}
    titulo = _texto_curto(dados.get("titulo"), MAX_TITULO)
    if titulo:
        mudancas["titulo"] = titulo
    if dados.get("reuniao_id"):
        mudancas["reuniao_id"] = _id_valido(dados.get("reuniao_id"), "reuniao_id")
    ref = _ref_sessao(db, sessao_id)
    if not ref.get().exists:
        raise ErroTranscricao("not-found", "sessão de transcrição não encontrada")
    if mudancas:
        ref.update(mudancas)
    return {"status": "vinculada", **mudancas}


_ACOES = {"anexar": anexar, "encerrar": encerrar, "vincular": vincular}


def processar(db, uid: str | None, dados: dict) -> dict:
    """Despacha a ação da callable. Separado dela para os testes."""
    acao = str((dados or {}).get("acao") or "")
    if acao == "iniciar":
        return iniciar(db, uid, dados)
    if acao in _ACOES:
        return _ACOES[acao](db, dados)
    raise ErroTranscricao("invalid-argument", "ação desconhecida")


def atender(req) -> dict:
    """Corpo da callable: só o dono (mesma checagem das regras), depois `processar`."""
    from main import _require_internal_user, get_db

    _require_internal_user(req)
    try:
        return processar(get_db(), req.auth.uid if req.auth else None, req.data or {})
    except ErroTranscricao as exc:
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode(exc.codigo), message=exc.mensagem)


@https_fn.on_call(memory=options.MemoryOption.MB_256, timeout_sec=30)
def transcricaoAoVivo(req: https_fn.CallableRequest) -> dict:
    """Recebe da ferramenta de reuniões: iniciar, anexar (lote ou sinal de vida), encerrar, vincular."""
    return atender(req)
