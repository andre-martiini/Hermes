"""Detector de subproduto: avisar quando o trabalho que ja aconteceu deixou um ativo.

A ideia central nao e medir nem propor trabalho novo. As acoes do usuario sao
majoritariamente reativas — demanda do campus, demanda da instituicao, vontade
avulsa — e resolvem o problema do dia e acabam. Alavancar nao exige acrescentar
trabalho: exige fazer o trabalho que ja vai acontecer de um jeito que deixe algo
para tras.

Quatro casos reais de uma unica semana, todos desperdicados:

- handoff de 12 secoes do SISPNAES para o novo desenvolvedor -> relato de
  experiencia sobre transicao de conhecimento em TI no setor publico, e **ja
  estava escrito**;
- analise de exequibilidade das planilhas de um pregao, feita pela segunda vez
  -> roteiro reproduzivel sob a Lei 14.133;
- o proprio SISPNAES, que so duas instituicoes da Rede Federal fazem -> caso
  documentado para o FIAE/Conif;
- nove pacotes de melhoria da automacao do PGD, com defeito medido -> caso de
  uso de IA em processo administrativo federal.

Nenhum exigiu acao nova. Exigiu alguem perguntando, na hora certa: "isso rende
alguma coisa alem de resolver o problema de hoje?".

O achado que orienta o modulo inteiro: **o usuario ja escreve um volume enorme
por padrao** — diarios de acao, prompts para desenvolvedor, handoffs, minutas,
pareceres — e esse corpo de texto esta todo dentro de um gerenciador de tarefas,
onde ninguem nunca vai ler. O sistema nao precisa faze-lo escrever mais. Precisa
avisar quando ele **ja escreveu**.

## As tres travas, e por que cada uma existe

**O momento.** Nao e a conclusao: quando se conclui, a energia acabou e o que se
quer e fechar a aba. Nao e a criacao: ali ainda nao se sabe o que aquilo vai
virar. E quando a acao **ganha corpo** — um documento foi anexado, o diario
passou de certo tamanho, ou N etapas foram concluidas.

**A escassez.** Sem ela vira praga. So eleva quando pelo menos um for verdadeiro:
e repetivel (um metodo se paga), e raro (documentar tem valor externo), ou ja
esta escrito (o custo marginal de publicar e quase zero).

**O teto.** Poucas elevacoes por mes, e nenhuma em semana cheia. Uma sugestao de
elevacao numa semana de dois workshops e uma viagem e ruido, nao ajuda.

## O que este modulo NAO faz

Nao olha para objetivo com `gerida_por_acoes: false`. Nada do modulo de saude e
materia-prima de ativo aqui: se um dia o usuario quiser escrever sobre a propria
reabilitacao, isso e uma acao do pilar Intelectual criada por ele, nao uma
elevacao automatica de telemetria clinica.

Nao decide sozinho. Toda elevacao e uma sugestao com "Nunca para esta acao" —
sem essa saida o sistema repete a mesma proposta e vira barulho.
"""

from __future__ import annotations

import os

COL_ELEVACOES = "elevacoes_sugeridas"

# Quantas elevacoes por mes. Tres e o comeco sugerido pelo usuario; a trava
# existe para o recurso nao virar praga, entao o numero e conservador de
# proposito e sobe so com evidencia de que as sugestoes estao sendo aceitas.
TETO_POR_MES = int(os.environ.get("ELEVACAO_TETO_MES", "3"))

# Acoes com data nos proximos 7 dias a partir das quais a semana conta como
# cheia. Calibravel: e um limiar de carga, nao uma verdade.
SEMANA_CHEIA_ACOES = int(os.environ.get("ELEVACAO_SEMANA_CHEIA", "25"))

# O que conta como "ganhou corpo".
CORPO_MIN_CARACTERES_DIARIO = int(os.environ.get("ELEVACAO_MIN_DIARIO", "1200"))
CORPO_MIN_ETAPAS_FEITAS = int(os.environ.get("ELEVACAO_MIN_ETAPAS", "3"))

MOTIVOS_ESCASSEZ = ("repetivel", "raro", "ja_escrito")

MODELO = os.environ.get("ELEVACAO_MODEL", "claude-fable-5")
MODELO_FALLBACK = os.environ.get("ELEVACAO_FALLBACK_MODEL", "claude-opus-4-8")
MAX_TOKENS = int(os.environ.get("ELEVACAO_MAX_TOKENS", "2048"))

STATUS_PENDENTE = "pendente"
STATUS_ACEITA = "aceita"
STATUS_ADIADA = "adiada"
STATUS_NUNCA = "nunca"

# Extensoes que sinalizam texto ja escrito, e nao anexo qualquer. Um PDF de
# comprovante nao e materia-prima de artigo; um .md de handoff e.
_EXTENSOES_DE_TEXTO = (".md", ".markdown", ".txt", ".doc", ".docx", ".odt", ".tex")


def _texto_do_diario(tarefa: dict) -> str:
    entradas = [e for e in (tarefa.get("acompanhamento") or []) if isinstance(e, dict)]
    return "\n".join(str(e.get("nota") or "") for e in entradas)


def _anexos(tarefa: dict) -> list[dict]:
    return [
        x for x in (tarefa.get("pool_dados") or [])
        if isinstance(x, dict) and x.get("tipo") == "arquivo"
    ]


def _etapas_feitas(tarefa: dict) -> int:
    """Contagem pelo modulo canonico, e nao por leitura direta do campo.

    `subtarefas.contar` ja resolve as duas grafias do texto (`text`/`texto`) e a
    deducao de estado a partir do `completed` antigo. Reimplementar aqui daria
    zero em todo plano real, e o detector nunca acharia corpo nenhum por etapas.
    """
    import subtarefas

    feitas, _ = subtarefas.contar(tarefa.get("plano_acao"))
    return feitas


def corpo_da_acao(tarefa: dict) -> dict | None:
    """O que da corpo a esta acao — ou None se ela ainda nao tem.

    Devolve a evidencia, nao um booleano, porque a evidencia e o que a sugestao
    precisa citar: "o que ja existe: docs/HANDOFF-SISPNAES.md, 12 secoes". Uma
    sugestao que nao consegue apontar o material perde o argumento inteiro — o
    valor dela e dizer que o custo marginal e quase zero.
    """
    anexos = _anexos(tarefa)
    documentos = [
        a for a in anexos
        if str(a.get("nome") or "").lower().endswith(_EXTENSOES_DE_TEXTO)
    ]
    diario = _texto_do_diario(tarefa)
    etapas = _etapas_feitas(tarefa)

    sinais = []
    if documentos:
        sinais.append({
            "tipo": "documento",
            "detalhe": [str(a.get("nome") or "") for a in documentos],
        })
    if len(diario) >= CORPO_MIN_CARACTERES_DIARIO:
        sinais.append({"tipo": "diario", "detalhe": f"{len(diario)} caracteres registrados"})
    if etapas >= CORPO_MIN_ETAPAS_FEITAS:
        sinais.append({"tipo": "etapas", "detalhe": f"{etapas} etapas concluidas"})
    # Anexo que nao e texto ainda conta como artefato produzido, mas sozinho e
    # sinal fraco: vale quando ha tambem diario ou etapas.
    if anexos and not documentos and sinais:
        sinais.append({"tipo": "artefato", "detalhe": [str(a.get("nome") or "") for a in anexos]})

    if not sinais:
        return None
    return {
        "sinais": sinais,
        "tem_texto_pronto": bool(documentos) or len(diario) >= CORPO_MIN_CARACTERES_DIARIO,
        "caracteres_diario": len(diario),
        "documentos": [str(a.get("nome") or "") for a in documentos],
        "etapas_feitas": etapas,
    }


def semana_esta_cheia(carga_semana, limiar: int = SEMANA_CHEIA_ACOES) -> bool:
    """A carga dos proximos sete dias ja passa do que cabe.

    O sistema ja calcula isso para o resumo matinal; reusar em vez de inventar
    outra metrica evita que "semana cheia" signifique duas coisas diferentes em
    duas telas.
    """
    total = 0
    for dia in carga_semana or []:
        try:
            total += int((dia or {}).get("total") or 0)
        except (TypeError, ValueError):
            continue
    return total >= limiar


def objetivos_elegiveis(objetivos) -> list[dict]:
    """Objetivos que podem receber elevacao.

    Objetivo servido por dado fica de fora inteiro. Sem essa exclusao o pilar
    Saude passaria a exibir progresso falso, feito de contagem de acao,
    concorrendo com o numero real que vem do peso — e a fila encheria de
    caminhada, fisioterapia e consulta.
    """
    elegiveis = []
    for obj in objetivos or []:
        if not isinstance(obj, dict):
            continue
        gravada = obj.get("gerida_por_acoes")
        gerida = bool(gravada) if gravada is not None else str(obj.get("pilar") or "") != "saude"
        if not gerida:
            continue
        if str(obj.get("status") or "").lower() in ("concluido", "concluído", "cancelado", "arquivado"):
            continue
        elegiveis.append(obj)
    return elegiveis


def _mes(data_iso: str) -> str:
    return str(data_iso or "")[:7]


def elevacoes_do_mes(sugestoes, hoje: str) -> int:
    """Quantas ja foram propostas neste mes.

    Conta proposta, nao aceitacao: o teto existe para o usuario nao ser
    interrompido demais, e uma sugestao recusada interrompeu do mesmo jeito.
    """
    mes = _mes(hoje)
    return len([
        s for s in (sugestoes or [])
        if isinstance(s, dict)
        and _mes(s.get("criada_em")) == mes
        and str(s.get("status") or "") != STATUS_NUNCA
    ])


def acoes_ja_decididas(sugestoes) -> dict[str, str]:
    """task_id -> status, para nao repetir o que ja foi perguntado.

    "Nunca para esta acao" e definitivo. Pendente e aceita tambem bloqueiam:
    propor de novo o que esta na fila e a forma mais rapida de o usuario parar
    de ler a fila.
    """
    decididas = {}
    for s in sugestoes or []:
        if not isinstance(s, dict):
            continue
        task_id = str(s.get("task_id") or "").strip()
        if not task_id:
            continue
        status = str(s.get("status") or STATUS_PENDENTE)
        anterior = decididas.get(task_id)
        # `nunca` vence qualquer outro status ja gravado para a mesma acao.
        if anterior == STATUS_NUNCA:
            continue
        decididas[task_id] = status
    return decididas


def candidatas(tarefas, decididas: dict, hoje: str) -> list[dict]:
    """Acoes com corpo que ainda nao foram perguntadas.

    Nao filtra por conclusao: o momento certo e quando a acao ganha corpo, e uma
    acao parcialmente feita ja indica materialidade. Esperar a conclusao e chegar
    quando a energia acabou.
    """
    saida = []
    for tarefa in tarefas or []:
        if not isinstance(tarefa, dict):
            continue
        task_id = str(tarefa.get("id") or "").strip()
        if not task_id:
            continue
        if decididas.get(task_id) in (STATUS_NUNCA, STATUS_PENDENTE, STATUS_ACEITA):
            continue
        corpo = corpo_da_acao(tarefa)
        if not corpo:
            continue
        saida.append({"task_id": task_id, "tarefa": tarefa, "corpo": corpo})
    # Quem ja tem texto pronto primeiro: e o de custo marginal mais baixo, e o
    # que o usuario disse ser o mais rentavel no caso dele.
    saida.sort(key=lambda c: (not c["corpo"]["tem_texto_pronto"], -c["corpo"]["caracteres_diario"]))
    return saida


def pode_rodar(sugestoes, carga_semana, hoje: str,
               teto: int = TETO_POR_MES, limiar_semana: int = SEMANA_CHEIA_ACOES) -> dict:
    """As travas de volume, avaliadas antes de qualquer chamada de IA.

    Sao baratas e decidem sozinhas se vale gastar uma chamada — e, mais
    importante, sao deterministicas: o teto nao pode depender do humor do modelo.
    """
    if semana_esta_cheia(carga_semana, limiar_semana):
        return {"pode": False, "motivo": "semana_cheia"}
    ja = elevacoes_do_mes(sugestoes, hoje)
    if ja >= teto:
        return {"pode": False, "motivo": "teto_do_mes", "ja_propostas": ja}
    return {"pode": True, "restantes": teto - ja}


def validar_proposta(proposta, objetivos_validos, task_ids_validos) -> dict | None:
    """A proposta da IA so vale se estiver inteira e apontar coisas que existem.

    A regra que impede a elevacao decorativa: se a IA nao consegue escrever, em
    uma frase, por que aquele trabalho serve aquele objetivo, ela nao propoe. A
    frase vai junto e e o que o usuario le para aceitar ou recusar — sem ela a
    sugestao e um palpite pedindo confianca.
    """
    if not isinstance(proposta, dict):
        return None

    task_id = str(proposta.get("task_id") or "").strip()
    objetivo_id = str(proposta.get("objetivo_id") or "").strip()
    if task_id not in task_ids_validos or objetivo_id not in objetivos_validos:
        return None

    motivo = str(proposta.get("motivo_escassez") or "").strip().lower()
    if motivo not in MOTIVOS_ESCASSEZ:
        return None

    campos = {
        "ativo_possivel": str(proposta.get("ativo_possivel") or "").strip(),
        "justificativa": str(proposta.get("justificativa") or "").strip(),
        "o_que_ja_existe": str(proposta.get("o_que_ja_existe") or "").strip(),
        "passo_que_falta": str(proposta.get("passo_que_falta") or "").strip(),
    }
    if not all(campos.values()):
        return None
    # Justificativa de uma linha, nao um paragrafo generico: e o teste de que a
    # IA de fato sabe por que aquilo serve ao objetivo.
    if len(campos["justificativa"]) < 20:
        return None

    return {
        "task_id": task_id,
        "objetivo_id": objetivo_id,
        "motivo_escassez": motivo,
        "custo_estimado": str(proposta.get("custo_estimado") or "").strip() or "nao estimado",
        **campos,
    }


def montar_dossie(candidata: dict, limite_diario: int = 4000) -> dict:
    """O que a IA recebe de uma acao candidata.

    Manda o texto do diario porque e nele que mora o ativo — e o corpo de texto
    que o usuario ja escreveu e que ninguem le. Truncado no fim, e nao no comeco:
    as entradas mais recentes sao as que descrevem o que a acao virou.
    """
    tarefa = candidata["tarefa"]
    diario = _texto_do_diario(tarefa)
    return {
        "task_id": candidata["task_id"],
        "titulo": str(tarefa.get("titulo") or ""),
        "descricao": str(tarefa.get("descricao") or "")[:1000],
        "documentos": candidata["corpo"]["documentos"],
        "etapas_feitas": candidata["corpo"]["etapas_feitas"],
        "diario": diario[-limite_diario:],
        "diario_truncado": len(diario) > limite_diario,
    }


def resumo_para_o_usuario(sugestao: dict, titulo_acao: str, nome_objetivo: str) -> str:
    """O texto do card. Nao e "considere transformar isso em artigo".

    Cada linha responde uma pergunta que o usuario faria antes de aceitar: o que
    ja existe, o que da para fazer com isso, a que objetivo serve, o que falta e
    quanto custa. Sugestao vaga e recusada sem leitura.
    """
    return (
        f'Elevacao sugerida — acao "{titulo_acao}"\n'
        f'O que ja existe: {sugestao["o_que_ja_existe"]}\n'
        f'Ativo possivel: {sugestao["ativo_possivel"]}\n'
        f'Objetivo servido: {nome_objetivo} — {sugestao["justificativa"]}\n'
        f'Passo que falta: {sugestao["passo_que_falta"]}\n'
        f'Custo estimado: {sugestao["custo_estimado"]}'
    )


# ---------------------------------------------------------------------------
# Orquestracao: a varredura agendada
# ---------------------------------------------------------------------------

PERSONA = """Voce examina o trabalho que uma pessoa JA FEZ e identifica o que
sobrou dele como ativo reaproveitavel.

Voce NAO propoe trabalho novo. Voce nao sugere "considere escrever um artigo".
Voce aponta que o material JA EXISTE e diz qual e o passo que falta.

Esta pessoa e servidora publica federal, trabalha com processos administrativos,
compras publicas, gestao de projetos e aplicacao de IA no setor publico. Ela
escreve um volume enorme por padrao — diarios de acao, handoffs, minutas,
pareceres — e esse texto morre dentro do gerenciador de tarefas.

So proponha uma elevacao se conseguir escrever, EM UMA FRASE, por que aquele
trabalho serve aquele objetivo estrategico. Se nao conseguir escrever a frase,
nao proponha. Frase generica ("contribui para o crescimento") nao vale.

Prefira, nesta ordem:
1. ja_escrito — o material esta pronto e o custo de publicar e quase zero;
2. repetivel — ja foi feito antes ou vai ser de novo, entao um metodo se paga;
3. raro — pouca gente na Rede Federal fez isso, entao documentar tem valor externo.

Se nada na lista merecer, nao chame a ferramenta e diga por que."""

_SCHEMA_PROPOSTA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "Id da acao, exatamente como recebido."},
        "objetivo_id": {"type": "string", "description": "Id do objetivo servido, da lista recebida."},
        "motivo_escassez": {"type": "string", "enum": list(MOTIVOS_ESCASSEZ)},
        "o_que_ja_existe": {"type": "string", "description": "O material concreto, citado: nome do arquivo, tamanho do diario, data."},
        "ativo_possivel": {"type": "string", "description": "O que aquilo pode virar, em uma linha."},
        "justificativa": {"type": "string", "description": "Por que serve a ESTE objetivo. Uma frase, especifica."},
        "passo_que_falta": {"type": "string", "description": "O que falta fazer, concreto."},
        "custo_estimado": {"type": "string", "description": "Ordem de grandeza: uma tarde, dois dias."},
    },
    "required": ["task_id", "objetivo_id", "motivo_escassez", "o_que_ja_existe",
                 "ativo_possivel", "justificativa", "passo_que_falta"],
}


def _filtro(campo: str, op: str, valor):
    """`FieldFilter` num lugar so, para o filtro morar na consulta e nao no `for`.

    Filtrar depois de ler significa ler um recorte arbitrario e procurar dentro
    dele: passado o limite, o que interessa pode estar todo fora. Este modulo ja
    teve esse defeito em duas leituras diferentes.
    """
    from firebase_admin import firestore as _fs

    return _fs.FieldFilter(campo, op, valor)


def _contador_do_mes(db, hoje: str):
    return (db.collection("system_usage").document("elevacoes_sugeridas")
            .collection("mensal").document(_mes(hoje)))


def id_da_reserva(hoje: str, task_id: str) -> str:
    """Id deterministico por acao e mes.

    Se o modelo emitir duas propostas para a MESMA acao na mesma resposta, as
    duas validam contra o mesmo conjunto de candidatas e o contador so serializa
    a contagem — sairiam dois cards para a mesma acao, consumindo duas vagas, e
    marcar "nunca" num deixaria o outro pendente, contradizendo a permanencia que
    o card promete. Com id deterministico a segunda colide e e recusada.

    O mes entra na chave porque a acao volta a ser candidata depois de adiada;
    dentro do mesmo mes ela nao volta, o que e desejado — insistir na mesma acao
    gastaria o teto de tres em uma so.
    """
    return f"{_mes(hoje)}__{task_id}"


def reservar_no_firestore(db, hoje: str, teto: int, ref, payload: dict,
                          ja_no_mes: int = 0) -> bool:
    """Confere o teto do mes e grava a sugestao na MESMA transacao.

    `claude_provider.run_tool_loop` executa as tool calls de uma rodada em
    paralelo, num ThreadPoolExecutor. Um contador em memoria deixaria duas
    threads lerem a mesma contagem antes de qualquer uma gravar, e uma rodada com
    uma vaga sobrando persistiria varias sugestoes — o teto e a unica coisa que
    impede o recurso de virar praga, entao ele nao pode depender de ordem de
    execucao entre threads. A transacao serializa leitura e escrita mesmo entre
    threads e entre execucoes sobrepostas do agendador, porque todas disputam o
    mesmo documento contador (chave = mes).
    """
    from firebase_admin import firestore as _fs

    contador = _contador_do_mes(db, hoje)

    @_fs.transactional
    def _txn(transaction):
        # A sugestao ja existir e resposta: id deterministico por acao e mes.
        if ref.get(transaction=transaction).exists:
            return False
        snap = contador.get(transaction=transaction)
        gravado = (snap.to_dict() or {}).get("count", 0) if snap.exists else 0
        # O contador nasceu depois das sugestoes. Enquanto ele nao existir — no
        # primeiro deploy, ou se o documento se perder — zero seria uma licenca
        # para recomecar a contagem do mes do zero com sugestoes ja na base.
        atual = max(int(gravado or 0), int(ja_no_mes or 0))
        if atual >= teto:
            return False
        transaction.set(contador, {"count": atual + 1, "atualizado_em": hoje}, merge=True)
        transaction.set(ref, payload)
        return True

    try:
        return bool(_txn(db.transaction()))
    except Exception as exc:
        print(f"[Elevacao] Falha ao reservar vaga do mes: {exc}")
        return False


def registrar_sugestao(db, sugestao: dict, hoje: str, titulo_acao: str,
                       nome_objetivo: str, teto: int = TETO_POR_MES,
                       reservar=reservar_no_firestore, ja_no_mes: int = 0) -> str | None:
    """Grava a sugestao se ainda houver vaga no mes. None quando nao ha.

    `reservar` e uma costura: a atomicidade e o ponto, e testa-la de verdade
    exigiria um Firestore. Injetando a reserva, o teste verifica o que e desta
    camada — que vaga negada nao vira sugestao gravada, e que o payload sai
    completo — sem testar a biblioteca do Google.
    """
    ref = db.collection(COL_ELEVACOES).document(id_da_reserva(hoje, sugestao["task_id"]))
    payload = {
        **sugestao,
        "status": STATUS_PENDENTE,
        "criada_em": hoje,
        "titulo_acao": titulo_acao,
        "nome_objetivo": nome_objetivo,
        "resumo": resumo_para_o_usuario(sugestao, titulo_acao, nome_objetivo),
    }
    return ref.id if reservar(db, hoje, teto, ref, payload, ja_no_mes) else None


class HistoricoIndisponivel(Exception):
    """A base de sugestoes nao pode ser lida agora."""


def _carregar_sugestoes(db, hoje: str) -> list[dict]:
    """O historico que sustenta as duas regras, sem teto de vida arbitrario.

    Um `limit` sobre a colecao inteira e uma bomba-relogio: passado o corte, um
    registro `nunca` cai fora da leitura e a acao volta a ser candidata, quebrando
    a permanencia que o card promete. Entao a busca e por recorte com significado,
    e nao por quantidade:

    - todo `nunca`, para sempre — e o que da permanencia a decisao;
    - todo `pendente` e `aceita`, de qualquer epoca — quem ja esta na fila nao e
      perguntado de novo;
    - tudo deste mes, para a contagem do teto.

    Levanta em vez de devolver lista vazia quando a leitura falha. Historico vazio
    nao e um estado neutro aqui: e o estado em que o teto parece zerado e nenhuma
    acao parece decidida — um erro transitorio viraria permissao para estourar o
    limite e repropor o que ja foi recusado para sempre. A trava falha fechada.
    """
    try:
        col = db.collection(COL_ELEVACOES)
        recortes = (
            col.where(filter=_filtro("status", "==", STATUS_NUNCA)),
            col.where(filter=_filtro("status", "in", [STATUS_PENDENTE, STATUS_ACEITA])),
            col.where(filter=_filtro("criada_em", ">=", f"{_mes(hoje)}-01")),
        )
        por_id = {}
        for recorte in recortes:
            for d in recorte.stream():
                por_id[d.id] = {**(d.to_dict() or {}), "id": d.id}
        return list(por_id.values())
    except Exception as exc:
        raise HistoricoIndisponivel(str(exc)) from exc


def preparar_rodada(db, hoje: str, carga_semana) -> dict:
    """Tudo que se decide sem IA: se vale rodar, e sobre o que.

    Separado da chamada ao modelo de proposito. As travas de volume sao
    deterministicas e baratas, e decidir antes evita gastar chamada num dia em
    que nenhuma sugestao poderia sair de qualquer forma.
    """
    try:
        sugestoes = _carregar_sugestoes(db, hoje)
    except HistoricoIndisponivel as exc:
        print(f"[Elevacao] Historico indisponivel, rodada abortada: {exc}")
        return {"rodar": False, "motivo": "historico_indisponivel"}
    veredito = pode_rodar(sugestoes, carga_semana, hoje)
    if not veredito["pode"]:
        return {"rodar": False, **veredito}

    objetivos = objetivos_elegiveis([
        {**(d.to_dict() or {}), "id": d.id}
        for d in db.collection("estrategia_pessoal").limit(80).stream()
    ])
    if not objetivos:
        return {"rodar": False, "motivo": "nenhum_objetivo_elegivel"}

    tarefas = [
        {**(d.to_dict() or {}), "id": d.id}
        for d in db.collection("tarefas")
        .where("status", "in", ["em andamento", "stand-by"]).limit(150).stream()
    ]
    candidatos = candidatas(tarefas, acoes_ja_decididas(sugestoes), hoje)
    if not candidatos:
        return {"rodar": False, "motivo": "nenhuma_acao_com_corpo"}

    return {
        "rodar": True,
        "restantes": veredito["restantes"],
        "ja_no_mes": elevacoes_do_mes(sugestoes, hoje),
        "objetivos": objetivos,
        "candidatos": candidatos,
    }


def _ferramenta_propor(db, hoje: str, rodada: dict, aceitas: list,
                      reservar=reservar_no_firestore):
    """`rodada["ja_no_mes"]` vem do historico lido em `preparar_rodada`, e e o
    piso da contagem: o contador transacional pode nao existir ainda."""
    """A tool de escrita. A validacao mora AQUI, e nao na confianca no modelo.

    O teto e a lista de objetivos validos sao conferidos no momento da gravacao:
    o modelo pode alucinar um id, insistir depois do limite, ou apontar um
    objetivo servido por dado. Qualquer uma dessas passaria se a checagem
    estivesse so no prompt.
    """
    objetivos_por_id = {o["id"]: o for o in rodada["objetivos"]}
    titulos = {c["task_id"]: str(c["tarefa"].get("titulo") or "") for c in rodada["candidatos"]}

    def propor_elevacao(**kwargs) -> dict:
        sugestao = validar_proposta(kwargs, set(objetivos_por_id), set(titulos))
        if not sugestao:
            return {"aceita": False, "motivo": "proposta incompleta, id invalido ou justificativa generica"}
        objetivo = objetivos_por_id[sugestao["objetivo_id"]]
        # O teto e conferido dentro da transacao, e nao aqui: esta funcao roda em
        # paralelo com as outras tool calls da mesma rodada.
        sugestao_id = registrar_sugestao(
            db, sugestao, hoje, titulos[sugestao["task_id"]],
            str(objetivo.get("objetivoMacro") or ""), reservar=reservar,
            ja_no_mes=int(rodada.get("ja_no_mes") or 0),
        )
        if not sugestao_id:
            return {"aceita": False, "motivo": "teto do mes ja atingido"}
        aceitas.append(sugestao_id)
        return {"aceita": True, "sugestao_id": sugestao_id}

    tools = [{
        "name": "propor_elevacao",
        "description": ("Registra UMA elevacao sugerida. So chame quando conseguir preencher "
                        "todos os campos com material que existe de fato na acao."),
        "input_schema": _SCHEMA_PROPOSTA,
    }]
    return tools, {"propor_elevacao": propor_elevacao}


def mensagem_da_rodada(rodada: dict, limite_candidatos: int = 8) -> str:
    """O que o modelo ve: os objetivos elegiveis e o material de cada candidata."""
    import json

    objetivos = [
        {"objetivo_id": o["id"], "pilar": o.get("pilar"),
         "objetivo": o.get("objetivoMacro"),
         "diretrizes": (o.get("diretrizesDerivadas") or [])[:4]}
        for o in rodada["objetivos"]
    ]
    dossies = [montar_dossie(c) for c in rodada["candidatos"][:limite_candidatos]]
    return (
        "Objetivos estrategicos que podem receber elevacao:\n"
        f"{json.dumps(objetivos, ensure_ascii=False, indent=1)}\n\n"
        "Acoes que ganharam corpo e ainda nao foram perguntadas:\n"
        f"{json.dumps(dossies, ensure_ascii=False, indent=1)}\n\n"
        f"Voce pode propor no maximo {rodada['restantes']} elevacao(oes) nesta rodada. "
        "Proponha menos, ou nenhuma, se o material nao sustentar."
    )


def rodar_deteccao(db, hoje: str, carga_semana, claude_key: str) -> dict:
    """Uma rodada completa: prepara, chama o modelo uma vez, grava o que passar.

    O modulo inteiro fica sem importar `firebase_functions` de proposito — o
    agendamento vive em `main.py`, junto dos outros. Assim a logica que decide
    quando e se perguntar continua testavel fora do venv de deploy, que e onde
    ela precisa estar: e ela que impede o recurso de virar praga.
    """
    try:
        import anthropic
    except ImportError:
        print("[Elevacao] Dependencia 'anthropic' nao instalada; abortando.")
        return {"rodou": False, "motivo": "sem_anthropic"}

    rodada = preparar_rodada(db, hoje, carga_semana)
    if not rodada["rodar"]:
        print(f"[Elevacao] Nada a fazer hoje: {rodada.get('motivo')}")
        return {"rodou": False, "motivo": rodada.get("motivo")}

    aceitas: list[str] = []
    tools, function_map = _ferramenta_propor(db, hoje, rodada, aceitas)
    try:
        from llm_providers import claude_provider

        resultado = claude_provider.run_tool_loop(
            client=anthropic.Anthropic(api_key=claude_key),
            model=MODELO,
            system_instruction=PERSONA,
            tools=tools,
            function_map=function_map,
            history=[],
            user_message=mensagem_da_rodada(rodada),
            max_tokens=MAX_TOKENS,
            fallback_model=MODELO_FALLBACK,
        )
    except Exception as exc:
        print(f"[Elevacao] Falha na chamada ao modelo: {exc}")
        return {"rodou": False, "motivo": "falha_no_modelo"}

    print(f"[Elevacao] Rodada concluida. propostas={len(aceitas)} "
          f"candidatas={len(rodada['candidatos'])} resumo={resultado['text'][:200]!r}")
    return {"rodou": True, "propostas": aceitas, "candidatas": len(rodada["candidatos"])}


# ---------------------------------------------------------------------------
# A alca: aceitar, adiar, nunca
# ---------------------------------------------------------------------------

DECISOES = {
    "aceitar": STATUS_ACEITA,
    "adiar": STATUS_ADIADA,
    "nunca": STATUS_NUNCA,
}


def decidir(db, sugestao_id: str, decisao: str, hoje: str,
            aplicar=None) -> dict:
    """Aplica a decisao do usuario sobre uma elevacao sugerida.

    Sem esta funcao o detector e inerte: as sugestoes aparecem na fila e nao ha
    como responder. As tres saidas do card sao a razao de ele nao virar barulho —
    principalmente "nunca", porque sem ela o sistema repete a mesma sugestao.

    Aceitar NAO cria a acao aqui. A criacao passa por `criar_acao_no_sistema`,
    que e quem sabe area tematica, deduplicacao e agenda; duplicar isso daria uma
    acao meia-boca gravada por um caminho paralelo.

    E o vinculo com o objetivo NAO vai na criacao, vai num `editar_acao` logo
    depois. Nao e capricho: nao existe um caminho de criacao de acao no Hermes,
    existem quatro reimplementacoes — handler compartilhado, adaptador do
    copiloto web, callable legada do Telegram, e o fluxo de confirmacao do
    Telegram com seu proprio callback montando um terceiro documento. Um campo
    novo passado na criacao funciona numa porta e some nas outras, em silencio.
    Dois passos explicitos valem mais que um campo que so as vezes chega.
    """
    alvo = DECISOES.get(str(decisao or "").strip().lower())
    if not alvo:
        return {"ok": False, "erro": f"Decisao invalida. Use: {', '.join(DECISOES)}."}

    ref = db.collection(COL_ELEVACOES).document(str(sugestao_id))
    try:
        ok, dados, erro = (aplicar or _aplicar_decisao)(db, ref, alvo, hoje)
    except Exception as exc:  # noqa: BLE001
        # Falhar aqui e falhar a decisao inteira, de proposito. Engolir o erro
        # deixaria a sugestao decidida com a vaga presa: nao da para repetir a
        # decisao (o status ja saiu de pendente) e a vaga nunca volta.
        return {"ok": False,
                "erro": f"A decisao nao foi gravada: {exc}. Tente de novo."}
    if not ok:
        return {"ok": False, "erro": erro}

    resposta = {"ok": True, "status": alvo, "sugestao_id": str(sugestao_id)}

    if alvo == STATUS_NUNCA:
        resposta["detalhe"] = (
            f'"{dados.get("titulo_acao")}" nao sera mais sugerida para elevacao, '
            "e a vaga do mes volta a ficar disponivel.")
    elif alvo == STATUS_ADIADA:
        resposta["detalhe"] = (
            "Adiada. A acao volta a ser candidata numa proxima varredura — "
            "'agora nao' e sobre o momento, nao sobre a acao.")
    else:
        resposta["detalhe"] = (
            "Aceita. Sao DOIS passos: crie a acao com criar_acao_no_sistema usando o "
            "rascunho abaixo e, com o id devolvido, chame editar_acao passando "
            f'estrategia_objetivo_id="{dados.get("objetivo_id")}" para vincular ao '
            f'objetivo "{dados.get("nome_objetivo")}". Sem o segundo passo a acao nasce '
            "solta, e o vinculo era o que a tornava uma elevacao.")
        resposta["rascunho_da_acao"] = {
            "titulo": str(dados.get("ativo_possivel") or "")[:120],
            "descricao": (
                f'Elevacao da acao "{dados.get("titulo_acao")}".\n'
                f'O que ja existe: {dados.get("o_que_ja_existe")}\n'
                f'Passo que falta: {dados.get("passo_que_falta")}\n'
                f'Custo estimado: {dados.get("custo_estimado")}'
            ),
        }
        resposta["vincular_depois"] = {
            "tool": "editar_acao",
            "estrategia_objetivo_id": dados.get("objetivo_id"),
            "objetivo": dados.get("nome_objetivo"),
        }
    return resposta


def _mes_da_vaga(dados: dict, hoje: str) -> str:
    """De qual mes a vaga volta: o da sugestao, nunca o de hoje.

    Recusar em setembro uma sugestao de agosto nao pode abrir vaga em setembro —
    a vaga que foi gasta foi a de agosto.
    """
    return str(dados.get("criada_em") or hoje)


def _corpo_da_decisao(transaction, ref, contador_de, alvo: str, hoje: str) -> tuple:
    """Le a sugestao, confere que ela ainda esta pendente e grava tudo de uma vez.

    Todas as leituras antes de todas as escritas, que e o que o Firestore exige
    dentro de uma transacao — inclusive a leitura do contador, cujo documento so
    da para saber depois de ler a sugestao (o mes vem dela).

    Devolve `(ok, dados, erro)`.
    """
    snap = ref.get(transaction=transaction)
    if not snap.exists:
        return False, {}, "Sugestao nao encontrada."
    dados = snap.to_dict() or {}
    if str(dados.get("status")) != STATUS_PENDENTE:
        return False, dados, f"Sugestao ja estava como '{dados.get('status')}'."

    contador, atual = None, 0
    if alvo == STATUS_NUNCA:
        # "Nunca" e ajuste de escopo, nao interrupcao gasta: a vaga volta. Sem
        # isto, tres recusas definitivas bloqueariam o resto do mes —
        # contradizendo a regra que `elevacoes_do_mes` ja aplica na leitura, e
        # deixando as duas contagens discordando entre si.
        contador = contador_de(_mes_da_vaga(dados, hoje))
        csnap = contador.get(transaction=transaction)
        atual = (csnap.to_dict() or {}).get("count", 0) if csnap.exists else 0

    transaction.update(ref, {"status": alvo, "decidida_em": hoje})
    if contador is not None:
        transaction.set(contador, {"count": max(0, int(atual or 0) - 1),
                                   "atualizado_em": hoje}, merge=True)
    return True, dados, ""


def _aplicar_decisao(db, ref, alvo: str, hoje: str) -> tuple:
    """A transicao de status e a devolucao da vaga na MESMA transacao.

    Separadas, duas chamadas concorrentes de `decidir(..., "nunca")` para a mesma
    sugestao passariam as duas pela checagem de pendente antes de qualquer uma
    gravar, e o contador seria decrementado duas vezes — subcontando o mes e
    abrindo vaga que nao existe. Nao e hipotese remota: `run_tool_loop` executa
    as tool calls de uma rodada em paralelo, num ThreadPoolExecutor, que e a
    mesma razao pela qual `reservar_no_firestore` ja e transacional.

    Juntas, tambem some o outro lado: status gravado com a devolucao falhando
    deixava a vaga presa para sempre, porque a decisao nao da para repetir.
    """
    from firebase_admin import firestore as _fs

    @_fs.transactional
    def _txn(transaction):
        return _corpo_da_decisao(transaction, ref,
                                 lambda mes: _contador_do_mes(db, mes), alvo, hoje)

    return _txn(db.transaction())


def listar_pendentes(db, limite: int = 20) -> dict:
    """As elevacoes esperando decisao, com o resumo que o usuario le.

    O filtro de status vai no Firestore, e nao depois da leitura. Limitar a
    colecao inteira e so entao procurar as pendentes funciona ate a colecao
    crescer: passado o corte, o recorte lido pode ser todo de sugestoes ja
    decididas, e esta tool responde "nao ha decisoes pendentes" enquanto o resumo
    matinal — que consulta por status — mostra que ha. Com o filtro na consulta o
    limite passa a se aplicar so ao que interessa, e o que interessa e limitado
    pelo teto mensal.
    """
    try:
        docs = list(db.collection(COL_ELEVACOES)
                    .where(filter=_filtro("status", "==", STATUS_PENDENTE))
                    .limit(200).stream())
    except Exception as exc:
        return {"total": 0, "sugestoes": [], "erro": str(exc)}
    pendentes = []
    for d in docs:
        dados = d.to_dict() or {}
        pendentes.append({
            "sugestao_id": d.id,
            "acao": dados.get("titulo_acao"),
            "objetivo": dados.get("nome_objetivo"),
            "motivo_escassez": dados.get("motivo_escassez"),
            "resumo": dados.get("resumo"),
            "criada_em": dados.get("criada_em"),
        })
    pendentes.sort(key=lambda s: str(s.get("criada_em") or ""))
    return {"total": len(pendentes), "sugestoes": pendentes[:limite]}
