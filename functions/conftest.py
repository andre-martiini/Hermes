"""Configuração do pytest para os testes das Functions.

Os testes nunca podem alcançar o Google de verdade. Neste computador as
credenciais padrão do gcloud apontam para a produção, e um teste que chegava a
`firestore.client()` gravava no Firestore real: em 04/10/2026 havia ~2.100
chamadas falsas de usuários de teste no `mcp_audit_log`. Apontar a credencial
para um arquivo inexistente reproduz a CI, onde não há credencial nenhuma.
O mesmo bloqueio vale para o `unittest` em test_000_sem_credenciais_reais.py.
"""

import os

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_credencial_inexistente_nos_testes.json")
