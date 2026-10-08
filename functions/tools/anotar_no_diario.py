"""Nota no diario pessoal (`diario_pessoal/{data}.notas_manuais`), pelo MCP.

Mesmo formato que `PersonalDiaryView.tsx::addNote` grava: `{texto, em}` (em =
ISO UTC com milissegundos e "Z") por ArrayUnion, com `data` no doc e merge --
nunca sobrescreve o diario ja gerado nem as outras notas. O gerador das 21h30
(`personal_diary._collect_diary_material`) le so `texto`; `origem` e extra.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from firebase_admin import firestore

from tools.registrar_saude import hoje_brasilia

COLECAO = "diario_pessoal"
LIMITE_TEXTO = 4000


class DiarioError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def anotar(db, texto, data=None, origem=None) -> dict:
    texto = str(texto or "").strip()
    if not texto:
        raise DiarioError("Texto da nota vazio.")
    if len(texto) > LIMITE_TEXTO:
        raise DiarioError(f"Nota longa demais ({len(texto)} caracteres; maximo {LIMITE_TEXTO}).")
    dia = str(data or "").strip() or hoje_brasilia()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia):
        raise DiarioError(f"`data` precisa ser YYYY-MM-DD; veio {data!r}.")

    nota = {"texto": texto,
            "em": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")}
    origem = str(origem or "").strip()
    if origem:
        nota["origem"] = origem
    db.collection(COLECAO).document(dia).set(
        {"data": dia, "notas_manuais": firestore.ArrayUnion([nota])}, merge=True)
    return {"status": "completed", "data": dia, "nota": nota,
            "observacao": "Entra no diario gerado as 21h30 desta data como anotacao do proprio usuario."}
