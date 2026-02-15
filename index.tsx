
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { Tarefa, Status, EntregaInstitucional, Prioridade, AtividadeRealizada, Afastamento, PlanoTrabalho, PlanoTrabalhoItem, Categoria, Acompanhamento, BrainstormIdea, FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill } from './types';
import { STATUS_COLORS, PROJECT_COLORS } from './constants';
import { db } from './firebase';
import { collection, onSnapshot, query, updateDoc, doc, addDoc, deleteDoc, setDoc, arrayUnion, arrayRemove } from 'firebase/firestore';
import { GoogleGenerativeAI } from "@google/generative-ai";
import FinanceView from './FinanceView';


type SortOption = 'date-asc' | 'date-desc' | 'priority-high' | 'priority-low';
type DateFilter = 'today' | 'week' | 'month';

interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info';
}

const ToastContainer = ({ toasts, removeToast }: { toasts: Toast[], removeToast: (id: string) => void }) => {
  return (
    <div className="fixed top-8 right-8 z-[200] flex flex-col gap-3 pointer-events-none">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`pointer-events-auto px-8 py-5 rounded-[1.25rem] shadow-[0_20px_50px_rgba(0,0,0,0.2)] flex items-center gap-4 animate-in slide-in-from-right-12 fade-in duration-500 min-w-[320px] backdrop-blur-md ${toast.type === 'success' ? 'bg-emerald-500/95 text-white' :
            toast.type === 'error' ? 'bg-rose-500/95 text-white' :
              'bg-slate-900/95 text-white'
            }`}
        >
          <div className="flex-shrink-0">
            {toast.type === 'success' && <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>}
            {toast.type === 'error' && <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>}
            {toast.type === 'info' && <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
          </div>
          <div className="flex-1">
            <span className="text-[10px] font-black uppercase tracking-[0.15em] leading-none opacity-80 block mb-0.5">{toast.type}</span>
            <span className="text-sm font-bold tracking-tight">{toast.message}</span>
          </div>
          <button onClick={() => removeToast(toast.id)} className="p-1.5 hover:bg-white/20 rounded-lg transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      ))}
    </div>
  );
};

// --- Utilitários ---
const getDaysInMonth = (year: number, month: number) => new Date(year, month + 1, 0).getDate();

const isWorkDay = (date: Date) => {
  const day = date.getDay();
  return day !== 0 && day !== 6; // Seg-Sex
};

const getMonthWorkDays = (year: number, month: number) => {
  const days = [];
  const totalDays = getDaysInMonth(year, month);
  for (let d = 1; d <= totalDays; d++) {
    const date = new Date(year, month, d);
    if (isWorkDay(date)) days.push(new Date(date));
  }
  return days;
};

const normalizeStatus = (status: string): string => {
  if (!status) return 'em andamento';
  return status
    .toLowerCase()
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
};

const formatDate = (dateStr: string) => {
  if (!dateStr || dateStr === "-" || dateStr === "0000-00-00" || dateStr.trim() === "") return 'Sem Data';
  const parts = dateStr.split('-');
  if (parts.length !== 3) return dateStr;
  const [year, month, day] = parts.map(Number);
  const date = new Date(year, month - 1, day);
  if (isNaN(date.getTime())) return dateStr;
  const dayOfWeek = new Intl.DateTimeFormat('pt-BR', { weekday: 'long' }).format(date);
  const capitalizedDay = dayOfWeek.charAt(0).toUpperCase() + dayOfWeek.slice(1);
  return `${parts[2]}/${parts[1]}/${parts[0]} (${capitalizedDay})`;
};

// --- Subcomponentes Atômicos ---
const FilterChip = React.memo(({ label, isActive, onClick, colorClass }: { label: string, isActive: boolean, onClick: () => void, colorClass?: string }) => (
  <button
    onClick={onClick}
    className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest border-2 transition-all duration-200 active:scale-95 ${isActive
      ? (colorClass || 'bg-slate-900 text-white border-slate-900 shadow-md')
      : 'bg-white text-slate-400 border-slate-200 border-dashed hover:border-slate-400 hover:text-slate-600'
      }`}
  >
    {label}
  </button>
));

const PgcMiniTaskCard = React.memo(({ task, onClick }: { task: Tarefa, onClick?: () => void }) => {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('tarefaId', task.id);
        e.dataTransfer.effectAllowed = 'copy';
      }}
      onClick={onClick}
      className={`bg-white border border-slate-200 p-3 rounded-xl shadow-sm hover:shadow-md hover:border-blue-400 transition-all ${onClick ? 'cursor-pointer' : 'cursor-grab'} active:cursor-grabbing w-full md:w-[280px] group`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase ${PROJECT_COLORS[task.projeto] || 'bg-slate-100 text-slate-600'}`}>
          {task.projeto}
        </span>
        <span className="text-[8px] font-black text-slate-400 uppercase">{formatDate(task.data_limite)}</span>
      </div>
      <h5 className="text-[11px] font-bold text-slate-900 leading-tight group-hover:text-blue-600 line-clamp-2">{task.titulo}</h5>
    </div>
  );
});

// --- Components ---

const CalendarView = ({
  tasks,
  viewMode,
  currentDate,
  onDateChange,
  onTaskClick,
  onViewModeChange
}: {
  tasks: Tarefa[],
  viewMode: 'month' | 'week',
  currentDate: Date,
  onDateChange: (d: Date) => void,
  onTaskClick: (t: Tarefa) => void,
  onViewModeChange: (m: 'month' | 'week') => void
}) => {
  const [days, setDays] = React.useState<Date[]>([]);

  useEffect(() => {
    const d = new Date(currentDate);
    const newDays = [];

    if (viewMode === 'month') {
      // First day of month
      d.setDate(1);
      // Backtrack to Sunday (or start of week)
      const dayOfWeek = d.getDay();
      d.setDate(d.getDate() - dayOfWeek);

      // 6 weeks (42 days) covers all months
      for (let i = 0; i < 42; i++) {
        newDays.push(new Date(d));
        d.setDate(d.getDate() + 1);
      }
    } else {
      // Week view
      const dayOfWeek = d.getDay();
      d.setDate(d.getDate() - dayOfWeek);
      for (let i = 0; i < 7; i++) {
        newDays.push(new Date(d));
        d.setDate(d.getDate() + 1);
      }
    }
    setDays(newDays);
  }, [currentDate, viewMode]);

  const tasksByDay = useMemo(() => {
    const map: Record<string, Tarefa[]> = {};
    tasks.forEach(t => {
      if (!t.data_limite || t.data_limite === '-' || t.data_limite === '0000-00-00') return;

      const endStr = t.data_limite;
      const startStr = t.is_single_day ? endStr : (t.data_inicio || t.data_criacao?.split('T')[0] || endStr);

      // Create dates using UTC to avoid timezone shifts
      let current = new Date(startStr + 'T12:00:00Z');
      const end = new Date(endStr + 'T12:00:00Z');

      // Sanity check: if start > end or range is too large (> 60 days), just show on end date to prevent freezes
      const diffTime = end.getTime() - current.getTime();
      const diffDays = diffTime / (1000 * 3600 * 24);

      if (current > end || diffDays > 60) {
        current = end;
      }

      let iterations = 0;
      // Loop through all days in the range
      while (current <= end) {
        if (iterations > 62) break; // Hard safety break
        iterations++;

        const dateStr = current.toISOString().split('T')[0];
        if (!map[dateStr]) map[dateStr] = [];
        // Avoid duplicate entries for the same task on the same day
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
    else d.setDate(d.getDate() + 7);
    onDateChange(d);
  };

  const prevPeriod = () => {
    const d = new Date(currentDate);
    if (viewMode === 'month') d.setMonth(d.getMonth() - 1);
    else d.setDate(d.getDate() - 7);
    onDateChange(d);
  };

  const monthName = new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(currentDate);

  return (
    <div className="bg-white rounded-[2rem] border border-slate-200 overflow-hidden shadow-sm animate-in fade-in">
      <div className="p-6 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h3 className="text-xl font-black text-slate-900 capitalize tracking-tight">{monthName}</h3>
          <div className="flex bg-slate-100 rounded-lg p-1">
            <button
              onClick={() => onViewModeChange('month')}
              className={`px-3 py-1 text-[10px] uppercase font-black rounded-md transition-all ${viewMode === 'month' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
            >
              Mês
            </button>
            <button
              onClick={() => onViewModeChange('week')}
              className={`px-3 py-1 text-[10px] uppercase font-black rounded-md transition-all ${viewMode === 'week' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
            >
              Semana
            </button>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={prevPeriod} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
            <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
          </button>
          <button onClick={() => onDateChange(new Date())} className="px-4 py-2 text-[10px] font-black uppercase bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors text-slate-700">Hoje</button>
          <button onClick={nextPeriod} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
            <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50">
        {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map(d => (
          <div key={d} className="py-3 text-center text-[10px] font-black text-slate-400 uppercase">{d}</div>
        ))}
      </div>

      <div className="grid grid-cols-7 auto-rows-fr bg-slate-200 gap-px border-b border-slate-200">
        {days.map((day, i) => {
          const dayStr = day.toISOString().split('T')[0];
          const isToday = new Date().toISOString().split('T')[0] === dayStr;
          const isCurrentMonth = day.getMonth() === currentDate.getMonth();
          const dayTasks = tasksByDay[dayStr] || [];

          return (
            <div
              key={i}
              className={`bg-white min-h-[120px] p-2 flex flex-col gap-1 transition-colors hover:bg-slate-50
                ${!isCurrentMonth ? 'bg-slate-50/50' : ''}
              `}
            >
              <div className="flex justify-between items-start">
                <span className={`text-xs font-bold w-6 h-6 flex items-center justify-center rounded-full ${isToday ? 'bg-rose-500 text-white' : !isCurrentMonth ? 'text-slate-300' : 'text-slate-700'}`}>
                  {day.getDate()}
                </span>
                {dayTasks.length > 0 && <span className="text-[9px] font-black text-slate-300">{dayTasks.length}</span>}
              </div>

              <div className="flex-1 flex flex-col gap-1 mt-1 overflow-y-auto max-h-[100px] scrollbar-hide">
                {dayTasks.map(t => {
                  // Show full card ONLY on start date and end date
                  // Show slim bar on all intermediate days
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
    </div>
  );
};

const RowCard = React.memo(({ task, onClick, onToggle, onDelete }: { task: Tarefa, onClick?: () => void, onToggle: (id: string, currentStatus: string) => void, onDelete: (id: string) => void }) => {
  const statusValue = normalizeStatus(task.status);
  const isCompleted = statusValue === 'concluido';
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  // Date Logic for Right Side
  const isSingleDay = task.is_single_day;
  const startDate = task.data_inicio;
  const endDate = task.data_limite;

  let dateDisplay = '';
  if (isSingleDay || !startDate || startDate === endDate) {
    dateDisplay = formatDate(endDate);
  } else {
    dateDisplay = `${formatDate(startDate).split(' ')[0]} - ${formatDate(endDate)}`;
  }

  return (
    <div
      onClick={onClick}
      onMouseLeave={() => setIsConfirmingDelete(false)}
      className={`group bg-white w-full p-8 border-b border-slate-200 hover:bg-slate-50 transition-all flex flex-col md:flex-row md:items-center gap-6 md:gap-8 animate-in cursor-pointer relative ${isCompleted ? 'opacity-60' : ''}`}
    >
      {/* Botão de Excluir Flutuante */}
      <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-all z-20">
        <button
          onClick={(e) => {
            e.stopPropagation();
            if (isConfirmingDelete) {
              onDelete(task.id);
            } else {
              setIsConfirmingDelete(true);
            }
          }}
          className={`px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all border flex items-center gap-2 ${isConfirmingDelete
            ? 'bg-rose-600 text-white border-rose-600 shadow-lg shadow-rose-200 animate-in zoom-in-95'
            : 'bg-white text-rose-500 border-rose-100 hover:bg-rose-50 shadow-sm'
            }`}
        >
          {isConfirmingDelete ? (
            <>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
              Confirmar?
            </>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
          )}
        </button>
      </div>

      <div className="flex-shrink-0">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle(task.id, task.status);
          }}
          className={`w-8 h-8 rounded-xl border-2 flex items-center justify-center transition-all ${isCompleted ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-slate-200 hover:border-slate-400 text-transparent'}`}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
        </button>
      </div>

      <div className="flex-1">
        <div className="flex items-center gap-2 mb-2">
          {task.categoria && task.categoria !== 'NÃO CLASSIFICADA' && (
            <span className={`text-[9px] font-black px-2 py-0.5 rounded uppercase tracking-wider 
              ${task.categoria === 'CLC' ? 'bg-blue-100 text-blue-700' :
                task.categoria === 'ASSISTÊNCIA' ? 'bg-emerald-100 text-emerald-700' :
                  'bg-slate-100 text-slate-600'}`}>
              {task.categoria}
            </span>
          )}
          <span className={`text-[9px] font-black px-2 py-0.5 rounded uppercase tracking-wider bg-slate-100 border border-slate-200 text-slate-600`}>
            {task.projeto}
          </span>
        </div>
        <div className={`text-lg font-bold text-slate-900 leading-snug group-hover:text-blue-600 transition-colors ${isCompleted ? 'line-through text-slate-400' : ''}`}>
          {task.titulo}
        </div>
      </div>

      <div className="hidden md:flex flex-col items-end gap-1 min-w-[150px]">
        <div className="text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Período</div>
        <div className="text-sm font-bold text-slate-700">
          {dateDisplay || '-'}
        </div>
        <div className="text-[9px] font-medium text-slate-400 mt-1">
          Criada em: {task.data_criacao ? formatDate(task.data_criacao.split('T')[0]).split(' ')[0] : '-'}
        </div>
        {task.status !== 'em andamento' && (
          <span className={`mt-1 text-[9px] font-black uppercase px-2 py-0.5 rounded ${STATUS_COLORS[statusValue] || 'bg-slate-100 text-slate-500'}`}>
            {task.status}
          </span>
        )}
      </div>
    </div>
  );
});

const CategoryView = ({ tasks, viewMode, onSelectTask }: { tasks: Tarefa[], viewMode: string, onSelectTask: (t: Tarefa) => void }) => {
  const isCLC = viewMode === 'licitacoes';
  const categoria = isCLC ? 'CLC' : 'ASSISTÊNCIA';
  const color = isCLC ? 'blue' : 'emerald';
  const title = isCLC ? 'Licitações' : 'Assistência Estudantil';

  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  const localDate = new Date(now.getTime() - offset);
  const todayStr = localDate.toISOString().split('T')[0];

  const pendentes = tasks.filter(t => t.categoria === categoria && normalizeStatus(t.status) !== 'concluido' && t.status !== 'excluído' as any);

  const getRelevantDate = (t: Tarefa) => {
    const isConcluido = normalizeStatus(t.status) === 'concluido';
    if (isConcluido) return t.data_conclusao || '';
    return t.data_criacao || '';
  };

  const historyTasks = tasks
    .filter(t => {
      const isCat = t.categoria === categoria;
      const isNotExcluded = t.status !== 'excluído' as any;
      const isConcluido = normalizeStatus(t.status) === 'concluido';
      const hasStarted = t.data_criacao && t.data_criacao <= todayStr;

      return isCat && isNotExcluded && (isConcluido || hasStarted);
    })
    .sort((a, b) => {
      const dateA = getRelevantDate(a);
      const dateB = getRelevantDate(b);
      return dateB.localeCompare(dateA);
    });

  return (
    <div className="animate-in grid grid-cols-1 lg:grid-cols-12 gap-10">
      {/* Lado Esquerdo: Ações Pendentes */}
      <div className="lg:col-span-8 flex flex-col gap-6">
        <div className={`bg-white border-l-8 border-${color}-600 p-8 rounded-[2rem] shadow-xl`}>
          <h3 className="text-2xl font-black text-slate-900 tracking-tight flex items-center justify-between">
            Ações em Aberto - {title}
            <span className={`bg-${color}-100 text-${color}-600 text-[10px] font-black px-4 py-1.5 rounded-full`}>{pendentes.length}</span>
          </h3>
        </div>

        <div className="bg-white border border-slate-200 rounded-[2rem] overflow-hidden shadow-2xl">
          <table className="w-full text-left">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Demanda</th>
                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-[200px]">Prazo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {pendentes.map(t => (
                <tr key={t.id} className="hover:bg-slate-50 transition-colors cursor-pointer" onClick={() => onSelectTask(t)}>
                  <td className="px-8 py-6">
                    <div className="text-[8px] font-black uppercase text-slate-400 mb-1">{t.projeto}</div>
                    <div className="text-sm font-black text-slate-900 leading-tight">{t.titulo}</div>
                  </td>
                  <td className="px-8 py-6 text-sm font-bold text-slate-600 whitespace-nowrap">{formatDate(t.data_limite)}</td>
                </tr>
              ))}
              {pendentes.length === 0 && (
                <tr>
                  <td colSpan={2} className="py-20 text-center text-slate-300 font-black uppercase tracking-widest italic">Nenhuma ação em aberto</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Lado Direito: Linha do Tempo (Concluídas + Iniciadas) */}
      <div className="lg:col-span-4 flex flex-col gap-6">
        <div className="bg-slate-900 text-white p-8 rounded-[2rem] shadow-xl">
          <h3 className="text-xl font-black tracking-tight uppercase tracking-widest">Histórico Realizado</h3>
          <p className="text-slate-400 text-[10px] font-black uppercase mt-1">Audit de Atividades</p>
        </div>

        <div className="relative pl-8 space-y-8 before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
          {historyTasks.map((t, idx) => {
            const isConcluido = normalizeStatus(t.status) === 'concluido';
            const displayDate = isConcluido ? (t.data_conclusao?.split('T')[0] || '') : t.data_criacao;
            const label = isConcluido ? 'Concluído' : 'Atividade Iniciada';

            return (
              <div key={t.id} className="relative group">
                <div className={`absolute -left-8 mt-1.5 w-6 h-6 rounded-full border-4 border-white ${isConcluido ? `bg-${color}-500` : 'bg-slate-400'} shadow-sm z-10 transition-transform group-hover:scale-125`}></div>
                <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-all cursor-pointer" onClick={() => onSelectTask(t)}>
                  <p className="text-[9px] font-black text-slate-400 uppercase mb-1">{formatDate(displayDate || '')}</p>
                  <h4 className="text-xs font-bold text-slate-900 leading-tight line-clamp-2">{t.titulo}</h4>
                  <div className="mt-3 flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 ${isConcluido ? `bg-${color}-500` : 'bg-slate-400'} rounded-full`}></span>
                    <span className="text-[8px] font-black text-slate-400 uppercase">{label}</span>
                  </div>
                </div>
              </div>
            );
          })}
          {historyTasks.length === 0 && (
            <div className="py-10 text-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
              <p className="text-slate-300 font-black text-[10px] uppercase">Sem histórico</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const TaskCreateModal = ({ onSave, onClose }: { onSave: (data: Partial<Tarefa>) => void, onClose: () => void }) => {
  const [formData, setFormData] = useState({
    titulo: '',
    data_inicio: new Date().toISOString().split('T')[0],
    data_limite: '',
    data_criacao: new Date().toISOString(), // Actual creation timestamp
    status: 'em andamento' as Status,
    categoria: 'NÃO CLASSIFICADA' as Categoria,
    notas: '',
    is_single_day: false
  });

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full max-w-xl rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <h3 className="text-2xl font-black text-slate-900 tracking-tight">Nova Ação</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-8 space-y-6">
          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Título da Tarefa</label>
            <input
              type="text"
              autoFocus
              value={formData.titulo}
              onChange={e => setFormData({ ...formData, titulo: e.target.value })}
              className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              placeholder="O que precisa ser feito?"
            />
          </div>

          <div className="flex items-center gap-3 bg-slate-50 p-4 rounded-2xl border border-slate-100">
            <input
              type="checkbox"
              id="single-day"
              checked={formData.is_single_day}
              onChange={e => {
                const checked = e.target.checked;
                setFormData(prev => ({
                  ...prev,
                  is_single_day: checked,
                  data_inicio: checked ? prev.data_limite || prev.data_inicio : prev.data_inicio
                }));
              }}
              className="w-5 h-5 rounded-lg border-slate-300 text-blue-600 focus:ring-blue-500 transition-all cursor-pointer"
            />
            <label htmlFor="single-day" className="text-xs font-bold text-slate-700 cursor-pointer select-none">Tarefa de um dia só (Apenas Prazo Final)</label>
          </div>

          <div className="grid grid-cols-2 gap-6">
            {!formData.is_single_day && (
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Data de Início</label>
                <input
                  type="date"
                  value={formData.data_inicio}
                  onChange={e => setFormData({ ...formData, data_inicio: e.target.value })}
                  className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                />
              </div>
            )}
            <div className={`space-y-2 ${formData.is_single_day ? 'col-span-2' : ''}`}>
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Prazo Final</label>
              <input
                type="date"
                value={formData.data_limite}
                onChange={e => {
                  const newLimit = e.target.value;
                  setFormData(prev => ({
                    ...prev,
                    data_limite: newLimit,
                    data_inicio: prev.is_single_day ? newLimit : prev.data_inicio
                  }));
                }}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Status</label>
              <select
                value={formData.status}
                onChange={e => setFormData({ ...formData, status: e.target.value as Status })}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
              >
                <option value="em andamento">Em Andamento</option>
                <option value="concluído">Concluído</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Tag (Classificação)</label>
              <select
                value={formData.categoria}
                onChange={e => setFormData({ ...formData, categoria: e.target.value as Categoria })}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
              >
                <option value="CLC">CLC</option>
                <option value="ASSISTÊNCIA">Assistência Estudantil</option>
                <option value="GERAL">Geral</option>
                <option value="NÃO CLASSIFICADA">Não Classificada</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Notas / Observações</label>
            <textarea
              rows={3}
              value={formData.notas}
              onChange={e => setFormData({ ...formData, notas: e.target.value })}
              className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-medium text-slate-700 focus:ring-2 focus:ring-slate-900 transition-all resize-none"
              placeholder="Detalhes da ação..."
            />
          </div>
        </div>

        <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4">
          <button onClick={onClose} className="flex-1 px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all">Cancelar</button>
          <button
            onClick={() => {
              if (!formData.titulo || !formData.data_limite) {
                alert("Preencha o título e o prazo final.");
                return;
              }

              // Validation
              if (!formData.is_single_day && formData.data_inicio > formData.data_limite) {
                alert("A data de início deve ser anterior ou igual ao prazo final.");
                return;
              }

              let finalNotes = formData.notas;
              if (formData.categoria !== 'NÃO CLASSIFICADA') {
                const tagStr = `Tag: ${formData.categoria}`;
                finalNotes = finalNotes ? `${finalNotes}\n\n${tagStr}` : tagStr;
              }

              onSave({
                ...formData,
                notas: finalNotes,
                data_criacao: new Date().toISOString()
              });
              onClose();
            }}
            className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
          >
            Criar Ação
          </button>
        </div>
      </div>
    </div>
  );
};

const TaskEditModal = ({ task, onSave, onDelete, onClose }: { task: Tarefa, onSave: (id: string, updates: Partial<Tarefa>) => void, onDelete: (id: string) => void, onClose: () => void }) => {
  const [formData, setFormData] = useState({
    titulo: task.titulo,
    data_inicio: task.data_inicio || (task.data_criacao ? task.data_criacao.split('T')[0] : ''),
    data_limite: task.data_limite === '-' ? '' : task.data_limite,
    data_criacao: task.data_criacao,
    status: task.status,
    categoria: task.categoria || 'NÃO CLASSIFICADA',
    notas: task.notas || '',
    acompanhamento: task.acompanhamento || [],
    is_single_day: !!task.is_single_day
  });

  const [newFollowUp, setNewFollowUp] = useState('');
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  // Helper to add follow-up locally before saving
  const handleAddFollowUp = () => {
    if (!newFollowUp.trim()) return;

    const newEntry: Acompanhamento = {
      data: new Date().toISOString(),
      nota: newFollowUp
    };

    setFormData(prev => ({
      ...prev,
      acompanhamento: [...prev.acompanhamento, newEntry]
    }));
    setNewFollowUp('');
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full max-w-xl max-h-[90vh] flex flex-col rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between flex-shrink-0">
          <h3 className="text-2xl font-black text-slate-900 tracking-tight">Editar Demanda</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-8 space-y-6 overflow-y-auto custom-scrollbar flex-1">
          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Título da Tarefa</label>
            <input
              type="text"
              value={formData.titulo}
              onChange={e => setFormData({ ...formData, titulo: e.target.value })}
              className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
            />
          </div>

          <div className="flex items-center gap-3 bg-slate-50 p-4 rounded-2xl border border-slate-100">
            <input
              type="checkbox"
              id="edit-single-day"
              checked={formData.is_single_day}
              onChange={e => {
                const checked = e.target.checked;
                setFormData(prev => ({
                  ...prev,
                  is_single_day: checked,
                  data_inicio: checked ? prev.data_limite || prev.data_inicio : prev.data_inicio
                }));
              }}
              className="w-5 h-5 rounded-lg border-slate-300 text-blue-600 focus:ring-blue-500 transition-all cursor-pointer"
            />
            <label htmlFor="edit-single-day" className="text-xs font-bold text-slate-700 cursor-pointer select-none">Tarefa de um dia só (Apenas Prazo Final)</label>
          </div>

          <div className="grid grid-cols-2 gap-6">
            {!formData.is_single_day && (
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Data de Início</label>
                <input
                  type="date"
                  value={formData.data_inicio}
                  onChange={e => setFormData({ ...formData, data_inicio: e.target.value })}
                  className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                />
              </div>
            )}
            <div className={`space-y-2 ${formData.is_single_day ? 'col-span-2' : ''}`}>
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Prazo Final</label>
              <input
                type="date"
                value={formData.data_limite}
                onChange={e => {
                  const newLimit = e.target.value;
                  setFormData(prev => ({
                    ...prev,
                    data_limite: newLimit,
                    data_inicio: prev.is_single_day ? newLimit : prev.data_inicio
                  }));
                }}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Tag (Classificação)</label>
              <select
                value={formData.categoria}
                onChange={e => setFormData({ ...formData, categoria: e.target.value as Categoria })}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              >
                <option value="CLC">CLC</option>
                <option value="ASSISTÊNCIA">Assistência Estudantil</option>
                <option value="GERAL">Geral</option>
                <option value="NÃO CLASSIFICADA">Não Classificada</option>
              </select>
            </div>
          </div>

          {/* New Acompanhamento Section */}
          <div className="space-y-3 pt-4 border-t border-slate-100">
            <label className="text-[10px] font-black text-blue-600 uppercase tracking-widest pl-1 flex items-center gap-2">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              Acompanhamento / Diário
            </label>

            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100 space-y-4 max-h-[200px] overflow-y-auto">
              {formData.acompanhamento.length === 0 ? (
                <p className="text-[10px] text-slate-400 font-medium italic text-center p-4">Nenhum registro de atividade.</p>
              ) : (
                <div className="space-y-3">
                  {formData.acompanhamento.map((entry, idx) => (
                    <div key={idx} className="flex gap-3 text-xs">
                      <div className="flex-shrink-0 w-24 text-[9px] font-black text-slate-400 uppercase pt-0.5 text-right">
                        {new Date(entry.data).toLocaleDateString('pt-BR')} <br />
                        {new Date(entry.data).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                      </div>
                      <div className="flex-1 bg-white p-2 rounded-lg border border-slate-100 text-slate-600 font-medium shadow-sm">
                        {entry.nota}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={newFollowUp}
                onChange={(e) => setNewFollowUp(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleAddFollowUp();
                }}
                placeholder="O que foi feito hoje?"
                className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-3 text-xs font-medium focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={handleAddFollowUp}
                disabled={!newFollowUp.trim()}
                className="bg-blue-100 text-blue-700 px-4 rounded-xl text-[10px] font-black uppercase hover:bg-blue-200 disabled:opacity-50 transition-all"
              >
                Adicionar
              </button>
            </div>
          </div>

          <div className="space-y-2 opacity-60">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Notas / Observações Originais (Imutável)</label>
            <textarea
              rows={2}
              value={formData.notas}
              readOnly
              disabled
              className="w-full bg-slate-100/50 border-none rounded-2xl px-6 py-4 text-xs font-medium text-slate-500 cursor-not-allowed resize-none"
            />
          </div>
        </div>

        <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4 flex-shrink-0">
          <button
            onClick={() => {
              if (!isConfirmingDelete) {
                setIsConfirmingDelete(true);
              } else {
                onDelete(task.id);
                onClose();
              }
            }}
            onMouseLeave={() => setIsConfirmingDelete(false)}
            className={`px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all border flex items-center gap-2 ${isConfirmingDelete
              ? 'bg-rose-600 text-white border-rose-600 shadow-lg shadow-rose-200 animate-in zoom-in-95'
              : 'text-rose-600 hover:bg-rose-50 border-rose-100'
              }`}
          >
            {isConfirmingDelete ? (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                Confirmar?
              </>
            ) : (
              'Excluir'
            )}
          </button>
          <div className="flex-1"></div>
          <button
            onClick={onClose}
            className="px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all"
          >
            Cancelar
          </button>
          <button
            onClick={() => {
              if (!formData.titulo || !formData.data_limite) {
                alert("Preencha o título e o prazo final.");
                return;
              }

              // Validation
              if (!formData.is_single_day && formData.data_inicio > formData.data_limite) {
                alert("A data de início deve ser anterior ou igual ao prazo final.");
                return;
              }

              // Verifica se tem algo no input de follow-up não adicionado
              let finalAcompanhamento = [...formData.acompanhamento];
              if (newFollowUp.trim()) {
                finalAcompanhamento.push({
                  data: new Date().toISOString(),
                  nota: newFollowUp
                });
              }

              onSave(task.id, {
                ...formData,
                acompanhamento: finalAcompanhamento
              });
              onClose();
            }}
            className="flex-1 bg-slate-900 text-white px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
          >
            Salvar Alterações
          </button>
        </div>
      </div>
    </div>
  );
};

const TaskExecutionView = ({ task, onSave, onClose }: { task: Tarefa, onSave: (id: string, updates: Partial<Tarefa>) => void, onClose: () => void }) => {
  const [newFollowUp, setNewFollowUp] = useState('');
  const [chatUrl, setChatUrl] = useState(task.chat_gemini_url || '');
  const [isTimerRunning, setIsTimerRunning] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [sessionTotalSeconds, setSessionTotalSeconds] = useState(task.tempo_total_segundos || 0);

  useEffect(() => {
    let interval: number | null = null;
    if (isTimerRunning) {
      interval = window.setInterval(() => {
        setSeconds(prev => prev + 1);
        setSessionTotalSeconds(prev => prev + 1);
      }, 1000);
    } else {
      if (interval) clearInterval(interval);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isTimerRunning]);

  const handleToggleTimer = () => {
    if (isTimerRunning) {
      // Quando parar, salvar o tempo total
      onSave(task.id, { tempo_total_segundos: sessionTotalSeconds });
    }
    setIsTimerRunning(!isTimerRunning);
  };

  const formatTime = (totalSeconds: number) => {
    const hrs = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleAddFollowUp = () => {
    if (!newFollowUp.trim()) return;
    const newEntry: Acompanhamento = {
      data: new Date().toISOString(),
      nota: newFollowUp
    };
    const updatedAcompanhamento = [...(task.acompanhamento || []), newEntry];
    onSave(task.id, { acompanhamento: updatedAcompanhamento });
    setNewFollowUp('');
  };

  const handleSaveChatUrl = () => {
    onSave(task.id, { chat_gemini_url: chatUrl });
  };

  return (
    <div className={`fixed inset-0 z-[200] flex flex-col transition-all duration-700 ease-in-out ${isTimerRunning ? 'bg-[#050505] text-white' : 'bg-slate-50 text-slate-900'} overflow-hidden`}>
      {/* Botão de Fechar Geral */}
      <button
        onClick={() => {
          if (isTimerRunning) handleToggleTimer();
          onClose();
        }}
        className={`fixed top-8 right-8 z-[210] p-3 rounded-2xl transition-all ${isTimerRunning ? 'bg-white/5 hover:bg-white/10 text-white/20' : 'bg-white shadow-lg text-slate-400 hover:text-slate-900 border border-slate-100'}`}
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
      </button>

      {isTimerRunning ? (
        /* --- MODO FOCO ATIVO --- */
        <div className="flex-1 flex flex-col items-center justify-center p-12 relative animate-in fade-in zoom-in-95 duration-1000 gap-16">
          <div className="text-center px-12 z-10">
            <span className="text-blue-400 text-[10px] font-black uppercase tracking-[0.4em] mb-6 block animate-pulse">Sessão em Execução</span>
            <h1 className="text-3xl md:text-5xl lg:text-6xl font-black tracking-tighter text-white/90 max-w-5xl mx-auto leading-tight">
              {task.titulo}
            </h1>
          </div>

          <div className="w-full max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div className="flex flex-col items-center justify-center">
              <div className="text-[8rem] md:text-[10rem] lg:text-[12rem] font-black tracking-tighter tabular-nums text-white leading-none drop-shadow-[0_0_50px_rgba(37,99,235,0.3)] relative">
                {formatTime(seconds).split(':').slice(1).join(':')}
                <span className="text-3xl md:text-4xl text-blue-500/50 absolute -right-16 bottom-8 uppercase tracking-widest leading-none">
                  {formatTime(seconds).split(':')[0]}h
                </span>
              </div>

              <button
                onClick={handleToggleTimer}
                className="flex items-center gap-4 px-12 py-6 mt-8 rounded-full bg-rose-500 text-white text-sm font-black uppercase tracking-widest shadow-[0_0_40px_rgba(244,63,94,0.4)] hover:bg-rose-600 transition-all hover:scale-105 active:scale-95"
              >
                <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
                Finalizar Sessão de Foco
              </button>
            </div>

            {/* Diário de Execução no Modo Foco */}
            <div className="w-full h-[400px] bg-white/5 rounded-[2.5rem] border border-white/10 p-8 flex flex-col backdrop-blur-sm">
              <div className="flex items-center justify-between mb-6 flex-shrink-0">
                <h4 className="text-[10px] font-black text-white/40 uppercase tracking-widest">Diário de Execução</h4>
                <div className="flex gap-2 w-full max-w-xs">
                  <input
                    type="text"
                    value={newFollowUp}
                    onChange={e => setNewFollowUp(e.target.value)}
                    placeholder="Registre o que você está fazendo..."
                    className="bg-white/10 border border-white/10 rounded-lg px-4 py-2 text-[11px] font-medium outline-none focus:ring-1 focus:ring-blue-500 text-white placeholder:text-white/20 w-full"
                    onKeyDown={e => e.key === 'Enter' && handleAddFollowUp()}
                  />
                  <button onClick={handleAddFollowUp} className="bg-blue-600 text-white px-4 rounded-lg text-[9px] font-black uppercase transition-all hover:bg-blue-500">Enviar</button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto custom-scrollbar space-y-3 pr-2">
                {task.acompanhamento && task.acompanhamento.length > 0 ? (
                  task.acompanhamento.slice().reverse().map((entry, idx) => (
                    <div key={idx} className="bg-white/5 p-4 rounded-2xl border border-white/5 flex gap-4 hover:bg-white/10 transition-colors">
                      <div className="flex-shrink-0 text-[8px] font-black text-white/30 uppercase leading-none min-w-[50px] pt-1">
                        {new Date(entry.data).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                      </div>
                      <p className="text-[11px] font-medium text-white/80 leading-snug">{entry.nota}</p>
                    </div>
                  ))
                ) : (
                  <div className="h-full flex items-center justify-center text-white/20 text-[10px] font-black uppercase tracking-widest italic">Nenhum registro nesta sessão</div>
                )}
              </div>
            </div>
          </div>

          {/* Overlay de Vinheta para Foco Distante */}
          <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(circle_at_center,transparent_20%,rgba(0,0,0,0.9)_100%)] z-[-1]"></div>
        </div>
      ) : (
        /* --- MODO PREPARAÇÃO --- */
        <div className="flex-1 flex flex-col overflow-hidden animate-in fade-in duration-500">
          <div className="p-10 pb-4">
            <span className="text-blue-600 text-[10px] font-black uppercase tracking-[0.3em] mb-2 block">Central de Execução / CLC</span>
            <h1 className="text-4xl font-black text-slate-900 tracking-tighter leading-none">{task.titulo}</h1>
          </div>

          <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-8 p-10 pt-4 overflow-hidden">
            {/* Esquerda: Botão de Play Gigante */}
            <div className="flex flex-col items-center justify-center bg-white rounded-[3rem] border border-slate-200 shadow-2xl relative group overflow-hidden">
              <div className="absolute inset-0 bg-blue-50 opacity-0 group-hover:opacity-100 transition-opacity duration-700"></div>

              <div className="relative text-center space-y-8 z-10">
                <div className="text-[10px] font-black text-slate-400 uppercase tracking-[0.4em]">Pronto para Começar?</div>
                <button
                  onClick={handleToggleTimer}
                  className="w-48 h-48 rounded-full bg-blue-600 text-white flex items-center justify-center shadow-[0_20px_60px_rgba(37,99,235,0.4)] hover:scale-110 active:scale-95 transition-all duration-500 group/play"
                >
                  <svg className="w-20 h-20 ml-3 group-hover/play:scale-110 transition-transform" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                </button>
                <div className="space-y-1">
                  <div className="text-4xl font-black text-slate-900 tabular-nums">
                    {formatTime(sessionTotalSeconds)}
                  </div>
                  <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Tempo Total Acumulado</div>
                </div>
              </div>

              {/* Status da Demanda no Canto */}
              <div className="absolute bottom-10 left-10 flex items-center gap-3">
                <button
                  onClick={() => onSave(task.id, { status: task.status === 'concluído' ? 'em andamento' : 'concluído' })}
                  className={`px-6 py-3 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all ${task.status === 'concluído' ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                    }`}
                >
                  {task.status === 'concluído' ? 'Concluída' : 'Marcar Concluída'}
                </button>
              </div>
            </div>

            {/* Direita: Especialista e Histórico */}
            <div className="flex flex-col gap-6 overflow-hidden">
              {/* Especialista */}
              <div className="bg-gradient-to-br from-indigo-600 to-blue-700 rounded-[2.5rem] p-6 text-white shadow-xl flex-shrink-0">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center backdrop-blur-md">
                      <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L14.85 8.15L21 11L14.85 13.85L12 20L9.15 13.85L3 11L9.15 8.15L12 2Z" /></svg>
                    </div>
                    <div>
                      <h4 className="text-xs font-black uppercase tracking-widest">Especialista CLC</h4>
                      <p className="text-[8px] text-white/50 uppercase font-bold tracking-widest">Chat Contextual</p>
                    </div>
                  </div>
                  <a
                    href={task.chat_gemini_url || "https://gemini.google.com/gem/096c0e51e1b9"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="bg-white text-indigo-600 px-6 py-3 rounded-xl text-[9px] font-black uppercase tracking-widest hover:bg-slate-100 transition-all flex items-center gap-2"
                  >
                    Abrir Chat
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                  </a>
                </div>
                <div className="relative">
                  <input
                    type="text"
                    placeholder="Cole o link do chat aqui para salvar..."
                    value={chatUrl}
                    onChange={e => setChatUrl(e.target.value)}
                    className="w-full bg-black/20 border border-white/10 rounded-xl px-4 py-3 text-[11px] font-medium focus:ring-1 focus:ring-white/30 outline-none text-white placeholder:text-white/30"
                  />
                  {chatUrl !== (task.chat_gemini_url || '') && (
                    <button onClick={handleSaveChatUrl} className="absolute right-2 top-2 bg-white text-blue-600 px-3 py-1.5 rounded-lg text-[8px] font-black uppercase shadow-lg">Salvar</button>
                  )}
                </div>
              </div>

              {/* Log de Atividade */}
              <div className="flex-1 bg-white rounded-[2.5rem] border border-slate-200 shadow-xl p-8 flex flex-col overflow-hidden">
                <div className="flex items-center justify-between mb-4 flex-shrink-0">
                  <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Diário de Execução</h4>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newFollowUp}
                      onChange={e => setNewFollowUp(e.target.value)}
                      placeholder="Registre o que foi feito..."
                      className="bg-slate-50 border border-slate-100 rounded-lg px-4 py-2 text-[11px] font-medium outline-none focus:ring-1 focus:ring-blue-500 w-48"
                      onKeyDown={e => e.key === 'Enter' && handleAddFollowUp()}
                    />
                    <button onClick={handleAddFollowUp} className="bg-slate-900 text-white px-4 rounded-lg text-[9px] font-black uppercase transition-all">Add</button>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar space-y-3 pr-2">
                  {task.acompanhamento && task.acompanhamento.length > 0 ? (
                    task.acompanhamento.slice().reverse().map((entry, idx) => (
                      <div key={idx} className="bg-slate-50 p-4 rounded-2xl border border-slate-100 flex gap-4 hover:border-blue-200 transition-colors">
                        <div className="flex-shrink-0 text-[8px] font-black text-slate-400 uppercase leading-none min-w-[50px] pt-1">
                          {new Date(entry.data).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}
                        </div>
                        <p className="text-[11px] font-medium text-slate-700 leading-snug">{entry.nota}</p>
                      </div>
                    ))
                  ) : (
                    <div className="h-full flex items-center justify-center text-slate-300 text-[10px] font-black uppercase tracking-widest italic opacity-50">Nenhum registro</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const AudioRecorder = React.memo(({ onAudioReady, disabled, compact }: { onAudioReady: (blob: Blob, base64: string, url: string) => void, disabled: boolean, compact?: boolean }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
        const audioUrl = URL.createObjectURL(audioBlob);
        const reader = new FileReader();
        reader.readAsDataURL(audioBlob);
        reader.onloadend = () => {
          const base64String = (reader.result as string).split(',')[1];
          onAudioReady(audioBlob, base64String, audioUrl);
        };
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingTime(0);
      timerRef.current = window.setInterval(() => setRecordingTime(prev => prev + 1), 1000);
    } catch (err) {
      console.error(err);
      alert("Erro ao acessar microfone.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  };

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  if (compact) {
    return (
      <div className="flex items-center">
        {isRecording ? (
          <button
            onClick={stopRecording}
            className="h-10 px-3 bg-rose-600 text-white rounded-xl flex items-center justify-center shadow-lg animate-pulse gap-2"
          >
            <div className="w-2 h-2 bg-white rounded-full animate-bounce"></div>
            <span className="text-[10px] font-black tabular-nums">{formatTime(recordingTime)}</span>
          </button>
        ) : (
          <button
            onClick={startRecording}
            disabled={disabled}
            className="w-10 h-10 bg-blue-600 text-white rounded-xl flex items-center justify-center shadow-lg active:scale-90 transition-transform disabled:opacity-50"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4">
      {isRecording ? (
        <div className="flex items-center gap-6 bg-rose-50 px-8 py-4 rounded-[2rem] border border-rose-100 shadow-xl animate-pulse">
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 bg-rose-600 rounded-full"></div>
            <span className="text-rose-600 font-black tabular-nums text-lg">{formatTime(recordingTime)}</span>
          </div>
          <button
            onClick={stopRecording}
            className="bg-rose-600 text-white p-4 rounded-full shadow-lg hover:bg-rose-700 transition-all active:scale-95"
          >
            <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
          </button>
        </div>
      ) : (
        <button
          onClick={startRecording}
          disabled={disabled}
          className="bg-blue-600 text-white p-4 md:p-8 rounded-full shadow-2xl hover:bg-blue-700 transition-all active:scale-95 disabled:opacity-50 group relative"
        >
          <div className="absolute inset-0 bg-blue-400 rounded-full animate-ping opacity-20 group-hover:block hidden"></div>
          <svg className="w-6 h-6 md:w-10 md:h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
        </button>
      )}
      <p className="hidden md:block text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{isRecording ? 'Gravando sua ideia...' : 'Clique para começar a gravar'}</p>
    </div>
  );
});

const FerramentasView = ({ ideas, onAudioReady, onDeleteIdea, onArchiveIdea, onAddTextIdea, onUpdateIdea, isProcessing, activeTool, setActiveTool, isAddingText, setIsAddingText }: {
  ideas: BrainstormIdea[],
  onAudioReady: (blob: Blob, base64: string, url: string) => void,
  onDeleteIdea: (id: string) => void,
  onArchiveIdea: (id: string) => void,
  onAddTextIdea: (text: string) => void,
  onUpdateIdea: (id: string, text: string) => void,
  isProcessing: boolean,
  activeTool: 'brainstorming' | null,
  setActiveTool: (tool: 'brainstorming' | null) => void,
  isAddingText: boolean,
  setIsAddingText: (val: boolean) => void
}) => {
  const [textInput, setTextInput] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [sortOrder, setSortOrder] = useState<'date-desc' | 'date-asc'>('date-desc');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const activeIdeas = ideas
    .filter(i => i.status !== 'archived')
    .filter(i => i.text.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => {
      if (sortOrder === 'date-desc') return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });

  const toggleCardExpansion = (id: string) => {
    setExpandedCards(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  if (!activeTool) {
    return (
      <div className="animate-in grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-8 pb-20 px-4 md:px-0">
        <button
          onClick={() => setActiveTool('brainstorming')}
          className="bg-white p-6 md:p-12 rounded-[2rem] md:rounded-[3rem] border border-slate-200 shadow-xl hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-blue-50 rounded-2xl flex items-center justify-center text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Brainstorming</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Grave ideias rápidas e transcreva com IA.</p>
          </div>
        </button>

        <button
          disabled
          className="bg-white p-6 md:p-12 rounded-[2rem] md:rounded-[3rem] border border-slate-100 shadow-sm opacity-60 grayscale cursor-not-allowed text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 relative overflow-hidden"
        >
          <div className="absolute top-2 right-2 md:top-4 md:right-4 bg-slate-100 text-slate-400 text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded-full">Em Breve</div>
          <div className="w-12 h-12 md:w-16 md:h-16 bg-slate-50 rounded-2xl flex items-center justify-center text-slate-400 flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-400 tracking-tighter mb-1 md:mb-2">Criação de DFD</h3>
            <p className="text-slate-400 font-medium leading-relaxed italic text-xs md:text-sm">Documento de Formalização.</p>
          </div>
        </button>

        <button
          disabled
          className="bg-white p-6 md:p-12 rounded-[2rem] md:rounded-[3rem] border border-slate-100 shadow-sm opacity-60 grayscale cursor-not-allowed text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 relative overflow-hidden"
        >
          <div className="absolute top-2 right-2 md:top-4 md:right-4 bg-slate-100 text-slate-400 text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded-full">Em Breve</div>
          <div className="w-12 h-12 md:w-16 md:h-16 bg-slate-50 rounded-2xl flex items-center justify-center text-slate-400 flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-400 tracking-tighter mb-1 md:mb-2">Termo de Referência</h3>
            <p className="text-slate-400 font-medium leading-relaxed italic text-xs md:text-sm">Elabore TRs com IA.</p>
          </div>
        </button>

        <button
          disabled
          className="bg-white p-6 md:p-12 rounded-[2rem] md:rounded-[3rem] border border-slate-100 shadow-sm opacity-60 grayscale cursor-not-allowed text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 relative overflow-hidden"
        >
          <div className="absolute top-2 right-2 md:top-4 md:right-4 bg-slate-100 text-slate-400 text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded-full">Em Breve</div>
          <div className="w-12 h-12 md:w-16 md:h-16 bg-slate-50 rounded-2xl flex items-center justify-center text-slate-400 flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-400 tracking-tighter mb-1 md:mb-2">Pesquisa CATMAT</h3>
            <p className="text-slate-400 font-medium leading-relaxed italic text-xs md:text-sm">Busca inteligente.</p>
          </div>
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="animate-in space-y-12 pb-40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setActiveTool(null)}
              className="p-3 bg-white border border-slate-200 rounded-2xl text-slate-400 hover:text-slate-900 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight uppercase tracking-widest text-[10px]">Ferramentas / Brainstorming</h3>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-4 max-w-4xl mx-auto w-full mb-8 px-2 md:px-0">
          <div className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-3 flex items-center gap-3 shadow-sm focus-within:ring-2 focus-within:ring-blue-100 transition-all">
            <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
            <input
              type="text"
              placeholder="Pesquisar nas ideias..."
              className="flex-1 bg-transparent outline-none text-xs md:text-sm font-bold text-slate-700 placeholder:text-slate-400"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
            />
          </div>
          <div className="flex bg-white border border-slate-200 rounded-xl p-1 shadow-sm w-fit self-end md:self-auto">
            <button
              onClick={() => setSortOrder('date-desc')}
              className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${sortOrder === 'date-desc' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'}`}
            >
              Recentes
            </button>
            <button
              onClick={() => setSortOrder('date-asc')}
              className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${sortOrder === 'date-asc' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'}`}
            >
              Antigas
            </button>
          </div>
        </div>

        <div className="flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-2 md:gap-8 mb-32 md:mb-0">
          {activeIdeas.map(idea => (
            <div key={idea.id} className="bg-white p-5 md:p-8 rounded-2xl md:rounded-[2.5rem] border border-slate-100 md:border-slate-200 shadow-sm md:shadow-lg hover:shadow-md md:hover:shadow-2xl transition-all group flex flex-col relative overflow-hidden">
              <div className="flex items-center justify-between mb-3 md:mb-6">
                <span className="text-[9px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest">{formatDate(idea.timestamp.split('T')[0])}</span>
                <div className="flex items-center gap-1 md:gap-2 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all">
                  {editingId === idea.id ? (
                    <button
                      onClick={() => {
                        if (editText.trim()) {
                          onUpdateIdea(idea.id, editText);
                          setEditingId(null);
                        }
                      }}
                      className="text-blue-600 hover:bg-blue-50 p-2 rounded-xl transition-colors"
                    >
                      <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => {
                          setEditingId(idea.id);
                          setEditText(idea.text);
                        }}
                        className="text-slate-400 hover:text-blue-600 p-2 rounded-xl transition-colors"
                        title="Editar"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                      </button>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(idea.text).then(() => {
                            setCopiedId(idea.id);
                            setTimeout(() => setCopiedId(null), 2000);
                          });
                        }}
                        className={`p-2 rounded-xl transition-colors ${copiedId === idea.id ? 'text-emerald-500 bg-emerald-50' : 'text-slate-400 hover:text-blue-600'}`}
                        title="Copiar Texto"
                      >
                        {copiedId === idea.id ? (
                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                        ) : (
                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                        )}
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => onArchiveIdea(idea.id)}
                    className="text-emerald-500 hover:bg-emerald-50 p-2 rounded-xl transition-colors"
                    title="Concluir / Arquivar"
                  >
                    <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                  </button>
                  <button
                    onClick={() => onDeleteIdea(idea.id)}
                    className="text-slate-300 hover:text-rose-500 p-2 rounded-xl transition-colors"
                    title="Excluir Permanentemente"
                  >
                    <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </button>
                </div>
              </div>

              {editingId === idea.id ? (
                <textarea
                  autoFocus
                  className="w-full bg-slate-50 border border-slate-200 rounded-2xl p-4 text-sm md:text-lg font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 min-h-[100px] resize-none"
                  value={editText}
                  onChange={e => setEditText(e.target.value)}
                />
              ) : (
                <div className="flex-1">
                  <p
                    className={`text-slate-800 font-bold leading-relaxed mb-3 md:mb-6 text-sm md:text-lg ${!expandedCards.has(idea.id) && idea.text.length > 150 ? 'line-clamp-3' : ''
                      }`}
                  >
                    "{idea.text}"
                  </p>
                  {idea.text.length > 150 && (
                    <button
                      onClick={() => toggleCardExpansion(idea.id)}
                      className="text-blue-600 hover:text-blue-700 text-xs font-black uppercase tracking-widest transition-colors flex items-center gap-1"
                    >
                      {expandedCards.has(idea.id) ? (
                        <>
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 15l7-7 7 7" /></svg>
                          Mostrar menos
                        </>
                      ) : (
                        <>
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                          Mostrar mais
                        </>
                      )}
                    </button>
                  )}
                </div>
              )}

              {idea.audioUrl && (
                <audio controls src={idea.audioUrl} className="w-full h-10 opacity-50 hover:opacity-100 transition-opacity" />
              )}
            </div>
          ))}
          {activeIdeas.length === 0 && !isProcessing && (
            <div className="col-span-full py-20 text-center border-4 border-dashed border-slate-100 rounded-[3rem]">
              <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Nenhuma ideia ativa</p>
              <p className="text-slate-400 text-sm font-medium mt-2">Grave ou digite uma ideia para começar.</p>
            </div>
          )}
        </div>
      </div>

      {/* Input Flutuante Centralizado */}
      {isAddingText && (
        <div className="fixed bottom-24 left-4 right-4 md:left-1/2 md:-translate-x-1/2 w-auto md:w-full md:max-w-2xl z-[110] flex items-center gap-2 animate-in zoom-in-95 slide-in-from-bottom-10 bg-white/90 backdrop-blur-md p-4 rounded-[2rem] shadow-2xl border border-slate-200">
          <input
            type="text"
            autoFocus
            placeholder="Sua ideia aqui..."
            className="flex-1 bg-white border border-slate-200 rounded-2xl px-6 py-4 text-sm font-medium focus:ring-4 focus:ring-blue-100 outline-none shadow-sm transition-all"
            value={textInput}
            onChange={e => setTextInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && textInput.trim()) {
                onAddTextIdea(textInput);
                setTextInput('');
                setIsAddingText(false);
              }
            }}
          />
          <button
            onClick={() => {
              if (textInput.trim()) {
                onAddTextIdea(textInput);
                setTextInput('');
                setIsAddingText(false);
              } else {
                setIsAddingText(false);
              }
            }}
            className="bg-blue-600 text-white p-4 rounded-2xl hover:bg-blue-700 transition-all shadow-xl shadow-blue-100 flex-shrink-0"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
          </button>
        </div>
      )}

      {/* Barra Inferior Fixa para Brainstorming */}
      {!isAddingText && (
        <div className="fixed bottom-0 left-0 right-0 bg-white/80 backdrop-blur-md border-t border-slate-200 supports-[backdrop-filter]:bg-white/60 px-6 py-4 z-[100] flex justify-between items-center shadow-[0_-10px_40px_rgba(0,0,0,0.1)]">
          <div className="font-black text-[10px] text-slate-400 uppercase tracking-widest pl-1">Ações Rápidas</div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setIsAddingText(true)}
              className="h-11 w-11 bg-slate-900 text-white rounded-xl flex items-center justify-center shadow-lg active:scale-90 transition-transform hover:bg-slate-800"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
            </button>
            <div className="h-8 w-px bg-slate-200"></div>
            <AudioRecorder onAudioReady={onAudioReady} disabled={isProcessing} compact />
          </div>
        </div>
      )}

      {isProcessing && (
        <div className="fixed top-20 right-4 z-[120] flex items-center gap-3 text-blue-600 font-black uppercase text-[10px] tracking-widest animate-pulse bg-white/90 px-4 py-2 rounded-full border border-blue-100 shadow-lg md:relative md:top-auto md:right-auto md:bg-transparent md:border-none md:shadow-none">
          <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          <span>Processando...</span>
        </div>
      )}
    </>
  );
};

const App: React.FC = () => {
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [entregas, setEntregas] = useState<EntregaInstitucional[]>([]);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Finance State
  const [financeTransactions, setFinanceTransactions] = useState<FinanceTransaction[]>([]);
  const [financeGoals, setFinanceGoals] = useState<FinanceGoal[]>([]);
  const [financeSettings, setFinanceSettings] = useState<FinanceSettings>({
    monthlyBudget: 5000,
    sprintDates: { 1: "08", 2: "15", 3: "22", 4: "01" }
  });

  // Finance Sync
  useEffect(() => {
    const unsubTransactions = onSnapshot(collection(db, 'finance_transactions'), (snapshot) => {
      setFinanceTransactions(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as FinanceTransaction)));
    });
    const unsubGoals = onSnapshot(collection(db, 'finance_goals'), (snapshot) => {
      setFinanceGoals(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as FinanceGoal)));
    });
    const unsubSettings = onSnapshot(doc(db, 'finance_settings', 'config'), (doc) => {
      if (doc.exists()) {
        setFinanceSettings(doc.data() as FinanceSettings);
      }
    });

    const qFixedBills = query(collection(db, 'fixed_bills'));
    const unsubFixedBills = onSnapshot(qFixedBills, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as FixedBill));
      setFixedBills(data);
    });

    return () => {
      unsubTransactions();
      unsubGoals();
      unsubSettings();
      unsubFixedBills();
    };
  }, []);

  // Finance Processing Logic (The Listener)
  useEffect(() => {
    const processFinanceTasks = async () => {
      // Monitora TODAS as tarefas de Gasto Semanal (ativas ou concluídas) para garantir sincronia
      const financeTasks = tarefas.filter(t =>
        t.status !== 'excluído' as any &&
        t.titulo.toLowerCase().includes('gasto semanal') &&
        t.notas && /Tag:\s*GASTO\s*SEMANAL/i.test(t.notas)
      );

      for (const task of financeTasks) {
        const valueMatch = task.notas?.match(/Valor:\s*R\$\s*([\d\.,]+)/i);
        if (valueMatch) {
          try {
            // Normaliza valor (formato BR: 1.000,00 -> 1000.00)
            const amountStr = valueMatch[1].replace(/\./g, '').replace(',', '.');
            const amount = parseFloat(amountStr);

            if (isNaN(amount)) continue;

            // Recalcula dados (Data, Sprint)
            const dateMatch = task.titulo.match(/(\d{2}\/\d{2}\/\d{4})/);
            let transactionDate = new Date().toISOString();
            if (dateMatch) {
              const [d, m, y] = dateMatch[1].split('/').map(Number);
              transactionDate = new Date(y, m - 1, d).toISOString();
            }

            const day = new Date(transactionDate).getDate();
            // Lógica original de sprint: < 8, < 15, < 22, resto (4)
            const sprintOriginal = day < 8 ? 1 : day < 15 ? 2 : day < 22 ? 3 : 4;

            const existingTransaction = financeTransactions.find(ft => ft.originalTaskId === task.id);

            if (existingTransaction) {
              // UPDATE: Se já existe, verifica se o valor mudou
              if (existingTransaction.amount !== amount) {
                await updateDoc(doc(db, 'finance_transactions', existingTransaction.id), {
                  amount,
                  date: transactionDate,
                  sprint: sprintOriginal,
                  description: task.titulo
                });
                showToast(`Valor atualizado: R$ ${amount.toLocaleString('pt-BR')}`, 'info');
              }
            } else {
              // CREATE: Se não existe, cria
              await addDoc(collection(db, 'finance_transactions'), {
                description: task.titulo,
                amount,
                date: transactionDate,
                sprint: sprintOriginal,
                category: 'Gasto Semanal',
                originalTaskId: task.id
              });

              // Marca como concluída apenas se ainda não estiver (para evitar updates desnecessários)
              if (normalizeStatus(task.status) !== 'concluido') {
                await updateDoc(doc(db, 'tarefas', task.id), {
                  status: 'concluído',
                  data_conclusao: new Date().toISOString().split('T')[0]
                });
                showToast(`Gasto processado: R$ ${amount.toLocaleString('pt-BR')}`, 'success');
              }
            }
          } catch (error) {
            console.error("Erro ao processar tarefa financeira:", error);
          }
        }
      }
    };

    if (tarefas.length > 0) {
      processFinanceTasks();
    }
  }, [tarefas, financeTransactions]); // Adicionado financeTransactions para garantir consistência


  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'success') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  };

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  const handleBatchTag = async (categoria: Categoria) => {
    if (selectedTaskIds.length === 0) return;
    try {
      setLoading(true);
      const batchSize = selectedTaskIds.length;

      const promises = selectedTaskIds.map(async (id) => {
        const t = tarefas.find(task => task.id === id);
        if (!t) return;

        let finalNotes = t.notas || '';
        const tagStr = `Tag: ${categoria}`;
        finalNotes = finalNotes.replace(/Tag:\s*(CLC|ASSISTÊNCIA|GERAL|NÃO CLASSIFICADA)/gi, '').trim();
        finalNotes = finalNotes ? `${finalNotes}\n\n${tagStr}` : tagStr;

        return updateDoc(doc(db, 'tarefas', id), {
          categoria: categoria,
          notas: finalNotes,
          data_atualizacao: new Date().toISOString()
        });
      });

      await Promise.all(promises);
      setSelectedTaskIds([]);
      showToast(`${batchSize} tarefas atualizadas!`, 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar em lote.", 'error');
    } finally {
      setLoading(false);
    }
  };

  // Dashboard states
  const [dashboardViewMode, setDashboardViewMode] = useState<'list' | 'calendar'>('list');
  const [fixedBills, setFixedBills] = useState<FixedBill[]>([]);
  const [calendarViewMode, setCalendarViewMode] = useState<'month' | 'week'>('month');
  const [calendarDate, setCalendarDate] = useState(new Date());

  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeModule, setActiveModule] = useState<'home' | 'acoes' | 'financeiro' | 'ferramentas'>('home');
  const [viewMode, setViewMode] = useState<'gallery' | 'pgc' | 'licitacoes' | 'assistencia' | 'sistemas' | 'plano-trabalho' | 'ferramentas'>('gallery');
  const [selectedTask, setSelectedTask] = useState<Tarefa | null>(null);
  const [planosTrabalho, setPlanosTrabalho] = useState<PlanoTrabalho[]>([]);
  const [statusFilter, setStatusFilter] = useState<Status[]>(['em andamento']);
  const [sortOption, setSortOption] = useState<SortOption>('date-asc');
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [syncData, setSyncData] = useState<any>(null);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);

  // Sync Logic
  useEffect(() => {
    const unsub = onSnapshot(doc(db, 'system', 'sync'), (snap) => {
      if (snap.exists()) {
        const data = snap.data();
        setSyncData(data);
        if (data.status === 'processing' || data.status === 'requested') setIsSyncing(true);
        if (data.status === 'completed' || data.status === 'error') setIsSyncing(false);
      }
    });
    return () => unsub();
  }, []);

  const handleSync = async () => {
    if (isSyncing) {
      setIsTerminalOpen(true);
      return;
    }

    setIsTerminalOpen(true);
    setIsSyncing(true);
    showToast("Iniciando Sincronização Profunda...", "info");

    try {
      await setDoc(doc(db, 'system', 'sync'), {
        status: 'requested',
        timestamp: new Date().toISOString(),
        logs: ["Aguardando resposta do Bot..."]
      });
    } catch (e) {
      console.error(e);
      showToast("Erro ao solicitar sincronização.", "error");
      setIsSyncing(false);
    }
  };
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [hasAutoExpanded, setHasAutoExpanded] = useState(false);

  // Estados PGC
  const [atividadesPGC, setAtividadesPGC] = useState<AtividadeRealizada[]>([]);
  const [afastamentos, setAfastamentos] = useState<Afastamento[]>([]);
  const [pgcSubView, setPgcSubView] = useState<'audit' | 'heatmap' | 'config'>('audit');
  const [unidades, setUnidades] = useState<{ id: string, nome: string }[]>([]);
  const [sistemasAtivos, setSistemasAtivos] = useState<string[]>([]);

  const [isImportPlanOpen, setIsImportPlanOpen] = useState(false);
  const [isCompletedTasksOpen, setIsCompletedTasksOpen] = useState(false);
  const [brainstormIdeas, setBrainstormIdeas] = useState<BrainstormIdea[]>([]);
  const [isProcessingIdea, setIsProcessingIdea] = useState(false);
  const [activeFerramenta, setActiveFerramenta] = useState<'brainstorming' | null>(null);
  const [isBrainstormingAddingText, setIsBrainstormingAddingText] = useState(false);

  const handleUpdateTarefa = async (id: string, updates: Partial<Tarefa>) => {
    try {
      const docRef = doc(db, 'tarefas', id);
      await updateDoc(docRef, {
        ...updates,
        data_atualizacao: new Date().toISOString()
      });
      showToast("Tarefa atualizada!", 'success');
    } catch (err) {
      console.error("Erro ao atualizar tarefa:", err);
      showToast("Erro ao salvar alterações.", 'error');
    }
  };

  const handleToggleTarefaStatus = async (id: string, currentStatus: string) => {
    try {
      const isConcluido = normalizeStatus(currentStatus) === 'concluido';
      const newStatus = isConcluido ? 'em andamento' : 'concluído';
      const now = new Date().toISOString();

      await updateDoc(doc(db, 'tarefas', id), {
        status: newStatus,
        data_conclusao: !isConcluido ? now : null,
        data_atualizacao: now
      });
      showToast(isConcluido ? "Tarefa reaberta!" : "Tarefa concluída!", 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao alterar status.", 'error');
    }
  };

  const handleDeleteTarefa = async (id: string) => {
    try {
      setLoading(true);
      const docRef = doc(db, 'tarefas', id);
      // Marcamos como excluída para o push-tasks remover do Google
      await updateDoc(docRef, {
        status: 'excluído' as any,
        data_atualizacao: new Date().toISOString()
      });
      showToast('Tarefa excluída!', 'success');
    } catch (err) {
      console.error("Erro ao excluir tarefa:", err);
      showToast("Erro ao excluir.", 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleAudioReady = async (blob: Blob, base64: string, url: string) => {
    if (isProcessingIdea) return;
    setIsProcessingIdea(true);
    showToast("Transcrevendo áudio...", "info");

    try {
      // Usando a chave que já deve estar configurada no ambiente
      const genAI = new GoogleGenerativeAI(((import.meta as any).env.VITE_GEMINI_API_KEY || 'AIzaSyD3g8j8mDoJtbSX-ryOHvxEp3kAK4WQMvY'));
      const model = genAI.getGenerativeModel({ model: "gemini-3-flash-preview" });

      const result = await model.generateContent([
        {
          inlineData: {
            mimeType: blob.type,
            data: base64
          }
        },
        { text: "Transcreva o áudio acima exatamente como falado, fazendo apenas as correções ortográficas e de pontuação necessárias. Não resuma, não interprete e não adicione nenhum texto além da transcrição." },
      ]);

      const response = await result.response;
      const text = response.text();

      await addDoc(collection(db, 'brainstorm_ideas'), {
        text: text || "Transcrição vazia",
        audioUrl: url,
        timestamp: new Date().toISOString(),
        status: 'active'
      });

      showToast("Ideia processada e salva!", "success");
    } catch (err) {
      console.error("Erro no processamento Gemini:", err);
      showToast("Erro ao transcrever áudio.", "error");
    } finally {
      setIsProcessingIdea(false);
    }
  };

  const handleUpdateIdea = async (id: string, text: string) => {
    try {
      await updateDoc(doc(db, 'brainstorm_ideas', id), { text });
      showToast("Ideia atualizada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar ideia.", "error");
    }
  };

  const handleArchiveIdea = async (id: string) => {
    try {
      await updateDoc(doc(db, 'brainstorm_ideas', id), {
        status: 'archived'
      });
      showToast("Ideia concluída e arquivada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao arquivar.", "error");
    }
  };

  const handleAddTextIdea = async (text: string) => {
    try {
      await addDoc(collection(db, 'brainstorm_ideas'), {
        text,
        timestamp: new Date().toISOString(),
        status: 'active'
      });
      showToast("Ideia registrada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao salvar ideia.", "error");
    }
  };

  const handleDeleteIdea = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'brainstorm_ideas', id));
      showToast("Ideia removida.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover.", "error");
    }
  };

  const handleCreateTarefa = async (data: Partial<Tarefa>) => {
    try {
      setLoading(true);
      await addDoc(collection(db, 'tarefas'), {
        ...data,
        google_id: "", // Sinaliza que precisa de PUSH
        data_atualizacao: new Date().toISOString(),
        projeto: 'Google Tasks',
        prioridade: 'média',
        contabilizar_meta: data.categoria === 'CLC' || data.categoria === 'ASSISTÊNCIA',
        acompanhamento: [],
        entregas_relacionadas: []
      });
      showToast("Nova ação criada!", 'success');
    } catch (err) {
      console.error("Erro ao criar tarefa:", err);
      showToast("Erro ao criar ação.", 'error');
    } finally {
      setLoading(false);
    }
  };



  useEffect(() => {
    setLoading(true);
    setError(null);

    // Listener para Tarefas
    const qTarefas = query(collection(db, 'tarefas'));
    const unsubscribeTarefas = onSnapshot(qTarefas, (snapshot) => {
      const dataT = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Tarefa));
      setTarefas(dataT);
      setLoading(false);
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Tarefas).");
      setLoading(false);
    });

    // Listener para Atividades PGC
    const qAtividadesPGC = query(collection(db, 'atividades_pgc'));
    const unsubscribeAtividadesPGC = onSnapshot(qAtividadesPGC, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as AtividadeRealizada));
      setAtividadesPGC(data);
    });

    // Listener para Afastamentos
    const qAfastamentos = query(collection(db, 'afastamentos'));
    const unsubscribeAfastamentos = onSnapshot(qAfastamentos, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Afastamento));
      setAfastamentos(data);
    });

    // Listener para Atividades (Entregas Legado/Config)
    const qAtividades = query(collection(db, 'atividades'));
    const unsubscribeAtividades = onSnapshot(qAtividades, (snapshot) => {
      const dataE = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as EntregaInstitucional));
      setEntregas(dataE);
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Atividades).");
    });


    const qUnidades = query(collection(db, 'unidades'));
    const unsubscribeUnidades = onSnapshot(qUnidades, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as { id: string, nome: string }));
      setUnidades(data);
    });

    const unsubscribeSistemas = onSnapshot(doc(db, 'configuracoes', 'sistemas'), (docSnap) => {
      if (docSnap.exists()) {
        setSistemasAtivos(docSnap.data().lista || []);
      }
    });

    return () => {
      unsubscribeTarefas();
      unsubscribeAtividades();
      unsubscribeAtividadesPGC();
      unsubscribeAfastamentos();
      unsubscribeUnidades();
      unsubscribeSistemas();
    };
  }, []);

  useEffect(() => {
    const qPlanos = query(collection(db, 'planos_trabalho'));
    const unsubscribePlanos = onSnapshot(qPlanos, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as PlanoTrabalho));
      setPlanosTrabalho(data);
    });
    return () => unsubscribePlanos();
  }, []);

  useEffect(() => {
    const qBrainstorm = query(collection(db, 'brainstorm_ideas'));
    const unsubscribeBrainstorm = onSnapshot(qBrainstorm, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as BrainstormIdea));
      setBrainstormIdeas(data.sort((a, b) => b.timestamp.localeCompare(a.timestamp)));
    });
    return () => unsubscribeBrainstorm();
  }, []);


  const handleLinkTarefa = async (tarefaId: string, entregaId: string) => {
    try {
      const docRef = doc(db, 'tarefas', tarefaId);
      await updateDoc(docRef, {
        entregas_relacionadas: arrayUnion(entregaId)
      });
      showToast("Vínculo criado com sucesso!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao vincular tarefa.", "error");
    }
  };

  const handleUnlinkTarefa = async (tarefaId: string, entregaId: string) => {
    try {
      const docRef = doc(db, 'tarefas', tarefaId);
      await updateDoc(docRef, {
        entregas_relacionadas: arrayRemove(entregaId)
      });
      showToast("Vínculo removido!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover vínculo.", "error");
    }
  };

  const handleCreateEntregaFromPlan = async (item: PlanoTrabalhoItem): Promise<string | null> => {
    try {
      const docRef = await addDoc(collection(db, 'atividades'), {
        entrega: item.entrega,
        area: item.unidade,
        descricao_trabalho: item.descricao || '',
        mes: currentMonth,
        ano: currentYear,
        status: 'planejada'
      });
      return docRef.id;
    } catch (e) {
      console.error(e);
      showToast("Erro ao registrar entrega.", "error");
      return null;
    }
  };

  const stats = useMemo(() => ({
    total: tarefas.length,
    emAndamento: tarefas.filter(t => normalizeStatus(t.status) === 'em andamento').length,
    concluidas: tarefas.filter(t => normalizeStatus(t.status) === 'concluido').length,
    clc: tarefas.filter(t => t.categoria === 'CLC' && normalizeStatus(t.status) !== 'concluido').length,
    assistencia: tarefas.filter(t => t.categoria === 'ASSISTÊNCIA' && normalizeStatus(t.status) !== 'concluido').length,
    geral: tarefas.filter(t => t.categoria === 'GERAL' && normalizeStatus(t.status) !== 'concluido').length,
    semTag: tarefas.filter(t => (t.categoria === 'NÃO CLASSIFICADA' || !t.categoria) && normalizeStatus(t.status) !== 'concluido' && t.status !== 'excluído' as any).length,
  }), [tarefas]);

  const prioridadesHoje = useMemo(() => {
    const now = new Date();
    const offset = now.getTimezoneOffset() * 60000;
    const localDate = new Date(now.getTime() - offset);
    const todayStr = localDate.toISOString().split('T')[0];

    return tarefas.filter(t => {
      if (normalizeStatus(t.status) === 'concluido' || t.status === 'excluído' as any) return false;
      if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") return false;
      return t.data_limite === todayStr;
    });
  }, [tarefas]);

  const filteredAndSortedTarefas = useMemo(() => {
    let result = [...tarefas];
    if (searchTerm) {
      const s = searchTerm.toLowerCase();
      if (s === 'filter:unclassified') {
        result = result.filter(t => (!t.categoria || t.categoria === 'NÃO CLASSIFICADA') && normalizeStatus(t.status) !== 'concluido');
      } else if (s === 'categoria:geral') {
        result = result.filter(t => t.categoria === 'GERAL');
      } else {
        result = result.filter(t => t.titulo?.toLowerCase().includes(s) || t.projeto?.toLowerCase().includes(s) || t.notas?.toLowerCase().includes(s));
      }
    }
    if (statusFilter.length > 0) {
      result = result.filter(t => statusFilter.some(sf => normalizeStatus(t.status) === normalizeStatus(sf)));
    }

    // Sempre remove excluídos
    result = result.filter(t => t.status !== 'excluído' as any);

    // Remove tarefas de Gasto Semanal (exclusivas do Financeiro)
    result = result.filter(t => !t.titulo.toLowerCase().includes('gasto semanal'));

    // Se estiver na visão Geral (que agora é a que mostra tudo ou sem categoria)
    // Se viewMode for gallery (Dashboard), ele mostra tudo filtrado por status.
    // Se criarmos uma visão específica para sem classificação, podemos filtrar aqui.
    if (viewMode === 'gallery' && searchTerm === 'filter:unclassified') {
      result = result.filter(t => (!t.categoria || t.categoria === 'NÃO CLASSIFICADA') && normalizeStatus(t.status) !== 'concluido');
    }

    result.sort((a, b) => {
      const dVal = (t: Tarefa) => (!t.data_limite || t.data_limite === "-" || t.data_limite.trim() === "") ? (sortOption === 'date-asc' ? Infinity : -Infinity) : new Date(t.data_limite).getTime();
      if (sortOption === 'date-asc') return dVal(a) - dVal(b);
      if (sortOption === 'date-desc') return dVal(b) - dVal(a);
      return 0;
    });
    return result;
  }, [tarefas, searchTerm, statusFilter, sortOption]);

  // Calcula tarefas não classificadas usando EXATAMENTE o mesmo filtro da exibição
  const unclassifiedTasksCount = useMemo(() => {
    return tarefas.filter(t =>
      (!t.categoria || t.categoria === 'NÃO CLASSIFICADA') &&
      normalizeStatus(t.status) !== 'concluido' &&
      t.status !== 'excluído' as any
    ).length;
  }, [tarefas]);

  const tarefasAgrupadas = useMemo<Record<string, Tarefa[]>>(() => {
    const groups: Record<string, Tarefa[]> = {};
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    const todayStr = now.toISOString().split('T')[0];
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];

    filteredAndSortedTarefas.forEach(t => {
      let label = "";
      if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") {
        label = "Sem Data";
      } else if (t.data_limite === todayStr) {
        label = "Hoje";
      } else if (t.data_limite === tomorrowStr) {
        label = "Amanhã";
      } else {
        const parts = t.data_limite.split('-');
        const date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
        const dayOfWeek = new Intl.DateTimeFormat('pt-BR', { weekday: 'long' }).format(date);
        const capitalizedDay = dayOfWeek.charAt(0).toUpperCase() + dayOfWeek.slice(1);
        label = `${parts[2]}/${parts[1]}/${parts[0]} - ${capitalizedDay}`;
      }

      if (!groups[label]) groups[label] = [];
      groups[label].push(t);
    });
    return groups;
  }, [filteredAndSortedTarefas]);

  useEffect(() => {
    if (!hasAutoExpanded && Object.keys(tarefasAgrupadas).length > 0) {
      setExpandedSections([Object.keys(tarefasAgrupadas)[0]]);
      setHasAutoExpanded(true);
    }
  }, [tarefasAgrupadas, hasAutoExpanded]);

  const toggleSection = (label: string) => {
    setExpandedSections(prev =>
      prev.includes(label) ? prev.filter(s => s !== label) : [...prev, label]
    );
  };

  // No PGC, filtramos as tarefas pelo período selecionado (mês/ano)
  // No PGC, filtramos as tarefas pelo período selecionado (mês/ano)
  const pgcTasks = useMemo<Tarefa[]>(() => {
    // Normalização agressiva para comparação de texto
    const norm = (val: any) => {
      if (!val) return "";
      return String(val).toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
    };

    return tarefas.filter(t => {
      if (t.status === 'excluído' as any) return false;

      const proj = norm(t.projeto);
      const cat = norm(t.categoria);

      // Identificadores das unidades PGD/PGC - Pelo PROJETO ou CATEGORIA
      const isCLC = proj.includes('CLC') || cat === 'CLC';
      const isASSIST = proj.includes('ASSIST') || proj.includes('ESTUDANTIL') || cat.includes('ASSISTENCIA');
      const isPgcUnit = isCLC || isASSIST;

      // Verifica se está vinculada a qualquer entrega institucional
      const linkedIds = Array.isArray(t.entregas_relacionadas) ? t.entregas_relacionadas.filter(id => !!id) : [];
      const isLinkedAtAll = linkedIds.length > 0;

      // Regra fundamental: Se não é unidade PGD e não foi vinculado manualmente, não entra no PGC
      if (!isPgcUnit && !isLinkedAtAll) return false;

      // Se estiver vinculado, aplicamos a regra de exibição temporal (mês atual)
      if (isLinkedAtAll) {
        if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") return true;
        const parts = t.data_limite.split(/[-/]/);
        if (parts.length < 3) return true;

        let taskYear = parseInt(parts[0]);
        let taskMonth = parseInt(parts[1]) - 1;

        if (taskYear < 1000) {
          taskYear = parseInt(parts[2]);
          taskMonth = parseInt(parts[1]) - 1;
        }

        return taskMonth === currentMonth && taskYear === currentYear;
      }

      // Se for unidade PGD mas ainda não vinculado, aparece no PGC (staging area)
      return isPgcUnit;
    });
  }, [tarefas, currentMonth, currentYear]);

  const pgcEntregas = useMemo<EntregaInstitucional[]>(() => entregas.filter(e => {
    return e.mes === currentMonth && e.ano === currentYear;
  }), [entregas, currentMonth, currentYear]);

  const pgcTasksAguardando = useMemo<Tarefa[]>(() => {
    const currentDeliveryIds = pgcEntregas.map(e => e.id);
    const norm = (val: any) => (val || '').toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();

    return pgcTasks.filter(t => {
      // Regra 1: Deve ser da categoria CLC ou ASSISTÊNCIA
      const isCLC = t.categoria === 'CLC' || (t.projeto && norm(t.projeto).includes('CLC'));
      const isAssist = t.categoria === 'ASSISTÊNCIA' || (t.projeto && (norm(t.projeto).includes('ASSIST') || norm(t.projeto).includes('ESTUDANTIL')));

      if (!isCLC && !isAssist) return false;

      // Regra 2: Verifica vínculos com entregas DO MÊS ATUAL
      const linkedIds = Array.isArray(t.entregas_relacionadas) ? t.entregas_relacionadas : [];
      const isLinkedToCurrent = linkedIds.some(id => currentDeliveryIds.includes(id));

      // Se JÁ estiver vinculado a uma entrega deste mês, não precisa aparecer na lista de "Aguardando"
      // POIS ela já aparecerá dentro do card da entrega correspondente.
      // Se estiver vinculado a entrega de OUTRO mês, deve aparecer aqui? 
      // O usuário disse: "todas as tarefas que tem a tag CLC ou a tag assistência estudantil devam constar nessa aba Audit PGC"
      // E "Se ela estiver vinculada a uma das atividades já cadastradas, ótimo, senão o sistema deve proporcionar uma forma inteligente de fazer essa vinculação."

      return !isLinkedToCurrent;
    });
  }, [pgcTasks, pgcEntregas]);

  const allUnidades = useMemo(() => {
    const fixed = ['CLC', 'Assistência Estudantil'];
    const dbUnidades = unidades.map(u => u.nome);
    return Array.from(new Set([...fixed, ...dbUnidades]));
  }, [unidades]);

  // Auditoria PGC - Heatmap de lacunas de registro
  const pgcAudit = useMemo(() => {
    const now = new Date();
    const workDays = getMonthWorkDays(currentYear, currentMonth);
    const gaps: Date[] = [];

    workDays.forEach(day => {
      // Ignorar dias futuros
      if (day > now) return;

      const dayStr = day.toISOString().split('T')[0];

      const hasActivity = atividadesPGC.some(a => {
        const start = a.data_inicio.split('T')[0];
        const end = a.data_fim?.split('T')[0] || start;
        return dayStr >= start && dayStr <= end;
      });

      const isAfastado = afastamentos.some(af => {
        const start = af.data_inicio.split('T')[0];
        const end = af.data_fim.split('T')[0];
        return dayStr >= start && dayStr <= end;
      });

      if (!hasActivity && !isAfastado) gaps.push(new Date(day));
    });

    return { gaps, totalWorkDays: workDays.length };
  }, [atividadesPGC, afastamentos]);

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col relative">

      {/* Menu Inicial (Home) */}
      {activeModule === 'home' && (
        <div className="min-h-screen flex flex-col items-center justify-center p-4 md:p-8">
          <div className="max-w-6xl w-full">
            {/* Logo e Título */}
            <div className="text-center mb-12 md:mb-16">
              <div className="flex items-center justify-center gap-4 mb-4">
                <img src="/logo.png" alt="Hermes" className="w-16 h-16 md:w-20 md:h-20 object-contain" />
                <h1 className="text-4xl md:text-6xl font-black tracking-tighter text-slate-900">HERMES</h1>
              </div>
              <p className="text-slate-500 text-sm md:text-base font-bold uppercase tracking-widest">Sistema de Gestão Integrada</p>
            </div>

            {/* Cards dos Módulos */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">

              {/* Card Ações */}
              <button
                onClick={() => setActiveModule('acoes')}
                className="group bg-white border-2 border-slate-200 rounded-[2.5rem] p-8 md:p-10 hover:border-blue-500 hover:shadow-2xl transition-all duration-300 active:scale-95 text-left relative overflow-hidden"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                <div className="relative z-10">
                  <div className="w-16 h-16 md:w-20 md:h-20 bg-blue-500 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300">
                    <svg className="w-8 h-8 md:w-10 md:h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                    </svg>
                  </div>
                  <h2 className="text-2xl md:text-3xl font-black text-slate-900 mb-3 group-hover:text-blue-600 transition-colors">Ações</h2>
                  <p className="text-slate-500 text-sm md:text-base font-medium leading-relaxed">Gestão de tarefas, CLC, Assistência Estudantil, PGC e Plano de Trabalho</p>
                  <div className="mt-6 flex items-center gap-2 text-blue-600 font-black text-xs uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                    <span>Acessar</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              </button>

              {/* Card Financeiro */}
              <button
                onClick={() => {
                  setActiveModule('financeiro');
                  setViewMode('finance');
                }}
                className="group bg-white border-2 border-slate-200 rounded-[2.5rem] p-8 md:p-10 hover:border-emerald-500 hover:shadow-2xl transition-all duration-300 active:scale-95 text-left relative overflow-hidden"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                <div className="relative z-10">
                  <div className="w-16 h-16 md:w-20 md:h-20 bg-emerald-500 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300">
                    <svg className="w-8 h-8 md:w-10 md:h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <h2 className="text-2xl md:text-3xl font-black text-slate-900 mb-3 group-hover:text-emerald-600 transition-colors">Financeiro</h2>
                  <p className="text-slate-500 text-sm md:text-base font-medium leading-relaxed">Gestão financeira e orçamentária</p>
                  <div className="mt-6 flex items-center gap-2 text-emerald-600 font-black text-xs uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                    <span>Acessar</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              </button>

              {/* Card Ferramentas */}
              <button
                onClick={() => {
                  setActiveModule('acoes');
                  setViewMode('ferramentas');
                  setActiveFerramenta(null);
                }}
                className="group bg-white border-2 border-slate-200 rounded-[2.5rem] p-8 md:p-10 hover:border-amber-500 hover:shadow-2xl transition-all duration-300 active:scale-95 text-left relative overflow-hidden"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                <div className="relative z-10">
                  <div className="w-16 h-16 md:w-20 md:h-20 bg-amber-500 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300">
                    <svg className="w-8 h-8 md:w-10 md:h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  </div>
                  <h2 className="text-2xl md:text-3xl font-black text-slate-900 mb-3 group-hover:text-amber-600 transition-colors">Ferramentas</h2>
                  <p className="text-slate-500 text-sm md:text-base font-medium leading-relaxed">Brainstorming, IA e outras ferramentas auxiliares</p>
                  <div className="mt-6 flex items-center gap-2 text-amber-600 font-black text-xs uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                    <span>Acessar</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              </button>

            </div>
          </div>
        </div>
      )}

      {/* Header e Conteúdo (apenas quando não está no home) */}
      {activeModule !== 'home' && (
        <>
          <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
            <div className="max-w-[1400px] mx-auto px-4 md:px-8 py-3 md:py-4">
              {/* Mobile Header */}
              <div className="flex md:hidden items-center justify-between">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setActiveModule('home')}
                    className="p-2 rounded-xl hover:bg-slate-100 transition-colors"
                    aria-label="Voltar ao Menu"
                  >
                    <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
                    </svg>
                  </button>
                  <img src="/logo.png" alt="Hermes" className="w-10 h-10 object-contain" />
                  <h1 className="text-lg font-black tracking-tighter text-slate-900">HERMES</h1>
                </div>
                <div className="flex items-center gap-2">
                  {/* Lógica de botões removida daqui para usar barra inferior */}
                  {viewMode !== 'ferramentas' && (
                    <button
                      onClick={() => setIsCreateModalOpen(true)}
                      className="bg-slate-900 text-white p-2.5 rounded-xl shadow-lg hover:bg-slate-800 transition-all active:scale-95"
                      aria-label="Criar Ação"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                    </button>
                  )}
                  <button
                    onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                    className="p-2.5 rounded-xl hover:bg-slate-100 transition-colors"
                    aria-label="Menu"
                  >
                    <svg className="w-6 h-6 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      {isMobileMenuOpen ? (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                      ) : (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" />
                      )}
                    </svg>
                  </button>
                </div>
              </div>

              {/* Desktop Header */}
              <div className="hidden md:flex items-center justify-between gap-4">
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setActiveModule('home')}
                      className="p-2 rounded-xl hover:bg-slate-100 transition-colors"
                      aria-label="Voltar ao Menu"
                    >
                      <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
                      </svg>
                    </button>
                    <img src="/logo.png" alt="Hermes" className="w-9 h-9 object-contain" />
                    <h1 className="text-xl font-black tracking-tighter text-slate-900">HERMES</h1>
                  </div>
                  {viewMode !== 'ferramentas' && activeModule !== 'financeiro' && (
                    <nav className="flex bg-slate-100 p-1 rounded-xl border border-slate-200">
                      <button
                        onClick={() => {
                          setViewMode('gallery');
                          setSearchTerm('');
                        }}
                        className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'gallery' && !searchTerm ? 'bg-white text-slate-900 shadow-sm border border-slate-100' : 'text-slate-500 hover:text-slate-800'}`}
                      >
                        Dashboard
                      </button>
                      {unclassifiedTasksCount > 0 && (
                        <button
                          onClick={() => {
                            setViewMode('gallery');
                            setSearchTerm(searchTerm === 'filter:unclassified' ? '' : 'filter:unclassified');
                          }}
                          className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${searchTerm === 'filter:unclassified' ? 'bg-rose-600 text-white shadow-lg' : 'text-slate-500 hover:text-slate-800'}`}
                        >
                          Não Classificadas
                        </button>
                      )}
                      <button onClick={() => setViewMode('licitacoes')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'licitacoes' ? 'bg-slate-900 text-white shadow-lg' : 'text-slate-500 hover:text-slate-800'}`}>CLC</button>
                      <button onClick={() => setViewMode('assistencia')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'assistencia' ? 'bg-slate-900 text-white shadow-lg' : 'text-slate-500 hover:text-slate-800'}`}>AE</button>
                      <button onClick={() => setViewMode('pgc')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'pgc' ? 'bg-slate-900 text-white shadow-lg' : 'text-slate-500 hover:text-slate-800'}`}>Audit PGC</button>
                      <button onClick={() => setViewMode('plano-trabalho')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'plano-trabalho' ? 'bg-slate-900 text-white shadow-lg' : 'text-slate-500 hover:text-slate-800'}`}>Plano</button>
                    </nav>
                  )}
                </div>

                {viewMode !== 'ferramentas' && (
                  <div className="flex items-center gap-4">
                    <div className="hidden lg:flex items-center bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 w-64 group focus-within:ring-2 focus-within:ring-blue-500 focus-within:bg-white transition-all">
                      <svg className="w-4 h-4 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                      <input type="text" placeholder="Pesquisar..." className="bg-transparent border-none outline-none text-xs font-bold text-slate-900 w-full" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
                    </div>
                    <button
                      onClick={handleSync}
                      className={`bg-white border border-slate-200 text-slate-700 px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-3 shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative`}
                    >
                      <svg className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                      {isSyncing ? 'Monitorar Sync' : 'Sync Google'}
                      {isSyncing && <span className="absolute -top-1 -right-1 w-3 h-3 bg-blue-500 rounded-full animate-ping"></span>}
                    </button>
                    <button
                      onClick={() => setIsCreateModalOpen(true)}
                      className="bg-slate-900 text-white px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 shadow-lg hover:bg-slate-800 transition-all active:scale-95"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                      Criar Ação
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Mobile Menu Drawer */}
            {isMobileMenuOpen && (
              <div className="md:hidden border-t border-slate-200 bg-white">
                <nav className="flex flex-col p-4 space-y-2">
                  {viewMode !== 'ferramentas' && (
                    <>
                      <button
                        onClick={() => {
                          setViewMode('gallery');
                          setSearchTerm('');
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left ${viewMode === 'gallery' && !searchTerm ? 'bg-slate-900 text-white' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`}
                      >
                        📊 Dashboard
                      </button>
                      {unclassifiedTasksCount > 0 && (
                        <button
                          onClick={() => {
                            setViewMode('gallery');
                            setSearchTerm('filter:unclassified');
                            setIsMobileMenuOpen(false);
                          }}
                          className={`px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left ${searchTerm === 'filter:unclassified' ? 'bg-rose-600 text-white' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`}
                        >
                          ⚠️ Não Classificadas
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setViewMode('licitacoes');
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left ${viewMode === 'licitacoes' ? 'bg-slate-900 text-white' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`}
                      >
                        📋 CLC
                      </button>
                      <button
                        onClick={() => {
                          setViewMode('assistencia');
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left ${viewMode === 'assistencia' ? 'bg-slate-900 text-white' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`}
                      >
                        🎓 Assistência Estudantil
                      </button>
                      <button
                        onClick={() => {
                          setViewMode('pgc');
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left ${viewMode === 'pgc' ? 'bg-slate-900 text-white' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`}
                      >
                        📈 Audit PGC
                      </button>
                      <button
                        onClick={() => {
                          setViewMode('plano-trabalho');
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left ${viewMode === 'plano-trabalho' ? 'bg-slate-900 text-white' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`}
                      >
                        📅 Plano de Trabalho
                      </button>
                    </>
                  )}

                  <div className="pt-4 border-t border-slate-200 mt-2">
                    <button
                      onClick={() => {
                        handleSync();
                        setIsMobileMenuOpen(false);
                      }}
                      className={`w-full px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left bg-blue-50 text-blue-700 hover:bg-blue-100 relative`}
                    >
                      🔄 {isSyncing ? 'Monitorar Sincronização...' : 'Sync Google'}
                      {isSyncing && <span className="absolute top-4 right-4 w-2 h-2 bg-blue-500 rounded-full animate-ping"></span>}
                    </button>
                  </div>
                </nav>
              </div>
            )}
          </header>

          <div className="max-w-[1400px] mx-auto w-full px-0 md:px-8 py-6">
            {/* Painel de Estatísticas e Filtros - APENAS NA VISÃO GERAL */}
            <main className="mb-20">
              {viewMode === 'gallery' ? (
                <>
                  <div className="flex flex-col md:flex-row items-center justify-between mb-8 gap-4 px-4 md:px-0">
                    {/* Layout & Sort Controls */}
                    <div className="flex items-center gap-4">
                      {searchTerm !== 'filter:unclassified' && (
                        <div className="bg-white p-0.5 md:p-1 rounded-xl border border-slate-200 inline-flex shadow-sm">
                          <button
                            onClick={() => setDashboardViewMode('list')}
                            className={`px-3 md:px-4 py-2 rounded-lg text-[9px] md:text-[10px] font-black uppercase tracking-wide md:tracking-widest transition-all flex items-center gap-1.5 md:gap-2 ${dashboardViewMode === 'list' ? 'bg-slate-900 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                          >
                            <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
                            <span className="hidden sm:inline">Lista</span>
                          </button>
                          <button
                            onClick={() => setDashboardViewMode('calendar')}
                            className={`px-3 md:px-4 py-2 rounded-lg text-[9px] md:text-[10px] font-black uppercase tracking-wide md:tracking-widest transition-all flex items-center gap-1.5 md:gap-2 ${dashboardViewMode === 'calendar' ? 'bg-slate-900 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                          >
                            <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                            <span className="hidden sm:inline">Calendário</span>
                          </button>
                        </div>
                      )}

                      <div className="bg-white p-0.5 md:p-1 rounded-xl border border-slate-200 inline-flex shadow-sm">
                        <button
                          onClick={() => setSortOption('date-asc')}
                          className={`px-3 md:px-4 py-2 rounded-lg text-[9px] md:text-[10px] font-black uppercase tracking-wide md:tracking-widest transition-all ${sortOption === 'date-asc' ? 'bg-slate-100 text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Antigas
                        </button>
                        <button
                          onClick={() => setSortOption('date-desc')}
                          className={`px-3 md:px-4 py-2 rounded-lg text-[9px] md:text-[10px] font-black uppercase tracking-wide md:tracking-widest transition-all ${sortOption === 'date-desc' ? 'bg-slate-100 text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Recentes
                        </button>
                      </div>
                    </div>
                  </div>

                  {dashboardViewMode === 'calendar' ? (
                    <CalendarView
                      tasks={filteredAndSortedTarefas}
                      viewMode={calendarViewMode}
                      currentDate={calendarDate}
                      onDateChange={setCalendarDate}
                      onTaskClick={setSelectedTask}
                      onViewModeChange={setCalendarViewMode}
                    />
                  ) : (
                    <>
                      {searchTerm === 'filter:unclassified' ? (
                        <div className="animate-in bg-white border border-slate-200 rounded-[2rem] overflow-hidden shadow-2xl">
                          <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex flex-col md:flex-row md:items-center justify-between gap-4">
                            <h3 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                              <span className="w-2 h-8 bg-rose-600 rounded-full"></span>
                              Organização Rápida
                            </h3>

                            {selectedTaskIds.length > 0 && (
                              <div className="flex items-center gap-2 bg-slate-900 p-2 rounded-2xl animate-in slide-in-from-top-4">
                                <span className="text-[9px] font-black text-white uppercase tracking-widest px-4">Classificar ({selectedTaskIds.length}):</span>
                                <button onClick={() => handleBatchTag('CLC')} className="bg-blue-600 hover:bg-blue-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-xl transition-all">CLC</button>
                                <button onClick={() => handleBatchTag('ASSISTÊNCIA')} className="bg-emerald-600 hover:bg-emerald-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-xl transition-all">Assistência</button>
                                <button onClick={() => handleBatchTag('GERAL')} className="bg-slate-500 hover:bg-slate-600 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-xl transition-all">Geral</button>
                              </div>
                            )}
                          </div>

                          <div className="overflow-x-auto">
                            <table className="w-full text-left">
                              <thead className="bg-slate-50 border-b border-slate-200">
                                <tr>
                                  <th className="px-8 py-4 w-12 text-center text-[10px] font-black text-slate-400 uppercase tracking-widest italic">#</th>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Descrição da Tarefa</th>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-40 text-center">Data Limite</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-50">
                                {filteredAndSortedTarefas.map((task) => (
                                  <tr
                                    key={task.id}
                                    onClick={() => setSelectedTask(task)}
                                    className={`hover:bg-slate-50 transition-colors cursor-pointer ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}
                                  >
                                    <td className="px-8 py-4 text-center">
                                      <input
                                        type="checkbox"
                                        checked={selectedTaskIds.includes(task.id)}
                                        onChange={(e) => {
                                          e.stopPropagation();
                                          setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id]);
                                        }}
                                        className="w-5 h-5 rounded-lg border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
                                      />
                                    </td>
                                    <td className="px-8 py-4">
                                      <div className="text-[13px] font-bold text-slate-800 hover:text-blue-600 transition-colors leading-snug">
                                        {task.titulo}
                                      </div>
                                    </td>
                                    <td className="px-8 py-4 text-center text-[10px] font-black text-slate-400 uppercase">
                                      {formatDate(task.data_limite)}
                                    </td>
                                  </tr>
                                ))}
                                {filteredAndSortedTarefas.length === 0 && (
                                  <tr>
                                    <td colSpan={3} className="py-20 text-center text-slate-300 font-black uppercase tracking-widest italic">Tudo classificado! Bom trabalho.</td>
                                  </tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                        </div>

                      ) : (
                        <div className="animate-in border border-slate-200 overflow-hidden shadow-2xl bg-white">
                          {Object.keys(tarefasAgrupadas).length > 0 ? (
                            Object.entries(tarefasAgrupadas).map(([label, tasks]: [string, Tarefa[]]) => (
                              <div key={label} className="border-b last:border-b-0 border-slate-200">
                                <button
                                  onClick={() => toggleSection(label)}
                                  className="w-full px-8 py-5 bg-slate-50 border-b border-slate-200 flex items-center justify-between hover:bg-slate-100 transition-colors group"
                                >
                                  <div className="flex items-center gap-4">
                                    <div className={`w-2 h-8 rounded-full ${label === 'Hoje' ? 'bg-blue-600' : 'bg-slate-300'}`}></div>
                                    <span className="text-sm font-black text-slate-900 uppercase tracking-[0.2em]">{label}</span>
                                    <span className="bg-white border border-slate-200 text-[10px] font-black px-2 py-0.5 rounded-md text-slate-500">{tasks.length}</span>
                                  </div>
                                  <svg className={`w-5 h-5 text-slate-400 transition-transform duration-300 ${expandedSections.includes(label) ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
                                  </svg>
                                </button>

                                {expandedSections.includes(label) && (
                                  <div className="animate-in origin-top">
                                    {tasks.map(task => (
                                      <RowCard
                                        key={task.id}
                                        task={task}
                                        onClick={() => setSelectedTask(task)}
                                        onToggle={handleToggleTarefaStatus}
                                        onDelete={handleDeleteTarefa}
                                      />
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))
                          ) : (
                            <div className="py-24 text-center bg-white">
                              <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Sem demandas encontradas</p>
                            </div>
                          )}
                        </div>
                      )}

                      <div className="mt-12 space-y-6">
                        <button
                          onClick={() => setIsCompletedTasksOpen(!isCompletedTasksOpen)}
                          className="w-full flex items-center gap-4 group cursor-pointer"
                        >
                          <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
                          <div className="flex items-center gap-2 text-slate-400 group-hover:text-slate-600 transition-colors">
                            <h3 className="text-[10px] font-black uppercase tracking-[0.3em]">Concluídas Recentemente</h3>
                            <svg className={`w-4 h-4 transition-transform duration-300 ${isCompletedTasksOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                            </svg>
                          </div>
                          <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
                        </button>

                        {isCompletedTasksOpen && (
                          <div className="bg-white border border-slate-200 rounded-[2rem] overflow-hidden shadow-sm opacity-60 hover:opacity-100 transition-opacity animate-in slide-in-from-top-4 duration-300">
                            {tarefas.filter(t => normalizeStatus(t.status) === 'concluido' && t.status !== 'excluído' as any).length > 0 ? (
                              tarefas
                                .filter(t => normalizeStatus(t.status) === 'concluido' && t.status !== 'excluído' as any)
                                .sort((a, b) => (b.data_conclusao || '').localeCompare(a.data_conclusao || ''))
                                .slice(0, 10)
                                .map(t => (
                                  <RowCard
                                    key={t.id}
                                    task={t}
                                    onClick={() => setSelectedTask(t)}
                                    onToggle={handleToggleTarefaStatus}
                                    onDelete={handleDeleteTarefa}
                                  />
                                ))
                            ) : (
                              <div className="py-12 text-center">
                                <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhuma tarefa concluída</p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </>
              ) : (viewMode === 'licitacoes' || viewMode === 'assistencia') ? (
                <CategoryView tasks={tarefas} viewMode={viewMode} onSelectTask={setSelectedTask} />
              ) : viewMode === 'sistemas' ? (
                <div className="animate-in space-y-8">
                  <div className="bg-white p-8 rounded-[2rem] border border-slate-200 shadow-xl">
                    <h3 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                      <span className="w-2 h-8 bg-amber-500 rounded-full"></span>
                      Desenvolvimento de Sistemas
                    </h3>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {(sistemasAtivos.length > 0
                      ? sistemasAtivos
                      : Array.from(new Set(tarefas.filter(t => t.categoria === 'SISTEMAS').map(t => t.sistema || 'OUTROS')))
                    ).map(sistema => (
                      <div key={sistema} className="bg-white border border-slate-200 rounded-[2rem] overflow-hidden shadow-lg flex flex-col">
                        <div className="p-6 bg-slate-900 text-white flex justify-between items-center">
                          <h4 className="text-xs font-black uppercase tracking-[0.2em]">{sistema}</h4>
                          <span className="bg-white/20 px-3 py-1 rounded-full text-[10px] font-black">{tarefas.filter(t => t.categoria === 'SISTEMAS' && (t.sistema || 'OUTROS') === sistema).length}</span>
                        </div>
                        <div className="p-6 space-y-4 flex-1 bg-slate-50/50">
                          {tarefas.filter(t => t.categoria === 'SISTEMAS' && (t.sistema || 'OUTROS') === sistema).map(t => (
                            <div key={t.id} className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm hover:border-amber-400 transition-all cursor-pointer" onClick={() => setSelectedTask(t)}>
                              <div className={`text-[8px] font-black mb-1.5 uppercase ${STATUS_COLORS[normalizeStatus(t.status)] || ''} border-none p-0 bg-transparent`}>
                                {t.status}
                              </div>
                              <div className="text-[11px] font-bold text-slate-700 leading-tight">{t.titulo}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : viewMode === 'plano-trabalho' ? (
                <div className="animate-in space-y-8">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 bg-white p-8 rounded-[2rem] border border-slate-200 shadow-xl">
                    <div>
                      <h3 className="text-2xl font-black text-slate-900 tracking-tight">Plano de Trabalho Mensal</h3>
                      <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">Acompanhamento de entregas vs execução real</p>
                    </div>
                    <div className="flex items-center gap-4">
                      <select
                        value={currentMonth}
                        onChange={(e) => setCurrentMonth(Number(e.target.value))}
                        className="text-[10px] font-black uppercase bg-slate-100 px-4 py-2 rounded-xl border-none outline-none focus:ring-2 focus:ring-slate-900"
                      >
                        {['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'].map((m, i) => (
                          <option key={i} value={i}>{m}</option>
                        ))}
                      </select>
                      <button
                        onClick={() => setIsImportPlanOpen(true)}
                        className="bg-slate-900 text-white px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center gap-3"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        Importar Plano Mensal
                      </button>
                    </div>
                  </div>
                  <div className="bg-white border border-slate-200 rounded-[2rem] overflow-hidden shadow-2xl overflow-x-auto">
                    <table className="w-full text-left min-w-[800px]">
                      <thead className="bg-slate-50 border-b border-slate-200">
                        <tr>
                          <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Origem / Unidade</th>
                          <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Entrega Institucional</th>
                          <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Descrição</th>
                          <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-[200px]">% Carga Horária</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)?.itens.map((item, i) => (
                          <tr key={i} className="hover:bg-slate-50 transition-colors">
                            <td className="px-8 py-6">
                              <div className="text-[10px] font-black text-slate-400 uppercase mb-1">{item.origem}</div>
                              <div className="text-xs font-black text-slate-900">{item.unidade}</div>
                            </td>
                            <td className="px-8 py-6 text-sm font-black text-slate-900">{item.entrega}</td>
                            <td className="px-8 py-6 text-xs font-medium text-slate-600 leading-relaxed max-w-xs">{item.descricao}</td>
                            <td className="px-8 py-6">
                              <div className="flex items-center gap-4">
                                <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                                  <div className="h-full bg-indigo-500 rounded-full transition-all duration-1000" style={{ width: `${item.percentual}%` }}></div>
                                </div>
                                <span className="text-[10px] font-black text-slate-900 w-10">{item.percentual}%</span>
                              </div>
                            </td>
                          </tr>
                        ))}
                        {(!planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)) && (
                          <tr>
                            <td colSpan={4} className="px-8 py-20 text-center">
                              <p className="text-slate-300 font-black text-sm uppercase tracking-widest italic">Nenhum plano de trabalho configurado para este período.</p>
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : viewMode === 'ferramentas' ? (
                <FerramentasView
                  ideas={brainstormIdeas}
                  onAudioReady={handleAudioReady}
                  onDeleteIdea={handleDeleteIdea}
                  onArchiveIdea={handleArchiveIdea}
                  onAddTextIdea={handleAddTextIdea}
                  onUpdateIdea={handleUpdateIdea}
                  isProcessing={isProcessingIdea}
                  activeTool={activeFerramenta}
                  setActiveTool={setActiveFerramenta}
                  isAddingText={isBrainstormingAddingText}
                  setIsAddingText={setIsBrainstormingAddingText}
                />
              ) : viewMode === 'finance' ? (
                <FinanceView
                  transactions={financeTransactions}
                  goals={financeGoals}
                  settings={financeSettings}
                  currentMonthTotal={financeTransactions.filter(t => new Date(t.date).getMonth() === new Date().getMonth()).reduce((acc, curr) => acc + curr.amount, 0)}
                  fixedBills={fixedBills}
                  onUpdateSettings={(newSettings) => setDoc(doc(db, 'finance_settings', 'config'), newSettings)}
                  onAddGoal={(goal) => addDoc(collection(db, 'finance_goals'), goal)}
                  onUpdateGoal={(goal) => updateDoc(doc(db, 'finance_goals', goal.id), goal as any)}
                  onAddBill={async (bill) => { await addDoc(collection(db, 'fixed_bills'), bill); }}
                  onUpdateBill={async (bill) => { await updateDoc(doc(db, 'fixed_bills', bill.id), bill as any); }}
                  onDeleteBill={async (id) => { await deleteDoc(doc(db, 'fixed_bills', id)); }}
                />
              ) : (
                <div className="space-y-10">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 bg-white p-8 rounded-[2rem] border border-slate-200 shadow-xl">
                    <div>
                      <h3 className="text-4xl font-black text-slate-900 tracking-tighter">Gestão PGC</h3>
                      <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">{new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}</p>
                    </div>
                    <div className="flex items-center gap-4">
                      <select
                        value={currentMonth}
                        onChange={(e) => setCurrentMonth(Number(e.target.value))}
                        className="text-[10px] font-black uppercase bg-slate-100 px-4 py-2 rounded-xl border-none outline-none focus:ring-2 focus:ring-slate-900"
                      >
                        {['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'].map((m, i) => (
                          <option key={i} value={i}>{m}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="flex border-b border-slate-200">
                    <button
                      onClick={() => setPgcSubView('audit')}
                      className={`px-8 py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 ${pgcSubView === 'audit' ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                    >
                      Resumo de Atividades
                    </button>
                  </div>

                  {pgcSubView === 'audit' && (
                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-220px)] pb-4">
                      <div className="lg:col-span-3 bg-white rounded-[2rem] border border-slate-200 shadow-xl flex flex-col overflow-hidden h-full">
                        <div className="p-6 border-b border-slate-100 flex-shrink-0 bg-slate-50/50">
                          <div className="flex items-center justify-between">
                            <h4 className="text-sm font-black text-slate-900 tracking-tight">Pendentes</h4>
                            <span className="bg-slate-900 text-white text-[9px] font-black px-2 py-1 rounded-full">{pgcTasksAguardando.length}</span>
                          </div>
                          <p className="text-slate-400 text-[9px] font-black uppercase tracking-widest mt-1">Arraste p/ vincular</p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                          {pgcTasksAguardando.map(task => (
                            <PgcMiniTaskCard key={task.id} task={task} onClick={() => setSelectedTask(task)} />
                          ))}
                          {pgcTasksAguardando.length === 0 && (
                            <div className="py-10 text-center">
                              <p className="text-slate-300 font-black text-[9px] uppercase tracking-widest italic">Tudo limpo!</p>
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="lg:col-span-9 bg-white rounded-[2rem] border border-slate-200 overflow-hidden shadow-xl flex flex-col h-full">
                        <div className="flex-1 overflow-y-auto divide-y divide-slate-100 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                          {(() => {
                            const currentPlan = planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`);

                            if (!currentPlan) return <div className="p-12 text-center h-full flex items-center justify-center"><p className="text-slate-300 font-black text-sm uppercase tracking-widest italic">Nenhum plano definido.</p></div>;

                            return currentPlan.itens.map((item, index) => {
                              const entregaEntity = pgcEntregas.find(e => e.entrega === item.entrega);
                              const entregaId = entregaEntity?.id;

                              const atividadesRelacionadas: AtividadeRealizada[] = entregaId ? atividadesPGC.filter(a => a.entrega_id === entregaId) : [];
                              const tarefasRelacionadas: Tarefa[] = entregaId ? pgcTasks.filter(t => t.entregas_relacionadas?.includes(entregaId)) : [];

                              return (
                                <div
                                  key={index}
                                  onDragOver={(e) => {
                                    e.preventDefault();
                                    e.dataTransfer.dropEffect = 'copy';
                                    e.currentTarget.classList.add('bg-blue-50');
                                  }}
                                  onDragLeave={(e) => {
                                    e.currentTarget.classList.remove('bg-blue-50');
                                  }}
                                  onDrop={async (e) => {
                                    e.preventDefault();
                                    e.currentTarget.classList.remove('bg-blue-50');
                                    const tarefaId = e.dataTransfer.getData('tarefaId');
                                    if (tarefaId) {
                                      let targetId = entregaId;
                                      if (!targetId) {
                                        const newId = await handleCreateEntregaFromPlan(item);
                                        if (newId) targetId = newId;
                                      }
                                      if (targetId) handleLinkTarefa(tarefaId, targetId);
                                    }
                                  }}
                                  className={`group flex flex-col md:flex-row hover:bg-slate-50 transition-all border-l-4 border-transparent hover:border-blue-500`}
                                >
                                  <div className="md:w-1/2 p-6 border-b md:border-b-0 md:border-r border-slate-100 bg-slate-50/30">
                                    <div className="flex flex-col gap-1 mb-3">
                                      <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{item.origem}</span>
                                      <div className="flex items-center gap-3">
                                        <span className="text-xs font-black text-blue-600 uppercase tracking-tight">{item.unidade}</span>
                                        {entregaEntity?.processo_sei && <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest font-mono border border-slate-200 px-1.5 rounded">SEI: {entregaEntity.processo_sei}</span>}
                                      </div>
                                    </div>

                                    <h4 className="text-sm font-black text-slate-900 tracking-tight leading-snug group-hover:text-blue-700 transition-all">{item.entrega}</h4>

                                    {item.descricao && (
                                      <p className="mt-2 text-[10px] font-medium text-slate-500 italic leading-relaxed line-clamp-3 bg-white p-2 rounded-lg border border-slate-100 shadow-sm">
                                        {item.descricao}
                                      </p>
                                    )}

                                    <div className="flex items-center gap-2 mt-4 text-[10px] font-black text-slate-500">
                                      <div className="w-1.5 h-1.5 bg-blue-500 rounded-full"></div>
                                      {atividadesRelacionadas.length + tarefasRelacionadas.length} Registros
                                    </div>
                                  </div>
                                  <div className="flex-1 p-6">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                      {atividadesRelacionadas.map(at => (
                                        <div key={at.id} className="p-3 rounded-xl bg-slate-50 border border-slate-100 hover:border-slate-200 transition-all">
                                          <p className="text-[8px] font-black text-slate-400 uppercase mb-1">{formatDate(at.data_inicio)}</p>
                                          <p className="text-[11px] font-bold text-slate-700 leading-tight">{at.descricao_atividade}</p>
                                        </div>
                                      ))}
                                      {tarefasRelacionadas.map(t => (
                                        <div
                                          key={t.id}
                                          className="p-3 rounded-xl bg-blue-50/20 border border-blue-100 hover:border-blue-300 hover:bg-blue-50/40 transition-all cursor-default group/task relative pr-8"
                                        >
                                          <button
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              if (entregaId) handleUnlinkTarefa(t.id, entregaId);
                                            }}
                                            className="absolute top-2 right-2 p-1 text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-full opacity-0 group-hover/task:opacity-100 transition-all"
                                            title="Desvincular"
                                          >
                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                                          </button>
                                          <div className="flex items-center justify-between mb-1">
                                            <p className="text-[8px] font-black text-blue-400 uppercase">Tarefa Geral</p>
                                            <p className="text-[8px] font-black text-slate-400 uppercase">{formatDate(t.data_limite)}</p>
                                          </div>
                                          <p className="text-[11px] font-bold text-slate-700 leading-tight group-hover/task:text-blue-700">{t.titulo}</p>
                                        </div>
                                      ))}
                                      {atividadesRelacionadas.length === 0 && tarefasRelacionadas.length === 0 && (
                                        <div className="col-span-full py-4">
                                          <p className="text-slate-300 text-[8px] font-black uppercase tracking-widest italic">Aguardando registros...</p>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              );
                            });
                          })()}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </main>

            <ToastContainer toasts={toasts} removeToast={removeToast} />

            {
              isCreateModalOpen && (
                <TaskCreateModal
                  onSave={handleCreateTarefa}
                  onClose={() => setIsCreateModalOpen(false)}
                />
              )
            }

            {
              selectedTask && (
                selectedTask.categoria === 'CLC' ? (
                  <TaskExecutionView
                    task={selectedTask}
                    onSave={handleUpdateTarefa}
                    onClose={() => setSelectedTask(null)}
                  />
                ) : (
                  <TaskEditModal
                    task={selectedTask}
                    onSave={handleUpdateTarefa}
                    onDelete={handleDeleteTarefa}
                    onClose={() => setSelectedTask(null)}
                  />
                )
              )
            }

            {
              isTerminalOpen && (
                <div className="fixed inset-0 z-[150] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-md animate-in fade-in duration-300">
                  <div className="bg-[#0C0C0C] w-full max-w-2xl rounded-[2rem] shadow-[0_0_100px_rgba(37,99,235,0.2)] border border-white/10 overflow-hidden flex flex-col h-[500px] animate-in zoom-in-95">
                    <div className="p-6 bg-white/5 border-b border-white/5 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex gap-1.5">
                          <div className="w-3 h-3 rounded-full bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.5)]"></div>
                          <div className="w-3 h-3 rounded-full bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]"></div>
                          <div className="w-3 h-3 rounded-full bg-emerald-500 shadow-[0_0_100px_rgba(16,185,129,0.5)]"></div>
                        </div>
                        <h3 className="text-[10px] font-black text-white/40 uppercase tracking-[0.3em] ml-2">Google Sync Console v2</h3>
                      </div>
                      <div className="flex items-center gap-4">
                        {isSyncing && (
                          <button
                            onClick={async () => {
                              await setDoc(doc(db, 'system', 'sync'), { status: 'idle', logs: [...(syncData?.logs || []), "--- INTERROMPIDO PELO USUÁRIO ---"] });
                              setIsSyncing(false);
                            }}
                            className="text-[9px] font-bold text-rose-500/60 hover:text-rose-400 bg-rose-500/10 border border-rose-500/20 px-3 py-1 rounded-full transition-all"
                          >
                            FORÇAR INTERRUPÇÃO
                          </button>
                        )}
                        <button onClick={() => setIsTerminalOpen(false)} className="text-white/40 hover:text-white transition-colors">
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </div>
                    </div>

                    <div className="flex-1 overflow-y-auto p-6 font-mono text-[11px] space-y-2 selection:bg-blue-500/30">
                      <div className="text-blue-400 opacity-60"># hermes_cli.py --sync-mode automatic</div>
                      {syncData?.logs?.map((log: string, i: number) => (
                        <div key={i} className={`flex gap-3 ${log.includes('ERRO') ? 'text-rose-400' : log.includes('PUSH') ? 'text-blue-400' : log.includes('PULL') ? 'text-emerald-400' : 'text-slate-400'}`}>
                          <span className="opacity-30 shrink-0">[{i}]</span>
                          <span className="leading-relaxed">{log}</span>
                        </div>
                      ))}
                      {isSyncing && (
                        <div className="flex items-center gap-2 text-white/50 animate-pulse">
                          <span className="w-1.5 h-1.5 bg-blue-500 rounded-full"></span>
                          <span>Processando transações em tempo real...</span>
                        </div>
                      )}
                      {!isSyncing && syncData?.status === 'completed' && (
                        <div className="pt-4 border-t border-white/5 text-emerald-400 font-bold">
                          ✓ SINCROIZAÇÃO CONCLUÍDA COM SUCESSO.
                        </div>
                      )}
                      {syncData?.status === 'error' && (
                        <div className="pt-4 border-t border-white/5 text-rose-500 font-bold">
                          ⚠ FALHA NO PROCESSAMENTO: {syncData.error_message}
                        </div>
                      )}
                    </div>

                    <div className="p-4 bg-white/5 text-[9px] font-bold text-white/20 uppercase tracking-widest flex justify-between items-center">
                      <span>Core: Firebase Firestore + Google Tasks API</span>
                      <span>Encerrado: {syncData?.last_success ? formatDate(syncData.last_success.split('T')[0]) : '-'}</span>
                    </div>
                  </div>
                </div>
              )
            }

            {
              isImportPlanOpen && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
                  <div className="bg-white w-full max-w-2xl rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
                    <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
                      <div>
                        <h3 className="text-2xl font-black text-slate-900 tracking-tight">Importar Plano Mensal</h3>
                        <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">Cole o JSON do plano de trabalho abaixo</p>
                      </div>
                      <button onClick={() => setIsImportPlanOpen(false)} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
                        <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    </div>

                    <div className="p-8 space-y-6">
                      <div className="grid grid-cols-2 gap-6">
                        <div className="space-y-2">
                          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Ano</label>
                          <input type="number" id="import-year" defaultValue={currentYear} className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900" />
                        </div>
                        <div className="space-y-2">
                          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Mês</label>
                          <select id="import-month" defaultValue={currentMonth + 1} className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900">
                            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(m => <option key={m} value={m}>{m}</option>)}
                          </select>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Dump JSON</label>
                        <textarea
                          id="import-json"
                          rows={10}
                          className="w-full bg-slate-900 text-blue-400 border-none rounded-2xl px-6 py-4 text-[10px] font-mono focus:ring-2 focus:ring-blue-500 transition-all resize-none"
                          placeholder='[ { "entrega": "Exemplo", "percentual": 50 }, ... ]'
                        />
                      </div>
                    </div>

                    <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4">
                      <button
                        onClick={() => setIsImportPlanOpen(false)}
                        className="flex-1 px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all"
                      >
                        Cancelar
                      </button>
                      <button
                        onClick={async () => {
                          try {
                            const year = (document.getElementById('import-year') as HTMLInputElement).value;
                            const month = (document.getElementById('import-month') as HTMLSelectElement).value.padStart(2, '0');
                            const rawText = (document.getElementById('import-json') as HTMLTextAreaElement).value;

                            let items: PlanoTrabalhoItem[] = [];

                            // Tenta detectar se é JSON ou o formato de texto/tabela
                            if (rawText.trim().startsWith('[') || rawText.trim().startsWith('{')) {
                              items = JSON.parse(rawText);
                            } else {
                              // Parser para o formato de tabela de texto
                              const lines = rawText.split('\n').map(l => l.trim()).filter(l => l !== '');
                              for (let i = 0; i < lines.length; i++) {
                                const line = lines[i];
                                if (line === 'Própria Unidade' || line === 'Outra Unidade') {
                                  const item: Partial<PlanoTrabalhoItem> = { origem: line };
                                  item.unidade = lines[++i] || '';
                                  item.entrega = lines[++i] || '';
                                  // Opcional: pular "Curtir"
                                  if (lines[i + 1] === 'Curtir') i++;
                                  const pctStr = lines[++i] || '0';
                                  item.percentual = parseFloat(pctStr.replace('%', '')) || 0;
                                  item.descricao = lines[++i] || '';
                                  items.push(item as PlanoTrabalhoItem);
                                }
                              }
                            }

                            if (items.length === 0) throw new Error("Nenhum item identificado no texto colado.");

                            const docId = `${year}-${month}`;
                            await setDoc(doc(db, 'planos_trabalho', docId), {
                              mes_ano: docId,
                              itens: items,
                              data_atualizacao: new Date().toISOString()
                            });

                            setIsImportPlanOpen(false);
                            alert(`Sucesso! ${items.length} entregas importadas para o plano ${docId}.`);
                          } catch (err: any) {
                            alert("Erro ao processar dados: " + err.message);
                          }
                        }}
                        className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
                      >
                        Processar e Gravar
                      </button>
                    </div>
                  </div>
                </div>
              )
            }
          </div>
        </>
      )}
    </div>
  );
};

const container = document.getElementById('root');
if (container) {
  const root = createRoot(container);
  root.render(<App />);
}

