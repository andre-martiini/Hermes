import json
import os
import re
import tempfile
import unicodedata
import uuid
from datetime import datetime, timezone
from io import BytesIO

from firebase_admin import firestore

from gemini_cost_controls import (
    GEMINI_BALANCED_MODEL,
    GEMINI_STRUCTURED_MODEL,
    generate_content_logged,
)
from pdf_precision import extract_pdf_text_with_fallback, is_pdf_mime_type

_TEXT_MODEL_ID = os.environ.get("TELEGRAM_EXTENDED_TEXT_MODEL", GEMINI_BALANCED_MODEL)


def _get_api_keys(db):
    doc = db.collection("system").document("api_keys").get()
    return doc.to_dict() or {} if doc.exists else {}


def _normalize_pop_text(text):
    return "".join(ch for ch in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(ch)).strip()


def execute(tool_name: str, slots: dict, db) -> str:
    if tool_name == "obter_contexto_tela":
        task_id = slots.get("task_id") or slots.get("id_tarefa")
        if not task_id:
            return "Nenhuma tarefa em foco no momento."
        doc_snap = db.collection("tarefas").document(str(task_id)).get()
        if not doc_snap.exists:
            return "Tarefa não identificada no banco de dados."
        task_data = doc_snap.to_dict() or {}
        diario_full = []
        for entry in sorted(task_data.get("acompanhamento", []), key=lambda x: x.get("data", "")):
            diario_full.append(f"[{entry.get('data')}] {entry.get('nota')}")
        arquivos_disponiveis = []
        for item in task_data.get("pool_dados", []):
            if item.get("tipo") != "arquivo":
                continue
            fid = item.get("drive_file_id")
            if not fid:
                raw = str(item.get("valor") or "")
                match = re.search(r"(?:/d/|id=)([a-zA-Z0-9_-]{10,})", raw)
                fid = match.group(1) if match else None
            if not fid:
                continue
            arquivos_disponiveis.append({
                "nome": item.get("nome", "Arquivo sem nome"),
                "drive_file_id": fid,
            })
        context = {
            "id": str(task_id),
            "titulo": task_data.get("titulo"),
            "area_tematica": task_data.get("area_tematica"),
            "sistema_id": task_data.get("sistema_id") or None,
            "plano_atual": task_data.get("plano_acao", []),
            "diario_integral": "\n".join(diario_full),
            "tags": task_data.get("tags", []),
            "arquivos_disponiveis": arquivos_disponiveis,
        }
        return json.dumps(context, ensure_ascii=False, indent=2)

    if tool_name == "ler_documento_na_integra":
        from google.genai import types
        from google import genai
        from googleapiclient.http import MediaIoBaseDownload
        from main import get_drive_service

        drive_file_id = slots.get("drive_file_id", "")
        query_especifica = slots.get("query_especifica", "")
        if not drive_file_id or not query_especifica:
            return "⚠️ Parâmetros insuficientes: forneça drive_file_id e query_especifica."
        keys = _get_api_keys(db)
        gemini_key = keys.get("gemini_api_key")
        if not gemini_key:
            return "⚠️ Gemini API não configurada."
        client = genai.Client(api_key=gemini_key)
        drive_service = get_drive_service()
        file_meta = drive_service.files().get(fileId=drive_file_id, fields="name,mimeType").execute()
        real_name = file_meta.get("name", "documento")
        mime = file_meta.get("mimeType", "application/octet-stream")
        req_dl = drive_service.files().get_media(fileId=drive_file_id)
        fh = BytesIO()
        dl = MediaIoBaseDownload(fh, req_dl)
        done = False
        while not done:
            _, done = dl.next_chunk()
        file_bytes = fh.getvalue()
        if is_pdf_mime_type(real_name, mime):
            pdf_result = extract_pdf_text_with_fallback(
                file_bytes,
                real_name,
                api_key=gemini_key,
                allow_gemini_fallback=False,
                max_pages=20,
            )
            pdf_text = (pdf_result.get("text") or "").strip()
            if pdf_text:
                response = generate_content_logged(
                    client,
                    model=_TEXT_MODEL_ID,
                    feature="telegram_extended.document_pdf_answer",
                    db=db,
                    contents=[
                        (
                            f"Responda exclusivamente a pergunta abaixo com base no documento '{real_name}'.\n\n"
                            f"PERGUNTA: {query_especifica}\n\n"
                            "REGRAS:\n"
                            "- Se a informação existir, responda de forma precisa e cite o trecho de origem.\n"
                            "- Se a informação não existir, declare isso explicitamente.\n"
                            "- Não invente dados externos.\n\n"
                            f"CONTEUDO EXTRAIDO:\n{pdf_text[:120000]}"
                        )
                    ],
                )
                return f"[Leitura de '{real_name}']\n{(response.text or '').strip()}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(real_name)[1] or ".bin") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        gemini_file = client.files.upload(
            file=tmp_path,
            config=types.UploadFileConfig(mime_type=mime, display_name=real_name),
        )
        try:
            response = generate_content_logged(
                client,
                model=_TEXT_MODEL_ID,
                feature="telegram_extended.document_file_answer",
                db=db,
                contents=[
                    types.Content(parts=[
                        types.Part.from_uri(file_uri=gemini_file.uri, mime_type=mime),
                        types.Part(text=(
                            f"Responda exclusivamente a seguinte pergunta sobre o arquivo '{real_name}': {query_especifica}\n"
                            "Se a informacao nao existir, diga explicitamente que nao foi encontrada."
                        )),
                    ])
                ],
            )
            return f"[Leitura de '{real_name}']\n{(response.text or '').strip()}"
        finally:
            try:
                client.files.delete(name=gemini_file.name)
            except Exception:
                pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if tool_name == "salvar_pop_global":
        titulo = str(slots.get("titulo") or "").strip()
        instrucao = str(slots.get("instrucao_sistema") or "").strip()
        gatilhos = slots.get("gatilhos") or []
        if not titulo:
            return json.dumps({"status": "error", "reason": "titulo_obrigatorio"}, ensure_ascii=False)
        if not instrucao:
            return json.dumps({"status": "error", "reason": "instrucao_obrigatoria"}, ensure_ascii=False)
        gatilhos_clean = []
        seen = set()
        for item in gatilhos:
            raw = str(item or "").strip().lower()
            norm = _normalize_pop_text(raw)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            gatilhos_clean.append(raw)
        if not gatilhos_clean:
            return json.dumps({"status": "error", "reason": "gatilhos_obrigatorios"}, ensure_ascii=False)
        titulo_norm = _normalize_pop_text(titulo)
        existing_ref = None
        existing_data = None
        normalized_triggers = {_normalize_pop_text(i) for i in gatilhos_clean}
        for pop_doc in db.collection("pops_diretrizes").stream():
            pop_data = pop_doc.to_dict() or {}
            existing_title_norm = _normalize_pop_text(pop_data.get("titulo") or "")
            existing_triggers_norm = {_normalize_pop_text(item) for item in (pop_data.get("gatilhos") or []) if _normalize_pop_text(item)}
            if titulo_norm == existing_title_norm or existing_triggers_norm.intersection(normalized_triggers):
                existing_ref = pop_doc.reference
                existing_data = pop_data
                break
        payload = {
            "titulo": titulo,
            "gatilhos": gatilhos_clean,
            "instrucao_sistema": instrucao,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "updated_by": "telegram",
            "origem": "telegram",
        }
        if existing_ref:
            payload["created_at"] = existing_data.get("created_at", firestore.SERVER_TIMESTAMP)
            existing_ref.set(payload, merge=True)
            return json.dumps({"status": "updated", "pop_id": existing_ref.id, "titulo": titulo, "gatilhos": gatilhos_clean}, ensure_ascii=False)
        new_ref = db.collection("pops_diretrizes").document()
        payload["created_at"] = firestore.SERVER_TIMESTAMP
        new_ref.set(payload)
        return json.dumps({"status": "saved", "pop_id": new_ref.id, "titulo": titulo, "gatilhos": gatilhos_clean}, ensure_ascii=False)

    if tool_name == "resolver_conflito_memoria":
        import main as main_mod

        memoria_id = str(slots.get("memoria_id") or "")
        decisao = str(slots.get("decisao") or "").strip().lower()
        fato_atualizado = str(slots.get("fato_atualizado") or "")
        categoria = str(slots.get("categoria") or "fato_isolado")
        if decisao == "manter_existente":
            db.collection("knowledge_nodes").document(memoria_id).set({
                "data_atualizacao": main_mod._iso_now_utc(),
                "conflito_resolvido_em": firestore.SERVER_TIMESTAMP,
                "ultima_decisao_humana": "manter_existente",
            }, merge=True)
            return json.dumps({"status": "resolved", "decision": "kept_existing", "memory_id": memoria_id}, ensure_ascii=False)
        if decisao != "substituir_pelo_novo":
            return json.dumps({"status": "error", "reason": "decisao_invalida"}, ensure_ascii=False)
        gemini_key = _get_api_keys(db).get("gemini_api_key")
        result = main_mod._save_memory_node(
            db=db,
            api_key=gemini_key,
            fato=fato_atualizado,
            categoria=categoria,
            session_id=None,
            user_uid=None,
            force_update_id=memoria_id,
        )
        result["decision"] = "replaced_existing"
        return json.dumps(result, ensure_ascii=False)

    if tool_name == "atualizar_personalidade":
        novo_texto = str(slots.get("nova_personalidade") or "").strip()
        motivo = str(slots.get("motivo") or "").strip()
        if not novo_texto:
            return json.dumps({"status": "ignored", "reason": "empty_personality"}, ensure_ascii=False)
        db.collection("system").document("copilot_soul").set({
            "content": novo_texto,
            "last_reason": motivo,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "updated_by_uid": None,
            "source": "telegram",
        }, merge=True)
        return json.dumps({"status": "updated", "content": novo_texto[:300]}, ensure_ascii=False)

    if tool_name == "resolver_conflito_procedimento":
        proc_id = str(slots.get("id_procedimento") or "")
        justificativa = str(slots.get("justificativa_humana") or "").strip()
        confirmar = bool(slots.get("confirmar_contrato"))
        proc_ref = db.collection("conhecimento_mestre").document(proc_id)
        proc_doc = proc_ref.get()
        if not proc_doc.exists:
            return f"⚠️ Procedimento '{proc_id}' não encontrado em conhecimento_mestre."
        proc = proc_doc.to_dict() or {}
        conteudo_atual = proc.get("conteudo_regra") or proc.get("conteudo", "(sem conteúdo)")
        titulo = proc.get("titulo", proc_id)
        if not confirmar:
            regra_booleana = f"SE ({justificativa}) ENTAO procedimento_valido = True E necessita_revisao = False"
            return (
                "## Contrato de Entendimento\n\n"
                f"**Procedimento:** {titulo}\n"
                f"**Status atual:** {proc.get('status', 'ativo')}\n\n"
                f"**Conteúdo atual:**\n```\n{conteudo_atual[:800]}{'...' if len(conteudo_atual) > 800 else ''}\n```\n\n"
                f"**Sua justificativa:** {justificativa}\n\n"
                f"**Regra booleana traduzida:**\n`{regra_booleana}`\n\n"
                "Para confirmar, chame novamente com `confirmar_contrato=True`."
            )
        proc_ref.update({"status": "arquivado_backup", "data_arquivamento": firestore.SERVER_TIMESTAMP})
        resolved_id = str(uuid.uuid4())[:12]
        db.collection("conhecimento_mestre").document(resolved_id).set({
            "titulo": titulo,
            "area_tematica": proc.get("area_tematica", ""),
            "conteudo_regra": conteudo_atual,
            "justificativa_da_regra": justificativa,
            "status": "ativo",
            "necessita_revisao": False,
            "tag_aviso": "",
            "data_criacao": firestore.SERVER_TIMESTAMP,
            "tipo": proc.get("tipo", "procedimento_evoluido"),
            "autor": "human_review_telegram",
            "procedimento_anterior_id": proc_id,
        })
        return (
            f"✅ Conflito resolvido. Procedimento **{titulo}** validado pelo revisor humano.\n"
            f"- Versão anterior arquivada\n"
            f"- Novo documento criado: `{resolved_id}`"
        )

    if tool_name == "editar_plano_acao":
        import difflib as _difflib

        task_id = str(slots.get("task_id") or "")
        novo_plano = slots.get("novo_plano") or []
        justificativa = str(slots.get("justificativa_diario") or "").strip()
        task_ref = db.collection("tarefas").document(task_id)
        task_doc = task_ref.get()
        if not task_doc.exists:
            return f"ERRO|Tarefa '{task_id}' não encontrada."
        task_data = task_doc.to_dict() or {}
        plano_atual = task_data.get("plano_acao", [])
        now_iso = datetime.now(timezone.utc).isoformat()
        plano_por_id = {p.get("id"): p for p in plano_atual if p.get("id")}
        textos_originais = [p.get("text", p.get("texto", "")) for p in plano_atual]
        plano_final = []
        for item in novo_plano:
            texto_novo = str(item.get("text") or item.get("texto") or "").strip()
            if not texto_novo:
                continue
            item_id = item.get("id", "")
            if item_id and item_id in plano_por_id:
                original = plano_por_id[item_id]
                plano_final.append({"id": item_id, "text": texto_novo, "completed": original.get("completed", False)})
                continue
            matches = _difflib.get_close_matches(texto_novo, textos_originais, n=1, cutoff=0.85)
            if matches:
                idx = textos_originais.index(matches[0])
                original = plano_atual[idx]
                plano_final.append({"id": original.get("id", str(uuid.uuid4())[:8]), "text": texto_novo, "completed": original.get("completed", False)})
                continue
            plano_final.append({"id": str(uuid.uuid4())[:8], "text": texto_novo, "completed": False})
        task_ref.update({
            "plano_acao": plano_final,
            "data_atualizacao": now_iso,
            "acompanhamento": firestore.ArrayUnion([{"data": now_iso, "nota": f"[Telegram Hermes] Plano de ação atualizado: {justificativa}"}]),
        })
        return "OK"

    if tool_name == "agendar_lembrete_acao":
        task_id = str(slots.get("task_id") or slots.get("id_tarefa") or "").strip()
        reminder_date = str(slots.get("data") or "").strip()
        reminder_time = str(slots.get("horario") or slots.get("hora") or "").strip()[:5]
        custom_message = str(slots.get("texto") or slots.get("message") or "").strip()[:500]

        if not task_id:
            return "ERRO|Informe o ID da acao para agendar o lembrete."
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", reminder_date):
            return "ERRO|Data invalida. Use YYYY-MM-DD."
        if not re.match(r"^\d{2}:\d{2}$", reminder_time):
            return "ERRO|Horario invalido. Use HH:MM."
        try:
            datetime.strptime(f"{reminder_date} {reminder_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            return "ERRO|Data ou horario inexistente."

        reminder_at = f"{reminder_date}T{reminder_time}:00"
        task_ref = db.collection("tarefas").document(task_id)
        task_doc = task_ref.get()
        if not task_doc.exists:
            return f"ERRO|Acao '{task_id}' nao encontrada."

        task_data = task_doc.to_dict() or {}
        reminders = task_data.get("reminders") if isinstance(task_data.get("reminders"), list) else []
        normalized = []
        for idx, reminder in enumerate(reminders):
            if not isinstance(reminder, dict) or not reminder.get("reminder_at"):
                continue
            normalized.append({
                "id": str(reminder.get("id") or f"legacy-{idx}"),
                "reminder_at": str(reminder.get("reminder_at")),
                "reminder_sent": bool(reminder.get("reminder_sent")),
                "created_at": str(reminder.get("created_at") or reminder.get("reminder_at")),
                "message": str(reminder.get("message") or "").strip(),
            })
        if not normalized and task_data.get("reminder_at"):
            normalized.append({
                "id": "legacy-reminder",
                "reminder_at": str(task_data.get("reminder_at")),
                "reminder_sent": bool(task_data.get("reminder_sent")),
                "created_at": str(task_data.get("data_atualizacao") or task_data.get("data_criacao") or task_data.get("reminder_at")),
                "message": str(task_data.get("reminder_message") or "").strip(),
            })

        now_iso = datetime.now(timezone.utc).isoformat()
        new_reminder = {
            "id": str(uuid.uuid4())[:12],
            "reminder_at": reminder_at,
            "reminder_sent": False,
            "created_at": now_iso,
            "created_by": "telegram",
        }
        if custom_message:
            new_reminder["message"] = custom_message
        ordered = sorted([*normalized, new_reminder], key=lambda item: item.get("reminder_at") or "")
        next_pending = next((item for item in ordered if not item.get("reminder_sent")), None)
        update_payload = {
            "reminders": ordered,
            "reminder_at": next_pending.get("reminder_at") if next_pending else None,
            "reminder_sent": bool(next_pending.get("reminder_sent")) if next_pending else True,
            "data_atualizacao": now_iso,
            "acompanhamento": firestore.ArrayUnion([{
                "data": now_iso,
                "nota": f"[Telegram Hermes] Lembrete agendado para {reminder_date} {reminder_time}."
            }]),
        }
        task_ref.update(update_payload)
        return f"OK|{task_id}|{reminder_at}"

    if tool_name == "preparar_edicao_acao":
        task_id = str(slots.get("task_id") or "")
        alteracoes = slots.get("alteracoes") or {}
        justificativa = str(slots.get("justificativa") or "")
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if "data_limite" in alteracoes:
            val = alteracoes["data_limite"]
            if val and val not in ("-", "0000-00-00") and val < today_str:
                return f"ERRO|A data de execução não pode ser no passado ({val})."
        allowed_fields = {"titulo", "descricao", "data_limite", "status", "tags", "area_tematica", "tipo_acao", "notas"}
        task_ref = db.collection("tarefas").document(task_id)
        task_doc = task_ref.get()
        if not task_doc.exists:
            return f"ERRO|Ação '{task_id}' não encontrada."
        task_data = task_doc.to_dict() or {}
        if task_data.get("status") == "concluído":
            return "ERRO|Esta ação já foi concluída e não pode ser editada."
        alteracoes_diff = {}
        for campo, novo_valor in alteracoes.items():
            if campo not in allowed_fields:
                continue
            original = task_data.get(campo)
            original_str = ", ".join(str(v) for v in original) if isinstance(original, list) else (str(original) if original is not None else "")
            novo_str = ", ".join(str(v) for v in novo_valor) if isinstance(novo_valor, list) else (str(novo_valor) if novo_valor is not None else "")
            alteracoes_diff[campo] = {"original": original_str, "novo": novo_str, "novo_raw": novo_valor}
        if not alteracoes_diff:
            return "ERRO|Nenhum campo válido para editar."
        snapshot_ts = task_data.get("data_atualizacao") or task_data.get("data_criacao", "")
        payload = {
            "task_id": task_id,
            "titulo": task_data.get("titulo", ""),
            "alteracoes": alteracoes_diff,
            "justificativa": justificativa,
            "snapshot_ts": str(snapshot_ts),
            "status": "pending",
        }
        return json.dumps(payload, ensure_ascii=False)

    if tool_name == "gerar_relatorio":
        from google import genai

        keys = _get_api_keys(db)
        gemini_key = keys.get("gemini_api_key")
        if not gemini_key:
            return "⚠️ Gemini API não configurada."
        client = genai.Client(api_key=gemini_key)
        titulo = str(slots.get("titulo") or "").strip()
        tipo = str(slots.get("tipo") or "executivo").strip()
        contexto = str(slots.get("contexto") or "").strip()
        secoes_customizadas = slots.get("secoes_customizadas") or []
        data_hoje = datetime.now(timezone.utc).strftime("%d/%m/%Y")
        report_id = str(uuid.uuid4())[:16]
        skeleton_prompt = (
            f"Crie um esqueleto de seções para um relatório {tipo} intitulado '{titulo}'.\n"
            f"CONTEXTO:\n{contexto[:2500]}\n\n"
            'Responda APENAS com JSON no formato {"secoes":["Seção 1","Seção 2"]}.'
        )
        if secoes_customizadas:
            skeleton_prompt += f"\nInclua obrigatoriamente: {secoes_customizadas}"
        skeleton_resp = generate_content_logged(
            client,
            model=GEMINI_STRUCTURED_MODEL,
            feature="telegram_extended.report_skeleton",
            db=db,
            contents=skeleton_prompt,
        )
        skeleton_text = skeleton_resp.text or ""
        json_match = re.search(r"\{.*\}", skeleton_text, re.DOTALL)
        if json_match:
            secoes = (json.loads(json_match.group()) or {}).get("secoes", [])
        else:
            secoes = ["Sumário Executivo", "Análise", "Conclusão e Recomendações"]
        sections_content = {}
        for secao in secoes:
            section_prompt = (
                f"Escreva a seção '{secao}' de um relatório {tipo} intitulado '{titulo}'.\n"
                f"Data: {data_hoje}\n\nCONTEXTO:\n{contexto[:4000]}\n\n"
                "Entregue Markdown direto, sem repetir o título da seção."
            )
            sect_resp = generate_content_logged(
                client,
                model=_TEXT_MODEL_ID,
                feature="telegram_extended.report_section",
                db=db,
                contents=section_prompt,
            )
            sections_content[secao] = sect_resp.text or "*(conteúdo indisponível)*"
        md_parts = [f"# {titulo}", "", f"**Tipo:** Relatório {tipo.capitalize()}  ", f"**Data:** {data_hoje}  ", "**Gerado por:** Hermes Telegram  ", "", "---", ""]
        for secao, content in sections_content.items():
            md_parts.append(f"## {secao}")
            md_parts.append("")
            md_parts.append(content)
            md_parts.append("")
        final_markdown = "\n".join(md_parts)
        db.collection("relatorios").document(report_id).set({
            "id": report_id,
            "titulo": titulo,
            "tipo": tipo,
            "markdown": final_markdown,
            "secoes": secoes,
            "session_id": None,
            "task_id": slots.get("task_id"),
            "createdAt": firestore.SERVER_TIMESTAMP,
            "driveFileId": None,
            "driveUrl": None,
            "source": "telegram",
        })
        return json.dumps({"report_id": report_id, "titulo": titulo, "secoes": secoes, "status": "gerado"}, ensure_ascii=False)

    if tool_name == "gerar_rascunho_formulario":
        titulo = str(slots.get("titulo") or "").strip()
        descricao = str(slots.get("descricao") or "").strip()
        perguntas = slots.get("perguntas") or []
        return json.dumps({"titulo": titulo, "descricao": descricao, "perguntas": perguntas, "status": "draft"}, ensure_ascii=False)

    if tool_name == "obter_portal_financeiro_publico":
        docs = db.collection("finance_transactions").where("origin", "==", "external").stream()
        transactions = []
        for snap in docs:
            item = snap.to_dict() or {}
            if item.get("status") == "deleted":
                continue
            item["id"] = snap.id
            transactions.append(item)
        transactions.sort(key=lambda entry: str(entry.get("date") or ""), reverse=True)
        return json.dumps({"valid": True, "transactions": transactions}, ensure_ascii=False)

    if tool_name == "registrar_transacao_financeira_publica":
        description = str(slots.get("description") or "").strip()
        amount = slots.get("amount")
        if not description:
            return "Descricao obrigatoria."
        numeric_amount = float(amount)
        now = datetime.now()
        day = now.day
        sprint = 1 if day < 8 else 2 if day < 15 else 3 if day < 22 else 4
        ref = db.collection("finance_transactions").document()
        ref.set({
            "description": description,
            "amount": numeric_amount,
            "date": now.isoformat(),
            "sprint": sprint,
            "category": "Gasto Externo",
            "status": "active",
            "origin": "external",
            "source": "telegram",
        })
        return json.dumps({"success": True, "id": ref.id}, ensure_ascii=False)

    if tool_name == "obter_portal_compras_publico":
        docs = db.collection("shopping_items").stream()
        items = []
        for snap in docs:
            item = snap.to_dict() or {}
            item["id"] = snap.id
            items.append(item)
        return json.dumps({"valid": True, "items": items}, ensure_ascii=False)

    if tool_name == "mutar_portal_compras_publico":
        action = str(slots.get("action") or "").strip()
        item_id = slots.get("item_id") or slots.get("itemId")
        value = slots.get("value")
        if action in {"toggle_planned", "toggle_purchased", "update_quantity"} and not item_id:
            return "item_id obrigatorio."
        if action == "toggle_planned":
            ref = db.collection("shopping_items").document(str(item_id))
            snap = ref.get()
            if not snap.exists:
                return "Item nao encontrado."
            item = snap.to_dict() or {}
            ref.update({"isPlanned": not bool(item.get("isPlanned")), "isPurchased": False})
        elif action == "toggle_purchased":
            ref = db.collection("shopping_items").document(str(item_id))
            snap = ref.get()
            if not snap.exists:
                return "Item nao encontrado."
            item = snap.to_dict() or {}
            ref.update({"isPurchased": not bool(item.get("isPurchased"))})
        elif action == "update_quantity":
            db.collection("shopping_items").document(str(item_id)).update({"quantidade": str(value or "")})
        elif action in {"clear_planning", "finalize"}:
            batch = db.batch()
            for snap in db.collection("shopping_items").stream():
                item = snap.to_dict() or {}
                if item.get("isPlanned") or item.get("isPurchased"):
                    batch.update(snap.reference, {"isPlanned": False, "isPurchased": False})
            batch.commit()
        else:
            return "Acao invalida."
        return json.dumps({"success": True}, ensure_ascii=False)

    if tool_name == "mutar_lista_compras":
        from security_portals import _normalize_name

        action = str(slots.get("action") or "").strip()
        item_id = str(slots.get("item_id") or slots.get("itemId") or "").strip()
        allowed_actions = {"create", "update", "delete", "import_batch", "clear_planning", "finalize"}
        if action not in allowed_actions:
            return "Acao invalida."
        if action == "create":
            nome = str(slots.get("nome") or "").strip()
            if not nome:
                return "Nome do item e obrigatorio."
            nome_norm = _normalize_name(nome)
            for snap in db.collection("shopping_items").stream():
                item = snap.to_dict() or {}
                if _normalize_name(str(item.get("nome") or "")) == nome_norm:
                    return "Ja existe um item com esse nome."
            payload = {
                "nome": nome,
                "categoria": str(slots.get("categoria") or "Geral").strip() or "Geral",
                "quantidade": str(slots.get("quantidade") or "1").strip() or "1",
                "unit": str(slots.get("unit") or "un").strip() or "un",
                "isPlanned": bool(slots.get("isPlanned")),
                "isPurchased": bool(slots.get("isPurchased")),
            }
            if payload["isPurchased"]:
                payload["isPlanned"] = True
            ordem = slots.get("ordem")
            if ordem is not None:
                payload["ordem"] = int(ordem)
            ref = db.collection("shopping_items").document()
            ref.set(payload)
            return json.dumps({"success": True, "id": ref.id}, ensure_ascii=False)
        if action == "update":
            if not item_id:
                return "item_id obrigatorio."
            ref = db.collection("shopping_items").document(item_id)
            snap = ref.get()
            if not snap.exists:
                return "Item nao encontrado."
            current = snap.to_dict() or {}
            updates = {}
            for field in ("nome", "categoria", "quantidade", "unit", "ordem", "isPlanned", "isPurchased"):
                if field in slots:
                    updates[field] = slots.get(field)
            if "nome" in updates:
                updates["nome"] = str(updates["nome"]).strip()
            if "categoria" in updates:
                updates["categoria"] = str(updates["categoria"]).strip() or "Geral"
            if "quantidade" in updates:
                updates["quantidade"] = str(updates["quantidade"]).strip() or "1"
            if "unit" in updates:
                updates["unit"] = str(updates["unit"]).strip() or "un"
            if "ordem" in updates and updates["ordem"] is not None:
                updates["ordem"] = int(updates["ordem"])
            if "isPurchased" in updates and updates["isPurchased"]:
                updates["isPlanned"] = True
            elif "isPurchased" in updates and not updates["isPurchased"] and "isPlanned" not in updates:
                updates["isPlanned"] = bool(current.get("isPlanned"))
            if "isPlanned" in updates and not updates["isPlanned"]:
                updates["isPurchased"] = False
            if not updates:
                return "Nenhum campo valido para atualizar."
            ref.update(updates)
            return json.dumps({"success": True, "id": item_id}, ensure_ascii=False)
        if action == "delete":
            if not item_id:
                return "item_id obrigatorio."
            db.collection("shopping_items").document(item_id).delete()
            return json.dumps({"success": True, "id": item_id}, ensure_ascii=False)
        if action == "import_batch":
            raw_text = str(slots.get("importText") or slots.get("import_text") or "").strip()
            if not raw_text:
                return "Texto de importacao obrigatorio."
            existing_names = {_normalize_name(str((snap.to_dict() or {}).get("nome") or "")) for snap in db.collection("shopping_items").stream()}
            batch = db.batch()
            created = 0
            for line in raw_text.splitlines():
                cleaned = line.strip()
                if not cleaned:
                    continue
                nome, categoria = [part.strip() for part in cleaned.split("|", 1)] if "|" in cleaned else [cleaned, "Geral"]
                nome_norm = _normalize_name(nome)
                if not nome or nome_norm in existing_names:
                    continue
                existing_names.add(nome_norm)
                ref = db.collection("shopping_items").document()
                batch.set(ref, {"nome": nome, "categoria": categoria or "Geral", "quantidade": "1", "unit": "un", "isPlanned": False, "isPurchased": False})
                created += 1
            batch.commit()
            return json.dumps({"success": True, "created": created}, ensure_ascii=False)
        batch = db.batch()
        affected = 0
        for snap in db.collection("shopping_items").stream():
            item = snap.to_dict() or {}
            if item.get("isPlanned") or item.get("isPurchased"):
                batch.update(snap.reference, {"isPlanned": False, "isPurchased": False})
                affected += 1
        batch.commit()
        return json.dumps({"success": True, "affected": affected}, ensure_ascii=False)

    if tool_name == "obter_projeto_bolsas_publico":
        project_id = str(slots.get("project_id") or slots.get("projectId") or "").strip()
        if not project_id:
            return "Projeto obrigatorio."
        snap = db.collection("projetos").document(project_id).get()
        if not snap.exists:
            return "Projeto nao encontrado."
        project = snap.to_dict() or {}
        return json.dumps({"valid": True, "project": {"id": snap.id, "nome": project.get("nome")}}, ensure_ascii=False)

    if tool_name == "registrar_inscricao_bolsa_publica":
        project_id = str(slots.get("project_id") or slots.get("projectId") or "").strip()
        form = slots.get("formData") or slots.get("form_data") or {}
        if not project_id or not isinstance(form, dict):
            return "Dados do cadastro invalidos."
        required_fields = ["nome", "cpf", "rg", "email", "telefone"]
        missing = [field for field in required_fields if not str(form.get(field) or "").strip()]
        if missing:
            return f"Campos obrigatorios ausentes: {', '.join(missing)}"
        project_snap = db.collection("projetos").document(project_id).get()
        if not project_snap.exists:
            return "Projeto nao encontrado."
        cpf = str(form.get("cpf") or "").strip()
        perfil_data = {
            "nome": str(form.get("nome") or "").strip(),
            "cpf": cpf,
            "rg": str(form.get("rg") or "").strip(),
            "email": str(form.get("email") or "").strip(),
            "telefone": str(form.get("telefone") or "").strip(),
            "origem": "telegram_publico",
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        pessoas = list(db.collection("perfil_pessoas").where("cpf", "==", cpf).limit(1).stream())
        if pessoas:
            pessoa_ref = pessoas[0].reference
            pessoa_ref.set(perfil_data, merge=True)
        else:
            pessoa_ref = db.collection("perfil_pessoas").document()
            pessoa_ref.set({**perfil_data, "created_at": firestore.SERVER_TIMESTAMP})
        existing_link = list(
            db.collection("vinculos_projeto")
            .where("project_id", "==", project_id)
            .where("cpf", "==", cpf)
            .limit(1)
            .stream()
        )
        if existing_link:
            return json.dumps({"success": True, "alreadyLinked": True, "person_id": pessoa_ref.id}, ensure_ascii=False)
        db.collection("vinculos_projeto").document().set({
            "project_id": project_id,
            "person_id": pessoa_ref.id,
            "cpf": cpf,
            "status": "inscrito",
            "created_at": firestore.SERVER_TIMESTAMP,
            "origem": "telegram_publico",
        })
        return json.dumps({"success": True, "person_id": pessoa_ref.id}, ensure_ascii=False)

    if tool_name == "consultar_financas_v2":
        mes = slots.get("mes")
        ano = slots.get("ano")
        now = datetime.now()
        if mes is None:
            mes = now.month - 1  # JS month is 0-indexed
            if mes < 0:
                mes = 11
                ano = (ano or now.year) - 1
        if ano is None:
            ano = now.year

        # Fetch data
        bills_docs = db.collection("fixed_bills").where("month", "==", mes).where("year", "==", ano).stream()
        income_docs = db.collection("income_entries").where("month", "==", mes).where("year", "==", ano).where("status", "==", "active").stream()
        goals_docs = db.collection("finance_goals").stream()
        settings_doc = db.collection("finance_settings").document("config").get()

        bills = []
        total_bills = 0.0
        total_paid_bills = 0.0
        for doc in bills_docs:
            d = doc.to_dict()
            d["id"] = doc.id
            bills.append(d)
            amount = float(d.get("amount", 0))
            total_bills += amount
            if d.get("isPaid"):
                total_paid_bills += amount

        income = []
        total_income = 0.0
        total_received_income = 0.0
        for doc in income_docs:
            d = doc.to_dict()
            d["id"] = doc.id
            income.append(d)
            amount = float(d.get("amount", 0))
            total_income += amount
            if d.get("isReceived"):
                total_received_income += amount

        goals = []
        for doc in goals_docs:
            d = doc.to_dict()
            d["id"] = doc.id
            goals.append(d)
        goals.sort(key=lambda x: x.get("priority", 99))

        settings = settings_doc.to_dict() or {}

        summary = {
            "periodo": {"mes": int(mes), "ano": int(ano)},
            "resumo": {
                "total_renda": total_income,
                "renda_recebida": total_received_income,
                "total_contas": total_bills,
                "contas_pagas": total_paid_bills,
                "saldo_previsto": total_income - total_bills,
                "saldo_atual": total_received_income - total_paid_bills
            },
            "metas": goals,
            "reserva_emergencia": {
                "alvo": settings.get("emergencyReserveTarget", 0),
                "atual": settings.get("emergencyReserveCurrent", 0)
            },
            "detalhes": {
                "contas": bills,
                "rendas": income
            }
        }
        return json.dumps(summary, ensure_ascii=False)

    if tool_name == "registrar_item_financeiro_v2":
        tipo = slots.get("tipo")
        descricao = str(slots.get("descricao") or "").strip()
        valor = float(slots.get("valor") or 0)
        categoria = str(slots.get("categoria") or "Geral").strip()
        
        now = datetime.now()
        mes = slots.get("mes")
        if mes is None:
            mes = now.month - 1
        ano = slots.get("ano") or now.year
        data_iso = slots.get("data") or now.isoformat()

        if tipo == "renda":
            ref = db.collection("income_entries").document()
            ref.set({
                "description": descricao,
                "amount": valor,
                "category": categoria,
                "month": int(mes),
                "year": int(ano),
                "isReceived": False,
                "status": "active",
                "date": data_iso,
                "source": "hermes_v2"
            })
            return json.dumps({"success": True, "tipo": "renda", "id": ref.id})

        elif tipo == "obrigacao_fixa":
            ref = db.collection("fixed_bills").document()
            ref.set({
                "description": descricao,
                "amount": valor,
                "category": categoria,
                "month": int(mes),
                "year": int(ano),
                "isPaid": False,
                "date": data_iso,
                "source": "hermes_v2"
            })
            return json.dumps({"success": True, "tipo": "obrigacao_fixa", "id": ref.id})

        elif tipo == "transacao_avulsa":
            day = now.day
            sprint = 1 if day < 8 else 2 if day < 15 else 3 if day < 22 else 4
            ref = db.collection("finance_transactions").document()
            ref.set({
                "description": descricao,
                "amount": valor,
                "category": categoria,
                "date": data_iso,
                "sprint": sprint,
                "status": "active",
                "origin": "internal",
                "source": "hermes_v2"
            })
            return json.dumps({"success": True, "tipo": "transacao_avulsa", "id": ref.id})

        return json.dumps({"success": False, "reason": "tipo_invalido"})

    raise KeyError(tool_name)
