import React, { useEffect, useMemo } from 'react';
import { Tarefa, GoogleCalendarEvent, formatDate, formatDateLocalISO } from '../types';
import { DayView } from './DayView';

export const CalendarView = ({
  tasks,
  googleEvents = [],
  viewMode,
  currentDate,
  onDateChange,
  onTaskClick,
  onViewModeChange,
  onTaskUpdate,
  onExecuteTask,
  onReorderTasks,
  showToast
}: {
  tasks: Tarefa[],
  googleEvents?: GoogleCalendarEvent[],
  viewMode: 'month' | 'week' | 'day',
  currentDate: Date,
  onDateChange: (d: Date) => void,
  onTaskClick: (t: Tarefa) => void,
  onViewModeChange: (m: 'month' | 'week' | 'day') => void,
  onTaskUpdate: (id: string, updates: Partial<Tarefa>, suppressToast?: boolean) => void,
  onExecuteTask: (t: Tarefa) => void,
  onReorderTasks?: (taskId: string, targetTaskId: string, label?: string) => void,
  showToast?: (message: string, type: 'success' | 'error' | 'info') => void
}) => {
  const [days, setDays] = React.useState<Date[]>([]);

  useEffect(() => {
    const d = new Date(currentDate);
    const newDays = [];

    if (viewMode === 'day') {
      newDays.push(new Date(currentDate));
    } else if (viewMode === 'month') {
      d.setDate(1);
      const dayOfWeek = d.getDay();
      d.setDate(d.getDate() - dayOfWeek);

      for (let i = 0; i < 42; i++) {
        newDays.push(new Date(d));
        d.setDate(d.getDate() + 1);
      }
    } else {
      const dayOfWeek = d.getDay();
      d.setDate(d.getDate() - dayOfWeek);
      for (let i = 0; i < 7; i++) {
        newDays.push(new Date(d));
        d.setDate(d.getDate() + 1);
      }
    }
    setDays(newDays);
  }, [currentDate, viewMode]);

  const googleEventsByDay = useMemo(() => {
    const map: Record<string, GoogleCalendarEvent[]> = {};
    if (!googleEvents) return map;
    
    googleEvents.forEach(e => {
      if (!e.data_inicio || !e.data_fim) return;
      
      const startStr = e.data_inicio.split('T')[0];
      const endStr = e.data_fim.split('T')[0];

      let current = new Date(startStr + 'T12:00:00Z');
      const end = new Date(endStr + 'T12:00:00Z');

      if (isNaN(current.getTime()) || isNaN(end.getTime())) return;

      const isTimed = e.data_inicio.includes('T');
      let iterations = 0;
      while (isTimed ? (current <= end) : (current < end)) {
        if (iterations > 62) break;
        iterations++;
        const dateStr = current.toISOString().split('T')[0];
        if (!map[dateStr]) map[dateStr] = [];
        if (!map[dateStr].find(x => x.id === e.id)) {
          map[dateStr].push(e);
        }
        current.setDate(current.getDate() + 1);
      }
    });
    return map;
  }, [googleEvents]);

  const tasksByDay = useMemo(() => {
    const map: Record<string, Tarefa[]> = {};
    if (!tasks) return map;

    tasks.forEach(t => {
      if (!t.data_limite || t.data_limite === '-' || t.data_limite === '0000-00-00') return;

      const endStr = t.data_limite;
      const startStr = t.is_single_day ? endStr : (t.data_inicio || endStr);

      let current = new Date(startStr + 'T12:00:00Z');
      const end = new Date(endStr + 'T12:00:00Z');

      if (isNaN(current.getTime()) || isNaN(end.getTime())) return;

      const diffTime = end.getTime() - current.getTime();
      const diffDays = diffTime / (1000 * 3600 * 24);

      if (current > end || diffDays > 60) {
        current = end;
      }

      let iterations = 0;
      while (current <= end) {
        if (iterations > 62) break; 
        iterations++;

        const dateStr = current.toISOString().split('T')[0];
        if (!map[dateStr]) map[dateStr] = [];
        if (!map[dateStr].find(x => x.id === t.id)) {
          map[dateStr].push(t);
        }
        current.setDate(current.getDate() + 1);
      }
    });
    return map;
  }, [tasks]);

  const nextPeriod = () => {
    const d = new Date(currentDate);
    if (viewMode === 'month') d.setMonth(d.getMonth() + 1);
    else if (viewMode === 'week') d.setDate(d.getDate() + 7);
    else d.setDate(d.getDate() + 1);
    onDateChange(d);
  };

  const prevPeriod = () => {
    const d = new Date(currentDate);
    if (viewMode === 'month') d.setMonth(d.getMonth() - 1);
    else if (viewMode === 'week') d.setDate(d.getDate() - 7);
    else d.setDate(d.getDate() - 1);
    onDateChange(d);
  };

  const monthName = useMemo(() => {
    try {
      if (!currentDate || isNaN(currentDate.getTime())) return "Data Inválida";
      return viewMode === 'day'
        ? new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(currentDate)
        : new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(currentDate);
    } catch (e) {
      console.error("Error formatting date:", e);
      return "Erro na Data";
    }
  }, [currentDate, viewMode]);

  return (
    <div className="bg-white rounded-none md:rounded-[2rem] border border-slate-200 overflow-hidden shadow-sm animate-in fade-in">
      <div className="p-3 md:p-6 border-b border-slate-100 flex flex-col md:flex-row items-center justify-between gap-4 md:gap-6">
        {/* Navegação e Data à Esquerda */}
        <div className="flex flex-col md:flex-row items-center gap-3 md:gap-4 w-full md:w-auto">
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl shadow-inner shrink-0">
            <button onClick={prevPeriod} className="p-2 hover:bg-white hover:shadow-sm rounded-lg transition-all text-slate-400 hover:text-slate-600">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <button onClick={() => onDateChange(new Date())} className="px-3 md:px-4 py-2 text-[9px] font-black uppercase bg-white text-slate-900 rounded-lg shadow-sm hover:bg-slate-50 transition-all active:scale-95">Hoje</button>
            <button onClick={nextPeriod} className="p-2 hover:bg-white hover:shadow-sm rounded-lg transition-all text-slate-400 hover:text-slate-600">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
            </button>
          </div>
          <h3 className="text-[10px] font-black text-slate-700 uppercase tracking-tight md:tracking-[0.2em] md:border-l md:border-slate-200 md:pl-4 text-center md:text-left truncate max-w-full">
            {monthName}
          </h3>
        </div>
        
        {/* Seletor de Visualização à Direita */}
        <div className="flex bg-slate-200/80 rounded-xl p-1 shadow-inner shrink-0 w-full md:w-auto">
          <button
            onClick={() => onViewModeChange('month')}
            className={`flex-1 md:flex-none px-4 md:px-6 py-2 text-[9px] uppercase font-black rounded-lg transition-all ${viewMode === 'month' ? 'bg-white shadow-md text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Mês
          </button>
          <button
            onClick={() => onViewModeChange('week')}
            className={`flex-1 md:flex-none px-4 md:px-6 py-2 text-[9px] uppercase font-black rounded-lg transition-all ${viewMode === 'week' ? 'bg-white shadow-md text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Semana
          </button>
          <button
            onClick={() => onViewModeChange('day')}
            className={`flex-1 md:flex-none px-4 md:px-6 py-2 text-[9px] uppercase font-black rounded-lg transition-all ${viewMode === 'day' ? 'bg-white shadow-md text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Dia
          </button>
        </div>
      </div>

      {viewMode === 'day' ? (
        <DayView
          tasks={tasks}
          googleEvents={googleEvents}
          currentDate={currentDate}
          onTaskClick={onTaskClick}
          onTaskUpdate={onTaskUpdate}
          onExecuteTask={onExecuteTask}
          onReorderTasks={onReorderTasks}
          showToast={showToast}
        />
      ) : (
        <>
          <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50">
            {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map(d => (
              <div key={d} className="py-3 text-center text-[10px] font-black text-slate-400 uppercase">{d}</div>
            ))}
          </div>

          <div className="grid grid-cols-7 auto-rows-fr bg-slate-200 gap-px border-b border-slate-200">
            {days.map((day, i) => {
              const dayStr = formatDateLocalISO(day);
              const isToday = formatDateLocalISO(new Date()) === dayStr;
              const isCurrentMonth = day.getMonth() === currentDate.getMonth();
              const dayTasks = tasksByDay[dayStr] || [];
              const dayGoogleEvents = googleEventsByDay[dayStr] || [];

              return (
                <div
                  key={i}
                  className={`bg-white ${viewMode === 'week' ? 'min-h-[450px]' : 'min-h-[120px]'} p-2 flex flex-col gap-1 transition-colors hover:bg-slate-50
                    ${!isCurrentMonth ? 'bg-slate-50/50' : ''}
                  `}
                >
                  <div className="flex justify-between items-start">
                    <span className={`text-xs font-bold w-6 h-6 flex items-center justify-center rounded-full ${isToday ? 'bg-rose-500 text-white' : !isCurrentMonth ? 'text-slate-300' : 'text-slate-700'}`}>
                      {day.getDate()}
                    </span>
                    {dayTasks.length > 0 && <span className="text-[9px] font-black text-slate-300">{dayTasks.length}</span>}
                  </div>

                  <div className={`flex-1 flex flex-col gap-1 mt-1 overflow-y-auto ${viewMode === 'week' ? 'max-h-[400px]' : 'max-h-[100px]'} scrollbar-hide`}>
                    {dayGoogleEvents.map(e => (
                      <div
                        key={e.id}
                        className="px-2 py-0.5 rounded-md bg-amber-50 border border-amber-100 text-amber-700 text-[8px] font-black truncate flex items-center gap-1"
                        title={e.titulo}
                      >
                        <div className="w-1.5 h-1.5 bg-amber-500 rounded-full"></div>
                        {e.titulo}
                      </div>
                    ))}
                    {dayTasks.map(t => {
                      const startStr = t.is_single_day ? (t.data_limite || '') : (t.data_inicio || t.data_criacao?.split('T')[0] || t.data_limite || '');
                      const endStr = t.data_limite || '';

                      const isStart = startStr === dayStr;
                      const isEnd = endStr === dayStr;

                      const showTitle = isStart || isEnd;

                      if (showTitle) {
                        return (
                          <div
                            key={`${t.id}-${dayStr}`}
                            onClick={() => onTaskClick(t)}
                            className={`px-2 py-1.5 rounded-md border text-[9px] font-bold cursor-pointer transition-all active:scale-95 group relative z-10
                              ${t.categoria === 'CLC' ? 'bg-blue-50 border-blue-100 text-blue-700 hover:border-blue-300' :
                                t.categoria === 'ASSISTÊNCIA' ? 'bg-emerald-50 border-emerald-100 text-emerald-700 hover:border-emerald-300' :
                                  'bg-slate-50 border-slate-100 text-slate-600 hover:border-slate-300'}
                            `}
                          >
                            <div className="line-clamp-2 leading-tight">{t.titulo}</div>
                            {isStart && endStr && startStr !== endStr && (
                              <div className="text-[7px] text-slate-400 mt-0.5">→ {formatDate(endStr).split(' ')[0]}</div>
                            )}
                          </div>
                        );
                      } else {
                        return (
                          <div
                            key={`${t.id}-${dayStr}`}
                            onClick={() => onTaskClick(t)}
                            title={t.titulo}
                            className={`h-1.5 rounded-full cursor-pointer transition-all hover:h-3 w-full my-0.5 relative z-0
                              ${t.categoria === 'CLC' ? 'bg-blue-300/60 hover:bg-blue-400' :
                                t.categoria === 'ASSISTÊNCIA' ? 'bg-emerald-300/60 hover:bg-emerald-400' :
                                  'bg-slate-300/60 hover:bg-slate-400'}
                            `}
                          />
                        );
                      }
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};
