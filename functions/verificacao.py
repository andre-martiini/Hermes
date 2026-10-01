"""Confirmação só do que foi verificado.

Toda frase de sucesso dita ao usuário ("registrei", "salvei") sai de
`montar_confirmacao`, a partir de um `ResultadoOperacao` produzido pelo código
depois de RELER o que foi gravado. O modelo pode redigir o tom em volta, mas
não decide se deu certo: em 28 e 30/09/2026 o Gemini do Telegram respondeu
"peso registrado" duas vezes sem ferramenta nenhuma, e nada foi gravado.

Três estados, nunca dois: `verificado`, `falhou` (sempre com motivo) e
`pendente` (aceito, mas ainda não concluído — "enfileirado" nunca é "enviado").
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Literal, Optional

Estado = Literal["verificado", "falhou", "pendente"]
ESTADOS = ("verificado", "falhou", "pendente")

_TOLERANCIA = 1e-6


@dataclass
class ResultadoOperacao:
    estado: Estado
    operacao: str
    alvo: str
    valor_esperado: Optional[dict] = None
    valor_relido: Optional[dict] = None
    motivo: Optional[str] = None
    run_id: Optional[str] = None

    def __post_init__(self):
        if self.estado not in ESTADOS:
            raise ValueError(f"estado inválido: {self.estado!r}")
        if self.estado == "falhou" and not (self.motivo or "").strip():
            raise ValueError("estado 'falhou' exige motivo")

    @property
    def ok(self) -> bool:
        return self.estado == "verificado"

    def to_dict(self) -> dict:
        return asdict(self)


def falhou(operacao: str, alvo: str, motivo: str, esperado: Optional[dict] = None) -> ResultadoOperacao:
    return ResultadoOperacao("falhou", operacao, alvo, valor_esperado=esperado, motivo=motivo)


def _referencia(db, caminho: str):
    partes = [p for p in str(caminho or "").split("/") if p]
    if len(partes) < 2 or len(partes) % 2:
        raise ValueError(f"caminho de documento inválido: {caminho!r}")
    ref = db.collection(partes[0]).document(partes[1])
    for i in range(2, len(partes), 2):
        ref = ref.collection(partes[i]).document(partes[i + 1])
    return ref


def _iguais(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= _TOLERANCIA
    return a == b


def _fmt(valor) -> str:
    if isinstance(valor, float):
        return f"{valor:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return repr(valor) if valor is None else str(valor)


def verificar_escrita(db, caminho: str, esperado: dict, operacao: str = "") -> ResultadoOperacao:
    """Relê o documento em `caminho` e compara só os campos de `esperado`."""
    try:
        snap = _referencia(db, caminho).get()
        dados = (snap.to_dict() or {}) if snap.exists else None
    except Exception as exc:
        return falhou(operacao, caminho, f"não consegui reler o registro gravado ({exc})", esperado)
    if dados is None:
        return falhou(operacao, caminho, "o registro não aparece ao reler o banco", esperado)

    relido = {campo: dados.get(campo) for campo in esperado}
    divergentes = [c for c in esperado if not _iguais(esperado[c], relido[c])]
    if divergentes:
        detalhe = "; ".join(f"{c} relido {_fmt(relido[c])}, esperado {_fmt(esperado[c])}" for c in divergentes)
        return ResultadoOperacao("falhou", operacao, caminho, valor_esperado=dict(esperado),
                                 valor_relido=relido, motivo=f"o valor gravado não confere ({detalhe})")
    return ResultadoOperacao("verificado", operacao, caminho, valor_esperado=dict(esperado), valor_relido=relido)


def _data_br(iso) -> str:
    texto = str(iso or "")
    if len(texto) >= 10 and texto[4] == "-" and texto[7] == "-":
        return f"{texto[8:10]}/{texto[5:7]}/{texto[0:4]}"
    return texto


def _peso_registrado(res: ResultadoOperacao) -> str:
    relido = res.valor_relido or {}
    return f"Peso registrado: {_fmt(float(relido['weight']))} kg em {_data_br(relido.get('date'))}."


# operacao -> (o que se tentou fazer, frase de sucesso a partir do valor RELIDO)
_OPERACOES: dict[str, tuple[str, Callable[[ResultadoOperacao], str]]] = {
    "registrar_peso": ("registrar o peso", _peso_registrado),
}


def montar_confirmacao(res: ResultadoOperacao) -> str:
    """Única fonte de texto de sucesso. Usa `valor_relido`, nunca `valor_esperado`."""
    descricao, sucesso = _OPERACOES.get(res.operacao, ("concluir a operação", None))
    if res.estado == "verificado":
        if sucesso and res.valor_relido:
            return sucesso(res)
        return f"Feito e conferido: {res.alvo}."
    if res.estado == "pendente":
        return "Aceito, aguardando conclusão."
    return f"Não consegui {descricao}: {res.motivo}"
