Set WshShell = CreateObject("WScript.Shell")
' Executa o bat em modo invisível (parâmetro 0)
WshShell.Run chr(34) & "C:\Users\T-GAMER\Documents\gestao-Hermes\automations\run_server_hidden.bat" & chr(34), 0
Set WshShell = Nothing
