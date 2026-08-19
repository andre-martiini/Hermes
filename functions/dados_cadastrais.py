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

O objeto completo (~11k caracteres com o perfil atual) estoura o teto de
truncamento do resultado de ferramenta em ambos os loops de tool-calling
(8000 chars no Godmode, `claude_provider.GODMODE_TOOL_RESULT_CHAR_LIMIT`;
12000 chars no copiloto padrão) — um corte no meio do JSON quebraria a
resposta. Por isso a leitura é sempre por seção: sem `secao`, devolve só o
índice de seções disponíveis; com `secao`, devolve o conteúdo completo
daquela seção (a maior seção individual hoje tem ~2.3k caracteres).
"""


def get_dados_cadastrais(db, user_uid: str | None, secao: str | None = None) -> dict:
    if not user_uid:
        return {"error": "Sem usuário autenticado."}
    snap = db.collection("usuarios").document(user_uid).get()
    dados = (snap.to_dict() or {}).get("dados_cadastrais") if snap.exists else None
    if not dados:
        return {"error": "Nenhum dado cadastral registrado ainda."}

    secoes_disponiveis = sorted(dados.keys())
    secao_norm = (secao or "").strip()
    if not secao_norm:
        return {
            "secoes_disponiveis": secoes_disponiveis,
            "instrucao": "Chame de novo passando 'secao' com um dos valores acima para ver o conteúdo completo dessa seção.",
        }
    if secao_norm not in dados:
        return {"error": f"Seção '{secao_norm}' não encontrada.", "secoes_disponiveis": secoes_disponiveis}
    return {secao_norm: dados[secao_norm]}
