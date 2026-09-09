"""Wrapper de I/O que resolve `autonomy.contracts.Mandato` a partir do
mecanismo de promoção de autonomia já existente e em produção
(`system/mcp_access.tipos_promovidos`, escrito por
`promocao_autonomia.decidir_promocao_autonomia` e lido por
`outbox_aprovacao._tipos_promovidos`/`criar_rascunho`).

Este módulo existe porque a decisão de produto — "que mandatos existem" e
"que categorias de conteúdo o Hermes pode usar com terceiros sem
confirmação humana por instância" — já tinha resposta funcional antes do
tipo `Mandato` existir: um `tipo` de rascunho de WhatsApp só entra em
`tipos_promovidos` depois que `promocao_autonomia.tipos_elegiveis_para_
promocao()` mede volume real e taxa de aprovação-sem-edição no histórico de
`whatsapp_outbox`, e o André decide explicitamente (aceitar/adiar/nunca)
via `decidir_promocao_autonomia()`. Ver
docs/autonomia/proposta-p02-mandato-io-wrapper.md para o raciocínio
completo, incluindo a tabela de mapeamento campo-a-campo e as duas decisões
de escopo que ficaram para o André — ambas respondidas por ele em
09/09/2026 ("pode seguir com suas recomendações, e qualquer destinatário"):

- `destinatarios_recursos = ("*",)` — qualquer destinatário reconhecido,
  preservando exatamente o comportamento atual de `criar_rascunho`/
  `liberar_rascunhos_promovidos` (nenhuma restrição por contato hoje).
- `valido_ate` — janela rolante automática (opção "a" da proposta):
  recalculada a cada chamada a partir de `agora`, nunca lida de um valor
  persistido. O mandato nunca expira de fato enquanto o `tipo` continuar em
  `tipos_promovidos`; a única forma real de revogação é removê-lo de lá
  (`forma_revogacao`, abaixo) — não muda a UX de `decidir_promocao_
  autonomia`, que já funciona hoje sem perguntar prazo.

Deliberadamente FORA do escopo deste módulo (ver proposta, seção "O que NÃO
está nesta proposta"): taxonomia nova de categorias de conteúdo (usa o
vocabulário livre que já existe, `tipo`, não inventa um enum fechado à
parte); `limite_por_janela`/`orcamento_maximo`/`horario_permitido_*` —
nenhum desses tem hoje uma fonte de dados real por trás (tipos promovidos
não têm dimensão de contagem-por-janela, orçamento nem horário conhecidas),
então ficam `None` — o que `autonomy.policy.mandato_cobre()` já trata
corretamente como "sem restrição adicional além do que já existe hoje",
não como dado ausente que precisaria falhar fechado (essas checagens só
disparam quando o campo correspondente está DECLARADO).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from autonomy.contracts import Mandato

_JANELA_VALIDADE_DIAS_PADRAO = 60


def _to_iso_data(val) -> str | None:
    """Mesma forma de `_to_iso` já duplicada em outbox_aprovacao.py e
    promocao_autonomia.py (datetime/Firestore Timestamp/str -> ISO) —
    repetida aqui em vez de importada de qualquer um dos dois para não criar
    uma dependência nova entre módulos de I/O que hoje não se importam entre
    si; é um helper puro de poucas linhas, o custo de manter os três em
    sincronia é baixo."""
    if val is None:
        return None
    if isinstance(val, (datetime, )):
        return val.isoformat()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if hasattr(val, "to_datetime"):
        return val.to_datetime().isoformat()
    return str(val)


def mandato_tipo_promovido(
    db,
    tipo: str,
    *,
    agora: datetime | None = None,
    janela_validade_dias: int = _JANELA_VALIDADE_DIAS_PADRAO,
) -> Mandato | None:
    """Resolve o `Mandato` correspondente a um `tipo` de rascunho de
    WhatsApp, se e somente se ele estiver em
    `system/mcp_access.tipos_promovidos` agora — não no momento em que o
    rascunho foi criado. Esta releitura (em vez de confiar no status
    `aguardando_janela` do documento, decidido no passado) é o ponto central
    desta sub-entrega: fecha a janela em que um `tipo` promovido no
    momento da criação do rascunho é revogado (`decidir_promocao_autonomia`
    removendo-o da lista, hoje só por edição direta do documento — não há
    tool dedicada) antes de a janela de cancelamento vencer, e o rascunho
    ainda assim seria enviado sozinho por carregar um status decidido no
    passado.

    Retorna `None` quando `tipo` (normalizado: strip + lower, mesmo padrão
    de `outbox_aprovacao._tipos_promovidos`) não está promovido agora —
    inclusive quando a leitura de `system/mcp_access` falha (fail-closed:
    uma falha de leitura nunca deve ser tratada como "está promovido").
    Quem chama isto com o retorno `None` deve tratar como "nenhum mandato
    cobre este pedido", não pular a checagem.

    `valido_ate`: ver docstring do módulo — janela rolante de
    `janela_validade_dias` dias a partir de `agora`, recalculada a cada
    chamada.
    """
    tipo_limpo = str(tipo or "").strip().lower()
    if not tipo_limpo:
        return None

    agora = agora or datetime.now(timezone.utc)

    try:
        snap = db.collection("system").document("mcp_access").get()
        promovidos: set[str] = set()
        if snap.exists:
            lista = (snap.to_dict() or {}).get("tipos_promovidos") or []
            promovidos = {str(t).strip().lower() for t in lista if str(t).strip()}
    except Exception as err:
        print(f"[MandatosIO] Falha ao ler tipos_promovidos de system/mcp_access: {err}")
        return None

    if tipo_limpo not in promovidos:
        return None

    origem_autorizacao = f"decidir_promocao_autonomia: tipo '{tipo_limpo}' aceito (data não disponível)"
    try:
        snap_sug = db.collection("promocoes_autonomia_sugeridas").document(tipo_limpo).get()
        if snap_sug.exists:
            dados_sug = snap_sug.to_dict() or {}
            if dados_sug.get("status") == "aceita":
                data_iso = _to_iso_data(dados_sug.get("decidida_em"))
                if data_iso:
                    origem_autorizacao = (
                        f"decidir_promocao_autonomia: tipo '{tipo_limpo}' aceito em {data_iso}"
                    )
    except Exception as err:
        # Não-crítico: só rastreabilidade extra em `origem_autorizacao`,
        # nunca afeta se o mandato cobre o pedido -- por isso não retorna
        # None aqui, ao contrário da leitura de `tipos_promovidos` acima.
        print(f"[MandatosIO] Falha ao ler origem_autorizacao para '{tipo_limpo}': {err}")

    try:
        return Mandato(
            mandato_id=f"tipo_promovido:{tipo_limpo}",
            finalidade=f"envio_promovido:{tipo_limpo}",
            destinatarios_recursos=("*",),
            classes_conteudo_permitidas=(tipo_limpo,),
            valido_ate=agora + timedelta(days=janela_validade_dias),
            origem_autorizacao=origem_autorizacao,
            forma_revogacao=(
                f"Remover '{tipo_limpo}' de system/mcp_access.tipos_promovidos "
                "(hoje só por edição direta do documento; não há tool dedicada "
                "para revogar um tipo já promovido)."
            ),
        )
    except ValueError as err:
        # Achado BLOQUEANTE da revisão adversarial desta sub-entrega:
        # `Mandato.__post_init__` (autonomy/contracts.py) levanta ValueError
        # estruturalmente quando `classes_conteudo_permitidas` contém
        # "outro" (em qualquer capitalização) -- e "outro" é o DEFAULT de
        # `tipo` para todo rascunho que não especifica um
        # (`outbox_aprovacao.criar_rascunho`, `tools/hermes_tools.py`).
        # `promocao_autonomia.tipos_elegiveis_para_promocao()` não exclui
        # "outro" da varredura por volume/taxa de aprovação -- se um humano
        # aceitar essa sugestão via `decidir_promocao_autonomia(db, "outro",
        # "aceitar")` (ação já suportada, sem validação extra ali), "outro"
        # entra em `system/mcp_access.tipos_promovidos` e, sem este guard,
        # toda chamada a `mandato_tipo_promovido("outro")` levantaria sem
        # ser capturada por ninguém no chamador -- derrubando o LOTE INTEIRO
        # de `liberar_rascunhos_promovidos` (nenhum outro rascunho do lote,
        # nem de tipos diferentes e válidos, seria processado naquele
        # ciclo), não só falhando fechado para este tipo. Trata como "não
        # promovido de verdade" -- consistente com o próprio contrato desta
        # função (retorna None, nunca levanta) e com a regra da seção 5.3 do
        # plano ("outro" nunca habilita envio autônomo).
        print(
            f"[MandatosIO] '{tipo_limpo}' está em tipos_promovidos mas não é um "
            f"rótulo válido para Mandato.classes_conteudo_permitidas ({err}); "
            "tratando como não promovido."
        )
        return None
