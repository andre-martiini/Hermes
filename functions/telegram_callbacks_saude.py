"""Callbacks do Telegram - check-ins de saude

Extraido de hermes_core_logic.py::_handle_telegram_callback (P02, modularizacao
por area -- hermes_core_logic.py e telegram_utils.py cresceram alem do teto de
~64000 tokens de saida por chamada de escrita do Argos; ver decisao do Andre em
2026-09-08). Split puramente mecanico: nenhuma linha de logica foi reescrita, so
movida e envolvida por `def handle(...) -> bool`. Cada `return
https_fn.Response("OK", status=200)` virou `return True` (o chamador, em
telegram_handlers_core.py, sempre monta essa mesma resposta no fim -- o valor de
retorno aqui so diz se este modulo tratou o callback, para o dispatcher decidir
se tenta o proximo).

ATENCAO para mock.patch/mock.patch.object em testes: as funcoes deste arquivo
resolvem nomes livres (`_send_telegram_message`, `_answer_callback_query`,
etc.) pelo namespace DESTE modulo, nao pelo de hermes_core_logic nem de
telegram_handlers_core -- mesmo padrao documentado em telegram_utils.py. Um
`mock.patch.object(hermes_core_logic, "_send_telegram_message", ...)` nao
intercepta uma chamada feita de dentro de uma funcao deste arquivo.
"""
import re
from datetime import datetime, timedelta, timezone

from telegram_utils import (
    _HEALTH_RADICULAR_LOCATIONS,
    _HEALTH_THERAPY_MODALITIES,
    _HEALTH_TRIGGER_TYPES,
    _answer_callback_query,
    _health_entry_source_after_telegram,
    _send_telegram_message,
    _send_telegram_message_with_keyboard,
)

def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn, _pending_web_card, _clear_pending_web_card) -> bool:
    """Trata os callback_query de check-in de saude (health_*). Retorna True se tratou."""
    if data.startswith("health_checkin:"):
        parts = data.split(":")
        checkin_date = parts[1] if len(parts) > 1 else ""
        checkin_mode = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", checkin_date):
                raise ValueError("data inválida")
            _answer_callback_query(token, query_id, "Check-in iniciado")
            if checkin_mode == "morning":
                response_text = (
                    "☀️ <b>Check-in da manhã</b>\n\n"
                    "Que nota você dá para a dor nos primeiros minutos depois de levantar da cama, "
                    "antes da caminhada? (0 = sem dor, 10 = pior possível)"
                )
                pain_keyboard = [
                    [{"text": str(n), "callback_data": f"health_mpain:{checkin_date}:{n}"} for n in range(0, 6)],
                    [{"text": str(n), "callback_data": f"health_mpain:{checkin_date}:{n}"} for n in range(6, 11)],
                ]
            else:
                response_text = "🌙 <b>Check-in da noite</b>\n\nComo ficou sua lombar hoje? (0 = sem dor, 10 = pior possível)"
                pain_keyboard = [
                    [{"text": str(n), "callback_data": f"health_pain:{checkin_date}:{n}"} for n in range(0, 6)],
                    [{"text": str(n), "callback_data": f"health_pain:{checkin_date}:{n}"} for n in range(6, 11)],
                ]
            _persist_callback_turn(f"Iniciar check-in ({'manhã' if checkin_mode == 'morning' else 'noite'})", response_text)
            _send_telegram_message_with_keyboard(token, chat_id, response_text, pain_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao iniciar check-in guiado: {exc}")
            _answer_callback_query(token, query_id, "Não consegui iniciar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui iniciar o check-in. Toque no botão novamente.")

    elif data.startswith("health_mpain:"):
        parts = data.split(":")
        mpain_date = parts[1] if len(parts) > 1 else ""
        mpain_raw = parts[2] if len(parts) > 2 else ""
        try:
            mpain_score = max(0, min(10, int(mpain_raw)))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", mpain_date):
                raise ValueError("data inválida")
            doc_ref = db.collection("health_exercise_logs").document(mpain_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_pain = current_data.get("pain") or {}
            current_pain["morning"] = mpain_score
            current_pain["telegram_checked_at"] = datetime.now(timezone.utc).isoformat()
            doc_ref.set({"pain": current_pain, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Dor ao acordar: {mpain_score}/10")
            response_text = "✅ Dor ao acordar registrada: <b>" + f"{mpain_score}/10</b>. E depois da caminhada, como ficou?"
            _persist_callback_turn(f"Check-in manhã — dor ao acordar: {mpain_score}/10", response_text)
            afterwalk_keyboard = [
                [{"text": str(n), "callback_data": f"health_mafterwalk:{mpain_date}:{n}"} for n in range(0, 6)],
                [{"text": str(n), "callback_data": f"health_mafterwalk:{mpain_date}:{n}"} for n in range(6, 11)],
            ]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, afterwalk_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar dor da manhã: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a dor da manhã. Tente responder novamente.")

    elif data.startswith("health_mafterwalk:"):
        parts = data.split(":")
        afterwalk_date = parts[1] if len(parts) > 1 else ""
        afterwalk_raw = parts[2] if len(parts) > 2 else ""
        try:
            afterwalk_score = max(0, min(10, int(afterwalk_raw)))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", afterwalk_date):
                raise ValueError("data inválida")
            doc_ref = db.collection("health_exercise_logs").document(afterwalk_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_pain = current_data.get("pain") or {}
            current_pain["afterWalk"] = afterwalk_score
            doc_ref.set({"pain": current_pain, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Dor após a caminhada: {afterwalk_score}/10")
            response_text = f"✅ Dor após a caminhada registrada: <b>{afterwalk_score}/10</b>. Você acordou com dor durante a noite?"
            _persist_callback_turn(f"Check-in manhã — dor após a caminhada: {afterwalk_score}/10", response_text)
            woke_keyboard = [[
                {"text": "Sim", "callback_data": f"health_woke:{afterwalk_date}:sim"},
                {"text": "Não", "callback_data": f"health_woke:{afterwalk_date}:nao"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, woke_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar dor após a caminhada: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar essa resposta. Tente novamente.")

    elif data.startswith("health_woke:"):
        parts = data.split(":")
        woke_date = parts[1] if len(parts) > 1 else ""
        woke_raw = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", woke_date):
                raise ValueError("data inválida")
            woke_in_pain = woke_raw == "sim"
            doc_ref = db.collection("health_exercise_logs").document(woke_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            sleep_quality = current_data.get("sleepQuality") or {}
            sleep_quality["wokeInPain"] = woke_in_pain
            doc_ref.set({"sleepQuality": sleep_quality, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, "Registrado")
            response_text = f"✅ Acordou com dor: <b>{'sim' if woke_in_pain else 'não'}</b>. Como foi a qualidade do sono? (1 = péssima, 5 = ótima)"
            _persist_callback_turn(f"Check-in manhã — acordou com dor: {'sim' if woke_in_pain else 'não'}", response_text)
            quality_keyboard = [[{"text": str(n), "callback_data": f"health_sleepq:{woke_date}:{n}"} for n in range(1, 6)]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, quality_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar despertar com dor: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar essa resposta. Tente novamente.")

    elif data.startswith("health_sleepq:"):
        parts = data.split(":")
        sleepq_date = parts[1] if len(parts) > 1 else ""
        sleepq_raw = parts[2] if len(parts) > 2 else ""
        try:
            sleepq_score = max(1, min(5, int(sleepq_raw)))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", sleepq_date):
                raise ValueError("data inválida")
            doc_ref = db.collection("health_exercise_logs").document(sleepq_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            sleep_quality = current_data.get("sleepQuality") or {}
            sleep_quality["quality"] = sleepq_score
            if "wokeInPain" not in sleep_quality:
                sleep_quality["wokeInPain"] = False
            doc_ref.set({"sleepQuality": sleep_quality, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Sono: {sleepq_score}/5")
            response_text = f"✅ Qualidade do sono: <b>{sleepq_score}/5</b>.\n\n☀️ Check-in da manhã completo! O da noite chega às 19h."
            _persist_callback_turn(f"Check-in manhã — sono: {sleepq_score}/5", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar qualidade do sono: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a qualidade do sono. Tente novamente.")

    elif data.startswith("health_pain:"):
        parts = data.split(":")
        pain_date = parts[1] if len(parts) > 1 else ""
        pain_raw = parts[2] if len(parts) > 2 else ""
        try:
            pain_score = max(0, min(10, int(pain_raw)))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", pain_date):
                raise ValueError("data inválida")
            doc_ref = db.collection("health_exercise_logs").document(pain_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_pain = current_data.get("pain") or {}
            current_pain["evening"] = pain_score
            current_pain["telegram_checked_at"] = datetime.now(timezone.utc).isoformat()
            doc_ref.set({"pain": current_pain, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Dor registrada: {pain_score}/10")
            response_text = f"✅ Dor registrada: <b>{pain_score}/10</b> em {pain_date}. Onde você sente o sintoma na perna?"
            _persist_callback_turn(f"Check-in lombar: {pain_score}/10", response_text)
            radicular_keyboard = [
                [{"text": label, "callback_data": f"health_radic:{pain_date}:{value}"}]
                for value, label in _HEALTH_RADICULAR_LOCATIONS
            ]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, radicular_keyboard)
            # O alerta de sinal vermelho (dor >= 9) e disparado pelo trigger
            # on_health_log_red_flag ao ver a escrita acima, nao aqui.
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar dor: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar esse check-in lombar. Tente responder novamente.")

    elif data.startswith("health_radic:"):
        parts = data.split(":")
        radic_date = parts[1] if len(parts) > 1 else ""
        radic_location = parts[2] if len(parts) > 2 else ""
        valid_locations = {value for value, _ in _HEALTH_RADICULAR_LOCATIONS}
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", radic_date) or radic_location not in valid_locations:
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(radic_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_radicular = current_data.get("radicular") or {}
            current_radicular["location"] = radic_location
            doc_ref.set({"radicular": current_radicular, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            location_label = dict(_HEALTH_RADICULAR_LOCATIONS).get(radic_location, radic_location)
            _answer_callback_query(token, query_id, f"Sintoma: {location_label}")
            response_text = f"✅ Sintoma na perna: <b>{location_label}</b>. Treino de força hoje?"
            _persist_callback_turn(f"Sintoma radicular: {location_label}", response_text)
            strength_keyboard = [[
                {"text": "Sim", "callback_data": f"health_strength:{radic_date}:sim"},
                {"text": "Não", "callback_data": f"health_strength:{radic_date}:nao"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, strength_keyboard)
            # O alerta de sinal vermelho (local == "pe") e disparado pelo trigger
            # on_health_log_red_flag ao ver a escrita acima, nao aqui.
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar sintoma radicular: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar o sintoma. Tente novamente.")

    elif data.startswith("health_strength:"):
        parts = data.split(":")
        strength_date = parts[1] if len(parts) > 1 else ""
        strength_raw = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", strength_date) or strength_raw not in ("sim", "nao"):
                raise ValueError("dados inválidos")
            done = strength_raw == "sim"
            doc_ref = db.collection("health_exercise_logs").document(strength_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_strength = current_data.get("strength") or {}
            current_strength["done"] = done
            doc_ref.set({"strength": current_strength, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, "Treino registrado" if done else "Ok, sem treino hoje")
            response_text = f"✅ Treino de força: <b>{'sim' if done else 'não'}</b>. Fez alguma terapia hoje?"
            _persist_callback_turn(f"Treino de força: {'sim' if done else 'não'}", response_text)
            therapy_keyboard = [
                [{"text": label, "callback_data": f"health_therapy:{strength_date}:{value}"}]
                for value, label in _HEALTH_THERAPY_MODALITIES
            ]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, therapy_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar treino: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar o treino. Tente novamente.")

    elif data.startswith("health_therapy:"):
        parts = data.split(":")
        therapy_date = parts[1] if len(parts) > 1 else ""
        therapy_value = parts[2] if len(parts) > 2 else ""
        valid_therapies = {value for value, _ in _HEALTH_THERAPY_MODALITIES}
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", therapy_date) or therapy_value not in valid_therapies:
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(therapy_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            therapy_list = [] if therapy_value == "nenhuma" else [therapy_value]
            doc_ref.set({"therapy": therapy_list, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            therapy_label = dict(_HEALTH_THERAPY_MODALITIES).get(therapy_value, therapy_value)
            _answer_callback_query(token, query_id, f"Terapia: {therapy_label}")
            response_text = f"✅ Terapia: <b>{therapy_label}</b>. Como foi a alimentação hoje?"
            _persist_callback_turn(f"Modalidade terapêutica: {therapy_label}", response_text)
            diet_keyboard = [[
                {"text": "Sim", "callback_data": f"health_diet:{therapy_date}:sim"},
                {"text": "Parcial", "callback_data": f"health_diet:{therapy_date}:parcial"},
                {"text": "Não", "callback_data": f"health_diet:{therapy_date}:nao"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, diet_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar terapia: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a terapia. Tente novamente.")

    elif data.startswith("health_diet:"):
        parts = data.split(":")
        diet_date = parts[1] if len(parts) > 1 else ""
        diet_value = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", diet_date) or diet_value not in ("sim", "parcial", "nao"):
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(diet_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_nutrition = current_data.get("nutrition") or {}
            current_nutrition["plan"] = diet_value
            doc_ref.set({"nutrition": current_nutrition, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Cardápio: {diet_value}")
            response_text = "✅ Alimentação registrada. Bateu a proteína hoje?"
            _persist_callback_turn(f"Aderência alimentar: {diet_value}", response_text)
            protein_keyboard = [[
                {"text": "Sim", "callback_data": f"health_protein:{diet_date}:sim"},
                {"text": "Não", "callback_data": f"health_protein:{diet_date}:nao"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, protein_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar alimentação: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a alimentação. Tente novamente.")

    elif data.startswith("health_protein:"):
        parts = data.split(":")
        protein_date = parts[1] if len(parts) > 1 else ""
        protein_value = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", protein_date) or protein_value not in ("sim", "nao"):
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(protein_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_nutrition = current_data.get("nutrition") or {}
            current_nutrition["proteinTarget"] = protein_value == "sim"
            doc_ref.set({"nutrition": current_nutrition, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, "Registrado")
            response_text = "✅ Proteína registrada. Medicação de hoje foi igual a de ontem?"
            _persist_callback_turn(f"Proteína batida: {protein_value}", response_text)
            meds_keyboard = [[
                {"text": "Igual a ontem", "callback_data": f"health_meds:{protein_date}:same"},
                {"text": "Nada hoje", "callback_data": f"health_meds:{protein_date}:clear"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, meds_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar proteína: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a proteína. Tente novamente.")

    elif data.startswith("health_meds:"):
        parts = data.split(":")
        meds_date = parts[1] if len(parts) > 1 else ""
        meds_action = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", meds_date) or meds_action not in ("same", "clear"):
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(meds_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            if meds_action == "same":
                yesterday = (datetime.strptime(meds_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
                yesterday_doc = db.collection("health_exercise_logs").document(yesterday).get()
                yesterday_meds = (yesterday_doc.to_dict() or {}).get("meds") if yesterday_doc.exists else None
                new_meds = yesterday_meds or {"pregabalina": False, "dipirona": 0, "adorlan": 0, "fexofenadina": False}
                meds_summary = "igual a ontem"
            else:
                new_meds = {"pregabalina": False, "dipirona": 0, "adorlan": 0, "fexofenadina": False}
                meds_summary = "nada hoje"
            doc_ref.set({"meds": new_meds, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, "Medicação registrada")
            response_text = f"✅ Medicação: <b>{meds_summary}</b>. Algum evento ou gatilho hoje?"
            _persist_callback_turn(f"Medicação: {meds_summary}", response_text)
            trigger_keyboard = [
                [{"text": label, "callback_data": f"health_trigger:{meds_date}:{value}"}]
                for value, label in _HEALTH_TRIGGER_TYPES
            ]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, trigger_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar medicação: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a medicação. Tente novamente. Edite pelo painel se preferir.")

    elif data.startswith("health_trigger:"):
        parts = data.split(":")
        trigger_date = parts[1] if len(parts) > 1 else ""
        trigger_value = parts[2] if len(parts) > 2 else ""
        valid_triggers = {value for value, _ in _HEALTH_TRIGGER_TYPES}
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", trigger_date) or trigger_value not in valid_triggers:
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(trigger_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            trigger_types = [] if trigger_value == "nenhum" else [trigger_value]
            current_triggers = current_data.get("triggers") or {}
            current_triggers["types"] = trigger_types
            doc_ref.set({"triggers": current_triggers, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            trigger_label = dict(_HEALTH_TRIGGER_TYPES).get(trigger_value, trigger_value)
            _answer_callback_query(token, query_id, "Registrado")
            response_text = f"✅ Check-in lombar completo para {trigger_date}. Gatilho: <b>{trigger_label}</b>.\n\nPara adicionar uma observação, use o painel."
            _persist_callback_turn(f"Evento/gatilho: {trigger_label}", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar gatilho: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar o gatilho. Tente novamente.")

    else:
        return False
    return True
