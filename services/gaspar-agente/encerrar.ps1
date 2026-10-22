# Encerra só a sessão do agente (não as outras sessões do Claude Code do André) e os processos bun
# dela: o plugin Telegram tenta matar poller órfão com `ps`, que não existe no Windows.
$todos = Get-CimInstance Win32_Process
$agente = $todos | Where-Object { $_.Name -eq 'claude.exe' -and $_.CommandLine -match 'plugin:telegram@claude-plugins-official' }
if (-not $agente) { exit 0 }

$pids = @($agente.ProcessId)
for ($i = 0; $i -lt $pids.Count; $i++) {
  $pids += @($todos | Where-Object { $_.ParentProcessId -eq $pids[$i] } | ForEach-Object { $_.ProcessId })
}
# Filhos antes do pai, para nenhum ficar órfão no meio do caminho.
[array]::Reverse($pids)
$pids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
