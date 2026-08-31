' Hermes - Inicializador Silencioso Completo
'
' Faz o mesmo que start.bat, mas sem abrir nenhuma janela de terminal.
' A saida de cada servico e redirecionada para arquivos em .\logs\

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
' A sincronizacao principal roda na Cloud Function. Iniciar tambem o watcher
' local faria dois consumidores responderem ao mesmo system/sync.
shell.Run "cmd /c title Hermes Sync (Monitor de Paginas) && python hermes_cli.py watch-pages > """ & logsDir & "\watch_pages.log"" 2>&1", HIDDEN, WAIT_ON_RETURN

shell.Run "cmd /c ""cd /d " & baseDir & "\hermes-voice-bridge && .venv\Scripts\python.exe -m uvicorn main:app --port 3002 > " & logsDir & "\voice_bridge.log 2>&1""", HIDDEN, WAIT_ON_RETURN
shell.Run "cmd /c ""cd /d " & baseDir & "\hermes-voice-client && .venv\Scripts\python.exe -m uvicorn main:app --port 8765 > " & logsDir & "\voice_client.log 2>&1""", HIDDEN, WAIT_ON_RETURN
