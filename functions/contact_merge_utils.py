import unicodedata
import re
import html
import os
import json
import urllib.request
from datetime import datetime, timezone

def _normalizar_texto(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()


def execute_contact_merge(db, primary_id: str, secondary_ids: list[str]) -> dict:
    """Mescla contatos secundários no contato principal."""
    primary_ref = db.collection("perfil_pessoas").document(primary_id)
    primary_doc = primary_ref.get()
    if not primary_doc.exists:
        return {"success": False, "error": "Contato principal não encontrado."}

    primary_data = primary_doc.to_dict() or {}
    extra_emails = []
    extra_phones = []
    extra_tags = set(primary_data.get("tags") or [])
    extra_observacoes_lines = []
    secondary_names = []

    for sec_id in secondary_ids:
        sec_ref = db.collection("perfil_pessoas").document(sec_id)
        sec_doc = sec_ref.get()
        if not sec_doc.exists:
            continue
        sec_data = sec_doc.to_dict() or {}
        secondary_names.append(sec_data.get("nome", ""))

        email = sec_data.get("email")
        if email and email.lower() != (primary_data.get("email") or "").lower():
            extra_emails.append(email)

        phone = sec_data.get("telefone")
        if phone and phone.strip() != (primary_data.get("telefone") or "").strip():
            extra_phones.append(phone)

        for t in (sec_data.get("tags") or []):
            extra_tags.add(t)

        obs = sec_data.get("observacoes")
        if obs and obs.strip():
            extra_observacoes_lines.append(f"Nota de {sec_data.get('nome')}: {obs.strip()}")

        sec_resumo = sec_data.get("resumo_ia")
        if sec_resumo and sec_resumo.strip():
            extra_observacoes_lines.append(f"Resumo IA anterior de {sec_data.get('nome')}: {sec_resumo.strip()}")

    merged_payload = {
        "tags": list(extra_tags),
        "data_atualizacao": datetime.now(timezone.utc).isoformat()
    }

    if not primary_data.get("email") and extra_emails:
        merged_payload["email"] = extra_emails.pop(0)

    if not primary_data.get("telefone") and extra_phones:
        merged_payload["telefone"] = extra_phones.pop(0)

    current_obs = primary_data.get("observacoes") or ""
    obs_parts = []
    if current_obs.strip():
        obs_parts.append(current_obs.strip())

    if extra_emails:
        obs_parts.append(f"E-mails mesclados adicionais: {', '.join(extra_emails)}")
    if extra_phones:
        obs_parts.append(f"Telefones mesclados adicionais: {', '.join(extra_phones)}")
    if extra_observacoes_lines:
        obs_parts.extend(extra_observacoes_lines)

    if obs_parts:
        merged_payload["observacoes"] = "\n".join(obs_parts)

    total_interactions_moved = 0
    for sec_id in secondary_ids:
        interactions_ref = db.collection("interacoes_pessoas").where("pessoa_id", "==", sec_id).stream()
        for inter_doc in interactions_ref:
            db.collection("interacoes_pessoas").document(inter_doc.id).update({
                "pessoa_id": primary_id
            })
            total_interactions_moved += 1

    primary_ref.update(merged_payload)

    for sec_id in secondary_ids:
        db.collection("perfil_pessoas").document(sec_id).delete()

    merge_desc = f"Perfis de {', '.join(secondary_names)} foram mesclados neste contato. {total_interactions_moved} interações transferidas."
    db.collection("interacoes_pessoas").document().set({
        "pessoa_id": primary_id,
        "tipo": "manual",
        "data": datetime.now(timezone.utc).isoformat(),
        "descricao": merge_desc,
    })

    return {
        "success": True,
        "primary_id": primary_id,
        "primary_name": primary_data.get("nome"),
        "merged_count": len(secondary_ids),
        "message": f"Contatos mesclados com sucesso! {len(secondary_ids)} perfis unificados em '{primary_data.get('nome')}'."
    }


def find_and_notify_duplicate_contacts(db):
    """
    Busca duplicatas de contatos não ignoradas e envia notificação no Telegram com botões Sim / Não.
    """
    # 1. Carrega os pares ignorados
    ignored_keys = set()
    for snap in db.collection("ignored_contact_merges").stream():
        d = snap.to_dict() or {}
        pair_key = d.get("pair_key")
        if pair_key:
            ignored_keys.add(pair_key)

    # 2. Carrega solicitações já enviadas ou processadas
    pending_keys = set()
    for snap in db.collection("contact_merge_requests").stream():
        d = snap.to_dict() or {}
        pair_key = d.get("pair_key")
        if pair_key:
            pending_keys.add(pair_key)

    # 3. Carrega contatos
    contacts = []
    for snap in db.collection("perfil_pessoas").stream():
        d = snap.to_dict() or {}
        d["id"] = snap.id
        if d.get("nome"):
            contacts.append(d)

    if len(contacts) < 2:
        return

    def get_pair_key(id1, id2):
        return ":".join(sorted([str(id1), str(id2)]))

    clean_tel = lambda t: re.sub(r"\D", "", str(t or ""))[-8:] if len(re.sub(r"\D", "", str(t or ""))) >= 8 else ""

    new_requests = []

    for i in range(len(contacts)):
        for j in range(i + 1, len(contacts)):
            c1 = contacts[i]
            c2 = contacts[j]
            pair_key = get_pair_key(c1["id"], c2["id"])

            if pair_key in ignored_keys or pair_key in pending_keys:
                continue

            reason = None

            # Telefone idêntico
            t1 = clean_tel(c1.get("telefone") or c1.get("whatsapp") or c1.get("celular"))
            t2 = clean_tel(c2.get("telefone") or c2.get("whatsapp") or c2.get("celular"))
            if t1 and t2 and t1 == t2:
                reason = f"Telefone idêntico (...{t1})"

            # E-mail idêntico
            e1 = _normalizar_texto(c1.get("email"))
            e2 = _normalizar_texto(c2.get("email"))
            if not reason and e1 and e2 and "@" in e1 and e1 == e2:
                reason = f"E-mail idêntico ({e1})"

            # Nomes similares (primeiros 2 nomes)
            if not reason:
                n1_tokens = [tok for tok in _normalizar_texto(c1["nome"]).split() if len(tok) >= 2]
                n2_tokens = [tok for tok in _normalizar_texto(c2["nome"]).split() if len(tok) >= 2]
                if len(n1_tokens) >= 2 and len(n2_tokens) >= 2:
                    if f"{n1_tokens[0]} {n1_tokens[1]}" == f"{n2_tokens[0]} {n2_tokens[1]}":
                        reason = f"Nomes similares ('{c1['nome']}' / '{c2['nome']}')"

            if reason:
                score1 = (2 if c1.get("email") else 0) + (2 if c1.get("telefone") else 0) + (1 if c1.get("observacoes") else 0)
                score2 = (2 if c2.get("email") else 0) + (2 if c2.get("telefone") else 0) + (1 if c2.get("observacoes") else 0)

                primary = c1 if score1 >= score2 else c2
                secondary = c2 if score1 >= score2 else c1

                req_ref = db.collection("contact_merge_requests").document()
                req_id = req_ref.id
                req_data = {
                    "pair_key": pair_key,
                    "reason": reason,
                    "primary_id": primary["id"],
                    "primary_name": primary["nome"],
                    "secondary_id": secondary["id"],
                    "secondary_name": secondary["nome"],
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc),
                }
                req_ref.set(req_data)
                pending_keys.add(pair_key)

                new_requests.append((req_id, req_data, primary, secondary))
                if len(new_requests) >= 2:
                    break
        if len(new_requests) >= 2:
            break

    if not new_requests:
        return

    sys_doc = db.collection("system").document("api_keys").get()
    keys_dict = sys_doc.to_dict() or {} if sys_doc.exists else {}
    token = keys_dict.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("ALLOWED_TELEGRAM_CHAT_ID") or keys_dict.get("telegram_chat_id")

    if not token or not chat_id:
        return

    for req_id, req_data, primary, secondary in new_requests:
        text = (
            f"🔀 <b>Sugestão de Mesclagem de Contatos</b>\n\n"
            f"Foi identificada uma duplicata na sua agenda de contatos:\n"
            f"• <b>Motivo:</b> {html.escape(req_data['reason'])}\n\n"
            f"⭐ <b>Perfil Principal Mantido:</b>\n"
            f"<b>{html.escape(primary['nome'])}</b>\n"
            f"📞 {html.escape(str(primary.get('telefone') or 'Sem telefone'))} | ✉️ {html.escape(str(primary.get('email') or 'Sem e-mail'))}\n\n"
            f"👥 <b>Perfil a Unificar (Secundário):</b>\n"
            f"<b>{html.escape(secondary['nome'])}</b>\n"
            f"📞 {html.escape(str(secondary.get('telefone') or 'Sem telefone'))}\n\n"
            f"Deseja mesclar estes dois contatos agora?"
        )

        inline_keyboard = [
            [
                {"text": "✅ Sim, Mesclar Contatos", "callback_data": f"merge_confirm:{req_id}"},
                {"text": "❌ Não, Ignorar", "callback_data": f"merge_ignore:{req_id}"},
            ]
        ]

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": inline_keyboard}
        }

        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:
            print(f"[ContactMergeNotify] Erro ao enviar mensagem no Telegram: {exc}")
