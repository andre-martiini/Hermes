
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Tarefa, GoogleCalendarEvent, formatDateLocalISO } from '../../../types';
import { normalizeStatus } from '../../utils/helpers';
import { timeToMinutes, minutesToTime, getYFromTime, getTimeFromY, snapToGrid, getColumnFromX } from '../../utils/calendarUtils';
import { PROJECT_COLORS } from '../../../constants';

interface TimeGridProps {
  days: Date[];
  tasks: Tarefa[];
  googleEvents?: GoogleCalendarEvent[];
  onTaskClick: (t: Tarefa) => void;
  onTaskUpdate: (id: string, updates: Partial<Tarefa>, suppressToast?: boolean) => void;
  onExecuteTask: (t: Tarefa) => void;
  onTaskCreate?: (task: Partial<Tarefa>) => void;
  onReorderTasks?: (taskId: string, targetTaskId: string, label?: string) => void;
  showToast?: (message: string, type: 'success' | 'error' | 'info') => void;
  sidebar?: React.ReactNode;
}

export const TimeGrid = ({
  days,
  tasks,
  googleEvents = [],
  onTaskClick,
  onTaskUpdate,
  onExecuteTask,
  onTaskCreate,
  sidebar
}: TimeGridProps) => {
  const [currentTime, setCurrentTime] = useState(new Date());
  const containerRef = useRef<HTMLDivElement>(null);

  const [dragging, setDragging] = useState<{
    id: string,
    task: Tarefa,
    startY: number,
    currentY: number,
    startX: number,
    currentX: number,
    originalStartMin: number,
    duration: number
  } | null>(null);

  const [resizing, setResizing] = useState<{
    id: string,
    type: 'top' | 'bottom',
    startY: number,
    currentY: number,
    originalStartMin: number,
    originalEndMin: number
  } | null>(null);

  const longPressTimer = useRef<NodeJS.Timeout | null>(null);
  const isLongPress = useRef(false);
  const startPos = useRef<{x: number, y: number} | null>(null);

  const hourHeight = 60;
  const step = 15;

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 60000);
    setCurrentTime(new Date());
    return () => clearInterval(timer);
  }, []);

  const eventsByDay = useMemo(() => {
    return days.map(day => {
      const dayStr = formatDateLocalISO(day);
      const dayGoogleEvents = googleEvents.filter(e => {
        if (!e.data_inicio || !e.data_fim) return false;
        const startStr = e.data_inicio.split('T')[0];
        const endStr = e.data_fim.split('T')[0];
        const isTimed = e.data_inicio.includes('T');
        if (startStr === dayStr) return isTimed;
        if (startStr !== endStr && isTimed) return dayStr >= startStr && dayStr <= endStr;
        return false;
      });
      const dayTasks = tasks.filter(t => {
        if ((t.status as any) === 'excluído') return false;
        if (t.horario_inicio && t.data_inicio) return t.data_inicio === dayStr;
        return false;
      }).sort((a, b) => (a.ordem || 0) - (b.ordem || 0));
      return { dayStr, googleEvents: dayGoogleEvents, tasks: dayTasks };
    });
  }, [days, googleEvents, tasks]);

  const getPositionedEvents = (dayIndex: number) => {
    const { googleEvents: gEvents, tasks: tTasks } = eventsByDay[dayIndex];
    const allItems = [
      ...gEvents.map(e => ({
        id: e.id,
        title: e.titulo,
        start: timeToMinutes(e.data_inicio?.includes('T') ? e.data_inicio.split('T')[1].substring(0, 5) : '00:00'),
        end: timeToMinutes(e.data_fim?.includes('T') ? e.data_fim.split('T')[1].substring(0, 5) : '23:59'),
        type: 'google' as const,
        data: e
      })),
      ...tTasks.map(t => {
        const start = timeToMinutes(t.horario_inicio || '00:00');
        const end = t.horario_fim ? timeToMinutes(t.horario_fim) : start + 60;
        return {
          id: t.id,
          title: t.titulo,
          start,
          end,
          type: 'task' as const,
          data: t
        };
      })
    ].sort((a, b) => a.start - b.start || b.end - a.end);

    const clusters: (any[])[] = [];
    let lastEnd = -1;
    allItems.forEach(item => {
      if (item.start >= lastEnd) clusters.push([item]);
      else clusters[clusters.length - 1].push(item);
      lastEnd = Math.max(lastEnd, item.end);
    });

    return clusters.flatMap(cluster => {
      const columns: (any[])[] = [];
      return cluster.map(item => {
        let colIndex = 0;
        while (columns[colIndex] && columns[colIndex].some(other => item.start < other.end && item.end > other.start)) colIndex++;
        if (!columns[colIndex]) columns[colIndex] = [];
        columns[colIndex].push(item);
        return { ...item, colIndex };
      }).map((item, _, clusterResults) => {
        const maxCol = Math.max(...clusterResults.map(i => i.colIndex)) + 1;
        return { ...item, totalCols: maxCol };
      });
    });
  };

  const handleGridMouseDown = (e: React.MouseEvent | React.TouchEvent, day: Date) => {
    const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY;
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
    startPos.current = { x: clientX, y: clientY };
    isLongPress.current = false;

    longPressTimer.current = setTimeout(() => {
      isLongPress.current = true;
      if (containerRef.current && onTaskCreate) {
         const rect = containerRef.current.getBoundingClientRect();
         const y = clientY - rect.top + containerRef.current.scrollTop;
         const timeStr = getTimeFromY(y, hourHeight, step);

         onTaskCreate({
           data_inicio: formatDateLocalISO(day),
           horario_inicio: timeStr,
           horario_fim: minutesToTime(timeToMinutes(timeStr) + 60)
         });
      }
    }, 600);
  };

  const handleGridMouseUp = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  const handleGridMouseMove = (e: React.MouseEvent | React.TouchEvent) => {
    if (longPressTimer.current && startPos.current) {
      const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY;
      const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
      const dist = Math.sqrt(Math.pow(clientX - startPos.current.x, 2) + Math.pow(clientY - startPos.current.y, 2));
      if (dist > 10) {
        clearTimeout(longPressTimer.current);
        longPressTimer.current = null;
      }
    }
  };

  const handleDropFromSidebar = (e: React.DragEvent, dayIndex: number) => {
    e.preventDefault();
    const taskId = e.dataTransfer.getData('task-id') || e.dataTransfer.getData('tarefaId');
    if (taskId && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const relativeY = e.clientY - rect.top + containerRef.current.scrollTop;
      const timeStr = getTimeFromY(relativeY, hourHeight, step);

      const newDate = days[dayIndex];
      onTaskUpdate(taskId, {
        data_inicio: formatDateLocalISO(newDate),
        horario_inicio: timeStr,
        horario_fim: minutesToTime(timeToMinutes(timeStr) + 60)
      });
    }
  };

  useEffect(() => {
    const handleMove = (e: MouseEvent | TouchEvent) => {
      if (!dragging && !resizing) return;
      if (e.cancelable) e.preventDefault();

      const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY;
      const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;

      if (dragging) {
        setDragging(prev => prev ? { ...prev, currentY: clientY, currentX: clientX } : null);
      } else if (resizing) {
        setResizing(prev => prev ? { ...prev, currentY: clientY } : null);
      }
    };

    const handleUp = (e: MouseEvent | TouchEvent) => {
      if (dragging) {
        const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY;
        const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;

        // Check if dropped on Sidebar (Unallocate)
        const sidebarEl = document.getElementById('unallocated-sidebar');
        if (sidebarEl) {
          const sidebarRect = sidebarEl.getBoundingClientRect();
          if (
            clientX >= sidebarRect.left &&
            clientX <= sidebarRect.right &&
            clientY >= sidebarRect.top &&
            clientY <= sidebarRect.bottom
          ) {
            onTaskUpdate(dragging.id, { horario_inicio: null, horario_fim: null });
            setDragging(null);
            return;
          }
        }

        if (containerRef.current) {
           const rect = containerRef.current.getBoundingClientRect();

           const deltaY = dragging.currentY - dragging.startY;
           const deltaMin = Math.round((deltaY / hourHeight) * 60 / step) * step;
           const newStartMin = Math.max(0, Math.min(1440 - dragging.duration, dragging.originalStartMin + deltaMin));

           const timeAxisWidth = 48;
           const gridWidth = rect.width - timeAxisWidth;
           const relativeX = dragging.currentX - rect.left - timeAxisWidth + containerRef.current.scrollLeft;

           const newColIndex = getColumnFromX(relativeX, gridWidth, days.length);
           const newDate = days[newColIndex];

           if (newDate) {
             const newDateStr = formatDateLocalISO(newDate);
             if (Math.abs(deltaMin) > 0 || newDateStr !== formatDateLocalISO(new Date(dragging.task.data_inicio))) {
                onTaskUpdate(dragging.id, {
                  data_inicio: newDateStr,
                  horario_inicio: minutesToTime(newStartMin),
                  horario_fim: minutesToTime(newStartMin + dragging.duration)
                });
             }
           }
        }
        setDragging(null);
      } else if (resizing) {
         const deltaY = resizing.currentY - resizing.startY;
         const deltaMin = Math.round((deltaY / hourHeight) * 60 / step) * step;
         let newStart = resizing.originalStartMin;
         let newEnd = resizing.originalEndMin;
         if (resizing.type === 'top') {
           newStart = Math.min(newStart + deltaMin, newEnd - 15);
           newStart = Math.max(0, newStart);
         } else {
           newEnd = Math.max(newStart + 15, newEnd + deltaMin);
           newEnd = Math.min(1440, newEnd);
         }
         if (newStart !== resizing.originalStartMin || newEnd !== resizing.originalEndMin) {
            onTaskUpdate(resizing.id, {
              horario_inicio: minutesToTime(newStart),
              horario_fim: minutesToTime(newEnd)
            });
         }
         setResizing(null);
      }
    };

    if (dragging || resizing) {
      window.addEventListener('mousemove', handleMove);
      window.addEventListener('mouseup', handleUp);
      window.addEventListener('touchmove', handleMove, { passive: false });
      window.addEventListener('touchend', handleUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
      window.removeEventListener('touchmove', handleMove);
      window.removeEventListener('touchend', handleUp);
    };
  }, [dragging, resizing, days, onTaskUpdate]);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-slate-50 border-t border-slate-100 relative select-none">
      <div className="flex flex-1 overflow-hidden relative">
        <div className="flex-1 overflow-y-auto custom-scrollbar relative flex" ref={containerRef}>
          <div className="w-12 flex-shrink-0 bg-white border-r border-slate-100 relative sticky left-0 z-20" style={{ height: 24 * hourHeight }}>
            {Array.from({ length: 24 }).map((_, i) => (
              <div key={i} className="absolute right-2 text-[10px] text-slate-300 font-mono" style={{ top: i * hourHeight - 6 }}>
                {i.toString().padStart(2, '0')}:00
              </div>
            ))}
          </div>

          {days.map((day, dayIndex) => {
             const dayStr = formatDateLocalISO(day);
             const isToday = formatDateLocalISO(currentTime) === dayStr;
             const positioned = getPositionedEvents(dayIndex);

             return (
               <div
                 key={dayStr}
                 className="flex-1 relative border-r border-slate-100 min-w-[150px] cursor-crosshair active:cursor-grabbing"
                 style={{ height: 24 * hourHeight }}
                 onMouseDown={(e) => handleGridMouseDown(e, day)}
                 onMouseUp={handleGridMouseUp}
                 onMouseMove={handleGridMouseMove}
                 onTouchStart={(e) => handleGridMouseDown(e, day)}
                 onTouchEnd={handleGridMouseUp}
                 onTouchMove={handleGridMouseMove}
                 onDragOver={(e) => e.preventDefault()}
                 onDrop={(e) => handleDropFromSidebar(e, dayIndex)}
               >
                 {Array.from({ length: 24 }).map((_, i) => (
                    <div key={i} className="absolute left-0 right-0 border-t border-slate-50" style={{ top: i * hourHeight, height: hourHeight }}></div>
                 ))}

                 {isToday && (
                    <div className="absolute left-0 right-0 border-t-2 border-red-500 z-20 pointer-events-none" style={{ top: (currentTime.getHours() * 60 + currentTime.getMinutes()) / 60 * hourHeight }}>
                      <div className="absolute -left-1.5 -top-1.5 w-3 h-3 bg-red-500 rounded-full"></div>
                    </div>
                 )}

                 {positioned.map(event => {
                   const isDragging = dragging?.id === event.id;
                   const startMin = event.start;
                   const endMin = event.end;
                   const top = (startMin / 60) * hourHeight;
                   const height = ((endMin - startMin) / 60) * hourHeight;
                   const columnWidth = 100 / event.totalCols;
                   const left = event.colIndex * columnWidth;

                   if (event.type === 'google') {
                      return (
                        <div
                          key={event.id}
                          className="absolute rounded-lg border-l-4 p-1 shadow-sm bg-amber-50/90 border-amber-500 text-slate-800 overflow-hidden"
                          style={{ top, height: Math.max(20, height), left: `${left}%`, width: `${columnWidth}%`, zIndex: 5 }}
                          onMouseDown={e => e.stopPropagation()}
                          onTouchStart={e => e.stopPropagation()}
                        >
                           <div className="text-[9px] font-black leading-tight line-clamp-1">{event.title}</div>
                        </div>
                      );
                   }

                   const taskItem = event.data as Tarefa;
                   return (
                     <div
                        key={event.id}
                        className={`absolute rounded-lg border p-1 shadow-sm group transition-all overflow-hidden hover:z-30 cursor-grab active:cursor-grabbing
                           ${taskItem.categoria === 'CLC' ? 'bg-blue-50 border-blue-200 text-blue-800' :
                             taskItem.categoria === 'ASSISTÊNCIA' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' :
                             'bg-white border-slate-200 text-slate-800'}
                           ${isDragging ? 'opacity-30' : ''}
                        `}
                        style={{ top, height: Math.max(30, height), left: `${left}%`, width: `${columnWidth}%`, zIndex: 10, touchAction: 'none' }}
                        onMouseDown={(e) => {
                          if ((e.target as HTMLElement).classList.contains('resize-handle')) return;
                          e.stopPropagation();
                          const clientY = e.clientY;
                          const clientX = e.clientX;
                          setDragging({
                            id: event.id,
                            task: event.data as Tarefa,
                            startY: clientY,
                            currentY: clientY,
                            startX: clientX,
                            currentX: clientX,
                            originalStartMin: startMin,
                            duration: endMin - startMin
                          });
                        }}
                        onTouchStart={(e) => {
                          if ((e.target as HTMLElement).classList.contains('resize-handle')) return;
                          e.stopPropagation();
                          const clientY = e.touches[0].clientY;
                          const clientX = e.touches[0].clientX;
                          setDragging({
                            id: event.id,
                            task: event.data as Tarefa,
                            startY: clientY,
                            currentY: clientY,
                            startX: clientX,
                            currentX: clientX,
                            originalStartMin: startMin,
                            duration: endMin - startMin
                          });
                        }}
                     >
                       <div className="flex justify-between items-start gap-1">
                         <div className="text-[10px] font-bold leading-tight line-clamp-2 flex-1">{taskItem.titulo}</div>
                         <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 bg-white/50 rounded backdrop-blur-sm">
                            <button
                              onClick={(e) => { e.stopPropagation(); onTaskUpdate(taskItem.id, { status: taskItem.status === 'concluído' ? 'em andamento' : 'concluído' }); }}
                              className={`p-0.5 rounded hover:bg-black/10 ${taskItem.status === 'concluído' ? 'text-emerald-600' : 'text-slate-400'}`}
                            >
                              <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                            </button>
                            <button onClick={(e) => { e.stopPropagation(); onExecuteTask(taskItem); }} className="p-0.5 rounded hover:bg-black/10 text-indigo-600">
                              <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /></svg>
                            </button>
                            <button onClick={(e) => { e.stopPropagation(); onTaskClick(taskItem); }} className="p-0.5 rounded hover:bg-black/10 text-slate-500">
                              <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                            </button>
                         </div>
                       </div>

                       <div
                         className="resize-handle absolute top-0 left-0 right-0 h-2 cursor-ns-resize hover:bg-black/10 z-20"
                         onMouseDown={(e) => {
                           e.stopPropagation();
                           e.preventDefault();
                           setResizing({ id: event.id, type: 'top', startY: e.clientY, currentY: e.clientY, originalStartMin: startMin, originalEndMin: endMin });
                         }}
                         onTouchStart={(e) => {
                           e.stopPropagation();
                           e.preventDefault();
                           setResizing({ id: event.id, type: 'top', startY: e.touches[0].clientY, currentY: e.touches[0].clientY, originalStartMin: startMin, originalEndMin: endMin });
                         }}
                       />
                       <div
                         className="resize-handle absolute bottom-0 left-0 right-0 h-2 cursor-ns-resize hover:bg-black/10 z-20"
                         onMouseDown={(e) => {
                           e.stopPropagation();
                           e.preventDefault();
                           setResizing({ id: event.id, type: 'bottom', startY: e.clientY, currentY: e.clientY, originalStartMin: startMin, originalEndMin: endMin });
                         }}
                         onTouchStart={(e) => {
                           e.stopPropagation();
                           e.preventDefault();
                           setResizing({ id: event.id, type: 'bottom', startY: e.touches[0].clientY, currentY: e.touches[0].clientY, originalStartMin: startMin, originalEndMin: endMin });
                         }}
                       />
                     </div>
                   );
                 })}
               </div>
             );
          })}

          {dragging && (
             (() => {
               const deltaY = dragging.currentY - dragging.startY;
               const newStartMin = Math.max(0, Math.min(1440 - dragging.duration, dragging.originalStartMin + (deltaY / hourHeight) * 60));

               const snappedStartMin = snapToGrid(newStartMin, step);
               const top = (snappedStartMin / 60) * hourHeight;
               const height = (dragging.duration / 60) * hourHeight;

               let left = 0;
               let width = 0;

               if (containerRef.current) {
                 const rect = containerRef.current.getBoundingClientRect();
                 const timeAxisWidth = 48;
                 const gridWidth = rect.width - timeAxisWidth;
                 const relativeX = dragging.currentX - rect.left - timeAxisWidth + containerRef.current.scrollLeft;
                 const colIndex = getColumnFromX(relativeX, gridWidth, days.length);

                 const colWidth = gridWidth / days.length;
                 left = timeAxisWidth + (colIndex * colWidth);
                 width = colWidth - 8;
               }

               return (
                 <div
                   className="absolute rounded-lg border-2 border-dashed border-blue-500 bg-blue-50/50 p-1 z-50 pointer-events-none"
                   style={{ top, left, width, height }}
                 >
                   <div className="text-[9px] font-bold text-blue-800">
                     {minutesToTime(snappedStartMin)} - {minutesToTime(snappedStartMin + dragging.duration)}
                   </div>
                   <div className="text-[10px] font-bold leading-tight line-clamp-2 opacity-50">{dragging.task.titulo}</div>
                 </div>
               );
             })()
          )}
        </div>
        {sidebar}
      </div>
    </div>
  );
};
