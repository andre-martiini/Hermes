import datetime
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from firebase_admin import firestore
from firebase_functions import scheduler_fn, options


def _last_day_of_month(ref: datetime.datetime) -> int:
    next_month = ref.replace(day=1) + datetime.timedelta(days=32)
    return (next_month.replace(day=1) - datetime.timedelta(days=1)).day


def _indice_semana(d: datetime.date) -> int:
    # Índice absoluto de semanas com início no domingo (alinhado à convenção 0=domingo)
    return (d.toordinal() - 7) // 7


def _deve_gerar_hoje(recorrencia: dict, now_sp: datetime.datetime) -> tuple[bool, str | None]:
    """
    Decide se o template deve gerar uma instância hoje.
    Retorna (deve_gerar, marcador_de_geracao). O marcador é gravado em
    recorrencia.ultima_geracao para evitar duplicidade: "YYYY-MM" na
    recorrência mensal e "YYYY-MM-DD" na semanal.
    Convenção de dias da semana: 0=domingo ... 6=sábado (mesma do JS getDay()).
    Templates sem o campo 'frequencia' são tratados como mensais (retrocompatibilidade).
    Semanal aceita múltiplos dias (dias_da_semana) e intervalo_semanas (ex.: 2 =
    a cada duas semanas), ancorado na semana da última geração.
    """
    frequencia = recorrencia.get("frequencia")
    if not frequencia:
        frequencia = "semanal" if (
            recorrencia.get("dia_da_semana") is not None or recorrencia.get("dias_da_semana")
        ) else "mensal"

    if frequencia == "semanal":
        dias = recorrencia.get("dias_da_semana")
        if not dias:
            dia_unico = recorrencia.get("dia_da_semana")
            if dia_unico is None:
                return False, None
            dias = [dia_unico]
        hoje_dow = (now_sp.weekday() + 1) % 7  # weekday(): 0=segunda -> converte para 0=domingo
        if hoje_dow not in {int(d) for d in dias}:
            return False, None
        marcador = now_sp.strftime("%Y-%m-%d")
        ultima = recorrencia.get("ultima_geracao")
        if ultima == marcador:
            return False, None
        intervalo = max(1, int(recorrencia.get("intervalo_semanas") or 1))
        if intervalo > 1 and ultima:
            # Como só geramos em semanas alinhadas, a semana da última geração
            # serve de âncora para o intervalo.
            try:
                semana_ultima = _indice_semana(datetime.date.fromisoformat(ultima))
                if (_indice_semana(now_sp.date()) - semana_ultima) % intervalo != 0:
                    return False, None
            except ValueError:
                pass  # ultima_geracao em formato inesperado (ex.: mensal): ignora a âncora
        return True, marcador

    dia_do_mes = recorrencia.get("dia_do_mes")
    if not dia_do_mes:
        return False, None
    # Dias que não existem no mês corrente (ex.: 31 em abril) caem no último dia do mês
    effective_day = min(int(dia_do_mes), _last_day_of_month(now_sp))
    if now_sp.day != effective_day:
        return False, None
    marcador = now_sp.strftime("%Y-%m")
    if recorrencia.get("ultima_geracao") == marcador:
        return False, None
    return True, marcador


@scheduler_fn.on_schedule(
    schedule="10 0 * * *",  # Todo dia à 00:10
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
def gerar_acoes_recorrentes_mensais(event: scheduler_fn.ScheduledEvent):
    # Apesar do nome (mantido para não recriar a função agendada no deploy),
    # este job processa recorrências semanais E mensais.
    from main import get_db
    db = get_db()
    sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
    now_sp = datetime.datetime.now(sp_tz)
    today_str = now_sp.strftime("%Y-%m-%d")

    templates = db.collection("tarefas").where(
        filter=firestore.FieldFilter("recorrencia.ativo", "==", True)
    ).get()

    created_count = 0
    for template_doc in templates:
        template_data = template_doc.to_dict()
        recorrencia = template_data.get("recorrencia") or {}
        deve_gerar, marcador = _deve_gerar_hoje(recorrencia, now_sp)
        if not deve_gerar:
            continue

        new_task = {
            "titulo": template_data.get("titulo", ""),
            "projeto": template_data.get("projeto", ""),
            "area_tematica": template_data.get("area_tematica", ""),
            "data_inicio": today_str,
            "data_limite": today_str,
            "status": "em andamento",
            "contabilizar_meta": template_data.get("contabilizar_meta", False),
            "data_criacao": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "acompanhamento": [],
            "entregas_relacionadas": [],
            "origem": template_data.get("origem", "manual"),
        }
        for optional_field in ("tags", "descricao", "tipo_acao", "horario_inicio", "horario_fim"):
            if template_data.get(optional_field):
                new_task[optional_field] = template_data[optional_field]

        db.collection("tarefas").add(new_task)
        template_doc.reference.update({"recorrencia.ultima_geracao": marcador})
        created_count += 1
        print(f"[Recorrência] Gerada nova instância de '{new_task['titulo']}' a partir do template {template_doc.id}.")

    if created_count == 0:
        print(f"[Recorrência] Nenhuma ação recorrente para gerar em {today_str}.")
