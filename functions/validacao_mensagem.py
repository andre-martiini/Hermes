"""Conferência de uma mensagem que o Gaspar vai mandar no WhatsApp em nome do André.

Vale para o Modo Secretário e o Modo Objetivo. O prompt já pede tudo isto; a
conferência é a trava do código para quando o modelo erra (regras do dono, 14/10/2026).
Até 28/10/2026 havia também a trava "nunca revelar que é assistente, robô ou IA": saiu, porque
o Gaspar se identifica nos dois modos (prefixo de `mensagens_gaspar`).
- nunca sugerir ligação, chamada ou videoconferência;
- nunca pagar, transferir, assinar nem aceitar termos ou valores;
- nunca chamar a esposa de "Tininha";
- nunca passar dado que o dono vetou, nem CPF ou número longo que ele não liberou;
- não repetir o que já foi dito.
"""

import re
import unicodedata
from difflib import SequenceMatcher

_TAMANHO_MAX = 1200
_SEMELHANCA_REPETICAO = 0.92

_CHAMADA = re.compile(
    r"\b(lig(ar|o|a|ue|uem|amos|aremos)|liga[çc](ão|ao|ões|oes)|chamada|videochamada|v[ií]deo ?chamada|"
    r"videoconfer[eê]ncia|telefonar|telefonema)\b",
    re.IGNORECASE,
)
_COMPROMISSO = re.compile(
    r"\b(pag(o|amos|uei|arei|aremos)|vou pagar|fa[cç]o o pix|mando o pix|transfiro|transferi|"
    r"assin(o|ei|arei)|vou assinar|aceito (o|os|a|as) (termos?|condi[cç](ão|oes|ões)|contrato|valor|or[cç]amento)|"
    r"concordo com (o|os|a|as) (termos?|condi[cç](ão|oes|ões)|contrato|valor))\b",
    re.IGNORECASE,
)
_TININHA = re.compile(r"\btininha\b", re.IGNORECASE)
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_NUMERO_LONGO = re.compile(r"\d[\d .-]{7,}\d")


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.lower().split())


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def itens(texto) -> list[str]:
    """Lista de itens vetados a partir de texto livre (linhas, vírgulas ou ponto e vírgula)."""
    if isinstance(texto, (list, tuple)):
        partes = [str(p) for p in texto]
    else:
        partes = re.split(r"[\n;,]", str(texto or ""))
    return [p.strip() for p in partes if len(p.strip()) >= 4]


def problemas(texto: str, *, nunca_informar=None, pode_informar: str = "",
              ja_enviadas: list[str] | None = None) -> list[str]:
    """Motivos para NÃO enviar `texto`; lista vazia quando pode sair."""
    texto = str(texto or "").strip()
    if not texto:
        return ["mensagem vazia"]
    achados = []
    if len(texto) > _TAMANHO_MAX:
        achados.append(f"mensagem longa demais ({len(texto)} caracteres)")
    if _CHAMADA.search(texto):
        achados.append("fala em ligação ou chamada")
    if _COMPROMISSO.search(texto):
        achados.append("compromete o André com pagamento, assinatura ou aceite")
    if _TININHA.search(texto):
        achados.append("usa o apelido 'Tininha'")

    liberados = _digitos(pode_informar)
    for numero in _CPF.findall(texto) + _NUMERO_LONGO.findall(texto):
        if _digitos(numero) and _digitos(numero) not in liberados:
            achados.append("contém documento ou número que não foi liberado")
            break

    normalizado = _normalizar(texto)
    for item in itens(nunca_informar):
        if _normalizar(item) in normalizado:
            achados.append(f"contém dado vetado ({item[:40]})")

    for anterior in ja_enviadas or []:
        if SequenceMatcher(None, normalizado, _normalizar(anterior)).ratio() >= _SEMELHANCA_REPETICAO:
            achados.append("repete uma mensagem já enviada")
            break
    return achados
