import React, { useState, useEffect, useRef } from 'react';
import {
  Tarefa, HermesNotification, WysiwygEditorProps, PlanoTrabalhoItem,
  EntregaInstitucional, AtividadeRealizada
} from '../../types';
import { formatDate } from '../../types';
import { STATUS_COLORS, PROJECT_COLORS } from '../../constants';
import { normalizeStatus } from '../../utils/helpers';

// Local Toast type (matches the one in index.tsx)
interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info';
  action?: { label: string | React.ReactNode, onClick: () => void };
  actions?: { label: string | React.ReactNode, onClick: () => void }[];
}

export const ToastContainer = ({ toasts, removeToast }: { toasts: Toast[], removeToast: (id: string) => void }) => {
  return (
    <div className="fixed bottom-4 sm:top-8 right-4 sm:right-8 left-4 sm:left-auto z-[9999] flex flex-col gap-3 pointer-events-none">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`pointer-events-auto px-6 py-4 rounded-lg sm:rounded-lg md:rounded-[1.25rem] shadow-[0_20px_50px_rgba(0,0,0,0.3)] backdrop-blur-md flex items-center gap-4 animate-in slide-in-from-bottom-12 sm:slide-in-from-right-12 fade-in duration-500 min-w-[320px] border border-white/10 ${toast.type === 'success' ? 'bg-emerald-600/95 text-white' :
            toast.type === 'error' ? 'bg-rose-600/95 text-white' :
              'bg-slate-900/95 text-white'
            }`}
        >
          <div className="flex-shrink-0">
            {toast.type === 'success' && <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg></div>}
            {toast.type === 'error' && <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg></div>}
            {toast.type === 'info' && <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg></div>}
          </div>
          <div className="flex-1">
            <span className="text-[10px] font-black uppercase tracking-[0.2em] leading-none opacity-60 block mb-0.5">{toast.type}</span>
            <span className="text-sm font-bold tracking-tight">{toast.message}</span>
          </div>
          <div className="flex items-center gap-2">
            {toast.action && (
              <button
                onClick={() => {
                  toast.action?.onClick();
                  removeToast(toast.id);
                }}
                className="bg-white/20 hover:bg-white/30 px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all active:scale-95"
              >
                {toast.action.label}
              </button>
            )}
            {toast.actions && toast.actions.map((act, i) => (
              <button
                key={i}
                onClick={() => {
                  act.onClick();
                  // Opicional: remover toast ao clicar? Depende da ação. 
                  // Para "copiar" talvez não precise remover.
                }}
                className="bg-white/10 hover:bg-white/20 p-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 flex items-center justify-center"
              >
                {act.label}
              </button>
            ))}
            <button onClick={() => removeToast(toast.id)} className="p-2 hover:bg-white/20 rounded-lg transition-colors opacity-40 hover:opacity-100">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};
export const FilterChip = React.memo(({ label, isActive, onClick, colorClass }: { label: string, isActive: boolean, onClick: () => void, colorClass?: string }) => (
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
export const PgcMiniTaskCard = React.memo(({ task, onClick }: { task: Tarefa, onClick?: () => void }) => {
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
      className="group border-b border-slate-100 hover:bg-slate-50 transition-all p-4 md:p-8 flex flex-col gap-3 md:gap-4"
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
export const RowCard = React.memo(({ task, onClick, onToggle, onDelete, onEdit, onUpdateToToday, highlighted }: {
  task: Tarefa,
  onClick?: () => void,
  onToggle: (id: string, currentStatus: string) => void,
  onDelete: (id: string) => void,
  onEdit: (t: Tarefa) => void,
  onUpdateToToday?: (t: Tarefa) => void,
  highlighted?: boolean
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
      className={`group w-full px-4 md:px-6 py-4 md:py-3 border-b border-slate-100 hover:bg-slate-50/80 transition-all flex flex-col sm:flex-row sm:items-center gap-4 md:gap-6 animate-in cursor-pointer relative ${isCompleted ? 'opacity-60 grayscale-[0.5]' : ''} ${highlighted ? 'bg-gradient-to-r from-amber-50 to-white border-l-4 border-l-amber-500 py-7 md:py-6 shadow-md ring-1 ring-amber-200/50' : 'bg-white'}`}
    >
      {/* Esquerda: Checkbox + Título */}
      <div className="flex items-center gap-4 flex-1 min-w-0">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle(task.id, task.status);
          }}
          className={`w-6 h-6 sm:w-5 sm:h-5 rounded-lg border-2 flex items-center justify-center transition-all flex-shrink-0 ${isCompleted ? 'bg-emerald-500 border-emerald-500 text-white' : (highlighted ? 'border-amber-300 hover:border-amber-500' : 'border-slate-200 hover:border-slate-400')} text-transparent`}
        >
          <svg className="w-4 h-4 sm:w-3.5 sm:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M5 13l4 4L19 7" /></svg>
        </button>

        <div className="flex flex-col gap-1 flex-1 min-w-0">
          {highlighted && !isCompleted && (
            <div className="flex items-center gap-1.5 animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
              <span className="text-[9px] font-black text-amber-600 uppercase tracking-[0.2em]">Prioridade Máxima • Ação do Dia</span>
            </div>
          )}
          <div className={`${highlighted ? 'text-base md:text-xl font-black text-amber-950' : 'text-sm md:text-base font-bold text-[#1a202c]'} leading-tight transition-colors ${isCompleted ? 'line-through text-slate-400' : (highlighted ? 'group-hover:text-amber-700' : 'group-hover:text-blue-600')} line-clamp-2 sm:line-clamp-1`}>
            {task.titulo}
          </div>
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
            {dateDisplay} {task.horario_inicio ? `• ${task.horario_inicio}` : ''}
          </div>

          {/* Ações: Sempre visíveis no mobile (sm:opacity-0), hover no desktop */}
          {!isCompleted && (
            <div className="flex items-center gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-all">
              {onUpdateToToday && (
                <button
                  onClick={(e) => { e.stopPropagation(); onUpdateToToday(task); }}
                  className="p-2 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg md:rounded-xl transition-all"
                  title="Atualizar para Hoje (Limpar Horário)"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </button>
              )}

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
export interface AutoExpandingTextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> { }

export const AutoExpandingTextarea = (props: AutoExpandingTextareaProps) => {
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
      className={`${props.className} resize-none overflow-hidden block`}
    />
  );
};

export const WysiwygEditor = ({ value, onChange, onKeyDown, placeholder, className, id }: WysiwygEditorProps) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-expand logic
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
    if (!text) return <span className="text-slate-400/50">{placeholder}</span>;

    const lines = text.split('\n');
    const processedLines: React.JSX.Element[] = [];
    let currentList: React.JSX.Element[] = [];

    const flushList = () => {
      if (currentList.length > 0) {
        processedLines.push(<ul key={`list-${processedLines.length}`} className="list-disc ml-6 my-1 space-y-0 shadow-none border-none bg-transparent">{currentList}</ul>);
        currentList = [];
      }
    };

    const formatInline = (text: string) => {
      return (
        <>
          {text.split(/(```[\s\S]+?```|`[^`]+`|\*[^*]+\*|_[^_]+_|~[^~]+~)/g).map((part, j) => {
            if (part.startsWith('```') && part.endsWith('```')) {
              return <pre key={j} className="bg-slate-100/80 p-2 rounded-lg font-mono text-[11px] my-1 overflow-x-auto border border-slate-200 text-slate-800">{part.slice(3, -3)}</pre>;
            }
            if (part.startsWith('*') && part.endsWith('*')) {
              return <span key={j} className="font-bold text-slate-900"><span className="opacity-20">*</span>{part.slice(1, -1)}<span className="opacity-20">*</span></span>;
            }
            if (part.startsWith('_') && part.endsWith('_')) {
              return <span key={j} className="italic"><span className="opacity-20">_</span>{part.slice(1, -1)}<span className="opacity-20">_</span></span>;
            }
            if (part.startsWith('~') && part.endsWith('~')) {
              return <span key={j} className="line-through opacity-60"><span className="opacity-20">~</span>{part.slice(1, -1)}<span className="opacity-20">~</span></span>;
            }
            if (part.startsWith('`') && part.endsWith('`')) {
              return <span key={j} className="font-mono bg-slate-100 px-1 rounded text-pink-600 border border-slate-200"><span className="opacity-20">`</span>{part.slice(1, -1)}<span className="opacity-20">`</span></span>;
            }
            return part;
          })}
        </>
      );
    };

    lines.forEach((line, index) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        currentList.push(<li key={index} className="pl-1 text-sm leading-relaxed">{formatInline(line.substring(line.indexOf(trimmed.startsWith('- ') ? '- ' : '* ') + 2))}</li>);
      } else {
        flushList();
        if (trimmed.startsWith('>')) {
          processedLines.push(
            <blockquote key={index} className="border-l-4 border-slate-300 pl-4 py-1 my-1 italic text-slate-500 bg-slate-50/50 rounded-r-lg leading-relaxed">
              {formatInline(line.substring(line.indexOf('>') + 1).trim())}
            </blockquote>
          );
        } else if (line === '') {
          processedLines.push(<div key={index} className="h-[1.625em]"></div>);
        } else {
          processedLines.push(<div key={index} className="min-h-[1.625em] leading-relaxed">{formatInline(line)}</div>);
        }
      }
    });
    flushList();

    return <div className="whitespace-pre-wrap break-words">{processedLines}</div>;
  };

  return (
    <div className={`relative min-h-[56px] group ${className}`}>
      {/* Background Decorative border to avoid glitchy rendering */}
      <div className="absolute inset-0 border border-slate-200 rounded-2xl pointer-events-none group-focus-within:ring-2 group-focus-within:ring-blue-500/20 group-focus-within:border-blue-500 transition-all"></div>

      {/* Display Layer */}
      <div
        className="absolute inset-0 p-4 pointer-events-none overflow-hidden text-sm font-medium leading-relaxed"
        style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'inherit' }}
      >
        {renderFormattedText(value)}
      </div>

      {/* Input Layer */}
      <textarea
        ref={textareaRef}
        id={id}
        value={value}
        onChange={handleInput}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        className="w-full bg-transparent border-none px-4 py-4 text-sm font-medium leading-relaxed text-transparent caret-blue-500 outline-none transition-all resize-none overflow-hidden block relative z-10"
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
export const NotificationCenter = ({
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
  onUpdateOverdue?: (id?: string) => void,
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
              onClick={(e) => {
                if ((e.target as HTMLElement).closest('button')) return;
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
                        e.preventDefault();
                        onMarkAsRead(n.id);
                        onUpdateOverdue(n.id);
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







