' Hermes Voice Server - Inicializador Silencioso
'
' Faz o mesmo que start_hermes_voice.bat, mas sem abrir nenhuma janela de
' console (nenhum flash, nada na barra de tarefas) e sem abrir aba do
' navegador automaticamente. A saida do uvicorn e redirecionada para
' .\logs\voice.log, ja que nao ha console visivel para acompanhar.
'
' Aponte o atalho da pasta Inicializar (shell:startup) "Hermes Copiloto de
' Voz" para "wscript.exe start_hermes_voice_hidden.vbs" (em vez do
' start_hermes_voice.bat) para que o servidor suba oculto junto com o
' Windows.
'
' ATENCAO: se um atalho na pasta Inicializar do Windows aponta pra ca, isso
' nao aparece em nenhuma busca dentro do repositorio. Confira os atalhos de
' Startup antes de remover/renomear este arquivo.

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
shell.Run "cmd /c title Hermes Voice Server && .venv\Scripts\python.exe -m uvicorn main:app --port 8765 > """ & logsDir & "\voice.log"" 2>&1", HIDDEN, WAIT_ON_RETURN
