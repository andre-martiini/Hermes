
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Tarefa, Status, EntregaInstitucional, Prioridade, AtividadeRealizada,
  Afastamento, PlanoTrabalho, PlanoTrabalhoItem, Categoria, Acompanhamento,
  BrainstormIdea, FinanceTransaction, FinanceGoal, FinanceSettings,
  FixedBill, BillRubric, IncomeEntry, IncomeRubric, HealthWeight,
  DailyHabits, HealthSettings, HermesNotification, AppSettings,
  formatDate, formatDateLocalISO, Sistema, SistemaStatus, WorkItem, WorkItemPhase,
  WorkItemPriority, QualityLog, WorkItemAudit, GoogleCalendarEvent,
  PoolItem, CustomNotification, HealthExam
} from './types';
import HealthView from './HealthView';
import { STATUS_COLORS, PROJECT_COLORS } from './constants';
import { db, functions, messaging, auth, googleProvider, signInWithPopup, signOut, browserLocalPersistence, browserSessionPersistence, setPersistence } from './firebase';
import { onAuthStateChanged, User } from 'firebase/auth';
import { collection, onSnapshot, query, updateDoc, doc, addDoc, deleteDoc, setDoc, arrayUnion, arrayRemove } from 'firebase/firestore';
import { getToken, onMessage } from 'firebase/messaging';
import { httpsCallable } from 'firebase/functions';
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
    <div className="fixed bottom-4 sm:top-8 right-4 sm:right-8 left-4 sm:left-auto z-[200] flex flex-col gap-3 pointer-events-none">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`pointer-events-auto px-8 py-5 rounded-lg sm:rounded-lg md:rounded-[1.25rem] shadow-[0_20px_50px_rgba(0,0,0,0.2)] flex items-center gap-4 animate-in slide-in-from-bottom-12 sm:slide-in-from-right-12 fade-in duration-500 min-w-[320px] backdrop-blur-md ${toast.type === 'success' ? 'bg-emerald-500/95 text-white' :
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
    enablePush: true,
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
    },
    custom: []
  },
  pomodoro: {
    focusTime: 10,
    breakTime: 5,
    enableBeep: true
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

const formatWhatsAppText = (text: string) => {
  if (!text) return text;

  // Process block-level elements
  const lines = text.split('\n');
  const processedLines: React.JSX.Element[] = [];
  let currentList: React.JSX.Element[] = [];

  const flushList = () => {
    if (currentList.length > 0) {
      processedLines.push(<ul key={`list-${processedLines.length}`} className="list-disc ml-6 my-2 space-y-1">{currentList}</ul>);
      currentList = [];
    }
  };

  lines.forEach((line, index) => {
    // Lists
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      currentList.push(<li key={index} className="pl-1">{formatInlineWhatsAppText(line.trim().substring(2))}</li>);
    } else {
      flushList();

      // Blockquote
      if (line.trim().startsWith('>')) {
        processedLines.push(
          <blockquote key={index} className="border-l-4 border-slate-300 pl-4 py-1 my-2 italic text-slate-500 bg-slate-50/50 rounded-r-lg">
            {formatInlineWhatsAppText(line.trim().substring(1).trim())}
          </blockquote>
        );
      } else if (line.trim() === '') {
        processedLines.push(<div key={index} className="h-2"></div>);
      } else {
        processedLines.push(<div key={index}>{formatInlineWhatsAppText(line)}</div>);
      }
    }
  });
  flushList();

  return <div className="space-y-0.5">{processedLines}</div>;
};

const formatInlineWhatsAppText = (text: string) => {
  let parts: (string | React.JSX.Element)[] = [text];

  const applyRegex = (regex: RegExp, formatter: (match: string) => React.JSX.Element) => {
    const newParts: (string | React.JSX.Element)[] = [];
    parts.forEach(part => {
      if (typeof part !== 'string') {
        newParts.push(part);
        return;
      }

      let lastIndex = 0;
      let match;
      while ((match = regex.exec(part)) !== null) {
        if (match.index > lastIndex) {
          newParts.push(part.substring(lastIndex, match.index));
        }
        newParts.push(formatter(match[1]));
        lastIndex = regex.lastIndex;
      }
      if (lastIndex < part.length) {
        newParts.push(part.substring(lastIndex));
      }
    });
    parts = newParts;
  };

  // Monospace ```text``` (do this first to avoid other formatting inside)
  applyRegex(/```([\s\S]+?)```/g, (inner) => <pre className="bg-slate-100/80 p-3 rounded-lg font-mono text-[11px] my-2 overflow-x-auto border border-slate-200 text-slate-800">{inner}</pre>);

  // Inline Code `text`
  applyRegex(/`([^`]+?)`/g, (inner) => <code className="bg-slate-100 px-1.5 py-0.5 rounded font-mono text-[11px] text-pink-600 border border-slate-200">{inner}</code>);

  // Bold *text*
  applyRegex(/\*([^\*]+?)\*/g, (inner) => <strong className="font-black text-slate-900">{inner}</strong>);

  // Italic _text_
  applyRegex(/_([^_]+?)_/g, (inner) => <em className="italic">{inner}</em>);

  // Strikethrough ~text~
  applyRegex(/~([^~]+?)~/g, (inner) => <del className="line-through opacity-60">{inner}</del>);

  return <>{parts.map((part, i) => <React.Fragment key={i}>{part}</React.Fragment>)}</>;
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
      className={`bg-white border border-slate-200 p-3 rounded-lg md:rounded-xl shadow-sm hover:shadow-md hover:border-blue-400 transition-all ${onClick ? 'cursor-pointer' : 'cursor-grab'} active:cursor-grabbing w-full md:w-[280px] group`}
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
          className="px-4 py-2 bg-white border border-slate-200 text-slate-600 rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-wider hover:bg-slate-50 transition-colors flex items-center gap-2 shadow-sm"
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
            <div key={at.id} className="p-4 rounded-none md:rounded-2xl bg-white border border-slate-200 shadow-sm hover:border-slate-300 transition-all">
              <p className="text-[8px] font-black text-slate-400 uppercase mb-1">{formatDate(at.data_inicio)}</p>
              <p className="text-[11px] font-bold text-slate-700 leading-tight">{at.descricao_atividade}</p>
              <div className="mt-2 text-[8px] font-black text-blue-500 uppercase tracking-widest">Atividade PGD</div>
            </div>
          ))}
          {tarefasRelacionadas.map(t => (
            <div
              key={t.id}
              onClick={() => onSelectTask(t)}
              className="p-4 rounded-none md:rounded-2xl bg-blue-50/30 border border-blue-100 shadow-sm hover:border-blue-300 hover:bg-blue-50/50 transition-all cursor-pointer group/task relative pr-10"
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
            <div className="col-span-full py-8 text-center bg-slate-50/50 rounded-none md:rounded-2xl border-2 border-dashed border-slate-100">
              <p className="text-slate-300 text-[10px] font-black uppercase tracking-widest italic">Nenhuma ação vinculada a esta entrega</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// --- Components ---

const ConsolidatedBacklogView = ({
  unidades,
  workItems,
  onClose,
  onUpdateWorkItem,
  onDeleteWorkItem
}: {
  unidades: { id: string, nome: string }[],
  workItems: WorkItem[],
  onClose: () => void,
  onUpdateWorkItem: (id: string, updates: Partial<WorkItem>) => void,
  onDeleteWorkItem: (id: string) => void
}) => {
  const [expandedSystems, setExpandedSystems] = useState<string[]>([]);

  const systemsWithItems = useMemo(() => {
    return unidades
      .filter(u => u.nome.startsWith('SISTEMA:'))
      .map(u => ({
        ...u,
        items: workItems.filter(w => w.sistema_id === u.id && !w.concluido)
      }))
      .filter(s => s.items.length > 0);
  }, [unidades, workItems]);

  const toggleSystem = (id: string) => {
    setExpandedSystems(prev =>
      prev.includes(id) ? prev.filter(sysId => sysId !== id) : [...prev, id]
    );
  };

  return (
    <div className="animate-in fade-in slide-in-from-bottom-8 duration-500">
      <div className="bg-white border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden shadow-xl">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight">Painel Geral de Demandas</h3>
            <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">Backlog Consolidado por Sistema</p>
          </div>
          <button onClick={onClose} className="p-3 bg-white border border-slate-200 rounded-full hover:bg-slate-50 transition-colors">
            <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="divide-y divide-slate-100">
          {systemsWithItems.map(system => (
            <div key={system.id} className="bg-white">
              <button
                onClick={() => toggleSystem(system.id)}
                className="w-full p-8 flex items-center justify-between hover:bg-slate-50 transition-colors group"
              >
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-violet-100 text-violet-600 rounded-2xl flex items-center justify-center">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                  </div>
                  <div className="text-left">
                    <h4 className="text-lg font-black text-slate-900">{system.nome.replace('SISTEMA:', '').trim()}</h4>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{system.items.length} itens pendentes</p>
                  </div>
                </div>
                <svg className={`w-6 h-6 text-slate-300 transition-transform duration-300 ${expandedSystems.includes(system.id) ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {expandedSystems.includes(system.id) && (
                <div className="p-8 pt-0 space-y-3 animate-in slide-in-from-top-4 duration-300">
                  {system.items.map(item => (
                    <div key={item.id} className="p-4 bg-slate-50 border border-slate-100 rounded-2xl flex items-center justify-between group/item">
                      <div className="flex items-center gap-4">
                        <button
                          onClick={() => onUpdateWorkItem(item.id, { concluido: true, data_conclusao: new Date().toISOString() })}
                          className="w-6 h-6 rounded-lg border-2 border-slate-200 hover:border-emerald-500 hover:bg-emerald-50 transition-all flex items-center justify-center text-transparent hover:text-emerald-500"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                        </button>
                        <span className="text-sm font-bold text-slate-700">{item.descricao}</span>
                      </div>
                      <button
                        onClick={() => { if (window.confirm("Excluir item?")) onDeleteWorkItem(item.id); }}
                        className="opacity-0 group-hover/item:opacity-100 p-2 text-slate-300 hover:text-rose-500 transition-all"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          {systemsWithItems.length === 0 && (
            <div className="p-20 text-center">
              <p className="text-slate-300 font-black text-sm uppercase tracking-widest italic">Nenhuma demanda pendente em nenhum sistema.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const DayView = ({
  tasks,
  googleEvents = [],
  currentDate,
  onTaskClick,
  onTaskUpdate,
  onExecuteTask
}: {
  tasks: Tarefa[],
  googleEvents?: GoogleCalendarEvent[],
  currentDate: Date,
  onTaskClick: (t: Tarefa) => void,
  onTaskUpdate: (id: string, updates: Partial<Tarefa>, suppressToast?: boolean) => void,
  onExecuteTask: (t: Tarefa) => void
}) => {
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
  const [resizing, setResizing] = useState<{ id: string, type: 'top' | 'bottom', startY: number, startMin: number } | null>(null);
  const [dragging, setDragging] = useState<{ id: string, startY: number, startMin: number } | null>(null);
  const [currentTime, setCurrentTime] = useState(new Date());
  const sidebarRef = useRef<HTMLDivElement>(null);

  const [confirmAction, setConfirmAction] = useState<{ taskId: string, newStatus: 'em andamento' | 'concluído' } | null>(null);

  const confirmTaskCompletion = () => {
    if (confirmAction) {
      onTaskUpdate(confirmAction.taskId, { status: confirmAction.newStatus });
      setConfirmAction(null);
    }
  };

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
  const isToday = formatDateLocalISO(currentDate) === formatDateLocalISO(new Date());

  const dayStr = formatDateLocalISO(currentDate);
  const { allDayEvents, timedEvents } = useMemo(() => {
    const dayEvents = googleEvents.filter(e => {
      const startStr = e.data_inicio.split('T')[0];
      const endStr = e.data_fim.split('T')[0];

      const isTimed = e.data_inicio.includes('T');
      // Se o início coincide
      if (startStr === dayStr) return true;

      // Se o evento dura múltiplos dias, verificamos se o dia atual está no intervalo
      if (startStr !== endStr) {
        return isTimed ? (dayStr >= startStr && dayStr <= endStr) : (dayStr >= startStr && dayStr < endStr);
      }

      return false;
    });

    return {
      allDayEvents: dayEvents.filter(e => !e.data_inicio.includes('T')),
      timedEvents: dayEvents.filter(e => e.data_inicio.includes('T'))
    };
  }, [googleEvents, dayStr]);

  const dayTasks = useMemo(() => tasks.filter(t => {
    if (t.status === 'excluído' as any) return false;

    // Se a tarefa já tem horário definido (está alocada), respeitamos estritamente a data definida
    if (t.horario_inicio && t.data_inicio) {
      return t.data_inicio === dayStr;
    }

    const end = t.data_limite;
    const hasDeadline = end && end !== '-' && end !== '0000-00-00';

    // Se não tem prazo, aparece sempre no sidebar para alocação (Critério: ações sem data definida)
    if (!hasDeadline) return true;

    // Critérios únicos para o campo aguardando alocação:
    // - As ações que são daquele dia (dayStr === end)
    // - As ações que são dos dias anteriores àquele dia (dayStr > end)
    // Ou seja: dayStr >= end
    return dayStr >= end;
  }), [tasks, dayStr]);

  const positionedEvents = useMemo(() => {
    const allItems = [
      ...timedEvents.map(e => ({
        id: e.id,
        title: e.titulo,
        start: timeToMinutes(e.data_inicio.includes('T') ? e.data_inicio.split('T')[1].substring(0, 5) : '00:00'),
        end: timeToMinutes(e.data_fim.includes('T') ? e.data_fim.split('T')[1].substring(0, 5) : '23:59'),
        type: 'google' as const,
        data: e
      })),
      ...dayTasks.filter(t => t.horario_inicio).map(t => ({
        id: t.id,
        title: t.titulo,
        start: timeToMinutes(t.horario_inicio || '00:00'),
        end: timeToMinutes(t.horario_fim || '01:00'),
        type: 'task' as const,
        data: t
      }))
    ].sort((a, b) => a.start - b.start || b.end - a.end);

    const clusters: (any[])[] = [];
    let lastEnd = -1;

    allItems.forEach(item => {
      if (item.start >= lastEnd) {
        clusters.push([item]);
      } else {
        clusters[clusters.length - 1].push(item);
      }
      lastEnd = Math.max(lastEnd, item.end);
    });

    return clusters.flatMap(cluster => {
      const columns: (any[])[] = [];
      return cluster.map(item => {
        let colIndex = 0;
        while (columns[colIndex] && columns[colIndex].some(other => item.start < other.end && item.end > other.start)) {
          colIndex++;
        }
        if (!columns[colIndex]) columns[colIndex] = [];
        columns[colIndex].push(item);

        return {
          ...item,
          colIndex
        };
      }).map((item, _, clusterResults) => {
        const maxCol = Math.max(...clusterResults.map(i => i.colIndex)) + 1;
        return { ...item, totalCols: maxCol };
      });
    });
  }, [timedEvents, dayTasks]);


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
    if (dragging && sidebarRef.current) {
      const sidebarRect = sidebarRef.current.getBoundingClientRect();
      if (
        e.clientX >= sidebarRect.left &&
        e.clientX <= sidebarRect.right &&
        e.clientY >= sidebarRect.top &&
        e.clientY <= sidebarRect.bottom
      ) {
        onTaskUpdate(dragging.id, { horario_inicio: null, horario_fim: null }, false);
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
    <div className="flex flex-col h-[600px] overflow-hidden bg-slate-50 border-t border-slate-100">
      {/* All Day Events Header */}
      {allDayEvents.length > 0 && (
        <div className="flex-shrink-0 bg-white border-b border-slate-100 flex items-center min-h-[40px] px-4 py-2 gap-4">
          <div className="w-16 flex-shrink-0 text-[9px] font-black text-slate-400 uppercase tracking-widest text-center">Dia Todo</div>
          <div className="flex-1 flex flex-wrap gap-2">
            {allDayEvents.map(event => (
              <div
                key={event.id}
                className="px-3 py-1 bg-amber-50 border border-amber-200 rounded-full text-[10px] font-bold text-amber-700 flex items-center gap-2 shadow-sm"
              >
                <div className="w-2 h-2 bg-amber-500 rounded-full"></div>
                <span className="flex-1">{event.titulo}</span>
                <span className="text-[7px] font-black px-1 py-0.5 rounded uppercase bg-amber-100 text-amber-700">Google</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden relative">
        <div className="flex-1 overflow-y-auto custom-scrollbar relative">
          <div
            className="relative w-full"
            style={{ height: 24 * hourHeight }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              const taskId = e.dataTransfer.getData('task-id') || e.dataTransfer.getData('tarefaId');
              const rect = e.currentTarget.getBoundingClientRect();
              const y = e.clientY - rect.top;
              const hour = Math.floor(y / hourHeight);
              if (taskId) {
                onTaskUpdate(taskId, {
                  horario_inicio: `${hour.toString().padStart(2, '0')}:00`,
                  horario_fim: `${(hour + 1).toString().padStart(2, '0')}:00`,
                  data_inicio: dayStr
                }, true);
              }
            }}
          >
            {/* Grid Lines */}
            {Array.from({ length: 24 }).map((_, i) => (
              <div key={i} className="absolute left-0 right-0 border-t border-slate-100 flex items-start" style={{ top: i * hourHeight, height: hourHeight }}>
                <span className="text-[10px] text-slate-300 font-mono -mt-2 bg-slate-50 px-1 ml-2">{i.toString().padStart(2, '0')}:00</span>
              </div>
            ))}

            {/* Current Time Indicator */}
            {isToday && (
              <div className="absolute left-0 right-0 border-t-2 border-red-500 z-20 pointer-events-none" style={{ top: currentTimeTop }}>
                <div className="absolute -left-1 -top-1.5 w-3 h-3 bg-red-500 rounded-full"></div>
              </div>
            )}

            {/* Timed Events (Tasks & Google) */}
            {positionedEvents.map(event => {
              const startMin = event.start;
              const endMin = event.end;
              const top = (startMin / 60) * hourHeight;
              const height = ((endMin - startMin) / 60) * hourHeight;

              const columnWidth = (100 - 18) / event.totalCols; // Remaining width after 18 units of left padding
              const left = 18 + (event.colIndex * columnWidth);
              const width = columnWidth - 0.5; // Minimal gap between columns

              if (event.type === 'google') {
                const googleEvent = event.data as GoogleCalendarEvent;
                return (
                  <div
                    key={event.id}
                    className="absolute rounded-lg md:rounded-xl border-l-4 p-2 shadow-sm bg-amber-50/90 border-amber-500 text-slate-800 transition-all hover:z-30"
                    style={{ top, height: Math.max(30, height), left: `${left}%`, width: `${width}%`, zIndex: 5 }}
                  >
                    <div className="flex justify-between items-start gap-2">
                      <div className="text-[11px] font-black leading-tight line-clamp-2 flex items-center gap-2">
                        <span className="w-2 h-2 bg-amber-500 rounded-full"></span>
                        {googleEvent.titulo}
                      </div>
                      <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-amber-100 text-amber-700">Google</span>
                    </div>
                  </div>
                );
              } else {
                const task = event.data as Tarefa;
                return (
                  <div
                    key={task.id}
                    className={`absolute rounded-lg md:rounded-xl border p-2 shadow-sm group transition-all cursor-grab active:cursor-grabbing overflow-hidden hover:z-30
                      ${task.categoria === 'CLC' ? 'bg-blue-50 border-blue-200 text-blue-800' :
                        task.categoria === 'ASSISTÊNCIA' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' :
                          'bg-white border-slate-200 text-slate-800'}
                    `}
                    style={{ top, height: Math.max(30, height), left: `${left}%`, width: `${width}%`, zIndex: 10 }}
                    onMouseDown={(e) => {
                      const target = e.target as HTMLElement;
                      if (target.classList.contains('resize-handle')) return;
                      setDragging({ id: task.id, startY: e.clientY, startMin });
                    }}
                  >
                    <div className="flex justify-between items-start gap-2">
                      <div className="text-[11px] font-black leading-tight line-clamp-2">{task.titulo}</div>
                      <div className="flex gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmAction({
                              taskId: task.id,
                              newStatus: task.status === 'concluído' ? 'em andamento' : 'concluído'
                            });
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
              }
            })}
          </div>
        </div>

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
                className="bg-white p-4 rounded-none md:rounded-2xl border border-slate-200 shadow-sm hover:border-blue-400 hover:shadow-md transition-all cursor-grab active:cursor-grabbing"
              >
                <div className="text-[10px] font-bold text-slate-700 leading-tight mb-2">{task.titulo}</div>
                <div className="flex items-center gap-2">
                  <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase ${PROJECT_COLORS[task.projeto] || 'bg-slate-100 text-slate-600'}`}>{task.projeto}</span>
                  {(!task.data_limite || task.data_limite === '-' || task.data_limite === '0000-00-00') && (
                    <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-amber-100 text-amber-700">Sem Prazo</span>
                  )}
                </div>
              </div>
            ))}
            {dayTasks.filter(t => !t.horario_inicio).length === 0 && (
              <div className="py-12 text-center border-2 border-dashed border-slate-200 rounded-none md:rounded-[2rem]">
                <p className="text-slate-300 text-[10px] font-black uppercase italic">Tudo alocado</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {confirmAction && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-white rounded-none md:rounded-[2rem] p-8 max-w-sm w-full shadow-2xl animate-in zoom-in-95">
            <h3 className="text-xl font-black text-slate-900 mb-2">Confirmar Ação</h3>
            <p className="text-slate-500 text-sm mb-8">Deseja marcar esta tarefa como <strong>{confirmAction.newStatus}</strong>?</p>
            <div className="flex gap-4">
              <button onClick={() => setConfirmAction(null)} className="flex-1 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50">Cancelar</button>
              <button onClick={confirmTaskCompletion} className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg shadow-slate-200">Confirmar</button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

const CalendarView = ({
  tasks,
  googleEvents = [],
  viewMode,
  currentDate,
  onDateChange,
  onTaskClick,
  onViewModeChange,
  onTaskUpdate,
  onExecuteTask
}: {
  tasks: Tarefa[],
  googleEvents?: GoogleCalendarEvent[],
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

  const googleEventsByDay = useMemo(() => {
    const map: Record<string, GoogleCalendarEvent[]> = {};
    googleEvents.forEach(e => {
      const startStr = e.data_inicio.split('T')[0];
      const endStr = e.data_fim.split('T')[0];

      let current = new Date(startStr + 'T12:00:00Z');
      const end = new Date(endStr + 'T12:00:00Z');

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
    tasks.forEach(t => {
      if (!t.data_limite || t.data_limite === '-' || t.data_limite === '0000-00-00') return;

      const endStr = t.data_limite;
      const startStr = t.is_single_day ? endStr : (t.data_inicio || endStr);

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
    <div className="bg-white rounded-none md:rounded-[2rem] border border-slate-200 overflow-hidden shadow-sm animate-in fade-in">
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
          googleEvents={googleEvents}
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

const RowCard = React.memo(({ task, onClick, onToggle, onDelete, onEdit }: {
  task: Tarefa,
  onClick?: () => void,
  onToggle: (id: string, currentStatus: string) => void,
  onDelete: (id: string) => void,
  onEdit: (t: Tarefa) => void
}) => {
  const statusValue = normalizeStatus(task.status);
  const isCompleted = statusValue === 'concluido';
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  const formatDateShort = (dateStr: string) => {
    if (!dateStr || dateStr === '-' || dateStr === 'Sem Data') return '-';
    // Normalize date string (strip time if present)
    const pureDate = dateStr.includes('T') ? dateStr.split('T')[0] : dateStr.split(' ')[0];
    const parts = pureDate.split('-');
    if (parts.length !== 3) return dateStr;
    const date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    if (date.getTime() === today.getTime()) return 'Hoje';
    const months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${parts[2]} ${months[Number(parts[1]) - 1]}`;
  };

  const getTagStyle = (name: string, type: 'category' | 'project') => {
    const n = name.toUpperCase();
    if (type === 'category') {
      if (n === 'CLC') return 'bg-blue-50 text-blue-600 border-blue-100';
      if (n === 'ASSISTÊNCIA' || n.includes('ESTUDANTIL')) return 'bg-emerald-50 text-emerald-600 border-emerald-100';
    }
    if (n === 'GOOGLE' || n === 'GOOGLE TASKS') return 'bg-blue-50 text-blue-600 border-blue-100';
    if (n.includes('MAGO')) return 'bg-purple-50 text-purple-600 border-purple-100';
    if (n.includes('SIGEX')) return 'bg-indigo-50 text-indigo-600 border-indigo-100';
    if (n.includes('PROEN')) return 'bg-cyan-50 text-cyan-600 border-cyan-100';
    if (n.includes('PLS')) return 'bg-orange-50 text-orange-600 border-orange-100';
    if (n.includes('PDI')) return 'bg-teal-50 text-teal-600 border-teal-100';
    return 'bg-slate-50 text-slate-500 border-slate-100';
  };

  const dateDisplay = formatDateShort(task.data_limite);

  return (
    <div
      onClick={onClick}
      onMouseLeave={() => setIsConfirmingDelete(false)}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('task-id', task.id);
        e.dataTransfer.effectAllowed = 'move';
      }}
      title={task.data_criacao ? `Criada em: ${formatDate(task.data_criacao.split('T')[0])}` : ''}
      className={`group bg-white w-full px-4 md:px-6 py-4 md:py-3 border-b border-slate-100 hover:bg-slate-50/80 transition-all flex flex-col sm:flex-row sm:items-center gap-4 md:gap-6 animate-in cursor-pointer relative ${isCompleted ? 'opacity-60 grayscale-[0.5]' : ''}`}
    >
      {/* Esquerda: Checkbox + Título */}
      <div className="flex items-center gap-4 flex-1 min-w-0">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle(task.id, task.status);
          }}
          className={`w-6 h-6 sm:w-5 sm:h-5 rounded-lg border-2 flex items-center justify-center transition-all flex-shrink-0 ${isCompleted ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-slate-200 hover:border-slate-400 text-transparent'}`}
        >
          <svg className="w-4 h-4 sm:w-3.5 sm:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M5 13l4 4L19 7" /></svg>
        </button>

        <div className={`text-sm md:text-base font-bold text-[#1a202c] leading-tight transition-colors ${isCompleted ? 'line-through text-slate-400' : 'group-hover:text-blue-600'} line-clamp-2 sm:line-clamp-1`}>
          {task.titulo}
        </div>
      </div>

      {/* Centro/Direita: Tags + Data + Ações */}
      <div className="flex items-center justify-between sm:justify-end gap-4 md:gap-6 flex-wrap sm:flex-nowrap">
        <div className="flex items-center gap-2 flex-wrap">
          {task.categoria && task.categoria !== 'NÃO CLASSIFICADA' && (
            <span className={`text-[8px] md:text-[9px] font-black px-2 py-0.5 rounded-full border whitespace-nowrap ${getTagStyle(task.categoria, 'category')}`}>
              {task.categoria}
            </span>
          )}
          <span className={`text-[8px] md:text-[9px] font-black px-2 py-0.5 rounded-full border whitespace-nowrap ${getTagStyle(task.projeto, 'project')}`}>
            {task.projeto}
          </span>

          {task.sync_status && (
            <div className={`w-2 h-2 rounded-full ${task.sync_status === 'new' ? 'bg-purple-500 animate-pulse' : 'bg-amber-500'}`} title={task.sync_status === 'new' ? 'Nova' : 'Atualizada'}></div>
          )}
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-1.5 text-slate-400 font-black uppercase text-[9px] md:text-[10px] tracking-widest min-w-[65px]">
            <svg className="w-3 h-3 md:w-3.5 md:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
            {dateDisplay}
          </div>

          {/* Ações: Sempre visíveis no mobile (sm:opacity-0), hover no desktop */}
          {!isCompleted && (
            <div className="flex items-center gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-all">
              <button
                onClick={(e) => { e.stopPropagation(); onEdit(task); }}
                className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg md:rounded-xl transition-all"
                title="Editar Ação"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
              </button>

              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (isConfirmingDelete) {
                    onDelete(task.id);
                  } else {
                    setIsConfirmingDelete(true);
                  }
                }}
                className={`p-2 rounded-lg md:rounded-xl transition-all ${isConfirmingDelete ? 'bg-rose-500 text-white shadow-lg shadow-rose-200' : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50'}`}
                title={isConfirmingDelete ? "Confirmar?" : "Excluir"}
              >
                {isConfirmingDelete ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                )}
              </button>
            </div>
          )}

          {isCompleted && (
            <span className={`text-[8px] md:text-[9px] font-black uppercase px-2 py-1 rounded-full ${STATUS_COLORS[statusValue] || 'bg-slate-100 text-slate-500'}`}>
              {task.status}
            </span>
          )}
        </div>
      </div>
    </div>
  );
});

const CategoryView = ({ tasks, viewMode, onSelectTask, onExecuteTask }: { tasks: Tarefa[], viewMode: string, onSelectTask: (t: Tarefa) => void, onExecuteTask: (t: Tarefa) => void }) => {
  const isCLC = viewMode === 'licitacoes';
  const categoria = isCLC ? 'CLC' : 'ASSISTÊNCIA';
  const color = isCLC ? 'blue' : 'emerald';
  const title = isCLC ? 'Licitações' : 'Assistência Estudantil';

  const todayStr = formatDateLocalISO(new Date());

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
          {/* Desktop Table View */}
          <table className="w-full text-left hidden md:table">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Demanda</th>
                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-[200px]">Prazo</th>
                <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-[250px] text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {pendentes.map(t => (
                <tr key={t.id} className="hover:bg-slate-50 transition-colors cursor-pointer" onClick={() => onExecuteTask(t)}>
                  <td className="px-8 py-6">
                    <div className="text-[8px] font-black uppercase text-slate-400 mb-1">{t.projeto}</div>
                    <div className="text-sm font-black text-slate-900 leading-tight">{t.titulo}</div>
                  </td>
                  <td className="px-8 py-6 text-sm font-bold text-slate-600 whitespace-nowrap">{formatDate(t.data_limite)}</td>
                  <td className="px-8 py-6 text-right">
                    <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={(e) => { e.stopPropagation(); onSelectTask(t); }}
                        className="px-4 py-2 bg-slate-100 text-slate-600 rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-wider hover:bg-slate-200 transition-colors"
                      >
                        Editar
                      </button>

                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Mobile Card View */}
          <div className="md:hidden divide-y divide-slate-100">
            {pendentes.map(t => (
              <div key={t.id} className="p-6 space-y-4 hover:bg-slate-50 transition-colors cursor-pointer" onClick={() => onExecuteTask(t)}>
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1">
                    <div className="text-[8px] font-black uppercase text-slate-400 mb-1">{t.projeto}</div>
                    <div className="text-sm font-black text-slate-900 leading-tight">{t.titulo}</div>
                  </div>
                  <div className="text-[9px] font-black text-blue-600 uppercase tracking-widest bg-blue-50 px-2 py-1 rounded whitespace-nowrap">
                    {formatDate(t.data_limite)}
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={(e) => { e.stopPropagation(); onSelectTask(t); }}
                    className="flex-1 px-4 py-3 bg-slate-100 text-slate-600 rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-wider text-center"
                  >
                    Editar
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); onExecuteTask(t); }}
                    className="flex-1 px-4 py-3 bg-slate-900 text-white rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-wider text-center"
                  >
                    Executar
                  </button>
                </div>
              </div>
            ))}
          </div>

          {pendentes.length === 0 && (
            <div className="py-20 text-center text-slate-300 font-black uppercase tracking-widest italic border-t border-slate-100">
              Nenhuma ação em aberto
            </div>
          )}
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
            <div className="py-10 text-center bg-slate-50 rounded-none md:rounded-2xl border-2 border-dashed border-slate-200">
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
  onUpdateOverdue,
  onNavigate
}: {
  notifications: HermesNotification[],
  onMarkAsRead: (id: string) => void,
  onDismiss: (id: string) => void,
  isOpen: boolean,
  onClose: () => void,
  onUpdateOverdue?: () => void,
  onNavigate?: (link: string) => void
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
    <div
      ref={dropdownRef}
      className="fixed sm:absolute bottom-0 sm:bottom-auto sm:top-full left-0 right-0 sm:left-auto sm:right-0 w-full sm:w-96 bg-white rounded-t-[2rem] sm:rounded-none md:rounded-[2.5rem] shadow-[0_-20px_50px_rgba(0,0,0,0.1)] sm:shadow-[0_20px_50px_rgba(0,0,0,0.2)] border-t sm:border border-slate-100 overflow-hidden z-[100] animate-in fade-in slide-in-from-bottom-10 sm:slide-in-from-top-4 sm:slide-in-from-right-4 duration-300"
    >
      <div className="w-12 h-1.5 bg-slate-200 rounded-full mx-auto mt-4 mb-2 sm:hidden"></div>
      <div className="p-8 border-b border-slate-50 bg-slate-50/50 flex items-center justify-between">
        <div>
          <h3 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em]">Notificações</h3>
          <p className="text-[9px] text-slate-400 font-bold uppercase mt-1">Hermes Intelligent Alerts</p>
        </div>
        <span className="bg-blue-600 text-white text-[10px] font-black px-2.5 py-1 rounded-full shadow-lg shadow-blue-200">
          {notifications.filter(n => !n.isRead).length}
        </span>
      </div>
      <div className="max-h-[70vh] sm:max-h-[400px] overflow-y-auto custom-scrollbar">
        {notifications.length > 0 ? (
          notifications.map(n => (
            <div
              key={n.id}
              className={`p-6 border-b border-slate-50 hover:bg-slate-50 transition-all cursor-pointer relative group ${!n.isRead ? 'bg-blue-50/30' : ''}`}
              onClick={() => {
                onMarkAsRead(n.id);
                if (n.link && onNavigate) {
                  onNavigate(n.link);
                  onClose();
                }
              }}
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
                      className="mt-4 w-full py-2.5 bg-slate-900 text-white text-[9px] font-black uppercase tracking-widest rounded-lg md:rounded-xl shadow-lg hover:bg-blue-600 transition-all active:scale-95"
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
  onEmitNotification,
  initialTab
}: {
  settings: AppSettings,
  unidades: { id: string, nome: string, palavras_chave?: string[] }[],
  onSave: (settings: AppSettings) => void,
  onClose: () => void,
  onAddUnidade: (nome: string) => void,
  onDeleteUnidade: (id: string) => void,
  onUpdateUnidade: (id: string, updates: any) => void,
  onEmitNotification: (title: string, message: string, type: 'info' | 'warning' | 'success' | 'error') => void,
  initialTab?: 'notifications' | 'context' | 'sistemas' | 'google'
}) => {
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);
  const [activeTab, setActiveTab] = useState<'notifications' | 'context' | 'sistemas' | 'google'>(initialTab || 'notifications');
  const [newUnidadeNome, setNewUnidadeNome] = useState('');
  const [newKeywordMap, setNewKeywordMap] = useState<{ [key: string]: string }>({});
  const [newCustom, setNewCustom] = useState<Partial<CustomNotification>>({
    frequency: 'daily',
    time: '09:00',
    enabled: true,
    daysOfWeek: [],
    dayOfMonth: 1
  });
  const [isAddingCustom, setIsAddingCustom] = useState(false);

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

          <div className="flex bg-slate-200/50 p-1 rounded-none md:rounded-2xl gap-1">
            <button
              onClick={() => setActiveTab('notifications')}
              className={`flex-1 py-4 rounded-lg md:rounded-xl flex items-center justify-center transition-all ${activeTab === 'notifications' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'}`}
              title="Notificações"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
            </button>
            <button
              onClick={() => setActiveTab('context')}
              className={`flex-1 py-4 rounded-lg md:rounded-xl flex items-center justify-center transition-all ${activeTab === 'context' ? 'bg-white text-emerald-600 shadow-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'}`}
              title="Contexto & Áreas"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>
            </button>
            <button
              onClick={() => setActiveTab('sistemas')}
              className={`flex-1 py-4 rounded-lg md:rounded-xl flex items-center justify-center transition-all ${activeTab === 'sistemas' ? 'bg-white text-violet-600 shadow-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'}`}
              title="Sistemas"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
            </button>
            <button
              onClick={() => setActiveTab('google')}
              className={`flex-1 py-4 rounded-lg md:rounded-xl flex items-center justify-center transition-all ${activeTab === 'google' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'}`}
              title="Google"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" /></svg>
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

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-blue-200 transition-all">
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

                <div className="flex flex-col p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-rose-200 transition-all gap-4">
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

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-emerald-200 transition-all">
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

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-blue-200 transition-all">
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

                <div className="flex flex-col p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-amber-200 transition-all gap-4">
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

              {/* Notificações Personalizadas Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500 delay-150">
                <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                  <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
                    <span className="w-2 h-2 bg-purple-500 rounded-full"></span>
                    Personalizadas
                  </h4>
                  <button
                    onClick={() => setIsAddingCustom(!isAddingCustom)}
                    className="text-[10px] font-black uppercase text-blue-600 hover:bg-blue-50 px-2 py-1 rounded transition-colors"
                  >
                    {isAddingCustom ? 'Cancelar' : '+ Nova'}
                  </button>
                </div>

                {/* Form de Adição */}
                {isAddingCustom && (
                  <div className="bg-slate-50 p-4 rounded-xl border border-blue-100 flex flex-col gap-3 animate-in fade-in slide-in-from-top-2">
                    <input
                      type="text"
                      placeholder="Mensagem da notificação..."
                      className="w-full bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none"
                      value={newCustom.message || ''}
                      onChange={e => setNewCustom({ ...newCustom, message: e.target.value })}
                    />
                    <div className="flex gap-2">
                      <select
                        className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-[10px] font-black uppercase text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
                        value={newCustom.frequency}
                        onChange={e => setNewCustom({ ...newCustom, frequency: e.target.value as any })}
                      >
                        <option value="daily">Diária</option>
                        <option value="weekly">Semanal</option>
                        <option value="monthly">Mensal</option>
                      </select>
                      <input
                        type="time"
                        className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
                        value={newCustom.time || ''}
                        onChange={e => setNewCustom({ ...newCustom, time: e.target.value })}
                      />
                    </div>

                    {/* Conditional Frequency Inputs */}
                    {newCustom.frequency === 'weekly' && (
                      <div className="flex gap-1 flex-wrap">
                        {['D', 'S', 'T', 'Q', 'Q', 'S', 'S'].map((d, i) => (
                          <button
                            key={i}
                            onClick={() => {
                              const current = newCustom.daysOfWeek || [];
                              const updated = current.includes(i) ? current.filter(x => x !== i) : [...current, i];
                              setNewCustom({ ...newCustom, daysOfWeek: updated });
                            }}
                            className={`w-6 h-6 rounded text-[9px] font-black ${newCustom.daysOfWeek?.includes(i) ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-400'}`}
                          >
                            {d}
                          </button>
                        ))}
                      </div>
                    )}

                    {newCustom.frequency === 'monthly' && (
                       <div className="flex items-center gap-2">
                         <span className="text-[10px] font-black text-slate-400 uppercase">Dia do mês:</span>
                         <input
                           type="number"
                           min="1"
                           max="31"
                           className="w-12 bg-white border border-slate-200 rounded-lg px-2 py-1 text-xs font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
                           value={newCustom.dayOfMonth || 1}
                           onChange={e => setNewCustom({ ...newCustom, dayOfMonth: Number(e.target.value) })}
                         />
                       </div>
                    )}

                    <button
                      disabled={!newCustom.message || !newCustom.time}
                      onClick={() => {
                        const notif: CustomNotification = {
                          id: Math.random().toString(36).substr(2, 9),
                          message: newCustom.message!,
                          frequency: newCustom.frequency as any,
                          time: newCustom.time!,
                          enabled: true,
                          daysOfWeek: newCustom.daysOfWeek || [],
                          dayOfMonth: newCustom.dayOfMonth || 1
                        };
                        setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            custom: [...(localSettings.notifications.custom || []), notif]
                          }
                        });
                        setIsAddingCustom(false);
                        setNewCustom({ frequency: 'daily', time: '09:00', enabled: true, daysOfWeek: [], dayOfMonth: 1 });
                      }}
                      className="bg-blue-600 text-white py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-colors disabled:opacity-50"
                    >
                      Salvar Notificação
                    </button>
                  </div>
                )}

                {/* Lista de Notificações Custom */}
                <div className="grid grid-cols-1 gap-3">
                  {(localSettings.notifications.custom || []).map(notif => (
                    <div key={notif.id} className="p-4 bg-white border border-slate-100 rounded-xl flex items-center justify-between group hover:border-purple-200 transition-all shadow-sm">
                      <div>
                        <p className="text-xs font-bold text-slate-900 line-clamp-1">{notif.message}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[9px] font-black text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded uppercase">
                            {notif.time}
                          </span>
                          <span className="text-[9px] font-black text-slate-400 uppercase">
                            {notif.frequency === 'daily' ? 'Diária' :
                             notif.frequency === 'weekly' ? `Semanal (${notif.daysOfWeek?.length} dias)` :
                             `Mensal (Dia ${notif.dayOfMonth})`}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                         <button
                           onClick={() => {
                              const updated = (localSettings.notifications.custom || []).map(n =>
                                n.id === notif.id ? { ...n, enabled: !n.enabled } : n
                              );
                              setLocalSettings({ ...localSettings, notifications: { ...localSettings.notifications, custom: updated } });
                           }}
                           className={`w-8 h-4 rounded-full transition-all relative ${notif.enabled ? 'bg-purple-600' : 'bg-slate-300'}`}
                         >
                           <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${notif.enabled ? 'left-4.5' : 'left-0.5'}`} />
                         </button>
                         <button
                           onClick={() => {
                              const updated = (localSettings.notifications.custom || []).filter(n => n.id !== notif.id);
                              setLocalSettings({ ...localSettings, notifications: { ...localSettings.notifications, custom: updated } });
                           }}
                           className="text-slate-300 hover:text-rose-500 p-1 transition-colors"
                         >
                           <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                         </button>
                      </div>
                    </div>
                  ))}
                  {(localSettings.notifications.custom || []).length === 0 && !isAddingCustom && (
                    <div className="text-center py-6 text-slate-300 text-[10px] font-black uppercase tracking-widest italic border-2 border-dashed border-slate-50 rounded-xl">
                      Nenhuma notificação personalizada
                    </div>
                  )}
                </div>
              </div>

              {/* Canal de Teste Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500 delay-200">
                <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                  <span className="w-2 h-2 bg-indigo-500 rounded-full"></span>
                  Conectividade
                </h4>

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-indigo-200 transition-all">
                  <div className="flex-1">
                    <p className="text-sm font-bold text-slate-900 mb-1">Notificações Push</p>
                    <p className="text-[11px] text-slate-500 font-medium">Receber alertas no celular (mesmo com app fechado)</p>
                  </div>
                  <button
                    onClick={() => setLocalSettings({
                      ...localSettings,
                      notifications: {
                        ...localSettings.notifications,
                        enablePush: !localSettings.notifications.enablePush
                      }
                    })}
                    className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.enablePush !== false ? 'bg-indigo-600' : 'bg-slate-300'}`}
                  >
                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.enablePush !== false ? 'left-7' : 'left-1'}`} />
                  </button>
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
                    <div key={u.id} className={`p-6 bg-slate-50 rounded-none md:rounded-[2rem] border ${isProtected ? 'border-amber-200 bg-amber-50/30' : 'border-slate-100'} space-y-4 shadow-sm`}>
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
                          className="flex-1 bg-white border border-slate-200 rounded-lg md:rounded-xl px-4 py-2 text-[10px] font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none"
                        />
                        <button
                          onClick={() => handleAddKeyword(u.id, u.palavras_chave || [])}
                          className="bg-blue-600 text-white px-4 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all shadow-md shadow-blue-100"
                        >
                          Add
                        </button>
                      </div>
                    </div>
                  );
                })}

                <div className="p-6 bg-blue-50/50 rounded-none md:rounded-[2rem] border-2 border-dashed border-blue-200 flex flex-col gap-4">
                  <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest text-center">Cadastrar Nova Área de Contexto</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Nome da Unidade (ex: DEV, MARKETING)"
                      value={newUnidadeNome}
                      onChange={(e) => setNewUnidadeNome(e.target.value)}
                      className="flex-1 bg-white border border-blue-100 rounded-lg md:rounded-xl px-4 py-3 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none shadow-sm"
                    />
                    <button
                      onClick={() => {
                        if (newUnidadeNome.trim()) {
                          onAddUnidade(newUnidadeNome.trim().toUpperCase());
                          setNewUnidadeNome('');
                        }
                      }}
                      className="bg-blue-600 text-white px-6 py-3 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all shadow-lg shadow-blue-200"
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
                      <div key={sistema.id} className="bg-violet-50 border border-violet-100 rounded-none md:rounded-2xl p-6 group hover:border-violet-300 transition-all">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-violet-500 rounded-lg md:rounded-xl flex items-center justify-center">
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
                            className="opacity-0 group-hover:opacity-100 p-2 hover:bg-rose-100 rounded-lg md:rounded-xl transition-all text-rose-600"
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
                    <div className="text-center py-12 bg-slate-50 rounded-none md:rounded-2xl border-2 border-dashed border-slate-200">
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
                <div className="bg-gradient-to-br from-violet-50 to-purple-50 border-2 border-violet-200 rounded-none md:rounded-2xl p-6">
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
                      className="flex-1 bg-white border border-violet-100 rounded-lg md:rounded-xl px-4 py-3 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none shadow-sm"
                    />
                    <button
                      onClick={() => {
                        if (newUnidadeNome.trim()) {
                          onAddUnidade(`SISTEMA: ${newUnidadeNome.trim()}`);
                          setNewUnidadeNome('');
                        }
                      }}
                      className="bg-violet-600 text-white px-6 py-3 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-violet-700 transition-all shadow-lg shadow-violet-200"
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
          ) : activeTab === 'google' ? (
            <div className="space-y-6 animate-in slide-in-from-right-4 duration-500">
              <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                Integração Google Drive
              </h4>

              <div className="p-6 bg-slate-50 rounded-none md:rounded-[2rem] border border-slate-100 space-y-4 shadow-sm">
                <p className="text-xs text-slate-500 font-medium">
                  Configure a pasta do Google Drive onde os arquivos do Pool de Dados serão armazenados.
                </p>

                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">ID da Pasta no Drive</label>
                  <input
                    type="text"
                    value={localSettings.googleDriveFolderId || ''}
                    onChange={(e) => setLocalSettings({ ...localSettings, googleDriveFolderId: e.target.value })}
                    placeholder="Ex: 1a2b3c4d5e6f7g8h9i0j..."
                    className="w-full bg-white border border-slate-200 rounded-lg md:rounded-xl px-4 py-3 text-xs font-mono text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                  <p className="text-[9px] text-slate-400 italic">
                    O ID da pasta é a parte final da URL da pasta no Google Drive.
                  </p>
                </div>
              </div>

              <div className="p-6 bg-amber-50 rounded-none md:rounded-[2rem] border border-amber-100">
                <div className="flex gap-3">
                  <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                  <div>
                    <p className="text-xs font-bold text-amber-800 uppercase tracking-wider mb-1">Nota sobre Permissões</p>
                    <p className="text-[10px] text-amber-700 leading-relaxed">
                      Ao adicionar novos escopos (como Google Drive), pode ser necessário re-autenticar o sistema usando o <strong>setup_credentials.bat</strong> para que o Hermes tenha permissão de escrita.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4 flex-shrink-0">
          <button onClick={onClose} className="flex-1 px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all">Cancelar</button>
          <button
            onClick={() => {
              onSave(localSettings);
              onClose();
            }}
            className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
          >
            Salvar Alterações
          </button>
        </div>
      </div>
    </div >
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
  const todayStr = formatDateLocalISO(new Date());

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
                className={`w-full flex items-center justify-between p-4 rounded-none md:rounded-2xl border-2 transition-all duration-300 ${isActive
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
            className="w-full bg-slate-900 text-white px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
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
  const clcKeywords = ['licitação', 'licitacao', 'pregão', 'pregao', 'contrato', 'dispensa', 'inexigibilidade', 'compra', 'aquisição', 'aquisicao', 'processo'];

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

// WorkItem modals removed in favor of inline logs

const TaskCreateModal = ({ unidades, onSave, onClose }: { unidades: { id: string, nome: string }[], onSave: (data: Partial<Tarefa>) => void, onClose: () => void }) => {
  const [formData, setFormData] = useState({
    titulo: '',
    data_inicio: formatDateLocalISO(new Date()),
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
              className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              placeholder="O que precisa ser feito?"
            />
            {formData.categoria !== 'NÃO CLASSIFICADA' && formData.categoria !== 'GERAL' && !autoClassified && (
              <p className="text-[9px] font-bold text-blue-600 pl-1 flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                Área detectada automaticamente. Você pode alterá-la abaixo.
              </p>
            )}
          </div>

          <div className="flex items-center gap-3 bg-slate-50 p-4 rounded-none md:rounded-2xl border border-slate-100">
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
                  className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
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
                className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Status</label>
              <select
                value={formData.status}
                onChange={e => setFormData({ ...formData, status: e.target.value as Status })}
                className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
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
                className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-black uppercase text-[10px] tracking-widest"
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
              className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-medium text-slate-700 focus:ring-2 focus:ring-slate-900 transition-all resize-none"
              placeholder="Detalhes da ação..."
            />
          </div>
        </div>

        <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4">
          <button onClick={onClose} className="flex-1 px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all">Cancelar</button>
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
            className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
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
    is_single_day: !!task.is_single_day,
    entregas_relacionadas: task.entregas_relacionadas || [],
    processo_sei: task.processo_sei || ''
  });

  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

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
            <textarea
              value={formData.titulo}
              onChange={e => setFormData({ ...formData, titulo: e.target.value })}
              className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all resize-none min-h-[100px]"
              rows={3}
            />
          </div>

          <div className="flex items-center gap-3 bg-slate-50 p-4 rounded-none md:rounded-2xl border border-slate-100">
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
                  className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
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
                className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Tag (Classificação)</label>
              <select
                value={formData.categoria}
                onChange={e => setFormData({ ...formData, categoria: e.target.value as Categoria })}
                className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-black uppercase text-[10px] tracking-widest"
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

            {/* Opção de Vínculo com PGC e Processo SEI */}
            {(formData.categoria === 'CLC' || formData.categoria === 'ASSISTÊNCIA' || formData.categoria === 'ASSISTÊNCIA ESTUDANTIL') && (
              <>
                <div className="space-y-2 animate-in fade-in slide-in-from-top-2">
                  <label className="text-[10px] font-black text-blue-600 uppercase tracking-widest pl-1">Vincular ação ao PGC</label>
                  <select
                    value={formData.entregas_relacionadas[0] || ''}
                    onChange={e => setFormData({ ...formData, entregas_relacionadas: e.target.value ? [e.target.value] : [] })}
                    className="w-full bg-blue-50 border-blue-100 rounded-none md:rounded-2xl px-6 py-4 text-xs font-bold text-blue-900 focus:ring-2 focus:ring-blue-500 transition-all"
                  >
                    <option value="">Não vinculado ao PGC</option>
                    {pgcEntregas.map(e => (
                      <option key={e.id} value={e.id}>{e.entrega}</option>
                    ))}
                  </select>
                  <p className="text-[9px] font-medium text-blue-400 pl-1 uppercase tracking-wider">Selecione a entrega institucional correspondente</p>
                </div>

                {formData.categoria === 'CLC' && (
                  <div className="space-y-4 animate-in fade-in slide-in-from-top-2">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-blue-600 uppercase tracking-widest pl-1">Número do Processo (SIPAC)</label>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={formData.processo_sei}
                          onChange={e => setFormData({ ...formData, processo_sei: e.target.value })}
                          placeholder="23083.XXXXXX/202X-XX"
                          className="flex-1 bg-white border-2 border-blue-50 rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-blue-900 focus:ring-2 focus:ring-blue-500 outline-none"
                        />
                        <button
                          onClick={async () => {
                            if (!formData.processo_sei) return;
                            setIsSyncing(true);
                            try {
                              const scrapeSipac = httpsCallable(functions, 'scrapeSipac');
                              await scrapeSipac({ taskId: task.id, processoSei: formData.processo_sei });
                              alert("Sincronização iniciada com sucesso!");
                            } catch (e) {
                              console.error(e);
                              alert("Erro ao iniciar sincronização.");
                            } finally {
                              setIsSyncing(false);
                            }
                          }}
                          disabled={isSyncing || !formData.processo_sei}
                          className="px-6 bg-blue-600 text-white rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all disabled:opacity-50"
                        >
                          {isSyncing ? 'Sincronizando...' : 'Sincronizar SIPAC'}
                        </button>
                      </div>
                      <div className="flex items-center justify-between px-1">
                        <p className="text-[9px] font-medium text-blue-400 uppercase tracking-wider">Número radical.numero/ano-dv</p>
                        {task.sync_status && (
                          <span className={`text-[9px] font-black uppercase tracking-widest ${
                            task.sync_status === 'concluido' ? 'text-emerald-500' :
                            task.sync_status === 'erro' ? 'text-rose-500' : 'text-amber-500 animate-pulse'
                          }`}>
                            Status: {task.sync_status}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <div className="p-6 md:p-8 bg-slate-50 border-t border-slate-100 flex flex-col md:flex-row gap-3 md:gap-4 flex-shrink-0">
          <button
            onClick={() => {
              if (!formData.titulo || !formData.data_limite) {
                alert("Preencha o título e o prazo final.");
                return;
              }
              if (!formData.is_single_day && formData.data_inicio > formData.data_limite) {
                alert("A data de início deve ser anterior ou igual ao prazo final.");
                return;
              }
              onSave(task.id, formData);
              onClose();
            }}
            className="w-full md:flex-1 bg-slate-900 text-white px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all order-1 md:order-3"
          >
            Salvar Alterações
          </button>

          <div className="flex gap-3 order-2 w-full md:w-auto">
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
              className={`flex-1 md:flex-none px-6 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all border flex items-center justify-center gap-2 ${isConfirmingDelete
                ? 'bg-rose-600 text-white border-rose-600 shadow-lg shadow-rose-200 animate-in zoom-in-95'
                : 'text-rose-600 hover:bg-rose-50 border-rose-100'
                }`}
            >
              {isConfirmingDelete ? 'Confirmar?' : 'Excluir'}
            </button>
            <button
              onClick={onClose}
              className="flex-1 md:hidden px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all border border-slate-200"
            >
              Cancelar
            </button>
          </div>

          <div className="hidden md:block md:flex-1 order-2"></div>

          <button
            onClick={onClose}
            className="hidden md:block px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all order-2"
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
};

const TaskExecutionView = ({ task, tarefas, appSettings, onSave, onClose, showToast }: { task: Tarefa, tarefas: Tarefa[], appSettings: AppSettings, onSave: (id: string, updates: Partial<Tarefa>) => void, onClose: () => void, showToast: (msg: string, type?: 'success' | 'error' | 'info') => void }) => {
  const [newFollowUp, setNewFollowUp] = useState('');
  const [newPoolItem, setNewPoolItem] = useState('');
  const [showPool, setShowPool] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [chatUrl, setChatUrl] = useState(task.chat_gemini_url || '');
  const [processoSei, setProcessoSei] = useState(task.processo_sei || '');
  const [isTimerRunning, setIsTimerRunning] = useState(false);
  const [pomodoroMode, setPomodoroMode] = useState<'focus' | 'break'>('focus');
  const [showPomodoroAlert, setShowPomodoroAlert] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [modalConfig, setModalConfig] = useState<{
    type: 'link' | 'contact' | 'edit_diary' | 'confirm_delete' | 'reset_timer' | 'file_upload';
    data?: any;
    isOpen: boolean;
  }>({ type: 'link', isOpen: false });
  const [modalInputValue, setModalInputValue] = useState('');
  const [modalInputName, setModalInputName] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [sessionTotalSeconds, setSessionTotalSeconds] = useState(task.tempo_total_segundos || 0);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [showDiaryMobileModal, setShowDiaryMobileModal] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editedTitle, setEditedTitle] = useState(task.titulo);

  useEffect(() => {
    setEditedTitle(task.titulo);
  }, [task.titulo]);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const diaryEndRef = useRef<HTMLDivElement>(null);
  const diaryMobileEndRef = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  // Garantir que estamos usando a versão mais recente da tarefa vinda do Firestore
  const currentTaskData = useMemo(() => tarefas.find(t => t.id === task.id) || task, [tarefas, task.id, task]);

  // Auto-scroll logic for Desktop
  useEffect(() => {
    if (shouldAutoScroll && diaryEndRef.current) {
      diaryEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentTaskData.acompanhamento, shouldAutoScroll]);

  // Auto-scroll logic for Mobile
  useEffect(() => {
    if (shouldAutoScroll && diaryMobileEndRef.current) {
      diaryMobileEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentTaskData.acompanhamento, showDiaryMobileModal, shouldAutoScroll]);

  const handleDiaryScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    // Se o usuário está a menos de 100px do fundo, habilita auto-scroll
    const isAtBottom = scrollHeight - scrollTop <= clientHeight + 100;
    setShouldAutoScroll(isAtBottom);
  };

  const nextTask = useMemo(() => {
    const now = new Date();
    const todayStr = formatDateLocalISO(now);
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
    const timeInterval = setInterval(() => {
      setCurrentTime(new Date());
    }, 30000); // 30s is enough for minute-based progress
    return () => clearInterval(timeInterval);
  }, []);

  useEffect(() => {
    let interval: number | null = null;
    if (isTimerRunning) {
      interval = window.setInterval(() => {
        setSeconds(prev => {
          const next = prev + 1;
          const focusTimeSeconds = (appSettings.pomodoro?.focusTime || 10) * 60;
          const breakTimeSeconds = (appSettings.pomodoro?.breakTime || 5) * 60;

          if (pomodoroMode === 'focus') {
            if (next > 0 && next % focusTimeSeconds === 0) {
              setShowPomodoroAlert(true);
              try {
                const audio = new Audio('https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3');
                audio.play().catch(() => {});
              } catch (e) {}
            }
          } else {
            if (next > 0 && next % breakTimeSeconds === 0) {
              setPomodoroMode('focus');
              setSeconds(0);
              showToast("Intervalo finalizado! De volta ao foco.", "info");
            }
          }
          return next;
        });

        if (pomodoroMode === 'focus') {
          setSessionTotalSeconds(prev => prev + 1);
        }
      }, 1000);
    } else {
      if (interval) clearInterval(interval);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isTimerRunning, pomodoroMode, appSettings.pomodoro]);

  const handleToggleTimer = () => {
    if (isTimerRunning) {
      // Quando parar, salvar o tempo total
      onSave(task.id, { tempo_total_segundos: sessionTotalSeconds });
    }

    setIsTimerRunning(!isTimerRunning);
  };

  const handleResetTimer = () => {
    setModalConfig({ type: 'reset_timer', isOpen: true });
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
    // Usar os acompanhamentos mais recentes para evitar sobrescrever dados
    const updatedAcompanhamento = [...(currentTaskData.acompanhamento || []), newEntry];
    onSave(task.id, { acompanhamento: updatedAcompanhamento });
    setNewFollowUp('');
    setShouldAutoScroll(true);
  };

  const handleDeleteDiaryEntry = (index: number) => {
    setModalConfig({ type: 'confirm_delete', isOpen: true, data: { index } });
  };

  const handleEditDiaryEntry = (index: number) => {
    const currentNote = (currentTaskData.acompanhamento || [])[index];
    if (!currentNote) return;
    setModalInputValue(currentNote.nota);
    setModalConfig({ type: 'edit_diary', isOpen: true, data: { index } });
  };

  const handleCopyAllHistory = () => {
    if (!task.acompanhamento) return;
    const history = task.acompanhamento
      .map(entry => `[${new Date(entry.data).toLocaleString('pt-BR')}] ${entry.nota}`)
      .join('\n\n');
    navigator.clipboard.writeText(history);
    showToast("Histórico completo copiado!", "success");
  };

  const handleCopyMessage = (text: string) => {
    navigator.clipboard.writeText(text);
    showToast("Mensagem copiada!", "success");
  };



  const handleSaveChatUrl = () => {
    onSave(task.id, { chat_gemini_url: chatUrl });
    showToast("Link do chat atualizado.", "success");
  };

  const handleSaveProcessoSei = () => {
    onSave(task.id, { processo_sei: processoSei });
    showToast("Processo SEI atualizado.", "success");
  };



  const onFileSelect = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    setPendingFile(file);
    setModalInputName(file.name);
    setModalConfig({ type: 'file_upload', isOpen: true });
  };

  const handleFileUpload = async (files: File | FileList, customName?: string) => {
    setIsUploading(true);
    const uploadFunc = httpsCallable(functions, 'upload_to_drive');
    const filesToUpload = files instanceof FileList ? Array.from(files) : [files];
    const uploadedItems: PoolItem[] = [];

    try {
      for (const file of filesToUpload) {
        // Convert file to base64
        const reader = new FileReader();
        const fileContentB64 = await new Promise<string>((resolve, reject) => {
          reader.onload = () => {
            const result = reader.result as string;
            resolve(result.split(',')[1]);
          };
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });

        const result = await uploadFunc({
          fileName: customName || file.name,
          fileContent: fileContentB64,
          mimeType: file.type,
          folderId: appSettings.googleDriveFolderId
        });

        const data = result.data as any;

        const newItem: PoolItem = {
          id: Math.random().toString(36).substr(2, 9),
          tipo: 'arquivo',
          valor: data.webViewLink,
          nome: customName || file.name,
          data_criacao: new Date().toISOString()
        };
        uploadedItems.push(newItem);
      }

      const newEntries = uploadedItems.map(item => ({
        data: new Date().toISOString(),
        nota: `FILE::${item.nome}::${item.valor}`
      }));

      onSave(task.id, {
        pool_dados: [...(currentTaskData.pool_dados || []), ...uploadedItems],
        acompanhamento: [...(currentTaskData.acompanhamento || []), ...newEntries]
      });

      showToast(`${uploadedItems.length} arquivo(s) carregado(s) com sucesso.`, "success");
      return uploadedItems;
    } catch (err) {
      console.error(err);
      showToast("Erro ao carregar arquivo para o Google Drive.", "error");
      return [];
    } finally {
      setIsUploading(false);
    }
  };

  const removePoolItem = (itemId: string) => {
    const updatedPool = (currentTaskData.pool_dados || []).filter(item => item.id !== itemId);
    onSave(task.id, { pool_dados: updatedPool });
  };

  const handleAddPoolItem = (valor: string, tipo: 'link' | 'telefone' | 'arquivo' = 'link', nome: string = '') => {
    if (!valor.trim()) return;

    const newItem: PoolItem = {
      id: Math.random().toString(36).substr(2, 9),
      tipo: tipo,
      valor: valor,
      nome: nome || valor,
      data_criacao: new Date().toISOString()
    };

    const updatedPool = [...(currentTaskData.pool_dados || []), newItem];

    // Auto-log no diário
    let notaContent = '';
    if (tipo === 'link') notaContent = `LINK::${nome}::${valor}`;
    else if (tipo === 'telefone') notaContent = `CONTACT::${nome}::${valor}`;
    else notaContent = valor;

    const noteObject = {
      data: new Date().toISOString(),
      nota: notaContent
    };

    const updatedAcompanhamento = [...(currentTaskData.acompanhamento || []), noteObject];

    onSave(task.id, { pool_dados: updatedPool, acompanhamento: updatedAcompanhamento });

    setNewPoolItem('');
    setShowAttachMenu(false);
  };


  const handleFileUploadInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setShowAttachMenu(false);
      onFileSelect(e.target.files);
    }
  };

  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);

  const handleCompleteTaskRequest = () => {
    if (isTimerRunning) {
      handleToggleTimer(); // Stop timer and save time
    }
    setIsConfirmModalOpen(true);
  };

  const confirmCompletion = () => {
    onSave(task.id, { status: 'concluído' });
    onClose();
  };

  const handleModalConfirm = () => {
    switch (modalConfig.type) {
      case 'reset_timer':
        setSeconds(0);
        setSessionTotalSeconds(0);
        onSave(task.id, { tempo_total_segundos: 0 });
        setIsTimerRunning(false);
        break;
      case 'confirm_delete':
        if (modalConfig.data?.index !== undefined) {
          const updated = [...(currentTaskData.acompanhamento || [])];
          updated.splice(modalConfig.data.index, 1);
          onSave(task.id, { acompanhamento: updated });
        }
        break;
      case 'edit_diary':
        if (modalConfig.data?.index !== undefined && modalInputValue.trim()) {
          const updated = [...(currentTaskData.acompanhamento || [])];
          updated[modalConfig.data.index] = { ...updated[modalConfig.data.index], nota: modalInputValue };
          onSave(task.id, { acompanhamento: updated });
        }
        break;
      case 'link':
        if (modalInputValue.trim()) handleAddPoolItem(modalInputValue, 'link', modalInputName);
        break;
      case 'contact':
        if (modalInputValue.trim()) handleAddPoolItem(modalInputValue, 'telefone', modalInputName);
        break;
      case 'file_upload':
        if (pendingFile) handleFileUpload(pendingFile, modalInputName);
        setPendingFile(null);
        break;
    }
    setModalConfig({ ...modalConfig, isOpen: false });
    setModalInputValue('');
    setModalInputName('');
  };

  const renderDiaryContent = (text: string) => {
    if (text.startsWith('LINK::')) {
      const parts = text.split('::');
      let url = '';
      let nome = '';

      if (parts.length >= 3) {
        nome = parts[1];
        url = parts[2];
      } else {
        url = text.replace('LINK::', '');
      }

      return (
        <a href={url} target="_blank" rel="noreferrer" className={`group flex items-center gap-4 p-4 rounded-none md:rounded-2xl border transition-all ${isTimerRunning ? 'bg-white/5 border-white/10 hover:bg-white/10' : 'bg-blue-50/50 border-blue-100 hover:bg-blue-50'}`}>
          <div className={`w-10 h-10 rounded-lg md:rounded-xl flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-blue-200 text-blue-600'}`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-xs font-bold truncate ${isTimerRunning ? 'text-white' : 'text-blue-900'}`}>{nome || url}</p>
            <p className={`text-[10px] uppercase font-black tracking-widest mt-0.5 ${isTimerRunning ? 'text-white/40' : 'text-blue-400'}`}>Link Externo</p>
          </div>
          <svg className={`w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity ${isTimerRunning ? 'text-white/60' : 'text-blue-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
        </a>
      );
    }
    if (text.startsWith('CONTACT::')) {
      const parts = text.split('::');
      let contact = '';
      let nome = '';

      if (parts.length >= 3) {
        nome = parts[1];
        contact = parts[2];
      } else {
        contact = text.replace('CONTACT::', '');
      }

      const num = contact.replace(/\D/g, '');
      const waLink = num.length >= 10 ? `https://wa.me/55${num}` : null;

      return (
        <div className={`group flex items-center gap-4 p-4 rounded-none md:rounded-2xl border transition-all ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-emerald-50/50 border-emerald-100'}`}>
          <div className={`w-10 h-10 rounded-lg md:rounded-xl flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-emerald-200 text-emerald-600'}`}>
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.022-.014-.503-.245-.583-.273-.08-.027-.138-.04-.197.048-.058.088-.227.288-.278.346-.05.058-.1.066-.188.022-.088-.044-.372-.137-.708-.437-.26-.231-.437-.515-.487-.603-.05-.088-.005-.135.039-.179.04-.04.088-.103.131-.154.044-.051.059-.088.088-.146.03-.058.015-.11-.008-.154-.022-.044-.197-.474-.27-.65-.072-.172-.143-.149-.197-.151l-.168-.002c-.058 0-.154.022-.234.11-.08.088-.307.3-.307.732 0 .432.315.849.359.907.044.058.62 1.04 1.502 1.42.21.09.372.143.5.184.21.067.4.057.55.035.168-.024.503-.205.574-.403.072-.198.072-.367.051-.403-.021-.037-.08-.058-.168-.102z" /><path d="M12 2C6.477 2 2 6.477 2 12c0 1.891.524 3.66 1.434 5.168L2 22l4.958-1.412A9.957 9.957 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18a7.96 7.96 0 01-4.07-1.112l-.292-.174-3.024.863.878-2.946-.19-.302A7.957 7.957 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-xs font-bold truncate ${isTimerRunning ? 'text-white' : 'text-emerald-900'}`}>{nome || contact}</p>
            <p className={`text-[10px] uppercase font-black tracking-widest mt-0.5 ${isTimerRunning ? 'text-white/40' : 'text-emerald-500'}`}>Contato Profissional</p>
          </div>
          {waLink && (
            <a href={waLink} target="_blank" rel="noreferrer" className={`p-2 rounded-lg transition-colors ${isTimerRunning ? 'hover:bg-white/10 text-white' : 'hover:bg-emerald-200 text-emerald-600'}`} title="WhatsApp">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
            </a>
          )}
        </div>
      );
    }
    if (text.startsWith('FILE::')) {
      const parts = text.split('::');
      const nome = parts[1] || 'Arquivo';
      const url = parts[2] || '#';

      return (
        <a href={url} target="_blank" rel="noreferrer" className={`group flex items-center gap-4 p-4 rounded-none md:rounded-2xl border transition-all ${isTimerRunning ? 'bg-white/5 border-white/10 hover:bg-white/10' : 'bg-amber-50/50 border-amber-100 hover:bg-amber-50'}`}>
          <div className={`w-10 h-10 rounded-lg md:rounded-xl flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-amber-200 text-amber-600'}`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-xs font-bold truncate ${isTimerRunning ? 'text-white' : 'text-amber-900'}`}>{nome}</p>
            <p className={`text-[10px] uppercase font-black tracking-widest mt-0.5 ${isTimerRunning ? 'text-white/40' : 'text-amber-600'}`}>Anexo</p>
          </div>
          <svg className={`w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity ${isTimerRunning ? 'text-white/60' : 'text-amber-500'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
        </a>
      );
    }

    return <div className={`text-xs md:text-sm leading-relaxed ${isTimerRunning ? 'text-white/90' : 'text-slate-700'}`}>{formatWhatsAppText(text)}</div>;
  };

  return (
    <div className={`fixed inset-0 z-[200] flex flex-col overflow-hidden transition-colors duration-500 ${isTimerRunning ? 'bg-[#050505] text-white' : 'bg-[#F2F4F7] text-slate-900'}`}>
      {/* Header: Title and Close */}
      <div className="p-6 md:p-10 pb-4 flex items-center justify-between shrink-0">
        <div className="flex flex-col">
          <span className="text-blue-500 text-[8px] md:text-[10px] font-black uppercase tracking-[0.3em] mb-1 md:mb-2 block">Central de Execução</span>
          {isEditingTitle ? (
            <div className="flex items-center gap-2">
              <input
                type="text"
                autoFocus
                value={editedTitle}
                onChange={e => setEditedTitle(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    onSave(task.id, { titulo: editedTitle });
                    setIsEditingTitle(false);
                    showToast("Título atualizado!", "success");
                  } else if (e.key === 'Escape') {
                    setEditedTitle(task.titulo);
                    setIsEditingTitle(false);
                  }
                }}
                className={`text-xl md:text-2xl lg:text-4xl font-black tracking-tighter leading-tight bg-transparent border-b-2 outline-none w-full max-w-2xl ${isTimerRunning ? 'text-white border-white/20 focus:border-white/50' : 'text-slate-900 border-slate-200 focus:border-blue-500'}`}
              />
              <button
                onClick={() => {
                  onSave(task.id, { titulo: editedTitle });
                  setIsEditingTitle(false);
                  showToast("Título atualizado!", "success");
                }}
                className="p-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors shadow-lg"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
              </button>
            </div>
          ) : (
            <div className="group flex items-center gap-4">
              <h1 className={`text-xl md:text-2xl lg:text-4xl font-black tracking-tighter leading-tight transition-colors ${isTimerRunning ? 'text-white' : 'text-slate-900'}`}>
                {task.titulo}
              </h1>
              <button
                onClick={() => setIsEditingTitle(true)}
                className={`p-2 opacity-0 group-hover:opacity-100 transition-all rounded-lg ${isTimerRunning ? 'text-white/40 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-100'}`}
                title="Editar título"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
              </button>
            </div>
          )}
          {task.descricao && (
            <p className={`mt-4 text-sm font-medium max-w-2xl leading-relaxed whitespace-pre-wrap transition-colors ${isTimerRunning ? 'text-white/60' : 'text-slate-500'}`}>
              {task.descricao}
            </p>
          )}
        </div>
        <button
          onClick={() => {
            if (isTimerRunning) handleToggleTimer();
            onClose();
          }}
          className={`p-3 rounded-none md:rounded-2xl transition-all border ${isTimerRunning ? 'bg-white/5 hover:bg-white/10 text-white/40 border-white/5' : 'bg-white hover:bg-slate-50 text-slate-400 border-slate-200'}`}
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
        </button>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-0 md:gap-8 p-0 md:p-10 pt-4 overflow-y-auto">
        {/* COLUNA DIREITA (AGORA NO TOPO NO MOBILE): Especialista + Cronômetro (5 colunas) */}
        <div className="lg:col-span-5 flex flex-col gap-0 md:gap-8 overflow-hidden px-0 md:px-0 order-1 lg:order-2">
          {/* Especialista Virtual (Mantém estilo gradiente em ambos os modos, pois é um card destacado) */}
          <div className="bg-gradient-to-br from-indigo-600 to-blue-700 !rounded-none md:rounded-[3rem] p-4 md:p-6 text-white shadow-2xl flex-shrink-0 relative overflow-hidden group">
            <div className="absolute -right-20 -top-20 w-64 h-64 bg-white/5 rounded-full blur-3xl group-hover:bg-white/10 transition-colors"></div>

            <div className="relative z-10 flex flex-col md:flex-row gap-6">
              <div className="flex-1">
                <h4 className="text-[10px] md:text-xs font-black uppercase tracking-widest leading-none opacity-70 mb-3">Especialista</h4>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type="text"
                      placeholder="Link do chat contextual..."
                      value={chatUrl}
                      onChange={e => setChatUrl(e.target.value)}
                      className="w-full bg-black/20 border border-white/10 rounded-none md:rounded-2xl px-4 py-3 text-xs font-medium focus:ring-2 focus:ring-white/30 outline-none text-white placeholder:text-white/20 transition-all"
                    />
                    {chatUrl !== (task.chat_gemini_url || '') && (
                      <button
                        onClick={handleSaveChatUrl}
                        className="absolute right-1 top-1 bottom-1 bg-emerald-500 text-white px-3 rounded-lg md:rounded-xl text-[8px] font-black uppercase shadow-lg hover:bg-emerald-600 transition-colors"
                      >
                        Salvar
                      </button>
                    )}
                  </div>
                  <a
                    href={task.chat_gemini_url || (task.categoria === 'CLC' ? "https://gemini.google.com/gem/096c0e51e1b9" : "https://gemini.google.com/")}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="bg-white text-indigo-600 w-10 h-10 md:w-11 md:h-11 flex items-center justify-center !rounded-none md:rounded-2xl hover:bg-slate-100 transition-all shadow-xl flex-shrink-0"
                    title="Abrir Chat"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                  </a>
                </div>
              </div>

              {task.categoria === 'CLC' && (
                <div className="flex-1 animate-in fade-in slide-in-from-top-2">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-[10px] md:text-xs font-black uppercase tracking-widest leading-none opacity-70">Processo SEI</h4>
                    {task.sync_status && (
                      <span className={`text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded ${
                        task.sync_status === 'concluido' ? 'bg-emerald-500/20 text-emerald-400' :
                        task.sync_status === 'erro' ? 'bg-rose-500/20 text-rose-400' :
                        'bg-amber-500/20 text-amber-400 animate-pulse'
                      }`}>
                        {task.sync_status}
                      </span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <input
                        type="text"
                        placeholder="Nº do Processo..."
                        value={processoSei}
                        onChange={e => setProcessoSei(e.target.value)}
                        className="w-full bg-black/20 border border-white/10 rounded-none md:rounded-2xl px-4 py-3 text-xs font-medium focus:ring-2 focus:ring-white/30 outline-none text-white placeholder:text-white/20 transition-all"
                      />
                      {processoSei !== (task.processo_sei || '') && (
                        <button
                          onClick={handleSaveProcessoSei}
                          className="absolute right-1 top-1 bottom-1 bg-blue-500 text-white px-3 rounded-lg md:rounded-xl text-[8px] font-black uppercase shadow-lg hover:bg-blue-600 transition-colors"
                        >
                          Salvar
                        </button>
                      )}
                    </div>
                    {task.processo_sei && (
                      <button
                        onClick={async () => {
                          try {
                            const scrapeSipac = httpsCallable(functions, 'scrapeSipac');
                            await scrapeSipac({ taskId: task.id, processoSei: task.processo_sei });
                            showToast("Sincronização iniciada.", "info");
                          } catch (e) {
                            showToast("Erro na sincronização.", "error");
                          }
                        }}
                        className="bg-white/10 hover:bg-white/20 text-white p-3 rounded-none md:rounded-2xl transition-all border border-white/5"
                        title="Sincronizar SIPAC agora"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Cronômetro Section */}
          <div className={`flex-1 !rounded-none md:rounded-[3rem] border p-6 md:p-10 flex flex-col relative overflow-hidden transition-all ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-200 shadow-xl shadow-slate-200/50'}`}>
            <div className={`absolute inset-0 transition-opacity duration-700 ${isTimerRunning ? 'bg-blue-500/5' : 'bg-transparent'}`}></div>

            <div className="relative z-10 text-center flex-1 flex flex-col items-center justify-center space-y-4 md:space-y-8">
              <div className={`text-[10px] font-black uppercase tracking-[0.5em] transition-colors ${isTimerRunning ? 'text-white/20' : 'text-slate-300'}`}>
                {isTimerRunning ? 'Sessão Ativa' : 'Foco em Pausa'}
              </div>

              <div className="flex flex-col items-center">
                <div className={`text-[3.5rem] md:text-[6rem] lg:text-[7.5rem] font-black tracking-tighter tabular-nums leading-none transition-colors drop-shadow-[0_10px_40px_rgba(255,255,255,0.05)] ${isTimerRunning ? 'text-white' : 'text-slate-900'}`}>
                  {formatTime(isTimerRunning ? seconds : sessionTotalSeconds).split(':').slice(1).join(':')}
                </div>
                <div className="text-[10px] md:text-lg font-bold text-blue-500 uppercase tracking-[0.3em] mt-0.5 md:mt-1">
                  {formatTime(isTimerRunning ? seconds : sessionTotalSeconds).split(':')[0]}h
                </div>
              </div>

              <div className="flex items-center gap-1 bg-black/10 p-1 rounded-xl mb-4">
                <button
                  onClick={() => { setPomodoroMode('focus'); setSeconds(0); }}
                  className={`px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all ${pomodoroMode === 'focus' ? 'bg-blue-600 text-white shadow-md' : 'text-slate-400'}`}
                >
                  Foco
                </button>
                <button
                  onClick={() => { setPomodoroMode('break'); setSeconds(0); }}
                  className={`px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all ${pomodoroMode === 'break' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400'}`}
                >
                  Intervalo
                </button>
              </div>

              <div className="flex gap-2 pb-4 md:pb-8">
                <button
                  onClick={handleToggleTimer}
                  className={`flex-1 md:flex-none flex items-center justify-center gap-2 md:gap-3 px-4 md:px-8 py-3 md:py-4 !rounded-none md:rounded-2xl text-[9px] md:text-[10px] font-black uppercase tracking-widest transition-all hover:scale-105 active:scale-95 shadow-2xl ${isTimerRunning
                    ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20 hover:bg-rose-500 hover:text-white'
                    : 'bg-blue-600 text-white shadow-blue-600/20 hover:bg-blue-500'
                    }`}
                >
                  {isTimerRunning ? (
                    <>
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
                      Pausar
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                      {sessionTotalSeconds > 0 ? 'Retomar' : 'Iniciar'}
                    </>
                  )}
                </button>

                <button
                  onClick={handleResetTimer}
                  className={`p-3 md:p-4 !rounded-none md:rounded-2xl transition-all shadow-xl hover:scale-105 active:scale-95 flex items-center justify-center ${isTimerRunning
                    ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20 hover:bg-rose-500 hover:text-white'
                    : 'bg-white text-slate-400 hover:text-rose-500 border border-slate-200 shadow-sm'
                    }`}
                  title="Reiniciar Cronômetro"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                </button>

                <button
                  onClick={handleCompleteTaskRequest}
                  className={`flex-1 md:flex-none px-4 md:px-6 py-3 md:py-4 !rounded-none md:rounded-2xl text-[8px] md:text-[9px] font-black uppercase tracking-widest transition-all shadow-xl ${task.status === 'concluído'
                    ? 'bg-emerald-500 text-white'
                    : isTimerRunning
                      ? 'bg-white/5 text-white/40 border border-white/10 hover:bg-white/10 hover:text-white'
                      : 'bg-white text-slate-400 border border-slate-200 shadow-sm hover:bg-slate-50 hover:text-slate-600'
                    }`}
                >
                  {task.status === 'concluído' ? 'Concluída' : 'Finalizar'}
                </button>
              </div>
            </div>

            {/* Schedule & Progress Section */}
            <div className="relative z-10 w-full mt-auto space-y-4 md:space-y-6">
              {/* Timeline Progress Bar */}
              {task.horario_inicio && task.horario_fim && (
                <div className="space-y-2">
                  <div className="flex justify-between items-end">
                    <span className={`text-[8px] font-black uppercase tracking-[0.2em] transition-colors ${isTimerRunning ? 'text-white/20' : 'text-slate-400'}`}>Progresso do Horário</span>
                    <span className="text-[9px] font-bold text-blue-400">
                      {(() => {
                        const now = currentTime;
                        const [sh, sm] = task.horario_inicio!.split(':').map(Number);
                        const [eh, em] = task.horario_fim!.split(':').map(Number);
                        const sMin = sh * 60 + sm;
                        const eMin = eh * 60 + em;
                        const cMin = now.getHours() * 60 + now.getMinutes();
                        if (cMin < sMin) return 'Aguardando Início';
                        if (cMin > eMin) return 'Tempo Esgotado';
                        const p = Math.round(((cMin - sMin) / (eMin - sMin)) * 100);
                        return `${p}% do tempo planejado`;
                      })()}
                    </span>
                  </div>
                  <div className={`h-1.5 w-full rounded-full overflow-hidden border transition-colors ${isTimerRunning ? 'bg-white/5 border-white/5' : 'bg-slate-200/50 border-slate-200'}`}>
                    <div
                      className="h-full bg-gradient-to-r from-blue-600 to-indigo-500 transition-all duration-1000 ease-out"
                      style={{
                        width: `${(() => {
                          const now = currentTime;
                          const [sh, sm] = task.horario_inicio!.split(':').map(Number);
                          const [eh, em] = task.horario_fim!.split(':').map(Number);
                          const sMin = sh * 60 + sm;
                          const eMin = eh * 60 + em;
                          const cMin = now.getHours() * 60 + now.getMinutes();
                          if (cMin < sMin) return 0;
                          if (cMin > eMin) return 100;
                          return Math.min(100, Math.max(0, ((cMin - sMin) / (eMin - sMin)) * 100));
                        })()}%`
                      }}
                    ></div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className={`rounded-lg md:rounded-xl p-3 border flex flex-col items-center transition-colors ${isTimerRunning ? 'bg-white/5 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <span className={`text-[7px] font-black uppercase tracking-widest mb-1 transition-colors ${isTimerRunning ? 'text-white/20' : 'text-slate-300'}`}>Início</span>
                  <span className={`text-[11px] font-bold transition-colors ${isTimerRunning ? 'text-white/80' : 'text-slate-700'}`}>{task.horario_inicio || '--:--'}</span>
                </div>
                <div className={`rounded-lg md:rounded-xl p-3 border flex flex-col items-center transition-colors ${isTimerRunning ? 'bg-white/5 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <span className={`text-[7px] font-black uppercase tracking-widest mb-1 transition-colors ${isTimerRunning ? 'text-white/20' : 'text-slate-300'}`}>Término</span>
                  <span className={`text-[11px] font-bold transition-colors ${isTimerRunning ? 'text-white/80' : 'text-slate-700'}`}>{task.horario_fim || '--:--'}</span>
                </div>

                {/* Notification Area */}
                <div className={`col-span-2 rounded-lg md:rounded-xl p-3 border flex items-center gap-3 transition-colors ${isTimerRunning ? 'bg-blue-500/5 border-blue-500/10' : 'bg-blue-50 border-blue-100'}`}>
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.5)]"></div>
                  <div className="flex-1 overflow-hidden">
                    <p className={`text-[8px] font-black uppercase tracking-widest mb-0.5 transition-colors ${isTimerRunning ? 'text-blue-400/60' : 'text-blue-400'}`}>Status da Organização</p>
                    <p className={`text-[10px] font-bold truncate transition-colors ${isTimerRunning ? 'text-blue-200' : 'text-blue-600'}`}>
                      {(() => {
                        const now = currentTime;
                        if (nextTask) {
                          const [nh, nm] = nextTask.horario_inicio!.split(':').map(Number);
                          const diff = (nh * 60 + nm) - (now.getHours() * 60 + now.getMinutes());
                          if (diff > 0 && diff <= 15) return `Próxima tarefa em ${diff} min: ${nextTask.titulo}`;
                        }

                        if (task.horario_fim) {
                          const [eh, em] = task.horario_fim!.split(':').map(Number);
                          const diffEnd = (eh * 60 + em) - (now.getHours() * 60 + now.getMinutes());
                          if (diffEnd > 0 && diffEnd <= 10) return `Atenção: Término previsto em ${diffEnd} minutos!`;
                          if (diffEnd < 0) return `Execução ultrapassou o horário em ${Math.abs(diffEnd)} min.`;
                        }

                        return nextTask ? `Próxima às ${nextTask.horario_inicio}: ${nextTask.titulo}` : "Sem tarefas pendentes hoje";
                      })()}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* COLUNA ESQUERDA (AGORA ABAIXO NO MOBILE): Pool e Diário (7 colunas) */}
        <div className="lg:col-span-7 flex flex-col relative h-auto md:h-full overflow-hidden order-2 lg:order-1">

          {/* Header Controls for Chat - Mobile side-by-side buttons */}
          <div className="flex items-center gap-2 mb-2 shrink-0 px-4 md:px-0">
            <button
              onClick={() => setShowDiaryMobileModal(true)}
              className={`lg:hidden flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${isTimerRunning ? 'bg-white/10 text-white/60 hover:bg-white/20' : 'bg-white text-slate-500 hover:bg-slate-50 border border-slate-200 shadow-sm'}`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
              Diário
            </button>
            <div className={`hidden lg:flex flex-1 items-center gap-4`}>
              <h4 className={`text-[10px] md:text-sm font-black uppercase tracking-widest flex items-center gap-2 ${isTimerRunning ? 'text-white/40' : 'text-slate-400'}`}>
                <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                Diário de Bordo
              </h4>
              {task.acompanhamento && task.acompanhamento.length > 0 && (
                <button
                  onClick={handleCopyAllHistory}
                  className={`flex items-center gap-2 px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all ${isTimerRunning ? 'bg-white/5 text-white/40 hover:bg-white/10 hover:text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                  Copiar Tudo
                </button>
              )}
            </div>
            <button
              onClick={() => setShowPool(!showPool)}
              className={`flex-1 lg:flex-none flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${showPool
                ? 'bg-blue-600 text-white'
                : isTimerRunning ? 'bg-white/10 text-white/60 hover:bg-white/20' : 'bg-white text-slate-500 hover:bg-slate-50 border border-slate-200 shadow-sm'
                }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z" /></svg>
              {showPool ? 'Ocultar Arquivos' : 'Ver Arquivos'}
            </button>
          </div>

          {/* Main Area: Chat or Pool Overlay */}
          <div className={`flex-1 !rounded-none md:rounded-[2.5rem] border relative overflow-hidden flex flex-col transition-colors ${isTimerRunning ? 'bg-white/5 border-white/10 backdrop-blur-sm' : 'bg-white border-slate-200 shadow-sm'}`}>

            {/* POOL OVERLAY */}
            {showPool && (
              <div className={`fixed lg:absolute inset-0 z-[250] lg:z-20 backdrop-blur-xl flex flex-col animate-in slide-in-from-top-4 ${isTimerRunning ? 'bg-[#050505]/95' : 'bg-slate-50/95'}`}>
                <div className={`p-6 border-b flex items-center justify-between ${isTimerRunning ? 'border-white/10' : 'border-slate-200'}`}>
                  <h3 className="text-sm font-black text-blue-400 uppercase tracking-widest">Pool de Dados do Projeto</h3>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newPoolItem}
                      onChange={e => setNewPoolItem(e.target.value)}
                      placeholder="Adicionar link..."
                      className={`border rounded-lg px-3 py-1.5 text-xs outline-none focus:border-blue-500 w-48 transition-colors ${isTimerRunning ? 'bg-white/10 border-white/10 text-white placeholder:text-white/20' : 'bg-white border-slate-200 text-slate-800 placeholder:text-slate-400'}`}
                      onKeyDown={e => e.key === 'Enter' && handleAddPoolItem(newPoolItem)}
                    />
                    <button onClick={() => setShowPool(false)} className={`p-2 rounded-lg transition-colors ${isTimerRunning ? 'hover:bg-white/10 text-white/40 hover:text-white' : 'hover:bg-slate-100 text-slate-400 hover:text-slate-600'}`}>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto custom-scrollbar p-6 grid grid-cols-1 md:grid-cols-2 gap-4 content-start">
                  {(task.pool_dados || []).map((item) => (
                    <div key={item.id} className={`p-4 rounded-none md:rounded-2xl border flex items-center gap-4 transition-all group ${isTimerRunning ? 'bg-white/5 border-white/5 hover:border-white/20' : 'bg-white border-slate-200 hover:border-slate-300 shadow-sm'}`}>
                      <div className={`w-10 h-10 rounded-lg md:rounded-xl flex items-center justify-center shrink-0 ${item.tipo === 'arquivo' ? 'bg-amber-500/20 text-amber-500' :
                        item.tipo === 'telefone' ? 'bg-emerald-500/20 text-emerald-500' :
                          'bg-blue-500/20 text-blue-500'
                        }`}>
                        {item.tipo === 'arquivo' && <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>}
                        {item.tipo === 'telefone' && <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.022-.014-.503-.245-.583-.273-.08-.027-.138-.04-.197.048-.058.088-.227.288-.278.346-.05.058-.1.066-.188.022-.088-.044-.372-.137-.708-.437-.26-.231-.437-.515-.487-.603-.05-.088-.005-.135.039-.179.04-.04.088-.103.131-.154.044-.051.059-.088.088-.146.03-.058.015-.11-.008-.154-.022-.044-.197-.474-.27-.65-.072-.172-.143-.149-.197-.151l-.168-.002c-.058 0-.154.022-.234.11-.08.088-.307.3-.307.732 0 .432.315.849.359.907.044.058.62 1.04 1.502 1.42.21.09.372.143.5.184.21.067.4.057.55.035.168-.024.503-.205.574-.403.072-.198.072-.367.051-.403-.021-.037-.08-.058-.168-.102z" /><path d="M12 2C6.477 2 2 6.477 2 12c0 1.891.524 3.66 1.434 5.168L2 22l4.958-1.412A9.957 9.957 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18a7.96 7.96 0 01-4.07-1.112l-.292-.174-3.024.863.878-2.946-.19-.302A7.957 7.957 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z" /></svg>}
                        {item.tipo === 'link' && <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm font-bold truncate ${isTimerRunning ? 'text-white/90' : 'text-slate-800'}`}>{item.nome || item.valor}</p>
                        <p className={`text-[10px] truncate ${isTimerRunning ? 'text-white/40' : 'text-slate-400'}`}>{new Date(item.data_criacao).toLocaleString('pt-BR')}</p>
                      </div>
                      <div className="flex gap-2">
                        <a href={item.valor} target="_blank" rel="noreferrer" className={`p-2 rounded-lg transition-colors ${isTimerRunning ? 'bg-white/10 hover:bg-white/20 text-white' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'}`} title="Abrir">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                        </a>
                        <button onClick={() => removePoolItem(item.id)} className="p-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 rounded-lg transition-colors" title="Excluir">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        </button>
                      </div>
                    </div>
                  ))}
                  {(task.pool_dados || []).length === 0 && (
                    <div className="col-span-full py-20 text-center">
                      <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 border ${isTimerRunning ? 'bg-white/5 border-white/5' : 'bg-slate-100 border-slate-200'}`}>
                        <svg className={`w-10 h-10 ${isTimerRunning ? 'text-white/20' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z" /></svg>
                      </div>
                      <p className={`text-xs font-medium ${isTimerRunning ? 'text-white/30' : 'text-slate-400'}`}>Nenhum arquivo no projeto</p>
                      <p className={`text-[10px] mt-1 ${isTimerRunning ? 'text-white/20' : 'text-slate-300'}`}>Use o menu de anexo ou arraste arquivos</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* CHAT/DIARY INTERFACE - Oculto no mobile para usar Modal */}
            <div 
              onScroll={handleDiaryScroll}
              className="flex-1 min-h-[350px] md:min-h-0 overflow-y-auto custom-scrollbar p-0 md:p-6 hidden lg:flex flex-col gap-4 relative z-10"
            >
              {/* Mensagem de Boas-vindas para contexto */}
              <div className="flex justify-center mb-6">
                <div className={`border rounded-full px-4 py-2 text-[10px] uppercase tracking-widest font-black ${isTimerRunning ? 'bg-white/5 border-white/5 text-white/40' : 'bg-slate-100 border-slate-200 text-slate-400'}`}>
                  Início da Sessão • {new Date(task.data_criacao || Date.now()).toLocaleDateString()}
                </div>
              </div>

              {task.acompanhamento && task.acompanhamento.map((entry, idx) => (
                <div key={idx} className="flex flex-col gap-1 items-start animate-in fade-in slide-in-from-bottom-2 duration-300 w-full">
                  <div className={`p-4 !rounded-none md:rounded-2xl rounded-tl-none border max-w-full md:max-w-[90%] shadow-lg relative group ${isTimerRunning ? 'bg-[#1A1A1A] border-white/10' : 'bg-white border-slate-100 shadow-slate-200'}`}>
                    {renderDiaryContent(entry.nota)}
                    <div className="flex items-center justify-between mt-2 gap-4">
                      <span className={`text-[9px] font-black uppercase tracking-wider ${isTimerRunning ? 'text-white/30' : 'text-slate-300'}`}>
                        {new Date(entry.data).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                      </span>

                      <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onClick={() => handleCopyMessage(entry.nota)} className={`transition-colors ${isTimerRunning ? 'text-white/40 hover:text-emerald-400' : 'text-slate-400 hover:text-emerald-500'}`} title="Copiar">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                        </button>
                        <button onClick={() => handleEditDiaryEntry(idx)} className={`transition-colors ${isTimerRunning ? 'text-white/40 hover:text-blue-400' : 'text-slate-400 hover:text-blue-500'}`} title="Editar">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                        </button>
                        <button onClick={() => handleDeleteDiaryEntry(idx)} className={`transition-colors ${isTimerRunning ? 'text-white/40 hover:text-rose-500' : 'text-slate-400 hover:text-rose-500'}`} title="Excluir">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}

              {isUploading && (
                <div className="flex flex-col gap-1 items-start animate-in fade-in slide-in-from-bottom-2 duration-300 w-full opacity-60">
                  <div className={`p-4 rounded-none md:rounded-2xl rounded-tl-none border max-w-[90%] shadow-lg ${isTimerRunning ? 'bg-[#1A1A1A] border-white/10' : 'bg-white border-slate-100 shadow-slate-200'}`}>
                    <div className="flex items-center gap-3">
                      <div className="w-4 h-4 rounded-full border-2 border-slate-300 border-t-blue-500 animate-spin"></div>
                      <p className={`text-xs font-bold ${isTimerRunning ? 'text-white/60' : 'text-slate-500'}`}>Enviando arquivos...</p>
                    </div>
                  </div>
                </div>
              )}

              {(!task.acompanhamento || task.acompanhamento.length === 0) && (
                <div className="flex-1 flex flex-col items-center justify-center text-center opacity-30 mt-10">
                  <p className={`text-sm font-medium mb-2 ${isTimerRunning ? 'text-white' : 'text-slate-800'}`}>Tudo pronto para começar?</p>
                  <p className={`text-xs ${isTimerRunning ? 'text-white/60' : 'text-slate-500'}`}>Registre seu diário de execução abaixo.</p>
                </div>
              )}
              {/* Invisible spacer for scrolling */}
              <div style={{ float: "left", clear: "both" }} ref={diaryEndRef}></div>
            </div>

            {/* INPUT AREA */}
            <div className={`p-4 border-t shrink-0 ${isTimerRunning ? 'bg-[#0A0A0A] border-white/10' : 'bg-white border-slate-100'}`}>
              <div
                onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('bg-blue-500/10', 'border-blue-500/50'); }}
                onDragLeave={e => { e.currentTarget.classList.remove('bg-blue-500/10', 'border-blue-500/50'); }}
                onDrop={async e => {
                  e.preventDefault();
                  e.currentTarget.classList.remove('bg-blue-500/10', 'border-blue-500/50');
                  const files = e.dataTransfer.files;
                  if (files && files.length > 0) {
                    await handleFileUpload(files);
                  }
                }}
                className={`relative border rounded-none md:rounded-2xl flex items-end gap-2 p-2 transition-all ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-200 focus-within:bg-white focus-within:border-blue-300'}`}
              >
                <div className="relative">
                  <button
                    onClick={() => setShowAttachMenu(!showAttachMenu)}
                    className={`p-3 rounded-lg md:rounded-xl transition-colors shrink-0 ${isTimerRunning ? 'text-white/40 hover:text-white hover:bg-white/10' : 'text-slate-400 hover:text-blue-600 hover:bg-blue-50'}`}
                    title="Anexar"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
                  </button>

                  {/* Attachment Menu */}
                  {showAttachMenu && (
                    <div className={`absolute bottom-12 left-0 w-48 rounded-lg md:rounded-xl border shadow-xl overflow-hidden animate-in zoom-in-95 origin-bottom-left z-[100] ${isTimerRunning ? 'bg-[#1A1A1A] border-white/10' : 'bg-white border-slate-200'}`}>
                      <input type="file" multiple ref={fileInputRef} className="hidden" onChange={handleFileUploadInput} />

                      <button onClick={() => fileInputRef.current?.click()} className={`w-full text-left px-4 py-3 text-xs font-bold flex items-center gap-2 ${isTimerRunning ? 'text-white/80 hover:bg-white/10' : 'text-slate-700 hover:bg-slate-50'}`}>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                        Carregar Arquivo
                      </button>
                      <button onClick={() => {
                        setModalConfig({ type: 'link', isOpen: true });
                        setModalInputValue('');
                        setModalInputName('');
                        setShowAttachMenu(false);
                      }} className={`w-full text-left px-4 py-3 text-xs font-bold flex items-center gap-2 ${isTimerRunning ? 'text-white/80 hover:bg-white/10' : 'text-slate-700 hover:bg-slate-50'}`}>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
                        Inserir Link
                      </button>
                      <button onClick={() => {
                        setModalConfig({ type: 'contact', isOpen: true });
                        setModalInputValue('');
                        setModalInputName('');
                        setShowAttachMenu(false);
                      }} className={`w-full text-left px-4 py-3 text-xs font-bold flex items-center gap-2 ${isTimerRunning ? 'text-white/80 hover:bg-white/10' : 'text-slate-700 hover:bg-slate-50'}`}>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" /></svg>
                        Inserir Contato
                      </button>
                    </div>
                  )}
                </div>

                <textarea
                  value={newFollowUp}
                  onChange={e => setNewFollowUp(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleAddFollowUp();
                    }
                  }}
                  placeholder="Anotação..."
                  className={`w-full bg-transparent border-none outline-none text-xs md:text-sm py-3 min-h-[44px] focus:min-h-[120px] max-h-48 resize-none custom-scrollbar transition-all duration-300 ${isTimerRunning ? 'text-white placeholder:text-white/20' : 'text-slate-800 placeholder:text-slate-400'}`}
                  rows={1}
                />

                <button
                  onClick={handleAddFollowUp}
                  disabled={!newFollowUp.trim()}
                  className={`p-3 rounded-lg md:rounded-xl transition-all shrink-0 ${newFollowUp.trim() ? 'bg-blue-600 text-white hover:bg-blue-500 shadow-lg shadow-blue-900/40' : (isTimerRunning ? 'bg-white/5 text-white/20 cursor-not-allowed' : 'bg-slate-100 text-slate-300 cursor-not-allowed')}`}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                </button>
              </div>
              <div className={`text-[10px] text-center mt-2 font-medium tracking-wide ${isTimerRunning ? 'text-white/20' : 'text-slate-400'}`}>
                <span className="hidden md:inline">Arraste arquivos para anexar • </span>Enter para enviar
              </div>
            </div>
          </div>
        </div>      </div>

      {/* Modal Diário Mobile */}
      {showDiaryMobileModal && (
        <div className={`fixed inset-0 z-[300] flex flex-col animate-in slide-in-from-bottom duration-300 lg:hidden ${isTimerRunning ? 'bg-[#050505] text-white' : 'bg-[#F2F4F7] text-slate-900'}`}>
          <div className="p-6 border-b flex items-center justify-between shrink-0">
            <h3 className="text-sm font-black uppercase tracking-widest text-blue-500">Registros do Diário</h3>
            <button
              onClick={() => setShowDiaryMobileModal(false)}
              className={`p-2 rounded-xl border ${isTimerRunning ? 'bg-white/5 border-white/10 text-white' : 'bg-white border-slate-200 text-slate-400'}`}
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div 
            onScroll={handleDiaryScroll}
            className="flex-1 overflow-y-auto p-4 flex flex-col gap-4"
          >
            {task.acompanhamento && task.acompanhamento.map((entry, idx) => (
              <div key={idx} className="flex flex-col gap-1 items-start w-full animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className={`p-4 rounded-2xl rounded-tl-none border shadow-lg relative ${isTimerRunning ? 'bg-[#1A1A1A] border-white/10' : 'bg-white border-slate-100 shadow-slate-200'}`}>
                  {renderDiaryContent(entry.nota)}
                  <div className="flex items-center justify-between mt-2 gap-4">
                    <span className={`text-[9px] font-black uppercase tracking-wider ${isTimerRunning ? 'text-white/30' : 'text-slate-300'}`}>
                      {new Date(entry.data).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <div className="flex items-center gap-2">
                      <button onClick={() => handleCopyMessage(entry.nota)} className={`transition-colors ${isTimerRunning ? 'text-white/40 hover:text-emerald-400' : 'text-slate-400 hover:text-emerald-500'}`} title="Copiar">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                      </button>
                      <button onClick={() => handleEditDiaryEntry(idx)} className={`transition-colors ${isTimerRunning ? 'text-white/40 hover:text-blue-400' : 'text-slate-400 hover:text-blue-500'}`} title="Editar">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                      </button>
                      <button onClick={() => handleDeleteDiaryEntry(idx)} className={`transition-colors ${isTimerRunning ? 'text-white/40 hover:text-rose-500' : 'text-slate-400 hover:text-rose-500'}`} title="Excluir">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {(!task.acompanhamento || task.acompanhamento.length === 0) && (
              <div className="flex-1 flex flex-col items-center justify-center text-center opacity-30 mt-10">
                <p className={`text-sm font-medium ${isTimerRunning ? 'text-white' : 'text-slate-800'}`}>Nenhum registro no diário ainda.</p>
              </div>
            )}
            {/* Invisible spacer for scrolling Mobile */}
            <div style={{ float: "left", clear: "both" }} ref={diaryMobileEndRef}></div>
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {isConfirmModalOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-[#111] border border-white/10 w-full max-w-sm rounded-none md:rounded-[2.5rem] p-10 shadow-2xl animate-in zoom-in-95 duration-300 text-center">
            <div className="w-20 h-20 bg-emerald-500/10 text-emerald-500 rounded-full flex items-center justify-center mx-auto mb-6">
              <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
            </div>
            <h3 className="text-white font-black text-2xl mb-2 tracking-tight">Concluir Tarefa?</h3>
            <p className="text-slate-400 text-sm mb-8 leading-relaxed">Você confirma a conclusão da ação <strong>{task.titulo}</strong>?</p>
            <div className="flex gap-4">
              <button
                onClick={() => setIsConfirmModalOpen(false)}
                className="flex-1 px-6 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-white/5 transition-all"
              >
                Agora não
              </button>
              <button
                onClick={confirmCompletion}
                className="flex-1 bg-emerald-500 text-white px-6 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-emerald-600 transition-all shadow-xl shadow-emerald-500/20"
              >
                Sim, concluída
              </button>
            </div>
          </div>
        </div>
      )}

      {/* GLOBAL MODAL */}
      {modalConfig.isOpen && (
        <div className="fixed inset-0 z-[300] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
          <div className={`w-full max-w-md p-6 rounded-none md:rounded-3xl shadow-2xl scale-100 animate-in zoom-in-95 duration-200 ${isTimerRunning ? 'bg-[#1A1A1A] border border-white/10 text-white' : 'bg-white text-slate-900 border border-slate-200'}`}>
            <h3 className="text-lg font-black tracking-tight mb-4">
              {modalConfig.type === 'link' && 'Inserir Link'}
              {modalConfig.type === 'contact' && 'Inserir Contato'}
              {modalConfig.type === 'edit_diary' && 'Editar Anotação'}
              {modalConfig.type === 'confirm_delete' && 'Confirmar Exclusão'}
              {modalConfig.type === 'reset_timer' && 'Reiniciar Cronômetro'}
              {modalConfig.type === 'file_upload' && 'Carregar Arquivo'}
            </h3>

            {(modalConfig.type === 'link' || modalConfig.type === 'contact' || modalConfig.type === 'file_upload') && (
              <div className="flex flex-col gap-4">
                <div>
                  <label className={`text-[10px] uppercase font-bold tracking-widest opacity-50 mb-1.5 block ${isTimerRunning ? 'text-white' : 'text-slate-500'}`}>
                    {modalConfig.type === 'file_upload' ? 'Nome do Arquivo' : 'Nome (Opcional)'}
                  </label>
                  <input
                    type="text"
                    value={modalInputName}
                    onChange={e => setModalInputName(e.target.value)}
                    className={`w-full p-3 rounded-lg md:rounded-xl outline-none text-sm font-medium transition-all ${isTimerRunning ? 'bg-white/5 border border-white/10 focus:border-white/30 text-white' : 'bg-slate-50 border border-slate-200 focus:border-blue-500 text-slate-800'}`}
                    placeholder={modalConfig.type === 'link' ? "Ex: Documento Google" : modalConfig.type === 'file_upload' ? "Nome do arquivo..." : "Ex: João Silva"}
                    autoFocus
                  />
                </div>
                {modalConfig.type !== 'file_upload' && (
                  <div>
                    <label className={`text-[10px] uppercase font-bold tracking-widest opacity-50 mb-1.5 block ${isTimerRunning ? 'text-white' : 'text-slate-500'}`}>
                      {modalConfig.type === 'link' ? 'URL' : 'Número / Contato'}
                    </label>
                    <input
                      type="text"
                      value={modalInputValue}
                      onChange={e => setModalInputValue(e.target.value)}
                      className={`w-full p-3 rounded-lg md:rounded-xl outline-none text-sm font-medium transition-all ${isTimerRunning ? 'bg-white/5 border border-white/10 focus:border-white/30 text-white' : 'bg-slate-50 border border-slate-200 focus:border-blue-500 text-slate-800'}`}
                      placeholder={modalConfig.type === 'link' ? 'https://...' : '(11) 9...'}
                      onKeyDown={e => e.key === 'Enter' && handleModalConfirm()}
                    />
                  </div>
                )}
                {modalConfig.type === 'file_upload' && pendingFile && (
                  <div className={`p-4 rounded-xl border flex items-center gap-3 ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-100'}`}>
                    <div className="w-10 h-10 bg-blue-500/10 text-blue-500 rounded-lg flex items-center justify-center">
                       <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-[10px] font-black uppercase tracking-widest opacity-40 ${isTimerRunning ? 'text-white' : 'text-slate-900'}`}>Deseja carregar este arquivo?</p>
                      <p className={`text-xs font-bold truncate ${isTimerRunning ? 'text-white' : 'text-slate-700'}`}>{pendingFile.name}</p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {modalConfig.type === 'edit_diary' && (
              <div>
                <textarea
                  value={modalInputValue}
                  onChange={e => setModalInputValue(e.target.value)}
                  className={`w-full p-3 rounded-lg md:rounded-xl outline-none text-sm font-medium transition-all min-h-[120px] resize-none ${isTimerRunning ? 'bg-white/5 border border-white/10 focus:border-white/30 text-white' : 'bg-slate-50 border border-slate-200 focus:border-blue-500 text-slate-800'}`}
                  autoFocus
                />
              </div>
            )}

            {modalConfig.type === 'confirm_delete' && (
              <p className={`text-sm opacity-70 ${isTimerRunning ? 'text-white' : 'text-slate-600'}`}>Tem certeza que deseja excluir este item permanentemente?</p>
            )}

            {modalConfig.type === 'reset_timer' && (
              <p className={`text-sm opacity-70 ${isTimerRunning ? 'text-white' : 'text-slate-600'}`}>Deseja zerar totalmente o tempo registrado nesta tarefa? Esta ação não pode ser desfeita.</p>
            )}

            <div className="flex gap-3 mt-6 justify-end">
              <button
                onClick={() => setModalConfig({ ...modalConfig, isOpen: false })}
                className={`px-4 py-2 rounded-lg md:rounded-xl text-xs font-bold uppercase tracking-wider transition-colors ${isTimerRunning ? 'hover:bg-white/10 text-white/60' : 'hover:bg-slate-100 text-slate-500'}`}
              >
                Cancelar
              </button>
              <button
                onClick={handleModalConfirm}
                className={`px-6 py-2 rounded-lg md:rounded-xl text-xs font-bold uppercase tracking-wider text-white shadow-lg transition-all transform active:scale-95 ${modalConfig.type === 'confirm_delete' || modalConfig.type === 'reset_timer'
                  ? 'bg-rose-500 hover:bg-rose-600 shadow-rose-500/20'
                  : 'bg-blue-600 hover:bg-blue-700 shadow-blue-600/20'
                  }`}
              >
                Confirmar
              </button>
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
  const [isProcessing, setIsProcessing] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [sortOrder, setSortOrder] = useState<'date-desc' | 'date-asc'>('date-desc');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isArchivedIdeasOpen, setIsArchivedIdeasOpen] = useState(false);

  // Gravador
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const activeIdeas = ideas
    .filter(i => i.status !== 'archived')
    .filter(i => i.text.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => {
      if (sortOrder === 'date-desc') return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });

  const archivedIdeas = ideas
    .filter(i => i.status === 'archived')
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
      <div className="animate-in grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 pb-20 px-0">
        <button
          onClick={() => setActiveTool('brainstorming')}
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-200 shadow-none md:shadow-xl hover:shadow-none md:hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 -ml-px -mt-px md:m-0"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-blue-50 rounded-none md:rounded-2xl flex items-center justify-center text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Notas Rápidas</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Registre notas rápidas para organizar depois.</p>
          </div>
        </button>

        <button
          disabled
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-100 shadow-none md:shadow-sm opacity-60 grayscale cursor-not-allowed text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 relative overflow-hidden -ml-px -mt-px md:m-0"
        >
          <div className="absolute top-2 right-2 md:top-4 md:right-4 bg-slate-100 text-slate-400 text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded-full">Em Breve</div>
          <div className="w-12 h-12 md:w-16 md:h-16 bg-slate-50 rounded-none md:rounded-2xl flex items-center justify-center text-slate-400 flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-400 tracking-tighter mb-1 md:mb-2">Criação de DFD</h3>
            <p className="text-slate-400 font-medium leading-relaxed italic text-xs md:text-sm">Documento de Formalização.</p>
          </div>
        </button>

        <button
          disabled
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-100 shadow-none md:shadow-sm opacity-60 grayscale cursor-not-allowed text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 relative overflow-hidden -ml-px -mt-px md:m-0"
        >
          <div className="absolute top-2 right-2 md:top-4 md:right-4 bg-slate-100 text-slate-400 text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded-full">Em Breve</div>
          <div className="w-12 h-12 md:w-16 md:h-16 bg-slate-50 rounded-none md:rounded-2xl flex items-center justify-center text-slate-400 flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-400 tracking-tighter mb-1 md:mb-2">Termo de Referência</h3>
            <p className="text-slate-400 font-medium leading-relaxed italic text-xs md:text-sm">Elabore TRs com IA.</p>
          </div>
        </button>

        <button
          disabled
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-100 shadow-none md:shadow-sm opacity-60 grayscale cursor-not-allowed text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 relative overflow-hidden -ml-px -mt-px md:m-0"
        >
          <div className="absolute top-2 right-2 md:top-4 md:right-4 bg-slate-100 text-slate-400 text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded-full">Em Breve</div>
          <div className="w-12 h-12 md:w-16 md:h-16 bg-slate-50 rounded-none md:rounded-2xl flex items-center justify-center text-slate-400 flex-shrink-0">
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

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/m4a' }); // ou audio/webm
        await handleProcessAudio(audioBlob);
        
        // Parar todas as tracks para desligar o ícone de microfone do navegador
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      alert("Permissão de microfone negada ou não disponível.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessing(true);
    try {
      // Converter Blob para Base64
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
    
          // Chamar a Cloud Function
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };
    
          // Adicionar a ideia transcrita ao banco
          if (data.refined) {
            onAddTextIdea(data.refined);
          }
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          alert("Erro ao processar áudio via Hermes AI.");
        } finally {
          setIsProcessing(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessing(false);
    }
  };

  return (
    <>
      <div className="animate-in space-y-12 pb-40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setActiveTool(null)}
              className="p-3 bg-white border border-slate-200 rounded-none md:rounded-2xl text-slate-400 hover:text-slate-900 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight uppercase tracking-widest text-[10px]">Ferramentas / Notas Rápidas</h3>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-4 max-w-4xl mx-auto w-full mb-8 px-0">
          <div className="flex-1 bg-white border border-slate-200 rounded-none md:rounded-xl px-4 py-3 flex items-center gap-3 shadow-none md:shadow-sm focus-within:ring-2 focus-within:ring-blue-100 transition-all">
            <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
            <input
              type="text"
              placeholder="Pesquisar nas notas..."
              className="flex-1 bg-transparent outline-none text-xs md:text-sm font-bold text-slate-700 placeholder:text-slate-400"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
            />
          </div>
          <div className="flex bg-white border border-slate-200 rounded-lg md:rounded-xl p-1 shadow-sm w-fit self-end md:self-auto">
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
          <div className="bg-white p-2 rounded-none md:rounded-[2rem] border-2 border-slate-100 shadow-none md:shadow-xl flex items-center gap-4 focus-within:border-blue-500 transition-all">
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessing}
              className={`p-4 rounded-none md:rounded-2xl transition-all flex-shrink-0 ${
                isRecording 
                  ? 'bg-rose-600 text-white animate-pulse shadow-lg' 
                  : isProcessing
                    ? 'bg-blue-100 text-blue-600 cursor-wait'
                    : 'bg-slate-50 text-slate-400 hover:text-blue-600 hover:bg-blue-50'
              }`}
            >
              {isProcessing ? (
                // Spinner de Carregamento
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              ) : isRecording ? (
                // Ícone de Parar (Quadrado)
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
              ) : (
                // Ícone de Microfone
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
              )}
            </button>

            <input
              type="text"
              disabled={isRecording || isProcessing}
              placeholder={
                isRecording 
                  ? "Gravando... Fale agora para transcrever." 
                  : isProcessing 
                    ? "Hermes AI está processando seu áudio..." 
                    : "Digite ou grave uma nova nota..."
              }
              className={`flex-1 bg-transparent border-none outline-none px-2 py-4 text-sm font-bold text-slate-800 placeholder:text-slate-300 ${(isRecording || isProcessing) ? 'opacity-50' : ''}`}
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
              className="bg-blue-600 text-white h-12 px-8 rounded-lg md:rounded-[1.25rem] text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all shadow-lg shadow-blue-100 active:scale-95"
            >
              Salvar Nota
            </button>
          </div>
        </div>

        <div className="flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 mb-32 md:mb-0">
          {activeIdeas.map(idea => (
            <div key={idea.id} className="bg-white p-5 md:p-8 rounded-none md:rounded-[2.5rem] border border-slate-100 md:border-slate-200 shadow-none md:shadow-lg hover:shadow-none md:hover:shadow-2xl transition-all group flex flex-col relative overflow-hidden -ml-px -mt-px md:m-0">
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
                      className="text-blue-600 hover:bg-blue-50 p-2 rounded-lg md:rounded-xl transition-colors"
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
                        className="text-slate-400 hover:text-blue-600 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Editar"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                      </button>
                      <button
                        onClick={() => onConvertToLog(idea)}
                        className="text-slate-400 hover:text-violet-600 p-2 rounded-lg md:rounded-xl transition-colors"
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
                        className={`p-2 rounded-lg md:rounded-xl transition-colors ${copiedId === idea.id ? 'text-emerald-500 bg-emerald-50' : 'text-slate-400 hover:text-blue-600'}`}
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
                    className="text-emerald-500 hover:bg-emerald-50 p-2 rounded-lg md:rounded-xl transition-colors"
                    title="Concluir / Arquivar"
                  >
                    <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                  </button>
                  <button
                    onClick={() => onDeleteIdea(idea.id)}
                    className="text-slate-300 hover:text-rose-500 p-2 rounded-lg md:rounded-xl transition-colors"
                    title="Excluir Permanentemente"
                  >
                    <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </button>
                </div>
              </div>

              {editingId === idea.id ? (
                <textarea
                  autoFocus
                  className="w-full bg-slate-50 border border-slate-200 rounded-none md:rounded-2xl p-4 text-sm md:text-lg font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 min-h-[100px] resize-none"
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
            <div className="col-span-full py-20 text-center border-4 border-dashed border-slate-100 rounded-none md:rounded-none md:rounded-[3rem]">
              <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Nenhuma nota ativa</p>
              <p className="text-slate-400 text-sm font-medium mt-2">Grave ou digite uma nota para começar.</p>
            </div>
          )}
        </div>

        {/* Seção Retrátil de Ideias Arquivadas */}
        <div className="mt-12 space-y-6">
          <button
            onClick={() => setIsArchivedIdeasOpen(!isArchivedIdeasOpen)}
            className="w-full flex items-center gap-4 group cursor-pointer"
          >
            <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
            <div className="flex items-center gap-2 text-slate-400 group-hover:text-slate-600 transition-colors">
              <h3 className="text-[10px] font-black uppercase tracking-[0.3em]">Notas Arquivadas</h3>
              <svg className={`w-4 h-4 transition-transform duration-300 ${isArchivedIdeasOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
            <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
          </button>

          {isArchivedIdeasOpen && (
            <div className="flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 opacity-60 hover:opacity-100 transition-opacity animate-in slide-in-from-top-4 duration-300">
              {archivedIdeas.map(idea => (
                <div key={idea.id} className="bg-white p-5 md:p-8 rounded-none md:rounded-[2.5rem] border border-slate-100 md:border-slate-200 shadow-none md:shadow-lg hover:shadow-none md:hover:shadow-2xl transition-all group flex flex-col relative overflow-hidden -ml-px -mt-px md:m-0">
                  <div className="flex items-center justify-between mb-3 md:mb-6">
                    <span className="text-[9px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest">{formatDate(idea.timestamp.split('T')[0])}</span>
                    <div className="flex items-center gap-1 md:gap-2 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all">
                      <button
                        onClick={() => onArchiveIdea(idea.id)}
                        className="text-blue-500 hover:bg-blue-50 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Restaurar Ideia"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>
                      </button>
                      <button
                        onClick={() => onDeleteIdea(idea.id)}
                        className="text-slate-300 hover:text-rose-500 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Excluir Permanentemente"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                      </button>
                    </div>
                  </div>

                  <div className="flex-1">
                    <p className="text-slate-500 font-bold italic leading-relaxed mb-3 md:mb-6 text-sm md:text-lg line-clamp-3">
                      "{idea.text}"
                    </p>
                  </div>
                </div>
              ))}
              {archivedIdeas.length === 0 && (
                <div className="col-span-full py-12 text-center">
                  <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhuma nota arquivada</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Input Flutuante Centralizado */}
      {isAddingText && (
        <div className="fixed bottom-24 left-4 right-4 md:left-1/2 md:-translate-x-1/2 w-auto md:w-full md:max-w-2xl z-[110] flex items-center gap-2 animate-in zoom-in-95 slide-in-from-bottom-10 bg-white/90 backdrop-blur-md p-4 rounded-none md:rounded-[2rem] shadow-2xl border border-slate-200">
          <button
            onClick={isRecording ? stopRecording : startRecording}
            className={`p-4 rounded-none md:rounded-2xl transition-all shadow-xl flex-shrink-0 ${
              isRecording 
                ? 'bg-rose-600 text-white animate-pulse shadow-rose-200' 
                : 'bg-white text-slate-400 hover:text-blue-600 border border-slate-200'
            }`}
          >
            {isRecording ? (
              // Ícone de Parar (Quadrado)
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
            ) : (
              // Ícone de Microfone
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
            )}
          </button>
          
          <input
            type="text"
            disabled={isRecording}
            autoFocus
            placeholder={isRecording ? "Gravando... Fale agora." : "Digite ou grave sua nota..."}
            className={`flex-1 bg-white border border-slate-200 rounded-none md:rounded-2xl px-6 py-4 text-sm font-medium focus:ring-4 focus:ring-blue-100 outline-none shadow-sm transition-all ${isRecording ? 'opacity-50' : ''}`}
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
            className="bg-blue-600 text-white p-4 rounded-none md:rounded-2xl hover:bg-blue-700 transition-all shadow-xl shadow-blue-100 flex-shrink-0"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
          </button>
        </div>
      )}

    </>
  );
};

const getBucketStartDate = (label: string): string => {
  const now = new Date();
  now.setHours(0, 0, 0, 0);

  if (label === 'Hoje') return now.toLocaleDateString('en-CA');

  if (label === 'Amanhã') {
    const d = new Date(now);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  if (label === 'Esta Semana') {
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const d = new Date(tomorrow);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  if (label === 'Este Mês') {
    const endOfWeek = new Date(now);
    endOfWeek.setDate(now.getDate() + (6 - now.getDay()));
    const d = new Date(endOfWeek);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  const meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  const lowerLabel = label.toLowerCase();

  const mesIndex = meses.findIndex(m => lowerLabel.includes(m));
  if (mesIndex >= 0) {
    const anoMatch = lowerLabel.match(/\d{4}/);
    if (anoMatch) {
      const ano = parseInt(anoMatch[0]);
      const d = new Date(ano, mesIndex, 1);
      return d.toLocaleDateString('en-CA');
    }
  }

  if (label === 'Atrasadas') {
    const d = new Date(now);
    d.setDate(d.getDate() - 1);
    return d.toLocaleDateString('en-CA');
  }

  return '';
};

const QuickNoteModal = ({ isOpen, onClose, onAddIdea }: { isOpen: boolean, onClose: () => void, onAddIdea: (text: string) => void }) => {
  const [textInput, setTextInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  if (!isOpen) return null;

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        await handleProcessAudio(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };
      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      alert("Permissão de microfone negada ou não disponível.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessing(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };
          if (data.refined) onAddIdea(data.refined);
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          alert("Erro ao processar áudio via Hermes AI.");
        } finally {
          setIsProcessing(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight">Nota Rápida</h3>
            <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-1">Captação Instantânea</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="p-8 space-y-6">
          <div className="bg-slate-50 p-2 rounded-none md:rounded-2xl border-2 border-slate-100 flex items-center gap-4 focus-within:border-blue-500 transition-all">
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessing}
              className={`p-4 rounded-none md:rounded-xl transition-all flex-shrink-0 ${
                isRecording
                  ? 'bg-rose-600 text-white animate-pulse shadow-lg'
                  : isProcessing
                    ? 'bg-blue-100 text-blue-600 cursor-wait'
                    : 'bg-white border border-slate-200 text-slate-400 hover:text-blue-600'
              }`}
            >
              {isProcessing ? (
                <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
              ) : isRecording ? (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
              )}
            </button>
            <input
              autoFocus
              type="text"
              disabled={isRecording || isProcessing}
              placeholder={isRecording ? "Gravando..." : isProcessing ? "Processando..." : "O que está pensando?"}
              className="flex-1 bg-transparent border-none outline-none py-4 text-base font-bold text-slate-800 placeholder:text-slate-300"
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && textInput.trim()) {
                  onAddIdea(textInput);
                  setTextInput('');
                  onClose();
                }
              }}
            />
          </div>
          <div className="flex gap-4">
            <button onClick={onClose} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all">Cancelar</button>
            <button
              onClick={() => {
                if (textInput.trim()) {
                  onAddIdea(textInput);
                  setTextInput('');
                  onClose();
                }
              }}
              disabled={!textInput.trim()}
              className="flex-1 bg-blue-600 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all disabled:opacity-50"
            >
              Salvar Nota
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [rememberMe, setRememberMe] = useState(true);
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState<GoogleCalendarEvent[]>([]);
  const [entregas, setEntregas] = useState<EntregaInstitucional[]>([]);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [showConsolidatedBacklog, setShowConsolidatedBacklog] = useState(false);
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
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [editingResource, setEditingResource] = useState<{ field: string, label: string, value: string } | null>(null);

  const [newLogText, setNewLogText] = useState('');
  const [newLogTipo, setNewLogTipo] = useState<'desenvolvimento' | 'ajuste'>('desenvolvimento');
  const [newLogAttachments, setNewLogAttachments] = useState<PoolItem[]>([]);
  const [editingWorkItem, setEditingWorkItem] = useState<WorkItem | null>(null);
  const [editingWorkItemText, setEditingWorkItemText] = useState('');
  const [editingWorkItemAttachments, setEditingWorkItemAttachments] = useState<PoolItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isQuickNoteModalOpen, setIsQuickNoteModalOpen] = useState(false);
  const [hasAutoExpanded, setHasAutoExpanded] = useState(false);

  // Estados PGC
  const [atividadesPGC, setAtividadesPGC] = useState<AtividadeRealizada[]>([]);
  const [afastamentos, setAfastamentos] = useState<Afastamento[]>([]);
  const [pgcSubView, setPgcSubView] = useState<'audit' | 'heatmap' | 'config' | 'plano'>('audit');
  const [unidades, setUnidades] = useState<{ id: string, nome: string }[]>([]);
  const [sistemasAtivos, setSistemasAtivos] = useState<string[]>([]);

  const [isImportPlanOpen, setIsImportPlanOpen] = useState(false);
  const [isCompletedTasksOpen, setIsCompletedTasksOpen] = useState(false);
  const [brainstormIdeas, setBrainstormIdeas] = useState<BrainstormIdea[]>([]);
  const [activeFerramenta, setActiveFerramenta] = useState<'brainstorming' | null>(null);
  const [isBrainstormingAddingText, setIsBrainstormingAddingText] = useState(false);
  const [convertingIdea, setConvertingIdea] = useState<BrainstormIdea | null>(null);
  const [isSystemSelectorOpen, setIsSystemSelectorOpen] = useState(false);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setAuthLoading(false);
    });
    return () => unsubscribe();
  }, []);

  const handleLogin = async () => {
    try {
      await setPersistence(auth, rememberMe ? browserLocalPersistence : browserSessionPersistence);
      await signInWithPopup(auth, googleProvider);
      showToast("Login realizado com sucesso!", "success");
    } catch (error) {
      console.error("Erro ao fazer login:", error);
      showToast("Erro ao fazer login com Google.", "error");
    }
  };

  const handleLogout = async () => {
    try {
      await signOut(auth);
      showToast("Sessão encerrada.", "info");
    } catch (error) {
      console.error("Erro ao fazer logout:", error);
    }
  };


  // Finance Sync
  useEffect(() => {
    const unsubSistemas = onSnapshot(collection(db, 'sistemas_detalhes'), (snapshot) => {
      setSistemasDetalhes(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Sistema)));
    });

    const unsubGoogleCalendar = onSnapshot(collection(db, 'google_calendar_events'), (snapshot) => {
      setGoogleCalendarEvents(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as GoogleCalendarEvent)));
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
    const unsubscribeSistemasAtivos = onSnapshot(doc(db, 'configuracoes', 'sistemas'), (docSnap) => {
      if (docSnap.exists()) {
        setSistemasAtivos(docSnap.data().lista || []);
      }
    });

    return () => {
      unsubSistemas();
      unsubGoogleCalendar();
      unsubWorkItems();
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
      unsubscribeSistemasAtivos();
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
                  data_conclusao: formatDateLocalISO(new Date())
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
  const [calendarViewMode, setCalendarViewMode] = useState<'month' | 'week' | 'day'>('month');
  const [calendarDate, setCalendarDate] = useState(new Date());

  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeModule, setActiveModule] = useState<'home' | 'dashboard' | 'acoes' | 'financeiro' | 'saude'>('dashboard');
  const [viewMode, setViewMode] = useState<'dashboard' | 'gallery' | 'pgc' | 'licitacoes' | 'assistencia' | 'sistemas' | 'finance' | 'saude' | 'ferramentas' | 'sistemas-dev'>('dashboard');
  const [selectedTask, setSelectedTask] = useState<Tarefa | null>(null);

  // Modal Mode State
  const [taskModalMode, setTaskModalMode] = useState<'default' | 'edit' | 'execute'>('default');

  // Reset modal mode when selected task is cleared
  useEffect(() => {
    if (!selectedTask) {
      setTaskModalMode('default');
    }
  }, [selectedTask]);

  // Sync selectedTask with updated data from Firestore to ensure components have latest data
  useEffect(() => {
    if (selectedTask) {
      const updated = tarefas.find(t => t.id === selectedTask.id);
      if (updated && JSON.stringify(updated) !== JSON.stringify(selectedTask)) {
        setSelectedTask(updated);
      }
    }
  }, [tarefas, selectedTask]);
  const [planosTrabalho, setPlanosTrabalho] = useState<PlanoTrabalho[]>([]);
  const [statusFilter, setStatusFilter] = useState<Status[]>(['em andamento']);
  const [areaFilter, setAreaFilter] = useState<string>('TODAS');
  const [sortOption, setSortOption] = useState<SortOption>('date-asc');
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [notifications, setNotifications] = useState<HermesNotification[]>([]);
  const [isNotificationCenterOpen, setIsNotificationCenterOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [syncData, setSyncData] = useState<any>(null);
  const [activePopup, setActivePopup] = useState<HermesNotification | null>(null);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [exams, setExams] = useState<HealthExam[]>([]);
  const [lastBackPress, setLastBackPress] = useState(0);

  const handleDashboardNavigate = (view: 'gallery' | 'finance' | 'saude' | 'sistemas-dev') => {
    setViewMode(view);
    if (view === 'gallery' || view === 'sistemas-dev') setActiveModule('acoes');
    else if (view === 'finance') setActiveModule('financeiro');
    else if (view === 'saude') setActiveModule('saude');
  };

  // Sync state changes with history to enable back button
  useEffect(() => {
    // Only push if we are NOT at dashboard (root)
    if (activeModule !== 'dashboard' || viewMode !== 'dashboard' || selectedSystemId || isLogsModalOpen || activeFerramenta) {
      window.history.pushState({ activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta }, "", window.location.pathname);
    }
  }, [activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta]);

  // Handle hardware/browser back button
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      if (isLogsModalOpen) {
        setIsLogsModalOpen(false);
        e.preventDefault();
      } else if (selectedSystemId) {
        setSelectedSystemId(null);
        e.preventDefault();
      } else if (activeFerramenta) {
        setActiveFerramenta(null);
        e.preventDefault();
      } else if (viewMode !== 'dashboard') {
        setActiveModule('dashboard');
        setViewMode('dashboard');
        e.preventDefault();
      } else {
        const now = Date.now();
        if (now - lastBackPress < 2000) return;
        e.preventDefault();
        setLastBackPress(now);
        showToast("Pressione voltar novamente para minimizar", "info");
        // Maintain the history entry to wait for second press
        window.history.pushState(null, "", window.location.pathname);
      }
    };

    // Initial dummy state to capture back press
    if (window.history.state === null) {
      window.history.pushState({}, "", window.location.pathname);
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta, lastBackPress]);
  const [appSettings, setAppSettings] = useState<AppSettings>(DEFAULT_APP_SETTINGS);
  const [isHabitsReminderOpen, setIsHabitsReminderOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'notifications' | 'context' | 'sistemas'>('notifications');

  // --- HermesNotification System & App Settings ---

  // --- Firebase Cloud Messaging (FCM) & Push Notifications ---
  useEffect(() => {
    const setupFCM = async () => {
      if (!messaging) return;
      try {
        console.log('Iniciando configuração de Push...');
        const permission = await Notification.requestPermission();
        console.log('Permissão de Notificação:', permission);

        if (permission === 'granted') {
          // Garante que o service worker está registrado antes de pedir o token
          const registration = await navigator.serviceWorker.ready;

          const token = await getToken(messaging, {
            vapidKey: 'BBXF5bMrAdRIXKGLHXMzsZSREaQoVo2VbVgcJJkA7_qu05v2GOcCqgLRjc54airIqf087t46jvggg7ZdmPzuqiE',
            serviceWorkerRegistration: registration
          }).catch(err => {
            console.error("Erro ao obter FCM Token:", err);
            return null;
          });

          if (token) {
            console.log('FCM Token obtido com sucesso:', token);
            await setDoc(doc(db, 'fcm_tokens', token), {
              token,
              last_updated: new Date().toISOString(),
              platform: 'web_pwa',
              userAgent: navigator.userAgent
            });
            console.log('Token persistido no Firestore.');
          } else {
            console.warn('FCM Token não foi gerado. Verifique a VAPID Key no Firebase Console.');
          }
        }
      } catch (error) {
        console.error('Falha crítica no setup do FCM:', error);
      }
    };

    setupFCM();

    const unsubscribe = onMessage(messaging!, (payload) => {
      console.log('Mensagem PUSH recebida em primeiro plano:', payload);
      if (payload.notification) {
        const newNotif: HermesNotification = {
          id: Math.random().toString(36).substr(2, 9),
          title: payload.notification.title || 'Hermes',
          message: payload.notification.body || '',
          type: 'info',
          timestamp: new Date().toISOString(),
          isRead: false,
          link: (payload.data as any)?.link || ""
        };
        setNotifications(prev => [newNotif, ...prev]);
        setActivePopup(newNotif);
      }
    });

    return () => unsubscribe();
  }, []);

  const emitNotification = async (title: string, message: string, type: 'info' | 'warning' | 'success' | 'error' = 'info', link?: string, id?: string) => {
    const newNotif: HermesNotification = {
      id: id || Math.random().toString(36).substr(2, 9),
      title,
      message,
      type,
      timestamp: new Date().toISOString(),
      isRead: false,
      link: link || ""
    };

    // 1. Atualiza estado local para feedback imediato (evita duplicados por ID)
    setNotifications(prev => {
      if (prev.some(n => n.id === newNotif.id)) return prev;
      return [newNotif, ...prev];
    });
    setActivePopup(newNotif);

    // 2. Persiste no Firestore para disparar Push Notification via Cloud Function
    try {
      // Usa setDoc com ID específico para evitar duplicados no Firestore
      // Garante que não há campos undefined
      const firestoreData = JSON.parse(JSON.stringify(newNotif));

      // Verifica configurações globais de push
      const shouldSendPush = appSettings.notifications?.enablePush !== false; // Default true

      await setDoc(doc(db, 'notificacoes', newNotif.id), {
        ...firestoreData,
        sent_to_push: !shouldSendPush // Se não deve enviar, já marca como enviado para a function ignorar
      });
    } catch (err) {
      console.error("Erro ao persistir notificação:", err);
      // Feedback visual do erro para o usuário (agora que estamos validando)
      alert(`Erro no sistema de notificação: ${err}`);
    }
  };

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
    const todayStr = formatDateLocalISO(new Date());
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

  const handleNotificationNavigate = (link: string) => {
    if (!link) return;

    switch (link) {
      case 'acoes':
        setActiveModule('acoes');
        setViewMode('gallery');
        break;
      case 'financeiro':
        setActiveModule('financeiro');
        setViewMode('finance');
        break;
      case 'pgc':
        setActiveModule('acoes');
        setViewMode('pgc');
        break;
      case 'saude':
        setActiveModule('saude');
        setViewMode('saude');
        break;
      case 'sistemas':
        setActiveModule('acoes');
        setViewMode('sistemas-dev');
        break;
      default:
        break;
    }
  };

  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // HermesNotification System Triggers (Time-based: Habits, Weigh-in)
  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date();
      const current_time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

      // Calculate local date string (YYYY-MM-DD) to match local time configuration
      const todayStr = formatDateLocalISO(now);

      // 1. Habits Reminder
      if (appSettings.notifications.habitsReminder.enabled && current_time === appSettings.notifications.habitsReminder.time) {
        const lastOpen = localStorage.getItem('lastHabitsReminderDate');
        if (lastOpen !== todayStr) {
          setIsHabitsReminderOpen(true);
          localStorage.setItem('lastHabitsReminderDate', todayStr);
        }
      }

      // 2. Weigh-in Reminder (Bell HermesNotification)
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
            emitNotification(
              "Lembrete de Pesagem",
              "Hora de registrar seu peso para acompanhar sua evolução no módulo Saúde!",
              'info',
              'saude',
              `weigh_in_${todayStr}`
            );
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
            emitNotification("Hermes: Próxima Tarefa", msg, 'info', '', `task_start_${t.id}_${todayStr}`);
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
            emitNotification("Hermes: Encerramento de Tarefa", msg, 'info', '', `task_end_${t.id}_${todayStr}`);
            localStorage.setItem(`lastEndRemind_${t.id}`, todayStr);
          }
        }
      });

      // 4. Custom Notifications
      const customNotifs = appSettings.notifications.custom || [];
      customNotifs.forEach((notif: CustomNotification) => {
         if (!notif.enabled) return;
         if (notif.time === current_time) {
            const NOTIF_KEY = `lastCustomNotif_${notif.id}`;
            const lastSent = localStorage.getItem(NOTIF_KEY);
            
            if (lastSent === todayStr) return;

            let shouldSend = false;
            if (notif.frequency === 'daily') {
               shouldSend = true;
            } else if (notif.frequency === 'weekly') {
               const dayOfWeek = now.getDay(); // 0-6
               if (notif.daysOfWeek && notif.daysOfWeek.includes(dayOfWeek)) {
                  shouldSend = true;
               }
            } else if (notif.frequency === 'monthly') {
               const dayOfMonth = now.getDate();
               if (dayOfMonth === notif.dayOfMonth) {
                 shouldSend = true;
               }
            }

            if (shouldSend) {
               emitNotification("Lembrete Personalizado", notif.message, 'info', '', `custom_${notif.id}_${todayStr}`);
               localStorage.setItem(NOTIF_KEY, todayStr);
            }
         }
      });

    }, 10000); // Check every 10 seconds to ensure we don't miss the minute
    return () => clearInterval(interval);
  }, [appSettings.notifications, tarefas]);

  // Data-driven Notifications (Budget, Overdue, PGC)
  useEffect(() => {
    const todayStr = formatDateLocalISO(new Date());

    // 1. Overdue Tasks (Once a day check)
    if (appSettings.notifications.overdueTasks.enabled && localStorage.getItem('lastOverdueCheckDate') !== todayStr) {
      const overdueCount = tarefas.filter(t =>
        normalizeStatus(t.status) !== 'concluido' &&
        t.status !== 'excluído' as any &&
        t.data_limite && t.data_limite !== "-" && t.data_limite !== "0000-00-00" &&
        t.data_limite < todayStr
      ).length;

      if (overdueCount > 0) {
        emitNotification(
          "Ações Vencidas",
          `Você tem ${overdueCount} ações fora do prazo. Que tal atualizá-las para hoje?`,
          'warning',
          'acoes',
          `overdue-${todayStr}`
        );
        localStorage.setItem('lastOverdueCheckDate', todayStr);
      }
    }

    // 2. Budget Risk (Whenever data changes, throttled to once per day notification AND real spending increase)
    if (appSettings.notifications.budgetRisk.enabled) {
      const now = new Date();
      const currentMonthStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
      const monthlyBudget = financeSettings.monthlyBudgets?.[currentMonthStr] || financeSettings.monthlyBudget;
      const totalSpend = financeTransactions.filter(t => {
        const d = new Date(t.date);
        return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
      }).reduce((acc, t) => acc + t.amount, 0);

      if (monthlyBudget > 0) {
        const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
        const currentDay = now.getDate();
        const budgetRatio = totalSpend / monthlyBudget;
        const timeRatio = currentDay / daysInMonth;

        // Condition: Over budget velocity AND (New day OR spending increased since last notification)
        const lastNotifiedSpend = parseFloat(localStorage.getItem(`lastBudgetRiskNotifiedSpend_${currentMonthStr}`) || '0');
        const isNewDay = localStorage.getItem('lastBudgetRiskNotifyDate') !== todayStr;
        const hasSpendIncreased = totalSpend > lastNotifiedSpend;

        if (budgetRatio > timeRatio * 1.15 && budgetRatio > 0.1 && hasSpendIncreased && isNewDay) {
          emitNotification(
            "Alerta de Orçamento",
            `Atenção: Gastos elevados! Você já utilizou ${(budgetRatio * 100).toFixed(0)}% do orçamento em ${(timeRatio * 100).toFixed(0)}% do mês.`,
            'warning',
            'financeiro',
            `budget-${todayStr}`
          );
          localStorage.setItem('lastBudgetRiskNotifyDate', todayStr);
          localStorage.setItem(`lastBudgetRiskNotifiedSpend_${currentMonthStr}`, totalSpend.toString());
        }
      }
    }

    // 3. Audit PGC
    if (appSettings.notifications.pgcAudit.enabled && localStorage.getItem('lastPgcNotifyDate') !== todayStr) {
      const now = new Date();
      const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
      if ((daysInMonth - now.getDate()) <= appSettings.notifications.pgcAudit.daysBeforeEnd) {
        emitNotification(
          "Auditoria PGC",
          "O mês está acabando. Verifique no módulo PGC se todas as entregas possuem ações vinculadas.",
          'info',
          'pgc',
          `pgc-${todayStr}`
        );
        localStorage.setItem('lastPgcNotifyDate', todayStr);
      }
    }
  }, [tarefas, financeTransactions, financeSettings, planosTrabalho, appSettings.notifications]);

  // Welcome HermesNotification
  useEffect(() => {
    const hasSeenWelcome = localStorage.getItem('hasSeenWelcome');
    if (!hasSeenWelcome && notifications.length === 0) {
      emitNotification(
        'Bem-vindo ao Hermes',
        'Sistema de notificações ativo. Configure suas preferências no ícone de engrenagem.',
        'info',
        undefined,
        'welcome'
      );
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
      showToast("Nota atualizada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar nota.", "error");
    }
  };

  const handleFinalizeIdeaConversion = async (sistemaId: string) => {
    if (!convertingIdea) return;
    const unit = unidades.find(u => u.id === sistemaId);
    if (!unit) return;

    // Criar o log no sistema ao invés de uma tarefa geral (ação)
    await handleCreateWorkItem(sistemaId, 'ajuste', convertingIdea.text);

    // Remover a nota original após a conversão bem-sucedida
    await deleteDoc(doc(db, 'brainstorm_ideas', convertingIdea.id));

    setIsSystemSelectorOpen(false);
    setConvertingIdea(null);
    showToast("Nota convertida em log do sistema com sucesso!", "success");
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

  const handleCreateWorkItem = async (sistemaId: string, tipo: 'desenvolvimento' | 'ajuste', descricao: string, attachments: PoolItem[] = []) => {
    try {
      if (!descricao.trim()) return;
      await addDoc(collection(db, 'sistemas_work_items'), {
        sistema_id: sistemaId,
        tipo,
        descricao,
        concluido: false,
        data_criacao: new Date().toISOString(),
        pool_dados: attachments
      });
      showToast(`${tipo === 'desenvolvimento' ? 'Desenvolvimento' : 'Ajuste'} registrado!`, "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao criar item.", "error");
    }
  };

  const handleUpdateWorkItem = async (id: string, updates: Partial<WorkItem>) => {
    try {
      await updateDoc(doc(db, 'sistemas_work_items', id), {
        ...updates
      } as any);
      showToast("Item de trabalho atualizado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar item.", "error");
    }
  };

  const handleFileUploadToDrive = async (file: File) => {
    try {
      setIsUploading(true);
      const reader = new FileReader();
      const base64Promise = new Promise<string>((resolve) => {
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1];
          resolve(base64);
        };
      });
      reader.readAsDataURL(file);
      const fileContent = await base64Promise;

      const uploadFunc = httpsCallable(functions, 'upload_to_drive');
      const result = await uploadFunc({
        fileName: file.name,
        fileContent: fileContent,
        mimeType: file.type,
        folderId: appSettings.googleDriveFolderId
      });

      const data = result.data as { fileId: string, webViewLink: string };
      
      const newItem: PoolItem = {
        id: data.fileId,
        tipo: 'arquivo',
        valor: data.webViewLink,
        nome: file.name,
        data_criacao: new Date().toISOString()
      };

      return newItem;
    } catch (err) {
      console.error(err);
      showToast("Erro ao carregar para o Drive.", "error");
      return null;
    } finally {
      setIsUploading(false);
    }
  };

  useEffect(() => {
     const unsub = onSnapshot(collection(db, 'exames'), (snap) => {
        const data = snap.docs.map(d => ({ id: d.id, ...d.data() } as HealthExam));
        setExams(data);
     });
     return () => unsub();
  }, []);

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
      const idea = brainstormIdeas.find(i => i.id === id);
      if (!idea) return;

      const newStatus = idea.status === 'archived' ? 'active' : 'archived';
      await updateDoc(doc(db, 'brainstorm_ideas', id), {
        status: newStatus
      });
      showToast(newStatus === 'archived' ? "Nota concluída e arquivada!" : "Nota restaurada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao processar nota.", "error");
    }
  };

  const handleAddTextIdea = async (text: string) => {
    try {
      await addDoc(collection(db, 'brainstorm_ideas'), {
        text,
        timestamp: new Date().toISOString(),
        status: 'active'
      });
      showToast("Nota registrada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao salvar nota.", "error");
    }
  };

  const handleDeleteIdea = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'brainstorm_ideas', id));
      showToast("Nota removida.", "info");
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



    return () => {
      unsubscribeTarefas();
      unsubscribeAtividades();
      unsubscribeAtividadesPGC();
      unsubscribeAfastamentos();
      unsubscribeUnidades();
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
    const todayStr = formatDateLocalISO(now);

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

  const tarefasAgrupadas: Record<string, Tarefa[]> = useMemo(() => {
    const buckets = {
      atrasadas: [] as Tarefa[],
      hoje: [] as Tarefa[],
      amanha: [] as Tarefa[],
      estaSemana: [] as Tarefa[],
      esteMes: [] as Tarefa[],
      semData: [] as Tarefa[]
    };
    const mesesFuturos: Record<string, { label: string, tasks: Tarefa[] }> = {};

    const now = new Date();
    // Reset hours to ensure clean comparisons
    now.setHours(0, 0, 0, 0);
    const todayStr = now.toLocaleDateString('en-CA'); // YYYY-MM-DD

    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toLocaleDateString('en-CA');

    // End of current week (Saturday)
    const endOfWeek = new Date(now);
    endOfWeek.setDate(now.getDate() + (6 - now.getDay()));
    const endOfWeekStr = endOfWeek.toLocaleDateString('en-CA');

    // End of current month
    const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    const endOfMonthStr = endOfMonth.toLocaleDateString('en-CA');

    filteredAndSortedTarefas.forEach(t => {
      // Sem Data
      if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") {
        buckets.semData.push(t);
        return;
      }

      // Check for valid date format to prevent errors
      if (!/^\d{4}-\d{2}-\d{2}$/.test(t.data_limite)) {
        buckets.semData.push(t);
        return;
      }

      if (t.data_limite < todayStr) {
        buckets.atrasadas.push(t);
      } else if (t.data_limite === todayStr) {
        buckets.hoje.push(t);
      } else if (t.data_limite === tomorrowStr) {
        buckets.amanha.push(t);
      } else if (t.data_limite <= endOfWeekStr) {
        buckets.estaSemana.push(t);
      } else if (t.data_limite <= endOfMonthStr) {
        buckets.esteMes.push(t);
      } else {
        // Future Months
        const parts = t.data_limite.split('-');
        const key = `${parts[0]}-${parts[1]}`; // sortable key YYYY-MM

        if (!mesesFuturos[key]) {
          const dateObj = new Date(Number(parts[0]), Number(parts[1]) - 1, 2);
          const monthName = dateObj.toLocaleString('pt-BR', { month: 'long', year: 'numeric' });
          const label = monthName.charAt(0).toUpperCase() + monthName.slice(1);
          mesesFuturos[key] = { label, tasks: [] };
        }
        mesesFuturos[key].tasks.push(t);
      }
    });

    // Build final object preserving desired order
    const finalGroups: Record<string, Tarefa[]> = {};

    if (buckets.atrasadas.length > 0) finalGroups["Atrasadas"] = buckets.atrasadas;
    if (buckets.hoje.length > 0) finalGroups["Hoje"] = buckets.hoje;
    if (buckets.amanha.length > 0) finalGroups["Amanhã"] = buckets.amanha;
    if (buckets.estaSemana.length > 0) finalGroups["Esta Semana"] = buckets.estaSemana;
    if (buckets.esteMes.length > 0) finalGroups["Este Mês"] = buckets.esteMes;

    // Sort future months chronologically
    Object.keys(mesesFuturos).sort().forEach(key => {
      finalGroups[mesesFuturos[key].label] = mesesFuturos[key].tasks;
    });

    if (buckets.semData.length > 0) finalGroups["Sem Prazo Definido"] = buckets.semData;

    return finalGroups;
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
  const pgcTasks: Tarefa[] = useMemo(() => {
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

  const pgcEntregas: EntregaInstitucional[] = useMemo(() => entregas.filter(e => {
    return e.mes === currentMonth && e.ano === currentYear;
  }), [entregas, currentMonth, currentYear]);

  const pgcTasksAguardando: Tarefa[] = useMemo(() => {
    const currentDeliveryIds = pgcEntregas.map(e => e.id);
    const norm = (val: any) => (val || '').toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();

    return pgcTasks.filter(t => {
      // Regra 1: Deve ser da categoria CLC ou ASSISTÊNCIA
      const isCLC = t.categoria === 'CLC' || (t.projeto && norm(t.projeto).includes('CLC'));
      const isAssist = t.categoria === 'ASSISTÊNCIA' || (t.projeto && (norm(t.projeto).includes('ASSIST') || norm(t.projeto).includes('ESTUDANTIL')));

      if (!isCLC && !isAssist) return false;

      // Regra de Filtro por Data (Visualização Diária)
      // Se estiver na visão de dia, mostra APENAS o que está agendado para aquele dia específico
      if (calendarViewMode === 'day') {
        const targetDateStr = calendarDate.toLocaleDateString('en-CA');
        if (t.data_limite !== targetDateStr) return false;
      }

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
  }, [pgcTasks, pgcEntregas, calendarViewMode, calendarDate]);

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

      const dayStr = formatDateLocalISO(day);

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

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">Hermes está carregando...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex flex-col items-center justify-center p-6">
        <div className="bg-white p-12 rounded-none md:rounded-[3rem] shadow-2xl border border-slate-100 max-w-md w-full text-center animate-in zoom-in-95">
          <div className="w-20 h-20 bg-slate-900 rounded-[2rem] flex items-center justify-center mx-auto mb-8 shadow-xl">
            <span className="text-white text-3xl font-black">H</span>
          </div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight mb-2">Hermes</h1>
          <p className="text-slate-500 text-sm font-medium mb-10 leading-relaxed">
            Bem-vindo ao seu ecossistema de produtividade e gestão à vista.
          </p>
          <button
            onClick={handleLogin}
            className="w-full bg-slate-900 text-white py-5 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] shadow-2xl shadow-slate-200 hover:bg-blue-600 transition-all active:scale-95 flex items-center justify-center gap-4"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.908 3.152-2.112 4.076-1.028.724-2.48 1.408-5.728 1.408-5.104 0-9.272-4.144-9.272-9.232s4.168-9.232 9.272-9.232c2.808 0 4.58 1.104 5.612 2.056l2.312-2.312c-1.936-1.824-4.52-3.112-7.924-3.112-6.524 0-12 5.424-12 12s5.476 12 12 12c3.552 0 6.228-1.172 8.528-3.564 2.376-2.376 3.128-5.704 3.128-8.32 0-.824-.068-1.552-.2-2.224h-11.456z" />
            </svg>
            Entrar com Google
          </button>

          <div className="mt-6 flex items-center justify-center gap-3">
            <input
              type="checkbox"
              id="remember-me"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
            />
            <label htmlFor="remember-me" className="text-[10px] font-black uppercase tracking-widest text-slate-400 cursor-pointer select-none hover:text-slate-600 transition-colors">
              Mantenha-me conectado
            </label>
          </div>
          <p className="text-[8px] font-black text-slate-300 uppercase tracking-widest mt-8">Secure Authentication via Firebase</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col md:flex-row relative">

      {/* Pop-up de Notificação */}
      {activePopup && (
        <div className="fixed bottom-8 left-4 right-4 md:left-8 md:right-auto z-[200] max-w-sm ml-auto mr-auto md:ml-0 md:mr-0 bg-white rounded-none md:rounded-[2.5rem] shadow-[0_30px_60px_rgba(0,0,0,0.25)] border border-slate-100 overflow-hidden animate-in slide-in-from-bottom-12 duration-500">
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
                className="flex-1 px-5 py-3 bg-slate-100 text-slate-500 rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-widest transition-all hover:bg-slate-200"
              >
                Entendido
              </button>
              {activePopup.link && (
                <button
                  onClick={() => {
                    handleNotificationNavigate(activePopup.link);
                    setActivePopup(null);
                  }}
                  className="flex-1 px-5 py-3 bg-slate-900 text-white rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-widest transition-all hover:bg-slate-800 shadow-lg shadow-slate-200"
                >
                  Ver Agora
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Sidebar Desktop */}
      <aside className="hidden md:flex w-72 bg-slate-900 text-white flex-col h-screen sticky top-0 overflow-y-auto shrink-0 z-50 shadow-2xl">
        <div className="p-8 flex flex-col h-full gap-10">
          <div className="flex items-center gap-4">
            <img src="/logo.png" alt="Hermes" className="w-12 h-12 object-contain" />
            <div>
              <h1 className="text-2xl font-black tracking-tighter">HERMES</h1>
              <p className="text-[8px] font-black text-slate-500 uppercase tracking-widest leading-none">Management System</p>
            </div>
          </div>

          <nav className="flex flex-col gap-2">
            {[
              { id: 'dashboard', label: 'Dashboard', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>, active: viewMode === 'dashboard', onClick: () => { setActiveModule('dashboard'); setViewMode('dashboard'); } },
              { id: 'acoes', label: 'Ações', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>, active: activeModule === 'acoes' && (viewMode === 'gallery' || viewMode === 'pgc' || viewMode === 'licitacoes' || viewMode === 'assistencia'), onClick: () => { setActiveModule('acoes'); setViewMode('gallery'); } },
              { id: 'finance', label: 'Financeiro', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>, active: activeModule === 'financeiro', onClick: () => { setActiveModule('financeiro'); setViewMode('finance'); } },
              { id: 'saude', label: 'Saúde', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>, active: activeModule === 'saude', onClick: () => { setActiveModule('saude'); setViewMode('saude'); } },
              { id: 'sistemas', label: 'Sistemas', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>, active: viewMode === 'sistemas-dev', onClick: () => { setActiveModule('acoes'); setViewMode('sistemas-dev'); } },
              { id: 'ferramentas', label: 'Ferramentas', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>, active: viewMode === 'ferramentas', onClick: () => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta(null); } },
            ].map(item => (
              <button
                key={item.id}
                onClick={item.onClick}
                className={`flex items-center gap-4 px-6 py-4 rounded-2xl transition-all duration-300 group ${item.active ? 'bg-white text-slate-900 shadow-xl' : 'text-slate-400 hover:text-white hover:bg-white/5'}`}
              >
                <div className={`${item.active ? 'text-slate-900' : 'group-hover:scale-110 transition-transform duration-300'}`}>
                  {item.icon}
                </div>
                <span className="text-[11px] font-black uppercase tracking-widest">{item.label}</span>
              </button>
            ))}
          </nav>

          <div className="mt-auto flex flex-col gap-6">
            <div className="flex items-center gap-3 bg-white/5 p-4 rounded-2xl border border-white/5">
              {user?.photoURL && (
                <img src={user.photoURL} alt="Profile" className="w-10 h-10 rounded-xl shadow-sm border border-white/10" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-black uppercase tracking-tight text-white truncate">{user?.displayName}</p>
                <button
                  onClick={handleLogout}
                  className="text-[8px] font-black text-slate-500 hover:text-rose-400 uppercase tracking-widest transition-colors"
                >
                  Sair do Sistema
                </button>
              </div>
            </div>
            <p className="text-center text-[8px] font-black text-slate-700 uppercase tracking-widest">
              Hermes v2.5.0 • 2024
            </p>
          </div>
        </div>
      </aside>

      {/* Conteúdo Principal */}
      <div className="flex-1 flex flex-col relative min-h-screen">
        <>
          <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
            <div className="max-w-[1400px] mx-auto px-4 md:px-8 py-3 md:py-4">
              {/* Mobile Header */}
              <div className="flex md:hidden items-center justify-between">
                <div className="flex items-center gap-4">
                  <button
                    onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                    className="p-2 text-slate-700 hover:bg-slate-100 rounded-lg transition-all active:scale-95"
                    aria-label="Menu"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      {isMobileMenuOpen ? (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                      ) : (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" />
                      )}
                    </svg>
                  </button>
                  <div 
                    onClick={() => { setActiveModule('dashboard'); setViewMode('dashboard'); }}
                    className="flex items-center cursor-pointer hover:opacity-80 transition-opacity"
                  >
                    <img src="/logo.png" alt="Hermes" className="w-9 h-9 object-contain" />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <button
                      onClick={() => setIsQuickNoteModalOpen(true)}
                      className="p-1.5 rounded-lg md:rounded-xl hover:bg-slate-100 transition-colors text-amber-500"
                      aria-label="Notas Rápidas"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsSettingsModalOpen(true)}
                      className="p-1.5 rounded-lg md:rounded-xl hover:bg-slate-100 transition-colors"
                      aria-label="Configurações"
                    >
                      <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsNotificationCenterOpen(!isNotificationCenterOpen)}
                      className="p-1.5 rounded-lg md:rounded-xl hover:bg-slate-100 transition-colors relative notification-trigger"
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
                      onNavigate={handleNotificationNavigate}
                    />
                  </div>
                  {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && (
                    <button
                      onClick={() => setIsCreateModalOpen(true)}
                      className="bg-slate-900 text-white p-1.5 rounded-lg md:rounded-xl shadow-lg hover:bg-slate-800 transition-all active:scale-95"
                      aria-label="Criar Ação"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                    </button>
                  )}
                </div>
              </div>

              {/* Desktop Header */}
              <div className="hidden md:flex items-center justify-between gap-4">
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-3">
                    {/* Botão de voltar removido pois agora temos sidebar */}
                    <div 
                      onClick={() => { setActiveModule('dashboard'); setViewMode('dashboard'); }}
                      className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity"
                    >
                      <h1 className="text-xl font-black tracking-tighter text-slate-900 uppercase">{activeModule === 'dashboard' ? 'Painel de Controle' : activeModule === 'acoes' ? 'Gestão de Ações' : activeModule === 'financeiro' ? 'Financeiro' : activeModule === 'saude' ? 'Saúde' : 'Hermes'}</h1>
                    </div>
                  </div>
                  {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && activeModule !== 'financeiro' && activeModule !== 'saude' && activeModule !== 'dashboard' && (
                    <nav className="flex bg-slate-100 p-1 rounded-lg md:rounded-xl border border-slate-200">
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
                          setIsQuickNoteModalOpen(true);
                        }}
                        className="bg-white border border-slate-200 text-amber-500 p-2 rounded-lg md:rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative"
                        aria-label="Notas Rápidas"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                      </button>
                    </div>
                    <div className="relative">
                      <button
                        onClick={() => setIsNotificationCenterOpen(!isNotificationCenterOpen)}
                        className="bg-white border border-slate-200 text-slate-700 p-2 rounded-lg md:rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative notification-trigger"
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
                        onUpdateOverdue={handleUpdateOverdueTasks}
                        onNavigate={handleNotificationNavigate}
                      />
                    </div>
                    {activeModule !== 'dashboard' && (
                      <div className="hidden lg:flex items-center bg-slate-50 border border-slate-200 rounded-lg md:rounded-xl px-4 py-2 w-64 group focus-within:ring-2 focus-within:ring-blue-500 focus-within:bg-white transition-all">
                        <svg className="w-4 h-4 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        <input type="text" placeholder="Pesquisar..." className="bg-transparent border-none outline-none text-xs font-bold text-slate-900 w-full" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
                      </div>
                    )}
                    <button
                      onClick={handleSync}
                      className={`bg-white border border-slate-200 text-slate-700 px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-3 shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative`}
                    >
                      <svg className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                      {isSyncing ? 'Monitorar Sync' : 'Sync Google'}
                      {isSyncing && <span className="absolute -top-1 -right-1 w-3 h-3 bg-blue-500 rounded-full animate-ping"></span>}
                    </button>
                    <button
                      onClick={() => setIsCreateModalOpen(true)}
                      className="bg-slate-900 text-white px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 shadow-lg hover:bg-slate-800 transition-all active:scale-95"
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
              <div className="md:hidden border-t border-slate-200 bg-white shadow-2xl animate-in slide-in-from-top-4 duration-300">
                <nav className="flex flex-col p-4 gap-2">
                  {[
                    { label: '🏠 Dashboard', active: viewMode === 'dashboard', onClick: () => { setActiveModule('dashboard'); setViewMode('dashboard'); } },
                    { label: '📊 Ações', active: activeModule === 'acoes' && (viewMode === 'gallery' || viewMode === 'pgc' || viewMode === 'licitacoes' || viewMode === 'assistencia'), onClick: () => { setActiveModule('acoes'); setViewMode('gallery'); } },
                    { label: '💰 Financeiro', active: activeModule === 'financeiro', onClick: () => { setActiveModule('financeiro'); setViewMode('finance'); } },
                    { label: '❤️ Saúde', active: activeModule === 'saude', onClick: () => { setActiveModule('saude'); setViewMode('saude'); } },
                    { label: '💻 Sistemas', active: viewMode === 'sistemas-dev', onClick: () => { setActiveModule('acoes'); setViewMode('sistemas-dev'); } },
                    { label: '🛠️ Ferramentas', active: viewMode === 'ferramentas', onClick: () => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta(null); } },
                  ].map((item, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        item.onClick();
                        setIsMobileMenuOpen(false);
                      }}
                      className={`px-6 py-4 rounded-2xl text-sm font-black uppercase tracking-widest transition-all ${item.active ? 'bg-slate-900 text-white shadow-lg' : 'bg-slate-50 text-slate-600'}`}
                    >
                      {item.label}
                    </button>
                  ))}

                  <div className="grid grid-cols-2 gap-2 mt-4 pt-4 border-t border-slate-100">
                    <button
                      onClick={() => {
                        handleSync();
                        setIsMobileMenuOpen(false);
                      }}
                      className="px-4 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest bg-blue-50 text-blue-700 flex items-center justify-center gap-2"
                    >
                      <svg className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                      {isSyncing ? 'Sync...' : 'Sync'}
                    </button>
                    <button
                      onClick={() => {
                        setIsSettingsModalOpen(true);
                        setIsMobileMenuOpen(false);
                      }}
                      className="px-4 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest bg-slate-100 text-slate-600 flex items-center justify-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                      Config
                    </button>
                    <button
                      onClick={handleLogout}
                      className="col-span-2 px-4 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest bg-rose-50 text-rose-600 flex items-center justify-center gap-2 mt-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
                      Sair da Conta
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
                  healthDailyHabits={healthDailyHabits}
                  healthSettings={healthSettings}
                  unidades={unidades}
                  sistemasDetalhes={sistemasDetalhes}
                  workItems={workItems}
                  currentMonth={currentMonth}
                  currentYear={currentYear}
                  onNavigate={handleDashboardNavigate}
                />
              ) : viewMode === 'gallery' ? (
                <>
                  {/* Mobile Search Bar */}
                  <div className="lg:hidden px-4 mb-6">
                    <div className="flex items-center bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm focus-within:ring-2 focus-within:ring-blue-500 transition-all">
                      <svg className="w-5 h-5 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                      <input
                        type="text"
                        placeholder="Pesquisar ações..."
                        className="bg-transparent border-none outline-none text-sm font-bold text-slate-900 w-full placeholder:text-slate-400"
                        value={searchTerm === 'filter:unclassified' ? '' : searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                      />
                      {searchTerm && searchTerm !== 'filter:unclassified' && (
                        <button onClick={() => setSearchTerm('')} className="ml-2 text-slate-400 hover:text-slate-600">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-col md:flex-row items-center justify-between mb-8 gap-4 px-4 md:px-0">
                    {/* Layout & Sort Controls */}
                    <div className="flex flex-wrap items-center gap-4 justify-center md:justify-start">
                      {/* Area Filter */}
                      <div className="relative group">
                        <select
                          value={areaFilter}
                          onChange={(e) => setAreaFilter(e.target.value)}
                          className="appearance-none bg-white pl-4 pr-10 py-2 rounded-lg md:rounded-xl border border-slate-200 text-[10px] font-black uppercase tracking-widest text-slate-700 outline-none focus:ring-2 focus:ring-slate-900 shadow-sm hover:border-slate-300 transition-all cursor-pointer"
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
                        <div className="bg-white p-0.5 md:p-1 rounded-lg md:rounded-xl border border-slate-200 inline-flex shadow-sm">
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
                        className="bg-white hover:bg-blue-50 border border-slate-200 text-slate-700 hover:text-blue-700 px-4 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest shadow-sm hover:shadow transition-all flex items-center gap-2 group"
                      >
                        <svg className="w-4 h-4 text-slate-400 group-hover:text-blue-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        Organizar o Dia
                      </button>
                    </div>
                  </div>

                  {dashboardViewMode === 'calendar' ? (
                    <CalendarView
                      tasks={filteredAndSortedTarefas}
                      googleEvents={googleCalendarEvents}
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
                              <div className="flex items-center gap-2 bg-slate-900 p-2 rounded-none md:rounded-2xl animate-in slide-in-from-top-4">
                                <span className="text-[9px] font-black text-white uppercase tracking-widest px-4">Classificar ({selectedTaskIds.length}):</span>
                                <button onClick={() => handleBatchTag('CLC')} className="bg-blue-600 hover:bg-blue-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">CLC</button>
                                <button onClick={() => handleBatchTag('ASSISTÊNCIA')} className="bg-emerald-600 hover:bg-emerald-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">Assistência</button>
                                <button onClick={() => handleBatchTag('GERAL')} className="bg-slate-500 hover:bg-slate-600 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">Geral</button>
                              </div>
                            )}
                          </div>

                          <div className="overflow-x-auto">
                            {/* Desktop Table */}
                            <table className="w-full text-left hidden md:table">
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
                                    onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
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
                              </tbody>
                            </table>

                            {/* Mobile Card View */}
                            <div className="md:hidden divide-y divide-slate-50">
                              {filteredAndSortedTarefas.map((task) => (
                                <div
                                  key={task.id}
                                  onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                                  className={`p-6 space-y-4 hover:bg-slate-50 transition-colors cursor-pointer ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}
                                >
                                  <div className="flex items-start gap-4">
                                    <input
                                      type="checkbox"
                                      checked={selectedTaskIds.includes(task.id)}
                                      onChange={(e) => {
                                        e.stopPropagation();
                                        setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id]);
                                      }}
                                      className="w-6 h-6 rounded-lg border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer shrink-0 mt-1"
                                    />
                                    <div className="flex-1 space-y-2">
                                      <div className="text-sm font-bold text-slate-800 leading-snug">
                                        {task.titulo}
                                      </div>
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest bg-slate-100 px-2 py-0.5 rounded">
                                          {formatDate(task.data_limite)}
                                        </div>
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
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>

                            {filteredAndSortedTarefas.length === 0 && (
                              <div className="py-20 text-center text-slate-300 font-black uppercase tracking-widest italic border-t border-slate-50">
                                Tudo classificado! Bom trabalho.
                              </div>
                            )}
                          </div>
                        </div>

                      ) : (
                        <div className="animate-in border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl bg-white">
                          {Object.keys(tarefasAgrupadas).length > 0 ? (
                            Object.entries(tarefasAgrupadas).map(([label, tasks]: [string, Tarefa[]]) => (
                              <div
                                key={label}
                                className="border-b last:border-b-0 border-slate-200 transition-colors"
                                onDragOver={(e) => {
                                  e.preventDefault();
                                  e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
                                }}
                                onDragLeave={(e) => {
                                  e.currentTarget.style.backgroundColor = '';
                                }}
                                onDrop={(e) => {
                                  e.preventDefault();
                                  e.currentTarget.style.backgroundColor = '';
                                  const taskId = e.dataTransfer.getData('task-id');
                                  if (taskId) {
                                    const date = getBucketStartDate(label);
                                    if (date || label === 'Sem Prazo Definido') {
                                      handleUpdateTarefa(taskId, { data_limite: date });
                                    }
                                  }
                                }}
                              >
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
                                      <div
                                        key={task.id}
                                        draggable
                                        onDragStart={(e) => {
                                          e.dataTransfer.setData('task-id', task.id);
                                          e.currentTarget.style.opacity = '0.5';
                                        }}
                                        onDragEnd={(e) => {
                                          e.currentTarget.style.opacity = '1';
                                        }}
                                      >
                                        <RowCard
                                          task={task}
                                          onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                                          onToggle={handleToggleTarefaStatus}
                                          onDelete={handleDeleteTarefa}
                                          onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                        />
                                      </div>
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
                                    onClick={() => { setSelectedTask(t); setTaskModalMode('execute'); }}
                                    onToggle={handleToggleTarefaStatus}
                                    onDelete={handleDeleteTarefa}
                                    onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}

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
                            <div key={t.id} className="bg-white p-4 rounded-lg md:rounded-xl border border-slate-200 shadow-sm hover:border-amber-400 transition-all cursor-pointer" onClick={() => setSelectedTask(t)}>
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

              ) : viewMode === 'saude' ? (
                <HealthView
                  weights={healthWeights}
                  dailyHabits={healthDailyHabits}
                  settings={healthSettings}
                  onUpdateSettings={handleUpdateHealthSettings}
                  onAddWeight={handleAddHealthWeight}
                  onDeleteWeight={handleDeleteHealthWeight}
                  onUpdateHabits={handleUpdateHealthHabits}
                  exams={exams}
                  onAddExam={async (exam, files) => {
                     let poolItems: PoolItem[] = [];
                     
                     if (files.length > 0 && appSettings.googleDriveFolderId) {
                        try {
                           showToast("Enviando arquivos para o Drive...", "info");
                           // Logic to upload to drive would go here.
                           // For now, we simulate or store metadata, or call a cloud function if available.
                           // Since I cannot implement direct Drive upload here without access token flow in frontend easily,
                           // I will assume the user might copy links or we store file names for now.
                           // Ideally this calls a backend endpoint.
                           
                           // Placeholder for drive upload success
                           poolItems = files.map(f => ({
                              id: Math.random().toString(36).substr(2, 9),
                              tipo: 'arquivo',
                              valor: '#', // The future link
                              nome: f.name,
                              data_criacao: new Date().toISOString()
                           }));
                           showToast("Arquivos indexados. O upload real requer backend.", "info");
                        } catch (e) {
                           console.error(e);
                           showToast("Erro no upload.", "error");
                        }
                     }

                     await addDoc(collection(db, 'exames'), {
                        ...exam,
                        pool_dados: poolItems,
                        data_criacao: new Date().toISOString()
                     });
                     showToast("Registro de saúde adicionado e indexado ao Drive.", "success");
                  }}
                  onDeleteExam={async (id) => {
                     if (window.confirm("Remover este registro?")) {
                        await deleteDoc(doc(db, 'exames', id));
                        showToast("Registro removido.", "info");
                     }
                  }}
                  onUpdateExam={async (id, updates) => {
                     await updateDoc(doc(db, 'exames', id), updates);
                     showToast("Registro atualizado.", "success");
                  }}
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
                  {showConsolidatedBacklog ? (
                    <ConsolidatedBacklogView
                      unidades={unidades}
                      workItems={workItems}
                      onClose={() => setShowConsolidatedBacklog(false)}
                      onUpdateWorkItem={handleUpdateWorkItem}
                      onDeleteWorkItem={handleDeleteWorkItem}
                    />
                  ) : !selectedSystemId ? (
                    /* VISÃO GERAL - LISTA DE SISTEMAS */
                    <>
                      <div className="hidden md:flex bg-white border border-slate-200 rounded-none md:rounded-[2rem] p-8 shadow-sm items-center justify-between mb-8">
                        <div>
                          <h2 className="text-3xl font-black text-slate-900 tracking-tight">Sistemas em Desenvolvimento</h2>
                          <p className="text-slate-500 font-bold mt-1">Gestão do Ciclo de Vida de Software</p>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="bg-violet-100 text-violet-700 px-4 py-2 rounded-lg md:rounded-xl text-sm font-black uppercase tracking-widest">
                            {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length} Sistemas
                          </div>
                          <button
                            onClick={() => setShowConsolidatedBacklog(true)}
                            className="bg-violet-600 text-white px-6 py-3 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-violet-700 transition-all flex items-center gap-3"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                            Backlog Consolidado
                          </button>
                          <button
                            onClick={() => {
                              setSettingsTab('sistemas');
                              setIsSettingsModalOpen(true);
                            }}
                            className="bg-slate-900 text-white px-6 py-3 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center gap-3"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                            Novo Sistema
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 px-0">
                        {unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(unit => {
                          const sysDetails = sistemasDetalhes.find(s => s.id === unit.id) || {
                            id: unit.id,
                            nome: unit.nome.replace('SISTEMA:', '').trim(),
                            status: 'ideia' as SistemaStatus,
                            data_criacao: new Date().toISOString(),
                            data_atualizacao: new Date().toISOString()
                          };
                          const systemName = unit.nome.replace('SISTEMA:', '').trim();
                          const ajustesPendentes = workItems.filter(w => w.sistema_id === unit.id && !w.concluido).length;

                          return (
                            <button
                              key={unit.id}
                              onClick={() => setSelectedSystemId(unit.id)}
                              className="bg-white border border-slate-200 rounded-none md:rounded-[2.5rem] p-8 text-left shadow-none md:shadow-xl hover:shadow-none md:hover:shadow-2xl hover:border-violet-300 transition-all group relative overflow-hidden -ml-px -mt-px md:m-0"
                            >
                              <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                              <div className="relative z-10 space-y-6">
                                <div className="flex justify-between items-start">
                                  <div className="w-14 h-14 bg-violet-100 text-violet-600 rounded-none md:rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform">
                                    <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                                  </div>
                                  <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest ${sysDetails.status === 'producao' ? 'bg-emerald-100 text-emerald-700' :
                                    sysDetails.status === 'desenvolvimento' ? 'bg-blue-100 text-blue-700' :
                                      sysDetails.status === 'testes' ? 'bg-amber-100 text-amber-700' :
                                        'bg-slate-100 text-slate-500'
                                    }`}>
                                    {sysDetails.status === 'prototipacao' ? 'Prototipação' :
                                      sysDetails.status === 'producao' ? 'Produção' :
                                        sysDetails.status}
                                  </span>
                                </div>
                                <div>
                                  <h3 className="text-xl font-black text-slate-900 mb-1 group-hover:text-violet-700 transition-colors">{systemName}</h3>
                                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                                    Atualizado em {formatDate(sysDetails.data_atualizacao?.split('T')[0] || formatDateLocalISO(new Date()))}
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
                          <div className="col-span-full text-center py-20 bg-slate-50 rounded-none md:rounded-[2.5rem] border-2 border-dashed border-slate-200">
                            <p className="text-slate-400 font-bold text-lg mb-2">Nenhum sistema cadastrado</p>
                            <button onClick={() => { setIsSettingsModalOpen(true); }} className="bg-slate-900 text-white px-6 py-3 rounded-lg md:rounded-xl font-bold uppercase tracking-widest text-xs hover:bg-slate-800 transition-all mt-4">
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
                      const ajustesPendentesCount = systemWorkItems.filter(w => !w.concluido).length;

                      const steps: SistemaStatus[] = ['ideia', 'prototipacao', 'desenvolvimento', 'testes', 'producao'];
                      const currentStepIndex = steps.indexOf(sysDetails.status);

                      return (
                        <div className="animate-in fade-in slide-in-from-bottom-8 duration-500">
                          {/* Navigation */}
                          <button
                            onClick={() => setSelectedSystemId(null)}
                            className="mb-8 px-6 md:px-0 flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold text-xs uppercase tracking-widest transition-colors"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
                            Voltar para Lista
                          </button>

                          <div className="bg-white border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden shadow-xl">
                            {/* Header Detalhado */}
                            <div className="hidden md:block bg-slate-900 p-8 md:p-12 text-white relative overflow-hidden">
                              <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/20 rounded-full -mr-20 -mt-20 blur-3xl"></div>
                              <div className="relative z-10 flex flex-col md:flex-row md:items-end justify-between gap-8">
                                <div className="space-y-4">
                                  <div className="inline-flex items-center gap-2 bg-white/10 px-3 py-1 rounded-lg backdrop-blur-sm border border-white/10">
                                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                                    <span className="text-[10px] font-black uppercase tracking-widest">
                                      {sysDetails.status === 'prototipacao' ? 'Prototipação' :
                                        sysDetails.status === 'producao' ? 'Produção' :
                                          sysDetails.status}
                                    </span>
                                  </div>
                                  <h2 className="text-4xl md:text-5xl font-black tracking-tight">{systemName}</h2>
                                </div>
                                <div className="text-right">
                                  <div className="text-3xl font-black text-violet-400">{ajustesPendentesCount}</div>
                                  <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Ajustes Pendentes</div>
                                </div>
                              </div>
                            </div>

                            {/* Status Stepper */}
                            <div className="bg-slate-50 border-b border-slate-100 p-6 md:p-10 flex flex-col items-center gap-8">
                              <div className="text-center">
                                <h2 className="text-2xl md:text-3xl font-black text-slate-900 tracking-tight uppercase">{systemName}</h2>
                                <div className="w-12 h-1.5 bg-violet-500 mx-auto mt-3 rounded-full"></div>
                              </div>

                              <div className="flex flex-wrap items-center justify-center bg-slate-200/50 p-1.5 rounded-none md:rounded-2xl gap-1 w-full md:w-auto">
                                {steps.map((step, idx) => {
                                  const isActive = sysDetails.status === step;
                                  const stepLabels: Record<string, string> = {
                                    ideia: 'Ideia',
                                    prototipacao: 'Protótipo',
                                    desenvolvimento: 'Dev',
                                    testes: 'Testes',
                                    producao: 'Produção'
                                  };
                                  return (
                                    <React.Fragment key={step}>
                                      <button
                                        onClick={() => handleUpdateSistema(unit.id, { status: step })}
                                        className={`flex-1 md:flex-none px-2 md:px-4 py-2 rounded-lg md:rounded-xl text-[8px] md:text-[9px] font-black uppercase tracking-widest transition-all ${isActive
                                          ? 'bg-violet-600 text-white shadow-lg'
                                          : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'
                                          }`}
                                      >
                                        {stepLabels[step]}
                                      </button>
                                      {idx < steps.length - 1 && (
                                        <div className="hidden md:flex items-center text-slate-300 px-1">
                                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                                        </div>
                                      )}
                                    </React.Fragment>
                                  );
                                })}
                              </div>
                            </div>

                            <div className="p-0 md:p-8 grid grid-cols-1 lg:grid-cols-3 gap-0 md:gap-12">
                              {/* Coluna 2: Links e Recursos (Agora embaixo no mobile) */}
                              <div className="lg:col-span-1 order-2 md:order-1 space-y-0 md:space-y-8">
                                <div className="p-6 md:p-0">
                                  <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
                                    <span className="w-1 h-4 bg-violet-500 rounded-full"></span>
                                    Recursos Principais
                                  </h4>
                                </div>

                                <div className="grid grid-cols-2 md:grid-cols-1 gap-0 md:gap-6">
                                  {/* Repositório */}
                                  <button
                                    onClick={() => setEditingResource({ field: 'repositorio_principal', label: 'Repositório', value: sysDetails.repositorio_principal || '' })}
                                    className="group bg-slate-900 p-6 rounded-none md:rounded-3xl border border-slate-800 hover:border-slate-600 hover:shadow-xl transition-all text-left flex flex-col justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden -ml-px -mt-px md:m-0"
                                  >
                                    <div className="absolute top-0 right-0 w-24 h-24 bg-violet-500/10 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                    {sysDetails.repositorio_principal && (
                                      <a
                                        href={sysDetails.repositorio_principal}
                                        target="_blank"
                                        rel="noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                        className="absolute top-4 right-4 z-20 p-2 bg-white/10 text-white rounded-lg hover:bg-violet-500 transition-all"
                                      >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                      </a>
                                    )}
                                    <div className="relative z-10 space-y-3">
                                      <div className="w-8 h-8 bg-white/10 text-white rounded-lg flex items-center justify-center">
                                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" /></svg>
                                      </div>
                                      <h5 className="text-[10px] md:text-xs font-black text-white uppercase tracking-widest">Repositório</h5>
                                    </div>
                                    <div className="relative z-10">
                                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{sysDetails.repositorio_principal ? 'Editar' : 'Configurar'}</span>
                                    </div>
                                  </button>

                                  {/* Documentação */}
                                  <button
                                    onClick={() => setEditingResource({ field: 'link_documentacao', label: 'Documentação', value: sysDetails.link_documentacao || '' })}
                                    className="group bg-white p-6 rounded-none md:rounded-3xl border border-slate-200 hover:border-violet-300 hover:shadow-xl transition-all text-left flex flex-col justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden -ml-px -mt-px md:m-0"
                                  >
                                    <div className="absolute top-0 right-0 w-24 h-24 bg-violet-500/5 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                    {sysDetails.link_documentacao && (
                                      <a
                                        href={sysDetails.link_documentacao}
                                        target="_blank"
                                        rel="noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                        className="absolute top-4 right-4 z-20 p-2 bg-violet-50 text-violet-600 rounded-lg hover:bg-violet-500 hover:text-white transition-all"
                                      >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                      </a>
                                    )}
                                    <div className="relative z-10 space-y-3">
                                      <div className="w-8 h-8 bg-violet-100 text-violet-600 rounded-lg flex items-center justify-center">
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                      </div>
                                      <h5 className="text-[10px] md:text-xs font-black text-slate-900 uppercase tracking-widest">Docs</h5>
                                    </div>
                                    <div className="relative z-10">
                                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{sysDetails.link_documentacao ? 'Editar' : 'Configurar'}</span>
                                    </div>
                                  </button>

                                  {/* AI Studio */}
                                  <button
                                    onClick={() => setEditingResource({ field: 'link_google_ai_studio', label: 'AI Studio', value: sysDetails.link_google_ai_studio || '' })}
                                    className="group bg-white p-6 rounded-none md:rounded-3xl border border-slate-200 hover:border-blue-300 hover:shadow-xl transition-all text-left flex flex-col justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden -ml-px -mt-px md:m-0"
                                  >
                                    <div className="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                    {sysDetails.link_google_ai_studio && (
                                      <a
                                        href={sysDetails.link_google_ai_studio}
                                        target="_blank"
                                        rel="noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                        className="absolute top-4 right-4 z-20 p-2 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-500 hover:text-white transition-all"
                                      >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                      </a>
                                    )}
                                    <div className="relative z-10 space-y-3">
                                      <div className="w-8 h-8 bg-blue-100 text-blue-600 rounded-lg flex items-center justify-center">
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                      </div>
                                      <h5 className="text-[10px] md:text-xs font-black text-slate-900 uppercase tracking-widest">AI Studio</h5>
                                    </div>
                                    <div className="relative z-10">
                                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{sysDetails.link_google_ai_studio ? 'Editar' : 'Configurar'}</span>
                                    </div>
                                  </button>

                                  {/* Link Hospedado */}
                                  <button
                                    onClick={() => setEditingResource({ field: 'link_hospedado', label: 'Hospedagem', value: sysDetails.link_hospedado || '' })}
                                    className="group bg-emerald-50 p-6 rounded-none md:rounded-3xl border border-emerald-100 hover:border-emerald-300 hover:shadow-xl transition-all text-left flex flex-col justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden -ml-px -mt-px md:m-0"
                                  >
                                    <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                    {sysDetails.link_hospedado && (
                                      <a
                                        href={sysDetails.link_hospedado}
                                        target="_blank"
                                        rel="noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                        className="absolute top-4 right-4 z-20 p-2 bg-emerald-200 text-emerald-700 rounded-lg hover:bg-emerald-500 hover:text-white transition-all"
                                      >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                      </a>
                                    )}
                                    <div className="relative z-10 space-y-3">
                                      <div className="w-8 h-8 bg-emerald-100 text-emerald-600 rounded-lg flex items-center justify-center">
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>
                                      </div>
                                      <h5 className="text-[10px] md:text-xs font-black text-emerald-900 uppercase tracking-widest">Produção</h5>
                                    </div>
                                    <div className="relative z-10">
                                      <span className="text-[10px] font-bold text-emerald-600/60 uppercase tracking-widest">{sysDetails.link_hospedado ? 'Editar' : 'Configurar'}</span>
                                    </div>
                                  </button>
                                </div>
                              </div>

                              {/* Coluna 1: Logs de Trabalho (Agora em cima no mobile) */}
                              <div className="lg:col-span-2 order-1 md:order-2 space-y-0 md:space-y-6">
                                <div className="bg-white border-0 md:border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden flex flex-col min-h-[400px] md:min-h-[600px] shadow-none md:shadow-sm">
                                  {/* Novo Log Input */}
                                  <div className="p-6 md:p-8 border-b border-slate-100 bg-slate-50">
                                    <div className="flex flex-col gap-6">
                                      <div className="flex items-center justify-between gap-4">
                                        <div className="flex items-center gap-3">
                                          <div className="p-2 bg-violet-600 text-white rounded-lg md:rounded-xl">
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                          </div>
                                          <h4 className="text-sm font-black text-slate-900 uppercase tracking-widest">Registro de Desenvolvimento</h4>
                                        </div>
                                        <button
                                          onClick={() => setIsLogsModalOpen(true)}
                                          className="flex items-center gap-2 px-4 py-2 bg-violet-50 text-violet-600 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-violet-100 transition-all border border-violet-100"
                                        >
                                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                          Logs Ativos
                                        </button>
                                      </div>

                                      <div className="flex flex-col gap-4">
                                        <div className="flex bg-white p-1 rounded-lg md:rounded-xl border border-slate-200 w-fit self-end">
                                          <button
                                            onClick={() => setNewLogTipo('desenvolvimento')}
                                            className={`px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${newLogTipo === 'desenvolvimento' ? 'bg-violet-600 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                                          >
                                            Desenvolvimento
                                          </button>
                                          <button
                                            onClick={() => setNewLogTipo('ajuste')}
                                            className={`px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${newLogTipo === 'ajuste' ? 'bg-amber-600 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                                          >
                                            Ajuste
                                          </button>
                                        </div>
                                        <textarea
                                          value={newLogText}
                                          onChange={(e) => setNewLogText(e.target.value)}
                                          placeholder="O que foi feito ou o que precisa ser ajustado?"
                                          rows={4}
                                          className="w-full bg-white border border-slate-200 rounded-none md:rounded-2xl px-6 py-4 text-sm font-medium text-slate-700 focus:ring-2 focus:ring-violet-500 outline-none transition-all resize-none shadow-sm"
                                        />
                                        <div className="flex flex-wrap gap-2">
                                          {newLogAttachments.map((at, i) => (
                                            <div key={i} className="relative group/at">
                                              <img src={at.valor} alt="preview" className="w-16 h-16 object-cover rounded-lg border border-slate-200" />
                                              <button
                                                onClick={() => setNewLogAttachments(prev => prev.filter((_, idx) => idx !== i))}
                                                className="absolute -top-1 -right-1 bg-rose-500 text-white rounded-full p-0.5 opacity-0 group-hover/at:opacity-100 transition-all z-10"
                                              >
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                              </button>
                                            </div>
                                          ))}
                                          <label className={`w-16 h-16 border-2 border-dashed border-slate-200 rounded-lg flex items-center justify-center cursor-pointer hover:border-violet-400 hover:bg-violet-50 transition-all ${isUploading ? 'animate-pulse pointer-events-none' : ''}`}>
                                            <input
                                              type="file"
                                              accept="image/*"
                                              className="hidden"
                                              onChange={async (e) => {
                                                const file = e.target.files?.[0];
                                                if (file) {
                                                  const item = await handleFileUploadToDrive(file);
                                                  if (item) setNewLogAttachments(prev => [...prev, item]);
                                                }
                                              }}
                                            />
                                            {isUploading ? (
                                              <div className="w-4 h-4 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                            ) : (
                                              <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                            )}
                                          </label>
                                        </div>
                                        <button
                                          onClick={() => {
                                            handleCreateWorkItem(unit.id, newLogTipo, newLogText, newLogAttachments);
                                            setNewLogText('');
                                            setNewLogAttachments([]);
                                          }}
                                          disabled={!newLogText.trim()}
                                          className="w-full bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 disabled:grayscale"
                                        >
                                          Registrar
                                        </button>
                                      </div>
                                    </div>
                                  </div>

                                  {/* Listagem de Logs (Desktop) - Hidden on Mobile if Modal is preferred, but user said "similar to action diary", so we show a button to open modal */}
                                  <div className="hidden md:block flex-1 overflow-y-auto p-8 bg-white space-y-8">
                                    {/* Ativos (Não concluídos) */}
                                    <div className="space-y-4">
                                      <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-violet-500 pl-3">Logs Ativos</h5>
                                      {systemWorkItems.filter(w => !w.concluido).sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime()).map(log => (
                                        <div key={log.id} className="group bg-slate-50 border border-slate-100 rounded-none md:rounded-3xl p-6 hover:border-violet-200 hover:bg-white transition-all">
                                          <div className="flex items-start justify-between gap-6">
                                            <div className="flex-1 space-y-2">
                                              <div className="flex items-center gap-3">
                                                <span className={`text-[8px] font-black px-2 py-0.5 rounded uppercase tracking-wider ${log.tipo === 'desenvolvimento' ? 'bg-violet-100 text-violet-700' : 'bg-amber-100 text-amber-700'}`}>
                                                  {log.tipo}
                                                </span>
                                                <span className="text-[8px] font-black text-slate-300 uppercase">{new Date(log.data_criacao).toLocaleDateString('pt-BR')}</span>
                                              </div>
                                              <p className="text-sm font-medium text-slate-700 leading-relaxed">{log.descricao}</p>
                                              {log.pool_dados && log.pool_dados.length > 0 && (
                                                <div className="flex flex-wrap gap-2 mt-3">
                                                  {log.pool_dados.map((at, i) => (
                                                    <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block">
                                                      <img src={at.valor} alt="preview" className="w-20 h-20 object-cover rounded-lg border border-slate-100 hover:scale-105 transition-transform shadow-sm" />
                                                    </a>
                                                  ))}
                                                </div>
                                              )}
                                            </div>
                                            <div className="flex gap-1 items-center opacity-0 group-hover:opacity-100 transition-opacity">
                                              <button
                                                onClick={() => {
                                                  setEditingWorkItem(log);
                                                  setEditingWorkItemText(log.descricao);
                                                  setEditingWorkItemAttachments(log.pool_dados || []);
                                                }}
                                                className="p-2 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-all"
                                                title="Editar"
                                              >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                              </button>
                                              <button
                                                onClick={() => {
                                                  if (window.confirm("Excluir este log permanentemente?")) {
                                                    handleDeleteWorkItem(log.id);
                                                  }
                                                }}
                                                className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-all"
                                                title="Excluir"
                                              >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                              </button>
                                              <button
                                                onClick={() => handleUpdateWorkItem(log.id, { concluido: true, data_conclusao: new Date().toISOString() })}
                                                className="w-10 h-10 rounded-full border-2 border-slate-200 flex items-center justify-center text-slate-300 hover:border-emerald-500 hover:text-emerald-500 hover:bg-emerald-50 transition-all group/check ml-2"
                                              >
                                                <svg className="w-5 h-5 opacity-0 group-hover/check:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                              </button>
                                            </div>
                                          </div>
                                        </div>
                                      ))}
                                      {systemWorkItems.filter(w => !w.concluido).length === 0 && (
                                        <div className="text-center py-12 bg-slate-50/50 rounded-none md:rounded-3xl border-2 border-dashed border-slate-100">
                                          <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhum log ativo</p>
                                        </div>
                                      )}
                                    </div>
                                    {/* Concluídos */}
                                    {systemWorkItems.filter(w => w.concluido).length > 0 && (
                                      <div className="space-y-4 pt-8">
                                        <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-emerald-500 pl-3">Concluídos</h5>
                                        <div className="space-y-3 opacity-60">
                                          {systemWorkItems.filter(w => w.concluido).sort((a, b) => new Date(b.data_conclusao!).getTime() - new Date(a.data_conclusao!).getTime()).map(log => (
                                            <div key={log.id} className="bg-white border border-slate-100 rounded-none md:rounded-2xl p-4 flex items-center justify-between gap-4">
                                              <div className="flex-1 flex items-center gap-4">
                                                <div className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
                                                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                </div>
                                                  <p className="text-xs font-medium text-slate-500 line-clamp-1">{log.descricao}</p>
                                                  {log.pool_dados && log.pool_dados.length > 0 && (
                                                    <div className="flex flex-wrap gap-1 mt-1">
                                                      {log.pool_dados.map((at, i) => (
                                                        <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block">
                                                          <img src={at.valor} alt="preview" className="w-8 h-8 object-cover rounded border border-slate-100 opacity-60 hover:opacity-100 transition-opacity" />
                                                        </a>
                                                      ))}
                                                    </div>
                                                  )}
                                                </div>
                                                <div className="flex gap-2 items-center">
                                                  <button
                                                    onClick={() => {
                                                      setEditingWorkItem(log);
                                                      setEditingWorkItemText(log.descricao);
                                                    }}
                                                    className="p-1.5 text-slate-300 hover:text-violet-600 rounded-lg transition-all"
                                                    title="Editar"
                                                  >
                                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                  </button>
                                                  <button
                                                    onClick={() => {
                                                      if (window.confirm("Excluir este log permanentemente?")) {
                                                        handleDeleteWorkItem(log.id);
                                                      }
                                                    }}
                                                    className="p-1.5 text-slate-300 hover:text-rose-600 rounded-lg transition-all"
                                                    title="Excluir"
                                                  >
                                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                  </button>
                                                  <button
                                                    onClick={() => handleUpdateWorkItem(log.id, { concluido: false })}
                                                    className="text-[9px] font-black text-slate-300 hover:text-violet-600 uppercase ml-2"
                                                  >
                                                    Reabrir
                                                  </button>
                                                </div>
                                              </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* Modal de Edição de Recurso (Link) */}
                            {editingResource && (
                              <div className="fixed inset-0 z-[400] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 md:p-8 animate-in zoom-in-95 duration-300">
                                <div className="bg-white w-full max-w-lg rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden">
                                  <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                                    <h3 className="text-xl font-black text-slate-900 tracking-tight">Editar {editingResource.label}</h3>
                                    <button onClick={() => setEditingResource(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                    </button>
                                  </div>
                                  <div className="p-8 space-y-6">
                                    <div className="space-y-2">
                                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">URL do Recurso</label>
                                      <input
                                        type="text"
                                        value={editingResource.value}
                                        onChange={(e) => setEditingResource({ ...editingResource, value: e.target.value })}
                                        placeholder="https://..."
                                        className="w-full bg-slate-50 border border-slate-200 rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-violet-500 transition-all"
                                      />
                                    </div>
                                    <div className="flex gap-4">
                                      <button
                                        onClick={() => setEditingResource(null)}
                                        className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all"
                                      >
                                        Cancelar
                                      </button>
                                      <button
                                        onClick={() => {
                                          handleUpdateSistema(unit.id, { [editingResource.field]: editingResource.value });
                                          setEditingResource(null);
                                        }}
                                        className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
                                      >
                                        Salvar Link
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Modal de Logs Full-screen */}
                            {isLogsModalOpen && (
                              <div className="fixed inset-0 z-[300] bg-white md:bg-black/60 md:backdrop-blur-sm flex items-center justify-center p-0 md:p-8 animate-in fade-in duration-300">
                                <div className="bg-white w-full h-full md:h-auto md:max-w-4xl md:rounded-[2.5rem] flex flex-col overflow-hidden shadow-2xl">
                                  <div className="p-6 md:p-10 border-b border-slate-100 flex items-center justify-between bg-white sticky top-0 z-10">
                                    <div className="flex items-center gap-4">
                                      <div className="p-3 bg-violet-100 text-violet-600 rounded-none md:rounded-2xl">
                                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                      </div>
                                      <div>
                                        <h3 className="text-2xl font-black text-slate-900 tracking-tight">Registro de Atividades</h3>
                                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">{systemName}</p>
                                      </div>
                                    </div>
                                    <button
                                      onClick={() => setIsLogsModalOpen(false)}
                                      className="p-3 bg-slate-100 text-slate-500 rounded-full hover:bg-slate-200 transition-all active:scale-95"
                                    >
                                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                    </button>
                                  </div>

                                  <div className="flex-1 overflow-y-auto p-6 md:p-12 space-y-12">
                                    <div className="space-y-6">
                                      <div className="flex items-center justify-between">
                                        <h5 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] border-l-4 border-violet-500 pl-4">Logs em Aberto</h5>
                                        <span className="bg-violet-100 text-violet-600 text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-widest">
                                          {systemWorkItems.filter(w => !w.concluido).length} Pendentes
                                        </span>
                                      </div>
                                      <div className="grid grid-cols-1 gap-4">
                                        {systemWorkItems.filter(w => !w.concluido).sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime()).map(log => (
                                          <div key={log.id} className="bg-slate-50 border border-slate-100 rounded-none md:rounded-[2rem] p-6 hover:shadow-md transition-all">
                                            <div className="flex items-start justify-between gap-6">
                                              <div className="flex-1 space-y-3">
                                                <div className="flex items-center gap-3">
                                                  <span className={`text-[8px] font-black px-2 py-1 rounded uppercase tracking-widest ${log.tipo === 'desenvolvimento' ? 'bg-violet-100 text-violet-700' : 'bg-amber-100 text-amber-700'}`}>
                                                    {log.tipo}
                                                  </span>
                                                  <span className="text-[8px] font-bold text-slate-300 uppercase tracking-widest">{new Date(log.data_criacao).toLocaleDateString('pt-BR')}</span>
                                                </div>
                                                <p className="text-sm md:text-base font-bold text-slate-700 leading-relaxed">{log.descricao}</p>
                                                {log.pool_dados && log.pool_dados.length > 0 && (
                                                  <div className="flex flex-wrap gap-2 mt-3">
                                                    {log.pool_dados.map((at, i) => (
                                                      <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block">
                                                        <img src={at.valor} alt="preview" className="w-20 h-20 object-cover rounded-lg border border-slate-100 hover:scale-105 transition-transform shadow-sm" />
                                                      </a>
                                                    ))}
                                                  </div>
                                                )}
                                              </div>
                                                <div className="flex gap-2 items-center">
                                                  <button
                                                    onClick={() => {
                                                      setEditingWorkItem(log);
                                                      setEditingWorkItemText(log.descricao);
                                                      setEditingWorkItemAttachments(log.pool_dados || []);
                                                    }}
                                                    className="p-3 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-xl transition-all"
                                                    title="Editar"
                                                  >
                                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                  </button>
                                                  <button
                                                    onClick={() => {
                                                      if (window.confirm("Excluir este log permanentemente?")) {
                                                        handleDeleteWorkItem(log.id);
                                                      }
                                                    }}
                                                    className="p-3 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all"
                                                    title="Excluir"
                                                  >
                                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                  </button>
                                                  <button
                                                    onClick={() => handleUpdateWorkItem(log.id, { concluido: true, data_conclusao: new Date().toISOString() })}
                                                    className="w-12 h-12 rounded-full border-2 border-slate-200 flex items-center justify-center text-slate-300 hover:border-emerald-500 hover:text-emerald-500 hover:bg-emerald-50 transition-all group/check shadow-sm ml-2"
                                                  >
                                                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                  </button>
                                                </div>
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    </div>

                                    {systemWorkItems.filter(w => w.concluido).length > 0 && (
                                      <div className="space-y-6">
                                        <h5 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] border-l-4 border-emerald-500 pl-4">Concluídos</h5>
                                        <div className="grid grid-cols-1 gap-4 opacity-70">
                                          {systemWorkItems.filter(w => w.concluido).sort((a, b) => new Date(b.data_conclusao!).getTime() - new Date(a.data_conclusao!).getTime()).map(log => (
                                            <div key={log.id} className="bg-white border border-slate-100 rounded-none md:rounded-2xl p-6 flex items-center justify-between gap-6">
                                              <div className="flex-1 space-y-2">
                                                <div className="flex items-center gap-3">
                                                  <span className="text-[8px] font-bold text-slate-300 uppercase tracking-widest">Concluído em {new Date(log.data_conclusao!).toLocaleDateString('pt-BR')}</span>
                                                </div>
                                                <p className="text-sm font-medium text-slate-500 leading-relaxed">{log.descricao}</p>
                                                {log.pool_dados && log.pool_dados.length > 0 && (
                                                  <div className="flex flex-wrap gap-1 mt-1">
                                                    {log.pool_dados.map((at, i) => (
                                                      <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block">
                                                        <img src={at.valor} alt="preview" className="w-10 h-10 object-cover rounded-lg border border-slate-100 opacity-60 hover:opacity-100 transition-opacity" />
                                                      </a>
                                                    ))}
                                                  </div>
                                                )}
                                              </div>
                                                <div className="flex gap-3 items-center">
                                                  <button
                                                    onClick={() => {
                                                      setEditingWorkItem(log);
                                                      setEditingWorkItemText(log.descricao);
                                                    }}
                                                    className="p-2 text-slate-400 hover:text-violet-600 rounded-lg transition-all"
                                                    title="Editar"
                                                  >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                  </button>
                                                  <button
                                                    onClick={() => {
                                                      if (window.confirm("Excluir este log permanentemente?")) {
                                                        handleDeleteWorkItem(log.id);
                                                      }
                                                    }}
                                                    className="p-2 text-slate-400 hover:text-rose-600 rounded-lg transition-all"
                                                    title="Excluir"
                                                  >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                  </button>
                                                  <button
                                                    onClick={() => handleUpdateWorkItem(log.id, { concluido: false })}
                                                    className="text-[10px] font-black text-violet-400 hover:text-violet-600 uppercase tracking-widest ml-2"
                                                  >
                                                    Reabrir
                                                  </button>
                                                </div>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )}
                            {/* Modal de Edição de Log */}
                            {editingWorkItem && (
                              <div className="fixed inset-0 z-[500] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 md:p-8 animate-in zoom-in-95 duration-300">
                                <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden">
                                  <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                                    <div className="flex items-center gap-4">
                                       <div className="p-3 bg-violet-100 text-violet-600 rounded-2xl">
                                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                       </div>
                                       <h3 className="text-xl font-black text-slate-900 tracking-tight">Editar Registro</h3>
                                    </div>
                                    <button onClick={() => setEditingWorkItem(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors text-slate-400">
                                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                    </button>
                                  </div>
                                  <div className="p-8 space-y-6">
                                    <div className="space-y-4">
                                      <div className="flex bg-slate-100 p-1 rounded-xl w-fit">
                                        <button
                                          onClick={() => setEditingWorkItem({ ...editingWorkItem, tipo: 'desenvolvimento' })}
                                          className={`px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${editingWorkItem.tipo === 'desenvolvimento' ? 'bg-violet-600 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                                        >
                                          Desenvolvimento
                                        </button>
                                        <button
                                          onClick={() => setEditingWorkItem({ ...editingWorkItem, tipo: 'ajuste' })}
                                          className={`px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${editingWorkItem.tipo === 'ajuste' ? 'bg-amber-600 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                                        >
                                          Ajuste
                                        </button>
                                      </div>
                                      
                                      <div className="space-y-2">
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Descrição</label>
                                        <textarea
                                          value={editingWorkItemText}
                                          onChange={(e) => setEditingWorkItemText(e.target.value)}
                                          rows={6}
                                          className="w-full bg-slate-50 border border-slate-200 rounded-none md:rounded-3xl px-8 py-6 text-base font-medium text-slate-700 outline-none focus:ring-2 focus:ring-violet-500 transition-all resize-none"
                                        />
                                      </div>

                                      <div className="space-y-2">
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Anexos (Drive)</label>
                                        <div className="flex flex-wrap gap-2">
                                          {editingWorkItemAttachments.map((at, i) => (
                                            <div key={i} className="relative group/at">
                                              <img src={at.valor} alt="preview" className="w-20 h-20 object-cover rounded-xl border border-slate-200" />
                                              <button
                                                onClick={() => setEditingWorkItemAttachments(prev => prev.filter((_, idx) => idx !== i))}
                                                className="absolute -top-2 -right-2 bg-rose-500 text-white rounded-full p-1 opacity-0 group-hover/at:opacity-100 transition-all z-10 shadow-lg"
                                              >
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                              </button>
                                            </div>
                                          ))}
                                          <label className={`w-20 h-20 border-2 border-dashed border-slate-200 rounded-xl flex items-center justify-center cursor-pointer hover:border-violet-400 hover:bg-violet-50 transition-all ${isUploading ? 'animate-pulse pointer-events-none' : ''}`}>
                                            <input
                                              type="file"
                                              accept="image/*"
                                              className="hidden"
                                              onChange={async (e) => {
                                                const file = e.target.files?.[0];
                                                if (file) {
                                                  const item = await handleFileUploadToDrive(file);
                                                  if (item) setEditingWorkItemAttachments(prev => [...prev, item]);
                                                }
                                              }}
                                            />
                                            {isUploading ? (
                                              <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                            ) : (
                                              <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                            )}
                                          </label>
                                        </div>
                                      </div>
                                    </div>
                                    
                                    <div className="flex gap-4 pt-4">
                                      <button
                                        onClick={() => setEditingWorkItem(null)}
                                        className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-[1.5rem] transition-all"
                                      >
                                        Cancelar
                                      </button>
                                      <button
                                        onClick={() => {
                                          handleUpdateWorkItem(editingWorkItem.id, { 
                                            descricao: editingWorkItemText,
                                            tipo: editingWorkItem.tipo,
                                            pool_dados: editingWorkItemAttachments
                                          });
                                          setEditingWorkItem(null);
                                          setEditingWorkItemAttachments([]);
                                        }}
                                        disabled={!editingWorkItemText.trim()}
                                        className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-[1.5rem] text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50"
                                      >
                                        Salvar Alterações
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })()
                  )}
                </div>



              ) : (
                <div className="space-y-10">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 bg-white p-8 rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl">
                    <div>
                      <h3 className="text-4xl font-black text-slate-900 tracking-tighter">Gestão PGC</h3>
                      <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">{new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}</p>
                    </div>
                    <div className="flex items-center gap-4">
                      {pgcSubView === 'plano' && (
                        <button
                          onClick={() => setIsImportPlanOpen(true)}
                          className="bg-slate-900 text-white px-6 py-3 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center gap-3"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                          Importar Planilha
                        </button>
                      )}

                      <select
                        value={currentMonth}
                        onChange={(e) => setCurrentMonth(Number(e.target.value))}
                        className="text-[10px] font-black uppercase bg-slate-100 px-4 py-2 rounded-lg md:rounded-xl border-none outline-none focus:ring-2 focus:ring-slate-900"
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
                      <div className="lg:col-span-3 bg-white rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl flex flex-col overflow-hidden h-full">
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

                      <div className="lg:col-span-9 bg-white rounded-none md:rounded-[2rem] border border-slate-200 overflow-hidden shadow-xl flex flex-col h-full">
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
                      <div className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl">
                        {/* Desktop Table */}
                        <table className="w-full text-left min-w-[800px] hidden md:table">
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
                          </tbody>
                        </table>

                        {/* Mobile Card View */}
                        <div className="md:hidden divide-y divide-slate-100">
                          {planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)?.itens.map((item, i) => (
                            <div key={i} className="p-6 space-y-4">
                              <div className="flex justify-between items-start gap-4">
                                <div className="flex-1">
                                  <div className="text-[8px] font-black text-slate-400 uppercase mb-1">{item.origem} • {item.unidade}</div>
                                  <div className="text-sm font-black text-slate-900 leading-tight">{item.entrega}</div>
                                </div>
                                <div className="bg-indigo-50 text-indigo-600 px-2 py-1 rounded text-[10px] font-black">{item.percentual}%</div>
                              </div>
                              <p className="text-xs text-slate-500 leading-relaxed">{item.descricao}</p>
                              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                                <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${item.percentual}%` }}></div>
                              </div>
                            </div>
                          ))}
                        </div>

                        {(!planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)) && (
                          <div className="px-8 py-20 text-center">
                            <p className="text-slate-300 font-black text-sm uppercase tracking-widest italic">Nenhum plano de trabalho configurado para este período.</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </main>
          </div>
        </>
      </div>

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
        selectedTask && (
          (taskModalMode === 'execute' || (taskModalMode === 'default' && selectedTask.categoria === 'CLC')) ? (
            <TaskExecutionView
              task={selectedTask}
              tarefas={tarefas}
              appSettings={appSettings}
              onSave={handleUpdateTarefa}
              onClose={() => setSelectedTask(null)}
              showToast={showToast}
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
            <div className="bg-[#0C0C0C] w-full max-w-2xl rounded-none md:rounded-[2rem] shadow-[0_0_100px_rgba(37,99,235,0.2)] border border-white/10 overflow-hidden flex flex-col h-[500px] animate-in zoom-in-95">
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
            onEmitNotification={emitNotification}
          />
        )
      }

      {
        isHabitsReminderOpen && (
          <DailyHabitsModal
            habits={healthDailyHabits.find(h => h.id === formatDateLocalISO(new Date())) || {
              id: formatDateLocalISO(new Date()),
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
            <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
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
                    <input type="number" id="import-year" defaultValue={currentYear} className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900" />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Mês</label>
                    <select id="import-month" defaultValue={currentMonth + 1} className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900">
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Dump JSON</label>
                  <textarea
                    id="import-json"
                    rows={10}
                    className="w-full bg-slate-900 text-blue-400 border-none rounded-none md:rounded-2xl px-6 py-4 text-[10px] font-mono focus:ring-2 focus:ring-blue-500 transition-all resize-none"
                    placeholder='[ { "entrega": "Exemplo", "percentual": 50 }, ... ]'
                  />
                </div>
              </div>

              <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4">
                <button
                  onClick={() => setIsImportPlanOpen(false)}
                  className="flex-1 px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all"
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
                  className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
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
          <div className="bg-white w-full max-w-md rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
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
                  className="w-full text-left p-4 rounded-none md:rounded-2xl border-2 border-slate-100 hover:border-violet-500 hover:bg-violet-50 transition-all flex items-center gap-3 group"
                >
                  <div className="w-10 h-10 bg-slate-100 group-hover:bg-violet-500 group-hover:text-white rounded-lg md:rounded-xl flex items-center justify-center transition-colors">
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

      {isQuickNoteModalOpen && (
        <QuickNoteModal
          isOpen={isQuickNoteModalOpen}
          onClose={() => setIsQuickNoteModalOpen(false)}
          onAddIdea={handleAddTextIdea}
        />
      )}
    </div>
  );
};

const container = document.getElementById('root');
if (container) {
  const root = createRoot(container);
  root.render(<App />);
}