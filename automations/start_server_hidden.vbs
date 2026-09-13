' Inicia o servidor de automacoes (PGD/ponto eletronico) sem abrir janela de console.
' Usado pelo atalho na pasta Inicializar (shell:startup) para subir junto com o Windows.
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\run_server_hidden.bat"

Set shell = CreateObject("WScript.Shell")
shell.Run """" & batPath & """", 0, False
