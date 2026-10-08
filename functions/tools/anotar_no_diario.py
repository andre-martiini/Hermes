"""Nota no diario pessoal (`diario_pessoal/{data}.notas_manuais`), pelo MCP.

Mesmo formato que `PersonalDiaryView.tsx::addNote` grava: `{texto, em}` (em =
ISO UTC com milissegundos e "Z") por ArrayUnion, com `data` no doc e merge --
nunca sobrescreve o diario ja gerado nem as outras notas. O gerador das 21h30
(`personal_diary._collect_diary_material`) le so `texto`; `origem` e extra.

So aceita HOJE (Brasilia): o gerador so processa o dia corrente e pula o doc que
ja tem `texto`. Depois da geracao a nota ainda e guardada, mas a resposta diz que
nao entra no texto (regenerar exigiria chamar o Gemini de dentro da tool).
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
    hoje = hoje_brasilia()
    dia = str(data or "").strip() or hoje
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia):
        raise DiarioError(f"`data` precisa ser YYYY-MM-DD; veio {data!r}.")
    if dia != hoje:
        raise DiarioError(f"So da para anotar no diario de hoje ({hoje}): o diario das 21h30 "
                          f"so le as notas do proprio dia, e uma nota em {dia} nunca entraria no texto.")

    nota = {"texto": texto,
            "em": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")}
    origem = str(origem or "").strip()
    if origem:
        nota["origem"] = origem
    ref = db.collection(COLECAO).document(dia)
    atual = ref.get()
    ja_gerado = bool(atual.exists and (atual.to_dict() or {}).get("texto"))
    ref.set({"data": dia, "notas_manuais": firestore.ArrayUnion([nota])}, merge=True)
    if ja_gerado:
        observacao = ("O diario de hoje ja foi gerado as 21h30; a nota fica guardada "
                      "mas nao entra no texto.")
    else:
        observacao = "Entra no diario gerado hoje as 21h30 como anotacao do proprio usuario."
    return {"status": "completed", "data": dia, "nota": nota,
            "incorporado_no_diario": not ja_gerado, "observacao": observacao}
