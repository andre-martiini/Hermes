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

$taskName = 'Hermes Allcare Local Agent'
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + (Join-Path $agentDir 'sync_once.py') + '"') -WorkingDirectory $agentDir
$atLogon = New-ScheduledTaskTrigger -AtLogOn
$periodic = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Hours 6) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($atLogon, $periodic) -Settings $settings -Description 'Sincroniza boletos do Portal Allcare com o Hermes pela conexão local.' -Force | Out-Null

& $python (Join-Path $agentDir 'sync_once.py')
if ($LASTEXITCODE -ne 0) { throw 'Agente instalado, mas a primeira sincronização falhou. Consulte %LOCALAPPDATA%\Hermes\allcare-agent.log.' }
Write-Host 'Agente Allcare instalado e primeira sincronização concluída.' -ForegroundColor Green
