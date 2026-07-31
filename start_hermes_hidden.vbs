' Hermes - Inicializador silencioso
' Sobe os mesmos servicos do start.bat, mas sem janelas visiveis.
'
' ATENCAO: este arquivo e o alvo do atalho "start_hermes_hidden" na pasta
' Startup do Windows (%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup).
' Nao ha nenhuma referencia a ele dentro do codigo do repositorio - por isso
' uma limpeza de "codigo morto" ja o apagou uma vez (commit 2e54c8f) sem
' perceber que ele era usado. Se for reorganizar/remover scripts soltos na
' raiz do projeto, verifique antes se algum atalho do Windows aponta pra ca.

Set WshShell = CreateObject("WScript.Shell")
base = "C:\Users\T-GAMER\Documents\gestao-Hermes"

WshShell.Run "cmd /c title Hermes Web (Frontend) && cd /d """ & base & """ && npm run dev", 0, False
WScript.Sleep 2000
WshShell.Run "cmd /c title Hermes Automations API && cd /d """ & base & "\automations"" && python server.py", 0, False
WshShell.Run "cmd /c title Hermes Sync (Google Tasks) && cd /d """ & base & """ && python hermes_cli.py watch", 0, False
WshShell.Run "cmd /c title Hermes Sync (Monitor de Paginas) && cd /d """ & base & """ && python hermes_cli.py watch-pages", 0, False

Set WshShell = Nothing
