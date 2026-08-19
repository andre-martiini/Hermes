"""
Resumo de saúde (peso, caminhada, calorias, sono, dor) compartilhado entre o
Copiloto padrão (main.py, tool `consultar_saude`) e o Godmode (godmode.py) —
mesmo padrão de extração já usado para finanças (`tools/telegram_extended.py`)
e estratégia (`strategy_tools.py`).
"""
from datetime import date, timedelta


def build_health_summary(db, ultimos_dias: int = 7, data_especifica: str | None = None) -> dict:
    if data_especifica:
        start_date = data_especifica
        end_date = data_especifica
    else:
        n = min(int(ultimos_dias or 7), 30)
        today = date.today()
        start_date = (today - timedelta(days=n - 1)).isoformat()
        end_date = today.isoformat()

    # Metas de caminhada do nivelamento atual (mínimo/ideal em km), com os
    # mesmos padrões da UI (3 km / 8 km).
    try:
        walk_settings = db.collection('health_settings').document('config').get().to_dict() or {}
    except Exception:
        walk_settings = {}
    walking_minimum_km = float(walk_settings.get('walkingMinimumKm') or 3)
    walking_ideal_km = float(walk_settings.get('walkingIdealKm') or 8)

    logs = []
    for d in db.collection('health_exercise_logs').stream():
        if start_date <= d.id <= end_date:
            entry = d.to_dict() or {}
            # Paradigma atual: blocos de caminhada registrados no Hermes
            # (web/Telegram). O campo `walk` é legado (Google Fit).
            walk_blocks = [b for b in (entry.get("walkBlocks") or []) if isinstance(b, dict)]
            walk_km = sum(float(b.get("distance") or 0) for b in walk_blocks)
            if walk_km >= walking_ideal_km:
                walk_level = "meta_ideal_atingida"
            elif walk_km >= walking_minimum_km:
                walk_level = "minimo_atingido"
            else:
                walk_level = "abaixo_do_minimo"
            logs.append({
                "data": d.id,
                "caminhada_km": round(walk_km, 2),
                "caminhada_blocos": walk_blocks,
                "caminhada_nivel": walk_level,
                "walk_legado_google_fit": entry.get("walk"),
                "calories": entry.get("calories"),
                "activeMinutes": entry.get("activeMinutes"),
                "heartRate": entry.get("heartRate"),
                "sleep": entry.get("sleep"),
                "pain": entry.get("pain"),
            })
    logs.sort(key=lambda x: x['data'], reverse=True)

    weight_start = (date.today() - timedelta(days=30)).isoformat()
    weights = []
    for d in db.collection('health_weights').stream():
        w = d.to_dict() or {}
        if w.get('date', '') >= weight_start:
            weights.append(w)
    weights.sort(key=lambda x: x.get('date', ''), reverse=True)

    return {
        "periodo": {"inicio": start_date, "fim": end_date},
        "metas_caminhada": {
            "minimo_km": walking_minimum_km,
            "ideal_km": walking_ideal_km,
            "paradigma": (
                "Abaixo do mínimo não pontua; do mínimo ao ideal o nível "
                "progride continuamente; acima do ideal é lucro."
            ),
        },
        "telemetria_diaria": logs,
        "pesos_recentes": weights[:5],
    }
