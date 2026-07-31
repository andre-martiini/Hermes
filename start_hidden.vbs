' Hermes - Inicializador Silencioso
'
' Faz o mesmo que start.bat, mas sem abrir nenhuma janela de terminal
' (nenhum flash de console, nada na barra de tarefas). A saida de cada
' servico e redirecionada para arquivos em .\logs\, ja que nao ha console
' visivel para acompanhar.
'
' Use este arquivo (em vez de start.bat) quando quiser que o Hermes inicie
' junto com o Windows sem janelas persistindo na tela: aponte um atalho na
' pasta Inicializar (shell:startup) ou uma tarefa no Agendador de Tarefas
' do Windows para "wscript.exe start_hidden.vbs".
'
' ATENCAO: se um atalho na pasta Inicializar do Windows aponta pra ca, isso
' nao aparece em nenhuma busca dentro do repositorio. Ja aconteceu de uma
' limpeza de "codigo morto" apagar o launcher oculto anterior por nao achar
' nenhuma referencia a ele (commit 2e54c8f) - confira os atalhos de Startup
' antes de remover/renomear este arquivo.

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
logsDir = baseDir & "\logs"
If Not fso.FolderExists(logsDir) Then
    fso.CreateFolder(logsDir)
End If

Const HIDDEN = 0
Const WAIT_ON_RETURN = False

shell.CurrentDirectory = baseDir
shell.Run "cmd /c title Hermes Web (Frontend) && npm run dev > """ & logsDir & "\frontend.log"" 2>&1", HIDDEN, WAIT_ON_RETURN

WScript.Sleep 2000

shell.CurrentDirectory = baseDir & "\automations"
shell.Run "cmd /c title Hermes Automations API && python server.py > """ & logsDir & "\automations.log"" 2>&1", HIDDEN, WAIT_ON_RETURN

shell.CurrentDirectory = baseDir
shell.Run "cmd /c title Hermes Sync (Google Tasks) && python hermes_cli.py watch > """ & logsDir & "\sync.log"" 2>&1", HIDDEN, WAIT_ON_RETURN
shell.Run "cmd /c title Hermes Sync (Monitor de Paginas) && python hermes_cli.py watch-pages > """ & logsDir & "\watch_pages.log"" 2>&1", HIDDEN, WAIT_ON_RETURN
