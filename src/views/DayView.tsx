
import React, { useState, useMemo } from 'react';
import { Tarefa, GoogleCalendarEvent, formatDateLocalISO } from '../../types';
import { normalizeStatus } from '../utils/helpers';
import { TimeGrid } from '../components/calendar/TimeGrid';
import { PROJECT_COLORS } from '../../constants';
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
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const dayStr = formatDateLocalISO(currentDate);

  const dayTasks = useMemo(() => tasks.filter(t => {
    if ((t.status as any) === 'excluído') return false;
    // Filter logic handled by TimeGrid for display, but here for sidebar?
    // Sidebar needs "Unallocated" tasks.

    // Logic from original DayView:
    const isConcluido = normalizeStatus(t.status) === 'concluido';
    if (t.horario_inicio && t.data_inicio) {
       // Allocated. Don't show in sidebar unless filtering logic allows duplicates?
       // Original DayView filtered out allocated tasks from sidebar.
       return false;
    }
    const end = t.data_limite;
    const hasDeadline = end && end !== '-' && end !== '0000-00-00';
    if (!hasDeadline) return true; // Show in sidebar
    if (isConcluido && end < dayStr) return false;
    return dayStr >= end; // Show overdue or today's unallocated
  }).sort((a, b) => (a.ordem || 0) - (b.ordem || 0)), [tasks, dayStr]);

  const handleTaskCreate = async (task: Partial<Tarefa>) => {
    try {
      await addDoc(collection(db, 'tarefas'), {
        ...task,
        titulo: 'Nova Tarefa',
        status: 'em andamento',
        prioridade: 'média',
        categoria: 'GERAL',
        projeto: 'GERAL',
        contabilizar_meta: true,
        data_criacao: new Date().toISOString()
      });
      if (showToast) showToast("Tarefa criada!", "success");
    } catch (e) {
      console.error(e);
      if (showToast) showToast("Erro ao criar tarefa.", "error");
    }
  };

  const Sidebar = (
    <div
      id="unallocated-sidebar"
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
        {dayTasks.map(taskItem => (
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
            <div className="flex items-center gap-2 mb-3">
              <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase ${PROJECT_COLORS[taskItem.projeto] || 'bg-slate-100 text-slate-600'}`}>{taskItem.projeto}</span>
              {(!taskItem.data_limite || taskItem.data_limite === '-' || taskItem.data_limite === '0000-00-00') && (
                <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-amber-100 text-amber-700">Sem Prazo</span>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-2 mt-2">
              <button
                onClick={(e) => { e.stopPropagation(); onTaskClick(taskItem); }}
                className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                title="Editar"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onTaskUpdate(taskItem.id, { status: 'concluído', data_conclusao: new Date().toISOString() }); }}
                className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors"
                title="Concluir"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); if(confirm('Excluir esta tarefa?')) onTaskUpdate(taskItem.id, { status: 'excluído' as any }); }}
                className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                title="Excluir"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
              </button>
            </div>
            <p className="md:hidden mt-3 text-[8px] font-black text-blue-600 uppercase tracking-widest">Toque para alocar agora</p>
          </div>
        ))}
        {dayTasks.length === 0 && (
          <div className="py-12 text-center border-2 border-dashed border-slate-200 rounded-none md:rounded-[2rem]">
            <p className="text-slate-300 text-[10px] font-black uppercase italic">Tudo alocado</p>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-[600px] overflow-hidden bg-slate-50 border-t border-slate-100 relative">
      <TimeGrid
        days={[currentDate]}
        tasks={tasks}
        googleEvents={googleEvents}
        onTaskClick={onTaskClick}
        onTaskUpdate={onTaskUpdate}
        onExecuteTask={onExecuteTask}
        onTaskCreate={handleTaskCreate}
        sidebar={Sidebar}
        showToast={showToast}
      />
      <button
          onClick={() => setIsSidebarOpen(true)}
          className="md:hidden fixed bottom-24 right-6 z-[60] w-14 h-14 bg-blue-600 text-white rounded-full shadow-2xl flex items-center justify-center animate-bounce"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 6v6m0 0v6m0-6h6m-6 0H6" /></svg>
        </button>
    </div>
  );
};
