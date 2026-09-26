"""Uso diário do Hermes Vídeo para o relatório de custos das 19h.

Mesmo esquema de `system_usage/{gemini,openai}/daily/{dia}` (dia em
America/Sao_Paulo), que `cost_report.gerar_relatorio_custos` lê: `calls` e
`estimated_usd`, mais a divisão por tipo (narração, quadro, clipe). O custo é o
preço de `config/video_precos` vezes o que foi gerado — o mesmo valor somado em
`custo_real_usd` do projeto, gravado no mesmo commit do item.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from firebase_admin import firestore

TZ = ZoneInfo("America/Sao_Paulo")


def ref_dia(db, agora: datetime | None = None):
    dia = (agora or datetime.now(timezone.utc)).astimezone(TZ).date().isoformat()
    return db.collection("system_usage").document("video").collection("daily").document(dia), dia


def campos(custo: float, tipo: str, dia: str) -> dict:
    return {
        "date": dia,
        "calls": firestore.Increment(1),
        "estimated_usd": firestore.Increment(round(custo, 4)),
        "itens": {tipo: firestore.Increment(1)},
        "usd_por_tipo": {tipo: firestore.Increment(round(custo, 4))},
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
