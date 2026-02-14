
import React, { useState, useEffect, useMemo } from 'react';
import { createRoot } from 'react-dom/client';
import { Tarefa, Status, EntregaInstitucional, Prioridade, AtividadeRealizada, Afastamento, PlanoTrabalho, PlanoTrabalhoItem, Categoria, Acompanhamento } from './types';
import { STATUS_COLORS, PROJECT_COLORS } from './constants';
import { db } from './firebase';
import { collection, onSnapshot, query, updateDoc, doc, addDoc, deleteDoc, setDoc, arrayUnion, arrayRemove } from 'firebase/firestore';


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
      const startStr = t.data_criacao ? t.data_criacao.split('T')[0] : endStr;

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
                  const startStr = t.data_criacao ? t.data_criacao.split('T')[0] : (t.data_limite || '');
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

const RowCard = React.memo(({ task, onClick, onToggle }: { task: Tarefa, onClick?: () => void, onToggle: (id: string, currentStatus: string) => void }) => {
  const statusValue = normalizeStatus(task.status);
  const isCompleted = statusValue === 'concluido';

  // Date Logic for Right Side
  const startDate = task.data_criacao ? task.data_criacao.split('T')[0] : null;
  const endDate = task.data_limite;

  let dateDisplay = '';
  if (startDate && endDate) {
    if (startDate === endDate) {
      dateDisplay = formatDate(endDate);
    } else {
      dateDisplay = `${formatDate(startDate)} - ${formatDate(endDate)}`;
    }
  } else if (endDate) {
    dateDisplay = formatDate(endDate);
  }

  return (
    <div
      className={`group bg-white w-full p-8 border-b border-slate-200 hover:bg-slate-50 transition-all flex flex-col md:flex-row md:items-center gap-6 md:gap-8 animate-in ${isCompleted ? 'opacity-60' : ''}`}
    >
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

      <div className="flex-1 cursor-pointer" onClick={onClick}>
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
        {/* Show status only if NOT 'Em Andamento' (optional per request interpretation, or just remove if cleaner) */}
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
    data_limite: '',
    data_criacao: new Date().toISOString().split('T')[0],
    status: 'em andamento' as Status,
    categoria: 'NÃO CLASSIFICADA' as Categoria,
    notas: ''
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

          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Data de Início</label>
              <input
                type="date"
                value={formData.data_criacao}
                onChange={e => setFormData({ ...formData, data_criacao: e.target.value })}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Prazo Final</label>
              <input
                type="date"
                value={formData.data_limite}
                onChange={e => setFormData({ ...formData, data_limite: e.target.value })}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
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
              if (!formData.titulo) return alert('O título é obrigatório.');
              let finalNotes = formData.notas;
              if (formData.categoria !== 'NÃO CLASSIFICADA') {
                const tagStr = `Tag: ${formData.categoria}`;
                finalNotes = finalNotes ? `${finalNotes}\n\n${tagStr}` : tagStr;
              }
              onSave({
                ...formData,
                notas: finalNotes,
                data_criacao: `${formData.data_criacao}T12:00:00Z`
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
    data_limite: task.data_limite === '-' ? '' : task.data_limite,
    data_criacao: task.data_criacao ? task.data_criacao.split('T')[0] : '',
    status: task.status,
    categoria: task.categoria || 'NÃO CLASSIFICADA',
    notas: task.notas || '',
    acompanhamento: task.acompanhamento || []
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

          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Data de Criação</label>
              <input
                type="date"
                value={formData.data_criacao}
                onChange={e => setFormData({ ...formData, data_criacao: e.target.value })}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Prazo Final</label>
              <input
                type="date"
                value={formData.data_limite}
                onChange={e => setFormData({ ...formData, data_limite: e.target.value })}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
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
                acompanhamento: finalAcompanhamento,
                data_criacao: formData.data_criacao ? `${formData.data_criacao}T12:00:00Z` : task.data_criacao
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

const App: React.FC = () => {
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [entregas, setEntregas] = useState<EntregaInstitucional[]>([]);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);

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
  const [calendarViewMode, setCalendarViewMode] = useState<'month' | 'week'>('month');
  const [calendarDate, setCalendarDate] = useState(new Date());

  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [viewMode, setViewMode] = useState<'gallery' | 'pgc' | 'licitacoes' | 'assistencia' | 'sistemas' | 'plano-trabalho'>('gallery');
  const [selectedTask, setSelectedTask] = useState<Tarefa | null>(null);
  const [planosTrabalho, setPlanosTrabalho] = useState<PlanoTrabalho[]>([]);
  const [statusFilter, setStatusFilter] = useState<Status[]>(['em andamento']);
  const [sortOption, setSortOption] = useState<SortOption>('date-asc');
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Sync Logic
  const handleSync = async () => {
    if (isSyncing) return;
    setIsSyncing(true);
    showToast("Solicitando sincronização com Google...", "info");

    try {
      await setDoc(doc(db, 'system', 'sync'), {
        status: 'requested',
        timestamp: new Date().toISOString()
      });

      // Simple feedback loop - wait for completion or timeout
      const unsubscribe = onSnapshot(doc(db, 'system', 'sync'), (doc) => {
        const data = doc.data();
        if (data?.status === 'completed') {
          showToast("Sincronização concluída com sucesso!", "success");
          setIsSyncing(false);
          unsubscribe();
        } else if (data?.status === 'error') {
          showToast(`Erro na sincronização: ${data.error_message}`, "error");
          setIsSyncing(false);
          unsubscribe();
        }
      });

      // Timeout safety
      setTimeout(() => {
        if (isSyncing) {
          setIsSyncing(false);
          // unsubscribe is local scope, can't easily unsubscribe here without more complex logic, 
          // but for a simple button it's fine. The snapshot listener will just detach naturally on unmount or ignore.
        }
      }, 15000);

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

      <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
        <div className="max-w-[1400px] mx-auto px-4 md:px-8 py-3 md:py-4">
          {/* Mobile Header */}
          <div className="flex md:hidden items-center justify-between">
            <div className="flex items-center gap-2">
              <img src="/logo.png" alt="Hermes" className="w-10 h-10 object-contain" />
              <h1 className="text-lg font-black tracking-tighter text-slate-900">HERMES</h1>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsCreateModalOpen(true)}
                className="bg-slate-900 text-white p-2.5 rounded-xl shadow-lg hover:bg-slate-800 transition-all active:scale-95"
                aria-label="Criar Ação"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
              </button>
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
                <img src="/logo.png" alt="Hermes" className="w-9 h-9 object-contain" />
                <h1 className="text-xl font-black tracking-tighter text-slate-900">HERMES</h1>
              </div>
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
            </div>

            <div className="flex items-center gap-4">
              <div className="hidden lg:flex items-center bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 w-64 group focus-within:ring-2 focus-within:ring-blue-500 focus-within:bg-white transition-all">
                <svg className="w-4 h-4 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                <input type="text" placeholder="Pesquisar..." className="bg-transparent border-none outline-none text-xs font-bold text-slate-900 w-full" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
              </div>
              <button
                onClick={handleSync}
                disabled={isSyncing}
                className={`bg-white border border-slate-200 text-slate-700 px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-3 shadow-sm hover:bg-slate-50 transition-all active:scale-95 ${isSyncing ? 'opacity-50 cursor-wait' : ''}`}
              >
                <svg className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                {isSyncing ? 'Sincronizar' : 'Sync Google'}
              </button>
              <button
                onClick={() => setIsCreateModalOpen(true)}
                className="bg-slate-900 text-white px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 shadow-lg hover:bg-slate-800 transition-all active:scale-95"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                Criar Ação
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Menu Drawer */}
        {isMobileMenuOpen && (
          <div className="md:hidden border-t border-slate-200 bg-white">
            <nav className="flex flex-col p-4 space-y-2">
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
              <div className="pt-4 border-t border-slate-200 mt-2">
                <button
                  onClick={() => {
                    handleSync();
                    setIsMobileMenuOpen(false);
                  }}
                  disabled={isSyncing}
                  className={`w-full px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left bg-blue-50 text-blue-700 hover:bg-blue-100 ${isSyncing ? 'opacity-50' : ''}`}
                >
                  🔄 {isSyncing ? 'Sincronizando...' : 'Sync Google'}
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
                              <tr key={task.id} className={`hover:bg-slate-50 transition-colors ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}>
                                <td className="px-8 py-4 text-center">
                                  <input
                                    type="checkbox"
                                    checked={selectedTaskIds.includes(task.id)}
                                    onChange={() => setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id])}
                                    className="w-5 h-5 rounded-lg border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
                                  />
                                </td>
                                <td className="px-8 py-4">
                                  <div onClick={() => setSelectedTask(task)} className="text-[13px] font-bold text-slate-800 cursor-pointer hover:text-blue-600 transition-colors leading-snug">
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
                  {/* LEFT: Pending Tasks */}
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

                  {/* RIGHT: Plan & Deliveries */}
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
                                    // Implicit creation
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
      </div>

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
          <TaskEditModal
            task={selectedTask}
            onSave={handleUpdateTarefa}
            onDelete={handleDeleteTarefa}
            onClose={() => setSelectedTask(null)}
          />

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
    </div >
  );
};

const container = document.getElementById('root');
if (container) {
  const root = createRoot(container);
  root.render(<App />);
}
