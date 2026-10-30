"""
CRUD de objetivos estratégicos pessoais (`estrategia_pessoal`), compartilhado
no Copiloto padrão (main.py, ferramentas do `copilot_mode == 'estrategia'`) —
mesmo padrão de extração já usado para finanças
(`tools/telegram_extended.py`).

Todas as funções operam sobre `db` e exigem `user_uid` (fail-closed: só
enxergam/alteram objetivos cujo `userId` bate exatamente com o chamador).
"""
import time
import uuid
from datetime import datetime, timezone

from firebase_admin import firestore

from bolso_aquisicoes import numero
from perfil_estrategia import FONTES, SENTIDOS, dia, hoje_brasilia, id_legado

# Unidade de meta de saúde -> fonte automática que a alimenta (as mesmas do resumo matinal).
_UNIDADES_FONTE = {"kg": "peso", "quilo": "peso", "quilos": "peso",
                   "cm": "cintura", "centimetro": "cintura", "centimetros": "cintura"}

PILARES = {'carreira', 'financas', 'saude', 'intelectual', 'estilo_vida'}
# `pausada` (30/10/2026): sai de "paradas", das sugestões de vínculo e de elevação e do
# check-in, até `dataRetomada`; a fila de atenção avisa quando a data chega.
STATUS_VALUES = {'ativo', 'concluido', 'revisar', 'pausada'}
TIPOS = {'absoluta', 'relativa_qualitativa'}
COLECAO_HISTORICO = 'estrategia_historico'
_CAMPOS_PERFIL = ('ciclo', 'linhaBase', 'indicadores')


def registrar_historico(destino, db, user_uid: str, objetivo_id: str, operacao: str,
                        antes: dict, depois: dict, origem: str = "mcp") -> None:
    """Antes e depois de toda mudança da estratégia, para reverter sem depender do diário.

    `destino` é a transação em curso (grava junto, ou nada) ou None (grava direto).
    Sentinelas do Firestore (DELETE_FIELD, SERVER_TIMESTAMP) viram None no registro.
    """
    def _limpo(valor):
        if isinstance(valor, dict):
            return {k: _limpo(v) for k, v in valor.items()}
        if isinstance(valor, list):
            return [_limpo(v) for v in valor]
        if isinstance(valor, (str, int, float, bool, type(None))):
            return valor
        # Datas (datetime, Timestamp do Firestore) viram texto, para o histórico reconstruir o documento.
        return valor.isoformat() if hasattr(valor, "isoformat") else None

    registro = {"objetivo_id": objetivo_id, "userId": user_uid, "origem": origem, "operacao": operacao,
                "antes": _limpo(antes), "depois": _limpo(depois),
                "em": firestore.SERVER_TIMESTAMP, "em_iso": datetime.now(timezone.utc).isoformat()}
    ref = db.collection(COLECAO_HISTORICO).document()
    if destino is not None:
        destino.set(ref, registro)
    else:
        ref.set(registro)


def _validar_ciclo(valor):
    if not isinstance(valor, dict):
        return None, "ciclo_invalido"
    inicio, fim = dia(valor.get("inicio")), dia(valor.get("fim"))
    if not inicio or not fim or fim <= inicio:
        return None, "ciclo_invalido"
    return {"inicio": inicio.isoformat(), "fim": fim.isoformat()}, None


def _validar_linha_base(valor):
    if not isinstance(valor, dict) or not dia(valor.get("data")):
        return None, "linhaBase_invalida"
    valores, erro = _esperado(valor.get("valores") or {})
    if erro:
        return None, "linhaBase_invalida"
    return {"data": dia(valor["data"]).isoformat(), "valores": valores}, None


def _validar_indicadores(valor):
    if not isinstance(valor, list):
        return None, "indicadores_invalidos"
    limpos, chaves = [], set()
    for ind in valor:
        if not isinstance(ind, dict):
            return None, "indicadores_invalidos"
        chave = str(ind.get("chave") or "").strip()
        if not chave or chave in chaves or ind.get("sentido") not in SENTIDOS or ind.get("fonte") not in FONTES:
            return None, "indicadores_invalidos"
        chaves.add(chave)
        limpo = {"chave": chave, "rotulo": str(ind.get("rotulo") or chave).strip(),
                 "unidade": str(ind.get("unidade") or "").strip(), "sentido": ind["sentido"], "fonte": ind["fonte"]}
        for campo in ("inicial", "alvoFinal"):
            if ind.get(campo) is not None:
                n = numero(ind[campo], None)
                if n is None or isinstance(ind[campo], bool):
                    return None, "indicadores_invalidos"
                limpo[campo] = n
        limpos.append(limpo)
    return limpos, None

# Fontes que o proprio sistema ja alimenta. Uma meta numerica ligada a uma delas
# le o valor de la em vez de depender de alguem lembrar de atualizar `valorAtual`.
FONTES_METRICA = {'peso', 'cintura'}


def _fonte_valida(fonte) -> str:
    """Nome de fonte reconhecida, ou vazio.

    Vazio significa "sem fonte automatica" — e o painel diz isso em vez de exibir
    zero, porque zero afirma "nao andou nada" e nao "ninguem esta medindo".
    """
    limpa = str(fonte or "").strip().lower()
    return limpa if limpa in FONTES_METRICA else ""


def novo_id_estrategia(prefixo: str) -> str:
    return f"{prefixo}-{int(time.time() * 1000)}-{str(uuid.uuid4())[:6]}"


def carregar_objetivo_estrategico(db, user_uid: str | None, objetivo_id: str):
    """Carrega um objetivo garantindo posse pelo usuário atual. Retorna (ref, data) ou (None, None).
    Fail-closed: exige usuário autenticado e que o userId do documento bata exatamente."""
    if not user_uid or not objetivo_id:
        return None, None
    ref = db.collection('estrategia_pessoal').document(str(objetivo_id))
    snap = ref.get()
    if not snap.exists:
        return None, None
    data = snap.to_dict() or {}
    if data.get('userId') != user_uid:
        return None, None
    return ref, data


def criar_objetivo_estrategico(
    db,
    user_uid: str | None,
    objetivoMacro: str,
    pilar: str = "carreira",
    tipoMeta: str = "relativa_qualitativa",
    status: str = "ativo",
    diretrizes: list[str] | None = None,
    indicadores: list[str] | None = None,
    marcos: list[str] | None = None,
    metrica_valor_inicial: float | None = None,
    metrica_valor_atual: float | None = None,
    metrica_valor_objetivo: float | None = None,
    metrica_unidade: str = "",
    metrica_fonte: str = "",
    gerida_por_acoes: bool | None = None,
) -> dict:
    if not user_uid:
        return {"status": "error", "reason": "auth_required"}
    titulo = (objetivoMacro or "").strip()
    if not titulo:
        return {"status": "error", "reason": "objetivoMacro_obrigatorio"}
    pilar_norm = (pilar or "carreira").strip().lower()
    if pilar_norm not in PILARES:
        pilar_norm = "carreira"
    tipo_norm = (tipoMeta or "relativa_qualitativa").strip().lower()
    if tipo_norm not in TIPOS:
        tipo_norm = "relativa_qualitativa"
    status_norm = (status or "ativo").strip().lower()
    if status_norm == "pausada":
        return {"status": "error", "reason": "pausar_com_editar_objetivo_estrategico_e_dataRetomada"}
    if status_norm not in STATUS_VALUES:
        status_norm = "ativo"

    diretrizes_clean = [str(d).strip() for d in (diretrizes or []) if str(d).strip()]
    if not diretrizes_clean:
        return {"status": "error", "reason": "diretrizes_obrigatorias"}

    indicadores_obj = [
        {"id": novo_id_estrategia("indicador"), "descricao": str(d).strip(), "concluido": False, "registros": []}
        for d in (indicadores or []) if str(d).strip()
    ]
    marcos_obj = [
        {"id": novo_id_estrategia("marco"), "descricao": str(d).strip(), "concluido": False, "registros": []}
        for d in (marcos or []) if str(d).strip()
    ]

    payload = {
        "userId": user_uid,
        "pilar": pilar_norm,
        "objetivoMacro": titulo,
        "tipoMeta": tipo_norm,
        "indicadoresSucesso": indicadores_obj,
        "marcos": marcos_obj,
        "diretrizesDerivadas": diretrizes_clean,
        "status": status_norm,
        # Quem serve este objetivo: acoes vinculadas, ou dado que o sistema ja
        # coleta. Gravada, e nao deduzida do pilar, para um objetivo novo
        # orientado a dado nascer fora das funcionalidades de vinculo sem que
        # ninguem edite uma lista de excecoes no codigo.
        "gerida_por_acoes": (pilar_norm != "saude") if gerida_por_acoes is None else bool(gerida_por_acoes),
        "timestamp": firestore.SERVER_TIMESTAMP,
    }

    if tipo_norm == "absoluta":
        val_obj = float(metrica_valor_objetivo or 0)
        val_atual = float(metrica_valor_atual or 0)
        val_ini = float(metrica_valor_inicial) if metrica_valor_inicial is not None else (val_atual if val_obj < val_atual else 0)
        payload["metricaAlvo"] = {
            "valorInicial": val_ini,
            "valorAtual": val_atual,
            "valorObjetivo": val_obj,
            "unidade": str(metrica_unidade or "").strip(),
            "fonte": _fonte_valida(metrica_fonte),
        }

    ref = db.collection('estrategia_pessoal').document()
    ref.set(payload)
    resultado = {"status": "created", "objetivo_id": ref.id, "objetivoMacro": titulo, "pilar": pilar_norm}
    unidade = str(metrica_unidade or "").strip().lower()
    if (pilar_norm == "saude" and tipo_norm == "absoluta" and unidade in _UNIDADES_FONTE
            and not payload["metricaAlvo"]["fonte"]):
        # Caso real: a meta de Saúde mostrou 95,7 kg digitados contra 93,4 kg medidos.
        fonte = _UNIDADES_FONTE[unidade]
        resultado["aviso"] = (f"Meta de saúde em {unidade} sem fonte: o valor atual fica parado no que foi "
                              f"digitado. Ligue metrica_fonte='{fonte}' com editar_objetivo_estrategico.")
    return resultado


def editar_objetivo_estrategico(
    db,
    user_uid: str | None,
    objetivo_id: str,
    objetivoMacro: str | None = None,
    pilar: str | None = None,
    tipoMeta: str | None = None,
    status: str | None = None,
    diretrizes: list[str] | None = None,
    metrica_valor_inicial: float | None = None,
    metrica_valor_atual: float | None = None,
    metrica_valor_objetivo: float | None = None,
    metrica_unidade: str | None = None,
    metrica_fonte: str | None = None,
    gerida_por_acoes: bool | None = None,
    ciclo: dict | None = None,
    linhaBase: dict | None = None,
    indicadores: list | None = None,
    dataRetomada: str | None = None,
    origem: str = "mcp",
) -> dict:
    ref, data = carregar_objetivo_estrategico(db, user_uid, objetivo_id)
    if not ref:
        return {"status": "error", "reason": "objetivo_nao_encontrado"}

    updates = {}
    # Perfil de 3 meses: ciclo, linha de base e indicadores numéricos.
    for campo, valor, validar in (("ciclo", ciclo, _validar_ciclo), ("linhaBase", linhaBase, _validar_linha_base),
                                  ("indicadores", indicadores, _validar_indicadores)):
        if valor not in (None, {}, []):  # vazio é "não enviado": `indicadores: []` não apaga o perfil
            limpo, erro = validar(valor)
            if erro:
                return {"status": "error", "reason": erro}
            updates[campo] = limpo
    if objetivoMacro is not None and str(objetivoMacro).strip():
        updates["objetivoMacro"] = str(objetivoMacro).strip()
    if pilar is not None:
        p = str(pilar).strip().lower()
        if p in PILARES:
            updates["pilar"] = p
    if status is not None:
        s = str(status).strip().lower()
        if s in STATUS_VALUES:
            updates["status"] = s
    if tipoMeta is not None:
        tm = str(tipoMeta).strip().lower()
        if tm in TIPOS:
            updates["tipoMeta"] = tm
    if diretrizes is not None:
        dz = [str(d).strip() for d in (diretrizes or []) if str(d).strip()]
        if not dz:
            return {"status": "error", "reason": "diretrizes_nao_podem_ficar_vazias"}
        updates["diretrizesDerivadas"] = dz
    if gerida_por_acoes is not None:
        updates["gerida_por_acoes"] = bool(gerida_por_acoes)

    # Pausada exige data de retomada (passada agora ou já gravada); sair da pausa a apaga.
    status_final = updates.get("status", str(data.get("status") or "").lower())
    if dataRetomada not in (None, ""):
        d = dia(dataRetomada)
        if not d or len(str(dataRetomada).strip()) != 10:
            return {"status": "error", "reason": "dataRetomada_invalida"}
        if d.isoformat() <= hoje_brasilia():
            return {"status": "error", "reason": "dataRetomada_deve_ser_futura"}
        if status_final != "pausada":
            return {"status": "error", "reason": "dataRetomada_so_com_status_pausada"}
        updates["dataRetomada"] = d.isoformat()
    if status_final == "pausada" and not updates.get("dataRetomada") and not dia(data.get("dataRetomada")):
        return {"status": "error", "reason": "pausada_exige_dataRetomada"}
    if status_final != "pausada" and "dataRetomada" in data:
        updates["dataRetomada"] = firestore.DELETE_FIELD

    # Métrica: só aplica se o objetivo é/torna-se absoluto
    tipo_final = updates.get("tipoMeta", data.get("tipoMeta"))
    # `metrica_fonte` precisa estar aqui: ligar ou desligar a fonte de uma meta ja
    # existente e feito com ele sozinho, e sem a entrada na guarda a chamada
    # devolvia `noop` sem nunca chegar na atribuicao abaixo.
    if tipo_final == "absoluta" and any(v is not None for v in [metrica_valor_inicial, metrica_valor_atual, metrica_valor_objetivo, metrica_unidade, metrica_fonte]):
        metrica = dict(data.get("metricaAlvo") or {})
        if metrica_valor_inicial is not None:
            metrica["valorInicial"] = float(metrica_valor_inicial)
        if metrica_valor_atual is not None:
            metrica["valorAtual"] = float(metrica_valor_atual)
        if metrica_valor_objetivo is not None:
            metrica["valorObjetivo"] = float(metrica_valor_objetivo)
        if metrica_unidade is not None:
            metrica["unidade"] = str(metrica_unidade).strip()
        if metrica_fonte is not None:
            metrica["fonte"] = _fonte_valida(metrica_fonte)
        metrica.setdefault("valorInicial", 0)
        metrica.setdefault("valorAtual", 0)
        metrica.setdefault("valorObjetivo", 0)
        metrica.setdefault("unidade", "")
        metrica.setdefault("fonte", "")
        updates["metricaAlvo"] = metrica

    if not updates:
        return {"status": "noop", "reason": "nenhum_campo_alterado"}

    alterados = [k for k in updates.keys() if k != "timestamp"]
    updates["timestamp"] = firestore.SERVER_TIMESTAMP
    # A mudança e o seu registro no mesmo lote: ou os dois, ou nenhum.
    lote = db.batch()
    lote.update(ref, updates)
    registrar_historico(lote, db, user_uid, ref.id, "editar",
                        {k: data.get(k) for k in alterados}, {k: updates[k] for k in alterados}, origem)
    lote.commit()
    return {
        "status": "updated",
        "objetivo_id": ref.id,
        "campos_alterados": alterados,
    }


def normalizar_item(item, tipo: str, indice: int) -> dict:
    """Marco ou indicador como dict, PRESERVANDO todo campo que não conhecemos.

    Antes cada escrita recompunha o item só com id, descricao, concluido,
    registros, dataConclusao e evidencia: qualquer adicionar/editar/concluir
    apagava em silêncio `dataAlvo` e `esperado` (perfil de 3 meses, 30/10/2026)
    e o que mais viesse depois. Item legado em texto puro ganha o id estável de
    `perfil_estrategia.id_legado` — o mesmo em toda leitura, e o que fica gravado.
    """
    if isinstance(item, str):
        return {"id": id_legado(tipo, indice, item), "descricao": item, "concluido": False, "registros": []}
    item = dict(item or {})
    # Só texto entra no hash: str(1.0) e String(1) divergem, e o id tem de ser o mesmo na tela.
    texto = item.get("descricao") if isinstance(item.get("descricao"), str) else ""
    return {**item,
            "id": item.get("id") or id_legado(tipo, indice, texto),
            "descricao": item.get("descricao", ""),
            "concluido": bool(item.get("concluido")),
            "registros": item.get("registros", [])}


def _data_alvo(valor):
    """(valor, erro): YYYY-MM-DD normalizado; vazio remove a data."""
    if valor == "":
        return "", None
    d = dia(valor)
    return (d.isoformat(), None) if d and len(str(valor).strip()) == 10 else (None, "dataAlvo_invalida")


def _esperado(valor):
    """(mapa, erro): chave do indicador -> número; {} limpa."""
    if not isinstance(valor, dict):
        return None, "esperado_invalido"
    limpo = {}
    for chave, numero_bruto in valor.items():
        n = numero(numero_bruto, None)
        if not str(chave).strip() or n is None or isinstance(numero_bruto, bool):
            return None, "esperado_invalido"
        limpo[str(chave).strip()] = n
    return limpo, None


def aplicar_item(data: dict, tipo: str, acao: str, descricao: str | None = None, item_id: str | None = None,
                 dataAlvo: str | None = None, esperado: dict | None = None, itens: list | None = None):
    """Parte pura de `gerenciar_item_estrategico`: (nova lista, resultado) ou (None, erro).

    `itens` (só em adicionar): vários de uma vez, [{descricao, dataAlvo, esperado}]. Tudo
    ou nada: um item inválido recusa o lote inteiro.
    """
    if itens == []:
        itens = None  # vazio é "não enviado", como em dataAlvo e esperado
    if itens is not None:
        if acao != "adicionar" or not isinstance(itens, list):
            return None, {"status": "error", "reason": "itens_so_em_adicionar_e_nao_vazio"}
        atual, ids = data, []
        for item in itens:
            if not isinstance(item, dict):
                return None, {"status": "error", "reason": "item_invalido"}
            lista, r = aplicar_item(atual, tipo, "adicionar", item.get("descricao"), None,
                                    item.get("dataAlvo"), item.get("esperado"))
            if lista is None:
                return None, {**r, "item": item.get("descricao")}
            atual = {**atual, ("indicadoresSucesso" if tipo == "indicador" else "marcos"): lista}
            ids.append(r["item_id"])
        return lista, {"item_id": ids[0], "item_ids": ids}

    campo = "indicadoresSucesso" if tipo == "indicador" else "marcos"
    if tipo != "marco":
        # Vazio é "não enviado": quem chama costuma preencher os opcionais assim.
        if dataAlvo not in (None, "") or esperado not in (None, {}):
            return None, {"status": "error", "reason": "dataAlvo_e_esperado_so_em_marco"}
        dataAlvo = esperado = None
    perfil = {}
    if dataAlvo is not None:
        perfil["dataAlvo"], erro = _data_alvo(dataAlvo)
        if erro:
            return None, {"status": "error", "reason": erro}
    if esperado is not None:
        perfil["esperado"], erro = _esperado(esperado)
        if erro:
            return None, {"status": "error", "reason": erro}

    def _com_perfil(alvo: dict) -> dict:
        for chave, valor in perfil.items():
            if valor in ("", {}):
                alvo.pop(chave, None)
            elif chave == "esperado":
                # Mescla por indicador: mandar só o peso não apaga a cintura do marco.
                atual = alvo.get("esperado") if isinstance(alvo.get("esperado"), dict) else {}
                alvo["esperado"] = {**atual, **valor}
            else:
                alvo[chave] = valor
        return alvo

    lista = [normalizar_item(item, tipo, i) for i, item in enumerate(data.get(campo) or [])]

    if acao == "adicionar":
        if not (descricao or "").strip():
            return None, {"status": "error", "reason": "descricao_obrigatoria"}
        novo = _com_perfil({"id": novo_id_estrategia(tipo), "descricao": descricao.strip(),
                            "concluido": False, "registros": []})
        lista.append(novo)
        return lista, {"item_id": novo["id"]}

    if not item_id:
        return None, {"status": "error", "reason": "item_id_obrigatorio"}
    alvo = next((it for it in lista if it["id"] == item_id), None)
    if not alvo:
        return None, {"status": "error", "reason": "item_nao_encontrado"}
    if acao == "editar":
        if not (descricao or "").strip() and not perfil:
            return None, {"status": "error", "reason": "nada_para_editar"}
        if (descricao or "").strip():
            alvo["descricao"] = descricao.strip()
        _com_perfil(alvo)
    elif acao == "remover":
        lista = [it for it in lista if it["id"] != item_id]
    elif acao == "concluir":
        alvo["concluido"] = True
        alvo["dataConclusao"] = datetime.now(timezone.utc).isoformat()
    return lista, {"item_id": item_id}


def gerenciar_item_estrategico(
    db,
    user_uid: str | None,
    objetivo_id: str,
    tipo: str,
    acao: str,
    descricao: str | None = None,
    item_id: str | None = None,
    dataAlvo: str | None = None,
    esperado: dict | None = None,
    itens: list | None = None,
    origem: str = "mcp",
) -> dict:
    if not user_uid or not objetivo_id:
        return {"status": "error", "reason": "objetivo_nao_encontrado"}
    tipo_norm = (tipo or "").strip().lower()
    if tipo_norm not in {"indicador", "marco"}:
        return {"status": "error", "reason": "tipo_invalido"}
    acao_norm = (acao or "").strip().lower()
    if acao_norm not in {"adicionar", "editar", "remover", "concluir"}:
        return {"status": "error", "reason": "acao_invalida"}
    campo = "indicadoresSucesso" if tipo_norm == "indicador" else "marcos"
    ref = db.collection('estrategia_pessoal').document(str(objetivo_id))

    # Transação: indispensável porque o loop de tool-calling pode disparar
    # várias chamadas gerenciar_item_estrategico em paralelo sobre o mesmo
    # objetivo. Ler/recompor/gravar o array inteiro fora de transação faria
    # o último writer sobrescrever silenciosamente os demais. A transação
    # relê dentro do escopo e o Firestore reexecuta sob contenção.
    @firestore.transactional
    def _aplicar(transaction):
        snap = ref.get(transaction=transaction)
        if not snap.exists:
            return {"status": "error", "reason": "objetivo_nao_encontrado"}
        data = snap.to_dict() or {}
        if data.get('userId') != user_uid:
            return {"status": "error", "reason": "objetivo_nao_encontrado"}

        lista, resultado = aplicar_item(data, tipo_norm, acao_norm, descricao, item_id, dataAlvo, esperado, itens)
        if lista is None:
            return resultado
        transaction.update(ref, {campo: lista, "timestamp": firestore.SERVER_TIMESTAMP})
        # Na mesma transação: a mudança e o seu registro entram juntos, ou nenhum.
        registrar_historico(transaction, db, user_uid, ref.id, f"{tipo_norm}:{acao_norm}",
                            {campo: data.get(campo) or []}, {campo: lista}, origem)
        return {
            "status": "ok",
            "objetivo_id": ref.id,
            "tipo": tipo_norm,
            "acao": acao_norm,
            **resultado,
        }

    return _aplicar(db.transaction())


def _serializavel(valor):
    """O que vai para o JSON do MCP: datas do Firestore viram texto ISO."""
    if isinstance(valor, dict):
        return {k: _serializavel(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_serializavel(v) for v in valor]
    return valor.isoformat() if hasattr(valor, "isoformat") else valor


def _objetivo_completo(objetivo_id: str, data: dict) -> dict:
    """O objetivo inteiro, com marcos e indicadores de sucesso sempre como dict e com o
    id que `gerenciar_item_estrategico` aceita (o legado em texto ganha `id_legado`)."""
    saida = {k: v for k, v in data.items() if k != "userId"}
    saida["id"] = objetivo_id
    saida["marcos"] = [normalizar_item(m, "marco", i) for i, m in enumerate(data.get("marcos") or [])]
    saida["indicadoresSucesso"] = [normalizar_item(m, "indicador", i)
                                   for i, m in enumerate(data.get("indicadoresSucesso") or [])]
    return _serializavel(saida)


def obter_objetivo_estrategico(db, user_uid: str | None, objetivo_id: str) -> dict:
    """Conteúdo inteiro de um objetivo: título, pilar, status, métrica com fonte,
    histórico, diretrizes, indicadores e marcos com id, data alvo e esperado."""
    ref, data = carregar_objetivo_estrategico(db, user_uid, objetivo_id)
    if not ref:
        return {"status": "error", "reason": "objetivo_nao_encontrado"}
    return {"status": "ok", "objetivo": _objetivo_completo(ref.id, data)}


def listar_objetivos_estrategicos(db, user_uid: str | None, completo: bool = True, status: str | None = None) -> dict:
    """Objetivos do usuário. `completo=false` devolve só id, título, pilar, status e contagens."""
    if not user_uid:
        return {"status": "error", "reason": "auth_required"}
    if isinstance(completo, str):  # o MCP não converte tipos: "false" em texto seria verdadeiro
        completo = completo.strip().lower() not in ("false", "0", "nao", "não", "")
    filtro = str(status or "").strip().lower()
    objetivos = []
    for snap in db.collection('estrategia_pessoal').where('userId', '==', user_uid).stream():
        data = snap.to_dict() or {}
        if data.get('userId') != user_uid or (filtro and str(data.get("status") or "").lower() != filtro):
            continue
        if completo:
            objetivos.append(_objetivo_completo(snap.id, data))
        else:
            marcos = data.get("marcos") or []
            objetivos.append({"id": snap.id, "objetivoMacro": data.get("objetivoMacro"), "pilar": data.get("pilar"),
                              "status": data.get("status"), "marcos": len(marcos),
                              "marcos_concluidos": sum(1 for m in marcos if isinstance(m, dict) and m.get("concluido"))})
    objetivos.sort(key=lambda o: (str(o.get("pilar") or ""), str(o.get("objetivoMacro") or "")))
    return {"status": "ok", "total": len(objetivos), "objetivos": objetivos}


def excluir_objetivo_estrategico(db, user_uid: str | None, objetivo_id: str) -> dict:
    ref, data = carregar_objetivo_estrategico(db, user_uid, objetivo_id)
    if not ref:
        return {"status": "error", "reason": "objetivo_nao_encontrado"}
    titulo = data.get("objetivoMacro", "")
    # O objetivo inteiro fica no histórico, no mesmo lote: excluir deixa de ser sem volta.
    lote = db.batch()
    lote.delete(ref)
    registrar_historico(lote, db, user_uid, objetivo_id, "excluir", {k: v for k, v in data.items() if k != "userId"}, {})
    lote.commit()
    return {"status": "deleted", "objetivo_id": objetivo_id, "objetivoMacro": titulo}
