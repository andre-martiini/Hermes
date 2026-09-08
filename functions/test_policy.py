"""Testes de `autonomy/policy.py` — motor de decisão puro + wrappers de I/O.

`test_floor_identico_ao_mcp_server` mudou de sentido na sub-entrega 2/N do
P02 (docs/autonomia/execucao.md): antes disso, `FLOOR_CONFIRMACAO_OBRIGATORIA`
e `mcp_server._CONFIRMACAO_OBRIGATORIA` eram DUAS constantes duplicadas que
precisavam ser mantidas manualmente iguais; agora `mcp_server.py` importa
este conjunto diretamente (`_CONFIRMACAO_OBRIGATORIA` é um alias, não uma
cópia), então o teste hoje é redundante com o próprio Python — mas continua
valendo como trava de regressão: se algum dia alguém reintroduzir um `set`
literal duplicado em `mcp_server.py` (em vez do alias), este teste volta a
ser o que pega a divergência antes de produção. Os testes do preflight que a
sub-entrega 2/N adicionou de fato (mapeamento de `PolicyDecision` para a
resposta do canal MCP, construção do `Principal` do canal) vivem em
`test_mcp_server.py`, não aqui — este arquivo continua sendo só sobre o
motor `avaliar()` em si, sem I/O nem canal.
"""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import mcp_server
from autonomy import policy
from autonomy.contracts import (
    ClasseEfeito,
    Decisao,
    EstadoAutonomia,
    Mandato,
    Principal,
    PolicyRequest,
    TipoPrincipal,
)

_AGORA = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def _principal(tipo=TipoPrincipal.DONO_INTERATIVO, uid="dono-uid", canal="mcp", origem_humana=True):
    return Principal(uid=uid, tipo=tipo, canal=canal, origem_humana=origem_humana)


def _req(
    ferramenta="ler_algo",
    classe_efeito=ClasseEfeito.OBSERVACAO_AUTORIZADA,
    principal=None,
    estado_autonomia=EstadoAutonomia.ATIVO,
    mandatos_aplicaveis=(),
    argumentos_resolvidos=None,
    sensibilidade=None,
    missao=None,
    orcamento_restante=None,
):
    return PolicyRequest(
        principal=principal or _principal(),
        ferramenta=ferramenta,
        classe_efeito=classe_efeito,
        argumentos_resolvidos=argumentos_resolvidos or {},
        estado_autonomia=estado_autonomia,
        mandatos_aplicaveis=mandatos_aplicaveis,
        sensibilidade=sensibilidade,
        missao=missao,
        orcamento_restante=orcamento_restante,
    )


class TestFloorIdenticoAoMcpServer(unittest.TestCase):
    def test_floor_identico_ao_mcp_server(self):
        self.assertEqual(
            policy.FLOOR_CONFIRMACAO_OBRIGATORIA,
            frozenset(mcp_server._CONFIRMACAO_OBRIGATORIA),
        )

    def test_floor_tem_exatamente_cinco_ferramentas(self):
        # Trava o tamanho também — "não cresce por hábito" (condição do
        # dono, 02/09/2026): uma mudança de tamanho sem tocar este teste
        # não deveria acontecer por acidente.
        self.assertEqual(len(policy.FLOOR_CONFIRMACAO_OBRIGATORIA), 5)

    def test_classe_efeito_piso_cobre_exatamente_o_floor(self):
        # Achado da sub-entrega 12/N: `avaliar()` só consulta
        # `request.principal` no ramo NÃO-piso (`veio_do_piso=False`); o
        # ramo do piso decide sem tocar principal (só o passo 6, estado,
        # é consultado). `decisao_piso()`/`_decisao_piso_mcp` só chamam
        # avaliar() com classe_efeito vindo de CLASSE_EFEITO_PISO — hoje,
        # isso significa que SEMPRE caem no ramo do piso, então nunca
        # dependem de `request.principal` estar bem formado por este
        # caminho específico. Essa garantia depende inteiramente das duas
        # tabelas (mantidas separadamente por design, ver docstring de
        # CLASSE_EFEITO_PISO) terem exatamente as mesmas chaves — este
        # teste trava essa invariante; se ela quebrar (uma ferramenta nova
        # em CLASSE_EFEITO_PISO sem estar em FLOOR_CONFIRMACAO_OBRIGATORIA),
        # o guard fail-closed de `decisao_erro_avaliacao()` (test_policy.py
        # ::TestDecisaoPiso) passa a ser a única proteção real contra um
        # principal malformado quebrar essas duas funções.
        self.assertEqual(
            set(policy.CLASSE_EFEITO_PISO.keys()),
            set(policy.FLOOR_CONFIRMACAO_OBRIGATORIA),
        )


class TestAvaliarPiso(unittest.TestCase):
    def test_ferramenta_do_piso_sempre_require_approval(self):
        # Mesmo com dono interativo e autonomia ativa, o piso decide e para.
        req = _req(ferramenta="schedule_whatsapp_message", classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS)
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.REQUIRE_APPROVAL)
        self.assertEqual(d.reason_code, "floor_nao_contornavel")
        self.assertTrue(d.approval_required)
        # Achado da revisão adversarial da correção do piso+estado (PR #191):
        # a refatoração que uniu piso e matriz padrão numa única variável de
        # decisão tinha deixado o `policy_id` do retorno final usar sempre
        # `_POLICY_ID_PADRAO`, fazendo uma decisão do piso se identificar
        # como se tivesse vindo da matriz de efeito da seção 5.1.
        self.assertEqual(d.policy_id, "floor-confirmacao-obrigatoria")
        self.assertIn("estado_autonomia", d.constraints_checked)

    def test_piso_nao_e_contornavel_por_mandato(self):
        mandato = Mandato(
            mandato_id="m1", finalidade="x",
            destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",),
        )
        req = _req(
            ferramenta="registrar_aporte_investimento",
            classe_efeito=ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
            mandatos_aplicaveis=(mandato,),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.REQUIRE_APPROVAL)
        self.assertEqual(d.reason_code, "floor_nao_contornavel")

    def test_piso_e_apertado_para_deny_quando_pausado(self):
        # Achado P1 #1 da segunda rodada da revisão do Codex (PR #191): antes
        # desta correção, o piso retornava require_approval direto no passo
        # 1, sem nunca consultar o estado de autonomia — um humano aprovando
        # essa pendência ainda executaria o efeito apesar da pausa. Agora o
        # mesmo aperto de estado que vale para mandato/matriz padrão também
        # vale para o piso.
        req = _req(
            ferramenta="schedule_whatsapp_message",
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            estado_autonomia=EstadoAutonomia.PAUSADO,
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.DENY)
        self.assertEqual(d.reason_code, "autonomia_pausada")
        self.assertFalse(d.approval_required)
        self.assertEqual(d.policy_id, policy._POLICY_ID_PADRAO)

    def test_piso_com_mandato_ainda_e_apertado_para_prepare_only_quando_somente_preparacao(self):
        # Reforça que o piso continua não-contornável por mandato mesmo
        # depois da correção: presença de um mandato aplicável não muda
        # nada — o ramo do piso nunca consulta `mandatos_aplicaveis`.
        mandato = Mandato(
            mandato_id="m1", finalidade="x",
            destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",),
        )
        req = _req(
            ferramenta="registrar_aporte_investimento",
            classe_efeito=ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
            estado_autonomia=EstadoAutonomia.SOMENTE_PREPARACAO,
            mandatos_aplicaveis=(mandato,),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.PREPARE_ONLY)
        self.assertEqual(d.reason_code, "autonomia_somente_preparacao")
        self.assertFalse(d.approval_required)

    def test_piso_e_apertado_para_prepare_only_quando_somente_preparacao(self):
        req = _req(
            ferramenta="registrar_aporte_investimento",
            classe_efeito=ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
            estado_autonomia=EstadoAutonomia.SOMENTE_PREPARACAO,
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.PREPARE_ONLY)
        self.assertEqual(d.reason_code, "autonomia_somente_preparacao")
        self.assertFalse(d.approval_required)
        self.assertEqual(d.policy_id, policy._POLICY_ID_PADRAO)

    def test_piso_continua_require_approval_quando_ativo(self):
        # Regressão: a correção acima não pode mudar o caso normal (estado
        # ativo — mesmo teste de test_ferramenta_do_piso_sempre_require_approval
        # repetido aqui para deixar explícito que o aperto só age quando o
        # estado realmente está pausado/restrito).
        req = _req(
            ferramenta="schedule_whatsapp_message",
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            estado_autonomia=EstadoAutonomia.ATIVO,
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.REQUIRE_APPROVAL)
        self.assertEqual(d.reason_code, "floor_nao_contornavel")


class TestAvaliarEstadoPausado(unittest.TestCase):
    def test_pausado_bloqueia_escrita(self):
        req = _req(classe_efeito=ClasseEfeito.ESCRITA_INTERNA_REVERSIVEL, estado_autonomia=EstadoAutonomia.PAUSADO)
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.DENY)
        self.assertEqual(d.reason_code, "autonomia_pausada")

    def test_pausado_permite_leitura(self):
        req = _req(classe_efeito=ClasseEfeito.OBSERVACAO_AUTORIZADA, estado_autonomia=EstadoAutonomia.PAUSADO)
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.ALLOW)
        self.assertEqual(d.reason_code, "observacao_autorizada")


class TestAvaliarAutoconcessao(unittest.TestCase):
    def test_runner_servico_nao_pode_autoconceder_compromisso_terceiros(self):
        req = _req(
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            principal=_principal(tipo=TipoPrincipal.RUNNER_SERVICO, uid=None, origem_humana=False),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.DENY)
        self.assertEqual(d.reason_code, "principal_nao_pode_autoconceder")

    def test_runner_servico_nao_pode_autoconceder_efeito_financeiro(self):
        req = _req(
            classe_efeito=ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
            principal=_principal(tipo=TipoPrincipal.RUNNER_SERVICO, uid=None, origem_humana=False),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.DENY)
        self.assertEqual(d.reason_code, "principal_nao_pode_autoconceder")

    def test_mandato_cobre_libera_runner_servico(self):
        mandato = Mandato(
            mandato_id="m1", finalidade="lembrete recorrente",
            destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",),
            valido_ate=_AGORA + timedelta(days=1),
        )
        req = _req(
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            principal=_principal(tipo=TipoPrincipal.RUNNER_SERVICO, uid=None, origem_humana=False),
            mandatos_aplicaveis=(mandato,),
            sensibilidade="geral",
            missao="lembrete recorrente",
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.ALLOW)
        self.assertEqual(d.reason_code, "dentro_de_mandato_vigente")

    def test_dono_pode_pedir_compromisso_terceiros_sem_mandato_mas_exige_aprovacao(self):
        req = _req(classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS, principal=_principal())
        d = policy.avaliar(req, agora=_AGORA)
        # Dono não é bloqueado pelo passo 3 (é dono), mas a matriz padrão
        # ainda exige require_approval — mandato não é a única forma de agir.
        self.assertEqual(d.decision, Decisao.REQUIRE_APPROVAL)
        self.assertEqual(d.reason_code, "compromisso_terceiros_exige_decisao_concreta")

    def test_dono_pedindo_efeito_financeiro_sem_mandato_e_negado(self):
        req = _req(classe_efeito=ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL, principal=_principal())
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.DENY)
        self.assertEqual(d.reason_code, "efeito_financeiro_destrutivo_exige_autorizacao_especifica")

    def test_terceiro_portal_nao_pode_autoconceder_compromisso_terceiros(self):
        req = _req(
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            principal=_principal(tipo=TipoPrincipal.TERCEIRO_PORTAL, uid=None),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.DENY)
        self.assertEqual(d.reason_code, "principal_nao_pode_autoconceder")

    def test_rotina_cowork_nao_pode_autoconceder_efeito_financeiro(self):
        req = _req(
            classe_efeito=ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
            principal=_principal(tipo=TipoPrincipal.ROTINA_COWORK, uid=None, origem_humana=False),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.DENY)
        self.assertEqual(d.reason_code, "principal_nao_pode_autoconceder")

    def test_rotina_cowork_com_mandato_e_liberada(self):
        mandato = Mandato(
            mandato_id="m1", finalidade="rotina agendada",
            destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",),
            valido_ate=_AGORA + timedelta(days=1),
        )
        req = _req(
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            principal=_principal(tipo=TipoPrincipal.ROTINA_COWORK, uid=None, origem_humana=False),
            mandatos_aplicaveis=(mandato,),
            sensibilidade="geral",
            missao="rotina agendada",
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.ALLOW)


class TestAvaliarMandatoNaoEscapaSomentePreparacao(unittest.TestCase):
    """Regressão do achado #1 da revisão adversarial: um mandato vigente
    aprovava o efeito direto, pulando o aperto de `somente_preparação` — um
    runner de serviço com mandato conseguia enviar um compromisso a
    terceiros mesmo com o dono tendo restringido a autonomia a preparação
    interna. Corrigido para que a decisão final (venha de mandato ou da
    matriz padrão) sempre passe pelo aperto de estado."""

    def test_mandato_e_apertado_para_prepare_only_quando_somente_preparacao(self):
        mandato = Mandato(
            mandato_id="m1", finalidade="lembrete recorrente",
            destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",),
            valido_ate=_AGORA + timedelta(days=1),
        )
        req = _req(
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            principal=_principal(tipo=TipoPrincipal.RUNNER_SERVICO, uid=None, origem_humana=False),
            mandatos_aplicaveis=(mandato,),
            estado_autonomia=EstadoAutonomia.SOMENTE_PREPARACAO,
            sensibilidade="geral",
            missao="lembrete recorrente",
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.PREPARE_ONLY)
        self.assertEqual(d.reason_code, "autonomia_somente_preparacao")

    def test_mandato_continua_valendo_quando_autonomia_ativa(self):
        # Confirma que a correção não quebrou o caso normal (sem aperto de
        # estado, o mandato ainda libera allow).
        mandato = Mandato(
            mandato_id="m1", finalidade="lembrete recorrente",
            destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",),
            valido_ate=_AGORA + timedelta(days=1),
        )
        req = _req(
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            principal=_principal(tipo=TipoPrincipal.RUNNER_SERVICO, uid=None, origem_humana=False),
            mandatos_aplicaveis=(mandato,),
            estado_autonomia=EstadoAutonomia.ATIVO,
            sensibilidade="geral",
            missao="lembrete recorrente",
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.ALLOW)
        self.assertEqual(d.reason_code, "dentro_de_mandato_vigente")


class TestAvaliarMandatoRebaixaDecisaoPadrao(unittest.TestCase):
    def test_mandato_rebaixa_coordenacao_limitada_para_allow(self):
        mandato = Mandato(
            mandato_id="m1", finalidade="coordenar agenda",
            destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",),
            valido_ate=_AGORA + timedelta(days=1),
        )
        req = _req(
            classe_efeito=ClasseEfeito.COORDENACAO_LIMITADA,
            mandatos_aplicaveis=(mandato,),
            sensibilidade="geral",
            missao="coordenar agenda",
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.ALLOW)
        self.assertEqual(d.reason_code, "dentro_de_mandato_vigente")

    def test_sem_mandato_coordenacao_limitada_e_require_approval(self):
        req = _req(classe_efeito=ClasseEfeito.COORDENACAO_LIMITADA)
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.REQUIRE_APPROVAL)
        self.assertEqual(d.reason_code, "coordenacao_limitada_exige_politica_previa")


class TestAvaliarMatrizEfeitoPadrao(unittest.TestCase):
    def test_observacao_autorizada_allow(self):
        d = policy.avaliar(_req(classe_efeito=ClasseEfeito.OBSERVACAO_AUTORIZADA), agora=_AGORA)
        self.assertEqual((d.decision, d.approval_required), (Decisao.ALLOW, False))

    def test_preparacao_interna_allow(self):
        d = policy.avaliar(_req(classe_efeito=ClasseEfeito.PREPARACAO_INTERNA), agora=_AGORA)
        self.assertEqual((d.decision, d.approval_required), (Decisao.ALLOW, False))
        # Achado P2 #1 da revisão do Codex (PR #191): o reason_code não pode
        # alegar mandato quando a decisão veio da matriz padrão (sem
        # mandato nenhum em mandatos_aplicaveis aqui).
        self.assertEqual(d.reason_code, "preparacao_interna_permitida_por_padrao")

    def test_escrita_interna_reversivel_allow(self):
        d = policy.avaliar(_req(classe_efeito=ClasseEfeito.ESCRITA_INTERNA_REVERSIVEL), agora=_AGORA)
        self.assertEqual((d.decision, d.approval_required), (Decisao.ALLOW, False))
        self.assertEqual(d.reason_code, "escrita_interna_reversivel_permitida_por_padrao")

    def test_coordenacao_limitada_require_approval(self):
        d = policy.avaliar(_req(classe_efeito=ClasseEfeito.COORDENACAO_LIMITADA), agora=_AGORA)
        self.assertEqual((d.decision, d.approval_required), (Decisao.REQUIRE_APPROVAL, True))

    def test_compromisso_terceiros_require_approval(self):
        d = policy.avaliar(_req(classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS), agora=_AGORA)
        self.assertEqual((d.decision, d.approval_required), (Decisao.REQUIRE_APPROVAL, True))

    def test_efeito_financeiro_destrutivo_deny(self):
        d = policy.avaliar(_req(classe_efeito=ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL), agora=_AGORA)
        self.assertEqual((d.decision, d.approval_required), (Decisao.DENY, False))

    def test_operation_hash_sempre_preenchido(self):
        d = policy.avaliar(_req(), agora=_AGORA)
        self.assertIsInstance(d.operation_hash, str)
        self.assertEqual(len(d.operation_hash), 64)  # sha256 hex


class TestAvaliarOrigemHumana(unittest.TestCase):
    """Terceira rodada da revisão do Codex (PR #191): a matriz de efeito
    (seção 5.1 do plano) define, para "Preparação interna" e "Escrita
    interna reversível" SEM mandato vigente, a regra "executar com mandato
    e orçamento válidos"/"executar dentro do mandato" — não ALLOW
    incondicional. A exceção que preserva a baixa fricção prometida na
    seção 5 é a presença de um humano de fato dirigindo o pedido agora
    (`Principal.origem_humana=True` — dono interativo ou cliente assistido
    em tempo real, que já é a própria confirmação); sem essa presença e sem
    mandato, o padrão passa a ser PREPARE_ONLY em vez de ALLOW."""

    def test_preparacao_interna_sem_mandato_e_sem_humano_vira_prepare_only(self):
        req = _req(
            classe_efeito=ClasseEfeito.PREPARACAO_INTERNA,
            principal=_principal(tipo=TipoPrincipal.ROTINA_COWORK, uid=None, origem_humana=False),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.PREPARE_ONLY)
        self.assertEqual(d.reason_code, "preparacao_interna_requer_mandato_ou_humano_presente")
        self.assertFalse(d.approval_required)

    def test_escrita_interna_reversivel_sem_mandato_e_sem_humano_vira_prepare_only(self):
        req = _req(
            classe_efeito=ClasseEfeito.ESCRITA_INTERNA_REVERSIVEL,
            principal=_principal(tipo=TipoPrincipal.RUNNER_SERVICO, uid=None, origem_humana=False),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.PREPARE_ONLY)
        self.assertEqual(d.reason_code, "escrita_interna_reversivel_requer_mandato_ou_humano_presente")
        self.assertFalse(d.approval_required)

    def test_preparacao_interna_com_humano_presente_continua_allow(self):
        # Regressão: dono interativo (humano presente por definição) não é
        # afetado pelo gate — continua ALLOW direto, sem exigir mandato.
        req = _req(
            classe_efeito=ClasseEfeito.PREPARACAO_INTERNA,
            principal=_principal(origem_humana=True),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.ALLOW)
        self.assertEqual(d.reason_code, "preparacao_interna_permitida_por_padrao")

    def test_escrita_interna_reversivel_com_humano_presente_continua_allow(self):
        req = _req(
            classe_efeito=ClasseEfeito.ESCRITA_INTERNA_REVERSIVEL,
            principal=_principal(origem_humana=True),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.ALLOW)
        self.assertEqual(d.reason_code, "escrita_interna_reversivel_permitida_por_padrao")

    def test_preparacao_interna_origem_humana_sem_ser_dono_nao_da_allow_regressao_seguranca(self):
        # Achado do Codex sobre a PR #192: `origem_humana=True` sozinho não
        # é suficiente — nada no sistema de tipos impede um `TERCEIRO_PORTAL`
        # (ou ROTINA_COWORK/RUNNER_SERVICO) de ser construído com
        # `origem_humana=True` (o próprio default do contrato). Um terceiro
        # com humano presente NO PORTAL não é o mesmo que o dono presente —
        # a exceção de baixa fricção da seção 5 é para o DONO, não para
        # "qualquer humano". Agora exige também `eh_dono()`.
        req = _req(
            classe_efeito=ClasseEfeito.PREPARACAO_INTERNA,
            principal=_principal(tipo=TipoPrincipal.TERCEIRO_PORTAL, uid=None, origem_humana=True),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.PREPARE_ONLY)
        self.assertEqual(d.reason_code, "preparacao_interna_requer_mandato_ou_humano_presente")

    def test_escrita_interna_reversivel_origem_humana_sem_ser_dono_nao_da_allow_regressao_seguranca(self):
        # Mesmo achado, ramo ESCRITA_INTERNA_REVERSIVEL — ROTINA_COWORK com
        # origem_humana=True (ex.: configurada por engano, ou um futuro
        # canal que confunde "humano configurou a rotina" com "humano
        # presente agora") não deve receber o mesmo passe do dono interativo.
        req = _req(
            classe_efeito=ClasseEfeito.ESCRITA_INTERNA_REVERSIVEL,
            principal=_principal(tipo=TipoPrincipal.ROTINA_COWORK, uid=None, origem_humana=True),
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.PREPARE_ONLY)
        self.assertEqual(d.reason_code, "escrita_interna_reversivel_requer_mandato_ou_humano_presente")

    def test_mandato_libera_preparacao_interna_mesmo_sem_humano_presente(self):
        # Regressão: um mandato vigente cobre o pedido pelo passo 4/5 de
        # `avaliar()`, que nunca chega a chamar `_decisao_padrao_por_classe`
        # (e portanto nunca consulta `origem_humana`) — o gate desta rodada
        # só se aplica ao fallback SEM mandato, não substitui o mandato.
        mandato = Mandato(
            mandato_id="m1", finalidade="preparar minuta semanal",
            destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",),
            valido_ate=_AGORA + timedelta(days=1),
        )
        req = _req(
            classe_efeito=ClasseEfeito.PREPARACAO_INTERNA,
            principal=_principal(tipo=TipoPrincipal.ROTINA_COWORK, uid=None, origem_humana=False),
            mandatos_aplicaveis=(mandato,),
            sensibilidade="geral",
            missao="preparar minuta semanal",
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.ALLOW)
        self.assertEqual(d.reason_code, "dentro_de_mandato_vigente")


class TestAvaliarSomentePreparacao(unittest.TestCase):
    def test_aperta_escrita_interna_reversivel_para_prepare_only(self):
        req = _req(
            classe_efeito=ClasseEfeito.ESCRITA_INTERNA_REVERSIVEL,
            estado_autonomia=EstadoAutonomia.SOMENTE_PREPARACAO,
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.PREPARE_ONLY)
        self.assertEqual(d.reason_code, "autonomia_somente_preparacao")

    def test_aperta_compromisso_terceiros_para_prepare_only(self):
        req = _req(
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            estado_autonomia=EstadoAutonomia.SOMENTE_PREPARACAO,
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.PREPARE_ONLY)

    def test_nao_afrouxa_leitura(self):
        req = _req(
            classe_efeito=ClasseEfeito.OBSERVACAO_AUTORIZADA,
            estado_autonomia=EstadoAutonomia.SOMENTE_PREPARACAO,
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.ALLOW)

    def test_nao_afrouxa_deny_existente(self):
        req = _req(
            classe_efeito=ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
            estado_autonomia=EstadoAutonomia.SOMENTE_PREPARACAO,
        )
        d = policy.avaliar(req, agora=_AGORA)
        self.assertEqual(d.decision, Decisao.DENY)


class TestMandatoCobre(unittest.TestCase):
    def _mandato(self, **overrides):
        base = dict(
            mandato_id="m1",
            finalidade="avisar fornecedor",
            destinatarios_recursos=("fulano@example.com",),
            classes_conteudo_permitidas=("geral",),
            # Quarta rodada da revisão do Codex (PR #191): `valido_ate=None`
            # (o default do contrato) agora NÃO cobre — ver
            # `test_sem_validade_nao_cobre_regressao_seguranca` abaixo. Cada
            # teste desta classe que não é sobre validade em si precisa de um
            # mandato válido para exercitar a checagem que de fato pretende
            # testar, então o fixture já vem com uma validade futura por
            # padrão (mesmo raciocínio de `missao=m.finalidade` no comentário
            # abaixo); `test_expirado_nao_cobre`/`test_ainda_valido_cobre`
            # sobrescrevem explicitamente.
            valido_ate=_AGORA + timedelta(days=1),
        )
        base.update(overrides)
        return Mandato(**base)

    # A partir da terceira rodada da revisão do Codex (PR #191),
    # `mandato_cobre` compara `missao` contra `finalidade` de forma
    # INCONDICIONAL (fail closed quando `missao` não foi informada — ver
    # `test_missao_nao_informada_nao_cobre_regressao_seguranca` abaixo) —
    # e essa checagem acontece ANTES de destino/classe/horário. Por isso os
    # testes abaixo passam `missao=m.finalidade` mesmo quando o teste não é
    # sobre missão/finalidade: sem isso, todos parariam na checagem de
    # missão antes de chegar na checagem que de fato pretendem exercitar.

    def test_revogado_nunca_cobre(self):
        m = self._mandato(revogado=True, destinatarios_recursos=("*",))
        req = _req(argumentos_resolvidos={"destinatario": "qualquer"}, missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_expirado_nao_cobre(self):
        m = self._mandato(valido_ate=_AGORA - timedelta(days=1), destinatarios_recursos=("*",))
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_ainda_valido_cobre(self):
        m = self._mandato(valido_ate=_AGORA + timedelta(days=1), destinatarios_recursos=("*",))
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_sem_validade_nao_cobre_regressao_seguranca(self):
        # Achado P1 da quarta rodada da revisão do Codex (PR #191): a versão
        # anterior só rejeitava quando `valido_ate` estava PREENCHIDO e no
        # passado — um mandato sem `valido_ate` (o default do contrato)
        # cobria indefinidamente, apesar de "validade" ser uma das condições
        # mínimas do mandato (seção 5.3) e de cada outro campo opcional desta
        # função já ter sido fechado no mesmo sentido. Agora falha fechado:
        # sem validade resolvida, o mandato não cobre.
        m = self._mandato(valido_ate=None, destinatarios_recursos=("*",))
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_destinatario_fora_da_lista_nao_cobre(self):
        m = self._mandato(destinatarios_recursos=("fulano@example.com",))
        req = _req(
            argumentos_resolvidos={"destinatario": "ciclano@example.com"},
            sensibilidade="geral",
            missao=m.finalidade,
        )
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_destinatario_na_lista_cobre(self):
        m = self._mandato(destinatarios_recursos=("fulano@example.com",))
        req = _req(
            argumentos_resolvidos={"destinatario": "fulano@example.com"},
            sensibilidade="geral",
            missao=m.finalidade,
        )
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_curinga_cobre_qualquer_destinatario(self):
        m = self._mandato(destinatarios_recursos=("*",))
        req = _req(
            argumentos_resolvidos={"destinatario": "qualquer@example.com"},
            sensibilidade="geral",
            missao=m.finalidade,
        )
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_substring_nao_ancorada_nao_cobre_regressao_seguranca(self):
        # Achado #2 da revisão adversarial: "@empresa.com" NÃO pode cobrir
        # "chefe@empresa.com.malicioso.net" só porque a substring aparece —
        # isso deixaria um mandato de domínio ser contornado por um
        # destinatário composto que embute o domínio autorizado como parte
        # de um domínio diferente.
        m = self._mandato(destinatarios_recursos=("@empresa.com",))
        req = _req(
            argumentos_resolvidos={"destinatario": "chefe@empresa.com.malicioso.net"},
            sensibilidade="geral",
            missao=m.finalidade,
        )
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_dominio_com_arroba_cobre_destinatario_legitimo(self):
        # O padrão de domínio "@dominio" continua funcionando para o caso
        # legítimo (sufixo exato, âncora no "@" real).
        m = self._mandato(destinatarios_recursos=("@empresa.com",))
        req = _req(
            argumentos_resolvidos={"destinatario": "chefe@empresa.com"},
            sensibilidade="geral",
            missao=m.finalidade,
        )
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_dominio_com_arroba_nao_cobre_domino_parecido(self):
        m = self._mandato(destinatarios_recursos=("@empresa.com",))
        req = _req(
            argumentos_resolvidos={"destinatario": "chefe@outraempresa.com"},
            sensibilidade="geral",
            missao=m.finalidade,
        )
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_destinos_vazio_nao_cobre_regressao_seguranca(self):
        # Achado P1 #2 da segunda rodada da revisão do Codex (PR #191):
        # `destinos and not (...)` pulava a checagem inteira quando
        # `destinatarios_recursos` vinha vazio (`set()` é falso em Python),
        # tratando um mandato SEM escopo de destino como se cobrisse
        # QUALQUER destinatário — o oposto do que o contrato pede (destino é
        # uma condição mínima do mandato, seção 5.3). Agora falha fechado.
        m = self._mandato(destinatarios_recursos=())
        req = _req(
            argumentos_resolvidos={"destinatario": "qualquer@example.com"},
            sensibilidade="geral",
            missao=m.finalidade,
        )
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_classe_conteudo_fora_da_lista_nao_cobre(self):
        m = self._mandato(destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",))
        req = _req(sensibilidade="financeiro", missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_classe_conteudo_na_lista_cobre(self):
        m = self._mandato(destinatarios_recursos=("*",), classes_conteudo_permitidas=("financeiro",))
        req = _req(sensibilidade="financeiro", missao=m.finalidade)
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_classes_vazio_nao_cobre_regressao_seguranca(self):
        # Mesmo achado, mesmo raciocínio para `classes_conteudo_permitidas`
        # vazio: sem classe declarada, o mandato não cobre nada.
        m = self._mandato(destinatarios_recursos=("*",), classes_conteudo_permitidas=())
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_sensibilidade_ausente_nao_cobre_mandato_restrito_regressao_seguranca(self):
        # Achado P1 #2 da revisão do Codex (PR #191): a versão original só
        # rejeitava quando `sensibilidade` estava preenchida e fora da
        # lista — como o contrato permite `sensibilidade=None` por padrão,
        # um mandato restrito a ("geral",) cobria por engano qualquer
        # pedido cujo chamador não preenchesse o campo, inclusive um efeito
        # financeiro/destrutivo. Agora falha fechado: ausência de
        # classificação NÃO passa por um mandato que declara classes.
        m = self._mandato(destinatarios_recursos=("*",), classes_conteudo_permitidas=("geral",))
        req = _req(sensibilidade=None, missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_fora_do_horario_permitido_nao_cobre(self):
        m = self._mandato(
            destinatarios_recursos=("*",),
            horario_permitido_inicio="09:00",
            horario_permitido_fim="18:00",
        )
        req = _req(sensibilidade="geral", missao=m.finalidade)
        agora_fora = datetime(2026, 9, 7, 22, 0, tzinfo=timezone.utc)
        self.assertFalse(policy.mandato_cobre(m, req, agora_fora))

    def test_dentro_do_horario_permitido_cobre(self):
        m = self._mandato(
            destinatarios_recursos=("*",),
            horario_permitido_inicio="09:00",
            horario_permitido_fim="18:00",
        )
        req = _req(sensibilidade="geral", missao=m.finalidade)
        agora_dentro = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
        self.assertTrue(policy.mandato_cobre(m, req, agora_dentro))

    def test_sem_restricao_de_horario_sempre_cobre(self):
        m = self._mandato(destinatarios_recursos=("*",))
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_horario_so_com_inicio_nao_cobre_regressao_seguranca(self):
        # Achado P1 da quarta rodada da revisão do Codex (PR #191): a versão
        # anterior só aplicava a restrição de horário quando os DOIS
        # extremos vinham preenchidos (`and`) — um mandato com só
        # `horario_permitido_inicio` (dado parcial/malformado; os dois
        # campos são independentemente opcionais no contrato) pulava a
        # checagem inteira, cobrindo qualquer horário como se não houvesse
        # restrição nenhuma. Agora falha fechado.
        m = self._mandato(destinatarios_recursos=("*",), horario_permitido_inicio="09:00")
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_horario_so_com_fim_nao_cobre_regressao_seguranca(self):
        m = self._mandato(destinatarios_recursos=("*",), horario_permitido_fim="18:00")
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_horario_com_strings_vazias_nao_cobre_regressao_seguranca(self):
        # Achado da revisão adversarial da própria correção acima: a checagem
        # externa original usava `inicio or fim` (truthiness), então
        # `"" or ""` era falsy e pulava a checagem de horário inteira — os
        # dois campos "presentes" mas vazios escapavam até da checagem de
        # configuração parcial, o mesmo padrão de bug que esta rodada fechou
        # em `estado_autonomia_atual` (valor presente e falsy tratado como
        # ausente). Corrigido para `is not None`.
        m = self._mandato(
            destinatarios_recursos=("*",),
            horario_permitido_inicio="", horario_permitido_fim="",
        )
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_janela_noturna_cobre_horario_apos_meia_noite(self):
        # Achado #3 da revisão adversarial: janela "22:00"-"06:00" (cruza a
        # meia-noite) era insatisfazível na versão original — corrigida.
        m = self._mandato(
            destinatarios_recursos=("*",),
            horario_permitido_inicio="22:00",
            horario_permitido_fim="06:00",
        )
        req = _req(sensibilidade="geral", missao=m.finalidade)
        agora_02h = datetime(2026, 9, 7, 2, 0, tzinfo=timezone.utc)
        self.assertTrue(policy.mandato_cobre(m, req, agora_02h))

    def test_janela_noturna_cobre_horario_antes_da_meia_noite(self):
        m = self._mandato(
            destinatarios_recursos=("*",),
            horario_permitido_inicio="22:00",
            horario_permitido_fim="06:00",
        )
        req = _req(sensibilidade="geral", missao=m.finalidade)
        agora_23h = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc)
        self.assertTrue(policy.mandato_cobre(m, req, agora_23h))

    def test_janela_noturna_nao_cobre_horario_fora_da_janela(self):
        m = self._mandato(
            destinatarios_recursos=("*",),
            horario_permitido_inicio="22:00",
            horario_permitido_fim="06:00",
        )
        req = _req(sensibilidade="geral", missao=m.finalidade)
        agora_meio_dia = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(policy.mandato_cobre(m, req, agora_meio_dia))

    def test_limite_por_janela_excedido_nao_cobre(self):
        # Achado P1 #1 da revisão do Codex (PR #191): agora há um lugar
        # concreto (`Mandato.usos_na_janela_atual`) para o chamador
        # informar a contagem já resolvida, e `mandato_cobre` aplica o
        # limite quando essa contagem é conhecida.
        m = self._mandato(
            destinatarios_recursos=("*",), limite_por_janela=1, usos_na_janela_atual=1,
        )
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_limite_por_janela_nao_excedido_cobre(self):
        m = self._mandato(
            destinatarios_recursos=("*",), limite_por_janela=3, usos_na_janela_atual=2,
        )
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_limite_por_janela_com_contagem_desconhecida_nao_cobre_regressao_seguranca(self):
        # Terceira rodada da revisão do Codex (PR #191): a correção
        # anterior só rejeitava quando `usos_na_janela_atual` já vinha
        # PREENCHIDO e no limite — com `limite_por_janela` declarado mas a
        # contagem ainda `None` (nenhum chamador a resolve nesta
        # sub-entrega), o limite era simplesmente ignorado, e um mandato
        # limitado cobria como se não tivesse limite nenhum. Agora falha
        # fechado: contagem desconhecida contra um limite declarado NÃO
        # cobre (mesmo raciocínio já aplicado a `sensibilidade`/
        # `destinatarios_recursos`/`classes_conteudo_permitidas`). Não
        # precisa de `missao=` — o limite é checado antes da missão.
        m = self._mandato(destinatarios_recursos=("*",), limite_por_janela=1)
        req = _req(sensibilidade="geral")
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_orcamento_maximo_com_saldo_desconhecido_nao_cobre_regressao_seguranca(self):
        # P02 passo 8, sub-entrega 4/N: mesmo raciocínio fail-closed já
        # aplicado a `limite_por_janela`/`usos_na_janela_atual` — um teto de
        # orçamento DECLARADO no mandato exige que o chamador tenha
        # RESOLVIDO `PolicyRequest.orcamento_restante`; enquanto ninguém
        # resolve esse saldo (`None`, o default), o mandato não cobre. Não
        # precisa de `missao=` — orçamento é checado antes da missão.
        m = self._mandato(destinatarios_recursos=("*",), orcamento_maximo=1000.0)
        req = _req(sensibilidade="geral")
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_orcamento_restante_esgotado_nao_cobre(self):
        m = self._mandato(destinatarios_recursos=("*",), orcamento_maximo=1000.0)
        req = _req(sensibilidade="geral", missao=m.finalidade, orcamento_restante=0.0)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_orcamento_restante_negativo_nao_cobre(self):
        m = self._mandato(destinatarios_recursos=("*",), orcamento_maximo=1000.0)
        req = _req(sensibilidade="geral", missao=m.finalidade, orcamento_restante=-50.0)
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_orcamento_restante_nan_nao_cobre_regressao_seguranca(self):
        # Achado da revisão adversarial desta sub-entrega: `float('nan')`
        # não é `None` nem `<= 0` (TODA comparação com NaN é `False`,
        # inclusive `nan <= 0`), então uma primeira versão desta checagem
        # (`if request.orcamento_restante <= 0: return False`) deixava um
        # saldo NaN passar como se fosse positivo válido — o oposto do
        # fail-closed que esta checagem existe para garantir. Reproduzível
        # hoje via `simular_politica` MCP: `json.loads` aceita o token
        # `NaN` por padrão, e `hermes_tools._principal_simulado` repassa
        # `orcamento_restante` sem validar o tipo.
        m = self._mandato(destinatarios_recursos=("*",), orcamento_maximo=1000.0)
        req = _req(sensibilidade="geral", missao=m.finalidade, orcamento_restante=float("nan"))
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_orcamento_restante_positivo_cobre(self):
        m = self._mandato(destinatarios_recursos=("*",), orcamento_maximo=1000.0)
        req = _req(sensibilidade="geral", missao=m.finalidade, orcamento_restante=250.0)
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_sem_orcamento_maximo_declarado_cobre_mesmo_sem_orcamento_restante(self):
        # Mandato sem teto de orçamento (default `orcamento_maximo=None`) —
        # nem toda finalidade tem dimensão financeira; a ausência de
        # `orcamento_restante` no pedido não pode bloquear um mandato que
        # nunca declarou teto nenhum.
        m = self._mandato(destinatarios_recursos=("*",))
        req = _req(sensibilidade="geral", missao=m.finalidade)
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_finalidade_diferente_da_missao_nao_cobre(self):
        # Achado P1 #3 da revisão do Codex (PR #191): antes, um mandato
        # emitido para um propósito podia cobrir por coincidência um pedido
        # de propósito totalmente diferente, desde que destino/classe/
        # horário batessem.
        m = self._mandato(destinatarios_recursos=("*",), finalidade="avisar fornecedor sobre atraso")
        req = _req(sensibilidade="geral", missao="cobrar fatura em aberto")
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))

    def test_finalidade_igual_a_missao_cobre(self):
        m = self._mandato(destinatarios_recursos=("*",), finalidade="avisar fornecedor sobre atraso")
        req = _req(sensibilidade="geral", missao="avisar fornecedor sobre atraso")
        self.assertTrue(policy.mandato_cobre(m, req, _AGORA))

    def test_missao_nao_informada_nao_cobre_regressao_seguranca(self):
        # Terceira rodada da revisão do Codex (PR #191): a versão anterior
        # só comparava `missao` contra `finalidade` quando AMBAS vinham
        # preenchidas — como `Mandato.finalidade` é campo obrigatório
        # (seção 5.3: "condições mínimas" inclui finalidade), essa
        # checagem nunca disparava quando o chamador simplesmente não
        # preenchia `missao` (`None`, o default de `PolicyRequest`),
        # deixando QUALQUER mandato com finalidade declarada cobrir um
        # pedido sem missão nenhuma. Agora falha fechado: missão ausente
        # nunca bate com uma finalidade declarada.
        m = self._mandato(destinatarios_recursos=("*",), finalidade="avisar fornecedor sobre atraso")
        req = _req(sensibilidade="geral")
        self.assertFalse(policy.mandato_cobre(m, req, _AGORA))


class TestConsultarPolitica(unittest.TestCase):
    def test_escopo_mcp_lista_piso(self):
        r = policy.consultar_politica("mcp")
        self.assertEqual(set(r["ferramentas_com_confirmacao_obrigatoria"]), set(mcp_server._CONFIRMACAO_OBRIGATORIA))
        self.assertEqual(r["escopo"], "mcp")

    def test_escopo_mcp_traz_classe_de_efeito_por_ferramenta(self):
        r = policy.consultar_politica("mcp")
        self.assertEqual(
            set(r["classe_efeito_por_ferramenta"]), set(policy.FLOOR_CONFIRMACAO_OBRIGATORIA)
        )
        self.assertEqual(
            r["classe_efeito_por_ferramenta"]["registrar_aporte_investimento"],
            ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL.value,
        )

    def test_escopo_generico_traz_referencia_padrao(self):
        r = policy.consultar_politica("qualquer_outro")
        self.assertEqual(r["policy_id"], policy._POLICY_ID_PADRAO)


class TestSimularPolitica(unittest.TestCase):
    def test_conta_permitidos_e_bloqueados(self):
        pedidos = [
            _req(ferramenta="ler_algo", classe_efeito=ClasseEfeito.OBSERVACAO_AUTORIZADA),
            _req(
                ferramenta="registrar_aporte_investimento",
                classe_efeito=ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
            ),
        ]
        r = policy.simular_politica(pedidos, agora=_AGORA)
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["permitidos"], 1)
        # registrar_aporte_investimento está no piso -> require_approval, não deny.
        self.assertEqual(r["bloqueados"], 0)
        self.assertEqual(r["requer_aprovacao"], 1)
        self.assertEqual(r["somente_preparacao"], 0)
        self.assertEqual(r["adiados"], 0)

    def test_nao_conflaciona_prepare_only_com_requer_aprovacao(self):
        # Achado P2 #2 da revisão do Codex (PR #191): a versão original
        # computava requer_aprovacao por subtração (total - permitidos -
        # bloqueados), o que contava um PREPARE_ONLY como se exigisse
        # aprovação — mas `approval_required` é False nesse caso.
        pedidos = [
            _req(
                ferramenta="editar_algo_reversivel",
                classe_efeito=ClasseEfeito.ESCRITA_INTERNA_REVERSIVEL,
                estado_autonomia=EstadoAutonomia.SOMENTE_PREPARACAO,
            ),
        ]
        r = policy.simular_politica(pedidos, agora=_AGORA)
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["permitidos"], 0)
        self.assertEqual(r["bloqueados"], 0)
        self.assertEqual(r["requer_aprovacao"], 0)
        self.assertEqual(r["somente_preparacao"], 1)
        self.assertEqual(r["resultados"][0]["decisao"]["decision"], Decisao.PREPARE_ONLY.value)
        self.assertFalse(r["resultados"][0]["decisao"]["approval_required"])

    def test_nao_muta_nada_apenas_le(self):
        pedidos = [_req()]
        antes = frozenset(policy.FLOOR_CONFIRMACAO_OBRIGATORIA)
        policy.simular_politica(pedidos, agora=_AGORA)
        self.assertEqual(policy.FLOOR_CONFIRMACAO_OBRIGATORIA, antes)


class TestPrepararPolitica(unittest.TestCase):
    def test_base_version_divergente_retorna_erro(self):
        r = policy.preparar_politica({}, base_version=999)
        self.assertIsNone(r["diff"])
        self.assertIn("erro", r)

    def test_sem_mudanca_nao_exige_justificativa(self):
        proposta = {"ferramentas_com_confirmacao_obrigatoria": sorted(policy.FLOOR_CONFIRMACAO_OBRIGATORIA)}
        r = policy.preparar_politica(proposta, base_version=policy._POLICY_VERSION_PADRAO)
        self.assertEqual(r["diff"]["adicionadas"], [])
        self.assertEqual(r["diff"]["removidas"], [])
        self.assertFalse(r["exige_justificativa_explicita"])
        self.assertIsNone(r["aviso"])

    def test_remocao_exige_justificativa_explicita(self):
        restante = sorted(policy.FLOOR_CONFIRMACAO_OBRIGATORIA)[1:]
        r = policy.preparar_politica(
            {"ferramentas_com_confirmacao_obrigatoria": restante},
            base_version=policy._POLICY_VERSION_PADRAO,
        )
        self.assertEqual(len(r["diff"]["removidas"]), 1)
        self.assertTrue(r["exige_justificativa_explicita"])
        self.assertIsNotNone(r["aviso"])


class TestEstadoAutonomiaAtual(unittest.TestCase):
    def test_documento_ausente_retorna_ativo(self):
        db = MagicMock()
        db.collection.return_value.document.return_value.get.return_value = MagicMock(exists=False)
        self.assertEqual(policy.estado_autonomia_atual(db), EstadoAutonomia.ATIVO)

    def test_falha_de_leitura_cai_para_somente_preparacao_nao_para_ativo(self):
        # Achado #4 da revisão adversarial: uma falha de leitura real
        # (Firestore indisponível) não pode colapsar no mesmo default do
        # "documento ausente" — isso seria fail-open no dia em que esta
        # função passar a ser consultada por um canal de verdade.
        db = MagicMock()
        db.collection.return_value.document.return_value.get.side_effect = RuntimeError("boom")
        self.assertEqual(policy.estado_autonomia_atual(db), EstadoAutonomia.SOMENTE_PREPARACAO)

    def test_valor_invalido_no_documento_cai_para_somente_preparacao(self):
        db = MagicMock()
        snap = MagicMock(exists=True)
        snap.to_dict.return_value = {"global": "valor-desconhecido-de-versao-futura"}
        db.collection.return_value.document.return_value.get.return_value = snap
        self.assertEqual(policy.estado_autonomia_atual(db), EstadoAutonomia.SOMENTE_PREPARACAO)

    def test_valor_vazio_presente_cai_para_somente_preparacao_regressao_seguranca(self):
        # Achado P1 da quarta rodada da revisão do Codex (PR #191): a versão
        # anterior usava `dados.get(dominio) or dados.get("global") or
        # ATIVO`, que tratava um valor PRESENTE MAS FALSY (`""` — por
        # exemplo um documento em escrita parcial) do mesmo jeito que uma
        # chave AUSENTE, caindo direto em ATIVO sem nunca passar pelo
        # fail-closed. Agora a chave é procurada por ausência, não por
        # truthiness: um valor presente e vazio é tratado como valor
        # inválido (mesmo caminho de `test_valor_invalido_no_documento_...`
        # acima), não como "nada configurado".
        db = MagicMock()
        snap = MagicMock(exists=True)
        snap.to_dict.return_value = {"global": ""}
        db.collection.return_value.document.return_value.get.return_value = snap
        self.assertEqual(policy.estado_autonomia_atual(db), EstadoAutonomia.SOMENTE_PREPARACAO)

    def test_documento_existe_mas_vazio_retorna_ativo(self):
        # Diferente do caso acima: aqui NENHUMA chave (nem `dominio` nem
        # "global") está presente no documento — isso ainda é "nada
        # configurado para este domínio", não um valor corrompido, e
        # continua caindo em ATIVO, igual ao documento totalmente ausente.
        db = MagicMock()
        snap = MagicMock(exists=True)
        snap.to_dict.return_value = {}
        db.collection.return_value.document.return_value.get.return_value = snap
        self.assertEqual(policy.estado_autonomia_atual(db), EstadoAutonomia.ATIVO)

    def test_le_estado_do_dominio_pedido(self):
        db = MagicMock()
        snap = MagicMock(exists=True)
        snap.to_dict.return_value = {"global": "somente_preparacao"}
        db.collection.return_value.document.return_value.get.return_value = snap
        self.assertEqual(policy.estado_autonomia_atual(db, dominio="global"), EstadoAutonomia.SOMENTE_PREPARACAO)

    def test_cai_para_global_quando_dominio_especifico_ausente(self):
        db = MagicMock()
        snap = MagicMock(exists=True)
        snap.to_dict.return_value = {"global": "pausado"}
        db.collection.return_value.document.return_value.get.return_value = snap
        self.assertEqual(policy.estado_autonomia_atual(db, dominio="financas"), EstadoAutonomia.PAUSADO)


class TestRegistrarDecisao(unittest.TestCase):
    def test_grava_apenas_chaves_dos_argumentos_nunca_valores(self):
        db = MagicMock()
        req = _req(argumentos_resolvidos={"destinatario": "segredo@example.com", "texto": "conteudo sensivel"})
        decisao = policy.avaliar(req, agora=_AGORA)
        policy.registrar_decisao(db, req, decisao)

        db.collection.assert_called_once_with("policy_decisions")
        gravado = db.collection.return_value.add.call_args[0][0]
        self.assertEqual(gravado["argumentos_chaves"], ["destinatario", "texto"])
        gravado_str = repr(gravado)
        self.assertNotIn("segredo@example.com", gravado_str)
        self.assertNotIn("conteudo sensivel", gravado_str)
        self.assertEqual(gravado["decision"], decisao.decision.value)
        self.assertEqual(gravado["operation_hash"], decisao.operation_hash)

    def test_falha_de_escrita_nao_propaga_excecao(self):
        db = MagicMock()
        db.collection.return_value.add.side_effect = RuntimeError("firestore indisponivel")
        req = _req()
        decisao = policy.avaliar(req, agora=_AGORA)
        try:
            policy.registrar_decisao(db, req, decisao)
        except Exception as exc:  # pragma: no cover - falharia o teste se levantasse
            self.fail(f"registrar_decisao não deveria propagar exceção, levantou: {exc}")


class TestDecisaoPiso(unittest.TestCase):
    """`decisao_piso()` — P02 sub-entrega 6/N: orquestração de
    estado_autonomia_atual()+PolicyRequest+avaliar()+registrar_decisao() num
    único ponto reutilizável por qualquer canal. O candidato natural para o
    primeiro consumidor novo era hermes_core_logic.py::
    schedule_whatsapp_message (canal Telegram) — chegou a ser implementado
    nesta sub-entrega, mas foi revertido: hermes_core_logic.py tem 276257
    caracteres, acima do limite de 200000 da API de escrita do Argos (ver
    docstring de decisao_piso() e docs/autonomia/execucao.md). Esta função
    segue testada e pronta para esse ou outro consumidor futuro."""

    def _db_com_estado(self, valor=None, existe=True):
        db = MagicMock()
        snap = MagicMock(exists=existe)
        snap.to_dict.return_value = {"global": valor} if valor is not None else {}
        db.collection.return_value.document.return_value.get.return_value = snap
        return db

    def test_ferramenta_fora_do_piso_retorna_none_sem_tocar_firestore(self):
        db = MagicMock()
        principal = _principal()
        resultado = policy.decisao_piso(db, principal, "ler_algo", {})
        self.assertIsNone(resultado)
        db.collection.assert_not_called()

    def test_estado_ativo_retorna_require_approval_e_registra(self):
        db = self._db_com_estado(existe=False)  # documento ausente -> ATIVO
        principal = _principal(tipo=TipoPrincipal.DONO_INTERATIVO)
        resultado = policy.decisao_piso(
            db, principal, "schedule_whatsapp_message",
            {"contact_number": "551199999999", "message": "oi"},
        )
        self.assertEqual(resultado.decision, Decisao.REQUIRE_APPROVAL)
        # registrar_decisao foi chamado: uma segunda leitura/escrita em
        # policy_decisions, além da leitura de system/autonomy_state.
        self.assertIn(
            "policy_decisions",
            [c.args[0] for c in db.collection.call_args_list if c.args],
        )

    def test_estado_pausado_bloqueia_com_deny(self):
        db = self._db_com_estado(valor="pausado")
        principal = _principal(tipo=TipoPrincipal.DONO_INTERATIVO)
        resultado = policy.decisao_piso(db, principal, "schedule_whatsapp_message", {})
        self.assertEqual(resultado.decision, Decisao.DENY)

    def test_estado_somente_preparacao_bloqueia_com_prepare_only(self):
        db = self._db_com_estado(valor="somente_preparacao")
        principal = _principal(tipo=TipoPrincipal.DONO_INTERATIVO)
        resultado = policy.decisao_piso(db, principal, "schedule_whatsapp_message", {})
        self.assertEqual(resultado.decision, Decisao.PREPARE_ONLY)

    def test_falha_ao_ler_estado_nao_propaga_excecao_e_cai_fechado(self):
        # estado_autonomia_atual() já é fail-safe internamente (cai em
        # SOMENTE_PREPARACAO numa falha de leitura) — este teste prova que
        # decisao_piso() não introduz nenhum caminho novo de propagação por
        # cima dela.
        db = MagicMock()
        db.collection.return_value.document.return_value.get.side_effect = RuntimeError("boom")
        principal = _principal(tipo=TipoPrincipal.DONO_INTERATIVO)
        try:
            resultado = policy.decisao_piso(db, principal, "schedule_whatsapp_message", {})
        except Exception as exc:  # pragma: no cover - falharia o teste se levantasse
            self.fail(f"decisao_piso não deveria propagar exceção, levantou: {exc}")
        self.assertEqual(resultado.decision, Decisao.PREPARE_ONLY)

    def test_falha_ao_registrar_decisao_nao_propaga_excecao(self):
        db = self._db_com_estado(existe=False)
        db.collection.return_value.add.side_effect = RuntimeError("firestore indisponivel")
        principal = _principal(tipo=TipoPrincipal.DONO_INTERATIVO)
        try:
            resultado = policy.decisao_piso(db, principal, "schedule_whatsapp_message", {})
        except Exception as exc:  # pragma: no cover - falharia o teste se levantasse
            self.fail(f"decisao_piso não deveria propagar exceção, levantou: {exc}")
        self.assertEqual(resultado.decision, Decisao.REQUIRE_APPROVAL)

    def test_falha_em_avaliar_nao_propaga_excecao_e_bloqueia_com_deny(self):
        # P02 sub-entrega 12/N: `avaliar(request)` era chamada sem
        # try/except ao redor — um `principal` malformado (None, ou um
        # objeto sem `.eh_dono()`/`.tipo`) propagaria a exceção de dentro
        # dela em vez de cair fail-closed, pendência registrada desde a
        # sub-entrega 8/N, endereçada agora que decisao_piso() tem
        # consumidores reais (mcp_jobs.py, confirm_whatsapp do Telegram).
        #
        # Usa mock.patch em vez de passar um principal malformado de
        # verdade: para os 5 tools do piso (o único caso que decisao_piso()
        # atende — classe_efeito vem de CLASSE_EFEITO_PISO, que hoje tem
        # exatamente as mesmas chaves de FLOOR_CONFIRMACAO_OBRIGATORIA),
        # avaliar() nunca toca request.principal — o ramo `if veio_do_piso`
        # fixa a decisão sem consultar o tipo/eh_dono() do principal (só o
        # passo 6, estado_autonomia, é consultado). Ou seja, um principal
        # malformado não derruba avaliar() HOJE por este caminho específico
        # — mas a proteção deve valer pela mesma razão que o resto desta
        # função já é fail-safe: não depender de nenhuma invariante de outro
        # módulo (ex.: CLASSE_EFEITO_PISO continuar sendo subconjunto exato
        # de FLOOR_CONFIRMACAO_OBRIGATORIA) para não propagar uma exceção.
        db = self._db_com_estado(existe=False)  # documento ausente -> ATIVO
        with patch.object(
            policy, "avaliar", side_effect=AttributeError("'NoneType' object has no attribute 'eh_dono'")
        ):
            try:
                resultado = policy.decisao_piso(db, None, "schedule_whatsapp_message", {"x": "y"})
            except Exception as exc:  # pragma: no cover - falharia o teste se levantasse
                self.fail(f"decisao_piso não deveria propagar exceção, levantou: {exc}")
        self.assertEqual(resultado.decision, Decisao.DENY)
        self.assertEqual(resultado.reason_code, "erro_interno_avaliacao_politica")
        # registrar_decisao ainda é tentado (mesmo com principal malformado,
        # ela própria já é fail-safe — request.principal.uid dentro do seu
        # próprio try/except, ver TestRegistrarDecisao).
        self.assertIn(
            "policy_decisions",
            [c.args[0] for c in db.collection.call_args_list if c.args],
        )

    def test_falha_em_avaliar_preserva_operation_hash_da_operacao_real(self):
        db = self._db_com_estado(existe=False)
        argumentos = {"contact_number": "5511999999999", "message": "oi"}
        with patch.object(policy, "avaliar", side_effect=RuntimeError("boom")):
            resultado = policy.decisao_piso(db, None, "schedule_whatsapp_message", argumentos)
        esperado = policy._hash_operacao(
            PolicyRequest(
                principal=None, ferramenta="schedule_whatsapp_message",
                classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
                argumentos_resolvidos=argumentos,
            )
        )
        self.assertEqual(resultado.operation_hash, esperado)

class TestDecisaoErroAvaliacao(unittest.TestCase):
    """`decisao_erro_avaliacao()` isolada — fallback fail-closed usado tanto
    por `decisao_piso()` quanto por `mcp_server.py::_decisao_piso_mcp`
    quando `avaliar()` não pôde ser executada (P02 sub-entrega 12/N)."""

    def test_e_sempre_deny_nunca_prepare_only_ou_require_approval(self):
        req = _req(ferramenta="registrar_aporte_investimento")
        decisao = policy.decisao_erro_avaliacao(req, motivo_legivel="motivo de teste")
        self.assertEqual(decisao.decision, Decisao.DENY)
        self.assertEqual(decisao.motivo_legivel, "motivo de teste")

    def test_nao_depende_de_principal_bem_formado(self):
        req = _req(ferramenta="criar_rascunho_email")
        req_malformado = replace(req, principal=None)
        # Não deve levantar AttributeError mesmo com principal=None: só usa
        # ferramenta/argumentos_resolvidos via _hash_operacao.
        decisao = policy.decisao_erro_avaliacao(req_malformado, motivo_legivel="x")
        self.assertEqual(decisao.operation_hash, policy._hash_operacao(req_malformado))


if __name__ == "__main__":
    unittest.main()
