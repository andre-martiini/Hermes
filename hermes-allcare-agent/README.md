# Agente local Allcare

Consulta o Portal do Beneficiário pela conexão deste computador e envia o boleto ao Hermes por uma Cloud Function autenticada. CPF, senha Allcare e refresh token Firebase ficam no Gerenciador de Credenciais do Windows; não são gravados em arquivos nem enviados ao repositório.

## Instalação

1. Execute `install.bat`.
2. Se ainda não houver sessão local do Hermes, informe uma vez o login do Hermes.
3. Informe a senha do Portal Allcare.

O instalador valida a senha localmente, executa a primeira sincronização e registra `HermesAllcareAgent` na inicialização do usuário. O processo sincroniza no logon e a cada 6 horas, sem exigir privilégios administrativos. O computador precisa estar ligado e conectado. O log fica em `%LOCALAPPDATA%\Hermes\allcare-agent.log`.

Para remover apenas a inicialização automática, execute no PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_task.ps1
```

As credenciais continuam no cofre do Windows para evitar apagamento acidental. Elas podem ser removidas manualmente no Gerenciador de Credenciais.
