"""Sweep de pedidos duráveis com lease vencida (P04 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, passo 7 do pacote: "Criar sweep de
leases vencidos, resultado desconhecido, retry agendado e falha final, com
fila de diagnóstico").

Mesmo padrão incremental das sub-entregas anteriores de P04: lógica pura,
sem I/O -- quem varre o armazenamento em busca de pedidos com lease vencida
(consulta por `status`+`lease.expires_at`, seção 9 "Paginar e indexar
status+next_attempt_at, executor+lease.expiry") e persiste o `PedidoDuravel`
devolvido por este módulo fica para a sub-entrega de wiring (passo 5/6/9 do
pacote), a mesma que ainda falta para `autonomy.execution`/`autonomy.runs`.

Escopo desta fatia -- deliberadamente MENOR que os quatro casos citados no
passo 7 do pacote:

- "Leases vencidos": tratado aqui (`varrer_lease_vencida`), mas só para
  `RESERVADO` e `EM_ANDAMENTO` -- exatamente os dois cenários de "worker
  morto" que a seção 10.2 do plano lista como teste obrigatório ("worker
  morto após reserva, após efeito e antes do resultado"). `VERIFICANDO`,
  `AGUARDANDO_APROVACAO` e `AGUARDANDO_EXTERNO` também sustentam lease
  (`autonomy.execution._STATUS_PERMITE_RENOVACAO_DE_LEASE`), mas o grafo de
  transições de `autonomy.requests` não modela um caminho direto e uniforme
  de vencimento para os três (ex.: `AGUARDANDO_APROVACAO` só permite ir para
  `EM_ANDAMENTO`/`CANCELADO` -- nunca `RETENTATIVA_AGENDADA`/`FALHA_FINAL`
  diretamente) -- decidir o que "lease vencida esperando aprovação/terceiro"
  deveria fazer é uma pergunta de produto distinta ("quanto tempo esperar
  antes de desistir de uma aprovação humana?"), não uma extensão mecânica
  desta função. Fica para uma sub-entrega futura, que provavelmente vai
  precisar de outro parâmetro (prazo de espera) que este módulo não tem hoje.
- "Retry agendado": tratado aqui (`promover_retentativa_pronta`) -- só a
  transição `RETENTATIVA_AGENDADA -> PENDENTE` quando `proximo_tentativa_em`
  já passou, liberando o pedido para `assumir_pedido` reivindicar de novo.
- "Falha final": tratado aqui como o desfecho de `varrer_lease_vencida`
  quando `tentativas` esgota `max_tentativas` -- inclui uma entrada de
  `DiagnosticoPedido` ("fila de diagnóstico").
- "Resultado desconhecido": FORA de escopo desta fatia -- `autonomy.requests`
  já modela `RESULTADO_DESCONHECIDO` como um estado que sai por reconciliação
  (`VERIFICANDO`) ou nova tentativa/falha, mas decidir SE/QUANDO uma
  reconciliação externa "demorou demais" e deve ser escalada exige um
  timestamp de "há quanto tempo está neste estado" que `PedidoDuravel` ainda
  não tem (o `criado_em`/histórico de transições fica para quando o wiring
  real definir como esse dado é persistido). Registrado como pendência
  explícita no bloco desta sub-entrega em docs/autonomia/execucao.md.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from autonomy.execution import PedidoDuravel
from autonomy.requests import (
    DEFAULT_MAX_TENTATIVAS,
    RequestStatus,
    _exigir_tz_aware,
    calcular_backoff_segundos,
    lease_expirada,
    validar_transicao,
)
from autonomy.runs import expirar_por_timeout as _run_expirar_por_timeout
from autonomy.runs import run_esta_ativo

#: Estados a partir dos quais `varrer_lease_vencida` sabe agir -- ver a
#: docstring do módulo para por que `VERIFICANDO`/`AGUARDANDO_APROVACAO`/
#: `AGUARDANDO_EXTERNO` ficam de fora desta fatia, mesmo sustentando lease.
_STATUS_LEASE_VENCIDA_TRATADOS: frozenset[RequestStatus] = frozenset({
    RequestStatus.RESERVADO,
    RequestStatus.EM_ANDAMENTO,
})


@dataclass(frozen=True)
class DiagnosticoPedido:
    """Uma entrada da "fila de diagnóstico" -- pedido que esgotou tentativas
    automáticas e precisa de atenção não-automática (passo 7 do pacote).
    Lógica pura: só o registro; persistência/alerta reais ficam para o
    wiring. Imutável, mesmo padrão de `Lease`/`LedgerEntry`/`AgentRun`."""

    request_id: str
    motivo: str
    status_anterior: RequestStatus
    tentativas: int
    registrado_em: datetime

    def __post_init__(self) -> None:
        _exigir_tz_aware(self.registrado_em, "registrado_em")
        if self.tentativas < 0:
            raise ValueError("tentativas não pode ser negativa.")


@dataclass(frozen=True)
class ResultadoSweepLeaseVencida:
    """Devolvido por `varrer_lease_vencida`: o `PedidoDuravel` atualizado e,
    quando o pedido esgotou as tentativas automáticas, a entrada de
    diagnóstico correspondente (`None` quando uma nova tentativa foi
    agendada em vez de desistir)."""

    pedido: PedidoDuravel
    diagnostico: DiagnosticoPedido | None


def varrer_lease_vencida(
    pedido: PedidoDuravel,
    agora: datetime | None = None,
    max_tentativas: int = DEFAULT_MAX_TENTATIVAS,
    rng: object | None = None,
) -> ResultadoSweepLeaseVencida:
    """Decide o desfecho de UM pedido cuja lease já venceu sem o executor
    ter renovado/concluído -- "worker morto" (seção 10.2 do plano).

    Só aceita `pedido.status` em `_STATUS_LEASE_VENCIDA_TRATADOS`
    (`RESERVADO`/`EM_ANDAMENTO` -- ver docstring do módulo) e exige
    `pedido.lease` presente e de fato vencida (`autonomy.requests.lease_expirada`)
    -- levanta `ValueError` fora disso, mesmo estilo defensivo dos módulos
    irmãos (nunca assume, sempre confere antes de agir).

    Fecha `pedido.run` por timeout (`autonomy.runs.expirar_por_timeout`)
    quando presente e ainda ativo -- mesmo raciocínio de
    `autonomy.execution._fechar_run_se_houver`: um `AgentRun` não deve ficar
    `INICIADO`/`EM_ANDAMENTO` para sempre só porque o PEDIDO já foi
    redirecionado por este sweep.

    `RESERVADO`: nenhum efeito foi produzido ainda (a reserva nunca chegou a
    `registrar_progresso`) -- "lease expira ou é liberada sem efeito: volta
    para a fila" (seção 4.5, comentário da própria aresta em
    `autonomy.requests._TRANSICOES_PERMITIDAS`). Não conta como tentativa
    esgotada: volta direto para `PENDENTE`, `tentativas` inalterada.

    `EM_ANDAMENTO`: efeito parcial pode já ter ocorrido -- conta como uma
    tentativa. Se `tentativas+1 < max_tentativas`, agenda nova tentativa
    (`RETENTATIVA_AGENDADA`, `proximo_tentativa_em` calculado por
    `autonomy.requests.calcular_backoff_segundos`, mesmo backoff com jitter
    de 1/5/20 minutos já usado no resto do pacote). Caso contrário, desiste
    (`FALHA_FINAL`) e devolve uma `DiagnosticoPedido` -- a "fila de
    diagnóstico" do passo 7."""
    if pedido.status not in _STATUS_LEASE_VENCIDA_TRATADOS:
        raise ValueError(
            f"pedido '{pedido.request_id}' está em '{pedido.status.value}', que não é "
            "varrido por lease vencida nesta sub-entrega -- só "
            f"{sorted(s.value for s in _STATUS_LEASE_VENCIDA_TRATADOS)} (ver docstring "
            "do módulo para os demais estados com lease ativa, fora de escopo aqui)."
        )
    if pedido.lease is None:
        raise ValueError(f"pedido '{pedido.request_id}' não tem lease -- nada para varrer.")
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not lease_expirada(pedido.lease, agora=agora_resolvido):
        raise ValueError(
            f"pedido '{pedido.request_id}' tem lease ainda válida (expira em "
            f"{pedido.lease.expires_at.isoformat()}) -- não é um caso de sweep."
        )

    run_atualizado = pedido.run
    if run_atualizado is not None and run_esta_ativo(run_atualizado):
        run_atualizado = _run_expirar_por_timeout(
            run_atualizado, lease_expirada=True, agora=agora_resolvido
        )

    if pedido.status == RequestStatus.RESERVADO:
        pedido_novo = dataclasses.replace(
            pedido, status=RequestStatus.PENDENTE, run=run_atualizado
        )
        return ResultadoSweepLeaseVencida(pedido=pedido_novo, diagnostico=None)

    # EM_ANDAMENTO daqui em diante.
    tentativas_novas = pedido.tentativas + 1
    if tentativas_novas >= max_tentativas:
        ok, motivo = validar_transicao(pedido.status, RequestStatus.FALHA_FINAL)
        if not ok:
            raise ValueError(motivo)
        pedido_novo = dataclasses.replace(
            pedido,
            status=RequestStatus.FALHA_FINAL,
            run=run_atualizado,
            tentativas=tentativas_novas,
            proximo_tentativa_em=None,
        )
        diagnostico = DiagnosticoPedido(
            request_id=pedido.request_id,
            motivo=(
                f"lease vencida em '{pedido.status.value}' após {tentativas_novas} "
                f"tentativa(s) automática(s) (limite {max_tentativas}) -- sem nova "
                "retentativa, requer atenção manual."
            ),
            status_anterior=pedido.status,
            tentativas=tentativas_novas,
            registrado_em=agora_resolvido,
        )
        return ResultadoSweepLeaseVencida(pedido=pedido_novo, diagnostico=diagnostico)

    ok, motivo = validar_transicao(pedido.status, RequestStatus.RETENTATIVA_AGENDADA)
    if not ok:
        raise ValueError(motivo)
    backoff_segundos = calcular_backoff_segundos(tentativas_novas, rng=rng)
    proximo_tentativa_em = agora_resolvido + timedelta(seconds=backoff_segundos)
    pedido_novo = dataclasses.replace(
        pedido,
        status=RequestStatus.RETENTATIVA_AGENDADA,
        run=run_atualizado,
        tentativas=tentativas_novas,
        proximo_tentativa_em=proximo_tentativa_em,
    )
    return ResultadoSweepLeaseVencida(pedido=pedido_novo, diagnostico=None)


def promover_retentativa_pronta(
    pedido: PedidoDuravel, agora: datetime | None = None
) -> PedidoDuravel:
    """`RETENTATIVA_AGENDADA -> PENDENTE` quando `proximo_tentativa_em` já
    passou -- libera o pedido para `assumir_pedido` reivindicar de novo
    (a próxima geração da lease, ver `autonomy.execution.assumir_pedido`).

    Levanta `ValueError` se `pedido.status` não for `RETENTATIVA_AGENDADA`,
    se `proximo_tentativa_em` não estiver definido (não deveria acontecer
    partindo de `varrer_lease_vencida`, mas esta função não assume a origem
    do pedido) ou se a hora agendada ainda não chegou -- mesmo estilo
    defensivo do resto do pacote, nunca promove cedo demais."""
    if pedido.status != RequestStatus.RETENTATIVA_AGENDADA:
        raise ValueError(
            f"pedido '{pedido.request_id}' está em '{pedido.status.value}', não "
            "'retentativa_agendada' -- nada para promover."
        )
    if pedido.proximo_tentativa_em is None:
        raise ValueError(
            f"pedido '{pedido.request_id}' está em retentativa_agendada sem "
            "proximo_tentativa_em definido -- não é possível decidir se já está pronto."
        )
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if agora_resolvido < pedido.proximo_tentativa_em:
        raise ValueError(
            f"pedido '{pedido.request_id}' só está pronto para nova tentativa em "
            f"{pedido.proximo_tentativa_em.isoformat()} (agora: {agora_resolvido.isoformat()})."
        )
    ok, motivo = validar_transicao(pedido.status, RequestStatus.PENDENTE)
    if not ok:
        raise ValueError(motivo)
    return dataclasses.replace(pedido, status=RequestStatus.PENDENTE, proximo_tentativa_em=None)
