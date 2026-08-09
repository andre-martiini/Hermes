' Inicia o worker de captura do WhatsApp sem abrir nenhuma janela de console.
' Usado pela Tarefa Agendada do Windows "Hermes WhatsApp Capture Worker" (gatilho: logon).
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\run-hidden.bat"

Set shell = CreateObject("WScript.Shell")
shell.Run """" & batPath & """", 0, False
