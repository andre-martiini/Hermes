# Sobe a sessão residente do Gaspar. O Agendador chama este script às 06:00 e a cada 30 min até 18:30;
# se o agente já estiver rodando, sai sem fazer nada (é o que faz o papel de vigia).
$agente = Get-CimInstance Win32_Process -Filter "Name='claude.exe'" |
  Where-Object { $_.CommandLine -match 'plugin:telegram@claude-plugins-official' }
if ($agente) { exit 0 }

$Host.UI.RawUI.WindowTitle = 'Gaspar agente'
# Perfil próprio do agente: login, plugins, memória e configurações separados dos do André.
$env:CLAUDE_CONFIG_DIR = "$env:USERPROFILE\.claude-gaspar"
# O token do bot fica só em telegram-gaspar: as outras sessões do Claude Code que carregarem
# o plugin não acham token, saem na hora e não disputam o getUpdates com o agente.
$env:TELEGRAM_STATE_DIR = "$env:USERPROFILE\.claude\channels\telegram-gaspar"
# Sem bun no PATH o plugin falha e o Claude Code passa ~15 min sem tentar de novo.
# Terminais abertos antes da instalação do Bun (e o Agendador) não têm o PATH novo.
$env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
# Uma falha anterior do plugin fica gravada neste cache e faz o agente pular o Telegram por ~15 min.
$cache = "$env:CLAUDE_CONFIG_DIR\mcp-needs-auth-cache.json"
if (Test-Path $cache) {
  $c = Get-Content $cache -Raw | ConvertFrom-Json
  $c.PSObject.Properties.Remove('plugin:telegram:telegram')
  [IO.File]::WriteAllText($cache, ($c | ConvertTo-Json -Compress))  # sem BOM (Set-Content do PS 5.1 grava BOM)
}
Set-Location $PSScriptRoot

# Canal gaspar-eventos (marco 2): usa a chave da conta de serviço do worker do WhatsApp; sem ela, o /loop varre tudo a cada 5 min.
$canais = @('plugin:telegram@claude-plugins-official')
$pulso = '5m'
if (Test-Path '..\..\firebase_service_account_key.json') {
  $env:GASPAR_EVENTOS = '1'
  $canais = @('--channels') + $canais + @('--dangerously-load-development-channels', 'server:gaspar-eventos')
  $pulso = '15m'
} else {
  $canais = @('--channels') + $canais
}
$prompt = "Bom dia. Voce acabou de iniciar. 1) Chame obter_estado_atual e obter_fila_atencao. 2) Rode /loop $pulso com o conteudo de .claude/loop.md. 3) Se ja passou das 07:00 e nao e janela protegida, mande ao Andre pelo telegram um bom-dia curto com no maximo 3 pontos; senao, espere a janela acabar."
# --channels aceita vários valores: o -- impede que ele engula o prompt.
# Entre aspas porque o Windows PowerShell 5.1 descarta um -- solto.
claude @canais '--' $prompt
