"""Adaptador entre o ciclo de jobs assíncronos do MCP (`mcp_jobs.py`) e o
vocabulário do protocolo novo de pedidos duráveis (P04 do plano de
autonomia, docs/plano-hermes-autonomo-2026-09-06.md, passo 6 do pacote:
"Unificar o ciclo de jobs MCP através de adaptador ao protocolo,
preservando job_id e sem fundir coleções cegamente").

`mcp_jobs.py` existe desde antes deste plano (ver seu próprio docstring) e
resolve um problema mais estreito que `autonomy/requests.py`: uma tool MCP
que passaria do limite de tempo do gateway devolve `{status: "processing",
job_id}` na hora, e um trigger do Firestore faz o trabalho de verdade,
gravando "done"/"error" no mesmo documento. Não há reserva por
lease/geração (é sempre uma execução, reivindicada só por um booleano
`reivindicado_em` dentro de uma transação -- ver
`mcp_jobs._reivindicar_job`), não há retentativa automática, não há
checkpoint intermediário: no caminho feliz, um job nasce, é reivindicado
uma vez, e termina.

ATENÇÃO para quem for consumir este adaptador (achado de revisão
adversarial desta sub-entrega): "termina" não é garantido pelo código
atual de `mcp_jobs.py`. `on_mcp_job_created` só grava `expira_em` nos
caminhos de conclusão (done/error/bloqueio de política/erro de
configuração) -- se o trigger for encerrado (timeout de 540s, OOM, queda
do runtime) DEPOIS de `_reivindicar_job` gravar `reivindicado_em` mas
ANTES de qualquer `ref.update(...)` de conclusão, o documento fica para
sempre em `status="processing"` com `reivindicado_em` já preenchido --
sem `expira_em`, nem elegível a TTL. Este adaptador traduziria esse job
para `EM_ANDAMENTO` indefinidamente, sem nenhum sinal de que a tradução é
sobre um job "zumbi", não um job realmente em andamento. Corrigir esse
comportamento é trabalho de `mcp_jobs.py` (ex.: um sweep de jobs
reivindicados há muito tempo sem conclusão, mesmo espírito de
`autonomy.sweep` para o protocolo novo) -- fora do escopo desta
sub-entrega, que só traduz o que o documento diz agora, sem inferir
frescor nem detectar jobs travados.

Esta sub-entrega NÃO toca `mcp_jobs.py` nem sua coleção `mcp_jobs` --
"preservando job_id e sem fundir coleções": os dois ciclos continuam
inteiramente separados no Firestore (`mcp_jobs` de um lado;
`agent_requests`/`operation_ledger`/`agent_runs` do outro). O que este
módulo faz é só TRADUZIR o vocabulário de UM job já existente (seu
`status` bruto -- "processing", "done", "error" -- mais o booleano
`reivindicado_em`) para o enum `autonomy.requests.RequestStatus` que o
resto do pacote P04 já usa -- para que um consumidor futuro (ex.: uma
consulta unificada de "todo trabalho em curso", ou o painel de missões da
seção 3.3 do plano) possa apresentar os dois ciclos com os mesmos nomes de
estado, sem precisar conhecer os dois formatos de documento.

Mapeamento (não há "pendente"/"reservado" distintos no ciclo de
`mcp_jobs.py` -- `criar_job` já grava `status="processing"` na própria
criação; a distinção equivalente é "ainda não reivindicado pelo trigger"
vs. "já reivindicado"):

| mcp_jobs (status, reivindicado_em) | RequestStatus  |
|---|---|
| ("processing", None)               | PENDENTE       |
| ("processing", <qualquer valor>)   | EM_ANDAMENTO   |
| ("done", *)                        | CONCLUIDO      |
| ("error", *)                       | FALHA_FINAL    |

"error" mapeia para `FALHA_FINAL`, não para `RequestStatus.ERRO_LEGADO`:
`ERRO_LEGADO` existe só para normalizar a LEITURA de registros do formato
legado de `agent_requests.py` (ver a docstring de `RequestStatus`) -- um
job MCP não é esse formato, é um ciclo próprio, mais simples, sem
retentativa automática (nenhum caminho de `mcp_jobs.py` volta um job de
"error" para "processing"), então `FALHA_FINAL` (estado terminal do
protocolo novo) é a tradução correta: um erro de job MCP já é definitivo
por construção deste ciclo, exatamente o que `FALHA_FINAL` descreve.

Nenhuma outra chave de `RequestStatus` é alcançável a partir de um job
MCP -- não há aprovação, não há dependência de terceiro, não há
retentativa agendada nem resultado desconhecido neste ciclo. Essas
diferenças de produto entre os dois protocolos são precisamente o motivo
de NÃO fundir as coleções cegamente, como o passo 6 do pacote adverte.
"""

from __future__ import annotations

from typing import Any

from autonomy.requests import RequestStatus

#: Valores aceitos no campo `status` de um documento `mcp_jobs` -- ver
#: `mcp_jobs.criar_job`/`mcp_jobs.on_mcp_job_created`. Qualquer outro valor
#: é dado corrompido ou de uma versão futura ainda não traduzida aqui.
_STATUS_MCP_CONHECIDOS = frozenset({"processing", "done", "error"})


class StatusMcpJobDesconhecido(ValueError):
    """`status` do documento `mcp_jobs` fora do conjunto conhecido -- falha
    fechada em vez de adivinhar uma tradução."""

    def __init__(self, status_bruto: Any) -> None:
        self.status_bruto = status_bruto
        super().__init__(
            f"status de job MCP desconhecido: {status_bruto!r} -- esperado um de "
            f"{sorted(_STATUS_MCP_CONHECIDOS)}"
        )


def request_status_de_job(dados: dict) -> RequestStatus:
    """Traduz o documento bruto de um job `mcp_jobs` (o dict devolvido por
    `snapshot.to_dict()`) para o `RequestStatus` equivalente -- ver a
    tabela no docstring do módulo.

    Só lê `status` e `reivindicado_em`; ignora qualquer outro campo do
    documento (`tool`, `arguments`, `resultado`, etc. não afetam a
    tradução). Levanta `StatusMcpJobDesconhecido` para um `status` fora do
    conjunto conhecido -- nunca devolve um `RequestStatus` adivinhado."""
    dados_seguros = dados or {}
    status_bruto = dados_seguros.get("status")
    if status_bruto not in _STATUS_MCP_CONHECIDOS:
        raise StatusMcpJobDesconhecido(status_bruto)
    if status_bruto == "done":
        return RequestStatus.CONCLUIDO
    if status_bruto == "error":
        return RequestStatus.FALHA_FINAL
    # status_bruto == "processing"
    if dados_seguros.get("reivindicado_em") is not None:
        return RequestStatus.EM_ANDAMENTO
    return RequestStatus.PENDENTE


def resumo_protocolo_de_job(job_id: str, dados: dict) -> dict:
    """Forma compacta e serializável, no vocabulário do protocolo novo, de
    UM job MCP -- útil para um consumidor futuro que precise listar jobs
    MCP lado a lado com pedidos do protocolo novo sem reimplementar a
    tradução acima. Não substitui `mcp_jobs.ler_job` (que continua sendo a
    forma canônica de consulta, com autorização por `uid` e mensagens em
    português) -- é só a projeção no vocabulário comum.

    `job_id` é preservado tal como recebido, nunca recalculado a partir de
    `dados` -- passo 6 do pacote: "preservando job_id"."""
    job_id_limpo = str(job_id or "").strip()
    if not job_id_limpo:
        raise ValueError("job_id é obrigatório.")
    request_status = request_status_de_job(dados)
    dados_seguros = dados or {}
    return {
        "job_id": job_id_limpo,
        "origem": "mcp_jobs",
        "request_status": request_status.value,
        "status_mcp_original": dados_seguros.get("status"),
        "tool": dados_seguros.get("tool"),
    }
