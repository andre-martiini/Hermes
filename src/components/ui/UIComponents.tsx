import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
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
        <h4 className="text-xl font-mono font-bold text-slate-900 tracking-tight leading-snug">
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

const isBlankTaskDescription = (value?: string | null) => !value || /^[\s\-_–—]*$/.test(value);

const hasDescriptionSynthesisContext = (task: Tarefa) => {
  const hasDiary = (task.acompanhamento || []).some(entry => String(entry?.nota || '').trim().length > 0);
  const hasPlan = (task.plano_acao || []).some(item => String(item?.text || '').trim().length > 0);
  return hasDiary || hasPlan;
};

export const RowCard = React.memo(({ task, isDark = false, onClick, onToggle, onDelete, onEdit, onUpdateToToday, onUpdateTask, onSynthesizeDescription, isSynthesizingDescription, highlighted }: {
  task: Tarefa,
  isDark?: boolean,
  onClick?: () => void,
  onToggle: (id: string, currentStatus: string) => void,
  onDelete: (id: string) => void,
  onEdit: (t: Tarefa) => void,
  onUpdateToToday?: (t: Tarefa) => void,
  onUpdateTask?: (id: string, updates: Partial<Tarefa>) => void,
  onSynthesizeDescription?: (t: Tarefa) => void | Promise<void>,
  isSynthesizingDescription?: boolean,
  highlighted?: boolean
}) => {
  const statusValue = normalizeStatus(task.status);
  const isCompleted = statusValue === 'concluido';
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isEditingDateTime, setIsEditingDateTime] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [localDate, setLocalDate] = useState(task.data_limite || '');
  const [localTime, setLocalTime] = useState(task.horario_inicio || '');
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLocalDate(task.data_limite || '');
    setLocalTime(task.horario_inicio || '');
  }, [task.data_limite, task.horario_inicio, isEditingDateTime]);

  // handleClickOutside removido pois agora utilizamos um modal centralizado com backdrop

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

  const getHighlightClass = (name?: string) => {
    if (isDark || !name || name === 'NÃO CLASSIFICADA') return '';
    const n = name.toUpperCase();
    if (n.includes('CLC')) return 'bg-blue-100/70 px-1 -mx-1 rounded-sm decoration-clone';
    if (n.includes('SAÚDE') || n.includes('SAUDE')) return 'bg-rose-100/70 px-1 -mx-1 rounded-sm decoration-clone';
    if (n.includes('FINANCEIRO') || n.includes('FINANCEIRA')) return 'bg-emerald-100/70 px-1 -mx-1 rounded-sm decoration-clone';
    if (n.includes('ASSISTÊNCIA') || n.includes('ESTUDANTIL')) return 'bg-purple-100/70 px-1 -mx-1 rounded-sm decoration-clone';
    return '';
  };

  const getTagStyle = (name: string) => {
    const n = name.toUpperCase();
    if (n.includes('CLC')) return 'bg-blue-50 text-blue-600 border-blue-100';
    if (n.includes('SAÚDE') || n.includes('SAUDE')) return 'bg-rose-50 text-rose-600 border-rose-100';
    if (n.includes('FINANCEIRO') || n.includes('FINANCEIRA')) return 'bg-emerald-50 text-emerald-600 border-emerald-100';
    if (n.includes('ASSISTÊNCIA') || n.includes('ESTUDANTIL')) return 'bg-purple-50 text-purple-600 border-purple-100';
    return 'bg-slate-50 text-slate-500 border-slate-100';
  };

  const highlightClass = getHighlightClass(task.area_tematica);

  const dateDisplay = formatDateShort(task.data_limite);
  const canSynthesizeDescription = isBlankTaskDescription(task.descricao) && hasDescriptionSynthesisContext(task);

  const handleQuickDate = (type: 'today' | 'tomorrow') => {
    const d = new Date();
    if (type === 'tomorrow') d.setDate(d.getDate() + 1);
    const dStr = d.toISOString().split('T')[0];
    setLocalDate(dStr);
    onUpdateTask?.(task.id, { data_limite: dStr, data_inicio: dStr, horario_inicio: localTime });
    setIsEditingDateTime(false);
  };

  const getTodayIso = () => {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const handleConfirmReschedule = () => {
    let finalDate = localDate;
    const today = getTodayIso();
    if (finalDate && finalDate < today) {
      finalDate = today;
      setLocalDate(finalDate);
    }
    if (finalDate !== task.data_limite || localTime !== (task.horario_inicio || '')) {
      onUpdateTask?.(task.id, { 
        data_limite: finalDate || task.data_limite, 
        data_inicio: finalDate || task.data_limite,
        horario_inicio: localTime 
      });
    }
    setIsEditingDateTime(false);
  };

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('task-id', task.id);
        e.dataTransfer.effectAllowed = 'move';
      }}
      className={`group w-full border-b transition-all flex flex-col animate-in relative ${isEditingDateTime ? 'z-[1000]' : 'z-auto'} ${isDark ? 'border-white/10' : 'border-border-grid'} ${isCompleted ? 'opacity-60 grayscale-[0.35]' : ''} ${highlighted ? (isDark ? 'bg-white/10 border-l-2 border-l-accent-tactile' : 'bg-surface-container border-l-2 border-l-primary-tactile') : 'bg-transparent'}`}
    >
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        onMouseLeave={() => setIsConfirmingDelete(false)}
        className={`w-full pl-4 pr-16 md:pl-6 md:pr-20 py-5 md:py-4 transition-all flex flex-col sm:flex-row sm:items-start gap-4 md:gap-6 cursor-pointer relative ${isDark ? 'hover:bg-white/[0.03]' : 'hover:bg-slate-50/70'}`}
      >
        <div className={`absolute top-3 right-3 z-10 flex items-center gap-1 ${isConfirmingDelete ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity duration-200`}>

          <button
            onClick={(e) => {
              e.stopPropagation();
              if (isConfirmingDelete) {
                onDelete(task.id);
              } else {
                setIsConfirmingDelete(true);
              }
            }}
            className={`p-1.5 transition-all flex items-center gap-1.5 rounded-none font-mono text-[9px] font-black uppercase ${
              isConfirmingDelete
                ? 'bg-rose-600 text-white px-2.5 shadow-soft-touch opacity-100'
                : `${isDark ? 'text-slate-500 hover:text-rose-400 hover:bg-white/5' : 'text-slate-400 hover:text-rose-600 hover:bg-slate-100'}`
            }`}
            title={isConfirmingDelete ? "Confirmar exclusão" : "Excluir ação"}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            {isConfirmingDelete && <span>Excluir?</span>}
          </button>
        </div>

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
          <div
            onClick={(e) => {
              e.stopPropagation();
              onClick?.();
            }}
            className={`cursor-pointer hover:underline decoration-1 ${highlighted ? `text-[15px] md:text-lg font-black` : `text-[13px] md:text-[15px] font-medium`} leading-snug transition-colors whitespace-normal break-words font-mono ${isCompleted ? 'line-through text-slate-400' : ''}`}
          >
            {highlightClass ? (
              <span className={highlightClass}>
                {task.titulo}
              </span>
            ) : task.titulo}
          </div>
        </div>
      </div>


      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 flex-wrap">
          {task.area_tematica && task.area_tematica !== 'NÃO CLASSIFICADA' && (
            <span className={`text-[8px] md:text-[9px] font-black px-2 py-0.5 rounded-none border font-mono uppercase ${isDark ? 'bg-white/10 text-white' : getTagStyle(task.area_tematica)}`}>
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
            {task.auto_data_atualizada && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" title="Data atualizada automaticamente" />
            )}
          </button>

          {isEditingDateTime && createPortal(
            <div 
              className="fixed inset-0 z-[99999] bg-black/70 backdrop-blur-md flex items-center justify-center p-4 animate-in fade-in duration-300 font-mono"
              onClick={(e) => { e.stopPropagation(); setIsEditingDateTime(false); }}
            >
              <div 
                className={`relative w-full max-w-md p-6 md:p-8 border shadow-2xl flex flex-col gap-6 animate-in zoom-in-95 duration-300 ${isDark ? 'bg-slate-900 border-slate-800 text-white shadow-black/80' : 'bg-white border-border-grid text-slate-900'}`}
                onClick={(e) => e.stopPropagation()}
              >
                {/* Header & Close Button */}
                <div className="flex items-center justify-between border-b pb-4 border-current/10">
                  <div className="min-w-0 pr-4">
                    <h3 className="text-base md:text-lg font-black uppercase tracking-widest">Alterar Cronograma</h3>
                    <p className="text-[10px] opacity-60 mt-1 font-mono truncate">{task.titulo}</p>
                  </div>
                  <button 
                    onClick={(e) => { e.stopPropagation(); setIsEditingDateTime(false); }}
                    className={`p-2 transition-transform hover:rotate-90 duration-200 shrink-0 ${isDark ? 'text-slate-400 hover:text-white' : 'text-slate-500 hover:text-black'}`}
                    title="Fechar"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>

                {/* Inputs Section */}
                <div className="flex flex-col gap-4 py-2">
                  <div className="space-y-1.5">
                    <label className={`text-xs font-black uppercase tracking-widest font-mono block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Reagendar Prazo (Data Limite)</label>
                    <input 
                      type="date"
                      min={getTodayIso()}
                      value={localDate}
                      onChange={(e) => setLocalDate(e.target.value)}
                      style={{ colorScheme: isDark ? 'dark' : 'light' }}
                      className={`w-full border px-3 py-2.5 text-xs font-black font-mono focus:ring-1 focus:ring-primary-tactile outline-none transition-colors ${isDark ? 'bg-slate-800 border-slate-700 text-slate-200' : 'bg-slate-50 border-border-grid text-slate-900'}`}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className={`text-xs font-black uppercase tracking-widest font-mono block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Horário Previsto</label>
                    <input 
                      type="time"
                      value={localTime}
                      onChange={(e) => setLocalTime(e.target.value)}
                      style={{ colorScheme: isDark ? 'dark' : 'light' }}
                      className={`w-full border px-3 py-2.5 text-xs font-black font-mono focus:ring-1 focus:ring-primary-tactile outline-none transition-colors ${isDark ? 'bg-slate-800 border-slate-700 text-slate-200' : 'bg-slate-50 border-border-grid text-slate-900'}`}
                    />
                  </div>
                </div>

                {/* Quick Actions & Confirm */}
                <div className="flex flex-col gap-3 pt-2 border-t border-current/10">
                  <div className="grid grid-cols-2 gap-3">
                    <button 
                      onClick={(e) => { e.stopPropagation(); handleQuickDate('today'); }}
                      className={`py-3 text-xs font-black uppercase tracking-widest transition-colors border ${isDark ? 'bg-slate-800 border-slate-700 hover:bg-slate-700 text-slate-200' : 'bg-slate-100 border-slate-200 hover:bg-slate-200 text-slate-800'}`}
                    >
                      Hoje
                    </button>
                    <button 
                      onClick={(e) => { e.stopPropagation(); handleQuickDate('tomorrow'); }}
                      className={`py-3 text-xs font-black uppercase tracking-widest transition-colors border ${isDark ? 'bg-slate-800 border-slate-700 hover:bg-slate-700 text-slate-200' : 'bg-slate-100 border-slate-200 hover:bg-slate-200 text-slate-800'}`}
                    >
                      Amanhã
                    </button>
                  </div>

                  <button 
                    onClick={(e) => { e.stopPropagation(); handleConfirmReschedule(); }}
                    className={`w-full py-3.5 text-xs font-black uppercase tracking-widest transition-colors shadow-soft-touch ${isDark ? 'bg-primary-tactile hover:bg-primary-tactile/80 text-white' : 'bg-slate-900 hover:bg-slate-800 text-white'}`}
                  >
                    Concluir Reagendamento
                  </button>
                </div>
              </div>
            </div>,
            document.body
          )}
        </div>
      </div>
    </div>

    {isExpanded && (
        <div 
          onClick={(e) => e.stopPropagation()} 
          className={`w-full px-4 md:px-6 py-4 border-t animate-in slide-in-from-top-2 duration-200 font-mono text-xs ${isDark ? 'bg-black/40 border-white/10 text-slate-300' : 'bg-slate-50/80 border-border-grid text-slate-700'}`}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 block mb-1">Descrição / Síntese</span>
              <div className="space-y-2">
                <p className="whitespace-pre-wrap font-mono leading-relaxed">{!isBlankTaskDescription(task.descricao) ? task.descricao : <span className="italic opacity-50">Sem descrição detalhada</span>}</p>
                {canSynthesizeDescription && onSynthesizeDescription && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSynthesizeDescription(task);
                    }}
                    disabled={isSynthesizingDescription}
                    className={`inline-flex items-center gap-2 px-3 py-1.5 border text-[9px] font-black uppercase tracking-widest transition-all disabled:opacity-60 disabled:cursor-wait ${isDark ? 'bg-indigo-500/15 border-indigo-400/30 text-indigo-200 hover:bg-indigo-500/25' : 'bg-indigo-50 border-indigo-100 text-indigo-700 hover:bg-indigo-100'}`}
                    title="Gerar descricao com IA a partir do diario e checklist"
                  >
                    <svg className={`w-3.5 h-3.5 ${isSynthesizingDescription ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    {isSynthesizingDescription ? 'Gerando...' : 'Gerar descricao com IA'}
                  </button>
                )}
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 block mb-1">Status</span>
                <span className={`inline-block px-2 py-0.5 uppercase tracking-widest text-[10px] font-black border ${task.status === 'concluído' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : task.status === 'stand-by' ? 'bg-amber-500/10 border-amber-500/30 text-amber-400' : 'bg-blue-500/10 border-blue-500/30 text-blue-400'}`}>
                  {task.status}
                </span>
              </div>
              {task.sistema && (
                <div>
                  <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 block mb-1">Sistema Associado</span>
                  <span className="inline-block px-2 py-0.5 bg-white/5 border border-white/10 text-[10px] font-bold text-slate-300">{task.sistema}</span>
                </div>
              )}
              {task.tags && task.tags.length > 0 && (
                <div>
                  <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 block mb-1">Tags</span>
                  <div className="flex flex-wrap gap-1.5">
                    {task.tags.map(tag => (
                      <span key={tag} className="px-2 py-0.5 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-[10px] font-bold">#{tag}</span>
                    ))}
                  </div>
                </div>
              )}
              {task.pool_dados && task.pool_dados.length > 0 && (
                <div>
                  <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 block mb-1">Anexos no Pool</span>
                  <span className="text-[11px] font-bold">{task.pool_dados.length} item(ns) anexado(s)</span>
                </div>
              )}
            </div>
          </div>
          {task.plano_acao && task.plano_acao.length > 0 && (
            <div className="mt-4 pt-3 border-t border-current/10">
              <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 block mb-2">Checklist / Plano de Ação ({task.plano_acao.filter(p => p.completed).length}/{task.plano_acao.length})</span>
              <div className="space-y-1.5 max-h-40 overflow-y-auto pr-2 custom-scrollbar">
                {task.plano_acao.map(item => (
                  <div key={item.id} className="flex items-start gap-2 text-[11px]">
                    <span className={`mt-0.5 text-[10px] shrink-0 ${item.completed ? 'text-emerald-400' : 'text-slate-500'}`}>{item.completed ? '✓' : '•'}</span>
                    <span className={item.completed ? 'line-through text-slate-500' : ''}>{item.text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
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
        <div className="flex items-center gap-2">
          <span className="bg-primary-tactile text-white text-[10px] font-black px-2.5 py-1 rounded-none shadow-soft-touch font-mono">
            {notifications.filter(n => !n.isRead).length}
          </span>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 transition-colors p-1"
            aria-label="Fechar notificações"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
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
