#!/usr/bin/env python3
"""Desfaz etapas de plano gravadas como repr de dicionario Python.

Antes da correcao de 28/08/2026, tres caminhos de criacao aplicavam `str()` no
objeto da etapa em vez de desempacota-lo. O resultado ficou gravado assim:

    "{'text': 'P0 — Notificacao de pendencias...', 'estado': 'pendente',
      'aguardando_de': 'desenvolvedor'}"

O texto real esta la dentro, junto com as chaves auxiliares. `estado`,
`data_prevista` e `aguardando_de` nunca chegaram aos campos proprios, entao a
etapa se comporta como pendente comum.

## Por que `ast.literal_eval` e nao `json.loads`

E repr de Python: aspas simples, `True`/`None`. `literal_eval` le exatamente
isso e **nao executa nada** — aceita so literais. Regex aqui seria pior que
nada: o texto da etapa contem virgulas, dois-pontos e aspas, e qualquer padrao
que tentasse recortar acabaria cortando conteudo.

## Regras

- Etapa cujo parse falha **fica como esta** e e reportada. Adivinhar o formato
  de um dado ja corrompido e como se perde o resto dele.
- Idempotente: uma etapa ja normalizada nao casa com o padrao e e ignorada.
- Simulacao por padrao. Escrever exige `--aplicar`.

Uso:
    python scripts/migrar_planos_stringificados.py
    python scripts/migrar_planos_stringificados.py --aplicar
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from datetime import datetime, timezone

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "functions"))
_CHAVE = os.environ.get("HERMES_SERVICE_ACCOUNT",
                        os.path.join(_RAIZ, "firebase_service_account_key.json"))

# So casa o que comeca como dicionario com chave `text`/`texto`. Serve de
# gatilho, nao de parser: quem le o conteudo e o `literal_eval`.
_PADRAO = re.compile(r"^\s*\{\s*['\"](text|texto)['\"]\s*:")


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(_CHAVE))
    return firestore.client()


def desempacotar(texto: str) -> dict | None:
    """Devolve o dicionario original, ou None se nao for um repr recuperavel."""
    if not _PADRAO.match(texto or ""):
        return None
    try:
        valor = ast.literal_eval(texto.strip())
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None
    return valor if isinstance(valor, dict) else None


def migrar_etapa(etapa: dict) -> dict | None:
    """Etapa corrigida, ou None quando nao ha nada a fazer."""
    import subtarefas

    bruto = subtarefas.texto_de(etapa)
    original = desempacotar(bruto)
    if not original:
        return None

    novo = dict(etapa)
    novo["text"] = str(original.get("text") or original.get("texto") or "").strip()
    novo.pop("texto", None)
    if not novo["text"]:
        return None

    # Os campos auxiliares vao para onde deveriam ter ido.
    estado = str(original.get("estado") or "").strip().lower()
    if estado in subtarefas.ESTADOS:
        novo["estado"] = estado
        novo["completed"] = estado == subtarefas.FEITO
    for campo in ("data_prevista", "aguardando_de"):
        valor = str(original.get(campo) or "").strip()
        if valor:
            novo[campo] = valor
    contador = original.get("degradation_count")
    if isinstance(contador, int) and contador:
        novo["degradation_count"] = contador
    return novo


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aplicar", action="store_true", help="grava (sem isto, so simula)")
    args = p.parse_args()

    db = _db()
    from firebase_admin import firestore

    tocadas = etapas_migradas = falhas = 0
    relatorio: list[str] = []
    problemas: list[str] = []

    for doc in db.collection("tarefas").stream():
        dados = doc.to_dict() or {}
        plano = dados.get("plano_acao") or []
        if not isinstance(plano, list) or not plano:
            continue

        novo_plano = []
        mudou = 0
        for etapa in plano:
            if not isinstance(etapa, dict):
                novo_plano.append(etapa)
                continue
            corrigida = migrar_etapa(etapa)
            if corrigida is None:
                # Ou ja esta boa, ou o parse falhou — nos dois casos, preserva.
                import subtarefas
                if _PADRAO.match(subtarefas.texto_de(etapa)):
                    falhas += 1
                    problemas.append(
                        f"{doc.id}: etapa nao pode ser desempacotada — "
                        f"{subtarefas.texto_de(etapa)[:70]}")
                novo_plano.append(etapa)
            else:
                novo_plano.append(corrigida)
                mudou += 1

        if not mudou:
            continue
        tocadas += 1
        etapas_migradas += mudou
        relatorio.append(f"  {doc.id}  {str(dados.get('titulo'))[:52]:54} "
                         f"{mudou}/{len(plano)} etapa(s)")

        if args.aplicar:
            agora = datetime.now(timezone.utc).isoformat()
            doc.reference.update({
                "plano_acao": novo_plano,
                "data_atualizacao": agora,
                "acompanhamento": firestore.ArrayUnion([{
                    "data": agora,
                    "nota": (f"[Migração] {mudou} etapa(s) do plano estavam gravadas como "
                             "texto de dicionário (falha da criação em 28/08) e foram "
                             "desempacotadas; estado e datas voltaram aos campos próprios."),
                }]),
            })

    print(f"{'APLICADO' if args.aplicar else 'SIMULAÇÃO'}")
    print(f"  ações a tocar:      {tocadas}")
    print(f"  etapas a migrar:    {etapas_migradas}")
    print(f"  etapas sem parse:   {falhas} (preservadas como estão)")
    if relatorio:
        print("\nações:")
        print("\n".join(relatorio))
    if problemas:
        print("\nnão migradas:")
        print("\n".join(f"  {x}" for x in problemas[:20]))
    if not args.aplicar and tocadas:
        print("\n(nada gravado — rode com --aplicar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
