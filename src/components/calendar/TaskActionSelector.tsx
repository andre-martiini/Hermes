import React, { useState, useRef, useEffect } from 'react';
import { Tarefa } from '../../../types';

interface TaskActionSelectorProps {
    task: Tarefa;
    isDark: boolean;
    onTaskUpdate: (id: string, updates: Partial<Tarefa>) => void;
    onTaskClick: (t: Tarefa) => void;
    onExecuteTask: (t: Tarefa) => void;
    position?: 'top-right' | 'bottom-right' | 'top-left' | 'static';
    onToggle?: (isOpen: boolean) => void;
}

export const TaskActionSelector: React.FC<TaskActionSelectorProps> = ({
    task,
    isDark,
    onTaskUpdate,
    onTaskClick,
    onExecuteTask,
    position = 'top-right',
    onToggle
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setIsOpen(false);
                if (onToggle) onToggle(false);
                setIsDeleting(false);
            }
        };
        if (isOpen) document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [isOpen, onToggle]);

    const handleAction = (e: React.MouseEvent, type: 'exec' | 'edit' | 'complete' | 'delete') => {
        e.stopPropagation();
        switch (type) {
            case 'exec': onExecuteTask(task); setIsOpen(false); if (onToggle) onToggle(false); break;
            case 'edit': onTaskClick(task); setIsOpen(false); if (onToggle) onToggle(false); break;
            case 'complete':
                onTaskUpdate(task.id, { status: task.status === 'concluído' ? 'em andamento' : 'concluído' });
                setIsOpen(false);
                if (onToggle) onToggle(false);
                break;
            case 'delete':
                if (isDeleting) {
                    onTaskUpdate(task.id, { status: 'excluído' as any });
                    setIsOpen(false);
                    if (onToggle) onToggle(false);
                } else {
                    setIsDeleting(true);
                }
                break;
        }
    };

    const posClasses = {
        'top-right': 'absolute top-1 right-1',
        'bottom-right': 'absolute bottom-1 right-1',
        'top-left': 'absolute top-1 left-1',
        'static': 'relative'
    }[position];

    return (
        <div ref={containerRef} className={`${posClasses} z-50`} onClick={e => e.stopPropagation()}>
            <button
                onClick={() => {
                    const next = !isOpen;
                    setIsOpen(next);
                    if (onToggle) onToggle(next);
                }}
                className={`p-1 rounded-lg transition-all shadow-sm ${isOpen ? 'scale-110 opacity-100' : 'scale-100 opacity-0 group-hover:opacity-100'} ${isDark ? 'bg-slate-700 text-slate-200 hover:bg-slate-600' : 'bg-white text-slate-600 hover:bg-slate-50 border border-slate-100'}`}
            >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                </svg>
            </button>

            {isOpen && (
                <div
                    className={`absolute ${position === 'top-right' ? 'top-8 right-0' : 'bottom-8 right-0'} w-36 rounded-xl shadow-2xl border overflow-hidden animate-in fade-in zoom-in duration-200 ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100'}`}
                >
                    <div className="p-1 flex flex-col">
                        <button onClick={e => handleAction(e, 'exec')} className={`flex items-center gap-2.5 px-3 py-2 text-[10px] font-black uppercase tracking-wider rounded-lg transition-colors ${isDark ? 'text-indigo-400 hover:bg-indigo-900/40 text-left' : 'text-indigo-600 hover:bg-indigo-50 text-left'}`}>
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /></svg>
                            Executar
                        </button>
                        <button onClick={e => handleAction(e, 'edit')} className={`flex items-center gap-2.5 px-3 py-2 text-[10px] font-black uppercase tracking-wider rounded-lg transition-colors ${isDark ? 'text-blue-400 hover:bg-blue-900/40 text-left' : 'text-blue-600 hover:bg-blue-50 text-left'}`}>
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                            Editar
                        </button>
                        <button onClick={e => handleAction(e, 'complete')} className={`flex items-center gap-2.5 px-3 py-2 text-[10px] font-black uppercase tracking-wider rounded-lg transition-colors ${task.status === 'concluído' ? 'text-emerald-500 bg-emerald-50/50' : isDark ? 'text-emerald-400 hover:bg-emerald-900/40 text-left' : 'text-emerald-600 hover:bg-emerald-50 text-left'}`}>
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                            {task.status === 'concluído' ? 'Reabrir' : 'Concluir'}
                        </button>
                        <div className={`h-px my-1 ${isDark ? 'bg-slate-800' : 'bg-slate-100'}`} />
                        <button onClick={e => handleAction(e, 'delete')} className={`flex items-center gap-2.5 px-3 py-2 text-[10px] font-black uppercase tracking-wider rounded-lg transition-all ${isDeleting ? 'bg-rose-500 text-white animate-pulse' : isDark ? 'text-rose-400 hover:bg-rose-900/40 text-left' : 'text-rose-600 hover:bg-rose-50 text-left'}`}>
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                            {isDeleting ? 'Confirmar?' : 'Excluir'}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
