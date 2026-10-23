# Sobe a sessão residente do Gaspar (24 h por dia, todos os dias). O Agendador chama este script a cada 30 min
# e a tarefa "Gaspar - encerrar" reinicia a sessão às 04:30 (contexto novo; agendamentos do /loop vencem em 7 dias);
# se o agente já estiver rodando, sai sem fazer nada (é o que faz o papel de vigia).
$agente = Get-CimInstance Win32_Process -Filter "Name='claude.exe'" |
  Where-Object { $_.CommandLine -match 'plugin:telegram@claude-plugins-official' }
if ($agente) { exit 0 }

$Host.UI.RawUI.WindowTitle = 'Gaspar agente'
# Perfil próprio do agente: login, plugins, memória e configurações separados dos do André.
$env:CLAUDE_CONFIG_DIR = "$env:USERPROFILE\.claude-gaspar"
# O token do bot fica só em telegram-gaspar: as outras sessões do Claude Code que carregarem
# o plugin não acham token, saem na hora e não disputam o getUpdates com o agente.
$env:TELEGRAM_STATE_DIR = "$env:USERPROFILE\.claude\channels\telegram-gaspar"
# Sem bun no PATH o plugin falha e o Claude Code passa ~15 min sem tentar de novo.
# Terminais abertos antes da instalação do Bun (e o Agendador) não têm o PATH novo.
$env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
# Uma falha anterior do plugin fica gravada neste cache e faz o agente pular o Telegram por ~15 min.
$cache = "$env:CLAUDE_CONFIG_DIR\mcp-needs-auth-cache.json"
if (Test-Path $cache) {
  $c = Get-Content $cache -Raw | ConvertFrom-Json
  $c.PSObject.Properties.Remove('plugin:telegram:telegram')
  [IO.File]::WriteAllText($cache, ($c | ConvertTo-Json -Compress))  # sem BOM (Set-Content do PS 5.1 grava BOM)
}
Set-Location $PSScriptRoot

# Canal gaspar-eventos (marco 2): usa a chave da conta de serviço do worker do WhatsApp; sem ela, o /loop varre tudo a cada 5 min.
$canais = @('plugin:telegram@claude-plugins-official')
$cron = '*/5 5-22 * * *'
if (Test-Path '..\..\firebase_service_account_key.json') {
  $env:GASPAR_EVENTOS = '1'
  $canais = @('--channels') + $canais + @('--dangerously-load-development-channels', 'server:gaspar-eventos')
  $cron = '*/15 5-22 * * *'
  # O Claude Code pede confirmação do --dangerously-load-development-channels a TODO início, sem opção
  # para lembrar. Este job escreve um Enter direto no buffer de entrada do console deste PowerShell
  # (WriteConsoleInput), sem depender de foco nem de tela desbloqueada, até a sessão começar (aparece o
  # histórico da conversa). Enter a mais no campo vazio não faz nada.
  Start-Job -ArgumentList $PID, (Get-Date), "$env:CLAUDE_CONFIG_DIR\projects" -ScriptBlock {
    param($console, $inicio, $projetos)
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ConsoleEnter {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct KEY_EVENT_RECORD { public int bKeyDown; public ushort wRepeatCount; public ushort wVirtualKeyCode;
    public ushort wVirtualScanCode; public char UnicodeChar; public uint dwControlKeyState; }
  [StructLayout(LayoutKind.Explicit)]
  public struct INPUT_RECORD { [FieldOffset(0)] public ushort EventType; [FieldOffset(4)] public KEY_EVENT_RECORD KeyEvent; }
  [DllImport("kernel32.dll")] static extern bool FreeConsole();
  [DllImport("kernel32.dll")] static extern bool AttachConsole(uint pid);
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateFile(string n, uint a, uint s, IntPtr sa, uint c, uint f, IntPtr t);
  [DllImport("kernel32.dll")] static extern bool WriteConsoleInput(IntPtr h, INPUT_RECORD[] b, uint n, out uint w);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  public static bool Enviar(uint pid) {
    FreeConsole();
    if (!AttachConsole(pid)) return false;
    IntPtr h = CreateFile("CONIN$", 0xC0000000, 3, IntPtr.Zero, 3, 0, IntPtr.Zero);
    var r = new INPUT_RECORD[2];
    for (int i = 0; i < 2; i++) { r[i].EventType = 1; r[i].KeyEvent.bKeyDown = i == 0 ? 1 : 0; r[i].KeyEvent.wRepeatCount = 1;
      r[i].KeyEvent.wVirtualKeyCode = 0x0D; r[i].KeyEvent.wVirtualScanCode = 0x1C; r[i].KeyEvent.UnicodeChar = '\r'; }
    uint w; bool ok = WriteConsoleInput(h, r, 2, out w);
    CloseHandle(h); FreeConsole(); return ok && w == 2;
  }
}
'@
    $limite = $inicio.AddHours(6)
    while ((Get-Date) -lt $limite) {
      Start-Sleep 15
      $sessao = Get-ChildItem "$projetos\*gaspar-agente\*.jsonl" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $inicio }
      if ($sessao) { break }
      try { [ConsoleEnter]::Enviar([uint32]$console) | Out-Null } catch {}
    }
  } | Out-Null
} else {
  $canais = @('--channels') + $canais
}
$prompt = "Voce acabou de iniciar. 0) Chame conversa_telegram para retomar o fio da conversa recente com o Andre (nao repita a ele o que ja foi dito; continue de onde parou). 1) Chame obter_estado_atual e obter_fila_atencao. 2) Agende o pulso com CronCreate, cron '$cron', prompt: siga o conteudo de .claude/loop.md (sem pulso de madrugada; eventos continuam chegando). 3) Briefing da manha (.claude/briefing.md), se o registro de hoje (consultar_execucoes_agente, gaspar-agente:AAAA-MM-DD) nao mostrar briefing nem bom-dia ja enviado: se ja passou das 05:00, faca agora; se for antes, agende com CronCreate para as 05:00 de hoje."
# --channels aceita vários valores: o -- impede que ele engula o prompt.
# Entre aspas porque o Windows PowerShell 5.1 descarta um -- solto.
# Sonnet 5.5: o Opus consome o limite semanal da assinatura bem mais rápido (medido em 22/10: ~94 mil tokens de contexto por turno).
claude --model claude-sonnet-5-5 @canais '--' $prompt
