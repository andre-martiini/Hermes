"""
Dados cadastrais pessoais completos do usuário (documentos, contato, família,
formação acadêmica, carreira, dados bancários, plano de saúde etc.), gravados
em `usuarios/{uid}.dados_cadastrais`.

Diferente de `ai_profile` (nome/cargo/setor/email + preferências + personalidade
destilada do diário), este campo NÃO é injetado na persona estática de nenhuma
superfície — é lido sob demanda por uma ferramenta (`consultar_dados_cadastrais`,
registrada em `main.py` e `godmode.py`), só declarada ao modelo quando o assunto
aparece na conversa (ver os `_gate_dados_cadastrais`/gate equivalente em cada
callable). Isso existe porque parte desse dado é sensível (CPF, RG, dados
bancários) — colocá-lo sempre no contexto multiplicaria sem necessidade quantas
vezes ele trafega para a API do Gemini/Claude.

Não há ferramenta de escrita para a IA: o dado é gravado uma vez via
`scripts/seed_dados_cadastrais.py` (execução local, fora deste callable) e
atualizado do mesmo jeito quando mudar — não vale o risco de deixar o modelo
reescrever CPF/RG/dados bancários a partir de uma instrução de chat.
"""


def get_dados_cadastrais(db, user_uid: str | None) -> dict:
    if not user_uid:
        return {"error": "Sem usuário autenticado."}
    snap = db.collection("usuarios").document(user_uid).get()
    dados = (snap.to_dict() or {}).get("dados_cadastrais") if snap.exists else None
    if not dados:
        return {"error": "Nenhum dado cadastral registrado ainda."}
    return dados
