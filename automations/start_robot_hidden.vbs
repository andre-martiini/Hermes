Set WshShell = CreateObject("WScript.Shell")
' Executa o bat em modo invisível (parâmetro 0)
WshShell.Run chr(34) & "automations\run_bridge_hidden.bat" & chr(34), 0
Set WshShell = Nothing
