"""Aceitar ou descartar uma sugestão de elevação pelo Painel do dia.

A decisão é a de `deteccao_subproduto.decidir` (mesma transação, mesma devolução
da vaga no "nunca"); este módulo só acrescenta o que o agente faz à mão depois do
"aceitar": criar a ação e vinculá-la ao objetivo. São os dois passos que
`decidir_elevacao` deixa para quem chama, e a tela não tem quem os faça.

Na tela, "Descartar" é `nunca` (a sugestão não volta e a vaga do mês é devolvida).

Se a ação não puder ser criada depois do "aceitar", a sugestão volta a `pendente`:
o André não fica com uma sugestão decidida e sem ação, que não dá para repetir.
"""

from __future__ import annotations

import deteccao_subproduto as ds

DECISOES_DA_TELA = {"aceitar": "aceitar", "descartar": "nunca"}


def _area_da_acao_de_origem(db, dados: dict) -> str:
    task_id = str(dados.get("task_id") or "").strip()
    if task_id:
        try:
            snap = db.collection("tarefas").document(task_id).get()
            area = str((snap.to_dict() or {}).get("area_tematica") or "").strip() if snap.exists else ""
            if area:
                return area
        except Exception as exc:  # noqa: BLE001 - a area e conforto, nao motivo para recusar
            print(f"[elevacao_pela_tela] area da acao de origem indisponivel: {exc}")
    return "GERAL"


def decidir_pela_tela(db, sugestao_id: str, decisao: str, hoje: str, *, criar_acao, vincular) -> dict:
    """`decisao`: `aceitar` ou `descartar`.

    `criar_acao(args) -> str` devolve a resposta de `criar_acao_no_sistema`
    (`OK|<id>` ou `ERRO|...`); `vincular(task_id, objetivo_id) -> dict` aplica o
    `editar_acao`. Entram por parâmetro para o teste não depender do Firestore.
    """
    alvo = DECISOES_DA_TELA.get(str(decisao or "").strip().lower())
    if not alvo:
        return {"ok": False, "erro": "Decisao invalida. Use aceitar ou descartar."}
    sugestao_id = str(sugestao_id or "").strip()
    if not sugestao_id:
        return {"ok": False, "erro": "Informe a sugestao."}

    ref = db.collection(ds.COL_ELEVACOES).document(sugestao_id)
    antes = ref.get()
    origem = (antes.to_dict() or {}) if antes.exists else {}

    res = ds.decidir(db, sugestao_id, alvo, hoje)
    if not res.get("ok") or alvo != "aceitar":
        return res

    rascunho = res.get("rascunho_da_acao") or {}
    objetivo_id = (res.get("vincular_depois") or {}).get("estrategia_objetivo_id")

    def _desfazer(motivo: str) -> dict:
        try:
            ref.update({"status": ds.STATUS_PENDENTE, "decidida_em": None})
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "erro": f"{motivo} E nao consegui devolver a sugestao a pendente ({exc}); "
                                         "avise o agente para conferir.", "rascunho_da_acao": rascunho}
        return {"ok": False, "erro": f"{motivo} A sugestao continua pendente."}

    try:
        criada = str(criar_acao({
            "titulo": rascunho.get("titulo"),
            "descricao": rascunho.get("descricao"),
            "area_tematica": _area_da_acao_de_origem(db, origem),
            "data_limite": hoje,
        }) or "")
    except Exception as exc:  # noqa: BLE001
        return _desfazer(f"Nao foi possivel criar a acao: {exc}.")
    if not criada.startswith("OK|"):
        return _desfazer(f"Nao foi possivel criar a acao: {criada.removeprefix('ERRO|')}.")
    task_id = criada.split("|", 1)[1].strip()

    if objetivo_id:
        try:
            vinculo = vincular(task_id, objetivo_id)
            if isinstance(vinculo, dict) and vinculo.get("erro"):
                raise RuntimeError(vinculo["erro"])
        except Exception as exc:  # noqa: BLE001
            # A acao existe: nao se cria de novo. Fica aceita, com o aviso do que falta.
            return {"ok": True, "status": ds.STATUS_ACEITA, "sugestao_id": sugestao_id, "task_id": task_id,
                    "aviso": f"Acao criada, mas o vinculo com o objetivo falhou ({exc}). Vincule pelo agente."}
    return {"ok": True, "status": ds.STATUS_ACEITA, "sugestao_id": sugestao_id, "task_id": task_id}
