#!/usr/bin/env python3
"""Reconstroi o historico de faturas de cartao a partir do Gmail.

A extracao de lancamentos entrou no `sync_boletos_gmail` a partir de agora, entao
so faturas novas seriam capturadas. Sem historico nao ha projecao de parcelas
util — uma compra em 10x feita tres meses atras e exatamente o que compromete os
meses seguintes, e ela nao aparece em lugar nenhum se a extracao comecar do zero.

As faturas antigas estao todas no Gmail. Este script varre o remetente do cartao,
destrava cada PDF com a senha do Secret Manager e roda a mesma extracao do sync.

E idempotente: reprocessar a mesma competencia atualiza os documentos em vez de
duplicar (ver `fatura_cartao._id_do_item`). `fixed_bills` nao e tocado aqui — a
correcao de total so acontece no fluxo normal e apenas da competencia de corte em
diante.

Uso:
    python scripts/backfill_faturas_cartao.py --dry-run     # so lista o que achou
    python scripts/backfill_faturas_cartao.py --meses 12    # processa 12 meses
"""

from __future__ import annotations

import argparse
import base64
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "functions"))


def _pdf_da_mensagem(service, msg_id: str) -> tuple[bytes | None, str, str]:
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    cabecalhos = {h["name"].lower(): h["value"]
                  for h in msg.get("payload", {}).get("headers", [])}
    remetente = cabecalhos.get("from", "")
    assunto = cabecalhos.get("subject", "")

    pdf = None

    def _varrer(partes):
        nonlocal pdf
        for parte in partes or []:
            if pdf:
                return
            _varrer(parte.get("parts"))
            corpo = parte.get("body", {})
            if parte.get("filename", "").lower().endswith(".pdf") and corpo.get("attachmentId"):
                anexo = service.users().messages().attachments().get(
                    userId="me", messageId=msg_id, id=corpo["attachmentId"]).execute()
                pdf = base64.urlsafe_b64decode(anexo["data"])

    _varrer([msg.get("payload", {})])
    return pdf, remetente, assunto


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meses", type=int, default=12,
                        help="quantos meses para tras varrer no Gmail (padrao 12)")
    parser.add_argument("--dry-run", action="store_true",
                        help="lista as faturas encontradas sem extrair nem gravar")
    parser.add_argument("--limpar", action="store_true",
                        help="apaga faturas e lancamentos antes de reprocessar. Necessario "
                             "quando a regra de competencia muda: os documentos antigos "
                             "ficariam orfaos sob a chave errada")
    args = parser.parse_args()

    import fatura_cartao
    from bill_pdf_passwords import find_password_config, read_password_secret
    from gmail_bill_pdf import prepare_pdf_for_gemini
    from main import get_db, get_gemini_api_key, get_gmail_service

    from google import genai
    from google.genai import types

    db = get_db()
    service = get_gmail_service()
    projeto = os.environ.get("GCLOUD_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "gestao-hermes"

    remetentes = " OR ".join(f"from:{e}" for e in fatura_cartao.REMETENTES_CARTAO)
    query = f"({remetentes}) has:attachment filename:pdf newer_than:{args.meses * 31}d"
    print(f"Gmail: {query}\n")

    mensagens = service.users().messages().list(
        userId="me", q=query, maxResults=60).execute().get("messages", [])
    print(f"{len(mensagens)} mensagem(ns) encontrada(s).\n")
    if not mensagens:
        return

    if args.limpar and not args.dry_run:
        apagados = 0
        for colecao in (fatura_cartao.COL_ITENS, fatura_cartao.COL_FATURAS):
            while True:
                lote = list(db.collection(colecao).limit(400).stream())
                if not lote:
                    break
                batch = db.batch()
                for d in lote:
                    batch.delete(d.reference)
                batch.commit()
                apagados += len(lote)
        print(f"{apagados} documento(s) apagado(s) antes do reprocessamento.\n")

    if args.dry_run:
        for m in mensagens:
            _, remetente, assunto = _pdf_da_mensagem(service, m["id"])
            print(f"  {m['id']}  {assunto[:70]}")
        print("\n[dry-run] nada extraido nem gravado.")
        return

    cliente = genai.Client(api_key=get_gemini_api_key())
    ok = falhas = 0

    for m in mensagens:
        msg_id = m["id"]
        try:
            pdf, remetente, assunto = _pdf_da_mensagem(service, msg_id)
            cartao = fatura_cartao.e_fatura_de_cartao(remetente)
            if not pdf or not cartao:
                print(f"  {msg_id}: sem PDF ou remetente fora da lista — pulado")
                continue

            config = find_password_config(db, remetente)
            senha = read_password_secret(projeto, config["secret_id"]) if config else None
            pdf, motivo = prepare_pdf_for_gemini(pdf, passwords=[senha] if senha else None)
            if not pdf:
                print(f"  {msg_id}: PDF nao pode ser lido ({motivo})")
                falhas += 1
                continue

            extraido = fatura_cartao.extrair(
                cliente, types, pdf, contexto_email=f"Assunto: {assunto}")
            resumo = fatura_cartao.salvar(db, cartao, extraido, google_message_id=msg_id)
            print(f"  {resumo['competencia']}: {resumo['itens_gravados']} lancamento(s), "
                  f"total R$ {resumo['total']}")
            ok += 1
        except Exception as exc:  # noqa: BLE001 — uma fatura ruim nao para o resto
            print(f"  {msg_id}: FALHA — {exc}")
            falhas += 1

    print(f"\n{ok} fatura(s) processada(s), {falhas} falha(s).")
    if ok:
        print("Confira com a tool `consultar_compromissos_futuros`.")


if __name__ == "__main__":
    main()
