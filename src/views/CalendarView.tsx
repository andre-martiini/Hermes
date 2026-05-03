
import React, { useEffect, useMemo } from 'react';
import { Tarefa, GoogleCalendarEvent, formatDateLocalISO } from '../../types';
import { DayView } from './DayView';
import { TimeGrid } from '../components/calendar/TimeGrid';
import { TaskCard } from '../components/calendar/TaskCard';
import { normalizeStatus, isStandbyStatus } from '../utils/helpers';
import { addDoc, collection, updateDoc, doc } from 'firebase/firestore';
import { db, functions } from '../../firebase';
import { httpsCallable } from 'firebase/functions';

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
  showToast,
  isDark
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
  showToast?: (message: string, type: 'success' | 'error' | 'info') => void,
  isDark?: boolean
}) => {
  const [days, setDays] = React.useState<Date[]>([]);
  const [showAgenda, setShowAgenda] = React.useState(true);
  const [showCompleted, setShowCompleted] = React.useState(false);
  const [weekViewType, setWeekViewType] = React.useState<'grid' | 'cards'>('grid');
  const [showStandby, setShowStandby] = React.useState(false);
  const [showPrevious, setShowPrevious] = React.useState(true);

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

  const handleTaskCreate = async (task: Partial<Tarefa>) => {
    try {
      const docRef = await addDoc(collection(db, 'tarefas'), {
        ...task,
        titulo: 'Nova Tarefa',
        status: 'em andamento',
        area_tematica: 'NÃO CLASSIFICADA',
        projeto: 'GERAL',
        contabilizar_meta: true,
        data_criacao: new Date().toISOString()
      });
      if (showToast) showToast("Tarefa criada!", "success");

      // Auto-classificacao asincrona
      try {
        const classificar = httpsCallable(functions, 'classificarAreaTematica');
        const result = await classificar({ titulo: 'Nova Tarefa' });
        const areaTematica = (result.data as any)?.area_tematica;
        if (areaTematica && areaTematica !== 'Nenhuma') {
          await updateDoc(doc(db, 'tarefas', docRef.id), { area_tematica: areaTematica });
          if (showToast) showToast(`Tarefa classificada como ${areaTematica} pela IA.`, 'info');
        }
      } catch (err) {
        console.error('Falha na autoclassificação:', err);
      }

    } catch (e) {
      console.error(e);
      if (showToast) showToast("Erro ao criar tarefa.", "error");
    }
  };

  const filteredGoogleEvents = useMemo(() => showAgenda ? googleEvents : [], [showAgenda, googleEvents]);

  const googleEventsByDay = useMemo(() => {
    const map: Record<string, GoogleCalendarEvent[]> = {};
    if (!filteredGoogleEvents) return map;

    filteredGoogleEvents.forEach(e => {
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
  }, [filteredGoogleEvents]);

  const filteredTasks = useMemo(() => {
    if (!tasks) return [];
    return tasks.filter(t => {
      // Se não quer ver concluídas e a tarefa está concluída, oculta
      if (!showCompleted && normalizeStatus(t.status) === 'concluido') return false;

      return true;
    });
  }, [tasks, showCompleted]);

  const tasksByDay = useMemo(() => {
    const map: Record<string, Tarefa[]> = {};
    if (!filteredTasks) return map;

    filteredTasks.forEach(t => {
      const taskDate = t.data_limite || t.data_inicio;
      if (!taskDate || taskDate === '-' || taskDate === '0000-00-00') return;

      const dateStr = taskDate.split('T')[0];
      if (!map[dateStr]) map[dateStr] = [];
      if (!map[dateStr].find(x => x.id === t.id)) {
        map[dateStr].push(t);
      }
    });
    return map;
  }, [filteredTasks]);

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

  const dateInfo = useMemo(() => {
    try {
      if (!currentDate || isNaN(currentDate.getTime())) return { main: "Data Inválida", sub: "" };

      const weekday = new Intl.DateTimeFormat('pt-BR', { weekday: 'long' }).format(currentDate);
      const isDay = viewMode === 'day';

      return {
        main: isDay
          ? new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(currentDate)
          : new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(currentDate),
        sub: isDay ? weekday : (viewMode === 'week' ? 'Visualização Semanal' : 'Visualização Mensal')
      };
    } catch (e) {
      console.error("Error formatting date:", e);
      return { main: "Erro na Data", sub: "" };
    }
  }, [currentDate, viewMode]);

  return (
    <div className={`${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'} rounded-none md:rounded-[2rem] border overflow-hidden shadow-sm animate-in fade-in`}>
      <div className={`p-3 md:p-6 border-b ${isDark ? 'border-slate-800' : 'border-slate-100'} flex flex-col md:flex-row items-center justify-between gap-4 md:gap-6`}>
        {/* Navegação e Data à Esquerda */}
        <div className="flex flex-col md:flex-row items-center gap-3 md:gap-4 w-full md:w-auto">
          <div className={`flex items-center gap-1 ${isDark ? 'bg-slate-800' : 'bg-slate-100'} p-1 rounded-xl shadow-inner shrink-0`}>
            <button onClick={prevPeriod} className={`p-2 rounded-lg transition-all ${isDark ? 'hover:bg-slate-700 text-slate-500 hover:text-slate-300' : 'hover:bg-white text-slate-400 hover:text-slate-600'} hover:shadow-sm`}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <button onClick={() => onDateChange(new Date())} className={`px-3 md:px-4 py-2 text-[9px] font-black uppercase rounded-lg shadow-sm transition-all active:scale-95 ${isDark ? 'bg-slate-700 text-white hover:bg-slate-600' : 'bg-white text-slate-900 hover:bg-slate-50'}`}>Hoje</button>
            <button onClick={nextPeriod} className={`p-2 rounded-lg transition-all ${isDark ? 'hover:bg-slate-700 text-slate-500 hover:text-slate-300' : 'hover:bg-white text-slate-400 hover:text-slate-600'} hover:shadow-sm`}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
            </button>
          </div>
          <div className={`flex flex-col md:border-l ${isDark ? 'text-slate-100 border-slate-700' : 'text-slate-700 border-slate-200'} md:pl-4 items-center md:items-start leading-tight truncate`}>
            <span className={`text-[8px] font-bold uppercase tracking-[0.1em] md:tracking-[0.2em] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
              {dateInfo.sub}
            </span>
            <h3 className={`text-[10px] font-black uppercase tracking-tight md:tracking-[0.2em] ${isDark ? 'text-slate-100' : 'text-slate-700'} truncate max-w-full`}>
              {dateInfo.main}
            </h3>
          </div>

          {viewMode === 'week' && (
            <div className={`flex ${isDark ? 'bg-slate-800' : 'bg-slate-100'} p-0.5 rounded-lg shadow-inner shrink-0 scale-90 md:scale-100 ml-2`}>
              <button
                onClick={() => setWeekViewType('grid')}
                className={`px-3 py-1.5 text-[8px] font-black uppercase rounded-md transition-all flex items-center gap-1.5 ${weekViewType === 'grid' ? isDark ? 'bg-slate-700 shadow-sm text-white border border-slate-600' : 'bg-white shadow-sm text-slate-900 border border-slate-200' : isDark ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600'}`}
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                Grade
              </button>
              <button
                onClick={() => setWeekViewType('cards')}
                className={`px-3 py-1.5 text-[8px] font-black uppercase rounded-md transition-all flex items-center gap-1.5 ${weekViewType === 'cards' ? isDark ? 'bg-slate-700 shadow-sm text-white border border-slate-600' : 'bg-white shadow-sm text-slate-900 border border-slate-200' : isDark ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600'}`}
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M4 6h16M4 12h16M4 18h16" /></svg>
                Cards
              </button>
            </div>
          )}

          <div
            onClick={() => setShowAgenda(!showAgenda)}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl transition-all cursor-pointer select-none active:scale-95 shadow-sm border ${isDark ? 'bg-slate-800 border-slate-700 hover:bg-slate-750' : 'bg-slate-50 border-slate-100 hover:bg-slate-100'}`}
          >
            <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${showAgenda ? 'bg-amber-500 border-amber-500' : isDark ? 'bg-slate-900 border-slate-600' : 'bg-white border-slate-300'}`}>
              {showAgenda && (
                <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
            <span className={`text-[9px] font-black uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Agenda</span>
          </div>

          <div
            onClick={() => setShowCompleted(!showCompleted)}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl transition-all cursor-pointer select-none active:scale-95 shadow-sm border ${isDark ? 'bg-slate-800 border-slate-700 hover:bg-slate-750' : 'bg-slate-50 border-slate-100 hover:bg-slate-100'}`}
          >
            <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${showCompleted ? 'bg-emerald-600 border-emerald-600' : isDark ? 'bg-slate-900 border-slate-600' : 'bg-white border-slate-300'}`}>
              {showCompleted && (
                <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
            <span className={`text-[9px] font-black uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Concluídas</span>
          </div>

          {viewMode === 'day' && (
            <>
              <div
                onClick={() => setShowStandby(!showStandby)}
                className={`flex items-center gap-2 px-3 py-2 rounded-xl transition-all cursor-pointer select-none active:scale-95 shadow-sm border ${isDark ? 'bg-slate-800 border-slate-700 hover:bg-slate-750' : 'bg-slate-50 border-slate-100 hover:bg-slate-100'}`}
              >
                <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${showStandby ? 'bg-indigo-600 border-indigo-600' : isDark ? 'bg-slate-900 border-slate-600' : 'bg-white border-slate-300'}`}>
                  {showStandby && (
                    <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
                <span className={`text-[9px] font-black uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Standby</span>
              </div>

              <div
                onClick={() => setShowPrevious(!showPrevious)}
                className={`flex items-center gap-2 px-3 py-2 rounded-xl transition-all cursor-pointer select-none active:scale-95 shadow-sm border ${isDark ? 'bg-slate-800 border-slate-700 hover:bg-slate-750' : 'bg-slate-50 border-slate-100 hover:bg-slate-100'}`}
              >
                <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${showPrevious ? 'bg-rose-600 border-rose-600' : isDark ? 'bg-slate-900 border-slate-600' : 'bg-white border-slate-300'}`}>
                  {showPrevious && (
                    <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
                <span className={`text-[9px] font-black uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Atrasadas</span>
              </div>
            </>
          )}
        </div>

        {/* Seletor de Visualização à Direita */}
        <div className={`flex ${isDark ? 'bg-slate-800' : 'bg-slate-200/80'} rounded-xl p-1 shadow-inner shrink-0 w-full md:w-auto`}>
          <button
            onClick={() => onViewModeChange('month')}
            className={`flex-1 md:flex-none px-4 md:px-6 py-2 text-[9px] uppercase font-black rounded-lg transition-all ${viewMode === 'month' ? isDark ? 'bg-slate-600 text-white shadow-md' : 'bg-white shadow-md text-slate-900' : isDark ? 'text-slate-500 hover:text-slate-300' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Mês
          </button>
          <button
            onClick={() => onViewModeChange('week')}
            className={`flex-1 md:flex-none px-4 md:px-6 py-2 text-[9px] uppercase font-black rounded-lg transition-all ${viewMode === 'week' ? isDark ? 'bg-slate-600 text-white shadow-md' : 'bg-white shadow-md text-slate-900' : isDark ? 'text-slate-500 hover:text-slate-300' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Semana
          </button>
          <button
            onClick={() => onViewModeChange('day')}
            className={`flex-1 md:flex-none px-4 md:px-6 py-2 text-[9px] uppercase font-black rounded-lg transition-all ${viewMode === 'day' ? isDark ? 'bg-slate-600 text-white shadow-md' : 'bg-white shadow-md text-slate-900' : isDark ? 'text-slate-500 hover:text-slate-300' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Dia
          </button>
        </div>
      </div>

      {viewMode === 'day' ? (
        <DayView
          tasks={filteredTasks}
          googleEvents={filteredGoogleEvents}
          currentDate={currentDate}
          onTaskClick={onTaskClick}
          onTaskUpdate={onTaskUpdate}
          onExecuteTask={onExecuteTask}
          onReorderTasks={onReorderTasks}
          showToast={showToast}
          isDark={isDark}
          hourHeight={90}
          showStandby={showStandby}
          showPrevious={showPrevious}
          disableExecuteOnClick={true}
        />
      ) : viewMode === 'week' ? (
        <div className="h-[600px] flex flex-col">
          <div className={`flex border-b shrink-0 ${isDark ? 'border-slate-800 bg-slate-900/50' : 'border-slate-100 bg-slate-50'} ${weekViewType === 'grid' ? 'pl-12' : ''}`}>
            {days.map(d => {
              const dayStr = formatDateLocalISO(d);
              const isToday = formatDateLocalISO(new Date()) === dayStr;
              const isWeekend = d.getDay() === 0 || d.getDay() === 6;
              return (
                <div
                  key={d.toString()}
                  className={`flex-1 py-2 flex flex-col items-center justify-center gap-1 cursor-pointer transition-all hover:bg-slate-400/5 active:scale-95`}
                  onClick={() => {
                    onDateChange(d);
                    onViewModeChange('day');
                  }}
                >
                  <div className={`text-[9px] font-black uppercase tracking-tight ${isToday ? 'text-rose-600' : isWeekend ? isDark ? 'text-slate-700' : 'text-slate-300' : isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                    {new Intl.DateTimeFormat('pt-BR', { weekday: 'short' }).format(d).replace('.', '')}
                  </div>
                  <div className={`w-7 h-7 flex items-center justify-center rounded-full text-[11px] font-black transition-all ${isToday ? 'bg-rose-500 text-white shadow-md' : isWeekend ? isDark ? 'text-slate-600' : 'text-slate-400' : isDark ? 'text-slate-400' : 'text-slate-700'}`}>
                    {d.getDate()}
                  </div>
                </div>
              );
            })}
          </div>

          {weekViewType === 'grid' ? (
            <TimeGrid
              days={days}
              tasks={filteredTasks}
              googleEvents={filteredGoogleEvents}
              onTaskClick={onTaskClick}
              onTaskUpdate={onTaskUpdate}
              onExecuteTask={onExecuteTask}
              onTaskCreate={handleTaskCreate}
              showToast={showToast}
              isDark={isDark}
              hourHeight={60}
              showStandby={showStandby}
              disableExecuteOnClick={false}
            />
          ) : (
            <div className={`flex-1 grid grid-cols-7 gap-px overflow-y-auto custom-scrollbar ${isDark ? 'bg-slate-800' : 'bg-slate-200'}`}>
              {days.map((day, i) => {
                const dayStr = formatDateLocalISO(day);
                const isToday = formatDateLocalISO(new Date()) === dayStr;
                const dayTasks = tasksByDay[dayStr] || [];
                const dayGoogleEvents = googleEventsByDay[dayStr] || [];

                return (
                  <div
                    key={i}
                    className={`min-h-full p-3 flex flex-col gap-2 transition-colors ${isDark ? 'hover:bg-slate-800/50' : 'hover:bg-slate-50'} ${day.getDay() === 0 || day.getDay() === 6 ? isDark ? 'bg-slate-950' : 'bg-slate-50/50' : isDark ? 'bg-slate-900' : 'bg-white'}`}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.currentTarget.style.backgroundColor = isDark ? 'rgba(30, 41, 59, 1)' : 'rgba(241, 245, 249, 0.9)';
                    }}
                    onDragLeave={(e) => {
                      e.currentTarget.style.backgroundColor = '';
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.currentTarget.style.backgroundColor = '';
                      const taskId = e.dataTransfer.getData('task-id');
                      if (taskId) {
                        onTaskUpdate(taskId, {
                          data_limite: dayStr,
                          data_inicio: dayStr
                        });
                        if (showToast) showToast(`Ação movida para ${dayStr.split('-').reverse().join('/')}`, "info");
                      }
                    }}
                  >
                    <div className="flex-1 flex flex-col gap-2 overflow-y-auto scrollbar-hide pointer-events-none">
                      {dayGoogleEvents.map(e => (
                        <div
                          key={e.id}
                          className={`px-2 py-1 rounded-md border text-[8px] font-black truncate flex items-center gap-1.5 ${isDark ? 'bg-amber-900/20 border-amber-800/50 text-amber-500' : 'bg-amber-50 border-amber-100 text-amber-700'}`}
                          title={e.titulo}
                        >
                          <div className="w-1.5 h-1.5 bg-amber-500 rounded-full"></div>
                          {e.titulo}
                        </div>
                      ))}
                      {dayTasks.map(t => (
                        <TaskCard
                          key={`${t.id}-${dayStr}`}
                          task={t}
                          isDark={isDark}
                          onTaskClick={onTaskClick}
                          onTaskUpdate={onTaskUpdate}
                          onExecuteTask={onExecuteTask}
                          dayStr={dayStr}
                          className="pointer-events-auto"
                        />
                      ))}
                      {dayTasks.length === 0 && dayGoogleEvents.length === 0 && (
                        <div className={`flex-1 flex items-center justify-center border-2 border-dashed rounded-2xl ${isDark ? 'border-slate-800' : 'border-slate-50'}`}>
                          <span className={`text-[9px] font-black uppercase tracking-widest ${isDark ? 'text-slate-800' : 'text-slate-200'}`}>Vazio</span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        <>
          <div className={`grid grid-cols-7 border-b ${isDark ? 'border-slate-800 bg-slate-900/50' : 'border-slate-100 bg-slate-50'}`}>
            {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map((d, i) => (
              <div key={d} className={`py-3 text-center text-[10px] font-black uppercase ${i === 0 || i === 6 ? 'text-slate-500' : 'text-slate-400'}`}>{d}</div>
            ))}
          </div>

          <div className={`grid grid-cols-7 auto-rows-fr gap-px border-b ${isDark ? 'bg-slate-800 border-slate-800' : 'bg-slate-200 border-slate-200'}`}>
            {days.map((day, i) => {
              const dayStr = formatDateLocalISO(day);
              const isToday = formatDateLocalISO(new Date()) === dayStr;
              const isCurrentMonth = day.getMonth() === currentDate.getMonth();
              const dayTasks = tasksByDay[dayStr] || [];
              const dayGoogleEvents = googleEventsByDay[dayStr] || [];

              return (
                <div
                  key={i}
                  className={`min-h-[120px] p-2 flex flex-col gap-1 transition-colors ${isDark ? 'hover:bg-slate-800/50' : 'hover:bg-slate-50'}
                      ${!isCurrentMonth ? (isDark ? 'bg-slate-900/50' : 'bg-slate-50/30') : (day.getDay() === 0 || day.getDay() === 6) ? (isDark ? 'bg-slate-900/40' : 'bg-slate-50/60') : (isDark ? 'bg-slate-900' : 'bg-white')}
                    `}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.currentTarget.style.backgroundColor = isDark ? 'rgba(30, 41, 59, 1)' : 'rgba(241, 245, 249, 0.9)';
                  }}
                  onDragLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '';
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    e.currentTarget.style.backgroundColor = '';
                    const taskId = e.dataTransfer.getData('task-id');
                    if (taskId) {
                      onTaskUpdate(taskId, {
                        data_limite: dayStr,
                        data_inicio: dayStr
                      });
                      if (showToast) showToast(`Ação movida para ${dayStr.split('-').reverse().join('/')}`, "info");
                    }
                  }}
                >
                  <div className="flex justify-between items-start pointer-events-none">
                    <span className={`text-xs font-bold w-6 h-6 flex items-center justify-center rounded-full ${isToday ? 'bg-rose-500 text-white' : !isCurrentMonth ? (isDark ? 'text-slate-700' : 'text-slate-300') : (isDark ? 'text-slate-400' : 'text-slate-700')}`}>
                      {day.getDate()}
                    </span>
                    {dayTasks.length > 0 && <span className={`text-[9px] font-black ${isDark ? 'text-slate-700' : 'text-slate-300'}`}>{dayTasks.length}</span>}
                  </div>

                  <div className={`flex-1 flex flex-col gap-1 mt-1 overflow-y-auto max-h-[220px] scrollbar-hide pointer-events-none`}>
                    {dayGoogleEvents.map(e => (
                      <div
                        key={e.id}
                        className={`px-2 py-0.5 rounded-md border text-[8px] font-black truncate flex items-center gap-1 ${isDark ? 'bg-amber-900/20 border-amber-800/50 text-amber-500' : 'bg-amber-50 border-amber-100 text-amber-700'}`}
                        title={e.titulo}
                      >
                        <div className="w-1.5 h-1.5 bg-amber-500 rounded-full"></div>
                        {e.titulo}
                      </div>
                    ))}
                    {dayTasks.map(t => (
                      <TaskCard
                        key={`${t.id}-${dayStr}`}
                        task={t}
                        isDark={isDark}
                        onTaskClick={onTaskClick}
                        onTaskUpdate={onTaskUpdate}
                        onExecuteTask={onExecuteTask}
                        dayStr={dayStr}
                        className="pointer-events-auto"
                      />
                    ))}
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
