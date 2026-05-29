Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
' Executa o bat em modo invisível (parâmetro 0)
WshShell.Run chr(34) & currentDir & "\run_hermes_hidden.bat" & chr(34), 0
Set WshShell = Nothing
