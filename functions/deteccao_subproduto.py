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

# Quantos dias a varredura olha para tras quando nao ha varredura anterior
# registrada. O normal e olhar desde a ultima bem-sucedida; este e o teto do
# caso sem marcador. Existe para o PASSIVO — tudo que ja foi concluido antes
# deste recurso subir — nao entrar pela porta semanal: isso e decisao separada,
# que depende de volume.
DIAS_TETO_VARREDURA = int(os.environ.get("ELEVACAO_DIAS_VARREDURA", "7"))

MOTIVOS_ESCASSEZ = ("repetivel", "raro", "ja_escrito")

# Com acento, que e como o status e gravado e normalizado em todos os caminhos.
STATUS_CONCLUIDO = "concluído"

# Teto de documentos por consulta da varredura. Quando o de concluidas bate no
# teto, a rodada nao viu tudo que havia na janela — e o marcador nao pode avancar
# por cima do que ela nao viu.
LIMITE_TAREFAS = int(os.environ.get("ELEVACAO_LIMITE_TAREFAS", "150"))

# Quantas candidatas o modelo ve numa rodada. Recorte de prompt, nao de busca: as
# candidatas ja vem ordenadas com as de texto pronto na frente.
LIMITE_CANDIDATAS = int(os.environ.get("ELEVACAO_LIMITE_CANDIDATAS", "8"))

# O passivo — tudo que foi concluido antes de a varredura por janela existir —
# entra por cota, e nao de uma vez. Sao 618 acoes, 124 com corpo: 124 cards de
# uma vez e fila ilegivel, e fila que ninguem le mata o modulo. Entao a cota
# caminha do mais recente para o mais antigo, somada as concluidas da janela
# normal, e o usuario manda parar quando as propostas ficarem inuteis — o que
# faz as mais antigas provavelmente nunca chegarem, de proposito.
COTA_PASSIVO = int(os.environ.get("ELEVACAO_COTA_PASSIVO", "10"))

# Quantos documentos de passivo a rodada pode LER para juntar a cota. A maioria
# nao tem corpo e nunca seria candidata; sem esta folga a cota seria gasta com
# documento que ja nasce descartado, e o passivo util levaria um ano para passar.
LEITURA_PASSIVO = int(os.environ.get("ELEVACAO_LEITURA_PASSIVO", "200"))

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


def _pilar(valor) -> str:
    """Pilar comparavel: minusculas E sem acento.

    A derivacao por pilar so vale enquanto o objetivo nao tem `gerida_por_acoes`
    gravada — ou seja, exatamente nos documentos legados, que sao os que podem
    ter grafia livre. `.lower()` sozinho nao resolve: "Saude" viraria "saude",
    mas "Saúde" viraria "saúde", que continua diferente. E a grafia acentuada
    circula de fato — `main.py:4534` ja precisa tratar as duas.

    O desfecho errado aqui e o unico que o modulo diz que nao pode acontecer: o
    objetivo de saude entrando como elegivel e a fila enchendo de proposta de
    elevacao em cima de telemetria clinica.
    """
    import unicodedata

    bruto = str(valor or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", bruto)
                   if unicodedata.category(c) != "Mn")


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
        gerida = bool(gravada) if gravada is not None else _pilar(obj.get("pilar")) != "saude"
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


def _idade_da_acao(candidata: dict, corte: str) -> tuple:
    """`(concluida_em, antigo)` — e "antigo" sai da DATA, nao da lista de origem.

    A marca `passivo` diz de qual lista a candidata veio; nao e a mesma coisa que
    a idade do trabalho. O terceiro recorte traz concluidas antigas mexidas desde
    o corte, e elas chegam pela lista da janela: uma acao de 2024 com anexo novo
    e candidata da janela, `passivo` False, e o card diria nada sobre a idade.

    O corte da janela e a fronteira certa porque ja e a definicao de "desta
    varredura": conclusao anterior a ele e trabalho que o usuario pode nao
    lembrar, tenha vindo por onde tiver vindo.
    """
    concluida_em = str((candidata.get("tarefa") or {}).get("data_conclusao") or "")[:10]
    if not concluida_em:
        # Acao viva nao tem idade de conclusao — nao ha o que ressalvar.
        return "", False
    return concluida_em, bool(corte) and concluida_em < corte


def resumo_para_o_usuario(sugestao: dict, titulo_acao: str, nome_objetivo: str,
                          concluida_em: str = "", antigo: bool = False) -> str:
    """O texto do card. Nao e "considere transformar isso em artigo".

    Cada linha responde uma pergunta que o usuario faria antes de aceitar: o que
    ja existe, o que da para fazer com isso, a que objetivo serve, o que falta e
    quanto custa. Sugestao vaga e recusada sem leitura.
    """
    idade = ""
    if antigo:
        # Sem esta linha o card apresenta trabalho antigo como se fosse desta
        # semana, e o usuario aceita sem saber o que esta aceitando.
        idade = (f" (trabalho antigo, concluido em {concluida_em})" if concluida_em
                 else " (trabalho antigo)")
    return (
        f'Elevacao sugerida — acao "{titulo_acao}"{idade}\n'
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


def _dias_antes(hoje: str, dias: int) -> str:
    from datetime import date, timedelta

    ano, mes, dia = (int(x) for x in str(hoje)[:10].split("-"))
    return (date(ano, mes, dia) - timedelta(days=dias)).isoformat()


def janela_de_conclusao(ultima_varredura, hoje: str) -> tuple[str, str]:
    """De quando contar as conclusoes, e por que o corte esta onde esta.

    A ancora e a ultima varredura bem-sucedida, e nao uma janela fixa a partir de
    hoje. A diferenca aparece quando uma varredura falha ou e pulada: com janela
    fixa de 7 dias, a rodada seguinte olha so os ultimos 7 dias e o intervalo
    perdido some — e some em silencio, que e o pior jeito de perder. Ancorada na
    ultima bem-sucedida, a janela cresce sozinha para cobrir o buraco.

    O teto de `DIAS_TETO_VARREDURA` vale para o caso em que NAO ha varredura
    anterior registrada — primeira rodada, ou marcador perdido. Ali "desde a
    ultima" significaria "desde sempre", e o passivo inteiro entraria pela porta
    semanal. O passivo e uma decisao separada, que depende de volume.

    Devolve `(corte, motivo)`. `motivo` e "" quando a ancora e a varredura
    anterior, e "sem_marcador" quando o teto foi usado por falta dela — quem
    chama registra isso, porque um corte que ninguem ve e exatamente o que esta
    funcao existe para evitar.
    """
    if not ultima_varredura:
        return _dias_antes(hoje, DIAS_TETO_VARREDURA), "sem_marcador"
    return str(ultima_varredura)[:10], ""


def _marcador_de_varredura(db):
    return db.collection("system_usage").document(COL_ELEVACOES)


class MarcadorIndisponivel(Exception):
    """O marcador da varredura nao pode ser lido agora."""


def ultima_varredura(db) -> str:
    """A data da ultima varredura que chegou a olhar as candidatas.

    Documento ausente devolve vazio; falha de LEITURA levanta. A diferenca e o
    que separa duas situacoes que parecem iguais e nao sao: sem marcador, a
    janela cai no teto de dias e nao ha nada anterior a perder; com marcador
    ilegivel, a janela tambem cairia no teto — mas ai existe um intervalo real
    entre o marcador verdadeiro e o teto, e a rodada terminaria gravando hoje por
    cima dele, descartando aquelas conclusoes para sempre.

    Vazio nao e "o lado seguro" enquanto o marcador avanca no fim da rodada. Ou a
    leitura vale, ou a rodada nao acontece.
    """
    try:
        snap = _marcador_de_varredura(db).get()
    except Exception as exc:  # noqa: BLE001
        raise MarcadorIndisponivel(str(exc)) from exc
    return str((snap.to_dict() or {}).get("ultima_varredura") or "") if snap.exists else ""


def marcar_varredura(db, hoje: str) -> None:
    """Avanca o marcador — so quando a rodada avaliou a janela INTEIRA.

    "Ate aqui esta tudo avaliado" e o que o marcador significa, e por isso ele nao
    avanca em nenhuma destas:

    - a rodada parou antes de olhar candidata (historico ou marcador
      indisponivel, semana cheia, teto do mes, nenhum objetivo elegivel);
    - a consulta de concluidas falhou por falta do indice;
    - havia mais conclusoes, ou mais concluidas mexidas desde o corte, do que o
      teto por consulta.

    Nos tres, avancar apagaria conclusoes que ninguem avaliou — e apagaria de
    forma definitiva, porque a janela seguinte comeca depois delas.
    """
    try:
        _marcador_de_varredura(db).set(
            {"ultima_varredura": str(hoje)[:10]}, merge=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[Elevacao] Falha ao gravar o marcador de varredura: {exc}")


def marcar_degradacao(db, hoje: str, motivo: str) -> None:
    """Grava — ou limpa — o aviso de que a varredura viu so parte da janela.

    Dois motivos chegam aqui: `indice_ausente` (a consulta de concluidas
    levantou) e `limite_atingido` (havia mais conclusoes do que o teto por
    consulta). Os dois sao silenciosos — a varredura roda, nao levanta, e so ve
    menos — e nos dois o marcador fica parado.

    E estado, nao evento: fica no documento ate uma varredura completa limpar.
    Vai para o resumo matinal porque e la que o usuario olha; morrer no log seria
    o mesmo que nao avisar.
    """
    try:
        _marcador_de_varredura(db).set(
            {"varredura_degradada": (
                {"data": str(hoje)[:10], "motivo": motivo} if motivo else None)},
            merge=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[Elevacao] Falha ao gravar o estado da varredura: {exc}")


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


# Por que a reserva falhou. Sao respostas diferentes, e nao graus da mesma.
MOTIVO_JA_SUGERIDA = "ja_sugerida_no_mes"
MOTIVO_TETO = "teto_do_mes"
MOTIVO_FALHA = "falha_na_reserva"


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

    Devolve `(ok, motivo)`, e nao um booleano, porque as duas recusas sao
    diferentes para quem chama: colisao de id significa "esta acao ja foi
    sugerida neste mes, tente outra", e teto significa "acabou a cota da rodada".
    Fundidas num False so, o modelo ouvia "acabou a cota" quando havia vaga e
    candidata sobrando — e podia parar de propor no resto da rodada por causa de
    uma colisao esperada.
    """
    from firebase_admin import firestore as _fs

    contador = _contador_do_mes(db, hoje)

    @_fs.transactional
    def _txn(transaction):
        # A sugestao ja existir e resposta: id deterministico por acao e mes.
        if ref.get(transaction=transaction).exists:
            return False, MOTIVO_JA_SUGERIDA
        snap = contador.get(transaction=transaction)
        gravado = (snap.to_dict() or {}).get("count", 0) if snap.exists else 0
        # O contador nasceu depois das sugestoes. Enquanto ele nao existir — no
        # primeiro deploy, ou se o documento se perder — zero seria uma licenca
        # para recomecar a contagem do mes do zero com sugestoes ja na base.
        atual = max(int(gravado or 0), int(ja_no_mes or 0))
        if atual >= teto:
            return False, MOTIVO_TETO
        transaction.set(contador, {"count": atual + 1, "atualizado_em": hoje}, merge=True)
        transaction.set(ref, payload)
        return True, ""

    try:
        return _txn(db.transaction())
    except Exception as exc:
        print(f"[Elevacao] Falha ao reservar vaga do mes: {exc}")
        return False, MOTIVO_FALHA


def registrar_sugestao(db, sugestao: dict, hoje: str, titulo_acao: str,
                       nome_objetivo: str, teto: int = TETO_POR_MES,
                       reservar=reservar_no_firestore, ja_no_mes: int = 0,
                       concluida_em: str = "", antigo: bool = False) -> tuple:
    """Grava a sugestao se ainda houver vaga no mes.

    Devolve `(sugestao_id, motivo)`. `sugestao_id` e None quando nao gravou, e
    `motivo` diz qual das recusas foi — quem chama precisa da diferenca para
    responder ao modelo sem desligar o resto da rodada.

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
        # Quando o trabalho aconteceu, gravado e nao deduzido: e o que separa
        # "fiz isso esta semana" de "fiz isso ha dois anos" na hora de decidir.
        "concluida_em": concluida_em or None,
        # `antigo` e sobre a IDADE do trabalho, e nao sobre a lista de origem:
        # concluida de 2024 mexida ontem chega pela janela, nao pelo passivo.
        "antigo": bool(antigo),
        "resumo": resumo_para_o_usuario(sugestao, titulo_acao, nome_objetivo,
                                        concluida_em=concluida_em, antigo=antigo),
    }
    ok, motivo = reservar(db, hoje, teto, ref, payload, ja_no_mes)
    return (ref.id if ok else None), motivo


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
    - todo `adiada`, de qualquer epoca — nao para bloquear (adiada volta a ser
      candidata de proposito), mas porque e a unica fonte que lembra QUAIS acoes
      voltar a oferecer depois que os cursores passaram por elas;
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
            col.where(filter=_filtro("status", "in",
                                     [STATUS_PENDENTE, STATUS_ACEITA, STATUS_ADIADA])),
            col.where(filter=_filtro("criada_em", ">=", f"{_mes(hoje)}-01")),
        )
        por_id = {}
        for recorte in recortes:
            for d in recorte.stream():
                por_id[d.id] = {**(d.to_dict() or {}), "id": d.id}
        return list(por_id.values())
    except Exception as exc:
        raise HistoricoIndisponivel(str(exc)) from exc


def _tarefas_da_varredura(db, corte: str) -> list[dict]:
    """As acoes vivas mais as concluidas desde o corte.

    As concluidas precisam entrar. O docstring de `candidatas` sempre disse que
    conclusao nao filtra — "o momento certo e quando a acao ganha corpo" — mas a
    consulta as removia antes de ela ser chamada, e o caso perdido era o melhor
    de todos: acao terminada na semana e a que com mais certeza deixou documento,
    diario e etapas prontas.

    Sao tres consultas porque o Firestore nao faz OR entre elas: as vivas, as
    concluidas dentro da janela, e as concluidas ANTIGAS que foram mexidas desde
    o corte — estas ultimas porque acao concluida pode ganhar corpo depois, e sem
    o terceiro recorte elas sumiriam para sempre. A segunda depende do
    indice composto (`status`, `data_conclusao`) declarado em
    `firestore.indexes.json` — se ele nao estiver publicado, a consulta levanta e
    a varredura segue so com as vivas, avisando: e melhor perder as concluidas
    numa rodada do que a rodada inteira.

    Devolve `(tarefas, incompleta)`. `incompleta` vazia significa que a rodada viu
    TODA a janela; com valor, viu so uma parte, e diz qual e o motivo:

    - `indice_ausente`: a consulta de concluidas levantou;
    - `limite_atingido`: havia mais conclusoes na janela do que o teto por
      consulta, entao sobrou coisa que esta rodada nao avaliou.

    Nos dois casos o marcador NAO pode avancar: ele significa "ate aqui esta tudo
    avaliado", e avancar por cima do que a rodada nao viu descarta aquelas
    conclusoes para sempre. E os dois viram aviso, porque sao silenciosos —
    a varredura roda, nao levanta, e so ve menos.

    `data_conclusao` e gravado como ISO nos quatro caminhos que concluem acao
    (index.tsx no web, confirmarEdicaoAcao e confirmarEdicaoEmLote no backend, e
    a callable do Telegram), entao a comparacao lexicografica com um corte
    `AAAA-MM-DD` vale tanto para "2026-08-22" quanto para
    "2026-08-22T10:00:00Z". Acao antiga sem o campo simplesmente nao casa — e
    passivo, nao regressao.
    """
    por_id = {}
    for d in (db.collection("tarefas")
              .where(filter=_filtro("status", "in", ["em andamento", "stand-by"]))
              .limit(LIMITE_TAREFAS).stream()):
        por_id[d.id] = {**(d.to_dict() or {}), "id": d.id}
    try:
        concluidas = list(db.collection("tarefas")
                          .where(filter=_filtro("status", "==", STATUS_CONCLUIDO))
                          .where(filter=_filtro("data_conclusao", ">=", corte))
                          .limit(LIMITE_TAREFAS).stream())
    except Exception as exc:  # noqa: BLE001
        print(f"[Elevacao] Concluidas fora desta rodada ({exc}). Indice composto "
              "(status, data_conclusao) publicado?")
        return list(por_id.values()), "indice_ausente"
    for d in concluidas:
        por_id[d.id] = {**(d.to_dict() or {}), "id": d.id}

    # Terceiro recorte: concluida ANTIGA que foi mexida desde o corte.
    #
    # Acao concluida pode ganhar corpo depois — anexar_arquivo nao tem guarda de
    # status, e a tela de execucao grava `pool_dados` direto. E o caso e
    # plausivel justamente aqui: escrever o handoff depois de fechar a acao.
    #
    # Sem isto, essas acoes some para sempre: a janela olha `data_conclusao`, que
    # nao mudou, e o cursor do passivo ja passou por elas quando ainda estavam
    # vazias. `data_atualizacao` e o unico campo que reflete o anexo novo.
    try:
        mexidas = list(db.collection("tarefas")
                       .where(filter=_filtro("status", "==", STATUS_CONCLUIDO))
                       .where(filter=_filtro("data_atualizacao", ">=", corte))
                       .limit(LIMITE_TAREFAS).stream())
    except Exception as exc:  # noqa: BLE001
        print(f"[Elevacao] Concluidas mexidas fora desta rodada ({exc}). Indice "
              "composto (status, data_atualizacao) publicado?")
        return list(por_id.values()), "indice_ausente"
    for d in mexidas:
        por_id[d.id] = {**(d.to_dict() or {}), "id": d.id}

    # O teto vale para os DOIS recortes de concluidas. Conferir so o primeiro
    # deixaria a rodada se declarar completa com o terceiro truncado, e as
    # omitidas ficariam invisiveis para sempre: a atualizacao delas e anterior ao
    # marcador novo, e o cursor do passivo ja passou por elas.
    if len(concluidas) >= LIMITE_TAREFAS or len(mexidas) >= LIMITE_TAREFAS:
        print(f"[Elevacao] Mais de {LIMITE_TAREFAS} conclusoes ou atualizacoes "
              f"desde {corte}; a rodada viu so uma parte.")
        return list(por_id.values()), "limite_atingido"
    return list(por_id.values()), ""


def cursor_do_passivo(db) -> str:
    """Ate onde o passivo ja foi caminhado. Vazio = ainda nao comecou.

    Guardado como `"data|task_id"`. O id entra por causa de empate: varias acoes
    podem ter a mesma `data_conclusao` (as gravadas so com data, sem hora), e um
    cursor so de data pularia as irmas da ultima servida.
    """
    try:
        snap = _marcador_de_varredura(db).get()
    except Exception as exc:  # noqa: BLE001
        raise MarcadorIndisponivel(str(exc)) from exc
    return str((snap.to_dict() or {}).get("passivo_cursor") or "") if snap.exists else ""


def _chave(data_conclusao, task_id: str) -> tuple:
    return (str(data_conclusao or ""), str(task_id or ""))


def _cursor_para_chave(cursor: str, corte: str) -> tuple:
    """Onde o passivo continua. Sem cursor, comeca na borda da janela normal.

    O passivo e por definicao o que a janela nao alcanca, entao o inicio do
    caminho e o proprio `corte` — nao ha corte por ano. A ordem decrescente ja
    entrega primeiro o que tem valor.
    """
    if not cursor:
        return _chave(corte, "")
    data, _, task_id = str(cursor).partition("|")
    return _chave(data, task_id)


def tarefas_adiadas(db, sugestoes, limite: int = 50) -> list[dict]:
    """As acoes que o usuario adiou, buscadas por id.

    `decidir(..., "adiar")` promete que "agora nao e sobre o momento, nao sobre a
    acao". Para acao viva a promessa se cumpre sozinha: a consulta dela e por
    status e ela reaparece na rodada seguinte. Para acao CONCLUIDA nao se cumpria:
    o marcador ja tinha passado da `data_conclusao` dela, e o cursor do passivo ja
    tinha passado da chave dela — entao "adiar" virava "nunca" em silencio,
    exatamente o oposto do que o card diz.

    A sugestao adiada e a unica fonte que sobrevive aos dois cursores, porque ela
    guarda o `task_id`. Buscar por id nao depende de janela nenhuma.
    """
    ids = []
    for s in sugestoes or []:
        if not isinstance(s, dict) or str(s.get("status")) != STATUS_ADIADA:
            continue
        task_id = str(s.get("task_id") or "").strip()
        if task_id and task_id not in ids:
            ids.append(task_id)

    tarefas = []
    for task_id in ids[:limite]:
        try:
            snap = db.collection("tarefas").document(task_id).get()
        except Exception as exc:  # noqa: BLE001
            print(f"[Elevacao] Falha ao reler a acao adiada {task_id}: {exc}")
            continue
        if snap.exists:
            tarefas.append({**(snap.to_dict() or {}), "id": snap.id})
    return tarefas


def _passivo(db, corte: str, cursor: str, cota: int, decididas: dict) -> tuple:
    """A cota do passivo desta rodada, do mais recente para o mais antigo.

    Devolve `(tarefas, novo_cursor, esgotou)`.

    A cota e de CANDIDATAS, e nao de documentos lidos: das 618 concluidas do
    passivo, so 124 tem corpo. Gastar a cota com documento que `candidatas` vai
    descartar faria o passivo util levar um ano para passar. Entao a rodada le
    ate `LEITURA_PASSIVO` documentos para juntar `cota` com corpo.

    O cursor anda sobre tudo que foi LIDO, inclusive o que nao tem corpo: acao
    concluida sem corpo nao vai ganhar corpo depois, entao voltar nela toda
    semana seria caminhar no lugar.
    """
    limite_chave = _cursor_para_chave(cursor, corte)
    try:
        docs = list(db.collection("tarefas")
                    .where(filter=_filtro("status", "==", STATUS_CONCLUIDO))
                    .where(filter=_filtro("data_conclusao", "<=", limite_chave[0]))
                    .order_by("data_conclusao", direction="DESCENDING")
                    .limit(LEITURA_PASSIVO).stream())
    except Exception as exc:  # noqa: BLE001
        print(f"[Elevacao] Passivo fora desta rodada ({exc}). Indice composto "
              "(status, data_conclusao) publicado?")
        return [], cursor, False

    # O `<=` da consulta traz de volta a propria ultima servida e as irmas de
    # mesma data que ja passaram; o corte fino por (data, id) e aqui.
    # A ordenacao fina por (data, id) e feita aqui, e nao na consulta: o Firestore
    # ordena so por `data_conclusao`, e dentro de uma mesma data a ordem entre
    # documentos nao e definida. Sem isto o cursor por (data, id) compararia
    # contra uma ordem que a consulta nao garante, e acoes de mesma data seriam
    # servidas duas vezes ou puladas.
    #
    # Fica um limite conhecido: se um unico dia tiver mais conclusoes do que a
    # pagina inteira, o desempate nao alcanca as que ficaram fora da pagina.
    adiante = sorted(
        ({**(d.to_dict() or {}), "id": d.id} for d in docs),
        key=lambda t: _chave(t.get("data_conclusao"), t["id"]), reverse=True)
    adiante = [t for t in adiante
               if _chave(t.get("data_conclusao"), t["id"]) < limite_chave]

    escolhidas, ultimo_lido = [], None
    for tarefa in adiante:
        ultimo_lido = tarefa
        if tarefa["id"] not in decididas and corpo_da_acao(tarefa):
            escolhidas.append(tarefa)
            if len(escolhidas) >= cota:
                break

    if ultimo_lido is None:
        return [], cursor, True
    novo = "|".join(_chave(ultimo_lido.get("data_conclusao"), ultimo_lido["id"]))
    # Esgotou so quando a leitura inteira coube nesta rodada: se veio pagina
    # cheia, ha mais atras dela.
    esgotou = len(docs) < LEITURA_PASSIVO and len(escolhidas) < cota
    return escolhidas, novo, esgotou


def avancar_passivo(db, cursor, esgotou, restantes) -> None:
    """Guarda ate onde o passivo caminhou, e quanto sobrou.

    `restantes` fica gravado em vez de ser contado na hora pelo resumo matinal:
    a contagem e uma agregacao no Firestore, e o resumo roda todo dia enquanto a
    varredura roda uma vez por semana. O numero e "onde eu estava na ultima
    varredura", que e exatamente a pergunta.
    """
    if not cursor:
        return
    try:
        _marcador_de_varredura(db).set({
            "passivo_cursor": str(cursor),
            "passivo_restantes": restantes,
            "passivo_esgotou": bool(esgotou),
        }, merge=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[Elevacao] Falha ao gravar o cursor do passivo: {exc}")


def contar_passivo(db, cursor: str, corte: str):
    """Quantas concluidas ainda estao atras do cursor. `None` quando nao da para contar.

    Vai para o resumo matinal, e nao so para o log: uma cota que caminha sem
    dizer quanto falta nao deixa ninguem decidir quando mandar parar — e mandar
    parar e exatamente como este caminho termina.

    `None` e honesto: melhor a tela nao mostrar numero do que mostrar um errado.
    """
    data, task_id = _cursor_para_chave(cursor, corte)
    try:
        base = (db.collection("tarefas")
                .where(filter=_filtro("status", "==", STATUS_CONCLUIDO)))
        # Datas estritamente anteriores contam inteiras.
        total = int(base.where(filter=_filtro("data_conclusao", "<", data))
                    .count().get()[0][0].value)
        # No dia do cursor, so as que ainda estao atras dele. Contar o dia inteiro
        # incluiria o proprio cursor e as irmas ja percorridas, e `restantes`
        # ficaria travado num numero que nunca desce — o oposto de "onde estou".
        if task_id:
            for d in base.where(filter=_filtro("data_conclusao", "==", data)).stream():
                if _chave(data, d.id) < (data, task_id):
                    total += 1
        return total
    except Exception as exc:  # noqa: BLE001
        print(f"[Elevacao] Nao foi possivel contar o passivo: {exc}")
        return None


def viu_todas_as_concluidas(candidatos, limite: int = LIMITE_CANDIDATAS) -> bool:
    """Se alguma candidata CONCLUIDA ficou fora do que o modelo viu.

    A assimetria e o ponto. `mensagem_da_rodada` mostra so as primeiras `limite`
    candidatas, e as que sobram nao correm o mesmo risco:

    - acao viva sobrando volta sozinha na proxima rodada, porque a consulta dela
      e por status e nao tem data nenhuma;
    - acao concluida sobrando so existe dentro da janela, e a janela anda com o
      marcador. Se ele avancar, ela nunca mais e candidata.

    Entao o marcador espera pelas concluidas e nao pelas vivas. Exigir todas
    travaria o marcador em qualquer semana movimentada, que e o caso normal, e
    nao o defeituoso.

    Candidata de passivo tambem nao segura: ela nao vem da janela e nao depende
    do marcador — tem cursor proprio. Confundir os dois travaria o marcador para
    sempre, porque quase sempre sobra passivo.

    Nem a readmitida por "adiar", pelo mesmo motivo e por um pior: ela volta pelo
    `task_id` da sugestao, entao o marcador nao a alcanca. E como adiada nao
    expira, elas se ACUMULAM em `candidatos` — bastariam algumas concluidas
    adiadas para o marcador nunca mais avancar. Uma correcao travando a outra.
    """
    return not any(
        str((c.get("tarefa") or {}).get("status")) == STATUS_CONCLUIDO
        and not c.get("passivo")
        and not c.get("readmitida")
        for c in (candidatos or [])[limite:]
    )


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

    try:
        marcador = ultima_varredura(db)
    except MarcadorIndisponivel as exc:
        # Mesma logica do historico: sem saber onde a janela comeca, a rodada nao
        # pode terminar gravando onde ela acaba.
        print(f"[Elevacao] Marcador indisponivel, rodada abortada: {exc}")
        return {"rodar": False, "motivo": "marcador_indisponivel"}

    try:
        cursor_passivo = cursor_do_passivo(db)
    except MarcadorIndisponivel as exc:
        print(f"[Elevacao] Marcador indisponivel, rodada abortada: {exc}")
        return {"rodar": False, "motivo": "marcador_indisponivel"}

    corte, motivo_do_corte = janela_de_conclusao(marcador, hoje)
    if motivo_do_corte:
        print(f"[Elevacao] Sem marcador de varredura anterior; conclusoes contadas "
              f"a partir de {corte} ({DIAS_TETO_VARREDURA} dias). O que foi "
              f"concluido antes disso e passivo, e nao entra por aqui.")
    decididas = acoes_ja_decididas(sugestoes)
    tarefas, incompleta = _tarefas_da_varredura(db, corte)
    # As adiadas voltam por id, e nao por janela: os cursores ja passaram por elas.
    # Uniao por id — uma acao viva adiada vem pelos dois caminhos, e candidata
    # repetida viraria dossie repetido no mesmo prompt.
    por_id = {t["id"]: t for t in tarefas}
    so_por_id = set()
    for t in tarefas_adiadas(db, sugestoes):
        if t["id"] not in por_id:
            por_id[t["id"]] = t
            so_por_id.add(t["id"])
    candidatos = candidatas(list(por_id.values()), decididas, hoje)
    # Quem so chegou pela releitura por id nao veio da janela, e por isso nao pode
    # segurar o marcador — ela volta pelo id na proxima rodada de qualquer jeito.
    for c in candidatos:
        if c["task_id"] in so_por_id:
            c["readmitida"] = True
    # "Ate aqui esta tudo avaliado" e o que o marcador significa, e ele so avanca
    # quando isso for verdade de ponta a ponta: a busca precisa ter trazido a
    # janela inteira, E o prompt precisa ter mostrado toda concluida que veio.
    if not incompleta and not viu_todas_as_concluidas(candidatos):
        incompleta = "candidatas_demais"
    marcar_degradacao(db, hoje, incompleta)
    pode_marcar = not incompleta

    # O passivo entra por fora da janela e com vagas proprias no prompt, para nao
    # disputar espaco com o trabalho da semana — que e o mais fresco e o que o
    # usuario lembra de ter feito.
    passivo_tarefas, cursor_novo, passivo_esgotou = _passivo(
        db, corte, cursor_passivo, COTA_PASSIVO, decididas)
    passivo = [{**c, "passivo": True}
               for c in candidatas(passivo_tarefas, decididas, hoje)]

    if not candidatos and not passivo:
        # Olhou e nao achou: a varredura cumpriu o papel, entao o marcador avanca.
        # Nao avancar aqui faria a janela crescer sem parar num sistema saudavel.
        return {"rodar": False, "motivo": "nenhuma_acao_com_corpo",
                "pode_marcar": pode_marcar, "passivo_cursor": cursor_novo,
                "passivo_esgotou": passivo_esgotou}

    return {
        "rodar": True,
        "restantes": veredito["restantes"],
        "ja_no_mes": elevacoes_do_mes(sugestoes, hoje),
        "objetivos": objetivos,
        "candidatos": candidatos,
        "passivo": passivo,
        "passivo_cursor": cursor_novo,
        "passivo_esgotou": passivo_esgotou,
        "corte_conclusao": corte,
        "pode_marcar": pode_marcar,
    }


# O que o modelo ouve em cada recusa. A diferenca importa: "ja sugerida" pede
# outra candidata, "teto" encerra a rodada. Dizer teto nas duas fazia o modelo
# desistir do resto quando so tinha havido uma colisao esperada.
_RECUSAS = {
    MOTIVO_JA_SUGERIDA: ("esta acao ja foi sugerida neste mes; escolha OUTRA "
                         "candidata — ainda ha vaga nesta rodada"),
    MOTIVO_TETO: "teto do mes ja atingido; nao proponha mais nesta rodada",
    MOTIVO_FALHA: ("nao foi possivel gravar agora; tente outra candidata ou "
                   "encerre a rodada"),
}


def _ferramenta_propor(db, hoje: str, rodada: dict, aceitas: list,
                      reservar=reservar_no_firestore):
    """A tool de escrita. A validacao mora AQUI, e nao na confianca no modelo.

    O teto e a lista de objetivos validos sao conferidos no momento da gravacao:
    o modelo pode alucinar um id, insistir depois do limite, ou apontar um
    objetivo servido por dado. Qualquer uma dessas passaria se a checagem
    estivesse so no prompt.

    `rodada["ja_no_mes"]` vem do historico lido em `preparar_rodada`, e e o piso
    da contagem: o contador transacional pode nao existir ainda.
    """
    objetivos_por_id = {o["id"]: o for o in rodada["objetivos"]}
    # As duas listas, e nao so `candidatos`. O passivo aparece no prompt por vaga
    # propria; se ele nao entrasse aqui, `validar_proposta` recusaria todo id de
    # passivo como inexistente — a cota inteira viraria um no-op que ainda por
    # cima avanca o cursor, descartando aquelas acoes em silencio.
    todas = list(rodada["candidatos"]) + list(rodada.get("passivo") or [])
    titulos = {c["task_id"]: str(c["tarefa"].get("titulo") or "") for c in todas}
    # Quando a acao foi concluida, e se ela veio do passivo. O card precisa disso:
    # sugestao sobre trabalho de 2024 apresentada igual a de trabalho desta semana
    # faz o usuario aceitar sem saber o que esta aceitando. Instruir o modelo a
    # dizer isso na justificativa nao basta — neste modulo a validacao mora na
    # gravacao, e nao na confianca no prompt.
    corte = str(rodada.get("corte_conclusao") or "")[:10]
    quando = {c["task_id"]: _idade_da_acao(c, corte) for c in todas}

    def propor_elevacao(**kwargs) -> dict:
        sugestao = validar_proposta(kwargs, set(objetivos_por_id), set(titulos))
        if not sugestao:
            return {"aceita": False, "motivo": "proposta incompleta, id invalido ou justificativa generica"}
        objetivo = objetivos_por_id[sugestao["objetivo_id"]]
        # O teto e conferido dentro da transacao, e nao aqui: esta funcao roda em
        # paralelo com as outras tool calls da mesma rodada.
        concluida_em, e_antigo = quando.get(sugestao["task_id"], ("", False))
        sugestao_id, motivo = registrar_sugestao(
            db, sugestao, hoje, titulos[sugestao["task_id"]],
            str(objetivo.get("objetivoMacro") or ""), reservar=reservar,
            ja_no_mes=int(rodada.get("ja_no_mes") or 0),
            concluida_em=concluida_em, antigo=e_antigo,
        )
        if not sugestao_id:
            return {"aceita": False, "motivo": _RECUSAS.get(motivo, _RECUSAS[MOTIVO_FALHA])}
        aceitas.append(sugestao_id)
        return {"aceita": True, "sugestao_id": sugestao_id}

    tools = [{
        "name": "propor_elevacao",
        "description": ("Registra UMA elevacao sugerida. So chame quando conseguir preencher "
                        "todos os campos com material que existe de fato na acao."),
        "input_schema": _SCHEMA_PROPOSTA,
    }]
    return tools, {"propor_elevacao": propor_elevacao}


def mensagem_da_rodada(rodada: dict, limite_candidatos: int = LIMITE_CANDIDATAS) -> str:
    """O que o modelo ve: os objetivos elegiveis e o material de cada candidata.

    As candidatas de passivo vem marcadas e em vagas proprias — sao trabalho
    antigo, e o modelo precisa saber disso para calibrar a proposta.
    """
    import json

    objetivos = [
        {"objetivo_id": o["id"], "pilar": o.get("pilar"),
         "objetivo": o.get("objetivoMacro"),
         "diretrizes": (o.get("diretrizesDerivadas") or [])[:4]}
        for o in rodada["objetivos"]
    ]
    # Vagas separadas de proposito. Somar as duas listas e cortar faria o passivo
    # — que e sempre mais antigo — perder toda disputa de ordenacao contra o
    # trabalho da semana, e a cota nunca sairia do lugar.
    dossies = [montar_dossie(c) for c in rodada["candidatos"][:limite_candidatos]]
    dossies += [{**montar_dossie(c), "passivo": True}
                for c in (rodada.get("passivo") or [])]
    return (
        "Objetivos estrategicos que podem receber elevacao:\n"
        f"{json.dumps(objetivos, ensure_ascii=False, indent=1)}\n\n"
        "Acoes que ganharam corpo e ainda nao foram perguntadas. As marcadas como "
        "passivo sao trabalho antigo, recuperado aos poucos — o material vale o "
        "mesmo, mas o usuario pode ja nem lembrar delas, entao a frase de "
        "justificativa precisa situar quando aquilo aconteceu:\n"
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
        # O marcador so avanca quando a rodada chegou a olhar as candidatas.
        # "Semana cheia" e "teto do mes" nao olharam nada: avancar ali apagaria
        # em silencio as conclusoes daquele intervalo, que e o modo de perda que
        # a janela ancorada existe para impedir.
        if rodada.get("pode_marcar"):
            marcar_varredura(db, hoje)
        if rodada.get("passivo_cursor"):
            # Mesmo corte do caminho de sucesso. Hoje o terceiro argumento so e
            # lido quando o cursor esta vazio — e aqui ele nunca esta, por causa
            # da guarda acima —, mas duas chamadas com argumentos diferentes para
            # a mesma coisa viram contagem errada assim que a guarda mudar.
            avancar_passivo(db, rodada["passivo_cursor"], rodada.get("passivo_esgotou"),
                            contar_passivo(db, rodada["passivo_cursor"],
                                           rodada.get("corte_conclusao") or hoje))
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
        # Sem avancar o marcador: as candidatas desta rodada nao foram julgadas,
        # e tem de continuar elegiveis na proxima.
        return {"rodou": False, "motivo": "falha_no_modelo"}

    if rodada.get("pode_marcar"):
        marcar_varredura(db, hoje)
    # O cursor do passivo anda por conta propria: ele nao depende da janela, e as
    # candidatas de passivo tem vaga garantida no prompt, entao o que a rodada
    # leu foi de fato oferecido ao modelo.
    avancar_passivo(db, rodada.get("passivo_cursor"), rodada.get("passivo_esgotou"),
                    contar_passivo(db, rodada.get("passivo_cursor") or "",
                                   rodada.get("corte_conclusao") or hoje))
    print(f"[Elevacao] Rodada concluida. propostas={len(aceitas)} "
          f"candidatas={len(rodada['candidatos'])}+{len(rodada.get('passivo') or [])} "
          f"conclusoes_desde={rodada.get('corte_conclusao')} "
          f"resumo={resultado['text'][:200]!r}")
    return {"rodou": True, "propostas": aceitas,
            "candidatas": len(rodada["candidatos"]),
            "candidatas_passivo": len(rodada.get("passivo") or [])}


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
            "concluida_em": dados.get("concluida_em"),
            "antigo": bool(dados.get("antigo")),
        })
    pendentes.sort(key=lambda s: str(s.get("criada_em") or ""))
    return {"total": len(pendentes), "sugestoes": pendentes[:limite]}
