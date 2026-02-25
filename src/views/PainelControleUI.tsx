import React, { useMemo } from 'react';

interface PainelControleUIProps {
  task: any;
  chatUrl: string;
  setChatUrl: (val: string) => void;
  handleSaveChatUrl: () => void;
  isTimerRunning: boolean;
  sessionTotalSeconds: number;
  seconds: number;
  pomodoroMode: 'focus' | 'break';
  setPomodoroMode: (mode: 'focus' | 'break') => void;
  handleToggleTimer: () => void;
  handleResetTimer: () => void;
  handleCompleteTaskRequest: () => void;
  appSettings: any;
  currentTime: Date;
  formatTime: (s: number) => string;
  isBreakActive: boolean;
  setModalConfig: (config: any) => void;
  setReminderDate: (val: string) => void;
  setReminderTime: (val: string) => void;
}

export const PainelControleUI = ({
  task, chatUrl, setChatUrl, handleSaveChatUrl, isTimerRunning, sessionTotalSeconds, seconds,
  pomodoroMode, setPomodoroMode, handleToggleTimer, handleResetTimer, handleCompleteTaskRequest,
  appSettings, currentTime, formatTime, isBreakActive, setModalConfig,
  setReminderDate, setReminderTime
}: PainelControleUIProps) => {

  // --- Lógica de Tempo Restante (Pomodoro) ---
  const countdownInfo = useMemo(() => {
    if (!appSettings.pomodoro?.enabled) return null;

    const focusLimit = (appSettings.pomodoro.focusTime || 25) * 60;
    const breakLimit = (appSettings.pomodoro.breakTime || 5) * 60;
    
    const limit = pomodoroMode === 'focus' ? focusLimit : breakLimit;
    const remaining = Math.max(0, limit - seconds);
    
    // Formata MM:SS
    const formatted = formatTime(remaining).split(':').slice(1).join(':');
    const label = pomodoroMode === 'focus' ? 'Para o Descanso' : 'Para o Foco';
    const colorClass = pomodoroMode === 'focus' ? 'text-blue-500' : 'text-rose-500';
    const bgClass = pomodoroMode === 'focus' ? 'bg-blue-500/5 border-blue-500/10' : 'bg-rose-500/5 border-rose-500/10';

    return { formatted, label, colorClass, bgClass, remaining };
  }, [appSettings.pomodoro, pomodoroMode, seconds, formatTime]);

  // Exibição do cronômetro principal (Tempo total acumulado ou da sessão)
  const timerDisplay = formatTime(isTimerRunning ? seconds : sessionTotalSeconds).split(':').slice(1).join(':');
  const timerHours = formatTime(isTimerRunning ? seconds : sessionTotalSeconds).split(':')[0];

  return (
    <div className="flex flex-col gap-4 md:gap-6 overflow-hidden px-0">

      {/* Card de Especialista / Chat - Ainda mais compacto no mobile */}
      <div className="bg-gradient-to-br from-indigo-600 to-blue-700 rounded-none md:rounded-[2rem] p-3 md:p-5 text-white shadow-2xl flex-shrink-0 relative overflow-hidden group">
        <div className="absolute -right-16 -top-16 w-32 h-32 bg-white/5 rounded-full blur-2xl group-hover:bg-white/10 transition-colors"></div>
        <div className="relative z-10 flex items-center gap-3">
            <div className="relative flex-1">
              <input
                type="text"
                placeholder="IA Chat..."
                value={chatUrl}
                onChange={e => setChatUrl(e.target.value)}
                className="w-full bg-black/20 border border-white/10 rounded-none md:rounded-xl px-3 py-1.5 text-[10px] md:text-xs font-medium focus:ring-2 focus:ring-white/30 outline-none text-white placeholder:text-white/20 transition-all"
              />
              {chatUrl !== (task.chat_gemini_url || '') && (
                <button
                  onClick={handleSaveChatUrl}
                  className="absolute right-1 top-1 bottom-1 bg-emerald-500 text-white px-2 rounded-none md:rounded-lg text-[7px] font-black uppercase"
                >
                  OK
                </button>
              )}
            </div>
            <a
              href={task.chat_gemini_url || "https://gemini.google.com/"}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-white text-indigo-600 w-8 h-8 md:w-10 md:h-10 flex items-center justify-center rounded-none md:rounded-xl shadow-xl flex-shrink-0"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
            </a>
        </div>
      </div>

      {/* Card Principal do Cronômetro - Versão Ultra Compacta Mobile */}
      <div className={`rounded-none md:rounded-[2rem] border p-3 md:p-6 flex flex-col relative overflow-hidden transition-all duration-1000 ${isBreakActive ? 'bg-rose-500/5 border-rose-500/20' : isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200 shadow-xl'}`}>
        
        <div className="relative z-10 flex flex-col gap-3 md:gap-6">
          
          {/* Header do Card (Mobile: Lado a Lado) */}
          <div className="flex flex-row items-center justify-between md:flex-col md:gap-6">
            
            {/* Display Principal (Esquerda no Mobile) */}
            <div className="flex flex-col items-start md:items-center">
              <span className={`text-[7px] md:text-[10px] font-black uppercase tracking-[0.4em] mb-1 ${isBreakActive ? 'text-rose-400' : isTimerRunning ? 'text-white/30' : 'text-slate-400'}`}>
                {isBreakActive ? 'Descanso' : isTimerRunning ? 'Foco' : 'Parado'}
              </span>
              <div
                className={`font-black tabular-nums leading-none tracking-tighter transition-colors select-none ${isBreakActive ? 'text-rose-500' : isTimerRunning ? 'text-white' : 'text-[#172B4D]'}`}
                style={{ fontSize: 'clamp(32px, 8vw, 88px)' }}
              >
                {timerDisplay}
              </div>
              <div className={`text-[8px] md:text-sm font-bold uppercase tracking-[0.1em] mt-0.5 ${isBreakActive ? 'text-rose-400/50' : 'text-blue-500'}`}>
                {timerHours}h Acumulados
              </div>
            </div>

            {/* Pomodoro Countdown (Direita no Mobile) */}
            {countdownInfo && (
              <div className={`p-2 md:p-4 rounded-none md:rounded-2xl border flex flex-col items-center justify-center transition-all min-w-[100px] md:max-w-[280px] ${countdownInfo.bgClass}`}>
                <span className={`text-[8px] md:text-[9px] font-black uppercase tracking-widest mb-0.5 opacity-60 ${countdownInfo.colorClass}`}>
                  {countdownInfo.label.split(' ')[2]}
                </span>
                <div className={`text-lg md:text-3xl font-black tabular-nums leading-none ${countdownInfo.colorClass}`}>
                  {countdownInfo.formatted}
                </div>
                <div className="hidden md:block w-full h-1 bg-current/10 rounded-full mt-3 overflow-hidden">
                  <div 
                    className="h-full bg-current transition-all duration-1000" 
                    style={{ width: `${(countdownInfo.remaining / ((pomodoroMode === 'focus' ? appSettings.pomodoro.focusTime : appSettings.pomodoro.breakTime) * 60)) * 100}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Botões de Ação Ultra Achatados para Mobile */}
          <div className="flex flex-row gap-1.5 w-full items-center justify-center">
            <button
              onClick={handleToggleTimer}
              className={`flex-[1.5] h-10 md:h-14 flex items-center justify-center gap-2 rounded-none md:rounded-xl text-[10px] font-black uppercase tracking-widest transition-all shadow-lg ${isTimerRunning
                ? 'bg-rose-500/20 text-rose-500 border border-rose-500/20'
                : 'bg-blue-600 text-white shadow-blue-600/30'
              }`}
            >
              {isTimerRunning ? (
                <svg className="w-5 h-5 md:w-5 md:h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
              ) : (
                <svg className="w-5 h-5 md:w-5 md:h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
              )}
            </button>

            <button
              onClick={() => {
                if (task.reminder_at) {
                  const [date, time] = task.reminder_at.split('T');
                  setReminderDate(date);
                  setReminderTime(time.slice(0, 5));
                } else {
                  // Pre-fill with today/now if no reminder
                  const now = new Date();
                  setReminderDate(now.toISOString().split('T')[0]);
                  setReminderTime(now.toTimeString().slice(0, 5));
                }
                setModalConfig({ type: 'reminder', isOpen: true });
              }}
              className={`flex-1 h-10 md:h-14 flex items-center justify-center rounded-none md:rounded-xl transition-all shadow-sm ${task.reminder_at && !task.reminder_sent ? 'bg-amber-500 text-white' : 'bg-slate-100 text-slate-500 border border-slate-200'}`}
            >
              <svg className="w-5 h-5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" strokeWidth="2.5" /></svg>
            </button>

            <button
              onClick={handleResetTimer}
              className="flex-1 h-10 md:h-14 flex items-center justify-center rounded-none md:rounded-xl bg-slate-100 text-slate-500 border border-slate-200"
            >
              <svg className="w-5 h-5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeWidth="2.5" /></svg>
            </button>

            <button
              onClick={handleCompleteTaskRequest}
              className="flex-1 h-10 md:h-14 flex items-center justify-center rounded-none md:rounded-xl bg-slate-100 text-slate-500 border border-slate-200"
            >
              <svg className="w-5 h-5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" strokeWidth="2.5" /></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};