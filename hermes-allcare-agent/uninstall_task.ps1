$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
Remove-ItemProperty -LiteralPath $runKey -Name 'HermesAllcareAgent' -ErrorAction SilentlyContinue
Write-Host 'Inicialização automática removida. As credenciais permanecem no cofre do Windows.'
