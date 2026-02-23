import React from 'react';

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

  const timerDisplay = formatTime(isTimerRunning ? seconds : sessionTotalSeconds)
    .split(':').slice(1).join(':');
  const timerHours = formatTime(isTimerRunning ? seconds : sessionTotalSeconds).split(':')[0];

  return (
    <div className="flex flex-col gap-4 md:gap-6 overflow-hidden px-0">

      {/* Card de Especialista / Chat */}
      <div className="bg-gradient-to-br from-indigo-600 to-blue-700 !rounded-none md:rounded-[2rem] p-4 md:p-5 text-white shadow-2xl flex-shrink-0 relative overflow-hidden group">
        <div className="absolute -right-16 -top-16 w-48 h-48 bg-white/5 rounded-full blur-3xl group-hover:bg-white/10 transition-colors"></div>
        <div className="relative z-10 flex items-center gap-3">
          <div className="flex-1">
            <h4 className="text-[9px] font-black uppercase tracking-widest opacity-60 mb-2">Especialista IA</h4>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  placeholder="Link do chat contextual..."
                  value={chatUrl}
                  onChange={e => setChatUrl(e.target.value)}
                  className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-xs font-medium focus:ring-2 focus:ring-white/30 outline-none text-white placeholder:text-white/20 transition-all"
                />
                {chatUrl !== (task.chat_gemini_url || '') && (
                  <button
                    onClick={handleSaveChatUrl}
                    className="absolute right-1 top-1 bottom-1 bg-emerald-500 text-white px-3 rounded-lg text-[8px] font-black uppercase shadow-lg hover:bg-emerald-600 transition-colors"
                  >
                    Salvar
                  </button>
                )}
              </div>
              <a
                href={task.chat_gemini_url || (task.categoria === 'CLC' ? "https://gemini.google.com/gem/096c0e51e1b9" : "https://gemini.google.com/")}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-white text-indigo-600 w-10 h-10 flex items-center justify-center rounded-xl hover:bg-slate-100 transition-all shadow-xl flex-shrink-0"
                title="Abrir Chat"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Card Principal do Cronômetro */}
      <div className={`!rounded-none md:rounded-[2rem] border p-6 flex flex-col relative overflow-hidden transition-all duration-1000 ${isBreakActive ? 'bg-rose-500/5 border-rose-500/20' : isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200 shadow-xl shadow-slate-200/50'}`}>
        <div className={`absolute inset-0 transition-opacity duration-700 ${isBreakActive ? 'bg-rose-500/10' : isTimerRunning ? 'bg-blue-500/5' : 'bg-transparent'}`}></div>

        <div className="relative z-10 flex flex-col items-center gap-4">

          {/* Status Label */}
          <span className={`text-[10px] font-black uppercase tracking-[0.4em] transition-colors ${isBreakActive ? 'text-rose-400 animate-pulse' : isTimerRunning ? 'text-white/30' : 'text-slate-400'}`}>
            {isBreakActive ? 'Descanso em Curso' : isTimerRunning ? 'Sessão Ativa' : 'Foco em Pausa'}
          </span>

          {/* Números do Cronômetro — elemento principal */}
          <div className="flex flex-col items-center">
            <div
              className={`font-black tabular-nums leading-none tracking-tighter transition-colors select-none ${isBreakActive ? 'text-rose-500' : isTimerRunning ? 'text-white' : 'text-[#172B4D]'}`}
              style={{ fontSize: 'clamp(56px, 10vw, 88px)' }}
            >
              {timerDisplay}
            </div>
            <div className={`text-sm font-bold uppercase tracking-[0.2em] mt-1 ${isBreakActive ? 'text-rose-400/50' : 'text-blue-500'}`}>
              {isBreakActive ? 'Pausa' : `${timerHours}h`}
            </div>
          </div>

          {/* Pill Seletor Foco / Descanso (apenas com Pomodoro) */}
          {appSettings.pomodoro?.enabled && (
            <div className={`flex items-center p-1 rounded-full w-full max-w-[240px] ${isTimerRunning ? 'bg-black/30' : 'bg-slate-100'}`}>
              <button
                onClick={() => { setPomodoroMode('focus'); }}
                className={`flex-1 px-4 py-2 rounded-full text-[9px] font-black uppercase tracking-widest transition-all ${pomodoroMode === 'focus' ? 'bg-blue-600 text-white shadow-md' : isTimerRunning ? 'text-white/40 hover:text-white/70' : 'text-slate-400 hover:text-slate-600'}`}
              >
                Foco
              </button>
              <button
                onClick={() => { setPomodoroMode('break'); }}
                className={`flex-1 px-4 py-2 rounded-full text-[9px] font-black uppercase tracking-widest transition-all ${pomodoroMode === 'break' ? 'bg-rose-600 text-white shadow-md' : isTimerRunning ? 'text-white/40 hover:text-white/70' : 'text-slate-400 hover:text-slate-600'}`}
              >
                Descanso
              </button>
            </div>
          )}

          {/* Botão Principal: Play/Pause — largo e chamativo */}
          <button
            onClick={handleToggleTimer}
            className={`w-full max-w-[300px] flex items-center justify-center gap-3 px-6 py-4 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all hover:scale-105 active:scale-95 shadow-xl ${isTimerRunning
              ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20 hover:bg-rose-500 hover:text-white'
              : 'bg-blue-600 text-white shadow-blue-600/30 hover:bg-blue-500'
            }`}
          >
            {isTimerRunning ? (
              <>
                <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
                Pausar
              </>
            ) : (
              <>
                <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                {sessionTotalSeconds > 0 ? 'Retomar' : 'Iniciar'}
              </>
            )}
          </button>

          {/* Botões secundários */}
          <div className="flex gap-2 w-full max-w-[300px]">
            <button
              onClick={() => {
                setModalConfig({ type: 'reminder', isOpen: true });
                if (task.reminder_at) {
                  const [d, t] = task.reminder_at.split('T');
                  setReminderDate(d);
                  setReminderTime(t.substring(0, 5));
                } else {
                  setReminderDate(new Date().toISOString().split('T')[0]);
                  setReminderTime("");
                }
              }}
              className={`flex-1 p-3 rounded-xl transition-all shadow hover:scale-105 active:scale-95 flex items-center justify-center gap-1.5 text-[9px] font-black uppercase tracking-wider ${task.reminder_at && !task.reminder_sent ? 'bg-amber-500 text-white shadow-amber-500/20' : isTimerRunning ? 'bg-white/5 text-white/40 border border-white/5 hover:bg-white/10' : 'bg-slate-100 text-slate-500 hover:text-amber-600 hover:bg-amber-50 border border-slate-200'}`}
              title="Agendar Lembrete"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
              Lembrete
            </button>

            <button
              onClick={handleResetTimer}
              className={`flex-1 p-3 rounded-xl transition-all shadow hover:scale-105 active:scale-95 flex items-center justify-center gap-1.5 text-[9px] font-black uppercase tracking-wider ${isTimerRunning
                ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20 hover:bg-rose-500 hover:text-white'
                : 'bg-slate-100 text-slate-500 hover:text-rose-500 hover:bg-rose-50 border border-slate-200'
              }`}
              title="Reiniciar Cronômetro"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
              Zerar
            </button>

            <button
              onClick={handleCompleteTaskRequest}
              className={`flex-1 p-3 rounded-xl transition-all shadow hover:scale-105 active:scale-95 flex items-center justify-center gap-1.5 text-[9px] font-black uppercase tracking-wider ${task.status === 'concluído'
                ? 'bg-emerald-500 text-white shadow-emerald-500/20'
                : isTimerRunning
                  ? 'bg-white/5 text-white/40 border border-white/10 hover:bg-white/10 hover:text-white'
                  : 'bg-slate-100 text-slate-500 hover:bg-emerald-50 hover:text-emerald-600 border border-slate-200'
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
              {task.status === 'concluído' ? 'Feita' : 'Finalizar'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
