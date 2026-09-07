# functions/tests_autonomy/

Suíte de testes dos módulos novos de `functions/autonomy/` (propostos em `docs/plano-hermes-autonomo-2026-09-06.md`, seção 3.3). Criado em P00, populado a partir de P01.

Convenção obrigatória (evidência do porquê em `docs/autonomia/baseline.md`, seção 3): todo teste novo aqui bloqueia rede real por padrão. A suíte legada em `functions/test_*.py` hoje "passa" porque o sandbox de CI não tem outbound para Firestore/Telegram/Gemini — não porque há isolamento deliberado. Os testes novos não devem repetir esse acidente.

Padrão a seguir (a implementar junto com o primeiro teste real, em P01): monkeypatch de `socket.socket` (ou equivalente) ativado por um fixture/setUp comum neste pacote, com allowlist explícita apenas para o Firestore Emulator local quando um teste precisar dele. Nenhum teste desta pasta deve depender de credencial real (`GOOGLE_APPLICATION_CREDENTIALS`, tokens de API) para passar.

Descoberta pelo `unittest discover` atual: verificar em P01 se `python -m unittest discover -s functions -p "test_*.py"` alcança este subpacote (precisa de `__init__.py` ou de um padrão de nome compatível) ou se precisa de um comando de CI dedicado (`npm run test:autonomy`, citado na seção 8.1/10.4 do plano). Não presumir — testar antes de declarar o pacote coberto pelo gate de CI.
