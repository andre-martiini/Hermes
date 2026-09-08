"""Ferramentas (function calling) do Gemini para o Telegram

Extraido de hermes_core_logic.py::_process_telegram_message (P02, modularizacao
por area -- hermes_core_logic.py e telegram_utils.py cresceram alem do teto de
~64000 tokens de saida por chamada de escrita do Argos; ver decisao do Andre em
2026-09-08). Split puramente mecanico: nenhuma linha de logica foi reescrita, so
movida para dentro de `build_telegram_tool_closures(...)`, uma factory function
que recebe exatamente as variaveis externas que os 21 closures capturam (nomes
identicos aos originais, preservados de proposito -- ver ATENCAO abaixo) e
devolve `tools_list`.

ATENCAO para mock.patch/mock.patch.object em testes: as funcoes deste arquivo
resolvem nomes livres (`_get_api_keys`, `_normalize_for_matching`, `firestore`,
etc.) pelo namespace DESTE modulo, nao pelo de hermes_core_logic nem de
telegram_handlers_core -- mesmo padrao documentado em telegram_utils.py. Um
`mock.patch.object(hermes_core_logic, "_get_api_keys", ...)` nao intercepta uma
chamada feita de dentro de uma funcao deste arquivo.

test_tool_schemas.py usa introspeccao AST (`ast.parse(inspect.getsource(...))`)
sobre este modulo/funcao para montar stubs de schema Gemini e para reexecutar
ativar_modo_secretario/desativar_modo_secretario/consultar_status_modo_secretario
isoladamente (esses 3 capturam so `db`) -- ver TestSecretarioTelegramExecucao.
"""
import html
import json
import re
from datetime import datetime, timedelta, timezone

import requests as _requests
from firebase_admin import firestore

from telegram_utils import _get_api_keys, _normalize_for_matching, normalizar_area_tematica

def build_telegram_tool_closures(db, session, contexto_ativo, acao_snapshot, request_acao_id, internal_hermes_request, explicit_web_request, _areas_validas):
    """Monta e devolve tools_list: os 21 closures de function-calling do Gemini para o Telegram."""
    # --- Tool definitions ---
    def consultar_historico_acoes(
        query: str,
        area_tematica: str = None,
        data_limite_inicio: str = None,
        data_limite_fim: str = None,
        status: str = None,
    ):
        """Busca ações e tarefas no Hermes. Use status para filtrar por estado (ex: 'em andamento', 'concluída', 'cancelada'). Use data_limite_inicio/fim (YYYY-MM-DD) para filtrar por prazo."""
        if contexto_ativo == "acao" and acao_snapshot:
            titulo_acao = acao_snapshot.get("titulo") or request_acao_id or "ação atual"
            return (
                f"Contexto trancado na ação '{titulo_acao}'. "
                "Os dados desta ação já estão carregados no contexto — use-os diretamente. "
                "Para pesquisar outras ações, o usuário deve sair primeiro com /sair."
            )
        from tools.busca_grafo import buscar_tarefas

        _STOPWORDS_TG = {"de", "a", "o", "que", "e", "do", "da", "em", "um", "uma",
                         "os", "as", "no", "na", "com", "por", "para", "dos", "das",
                         "nos", "nas", "ao", "se", "ou", "acao", "acoes", "tarefa",
                         "tarefas", "pesquisa", "pesquisar", "pesquise", "busca",
                         "buscar", "busque", "procura", "procurar", "procure",
                         "localiza", "localizar", "localize", "ative", "ativar",
                         "ativa", "contexto"}
        _tg_terms = [w for w in re.findall(r"[\w./-]+", _normalize_for_matching(query), flags=re.UNICODE) if w not in _STOPWORDS_TG and len(w) > 2]
        _tg_mode = "all" if len(_tg_terms) >= 2 else "any"
        res = buscar_tarefas(query, area_tematica=area_tematica, match_mode=_tg_mode,
                             data_limite_inicio=data_limite_inicio, data_limite_fim=data_limite_fim,
                             status=status)
        if _tg_mode == "all" and not res.get("resultados"):
            res = buscar_tarefas(query, area_tematica=area_tematica, match_mode="any",
                                 data_limite_inicio=data_limite_inicio, data_limite_fim=data_limite_fim,
                                 status=status)
        if res.get("erro"):
            return f"⚠️ [ERRO] {res['erro']}"
        resultados = res.get("resultados", [])
        if not resultados:
            filtros_desc = []
            if query and query.strip():
                filtros_desc.append(f"query='{query.strip()}'")
            if status:
                filtros_desc.append(f"status='{status}'")
            if area_tematica:
                filtros_desc.append(f"area='{area_tematica}'")
            if data_limite_inicio or data_limite_fim:
                filtros_desc.append(f"prazo=[{data_limite_inicio or '*'} a {data_limite_fim or '*'}]")
            filtros_str = ", ".join(filtros_desc) if filtros_desc else "(sem filtros)"
            return (
                f"NENHUMA TAREFA ENCONTRADA com os filtros: {filtros_str}.\n"
                "INSTRUCAO OBRIGATORIA: Informe ao usuario que nao encontrou. "
                "NAO invente titulos, status ou dados. NAO use RAG para compensar."
            )
        lines = [
            "=== TAREFAS REAIS ENCONTRADAS NO BANCO DE DADOS ===",
            "REGRA: Use EXCLUSIVAMENTE os campos abaixo. Nao invente, nao complete, nao use RAG.",
            "",
        ]
        if res.get("aviso"):
            lines.append(f"AVISO TECNICO: {res['aviso']}")
        for r in resultados:
            lines.append(f"ID: {r['id']}")
            lines.append(f"Titulo: {r['titulo']}")
            lines.append(f"Status: {r['status']} | Tipo: {r.get('tipo_acao') or 'nao informado'}")
            lines.append(f"Prazo: {r.get('data_limite', 'N/A')} | Area: {r['area']}")
            if r.get('processo_sei'):
                lines.append(f"Processo SEI: {r['processo_sei']}")
            lines.append(f"Responsavel: {r['responsavel'] or 'nao informado'}")
            if r.get('tags'):
                lines.append(f"Tags: {', '.join(r['tags'])}")
            if r.get('sintese_demanda'):
                lines.append(f"Sintese da Demanda: {r['sintese_demanda']}")
            if r.get('descricao'):
                lines.append(f"Descricao: {r['descricao']}")
            if r.get('notas'):
                lines.append(f"Notas: {r['notas']}")
            plano = r.get('plano_acao', [])
            if plano:
                lines.append("Plano de Acao:")
                for passo in plano:
                    lines.append(f"  {passo}")
            acomp = r.get('acompanhamento_recente', [])
            if acomp:
                lines.append("Diario de Bordo (ultimas entradas):")
                for entrada in acomp:
                    lines.append(f"  {entrada}")
            lines.append("---")
        return "\n".join(lines)

    def buscar_arquivos_acervo(query: str):
        """Busca documentos, manuais e arquivos no Acervo Global do Hermes."""
        from tools.busca_acervo import buscar_acervo
        res = buscar_acervo(query)
        if res.get("erro"):
            return f"⚠️ [ERRO] {res['erro']}"
        resultados = res.get("resultados", [])
        if not resultados:
            return "Nenhum documento encontrado."
        return "\n\n".join(
            f"DOC: {r['titulo']} | FONTE: {r['fonte']}\nTRECHO: {r['trecho']}"
            for r in resultados
        )

    def pesquisar_internet(query: str):
        """Busca informações recentes na internet via Tavily."""
        try:
            if internal_hermes_request and not explicit_web_request:
                return (
                    '{"error": "Bloqueado: o pedido atual e interno do Hermes. '
                    'Nao use internet como substituto para consultas do sistema."}'
                )
            tavily_key = _get_api_keys(db).get("tavily_api_key")
            if not tavily_key:
                return '{"error": "Tavily não configurado."}'
            resp = _requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "search_depth": "advanced",
                      "include_answer": True, "include_raw_content": False, "max_results": 5},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            parts = []
            if data.get("answer"):
                parts.append(f"RESPOSTA: {data['answer']}\n")
            for r in data.get("results", []):
                parts.append(f"FONTE: {r.get('title','')} ({r.get('url','')})\n{r.get('content','')}")
            return "\n\n".join(parts) or "Sem resultados."
        except Exception as e:
            return f'{{"error": "{e}"}}'

    def ler_pagina_web(url: str):
        """Lê o conteúdo de uma URL via Jina Reader."""
        try:
            resp = _requests.get(f"https://r.jina.ai/{url}",
                                 headers={"Accept": "text/markdown"}, timeout=25)
            if resp.status_code in (401, 403, 429):
                return '{"error": "Acesso bloqueado pela página de destino."}'
            resp.raise_for_status()
            content = resp.text.strip()
            return content[:12000] + "\n[truncado]" if len(content) > 12000 else content
        except Exception as e:
            return f'{{"error": "{e}"}}'

    def consultar_agenda(data_inicio: str, data_fim: str):
        """Retorna eventos ocupados no período para verificação de disponibilidade (YYYY-MM-DD)."""
        try:
            from main import get_calendar_service, get_target_calendar_id
            import hermes_calendar_tools as hc_tools
            c_service = get_calendar_service()
            # Na main.py talvez get_db e db global não funcionem direto dentro da tool, mas 'db' é capturado!
            c_id = get_target_calendar_id(db)
            if not c_service or not c_id:
                return "Google Calendar não configurado."
            events = hc_tools.consultar_eventos(c_service, c_id, data_inicio, data_fim)
            return hc_tools.formatar_eventos_para_llm(events)
        except Exception as e:
            return f"Erro ao consultar agenda: {e}"

    def encontrar_slot_livre(a_partir_de: str, duracao_min: int = 30):
        """Encontra o próximo horário livre na agenda. a_partir_de = YYYY-MM-DD. Retorna JSON com data, horario_inicio, horario_fim."""
        try:
            from main import get_calendar_service, get_target_calendar_id
            import hermes_calendar_tools as hc_tools
            c_service = get_calendar_service()
            c_id = get_target_calendar_id(db)
            if not c_service or not c_id:
                return "Erro: Google Calendar não configurado."
            slot = hc_tools.encontrar_proximo_slot(c_service, c_id, a_partir_de, duracao_min)
            if slot:
                import json as _js
                return _js.dumps(slot, ensure_ascii=False)
            return "Nenhum slot livre encontrado."
        except Exception as e:
            return f"Erro ao buscar slot livre: {e}"

    def criar_acao_no_sistema(
        titulo: str,
        descricao: str = "",
        area_tematica: str = "GERAL",
        data_limite: str = None,
        prazo_final: str = None,
        tipo_acao: str = "fast",
        tags: list[str] = None,
        notas: str = "",
        plano_acao: list[str] = None,
        horario_inicio: str = None,
        horario_fim: str = None,
        recorrencia_mensal: bool = False,
        dia_do_mes_recorrencia: int = None,
        recorrencia_semanal: bool = False,
        dias_da_semana_recorrencia: list[int] = None,
        intervalo_semanas_recorrencia: int = None,
    ):
        """
        Cria uma nova ação no Hermes. Apresente draft ao usuário antes de chamar.
        Retorna 'OK|{ID}' em caso de sucesso ou 'ERRO|{detalhe}'.
        IMPORTANTE: area_tematica deve ser EXATAMENTE UMA das áreas temáticas válidas
        listadas no contexto do sistema. Nunca invente uma nova; se nenhuma se encaixar, use 'GERAL'.
        - data_limite: DATA DE EXECUÇÃO (YYYY-MM-DD), o dia em que o trabalho deve ser feito. Não é o prazo.
        - prazo_final: PRAZO FINAL (YYYY-MM-DD), opcional — só preencha se o usuário mencionar um prazo real distinto da data de execução.
        - recorrencia_mensal: True se o usuário pedir para a ação se repetir todo mês (ex.: "todo dia 5", "mensalmente").
        - dia_do_mes_recorrencia: dia do mês (1 a 31) em que a ação deve se repetir. Obrigatório quando recorrencia_mensal=True.
        - recorrencia_semanal: True se o usuário pedir para a ação se repetir semanalmente (ex.: "todos os domingos", "toda segunda e quarta", "a cada 15 dias").
        - dias_da_semana_recorrencia: lista de dias da semana (0=domingo, 1=segunda, ..., 6=sábado). Aceita um ou mais dias. Obrigatório quando recorrencia_semanal=True.
        - intervalo_semanas_recorrencia: repetir a cada N semanas (1=toda semana, 2=quinzenal, etc.). Opcional; padrão 1.
        Use recorrencia_semanal OU recorrencia_mensal, nunca ambas.
        """
        import uuid as _uuid
        # Garante que o copiloto só use áreas temáticas existentes (fallback 'GERAL').
        area_tematica = normalizar_area_tematica(area_tematica, _areas_validas)
        now_iso = datetime.now(timezone.utc).isoformat()

        # Normalização de horários
        def normalize_hhmm(t_str: str) -> str | None:
            if not t_str:
                return None
            t_str = str(t_str).strip()
            if ":" not in t_str:
                return None
            try:
                h, m = t_str.split(":")
                return f"{int(h):02d}:{int(m):02d}"
            except:
                return t_str

        horario_inicio = normalize_hhmm(horario_inicio)
        horario_fim = normalize_hhmm(horario_fim)

        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt
        tz = ZoneInfo("America/Sao_Paulo")
        now_local = _dt.now(tz)
        today_local = now_local.strftime("%Y-%m-%d")

        if not data_limite or str(data_limite) < today_local:
            data_limite = today_local

        if prazo_final and str(prazo_final) < today_local:
            prazo_final = today_local

        if data_limite == today_local and horario_inicio:
            current_time_str = now_local.strftime("%H:%M")
            if horario_inicio < current_time_str:
                return f"ERRO|Não é possível agendar um horário anterior ao horário atual ({current_time_str}). Por favor, escolha um horário posterior."

        # Idempotência: reivindica atomicamente a chave (título, data, horário) para evitar
        # criar a mesma ação duas ou três vezes quando o modelo chama esta tool mais de uma
        # vez para o mesmo pedido (retry, lote de function calls repetido) — sintoma relatado
        # como "aparece duplicada no mesmo horário, com evento duplicado na agenda".
        from main import claim_action_dedup_slot, store_action_dedup_result
        _dedup_status, _dedup_task_id = claim_action_dedup_slot(db, titulo, data_limite, horario_inicio)
        if _dedup_status == "duplicate":
            print(f"[Core] Ação duplicada evitada: reaproveitando {_dedup_task_id} em vez de criar outra.")
            return f"OK|{_dedup_task_id}"
        if _dedup_status == "pending":
            return "ERRO|Esta ação já está sendo registrada por outra chamada. Aguarde alguns segundos e verifique a lista de ações antes de tentar de novo."

        task_id = str(_uuid.uuid4())[:20]
        # Aceita lista de strings (uso historico) ou de objetos com os campos da
        # subtarefa — `subtarefas.converter_plano` normaliza os dois.
        import subtarefas as _sub
        plano_convertido = _sub.converter_plano(plano_acao)
        try:
            from main import get_calendar_service, get_target_calendar_id
            import hermes_calendar_tools as hc_tools
            c_service = get_calendar_service()
            c_id = get_target_calendar_id(db)
            if c_service and c_id and horario_inicio and horario_fim:
                hc_tools.reagendar_acoes_hermes(db, c_service, c_id, data_limite, horario_inicio, horario_fim)
        except Exception as e:
            print(f"[Core] Erro ao reagendar iterativo: {e}")

        doc = {
            "id": task_id,
            "titulo": titulo.strip(),
            "descricao": descricao or "",
            "area_tematica": area_tematica or "GERAL",
            "data_limite": data_limite,
            "prazo_final": prazo_final,
            "horario_inicio": horario_inicio,
            "horario_fim": horario_fim,
            "tipo_acao": tipo_acao or "fast",
            "tags": tags or [],
            "notas": notas or "",
            "plano_acao": plano_convertido,
            "status": "em andamento",
            "criado_em": now_iso,
            "data_criacao": now_iso,
            "data_atualizacao": now_iso,
            "origem_ingestao": "telegram",
            "acompanhamento": [],
            "sync_status": "new",
        }
        if recorrencia_semanal and dias_da_semana_recorrencia:
            doc["recorrencia"] = {
                "ativo": True,
                "frequencia": "semanal",
                "dias_da_semana": sorted({max(0, min(6, int(d))) for d in dias_da_semana_recorrencia}),
            }
            if intervalo_semanas_recorrencia and int(intervalo_semanas_recorrencia) > 1:
                doc["recorrencia"]["intervalo_semanas"] = min(12, int(intervalo_semanas_recorrencia))
        elif recorrencia_mensal and dia_do_mes_recorrencia:
            doc["recorrencia"] = {
                "ativo": True,
                "frequencia": "mensal",
                "dia_do_mes": max(1, min(31, int(dia_do_mes_recorrencia))),
            }
        try:
            db.collection("tarefas").document(task_id).set(doc)
            store_action_dedup_result(db, titulo, data_limite, horario_inicio, task_id)
            return f"OK|{task_id}"
        except Exception as e:
            from main import release_action_dedup_slot
            release_action_dedup_slot(db, titulo, data_limite, horario_inicio)
            return f"ERRO|{e}"

    def reagendar_acoes_em_lote(
        nova_data_inicio: str,
        max_por_semana: int = 5,
        estrategia: str = "data_criacao",
        filtro_data: str = None,
        task_ids: list[str] = None,
        justificativa: str = "",
    ):
        """
        Reagenda múltiplas ações de uma vez, redistribuindo-as a partir de uma data de início.
        Executa imediatamente após confirmação do usuário.

        Parâmetros:
        - nova_data_inicio: YYYY-MM-DD — primeiro dia útil a partir do qual distribuir as ações
        - max_por_semana: máximo de ações por semana (padrão 5)
        - estrategia: "data_criacao" (padrão) | "tipo_acao" (fast primeiro) | "alfa" (alfabética)
        - filtro_data: YYYY-MM-DD — seleciona ações com data_limite igual a essa data
        - task_ids: lista explícita de IDs de tarefas (alternativa ao filtro_data)
        - justificativa: motivo gravado no diário de cada ação reagendada

        Retorna resumo textual com as ações reagendadas ou mensagem de erro.
        """
        try:
            from datetime import timedelta as _td

            if not filtro_data and not task_ids:
                return "ERRO|Forneça filtro_data (YYYY-MM-DD) ou task_ids."

            tasks = []
            if task_ids:
                for tid in (task_ids or []):
                    tdoc = db.collection('tarefas').document(str(tid)).get()
                    if tdoc.exists:
                        t = tdoc.to_dict()
                        if t.get('status') not in ('concluído', 'cancelado'):
                            tasks.append({'_id': str(tid), **t})
            else:
                q = db.collection('tarefas')\
                    .where('data_limite', '==', filtro_data)\
                    .where('status', 'in', ['em andamento', 'stand-by'])\
                    .get()
                for qdoc in q:
                    tasks.append({'_id': qdoc.id, **qdoc.to_dict()})

            if not tasks:
                return "Nenhuma ação encontrada com os critérios informados."

            if estrategia == 'tipo_acao':
                tasks.sort(key=lambda x: (0 if x.get('tipo_acao') == 'fast' else 1, x.get('data_criacao', '')))
            elif estrategia == 'alfa':
                tasks.sort(key=lambda x: x.get('titulo', '').lower())
            else:
                tasks.sort(key=lambda x: x.get('data_criacao', ''))

            try:
                start_date = datetime.strptime(nova_data_inicio, "%Y-%m-%d").date()
                today_date = datetime.now(timezone.utc).date()
                if start_date < today_date:
                    start_date = today_date
            except ValueError:
                return f"ERRO|Formato de data inválido: '{nova_data_inicio}'. Use YYYY-MM-DD."

            def _next_weekday(d):
                while d.weekday() >= 5:
                    d += _td(days=1)
                return d

            day_cursor = _next_weekday(start_date)

            batch = db.batch()
            now_iso = datetime.now(timezone.utc).isoformat()
            diary_entry = {
                'data': now_iso,
                'nota': f"[Copiloto Hermes] {justificativa or 'Reagendamento em lote.'}"
            }

            count_this_week = 0
            updated_lines = []

            for task in tasks:
                if count_this_week >= max_por_semana:
                    days_to_monday = 7 - day_cursor.weekday()
                    day_cursor += _td(days=days_to_monday)
                    day_cursor = _next_weekday(day_cursor)
                    count_this_week = 0

                nova_data_str = day_cursor.strftime("%Y-%m-%d")
                task_ref = db.collection('tarefas').document(task['_id'])
                batch.update(task_ref, {
                    'data_limite': nova_data_str,
                    'data_inicio': nova_data_str,
                    'data_atualizacao': now_iso,
                    'acompanhamento': firestore.ArrayUnion([diary_entry]),
                })
                updated_lines.append(f"• [{task.get('titulo', task['_id'])}](task:{task['_id']}) → {nova_data_str}")

                count_this_week += 1
                day_cursor += _td(days=1)
                day_cursor = _next_weekday(day_cursor)

            batch.commit()
            return f"✅ {len(updated_lines)} ações reagendadas:\n" + "\n".join(updated_lines)

        except Exception as _e:
            return f"ERRO|{_e}"

    def editar_acoes_em_lote(
        itens: list[dict],
        justificativa: str = "",
    ):
        """
        Edita múltiplas ações no sistema simultaneamente (ex.: alterar datas de execução, prazos finais, status, áreas temáticas, tags, etc.).

        Parâmetros:
        - itens: lista de dicionários contendo:
          - task_id (str): ID da tarefa a ser alterada
          - alteracoes (dict): dicionário com campos e novos valores (ex.: {"data_limite": "2026-08-25"})
        - justificativa: motivo registrado no diário de acompanhamento de cada ação
        """
        try:
            from datetime import datetime as _dt, timezone as _tz

            def _como_dict(valor):
                """Aceita dict ou JSON serializado — o schema declarado pode ter
                virado STRING no saneamento, e o modelo às vezes manda texto."""
                if isinstance(valor, dict):
                    return valor
                if isinstance(valor, str) and valor.strip():
                    try:
                        carregado = json.loads(valor)
                        return carregado if isinstance(carregado, dict) else {}
                    except Exception:
                        return {}
                return {}

            if isinstance(itens, str):
                try:
                    itens = json.loads(itens)
                except Exception:
                    return "ERRO|Não consegui ler a lista de itens. Envie uma lista com 'task_id' e 'alteracoes'."
            if isinstance(itens, dict):
                itens = [itens]
            if not itens or not isinstance(itens, list):
                return "ERRO|Forneça uma lista de itens com 'task_id' e 'alteracoes'."

            _ALLOWED = {'titulo', 'descricao', 'data_limite', 'data_inicio', 'prazo_final', 'horario_inicio', 'horario_fim', 'status', 'tags', 'area_tematica', 'tipo_acao', 'notas', 'email_link_optout'}
            today_str = _dt.now(_tz.utc).strftime("%Y-%m-%d")
            now_iso = _dt.now(_tz.utc).isoformat()
            batch = db.batch()
            count = 0
            resumo_linhas = []

            for item in itens:
                item = _como_dict(item)
                tid = str(item.get('task_id') or '').strip()
                if not tid:
                    continue
                alteracoes = _como_dict(item.get('alteracoes'))
                task_ref = db.collection('tarefas').document(tid)
                task_doc = task_ref.get()
                if not task_doc.exists:
                    continue
                task_data = task_doc.to_dict() or {}
                updates = {}
                for campo, novo_valor in alteracoes.items():
                    if campo not in _ALLOWED:
                        continue
                    if campo == 'status':
                        if novo_valor in ('concluido', 'concluida', 'finalizado'): novo_valor = 'concluído'
                        elif novo_valor in ('stand by', 'standby'): novo_valor = 'stand-by'
                        elif novo_valor in ('em andamento', 'andamento', 'aberto'): novo_valor = 'em andamento'
                        elif novo_valor in ('excluido', 'excluir', 'cancelado', 'deletar'): novo_valor = 'excluído'
                    updates[campo] = novo_valor

                if not updates:
                    continue

                if 'data_limite' in updates or 'data_inicio' in updates:
                    single_date = updates.get('data_limite') or updates.get('data_inicio') or ''
                    if single_date and single_date not in ('-', '0000-00-00') and single_date < today_str:
                        single_date = today_str
                    updates['data_limite'] = single_date
                    updates['data_inicio'] = single_date

                updates['data_atualizacao'] = now_iso
                if updates.get('status') == 'concluído':
                    updates['data_conclusao'] = now_iso
                elif updates.get('status') in ('em andamento', 'stand-by'):
                    updates['data_conclusao'] = None

                campos_desc = ', '.join(f"{k}='{v}'" for k, v in updates.items() if k not in ('data_atualizacao', 'data_conclusao'))
                diary_entry = {
                    'data': now_iso,
                    'nota': f"[Copiloto Hermes/Telegram] Edição em lote ({justificativa}). Campos alterados: {campos_desc}."
                }
                batch.update(task_ref, {
                    **updates,
                    'acompanhamento': firestore.ArrayUnion([diary_entry])
                })
                count += 1
                titulo = task_data.get('titulo', tid)
                resumo_linhas.append(f"• {titulo}: {campos_desc}")

            if count == 0:
                return "Nenhuma ação pôde ser atualizada com os dados fornecidos."

            batch.commit()
            return f"Sucesso! {count} ações atualizadas:\n" + "\n".join(resumo_linhas)
        except Exception as e:
            return f"ERRO ao editar ações em lote: {e}"

    def salvar_memoria_global(fato: str, categoria: str):
        """Persiste fato durável na memória global do Hermes. Apenas para regras estáveis e preferências permanentes."""
        try:
            import uuid as _uuid
            node_id = str(_uuid.uuid4())[:16]
            db.collection("knowledge_nodes").document(node_id).set({
                "id": node_id,
                "fato": fato,
                "categoria": categoria,
                "data_criacao": datetime.now(timezone.utc).isoformat(),
                "origem": "telegram",
            })
            return json.dumps({"status": "saved", "id": node_id}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "reason": str(e)}, ensure_ascii=False)

    def registrar_correcao_procedimento(
        area_tematica: str,
        titulo_procedimento: str,
        correcao_descrita: str,
        novo_conteudo_proposto: str,
        justificativa: str,
    ):
        """[FERRAMENTA OCULTA] Registra correção de procedimento silenciosamente."""
        try:
            import uuid as _uuid
            cid = str(_uuid.uuid4())[:12]
            db.collection("correcoes_pendentes").document(cid).set({
                "id": cid,
                "area_tematica": area_tematica,
                "titulo_procedimento": titulo_procedimento,
                "correcao_descrita": correcao_descrita,
                "novo_conteudo_proposto": novo_conteudo_proposto,
                "justificativa_usuario": justificativa,
                "status": "pendente",
                "data_criacao": firestore.SERVER_TIMESTAMP,
                "origem": "telegram",
            })
            return f"Correção registrada (ID: {cid})."
        except Exception as e:
            return f"Erro: {e}"

    def agendar_lembrete_acao(data: str, horario: str, task_id: str = None, texto: str = ""):
        """
        Agenda um lembrete para uma acao do Hermes.
        data: Data do lembrete no formato YYYY-MM-DD.
        horario: Horario do lembrete no formato HH:MM.
        task_id: ID da acao. Opcional quando ja existe uma acao em contexto.
        texto: Texto personalizado opcional que aparecera no lembrete.
        """
        from tools.telegram_extended import execute
        actual_task_id = task_id or request_acao_id or session.get("current_task_id")
        if not actual_task_id:
            return "ERRO|Nenhuma ação ativa em contexto e nenhum task_id foi informado para agendar o lembrete."
        slots = {"task_id": actual_task_id, "data": data, "horario": horario, "texto": texto}
        return execute("agendar_lembrete_acao", slots, db)

    def consultar_financas_v2(mes: int = None, ano: int = None):
        """Retorna resumo financeiro (balancete, metas, extrato). mes (0-11), ano (YYYY). Se mes for omitido, assume o mes anterior ao atual."""
        from tools.telegram_extended import execute
        return execute("consultar_financas_v2", {"mes": mes, "ano": ano}, db)

    def registrar_item_financeiro_v2(tipo: str, descricao: str, valor: float, mes: int = None, ano: int = None, data: str = None):
        """
        Registra nova renda, obrigacao_fixa ou transacao_avulsa no sistema financeiro.
        tipo: 'renda' | 'obrigacao_fixa' | 'transacao_avulsa'.
        Obrigatório apresentar rascunho completo ao usuário para confirmação antes de persistir.
        Categoria não deve ser inferida nem solicitada por enquanto; o sistema grava "Geral" internamente.
        """
        from tools.telegram_extended import execute
        slots = {"tipo": tipo, "descricao": descricao, "valor": valor, "categoria": "Geral", "mes": mes, "ano": ano, "data": data}
        return execute("registrar_item_financeiro_v2", slots, db)

    def buscar_e_analisar_email(query: str, max_results: int = 5):
        """Busca e analisa e-mails no Gmail. Use query padrão do Gmail (ex: 'from:x@y.com newer_than:2d')."""
        try:
            from tools.buscar_e_analisar_email import buscar_e_analisar_email as _fn
            return _fn(query=query, max_results=min(int(max_results), 5))
        except Exception as e:
            return f"Erro: {e}"

    def propor_acao_para_confirmacao(
        titulo: str,
        descricao: str = "",
        area_tematica: str = "GERAL",
        data_limite: str = None,
        prazo_final: str = None,
        tipo_acao: str = "fast",
        tags: list[str] = None,
        notas: str = "",
        plano_acao: list[str] = None,
        horario_inicio: str = None,
        horario_fim: str = None,
    ):
        """
        Gera uma proposta de criação de ação para o usuário confirmar via botões.
        Use esta ferramenta SEMPRE antes de criar uma ação.
        - data_limite: DATA DE EXECUÇÃO (YYYY-MM-DD), o dia em que o trabalho deve ser feito. Não é o prazo.
        - prazo_final: PRAZO FINAL (YYYY-MM-DD), opcional — só preencha se o usuário mencionar um prazo real distinto da data de execução.
        """
        # Normalização de horários
        def normalize_hhmm(t_str: str) -> str | None:
            if not t_str:
                return None
            t_str = str(t_str).strip()
            if ":" not in t_str:
                return None
            try:
                h, m = t_str.split(":")
                return f"{int(h):02d}:{int(m):02d}"
            except:
                return t_str

        horario_inicio = normalize_hhmm(horario_inicio)
        horario_fim = normalize_hhmm(horario_fim)

        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt
        tz = ZoneInfo("America/Sao_Paulo")
        now_local = _dt.now(tz)
        today_local = now_local.strftime("%Y-%m-%d")

        eff_limit = data_limite or today_local
        if eff_limit < today_local:
            eff_limit = today_local

        eff_prazo_final = prazo_final
        if eff_prazo_final and eff_prazo_final < today_local:
            eff_prazo_final = today_local

        if eff_limit == today_local and horario_inicio:
            current_time_str = now_local.strftime("%H:%M")
            if horario_inicio < current_time_str:
                return f"ERRO|Não é possível propor um horário anterior ao horário atual ({current_time_str}). Por favor, escolha um horário posterior."

        pending_data = {
            "titulo": titulo,
            "descricao": descricao,
            "area_tematica": area_tematica,
            "data_limite": eff_limit,
            "prazo_final": eff_prazo_final,
            "tipo_acao": tipo_acao,
            "tags": tags or [],
            "notas": notas,
            "plano_acao": plano_acao or [],
            "horario_inicio": horario_inicio,
            "horario_fim": horario_fim,
        }
        session.setdefault("pending_confirmations", {})["acao"] = pending_data
        session["_pending_confirm_type"] = "acao"

        draft = (
            f"📝 <b>PROPOSTA DE AÇÃO</b>\n"
            f"• Título: {titulo}\n"
            f"• Área: {area_tematica}\n"
            f"• Data de Execução: {pending_data['data_limite']}\n"
        )
        if pending_data['prazo_final']:
            draft += f"• Prazo Final: {pending_data['prazo_final']}\n"
        if tags: draft += f"• Tags: {', '.join(tags)}\n"
        if plano_acao: draft += f"• Passos: {len(plano_acao)}\n"

        return f"Proposta gerada com sucesso. Draft: {draft}\n\n[SISTEMA: Os botões de confirmação serão anexados automaticamente a esta resposta.]"

    def propor_lancamento_financeiro(tipo: str, descricao: str, valor: float, mes: int = None, ano: int = None, data: str = None):
        """
        Gera uma proposta de lançamento financeiro para o usuário confirmar via botões.
        tipo: 'renda' | 'obrigacao_fixa' | 'transacao_avulsa'.
        Categoria não deve ser inferida nem exibida por enquanto.
        """
        pending_data = {
            "tipo": tipo,
            "descricao": descricao,
            "valor": valor,
            "categoria": "Geral",
            "mes": mes,
            "ano": ano,
            "data": data
        }
        session.setdefault("pending_confirmations", {})["financeiro"] = pending_data
        session["_pending_confirm_type"] = "financeiro"

        draft = (
            f"💰 <b>PROPOSTA DE LANÇAMENTO</b>\n"
            f"• Tipo: {tipo}\n"
            f"• Descrição: {descricao}\n"
            f"• Valor: R$ {valor:.2f}\n"
        )
        return f"Proposta financeira gerada. Draft: {draft}\n\n[SISTEMA: Os botões de confirmação serão anexados automaticamente a esta resposta.]"

    def schedule_whatsapp_message(contact_number: str, message: str, scheduled_time: str) -> str:
        """
        Prepara uma mensagem de WhatsApp para confirmacao por botoes.
        O enfileiramento real acontece apenas no callback confirm_whatsapp.
        """
        pending_data = {
            "contact_number": str(contact_number or "").strip(),
            "message": str(message or "").strip(),
            "scheduled_time": str(scheduled_time or "").strip(),
        }
        session.setdefault("pending_confirmations", {})["whatsapp"] = pending_data
        session["_pending_confirm_type"] = "whatsapp"

        draft = (
            f"📲 <b>PROPOSTA DE WHATSAPP</b>\n"
            f"• Destinatário: {html.escape(pending_data['contact_number'])}\n"
            f"• Agendamento: {html.escape(pending_data['scheduled_time'])}\n"
            f"• Mensagem: {html.escape(pending_data['message'][:700])}"
        )
        return f"Proposta de WhatsApp gerada. Draft: {draft}\n\n[SISTEMA: Os botões de confirmação serão anexados automaticamente a esta resposta.]"

    # O Telegram usa closures próprias (inclusive confirmações por botões),
    # não o catálogo MCP. Reutilizar os handlers mantém a regra de negócio única.
    def ativar_modo_secretario(contatos: list[str] = None, duracao_horas: float = None) -> str:
        """Ativa o atendimento autônomo no WhatsApp para contatos autorizados.

        Args:
            contatos: Nomes, telefones ou JIDs. Omitir mantém a lista atual.
            duracao_horas: Duração em horas; 0.5 equivale a 30 minutos.
                Omitir mantém ativo até desligar manualmente.
        """
        from tools.hermes_tools import execute
        from tools.tool_context import ToolContext

        resultado = execute(
            "ativar_modo_secretario",
            {"contatos": contatos, "duracao_horas": duracao_horas},
            ToolContext(_db=db, canal="telegram"),
        )
        return json.dumps(resultado, ensure_ascii=False, default=str)

    def desativar_modo_secretario() -> str:
        """Desativa imediatamente o atendimento autônomo do Modo Secretário no WhatsApp."""
        from tools.hermes_tools import execute
        from tools.tool_context import ToolContext

        resultado = execute("desativar_modo_secretario", {}, ToolContext(_db=db, canal="telegram"))
        return json.dumps(resultado, ensure_ascii=False, default=str)

    def consultar_status_modo_secretario() -> str:
        """Consulta se o Modo Secretário está ativo, seus contatos e a expiração."""
        from tools.hermes_tools import execute
        from tools.tool_context import ToolContext

        resultado = execute("consultar_status_modo_secretario", {}, ToolContext(_db=db, canal="telegram"))
        return json.dumps(resultado, ensure_ascii=False, default=str)

    tools_list = [

        consultar_historico_acoes,
        buscar_arquivos_acervo,
        pesquisar_internet,
        ler_pagina_web,
        consultar_agenda,
        encontrar_slot_livre,
        criar_acao_no_sistema,
        reagendar_acoes_em_lote,
        editar_acoes_em_lote,
        salvar_memoria_global,
        registrar_correcao_procedimento,
        buscar_e_analisar_email,
        consultar_financas_v2,
        registrar_item_financeiro_v2,
        propor_acao_para_confirmacao,
        propor_lancamento_financeiro,
        schedule_whatsapp_message,
        agendar_lembrete_acao,
        ativar_modo_secretario,
        desativar_modo_secretario,
        consultar_status_modo_secretario,
    ]

    # function_map não é recalculado aqui: quem chama (telegram_handlers_core.py)
    # já faz `function_map = {fn.__name__: fn for fn in tools_list}` a partir do
    # retorno desta função (mesmo dict que o código original computava inline).
    return tools_list
