"""Vários compromissos por chat e substituição explícita (P07 do plano de
autonomia, passo 3).

Lógica pura -- sem I/O e sem wiring. O registro é uma tupla imutável de
`Compromisso`; cada operação devolve um registro novo. Dois compromissos do
mesmo chat são independentes: substituir um nunca mexe no outro. Substituição só acontece por relação explícita (`substituir`), nunca por
semelhança de texto, e nunca atravessa chats.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from autonomy.commitments import chave_compromisso

ABERTO = "aberto"
SUBSTITUIDO = "substituido"
ESTADOS = (ABERTO, SUBSTITUIDO)


@dataclass(frozen=True)
class Compromisso:
    chave: str
    chat_id: str
    texto: str
    estado: str = ABERTO
    substituido_por: str | None = None

    def __post_init__(self):
        if not all(type(v) is str for v in (self.chave, self.chat_id, self.texto)) or (
            self.substituido_por is not None and type(self.substituido_por) is not str
        ):
            raise ValueError("chave, chat_id e texto devem ser texto")
        object.__setattr__(self, "texto", self.texto.strip())
        if not self.texto.strip() or not self.texto.isprintable():
            raise ValueError("texto do compromisso é obrigatório e imprimível")
        if self.estado not in ESTADOS:
            raise ValueError("estado inválido")
        if (self.estado == SUBSTITUIDO) != (self.substituido_por is not None):
            raise ValueError("substituido_por só existe em compromisso substituído")
        if self.substituido_por is not None and (
            not isinstance(self.substituido_por, str) or self.substituido_por == self.chave
        ):
            raise ValueError("substituido_por inválido")
        partes = self.chave.split("__")
        try:
            esperada = chave_compromisso(self.chat_id, partes[1], int(partes[2]))
        except (ValueError, IndexError):
            raise ValueError("chave incoerente com o chat") from None
        if len(partes) != 3 or esperada != self.chave:
            raise ValueError("chave incoerente com o chat")


def abrir(registro, chat_id, mensagem_id, indice, texto) -> tuple[Compromisso, ...]:
    """Acrescenta um compromisso. Chave repetida é erro (idempotência fica com
    quem chama: ver `existe`)."""
    registro = _registro(registro)
    _texto(chat_id)
    _texto(mensagem_id)
    if type(indice) is not int or type(texto) is not str:
        raise ValueError("indice deve ser int e texto deve ser texto")
    chave = chave_compromisso(chat_id, mensagem_id, indice)
    if existe(registro, chave):
        raise ValueError("compromisso já registrado")
    novo = Compromisso(chave, chat_id, texto)
    return tuple.__add__(registro, (novo,))


def existe(registro, chave) -> bool:
    _texto(chave)
    return any(c.chave == chave for c in _registro(registro))


def ativos(registro, chat_id) -> tuple[Compromisso, ...]:
    _texto(chat_id)
    return tuple(
        c for c in _registro(registro) if c.chat_id == chat_id and c.estado == ABERTO
    )


def substituir(registro, chave_antiga, chave_nova) -> tuple[Compromisso, ...]:
    """O compromisso novo substitui o antigo (relação explícita). Exige: ambos
    existem, mesmo chat, chaves diferentes, antigo ainda aberto e novo aberto
    (sem ciclo nem substituição por algo já substituído)."""
    registro = _registro(registro)
    _texto(chave_antiga)
    _texto(chave_nova)
    if chave_antiga == chave_nova:
        raise ValueError("um compromisso não substitui a si mesmo")
    antigo = _buscar(registro, chave_antiga)
    novo = _buscar(registro, chave_nova)
    if antigo.chat_id != novo.chat_id:
        raise ValueError("substituição não atravessa chats")
    if antigo.estado != ABERTO:
        raise ValueError("compromisso antigo não está aberto")
    if novo.estado != ABERTO:
        raise ValueError("compromisso novo não está aberto")
    return tuple(
        replace(c, estado=SUBSTITUIDO, substituido_por=chave_nova)
        if c.chave == chave_antiga
        else c
        for c in registro
    )


def _buscar(registro, chave) -> Compromisso:
    for c in registro:
        if c.chave == chave:
            return c
    raise ValueError("compromisso inexistente")


def _texto(valor) -> None:
    if type(valor) is not str:
        raise ValueError("chave e chat_id devem ser texto")


def _registro(registro) -> tuple[Compromisso, ...]:
    if type(registro) is not tuple or not all(type(c) is Compromisso for c in registro):
        raise ValueError("registro deve ser tupla de Compromisso")
    chaves = [c.chave for c in registro]
    if len(set(chaves)) != len(chaves):
        raise ValueError("registro com chaves duplicadas")
    por_chave = {c.chave: c for c in registro}
    for c in registro:
        if c.substituido_por is not None:
            alvo = por_chave.get(c.substituido_por)
            if alvo is None or alvo.chat_id != c.chat_id:
                raise ValueError("substituido_por aponta para compromisso inválido")
    for c in registro:
        visto = {c.chave}
        atual = c
        while atual.substituido_por is not None:
            if atual.substituido_por in visto:
                raise ValueError("registro com ciclo de substituição")
            visto.add(atual.substituido_por)
            atual = por_chave[atual.substituido_por]
    return registro
