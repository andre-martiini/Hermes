import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Tarefa, GoogleCalendarEvent, PlanoTrabalhoItem, EntregaInstitucional,
  AtividadeRealizada, WorkItem, WorkItemPhase, Acompanhamento,
  PoolItem, ConhecimentoItem, AppSettings
} from '../../types';
import { formatDate, formatDateLocalISO } from '../../types';
import { PROJECT_COLORS } from '../../constants';
import { normalizeStatus, formatWhatsAppText, callScrapeSipac } from '../utils/helpers';
import { RowCard, PgcAuditRow, WysiwygEditor } from '../components/ui/UIComponents';
import { db, functions } from '../../firebase';
import { httpsCallable } from 'firebase/functions';
import { setDoc, doc } from 'firebase/firestore';
export const DayView = ({
  tasks,
  googleEvents = [],
  currentDate,
  onTaskClick,
  onTaskUpdate,
  onExecuteTask,
  onReorderTasks,
  showToast
}: {
  tasks: Tarefa[],
  googleEvents?: GoogleCalendarEvent[],
  currentDate: Date,
  onTaskClick: (t: Tarefa) => void,
  onTaskUpdate: (id: string, updates: Partial<Tarefa>, suppressToast?: boolean) => void,
  onExecuteTask: (t: Tarefa) => void,
  onReorderTasks?: (taskId: string, targetTaskId: string, label?: string) => void,
  showToast?: (message: string, type: 'success' | 'error' | 'info') => void
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
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [dragging, setDragging] = useState<{ id: string, startY: number, startMin: number } | null>(null);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [contextMenu, setContextMenu] = useState<{ x: number, y: number, task: Tarefa } | null>(null);
  const [editingTimeTask, setEditingTimeTask] = useState<Tarefa | null>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const dragStartRef = useRef<{ x: number, y: number } | null>(null);

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
    if (!googleEvents) return { allDayEvents: [], timedEvents: [] };
    const dayEvents = googleEvents.filter(e => {
      if (!e.data_inicio || !e.data_fim) return false;
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
      allDayEvents: dayEvents.filter(e => !e.data_inicio?.includes('T')),
      timedEvents: dayEvents.filter(e => e.data_inicio?.includes('T'))
    };
  }, [googleEvents, dayStr]);

  const dayTasks = useMemo(() => tasks.filter(t => {
    if (t.status === 'excluído' as any) return false;

    const isConcluido = normalizeStatus(t.status) === 'concluido';

    // Se a tarefa já tem horário definido (está alocada), respeitamos estritamente a data definida
    if (t.horario_inicio && t.data_inicio) {
      // Se não está concluída e é do passado, permitimos aparecer no sidebar de hoje (rollover)
      if (!isConcluido && t.data_inicio < dayStr && dayStr === formatDateLocalISO(new Date())) {
        return true;
      }
      return t.data_inicio === dayStr;
    }

    const end = t.data_limite;
    const hasDeadline = end && end !== '-' && end !== '0000-00-00';

    // Se não tem prazo, aparece sempre no sidebar para alocação (Critério: ações sem data definida)
    if (!hasDeadline) return true;

    // Se já está concluída e o prazo passou, não deve aparecer hoje (a menos que estejamos vendo o dia em que ela venceu)
    if (isConcluido && end < dayStr) return false;

    // Critérios únicos para o campo aguardando alocação:
    // - As ações que são daquele dia (dayStr === end)
    // - As ações que são dos dias anteriores àquele dia (dayStr > end)
    // Ou seja: dayStr >= end
    return dayStr >= end;
  }).sort((a, b) => (a.ordem || 0) - (b.ordem || 0)), [tasks, dayStr]);

  const positionedEvents = useMemo(() => {
    if (!timedEvents || !dayTasks) return [];
    const allItems = [
      ...timedEvents.map(e => ({
        id: e.id,
        title: e.titulo,
        start: timeToMinutes(e.data_inicio?.includes('T') ? e.data_inicio.split('T')[1].substring(0, 5) : '00:00'),
        end: timeToMinutes(e.data_fim?.includes('T') ? e.data_fim.split('T')[1].substring(0, 5) : '23:59'),
        type: 'google' as const,
        data: e
      })),
      ...dayTasks.filter(t => t.horario_inicio && t.data_inicio === dayStr).map(t => ({
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
    <div className="flex flex-col h-[600px] overflow-hidden bg-slate-50 border-t border-slate-100 relative">
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
        {/* Floating Action Button for Mobile Allocation */}
        <button
          onClick={() => setIsSidebarOpen(true)}
          className="md:hidden fixed bottom-24 right-6 z-[60] w-14 h-14 bg-blue-600 text-white rounded-full shadow-2xl flex items-center justify-center animate-bounce"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 6v6m0 0v6m0-6h6m-6 0H6" /></svg>
        </button>

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
                      dragStartRef.current = { x: e.clientX, y: e.clientY };
                      setDragging({ id: task.id, startY: e.clientY, startMin });
                    }}
                    onClick={(e) => {
                      if (dragStartRef.current && Math.abs(e.clientX - dragStartRef.current.x) < 5 && Math.abs(e.clientY - dragStartRef.current.y) < 5) {
                         e.stopPropagation();
                         setContextMenu({ x: e.clientX, y: e.clientY, task });
                      }
                      dragStartRef.current = null;
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
          className={`${isSidebarOpen ? 'fixed inset-0 z-[100] bg-white' : 'hidden'} md:relative md:block md:w-64 bg-slate-50 border-l border-slate-200 p-6 overflow-y-auto custom-scrollbar animate-in slide-in-from-right duration-300`}
          onDragOver={e => e.preventDefault()}
          onDrop={(e) => {
            const taskId = e.dataTransfer.getData('task-id');
            if (taskId) {
              onTaskUpdate(taskId, { horario_inicio: null, horario_fim: null });
            }
          }}
        >
          <div className="flex items-center justify-between mb-8">
            <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Aguardando Alocação</h4>
            <button onClick={() => setIsSidebarOpen(false)} className="md:hidden p-2 bg-slate-200 rounded-full">
               <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>

          <div className="space-y-3">
            {dayTasks.filter(t => !t.horario_inicio || (t.data_inicio && t.data_inicio < dayStr)).map(task => (
              <div
                key={task.id}
                draggable
                onDragStart={(e) => e.dataTransfer.setData('task-id', task.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const draggedId = e.dataTransfer.getData('task-id');
                  if (draggedId && draggedId !== task.id && onReorderTasks) {
                    onReorderTasks(draggedId, task.id);
                  }
                }}
                onClick={() => {
                  if (window.innerWidth < 768) {
                    // Mobile: Allocate to current hour by default if clicked
                    const now = new Date();
                    const hour = now.getHours();
                    onTaskUpdate(task.id, {
                      horario_inicio: `${hour.toString().padStart(2, '0')}:00`,
                      horario_fim: `${(hour + 1).toString().padStart(2, '0')}:00`,
                      data_inicio: dayStr
                    });
                    setIsSidebarOpen(false);
                    if (showToast) showToast("Alocado para agora!", "success");
                  }
                }}
                className="bg-white p-4 rounded-none md:rounded-2xl border border-slate-200 shadow-sm hover:border-blue-400 hover:shadow-md transition-all cursor-pointer md:cursor-grab active:cursor-grabbing"
              >
                <div className="text-[10px] font-bold text-slate-700 leading-tight mb-2">{task.titulo}</div>
                <div className="flex items-center gap-2">
                  <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase ${PROJECT_COLORS[task.projeto] || 'bg-slate-100 text-slate-600'}`}>{task.projeto}</span>
                  {(!task.data_limite || task.data_limite === '-' || task.data_limite === '0000-00-00') && (
                    <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-amber-100 text-amber-700">Sem Prazo</span>
                  )}
                </div>
                <p className="md:hidden mt-3 text-[8px] font-black text-blue-600 uppercase tracking-widest">Toque para alocar agora</p>
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

      {contextMenu && (
        <>
          <div className="fixed inset-0 z-[150]" onClick={() => setContextMenu(null)}></div>
          <div
            className="absolute z-[160] bg-white rounded-xl shadow-2xl border border-slate-100 py-2 w-48 animate-in fade-in zoom-in-95"
            style={{ top: Math.min(contextMenu.y, window.innerHeight - 200), left: Math.min(contextMenu.x, window.innerWidth - 200) }}
          >
            <button
              onClick={() => {
                onTaskUpdate(contextMenu.task.id, { horario_inicio: null, horario_fim: null });
                setContextMenu(null);
                if (showToast) showToast("Movido para Aguardando Alocação", "info");
              }}
              className="w-full text-left px-4 py-3 hover:bg-slate-50 text-xs font-bold text-slate-700 flex items-center gap-2"
            >
              <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
              Aguardando Alocação
            </button>
            <button
              onClick={() => {
                setEditingTimeTask(contextMenu.task);
                setContextMenu(null);
              }}
              className="w-full text-left px-4 py-3 hover:bg-slate-50 text-xs font-bold text-slate-700 flex items-center gap-2"
            >
              <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              Alterar Horário
            </button>
            <div className="border-t border-slate-100 my-1"></div>
            <button
              onClick={() => {
                onTaskClick(contextMenu.task);
                setContextMenu(null);
              }}
              className="w-full text-left px-4 py-3 hover:bg-slate-50 text-xs font-bold text-slate-700 flex items-center gap-2"
            >
              <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
              Editar Detalhes
            </button>
          </div>
        </>
      )}

      {editingTimeTask && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl p-6 max-w-xs w-full shadow-2xl animate-in zoom-in-95">
            <h3 className="text-sm font-black text-slate-900 mb-4 uppercase tracking-widest">Alterar Horário</h3>
            <div className="space-y-4">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase">Início</label>
                <input
                  type="time"
                  defaultValue={editingTimeTask.horario_inicio || ''}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
                  id="edit-start-time"
                />
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase">Fim</label>
                <input
                  type="time"
                  defaultValue={editingTimeTask.horario_fim || ''}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
                  id="edit-end-time"
                />
              </div>
              <div className="flex gap-2 pt-2">
                <button onClick={() => setEditingTimeTask(null)} className="flex-1 py-2 text-[10px] font-black uppercase text-slate-400 hover:bg-slate-50 rounded-xl">Cancelar</button>
                <button
                  onClick={() => {
                    const start = (document.getElementById('edit-start-time') as HTMLInputElement).value;
                    const end = (document.getElementById('edit-end-time') as HTMLInputElement).value;
                    if (start && end) {
                      onTaskUpdate(editingTimeTask.id, { horario_inicio: start, horario_fim: end }, true);
                      setEditingTimeTask(null);
                    }
                  }}
                  className="flex-1 bg-slate-900 text-white py-2 text-[10px] font-black uppercase rounded-xl shadow-lg"
                >
                  Salvar
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

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

      // Create dates using UTC to avoid timezone shifts
      let current = new Date(startStr + 'T12:00:00Z');
      const end = new Date(endStr + 'T12:00:00Z');

      if (isNaN(current.getTime()) || isNaN(end.getTime())) return;

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
export const CategoryView = ({ tasks, viewMode, onSelectTask, onExecuteTask }: { tasks: Tarefa[], viewMode: string, onSelectTask: (t: Tarefa) => void, onExecuteTask: (t: Tarefa) => void }) => {
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
export const TaskExecutionView = ({ task, tarefas, appSettings, onSave, onClose, showToast }: { task: Tarefa, tarefas: Tarefa[], appSettings: AppSettings, onSave: (id: string, updates: Partial<Tarefa>) => void, onClose: () => void, showToast: (msg: string, type?: 'success' | 'error' | 'info') => void }) => {
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

  // Transcription states
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessingTranscription, setIsProcessingTranscription] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

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
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        await handleProcessAudio(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      showToast("Erro ao acessar microfone.", "error");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessingTranscription(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string; refined: string };
          if (data.refined) {
            setNewFollowUp(prev => prev + (prev ? '\n' : '') + data.refined);
          }
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          showToast("Erro ao processar áudio.", "error");
        } finally {
          setIsProcessingTranscription(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessingTranscription(false);
    }
  };

  const applyFormatting = (symbol: string) => {
    const textarea = document.getElementById('diary-input') as HTMLTextAreaElement;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = newFollowUp;
    const selectedText = text.substring(start, end);
    const before = text.substring(0, start);
    const after = text.substring(end);
    const newText = `${before}${symbol}${selectedText}${symbol}${after}`;
    setNewFollowUp(newText);

    // Devolve o foco e ajusta seleção
    setTimeout(() => {
      textarea.focus();
      textarea.setSelectionRange(start + symbol.length, end + symbol.length);
    }, 0);
  };

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

      // Mirror to Knowledge base
      for (const item of uploadedItems) {
        const knowledgeItem: ConhecimentoItem = {
          id: item.id,
          titulo: item.nome || 'Sem título',
          tipo_arquivo: item.nome?.split('.').pop()?.toLowerCase() || 'unknown',
          url_drive: item.valor,
          tamanho: 0,
          data_criacao: item.data_criacao,
          origem: { modulo: 'tarefas', id_origem: task.id }
        };
        setDoc(doc(db, 'conhecimento', item.id), knowledgeItem).catch(console.error);
      }

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
                            await callScrapeSipac(task.id, task.processo_sei);
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

                <div className="flex-1 flex flex-col min-w-0">
                  <div className="relative group">
                    <WysiwygEditor
                      id="diary-input"
                      value={newFollowUp}
                      onChange={setNewFollowUp}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleAddFollowUp();
                        }
                      }}
                      placeholder="Anotação..."
                      className={isTimerRunning ? 'text-white' : 'text-slate-800'}
                    />
                    
                    <button
                      onClick={isRecording ? stopRecording : startRecording}
                      disabled={isProcessingTranscription}
                      className={`absolute right-4 top-1/2 -translate-y-1/2 p-2 rounded-xl transition-all z-20 ${
                        isRecording 
                          ? 'bg-rose-600 text-white animate-pulse shadow-lg' 
                          : isProcessingTranscription
                            ? (isTimerRunning ? 'bg-white/10 text-white/40' : 'bg-blue-100 text-blue-600')
                            : (isTimerRunning ? 'text-white/40 hover:text-white hover:bg-white/10' : 'text-slate-400 hover:text-blue-600 hover:bg-blue-50')
                      }`}
                      title={isRecording ? "Parar Gravação" : "Gravar Anotação"}
                    >
                      {isProcessingTranscription ? (
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                      ) : isRecording ? (
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                      )}
                    </button>
                  </div>
                  <div className={`flex items-center gap-1 mt-1 pt-2 border-t ${isTimerRunning ? 'border-white/10' : 'border-slate-100'}`}>
                    <button
                      onClick={() => applyFormatting('*')}
                      className={`p-1.5 rounded hover:bg-black/10 text-[10px] font-black w-8 h-8 flex items-center justify-center ${isTimerRunning ? 'text-white/40' : 'text-slate-400'}`}
                      title="Negrito (*text*)"
                    >
                      B
                    </button>
                    <button
                      onClick={() => applyFormatting('_')}
                      className={`p-1.5 rounded hover:bg-black/10 text-[10px] italic w-8 h-8 flex items-center justify-center ${isTimerRunning ? 'text-white/40' : 'text-slate-400'}`}
                      title="Itálico (_text_)"
                    >
                      I
                    </button>
                    <button
                      onClick={() => applyFormatting('~')}
                      className={`p-1.5 rounded hover:bg-black/10 text-[10px] line-through w-8 h-8 flex items-center justify-center ${isTimerRunning ? 'text-white/40' : 'text-slate-400'}`}
                      title="Tachado (~text~)"
                    >
                      S
                    </button>
                    <button
                      onClick={() => applyFormatting('`')}
                      className={`p-1.5 rounded hover:bg-black/10 text-[10px] font-mono w-8 h-8 flex items-center justify-center ${isTimerRunning ? 'text-white/40' : 'text-slate-400'}`}
                      title="Código (`text`)"
                    >
                      &lt;/&gt;
                    </button>
                  </div>
                </div>

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




