# Sobe a sessão residente do Gaspar (marco 1).
# O token do bot fica só em telegram-gaspar: as outras sessões do Claude Code que carregarem
# o plugin não acham token, saem na hora e não disputam o getUpdates com o agente.
$env:TELEGRAM_STATE_DIR = "$env:USERPROFILE\.claude\channels\telegram-gaspar"
# Sem bun no PATH o plugin falha e o Claude Code passa ~15 min sem tentar de novo.
# Terminais abertos antes da instalação do Bun (e o Agendador) não têm o PATH novo.
$env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
Set-Location $PSScriptRoot
$prompt = 'Bom dia. Voce acabou de iniciar. 1) Chame obter_estado_atual e obter_fila_atencao. 2) Rode /loop 5m com o conteudo de .claude/loop.md. 3) Se ja passou das 07:00 e nao e janela protegida, mande ao Andre pelo telegram um bom-dia curto com no maximo 3 pontos; senao, espere a janela acabar.'
# --channels aceita vários valores: o -- impede que ele engula o prompt.
# Entre aspas porque o Windows PowerShell 5.1 descarta um -- solto.
claude --channels plugin:telegram@claude-plugins-official '--' $prompt
