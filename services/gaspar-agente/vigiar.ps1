# Vigia do agente do Telegram. Roda como tarefa própria a cada 5 min ("Gaspar - vigia", ver README).
#
# A tarefa "Gaspar - iniciar" não serve de vigia: está com MultipleInstances=IgnoreNew e a instância que
# lançou o agente continua viva enquanto ele roda, então o Agendador recusa os disparos de 30 min
# (resultado 0x800710E0) e o iniciar.ps1 nunca chega a conferir nada. Em 28/10/2026 os processos bun do
# plugin do Telegram e do canal gaspar-eventos sumiram com o claude.exe de pé, e o agente ficou mudo por
# mais de uma hora, até ser reiniciado à mão.
#
# Aqui: se o claude do agente está no ar mas o poller do Telegram (bot.pid) ou o canal de eventos não estão,
# duas conferências seguidas (5 min) encerram a sessão (encerrar.ps1) e religam pela tarefa "Gaspar - iniciar".
# No máximo 3 religadas por hora: se a causa for outra, não fica reiniciando em loop (cada subida gasta tokens).
# Não trata o conector Sistema Hermes invalidado: isso pede login do dono, e reiniciar não resolve.
#
# -Simular: só mostra a decisão, sem gravar nem mexer em nada.   -Teste: confere a regra com casos fabricados.
param([switch]$Simular, [switch]$Teste)

# Devolve $null se o agente está saudável, ou o motivo em texto.
function Get-MotivoDoenca($idadeMin, $pollerVivo, $eventosEsperado, $eventosVivo) {
  if ($idadeMin -lt 5) { return $null }   # ainda subindo os canais
  if (-not $pollerVivo) { return 'poller do Telegram (bot.pid) morto' }
  if ($eventosEsperado -and -not $eventosVivo) { return 'canal gaspar-eventos morto' }
  return $null
}

if ($Teste) {
  $casos = @(
    @{ n = 'subindo: ainda nao exige nada'; a = @(2, $false, $true, $false); esperado = $null },
    @{ n = 'saudavel com eventos'; a = @(30, $true, $true, $true); esperado = $null },
    @{ n = 'saudavel sem chave (canal de eventos nao esperado)'; a = @(30, $true, $false, $false); esperado = $null },
    @{ n = 'poller morto'; a = @(30, $false, $true, $true); esperado = 'poller' },
    @{ n = 'canal de eventos morto'; a = @(30, $true, $true, $false); esperado = 'eventos' }
  )
  $ruins = 0
  foreach ($c in $casos) {
    $m = Get-MotivoDoenca $c.a[0] $c.a[1] $c.a[2] $c.a[3]
    $ok = if ($null -eq $c.esperado) { $null -eq $m } else { [bool]($m -match $c.esperado) }
    $marca = if ($ok) { 'ok    ' } else { 'FALHOU' }
    "$marca $($c.n)"
    if (-not $ok) { $ruins++ }
  }
  if ($ruins) { exit 1 }
  'todos os casos ok'
  exit 0
}

$estado = Join-Path $env:USERPROFILE '.claude-gaspar'   # perfil do agente: onde ele guarda o que é dele
$suspeita = Join-Path $estado 'vigia-suspeita.txt'
$ultimo = Join-Path $estado 'vigia-ultimo.txt'
$logArq = Join-Path $estado 'vigia.log'
$botPid = Join-Path $env:USERPROFILE '.claude\channels\telegram-gaspar\bot.pid'
$chave = Join-Path $PSScriptRoot '..\..\firebase_service_account_key.json'   # sem ela o iniciar.ps1 não liga o canal de eventos
$agora = Get-Date

function Registrar($acao, $detalhe) {
  Add-Content -Path $logArq -Value ('{0} | {1} | {2}' -f $agora.ToString('yyyy-MM-dd HH:mm:ss'), $acao, $detalhe)
}

$agente = @(Get-CimInstance Win32_Process -Filter "Name='claude.exe'" |
  Where-Object { $_.CommandLine -match 'plugin:telegram@claude-plugins-official' }) |
  Sort-Object CreationDate | Select-Object -First 1

if (-not $agente) {
  if ($Simular) { 'sem sessao do agente: a tarefa "Gaspar - iniciar" liga'; exit 0 }
  Remove-Item $suspeita -ErrorAction SilentlyContinue
  Set-Content $ultimo ('{0} sem sessao do agente (a tarefa iniciar liga)' -f $agora.ToString('s'))
  exit 0
}

$idade = ($agora - $agente.CreationDate).TotalMinutes
$pollerVivo = $false
try {
  $p = Get-Process -Id ([int](Get-Content $botPid -Raw).Trim()) -ErrorAction Stop
  $pollerVivo = ($p.ProcessName -eq 'bun')
} catch { }
$eventosEsperado = Test-Path $chave
$eventosVivo = [bool](Get-CimInstance Win32_Process -Filter "Name='bun.exe' AND ParentProcessId=$($agente.ProcessId)" |
  Where-Object { $_.CommandLine -match 'gaspar-eventos' })
$motivo = Get-MotivoDoenca $idade $pollerVivo $eventosEsperado $eventosVivo

if ($Simular) {
  $veredito = if ($motivo) { "DOENTE: $motivo" } else { 'saudavel' }
  'idade={0}min poller={1} eventosEsperado={2} eventosVivo={3} -> {4}' -f [int]$idade, $pollerVivo, $eventosEsperado, $eventosVivo, $veredito
  exit 0
}

Set-Content $ultimo ('{0} {1}' -f $agora.ToString('s'), $(if ($motivo) { "doente: $motivo" } else { 'saudavel' }))
if (-not $motivo) { Remove-Item $suspeita -ErrorAction SilentlyContinue; exit 0 }

# Só age se a doença persistir na conferência seguinte: um soluço passageiro não reinicia o agente.
if (-not (Test-Path $suspeita) -or ($agora - (Get-Item $suspeita).LastWriteTime).TotalMinutes -gt 20) {
  Set-Content $suspeita $motivo
  Registrar 'suspeita' $motivo
  exit 0
}
if (($agora - (Get-Item $suspeita).LastWriteTime).TotalMinutes -lt 3) { exit 0 }

$recentes = 0
if (Test-Path $logArq) {
  $recentes = @(Get-Content $logArq | Where-Object { $_ -match '\| reinicio \|' } | Where-Object {
    [datetime]::ParseExact($_.Substring(0, 19), 'yyyy-MM-dd HH:mm:ss', [Globalization.CultureInfo]::InvariantCulture) -gt $agora.AddHours(-1)
  }).Count
}
if ($recentes -ge 3) { Registrar 'limite' "3 religadas na ultima hora; nao religo ($motivo)"; exit 0 }

Registrar 'reinicio' $motivo
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'encerrar.ps1')
# A instância antiga do "iniciar" só termina quando o claude sai; com ela ainda Running, o Agendador recusaria o Run.
for ($i = 0; $i -lt 30; $i++) {
  if ((Get-ScheduledTask -TaskName 'Gaspar - iniciar').State -ne 'Running') { break }
  Start-Sleep 2
}
schtasks /Run /TN 'Gaspar - iniciar' | Out-Null
Remove-Item $suspeita -ErrorAction SilentlyContinue
