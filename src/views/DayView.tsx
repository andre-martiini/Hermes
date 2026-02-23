import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Tarefa, GoogleCalendarEvent, AppSettings, formatDateLocalISO } from '../../types';
import { normalizeStatus } from '../utils/helpers';
import { PROJECT_COLORS } from '../../constants';

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
      {allDayEvents.length > 0 && (
        <div className="flex-shrink-0 bg-white border-b border-slate-100 flex items-center min-h-[40px] px-4 py-2 gap-4">
          <div className="w-16 flex-shrink-0 text-[10px] font-black text-slate-400 uppercase tracking-widest text-center">Dia Todo</div>
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
            {Array.from({ length: 24 }).map((_, i) => (
              <div key={i} className="absolute left-0 right-0 border-t border-slate-100 flex items-start" style={{ top: i * hourHeight, height: hourHeight }}>
                <span className="text-[10px] text-slate-300 font-mono -mt-2 bg-slate-50 px-1 ml-2">{i.toString().padStart(2, '0')}:00</span>
              </div>
            ))}

            {isToday && (
              <div className="absolute left-0 right-0 border-t-2 border-red-500 z-20 pointer-events-none" style={{ top: currentTimeTop }}>
                <div className="absolute -left-1 -top-1.5 w-3 h-3 bg-red-500 rounded-full"></div>
              </div>
            )}

            {positionedEvents.map(event => {
              const startMin = event.start;
              const endMin = event.end;
              const top = (startMin / 60) * hourHeight;
              const height = ((endMin - startMin) / 60) * hourHeight;

              const columnWidth = (100 - 18) / event.totalCols; 
              const left = 18 + (event.colIndex * columnWidth);
              const width = columnWidth - 0.5; 

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
                const taskItem = event.data as Tarefa;
                return (
                  <div
                    key={taskItem.id}
                    className={`absolute rounded-lg md:rounded-xl border p-2 shadow-sm group transition-all cursor-grab active:cursor-grabbing overflow-hidden hover:z-30
                      ${taskItem.categoria === 'CLC' ? 'bg-blue-50 border-blue-200 text-blue-800' :
                        taskItem.categoria === 'ASSISTÊNCIA' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' :
                          'bg-white border-slate-200 text-slate-800'}
                    `}
                    style={{ top, height: Math.max(30, height), left: `${left}%`, width: `${width}%`, zIndex: 10 }}
                    onMouseDown={(e) => {
                      const target = e.target as HTMLElement;
                      if (target.classList.contains('resize-handle')) return;
                      dragStartRef.current = { x: e.clientX, y: e.clientY };
                      setDragging({ id: taskItem.id, startY: e.clientY, startMin });
                    }}
                    onClick={(e) => {
                      if (dragStartRef.current && Math.abs(e.clientX - dragStartRef.current.x) < 5 && Math.abs(e.clientY - dragStartRef.current.y) < 5) {
                         e.stopPropagation();
                         setContextMenu({ x: e.clientX, y: e.clientY, task: taskItem });
                      }
                      dragStartRef.current = null;
                    }}
                  >
                    <div className="flex justify-between items-start gap-2">
                      <div className="text-[11px] font-black leading-tight line-clamp-2">{taskItem.titulo}</div>
                      <div className="flex gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmAction({
                              taskId: taskItem.id,
                              newStatus: taskItem.status === 'concluído' ? 'em andamento' : 'concluído'
                            });
                          }}
                          className={`p-1 hover:bg-black/5 rounded ${taskItem.status === 'concluído' ? 'text-emerald-600 bg-emerald-100' : 'text-slate-400 hover:text-emerald-600'}`}
                          title={taskItem.status === 'concluído' ? 'Reabrir' : 'Concluir'}
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); onExecuteTask(taskItem); }} className="p-1 hover:bg-black/5 rounded text-indigo-600" title="Executar">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); onTaskClick(taskItem); }} className="p-1 hover:bg-black/5 rounded" title="Editar">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                        </button>
                      </div>
                    </div>

                    <div
                      className="resize-handle absolute top-0 left-0 right-0 h-2 cursor-ns-resize hover:bg-black/10 transition-colors"
                      onMouseDown={(e) => {
                        e.stopPropagation();
                        setResizing({ id: taskItem.id, type: 'top', startY: e.clientY, startMin });
                      }}
                    />
                    <div
                      className="resize-handle absolute bottom-0 left-0 right-0 h-2 cursor-ns-resize hover:bg-black/10 transition-colors"
                      onMouseDown={(e) => {
                        e.stopPropagation();
                        setResizing({ id: taskItem.id, type: 'bottom', startY: e.clientY, startMin: endMin });
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
            {dayTasks.filter(t => !t.horario_inicio || (t.data_inicio && t.data_inicio < dayStr)).map(taskItem => (
              <div
                key={taskItem.id}
                draggable
                onDragStart={(e) => e.dataTransfer.setData('task-id', taskItem.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const draggedId = e.dataTransfer.getData('task-id');
                  if (draggedId && draggedId !== taskItem.id && onReorderTasks) {
                    onReorderTasks(draggedId, taskItem.id);
                  }
                }}
                onClick={() => {
                  if (window.innerWidth < 768) {
                    const now = new Date();
                    const hour = now.getHours();
                    onTaskUpdate(taskItem.id, {
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
                <div className="text-[10px] font-bold text-slate-700 leading-tight mb-2">{taskItem.titulo}</div>
                <div className="flex items-center gap-2">
                  <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase ${PROJECT_COLORS[taskItem.projeto] || 'bg-slate-100 text-slate-600'}`}>{taskItem.projeto}</span>
                  {(!taskItem.data_limite || taskItem.data_limite === '-' || taskItem.data_limite === '0000-00-00') && (
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
                    const startInput = document.getElementById('edit-start-time') as HTMLInputElement;
                    const endInput = document.getElementById('edit-end-time') as HTMLInputElement;
                    if (startInput?.value && endInput?.value) {
                      onTaskUpdate(editingTimeTask.id, { horario_inicio: startInput.value, horario_fim: endInput.value }, true);
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
