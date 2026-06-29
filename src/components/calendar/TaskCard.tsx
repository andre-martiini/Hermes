import React from 'react';
import { Tarefa } from '../../../types';
import { normalizeAreaName } from '../../utils/strategicAreas';
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
            degradationStyles = isDark ? "bg-amber-900/10 border-amber-800/50 hover:border-amber-700" : "bg-yellow-50 border-amber-200 hover:border-amber-400";
        } else if (degradationCount === 2) {
            degradationStyles = isDark ? "bg-orange-900/10 border-orange-800/50 hover:border-orange-700" : "bg-orange-50 border-orange-300 hover:border-orange-500";
        } else if (degradationCount >= 3) {
            degradationStyles = isDark ? "bg-red-900/10 border-red-800/50 hover:border-red-700 animate-pulse-slow" : "bg-red-50 border-red-400 hover:border-red-600 animate-pulse-slow shadow-[inset_0_0_10px_rgba(239,68,68,0.1)]";
        }
    }

    const areaName = normalizeAreaName(task.area_tematica);
    const areaStyles = degradationStyles || (areaName === 'CLC'
        ? isDark ? 'bg-blue-900/20 border-blue-800/50 text-blue-400 hover:border-blue-700' : 'bg-white border-blue-200 text-blue-700 hover:border-blue-400'
        : areaName === 'ASSISTENCIA' || areaName === 'ASSISTENCIA ESTUDANTIL'
            ? isDark ? 'bg-purple-900/20 border-purple-800/50 text-purple-400 hover:border-purple-700' : 'bg-white border-purple-200 text-purple-700 hover:border-purple-400'
        : areaName === 'SAUDE'
            ? isDark ? 'bg-rose-900/20 border-rose-800/50 text-rose-400 hover:border-rose-700' : 'bg-white border-rose-200 text-rose-700 hover:border-rose-400'
        : areaName === 'FINANCEIRO' || areaName === 'FINANCEIRA' || areaName === 'FINANCAS'
            ? isDark ? 'bg-emerald-900/20 border-emerald-800/50 text-emerald-400 hover:border-emerald-700' : 'bg-white border-emerald-200 text-emerald-700 hover:border-emerald-400'
        : areaName === 'CARREIRA'
            ? isDark ? 'bg-blue-900/20 border-blue-800/50 text-blue-400 hover:border-blue-700' : 'bg-white border-blue-200 text-blue-700 hover:border-blue-400'
        : areaName === 'INTELECTUAL'
            ? isDark ? 'bg-amber-900/20 border-amber-800/50 text-amber-400 hover:border-amber-700' : 'bg-white border-amber-200 text-amber-700 hover:border-amber-400'
        : areaName === 'ESTILO DE VIDA'
            ? isDark ? 'bg-cyan-900/20 border-cyan-800/50 text-cyan-400 hover:border-cyan-700' : 'bg-white border-cyan-200 text-cyan-700 hover:border-cyan-400'
            : isDark ? 'bg-slate-800 border-slate-700 text-slate-300 hover:border-slate-600' : 'bg-white border-[#e5e7eb] dark:border-white/10 text-slate-600 hover:border-slate-400');

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
            className={`group relative p-2 rounded-lg border text-[10px] font-bold cursor-pointer transition-all active:scale-95 ${isMenuOpen ? 'z-50 shadow-xl' : 'z-10 shadow-sm'} pointer-events-auto ${areaStyles} ${className}`}
        >
            <div className="flex justify-between items-start gap-2 mb-1">
                <div className="line-clamp-6 leading-tight flex-1 pr-6 font-semibold">{task.titulo}</div>
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
                        <span className={`shrink-0 text-[7px] font-black uppercase px-1.5 py-0.5 rounded-lg border border-current ${isDark ? 'bg-white/10 text-slate-300' : 'bg-white text-slate-600'}`}>
                            {task.area_tematica.replace('SISTEMA:', '').trim()}
                        </span>
                    )}
                    {dayStr && task.prazo_final && task.prazo_final < dayStr && task.prazo_final !== '-' && task.prazo_final !== '0000-00-00' ? (
                        <span className={`shrink-0 text-[7px] font-black uppercase px-2 py-0.5 rounded-lg border ${isDark ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' : 'bg-rose-600 text-white border-rose-700 shadow-sm'}`}>
                            Atrasado
                        </span>
                    ) : dayStr && task.data_limite && task.data_limite < dayStr && task.data_limite !== '-' && task.data_limite !== '0000-00-00' ? (
                        <span className={`shrink-0 text-[7px] font-black uppercase px-2 py-0.5 rounded-lg border ${isDark ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' : 'bg-amber-500 text-white border-amber-600 shadow-sm'}`}>
                            Reagendar
                        </span>
                    ) : null}
                </div>
                {task.horario_inicio && (
                    <span className={`shrink-0 text-[8px] font-black px-1.5 py-0.5 rounded-lg border font-sans ${isDark ? 'bg-black/20 border-white/5 text-slate-400' : 'bg-slate-950 border-slate-700 text-white'}`}>
                        {task.horario_inicio}
                    </span>
                )}
            </div>
        </div>
    );
};
