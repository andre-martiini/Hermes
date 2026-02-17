
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { Tarefa, Status, EntregaInstitucional, Prioridade, AtividadeRealizada, Afastamento, PlanoTrabalho, PlanoTrabalhoItem, Categoria, Acompanhamento, BrainstormIdea, FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill, BillRubric, IncomeEntry, IncomeRubric, HealthWeight, DailyHabits, HealthSettings, Notification as AppNotification, AppSettings, formatDate, Sistema, SistemaStatus, WorkItem, WorkItemPhase, WorkItemPriority, QualityLog, WorkItemAudit } from './types';
import HealthView from './HealthView';
import { STATUS_COLORS, PROJECT_COLORS } from './constants';
import { db } from './firebase';
import { collection, onSnapshot, query, updateDoc, doc, addDoc, deleteDoc, setDoc, arrayUnion, arrayRemove } from 'firebase/firestore';
import { GoogleGenerativeAI } from "@google/generative-ai";
import FinanceView from './FinanceView';
import DashboardView from './DashboardView';


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
const DEFAULT_APP_SETTINGS: AppSettings = {
  notifications: {
    habitsReminder: {
      enabled: true,
      time: "20:00"
    },
    weighInReminder: {
      enabled: true,
      frequency: 'weekly',
      time: "07:00",
      dayOfWeek: 1 // Segunda-feira
    },
    budgetRisk: {
      enabled: true
    },
    overdueTasks: {
      enabled: true
    },
    pgcAudit: {
      enabled: true,
      daysBeforeEnd: 5
    }
  }
};

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

// Moved formatDate to types.ts to break circular dependency


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
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase ${PROJECT_COLORS[task.projeto] || 'bg-slate-100 text-slate-600'}`}>
          {task.projeto}
        </span>
        <span className="text-[8px] font-black text-slate-400 uppercase">{formatDate(task.data_limite)}</span>
        
        {/* Badge de Sincronização */}
        {task.sync_status === 'new' && (
          <span className="text-[7px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse">
            Novo
          </span>
        )}
        {task.sync_status === 'updated' && (
          <span className="text-[7px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">
            Atualizada
          </span>
        )}
      </div>
      <h5 className="text-[11px] font-bold text-slate-900 leading-tight group-hover:text-blue-600 line-clamp-2">{task.titulo}</h5>
    </div>
  );
});

const PgcAuditRow = ({
  item,
  entregaEntity,
  atividadesRelacionadas,
  tarefasRelacionadas,
  onDrop,
  onUnlinkTarefa,
  onSelectTask
}: {
  item: PlanoTrabalhoItem,
  entregaEntity?: EntregaInstitucional,
  atividadesRelacionadas: AtividadeRealizada[],
  tarefasRelacionadas: Tarefa[],
  onDrop: (tarefaId: string) => void,
  onUnlinkTarefa: (tarefaId: string, entregaId: string) => void,
  onSelectTask: (t: Tarefa) => void
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const entregaId = entregaEntity?.id;

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        e.currentTarget.classList.add('bg-blue-50');
      }}
      onDragLeave={(e) => {
        e.currentTarget.classList.remove('bg-blue-50');
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.currentTarget.classList.remove('bg-blue-50');
        const tarefaId = e.dataTransfer.getData('tarefaId');
        if (tarefaId) onDrop(tarefaId);
      }}
      className="group border-b border-slate-100 hover:bg-slate-50 transition-all p-8 flex flex-col gap-4"
    >
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-[10px] font-black text-blue-600 uppercase tracking-widest">{item.unidade}</span>
          {entregaEntity?.processo_sei && (
            <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest font-mono border border-slate-200 px-1.5 rounded">
              SEI: {entregaEntity.processo_sei}
            </span>
          )}
        </div>
        <h4 className="text-xl font-black text-slate-900 tracking-tight leading-snug">
          {item.entrega}
        </h4>
        <p className="text-xs font-medium text-slate-500 leading-relaxed mt-1">
          {item.descricao}
        </p>
      </div>

      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-[10px] font-black text-slate-400 uppercase">
            <div className="w-1.5 h-1.5 bg-blue-500 rounded-full"></div>
            {atividadesRelacionadas.length + tarefasRelacionadas.length} Ações vinculadas
          </div>
        </div>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="px-4 py-2 bg-white border border-slate-200 text-slate-600 rounded-xl text-[9px] font-black uppercase tracking-wider hover:bg-slate-50 transition-colors flex items-center gap-2 shadow-sm"
        >
          {isExpanded ? 'Ocultar Ações' : 'Ações Relacionadas'}
          <svg className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {isExpanded && (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 animate-in slide-in-from-top-2 duration-300">
          {atividadesRelacionadas.map(at => (
            <div key={at.id} className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm hover:border-slate-300 transition-all">
              <p className="text-[8px] font-black text-slate-400 uppercase mb-1">{formatDate(at.data_inicio)}</p>
              <p className="text-[11px] font-bold text-slate-700 leading-tight">{at.descricao_atividade}</p>
              <div className="mt-2 text-[8px] font-black text-blue-500 uppercase tracking-widest">Atividade PGD</div>
            </div>
          ))}
          {tarefasRelacionadas.map(t => (
            <div
              key={t.id}
              onClick={() => onSelectTask(t)}
              className="p-4 rounded-2xl bg-blue-50/30 border border-blue-100 shadow-sm hover:border-blue-300 hover:bg-blue-50/50 transition-all cursor-pointer group/task relative pr-10"
            >
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (entregaId) onUnlinkTarefa(t.id, entregaId);
                }}
                className="absolute top-3 right-3 p-1.5 text-slate-300 hover:text-rose-500 hover:bg-white rounded-lg opacity-0 group-hover/task:opacity-100 transition-all shadow-sm"
                title="Desvincular"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[8px] font-black text-blue-500 uppercase tracking-widest">Tarefa Geral</p>
                <p className="text-[8px] font-black text-slate-400 uppercase tracking-widest">{formatDate(t.data_limite)}</p>
              </div>
              <p className="text-xs font-bold text-slate-800 leading-snug group-hover/task:text-blue-700 transition-colors">{t.titulo}</p>
            </div>
          ))}
          {atividadesRelacionadas.length === 0 && tarefasRelacionadas.length === 0 && (
            <div className="col-span-full py-8 text-center bg-slate-50/50 rounded-2xl border-2 border-dashed border-slate-100">
              <p className="text-slate-300 text-[10px] font-black uppercase tracking-widest italic">Nenhuma ação vinculada a esta entrega</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// --- Components ---

const DayView = ({
  tasks,
  currentDate,
  onTaskClick,
  onTaskUpdate,
  onExecuteTask
}: {
  tasks: Tarefa[],
  currentDate: Date,
  onTaskClick: (t: Tarefa) => void,
  onTaskUpdate: (id: string, updates: Partial<Tarefa>, suppressToast?: boolean) => void,
  onExecuteTask: (t: Tarefa) => void
}) => {
  const [resizing, setResizing] = useState<{ id: string, type: 'top' | 'bottom', startY: number, startMin: number } | null>(null);
  const [dragging, setDragging] = useState<{ id: string, startY: number, startMin: number } | null>(null);
  const [currentTime, setCurrentTime] = useState(new Date());
  const sidebarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 60000);
    // Initial update
    setCurrentTime(new Date());
    return () => clearInterval(timer);
  }, []);

  // Calculate current time position
  const currentMinutes = currentTime.getHours() * 60 + currentTime.getMinutes();
  const hourHeight = 60;
  const currentTimeTop = (currentMinutes / 60) * hourHeight;
  // Make sure we only show line if current day is today
  const isToday = currentDate.toISOString().split('T')[0] === new Date().toISOString().split('T')[0];

  const dayStr = currentDate.toISOString().split('T')[0];
  const dayTasks = useMemo(() => tasks.filter(t => {
    if (t.status === 'excluído' as any) return false;
    const start = t.data_inicio || t.data_criacao?.split('T')[0] || t.data_limite;
    const end = t.data_limite;
    return dayStr >= start && dayStr <= end;
  }), [tasks, dayStr]);

  const timeToMinutes = (time: string) => {
    if (!time) return 0;
    const [h, m] = time.split(':').map(Number);
    return h * 60 + m;
  };

  const minutesToTime = (minutes: number) => {
    const h = Math.max(0, Math.min(23, Math.floor(minutes / 60)));
    const m = Math.max(0, Math.min(59, Math.floor(minutes % 60)));
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (resizing) {
      const deltaY = e.clientY - resizing.startY;
      const deltaMin = Math.round((deltaY / hourHeight) * 60 / 15) * 15;

      const task = tasks.find(t => t.id === resizing.id);
      if (!task) return;

      if (resizing.type === 'bottom') {
        const newEndMin = Math.max(timeToMinutes(task.horario_inicio || '00:00') + 15, resizing.startMin + deltaMin);
        onTaskUpdate(resizing.id, { horario_fim: minutesToTime(newEndMin) }, true);
      } else {
        const duration = timeToMinutes(task.horario_fim || '01:00') - timeToMinutes(task.horario_inicio || '00:00');
        const newStartMin = Math.min(timeToMinutes(task.horario_fim || '01:00') - 15, resizing.startMin + deltaMin);
        onTaskUpdate(resizing.id, { horario_inicio: minutesToTime(newStartMin) }, true);
      }
    } else if (dragging) {
      const deltaY = e.clientY - dragging.startY;
      const deltaMin = Math.round((deltaY / hourHeight) * 60 / 15) * 15;

      const task = tasks.find(t => t.id === dragging.id);
      if (!task) return;

      const duration = timeToMinutes(task.horario_fim || '01:00') - timeToMinutes(task.horario_inicio || '00:00');
      const newStartMin = Math.max(0, Math.min(24 * 60 - duration, dragging.startMin + deltaMin));
      onTaskUpdate(dragging.id, {
        horario_inicio: minutesToTime(newStartMin),
        horario_fim: minutesToTime(newStartMin + duration)
      }, true);
    }
  };

  const handleMouseUp = (e: MouseEvent) => {
    // Check if dropped on sidebar
    if (dragging && sidebarRef.current) {
      const sidebarRect = sidebarRef.current.getBoundingClientRect();
      if (
        e.clientX >= sidebarRect.left &&
        e.clientX <= sidebarRect.right &&
        e.clientY >= sidebarRect.top &&
        e.clientY <= sidebarRect.bottom
      ) {
         // Return to backlog
         onTaskUpdate(dragging.id, { horario_inicio: null, horario_fim: null }, false);
         // You might see the gray area here because the container has bg-slate-50, but the calendar grid has bg-white. 
         // When content doesn't fill height, the gray background shows.
      }
    }
    setResizing(null);
    setDragging(null);
  };

  useEffect(() => {
    if (resizing || dragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [resizing, dragging]);

  return (
    <div className="flex h-[600px] overflow-hidden bg-slate-50 border-t border-slate-100">
      {/* Scrollable Container for Hours + Grid */}
      <div className="flex-1 flex overflow-y-auto custom-scrollbar relative">
        {/* Hour Column */}
        <div className="w-16 flex-shrink-0 bg-white border-r border-slate-100 select-none">
          <div className="relative" style={{ height: 24 * hourHeight }}>
            {Array.from({ length: 24 }).map((_, h) => (
              <div key={h} className="h-[60px] border-b border-slate-50 flex items-start justify-center pt-1">
                <span className="text-[10px] font-black text-slate-300 uppercase">{h.toString().padStart(2, '0')}:00</span>
              </div>
            ))}
          </div>
        </div>

        {/* Main Grid Area */}
        <div className="flex-1 relative bg-white" onDragOver={e => e.preventDefault()}>
          <div className="absolute inset-0 z-0 pointer-events-none">
            {Array.from({ length: 24 }).map((_, h) => (
              <div key={h} className="h-[60px] border-b border-slate-100 w-full"></div>
            ))}
            
            {/* Current Time Line */}
            {isToday && (
               <div 
                 className="absolute left-0 right-0 border-t-2 border-red-500 z-20 pointer-events-none flex items-center"
                 style={{ top: currentTimeTop, opacity: 0.7 }}
               >
                 <div className="absolute -left-1 w-2 h-2 bg-red-500 rounded-full"></div>
               </div>
            )}
          </div>

          <div className="relative w-full" style={{ height: 24 * hourHeight }} onDrop={(e) => {
            const taskId = e.dataTransfer.getData('task-id');
            const rect = e.currentTarget.getBoundingClientRect();
            const scrollContainer = e.currentTarget.closest('.custom-scrollbar');
            const scrollTop = scrollContainer ? (scrollContainer as HTMLElement).scrollTop : 0;
            
            // Adjust Y calculation to be relative to the grid container
            // The rect.top already accounts for scroll if the container moves? 
            // actually, rect includes viewport position.
            // e.clientY is viewport Y.
            // y = e.clientY - rect.top gives position relative to the VISIBLE top of the element.
            // If the element is scrolled, its content is shifted.
            // But here the element is "relative w-full" inside the scroll view.
            // The "relative w-full" div has height 24 * hourHeight (1440px).
            // It is inside "flex-1 relative bg-white" which is inside "flex-1 flex overflow-y-auto" (the scroller).
            
            // Wait, the Drop target is the inner div `style={{ height: 24 * hourHeight }}`.
            // This div is TALL. It is NOT scrolling itself. It is inside a scrolling parent.
            // So resizing/positioning logic relies on `top` CSS property relative to this tall div.
            
            // When we calculate `y`:
            // e.clientY is mouse Y.
            // rect.top is the top of the tall div relative to viewport.
            // So (e.clientY - rect.top) IS the Y coordinate inside the tall div.
            // We do NOT need to add scrollTop if we are measuring relative to the target element's bounding rect, 
            // BECAUSE the target element moves UP when we scroll down.
            // Example:
            // Scrolled 0px. Top of div is at 100px. Mouse at 150px. Y = 150 - 100 = 50. Correct.
            // Scrolled 1000px. Top of div is at -900px. Mouse at 150px. Y = 150 - (-900) = 1050. Correct.
            
            // So the original logic `const y = e.clientY - rect.top;` is implicitly correct if `e.currentTarget` is the tall div.
            // In the original code: `onDrop` was on `style={{ height: 24 * hourHeight }}`, which IS the tall div.
            // So `y` calculation remains valid without manual scrollTop adjustment.
            
            // However, the original code had:
            // const scrollContainer = e.currentTarget.parentElement;
            // const scrollTop = scrollContainer ? scrollContainer.scrollTop : 0;
            // But it didn't USE `scrollTop` in the `y` calculation in the snippet I saw!
            // Snippet:
            // const y = e.clientY - rect.top;
            // const hour = Math.floor(y / hourHeight);
            
            // It seems `scrollTop` variable was defined but unused or I missed its usage?
            // Let's re-read the specific block in the previous `view_file`.
            
            // Line 384: `const scrollTop = scrollContainer ? scrollContainer.scrollTop : 0;`
            // Line 385: `const y = e.clientY - rect.top;`
            
            // The `scrollTop` was indeed unused in the calculation provided in the snippet.
            // So I can safely ignore it or remove it.
            // But to be safe and clean, I will just proceed with the same logic.
            
            const y = e.clientY - rect.top;
            const hour = Math.floor(y / hourHeight);
            if (taskId) {
              onTaskUpdate(taskId, {
                horario_inicio: `${hour.toString().padStart(2, '0')}:00`,
                horario_fim: `${(hour + 1).toString().padStart(2, '0')}:00`
              }, true);
            }
          }}>
            {dayTasks.filter(t => t.horario_inicio).map(task => {
              const startMin = timeToMinutes(task.horario_inicio!);
              const endMin = timeToMinutes(task.horario_fim || minutesToTime(startMin + 60));
              const top = (startMin / 60) * hourHeight;
              const height = ((endMin - startMin) / 60) * hourHeight;
  
              return (
                <div
                  key={task.id}
                  className={`absolute left-4 right-4 rounded-xl border-2 p-3 shadow-md group transition-all cursor-grab active:cursor-grabbing overflow-hidden
                    ${task.categoria === 'CLC' ? 'bg-blue-50 border-blue-200 text-blue-800' :
                      task.categoria === 'ASSISTÊNCIA' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' :
                        'bg-white border-slate-200 text-slate-800'}
                  `}
                  style={{ top, height: Math.max(30, height), minHeight: 30, zIndex: 10 }}
                  onMouseDown={(e) => {
                    const target = e.target as HTMLElement;
                    if (target.classList.contains('resize-handle')) return;
                    setDragging({ id: task.id, startY: e.clientY, startMin });
                  }}
                >
                  <div className="flex justify-between items-start gap-2">
                    <div className="text-[11px] font-black leading-tight line-clamp-2">{task.titulo}</div>
                    <div className="flex gap-1 shrink-0">
                      <button 
                        onClick={(e) => { 
                          e.stopPropagation(); 
                          if(window.confirm(task.status === 'concluído' ? "Reabrir tarefa?" : "Concluir tarefa?")) {
                            onTaskUpdate(task.id, { status: task.status === 'concluído' ? 'em andamento' : 'concluído' });
                          }
                        }} 
                        className={`p-1 hover:bg-black/5 rounded ${task.status === 'concluído' ? 'text-emerald-600 bg-emerald-100' : 'text-slate-400 hover:text-emerald-600'}`} 
                        title={task.status === 'concluído' ? 'Reabrir' : 'Concluir'}
                      >
                         <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); onExecuteTask(task); }} className="p-1 hover:bg-black/5 rounded text-indigo-600" title="Executar">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); onTaskClick(task); }} className="p-1 hover:bg-black/5 rounded" title="Editar">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                      </button>
                    </div>
                  </div>
                  <div className="text-[9px] font-black mt-1 opacity-40 uppercase tracking-widest">{task.horario_inicio} - {task.horario_fim}</div>
  
                  {/* Handles */}
                  <div
                    className="resize-handle absolute top-0 left-0 right-0 h-2 cursor-ns-resize hover:bg-black/10 transition-colors"
                    onMouseDown={(e) => {
                      e.stopPropagation();
                      setResizing({ id: task.id, type: 'top', startY: e.clientY, startMin });
                    }}
                  />
                  <div
                    className="resize-handle absolute bottom-0 left-0 right-0 h-2 cursor-ns-resize hover:bg-black/10 transition-colors"
                    onMouseDown={(e) => {
                      e.stopPropagation();
                      setResizing({ id: task.id, type: 'bottom', startY: e.clientY, startMin: endMin });
                    }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Side Backlog for current day */}
      <div 
        ref={sidebarRef}
        className="hidden md:block w-64 bg-slate-50 border-l border-slate-200 p-6 overflow-y-auto custom-scrollbar"
        onDragOver={e => e.preventDefault()}
        onDrop={(e) => {
           const taskId = e.dataTransfer.getData('task-id');
           if (taskId) {
             onTaskUpdate(taskId, { horario_inicio: null, horario_fim: null });
           }
        }}
      >
        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-6">Aguardando Alocação</h4>
        <div className="space-y-3">
          {dayTasks.filter(t => !t.horario_inicio).map(task => (
            <div
              key={task.id}
              draggable
              onDragStart={(e) => e.dataTransfer.setData('task-id', task.id)}
              className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm hover:border-blue-400 hover:shadow-md transition-all cursor-grab active:cursor-grabbing"
            >
              <div className="text-[10px] font-bold text-slate-700 leading-tight mb-2">{task.titulo}</div>
              <div className="flex items-center gap-2">
                <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase ${PROJECT_COLORS[task.projeto] || 'bg-slate-100 text-slate-600'}`}>{task.projeto}</span>
              </div>
            </div>
          ))}
          {dayTasks.filter(t => !t.horario_inicio).length === 0 && (
            <div className="py-12 text-center border-2 border-dashed border-slate-200 rounded-[2rem]">
              <p className="text-slate-300 text-[10px] font-black uppercase italic">Tudo alocado</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const CalendarView = ({
  tasks,
  viewMode,
  currentDate,
  onDateChange,
  onTaskClick,
  onViewModeChange,
  onTaskUpdate,
  onExecuteTask
}: {
  tasks: Tarefa[],
  viewMode: 'month' | 'week' | 'day',
  currentDate: Date,
  onDateChange: (d: Date) => void,
  onTaskClick: (t: Tarefa) => void,
  onViewModeChange: (m: 'month' | 'week' | 'day') => void,
  onTaskUpdate: (id: string, updates: Partial<Tarefa>, suppressToast?: boolean) => void,
  onExecuteTask: (t: Tarefa) => void
}) => {
  const [days, setDays] = React.useState<Date[]>([]);

  useEffect(() => {
    const d = new Date(currentDate);
    const newDays = [];

    if (viewMode === 'day') {
      newDays.push(new Date(currentDate));
    } else if (viewMode === 'month') {
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

  const monthName = viewMode === 'day'
    ? new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(currentDate)
    : new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(currentDate);

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
            <button
              onClick={() => onViewModeChange('day')}
              className={`px-3 py-1 text-[10px] uppercase font-black rounded-md transition-all ${viewMode === 'day' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
            >
              Dia
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

      {viewMode === 'day' ? (
        <DayView
          tasks={tasks}
          currentDate={currentDate}
          onTaskClick={onTaskClick}
          onTaskUpdate={onTaskUpdate}
          onExecuteTask={onExecuteTask}
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
        </>
      )}
    </div>
  );
};

const RowCard = React.memo(({ task, onClick, onToggle, onDelete, onEdit, onExecute }: { 
  task: Tarefa, 
  onClick?: () => void, 
  onToggle: (id: string, currentStatus: string) => void, 
  onDelete: (id: string) => void,
  onEdit: (t: Tarefa) => void,
  onExecute: (t: Tarefa) => void 
}) => {
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

  const getTagStyle = (name: string, type: 'category' | 'project') => {
    const n = name.toUpperCase();
    if (type === 'category') {
      if (n === 'CLC') return 'bg-blue-100 text-blue-800 border-blue-200';
      if (n === 'ASSISTÊNCIA' || n === 'ASSISTÊNCIA ESTUDANTIL') return 'bg-emerald-100 text-emerald-800 border-emerald-200';
    }
    
    // Project Colors
    if (n.includes('MAGO')) return 'bg-purple-100 text-purple-800 border-purple-200';
    if (n.includes('SIGEX')) return 'bg-indigo-100 text-indigo-800 border-indigo-200';
    if (n.includes('PROEN')) return 'bg-cyan-100 text-cyan-800 border-cyan-200';
    if (n.includes('PLS')) return 'bg-orange-100 text-orange-800 border-orange-200';
    if (n.includes('PDI')) return 'bg-teal-100 text-teal-800 border-teal-200';
    
    return 'bg-slate-100 text-slate-600 border-slate-200';
  };

  return (
    <div
      onClick={onClick}
      onMouseLeave={() => setIsConfirmingDelete(false)}
      className={`group bg-white w-full p-4 md:p-8 border-b border-slate-100 hover:bg-slate-50 transition-all flex flex-col md:flex-row items-start md:items-center gap-4 md:gap-8 animate-in cursor-pointer relative ${isCompleted ? 'opacity-60' : ''}`}
    >
      {/* Botão de Excluir Flutuante */}
      <div className="absolute top-2 right-2 md:top-4 md:right-4 opacity-0 group-hover:opacity-100 transition-all z-20">
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

      <div className="flex-shrink-0 mt-1 md:mt-0 flex items-center gap-4">
         <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle(task.id, task.status);
          }}
          className={`w-6 h-6 md:w-8 md:h-8 rounded-lg md:rounded-xl border-2 flex items-center justify-center transition-all ${isCompleted ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-slate-200 hover:border-slate-400 text-transparent'}`}
        >
          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
        </button>
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          {task.categoria && task.categoria !== 'NÃO CLASSIFICADA' && (
            <span className={`text-[8px] md:text-[9px] font-black px-2 py-0.5 rounded uppercase tracking-wider border ${getTagStyle(task.categoria, 'category')}`}>
              {task.categoria}
            </span>
          )}
          <span className={`text-[8px] md:text-[9px] font-black px-2 py-0.5 rounded uppercase tracking-wider border ${getTagStyle(task.projeto, 'project')}`}>
            {task.projeto}
          </span>
          
          {/* Badge de Sincronização */}
          {task.sync_status === 'new' && (
            <span className="text-[8px] md:text-[9px] font-black px-2 py-0.5 rounded uppercase tracking-wider bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse flex items-center gap-1">
              <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z" /></svg>
              Novo
            </span>
          )}
          {task.sync_status === 'updated' && (
            <span className="text-[8px] md:text-[9px] font-black px-2 py-0.5 rounded uppercase tracking-wider bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm flex items-center gap-1">
              <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" /></svg>
              Atualizada
            </span>
          )}
        </div>
        <div className={`text-sm md:text-base font-bold text-slate-800 leading-snug group-hover:text-blue-600 transition-colors ${isCompleted ? 'line-through text-slate-400' : ''}`}>
          {task.titulo}
        </div>
      </div>

      <div className="hidden md:flex flex-col items-end gap-1 min-w-[200px]">
         <div className="flex gap-2 mb-2 mr-12">
            <button
               onClick={(e) => { e.stopPropagation(); onEdit(task); }}
               className="px-3 py-1.5 bg-slate-100 text-slate-500 rounded-lg text-[9px] font-black uppercase tracking-wider hover:bg-slate-200 transition-colors"
             >
               Editar
             </button>
             <button
               onClick={(e) => { e.stopPropagation(); onExecute(task); }}
               className="px-3 py-1.5 bg-slate-800 text-white rounded-lg text-[9px] font-black uppercase tracking-wider hover:bg-slate-700 transition-colors shadow-sm"
             >
               Executar
             </button>
         </div>

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

const CategoryView = ({ tasks, viewMode, onSelectTask, onExecuteTask }: { tasks: Tarefa[], viewMode: string, onSelectTask: (t: Tarefa) => void, onExecuteTask: (t: Tarefa) => void }) => {
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
        <div className={`bg-white border-l-8 border-${color}-600 p-8 rounded-none md:rounded-[2rem] shadow-xl`}>
          <h3 className="text-2xl font-black text-slate-900 tracking-tight flex items-center justify-between">
            Ações em Aberto - {title}
            <span className={`bg-${color}-100 text-${color}-600 text-[10px] font-black px-4 py-1.5 rounded-full`}>{pendentes.length}</span>
          </h3>
        </div>

        <div className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl">
          <table className="w-full text-left">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Demanda</th>
                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-[200px]">Prazo</th>
                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-[250px] text-right">Ações</th>
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
                  <td className="px-8 py-6 text-right">
                    <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={(e) => { e.stopPropagation(); onSelectTask(t); }}
                        className="px-4 py-2 bg-slate-100 text-slate-600 rounded-xl text-[9px] font-black uppercase tracking-wider hover:bg-slate-200 transition-colors"
                      >
                        Editar
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); onExecuteTask(t); }}
                        className="px-4 py-2 bg-slate-900 text-white rounded-xl text-[9px] font-black uppercase tracking-wider hover:bg-slate-800 transition-colors shadow-lg shadow-slate-200"
                      >
                        Executar
                      </button>
                    </div>
                  </td>
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
        <div className="bg-slate-900 text-white p-8 rounded-none md:rounded-[2rem] shadow-xl">
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
                <div className="bg-white p-5 rounded-none md:rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-all cursor-pointer" onClick={() => onSelectTask(t)}>
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

const NotificationCenter = ({
  notifications,
  onMarkAsRead,
  onDismiss,
  isOpen,
  onClose,
  onUpdateOverdue
}: {
  notifications: AppNotification[],
  onMarkAsRead: (id: string) => void,
  onDismiss: (id: string) => void,
  isOpen: boolean,
  onClose: () => void,
  onUpdateOverdue?: () => void
}) => {
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Element;
      if (
        dropdownRef.current && 
        !dropdownRef.current.contains(target as Node) &&
        !target.closest('.notification-trigger')
      ) {
        onClose();
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div ref={dropdownRef} className="fixed sm:absolute top-16 sm:top-full mt-2 sm:mt-4 inset-x-4 sm:inset-auto sm:right-0 w-auto sm:w-96 bg-white rounded-[2.5rem] shadow-[0_20px_50px_rgba(0,0,0,0.2)] border border-slate-100 overflow-hidden z-[100] animate-in fade-in slide-in-from-top-4 sm:slide-in-from-right-4 duration-300">
      <div className="p-8 border-b border-slate-50 bg-slate-50/50 flex items-center justify-between">
        <div>
          <h3 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em]">Notificações</h3>
          <p className="text-[9px] text-slate-400 font-bold uppercase mt-1">Hermes Intelligent Alerts</p>
        </div>
        <span className="bg-blue-600 text-white text-[10px] font-black px-2.5 py-1 rounded-full shadow-lg shadow-blue-200">
          {notifications.filter(n => !n.isRead).length}
        </span>
      </div>
      <div className="max-h-[400px] overflow-y-auto custom-scrollbar">
        {notifications.length > 0 ? (
          notifications.map(n => (
            <div
              key={n.id}
              className={`p-6 border-b border-slate-50 hover:bg-slate-50 transition-all cursor-pointer relative group ${!n.isRead ? 'bg-blue-50/30' : ''}`}
              onClick={() => onMarkAsRead(n.id)}
            >
              <div className="flex gap-4">
                <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${n.type === 'success' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]' :
                  n.type === 'warning' ? 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]' :
                    n.type === 'error' ? 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.4)]' :
                      'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.4)]'
                  }`} />
                <div className="flex-1">
                  <h4 className={`text-xs font-bold leading-tight mb-1 ${!n.isRead ? 'text-slate-900' : 'text-slate-600'}`}>{n.title}</h4>
                  <p className="text-[11px] text-slate-500 leading-relaxed font-medium">{n.message}</p>
                  <div className="flex items-center justify-between mt-3">
                    <span className="text-[8px] font-black text-slate-300 uppercase tracking-widest">{formatDate(n.timestamp.split('T')[0])}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDismiss(n.id);
                      }}
                      className="text-[8px] font-black text-slate-300 uppercase tracking-widest hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-all"
                    >
                      Remover
                    </button>
                  </div>
                  {n.title === "Ações Vencidas" && onUpdateOverdue && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onUpdateOverdue();
                        onMarkAsRead(n.id);
                      }}
                      className="mt-4 w-full py-2.5 bg-slate-900 text-white text-[9px] font-black uppercase tracking-widest rounded-xl shadow-lg hover:bg-blue-600 transition-all active:scale-95"
                    >
                      Atualizar tudo para hoje
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="p-16 text-center">
            <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
            </div>
            <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Tudo limpo por aqui</p>
          </div>
        )}
      </div>
      {notifications.length > 0 && (
        <button
          onClick={() => notifications.forEach(n => onDismiss(n.id))}
          className="w-full py-5 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em] hover:bg-slate-50 transition-colors border-t border-slate-50 group"
        >
          Limpar todas as notificações <span className="group-hover:text-blue-600 transition-colors ml-1">→</span>
        </button>
      )}
    </div>
  );
};

const SettingsModal = ({
  settings,
  unidades,
  onSave,
  onClose,
  onAddUnidade,
  onDeleteUnidade,
  onUpdateUnidade,
  initialTab
}: {
  settings: AppSettings,
  unidades: { id: string, nome: string, palavras_chave?: string[] }[],
  onSave: (settings: AppSettings) => void,
  onClose: () => void,
  onAddUnidade: (nome: string) => void,
  onDeleteUnidade: (id: string) => void,
  onUpdateUnidade: (id: string, updates: any) => void,
  initialTab?: 'notifications' | 'context' | 'sistemas'
}) => {
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);
  const [activeTab, setActiveTab] = useState<'notifications' | 'context' | 'sistemas'>(initialTab || 'notifications');
  const [newUnidadeNome, setNewUnidadeNome] = useState('');
  const [newKeywordMap, setNewKeywordMap] = useState<{ [key: string]: string }>({});

  // Check for protected units only for deletion logic, not for hiding them
  // We process all units from the 'unidades' prop.

  const handleAddKeyword = (uId: string, current: string[]) => {
    const val = newKeywordMap[uId]?.trim();
    if (!val) return;
    const updated = Array.from(new Set([...current, val]));
    onUpdateUnidade(uId, { palavras_chave: updated });
    setNewKeywordMap({ ...newKeywordMap, [uId]: '' });
  };

  const handleRemoveKeyword = (uId: string, current: string[], kw: string) => {
    const updated = current.filter(k => k !== kw);
    onUpdateUnidade(uId, { palavras_chave: updated });
  };

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-0 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-full md:h-auto md:max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300 flex flex-col max-h-[90vh]">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex flex-col gap-6 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-2xl font-black text-slate-900 tracking-tight">Configurações</h3>
              <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">Painel de Preferências</p>
            </div>
            <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
              <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>

          <div className="flex bg-slate-200/50 p-1 rounded-2xl">
            <button
              onClick={() => setActiveTab('notifications')}
              className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${activeTab === 'notifications' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
            >
              🔔 Notificações
            </button>
            <button
              onClick={() => setActiveTab('context')}
              className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${activeTab === 'context' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
            >
              🏷️ Contexto & Áreas
            </button>
            <button
              onClick={() => setActiveTab('sistemas')}
              className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${activeTab === 'sistemas' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
            >
              💻 Sistemas
            </button>
          </div>
        </div>

        <div className="p-8 space-y-10 overflow-y-auto custom-scrollbar flex-1">
          {activeTab === 'notifications' ? (
            <>
              {/* Geral / Saúde Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500">
                <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                  <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                  Geral / Saúde
                </h4>

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-2xl border border-slate-100 group hover:border-blue-200 transition-all">
                  <div className="flex-1">
                    <p className="text-sm font-bold text-slate-900 mb-1">Hábitos de Hoje</p>
                    <p className="text-[11px] text-slate-500 font-medium">Abrir lembrete para marcar hábitos cumpridos</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <input
                      type="time"
                      value={localSettings.notifications.habitsReminder.time}
                      onChange={(e) => setLocalSettings({
                        ...localSettings,
                        notifications: {
                          ...localSettings.notifications,
                          habitsReminder: { ...localSettings.notifications.habitsReminder, time: e.target.value }
                        }
                      })}
                      className="bg-white border-none rounded-lg px-3 py-1.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                      onClick={() => setLocalSettings({
                        ...localSettings,
                        notifications: {
                          ...localSettings.notifications,
                          habitsReminder: { ...localSettings.notifications.habitsReminder, enabled: !localSettings.notifications.habitsReminder.enabled }
                        }
                      })}
                      className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.habitsReminder.enabled ? 'bg-blue-600' : 'bg-slate-300'}`}
                    >
                      <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.habitsReminder.enabled ? 'left-7' : 'left-1'}`} />
                    </button>
                  </div>
                </div>

                <div className="flex flex-col p-6 bg-slate-50 rounded-2xl border border-slate-100 group hover:border-rose-200 transition-all gap-4">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="text-sm font-bold text-slate-900 mb-1">Lembrete de Pesagem</p>
                      <p className="text-[11px] text-slate-500 font-medium">Registrar peso na balança</p>
                    </div>
                    <button
                      onClick={() => setLocalSettings({
                        ...localSettings,
                        notifications: {
                          ...localSettings.notifications,
                          weighInReminder: { ...localSettings.notifications.weighInReminder, enabled: !localSettings.notifications.weighInReminder.enabled }
                        }
                      })}
                      className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.weighInReminder.enabled ? 'bg-rose-600' : 'bg-slate-300'}`}
                    >
                      <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.weighInReminder.enabled ? 'left-7' : 'left-1'}`} />
                    </button>
                  </div>
                  {localSettings.notifications.weighInReminder.enabled && (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <select
                        value={localSettings.notifications.weighInReminder.frequency}
                        onChange={(e) => setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            weighInReminder: { ...localSettings.notifications.weighInReminder, frequency: e.target.value as any }
                          }
                        })}
                        className="bg-white border-none rounded-lg px-3 py-1.5 text-[10px] font-black uppercase text-slate-900 focus:ring-2 focus:ring-rose-500"
                      >
                        <option value="weekly">Semanal</option>
                        <option value="biweekly">Quinzenal</option>
                        <option value="monthly">Mensal</option>
                      </select>
                      <select
                        value={localSettings.notifications.weighInReminder.dayOfWeek}
                        onChange={(e) => setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            weighInReminder: { ...localSettings.notifications.weighInReminder, dayOfWeek: Number(e.target.value) }
                          }
                        })}
                        className="bg-white border-none rounded-lg px-3 py-1.5 text-[10px] font-black uppercase text-slate-900 focus:ring-2 focus:ring-rose-500"
                      >
                        <option value={0}>Domingo</option>
                        <option value={1}>Segunda</option>
                        <option value={2}>Terça</option>
                        <option value={3}>Quarta</option>
                        <option value={4}>Quinta</option>
                        <option value={5}>Sexta</option>
                        <option value={6}>Sábado</option>
                      </select>
                      <input
                        type="time"
                        value={localSettings.notifications.weighInReminder.time}
                        onChange={(e) => setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            weighInReminder: { ...localSettings.notifications.weighInReminder, time: e.target.value }
                          }
                        })}
                        className="bg-white border-none rounded-lg px-3 py-1.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-rose-500"
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Financeiro / Ações Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500 delay-100">
                <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                  <span className="w-2 h-2 bg-emerald-500 rounded-full"></span>
                  Financeiro / Ações
                </h4>

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-2xl border border-slate-100 group hover:border-emerald-200 transition-all">
                  <div className="flex-1">
                    <p className="text-sm font-bold text-slate-900 mb-1">Risco Orçamentário</p>
                    <p className="text-[11px] text-slate-500 font-medium">Avisar se gastos estiverem acima do esperado</p>
                  </div>
                  <button
                    onClick={() => setLocalSettings({
                      ...localSettings,
                      notifications: {
                        ...localSettings.notifications,
                        budgetRisk: { ...localSettings.notifications.budgetRisk, enabled: !localSettings.notifications.budgetRisk.enabled }
                      }
                    })}
                    className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.budgetRisk.enabled ? 'bg-emerald-600' : 'bg-slate-300'}`}
                  >
                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.budgetRisk.enabled ? 'left-7' : 'left-1'}`} />
                  </button>
                </div>

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-2xl border border-slate-100 group hover:border-blue-200 transition-all">
                  <div className="flex-1">
                    <p className="text-sm font-bold text-slate-900 mb-1">Ações Vencidas</p>
                    <p className="text-[11px] text-slate-500 font-medium">Alertar sobre tarefas fora do prazo</p>
                  </div>
                  <button
                    onClick={() => setLocalSettings({
                      ...localSettings,
                      notifications: {
                        ...localSettings.notifications,
                        overdueTasks: { ...localSettings.notifications.overdueTasks, enabled: !localSettings.notifications.overdueTasks.enabled }
                      }
                    })}
                    className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.overdueTasks.enabled ? 'bg-blue-600' : 'bg-slate-300'}`}
                  >
                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.overdueTasks.enabled ? 'left-7' : 'left-1'}`} />
                  </button>
                </div>

                <div className="flex flex-col p-6 bg-slate-50 rounded-2xl border border-slate-100 group hover:border-amber-200 transition-all gap-4">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="text-sm font-bold text-slate-900 mb-1">Audit PGC</p>
                      <p className="text-[11px] text-slate-500 font-medium">Verificar vínculos antes do fim do mês</p>
                    </div>
                    <button
                      onClick={() => setLocalSettings({
                        ...localSettings,
                        notifications: {
                          ...localSettings.notifications,
                          pgcAudit: { ...localSettings.notifications.pgcAudit, enabled: !localSettings.notifications.pgcAudit.enabled }
                        }
                      })}
                      className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.pgcAudit.enabled ? 'bg-amber-600' : 'bg-slate-300'}`}
                    >
                      <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.pgcAudit.enabled ? 'left-7' : 'left-1'}`} />
                    </button>
                  </div>
                  {localSettings.notifications.pgcAudit.enabled && (
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] font-black text-slate-400 uppercase">Avisar</span>
                      <input
                        type="number"
                        min="1"
                        max="28"
                        value={localSettings.notifications.pgcAudit.daysBeforeEnd}
                        onChange={(e) => setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            pgcAudit: { ...localSettings.notifications.pgcAudit, daysBeforeEnd: Number(e.target.value) }
                          }
                        })}
                        className="w-16 bg-white border-2 border-slate-100 rounded-lg px-3 py-1.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-amber-500 outline-none"
                      />
                      <span className="text-[10px] font-black text-slate-400 uppercase">dias antes</span>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : activeTab === 'context' ? (
            /* Unidades / áreas e Palavras-Chave TAB */
            <div className="space-y-6 animate-in slide-in-from-right-4 duration-500">
              <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                <span className="w-2 h-2 bg-amber-500 rounded-full"></span>
                Áreas e Palavras-Chave
              </h4>

              <div className="space-y-4">
                {unidades.map((u) => {
                  const isProtected = ['CLC', 'ASSISTÊNCIA', 'ASSISTÊNCIA ESTUDANTIL'].includes(u.nome.toUpperCase());
                  return (
                    <div key={u.id} className={`p-6 bg-slate-50 rounded-[2rem] border ${isProtected ? 'border-amber-200 bg-amber-50/30' : 'border-slate-100'} space-y-4 shadow-sm`}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <h5 className="text-xs font-black text-slate-900 uppercase tracking-widest">{u.nome}</h5>
                          {isProtected && <span className="bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-[8px] font-black uppercase tracking-widest">Protegido</span>}
                        </div>
                        
                        {!isProtected && (
                          <button
                            onClick={() => onDeleteUnidade(u.id)}
                            className="p-2 text-rose-300 hover:text-rose-600 hover:bg-rose-50 rounded-full transition-all"
                            title="Remover Área"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          </button>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {(u.palavras_chave || []).map((kw, i) => (
                          <span key={i} className="inline-flex items-center gap-1 px-3 py-1 bg-white border border-slate-200 rounded-full text-[9px] font-black text-slate-600 uppercase group/kw">
                            {kw}
                            <button onClick={() => handleRemoveKeyword(u.id, u.palavras_chave || [], kw)} className="text-slate-300 hover:text-rose-500 transition-colors">
                              <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                          </span>
                        ))}
                        {(u.palavras_chave || []).length === 0 && (
                          <p className="text-[10px] text-slate-400 italic">Sem palavras-chave definidas</p>
                        )}
                      </div>

                      <div className="flex gap-2">
                        <input
                          type="text"
                          placeholder="Nova palavra-chave..."
                          value={newKeywordMap[u.id] || ''}
                          onChange={(e) => setNewKeywordMap({ ...newKeywordMap, [u.id]: e.target.value })}
                          onKeyDown={(e) => e.key === 'Enter' && handleAddKeyword(u.id, u.palavras_chave || [])}
                          className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-2 text-[10px] font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none"
                        />
                        <button
                          onClick={() => handleAddKeyword(u.id, u.palavras_chave || [])}
                          className="bg-blue-600 text-white px-4 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all shadow-md shadow-blue-100"
                        >
                          Add
                        </button>
                      </div>
                    </div>
                  );
                })}

                <div className="p-6 bg-blue-50/50 rounded-[2rem] border-2 border-dashed border-blue-200 flex flex-col gap-4">
                  <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest text-center">Cadastrar Nova Área de Contexto</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Nome da Unidade (ex: DEV, MARKETING)"
                      value={newUnidadeNome}
                      onChange={(e) => setNewUnidadeNome(e.target.value)}
                      className="flex-1 bg-white border border-blue-100 rounded-xl px-4 py-3 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none shadow-sm"
                    />
                    <button
                      onClick={() => {
                        if (newUnidadeNome.trim()) {
                          onAddUnidade(newUnidadeNome.trim().toUpperCase());
                          setNewUnidadeNome('');
                        }
                      }}
                      className="bg-blue-600 text-white px-6 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all shadow-lg shadow-blue-200"
                    >
                      Criar
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : activeTab === 'sistemas' ? (
            <div className="space-y-6 animate-in slide-in-from-bottom-4 duration-500">
              <div className="space-y-4">
                <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                  <span className="w-2 h-2 bg-violet-500 rounded-full"></span>
                  Sistemas em Desenvolvimento
                </h4>

                <p className="text-xs text-slate-500 font-medium">
                  Cadastre os sistemas que você está desenvolvendo para gerenciá-los no módulo Sistemas.
                </p>

                {/* Lista de Sistemas */}
                <div className="space-y-3">
                  {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length > 0 ? (
                    unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(sistema => (
                      <div key={sistema.id} className="bg-violet-50 border border-violet-100 rounded-2xl p-6 group hover:border-violet-300 transition-all">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-violet-500 rounded-xl flex items-center justify-center">
                              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                              </svg>
                            </div>
                            <div>
                              <p className="text-sm font-black text-slate-900">{sistema.nome.replace('SISTEMA:', '').trim()}</p>
                              <p className="text-[10px] text-slate-500 font-medium">Sistema cadastrado</p>
                            </div>
                          </div>
                          <button
                            onClick={() => onDeleteUnidade(sistema.id)}
                            className="opacity-0 group-hover:opacity-100 p-2 hover:bg-rose-100 rounded-xl transition-all text-rose-600"
                            title="Remover sistema"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-12 bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                      <div className="w-16 h-16 bg-violet-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <svg className="w-8 h-8 text-violet-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                        </svg>
                      </div>
                      <p className="text-slate-400 font-bold text-sm">Nenhum sistema cadastrado</p>
                      <p className="text-slate-400 text-xs mt-1">Adicione seu primeiro sistema abaixo</p>
                    </div>
                  )}
                </div>

                {/* Formulário para adicionar novo sistema */}
                <div className="bg-gradient-to-br from-violet-50 to-purple-50 border-2 border-violet-200 rounded-2xl p-6">
                  <p className="text-[10px] font-black text-violet-600 uppercase tracking-widest text-center mb-4">Cadastrar Novo Sistema</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Nome do Sistema (ex: Hermes, Portal Web, API REST)"
                      value={newUnidadeNome}
                      onChange={(e) => setNewUnidadeNome(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && newUnidadeNome.trim()) {
                          onAddUnidade(`SISTEMA: ${newUnidadeNome.trim()}`);
                          setNewUnidadeNome('');
                        }
                      }}
                      className="flex-1 bg-white border border-violet-100 rounded-xl px-4 py-3 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none shadow-sm"
                    />
                    <button
                      onClick={() => {
                        if (newUnidadeNome.trim()) {
                          onAddUnidade(`SISTEMA: ${newUnidadeNome.trim()}`);
                          setNewUnidadeNome('');
                        }
                      }}
                      className="bg-violet-600 text-white px-6 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-violet-700 transition-all shadow-lg shadow-violet-200"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" />
                      </svg>
                    </button>
                  </div>
                  <p className="text-[9px] text-violet-600 font-medium mt-2 text-center">Pressione Enter ou clique no botão + para adicionar</p>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4 flex-shrink-0">
          <button onClick={onClose} className="flex-1 px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all">Cancelar</button>
          <button
            onClick={() => {
              onSave(localSettings);
              onClose();
            }}
            className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
          >
            Salvar Alterações
          </button>
        </div>
      </div>
    </div>
  );
};

const DailyHabitsModal = ({
  habits,
  onUpdateHabits,
  onClose
}: {
  habits: DailyHabits,
  onUpdateHabits: (date: string, updates: Partial<DailyHabits>) => void,
  onClose: () => void
}) => {
  const todayStr = new Date().toISOString().split('T')[0];

  const handleHabitToggle = (habitKey: keyof DailyHabits) => {
    if (habitKey === 'id') return;
    onUpdateHabits(todayStr, { [habitKey]: !habits[habitKey] });
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-0 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-full md:h-auto md:max-w-md rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-8 border-b border-slate-100 bg-amber-500/5 flex items-center justify-between">
          <div>
            <h3 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-3">
              <span className="w-2 h-8 bg-amber-500 rounded-full"></span>
              Hábitos de Hoje
            </h3>
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">Lembrete Diário</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-8 space-y-3">
          {[
            { id: 'noSugar', label: 'Sem Açúcar', color: 'rose' },
            { id: 'noAlcohol', label: 'Sem Álcool', color: 'purple' },
            { id: 'noSnacks', label: 'Sem Lanches/Delivery', color: 'orange' },
            { id: 'workout', label: 'Treino do Dia', color: 'emerald' },
            { id: 'eatUntil18', label: 'Comer até as 18h', color: 'blue' },
            { id: 'eatSlowly', label: 'Comer Devagar', color: 'indigo' }
          ].map((habit) => {
            const colorMap: Record<string, { bg: string, border: string, text: string, dot: string }> = {
              rose: { bg: 'bg-rose-50', border: 'border-rose-200', text: 'text-rose-700', dot: 'bg-rose-500' },
              purple: { bg: 'bg-purple-50', border: 'border-purple-200', text: 'text-purple-700', dot: 'bg-purple-500' },
              orange: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', dot: 'bg-orange-500' },
              emerald: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', dot: 'bg-emerald-500' },
              blue: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', dot: 'bg-blue-500' },
              indigo: { bg: 'bg-indigo-50', border: 'border-indigo-200', text: 'text-indigo-700', dot: 'bg-indigo-500' }
            };
            const colors = colorMap[habit.color] || colorMap.rose;
            const isActive = !!habits[habit.id as keyof DailyHabits];

            return (
              <button
                key={habit.id}
                onClick={() => handleHabitToggle(habit.id as keyof DailyHabits)}
                className={`w-full flex items-center justify-between p-4 rounded-2xl border-2 transition-all duration-300 ${isActive
                  ? `${colors.bg} ${colors.border} shadow-sm`
                  : 'bg-white border-slate-100 hover:border-slate-200'
                  }`}
              >
                <span className={`text-sm font-bold ${isActive ? colors.text : 'text-slate-600'}`}>
                  {habit.label}
                </span>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${isActive
                  ? `${colors.dot} text-white scale-110`
                  : 'border-2 border-slate-200'
                  }`}>
                  {isActive && (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" /></svg>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        <div className="p-8 bg-slate-50 border-t border-slate-100">
          <button
            onClick={onClose}
            className="w-full bg-slate-900 text-white px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
          >
            Concluir Registro
          </button>
        </div>
      </div>
    </div>
  );
};

// Função para detectar automaticamente a área baseada em palavras-chave
const detectAreaFromTitle = (titulo: string): Categoria => {
  const tituloLower = titulo.toLowerCase();
  
  // Palavras-chave para CLC
  const clcKeywords = ['licitação', 'licitacao', 'pregão', 'pregao', 'contrato', 'dispensa', 'inexigibilidade', 'compra', 'aquisição', 'aquisicao'];
  
  // Palavras-chave para Assistência Estudantil
  const assistenciaKeywords = ['assistência', 'assistencia', 'estudantil', 'aluno', 'bolsa', 'auxílio', 'auxilio', 'permanência', 'permanencia'];
  
  // Verifica CLC primeiro
  if (clcKeywords.some(keyword => tituloLower.includes(keyword))) {
    return 'CLC';
  }
  
  // Verifica Assistência Estudantil
  if (assistenciaKeywords.some(keyword => tituloLower.includes(keyword))) {
    return 'ASSISTÊNCIA';
  }
  
  // Se não encontrar palavras-chave específicas, retorna GERAL
  return 'GERAL';
};

const WORK_ITEM_PHASES: { id: WorkItemPhase, label: string, icon: string }[] = [
  { id: 'planejamento', label: '1. Ideia', icon: '💡' },
  { id: 'prototipagem', label: '2. Protótipo', icon: '🎨' },
  { id: 'desenvolvimento', label: '3. Código', icon: '💻' },
  { id: 'testes', label: '4. Testes', icon: '🧪' },
  { id: 'producao', label: '5. Entrega', icon: '🚀' }
];

const WorkItemModal = ({
  workItem,
  onSave,
  onDelete,
  onClose
}: {
  workItem: WorkItem,
  onSave: (id: string, updates: Partial<WorkItem>) => void,
  onDelete: (id: string) => void,
  onClose: () => void
}) => {
  const [formData, setFormData] = useState<WorkItem>(workItem);
  const [activePhaseTab, setActivePhaseTab] = useState<WorkItemPhase>(workItem.fase);
  const isFrozen = workItem.fase === 'producao';

  const handlePhaseChange = (newPhase: WorkItemPhase) => {
    if (isFrozen && newPhase !== 'producao') {
      // Allow viewing other tabs even if frozen, but they remain read-only
      setActivePhaseTab(newPhase);
      return;
    }
    setFormData(prev => ({ ...prev, fase: newPhase }));
    setActivePhaseTab(newPhase);
  };

  const handleAddQualityLog = () => {
    const newLog: QualityLog = {
      id: Math.random().toString(36).substr(2, 9),
      tipo: 'Bug',
      descricao: '',
      status: 'Pendente',
      ambiente: 'Local',
      data_criacao: new Date().toISOString()
    };
    setFormData(prev => ({ ...prev, log_qualidade: [...prev.log_qualidade, newLog] }));
  };

  const updateQualityLog = (logId: string, updates: Partial<QualityLog>) => {
    setFormData(prev => ({
      ...prev,
      log_qualidade: prev.log_qualidade.map(log => log.id === logId ? { ...log, ...updates } : log)
    }));
  };

  const removeQualityLog = (logId: string) => {
    setFormData(prev => ({
      ...prev,
      log_qualidade: prev.log_qualidade.filter(log => log.id !== logId)
    }));
  };

  return (
    <div className="fixed inset-0 z-[160] flex items-center justify-center p-0 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-full md:h-auto md:max-w-4xl md:max-h-[90vh] flex flex-col rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        {/* Header */}
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex flex-col gap-6 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <span className="bg-violet-100 text-violet-700 px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest">Item de Trabalho</span>
                {isFrozen && <span className="bg-emerald-100 text-emerald-700 px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest">Congelado (Produção)</span>}
              </div>
              <h3 className="text-2xl font-black text-slate-900 tracking-tight">{workItem.titulo || 'Novo Item'}</h3>
            </div>
            <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
              <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>

          {/* Phase Stepper Tabs */}
          <div className="flex bg-slate-200/50 p-1 rounded-2xl overflow-x-auto scrollbar-hide">
            {WORK_ITEM_PHASES.map((phase) => {
              const isActive = activePhaseTab === phase.id;
              const isCurrentPhase = formData.fase === phase.id;
              return (
                <button
                  key={phase.id}
                  onClick={() => handlePhaseChange(phase.id)}
                  className={`flex-1 min-w-[120px] py-3 px-4 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${isActive ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                >
                  <span className={isActive ? 'opacity-100' : 'opacity-40'}>{phase.icon}</span>
                  {phase.label}
                  {isCurrentPhase && <div className="w-1.5 h-1.5 bg-violet-500 rounded-full"></div>}
                </button>
              );
            })}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-8 space-y-8 custom-scrollbar bg-white">
          {activePhaseTab === 'planejamento' && (
            <div className="space-y-6 animate-in slide-in-from-right-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Título</label>
                  <input
                    type="text"
                    disabled={isFrozen}
                    value={formData.titulo}
                    onChange={(e) => setFormData({ ...formData, titulo: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none transition-all disabled:opacity-60"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Origem da Demanda</label>
                  <input
                    type="text"
                    disabled={isFrozen}
                    value={formData.origem_demanda}
                    onChange={(e) => setFormData({ ...formData, origem_demanda: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none transition-all disabled:opacity-60"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Prioridade</label>
                  <select
                    disabled={isFrozen}
                    value={formData.prioridade}
                    onChange={(e) => setFormData({ ...formData, prioridade: e.target.value as WorkItemPriority })}
                    className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none transition-all disabled:opacity-60"
                  >
                    <option value="Baixa">Baixa</option>
                    <option value="Média">Média</option>
                    <option value="Alta">Alta</option>
                    <option value="Crítica">Crítica</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Link de Referência (Docs/Drive)</label>
                  <input
                    type="text"
                    disabled={isFrozen}
                    value={formData.link_referencia || ''}
                    onChange={(e) => setFormData({ ...formData, link_referencia: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none transition-all disabled:opacity-60"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Descrição do Problema / Funcionalidade</label>
                <textarea
                  rows={4}
                  disabled={isFrozen}
                  value={formData.descricao}
                  onChange={(e) => setFormData({ ...formData, descricao: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-medium text-slate-700 focus:ring-2 focus:ring-violet-500 outline-none transition-all resize-none disabled:opacity-60"
                />
              </div>
            </div>
          )}

          {activePhaseTab === 'prototipagem' && (
            <div className="space-y-6 animate-in slide-in-from-right-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Link AI Studio / Prompt</label>
                  <input
                    type="text"
                    disabled={isFrozen}
                    value={formData.link_ai_studio || ''}
                    onChange={(e) => setFormData({ ...formData, link_ai_studio: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none transition-all disabled:opacity-60"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Status de Validação</label>
                  <div className="flex items-center gap-4 h-[56px]">
                    <button
                      disabled={isFrozen}
                      onClick={() => setFormData({ ...formData, validado: !formData.validado })}
                      className={`flex-1 h-full rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all ${formData.validado ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-400'}`}
                    >
                      {formData.validado ? '✓ Estrutura Validada' : 'Pendente de Validação'}
                    </button>
                  </div>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Definições de Arquitetura (BD, Libs, etc)</label>
                <textarea
                  rows={6}
                  disabled={isFrozen}
                  value={formData.definicoes_arquitetura || ''}
                  onChange={(e) => setFormData({ ...formData, definicoes_arquitetura: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-mono text-slate-700 focus:ring-2 focus:ring-violet-500 outline-none transition-all resize-none disabled:opacity-60"
                  placeholder="Ex: Utilizar Firestore para persistência e React Hook Form para validação..."
                />
              </div>
            </div>
          )}

          {activePhaseTab === 'desenvolvimento' && (
            <div className="space-y-6 animate-in slide-in-from-right-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Branch / Versão Dev</label>
                  <input
                    type="text"
                    disabled={isFrozen}
                    value={formData.branch_versao || ''}
                    onChange={(e) => setFormData({ ...formData, branch_versao: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-mono text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none transition-all disabled:opacity-60"
                    placeholder="feat/nova-funcionalidade"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Dívida Técnica</label>
                  <button
                    disabled={isFrozen}
                    onClick={() => setFormData({ ...formData, divida_tecnica: !formData.divida_tecnica })}
                    className={`w-full h-[56px] rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all ${formData.divida_tecnica ? 'bg-amber-500 text-white' : 'bg-slate-100 text-slate-400'}`}
                  >
                    {formData.divida_tecnica ? '⚠ Possui Dívida Técnica' : 'Sem Dívida Técnica'}
                  </button>
                </div>
              </div>
              {formData.divida_tecnica && (
                <div className="space-y-2 animate-in zoom-in-95">
                  <label className="text-[10px] font-black text-amber-600 uppercase tracking-widest pl-1">Descrição da Dívida Técnica</label>
                  <textarea
                    rows={3}
                    disabled={isFrozen}
                    value={formData.divida_tecnica_descricao || ''}
                    onChange={(e) => setFormData({ ...formData, divida_tecnica_descricao: e.target.value })}
                    className="w-full bg-amber-50 border border-amber-100 rounded-2xl px-6 py-4 text-sm font-medium text-amber-900 focus:ring-2 focus:ring-amber-500 outline-none transition-all resize-none disabled:opacity-60"
                    placeholder="O que precisará ser revisto futuramente?"
                  />
                </div>
              )}
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Dependências / Impactos</label>
                <textarea
                  rows={3}
                  disabled={isFrozen}
                  value={formData.dependencias || ''}
                  onChange={(e) => setFormData({ ...formData, dependencias: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-medium text-slate-700 focus:ring-2 focus:ring-violet-500 outline-none transition-all resize-none disabled:opacity-60"
                  placeholder="Quais outros módulos podem ser impactados?"
                />
              </div>
            </div>
          )}

          {activePhaseTab === 'testes' && (
            <div className="space-y-6 animate-in slide-in-from-right-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-black text-slate-900 uppercase tracking-widest flex items-center gap-2">
                  <span className="w-2 h-2 bg-amber-500 rounded-full"></span>
                  Log de Qualidade
                </h4>
                {!isFrozen && (
                  <button
                    onClick={handleAddQualityLog}
                    className="bg-violet-600 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-violet-700 transition-all shadow-md shadow-violet-100"
                  >
                    + Registrar Ocorrência
                  </button>
                )}
              </div>

              <div className="space-y-4">
                {formData.log_qualidade.map((log) => (
                  <div key={log.id} className="bg-slate-50 rounded-[2rem] border border-slate-100 overflow-hidden">
                    <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-6">
                      <div className="space-y-2">
                        <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Tipo</label>
                        <select
                          disabled={isFrozen}
                          value={log.tipo}
                          onChange={(e) => updateQualityLog(log.id, { tipo: e.target.value as any })}
                          className="w-full bg-white border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-violet-500"
                        >
                          <option value="Bug">Bug (Erro)</option>
                          <option value="Melhoria">Melhoria (Ajuste)</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Ambiente</label>
                        <select
                          disabled={isFrozen}
                          value={log.ambiente}
                          onChange={(e) => updateQualityLog(log.id, { ambiente: e.target.value as any })}
                          className="w-full bg-white border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-violet-500"
                        >
                          <option value="Local">Ambiente Local</option>
                          <option value="Staging">Staging / Homologação</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</label>
                        <select
                          disabled={isFrozen}
                          value={log.status}
                          onChange={(e) => updateQualityLog(log.id, { status: e.target.value as any })}
                          className={`w-full bg-white border-none rounded-xl px-4 py-2 text-xs font-black uppercase tracking-widest ${log.status === 'Corrigido' ? 'text-emerald-600' : log.status === 'Pendente' ? 'text-rose-500' : 'text-slate-400'}`}
                        >
                          <option value="Pendente">Pendente</option>
                          <option value="Corrigido">Corrigido</option>
                          <option value="Ignorado">Ignorado</option>
                        </select>
                      </div>
                    </div>
                    <div className="px-6 pb-6 space-y-4">
                      <div className="space-y-2">
                        <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">O que aconteceu vs O que deveria acontecer</label>
                        <textarea
                          disabled={isFrozen}
                          value={log.descricao}
                          onChange={(e) => updateQualityLog(log.id, { descricao: e.target.value })}
                          className="w-full bg-white border-none rounded-xl px-4 py-3 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-violet-500 resize-none"
                          rows={2}
                        />
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="flex-1 space-y-2">
                          <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Evidência (Logs / Links)</label>
                          <input
                            type="text"
                            disabled={isFrozen}
                            value={log.evidencia || ''}
                            onChange={(e) => updateQualityLog(log.id, { evidencia: e.target.value })}
                            className="w-full bg-white border-none rounded-xl px-4 py-2 text-xs font-mono text-slate-600"
                            placeholder="URL do print ou log de erro..."
                          />
                        </div>
                        {!isFrozen && (
                          <button
                            onClick={() => removeQualityLog(log.id)}
                            className="mt-6 p-2 text-rose-300 hover:text-rose-600 hover:bg-white rounded-xl transition-all"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
                {formData.log_qualidade.length === 0 && (
                  <div className="py-12 text-center bg-slate-50 rounded-[2rem] border-2 border-dashed border-slate-100">
                    <p className="text-slate-300 font-black text-[10px] uppercase tracking-[0.2em] italic">Nenhuma ocorrência registrada</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {activePhaseTab === 'producao' && (
            <div className="space-y-6 animate-in slide-in-from-right-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Versão da Release</label>
                  <input
                    type="text"
                    value={formData.versao_release || ''}
                    onChange={(e) => setFormData({ ...formData, versao_release: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-black text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none"
                    placeholder="ex: v1.0.2"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Data de Publicação</label>
                  <input
                    type="date"
                    value={formData.data_publicacao || ''}
                    onChange={(e) => setFormData({ ...formData, data_publicacao: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Notas da Versão (Changelog Público)</label>
                <textarea
                  rows={8}
                  value={formData.changelog || ''}
                  onChange={(e) => setFormData({ ...formData, changelog: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-100 rounded-2xl px-6 py-4 text-sm font-medium text-slate-700 focus:ring-2 focus:ring-violet-500 outline-none resize-none"
                  placeholder="Consolide o que foi entregue nesta versão..."
                />
              </div>
            </div>
          )}

          {/* Audit Log / History (Always visible at the bottom) */}
          <div className="mt-12 pt-8 border-t border-slate-100">
            <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4">Histórico de Alterações</h4>
            <div className="space-y-3">
              {(formData.historico || []).slice().reverse().map((audit) => (
                <div key={audit.id} className="flex items-center gap-3 text-[10px] font-medium text-slate-500">
                  <span className="font-mono text-slate-300 shrink-0">{new Date(audit.timestamp).toLocaleString('pt-BR')}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-black text-slate-700 uppercase">{audit.usuario}</span>
                    <span className="text-slate-300">moveu de</span>
                    <span className="bg-slate-100 px-2 py-0.5 rounded uppercase font-bold">{audit.fase_anterior}</span>
                    <span className="text-slate-300">para</span>
                    <span className="bg-violet-100 text-violet-700 px-2 py-0.5 rounded uppercase font-bold">{audit.fase_nova}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4 flex-shrink-0">
          <button
            onClick={() => {
              if (window.confirm("Deseja realmente excluir este item?")) {
                onDelete(workItem.id);
                onClose();
              }
            }}
            className="px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest text-rose-600 hover:bg-rose-50 transition-all border border-rose-100"
          >
            Excluir
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
              if (!formData.titulo) {
                alert("O título é obrigatório.");
                return;
              }
              onSave(workItem.id, formData);
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

const WorkItemCreateModal = ({ sistemaId, onSave, onClose }: { sistemaId: string, onSave: (data: Partial<WorkItem>) => void, onClose: () => void }) => {
  const [formData, setFormData] = useState({
    titulo: '',
    descricao: '',
    origem_demanda: '',
    prioridade: 'Média' as WorkItemPriority,
    sistema_id: sistemaId
  });

  return (
    <div className="fixed inset-0 z-[160] flex items-center justify-center p-0 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-full md:h-auto md:max-w-xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <h3 className="text-2xl font-black text-slate-900 tracking-tight">Novo Item de Trabalho</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-8 space-y-6">
          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Título da Funcionalidade</label>
            <input
              type="text"
              autoFocus
              value={formData.titulo}
              onChange={e => setFormData({ ...formData, titulo: e.target.value })}
              className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 transition-all"
              placeholder="O que será desenvolvido?"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Origem da Demanda</label>
              <input
                type="text"
                value={formData.origem_demanda}
                onChange={e => setFormData({ ...formData, origem_demanda: e.target.value })}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-violet-500"
                placeholder="Quem solicitou?"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Prioridade</label>
              <select
                value={formData.prioridade}
                onChange={e => setFormData({ ...formData, prioridade: e.target.value as WorkItemPriority })}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-violet-500"
              >
                <option value="Baixa">Baixa</option>
                <option value="Média">Média</option>
                <option value="Alta">Alta</option>
                <option value="Crítica">Crítica</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Descrição</label>
            <textarea
              rows={3}
              value={formData.descricao}
              onChange={e => setFormData({ ...formData, descricao: e.target.value })}
              className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-medium text-slate-700 focus:ring-2 focus:ring-violet-500 transition-all resize-none"
              placeholder="Detalhes da demanda..."
            />
          </div>
        </div>

        <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4">
          <button onClick={onClose} className="flex-1 px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all">Cancelar</button>
          <button
            onClick={() => {
              if (!formData.titulo) {
                alert("Preencha o título.");
                return;
              }
              onSave(formData);
              onClose();
            }}
            className="flex-1 bg-violet-600 text-white px-8 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-violet-700 transition-all"
          >
            Criar Item
          </button>
        </div>
      </div>
    </div>
  );
};

const TaskCreateModal = ({ unidades, onSave, onClose }: { unidades: { id: string, nome: string }[], onSave: (data: Partial<Tarefa>) => void, onClose: () => void }) => {
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
  
  const [autoClassified, setAutoClassified] = useState(false);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-0 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-full md:h-auto md:max-w-xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <h3 className="text-2xl font-black text-slate-900 tracking-tight">Nova Ação</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-8 space-y-6">
          <div className="space-y-2">
            <label htmlFor="task-title-input" className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Título da Tarefa</label>
            <input
              id="task-title-input"
              type="text"
              autoFocus
              value={formData.titulo}
              onChange={e => {
                const newTitulo = e.target.value;
                const detectedArea = detectAreaFromTitle(newTitulo);
                
                setFormData({ 
                  ...formData, 
                  titulo: newTitulo,
                  // Só atualiza a categoria automaticamente se ainda não foi manualmente alterada
                  categoria: autoClassified ? formData.categoria : detectedArea
                });
              }}
              className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              placeholder="O que precisa ser feito?"
            />
            {formData.categoria !== 'NÃO CLASSIFICADA' && formData.categoria !== 'GERAL' && !autoClassified && (
              <p className="text-[9px] font-bold text-blue-600 pl-1 flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                Área detectada automaticamente. Você pode alterá-la abaixo.
              </p>
            )}
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
                onChange={e => {
                  setFormData({ ...formData, categoria: e.target.value as Categoria });
                  setAutoClassified(true); // Marca que o usuário alterou manualmente
                }}
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-black uppercase text-[10px] tracking-widest"
              >
                <option value="GERAL">Geral</option>
                <option value="NÃO CLASSIFICADA">Não Classificada</option>
                <option value="CLC">CLC</option>
                <option value="ASSISTÊNCIA">Assistência Estudantil</option>
                {unidades.filter(u => u.nome !== 'CLC' && u.nome !== 'Assistência Estudantil').map(u => (
                  <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                ))}
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

const TaskEditModal = ({ unidades, task, onSave, onDelete, onClose, pgcEntregas = [] }: { unidades: { id: string, nome: string }[], task: Tarefa, onSave: (id: string, updates: Partial<Tarefa>) => void, onDelete: (id: string) => void, onClose: () => void, pgcEntregas?: EntregaInstitucional[] }) => {
  const [formData, setFormData] = useState({
    titulo: task.titulo,
    data_inicio: task.data_inicio || (task.data_criacao ? task.data_criacao.split('T')[0] : ''),
    data_limite: task.data_limite === '-' ? '' : task.data_limite,
    data_criacao: task.data_criacao,
    status: task.status,
    categoria: task.categoria || 'NÃO CLASSIFICADA',
    notas: task.notas || '',
    acompanhamento: task.acompanhamento || [],
    is_single_day: !!task.is_single_day,
    entregas_relacionadas: task.entregas_relacionadas || []
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
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-0 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-full md:h-auto md:max-w-xl md:max-h-[90vh] flex flex-col rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
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
                className="w-full bg-slate-100 border-none rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-black uppercase text-[10px] tracking-widest"
              >
                <option value="GERAL">Geral</option>
                <option value="NÃO CLASSIFICADA">Não Classificada</option>
                <option value="CLC">CLC</option>
                <option value="ASSISTÊNCIA">Assistência Estudantil</option>
                {unidades.filter(u => u.nome !== 'CLC' && u.nome !== 'Assistência Estudantil').map(u => (
                  <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                ))}
              </select>
            </div>

            {/* Opção de Vínculo com PGC */}
            {(formData.categoria === 'CLC' || formData.categoria === 'ASSISTÊNCIA' || formData.categoria === 'ASSISTÊNCIA ESTUDANTIL') && (
              <div className="space-y-2 animate-in fade-in slide-in-from-top-2">
                <label className="text-[10px] font-black text-blue-600 uppercase tracking-widest pl-1">Vincular ação ao PGC</label>
                <select
                  value={formData.entregas_relacionadas[0] || ''}
                  onChange={e => setFormData({ ...formData, entregas_relacionadas: e.target.value ? [e.target.value] : [] })}
                  className="w-full bg-blue-50 border-blue-100 rounded-2xl px-6 py-4 text-xs font-bold text-blue-900 focus:ring-2 focus:ring-blue-500 transition-all"
                >
                  <option value="">Não vinculado ao PGC</option>
                  {pgcEntregas.map(e => (
                    <option key={e.id} value={e.id}>{e.entrega}</option>
                  ))}
                </select>
                <p className="text-[9px] font-medium text-blue-400 pl-1 uppercase tracking-wider">Selecione a entrega institucional correspondente</p>
              </div>
            )}
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

const TaskExecutionView = ({ task, tarefas, onSave, onClose }: { task: Tarefa, tarefas: Tarefa[], onSave: (id: string, updates: Partial<Tarefa>) => void, onClose: () => void }) => {
  const [newFollowUp, setNewFollowUp] = useState('');
  const [chatUrl, setChatUrl] = useState(task.chat_gemini_url || '');
  const [isTimerRunning, setIsTimerRunning] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [sessionTotalSeconds, setSessionTotalSeconds] = useState(task.tempo_total_segundos || 0);

  const nextTask = useMemo(() => {
    const now = new Date();
    const todayStr = now.toISOString().split('T')[0];
    const currentTimeInMinutes = now.getHours() * 60 + now.getMinutes();

    const todayTasks = tarefas
      .filter(t => t.data_limite === todayStr && normalizeStatus(t.status) !== 'concluido' && t.horario_inicio && t.id !== task.id)
      .sort((a, b) => {
        const [ha, ma] = a.horario_inicio!.split(':').map(Number);
        const [hb, mb] = b.horario_inicio!.split(':').map(Number);
        return (ha * 60 + ma) - (hb * 60 + mb);
      });

    return todayTasks.find(t => {
      const [h, m] = t.horario_inicio!.split(':').map(Number);
      return (h * 60 + m) > currentTimeInMinutes;
    });
  }, [tarefas, task.id]);

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

  const handleCompleteTask = () => {
    if (isTimerRunning) {
      handleToggleTimer(); // Stop timer and save time
    }
    if (window.confirm("Deseja realmente concluir esta tarefa?")) {
      onSave(task.id, { status: 'concluído' });
      onClose();
    }
  };

  return (
    <div className={`fixed inset-0 z-[200] flex flex-col transition-all duration-700 ease-in-out ${isTimerRunning ? 'bg-[#050505] text-white' : 'bg-[#050505] text-white'} overflow-hidden`}>
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
          {nextTask && (
            <div className="fixed top-12 left-1/2 -translate-x-1/2 z-[210] animate-in slide-in-from-top-8 duration-1000">
               <div className="bg-white/5 backdrop-blur-xl border border-white/10 px-8 py-4 rounded-full flex items-center gap-4 shadow-2xl">
                 <div className="w-2 h-2 bg-amber-500 rounded-full animate-pulse"></div>
                 <div className="flex flex-col">
                   <span className="text-[8px] font-black text-white/40 uppercase tracking-[0.2em]">Próxima Tarefa às {nextTask.horario_inicio}</span>
                   <span className="text-xs font-bold text-white/90">{nextTask.titulo}</span>
                 </div>
               </div>
            </div>
          )}

          <div className="text-center px-12 z-10">
            <span className="text-blue-400 text-[10px] font-black uppercase tracking-[0.4em] mb-6 block animate-pulse">Sessão em Execução</span>
            <h1 className="text-3xl md:text-5xl lg:text-6xl font-black tracking-tighter text-white/90 max-w-5xl mx-auto leading-tight">
              {task.titulo}
            </h1>
          </div>

          <div className="w-full max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div className="flex flex-col items-center justify-center">
              <div className="text-[10rem] md:text-[14rem] lg:text-[16rem] font-black tracking-tighter tabular-nums text-white leading-none drop-shadow-[0_0_50px_rgba(37,99,235,0.3)] relative">
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

              <button
                onClick={() => {
                  onSave(task.id, { status: task.status === 'concluído' ? 'em andamento' : 'concluído' });
                  if (task.status !== 'concluído') {
                    // Se não estava concluída e agora vai ficar, paramos o timer
                    handleToggleTimer();
                    onClose();
                  }
                }}
                className={`mt-6 flex items-center gap-2 px-8 py-3 rounded-full border text-xs font-black uppercase tracking-widest transition-all ${task.status === 'concluído' ? 'bg-emerald-500 text-white border-emerald-500' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500 hover:text-white'}`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                {task.status === 'concluído' ? 'Tarefa Concluída' : 'Concluir Tarefa'}
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
        <div className="flex-1 flex flex-col overflow-hidden animate-in fade-in duration-500 text-slate-300">
          <div className="p-10 pb-4">
            <span className="text-blue-600 text-[10px] font-black uppercase tracking-[0.3em] mb-2 block">Central de Execução</span>
            <h1 className="text-4xl font-black text-white tracking-tighter leading-none">{task.titulo}</h1>
          </div>

          <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-8 p-10 pt-4 overflow-hidden">
            {/* Esquerda: Botão de Play Gigante */}
            <div className="flex flex-col items-center justify-center bg-white/5 rounded-[3rem] border border-white/10 shadow-2xl relative group overflow-hidden">
              <div className="absolute inset-0 bg-blue-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-700"></div>

              <div className="relative text-center space-y-8 z-10">
                <div className="text-[10px] font-black text-slate-400 uppercase tracking-[0.4em]">Pronto para Começar?</div>
                <button
                  onClick={handleToggleTimer}
                  className="w-48 h-48 rounded-full bg-blue-600 text-white flex items-center justify-center shadow-[0_20px_60px_rgba(37,99,235,0.4)] hover:scale-110 active:scale-95 transition-all duration-500 group/play"
                >
                  <svg className="w-20 h-20 ml-3 group-hover/play:scale-110 transition-transform" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                </button>
                <div className="space-y-1">
                  <div className="text-4xl font-black text-white tabular-nums">
                    {formatTime(sessionTotalSeconds)}
                  </div>
                  <div className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Tempo Total Acumulado</div>
                </div>
              </div>

              {/* Status da Demanda no Canto */}
              <div className="absolute bottom-10 left-10 flex items-center gap-3">
                <button
                  onClick={handleCompleteTask}
                  className={`px-6 py-3 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all ${task.status === 'concluído' ? 'bg-emerald-500 text-white' : 'bg-white/10 text-slate-400 hover:bg-white/20'
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
                      <h4 className="text-xs font-black uppercase tracking-widest">Especialista Virtual</h4>
                      <p className="text-[8px] text-white/50 uppercase font-bold tracking-widest">Chat Contextual</p>
                    </div>
                  </div>
                  <a
                    href={task.chat_gemini_url || (task.categoria === 'CLC' ? "https://gemini.google.com/gem/096c0e51e1b9" : "https://gemini.google.com/")}
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
              <div className="flex-1 bg-white/5 rounded-[2.5rem] border border-white/10 shadow-xl p-8 flex flex-col overflow-hidden">
                <div className="flex items-center justify-between mb-4 flex-shrink-0">
                  <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Diário de Execução</h4>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newFollowUp}
                      onChange={e => setNewFollowUp(e.target.value)}
                      placeholder="Registre o que foi feito..."
                      className="bg-black/20 border border-white/10 rounded-lg px-4 py-2 text-[11px] font-medium outline-none focus:ring-1 focus:ring-blue-500 w-48 text-slate-300 placeholder:text-slate-600"
                      onKeyDown={e => e.key === 'Enter' && handleAddFollowUp()}
                    />
                    <button onClick={handleAddFollowUp} className="bg-white/10 text-slate-300 hover:text-white px-4 rounded-lg text-[9px] font-black uppercase transition-all">Add</button>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar space-y-3 pr-2">
                  {task.acompanhamento && task.acompanhamento.length > 0 ? (
                    task.acompanhamento.slice().reverse().map((entry, idx) => (
                      <div key={idx} className="bg-black/20 p-4 rounded-2xl border border-white/5 flex gap-4 hover:border-white/20 transition-colors">
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

const FerramentasView = ({ ideas, onDeleteIdea, onArchiveIdea, onAddTextIdea, onUpdateIdea, onConvertToLog, activeTool, setActiveTool, isAddingText, setIsAddingText }: {
  ideas: BrainstormIdea[],
  onDeleteIdea: (id: string) => void,
  onArchiveIdea: (id: string) => void,
  onAddTextIdea: (text: string) => void,
  onUpdateIdea: (id: string, text: string) => void,
  onConvertToLog: (idea: BrainstormIdea) => void,
  activeTool: 'brainstorming' | null,
  setActiveTool: (tool: 'brainstorming' | null) => void,
  isAddingText: boolean,
  setIsAddingText: (val: boolean) => void
}) => {
  const isProcessing = false;
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
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-200 shadow-xl hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-blue-50 rounded-2xl flex items-center justify-center text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Brainstorming</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Registre ideias rápidas para organizar depois.</p>
          </div>
        </button>

        <button
          disabled
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-100 shadow-sm opacity-60 grayscale cursor-not-allowed text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 relative overflow-hidden"
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
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-100 shadow-sm opacity-60 grayscale cursor-not-allowed text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 relative overflow-hidden"
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
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-100 shadow-sm opacity-60 grayscale cursor-not-allowed text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 relative overflow-hidden"
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

        {/* Inserção de Nova Ideia via Digitação */}
        <div className="max-w-4xl mx-auto w-full mb-12 animate-in slide-in-from-top-4 duration-500">
          <div className="bg-white p-2 rounded-[2rem] border-2 border-slate-100 shadow-xl flex items-center gap-4 focus-within:border-blue-500 transition-all">
            <input
              type="text"
              placeholder="Digite uma nova ideia..."
              className="flex-1 bg-transparent border-none outline-none px-6 py-4 text-sm font-bold text-slate-800 placeholder:text-slate-300"
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && textInput.trim()) {
                  onAddTextIdea(textInput);
                  setTextInput('');
                }
              }}
            />
            <button
              onClick={() => {
                if (textInput.trim()) {
                  onAddTextIdea(textInput);
                  setTextInput('');
                }
              }}
              className="bg-blue-600 text-white h-12 px-8 rounded-[1.25rem] text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all shadow-lg shadow-blue-100 active:scale-95"
            >
              Salvar Ideia
            </button>
          </div>
        </div>

        <div className="flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-2 md:gap-8 mb-32 md:mb-0">
          {activeIdeas.map(idea => (
            <div key={idea.id} className="bg-white p-5 md:p-8 rounded-none md:rounded-[2.5rem] border border-slate-100 md:border-slate-200 shadow-sm md:shadow-lg hover:shadow-md md:hover:shadow-2xl transition-all group flex flex-col relative overflow-hidden">
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
                        onClick={() => onConvertToLog(idea)}
                        className="text-slate-400 hover:text-violet-600 p-2 rounded-xl transition-colors"
                        title="Converter em Log"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
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
            <div className="col-span-full py-20 text-center border-4 border-dashed border-slate-100 rounded-none md:rounded-[3rem]">
              <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Nenhuma ideia ativa</p>
              <p className="text-slate-400 text-sm font-medium mt-2">Grave ou digite uma ideia para começar.</p>
            </div>
          )}
        </div>
      </div>

      {/* Input Flutuante Centralizado */}
      {isAddingText && (
        <div className="fixed bottom-24 left-4 right-4 md:left-1/2 md:-translate-x-1/2 w-auto md:w-full md:max-w-2xl z-[110] flex items-center gap-2 animate-in zoom-in-95 slide-in-from-bottom-10 bg-white/90 backdrop-blur-md p-4 rounded-none md:rounded-[2rem] shadow-2xl border border-slate-200">
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
    monthlyBudgets: {},
    sprintDates: { 1: "08", 2: "15", 3: "22", 4: "01" },
    emergencyReserveTarget: 0,
    emergencyReserveCurrent: 0,
    billCategories: ['Conta Fixa', 'Poupança', 'Investimento'],
    incomeCategories: ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']
  });


  // Health State
  const [healthWeights, setHealthWeights] = useState<HealthWeight[]>([]);
  const [healthDailyHabits, setHealthDailyHabits] = useState<DailyHabits[]>([]);
  const [healthSettings, setHealthSettings] = useState<HealthSettings>({ targetWeight: 0 });

  // Systems State
  const [sistemasDetalhes, setSistemasDetalhes] = useState<Sistema[]>([]);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [selectedWorkItem, setSelectedWorkItem] = useState<WorkItem | null>(null);
  const [isWorkItemCreateModalOpen, setIsWorkItemCreateModalOpen] = useState(false);
  const [workItemViewMode, setWorkItemViewMode] = useState<'list' | 'kanban'>('kanban');



  // Finance Sync
  useEffect(() => {
    const unsubSistemas = onSnapshot(collection(db, 'sistemas_detalhes'), (snapshot) => {
      setSistemasDetalhes(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Sistema)));
    });

    const unsubWorkItems = onSnapshot(collection(db, 'sistemas_work_items'), (snapshot) => {
      setWorkItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as WorkItem)));
    });

    const unsubTransactions = onSnapshot(collection(db, 'finance_transactions'), (snapshot) => {
      setFinanceTransactions(snapshot.docs
        .map(d => ({ id: d.id, ...d.data() } as FinanceTransaction))
        .filter(t => t.status !== 'deleted')
      );
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

    const unsubRubrics = onSnapshot(collection(db, 'bill_rubrics'), (snapshot) => {
      setBillRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as BillRubric)));
    });

    const unsubIncomeEntries = onSnapshot(collection(db, 'income_entries'), (snapshot) => {
      setIncomeEntries(snapshot.docs
        .map(d => ({ id: d.id, ...d.data() } as IncomeEntry))
        .filter(e => e.status !== 'deleted')
      );
    });

    const unsubIncomeRubrics = onSnapshot(collection(db, 'income_rubrics'), (snapshot) => {
      setIncomeRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as IncomeRubric)));
    });

    // Health Sync
    const unsubHealthWeights = onSnapshot(collection(db, 'health_weights'), (snapshot) => {
      setHealthWeights(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as HealthWeight)));
    });
    const unsubHealthHabits = onSnapshot(collection(db, 'health_daily_habits'), (snapshot) => {
      setHealthDailyHabits(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as DailyHabits)));
    });
    const unsubHealthSettings = onSnapshot(doc(db, 'health_settings', 'config'), (doc) => {
      if (doc.exists()) setHealthSettings(doc.data() as HealthSettings);
    });

    return () => {
      unsubSistemas();
      unsubTransactions();
      unsubGoals();
      unsubSettings();
      unsubFixedBills();
      unsubRubrics();
      unsubIncomeEntries();
      unsubIncomeRubrics();
      unsubHealthWeights();
      unsubHealthHabits();
      unsubHealthSettings();
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

            // Busca por ID original ou por período (título idêntico para Gasto Semanal)
            // Isso garante que se uma tarefa for apagada e recriada, ela atualize a transação existente em vez de duplicar
            const existingTransaction = financeTransactions.find(ft =>
              ft.originalTaskId === task.id ||
              (ft.category === 'Gasto Semanal' && ft.description.toLowerCase() === task.titulo.toLowerCase())
            );

            if (existingTransaction) {
              // UPDATE: Se já existe, verifica se houve mudança significativa
              const hasChanged = existingTransaction.amount !== amount ||
                existingTransaction.date !== transactionDate ||
                existingTransaction.originalTaskId !== task.id;

              if (hasChanged) {
                await updateDoc(doc(db, 'finance_transactions', existingTransaction.id), {
                  amount,
                  date: transactionDate,
                  sprint: sprintOriginal,
                  description: task.titulo,
                  originalTaskId: task.id // Atualiza o vínculo para a tarefa mais recente
                });

                if (existingTransaction.amount !== amount) {
                  showToast(`Valor atualizado: R$ ${amount.toLocaleString('pt-BR')}`, 'info');
                }
              }
            } else {
              // CREATE: Se não existe transação para este período/tarefa, cria uma nova
              await addDoc(collection(db, 'finance_transactions'), {
                description: task.titulo,
                amount,
                date: transactionDate,
                sprint: sprintOriginal,
                category: 'Gasto Semanal',
                originalTaskId: task.id
              });

              // Marca como concluída apenas se ainda não estiver
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
  const [billRubrics, setBillRubrics] = useState<BillRubric[]>([]);
  const [incomeEntries, setIncomeEntries] = useState<IncomeEntry[]>([]);
  const [incomeRubrics, setIncomeRubrics] = useState<IncomeRubric[]>([]);
  const [calendarViewMode, setCalendarViewMode] = useState<'month' | 'week'>('month');
  const [calendarDate, setCalendarDate] = useState(new Date());

  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeModule, setActiveModule] = useState<'home' | 'dashboard' | 'acoes' | 'financeiro' | 'saude'>('home');
  const [viewMode, setViewMode] = useState<'dashboard' | 'gallery' | 'pgc' | 'licitacoes' | 'assistencia' | 'sistemas' | 'finance' | 'saude' | 'ferramentas' | 'sistemas-dev'>('gallery');
  const [selectedTask, setSelectedTask] = useState<Tarefa | null>(null);

  // Modal Mode State
  const [taskModalMode, setTaskModalMode] = useState<'default' | 'edit' | 'execute'>('default');

  // Reset modal mode when selected task is cleared
  useEffect(() => {
    if (!selectedTask) {
      setTaskModalMode('default');
    }
  }, [selectedTask]);
  const [planosTrabalho, setPlanosTrabalho] = useState<PlanoTrabalho[]>([]);
  const [statusFilter, setStatusFilter] = useState<Status[]>(['em andamento']);
  const [areaFilter, setAreaFilter] = useState<string>('TODAS');
  const [sortOption, setSortOption] = useState<SortOption>('date-asc');
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [isNotificationCenterOpen, setIsNotificationCenterOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [syncData, setSyncData] = useState<any>(null);
  const [activePopup, setActivePopup] = useState<AppNotification | null>(null);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [appSettings, setAppSettings] = useState<AppSettings>(DEFAULT_APP_SETTINGS);
  const [isHabitsReminderOpen, setIsHabitsReminderOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'notifications' | 'context' | 'sistemas'>('notifications');

  // --- Notification System & App Settings ---

  useEffect(() => {
    const unsub = onSnapshot(doc(db, 'configuracoes', 'geral'), (snap) => {
      if (snap.exists()) {
        setAppSettings(snap.data() as AppSettings);
      }
    });
    return () => unsub();
  }, []);

  const handleUpdateAppSettings = async (newSettings: AppSettings) => {
    try {
      await setDoc(doc(db, 'configuracoes', 'geral'), newSettings);
      showToast("Configurações atualizadas!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao salvar configurações.", "error");
    }
  };

  const handleUpdateOverdueTasks = async () => {
    const todayStr = new Date().toISOString().split('T')[0];
    const overdue = tarefas.filter(t =>
      normalizeStatus(t.status) !== 'concluido' &&
      t.status !== 'excluído' as any &&
      t.data_limite && t.data_limite !== "-" && t.data_limite !== "0000-00-00" &&
      t.data_limite < todayStr
    );

    try {
      const promises = overdue.map(t => updateDoc(doc(db, 'tarefas', t.id), {
        data_limite: todayStr,
        data_atualizacao: new Date().toISOString()
      }));
      await Promise.all(promises);
      showToast(`${overdue.length} ações atualizadas para hoje!`, 'success');
      const targetNotif = notifications.find(n => n.title === "Ações Vencidas");
      if (targetNotif) handleDismissNotification(targetNotif.id);
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar tarefas.", 'error');
    }
  };

  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // Notification System Triggers (Time-based: Habits, Weigh-in)
  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date();
      const current_time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      
      // Calculate local date string (YYYY-MM-DD) to match local time configuration
      const offset = now.getTimezoneOffset() * 60000;
      const localDate = new Date(now.getTime() - offset);
      const todayStr = localDate.toISOString().split('T')[0];

      // 1. Habits Reminder
      if (appSettings.notifications.habitsReminder.enabled && current_time === appSettings.notifications.habitsReminder.time) {
        const lastOpen = localStorage.getItem('lastHabitsReminderDate');
        if (lastOpen !== todayStr) {
          setIsHabitsReminderOpen(true);
          localStorage.setItem('lastHabitsReminderDate', todayStr);
        }
      }

      // 2. Weigh-in Reminder (Bell Notification)
      if (appSettings.notifications.weighInReminder.enabled && current_time === appSettings.notifications.weighInReminder.time) {
        const lastWeighInRemind = localStorage.getItem('lastWeighInRemindDate');
        if (lastWeighInRemind !== todayStr) {
          const dayMatch = now.getDay() === appSettings.notifications.weighInReminder.dayOfWeek;
          let shouldRemind = false;

          if (appSettings.notifications.weighInReminder.frequency === 'weekly' && dayMatch) {
            shouldRemind = true;
          } else if (appSettings.notifications.weighInReminder.frequency === 'biweekly') {
            const weekRef = Math.floor(now.getTime() / (7 * 24 * 60 * 60 * 1000));
            if (dayMatch && weekRef % 2 === 0) shouldRemind = true;
          } else if (appSettings.notifications.weighInReminder.frequency === 'monthly' && now.getDate() === 1) {
            shouldRemind = true;
          }

          if (shouldRemind) {
            const newNotif: AppNotification = {
              id: Math.random().toString(36).substring(2, 9),
              title: "Lembrete de Pesagem",
              message: "Hora de registrar seu peso para acompanhar sua evolução no módulo Saúde!",
              type: 'info',
              timestamp: new Date().toISOString(),
              isRead: false,
              link: 'saude'
            };
            setNotifications(prev => [newNotif, ...prev]);
            setActivePopup(newNotif);
            localStorage.setItem('lastWeighInRemindDate', todayStr);
          }
        }
      }
      // 3. Daily Task Notifications
      const currentTimeInMinutes = now.getHours() * 60 + now.getMinutes();
      tarefas.forEach(t => {
        if (t.status === 'concluído' || t.data_limite !== todayStr) return;

        if (t.horario_inicio) {
          const [h, m] = t.horario_inicio.split(':').map(Number);
          const startMin = h * 60 + m;
          const diff = startMin - currentTimeInMinutes;
          const lastReminded = localStorage.getItem(`lastStartRemind_${t.id}`);
          if (diff === 15 && lastReminded !== todayStr) {
            const msg = `Sua tarefa "${t.titulo}" inicia em 15 minutos!`;
            showToast(msg, "info");
            if ("Notification" in window && Notification.permission === "granted") {
              new Notification("Hermes: Próxima Tarefa", { body: msg });
            }
            localStorage.setItem(`lastStartRemind_${t.id}`, todayStr);
          }
        }

        if (t.horario_fim) {
          const [h, m] = t.horario_fim.split(':').map(Number);
          const endMin = h * 60 + m;
          const diff = endMin - currentTimeInMinutes;
          const lastReminded = localStorage.getItem(`lastEndRemind_${t.id}`);
          if (diff === 15 && lastReminded !== todayStr) {
            const msg = `Sua tarefa "${t.titulo}" encerra em 15 minutos!`;
            showToast(msg, "info");
            if ("Notification" in window && Notification.permission === "granted") {
              new Notification("Hermes: Encerramento de Tarefa", { body: msg });
            }
            localStorage.setItem(`lastEndRemind_${t.id}`, todayStr);
          }
        }
      });
    }, 10000); // Check every 10 seconds to ensure we don't miss the minute
    return () => clearInterval(interval);
  }, [appSettings.notifications, tarefas]);

  // Data-driven Notifications (Budget, Overdue, PGC)
  useEffect(() => {
    const todayStr = new Date().toISOString().split('T')[0];
    const newNotifications: AppNotification[] = [];

    // 1. Overdue Tasks (Once a day check)
    if (appSettings.notifications.overdueTasks.enabled && localStorage.getItem('lastOverdueCheckDate') !== todayStr) {
      const overdueCount = tarefas.filter(t =>
        normalizeStatus(t.status) !== 'concluido' &&
        t.status !== 'excluído' as any &&
        t.data_limite && t.data_limite !== "-" && t.data_limite !== "0000-00-00" &&
        t.data_limite < todayStr
      ).length;

      if (overdueCount > 0) {
        newNotifications.push({
          id: `overdue-${todayStr}`,
          title: "Ações Vencidas",
          message: `Você tem ${overdueCount} ações fora do prazo. Que tal atualizá-las para hoje?`,
          type: 'warning',
          timestamp: new Date().toISOString(),
          isRead: false,
          link: 'acoes'
        });
        localStorage.setItem('lastOverdueCheckDate', todayStr);
      }
    }

    // 2. Budget Risk (Whenever data changes, throttled to once per day notification)
    if (appSettings.notifications.budgetRisk.enabled && localStorage.getItem('lastBudgetRiskNotifyDate') !== todayStr) {
      const now = new Date();
      const currentMonthStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
      const monthlyBudget = financeSettings.monthlyBudgets?.[currentMonthStr] || financeSettings.monthlyBudget;
      const totalSpend = financeTransactions.filter(t => t.date.startsWith(currentMonthStr)).reduce((acc, t) => acc + t.amount, 0);

      if (monthlyBudget > 0) {
        const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
        const currentDay = now.getDate();
        const budgetRatio = totalSpend / monthlyBudget;
        const timeRatio = currentDay / daysInMonth;

        if (budgetRatio > timeRatio * 1.15 && budgetRatio > 0.1) {
          newNotifications.push({
            id: `budget-${todayStr}`,
            title: "Alerta de Orçamento",
            message: `Atenção: Gastos elevados! Você já utilizou ${(budgetRatio * 100).toFixed(0)}% do orçamento em ${(timeRatio * 100).toFixed(0)}% do mês.`,
            type: 'warning',
            timestamp: new Date().toISOString(),
            isRead: false,
            link: 'financeiro'
          });
          localStorage.setItem('lastBudgetRiskNotifyDate', todayStr);
        }
      }
    }

    // 3. Audit PGC
    if (appSettings.notifications.pgcAudit.enabled && localStorage.getItem('lastPgcNotifyDate') !== todayStr) {
      const now = new Date();
      const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
      if ((daysInMonth - now.getDate()) <= appSettings.notifications.pgcAudit.daysBeforeEnd) {
        newNotifications.push({
          id: `pgc-${todayStr}`,
          title: "Auditoria PGC",
          message: "O mês está acabando. Verifique no módulo PGC se todas as entregas possuem ações vinculadas.",
          type: 'info',
          timestamp: new Date().toISOString(),
          isRead: false,
          link: 'pgc'
        });
        localStorage.setItem('lastPgcNotifyDate', todayStr);
      }
    }

    if (newNotifications.length > 0) {
      setNotifications(prev => {
        const existingIds = new Set(prev.map(n => n.id));
        const filteredNew = newNotifications.filter(n => !existingIds.has(n.id));
        return [...filteredNew, ...prev];
      });
    }
  }, [tarefas, financeTransactions, financeSettings, planosTrabalho, appSettings.notifications]);

  // Welcome Notification
  useEffect(() => {
    const hasSeenWelcome = localStorage.getItem('hasSeenWelcome');
    if (!hasSeenWelcome && notifications.length === 0) {
      const welcomeNote: AppNotification = {
        id: 'welcome',
        title: 'Bem-vindo ao Hermes',
        message: 'Sistema de notificações ativo. Configure suas preferências no ícone de engrenagem.',
        type: 'info',
        timestamp: new Date().toISOString(),
        isRead: false
      };
      setNotifications([welcomeNote]);
      setTimeout(() => setActivePopup(welcomeNote), 2000);
      localStorage.setItem('hasSeenWelcome', 'true');
    }
  }, []);

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
  const [activeFerramenta, setActiveFerramenta] = useState<'brainstorming' | null>(null);
  const [isBrainstormingAddingText, setIsBrainstormingAddingText] = useState(false);
  const [convertingIdea, setConvertingIdea] = useState<BrainstormIdea | null>(null);
  const [isSystemSelectorOpen, setIsSystemSelectorOpen] = useState(false);

  const handleUpdateTarefa = async (id: string, updates: Partial<Tarefa>, suppressToast = false) => {
    try {
      const docRef = doc(db, 'tarefas', id);
      await updateDoc(docRef, {
        ...updates,
        data_atualizacao: new Date().toISOString()
      });
      if (!suppressToast) showToast("Tarefa atualizada!", 'success');
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


  const handleUpdateIdea = async (id: string, text: string) => {
    try {
      await updateDoc(doc(db, 'brainstorm_ideas', id), { text });
      showToast("Ideia atualizada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar ideia.", "error");
    }
  };

  const handleFinalizeIdeaConversion = async (sistemaId: string) => {
    if (!convertingIdea) return;
    const unit = unidades.find(u => u.id === sistemaId);
    if (!unit) return;

    await handleCreateTarefa({
      titulo: convertingIdea.text,
      categoria: unit.nome,
      data_limite: new Date().toISOString().split('T')[0],
      status: 'em andamento'
    });

    await handleDeleteIdea(convertingIdea.id);
    setIsSystemSelectorOpen(false);
    setConvertingIdea(null);
    showToast("Ideia convertida em Log com sucesso!", "success");
  };

  const handleUpdateSistema = async (id: string, updates: Partial<Sistema>) => {
    try {
      // Check if document exists first or use setDoc with merge
      await setDoc(doc(db, 'sistemas_detalhes', id), {
        ...updates,
        data_atualizacao: new Date().toISOString()
      }, { merge: true });
      showToast("Sistema atualizado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar sistema.", "error");
    }
  };

  const handleCreateWorkItem = async (workItem: Partial<WorkItem>) => {
    try {
      await addDoc(collection(db, 'sistemas_work_items'), {
        ...workItem,
        fase: 'planejamento',
        data_criacao: new Date().toISOString(),
        data_atualizacao: new Date().toISOString(),
        historico: [{
          id: Math.random().toString(36).substr(2, 9),
          timestamp: new Date().toISOString(),
          usuario: 'Usuário',
          fase_anterior: 'novo',
          fase_nova: 'planejamento'
        }],
        log_qualidade: []
      } as any);
      showToast("Item de trabalho criado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao criar item.", "error");
    }
  };

  const handleUpdateWorkItem = async (id: string, updates: Partial<WorkItem>) => {
    try {
      // If phase changed, add to history
      const currentItem = workItems.find(w => w.id === id);
      if (updates.fase && currentItem && updates.fase !== currentItem.fase) {
        const audit: WorkItemAudit = {
          id: Math.random().toString(36).substr(2, 9),
          timestamp: new Date().toISOString(),
          usuario: 'Usuário',
          fase_anterior: currentItem.fase,
          fase_nova: updates.fase as WorkItemPhase
        };
        updates.historico = [...(currentItem.historico || []), audit];
      }

      await updateDoc(doc(db, 'sistemas_work_items', id), {
        ...updates,
        data_atualizacao: new Date().toISOString()
      } as any);
      showToast("Item de trabalho atualizado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar item.", "error");
    }
  };

  const handleDeleteWorkItem = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'sistemas_work_items', id));
      showToast("Item de trabalho removido.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover item.", "error");
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
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as { id: string, nome: string, palavras_chave?: string[] }));
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

  const handleAddUnidade = async (nome: string) => {
    try {
      await addDoc(collection(db, 'unidades'), {
        nome: nome,
        palavras_chave: []
      });
      showToast(`Área ${nome} adicionada!`, 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao adicionar área.", 'error');
    }
  };

  const handleDeleteUnidade = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'unidades', id));
      showToast("Área removida.", 'info');
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover área.", 'error');
    }
  };

  const handleUpdateUnidade = async (id: string, updates: any) => {
    try {
      await updateDoc(doc(db, 'unidades', id), updates);
      showToast("Área atualizada!", 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar área.", 'error');
    }
  };

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
      const docRef = await addDoc(collection(db, 'entregas'), {
        entrega: item.entrega,
        area: item.origem,
        unidade: item.unidade,
        mes: currentMonth,
        ano: currentYear
      });
      return docRef.id;
    } catch (err) {
      console.error(err);
      return null;
    }
  };

  // Health Handlers
  const handleUpdateHealthSettings = async (settings: HealthSettings) => {
    await setDoc(doc(db, 'health_settings', 'config'), settings);
    showToast("Meta de peso atualizada!", "success");
  };

  const handleAddHealthWeight = async (weight: number, date: string) => {
    await addDoc(collection(db, 'health_weights'), { weight, date });
    showToast("Peso registrado com sucesso!", "success");
  };

  const handleDeleteHealthWeight = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'health_weights', id));
      showToast("Registro de peso removido.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover registro.", "error");
    }
  };

  const handleUpdateFinanceGoal = async (goal: FinanceGoal) => {
    try {
      await updateDoc(doc(db, 'finance_goals', goal.id), goal as any);
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar meta.", "error");
    }
  };

  const handleReorderFinanceGoals = async (reorderedGoals: FinanceGoal[]) => {
    try {
      const promises = reorderedGoals.map((goal, index) =>
        updateDoc(doc(db, 'finance_goals', goal.id), { priority: index + 1 })
      );
      await Promise.all(promises);
      showToast("Prioridades atualizadas!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao reordenar metas.", "error");
    }
  };

  const handleDeleteFinanceGoal = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'finance_goals', id));
      showToast("Meta removida!", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover meta.", "error");
    }
  };

  const handleUpdateHealthHabits = async (date: string, habits: Partial<DailyHabits>) => {
    await setDoc(doc(db, 'health_daily_habits', date), habits, { merge: true });
  };

  const handleMarkNotificationRead = (id: string) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, isRead: true } : n));
  };

  const handleDismissNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
    if (activePopup?.id === id) setActivePopup(null);
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

    if (areaFilter !== 'TODAS') {
       const norm = (val: any) => (val || '').toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
       const filterNorm = norm(areaFilter);
       result = result.filter(t => {
         const cat = norm(t.categoria);
         if (filterNorm === 'CLC') return cat === 'CLC';
         if (filterNorm === 'ASSISTENCIA') return cat === 'ASSISTENCIA' || cat === 'ASSISTENCIA ESTUDANTIL';
         if (filterNorm === 'NAO CLASSIFICADA') return !t.categoria || cat === 'NAO CLASSIFICADA'; 
         return cat === filterNorm;
       });
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
  }, [tarefas, searchTerm, statusFilter, sortOption, areaFilter]);

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

      {/* Pop-up de Notificação */}
      {activePopup && (
        <div className="fixed bottom-8 left-4 right-4 md:left-8 md:right-auto z-[200] max-w-sm ml-auto mr-auto md:ml-0 md:mr-0 bg-white rounded-[2.5rem] shadow-[0_30px_60px_rgba(0,0,0,0.25)] border border-slate-100 overflow-hidden animate-in slide-in-from-bottom-12 duration-500">
          <div className={`h-2 w-full ${activePopup.type === 'success' ? 'bg-emerald-500' :
            activePopup.type === 'warning' ? 'bg-amber-500' :
              activePopup.type === 'error' ? 'bg-rose-500' : 'bg-blue-600'
            }`} />
          <div className="p-8">
            <div className="flex justify-between items-start mb-3">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em]">{activePopup.title}</span>
                <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse"></span>
              </div>
              <button onClick={() => setActivePopup(null)} className="text-slate-300 hover:text-slate-600 transition-colors p-1">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed font-bold">{activePopup.message}</p>
            <div className="mt-6 flex gap-3">
              <button
                onClick={() => setActivePopup(null)}
                className="flex-1 px-5 py-3 bg-slate-900 text-white rounded-xl text-[9px] font-black uppercase tracking-widest transition-all hover:bg-slate-800 shadow-lg shadow-slate-200"
              >
                Entendido
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Menu Inicial (Home) */}
      {activeModule === 'home' && (
        <div className="min-h-screen flex flex-col items-center justify-center p-0 md:p-8">
          <div className="max-w-6xl w-full px-0 md:px-4">
            {/* Logo e Título */}
            <div className="flex justify-end p-4 md:absolute md:top-12 md:right-12 gap-3">
              <div className="relative">
                <button
                  onClick={() => {
                    setActiveModule('acoes');
                    setViewMode('ferramentas');
                    setActiveFerramenta('brainstorming');
                  }}
                  className="bg-white border-2 border-slate-100 text-amber-500 p-4 rounded-2xl shadow-xl hover:bg-slate-50 transition-all active:scale-95 group"
                  aria-label="Ideias Rápidas"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                </button>
              </div>

              <div className="relative">
                <button
                  onClick={() => setIsSettingsModalOpen(true)}
                  className="bg-white border-2 border-slate-100 text-slate-700 p-4 rounded-2xl shadow-xl hover:bg-slate-50 transition-all active:scale-95 group"
                  aria-label="Configurações"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                </button>
              </div>

              <div className="relative">
                <button
                  onClick={() => setIsNotificationCenterOpen(!isNotificationCenterOpen)}
                  className="bg-white border-2 border-slate-100 text-slate-700 p-4 rounded-2xl shadow-xl hover:bg-slate-50 transition-all active:scale-95 group relative notification-trigger"
                  aria-label="Notificações"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                  {notifications.some(n => !n.isRead) && (
                    <span className="absolute top-4 right-4 w-3.5 h-3.5 bg-rose-500 border-4 border-white rounded-full"></span>
                  )}
                </button>
                <NotificationCenter
                  notifications={notifications}
                  onMarkAsRead={handleMarkNotificationRead}
                  onDismiss={handleDismissNotification}
                  isOpen={isNotificationCenterOpen}
                  onClose={() => setIsNotificationCenterOpen(false)}
                  onUpdateOverdue={handleUpdateOverdueTasks}
                />
              </div>
            </div>

            <div className="text-center mb-12 md:mb-16">
              <div className="flex items-center justify-center gap-4 mb-4">
                <img src="/logo.png" alt="Hermes" className="w-16 h-16 md:w-20 md:h-20 object-contain" />
                <h1 className="text-4xl md:text-6xl font-black tracking-tighter text-slate-900">HERMES</h1>
              </div>
              <p className="text-slate-500 text-sm md:text-base font-bold uppercase tracking-widest">Sistema de Gestão Integrada</p>
            </div>

            {/* Cards dos Módulos */}
            {/* Cards dos Módulos */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-0 md:gap-6">

              {/* Card Dashboard */}
              <button
                onClick={() => {
                  setActiveModule('dashboard');
                  setViewMode('dashboard');
                }}
                className="group bg-white border border-slate-200 md:border-2 rounded-none md:rounded-[2rem] p-4 md:p-6 hover:border-indigo-500 hover:z-10 hover:shadow-xl transition-all duration-300 active:scale-95 text-left relative overflow-hidden -ml-px -mt-px md:m-0"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                <div className="relative z-10">
                  <div className="w-10 h-10 md:w-12 md:h-12 bg-indigo-600 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300 text-white font-black">
                    <svg className="w-5 h-5 md:w-6 md:h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <h2 className="text-lg md:text-xl font-black text-slate-900 mb-2 group-hover:text-indigo-600 transition-colors">Dashboard</h2>
                  <p className="text-slate-500 text-xs font-medium leading-relaxed">Visão geral de todos os módulos</p>
                  <div className="mt-6 flex items-center gap-2 text-indigo-600 font-black text-xs uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                    <span>Acessar</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              </button>

              {/* Card Ações */}
              <button
                onClick={() => {
                  setActiveModule('acoes');
                  setViewMode('gallery');
                }}
                className="group bg-white border border-slate-200 md:border-2 rounded-none md:rounded-[2rem] p-4 md:p-6 hover:border-blue-500 hover:z-10 hover:shadow-xl transition-all duration-300 active:scale-95 text-left relative overflow-hidden -ml-px -mt-px md:m-0"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                <div className="relative z-10">
                  <div className="w-10 h-10 md:w-12 md:h-12 bg-blue-500 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                    <svg className="w-5 h-5 md:w-6 md:h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 14l2 2 4-4" />
                    </svg>
                  </div>
                  <h2 className="text-lg md:text-xl font-black text-slate-900 mb-2 group-hover:text-blue-600 transition-colors">Ações</h2>
                  <p className="text-slate-500 text-xs font-medium leading-relaxed">Tarefas, PGC e Plano de Trabalho</p>
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
                className="group bg-white border border-slate-200 md:border-2 rounded-none md:rounded-[2rem] p-4 md:p-6 hover:border-emerald-500 hover:z-10 hover:shadow-xl transition-all duration-300 active:scale-95 text-left relative overflow-hidden -ml-px -mt-px md:m-0"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                <div className="relative z-10">
                  <div className="w-10 h-10 md:w-12 md:h-12 bg-emerald-500 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                    <svg className="w-5 h-5 md:w-6 md:h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <h2 className="text-lg md:text-xl font-black text-slate-900 mb-2 group-hover:text-emerald-600 transition-colors">Financeiro</h2>
                  <p className="text-slate-500 text-xs font-medium leading-relaxed">Gestão financeira e orçamentária</p>
                  <div className="mt-6 flex items-center gap-2 text-emerald-600 font-black text-xs uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                    <span>Acessar</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              </button>

              {/* Card Saúde */}
              <button
                onClick={() => {
                  setActiveModule('saude');
                  setViewMode('saude');
                }}
                className="group bg-white border border-slate-200 md:border-2 rounded-none md:rounded-[2rem] p-4 md:p-6 hover:border-rose-500 hover:z-10 hover:shadow-xl transition-all duration-300 active:scale-95 text-left relative overflow-hidden -ml-px -mt-px md:m-0"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-rose-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                <div className="relative z-10">
                  <div className="w-10 h-10 md:w-12 md:h-12 bg-rose-500 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                    <svg className="w-5 h-5 md:w-6 md:h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                  </div>
                  <h2 className="text-lg md:text-xl font-black text-slate-900 mb-2 group-hover:text-rose-600 transition-colors">Saúde</h2>
                  <p className="text-slate-500 text-xs font-medium leading-relaxed">Acompanhamento e bem-estar</p>
                  <div className="mt-6 flex items-center gap-2 text-rose-600 font-black text-xs uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
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
                className="group bg-white border border-slate-200 md:border-2 rounded-none md:rounded-[2rem] p-4 md:p-6 hover:border-amber-500 hover:z-10 hover:shadow-xl transition-all duration-300 active:scale-95 text-left relative overflow-hidden -ml-px -mt-px md:m-0"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                <div className="relative z-10">
                  <div className="w-10 h-10 md:w-12 md:h-12 bg-amber-500 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                    <svg className="w-5 h-5 md:w-6 md:h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  </div>
                  <h2 className="text-lg md:text-xl font-black text-slate-900 mb-2 group-hover:text-amber-600 transition-colors">Ferramentas</h2>
                  <p className="text-slate-500 text-xs font-medium leading-relaxed">Brainstorming e IA</p>
                  <div className="mt-6 flex items-center gap-2 text-amber-600 font-black text-xs uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                    <span>Acessar</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              </button>

              {/* Card Sistemas */}
              <button
                onClick={() => {
                  setActiveModule('acoes');
                  setViewMode('sistemas-dev');
                }}
                className="group bg-white border border-slate-200 md:border-2 rounded-none md:rounded-[2rem] p-4 md:p-6 hover:border-violet-500 hover:z-10 hover:shadow-xl transition-all duration-300 active:scale-95 text-left relative overflow-hidden -ml-px -mt-px md:m-0"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                <div className="relative z-10">
                  <div className="w-10 h-10 md:w-12 md:h-12 bg-violet-500 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                    <svg className="w-5 h-5 md:w-6 md:h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                    </svg>
                  </div>
                  <h2 className="text-lg md:text-xl font-black text-slate-900 mb-2 group-hover:text-violet-600 transition-colors">Sistemas</h2>
                  <p className="text-slate-500 text-xs font-medium leading-relaxed">Ciclo de vida de software</p>
                  <div className="mt-6 flex items-center gap-2 text-violet-600 font-black text-xs uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
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
                    className="p-1.5 md:p-2 rounded-xl hover:bg-slate-100 transition-colors"
                    aria-label="Voltar ao Menu"
                  >
                    <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
                    </svg>
                  </button>
                  <img src="/logo.png" alt="Hermes" className="w-8 h-8 md:w-10 md:h-10 object-contain" />
                  <h1 className="text-base md:text-lg font-black tracking-tighter text-slate-900">HERMES</h1>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <button
                      onClick={() => {
                        setActiveModule('acoes');
                        setViewMode('ferramentas');
                        setActiveFerramenta('brainstorming');
                      }}
                       className="p-1.5 rounded-xl hover:bg-slate-100 transition-colors text-amber-500"
                      aria-label="Ideias Rápidas"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsSettingsModalOpen(true)}
                      className="p-1.5 rounded-xl hover:bg-slate-100 transition-colors"
                      aria-label="Configurações"
                    >
                      <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsNotificationCenterOpen(!isNotificationCenterOpen)}
                      className="p-1.5 rounded-xl hover:bg-slate-100 transition-colors relative notification-trigger"
                      aria-label="Notificações"
                    >
                      <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                      {notifications.some(n => !n.isRead) && (
                        <span className="absolute top-2.5 right-2.5 w-2.5 h-2.5 bg-rose-500 border-2 border-white rounded-full"></span>
                      )}
                    </button>
                    <NotificationCenter
                      notifications={notifications}
                      onMarkAsRead={handleMarkNotificationRead}
                      onDismiss={handleDismissNotification}
                      isOpen={isNotificationCenterOpen}
                      onClose={() => setIsNotificationCenterOpen(false)}
                      onUpdateOverdue={handleUpdateOverdueTasks}
                    />
                  </div>
                  {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && (
                    <button
                      onClick={() => setIsCreateModalOpen(true)}
                      className="bg-slate-900 text-white p-1.5 rounded-xl shadow-lg hover:bg-slate-800 transition-all active:scale-95"
                      aria-label="Criar Ação"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                    </button>
                  )}
                  <button
                    onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                    className="p-1.5 rounded-xl hover:bg-slate-100 transition-colors"
                    aria-label="Menu"
                  >
                    <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                  {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && activeModule !== 'financeiro' && activeModule !== 'saude' && activeModule !== 'dashboard' && (
                    <nav className="flex bg-slate-100 p-1 rounded-xl border border-slate-200">
                      <button
                        onClick={() => {
                          setViewMode('gallery');
                          setSearchTerm('');
                        }}
                        className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'gallery' && !searchTerm ? 'bg-white text-slate-900 shadow-sm border border-slate-100' : 'text-slate-500 hover:text-slate-800'}`}
                      >
                        Ações
                      </button>
                      <button onClick={() => setViewMode('pgc')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'pgc' ? 'bg-slate-900 text-white shadow-lg' : 'text-slate-500 hover:text-slate-800'}`}>PGC</button>
                    </nav>
                  )}
                </div>

                {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && (
                  <div className="flex items-center gap-4">
                    <div className="relative">
                      <button
                        onClick={() => {
                           setActiveModule('acoes');
                           setViewMode('ferramentas');
                           setActiveFerramenta('brainstorming');
                        }}
                         className="bg-white border border-slate-200 text-amber-500 p-2 rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative"
                        aria-label="Ideias Rápidas"
                      >
                         <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                      </button>
                    </div>
                    <div className="relative">
                      <button
                        onClick={() => setIsNotificationCenterOpen(!isNotificationCenterOpen)}
                        className="bg-white border border-slate-200 text-slate-700 p-2 rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative notification-trigger"
                        aria-label="Notificações"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                        {notifications.some(n => !n.isRead) && (
                          <span className="absolute top-2 right-2 w-2.5 h-2.5 bg-rose-500 border-2 border-white rounded-full"></span>
                        )}
                      </button>
                      <NotificationCenter
                        notifications={notifications}
                        onMarkAsRead={handleMarkNotificationRead}
                        onDismiss={handleDismissNotification}
                        isOpen={isNotificationCenterOpen}
                        onClose={() => setIsNotificationCenterOpen(false)}
                      />
                    </div>
                    {activeModule !== 'dashboard' && (
                      <div className="hidden lg:flex items-center bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 w-64 group focus-within:ring-2 focus-within:ring-blue-500 focus-within:bg-white transition-all">
                        <svg className="w-4 h-4 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        <input type="text" placeholder="Pesquisar..." className="bg-transparent border-none outline-none text-xs font-bold text-slate-900 w-full" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
                      </div>
                    )}
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
                  {viewMode !== 'ferramentas' && activeModule !== 'dashboard' && (
                    <>
                      <button
                        onClick={() => {
                          setViewMode('gallery');
                          setSearchTerm('');
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left ${viewMode === 'gallery' && !searchTerm ? 'bg-slate-900 text-white' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`}
                      >
                        📊 Ações
                      </button>
                      <button
                        onClick={() => {
                          setViewMode('pgc');
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-3 rounded-xl text-sm font-black uppercase tracking-wide transition-all text-left ${viewMode === 'pgc' ? 'bg-slate-900 text-white' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`}
                      >
                        📈 PGC
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
              {viewMode === 'dashboard' ? (
                <DashboardView
                  tarefas={tarefas}
                  financeTransactions={financeTransactions}
                  financeSettings={financeSettings}
                  fixedBills={fixedBills}
                  incomeEntries={incomeEntries}
                  healthWeights={healthWeights}
                  unidades={unidades}
                  sistemasDetalhes={sistemasDetalhes}
                  currentMonth={currentMonth}
                  currentYear={currentYear}
                />
              ) : viewMode === 'gallery' ? (
                <>
                  <div className="flex flex-col md:flex-row items-center justify-between mb-8 gap-4 px-4 md:px-0">
                    {/* Layout & Sort Controls */}
                    <div className="flex flex-wrap items-center gap-4 justify-center md:justify-start">
                      {/* Area Filter */}
                       <div className="relative group">
                        <select
                          value={areaFilter}
                          onChange={(e) => setAreaFilter(e.target.value)}
                          className="appearance-none bg-white pl-4 pr-10 py-2 rounded-xl border border-slate-200 text-[10px] font-black uppercase tracking-widest text-slate-700 outline-none focus:ring-2 focus:ring-slate-900 shadow-sm hover:border-slate-300 transition-all cursor-pointer"
                        >
                          <option value="TODAS">Todas as Áreas</option>
                          <option value="CLC">CLC</option>
                          <option value="ASSISTÊNCIA">Assistência Estudantil</option>
                          <option value="GERAL">Geral</option>
                          <option value="NÃO CLASSIFICADA">Não Classificada</option>
                          {unidades.filter(u => !['CLC', 'ASSISTÊNCIA', 'ASSISTÊNCIA ESTUDANTIL'].includes(u.nome.toUpperCase())).map(u => (
                            <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                          ))}
                        </select>
                        <div className="absolute inset-y-0 right-0 flex items-center px-3 pointer-events-none text-slate-400">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
                        </div>
                      </div>


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

                      <button
                        onClick={() => {
                          setDashboardViewMode('calendar');
                          setCalendarViewMode('day');
                          setCalendarDate(new Date());
                        }}
                        className="bg-white hover:bg-blue-50 border border-slate-200 text-slate-700 hover:text-blue-700 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-sm hover:shadow transition-all flex items-center gap-2 group"
                      >
                        <svg className="w-4 h-4 text-slate-400 group-hover:text-blue-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        Organizar o Dia
                      </button>
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
                      onTaskUpdate={handleUpdateTarefa}
                      onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
                    />
                  ) : (
                    <>
                      {searchTerm === 'filter:unclassified' ? (
                        <div className="animate-in bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl">
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
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <div className="text-[13px] font-bold text-slate-800 hover:text-blue-600 transition-colors leading-snug">
                                          {task.titulo}
                                        </div>
                                        {task.sync_status === 'new' && (
                                          <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse">
                                            Novo
                                          </span>
                                        )}
                                        {task.sync_status === 'updated' && (
                                          <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">
                                            Atualizada
                                          </span>
                                        )}
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
                        <div className="animate-in border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl bg-white">
                          {Object.keys(tarefasAgrupadas).length > 0 ? (
                            Object.entries(tarefasAgrupadas).map(([label, tasks]: [string, Tarefa[]]) => (
                              <div key={label} className="border-b last:border-b-0 border-slate-200">
                                <button
                                  onClick={() => toggleSection(label)}
                                  className="w-full px-6 py-3 bg-transparent border-b border-slate-100 flex items-center justify-between hover:bg-slate-50 transition-colors group"
                                >
                                  <div className="flex items-center gap-3">
                                    <span className="text-xs font-black text-slate-400 uppercase tracking-[0.2em]">{label}</span>
                                    <span className="text-[10px] font-bold text-slate-300">({tasks.length})</span>
                                  </div>
                                  <svg className={`w-4 h-4 text-slate-300 transition-transform duration-300 ${expandedSections.includes(label) ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
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
                                        onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                        onExecute={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
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
                          <div className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-sm opacity-60 hover:opacity-100 transition-opacity animate-in slide-in-from-top-4 duration-300">
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
                                    onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                    onExecute={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
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
                <CategoryView
                  tasks={tarefas}
                  viewMode={viewMode}
                  onSelectTask={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                  onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
                />
              ) : viewMode === 'sistemas' ? (
                <div className="animate-in space-y-8">
                  <div className="bg-white p-8 rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl">
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
                      <div key={sistema} className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-lg flex flex-col">
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
              ) : viewMode === 'plano-trabalho-REMOVED' ? (
                /* Removed Plano de Trabalho View as it is now inside PGC */
                null
              ) : viewMode === 'saude' ? (
                <HealthView
                  weights={healthWeights}
                  dailyHabits={healthDailyHabits}
                  settings={healthSettings}
                  onUpdateSettings={handleUpdateHealthSettings}
                  onAddWeight={handleAddHealthWeight}
                  onDeleteWeight={handleDeleteHealthWeight}
                  onUpdateHabits={handleUpdateHealthHabits}
                />
              ) : viewMode === 'ferramentas' ? (
                <FerramentasView
                  ideas={brainstormIdeas}
                  onDeleteIdea={handleDeleteIdea}
                  onArchiveIdea={handleArchiveIdea}
                  onAddTextIdea={handleAddTextIdea}
                  onUpdateIdea={handleUpdateIdea}
                  onConvertToLog={(idea) => {
                    setConvertingIdea(idea);
                    setIsSystemSelectorOpen(true);
                  }}
                  activeTool={activeFerramenta}
                  setActiveTool={setActiveFerramenta}
                  isAddingText={isBrainstormingAddingText}
                  setIsAddingText={setIsBrainstormingAddingText}
                />
              ) : viewMode === 'finance' ? (
                <FinanceView
                  transactions={financeTransactions}
                  goals={(() => {
                    const totalSavings = fixedBills
                      .filter(b => b.category === 'Poupança' && b.isPaid)
                      .reduce((acc, curr) => acc + curr.amount, 0);

                    const emergencyCurrent = financeSettings.emergencyReserveCurrent || 0;
                    let remaining = Math.max(0, totalSavings + emergencyCurrent - (financeSettings.emergencyReserveTarget || 0));
                    // Note: The logic here is a bit tricky. If "Poupança" bills are the ONLY thing that fills goals,
                    // and emergency reserve is a manual pot, then typically goals = totalSavings if emergency is full.
                    // But if emergency is manual, maybe the user wants: Remaining = total_saved_in_savings_bills.
                    // Let's assume goals are filled by "Poupança" items, but only if the manual emergency reserve is >= target.

                    const isEmergencyFull = emergencyCurrent >= (financeSettings.emergencyReserveTarget || 0);
                    let availableForGoals = isEmergencyFull ? totalSavings : 0;

                    return [...financeGoals].sort((a, b) => a.priority - b.priority).map(goal => {
                      const allocated = Math.min(availableForGoals, goal.targetAmount);
                      availableForGoals -= allocated;
                      return { ...goal, currentAmount: allocated };
                    });
                  })()}
                  emergencyReserve={{
                    target: financeSettings.emergencyReserveTarget || 0,
                    current: financeSettings.emergencyReserveCurrent || 0
                  }}
                  settings={financeSettings}
                  currentMonth={currentMonth}
                  currentYear={currentYear}
                  onMonthChange={(m, y) => {
                    setCurrentMonth(m);
                    setCurrentYear(y);
                  }}
                  currentMonthTotal={financeTransactions.filter(t => {
                    const d = new Date(t.date);
                    return d.getMonth() === currentMonth && d.getFullYear() === currentYear;
                  }).reduce((acc, curr) => acc + curr.amount, 0)}
                  currentMonthIncome={incomeEntries.filter(e => {
                    return e.month === currentMonth && e.year === currentYear;
                  }).reduce((acc, curr) => acc + curr.amount, 0)}
                  fixedBills={fixedBills}
                  billRubrics={billRubrics}
                  incomeEntries={incomeEntries}
                  incomeRubrics={incomeRubrics}
                  onAddRubric={async (rubric) => { await addDoc(collection(db, 'bill_rubrics'), rubric); }}
                  onUpdateRubric={async (rubric) => { await updateDoc(doc(db, 'bill_rubrics', rubric.id), rubric as any); }}
                  onDeleteRubric={async (id) => { await deleteDoc(doc(db, 'bill_rubrics', id)); }}
                  onAddIncomeRubric={async (rubric) => { await addDoc(collection(db, 'income_rubrics'), rubric); }}
                  onUpdateIncomeRubric={async (rubric) => { await updateDoc(doc(db, 'income_rubrics', rubric.id), rubric as any); }}
                  onDeleteIncomeRubric={async (id) => { await deleteDoc(doc(db, 'income_rubrics', id)); }}
                  onAddIncomeEntry={async (entry) => { await addDoc(collection(db, 'income_entries'), { ...entry, month: currentMonth, year: currentYear, status: 'active' }); }}
                  onUpdateIncomeEntry={async (entry) => { await updateDoc(doc(db, 'income_entries', entry.id), entry as any); }}
                  onDeleteIncomeEntry={async (id) => { await updateDoc(doc(db, 'income_entries', id), { status: 'deleted' }); }}
                  onUpdateSettings={(newSettings) => setDoc(doc(db, 'finance_settings', 'config'), newSettings)}
                  onAddGoal={(goal) => addDoc(collection(db, 'finance_goals'), { ...goal, priority: financeGoals.length + 1 })}
                  onUpdateGoal={handleUpdateFinanceGoal}
                  onDeleteGoal={handleDeleteFinanceGoal}
                  onReorderGoals={handleReorderFinanceGoals}
                  onAddBill={async (bill) => { await addDoc(collection(db, 'fixed_bills'), { ...bill, month: currentMonth, year: currentYear }); }}
                  onUpdateBill={async (bill) => { await updateDoc(doc(db, 'fixed_bills', bill.id), bill as any); }}
                  onDeleteBill={async (id) => { await deleteDoc(doc(db, 'fixed_bills', id)); }}
                  onAddTransaction={async (t) => { await addDoc(collection(db, 'finance_transactions'), { ...t, status: 'active' }); }}
                  onUpdateTransaction={async (t) => { await updateDoc(doc(db, 'finance_transactions', t.id), t as any); }}
                  onDeleteTransaction={async (id) => { await updateDoc(doc(db, 'finance_transactions', id), { status: 'deleted' }); }}
                />

              ) : viewMode === 'sistemas-dev' ? (
                <div className="space-y-8 animate-in fade-in duration-500 pb-20">
                  {!selectedSystemId ? (
                    /* VISÃO GERAL - LISTA DE SISTEMAS */
                    <>
                      <div className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] p-8 shadow-sm flex items-center justify-between">
                        <div>
                          <h2 className="text-3xl font-black text-slate-900 tracking-tight">Sistemas em Desenvolvimento</h2>
                          <p className="text-slate-500 font-bold mt-1">Gestão do Ciclo de Vida de Software</p>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="bg-violet-100 text-violet-700 px-4 py-2 rounded-xl text-sm font-black uppercase tracking-widest">
                            {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length} Sistemas
                          </div>
                          <button
                            onClick={() => {
                              setSettingsTab('sistemas');
                              setIsSettingsModalOpen(true);
                            }}
                            className="bg-slate-900 text-white px-6 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center gap-3"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                            Novo Sistema
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                        {unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(unit => {
                          const sysDetails = sistemasDetalhes.find(s => s.id === unit.id) || {
                            id: unit.id,
                            nome: unit.nome.replace('SISTEMA:', '').trim(),
                            status: 'ideia' as SistemaStatus,
                            data_criacao: new Date().toISOString(),
                            data_atualizacao: new Date().toISOString()
                          };
                          const systemName = unit.nome.replace('SISTEMA:', '').trim();
                          const ajustesPendentes = workItems.filter(w => w.sistema_id === unit.id && w.fase !== 'producao').length;

                          return (
                            <button
                              key={unit.id}
                              onClick={() => setSelectedSystemId(unit.id)}
                              className="bg-white border border-slate-200 rounded-none md:rounded-[2.5rem] p-8 text-left hover:shadow-xl hover:border-violet-300 transition-all group relative overflow-hidden"
                            >
                              <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                              <div className="relative z-10 space-y-6">
                                <div className="flex justify-between items-start">
                                  <div className="w-14 h-14 bg-violet-100 text-violet-600 rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform">
                                    <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                                  </div>
                                  <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest ${sysDetails.status === 'producao' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                                    {sysDetails.status}
                                  </span>
                                </div>
                                <div>
                                  <h3 className="text-xl font-black text-slate-900 mb-1 group-hover:text-violet-700 transition-colors">{systemName}</h3>
                                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                                    Atualizado em {formatDate(sysDetails.data_atualizacao?.split('T')[0] || new Date().toISOString().split('T')[0])}
                                  </p>
                                </div>
                                <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                                  <span className="text-xs font-bold text-slate-500">{ajustesPendentes} ajustes pendentes</span>
                                  <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center group-hover:bg-violet-500 group-hover:text-white transition-colors">
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
                                  </div>
                                </div>
                              </div>
                            </button>
                          );
                        })}

                        {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length === 0 && (
                          <div className="col-span-full text-center py-20 bg-slate-50 rounded-[2.5rem] border-2 border-dashed border-slate-200">
                            <p className="text-slate-400 font-bold text-lg mb-2">Nenhum sistema cadastrado</p>
                            <button onClick={() => { setIsSettingsModalOpen(true); }} className="bg-slate-900 text-white px-6 py-3 rounded-xl font-bold uppercase tracking-widest text-xs hover:bg-slate-800 transition-all mt-4">
                              Ir para Configurações
                            </button>
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    /* VISÃO DETALHADA - SISTEMA SELECIONADO */
                    (() => {
                      const unit = unidades.find(u => u.id === selectedSystemId);
                      if (!unit) return null;

                      const sysDetails = sistemasDetalhes.find(s => s.id === unit.id) || {
                        id: unit.id,
                        nome: unit.nome.replace('SISTEMA:', '').trim(),
                        status: 'ideia' as SistemaStatus,
                        data_criacao: new Date().toISOString(),
                        data_atualizacao: new Date().toISOString()
                      };

                      const systemName = unit.nome.replace('SISTEMA:', '').trim();
                      const systemWorkItems = workItems.filter(w => w.sistema_id === unit.id);
                      const ajustesPendentesCount = systemWorkItems.filter(w => w.fase !== 'producao').length;

                      const steps: SistemaStatus[] = ['ideia', 'prototipacao', 'desenvolvimento', 'testes', 'producao'];
                      const currentStepIndex = steps.indexOf(sysDetails.status);

                      return (
                        <div className="animate-in fade-in slide-in-from-bottom-8 duration-500">
                          {/* Navigation */}
                          <button
                            onClick={() => setSelectedSystemId(null)}
                            className="mb-8 flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold text-xs uppercase tracking-widest transition-colors"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
                            Voltar para Lista
                          </button>

                          <div className="bg-white border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden shadow-xl">
                            {/* Header Detalhado */}
                            <div className="bg-slate-900 p-8 md:p-12 text-white relative overflow-hidden">
                              <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/20 rounded-full -mr-20 -mt-20 blur-3xl"></div>
                              <div className="relative z-10 flex flex-col md:flex-row md:items-end justify-between gap-8">
                                <div className="space-y-4">
                                  <div className="inline-flex items-center gap-2 bg-white/10 px-3 py-1 rounded-lg backdrop-blur-sm border border-white/10">
                                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                                    <span className="text-[10px] font-black uppercase tracking-widest">{sysDetails.status}</span>
                                  </div>
                                  <h2 className="text-4xl md:text-5xl font-black tracking-tight">{systemName}</h2>
                                  <textarea
                                    value={sysDetails.objetivo_negocio || ''}
                                    onChange={(e) => handleUpdateSistema(unit.id, { objetivo_negocio: e.target.value })}
                                    placeholder="Descrição do objetivo do negócio (ex: Otimizar processos de...)"
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm font-medium text-slate-300 outline-none placeholder:text-slate-600 focus:ring-1 focus:ring-violet-500 mt-4 resize-none transition-all"
                                    rows={2}
                                  />
                                </div>
                                <div className="text-right">
                                  <div className="text-3xl font-black text-violet-400">{ajustesPendentesCount}</div>
                                  <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Ajustes Pendentes</div>
                                </div>
                              </div>
                            </div>

                            {/* Workflow Stepper */}
                            <div className="bg-slate-50 border-b border-slate-200 p-8 overflow-x-auto">
                              <div className="flex items-center justify-between min-w-[600px] relative">
                                {/* Linha de fundo */}
                                <div className="absolute top-1/2 left-0 w-full h-1 bg-slate-200 -z-0 rounded-full"></div>
                                {/* Linha de progresso */}
                                <div
                                  className="absolute top-1/2 left-0 h-1 bg-violet-500 -z-0 rounded-full transition-all duration-500 ease-out"
                                  style={{ width: `${(currentStepIndex / (steps.length - 1)) * 100}%` }}
                                ></div>

                                {steps.map((step, index) => {
                                  let state = 'upcoming'; // upcoming, current, completed
                                  if (index < currentStepIndex) state = 'completed';
                                  if (index === currentStepIndex) state = 'current';

                                  return (
                                    <button
                                      key={step}
                                      onClick={() => handleUpdateSistema(unit.id, { status: step })}
                                      className="relative z-10 flex flex-col items-center gap-3 group focus:outline-none"
                                    >
                                      <div className={`w-10 h-10 rounded-full flex items-center justify-center border-4 transition-all duration-300 ${state === 'completed' ? 'bg-violet-500 border-violet-500 text-white' : state === 'current' ? 'bg-white border-violet-500 text-violet-600 shadow-lg scale-110' : 'bg-white border-slate-200 text-slate-300 hover:border-slate-300'}`}>
                                        {state === 'completed' ? (
                                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                        ) : (
                                          <span className="text-xs font-black">{index + 1}</span>
                                        )}
                                      </div>
                                      <span className={`text-[10px] font-black uppercase tracking-widest transition-colors ${state === 'current' ? 'text-violet-600' : state === 'completed' ? 'text-slate-900' : 'text-slate-400'}`}>
                                        {step}
                                      </span>
                                    </button>
                                  );
                                })}
                              </div>
                            </div>

                            <div className="p-8 grid grid-cols-1 lg:grid-cols-3 gap-12">
                              {/* Coluna 1: Links e Recursos */}
                              <div className="lg:col-span-1 space-y-8">
                                <div>
                                  <h4 className="text-xs font-black text-slate-900 uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
                                    <span className="w-1 h-4 bg-violet-500 rounded-full"></span>
                                    Recursos Principais
                                  </h4>

                                  <div className="space-y-6">
                                    {/* Tecnologia Base */}
                                    <div className="group bg-slate-50 p-4 rounded-2xl border border-slate-100 hover:border-violet-200 hover:shadow-md transition-all">
                                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-2 mb-2">
                                        <svg className="w-4 h-4 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                                        Tecnologia Base
                                      </label>
                                      <input
                                        type="text"
                                        value={sysDetails.tecnologia_base || ''}
                                        onChange={(e) => handleUpdateSistema(unit.id, { tecnologia_base: e.target.value })}
                                        placeholder="Ex: React, Python, Flutter..."
                                        className="w-full bg-white border-none rounded-xl px-0 py-1 text-sm font-bold text-slate-700 outline-none placeholder:text-slate-300 focus:ring-0"
                                      />
                                    </div>

                                    {/* Repositório Principal */}
                                    <div className="group bg-slate-900 p-4 rounded-2xl border border-slate-800 hover:border-slate-600 hover:shadow-md transition-all">
                                      <div className="flex items-center justify-between mb-2">
                                        <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wide flex items-center gap-2">
                                          <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" /></svg>
                                          Repositório
                                        </label>
                                        {sysDetails.repositorio_principal && <span className="w-2 h-2 rounded-full bg-emerald-400"></span>}
                                      </div>
                                      <div className="flex gap-2">
                                        <input
                                          type="text"
                                          value={sysDetails.repositorio_principal || ''}
                                          onChange={(e) => handleUpdateSistema(unit.id, { repositorio_principal: e.target.value })}
                                          placeholder="github.com/usuario/projeto"
                                          className="w-full bg-slate-800 border-none rounded-xl px-0 py-1 text-sm font-bold text-white outline-none placeholder:text-slate-600 focus:ring-0"
                                        />
                                        {sysDetails.repositorio_principal && (
                                          <a href={sysDetails.repositorio_principal} target="_blank" rel="noreferrer" className="shrink-0 p-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600 transition-colors">
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                          </a>
                                        )}
                                      </div>
                                    </div>

                                    {/* Documentação */}
                                    <div className="group bg-slate-50 p-4 rounded-2xl border border-slate-100 hover:border-violet-200 hover:shadow-md transition-all">
                                      <div className="flex items-center justify-between mb-2">
                                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-2">
                                          <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                          Documentação
                                        </label>
                                        {sysDetails.link_documentacao && <span className="w-2 h-2 rounded-full bg-emerald-400"></span>}
                                      </div>
                                      <div className="flex gap-2">
                                        <input
                                          type="text"
                                          value={sysDetails.link_documentacao || ''}
                                          onChange={(e) => handleUpdateSistema(unit.id, { link_documentacao: e.target.value })}
                                          placeholder="https://notion.so/..."
                                          className="w-full bg-white border-none rounded-xl px-0 py-1 text-sm font-bold text-slate-700 outline-none placeholder:text-slate-300 focus:ring-0"
                                        />
                                        {sysDetails.link_documentacao && (
                                          <a href={sysDetails.link_documentacao} target="_blank" rel="noreferrer" className="shrink-0 p-2 bg-violet-100 text-violet-600 rounded-lg hover:bg-violet-200 transition-colors">
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                          </a>
                                        )}
                                      </div>
                                    </div>

                                    {/* AI Studio */}
                                    {(['prototipacao', 'desenvolvimento', 'testes', 'producao'].includes(sysDetails.status) || sysDetails.link_google_ai_studio) && (
                                      <div className="group bg-slate-50 p-4 rounded-2xl border border-slate-100 hover:border-blue-200 hover:shadow-md transition-all animate-in slide-in-from-left-4">
                                        <div className="flex items-center justify-between mb-2">
                                          <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-2">
                                            <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                            AI Studio
                                          </label>
                                          {sysDetails.link_google_ai_studio && <span className="w-2 h-2 rounded-full bg-emerald-400"></span>}
                                        </div>
                                        <div className="flex gap-2">
                                          <input
                                            type="text"
                                            value={sysDetails.link_google_ai_studio || ''}
                                            onChange={(e) => handleUpdateSistema(unit.id, { link_google_ai_studio: e.target.value })}
                                            placeholder="Link do Prompt..."
                                            className="w-full bg-white border-none rounded-xl px-0 py-1 text-sm font-bold text-slate-700 outline-none placeholder:text-slate-300 focus:ring-0"
                                          />
                                          {sysDetails.link_google_ai_studio && (
                                            <a href={sysDetails.link_google_ai_studio} target="_blank" rel="noreferrer" className="shrink-0 p-2 bg-blue-100 text-blue-600 rounded-lg hover:bg-blue-200 transition-colors">
                                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                            </a>
                                          )}
                                        </div>
                                      </div>
                                    )}

                                    {/* GitHub */}
                                    {(['desenvolvimento', 'testes', 'producao'].includes(sysDetails.status) || sysDetails.link_github) && (
                                      <div className="group bg-slate-900 p-4 rounded-2xl border border-slate-800 hover:border-slate-600 hover:shadow-md transition-all animate-in slide-in-from-left-4 delay-75">
                                        <div className="flex items-center justify-between mb-2">
                                          <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wide flex items-center gap-2">
                                            <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" /></svg>
                                            GitHub Repo
                                          </label>
                                          {sysDetails.link_github && <span className="w-2 h-2 rounded-full bg-emerald-400"></span>}
                                        </div>
                                        <div className="flex gap-2">
                                          <input
                                            type="text"
                                            value={sysDetails.link_github || ''}
                                            onChange={(e) => handleUpdateSistema(unit.id, { link_github: e.target.value })}
                                            placeholder="github.com/..."
                                            className="w-full bg-slate-800 border-none rounded-xl px-0 py-1 text-sm font-bold text-white outline-none placeholder:text-slate-600 focus:ring-0"
                                          />
                                          {sysDetails.link_github && (
                                            <a href={sysDetails.link_github} target="_blank" rel="noreferrer" className="shrink-0 p-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600 transition-colors">
                                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                            </a>
                                          )}
                                        </div>
                                      </div>
                                    )}

                                    {/* Produção */}
                                    {(['desenvolvimento', 'testes', 'producao'].includes(sysDetails.status) || sysDetails.link_hospedado) && (
                                      <div className="group bg-emerald-50 p-4 rounded-2xl border border-emerald-100 hover:border-emerald-300 hover:shadow-md transition-all animate-in slide-in-from-left-4 delay-100">
                                        <div className="flex items-center justify-between mb-2">
                                          <label className="text-[10px] font-bold text-emerald-600 uppercase tracking-wide flex items-center gap-2">
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>
                                            Link Hospedado
                                          </label>
                                          {sysDetails.link_hospedado && <span className="w-2 h-2 rounded-full bg-emerald-500"></span>}
                                        </div>
                                        <div className="flex gap-2">
                                          <input
                                            type="text"
                                            value={sysDetails.link_hospedado || ''}
                                            onChange={(e) => handleUpdateSistema(unit.id, { link_hospedado: e.target.value })}
                                            placeholder="https://..."
                                            className="w-full bg-white border-none rounded-xl px-0 py-1 text-sm font-bold text-emerald-800 outline-none placeholder:text-emerald-200 focus:ring-0"
                                          />
                                          {sysDetails.link_hospedado && (
                                            <a href={sysDetails.link_hospedado} target="_blank" rel="noreferrer" className="shrink-0 p-2 bg-emerald-200 text-emerald-700 rounded-lg hover:bg-emerald-300 transition-colors">
                                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                            </a>
                                          )}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>

                              {/* Coluna 2 e 3: Itens de Trabalho */}
                              <div className="lg:col-span-2 space-y-6">
                                <div className="bg-white border border-slate-200 rounded-[2.5rem] overflow-hidden flex flex-col min-h-[600px] shadow-sm">
                                  {/* Header da Seção de Itens */}
                                  <div className="p-8 border-b border-slate-100 bg-slate-50 flex flex-col md:flex-row md:items-center justify-between gap-6">
                                    <div className="flex items-center gap-4">
                                      <div className="p-3 bg-violet-600 text-white rounded-2xl shadow-lg shadow-violet-100">
                                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                                      </div>
                                      <div>
                                        <h4 className="text-xl font-black text-slate-900 tracking-tight">Itens de Trabalho</h4>
                                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em]">Fluxo de Desenvolvimento</p>
                                      </div>
                                    </div>

                                    <div className="flex items-center gap-4">
                                      <div className="bg-white p-1 rounded-xl border border-slate-200 flex shadow-sm">
                                        <button
                                          onClick={() => setWorkItemViewMode('kanban')}
                                          className={`px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${workItemViewMode === 'kanban' ? 'bg-slate-900 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                                        >
                                          Quadro
                                        </button>
                                        <button
                                          onClick={() => setWorkItemViewMode('list')}
                                          className={`px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${workItemViewMode === 'list' ? 'bg-slate-900 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                                        >
                                          Lista
                                        </button>
                                      </div>
                                      <button
                                        onClick={() => setIsWorkItemCreateModalOpen(true)}
                                        className="bg-violet-600 text-white px-6 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-violet-700 transition-all active:scale-95"
                                      >
                                        + Novo Item
                                      </button>
                                    </div>
                                  </div>

                                  {/* Visualização Kanban */}
                                  {workItemViewMode === 'kanban' ? (
                                    <div className="flex-1 overflow-x-auto p-8 bg-slate-50/50">
                                      <div className="flex gap-6 h-full min-h-[500px]">
                                        {WORK_ITEM_PHASES.map(phase => {
                                          const phaseItems = workItems.filter(w => w.sistema_id === unit.id && w.fase === phase.id);
                                          return (
                                            <div key={phase.id} className="flex-shrink-0 w-80 flex flex-col gap-4">
                                              <div className="flex items-center justify-between px-2">
                                                <div className="flex items-center gap-2">
                                                  <span className="text-lg">{phase.icon}</span>
                                                  <h5 className="text-[11px] font-black text-slate-900 uppercase tracking-widest">{phase.label.split('. ')[1]}</h5>
                                                </div>
                                                <span className="bg-white border border-slate-200 text-slate-400 px-2 py-0.5 rounded-full text-[10px] font-black">{phaseItems.length}</span>
                                              </div>

                                              <div className="flex-1 space-y-3">
                                                {phaseItems.map(item => (
                                                  <div
                                                    key={item.id}
                                                    onClick={() => setSelectedWorkItem(item)}
                                                    className="bg-white p-5 rounded-[1.5rem] border border-slate-200 shadow-sm hover:shadow-md hover:border-violet-400 transition-all cursor-pointer group animate-in fade-in slide-in-from-bottom-2"
                                                  >
                                                    <div className="flex justify-between items-start mb-3">
                                                      <span className={`text-[8px] font-black px-2 py-0.5 rounded uppercase tracking-wider ${
                                                        item.prioridade === 'Crítica' ? 'bg-rose-100 text-rose-600' :
                                                        item.prioridade === 'Alta' ? 'bg-orange-100 text-orange-600' :
                                                        item.prioridade === 'Média' ? 'bg-blue-100 text-blue-600' :
                                                        'bg-slate-100 text-slate-500'
                                                      }`}>
                                                        {item.prioridade}
                                                      </span>
                                                      <span className="text-[8px] font-black text-slate-300 uppercase">{formatDate(item.data_atualizacao.split('T')[0])}</span>
                                                    </div>
                                                    <h6 className="text-sm font-bold text-slate-800 leading-tight group-hover:text-violet-600 transition-colors line-clamp-2">{item.titulo}</h6>
                                                    <p className="text-[11px] text-slate-400 mt-2 line-clamp-2 leading-relaxed">{item.descricao}</p>

                                                    {item.log_qualidade?.length > 0 && (
                                                      <div className="mt-4 pt-4 border-t border-slate-50 flex items-center gap-3">
                                                        <span className="text-[9px] font-black text-rose-500 uppercase flex items-center gap-1">
                                                          <div className="w-1.5 h-1.5 bg-rose-500 rounded-full"></div>
                                                          {item.log_qualidade.filter(l => l.tipo === 'Bug' && l.status === 'Pendente').length} Bugs
                                                        </span>
                                                        <span className="text-[9px] font-black text-blue-500 uppercase flex items-center gap-1">
                                                          <div className="w-1.5 h-1.5 bg-blue-500 rounded-full"></div>
                                                          {item.log_qualidade.filter(l => l.tipo === 'Melhoria' && l.status === 'Pendente').length} Melhorias
                                                        </span>
                                                      </div>
                                                    )}
                                                  </div>
                                                ))}
                                                {phaseItems.length === 0 && (
                                                  <div className="h-24 border-2 border-dashed border-slate-200 rounded-[1.5rem] flex items-center justify-center">
                                                    <p className="text-[10px] font-black text-slate-300 uppercase tracking-widest italic">Vazio</p>
                                                  </div>
                                                )}
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  ) : (
                                    /* Visualização Lista */
                                    <div className="flex-1 overflow-y-auto">
                                      <table className="w-full text-left">
                                        <thead className="bg-slate-50 border-b border-slate-100">
                                          <tr>
                                            <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Funcionalidade</th>
                                            <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Fase Atual</th>
                                            <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Prioridade</th>
                                            <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Última Alt.</th>
                                          </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-50">
                                          {workItems.filter(w => w.sistema_id === unit.id).map(item => (
                                            <tr
                                              key={item.id}
                                              onClick={() => setSelectedWorkItem(item)}
                                              className="hover:bg-slate-50 transition-colors cursor-pointer group"
                                            >
                                              <td className="px-8 py-6">
                                                <div className="text-sm font-bold text-slate-800 group-hover:text-violet-600 transition-colors">{item.titulo}</div>
                                                <div className="text-[11px] text-slate-400 mt-1 line-clamp-1">{item.descricao}</div>
                                              </td>
                                              <td className="px-8 py-6">
                                                <span className="bg-violet-50 text-violet-700 px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border border-violet-100">
                                                  {item.fase}
                                                </span>
                                              </td>
                                              <td className="px-8 py-6">
                                                <span className={`text-[10px] font-black uppercase tracking-widest ${
                                                  item.prioridade === 'Crítica' ? 'text-rose-600' :
                                                  item.prioridade === 'Alta' ? 'text-orange-600' :
                                                  item.prioridade === 'Média' ? 'text-blue-600' :
                                                  'text-slate-400'
                                                }`}>
                                                  {item.prioridade}
                                                </span>
                                              </td>
                                              <td className="px-8 py-6 text-xs font-medium text-slate-400 tabular-nums">
                                                {formatDate(item.data_atualizacao.split('T')[0])}
                                              </td>
                                            </tr>
                                          ))}
                                          {workItems.filter(w => w.sistema_id === unit.id).length === 0 && (
                                            <tr>
                                              <td colSpan={4} className="py-20 text-center text-slate-300 font-black uppercase tracking-widest italic">Nenhum item registrado</td>
                                            </tr>
                                          )}
                                        </tbody>
                                      </table>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })()
                  )}
                </div>



              ) : (
                <div className="space-y-10">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 bg-white p-8 rounded-[2rem] border border-slate-200 shadow-xl">
                    <div>
                      <h3 className="text-4xl font-black text-slate-900 tracking-tighter">Gestão PGC</h3>
                      <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">{new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}</p>
                    </div>
                    <div className="flex items-center gap-4">
                      {pgcSubView === 'plano' && (
                        <button
                          onClick={() => setIsImportPlanOpen(true)}
                          className="bg-slate-900 text-white px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center gap-3"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                          Importar Planilha
                        </button>
                      )}
                      
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

                  <div className="flex border-b border-slate-200 gap-8">
                    <button
                      onClick={() => setPgcSubView('audit')}
                      className={`px-2 py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 ${pgcSubView === 'audit' ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                    >
                      Resumo de Atividades
                    </button>
                    <button
                      onClick={() => setPgcSubView('plano')}
                      className={`px-2 py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 ${pgcSubView === 'plano' ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                    >
                      Plano de Trabalho
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
                                <React.Fragment key={String(index)}>
                                  <PgcAuditRow
                                    item={item}
                                    entregaEntity={entregaEntity}
                                    atividadesRelacionadas={atividadesRelacionadas}
                                    tarefasRelacionadas={tarefasRelacionadas}
                                    onDrop={async (tarefaId) => {
                                      let targetId = entregaId;
                                      if (!targetId) {
                                        const newId = await handleCreateEntregaFromPlan(item);
                                        if (newId) targetId = newId;
                                      }
                                      if (targetId) handleLinkTarefa(tarefaId, targetId);
                                    }}
                                    onUnlinkTarefa={handleUnlinkTarefa}
                                    onSelectTask={setSelectedTask}
                                  />
                                </React.Fragment>
                              );
                            });
                          })()}
                        </div>
                      </div>
                    </div>
                  )}

                  {pgcSubView === 'plano' && (
                  <div className="animate-in space-y-8">
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
                  )}
                </div>
              )}
            </main>
          </div>
        </>
      )}

      <ToastContainer toasts={toasts} removeToast={removeToast} />

      {
        isCreateModalOpen && (
          <TaskCreateModal
            unidades={unidades}
            onSave={handleCreateTarefa}
            onClose={() => setIsCreateModalOpen(false)}
          />
        )
      }

      {
        isWorkItemCreateModalOpen && selectedSystemId && (
          <WorkItemCreateModal
            sistemaId={selectedSystemId}
            onSave={handleCreateWorkItem}
            onClose={() => setIsWorkItemCreateModalOpen(false)}
          />
        )
      }

      {
        selectedWorkItem && (
          <WorkItemModal
            workItem={selectedWorkItem}
            onSave={handleUpdateWorkItem}
            onDelete={handleDeleteWorkItem}
            onClose={() => setSelectedWorkItem(null)}
          />
        )
      }

      {
        selectedTask && (
          (taskModalMode === 'execute' || (taskModalMode === 'default' && selectedTask.categoria === 'CLC')) ? (
            <TaskExecutionView
              task={selectedTask}
              tarefas={tarefas}
              onSave={handleUpdateTarefa}
              onClose={() => setSelectedTask(null)}
            />
          ) : (
            <TaskEditModal
              unidades={unidades}
              task={selectedTask}
              onSave={handleUpdateTarefa}
              onDelete={handleDeleteTarefa}
              onClose={() => setSelectedTask(null)}
              pgcEntregas={pgcEntregas}
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
        isSettingsModalOpen && (
          <SettingsModal
            settings={appSettings}
            unidades={unidades}
            initialTab={settingsTab}
            onSave={handleUpdateAppSettings}
            onClose={() => {
              setIsSettingsModalOpen(false);
              setSettingsTab('notifications');
            }}
            onAddUnidade={handleAddUnidade}
            onDeleteUnidade={handleDeleteUnidade}
            onUpdateUnidade={handleUpdateUnidade}
          />
        )
      }

      {
        isHabitsReminderOpen && (
          <DailyHabitsModal
            habits={healthDailyHabits.find(h => h.id === new Date().toISOString().split('T')[0]) || {
              id: new Date().toISOString().split('T')[0],
              noSugar: false,
              noAlcohol: false,
              noSnacks: false,
              workout: false,
              eatUntil18: false,
              eatSlowly: false
            }}
            onUpdateHabits={handleUpdateHealthHabits}
            onClose={() => setIsHabitsReminderOpen(false)}
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

      {isSystemSelectorOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white w-full max-w-md rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
            <div className="p-8 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-xl font-black text-slate-900">Selecionar Sistema</h3>
              <button onClick={() => setIsSystemSelectorOpen(false)} className="p-2 hover:bg-slate-100 rounded-full">
                <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="p-8 space-y-3 max-h-[400px] overflow-y-auto custom-scrollbar">
              {unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(sistema => (
                <button
                  key={sistema.id}
                  onClick={() => handleFinalizeIdeaConversion(sistema.id)}
                  className="w-full text-left p-4 rounded-2xl border-2 border-slate-100 hover:border-violet-500 hover:bg-violet-50 transition-all flex items-center gap-3 group"
                >
                  <div className="w-10 h-10 bg-slate-100 group-hover:bg-violet-500 group-hover:text-white rounded-xl flex items-center justify-center transition-colors">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                  </div>
                  <span className="font-bold text-slate-700 group-hover:text-violet-700">{sistema.nome.replace('SISTEMA:', '').trim()}</span>
                </button>
              ))}
              {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length === 0 && (
                <p className="text-center text-slate-400 py-8 italic text-sm">Nenhum sistema cadastrado.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const container = document.getElementById('root');
if (container) {
  const root = createRoot(container);
  root.render(<App />);
}

