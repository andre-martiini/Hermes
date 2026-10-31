# Faz o Gaspar subir sozinho depois de um reinício do Windows. Rode UMA vez, no PowerShell, como o usuário que roda o agente
# (não precisa de administrador):
#   .\instalar-tarefas.ps1                        mostra o que faria, sem alterar nada
#   .\instalar-tarefas.ps1 -Aplicar               aplica
#   .\instalar-tarefas.ps1 -Aplicar -TravarTela   aplica e trava a tela depois do logon (use junto com o login automático)
#
# 1. "Gaspar - iniciar" ganha um gatilho "ao fazer logon" (30 s de atraso, para a rede subir). Antes, depois de um reinício o
#    agente só voltava no próximo disparo de 30 min. É a MESMA tarefa, não uma segunda: o IgnoreNew dela impede dois agentes.
#    Atenção: recadastrar a tarefa encerra a instância que está rodando; o script a liga de novo em seguida.
# 2. Cria "Gaspar - vigia" (vigiar.ps1, a cada 5 min), se não existir.
# 3. Com -TravarTela, cria "Gaspar - travar tela": trava a tela 90 s depois do logon. O agente e o worker do WhatsApp seguem
#    rodando com a tela travada (o iniciar.ps1 já foi feito para isso).
# O worker do WhatsApp já sobe no logon: não muda. O login automático do Windows NÃO é configurado aqui (pede a senha): ver README.
param([switch]$Aplicar, [switch]$TravarTela)
$ErrorActionPreference = 'Stop'
$vigiar = Join-Path $PSScriptRoot 'vigiar.ps1'
$pasta = Join-Path $env:USERPROFILE '.claude-gaspar\tarefas-backup'
if ($vigiar -match '\s') { throw "o caminho do vigiar.ps1 tem espaco ($vigiar); ajuste o script" }
if (-not $Aplicar) { 'MODO SIMULACAO: nada sera alterado. Use -Aplicar para aplicar.'; '' }

# --- 1. gatilho de logon na tarefa "iniciar" ---
$nome = 'Gaspar - iniciar'
$t = Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue
if (-not $t) {
  "AVISO: a tarefa '$nome' nao existe (crie pelo README)."
} elseif (@($t.Triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger' }).Count -gt 0) {
  'iniciar: ja tem gatilho de logon (nada a fazer)'
} else {
  'iniciar: vai ganhar gatilho de logon com 30 s de atraso (e sera religada em seguida)'
  if ($Aplicar) {
    New-Item -ItemType Directory -Force $pasta | Out-Null
    $original = (Export-ScheduledTask -TaskName $nome) | Out-String
    $arq = Join-Path $pasta ('iniciar-{0}.xml' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    [IO.File]::WriteAllText($arq, $original)
    "  backup do XML: $arq"
    $xml = [xml]$original
    $uri = $xml.DocumentElement.NamespaceURI
    $logon = $xml.CreateElement('LogonTrigger', $uri)
    foreach ($par in @(@('Enabled', 'true'), @('UserId', "$env:USERDOMAIN\$env:USERNAME"), @('Delay', 'PT30S'))) {
      $e = $xml.CreateElement($par[0], $uri); $e.InnerText = $par[1]; [void]$logon.AppendChild($e)
    }
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable); $ns.AddNamespace('t', $uri)
    [void]$xml.SelectSingleNode('//t:Triggers', $ns).AppendChild($logon)
    try {
      Register-ScheduledTask -TaskName $nome -Xml $xml.OuterXml -Force | Out-Null
      $novo = Get-ScheduledTask -TaskName $nome
      $temLogon = @($novo.Triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger' }).Count -gt 0
      $temRepeticao = @($novo.Triggers | Where-Object { $_.Repetition.Interval -eq 'PT30M' }).Count -gt 0
      if (-not ($temLogon -and $temRepeticao)) { throw 'gatilhos inesperados depois de recadastrar' }
    } catch {
      "  FALHOU ($_); restaurando o backup"
      Register-ScheduledTask -TaskName $nome -Xml $original -Force | Out-Null
      throw
    }
    Start-ScheduledTask -TaskName $nome
    '  ok: gatilho de logon criado e a tarefa religada'
  }
}

# --- 2. vigia ---
if (Get-ScheduledTask -TaskName 'Gaspar - vigia' -ErrorAction SilentlyContinue) {
  'vigia: ja existe (nada a fazer)'
} else {
  'vigia: sera criada (vigiar.ps1, a cada 5 min)'
  if ($Aplicar) {
    $tr = "conhost.exe --headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File $vigiar"
    schtasks /Create /TN 'Gaspar - vigia' /SC MINUTE /MO 5 /IT /TR $tr /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'schtasks /Create falhou para o vigia' }
    schtasks /Run /TN 'Gaspar - vigia' | Out-Null
    '  ok: vigia criada e disparada uma vez (confira %USERPROFILE%\.claude-gaspar\vigia-ultimo.txt)'
  }
}

# --- 3. travar a tela ---
if ($TravarTela) {
  if (Get-ScheduledTask -TaskName 'Gaspar - travar tela' -ErrorAction SilentlyContinue) {
    'travar tela: ja existe (nada a fazer)'
  } else {
    'travar tela: sera criada (90 s depois do logon)'
    if ($Aplicar) {
      # schtasks /SC ONLOGON exige administrador; Register-ScheduledTask com o proprio usuario, nao
      $gat = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
      $gat.Delay = 'PT1M30S'
      $acao = New-ScheduledTaskAction -Execute 'rundll32.exe' -Argument 'user32.dll,LockWorkStation'
      $prin = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
      Register-ScheduledTask -TaskName 'Gaspar - travar tela' -Trigger $gat -Action $acao -Principal $prin | Out-Null
      '  ok: tarefa criada'
    }
  }
} else {
  'travar tela: nao pedido (use -TravarTela se for ligar o login automatico)'
}

''
if ($Aplicar) { 'Feito. Falta so o login automatico do Windows, se quiser subir sem digitar a senha (ver README).' }
else { 'Conferiu? Rode de novo com -Aplicar.' }
