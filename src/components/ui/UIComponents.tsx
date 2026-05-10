import React, { useState, useEffect, useRef } from 'react';
import {
  Tarefa, HermesNotification, WysiwygEditorProps, PlanoTrabalhoItem,
  EntregaInstitucional, AtividadeRealizada, Toast
} from '@/types';
import { formatDate } from '@/types';
import { STATUS_COLORS, PROJECT_COLORS } from '@/constants';
import { normalizeStatus } from '../../utils/helpers';

export const ToastContainer = ({ toasts, removeToast }: { toasts: Toast[], removeToast: (id: string) => void }) => {
  return (
    <div className="fixed bottom-4 sm:top-8 right-4 sm:right-8 left-4 sm:left-auto z-[9999] flex flex-col gap-3 pointer-events-none">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`pointer-events-auto px-6 py-4 rounded-none shadow-soft-touch backdrop-blur-md flex items-center gap-4 animate-in slide-in-from-bottom-12 sm:slide-in-from-right-12 fade-in duration-500 min-w-[320px] border border-border-grid ${toast.type === 'success' ? 'bg-emerald-600/95 text-white' :
            toast.type === 'error' ? 'bg-rose-600/95 text-white' :
              toast.type === 'warning' ? 'bg-amber-500/95 text-white' :
                'bg-slate-900/95 text-white'
            }`}
        >
          <div className="flex-shrink-0">
            {toast.type === 'success' && <div className="w-8 h-8 rounded-none bg-white/20 flex items-center justify-center"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg></div>}
            {toast.type === 'error' && <div className="w-8 h-8 rounded-none bg-white/20 flex items-center justify-center"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg></div>}
            {toast.type === 'info' && <div className="w-8 h-8 rounded-none bg-white/20 flex items-center justify-center"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg></div>}
            {toast.type === 'warning' && <div className="w-8 h-8 rounded-none bg-white/20 flex items-center justify-center"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg></div>}
          </div>
          <div className="flex-1">
            <span className="text-[10px] font-black uppercase tracking-[0.2em] leading-none opacity-60 block mb-0.5 font-mono">{toast.type}</span>
            <span className="text-sm font-bold tracking-tight">{toast.message}</span>
          </div>
          <button onClick={() => removeToast(toast.id)} className="p-2 hover:bg-white/20 rounded-none transition-colors opacity-40 hover:opacity-100">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      ))}
    </div>
  );
};

export const FilterChip = React.memo(({ label, isActive, onClick, colorClass }: { label: string, isActive: boolean, onClick: () => void, colorClass?: string }) => (
  <button
    onClick={onClick}
    className={`px-4 py-1.5 rounded-none text-[10px] font-black uppercase tracking-widest border transition-all duration-200 active:scale-95 font-mono ${isActive
      ? (colorClass || 'bg-slate-900 text-white border-slate-900 shadow-soft-touch')
      : 'bg-white text-slate-400 border-border-grid hover:border-slate-400 hover:text-slate-600'
      }`}
  >
    {label}
  </button>
));

export const PgcMiniTaskCard = React.memo(({ task, onClick }: { task: Tarefa, onClick?: () => void }) => {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('tarefaId', task.id);
        e.dataTransfer.effectAllowed = 'copy';
      }}
      onClick={onClick}
      className={`bg-white border border-border-grid p-3 rounded-none shadow-soft-touch hover:border-primary-tactile transition-all ${onClick ? 'cursor-pointer' : 'cursor-grab'} active:cursor-grabbing w-full md:w-[280px] group`}
    >
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        {task.area_tematica && (
            <span className={`text-[8px] font-black px-1.5 py-0.5 rounded-none border border-current uppercase font-mono ${PROJECT_COLORS[task.area_tematica] || 'bg-slate-100 text-slate-600'}`}>
                {task.area_tematica.replace('SISTEMA:', '').trim()}
            </span>
        )}
        <span className="text-[8px] font-black text-slate-400 uppercase font-mono">{formatDate(task.data_limite)}</span>
      </div>
      <h5 className="text-[11px] font-bold text-text-main leading-tight group-hover:text-primary-tactile line-clamp-2">{task.titulo}</h5>
    </div>
  );
});

export const PgcAuditRow = ({
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
      className="group border-b border-border-grid hover:bg-slate-50 transition-all p-4 md:p-8 flex flex-col gap-3 md:gap-4"
    >
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-[10px] font-black text-primary-tactile uppercase tracking-widest font-mono">{item.unidade}</span>
          {entregaEntity?.processo_sei && (
            <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest font-mono border border-border-grid px-1.5 rounded-none">
              SEI: {entregaEntity.processo_sei}
            </span>
          )}
        </div>
        <h4 className="text-xl font-black text-slate-900 tracking-tight leading-snug font-serif">
          {item.entrega}
        </h4>
        <p className="text-xs font-medium text-slate-500 leading-relaxed mt-1">
          {item.descricao}
        </p>
      </div>

      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-[10px] font-black text-slate-400 uppercase font-mono">
            <div className="w-1.5 h-1.5 bg-primary-tactile rounded-none"></div>
            {atividadesRelacionadas.length + tarefasRelacionadas.length} Ações vinculadas
          </div>
        </div>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="px-6 py-2 bg-white border border-border-grid text-slate-600 rounded-none text-[9px] font-black uppercase tracking-wider hover:bg-slate-50 transition-all flex items-center gap-2 shadow-soft-touch font-mono"
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
            <div key={at.id} className="p-4 rounded-none bg-white border border-border-grid shadow-soft-touch hover:border-slate-300 transition-all">
              <p className="text-[8px] font-black text-slate-400 uppercase mb-1 font-mono">{formatDate(at.data_inicio)}</p>
              <p className="text-[11px] font-bold text-slate-700 leading-tight">{at.descricao_atividade}</p>
              <div className="mt-2 text-[8px] font-black text-accent-tactile uppercase tracking-widest font-mono">Atividade PGD</div>
            </div>
          ))}
          {tarefasRelacionadas.map(t => (
            <div
              key={t.id}
              onClick={() => onSelectTask(t)}
              className="p-4 rounded-none bg-surface-container-low border border-border-grid shadow-soft-touch hover:border-primary-tactile transition-all cursor-pointer group/task relative pr-10"
            >
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (entregaId) onUnlinkTarefa(t.id, entregaId);
                }}
                className="absolute top-3 right-3 p-1.5 text-slate-300 hover:text-rose-500 hover:bg-white rounded-none opacity-0 group-hover/task:opacity-100 transition-all"
                title="Desvincular"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[8px] font-black text-primary-tactile uppercase tracking-widest font-mono">Tarefa Geral</p>
                <p className="text-[8px] font-black text-slate-400 uppercase tracking-widest font-mono">{formatDate(t.data_limite)}</p>
              </div>
              <p className="text-xs font-bold text-slate-800 leading-snug group-hover/task:text-primary-tactile transition-colors">{t.titulo}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export const RowCard = React.memo(({ task, isDark = false, onClick, onToggle, onDelete, onEdit, onUpdateToToday, onUpdateTask, highlighted }: {
  task: Tarefa,
  isDark?: boolean,
  onClick?: () => void,
  onToggle: (id: string, currentStatus: string) => void,
  onDelete: (id: string) => void,
  onEdit: (t: Tarefa) => void,
  onUpdateToToday?: (t: Tarefa) => void,
  onUpdateTask?: (id: string, updates: Partial<Tarefa>) => void,
  highlighted?: boolean
}) => {
  const statusValue = normalizeStatus(task.status);
  const isCompleted = statusValue === 'concluido';
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isEditingDateTime, setIsEditingDateTime] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsEditingDateTime(false);
      }
    };
    if (isEditingDateTime) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isEditingDateTime]);

  const formatDateShort = (dateStr: string) => {
    if (!dateStr || dateStr === '-' || dateStr === 'Sem Data') return '-';
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
      if (n === 'SAÚDE' || n === 'SAUDE') return 'bg-rose-50 text-rose-600 border-rose-100';
      if (n === 'FINANCEIRO' || n === 'FINANCEIRA') return 'bg-emerald-50 text-emerald-600 border-emerald-100';
      if (n === 'ASSISTÊNCIA' || n.includes('ESTUDANTIL')) return 'bg-purple-50 text-purple-600 border-purple-100';
    }
    return 'bg-slate-50 text-slate-500 border-slate-100';
  };

  const dateDisplay = formatDateShort(task.data_limite);

  const handleQuickDate = (type: 'today' | 'tomorrow') => {
    const d = new Date();
    if (type === 'tomorrow') d.setDate(d.getDate() + 1);
    const dStr = d.toISOString().split('T')[0];
    onUpdateTask?.(task.id, { data_limite: dStr, data_inicio: dStr });
    setIsEditingDateTime(false);
  };

  return (
    <div
      onClick={onClick}
      onMouseLeave={() => setIsConfirmingDelete(false)}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('task-id', task.id);
        e.dataTransfer.effectAllowed = 'move';
      }}
      className={`group w-full px-4 md:px-6 py-5 md:py-4 border-b transition-all flex flex-col sm:flex-row sm:items-start gap-4 md:gap-6 animate-in cursor-pointer relative ${isEditingDateTime ? 'z-[100]' : 'z-auto'} ${isDark ? 'border-white/10 hover:bg-white/[0.03]' : 'border-border-grid hover:bg-slate-50/70'} ${isCompleted ? 'opacity-60 grayscale-[0.35]' : ''} ${highlighted ? (isDark ? 'bg-white/10 border-l-2 border-l-accent-tactile' : 'bg-surface-container border-l-2 border-l-primary-tactile') : 'bg-transparent'}`}
    >
      <div className="flex items-center gap-2 md:gap-3 flex-1 min-w-0">
        <div className="flex flex-col gap-0.5 text-slate-300 group-hover:text-slate-400 cursor-grab active:cursor-grabbing transition-colors shrink-0">
          <div className="flex gap-0.5">
            <div className="w-0.5 h-0.5 bg-current rounded-full"></div>
            <div className="w-0.5 h-0.5 bg-current rounded-full"></div>
          </div>
          <div className="flex gap-0.5">
            <div className="w-0.5 h-0.5 bg-current rounded-full"></div>
            <div className="w-0.5 h-0.5 bg-current rounded-full"></div>
          </div>
          <div className="flex gap-0.5">
            <div className="w-0.5 h-0.5 bg-current rounded-full"></div>
            <div className="w-0.5 h-0.5 bg-current rounded-full"></div>
          </div>
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle(task.id, task.status);
          }}
          className={`w-5 h-5 rounded-none border flex items-center justify-center transition-all flex-shrink-0 ${isCompleted ? 'bg-emerald-500 border-emerald-500 text-white shadow-soft-touch' : 'border-border-grid hover:border-primary-tactile'} text-transparent`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M5 13l4 4L19 7" /></svg>
        </button>

        <div className="flex flex-col gap-1 flex-1 min-w-0">
          {highlighted && !isCompleted && (
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-none bg-primary-tactile"></span>
              <span className={`text-[9px] font-black uppercase tracking-widest font-mono ${isDark ? 'text-accent-tactile' : 'text-primary-tactile'}`}>Próxima Ação</span>
            </div>
          )}
          <div className={`${highlighted ? `text-[15px] md:text-lg font-black` : `text-[13px] md:text-[15px] font-medium`} leading-snug transition-colors whitespace-normal break-words font-mono ${isCompleted ? 'line-through text-slate-400' : ''}`}>
            {task.titulo}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 flex-wrap">
          {task.area_tematica && task.area_tematica !== 'NÃO CLASSIFICADA' && (
            <span className={`text-[8px] md:text-[9px] font-black px-2 py-0.5 rounded-none border font-mono uppercase ${isDark ? 'bg-white/10 text-white' : getTagStyle(task.area_tematica, 'category')}`}>
              {task.area_tematica.replace('SISTEMA:', '').trim()}
            </span>
          )}
        </div>

        <div className="relative" ref={menuRef}>
          <button 
            onClick={(e) => {
              e.stopPropagation();
              setIsEditingDateTime(!isEditingDateTime);
            }}
            className={`flex items-center gap-1.5 font-black uppercase text-[9px] md:text-[10px] tracking-widest min-w-[65px] font-mono transition-all px-2 py-1 -mx-2 -my-1 border border-transparent hover:border-primary-tactile/30 hover:bg-primary-tactile/5 hover:text-primary-tactile ${isDark ? 'text-slate-400' : 'text-slate-500'}`}
          >
            <svg className="w-3 h-3 md:w-3.5 md:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
            <span>{dateDisplay} {task.horario_inicio ? `• ${task.horario_inicio}` : ''}</span>
          </button>

          {isEditingDateTime && (
            <div className="absolute top-full right-0 mt-2 p-4 bg-white border border-border-grid shadow-xl z-50 flex flex-col gap-3 min-w-[200px] animate-in fade-in zoom-in-95 duration-200">
              <div className="space-y-1">
                <p className="text-[8px] font-black text-slate-400 uppercase tracking-widest font-mono">Reagendar Prazo</p>
                <input 
                  type="date"
                  value={task.data_limite || ''}
                  onChange={(e) => {
                    onUpdateTask?.(task.id, { data_limite: e.target.value, data_inicio: e.target.value });
                  }}
                  className="w-full bg-slate-50 border border-border-grid px-2 py-1.5 text-[10px] font-black font-mono focus:ring-1 focus:ring-primary-tactile outline-none"
                />
              </div>
              <div className="space-y-1">
                <p className="text-[8px] font-black text-slate-400 uppercase tracking-widest font-mono">Horário</p>
                <input 
                  type="time"
                  value={task.horario_inicio || ''}
                  onChange={(e) => {
                    onUpdateTask?.(task.id, { horario_inicio: e.target.value });
                  }}
                  className="w-full bg-slate-50 border border-border-grid px-2 py-1.5 text-[10px] font-black font-mono focus:ring-1 focus:ring-primary-tactile outline-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-2 pt-1">
                <button 
                  onClick={(e) => { e.stopPropagation(); handleQuickDate('today'); }}
                  className="py-2 bg-slate-100 hover:bg-slate-200 text-[8px] font-black uppercase tracking-widest font-mono transition-colors"
                >
                  Hoje
                </button>
                <button 
                  onClick={(e) => { e.stopPropagation(); handleQuickDate('tomorrow'); }}
                  className="py-2 bg-slate-100 hover:bg-slate-200 text-[8px] font-black uppercase tracking-widest font-mono transition-colors"
                >
                  Amanhã
                </button>
              </div>
              <button 
                onClick={(e) => { e.stopPropagation(); setIsEditingDateTime(false); }}
                className="w-full bg-slate-900 text-white py-2 text-[8px] font-black uppercase tracking-widest font-mono hover:bg-slate-800 transition-colors"
              >
                Concluir
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

export const AutoExpandingTextarea = (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [props.value]);

  return (
    <textarea
      {...props}
      ref={textareaRef}
      className={`${props.className} resize-none overflow-hidden block border-none focus:ring-0`}
    />
  );
};

export const NotificationCenter = ({
  notifications,
  onMarkAsRead,
  onDismiss,
  isOpen,
  onClose,
  onUpdateOverdue,
  onNavigate,
  direction = 'down'
}: {
  notifications: HermesNotification[],
  onMarkAsRead: (id: string) => void,
  onDismiss: (id: string) => void,
  isOpen: boolean,
  onClose: () => void,
  onUpdateOverdue?: (id?: string) => void,
  onNavigate?: (link: string) => void,
  direction?: 'up' | 'down'
}) => {
  const dropdownRef = useRef<HTMLDivElement>(null);
  if (!isOpen) return null;

  return (
    <div
      ref={dropdownRef}
      className={`fixed sm:absolute ${direction === 'up' ? 'bottom-full mb-6' : 'top-full mt-2'} right-0 w-full sm:w-96 bg-white rounded-none shadow-soft-touch border border-border-grid overflow-hidden z-[100] animate-in fade-in duration-300 font-mono`}
    >
      <div className="p-6 border-b border-border-grid bg-surface-container-low flex items-center justify-between">
        <div>
          <h3 className="text-[10px] font-black text-on-surface uppercase tracking-widest font-mono">Notificações</h3>
          <p className="text-[8px] text-slate-400 font-black uppercase mt-1 font-mono">Hermes Sys-Core</p>
        </div>
        <span className="bg-primary-tactile text-white text-[10px] font-black px-2.5 py-1 rounded-none shadow-soft-touch font-mono">
          {notifications.filter(n => !n.isRead).length}
        </span>
      </div>
      <div className="max-h-[400px] overflow-y-auto custom-scrollbar">
        {notifications.length > 0 ? (
          notifications.map(n => (
            <div
              key={n.id}
              className={`p-5 border-b border-border-grid hover:bg-slate-50 transition-all cursor-pointer relative group ${!n.isRead ? 'bg-surface-container-low' : ''}`}
              onClick={() => {
                onMarkAsRead(n.id);
                if (n.link && onNavigate) { onNavigate(n.link); onClose(); }
              }}
            >
              <div className="flex gap-4">
                <div className={`w-1.5 h-6 rounded-none shrink-0 ${n.type === 'success' ? 'bg-emerald-500' :
                  n.type === 'warning' ? 'bg-operational-orange' :
                    n.type === 'error' ? 'bg-rose-500' : 'bg-accent-tactile'
                  }`} />
                <div className="flex-1">
                  <h4 className={`text-xs font-bold leading-tight mb-1 ${!n.isRead ? 'text-slate-900' : 'text-slate-500'}`}>{n.title}</h4>
                  <p className="text-[10px] text-slate-500 leading-relaxed">{n.message}</p>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="p-12 text-center opacity-40">
            <p className="text-slate-400 font-black text-[10px] uppercase tracking-widest font-mono italic">Sem pendências</p>
          </div>
        )}
      </div>
    </div>
  );
};

export const WysiwygEditor = ({ value, onChange, onKeyDown, placeholder, className, id, onPaste }: WysiwygEditorProps) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [value]);

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
  };

  const renderFormattedText = (text: string) => {
    if (!text) return <span className="text-slate-400/50 font-mono">{placeholder}</span>;
    const lines = text.split('\n');
    const processedLines: React.JSX.Element[] = [];
    
    lines.forEach((line, index) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('>')) {
        processedLines.push(
          <blockquote key={index} className="border-l-4 border-primary-tactile pl-4 py-1 my-1 italic text-slate-500 bg-surface-container-low rounded-none leading-relaxed">
            {line.substring(line.indexOf('>') + 1).trim()}
          </blockquote>
        );
      } else if (line === '') {
        processedLines.push(<div key={index} className="h-[1.625em]"></div>);
      } else {
        processedLines.push(<div key={index} className="min-h-[1.625em] leading-relaxed">{line}</div>);
      }
    });

    return <div className="whitespace-pre-wrap break-words">{processedLines}</div>;
  };

  return (
    <div className={`relative min-h-[56px] group ${className}`}>
      <div className="absolute inset-0 border border-border-grid rounded-none pointer-events-none group-focus-within:border-primary-tactile transition-all"></div>
      <div
        className="absolute inset-0 p-4 pointer-events-none overflow-hidden text-sm font-medium leading-relaxed"
        style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'inherit' }}
      >
        {renderFormattedText(value)}
      </div>
      <textarea
        ref={textareaRef}
        id={id}
        value={value}
        onChange={handleInput}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
        placeholder={placeholder}
        className="w-full bg-transparent border-none px-4 py-4 text-sm font-medium leading-relaxed text-transparent caret-primary-tactile outline-none transition-all resize-none overflow-hidden block relative z-10"
        style={{
          minHeight: 'inherit',
          WebkitTextFillColor: 'transparent',
          appearance: 'none',
          WebkitAppearance: 'none'
        }}
        spellCheck={false}
      />
    </div>
  );
};

export const CollapsibleContainer = ({ children, maxLines = 5, className = "" }: { children: React.ReactNode, maxLines?: number, className?: string }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isTruncated, setIsTruncated] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const checkTruncation = () => {
      if (containerRef.current && !isExpanded) {
        const { scrollHeight, clientHeight } = containerRef.current;
        if (scrollHeight > clientHeight) setIsTruncated(true);
      }
    };
    setTimeout(checkTruncation, 100);
  }, [children, isExpanded]);

  return (
    <div className={`relative ${className}`}>
      <div
        ref={containerRef}
        className={`transition-all duration-300 ${!isExpanded ? 'overflow-hidden' : ''}`}
        style={!isExpanded ? {
          display: '-webkit-box',
          WebkitLineClamp: maxLines,
          WebkitBoxOrient: 'vertical',
        } : {}}
      >
        {children}
      </div>
      {(isTruncated || isExpanded) && (
        <button
          onClick={(e) => { e.stopPropagation(); setIsExpanded(!isExpanded); }}
          className="text-[10px] font-black uppercase tracking-widest text-accent-tactile hover:text-primary-tactile mt-2 flex items-center gap-1 transition-all group/expand font-mono"
        >
          {isExpanded ? 'Ocultar' : 'Ver mais'}
          <svg className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
        </button>
      )}
    </div>
  );
};
