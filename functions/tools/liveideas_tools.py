"""Ferramentas do Live Ideas no conector MCP do Gaspar.

Cada ferramenta manda uma ação ao notebook pelo canal `/gaspar`
(`liveideas.comando`, que já confere se o notebook está ligado e espera até
20 s) e devolve um dict curto. `reuniao_id`/`processo_id` das ferramentas
viram `reuniao`/`processo` do canal; a validação dos ids é do notebook.

Gerar e ajustar levam mais que uma chamada: `gerar`/`ajustar` gravam um pedido
em `liveideas_pedidos/{id}` (só depois da resposta do notebook) e o Claude
acompanha com `consultar`. Com `task_id`, o resultado pronto vai para a ação
uma vez só: `anexado` é marcado em transação ANTES de anexar, então duas
consultas simultâneas não anexam duas vezes.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from firebase_admin import firestore

import liveideas

COLECAO = "liveideas_pedidos"
ORIENTACAO = "consulte com liveideas_consultar em uns 30 segundos"
_NAO_ENCONTRADO = "pedido não encontrado"
_ROTULO = {"processo": "Processo", "fluxo": "Fluxo", "mapa": "Mapa de ideias"}
DIARIO_MAX = 20  # entradas do diário que vão no grafo: o `obter_acao` mostra 20 por padrão e o Live Ideas usa só as 5 últimas
_DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
# começo das notas que o `_anexar` escreve no diário ("<Rótulo> gerado no Live Ideas: ..."): não são conteúdo da ação
_NOTA_DE_LINK = tuple(f"{r} gerado no Live Ideas:" for r in (*_ROTULO.values(), "Diagrama"))
_NOTA_DE_ARQUIVO = "FILE::"  # arquivo anexado, guardado como "FILE::JSON::{...}": não é texto da ação
_BRASILIA = ZoneInfo("America/Sao_Paulo")


def _sem_vazios(dados: dict) -> dict:
    """Tira os ausentes: None e texto vazio ou só com espaços (o Claude manda "" para "nenhum")."""
    return {k: v for k, v in dados.items() if v is not None and not (isinstance(v, str) and not v.strip())}


def _enviar(ctx, acao: str, corpo: dict) -> tuple[dict | None, dict | None]:
    """`(resposta, None)` com 200; `(None, {"erro": ...})` em qualquer outro caso."""
    try:
        status, resp = liveideas.comando(liveideas.banco_liveideas(ctx.db), acao, corpo)
    except liveideas.LiveIdeasIndisponivel as exc:
        return None, {"erro": exc.mensagem}
    if status != 200:
        return None, {"erro": str(resp.get("erro") or f"o Live Ideas recusou o pedido ({status})")}
    return resp, None


def _alvo(args: dict) -> dict:
    return _sem_vazios({"reuniao": args.get("reuniao_id"), "processo": args.get("processo_id")})


def _ids(pedido: dict) -> dict:
    return _sem_vazios({"reuniao_id": pedido.get("reuniao"), "processo_id": pedido.get("processo")})


def _criar_pedido(ctx, dados: dict) -> str:
    ref = ctx.db.collection(COLECAO).document()
    ref.set(_sem_vazios({"uid": ctx.user_uid, **dados, "criado": firestore.SERVER_TIMESTAMP, "anexado": False}))
    return ref.id


def _dia_de_brasilia(data: str) -> str | None:
    """AAAA-MM-DD, no horário de Brasília, da data do diário (o `obter_acao` a entrega em UTC); None se não houver data.
    Sem hora e fuso não há o que converter: fica o dia como está escrito."""
    try:
        quando = datetime.fromisoformat(data)
    except ValueError:  # entrada sem data chega como "None"
        quando = None
    if quando is not None and quando.tzinfo is not None:
        return quando.astimezone(_BRASILIA).strftime("%Y-%m-%d")
    achada = _DATA_ISO.match(data)
    return achada[0] if achada else None


def _acao_do_gaspar(ctx, acao_id: str) -> dict | None:
    """A ação no formato do campo `acao` do Live Ideas, ou None se não existir.
    Lê pelo `obter_acao` (etapa inteira, sem corte; diário do mais antigo ao mais novo); as datas do diário saem
    em Brasília (as de lá vêm em UTC, e uma nota das 22h de domingo viraria segunda)."""
    from tools import hermes_tools  # aqui dentro: o hermes_tools é quem carrega este módulo

    a = hermes_tools.obter_acao(ctx, {"task_id": acao_id, "limite_diario": DIARIO_MAX})
    if a.get("status") == "not_found":
        return None
    diario = []
    for e in a["diario"]:
        nota = str(e.get("nota") or "").strip()
        if nota and not nota.startswith((*_NOTA_DE_LINK, _NOTA_DE_ARQUIVO)):  # link de grafo anterior e anexo não viram nó
            dia = _dia_de_brasilia(e["data"])
            diario.append({"texto": f"[{dia}] {nota}" if dia else nota})
    return {"id": a["id"], "titulo": a.get("titulo") or "", "descricao": a["descricao"], "notas": a["notas"],
            "plano_acao": [{"texto": e["texto"], "estado": e["estado"]} for e in a["plano_acao"]],
            "diario": diario}


def _corpo_da_acao(ctx, args: dict, acao_id: str) -> tuple[dict | None, dict | None]:
    """`(corpo do gerar, None)` ou `(None, {"erro": ...})`. Tudo que dá para recusar sem ler a ação vem antes."""
    if "/" in acao_id:  # "/" mudaria o caminho no Firestore
        return None, {"erro": "acao_id inválido: informe o id da ação do Gaspar, sem barra"}
    if _sem_vazios({"texto": args.get("texto"), "reuniao_id": args.get("reuniao_id")}):
        return None, {"erro": "com acao_id não informe texto nem reuniao_id: o grafo sai da própria ação"}
    if args.get("tipo") != "mapa":
        return None, {"erro": "acao_id só vale para tipo=mapa"}
    acao = _acao_do_gaspar(ctx, acao_id)
    if acao is None:
        return None, {"erro": f"ação {acao_id!r} não encontrada no Gaspar"}
    refazer = _incluir_transcricao(args.get("refazer")) or None  # só vai quando verdadeiro (aceita "true" como lá)
    agrupar = _incluir_transcricao(args.get("agrupar_concluidas")) or None  # idem
    return _sem_vazios({"tipo": "mapa", "acao": acao, "titulo": args.get("titulo"), "refazer": refazer,
                        "agrupar_concluidas": agrupar}), None


def gerar(ctx, args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip() or None  # vazio ou só espaços: sem ação
    acao_id = str(args.get("acao_id") or "").strip() or None
    if acao_id:
        corpo, erro = _corpo_da_acao(ctx, args, acao_id)
        if erro:
            return erro
        task_id = acao_id  # o consultar anexa o link na própria ação
    else:
        if _incluir_transcricao(args.get("agrupar_concluidas")):
            return {"erro": "agrupar_concluidas só vale com acao_id"}
        if task_id and "/" in task_id:  # "/" mudaria o caminho no Firestore
            return {"erro": "task_id inválido: informe o id da ação do Gaspar, sem barra"}
        if task_id and not ctx.db.collection("tarefas").document(task_id).get().exists:
            return {"erro": f"ação {task_id!r} não encontrada no Gaspar"}
        corpo = _sem_vazios({"tipo": args.get("tipo"), "texto": args.get("texto"),
                             "reuniao": args.get("reuniao_id"), "titulo": args.get("titulo")})
    resp, erro = _enviar(ctx, "gerar", corpo)
    if erro:
        return erro
    if resp.get("repetido"):
        task_id = None  # o link já foi (ou será) anotado pelo pedido que gerou este grafo: outro `task_id` duplicaria a nota
    tipo = resp.get("tipo") or args.get("tipo")
    pedido_id = _criar_pedido(ctx, {"tipo": tipo, "reuniao": resp.get("reuniao"), "processo": resp.get("processo"),
                                    "geracao": resp.get("geracao"), "task_id": task_id})
    saida = {"pedido_id": pedido_id, "tipo": tipo, "estado": "gerando", "orientacao": ORIENTACAO}
    if resp.get("repetido"):  # o Live Ideas já tinha um mapa desta ação e devolveu esse
        saida["repetido"] = True
        saida["orientacao"] += ("; já havia um mapa desta ação; o grafo existente não foi agrupado; para a versão agrupada, "
                                "chame de novo com refazer=true e agrupar_concluidas=true" if corpo.get("agrupar_concluidas")
                                else "; já havia um mapa desta ação (para criar outro, chame de novo com refazer=true)")
    return saida


def ajustar(ctx, args: dict) -> dict:
    alvo = _alvo(args)
    resp, erro = _enviar(ctx, "ajustar", {**alvo, "pedido": args.get("pedido")})
    if erro:
        return erro
    pedido_id = _criar_pedido(ctx, {"tipo": "ajuste", "ajuste": resp.get("ajuste"), **alvo})
    return {"pedido_id": pedido_id, "tipo": "ajuste", "estado": "gerando", "orientacao": ORIENTACAO}


def consultar(ctx, args: dict) -> dict:
    pedido_id = str(args.get("pedido_id") or "").strip()
    if not pedido_id or "/" in pedido_id:
        return {"erro": _NAO_ENCONTRADO}
    ref = ctx.db.collection(COLECAO).document(pedido_id)
    snap = ref.get()
    pedido = (snap.to_dict() or {}) if snap.exists else {}
    # Falha fechada: pedido de outro dono responde igual a inexistente.
    if not ctx.user_uid or pedido.get("uid") != ctx.user_uid:
        return {"erro": _NAO_ENCONTRADO}

    tipo = pedido.get("tipo")
    if tipo == "ajuste":
        corpo = {"tipo": "ajuste", "ajuste": pedido.get("ajuste")}
    else:
        corpo = _sem_vazios({"tipo": tipo, "reuniao": pedido.get("reuniao"),
                             "processo": pedido.get("processo"), "geracao": pedido.get("geracao")})
    resp, erro = _enviar(ctx, "consultar", corpo)
    if erro:
        return erro

    saida = {"pedido_id": pedido_id, "tipo": tipo, **_ids(pedido),
             "estado": resp.get("estado"), "custo": resp.get("custo")}
    if resp.get("erro"):
        # `falhou` é resposta da consulta, não erro da ferramenta.
        saida["motivo"] = resp["erro"]
    if tipo == "ajuste":
        saida["resposta"] = resp.get("resposta")
        saida["propostas"] = resp.get("propostas") or []
        if saida["propostas"]:
            saida["orientacao"] = ("mostre a proposta ao usuário e só com o sim dele chame liveideas_aplicar "
                                   "com o proposta_id")
        return saida
    for campo in ("titulo", "texto", "link"):
        if resp.get(campo):
            saida[campo] = resp[campo]
    if saida["estado"] == "pronto" and pedido.get("task_id"):
        saida["anexo"] = _anexar(ctx.db, ref, pedido, resp)
    return saida


def _marcar_anexado(db, ref) -> bool:
    """True só para a consulta que virou `anexado` de False para True."""
    @firestore.transactional
    def _marcar(tx):
        if (ref.get(transaction=tx).to_dict() or {}).get("anexado"):
            return False
        tx.update(ref, {"anexado": True})
        return True

    return _marcar(db.transaction())


def _anexar(db, ref, pedido: dict, resp: dict):
    task_id, tipo = str(pedido["task_id"]), pedido.get("tipo")
    titulo = resp.get("titulo") or pedido.get("processo") or pedido.get("reuniao")
    nota = f"{_ROTULO.get(tipo, 'Diagrama')} gerado no Live Ideas: {titulo}, {resp.get('link')}"
    marcou = False
    try:
        marcou = _marcar_anexado(db, ref)
        if not marcou:
            return "já estava anexado na ação"
        if tipo == "processo":
            if not resp.get("bpmn"):
                # Fica marcado: consultar de novo não traria o arquivo.
                return {"aviso": "o Live Ideas não devolveu o arquivo do processo; anexe pela tela"}
            import imagens_geradas
            from tools import anexar_arquivo

            nome = f"{titulo}.bpmn"
            service = imagens_geradas._drive_service()
            pasta = anexar_arquivo._pasta_de_anexos(service, db)
            drive_id, link = imagens_geradas._publicar_drive(
                service, pasta, nome, resp["bpmn"].encode("utf-8"), "application/xml")
            imagens_geradas._anexar_na_acao(db, task_id, nome=nome, link=link, drive_id=drive_id,
                                            prompt="", nota=nota)
            return {"task_id": task_id, "arquivo": nome, "link_drive": link, "nota": nota}
        agora = datetime.now(timezone.utc).isoformat()
        db.collection("tarefas").document(task_id).update(
            {"acompanhamento": firestore.ArrayUnion([{"data": agora, "nota": nota}])})
        return {"task_id": task_id, "nota": nota}
    except Exception as exc:  # noqa: BLE001 - o resultado pronto não pode se perder por causa do anexo
        print(f"[liveideas] Falha ao anexar o pedido {ref.id} na ação {task_id}: {exc}")
        if marcou:
            # ponytail: se o Drive gravou e a ação não, a nova tentativa sobe outro arquivo (o primeiro fica solto)
            try:
                ref.update({"anexado": False})
            except Exception:  # noqa: BLE001
                pass
        return {"aviso": "não consegui anexar na ação agora; consulte de novo para tentar outra vez"}


def listar(ctx, args: dict) -> dict:
    resp, erro = _enviar(ctx, "listar", _sem_vazios({"tipo": args.get("tipo"), "busca": args.get("busca")}))
    return erro or resp


TRANSCRICAO_MAX_PADRAO = 12000
TRANSCRICAO_MAX_MIN = 1000
TRANSCRICAO_MAX_MAX = 50000
_NOTEBOOK_SEM_TRANSCRICAO = ("o notebook do Live Ideas ainda não devolve a transcrição; atualize-o "
                             "(atualizar-servidor.ps1) e peça de novo")


def _inteiro(valor, padrao: int, minimo: int, maximo: int) -> int:
    if valor is None or valor == "" or isinstance(valor, bool):
        return padrao
    try:
        return max(minimo, min(int(valor), maximo))
    except (TypeError, ValueError, OverflowError):
        return padrao


def _incluir_transcricao(valor) -> bool:
    if isinstance(valor, str):
        return valor.strip().lower() in ("true", "1", "sim", "yes")
    return valor is True


def _transcricao(bruta, apos: int, maximo: int) -> dict:
    """Confere a transcrição do notebook e reaplica o teto aqui (o notebook antigo ou com defeito não estoura a conversa)."""
    if not isinstance(bruta, dict):
        return {"erro": _NOTEBOOK_SEM_TRANSCRICAO}
    trechos, usados = [], 0
    for t in bruta.get("trechos") or []:
        if not isinstance(t, dict) or not isinstance(t.get("seq"), int) or t["seq"] <= apos:
            continue
        texto = str(t.get("texto") or "")
        if trechos and usados + len(texto) > maximo:
            break
        trechos.append({"seq": t["seq"], "t": t.get("t") or "", "falante": t.get("falante") or "", "texto": texto})
        usados += len(texto)
    ultimo = bruta.get("ultimo_seq") if isinstance(bruta.get("ultimo_seq"), int) else apos
    proximo = trechos[-1]["seq"] if trechos else apos
    estado = bruta.get("estado") if bruta.get("estado") in ("ao_vivo", "encerrada") else "encerrada"
    saida = {"trechos": trechos, "proximo_seq": proximo, "ultimo_seq": ultimo,
             "truncado": proximo < ultimo, "estado": estado, "caracteres": usados}
    if saida["truncado"]:
        saida["orientacao"] = (f"há mais falas já gravadas: chame liveideas_ler de novo agora com incluir_transcricao=true "
                               f"e apos_seq={proximo}")
    elif estado == "ao_vivo":
        saida["orientacao"] = (f"reunião ao vivo: para as falas novas, chame de novo em ~30 s com incluir_transcricao=true "
                               f"e apos_seq={proximo}")
    else:
        saida["orientacao"] = "reunião encerrada: não virão falas novas"
    return saida


def ler(ctx, args: dict) -> dict:
    args = args or {}
    corpo = _alvo(args)
    incluir = _incluir_transcricao(args.get("incluir_transcricao"))
    if incluir:
        if "processo" in corpo:
            return {"erro": "a transcrição só existe para reunião: informe reuniao_id"}
        apos = _inteiro(args.get("apos_seq"), 0, 0, 10**9)
        maximo = _inteiro(args.get("max_caracteres_transcricao"), TRANSCRICAO_MAX_PADRAO,
                          TRANSCRICAO_MAX_MIN, TRANSCRICAO_MAX_MAX)
        corpo["transcricao"] = {"apos": apos, "max": maximo}
    resp, erro = _enviar(ctx, "ler", corpo)
    if erro:
        return erro
    resp.pop("bpmn", None)  # o XML é para o anexo, não para a conversa
    bruta = resp.pop("transcricao", None)
    if incluir:
        resp["transcricao"] = _transcricao(bruta, apos, maximo)
    return resp


def _proposta(ctx, acao: str, args: dict) -> dict:
    resp, erro = _enviar(ctx, acao, {**_alvo(args), "proposta": args.get("proposta_id")})
    return erro or resp


def aplicar(ctx, args: dict) -> dict:
    return _proposta(ctx, "aplicar", args)


def descartar(ctx, args: dict) -> dict:
    return _proposta(ctx, "descartar", args)


def desfazer(ctx, args: dict) -> dict:
    return _proposta(ctx, "desfazer", args)


def renomear(ctx, args: dict) -> dict:
    resp, erro = _enviar(ctx, "renomear", {**_alvo(args), "titulo": args.get("titulo")})
    return erro or resp


def apagar(ctx, args: dict) -> dict:
    resp, erro = _enviar(ctx, "apagar", _alvo(args))
    return erro or resp


def _data_br(iso) -> str | None:
    """`data` do `listar` (ISO) em dd/mm/aaaa, no horário de Brasília quando vem com fuso."""
    try:
        quando = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if quando.tzinfo:
        try:
            from zoneinfo import ZoneInfo

            quando = quando.astimezone(ZoneInfo("America/Sao_Paulo"))
        except Exception:  # noqa: BLE001 - sem base de fusos, fica a data como veio
            pass
    return quando.strftime("%d/%m/%Y")


def previa_apagar(ctx, args: dict) -> dict:
    """Prévia do piso de confirmação, só com leituras: título e data pelo `listar`;
    fora dos 50 mais recentes, o título pelo `ler`; sem nenhum dos dois, o id.
    O `ler` só vai se o `listar` respondeu: senão a prévia somaria dois prazos de 20 s."""
    alvo = _alvo(args)
    resp, _ = _enviar(ctx, "listar", {"tipo": "processo"} if "processo" in alvo else {})
    item = next((i for i in (resp or {}).get("itens") or [] if i.get("id") in alvo.values()), None)
    if item is None and resp is not None:
        item, _ = _enviar(ctx, "ler", alvo)
    item = item or {}
    titulo = item.get("titulo") or ", ".join(alvo.values())
    data = _data_br(item["data"]) if item.get("data") else None
    return {"status": "confirmation_required",
            "resumo": f"vai para a lixeira: {titulo}" + (f", {data}" if data else "")}
