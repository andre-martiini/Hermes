"""Contratos de dados do modelo unificado de identidade e política de
autonomia (P02 do plano de autonomia, docs/plano-hermes-autonomo-2026-09-06.md
— arquivo ainda não mergeado em `main`, vive na PR #184).

Define o vocabulário compartilhado entre `autonomy/policy.py` e os canais que
o consultam (MCP, web, Telegram, voz): quem está pedindo (`Principal`), o que
está pedindo (`PolicyRequest`), e a resposta estruturada da decisão
(`PolicyDecision`) — seção 5 do plano.

Este módulo não decide nada por si só (isso é `policy.py`) nem faz I/O — só
define tipos, para poder ser importado por qualquer canal (incluindo
hermes-voice-bridge, que roda como serviço separado) sem puxar Firestore.

Hoje (antes desta sub-entrega) não existe NENHUM desses conceitos no código:
`tools/tool_context.py::ToolContext` carrega um `user_uid: str | None` cru,
sem tipo de principal; `mcp_oauth.py` emite um único escopo (`hermes:tools`)
para todo cliente OAuth, sem distinguir dono interativo de rotina autônoma —
exatamente o problema que `TipoPrincipal` abaixo resolve (P02 passo 1-2).
Esta sub-entrega (1/N) só introduz os tipos; NENHUM canal foi religado ainda
(ver docs/autonomia/execucao.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TipoPrincipal(str, Enum):
    """Os cinco tipos de identidade distintos exigidos pelo passo 1 do P02.

    A mesma ação deve receber a mesma decisão em qualquer canal — mas o TIPO
    de quem pede continua importando: um runner de serviço nunca pode se
    passar pelo dono interativo só porque os dois autenticam com o mesmo uid.
    """

    #: O André, numa sessão viva e interativa (web, Telegram, voz) — humano
    #: presente, respondendo em tempo real.
    DONO_INTERATIVO = "dono_interativo"

    #: Um cliente MCP hospedado (Claude.ai, Claude Desktop) usado pelo dono,
    #: com ele acompanhando a conversa, mas sem clique de UI por chamada —
    #: intermediário entre "dono interativo" e "runner de serviço".
    CLIENTE_ASSISTIDO = "cliente_assistido"

    #: Uma rotina agendada do Cowork — roda sem humano olhando em tempo real,
    #: mas foi configurada por decisão explícita do dono.
    ROTINA_COWORK = "rotina_cowork"

    #: Um processo de longa duração agindo em nome do dono sem sessão
    #: interativa (job assíncrono, trigger de Firestore, worker). O tipo mais
    #: restrito: nunca deve conseguir conceder a si mesmo uma permissão.
    RUNNER_SERVICO = "runner_servico"

    #: Alguém que NÃO é o dono, agindo por um portal público (ex.: portal de
    #: compras, de bolsas) — sem nenhuma das capacidades do dono.
    TERCEIRO_PORTAL = "terceiro_portal"


class Decisao(str, Enum):
    """Os cinco valores possíveis de decisão de política — seção 5.2 do
    plano, verbatim."""

    ALLOW = "allow"
    PREPARE_ONLY = "prepare_only"
    REQUIRE_APPROVAL = "require_approval"
    DEFER = "defer"
    DENY = "deny"


class ClasseEfeito(str, Enum):
    """A matriz de efeito da seção 5.1 do plano, na mesma ordem (da mais
    livre à mais restrita). Usada para classificar uma ferramenta/ação antes
    de decidir."""

    OBSERVACAO_AUTORIZADA = "observacao_autorizada"
    PREPARACAO_INTERNA = "preparacao_interna"
    ESCRITA_INTERNA_REVERSIVEL = "escrita_interna_reversivel"
    COORDENACAO_LIMITADA = "coordenacao_limitada"
    COMPROMISSO_TERCEIROS = "compromisso_terceiros"
    EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL = "efeito_financeiro_destrutivo_institucional"


class EstadoAutonomia(str, Enum):
    """Controle global e por domínio — seção 5.4 do plano."""

    ATIVO = "ativo"
    SOMENTE_PREPARACAO = "somente_preparacao"
    PAUSADO = "pausado"


@dataclass(frozen=True)
class Principal:
    """Quem está pedindo. Construído pelo adaptador de cada canal a partir de
    uma identidade JÁ VERIFICADA por esse canal (token OAuth, ID token
    Firebase, chat_id do Telegram, etc.) — este tipo nunca autentica nada
    sozinho, só representa o resultado de uma autenticação que já aconteceu.
    """

    uid: str | None
    tipo: TipoPrincipal
    canal: str  # "web" | "telegram" | "mcp" | "voz" | "whatsapp" | ...
    client_id: str | None = None       # DCR client_id (OAuth), quando houver
    origem_humana: bool = True         # False para rotina_cowork/runner_servico sem humano olhando agora
    autenticado_em: datetime | None = None

    def eh_dono(self) -> bool:
        """Atalho para os dois tipos que representam o próprio dono agindo
        (interativo ou assistido) — distinto de rotina/runner/terceiro."""
        return self.tipo in (TipoPrincipal.DONO_INTERATIVO, TipoPrincipal.CLIENTE_ASSISTIDO)


@dataclass(frozen=True)
class PolicyRequest:
    """Entrada da decisão de política — seção 5.2 do plano: "identidade
    autenticada, cliente/canal, origem humana ou rotina, missão, ferramenta,
    argumentos resolvidos, versões de fonte, sensibilidade, orçamento e
    política vigente."

    `estado_autonomia` e `mandatos_aplicaveis` representam a "política
    vigente" já resolvida pelo chamador (thin wrapper de leitura em
    `policy.py`, não deste tipo) — mantém `avaliar()` pura e testável sem
    Firestore.
    """

    principal: Principal
    ferramenta: str
    classe_efeito: ClasseEfeito
    argumentos_resolvidos: dict = field(default_factory=dict)
    missao: str | None = None
    versoes_fonte: dict = field(default_factory=dict)
    sensibilidade: str | None = None          # ex.: "financeiro", "terceiros", None
    orcamento_restante: float | None = None
    estado_autonomia: EstadoAutonomia = EstadoAutonomia.ATIVO
    mandatos_aplicaveis: tuple["Mandato", ...] = ()


@dataclass(frozen=True)
class PolicyDecision:
    """Saída estruturada da decisão de política — seção 5.2 do plano,
    verbatim (mesmos nomes de campo do JSON de exemplo)."""

    decision: Decisao
    policy_id: str
    policy_version: int
    reason_code: str
    constraints_checked: tuple[str, ...] = ()
    approval_required: bool = False
    expires_at: datetime | None = None
    operation_hash: str | None = None
    motivo_legivel: str | None = None   # texto explicável, além do reason_code

    def to_dict(self) -> dict:
        """Forma serializável (persistência/log): datas em isoformat, enum
        como valor string."""
        return {
            "decision": self.decision.value,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "reason_code": self.reason_code,
            "constraints_checked": list(self.constraints_checked),
            "approval_required": self.approval_required,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "operation_hash": self.operation_hash,
            "motivo_legivel": self.motivo_legivel,
        }


@dataclass(frozen=True)
class Mandato:
    """Mandato persistente — seção 5.3 do plano. Condições mínimas:
    finalidade, destinatários/recursos, classes de conteúdo permitidas,
    limites por janela, horário, validade, origem de autorização e forma de
    revogação. "Tipos 'outro' e rótulos livres não podem habilitar envio
    autônomo" (seção 5.3) — por isso `classes_conteudo_permitidas` é uma
    tupla fechada, nunca um texto livre interpretado depois.

    `usos_na_janela_atual` (adicionado após revisão do Codex na PR #191):
    o dado de contagem de uso que `autonomy.policy.mandato_cobre()` compara
    contra `limite_por_janela` — esta classe é só o tipo, não faz I/O, então
    quem monta o `Mandato` (um wrapper com acesso a Firestore/histórico,
    ainda não implementado nesta sub-entrega, já que mandatos persistidos
    ficam para a sub-entrega seguinte) precisa RESOLVER e preencher este
    campo antes de colocar o mandato em `PolicyRequest.mandatos_aplicaveis`.
    `None` (o default) significa "contagem não verificada" — terceira rodada
    da revisão do Codex (PR #191): quando `limite_por_janela` está declarado
    mas a contagem ainda é `None`, `mandato_cobre` trata o mandato como NÃO
    coberto (falha fechada), em vez de pular o limite como se não existisse.
    O campo existe desde já para que o wrapper futuro (ainda não
    implementado nesta sub-entrega) tenha onde escrever a contagem
    resolvida, em vez de a checagem ficar sem nenhum lugar para acontecer.
    """

    mandato_id: str
    finalidade: str
    destinatarios_recursos: tuple[str, ...]
    classes_conteudo_permitidas: tuple[str, ...]
    limite_por_janela: int | None = None
    janela_dias: int | None = None
    usos_na_janela_atual: int | None = None
    # "HH:MM". Os dois só significam "sem restrição de horário" quando AMBOS
    # são None — quarta rodada da revisão do Codex (PR #191):
    # `autonomy.policy.mandato_cobre()` falha fechado quando só um dos dois
    # está preenchido (configuração parcial), em vez de tratar isso como
    # "sem restrição". Preencha os dois ou nenhum.
    horario_permitido_inicio: str | None = None
    horario_permitido_fim: str | None = None
    # `None` (o default) significa "validade não resolvida" — quarta rodada
    # da revisão do Codex (PR #191): `mandato_cobre()` passou a falhar
    # fechado quando `valido_ate` é `None`, em vez de tratar ausência de
    # validade como "cobre indefinidamente". Todo mandato real precisa desta
    # data preenchida para cobrir algo.
    valido_ate: datetime | None = None
    origem_autorizacao: str = ""       # referência a como/quando o dono concedeu isto
    forma_revogacao: str = ""
    revogado: bool = False
