# Sobe a sessão residente do Gaspar (marco 1).
# O token do bot fica só em telegram-gaspar: as outras sessões do Claude Code que carregarem
# o plugin não acham token, saem na hora e não disputam o getUpdates com o agente.
$env:TELEGRAM_STATE_DIR = "$env:USERPROFILE\.claude\channels\telegram-gaspar"
Set-Location $PSScriptRoot
$prompt = 'Bom dia. Voce acabou de iniciar. 1) Chame obter_estado_atual e obter_fila_atencao. 2) Rode /loop 5m com o conteudo de .claude/loop.md. 3) Se ja passou das 07:00 e nao e janela protegida, mande ao Andre pelo telegram um bom-dia curto com no maximo 3 pontos; senao, espere a janela acabar.'
# --channels aceita vários valores: o -- impede que ele engula o prompt.
claude --channels plugin:telegram@claude-plugins-official -- $prompt
