"""Heartbeat e cobertura por integração (P05 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, seção "P05 — Normalizar eventos e
saúde das integrações", passo 7 do pacote: "Publicar heartbeat/cobertura por
integração, com estado healthy/degraded/unavailable/unknown e dados de
última leitura bem-sucedida.").

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/events.py` (P05
sub-entrega 1/N) e `autonomy/requests.py`/`autonomy/ledger.py` (P04): tipos e
regra de derivação de estado primeiro (testável sem Firestore), wiring numa
sub-entrega seguinte. Nenhum trigger/scheduler existente (main.py,
google_push_watch.py, whatsapp_ingest.py) importa este módulo ainda -- eles
continuam gravando seu próprio estado de sync do jeito que já fazem hoje
(`system/sync`, `system/gmail_sync`, `system/whatsapp_ingest`, os docs de
watch do Calendar/Drive/Gmail), cada um com um formato diferente e, para
SIPAC/finanças/repositório, nenhum estado persistido. Este módulo não lê
nenhum desses documentos nem decide QUANDO uma integração é considerada
"a mesma" entre chamadas -- só define a FORMA do registro de saúde
(`IntegrationHealth`, seção 5 do plano, entidade `integration_health`) e como
derivar `status` a partir de dados objetivos (idade da última leitura
confiável, ausência de leitura, ou um `error_code` explícito), nunca como
relato textual livre -- mesma exigência já seguida pelo resto do pacote de
autonomia (ex.: `autonomy/verifiers.py`, P04 passo 8: resultado observado por
verificação determinística, não por afirmação).

"Indisponibilidade não é dado vazio" (seção 5 do plano, mesma linha do
contrato de `integration_health`): uma integração sem leitura bem-sucedida
ainda registrada produz `IntegrationStatus.UNKNOWN`, nunca um registro
ausente nem zeros -- é exatamente o anti-padrão que o passo 8 do pacote
(ainda não implementado) existe para substituir em `obter_estado_atual`
(achado A09 do plano, `hermes_tools.py`: falha de fonte vira lista vazia/
contador zero, indistinguível de "genuinamente não há nada").

O passo 8 do pacote (substituir zeros de fallback por status de fonte em
`obter_estado_atual`) e a tool `consultar_saude_integracoes` (seção 6 do
plano) ficam para sub-entregas seguintes -- ambos dependem de algo real
persistir `IntegrationHealth` primeiro, o que por sua vez depende de decidir,
por integração, qual documento de sync já existente lê e com que thresholds
de frescor (ver `proximo_pacote` do bloco desta sub-entrega em
docs/autonomia/execucao.md para as integrações mapeadas por esta sub-entrega
e o estado de sync que cada uma já tem hoje).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .ledger import _snapshot_json
from .requests import _exigir_tz_aware


class IntegrationStatus(str, Enum):
    """Os quatro estados do passo 7 do pacote, verbatim: "healthy/degraded/
    unavailable/unknown". Em inglês (não seguindo o padrão em português dos
    demais enums deste pacote -- `RequestStatus`, `CategoriaEvento`) porque o
    próprio texto do plano já usa estas quatro palavras como o vocabulário do
    contrato, não uma tradução livre desta sub-entrega."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


#: Ponto de partida razoável (mesmo espírito de `DEFAULT_LEASE_SEGUNDOS` em
#: `autonomy/requests.py`): acima disto sem leitura confirmada nova, uma
#: integração passa de HEALTHY para DEGRADED. As integrações mapeadas por
#: esta sub-entrega têm frequências de sync muito diferentes entre si
#: (WhatsApp é cursor quase contínuo; sync completo de Calendar/Drive/
#: Contacts é agendado a cada poucas horas; SIPAC e finanças hoje não têm
#: nenhum job agendado) -- por isso `calcular_status_integracao` aceita
#: thresholds explícitos por chamada em vez de decidir sozinho um valor por
#: integração; estas constantes são só o default de quem ainda não tem um
#: valor melhor. Quem fizer o wiring (ler `system/sync`, `system/gmail_sync`,
#: etc. e chamar `montar_saude_integracao`) deve ajustar por integração.
DEFAULT_LIMITE_DEGRADADO_SEGUNDOS = 30 * 60
#: Acima disto, UNAVAILABLE -- mesmo raciocínio de ponto de partida acima.
DEFAULT_LIMITE_INDISPONIVEL_SEGUNDOS = 6 * 60 * 60


def calcular_lag_segundos(
    heartbeat_at: datetime,
    last_success_at: datetime | None,
    coverage_until: datetime | None,
) -> float | None:
    """Idade, em segundos, da leitura confiável mais recente conhecida.

    Usa `coverage_until` quando fornecido -- é o instante até onde a fonte
    está CONFIRMADA completa (pode ser mais conservador que
    `last_success_at` para uma integração com cursor/watermark, onde uma
    sincronização pode ter "rodado com sucesso" sem necessariamente ter
    avançado a cobertura até o fim, ex.: uma página parcial de resultados).
    Cai para `last_success_at` quando `coverage_until` não é fornecido.
    Devolve `None` quando nenhum dos dois está disponível -- não há idade
    para calcular, e `0.0` mentiria dizendo "acabou de ler com sucesso".

    Levanta `ValueError` se `last_success_at` OU `coverage_until` (qualquer
    um dos dois fornecidos, não só o que acaba sendo usado como referência)
    for POSTERIOR a `heartbeat_at` -- heartbeat descreve "agora, quando este
    registro foi calculado", então uma leitura confirmada no futuro em
    relação a ele é entrada inconsistente (relógio incorreto ou registro
    construído fora de ordem), não um caso a normalizar silenciosamente.
    Achado real de revisão automática do Codex (P2) na PR desta sub-entrega:
    quando `coverage_until` é fornecido, ele vira a única referência usada no
    cálculo, mas `last_success_at` (se também fornecido) nunca era comparado
    a `heartbeat_at` -- um registro com heartbeat ao meio-dia, coverage_until
    às 11h (válido) e last_success_at às 13h (POSTERIOR ao próprio heartbeat
    que resume o estado) era aceito porque só o campo efetivamente usado no
    cálculo passava por essa checagem.

    Valida tz-awareness de `last_success_at` E `coverage_until` quando
    fornecidos, mesmo que só um dos dois acabe sendo usado como referência --
    achado real de revisão adversarial independente (P05 sub-entrega 2/N):
    sem isto, chamar esta função isoladamente (fora de
    `montar_saude_integracao`/`IntegrationHealth`, que validam os dois campos
    incondicionalmente em `__post_init__`) com `coverage_until` válido e
    `last_success_at` NAIVE não levantava erro nenhum -- o campo naive
    simplesmente nunca era examinado, quebrando a garantia de "todo datetime
    que devia ser um instante absoluto é validado" que o resto do módulo
    segue.

    Normaliza todo datetime para UTC (`.astimezone(timezone.utc)`) ANTES de
    subtrair -- outro achado real de revisão automática do Codex (P2) na PR
    desta sub-entrega, mesma classe de bug já corrigida antes em
    `autonomy/requests.py` (`nova_lease`, achado do Codex na PR #326):
    `datetime - datetime` faz aritmética de "relógio de parede" quando os
    dois operandos carregam um `tzinfo` ciente de DST (`ZoneInfo`), não
    aritmética de tempo decorrido -- perto de uma transição de horário de
    verão, dois instantes com o MESMO offset nominal mas em lados diferentes
    da transição produzem um `total_seconds()` que não corresponde ao tempo
    real decorrido (ex.: America/New_York, 01:15 antes do fallback até 01:45
    depois do fallback é 1h30 de relógio de parede, mas 2h30 de tempo real
    decorrido -- a diferença de uma hora inteira do fallback). Converter para
    UTC (que não observa DST) antes de subtrair torna a aritmética sempre de
    tempo decorrido de verdade, qualquer que seja o fuso de entrada."""
    _exigir_tz_aware(heartbeat_at, "heartbeat_at")
    if last_success_at is not None:
        _exigir_tz_aware(last_success_at, "last_success_at")
    if coverage_until is not None:
        _exigir_tz_aware(coverage_until, "coverage_until")

    heartbeat_utc = heartbeat_at.astimezone(timezone.utc)
    for nome, valor in (
        ("last_success_at", last_success_at),
        ("coverage_until", coverage_until),
    ):
        if valor is not None and valor.astimezone(timezone.utc) > heartbeat_utc:
            raise ValueError(
                f"{nome} é posterior a heartbeat_at ({nome}={valor.isoformat()}, "
                f"heartbeat_at={heartbeat_at.isoformat()}) -- heartbeat_at deve "
                "descrever um instante igual ou posterior a toda leitura que ele "
                "resume."
            )

    referencia = coverage_until if coverage_until is not None else last_success_at
    if referencia is None:
        return None
    return (heartbeat_utc - referencia.astimezone(timezone.utc)).total_seconds()


def calcular_status_integracao(
    heartbeat_at: datetime,
    last_success_at: datetime | None,
    coverage_until: datetime | None,
    error_code: str | None,
    limite_degradado_segundos: float = DEFAULT_LIMITE_DEGRADADO_SEGUNDOS,
    limite_indisponivel_segundos: float = DEFAULT_LIMITE_INDISPONIVEL_SEGUNDOS,
) -> IntegrationStatus:
    """Deriva o `IntegrationStatus` a partir de dados objetivos -- nunca por
    afirmação de quem chama (ver docstring do módulo).

    Ordem de decisão:

    1. `error_code` presente -> sempre `UNAVAILABLE`, qualquer que seja o
       frescor. Um erro explícito reportado pela própria integração é o
       sinal mais forte de indisponibilidade que existe; uma leitura
       recente bem-sucedida ANTES do erro não torna a integração disponível
       AGORA.
    2. Sem `error_code` e sem nenhuma leitura de referência
       (`coverage_until`/`last_success_at` ambos `None`, via
       `calcular_lag_segundos`) -> `UNKNOWN`. Nunca houve uma leitura
       bem-sucedida registrada para avaliar frescor -- não é o mesmo que
       "com problema", mas também não é o mesmo que "saudável" (mesma
       distinção de "indisponibilidade não é dado vazio" do contrato).
    3. Caso contrário, o `status` vem só da idade da leitura de referência
       (`lag_segundos`) comparada aos dois limites: até
       `limite_degradado_segundos` é `HEALTHY`; até
       `limite_indisponivel_segundos` é `DEGRADED`; acima disso,
       `UNAVAILABLE`. Limites são inclusivos no lado "melhor" (exatamente no
       limite ainda conta como o estado mais favorável) -- decisão
       arbitrária razoável na ausência de uma regra do plano, documentada
       para poder ser revisada.

    Levanta `ValueError` se `limite_degradado_segundos` ou
    `limite_indisponivel_segundos` não forem positivos, ou se o degradado
    exceder o indisponível (thresholds invertidos são erro de configuração
    de quem chama, não um caso a normalizar silenciosamente)."""
    if limite_degradado_segundos <= 0 or limite_indisponivel_segundos <= 0:
        raise ValueError("os limites de frescor devem ser positivos.")
    if limite_degradado_segundos > limite_indisponivel_segundos:
        raise ValueError(
            "limite_degradado_segundos não pode exceder limite_indisponivel_segundos "
            f"(recebido degradado={limite_degradado_segundos}, "
            f"indisponivel={limite_indisponivel_segundos})."
        )
    if error_code is not None and not str(error_code).strip():
        raise ValueError("error_code, se fornecido, não pode ser vazio -- use None para ausência de erro.")

    lag_segundos = calcular_lag_segundos(heartbeat_at, last_success_at, coverage_until)

    if error_code is not None:
        return IntegrationStatus.UNAVAILABLE
    if lag_segundos is None:
        return IntegrationStatus.UNKNOWN
    if lag_segundos <= limite_degradado_segundos:
        return IntegrationStatus.HEALTHY
    if lag_segundos <= limite_indisponivel_segundos:
        return IntegrationStatus.DEGRADED
    return IntegrationStatus.UNAVAILABLE


@dataclass(frozen=True)
class IntegrationHealth:
    """Registro de saúde de uma integração -- entidade `integration_health`
    da seção 5 do plano ("Estado da integração"). Campos exatamente os do
    contrato: `integration, last_success_at, last_event_at, coverage_until,
    lag_seconds, heartbeat_at, status, error_code, capabilities`.

    `last_event_at` é só informativo nesta sub-entrega -- registra a última
    vez que ALGUM evento dessa integração foi observado (podendo ser mais
    recente que `last_success_at`, ex.: um evento chegou por webhook mas o
    ciclo de sync completo que confirmaria cobertura ainda não rodou), mas
    não participa do cálculo de `status`/`lag_seconds` (esses usam
    `coverage_until`/`last_success_at`, que descrevem CONFIRMAÇÃO de
    leitura, não só observação de uma ocorrência isolada). Uma sub-entrega
    futura pode vir a usar `last_event_at` para outra finalidade (ex.: nota
    de frescor mais otimista para exibição), mas isso é decisão de quem
    fizer o wiring, não desta sub-entrega.

    `status` e `lag_seconds` NÃO são livres -- `__post_init__` valida os dois
    contra os demais campos e falha fechado se forem inconsistentes, mesmo
    espírito já usado para `EventEnvelope.event_id` em `autonomy/events.py`
    (P05 sub-entrega 1/N): um registro de saúde que pudesse afirmar
    `status=healthy` sem que os dados sustentem isso reintroduziria
    exatamente o problema que este módulo existe para evitar
    ("indisponibilidade não é dado vazio" vale também no sentido inverso --
    disponibilidade não é afirmação livre).

    `lag_seconds` é validado por IGUALDADE contra `calcular_lag_segundos`
    (determinístico, não depende de threshold nenhum). `status` só pode ser
    validado por CONSISTÊNCIA, não por igualdade a um valor recalculado: qual
    threshold separa `HEALTHY`/`DEGRADED`/`UNAVAILABLE` é uma decisão por
    integração que este dataclass não conhece (`IntegrationHealth` não guarda
    threshold nenhum -- não é um campo do contrato da seção 5) -- fixar aqui
    os thresholds default de `calcular_status_integracao` rejeitaria
    incorretamente um registro válido construído com thresholds diferentes
    (ex.: por `montar_saude_integracao(..., limite_degradado_segundos=...)`).
    Em vez disso, `__post_init__` só garante a consistência que NÃO depende
    de threshold: `error_code` presente exige `status=UNAVAILABLE`; ausência
    de qualquer leitura de referência (`lag_seconds is None`) exige
    `status=UNKNOWN`; havendo leitura de referência e nenhum erro, `status`
    deve ser um dos três estados restantes (`HEALTHY`/`DEGRADED`/
    `UNAVAILABLE`) -- qual dos três é responsabilidade de quem calculou
    (`calcular_status_integracao`, com o threshold que escolher). Não
    construa esta classe diretamente com `status`/`lag_seconds` calculados à
    mão -- use `montar_saude_integracao()`.

    `capabilities` é congelado recursivamente em `__post_init__` (via
    `autonomy.ledger._snapshot_json`, mesmo mecanismo de
    `EventEnvelope.metadata`/`Checkpoint.dados`) -- sem isso, o `dict` do
    chamador (ou um aninhado dentro dele) mutado depois da construção
    vazaria para dentro do registro "imutável", mesma classe de bug já
    encontrada e corrigida em `events.py`/`ledger.py`."""

    integration: str
    heartbeat_at: datetime
    status: IntegrationStatus
    last_success_at: datetime | None = None
    last_event_at: datetime | None = None
    coverage_until: datetime | None = None
    lag_seconds: float | None = None
    error_code: str | None = None
    capabilities: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.integration).strip():
            raise ValueError("integration não pode ser vazio.")
        if self.error_code is not None and not str(self.error_code).strip():
            raise ValueError(
                "error_code, se fornecido, não pode ser vazio -- use None para "
                "ausência de erro."
            )
        _exigir_tz_aware(self.heartbeat_at, "heartbeat_at")
        for nome, valor in (
            ("last_success_at", self.last_success_at),
            ("last_event_at", self.last_event_at),
            ("coverage_until", self.coverage_until),
        ):
            if valor is not None:
                _exigir_tz_aware(valor, nome)

        object.__setattr__(self, "capabilities", _snapshot_json(dict(self.capabilities)))

        lag_esperado = calcular_lag_segundos(
            self.heartbeat_at, self.last_success_at, self.coverage_until
        )
        if self.lag_seconds != lag_esperado:
            raise ValueError(
                "lag_seconds não bate com o valor determinístico calculado a partir "
                "de heartbeat_at/last_success_at/coverage_until -- use "
                "montar_saude_integracao() em vez de calcular lag_seconds manualmente "
                f"(esperado={lag_esperado!r}, recebido={self.lag_seconds!r})."
            )
        if self.error_code is not None:
            if self.status != IntegrationStatus.UNAVAILABLE:
                raise ValueError(
                    "status deve ser UNAVAILABLE quando error_code está presente "
                    f"(recebido status={self.status!r} com error_code={self.error_code!r})."
                )
        elif lag_esperado is None:
            if self.status != IntegrationStatus.UNKNOWN:
                raise ValueError(
                    "status deve ser UNKNOWN quando não há last_success_at nem "
                    f"coverage_until e nenhum error_code (recebido status={self.status!r})."
                )
        elif self.status not in (
            IntegrationStatus.HEALTHY,
            IntegrationStatus.DEGRADED,
            IntegrationStatus.UNAVAILABLE,
        ):
            raise ValueError(
                "status deve ser HEALTHY, DEGRADED ou UNAVAILABLE quando há leitura "
                "de referência (last_success_at/coverage_until) e nenhum error_code "
                f"(recebido status={self.status!r}) -- qual dos três depende do "
                "threshold escolhido por calcular_status_integracao, que este "
                "__post_init__ não conhece (ver docstring da classe)."
            )


def montar_saude_integracao(
    integration: str,
    heartbeat_at: datetime,
    last_success_at: datetime | None = None,
    last_event_at: datetime | None = None,
    coverage_until: datetime | None = None,
    error_code: str | None = None,
    capabilities: Mapping[str, Any] | None = None,
    limite_degradado_segundos: float = DEFAULT_LIMITE_DEGRADADO_SEGUNDOS,
    limite_indisponivel_segundos: float = DEFAULT_LIMITE_INDISPONIVEL_SEGUNDOS,
) -> IntegrationHealth:
    """Forma preferida de construir um `IntegrationHealth`: calcula
    `lag_seconds`/`status` e monta o registro numa única chamada consistente,
    com os thresholds de frescor que fizerem sentido para ESTA integração.
    `IntegrationHealth.__post_init__` só valida `status` por CONSISTÊNCIA
    (não por igualdade a um threshold fixo -- ver docstring da classe), então
    thresholds customizados aqui produzem um registro que passa na validação
    normalmente, sem precisar coincidir com `DEFAULT_LIMITE_*`."""
    lag_seconds = calcular_lag_segundos(heartbeat_at, last_success_at, coverage_until)
    status = calcular_status_integracao(
        heartbeat_at=heartbeat_at,
        last_success_at=last_success_at,
        coverage_until=coverage_until,
        error_code=error_code,
        limite_degradado_segundos=limite_degradado_segundos,
        limite_indisponivel_segundos=limite_indisponivel_segundos,
    )
    return IntegrationHealth(
        integration=integration,
        heartbeat_at=heartbeat_at,
        status=status,
        last_success_at=last_success_at,
        last_event_at=last_event_at,
        coverage_until=coverage_until,
        lag_seconds=lag_seconds,
        error_code=error_code,
        capabilities=dict(capabilities or {}),
    )
