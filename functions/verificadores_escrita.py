"""Verificadores por releitura das ferramentas de escrita (copiloto web, Telegram e MCP).

Cada verificador recebe (db, args, resultado) depois que a ferramenta rodou,
descobre pelo retorno ou pelos argumentos qual documento ela diz ter gravado,
relê esse documento e devolve um `verificacao.ResultadoOperacao`. Retorno de
erro da própria ferramenta vira `falhou`; "nada mudou" também, porque nada foi
gravado. Formatos de retorno levantados no código em 01/10/2026.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from subtarefas import resumo_valor
from verificacao import ResultadoOperacao

PROPOSTAS = frozenset({
    "propor_acao_para_confirmacao", "propor_lancamento_financeiro", "schedule_whatsapp_message",
    "preparar_edicao_acao", "preparar_edicao_em_lote", "preparar_reagendamento_em_lote",
    "preparar_remocao_horarios_em_lote", "preparar_vinculo_contatos", "preparar_atualizacao_contato",
    "gerar_rascunho_formulario", "criar_rascunho_whatsapp", "criar_rascunho_email",
})

_COLECAO_FINANCEIRA = {"renda": "income_entries", "obrigacao_fixa": "fixed_bills",
                       "transacao_avulsa": "finance_transactions"}


# --- utilitários ---------------------------------------------------------------

def _ok(nome, alvo, relido=None, esperado=None):
    return ResultadoOperacao("verificado", nome, alvo, valor_esperado=esperado, valor_relido=relido)


def _falhou(nome, alvo, motivo, relido=None):
    return ResultadoOperacao("falhou", nome, alvo, valor_relido=relido, motivo=motivo)


def _resumo(resultado, limite=200) -> str:
    texto = resultado if isinstance(resultado, str) else json.dumps(resultado, ensure_ascii=False, default=str)
    texto = re.sub(r"^ERRO\|", "", (texto or "").strip())
    return (texto[:limite] + "…") if len(texto) > limite else (texto or "retorno vazio")


def _erro_da_ferramenta(nome, resultado):
    return _falhou(nome, "?", f"a ferramenta respondeu com erro: {_resumo(resultado)}. Nada foi confirmado.")


def _json(resultado):
    if isinstance(resultado, dict):
        return resultado
    texto = (resultado or "").strip() if isinstance(resultado, str) else ""
    if texto.startswith("{"):
        try:
            dados = json.loads(texto)
            return dados if isinstance(dados, dict) else None
        except ValueError:
            return None
    return None


def _texto(resultado) -> str:
    return resultado if isinstance(resultado, str) else json.dumps(resultado or {}, ensure_ascii=False, default=str)


def _doc(db, colecao, doc_id):
    if not doc_id:
        return None
    snap = db.collection(colecao).document(str(doc_id)).get()
    return (snap.to_dict() or {}) if snap.exists else None


def _norm(valor) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto).strip().casefold()


def _ausente(nome, alvo):
    return _falhou(nome, alvo, "o registro não aparece ao reler o banco. Nada foi confirmado.")


def _confere(nome, alvo, doc, esperado: dict):
    """Compara campos (texto normalizado; números com tolerância)."""
    if doc is None:
        return _ausente(nome, alvo)
    relido = {c: doc.get(c) for c in esperado}
    for campo, valor in esperado.items():
        atual = relido[campo]
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            try:
                igual = abs(float(atual) - float(valor)) <= 1e-6
            except (TypeError, ValueError):
                igual = False
        elif isinstance(valor, bool):
            igual = atual is valor
        else:
            igual = _norm(atual) == _norm(valor)
        if not igual:
            return _falhou(nome, alvo, f"o valor gravado não confere ({campo} relido {atual!r}, esperado {valor!r})",
                           relido)
    return _ok(nome, alvo, relido, esperado)


def _ok_pipe(resultado):
    texto = _texto(resultado).strip()
    if not texto.startswith("OK|"):
        return None
    return texto[3:].split("\n", 1)[0].split("|")


def _arg(args, *nomes):
    for nome in nomes:
        if args.get(nome) not in (None, ""):
            return args[nome]
    return None


def _recente(valor, minutos=15) -> bool:
    try:
        if hasattr(valor, "timestamp"):
            momento = datetime.fromtimestamp(valor.timestamp(), timezone.utc)
        else:
            momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
            if momento.tzinfo is None:
                momento = momento.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OSError):
        return False
    return datetime.now(timezone.utc) - momento <= timedelta(minutes=minutos)


# --- ações (tarefas) ---------------------------------------------------------------

def criar_acao(db, args, resultado):
    partes = _ok_pipe(resultado)
    if not partes or not partes[0].strip():
        return _erro_da_ferramenta("criar_acao_no_sistema", resultado)
    task_id = partes[0].strip()
    esperado = {"titulo": args["titulo"]} if _arg(args, "titulo") else {}
    return _confere("criar_acao_no_sistema", f"tarefas/{task_id}", _doc(db, "tarefas", task_id), esperado)


def registrar_no_diario(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") != "ok" or not dados.get("task_id"):
        return _erro_da_ferramenta("registrar_no_diario", resultado)
    alvo = f"tarefas/{dados['task_id']}"
    doc = _doc(db, "tarefas", dados["task_id"])
    if doc is None:
        return _ausente("registrar_no_diario", alvo)
    nota = _norm(_arg(args, "nota"))
    notas = [_norm((item or {}).get("nota")) for item in (doc.get("acompanhamento") or []) if isinstance(item, dict)]
    if nota and nota not in notas:
        return _falhou("registrar_no_diario", alvo, "a nota não aparece no diário da ação ao reler o banco.")
    return _ok("registrar_no_diario", alvo, {"nota": _arg(args, "nota")})


def _etapas(doc):
    return {str(e.get("id")): e for e in (doc.get("plano_acao") or []) if isinstance(e, dict) and e.get("id")}


def editar_plano(db, args, resultado, nome="editar_plano_acao"):
    texto = _texto(resultado).strip()
    if texto.startswith("AVISO|") or texto.startswith("OK|Nenhuma etapa mudou"):
        return _falhou(nome, f"tarefas/{_arg(args, 'task_id')}",
                       "nenhuma etapa foi gravada: os valores enviados já eram os atuais.")
    partes = _ok_pipe(resultado)
    if partes is None:
        return _erro_da_ferramenta(nome, resultado)
    try:
        diff = json.loads("|".join(partes))
    except ValueError:
        return _erro_da_ferramenta(nome, resultado)
    task_id = _arg(args, "task_id")
    alvo = f"tarefas/{task_id}"
    doc = _doc(db, "tarefas", task_id)
    if doc is None:
        return _ausente(nome, alvo)
    etapas = _etapas(doc)
    for etapa_id, campos in (diff.get("alteradas") or {}).items():
        etapa = etapas.get(str(etapa_id))
        if etapa is None:
            return _falhou(nome, alvo, f"a etapa {etapa_id} não aparece no plano ao reler o banco.")
        for campo, par in (campos or {}).items():
            depois = par[1] if isinstance(par, (list, tuple)) and len(par) == 2 else par
            atual = etapa.get(campo)
            if (atual in (None, "") and depois in (None, "")) or _norm(atual) == _norm(depois):
                continue
            # O diff resume texto longo (77 caracteres + "..."): compara resumo com resumo.
            if _norm(resumo_valor(atual)) == _norm(depois):
                continue
            return _falhou(nome, alvo, f"a etapa {etapa_id} ficou com {campo}={atual!r}, esperado {depois!r}.")
    for etapa_id in diff.get("adicionadas") or []:
        if str(etapa_id) not in etapas:
            return _falhou(nome, alvo, f"a etapa nova {etapa_id} não aparece no plano ao reler o banco.")
    for etapa_id in diff.get("removidas") or []:
        if str(etapa_id) in etapas:
            return _falhou(nome, alvo, f"a etapa {etapa_id} ainda está no plano ao reler o banco.")
    return _ok(nome, alvo, {"etapas": len(etapas)})


def editar_etapa(db, args, resultado):
    return editar_plano(db, args, resultado, nome="editar_etapa")


def agendar_lembrete(db, args, resultado):
    partes = _ok_pipe(resultado)
    if not partes or len(partes) < 2:
        return _erro_da_ferramenta("agendar_lembrete_acao", resultado)
    task_id, quando = partes[0].strip(), partes[1].strip()
    alvo = f"tarefas/{task_id}"
    doc = _doc(db, "tarefas", task_id)
    if doc is None:
        return _ausente("agendar_lembrete_acao", alvo)
    if not any(str((r or {}).get("reminder_at")) == quando for r in (doc.get("reminders") or [])):
        return _falhou("agendar_lembrete_acao", alvo, f"o lembrete de {quando} não aparece na ação ao reler o banco.")
    return _ok("agendar_lembrete_acao", alvo, {"reminder_at": quando})


_CAMPOS_COMPARAVEIS = ("titulo", "descricao", "notas", "projeto", "prazo_final", "horario_inicio", "horario_fim")


def editar_acao(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") != "completed":
        return _erro_da_ferramenta("editar_acao", resultado)
    task_id = _arg(args, "task_id")
    alvo = f"tarefas/{task_id}"
    doc = _doc(db, "tarefas", task_id)
    if doc is None:
        return _ausente("editar_acao", alvo)
    pedidos = dict(args.get("alteracoes") or {})
    pedidos.update({k: v for k, v in args.items() if k in _CAMPOS_COMPARAVEIS})
    alterados = dados.get("campos_alterados") or []
    for campo in alterados:
        if campo not in doc:
            return _falhou("editar_acao", alvo, f"o campo {campo} não aparece na ação ao reler o banco.")
    esperado = {c: pedidos[c] for c in alterados if c in _CAMPOS_COMPARAVEIS and c in pedidos
                and not isinstance(pedidos[c], dict)}
    return _confere("editar_acao", alvo, doc, esperado) if esperado else _ok(
        "editar_acao", alvo, {c: doc.get(c) for c in alterados})


def _itens_lote(args):
    itens = args.get("itens") or []
    if isinstance(itens, str):
        try:
            itens = json.loads(itens)
        except ValueError:
            itens = []
    return [i for i in itens if isinstance(i, dict) and i.get("task_id")]


def editar_acoes_em_lote(db, args, resultado):
    itens = _itens_lote(args)
    dados = _json(resultado)
    if dados is not None:
        if dados.get("status") != "completed":
            return _erro_da_ferramenta("editar_acoes_em_lote", resultado)
        aplicadas = int(dados.get("count") or 0)
    else:
        m = re.match(r"\s*Sucesso! (\d+) aç", _texto(resultado))
        if not m:
            return _erro_da_ferramenta("editar_acoes_em_lote", resultado)
        aplicadas = int(m.group(1))
    alvo = f"tarefas ({len(itens)} ações)"
    ausentes = [i["task_id"] for i in itens if _doc(db, "tarefas", i["task_id"]) is None]
    if ausentes:
        return _falhou("editar_acoes_em_lote", alvo, f"ações não encontradas ao reler: {', '.join(ausentes[:5])}.")
    if itens and aplicadas < len(itens):
        return _falhou("editar_acoes_em_lote", alvo,
                       f"só {aplicadas} de {len(itens)} ações foram atualizadas; as outras foram puladas.")
    return _ok("editar_acoes_em_lote", alvo, {"aplicadas": aplicadas})


def reagendar_acoes_em_lote(db, args, resultado):
    texto = _texto(resultado)
    pares = re.findall(r"\(task:([^)]+)\)\s*→\s*(\d{4}-\d{2}-\d{2})", texto)
    if pares:
        for task_id, data in pares:
            doc = _doc(db, "tarefas", task_id.strip())
            if doc is None:
                return _ausente("reagendar_acoes_em_lote", f"tarefas/{task_id}")
            if str(doc.get("data_limite") or "")[:10] != data:
                return _falhou("reagendar_acoes_em_lote", f"tarefas/{task_id}",
                               f"a ação ficou com data {doc.get('data_limite')!r}, esperado {data}.")
        return _ok("reagendar_acoes_em_lote", f"tarefas ({len(pares)} ações)", {"reagendadas": len(pares)})
    dados = _json(resultado)
    if not dados or dados.get("status") != "completed":
        return _erro_da_ferramenta("reagendar_acoes_em_lote", resultado)
    ids = [str(t) for t in (args.get("task_ids") or [])]
    if not ids:
        return None
    nao_tocadas = [t for t in ids if not _recente((_doc(db, "tarefas", t) or {}).get("data_atualizacao"))]
    if nao_tocadas:
        return _falhou("reagendar_acoes_em_lote", f"tarefas ({len(ids)} ações)",
                       f"ações sem atualização recente ao reler: {', '.join(nao_tocadas[:5])}.")
    return _ok("reagendar_acoes_em_lote", f"tarefas ({len(ids)} ações)", {"reagendadas": len(ids)})


# --- memória, POPs, personalidade e procedimentos --------------------------------

def salvar_memoria(db, args, resultado):
    dados = _json(resultado)
    if not dados:
        return _erro_da_ferramenta("salvar_memoria_global", resultado)
    status = dados.get("status")
    memoria_id = dados.get("memory_id") or dados.get("id")
    alvo = f"knowledge_nodes/{memoria_id}"
    if status == "conflict":
        return ResultadoOperacao("pendente", "salvar_memoria_global", alvo)
    if status == "ignored" and dados.get("reason") == "duplicate":
        return _ok("salvar_memoria_global", alvo) if _doc(db, "knowledge_nodes", memoria_id) else _ausente(
            "salvar_memoria_global", alvo)
    if status != "saved":
        return _falhou("salvar_memoria_global", alvo, f"a memória não foi gravada ({dados.get('reason') or status}).")
    doc = _doc(db, "knowledge_nodes", memoria_id)
    if doc is None:
        return _ausente("salvar_memoria_global", alvo)
    fato = _arg(args, "fato")
    gravado = doc.get("texto_memoria") or doc.get("fato")
    if fato and _norm(gravado) != _norm(fato):
        return _falhou("salvar_memoria_global", alvo, "o texto gravado não confere com o fato enviado.")
    return _ok("salvar_memoria_global", alvo, {"texto": gravado})


def salvar_pop(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") not in ("saved", "updated"):
        return _erro_da_ferramenta("salvar_pop_global", resultado)
    alvo = f"pops_diretrizes/{dados.get('pop_id')}"
    instrucao = _arg(args, "instrucao_sistema", "instrucao", "conteudo")
    esperado = {"instrucao_sistema": instrucao} if instrucao else {}
    return _confere("salvar_pop_global", alvo, _doc(db, "pops_diretrizes", dados.get("pop_id")), esperado)


def resolver_conflito_memoria(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") not in ("resolved", "updated"):
        return _erro_da_ferramenta("resolver_conflito_memoria", resultado)
    memoria_id = dados.get("memory_id") or _arg(args, "memoria_id")
    alvo = f"knowledge_nodes/{memoria_id}"
    doc = _doc(db, "knowledge_nodes", memoria_id)
    if dados["status"] == "updated":
        return _confere("resolver_conflito_memoria", alvo, doc,
                        {"texto_memoria": _arg(args, "fato_atualizado")} if _arg(args, "fato_atualizado") else {})
    return _confere("resolver_conflito_memoria", alvo, doc, {"ultima_decisao_humana": "manter_existente"})


def atualizar_personalidade(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") != "updated":
        return _erro_da_ferramenta("atualizar_personalidade", resultado)
    return _confere("atualizar_personalidade", "system/copilot_soul", _doc(db, "system", "copilot_soul"),
                    {"content": str(_arg(args, "nova_personalidade") or "").strip()})


def resolver_conflito_procedimento(db, args, resultado):
    if not args.get("confirmar_contrato"):
        return ResultadoOperacao("pendente", "resolver_conflito_procedimento", "proposta")
    m = re.search(r"Novo documento criado:\s*`([^`]+)`", _texto(resultado))
    if not m:
        return _erro_da_ferramenta("resolver_conflito_procedimento", resultado)
    return _confere("resolver_conflito_procedimento", f"conhecimento_mestre/{m.group(1)}",
                    _doc(db, "conhecimento_mestre", m.group(1)), {"status": "ativo"})


def registrar_correcao(db, args, resultado):
    m = re.search(r"\(ID:\s*([A-Za-z0-9_-]+)\)", _texto(resultado))
    if not m:
        return _erro_da_ferramenta("registrar_correcao_procedimento", resultado)
    alvo = f"correcoes_pendentes/{m.group(1)}"
    doc = _doc(db, "correcoes_pendentes", m.group(1))
    return _ok("registrar_correcao_procedimento", alvo) if doc is not None else _ausente(
        "registrar_correcao_procedimento", alvo)


# --- estratégia pessoal ----------------------------------------------------------

def criar_objetivo(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") != "created":
        return _erro_da_ferramenta("criar_objetivo_estrategico", resultado)
    return _confere("criar_objetivo_estrategico", f"estrategia_pessoal/{dados.get('objetivo_id')}",
                    _doc(db, "estrategia_pessoal", dados.get("objetivo_id")),
                    {"objetivoMacro": args["objetivoMacro"]} if _arg(args, "objetivoMacro") else {})


def editar_objetivo(db, args, resultado):
    dados = _json(resultado)
    alvo = f"estrategia_pessoal/{_arg(args, 'objetivo_id')}"
    if dados and dados.get("status") == "noop":
        return _falhou("editar_objetivo_estrategico", alvo, "nenhum campo foi alterado.")
    if not dados or dados.get("status") != "updated":
        return _erro_da_ferramenta("editar_objetivo_estrategico", resultado)
    doc = _doc(db, "estrategia_pessoal", _arg(args, "objetivo_id"))
    esperado = {"objetivoMacro": args["objetivoMacro"]} if "objetivoMacro" in (dados.get("campos_alterados") or []) \
        and _arg(args, "objetivoMacro") else {}
    return _confere("editar_objetivo_estrategico", alvo, doc, esperado)


def gerenciar_item_estrategico(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") != "ok":
        return _erro_da_ferramenta("gerenciar_item_estrategico", resultado)
    alvo = f"estrategia_pessoal/{dados.get('objetivo_id')}"
    doc = _doc(db, "estrategia_pessoal", dados.get("objetivo_id"))
    if doc is None:
        return _ausente("gerenciar_item_estrategico", alvo)
    lista = doc.get("marcos" if dados.get("tipo") == "marco" else "indicadoresSucesso") or []
    item = next((i for i in lista if isinstance(i, dict) and str(i.get("id")) == str(dados.get("item_id"))), None)
    acao = dados.get("acao")
    if acao == "remover":
        return _ok("gerenciar_item_estrategico", alvo) if item is None else _falhou(
            "gerenciar_item_estrategico", alvo, "o item ainda aparece ao reler o banco.")
    if item is None:
        return _falhou("gerenciar_item_estrategico", alvo, "o item não aparece ao reler o banco.")
    if acao == "concluir" and item.get("concluido") is not True:
        return _falhou("gerenciar_item_estrategico", alvo, "o item não ficou concluído ao reler o banco.")
    return _ok("gerenciar_item_estrategico", alvo, {"item_id": item.get("id")})


def excluir_objetivo(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") != "deleted":
        return _erro_da_ferramenta("excluir_objetivo_estrategico", resultado)
    alvo = f"estrategia_pessoal/{dados.get('objetivo_id')}"
    if _doc(db, "estrategia_pessoal", dados.get("objetivo_id")) is not None:
        return _falhou("excluir_objetivo_estrategico", alvo, "o objetivo ainda existe ao reler o banco.")
    return _ok("excluir_objetivo_estrategico", alvo)


# --- finanças, contatos, saúde, mídia, SIPAC, WhatsApp, secretário -----------------

def registrar_item_financeiro(db, args, resultado):
    dados = _json(re.sub(r"^ERRO\|", "", _texto(resultado).strip()))
    if not dados or dados.get("success") is not True:
        return _erro_da_ferramenta("registrar_item_financeiro_v2", resultado)
    colecao = _COLECAO_FINANCEIRA.get(dados.get("tipo"))
    alvo = f"{colecao}/{dados.get('id')}"
    if colecao is None:
        return _falhou("registrar_item_financeiro_v2", alvo, f"tipo desconhecido: {dados.get('tipo')!r}.")
    esperado = {}
    if _arg(args, "valor") is not None:
        try:
            esperado["amount"] = float(str(args["valor"]).replace(",", "."))
        except ValueError:
            pass
    return _confere("registrar_item_financeiro_v2", alvo, _doc(db, colecao, dados.get("id")), esperado)


def registrar_interacao(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") != "ok":
        return _erro_da_ferramenta("registrar_interacao_contato", resultado)
    return _confere("registrar_interacao_contato", f"interacoes_pessoas/{dados.get('interacao_id')}",
                    _doc(db, "interacoes_pessoas", dados.get("interacao_id")),
                    {"pessoa_id": args["pessoa_id"]} if _arg(args, "pessoa_id") else {})


def registrar_peso(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("estado") not in ("verificado", "falhou", "pendente"):
        return _erro_da_ferramenta("registrar_peso", resultado)
    campos = ("estado", "operacao", "alvo", "valor_esperado", "valor_relido", "motivo", "run_id")
    return ResultadoOperacao(**{c: dados.get(c) for c in campos})


def registrar_saude(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") != "completed":
        return _erro_da_ferramenta("registrar_saude", resultado)
    dia = dados.get("data")
    for campo, colecao, chave in (("peso", "health_weights", "weight"), ("cintura", "health_waist", "cm")):
        if campo in (dados.get("campos_alterados") or []):
            docs = list(db.collection(colecao).where("date", "==", dia).limit(1).stream())
            gravado = (docs[0].to_dict() or {}).get(chave) if docs else None
            try:
                igual = gravado is not None and abs(float(gravado) - float(str(args[campo]).replace(",", "."))) <= 1e-6
            except (KeyError, TypeError, ValueError):
                igual = False
            if not igual:
                return _falhou("registrar_saude", f"{colecao} ({dia})",
                               f"{campo} relido {gravado!r} não confere com o enviado.")
    resto = [c for c in (dados.get("campos_alterados") or []) if c not in ("peso", "cintura")]
    if resto and _doc(db, "health_exercise_logs", dia) is None:
        return _ausente("registrar_saude", f"health_exercise_logs/{dia}")
    return _ok("registrar_saude", f"saúde ({dia})", {"campos": dados.get("campos_alterados")})


def gerar_imagem(db, args, resultado):
    dados = _json(resultado)
    if dados and dados.get("status") == "processing":
        return ResultadoOperacao("pendente", "gerar_imagem", f"mcp_jobs/{dados.get('job_id')}")
    m = re.search(r"imagens_geradas(?:%2F|/)\d{4}-\d{2}(?:%2F|/)([0-9a-f]{6,})", _texto(resultado))
    if not m:
        return _erro_da_ferramenta("gerar_imagem", resultado)
    alvo = f"imagens_geradas/{m.group(1)}"
    return _ok("gerar_imagem", alvo) if _doc(db, "imagens_geradas", m.group(1)) is not None else _ausente(
        "gerar_imagem", alvo)


def gerar_relatorio(db, args, resultado):
    dados = _json(resultado)
    if dados and dados.get("status") == "processing":
        return ResultadoOperacao("pendente", "gerar_relatorio", f"mcp_jobs/{dados.get('job_id')}")
    if not dados or not dados.get("report_id"):
        return _erro_da_ferramenta("gerar_relatorio", resultado)
    alvo = f"relatorios/{dados['report_id']}"
    return _ok("gerar_relatorio", alvo) if _doc(db, "relatorios", dados["report_id"]) is not None else _ausente(
        "gerar_relatorio", alvo)


def incorporar_documento_sipac(db, args, resultado):
    texto = _texto(resultado)
    m = re.search(r"\]\(([^)]+)\)\.?\s*$", texto.strip())
    if not texto.startswith("Sucesso") or not m:
        return _erro_da_ferramenta("incorporar_documento_especifico_sipac_no_rag_da_acao", resultado)
    task_id = m.group(1)
    alvo = f"tarefas/{task_id}"
    doc = _doc(db, "tarefas", task_id)
    if doc is None:
        return _ausente("incorporar_documento_especifico_sipac_no_rag_da_acao", alvo)
    marca = f"seq #{args.get('sequencial')}".casefold()
    if not any(marca in str((i or {}).get("nome", "")).casefold() for i in (doc.get("pool_dados") or [])):
        return _falhou("incorporar_documento_especifico_sipac_no_rag_da_acao", alvo,
                       "o documento não aparece nos anexos da ação ao reler o banco.")
    return _ok("incorporar_documento_especifico_sipac_no_rag_da_acao", alvo)


def acompanhar_sipac(db, args, resultado):
    texto = _texto(resultado)
    if not texto.startswith("Sucesso"):
        return _erro_da_ferramenta("acompanhar_processo_sipac", resultado)
    numero = str(_arg(args, "numero_processo") or "")
    docs = list(db.collection("sipac_processos").where("numeroProcesso", "==", numero).limit(5).stream())
    esperado = bool(args.get("acompanhar", True))
    if not any((d.to_dict() or {}).get("acompanhar") is esperado for d in docs):
        return _falhou("acompanhar_processo_sipac", f"sipac_processos ({numero})",
                       "o acompanhamento não aparece com esse estado ao reler o banco.")
    return _ok("acompanhar_processo_sipac", f"sipac_processos ({numero})", {"acompanhar": esperado})


def cancelar_envio(db, args, resultado):
    dados = _json(resultado)
    if not dados or dados.get("status") not in ("ok", "already_canceled"):
        return _erro_da_ferramenta("cancelar_envio_whatsapp", resultado)
    outbox_id = dados.get("outbox_id") or _arg(args, "job_id")
    return _confere("cancelar_envio_whatsapp", f"whatsapp_outbox/{outbox_id}",
                    _doc(db, "whatsapp_outbox", outbox_id), {"status": "canceled"})


def _secretario(ligado: bool, nome: str):
    def verificar(db, args, resultado):
        dados = _json(resultado)
        if not dados or dados.get("success") is not True:
            return _erro_da_ferramenta(nome, resultado)
        settings = _doc(db, "system", "settings") or {}
        atual = (settings.get("whatsapp_secretario") or {}).get("enabled")
        if atual is not ligado:
            return _falhou(nome, "system/settings", f"o modo secretário ficou enabled={atual!r} ao reler o banco.")
        return _ok(nome, "system/settings", {"enabled": atual})
    return verificar


VERIFICADORES = {
    "criar_acao_no_sistema": criar_acao,
    "registrar_no_diario": registrar_no_diario,
    "editar_plano_acao": editar_plano,
    "editar_etapa": editar_etapa,
    "agendar_lembrete_acao": agendar_lembrete,
    "editar_acao": editar_acao,
    "editar_acoes_em_lote": editar_acoes_em_lote,
    "reagendar_acoes_em_lote": reagendar_acoes_em_lote,
    "salvar_memoria_global": salvar_memoria,
    "salvar_pop_global": salvar_pop,
    "resolver_conflito_memoria": resolver_conflito_memoria,
    "atualizar_personalidade": atualizar_personalidade,
    "resolver_conflito_procedimento": resolver_conflito_procedimento,
    "registrar_correcao_procedimento": registrar_correcao,
    "criar_objetivo_estrategico": criar_objetivo,
    "editar_objetivo_estrategico": editar_objetivo,
    "gerenciar_item_estrategico": gerenciar_item_estrategico,
    "excluir_objetivo_estrategico": excluir_objetivo,
    "registrar_item_financeiro_v2": registrar_item_financeiro,
    "registrar_interacao_contato": registrar_interacao,
    "registrar_peso": registrar_peso,
    "registrar_saude": registrar_saude,
    "gerar_imagem": gerar_imagem,
    "gerar_relatorio": gerar_relatorio,
    "incorporar_documento_especifico_sipac_no_rag_da_acao": incorporar_documento_sipac,
    "acompanhar_processo_sipac": acompanhar_sipac,
    "acompanhar_processo_sipac_copiloto": acompanhar_sipac,
    "cancelar_envio_whatsapp": cancelar_envio,
    "ativar_modo_secretario": _secretario(True, "ativar_modo_secretario"),
    "desativar_modo_secretario": _secretario(False, "desativar_modo_secretario"),
}
