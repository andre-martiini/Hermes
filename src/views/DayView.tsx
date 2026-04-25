import React, { useState, useMemo } from 'react';
import { Tarefa, GoogleCalendarEvent, formatDateLocalISO } from '../../types';
import { normalizeStatus, isStandbyStatus } from '../utils/helpers';
import { TimeGrid } from '../components/calendar/TimeGrid';
import { TaskCard } from '../components/calendar/TaskCard';
import { addDoc, collection } from 'firebase/firestore';
import { db } from '../../firebase';

export const DayView = ({
  tasks,
  googleEvents = [],
  currentDate,
  onTaskClick,
  onTaskUpdate,
  onExecuteTask,
  onReorderTasks,
  showToast,
  isDark,
  hourHeight,
  showStandby,
  showPrevious,
  disableExecuteOnClick
}: {
  tasks: Tarefa[],
  googleEvents?: GoogleCalendarEvent[],
  currentDate: Date,
  onTaskClick: (t: Tarefa) => void,
  onTaskUpdate: (id: string, updates: Partial<Tarefa>, suppressToast?: boolean) => void,
  onExecuteTask: (t: Tarefa) => void,
  onReorderTasks?: (taskId: string, targetTaskId: string, label?: string) => void,
  showToast?: (message: string, type: 'success' | 'error' | 'info') => void,
  isDark?: boolean,
  hourHeight?: number,
  showStandby?: boolean,
  showPrevious?: boolean,
  disableExecuteOnClick?: boolean
}) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const dayStr = formatDateLocalISO(currentDate);

  const dayTasks = useMemo(() => {
    return tasks.filter(t => {
      if ((t.status as any) === 'excluído') return false;

      const isConcluido = normalizeStatus(t.status) === 'concluido';
      if (isConcluido) return false;

      // Novo critério: Standby = Status de standby OU data_limite vazia
      const noDate = !t.data_limite || t.data_limite === '-' || t.data_limite === '0000-00-00';
      const isStandBy = isStandbyStatus(t.status) || noDate;

      // Se o botão de standby estiver desligado, oculta tudo que se encaixa no critério acima
      if (isStandBy && !showStandby) return false;

      const scheduledDate = t.data_limite || t.data_inicio;

      // Se não quiser ver atrasadas (dia anterior)
      if (!showPrevious && scheduledDate && scheduledDate < dayStr && scheduledDate !== '-' && scheduledDate !== '0000-00-00') {
        return false;
      }

      if (t.horario_inicio && scheduledDate) return false;

      const end = t.data_limite || t.data_inicio;
      const hasDeadline = end && end !== '-' && end !== '0000-00-00';
      if (!hasDeadline) return true;
      return dayStr >= end;
    }).sort((a, b) => (a.ordem || 0) - (b.ordem || 0));
  }, [tasks, dayStr, showStandby, showPrevious]);

  const handleCreateTarefa = async (titulo: string) => {
    try {
      await addDoc(collection(db, 'tarefas'), {
        titulo,
        status: 'pendente',
        data_criacao: new Date().toISOString(),
        data_limite: dayStr,
        ordem: dayTasks.length
      });
      if (showToast) showToast('Ação criada com sucesso!', 'success');
    } catch (error) {
      console.error('Erro ao criar ação:', error);
      if (showToast) showToast('Erro ao criar ação', 'error');
    }
  };

  const sidebar = (
    <div className={`w-full md:w-80 h-full flex flex-col border-r ${isDark ? 'bg-[#020817] border-slate-800' : 'bg-white border-slate-200'}`}>
      <div className="p-6 border-b border-slate-100 flex items-center justify-between">
        <h3 className={`text-xs font-black uppercase tracking-widest ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Ações Disponíveis</h3>
        <button
          onClick={() => {
            const titulo = prompt('Título da nova ação:');
            if (titulo) handleCreateTarefa(titulo);
          }}
          className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-all active:scale-95 shadow-lg shadow-blue-500/20"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
        {dayTasks.map(taskItem => (
          <TaskCard
            key={taskItem.id}
            task={taskItem}
            isDark={isDark}
            onTaskClick={onTaskClick}
            onTaskUpdate={(id, updates) => onTaskUpdate(id, updates)}
            onExecuteTask={onExecuteTask}
            dayStr={dayStr}
            onDrop={(e: React.DragEvent) => {
              const draggedId = e.dataTransfer.getData('task-id');
              if (draggedId && draggedId !== taskItem.id) {
                onReorderTasks?.(draggedId, taskItem.id);
              }
            }}
            onDragOver={(e: React.DragEvent) => {
              e.preventDefault();
              (e.currentTarget as HTMLElement).style.backgroundColor = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.02)';
            }}
          />
        ))}

        {dayTasks.length === 0 && (
          <div className={`py-12 text-center border-2 border-dashed rounded-[2rem] ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
            <p className={`${isDark ? 'text-slate-700' : 'text-slate-300'} text-[10px] font-black uppercase italic`}>Tudo alocado</p>
          </div>
        )}
      </div>

      <p className="md:hidden mt-6 text-[8px] font-black text-blue-600 uppercase tracking-widest text-center">Toque para alocar agora</p>
    </div>
  );

  return (
    <div className={`flex flex-col h-[600px] overflow-hidden border-t relative ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-50 border-slate-100'}`}>
      <TimeGrid
        days={[currentDate]}
        tasks={tasks}
        googleEvents={googleEvents}
        onTaskClick={onTaskClick}
        onTaskUpdate={onTaskUpdate}
        onExecuteTask={onExecuteTask}
        onReorderTasks={onReorderTasks}
        showToast={showToast}
        isDark={isDark}
        sidebar={sidebar}
        hourHeight={hourHeight}
        showStandby={showStandby}
        disableExecuteOnClick={disableExecuteOnClick}
      />
    </div>
  );
};
