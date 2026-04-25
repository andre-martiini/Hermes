import React, { useMemo } from 'react';

interface PainelControleUIProps {
  task: any;
  chatUrl: string;
  setChatUrl: (val: string) => void;
  handleSaveChatUrl: () => void;
  handleCompleteTaskRequest: () => void;
  setModalConfig: (config: any) => void;
  setReminderDate: (val: string) => void;
  setReminderTime: (val: string) => void;
  showToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

export const PainelControleUI = ({
  task, chatUrl, setChatUrl, handleSaveChatUrl, handleCompleteTaskRequest,
  setModalConfig, setReminderDate, setReminderTime, showToast
}: PainelControleUIProps) => {
  const reminders = useMemo(() => {
    const taskReminders = Array.isArray(task.reminders) ? [...task.reminders] : [];
    taskReminders.sort((a, b) => new Date(a.reminder_at).getTime() - new Date(b.reminder_at).getTime());
    if (taskReminders.length > 0) return taskReminders;
    if (task.reminder_at) return [{ reminder_at: task.reminder_at, reminder_sent: Boolean(task.reminder_sent) }];
    return [];
  }, [task.reminder_at, task.reminder_sent, task.reminders]);

  const nextPendingReminder = useMemo(
    () => reminders.find((reminder: any) => !reminder.reminder_sent),
    [reminders]
  );

  return (
    <div className="flex flex-col gap-4 md:gap-6 overflow-hidden px-0">

      {/* Card de Especialista / Chat */}
      <div className="bg-gradient-to-br from-indigo-600 to-blue-700 rounded-none md:rounded-[1.5rem] p-3 md:p-4 text-white shadow-2xl flex-shrink-0 relative overflow-hidden group">
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

      {/* Botões de Ação Auxiliares */}
      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={() => {
            if (nextPendingReminder?.reminder_at) {
              const [date, time] = nextPendingReminder.reminder_at.split('T');
              setReminderDate(date);
              setReminderTime(time.slice(0, 5));
            } else {
              const now = new Date();
              setReminderDate(now.toISOString().split('T')[0]);
              setReminderTime(now.toTimeString().slice(0, 5));
            }
            setModalConfig({ type: 'reminder', isOpen: true });
          }}
          className={`h-16 flex flex-col items-center justify-center gap-1 rounded-none md:rounded-2xl transition-all border ${nextPendingReminder ? 'bg-amber-500 text-white border-amber-600 shadow-lg' : 'bg-white text-slate-400 border-slate-200 hover:bg-slate-50'}`}
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" strokeWidth="2.5" /></svg>
          <span className="text-[8px] font-black uppercase tracking-widest">Lembrete</span>
        </button>

        <button
          onClick={handleCompleteTaskRequest}
          className="h-16 flex flex-col items-center justify-center gap-1 rounded-none md:rounded-2xl bg-emerald-50 text-emerald-600 border border-emerald-100 hover:bg-emerald-100 transition-all shadow-sm"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" strokeWidth="3" /></svg>
          <span className="text-[8px] font-black uppercase tracking-widest">Concluir</span>
        </button>
      </div>
    </div>
  );
};
