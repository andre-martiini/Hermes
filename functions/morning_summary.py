"""
Resumo Matinal — Camada 1: coletor prospectivo determinístico.

Par simétrico de `personal_diary._collect_diary_material`: mesmo princípio de
varrer todas as superfícies do Hermes num único coletor, mas apontado para
frente — o diário das 21h30 fecha o dia, este abre.

Regra de arquitetura, a mesma de `health_weekly_report.py`: **a conta é feita
em Python**. Não há nenhuma chamada de LLM neste módulo. O que ele devolve já
é o resultado final — números, listas e a escolha dos focos do dia por regra
explícita e auditável (`_escolher_foco`). Uma camada de narrativa por modelo
pode ser acoplada depois por cima deste dict, sem recalcular nada e sem poder
inventar número nenhum.

O que este resumo mostra e nenhuma outra tela do sistema mostra:

  - **A herança da madrugada.** `daily_reset_job.py` arrasta toda ação atrasada
    para hoje às 00:00, incrementa `degradation_count` e marca
    `auto_data_atualizada`. Hoje esses dois campos só existem como badge no
    card (`src/components/ui/UIComponents.tsx`) e cor da borda
    (`src/components/calendar/TaskCard.tsx`) — nunca são somados em lugar
    nenhum. A diferença entre "escolhi fazer hoje" e "o sistema empurrou para
    hoje às 00:00" se perde todas as manhãs, inclusive no briefing das 5h
    (`daily_morning_briefing.py`), que lista as duas coisas no mesmo bullet.

  - **As filas de decisão** que só aparecem quando se abre a tela certa:
    sugestões de vínculo sinal↔ação, fusões de contato, contas fixas vencendo,
    notificações do planejador de IA ainda na fila. O critério para entrar aqui
    é estrito: precisa ser algo que *espera uma decisão do usuário*. Consolidação
    de WhatsApp não entra (ver `_coletar_filas`).

  - **As metas de `estrategia_pessoal` sem movimento.** O elo curto↔longo prazo
    (`tarefas.estrategia_objetivo_id`) já existe e nunca é atravessado num
    lugar só: qual meta as ações de hoje servem, e qual está parada há quanto
    tempo. Com uma ressalva importante: nem todo pilar é executado por ações —
    o pilar `saude` vive nos registros do módulo Saúde, e é de lá que sai o
    movimento dele (ver `_coletar_estrategia`).

  - **O que da rotina de hoje já foi cumprido.** Só para as rotinas que deixam
    rastro conferível — pesagem, cintura e os dois check-ins. As demais são
    avisos ilustrativos e não ganham marcador (ver `_rotina_verificavel`).

Persistido em `resumo_matinal/{YYYY-MM-DD}`, simétrico a
`diario_pessoal/{YYYY-MM-DD}`. O campo `foco[]` fica gravado de propósito: é o
que permite, depois, medir aderência (dos focos propostos, quantos saíram) sem
precisar reconstruir a manhã.

Sistema pessoal de um único usuário — as coleções não são filtradas por
`userId`, mesma premissa já adotada em `ai_notification_planner.py`.
"""

from datetime import datetime, timedelta, timezone

from firebase_admin import firestore
from firebase_functions import https_fn, scheduler_fn, options

import os

import subtarefas

VERSAO = "v1"

MAX_FOCO = 3
DEGRADACAO_CRITICA = 3
PRAZO_IMINENTE_DIAS = 2
PRAZO_DURO_HORIZONTE_DIAS = 7
CONTA_VENCENDO_DIAS = 3
META_PARADA_DIAS = 10
AMOSTRA_FILA = 3

# Janela em que faz sentido procurar buraco livre na agenda.
JANELA_DIA_INICIO = "07:00"
JANELA_DIA_FIM = "19:00"
JANELA_LIVRE_MINIMA_MIN = 45
MAX_JANELAS_LIVRES = 3

STATUS_ATIVOS = ["em andamento", "stand-by"]

_DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]

def _pilar(valor) -> str:
    """Pilar comparável: minúsculas e sem acento.

    Só importa nos documentos legados, que são justamente os que não têm
    `gerida_por_acoes` gravada e por isso dependem da derivação por pilar — e são
    os que podem ter grafia livre. `.lower()` sozinho não basta: "Saúde" vira
    "saúde", que continua diferente de "saude".
    """
    import unicodedata

    bruto = str(valor or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", bruto)
                   if unicodedata.category(c) != "Mn")


_PILAR_LABEL = {
    "carreira": "Carreira",
    "financas": "Finanças",
    "saude": "Saúde",
    "intelectual": "Intelectual",
    "estilo_vida": "Estilo de vida",
}


# --------------------------------------------------------------------------- #
# Helpers de data                                                              #
# --------------------------------------------------------------------------- #

def _hoje_sp() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")


def _shift(date_str: str, days: int) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


def _dias_entre(de: str, ate: str) -> int:
    return (datetime.strptime(ate, "%Y-%m-%d") - datetime.strptime(de, "%Y-%m-%d")).days


def _js_weekday(date_str: str) -> int:
    """Domingo=0..Sábado=6 — a convenção usada em `health_telegram_reminders.daysOfWeek`
    (herdada do `Date.getDay()` do HealthView.tsx), não a do Python (segunda=0)."""
    return (datetime.strptime(date_str, "%Y-%m-%d").weekday() + 1) % 7


def _data_valida(valor) -> str:
    """Normaliza um campo de data do Firestore para 'YYYY-MM-DD' ou string vazia.
    Os placeholders '-' e '0000-00-00' são usados no lugar de null pelo frontend."""
    texto = str(valor or "").strip()
    if texto in ("", "-", "0000-00-00"):
        return ""
    return texto[:10]


def _query_por_prefixo_de_data(db, collection: str, field: str, date_str: str) -> list:
    """Mesma técnica de `personal_diary._query_by_date_range`: comparação lexicográfica
    de strings ISO, que funciona tanto para datas puras quanto para datetimes completos."""
    try:
        return list(
            db.collection(collection)
            .where(filter=firestore.FieldFilter(field, ">=", date_str))
            .where(filter=firestore.FieldFilter(field, "<", _shift(date_str, 1)))
            .stream()
        )
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar {collection}.{field} em {date_str}: {exc}")
        return []


def _hhmm_para_min(valor) -> int | None:
    texto = str(valor or "").strip()
    if len(texto) < 4 or ":" not in texto:
        return None
    try:
        h, m = texto.split(":")[:2]
        total = int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return None
    return total if 0 <= total <= 24 * 60 else None


def _min_para_hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _ts_local_hhmm(valor) -> str | None:
    """Timestamp nativo do Firestore (UTC) -> 'HH:MM' no fuso de São Paulo."""
    from zoneinfo import ZoneInfo

    if not hasattr(valor, "astimezone"):
        return None
    try:
        return valor.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M")
    except Exception:
        return None


def _hora_do_iso(valor) -> str | None:
    """'2026-08-22T14:30:00-03:00' -> '14:30'. Evento de dia inteiro (data pura) -> None."""
    texto = str(valor or "")
    if "T" not in texto:
        return None
    return texto.split("T", 1)[1][:5] or None


# --------------------------------------------------------------------------- #
# Coleta                                                                       #
# --------------------------------------------------------------------------- #

def _coletar_acoes(db, hoje: str) -> dict:
    """Varredura única de `tarefas` ativas. Tudo que as outras seções precisam saber
    sobre ações sai daqui — a coleção é lida uma vez só."""
    horizonte_prazo = _shift(hoje, PRAZO_DURO_HORIZONTE_DIAS)

    por_lane: dict[str, list] = {"avanco": [], "continuo": [], "aguardando_terceiro": []}
    atrasadas, prazos_duros = [], []
    carga_semana = {_shift(hoje, i): 0 for i in range(7)}
    acoes_por_meta: dict[str, list] = {}
    movimento_por_meta: dict[str, str] = {}

    total_ativas = herdadas = criticas = cobrar = sem_plano = 0

    try:
        docs = list(db.collection("tarefas").where(filter=firestore.FieldFilter("status", "in", STATUS_ATIVOS)).stream())
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar tarefas: {exc}")
        docs = []

    for doc in docs:
        data = doc.to_dict() or {}
        titulo = str(data.get("titulo") or "(sem título)")
        data_limite = _data_valida(data.get("data_limite"))
        prazo_final = _data_valida(data.get("prazo_final"))
        # A faixa é derivada do estado das subtarefas, com o valor gravado como
        # entrada — e não o contrário. Antes de 26/08/2026 nada no sistema
        # escrevia esse campo além do reset da virada do dia, então as 43 ações
        # ativas estavam todas em `avanco` por falta de produtor, não por
        # estarem todas avançando.
        plano = data.get("plano_acao") or []
        lane = subtarefas.derivar_lane(plano, data.get("execution_lane"))
        if lane not in por_lane:
            lane = "avanco"
        # Espelha, não move: o contador da macroação é o maior entre o que está
        # gravado e os das subtarefas, para que as ações que já acumularam
        # adiamentos sem histórico por etapa não zerem de uma vez.
        degradacao = subtarefas.degradacao_da_acao(plano, data.get("degradation_count"))
        herdada = bool(data.get("auto_data_atualizada"))
        e_cobrar = titulo.startswith("[COBRAR]")
        meta_id = str(data.get("estrategia_objetivo_id") or "").strip()

        total_ativas += 1
        if data_limite in carga_semana:
            carga_semana[data_limite] += 1

        # Último movimento da ação — alimenta o "dias sem movimento" da meta ligada.
        if meta_id:
            acomp = data.get("acompanhamento") or []
            ultima_nota = max(
                (_data_valida(e.get("data")) for e in acomp if isinstance(e, dict)),
                default="",
            )
            movimento = max(
                _data_valida(data.get("data_atualizacao")),
                _data_valida(data.get("data_conclusao")),
                _data_valida(data.get("data_criacao")),
                ultima_nota,
            )
            if movimento > movimento_por_meta.get(meta_id, ""):
                movimento_por_meta[meta_id] = movimento

        if prazo_final and hoje <= prazo_final <= horizonte_prazo:
            prazos_duros.append({
                "id": doc.id,
                "titulo": titulo,
                "prazo_final": prazo_final,
                "dias": _dias_entre(hoje, prazo_final),
            })

        # Só o que cai hoje (ou ficou para trás) entra no corpo do resumo — o resto
        # da semana aparece agregado em `carga_semana`.
        e_de_hoje = data_limite == hoje
        e_atrasada = bool(data_limite) and data_limite < hoje
        if not e_de_hoje and not e_atrasada:
            continue

        etapas_feitas, etapas_totais = subtarefas.contar(plano)
        if not etapas_totais:
            sem_plano += 1

        # `subtarefa_do_dia` escolhe pela menor data prevista; `proximo_passo`
        # sempre escolheu pela ordem do plano. Numa ação sem datas por etapa —
        # que são todas as anteriores a 26/08/2026 — as duas coincidem, porque
        # a herança faz todas as etapas caírem na data da macroação e o empate
        # resolve pela ordem.
        corrente = subtarefas.subtarefa_corrente(plano, data_limite)
        proximo_passo = subtarefas.texto_de(corrente) if corrente else None
        subtarefa_do_dia = None
        if corrente:
            subtarefa_do_dia = {
                "id": corrente.get("id"),
                "texto": subtarefas.texto_de(corrente),
                "estado": subtarefas.estado_de(corrente),
                "data_prevista": subtarefas.data_prevista_de(corrente, data_limite, plano),
                "aguardando_de": corrente.get("aguardando_de"),
                "degradation_count": int(corrente.get("degradation_count") or 0),
            }

        # A espera some hoje: a macroação aparece em `avanco` por causa de outra
        # etapa e a pendência de terceiro fica invisível. Aqui ela tem lista
        # própria, independente da faixa da ação.
        esperando = [
            {"id": i.get("id"), "texto": subtarefas.texto_de(i),
             "aguardando_de": i.get("aguardando_de"),
             "data_prevista": subtarefas.data_prevista_de(i, data_limite, plano)}
            for i in subtarefas.aguardando_terceiros(plano)
        ]

        item = {
            "id": doc.id,
            "titulo": titulo,
            "status": data.get("status"),
            "area_tematica": data.get("area_tematica"),
            "projeto": data.get("projeto"),
            "horario_inicio": data.get("horario_inicio") or None,
            "horario_fim": data.get("horario_fim") or None,
            "execution_lane": lane,
            "degradation_count": degradacao,
            "herdada": herdada,
            "cobrar": e_cobrar,
            "atrasada": e_atrasada,
            "data_limite": data_limite,
            "prazo_final": prazo_final or None,
            "proximo_passo": proximo_passo,
            "subtarefa_do_dia": subtarefa_do_dia,
            "aguardando_terceiro": esperando,
            "etapas_feitas": etapas_feitas,
            "etapas_totais": etapas_totais,
            "estrategia_objetivo_id": meta_id or None,
        }

        if herdada:
            herdadas += 1
        if degradacao >= DEGRADACAO_CRITICA:
            criticas += 1
        if e_cobrar:
            cobrar += 1
        if e_atrasada:
            atrasadas.append(item)
        if meta_id:
            acoes_por_meta.setdefault(meta_id, []).append(item)

        por_lane[lane].append(item)

    def _ordenar(itens: list) -> list:
        # Agendadas primeiro (por horário), depois por degradação decrescente.
        return sorted(itens, key=lambda t: (
            t["horario_inicio"] or "99:99",
            -t["degradation_count"],
            t["titulo"],
        ))

    for lane in por_lane:
        por_lane[lane] = _ordenar(por_lane[lane])

    prazos_duros.sort(key=lambda p: p["prazo_final"])

    return {
        "por_lane": por_lane,
        "atrasadas": _ordenar(atrasadas),
        "prazos_duros": prazos_duros,
        "carga_semana": [{"data": d, "total": carga_semana[d]} for d in sorted(carga_semana)],
        "acoes_por_meta": acoes_por_meta,
        "movimento_por_meta": movimento_por_meta,
        "contadores": {
            "ativas": total_ativas,
            "hoje": sum(len(v) for v in por_lane.values()),
            "herdadas": herdadas,
            "criticas": criticas,
            "cobrar": cobrar,
            "sem_plano": sem_plano,
        },
    }


def _coletar_agenda(db, hoje: str) -> dict:
    eventos = []
    for doc in _query_por_prefixo_de_data(db, "google_calendar_events", "data_inicio", hoje):
        data = doc.to_dict() or {}
        eventos.append({
            "titulo": data.get("titulo") or "(sem título)",
            "inicio": _hora_do_iso(data.get("data_inicio")),
            "fim": _hora_do_iso(data.get("data_fim")),
            "dia_inteiro": _hora_do_iso(data.get("data_inicio")) is None,
        })
    eventos.sort(key=lambda e: e["inicio"] or "00:00")
    return {"eventos": eventos, "janelas_livres": _calcular_janelas_livres(eventos)}


def _calcular_janelas_livres(eventos: list) -> list:
    """Buracos de pelo menos `JANELA_LIVRE_MINIMA_MIN` na janela útil do dia.
    Eventos de dia inteiro não bloqueiam agenda — são marcadores, não compromissos."""
    inicio = _hhmm_para_min(JANELA_DIA_INICIO) or 0
    fim = _hhmm_para_min(JANELA_DIA_FIM) or 24 * 60

    ocupado = []
    for ev in eventos:
        if ev["dia_inteiro"]:
            continue
        ini = _hhmm_para_min(ev["inicio"])
        if ini is None:
            continue
        # Evento sem hora de fim ocupa 1h por convenção — melhor superestimar
        # ocupação do que anunciar uma janela livre que não existe.
        f = _hhmm_para_min(ev["fim"]) or (ini + 60)
        ocupado.append((max(ini, inicio), min(max(f, ini + 15), fim)))

    ocupado.sort()
    fundidos: list[list[int]] = []
    for ini, f in ocupado:
        if f <= inicio or ini >= fim:
            continue
        if fundidos and ini <= fundidos[-1][1]:
            fundidos[-1][1] = max(fundidos[-1][1], f)
        else:
            fundidos.append([ini, f])

    janelas, cursor = [], inicio
    for ini, f in fundidos:
        if ini - cursor >= JANELA_LIVRE_MINIMA_MIN:
            janelas.append({"inicio": _min_para_hhmm(cursor), "fim": _min_para_hhmm(ini), "minutos": ini - cursor})
        cursor = max(cursor, f)
    if fim - cursor >= JANELA_LIVRE_MINIMA_MIN:
        janelas.append({"inicio": _min_para_hhmm(cursor), "fim": _min_para_hhmm(fim), "minutos": fim - cursor})

    return janelas[:MAX_JANELAS_LIVRES]


def _fila(total: int, amostra: list, rota: str) -> dict:
    """Uma fila do painel "Esperando voce decidir".

    `rota` vazia significa que a fila **nao tem tela** — o card e informativo e
    nao deve virar botao. Ate 28/08/2026 toda fila levava a alguma rota, e as
    que nao tinham destino real usavam "dashboard": o clique ia para a tela
    inicial, e o usuario ficava procurando o que nao existia.
    """
    return {"total": total, "amostra": amostra[:AMOSTRA_FILA], "rota": rota}


# Os dois jeitos de a varredura de elevações ver só parte da janela. Enquanto um
# deles estiver gravado, o marcador fica parado — então o intervalo não se perde,
# mas também não anda: é isso que estes avisos existem para tornar visível.
_AVISOS_DE_VARREDURA = {
    "indice_ausente": {
        "titulo": "A varredura de elevações rodou sem as ações concluídas",
        "detalhe": (
            "Falta o índice composto `tarefas (status, data_conclusao)` no Firestore. "
            "A varredura continua rodando com as ações em andamento, mas trabalho "
            "concluído — que é o caso mais forte, porque é o que mais deixa documento "
            "pronto — não vira sugestão até o índice ser publicado. Nada se perde: a "
            "janela não avança enquanto isso."),
    },
    "candidatas_demais": {
        "titulo": "A varredura de elevações teve mais candidatas do que consegue avaliar",
        "detalhe": (
            "Sobraram ações concluídas fora do recorte que vai para o modelo, então a "
            "janela não avançou — nada se perde, mas o período fica parado até o "
            "acúmulo baixar. Decidir as sugestões pendentes é o que destrava."),
    },
    "limite_atingido": {
        "titulo": "A varredura de elevações viu só parte do período",
        "detalhe": (
            "Há mais ações concluídas no período do que a varredura lê de uma vez. Ela "
            "avaliou uma parte e não avançou a janela, então nada se perde — mas também "
            "não anda sozinho: o acúmulo precisa de uma decisão sobre passar o passivo "
            "de uma vez."),
    },
}


def _coletar_passivo_de_elevacao(db) -> dict | None:
    """Onde a recuperação do passivo está: quanto falta e quanto sai por rodada.

    Não é fila (não espera decisão) e não é aviso (nada está errado) — é uma
    esteira andando devagar de propósito, e sem número visível ninguém sabe
    quando mandar parar. Mandar parar é como este caminho termina.

    O número é gravado pela varredura, que roda uma vez por semana; ler aqui
    seria uma agregação por dia para um dado que muda por semana.
    """
    try:
        snap = db.collection("system_usage").document("elevacoes_sugeridas").get()
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar o passivo de elevação: {exc}")
        return None
    if not snap.exists:
        return None
    dados = snap.to_dict() or {}
    if not dados.get("passivo_cursor"):
        return None
    return {
        # `None` quando a contagem falhou: melhor não mostrar número do que um errado.
        "restantes": dados.get("passivo_restantes"),
        "cota_por_rodada": int(os.environ.get("ELEVACAO_COTA_PASSIVO", "10")),
        "ate": str(dados.get("passivo_cursor") or "").split("|")[0] or None,
        "esgotou": bool(dados.get("passivo_esgotou")),
    }


def _coletar_avisos_do_sistema(db) -> list[dict]:
    """Coisas do proprio Hermes que pararam de funcionar direito.

    Nao e fila: fila e decisao esperando o usuario, e entra na contagem de
    pendencias. Isto e outra coisa — o sistema avisando que esta rodando pela
    metade. Sem uma superficie assim, um modo degradado silencioso (roda, nao da
    erro, so ve menos) so existiria num log que ninguem le.
    """
    avisos = []
    try:
        snap = db.collection("system_usage").document("elevacoes_sugeridas").get()
        degradada = (snap.to_dict() or {}).get("varredura_degradada") if snap.exists else None
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar o estado da varredura: {exc}")
        return avisos

    motivo = degradada.get("motivo") if isinstance(degradada, dict) else None
    texto = _AVISOS_DE_VARREDURA.get(motivo)
    if texto:
        avisos.append({
            "id": f"elevacao_{motivo}",
            "gravidade": "atencao",
            "titulo": texto["titulo"],
            "detalhe": texto["detalhe"],
            "desde": degradada.get("data"),
        })
    return avisos


def _coletar_filas(db, hoje: str) -> dict:
    """As decisões pendentes que hoje só existem dentro de uma tela específica."""
    filas = {}

    # Sugestões de vínculo sinal↔ação (e-mail, WhatsApp, SIPAC, agenda, páginas).
    try:
        docs = list(db.collection("email_action_suggestions").where(filter=firestore.FieldFilter("status", "==", "pending")).limit(60).stream())
        amostra = sorted(
            ({"titulo": (d.to_dict() or {}).get("titulo_sinal") or "(sem título)",
              "canal": (d.to_dict() or {}).get("canal") or "email",
              "desde": _data_valida((d.to_dict() or {}).get("analyzed_at"))} for d in docs),
            key=lambda s: s["desde"] or "9999",
        )
        filas["sugestoes_vinculo"] = _fila(len(docs), amostra, "dashboard")
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar email_action_suggestions: {exc}")

    # Elevacoes sugeridas: o trabalho ja feito que rende um ativo se alguem
    # perguntar.
    #
    # Rota VAZIA, de proposito: nao existe tela que liste elevacoes nem que ofereca
    # aceitar, adiar ou nunca — isso se decide pelo copiloto, com
    # `decidir_elevacao`. Apontar para "strategy" tornaria o card clicavel e
    # levaria a uma tela sem a fila e sem a decisao, que e exatamente o erro
    # descrito no docstring de `_fila` algumas linhas acima: fila sem destino real
    # usando uma rota qualquer, e o usuario procurando o que nao existe.
    try:
        docs = [d.to_dict() or {} for d in db.collection("elevacoes_sugeridas")
                .where(filter=firestore.FieldFilter("status", "==", "pendente")).limit(20).stream()]
        if docs:
            amostra = [{"titulo": d.get("titulo_acao") or "(sem título)",
                        "ativo": d.get("ativo_possivel") or "",
                        "objetivo": d.get("nome_objetivo") or ""} for d in docs]
            filas["elevacoes"] = _fila(len(docs), amostra, "")
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar elevacoes_sugeridas: {exc}")

    # `whatsapp_consolidacoes` sem `task_id` NÃO entra aqui, de propósito: consolidar
    # uma conversa é muitas vezes um fim em si (ler o que foi dito), e as duas saídas
    # possíveis — anexar a uma ação ou não fazer nada — são ambas estados finais
    # legítimos. Uma consolidação parada não é uma decisão pendente, é um arquivo.

    # Fusões de contato aguardando decisão.
    try:
        docs = list(db.collection("contact_merge_requests").where(filter=firestore.FieldFilter("status", "==", "pending")).limit(40).stream())
        amostra = [{
            "titulo": f"{(d.to_dict() or {}).get('primary_name') or '?'} ↔ {(d.to_dict() or {}).get('secondary_name') or '?'}",
            "motivo": (d.to_dict() or {}).get("reason"),
        } for d in docs]
        filas["fusoes_contatos"] = _fila(len(docs), amostra, "contacts")
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar contact_merge_requests: {exc}")

    # Notificações propostas pelo planejador de IA ainda na fila.
    try:
        docs = list(db.collection("scheduled_notifications").where(filter=firestore.FieldFilter("status", "==", "pending")).limit(20).stream())
        amostra = [{
            "titulo": (d.to_dict() or {}).get("title") or "(sem título)",
            # `send_at` é datetime nativo (não string ISO) — gravado assim por
            # ai_notification_planner.propor_notificacao.
            "quando": _ts_local_hhmm((d.to_dict() or {}).get("send_at")),
        } for d in docs]
        # Sem rota: estas notificacoes NAO tem tela. Elas sao entregues pelo
        # Telegram no horario de `send_at`, e a decisao (util/dispensar) acontece
        # nos botoes da propria mensagem. Apontar para "dashboard" fazia o card
        # parecer clicavel e levava o usuario para a tela inicial, que nao tem
        # nada a ver com elas.
        filas["notificacoes_ia"] = _fila(len(docs), amostra, "")
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar scheduled_notifications: {exc}")

    filas["contas"] = _coletar_contas(db, hoje)
    return filas


def _coletar_contas(db, hoje: str) -> dict:
    """
    Contas fixas vencidas ou vencendo em até `CONTA_VENCENDO_DIAS`. Cobre a virada
    de mês: no fim do mês, o vencimento seguinte está no documento do mês que vem.

    Olha SÓ o mês corrente, de propósito. `fixed_bills` tem dezenas de docs de
    meses antigos com `isPaid: false` — são registros do início do uso do sistema
    que foram pagos e nunca marcados, não dívida real (confirmado pelo usuário em
    2026-08-22). Varrer a coleção inteira encheria o painel de ruído histórico e
    faria a fila perder credibilidade.
    """
    ano, mes, dia = (int(p) for p in hoje.split("-"))
    limite = dia + CONTA_VENCENDO_DIAS

    def _mes_seguinte(m: int, a: int) -> tuple[int, int]:
        return (1, a + 1) if m == 12 else (m + 1, a)

    def _buscar(mes_1based: int, ano_alvo: int) -> list:
        try:
            # `month` é gravado 0-11 pelo frontend (índice de Date.getMonth()).
            return list(
                db.collection("fixed_bills")
                .where(filter=firestore.FieldFilter("month", "==", mes_1based - 1))
                .where(filter=firestore.FieldFilter("year", "==", ano_alvo))
                .limit(80)
                .stream()
            )
        except Exception as exc:
            print(f"[ResumoMatinal] Falha ao consultar fixed_bills {mes_1based}/{ano_alvo}: {exc}")
            return []

    pendentes = []
    for doc in _buscar(mes, ano):
        data = doc.to_dict() or {}
        if data.get("isPaid"):
            continue
        due = int(data.get("dueDay") or 0)
        if not due or due > limite:
            continue
        pendentes.append({
            "titulo": data.get("description") or "(sem descrição)",
            "valor": data.get("amount"),
            "vencimento": f"{ano}-{mes:02d}-{due:02d}",
            "dias": due - dia,
            "vencida": due < dia,
        })

    # Só olha o mês seguinte se a janela de 3 dias atravessa a virada.
    from calendar import monthrange
    if limite > monthrange(ano, mes)[1]:
        prox_mes, prox_ano = _mes_seguinte(mes, ano)
        sobra = limite - monthrange(ano, mes)[1]
        for doc in _buscar(prox_mes, prox_ano):
            data = doc.to_dict() or {}
            due = int(data.get("dueDay") or 0)
            if data.get("isPaid") or not due or due > sobra:
                continue
            pendentes.append({
                "titulo": data.get("description") or "(sem descrição)",
                "valor": data.get("amount"),
                "vencimento": f"{prox_ano}-{prox_mes:02d}-{due:02d}",
                "dias": monthrange(ano, mes)[1] - dia + due,
                "vencida": False,
            })

    pendentes.sort(key=lambda c: c["dias"])
    return _fila(len(pendentes), pendentes, "finance")


def _rotina_verificavel(rotina: dict) -> str | None:
    """
    Nem toda rotina de saúde é verificável, e as que não são não devem ganhar
    marcador de feito/não feito — "almoçar com calma" e "janela alimentar" são
    avisos para acompanhar o dia, não itens de checklist.

    Só entram aqui as rotinas que deixam rastro conferível numa coleção:
    pesagem (`health_weights`), cintura (`health_waist`) e os dois check-ins
    (`health_exercise_logs.pain.morning`/`.evening`, gravados pelo callback
    `health_checkin:` em hermes_core_logic.py).

    Resolve por `category` quando existe uma (é o que o usuário controla na UI)
    e cai para o `id` nas duas rotinas que nasceram como `custom`.
    """
    categoria = str(rotina.get("category") or "")
    if categoria == "checkin_morning":
        return "checkin_manha"
    if categoria == "checkin_night":
        return "checkin_noite"
    rotina_id = str(rotina.get("id") or "")
    if rotina_id == "daily_weighin":
        return "pesagem"
    if rotina_id == "waist_saturday":
        return "cintura"
    return None


def _ultima_medida(db, colecao: str, campo: str, hoje: str, dias: int = 60) -> dict | None:
    """Ultimo valor registrado numa colecao de medicao, com a data dele.

    Separada de `_coletar_saude` para ser testavel: aquela importa de `main`, e um
    teste do valor da medida nao deveria arrastar o modulo inteiro junto.
    """
    try:
        medidas = sorted(
            ((str((d.to_dict() or {}).get("date") or "")[:10], float((d.to_dict() or {}).get(campo) or 0))
             for d in db.collection(colecao)
             .where(filter=firestore.FieldFilter("date", ">=", _shift(hoje, -dias)))
             .where(filter=firestore.FieldFilter("date", "<=", hoje)).stream()),
            key=lambda m: m[0],
        )
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar {colecao}: {exc}")
        return None
    validas = [m for m in medidas if m[1] > 0]
    if not validas:
        return None
    return {"ultimo": validas[-1][1], "data": validas[-1][0]}


def _coletar_saude(db, hoje: str, ontem: str) -> dict:
    from main import _cached_doc_get

    saude: dict = {
        "rotinas_hoje": [],
        "pesagem_registrada": False,
        "cintura_registrada": False,
        "checkin_manha": False,
        "checkin_noite": False,
        "peso": None,
        "dor_ontem": None,
        # Data do registro mais recente do módulo Saúde. É daqui que sai o
        # "movimento" das metas do pilar saúde — ver _coletar_estrategia.
        "ultimo_registro": None,
    }

    dia_js = _js_weekday(hoje)
    # Mesma resolução do motor de lembretes (main.check_and_send_reminders): os
    # padrões vêm do código e o que estiver em `health_telegram_reminders` sobrepõe.
    from health_routines import DEFAULT_HEALTH_REMINDERS

    rotinas = {item["id"]: item for item in DEFAULT_HEALTH_REMINDERS}
    try:
        for doc in db.collection("health_telegram_reminders").stream():
            data = doc.to_dict() or {}
            data["id"] = data.get("id") or doc.id
            rotinas[doc.id] = data
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar health_telegram_reminders: {exc}")

    rotinas_do_dia = []
    for rotina in rotinas.values():
        if not rotina.get("enabled", True):
            continue
        dias = rotina.get("daysOfWeek")
        if isinstance(dias, list) and dias and dia_js not in dias:
            continue
        rotinas_do_dia.append({
            "titulo": rotina.get("title") or "Rotina de saúde",
            "hora": rotina.get("time"),
            "categoria": rotina.get("category"),
            "verificavel": _rotina_verificavel(rotina),
        })
    rotinas_do_dia.sort(key=lambda r: r["hora"] or "99:99")

    # --- O que o sistema consegue confirmar que já aconteceu hoje ---
    saude["pesagem_registrada"] = bool(_query_por_prefixo_de_data(db, "health_weights", "date", hoje))
    saude["cintura_registrada"] = bool(_query_por_prefixo_de_data(db, "health_waist", "date", hoje))

    try:
        log_hoje = db.collection("health_exercise_logs").document(hoje).get()
        dor_hoje = ((log_hoje.to_dict() or {}) if log_hoje.exists else {}).get("pain") or {}
        saude["checkin_manha"] = dor_hoje.get("morning") is not None
        saude["checkin_noite"] = dor_hoje.get("evening") is not None
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar health_exercise_logs de {hoje}: {exc}")

    feito_por_chave = {
        "pesagem": saude["pesagem_registrada"],
        "cintura": saude["cintura_registrada"],
        "checkin_manha": saude["checkin_manha"],
        "checkin_noite": saude["checkin_noite"],
    }
    for r in rotinas_do_dia:
        # `None` (não verificável) é diferente de `False` (verificável e ainda não
        # feito) — a UI usa essa distinção para não marcar aviso ilustrativo.
        r["feito"] = feito_por_chave.get(r["verificavel"]) if r["verificavel"] else None
    saude["rotinas_hoje"] = rotinas_do_dia

    try:
        pesos = sorted(
            ((str((d.to_dict() or {}).get("date") or "")[:10], float((d.to_dict() or {}).get("weight") or 0))
             for d in db.collection("health_weights")
             .where(filter=firestore.FieldFilter("date", ">=", _shift(hoje, -14)))
             .where(filter=firestore.FieldFilter("date", "<=", hoje)).stream()),
            key=lambda p: p[0],
        )
        pesos = [p for p in pesos if p[1] > 0]
        if pesos:
            recentes = [w for d, w in pesos if d >= _shift(hoje, -6)]
            config = _cached_doc_get(db, "health_settings", "config")
            alvo = ((config.to_dict() or {}) if config.exists else {}).get("targetWeight")
            saude["peso"] = {
                "ultimo": pesos[-1][1],
                "data": pesos[-1][0],
                # Média de 2 pontos não é confiável — mesmo corte usado em health_weekly_report.
                "media7": round(sum(recentes) / len(recentes), 2) if len(recentes) >= 3 else None,
                "alvo": alvo,
                "falta": round(pesos[-1][1] - float(alvo), 2) if alvo else None,
            }
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar health_weights: {exc}")

    try:
        log = db.collection("health_exercise_logs").document(ontem).get()
        if log.exists:
            dor = (log.to_dict() or {}).get("pain") or {}
            saude["dor_ontem"] = {
                "manha": dor.get("morning"),
                "noite": dor.get("evening"),
                "ciatica": bool(dor.get("sciatica")),
                "crise": bool(dor.get("crisis")),
            }
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar health_exercise_logs de {ontem}: {exc}")

    # Movimento do módulo Saúde: o pilar não é gerido por ações, então é aqui que
    # está a evidência de que ele anda. Pesagem é diária e é o sinal mais forte;
    # cintura e check-in entram porque numa semana sem pesagem eles ainda contam.
    candidatos = []
    if saude["peso"]:
        candidatos.append(saude["peso"]["data"])
    if saude["cintura_registrada"] or saude["checkin_manha"] or saude["checkin_noite"]:
        candidatos.append(hoje)
    if saude["dor_ontem"]:
        candidatos.append(ontem)
    try:
        for d in (db.collection("health_waist")
                  .where(filter=firestore.FieldFilter("date", ">=", _shift(hoje, -14)))
                  .where(filter=firestore.FieldFilter("date", "<=", hoje)).stream()):
            candidatos.append(_data_valida((d.to_dict() or {}).get("date")))
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar health_waist: {exc}")

    # A cintura tinha so a data usada como sinal de movimento; o valor em si era
    # descartado. Meta ligada a fonte `cintura` lia sempre None e caia no valor
    # manual antigo — a fonte automatica que o campo anuncia nunca chegava a valer.
    cintura = _ultima_medida(db, "health_waist", "cm", hoje, dias=60)
    if cintura:
        saude["cintura"] = cintura

    saude["ultimo_registro"] = max((c for c in candidatos if c), default=None)
    return saude


# Métrica cuja fonte o sistema já alimenta sozinho. A chave é gravada em
# `metricaAlvo.fonte`; o valor vem de `medicoes`, montado a partir do módulo Saúde.
_FONTES_AUTOMATICAS = {"peso", "cintura"}


def _fonte_da_metrica(data: dict, metrica: dict) -> str | None:
    """Qual fonte automática alimenta esta métrica, se alguma.

    `metricaAlvo.fonte` manda. Sem ela, deriva do que já existe na base — meta de
    saúde em kg é peso, em cm é cintura —, para os objetivos criados antes deste
    campo não precisarem de migração para voltarem a mostrar progresso real.
    """
    # Chave gravada, ainda que vazia, e resposta: significa "sem fonte", e
    # desligar a fonte de uma meta de saude em kg tem de continuar desligada. So
    # documento anterior ao campo cai na derivacao por unidade — depois que
    # `criar_objetivo_estrategico` passou a gravar `fonte`, toda meta absoluta
    # nova tem a chave, e sem esta distincao ela nasceria ligada sem ninguem pedir.
    if "fonte" in metrica:
        gravada = str(metrica.get("fonte") or "").strip().lower()
        return gravada if gravada in _FONTES_AUTOMATICAS else None
    if _pilar(data.get("pilar")) != "saude":
        return None
    unidade = str(metrica.get("unidade") or "").strip().lower()
    if unidade in ("kg", "quilo", "quilos"):
        return "peso"
    if unidade in ("cm", "centimetro", "centimetros"):
        return "cintura"
    return None


def _progresso_da_meta(data: dict, medicoes: dict) -> dict:
    """Progresso de uma meta numérica, dizendo DE ONDE saiu o número.

    O painel mostrava 0% para a meta de peso enquanto o usuário pesava todo dia:
    `metricaAlvo.valorAtual` guardava o valor de quando a meta foi criada e nunca
    era sincronizado com `health_weights`. Zero e "não sei" apareciam iguais, e um
    indicador que erra sobre o que o próprio sistema já sabe não sustenta nada
    construído em cima dele.

    Três origens, distintas de propósito:

    - `automatica`: a fonte está ligada e tem medição — o número é o real de hoje.
    - `manual`: não há fonte, mas o valor foi mexido desde a criação; vale o que
      o usuário anotou.
    - `sem_fonte`: métrica numérica que ninguém alimenta. Devolve progresso nulo,
      NUNCA zero: exibir 0% aqui afirma "não andou nada", que é diferente de
      "ninguém está medindo".
    """
    metrica = data.get("metricaAlvo") or {}
    if not metrica:
        return {"progresso_pct": None, "progresso_origem": None,
                "metrica_fonte": None, "valor_atual": None}

    try:
        ini = float(metrica.get("valorInicial") or 0)
        obj = float(metrica.get("valorObjetivo") or 0)
        registrado = float(metrica.get("valorAtual") or 0)
    except (TypeError, ValueError):
        return {"progresso_pct": None, "progresso_origem": "sem_fonte",
                "metrica_fonte": None, "valor_atual": None}

    fonte = _fonte_da_metrica(data, metrica)
    medido = medicoes.get(fonte) if fonte else None

    if medido is not None:
        atual, origem = float(medido), "automatica"
    elif metrica.get("valorAtual") is not None and registrado != ini:
        # Valor mexido desde a criação: alguém mantém isto na mão.
        atual, origem = registrado, "manual"
    elif data.get("historicoMetrica"):
        atual, origem = registrado, "manual"
    else:
        return {"progresso_pct": None, "progresso_origem": "sem_fonte",
                "metrica_fonte": fonte, "valor_atual": None}

    progresso = None
    if obj != ini:
        progresso = round(max(0.0, min(1.0, (atual - ini) / (obj - ini))) * 100)
    return {"progresso_pct": progresso, "progresso_origem": origem,
            "metrica_fonte": fonte, "valor_atual": atual}


def _coletar_estrategia(db, hoje: str, acoes_por_meta: dict, movimento_por_meta: dict,
                       movimento_saude: str | None = None,
                       medicoes: dict | None = None) -> dict:
    """
    Projeta o dia contra as metas: quantas ações de hoje servem cada uma, e há
    quantos dias cada meta não vê movimento.

    Nem toda meta é gerida por ações. `gerida_por_acoes: false` marca a meta
    servida por dado — hoje o pilar `saude`, executado pelos registros do módulo
    (pesagem, cintura, check-ins) — e cobrar dela uma ação vinculada é cobrar a
    coisa errada: produz a afirmação falsa "parada há N dias" num dia em que o
    usuário se pesou de manhã. Para essas metas o movimento vem de
    `movimento_saude`, e elas ficam fora da conta de "metas que recebem trabalho
    hoje".

    A flag é lida do objetivo, não deduzida do nome do pilar: um objetivo novo
    orientado a dado precisa nascer fora das funcionalidades de vínculo sem que
    ninguém edite uma lista de exceções. A derivação por pilar continua como
    valor padrão para os objetivos gravados antes do campo existir.
    """
    metas = []
    try:
        docs = list(db.collection("estrategia_pessoal").limit(80).stream())
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao consultar estrategia_pessoal: {exc}")
        docs = []

    for doc in docs:
        data = doc.to_dict() or {}
        if str(data.get("status") or "").lower() in ("concluido", "concluído", "cancelado", "arquivado"):
            continue

        # Movimento próprio da meta: registros de métrica, marcos e indicadores.
        movimentos = [movimento_por_meta.get(doc.id, "")]
        for h in data.get("historicoMetrica") or []:
            if isinstance(h, dict):
                movimentos.append(_data_valida(h.get("data")))
        for campo in ("marcos", "indicadoresSucesso"):
            for item in data.get(campo) or []:
                if not isinstance(item, dict):
                    continue
                movimentos.append(_data_valida(item.get("dataConclusao")))
                for reg in item.get("registros") or []:
                    if isinstance(reg, dict):
                        movimentos.append(_data_valida(reg.get("data")))

        pilar = str(data.get("pilar") or "")
        gravada = data.get("gerida_por_acoes")
        # Derivação por pilar só enquanto o objetivo não tem a flag gravada.
        gerida_por_acoes = bool(gravada) if gravada is not None else _pilar(pilar) != "saude"
        if not gerida_por_acoes and movimento_saude:
            movimentos.append(movimento_saude)

        ultimo = max((m for m in movimentos if m), default="")
        dias_parada = _dias_entre(ultimo, hoje) if ultimo else None

        marcos = [m for m in (data.get("marcos") or []) if isinstance(m, dict)]
        metrica = data.get("metricaAlvo") or {}
        progresso = _progresso_da_meta(data, medicoes or {})

        acoes = acoes_por_meta.get(doc.id) or []
        metas.append({
            "id": doc.id,
            "pilar": data.get("pilar"),
            "pilar_label": _PILAR_LABEL.get(pilar, data.get("pilar")),
            "gerida_por_acoes": gerida_por_acoes,
            "objetivo": data.get("objetivoMacro") or "(sem título)",
            "status": data.get("status"),
            "acoes_hoje": len(acoes),
            "titulos_hoje": [a["titulo"] for a in acoes][:AMOSTRA_FILA],
            "ultimo_movimento": ultimo or None,
            "dias_parada": dias_parada,
            "progresso_pct": progresso["progresso_pct"],
            # Diz de onde saiu o numero — ou que ninguem o alimenta.
            "progresso_origem": progresso["progresso_origem"],
            "metrica_fonte": progresso["metrica_fonte"],
            "valor_atual": progresso["valor_atual"],
            "unidade": metrica.get("unidade") or None,
            "marcos_abertos": len([m for m in marcos if not m.get("concluido")]),
            "marcos_total": len(marcos),
        })

    metas.sort(key=lambda m: (-m["acoes_hoje"], -(m["dias_parada"] if m["dias_parada"] is not None else 999)))

    def _esta_parada(m: dict) -> bool:
        atrasada = m["dias_parada"] is None or m["dias_parada"] >= META_PARADA_DIAS
        # Meta gerida por ações só conta como parada se também não tem ação hoje;
        # meta de saúde depende só do próprio módulo ter registro recente.
        return atrasada and (not m["gerida_por_acoes"] or m["acoes_hoje"] == 0)

    geridas_por_acoes = [m for m in metas if m["gerida_por_acoes"]]
    return {
        "metas": metas,
        "paradas": sorted([m for m in metas if _esta_parada(m)],
                          key=lambda m: -(m["dias_parada"] if m["dias_parada"] is not None else 999)),
        "servidas_hoje": len([m for m in geridas_por_acoes if m["acoes_hoje"] > 0]),
        # Denominador honesto do "X de N metas recebem trabalho hoje": só as que
        # são de fato executadas por ações.
        "total_geridas_por_acoes": len(geridas_por_acoes),
    }


def _coletar_ontem(db, ontem: str) -> dict:
    """A ponte com o diário: o que ficou registrado ontem e o que de fato foi fechado."""
    concluidas = []
    for doc in _query_por_prefixo_de_data(db, "tarefas", "data_conclusao", ontem):
        concluidas.append(str((doc.to_dict() or {}).get("titulo") or "(sem título)"))

    diario = None
    try:
        snap = db.collection("diario_pessoal").document(ontem).get()
        if snap.exists:
            data = snap.to_dict() or {}
            texto = str(data.get("texto") or "").strip()
            if texto:
                diario = {
                    "data": ontem,
                    "texto": texto,
                    "editado": bool(data.get("editado")),
                }
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao ler diário de {ontem}: {exc}")

    return {"concluidas": concluidas, "diario": diario}


def _coletar_perfil(db) -> dict | None:
    """`ai_profile.personalidade` — o "estado atual" que `consolidar_personalidade`
    já destila dos diários todo domingo. Aqui só é lido, nunca recalculado."""
    try:
        from personal_diary import _resolve_default_uid
        uid = _resolve_default_uid(db)
        if not uid:
            return None
        snap = db.collection("usuarios").document(uid).get()
        if not snap.exists:
            return None
        perfil = ((snap.to_dict() or {}).get("ai_profile") or {}).get("personalidade")
        if not isinstance(perfil, dict) or not perfil:
            return None
        return {
            "resumo": perfil.get("resumo_narrativo"),
            "rotinas": perfil.get("rotinas") or [],
            "gatilhos": perfil.get("gatilhos_de_estresse") or [],
            "energia": perfil.get("fontes_de_energia") or [],
        }
    except Exception as exc:
        print(f"[ResumoMatinal] Falha ao ler perfil de personalidade: {exc}")
        return None


# --------------------------------------------------------------------------- #
# Regra de foco                                                                #
# --------------------------------------------------------------------------- #

def _escolher_foco(acoes: dict, estrategia: dict, hoje: str) -> list:
    """
    Escolhe até `MAX_FOCO` ações do dia por regra explícita, em ordem de precedência.
    Isto é deliberadamente código, não modelo: a mesma lição de
    `health_weekly_report.py` — quem escolhe precisa ser auditável e estável entre
    execuções. Uma camada de narrativa pode depois justificar a escolha em prosa,
    mas não pode mudá-la.
    """
    candidatas = [t for lane in acoes["por_lane"].values() for t in lane]
    if not candidatas:
        return []

    metas_paradas = {m["id"]: m for m in estrategia["paradas"]}
    escolhidas: list = []
    vistos: set = set()

    def _incluir(tarefa: dict, regra: str, motivo: str) -> None:
        if len(escolhidas) >= MAX_FOCO or tarefa["id"] in vistos:
            return
        vistos.add(tarefa["id"])
        escolhidas.append({
            "task_id": tarefa["id"],
            "titulo": tarefa["titulo"],
            "regra": regra,
            "motivo": motivo,
            "proximo_passo": tarefa["proximo_passo"],
            "subtarefa_do_dia": tarefa.get("subtarefa_do_dia"),
            "horario_inicio": tarefa["horario_inicio"],
        })

    # 1. Prazo duro chegando — é o único prazo que o reset da meia-noite não move.
    for t in sorted((c for c in candidatas if c["prazo_final"]), key=lambda c: c["prazo_final"]):
        dias = _dias_entre(hoje, t["prazo_final"])
        if dias <= PRAZO_IMINENTE_DIAS:
            quando = "vence hoje" if dias == 0 else ("venceu" if dias < 0 else f"vence em {dias} dia(s)")
            _incluir(t, "prazo_final_iminente", f"Prazo final {quando} ({t['prazo_final']}).")

    # 2. Degradação crítica — já foi adiada 3+ vezes pelo reset automático.
    # Nomear a etapa é o ponto: "adiada 33x" diz que algo está parado, não o quê.
    # Quando a etapa tem contador próprio, é dela que o número fala.
    for t in sorted((c for c in candidatas if c["degradation_count"] >= DEGRADACAO_CRITICA),
                    key=lambda c: -c["degradation_count"]):
        etapa = t.get("subtarefa_do_dia") or {}
        if etapa.get("texto") and etapa.get("degradation_count"):
            motivo = (f"A etapa \"{etapa['texto'][:70]}\" foi adiada "
                      f"{etapa['degradation_count']}x — é ela que está segurando a ação.")
        else:
            motivo = f"Adiada automaticamente {t['degradation_count']}x — não sobrevive a mais um dia."
        _incluir(t, "degradacao_critica", motivo)

    # 3. SLA de espera estourado: virou cobrança e ninguém cobrou.
    for t in (c for c in candidatas if c["cobrar"]):
        _incluir(t, "sla_estourado", "Estourou o SLA de espera e virou cobrança.")

    # 4. A meta parada há mais tempo que tenha alguma ação disponível hoje.
    for t in sorted((c for c in candidatas if c["estrategia_objetivo_id"] in metas_paradas),
                    key=lambda c: -(metas_paradas[c["estrategia_objetivo_id"]]["dias_parada"] or 999)):
        meta = metas_paradas[t["estrategia_objetivo_id"]]
        dias = meta["dias_parada"]
        quanto = f"parada há {dias} dias" if dias is not None else "que nunca registrou movimento"
        _incluir(t, "meta_parada", f"Move a meta \"{meta['objetivo']}\", {quanto}.")

    # 5. Compromisso com hora marcada — o dia já reservou espaço para isto.
    for t in (c for c in candidatas if c["horario_inicio"]):
        _incluir(t, "agendada", f"Tem horário marcado ({t['horario_inicio']}).")

    # 6. Preenchimento: fila de avanço, na ordem em que a view já mostra.
    for t in acoes["por_lane"].get("avanco", []):
        _incluir(t, "fila_avanco", "Próxima da fila de avanço.")

    return escolhidas


# --------------------------------------------------------------------------- #
# Montagem                                                                     #
# --------------------------------------------------------------------------- #

def build_morning_summary(db, date_str: str | None = None) -> dict:
    """Monta o resumo matinal completo. Determinístico, sem IA, sem escrita."""
    hoje = date_str or _hoje_sp()
    ontem = _shift(hoje, -1)

    acoes = _coletar_acoes(db, hoje)
    agenda = _coletar_agenda(db, hoje)
    filas = _coletar_filas(db, hoje)
    avisos_do_sistema = _coletar_avisos_do_sistema(db)
    passivo_elevacao = _coletar_passivo_de_elevacao(db)
    saude = _coletar_saude(db, hoje, ontem)
    # Depende de `saude`: o pilar saúde não é gerido por ações, seu movimento vem
    # dos registros do módulo Saúde.
    # O modulo Saude ja mediu hoje; a meta de peso passa a ler DESSE numero em vez
    # do `valorAtual` congelado na criacao do objetivo.
    medicoes = {
        "peso": (saude.get("peso") or {}).get("ultimo"),
        "cintura": (saude.get("cintura") or {}).get("ultimo"),
    }
    estrategia = _coletar_estrategia(db, hoje, acoes["acoes_por_meta"],
                                     acoes["movimento_por_meta"], saude["ultimo_registro"],
                                     medicoes={k: v for k, v in medicoes.items() if v})
    ontem_data = _coletar_ontem(db, ontem)
    perfil = _coletar_perfil(db)
    foco = _escolher_foco(acoes, estrategia, hoje)
    # Índice materializado pelo mesmo ciclo que recebe mensagens de WhatsApp.
    # A leitura é pequena e não faz RPC ao WhatsApp/Gmail durante a abertura de
    # uma sessão MCP.
    from inbox_pendentes import coletar as coletar_respostas_pendentes
    respostas_pendentes = coletar_respostas_pendentes(db)

    dia_semana = _DIAS_SEMANA[datetime.strptime(hoje, "%Y-%m-%d").weekday()]
    pendencias = sum(f.get("total", 0) for f in filas.values() if isinstance(f, dict))

    return {
        "data": hoje,
        "dia_semana": dia_semana,
        "versao": VERSAO,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "foco": foco,
        "hoje": {
            "avanco": acoes["por_lane"].get("avanco", []),
            "continuo": acoes["por_lane"].get("continuo", []),
            "aguardando_terceiro": acoes["por_lane"].get("aguardando_terceiro", []),
            "atrasadas": acoes["atrasadas"],
        },
        "agenda": agenda["eventos"],
        "janelas_livres": agenda["janelas_livres"],
        "prazos_duros": acoes["prazos_duros"],
        "carga_semana": acoes["carga_semana"],
        "filas": filas,
        # Fora de `filas` de proposito: aviso do sistema nao e decisao pendente e
        # nao pode entrar na contagem de `pendencias`.
        "avisos_do_sistema": avisos_do_sistema,
        # Fora de `filas` e fora de `avisos`: não espera decisão e não é defeito.
        "passivo_elevacao": passivo_elevacao,
        "saude": saude,
        "estrategia": estrategia,
        "ontem": ontem_data,
        "perfil": perfil,
        "respostas_pendentes": respostas_pendentes,
        "contadores": {**acoes["contadores"], "pendencias": pendencias, "focos": len(foco)},
    }


def _persistir(db, resumo: dict) -> None:
    """
    Grava o resumo preservando os campos que a UI e a noite escrevem (`visto_em`,
    e no futuro `aderencia`), mas SUBSTITUINDO por inteiro tudo que o coletor
    produz.

    Não use `merge=True` aqui: ele é um merge recursivo, então uma chave que o
    coletor parou de emitir sobrevive no documento para sempre. Foi exatamente o
    que aconteceu quando `consolidacoes_whatsapp` saiu de `_coletar_filas` — o
    campo continuou no doc, e a tela seguiu mostrando a fila removida. Mesmo
    erro já corrigido em `scripts/seed_dados_cadastrais.py` (ver docs/okf/log.md,
    2026-08-19).

    `merge=[<campos>]` substitui cada campo listado por completo e deixa os
    demais intactos — que é o que se quer aqui.
    """
    db.collection("resumo_matinal").document(resumo["data"]).set(resumo, merge=list(resumo.keys()))


# --------------------------------------------------------------------------- #
# Entradas                                                                     #
# --------------------------------------------------------------------------- #

@scheduler_fn.on_schedule(
    schedule="30 4 * * *",  # depois do reset da meia-noite (daily_reset_job.py), antes de acordar
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=180,
)
def gerar_resumo_matinal(event: scheduler_fn.ScheduledEvent = None) -> None:
    """Agendada 04:30 BRT. Precisa rodar DEPOIS de `daily_wip_reset_and_degradation`
    (00:00), que é quem produz a herança do dia — rodar antes mostraria o dia de
    ontem."""
    from main import get_db, _cached_doc_get

    db = get_db()
    cfg = _cached_doc_get(db, "system", "settings")
    settings = ((cfg.to_dict() or {}) if cfg.exists else {}).get("resumo_matinal") or {}
    if not settings.get("enabled", True):
        print("[ResumoMatinal] Desativado em system/settings.resumo_matinal.enabled.")
        return

    resumo = build_morning_summary(db)
    _persistir(db, resumo)
    c = resumo["contadores"]
    print(
        f"[ResumoMatinal] {resumo['data']} gerado — {c['hoje']} ação(ões) hoje, "
        f"{c['herdadas']} herdada(s), {c['criticas']} crítica(s), {c['pendencias']} pendência(s)."
    )


@https_fn.on_call(memory=options.MemoryOption.MB_512, timeout_sec=120)
def gerarResumoMatinal(req: https_fn.CallableRequest):
    """
    Regeneração sob demanda a partir da web (`MorningSummaryView.tsx`): ocorre
    automaticamente a cada acesso ao Resumo do Dia e também serve de fallback
    quando o agendador ainda não rodou (primeiro dia ou virada do dia).
    """
    from main import get_db

    if not (req.auth and req.auth.uid):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Usuário não autenticado.",
        )

    data = req.data or {}
    date_str = str(data.get("date") or "").strip() or None
    if date_str:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Campo 'date' deve estar no formato YYYY-MM-DD.",
            )

    db = get_db()
    resumo = build_morning_summary(db, date_str)
    _persistir(db, resumo)
    return resumo
