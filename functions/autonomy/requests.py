"""Contratos e lógica pura de estados/lease/geração para pedidos duráveis
(P04 do plano de autonomia, docs/plano-hermes-autonomo-2026-09-06.md, seção
4.4 "Pedido" e seção 4.5 "Reserva, retomada e idempotência", passo 1 do
pacote: "Implementar os estados, leases e gerações da seção 4").

Define o vocabulário novo sem tocar no I/O existente -- `agent_requests.py`
continua sendo a única fonte que fala com Firestore hoje, e o pedido legado
(`STATUS_PENDENTE`/`STATUS_EM_ANDAMENTO`/`STATUS_CONCLUIDO`/`STATUS_ERRO` em
`agent_requests.py`) não é alterado por este módulo. Mesmo padrão
incremental já usado em P02 sub-entrega 1/N (`autonomy/contracts.py`): só
tipos e lógica pura primeiro (testável sem Firestore), wiring numa
sub-entrega seguinte -- ver `proximo_pacote` do bloco desta sub-entrega em
docs/autonomia/execucao.md.

Estados novos (seção 4.4, "Pedido"): pendente → reservado → em_andamento →
verificando → concluido. Caminhos adicionais: aguardando_aprovacao,
aguardando_externo, retentativa_agendada, resultado_desconhecido,
falha_final e cancelado. "O status legado erro é preservado para registros
antigos e normalizado na leitura; novos erros distinguem recuperável e
terminal" -- por isso `RequestStatus` inclui `ERRO_LEGADO` como estado
terminal compatível para leitura/normalização de registros antigos, mas
nenhum código novo deve produzi-lo (usar `FALHA_FINAL` ou
`RETENTATIVA_AGENDADA`, que já distinguem terminal de recuperável).

A máquina de estados (`_TRANSICOES_PERMITIDAS`) é uma primeira modelagem
das transições implícitas na seção 4.4 -- o plano descreve os estados e diz
"toda espera registra motivo, responsável, condição de retomada e próxima
revisão" (isso para MISSÃO; para pedido, só lista os nomes dos estados sem
desenhar o grafo completo). As arestas abaixo são a interpretação desta
sub-entrega, documentada para poder ser revisada por quem vier depois, não
uma citação literal do plano.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class RequestStatus(str, Enum):
    """Os estados de um pedido durável -- seção 4.4, "Pedido"."""

    PENDENTE = "pendente"
    RESERVADO = "reservado"
    EM_ANDAMENTO = "em_andamento"
    VERIFICANDO = "verificando"
    CONCLUIDO = "concluido"
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"
    AGUARDANDO_EXTERNO = "aguardando_externo"
    RETENTATIVA_AGENDADA = "retentativa_agendada"
    RESULTADO_DESCONHECIDO = "resultado_desconhecido"
    FALHA_FINAL = "falha_final"
    CANCELADO = "cancelado"
    #: Só para leitura/normalização de registros legados (`agent_requests.py`
    #: usa "erro" hoje). Código novo nunca deve transicionar PARA este
    #: estado -- ver `_TRANSICOES_PERMITIDAS` (nenhum outro estado o inclui
    #: como destino permitido).
    ERRO_LEGADO = "erro"


#: Estados finais: nenhuma transição de saída (seção 4.4: "concluido e erro
#: são terminais (não regridem nem se sobrescrevem)" -- generalizado aqui
#: para os demais terminais novos do pedido).
ESTADOS_TERMINAIS: frozenset[RequestStatus] = frozenset({
    RequestStatus.CONCLUIDO,
    RequestStatus.FALHA_FINAL,
    RequestStatus.CANCELADO,
    RequestStatus.ERRO_LEGADO,
})


_TRANSICOES_PERMITIDAS: dict[RequestStatus, frozenset[RequestStatus]] = {
    RequestStatus.PENDENTE: frozenset({
        RequestStatus.RESERVADO,
        RequestStatus.CANCELADO,
    }),
    RequestStatus.RESERVADO: frozenset({
        RequestStatus.EM_ANDAMENTO,
        # Lease expira ou é liberada sem efeito: volta para a fila.
        RequestStatus.PENDENTE,
        RequestStatus.CANCELADO,
    }),
    RequestStatus.EM_ANDAMENTO: frozenset({
        RequestStatus.VERIFICANDO,
        RequestStatus.AGUARDANDO_APROVACAO,
        RequestStatus.AGUARDANDO_EXTERNO,
        RequestStatus.RETENTATIVA_AGENDADA,
        RequestStatus.RESULTADO_DESCONHECIDO,
        RequestStatus.FALHA_FINAL,
        RequestStatus.CANCELADO,
    }),
    RequestStatus.VERIFICANDO: frozenset({
        RequestStatus.CONCLUIDO,
        RequestStatus.RETENTATIVA_AGENDADA,
        RequestStatus.FALHA_FINAL,
        RequestStatus.RESULTADO_DESCONHECIDO,
    }),
    RequestStatus.AGUARDANDO_APROVACAO: frozenset({
        RequestStatus.EM_ANDAMENTO,
        RequestStatus.CANCELADO,
    }),
    RequestStatus.AGUARDANDO_EXTERNO: frozenset({
        RequestStatus.EM_ANDAMENTO,
        RequestStatus.VERIFICANDO,
        RequestStatus.RESULTADO_DESCONHECIDO,
        RequestStatus.CANCELADO,
    }),
    RequestStatus.RETENTATIVA_AGENDADA: frozenset({
        RequestStatus.RESERVADO,
        RequestStatus.PENDENTE,
        RequestStatus.FALHA_FINAL,
        RequestStatus.CANCELADO,
    }),
    # "Operação externa incerta vai para reconciliação" (seção 4.5, item 8) --
    # nunca volta direto para EM_ANDAMENTO: precisa passar por VERIFICANDO
    # (reconciliação confirma o efeito) ou re-agendar tentativa.
    RequestStatus.RESULTADO_DESCONHECIDO: frozenset({
        RequestStatus.VERIFICANDO,
        RequestStatus.RETENTATIVA_AGENDADA,
        RequestStatus.FALHA_FINAL,
    }),
    RequestStatus.CONCLUIDO: frozenset(),
    RequestStatus.FALHA_FINAL: frozenset(),
    RequestStatus.CANCELADO: frozenset(),
    RequestStatus.ERRO_LEGADO: frozenset(),
}


def transicoes_permitidas(status_atual: RequestStatus) -> frozenset[RequestStatus]:
    """Destinos permitidos a partir de `status_atual`. Estado desconhecido
    (não deveria acontecer com o enum tipado, mas defende contra uso via
    valor cru) devolve conjunto vazio -- falha fechada, não permissiva."""
    return _TRANSICOES_PERMITIDAS.get(status_atual, frozenset())


def validar_transicao(status_atual: RequestStatus, status_novo: RequestStatus) -> tuple[bool, str]:
    """Valida se `status_atual -> status_novo` é uma transição permitida.

    Devolve (True, "") quando válida, ou (False, motivo_legível) quando não.
    Não faz I/O nem grava nada -- quem chama decide o que fazer com o
    resultado (mesmo espírito de `agent_requests.validar_transicao`, que
    esta função substitui/estende para o conjunto novo de estados quando o
    wiring acontecer)."""
    if status_atual == status_novo:
        return False, f"pedido já está em '{status_atual.value}'"
    if status_atual in ESTADOS_TERMINAIS:
        return False, f"'{status_atual.value}' é terminal, não transiciona para nada"
    permitidas = transicoes_permitidas(status_atual)
    if status_novo not in permitidas:
        return False, (
            f"transição '{status_atual.value}' -> '{status_novo.value}' não é permitida "
            f"(permitidas a partir de '{status_atual.value}': "
            f"{sorted(s.value for s in permitidas) or 'nenhuma'})"
        )
    return True, ""


# ---------------------------------------------------------------------------
# Lease e geração -- seção 4.5, itens 1-5
# ---------------------------------------------------------------------------

#: "lease de 5 minutos" (seção 4.5, item de parâmetros iniciais propostos).
DEFAULT_LEASE_SEGUNDOS = 5 * 60
#: "renovação a cada minuto".
DEFAULT_RENOVACAO_SEGUNDOS = 60
#: "máximo de 3 tentativas automáticas".
DEFAULT_MAX_TENTATIVAS = 3
#: "backoff com jitter em torno de 1, 5 e 20 minutos". Tentativas além da
#: última posição reusam o último patamar (ver `calcular_backoff_segundos`).
BACKOFF_BASE_SEGUNDOS: tuple[float, ...] = (60.0, 5 * 60.0, 20 * 60.0)
#: Fração de jitter (+-20%) -- ponto de partida razoável; o plano pede
#: "jitter" mas não especifica a amplitude exata.
JITTER_FRACAO = 0.2


@dataclass(frozen=True)
class Lease:
    """Reserva exclusiva de um pedido por um executor -- seção 4.5, itens
    1-5: "Servidor emite lease_token, generation monotônica e expires_at."

    `generation` cresce a cada nova reserva do MESMO pedido (mesmo que seja
    o mesmo executor reservando de novo depois de uma lease anterior
    expirar) -- é o mecanismo de fencing que impede um executor que perdeu a
    reserva de concluir ou produzir efeito depois (seção 4.5, item 5:
    "Consumidor anterior perde direito de concluir ou produzir nova
    operação depois de perder a reserva"). Um token sozinho não bastaria
    porque, em tese, um executor lento poderia reapresentar um token válido
    depois de uma corrida perdida por outra reserva -- a `generation`
    monotônica torna esse replay detectável mesmo que dois tokens
    colidissem (o que `secrets.token_urlsafe` já torna praticamente
    impossível, mas a defesa em camadas é o ponto do fencing por geração)."""

    lease_token: str
    generation: int
    executor_id: str
    expires_at: datetime

    def __post_init__(self) -> None:
        _exigir_tz_aware(self.expires_at, "expires_at")


def _exigir_tz_aware(dt: datetime, nome_param: str) -> None:
    """Falha cedo e com mensagem clara quando um datetime "naive" (sem
    timezone) chega onde um instante absoluto é esperado -- achado da 1a
    rodada de revisão adversarial (P04 sub-entrega 1/N): sem esta checagem,
    `lease_expirada`/`lease_valida_para_acao` levantavam
    `TypeError: can't compare offset-naive and offset-aware datetimes` numa
    comparação distante da causa raiz (o `agora`/`expires_at` naive
    construído bem antes), em vez de um erro claro no ponto de entrada."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(
            f"{nome_param} deve ser timezone-aware (ex.: datetime.now(timezone.utc)); "
            f"recebido: {dt!r}"
        )


def gerar_lease_token() -> str:
    """Token de reserva opaco e imprevisível. `secrets.token_urlsafe`, não
    hash determinístico de request_id/executor_id -- duas reservas do mesmo
    pedido pelo mesmo executor nunca devem produzir o mesmo token."""
    return secrets.token_urlsafe(24)


def nova_lease(
    executor_id: str,
    generation_anterior: int,
    agora: datetime | None = None,
    duracao_segundos: float = DEFAULT_LEASE_SEGUNDOS,
) -> Lease:
    """Emite uma nova lease para `executor_id`, incrementando a geração.

    `generation_anterior` é 0 para a primeira reserva de um pedido que nunca
    foi reservado antes (nenhum código de produção decide esse valor ainda
    nesta sub-entrega -- quem vier a persistir pedidos com lease precisa ler
    a geração atual do documento e passá-la aqui)."""
    executor_id_limpo = str(executor_id or "").strip()
    if not executor_id_limpo:
        raise ValueError("executor_id é obrigatório para emitir uma lease.")
    if duracao_segundos <= 0:
        raise ValueError("duracao_segundos deve ser positivo.")
    if generation_anterior < 0:
        raise ValueError("generation_anterior não pode ser negativa.")
    if agora is not None:
        _exigir_tz_aware(agora, "agora")

    agora_resolvido = agora or datetime.now(timezone.utc)
    return Lease(
        lease_token=gerar_lease_token(),
        generation=int(generation_anterior) + 1,
        executor_id=executor_id_limpo,
        expires_at=agora_resolvido + timedelta(seconds=duracao_segundos),
    )


def lease_expirada(lease: Lease, agora: datetime | None = None) -> bool:
    """`agora >= expires_at` conta como expirada (limite inclusivo -- o
    instante exato de expiração já não cobre mais o executor)."""
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_resolvido = agora or datetime.now(timezone.utc)
    return agora_resolvido >= lease.expires_at


def lease_valida_para_acao(
    lease_atual: Lease | None,
    token_apresentado: str,
    generation_apresentada: int,
    agora: datetime | None = None,
) -> tuple[bool, str]:
    """Fencing -- seção 4.5, itens 4-5: "início, heartbeat, checkpoint e
    conclusão exigem o mesmo token/geração ainda válidos."

    Compara o token com `secrets.compare_digest` (tempo constante -- mesmo
    padrão já esperado de qualquer comparação de segredo/token neste
    projeto, evita side-channel por tempo de resposta).

    `token_apresentado`/`generation_apresentada` vêm de um CONSUMIDOR (seção
    4.5, item 1: "capacidades declaradas" no pedido) -- entrada não confiável
    por definição, então esta função nunca deve deixar escapar uma exceção
    por causa de um valor malformado apresentado por ele; um valor
    inválido/malformado é só mais um jeito de "não confere", nunca um erro
    de programação do chamador (ao contrário de `agora`/`generation_anterior`
    em `nova_lease`, que são responsabilidade de quem chama esta função, não
    do consumidor externo, e por isso continuam levantando ValueError).
    Achado da 1a rodada de revisão adversarial (P04 sub-entrega 1/N): sem
    isto, `generation_apresentada` não-numérica levantava `ValueError` e
    `token_apresentado` não-ASCII levantava `TypeError` de dentro de
    `secrets.compare_digest`, em vez de reprovar a ação normalmente."""
    if lease_atual is None:
        return False, "nenhuma reserva ativa para este pedido"
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    if lease_expirada(lease_atual, agora=agora):
        return False, "lease expirada"
    try:
        generation_normalizada = int(generation_apresentada)
    except (TypeError, ValueError, OverflowError):
        # OverflowError (2a rodada de revisão adversarial, P04 sub-entrega
        # 1/N): int() de um float/Decimal infinito (`float("inf")`,
        # `Decimal("Infinity")`) levanta OverflowError, não ValueError --
        # `json.loads` aceita "Infinity"/"-Infinity" como extensão por
        # padrão, então um consumidor podia enviar isso num payload e
        # crashar esta função exatamente do jeito que o fix anterior
        # deveria ter fechado.
        return False, "geração apresentada não é um inteiro válido"
    if lease_atual.generation != generation_normalizada:
        return False, "geração não confere (reserva perdida para outro executor)"
    try:
        token_confere = secrets.compare_digest(
            lease_atual.lease_token, str(token_apresentado or "")
        )
    except TypeError:
        # secrets.compare_digest recusa comparar strings não-ASCII -- um
        # token de consumidor com esse formato nunca poderia mesmo assim
        # coincidir com o token real (gerado por secrets.token_urlsafe,
        # sempre ASCII), então é só mais um "não confere".
        token_confere = False
    if not token_confere:
        return False, "token de reserva não confere"
    return True, ""


def calcular_backoff_segundos(tentativa: int, rng: object | None = None) -> float:
    """Backoff com jitter -- seção 4.5: "backoff com jitter em torno de 1, 5
    e 20 minutos", para até `DEFAULT_MAX_TENTATIVAS` tentativas automáticas.

    `tentativa` é 1-indexado (a primeira retentativa é `tentativa=1`).
    Tentativas além do maior patamar declarado reusam esse último patamar
    (o plano não define um patamar além de 20 minutos).

    `rng` aceita qualquer objeto com `.uniform(a, b)` (ex.: `random.Random`
    com seed fixa em teste) -- por padrão usa `secrets.SystemRandom()`, que
    também expõe `.uniform`."""
    if tentativa < 1:
        raise ValueError("tentativa deve ser >= 1 (1-indexada).")

    indice = min(tentativa, len(BACKOFF_BASE_SEGUNDOS)) - 1
    base = BACKOFF_BASE_SEGUNDOS[indice]
    escolhedor = rng if rng is not None else secrets.SystemRandom()
    jitter = escolhedor.uniform(-JITTER_FRACAO, JITTER_FRACAO)
    # Piso de 1s: jitter negativo no patamar mínimo (60s) nunca deve produzir
    # backoff zero/negativo.
    return max(1.0, base * (1 + jitter))
