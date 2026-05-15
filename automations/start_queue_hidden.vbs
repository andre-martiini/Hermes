Set WshShell = CreateObject("WScript.Shell")
' Inicia o queue_processor em modo invisível (janela oculta)
WshShell.Run chr(34) & "C:\Users\T-GAMER\Documents\gestao-Hermes\automations\run_queue_hidden.bat" & chr(34), 0
Set WshShell = Nothing
