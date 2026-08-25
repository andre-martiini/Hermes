$ErrorActionPreference = 'Stop'
$agentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $agentDir '.venv\Scripts\python.exe'
$pythonw = Join-Path $agentDir '.venv\Scripts\pythonw.exe'

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv (Join-Path $agentDir '.venv')
}
& $python -m pip install --disable-pip-version-check -r (Join-Path $agentDir 'requirements.txt')
& $python (Join-Path $agentDir 'setup_agent.py')
if ($LASTEXITCODE -ne 0) { throw 'Configuração do agente não foi concluída.' }

$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runValue = '"' + $pythonw + '" "' + (Join-Path $agentDir 'agent_loop.py') + '"'
New-ItemProperty -LiteralPath $runKey -Name 'HermesAllcareAgent' -Value $runValue -PropertyType String -Force | Out-Null

& $python (Join-Path $agentDir 'sync_once.py')
if ($LASTEXITCODE -ne 0) { throw 'Agente instalado, mas a primeira sincronização falhou. Consulte %LOCALAPPDATA%\Hermes\allcare-agent.log.' }
Start-Process -FilePath $pythonw -ArgumentList ('"' + (Join-Path $agentDir 'agent_loop.py') + '"') -WorkingDirectory $agentDir -WindowStyle Hidden
Write-Host 'Agente Allcare instalado na inicialização do usuário e primeira sincronização concluída.' -ForegroundColor Green
