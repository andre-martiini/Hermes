$taskName = 'Hermes Allcare Local Agent'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
Write-Host 'Tarefa agendada removida. As credenciais permanecem no cofre do Windows.'
