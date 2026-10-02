"""`registrar_observacao_externa` — P05 passo 9 do plano de autonomia
(docs/plano-hermes-autonomo-2026-09-06.md): "Implementar
registrar_observacao_externa para fatos vindos de conectores do Claude,
guardando origem e nível de verificação."

## O problema que isto resolve

Um cliente Claude com OUTROS conectores instalados (Google Drive, Gmail,
Calendar, um CRM, etc.) às vezes descobre um fato relevante por um caminho que
o Hermes não tem — ex.: lê um e-mail por um conector de terceiros, confere uma
data num sistema externo, recebe um documento por um canal que o Hermes não
assina. Hoje não há onde guardar "o conector X me disse Y sobre Z, na hora W"
sem ou (a) inventar uma tool que grava esse fato como se fosse uma preferência
do usuário ou uma memória confiável, ou (b) perder a informação porque não
coube em nenhuma tool existente.

## Decisão de escopo desta sub-entrega (registrada aqui e no diário)

O plano (seção 4.2, tabela "Memória") sugere estender `knowledge_nodes`/
`knowledge_edges` com campos como `claim_type`, `subject`, `predicate`,
`evidence_refs`. Essa linha da tabela NÃO tem pacote atribuído (ao contrário
de quase todas as outras linhas da seção 6.2, que dizem "P04"/"P05" etc.
explicitamente) — e `knowledge_graph.py` hoje é inteiramente sobre
embeddings e o "Dual-Pass" que cristaliza TAREFAS CONCLUÍDAS por similaridade
semântica (ver `knowledge_graph.py` linhas 1-28 e `_crystallize_task`). Gravar
uma observação externa crua ali, sem embedding e sem relação com tarefa
concluída nenhuma, misturaria dois propósitos diferentes do módulo.

Esta sub-entrega usa uma coleção NOVA e ISOLADA (`observacoes_externas`), sem
tocar `knowledge_graph.py`. A garantia do contrato ("não vira
preferência/autorização") nasce por OMISSÃO: nenhum código deste módulo lê
ou escreve `knowledge_nodes`, `memorias_globais`, `autonomy_policies` ou
qualquer coleção consultada por `salvar_memoria_global`,
`resolver_conflito_memoria` ou `autonomy/policy.py`. Não existe hoje um
mecanismo ativo (ex. um campo imutável `pode_virar_preferencia: false`) que
IMPEDIRIA uma sub-entrega futura de promover isto a memória por engano — só
o fato de que nada hoje lê esta coleção para decidir uma política ou
responder por uma preferência do usuário. Registrado aqui para que uma
sub-entrega futura que precise ler `observacoes_externas` saiba que essa
garantia é estrutural (isolamento), não imposta por um campo de dados.

## "Nível de verificação" — vocabulário novo, sem precedente no código

O contrato da seção 6.2 do plano não lista um campo de verificação — só
"fonte, ID/URL, horário, artefato/hash e assunto". O passo 9 da lista do
pacote (seção 9) pede, além da fonte, "nível de verificação", sem definir um
enum. Não há precedente a reaproveitar (`trust_level`, mencionado na seção
4.2 para a entidade `autonomy_events`, é uma coleção "Nova" que ainda não
existe). Esta sub-entrega define dois valores, deliberadamente honestos sobre
o que o Hermes de fato sabe:

- `nao_verificado` (padrão): o cliente relatou o fato; o Hermes não conferiu
  nada.
- `verificado_pelo_cliente`: o próprio cliente/conector AFIRMA ter conferido
  o fato contra uma fonte confiável antes de reportar. O Hermes continua sem
  verificação própria — este nível não promove o fato a "confirmado pelo
  Hermes", só registra uma alegação mais forte do lado de quem relatou.

Nenhum consumidor deste módulo deve tratar `verificado_pelo_cliente` como
prova. Isso é deliberado: o plano (seção 4.1) exige distinguir dado
observado, relato humano, inferência e previsão — este campo é só a segunda
categoria (relato), em dois graus de confiança autodeclarada.
"""

from __future__ import annotations

NIVEIS_VERIFICACAO = ("nao_verificado", "verificado_pelo_cliente")
NIVEL_VERIFICACAO_PADRAO = "nao_verificado"

COL_OBSERVACOES = "observacoes_externas"

_CAMPOS_RELIDOS = (
    "fonte",
    "assunto",
    "horario",
    "id_ou_url",
    "artefato_hash",
    "nivel_verificacao",
    "registrado_por",
    "schema_version",
)


def _texto_obrigatorio(args: dict, campo: str) -> tuple[str | None, str | None]:
    """Devolve `(valor, erro)`; exatamente um dos dois é `None`."""
    bruto = args.get(campo)
    valor = str(bruto).strip() if bruto is not None else ""
    if not valor:
        return None, f"`{campo}` é obrigatório. Nada foi gravado."
    return valor, None


def registrar(ctx, args: dict) -> dict:
    """Registra, numa coleção isolada, um fato relatado por OUTRO conector do
    cliente Claude — nunca uma preferência, memória ou autorização.

    Não lê nem escreve em nenhuma coleção de memória, política ou
    autorização: só grava o relato com proveniência e relê o mesmo documento
    para confirmar (D07 do plano — evidência define conclusão, nunca texto
    do agente ou HTTP 200)."""
    campos_erro: list[str] = []
    valores: dict[str, str] = {}
    for campo in ("fonte", "assunto", "horario"):
        valor, erro = _texto_obrigatorio(args, campo)
        if erro:
            campos_erro.append(erro)
        else:
            valores[campo] = valor
    if campos_erro:
        return {"erro": " ".join(campos_erro), "aplicado": False}

    nivel = str(args.get("nivel_verificacao") or NIVEL_VERIFICACAO_PADRAO).strip()
    if nivel not in NIVEIS_VERIFICACAO:
        return {
            "erro": (
                f"`nivel_verificacao` = {nivel!r} não é um valor aceito. "
                f"Use um de: {', '.join(NIVEIS_VERIFICACAO)}. Nada foi gravado."
            ),
            "aplicado": False,
        }

    def _texto_opcional(campo: str) -> str | None:
        bruto = args.get(campo)
        valor = str(bruto).strip() if bruto is not None else ""
        return valor or None

    id_ou_url = _texto_opcional("id_ou_url")
    artefato_hash = _texto_opcional("artefato_hash")

    from firebase_admin import firestore

    documento = {
        "fonte": valores["fonte"],
        "assunto": valores["assunto"],
        "horario": valores["horario"],
        "id_ou_url": id_ou_url,
        "artefato_hash": artefato_hash,
        "nivel_verificacao": nivel,
        "registrado_por": {
            "user_uid": ctx.user_uid,
            "canal": ctx.canal,
            "session_id": ctx.session_id,
        },
        "schema_version": 1,
        # occurred_at (`horario`, texto livre do chamador) e ingested_at
        # (este timestamp do servidor) sao deliberadamente distintos --
        # plano, secao 4.1: "Separar occurred_at de ingested_at".
        "ingested_at": firestore.SERVER_TIMESTAMP,
    }

    ref = ctx.db.collection(COL_OBSERVACOES).document()
    try:
        ref.set(documento)
    except Exception as exc_set:
        # A excecao do SDK NAO prova que nada foi gravado: um timeout/deadline
        # pode ter ocorrido depois que o Firestore ja confirmou a escrita no
        # servidor, so sem o cliente receber a resposta (achado da revisao
        # adversarial externa, Codex, P2). Tenta reler pela mesma referencia
        # antes de afirmar "nada foi gravado".
        try:
            snap_apos_falha = ref.get()
        except Exception as exc_get_verificacao:
            # A releitura de verificação TAMBÉM falhou -- isto é diferente de
            # "confirmei que o documento não existe". Não afirmar nenhum dos
            # dois lados (nem aplicado=True, nem aplicado=False): o chamador
            # precisa checar antes de repetir, já que a tool não é idempotente.
            return {
                "erro": (
                    f"falha ao gravar ({exc_set}) e a releitura de verificação "
                    f"também falhou ({exc_get_verificacao}) -- não dá para "
                    "confirmar se a observação foi gravada ou não. NÃO repita a "
                    "mesma chamada sem checar antes: o documento pode já existir "
                    f"em {COL_OBSERVACOES}/{ref.id}."
                ),
                "resultado": "desconhecido",
                "observacao_id": ref.id,
            }
        if snap_apos_falha.exists:
            relido_apos_falha = snap_apos_falha.to_dict() or {}
            return {
                "status": "completed",
                "observacao_id": ref.id,
                **{campo: relido_apos_falha.get(campo) for campo in _CAMPOS_RELIDOS},
                "nota": (
                    "A chamada de gravação reportou uma falha "
                    f"({exc_set}), mas a releitura confirma que a observação FOI "
                    f"gravada ({COL_OBSERVACOES}/{ref.id}). Isolada, não cria nem "
                    "altera preferência, memória ou autorização."
                ),
            }
        return {
            "erro": (
                f"falha ao gravar ({exc_set}); a releitura confirma que o "
                "documento NÃO existe -- nada foi gravado."
            ),
            "aplicado": False,
        }

    try:
        relido_snap = ref.get()
    except Exception as exc:
        return {
            "erro": (
                f"a observação FOI gravada ({COL_OBSERVACOES}/{ref.id}), mas não consegui "
                f"reler para confirmar ({exc})."
            ),
            "aplicado": True,
            "observacao_id": ref.id,
        }
    relido = (relido_snap.to_dict() or {}) if relido_snap.exists else {}
    if not relido_snap.exists:
        return {
            "erro": (
                f"a observação FOI gravada ({COL_OBSERVACOES}/{ref.id}), mas não aparece ao "
                "reler o banco imediatamente após gravar."
            ),
            "aplicado": True,
            "observacao_id": ref.id,
        }

    return {
        "status": "completed",
        "observacao_id": ref.id,
        **{campo: relido.get(campo) for campo in _CAMPOS_RELIDOS},
        "nota": (
            "Observação registrada com proveniência, isolada em "
            f"`{COL_OBSERVACOES}`. Isto NÃO cria nem altera preferência, memória "
            "ou autorização — nenhum outro módulo lê esta coleção."
        ),
    }
