import React from 'react';
import { Tarefa } from '../../../types';
import { TaskActionSelector } from './TaskActionSelector';

interface TaskCardProps {
    task: Tarefa;
    isDark?: boolean;
    onTaskClick: (t: Tarefa) => void;
    onTaskUpdate: (id: string, updates: Partial<Tarefa>) => void;
    onExecuteTask: (t: Tarefa) => void;
    dayStr?: string;
    className?: string;
    onDragOver?: (e: React.DragEvent) => void;
    onDrop?: (e: React.DragEvent) => void;
    showDegradation?: boolean;
    customClick?: (t: Tarefa) => void;
}

export const TaskCard: React.FC<TaskCardProps> = ({
    task,
    isDark,
    onTaskClick,
    onTaskUpdate,
    onExecuteTask,
    className = "",
    onDragOver,
    onDrop,
    showDegradation = false,
    customClick,
    dayStr
}) => {
    const degradationCount = task.degradation_count || 0;
    let degradationStyles = "";
    if (showDegradation) {
        if (degradationCount === 1) {
            degradationStyles = isDark ? "bg-amber-900/10 border-amber-800/50 hover:border-amber-700" : "bg-yellow-50 border-yellow-200 hover:border-yellow-300";
        } else if (degradationCount === 2) {
            degradationStyles = isDark ? "bg-orange-900/10 border-orange-800/50 hover:border-orange-700" : "bg-orange-50 border-orange-300 hover:border-orange-400";
        } else if (degradationCount >= 3) {
            degradationStyles = isDark ? "bg-red-900/10 border-red-800/50 hover:border-red-700 animate-pulse-slow" : "bg-red-50 border-red-400 hover:border-red-500 animate-pulse-slow";
        }
    }

    const areaStyles = degradationStyles || (task.area_tematica === 'CLC'
        ? isDark ? 'bg-blue-900/20 border-blue-800/50 text-blue-400 hover:border-blue-700' : 'bg-blue-50 border-blue-100 text-blue-700 hover:border-blue-300'
        : task.area_tematica === 'ASSISTÊNCIA' || task.area_tematica === 'ASSISTÊNCIA ESTUDANTIL'
            ? isDark ? 'bg-purple-900/20 border-purple-800/50 text-purple-400 hover:border-purple-700' : 'bg-purple-50 border-purple-100 text-purple-700 hover:border-purple-300'
        : task.area_tematica === 'SAÚDE' || task.area_tematica === 'SAUDE'
            ? isDark ? 'bg-rose-900/20 border-rose-800/50 text-rose-400 hover:border-rose-700' : 'bg-rose-50 border-rose-100 text-rose-700 hover:border-rose-300'
        : task.area_tematica === 'FINANCEIRO' || task.area_tematica === 'FINANCEIRA'
            ? isDark ? 'bg-emerald-900/20 border-emerald-800/50 text-emerald-400 hover:border-emerald-700' : 'bg-emerald-50 border-emerald-100 text-emerald-700 hover:border-emerald-300'
            : isDark ? 'bg-slate-800 border-slate-700 text-slate-300 hover:border-slate-600' : 'bg-slate-50 border-slate-100 text-slate-600 hover:border-slate-300');

    const [isMenuOpen, setIsMenuOpen] = React.useState(false);

    const handleCardClick = (e: React.MouseEvent) => {
        if (customClick) {
            customClick(task);
            return;
        }
        onExecuteTask(task);
    };

    return (
        <div
            onClick={handleCardClick}
            draggable
            onDragStart={(e) => {
                e.dataTransfer.setData('task-id', task.id);
                e.dataTransfer.effectAllowed = 'move';
            }}
            onDragOver={onDragOver}
            onDrop={onDrop}
            className={`group relative p-2 rounded-xl border text-[10px] font-bold cursor-pointer transition-all active:scale-95 ${isMenuOpen ? 'z-50 shadow-xl' : 'z-10 shadow-sm'} pointer-events-auto ${areaStyles} ${className}`}
        >
            <div className="flex justify-between items-start gap-2 mb-1">
                <div className="line-clamp-6 leading-tight flex-1 pr-6">{task.titulo}</div>
                <TaskActionSelector
                    task={task}
                    isDark={!!isDark}
                    onTaskUpdate={onTaskUpdate}
                    onTaskClick={onTaskClick}
                    onExecuteTask={onExecuteTask}
                    onToggle={setIsMenuOpen}
                />
            </div>

            <div className="flex items-center justify-between mt-1">
                <div className="flex items-center gap-1.5 overflow-hidden">
                    {task.area_tematica && (
                        <span className={`shrink-0 text-[7px] font-black uppercase px-1.5 py-0.5 rounded-sm ${isDark ? 'bg-white/10 text-slate-300' : 'bg-black/5 text-slate-600'}`}>
                            {task.area_tematica}
                        </span>
                    )}
                    {task.projeto && !task.projeto.toUpperCase().includes('GOOGLE') && (
                        <span className="text-[7px] font-black uppercase tracking-widest opacity-60 truncate">{task.projeto}</span>
                    )}
                    {dayStr && task.data_limite && task.data_limite < dayStr && task.data_limite !== '-' && task.data_limite !== '0000-00-00' && (
                        <span className={`shrink-0 text-[7px] font-black uppercase px-2 py-0.5 rounded-full ${isDark ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-rose-50 text-rose-600 border border-rose-100'}`}>
                            Dia Anterior
                        </span>
                    )}
                </div>
                {task.horario_inicio && (
                    <span className={`shrink-0 text-[8px] font-black px-1.5 py-0.5 rounded border ${isDark ? 'bg-black/20 border-white/5 text-slate-400' : 'bg-white/50 border-black/5 text-slate-600'}`}>
                        {task.horario_inicio}
                    </span>
                )}
            </div>
        </div>
    );
};
