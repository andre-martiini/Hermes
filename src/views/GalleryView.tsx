import React, { useState, useEffect } from 'react';
import type { Tarefa, GoogleCalendarEvent, Categoria } from '../../types';
import { formatDate } from '../../types';
import { CalendarView } from './CalendarView';
import { RowCard } from '../components/ui/UIComponents';
import { normalizeStatus } from '../utils/helpers';

const getBucketStartDate = (label: string): string => {
  const now = new Date();
  now.setHours(0, 0, 0, 0);

  if (label === 'Hoje') return now.toLocaleDateString('en-CA');

  if (label === 'Amanhã') {
    const d = new Date(now);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  if (label === 'Esta Semana') {
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const d = new Date(tomorrow);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  if (label === 'Este Mês') {
    const endOfWeek = new Date(now);
    endOfWeek.setDate(now.getDate() + (6 - now.getDay()));
    const d = new Date(endOfWeek);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  const meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  const lowerLabel = label.toLowerCase();
  const mesIndex = meses.findIndex(m => lowerLabel.includes(m));
  if (mesIndex >= 0) {
    const anoMatch = lowerLabel.match(/\d{4}/);
    if (anoMatch) {
      const ano = parseInt(anoMatch[0]);
      const d = new Date(ano, mesIndex, 1);
      return d.toLocaleDateString('en-CA');
    }
  }

  if (label === 'Atrasadas') {
    const d = new Date(now);
    d.setDate(d.getDate() - 1);
    return d.toLocaleDateString('en-CA');
  }

  return now.toLocaleDateString('en-CA');
};

interface GalleryViewProps {
  searchTerm: string;
  setSearchTerm: (v: string) => void;
  areaFilter: string;
  setAreaFilter: (v: string) => void;
  unidades: { id: string; nome: string }[];
  dashboardViewMode: 'list' | 'calendar';
  setDashboardViewMode: (v: 'list' | 'calendar') => void;
  calendarViewMode: 'month' | 'week' | 'day';
  setCalendarViewMode: (v: 'month' | 'week' | 'day') => void;
  calendarDate: Date;
  setCalendarDate: (d: Date) => void;
  primaryCalendarEvents: GoogleCalendarEvent[];
  filteredAndSortedTarefas: Tarefa[];
  tarefasAgrupadas: Record<string, Tarefa[]>;
  tarefas: Tarefa[];
  selectedTaskIds: string[];
  setSelectedTaskIds: React.Dispatch<React.SetStateAction<string[]>>;
  isCompletedTasksOpen: boolean;
  setIsCompletedTasksOpen: (v: boolean) => void;
  setSelectedTask: (t: Tarefa | null) => void;
  setTaskModalMode: (m: string) => void;
  handleUpdateTarefa: (id: string, updates: Partial<Tarefa>) => Promise<void> | void;
  handleReorderTasks: (draggedId: string, targetId: string, label: string) => void;
  handleToggleTarefaStatus: (id: string, currentStatus: string) => void;
  handleDeleteTarefa: (id: string) => void;
  handleUpdateToToday: (task: Tarefa) => void;
  handleBatchTag: (categoria: Categoria) => void;
  showToast: (msg: string, type: string) => void;
}

export function GalleryView({
  searchTerm,
  setSearchTerm,
  areaFilter,
  setAreaFilter,
  unidades,
  dashboardViewMode,
  setDashboardViewMode,
  calendarViewMode,
  setCalendarViewMode,
  calendarDate,
  setCalendarDate,
  primaryCalendarEvents,
  filteredAndSortedTarefas,
  tarefasAgrupadas,
  tarefas,
  selectedTaskIds,
  setSelectedTaskIds,
  isCompletedTasksOpen,
  setIsCompletedTasksOpen,
  setSelectedTask,
  setTaskModalMode,
  handleUpdateTarefa,
  handleReorderTasks,
  handleToggleTarefaStatus,
  handleDeleteTarefa,
  handleUpdateToToday,
  handleBatchTag,
  showToast,
}: GalleryViewProps) {
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [hasAutoExpanded, setHasAutoExpanded] = useState(false);

  useEffect(() => {
    if (!hasAutoExpanded && Object.keys(tarefasAgrupadas).length > 0) {
      const keys = Object.keys(tarefasAgrupadas);
      let sectionsToExpand: string[] = [];
      if (keys.includes('Atrasadas')) sectionsToExpand.push('Atrasadas');
      if (keys.includes('Hoje')) sectionsToExpand.push('Hoje');
      if (sectionsToExpand.length === 0) {
        const fallback = keys.find(k => k !== 'Ações em Stand-by' && k !== 'Concluídas');
        if (fallback) sectionsToExpand = [fallback];
      }
      setExpandedSections(sectionsToExpand);
      setHasAutoExpanded(true);
    }
  }, [tarefasAgrupadas, hasAutoExpanded]);

  const toggleSection = (label: string) => {
    setExpandedSections(prev =>
      prev.includes(label) ? prev.filter(s => s !== label) : [...prev, label]
    );
  };

  return (
    <>
      {/* Mobile Search Bar */}
      <div className="lg:hidden px-4 mb-6">
        <div className="flex items-center bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm focus-within:ring-2 focus-within:ring-blue-500 transition-all">
          <svg className="w-5 h-5 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
          <input
            type="text"
            placeholder="Pesquisar ações..."
            className="bg-transparent border-none outline-none text-sm font-bold text-slate-900 w-full placeholder:text-slate-400"
            value={searchTerm === 'filter:unclassified' ? '' : searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          {searchTerm && searchTerm !== 'filter:unclassified' && (
            <button onClick={() => setSearchTerm('')} className="ml-2 text-slate-400 hover:text-slate-600">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-col md:flex-row items-center justify-between mb-8 gap-4 px-4 md:px-0">
        <div className="flex items-center justify-between w-full gap-2">
          <div className="relative group flex-shrink-1 min-w-0 max-w-[140px] md:max-w-none md:min-w-[180px]">
            <select
              value={areaFilter}
              onChange={(e) => setAreaFilter(e.target.value)}
              className="h-11 w-full appearance-none bg-white pl-3 md:pl-4 pr-8 md:pr-10 rounded-xl border border-slate-200 text-[10px] font-black uppercase tracking-tight md:tracking-widest text-slate-700 outline-none focus:ring-2 focus:ring-slate-900 shadow-sm hover:border-slate-300 transition-all cursor-pointer truncate"
            >
              <option value="TODAS">TODAS</option>
              <option value="CLC">CLC</option>
              <option value="ASSISTÊNCIA">ASSISTÊNCIA</option>
              <option value="GERAL">GERAL</option>
              <option value="NÃO CLASSIFICADA">PENDENTES</option>
              {unidades.filter(u => !['CLC', 'ASSISTÊNCIA', 'ASSISTÊNCIA ESTUDANTIL'].includes(u.nome.toUpperCase())).map(u => (
                <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
              ))}
            </select>
            <div className="absolute inset-y-0 right-0 flex items-center px-2 md:px-3 pointer-events-none text-slate-400">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
            </div>
          </div>

          <div className="flex items-center gap-1 md:gap-2 flex-shrink-0">
            {searchTerm !== 'filter:unclassified' && (
              <div className="h-11 bg-slate-100 p-1 rounded-xl shadow-inner inline-flex border border-slate-200">
                <button
                  onClick={() => setDashboardViewMode('list')}
                  className={`px-2 md:px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${dashboardViewMode === 'list' ? 'bg-white shadow-md text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
                  <span className="hidden lg:inline">Lista</span>
                </button>
                <button
                  onClick={() => setDashboardViewMode('calendar')}
                  className={`px-2 md:px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${dashboardViewMode === 'calendar' ? 'bg-white shadow-md text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2-2v12a2 2 0 002 2z" /></svg>
                  <span className="hidden lg:inline">Calendário</span>
                </button>
              </div>
            )}

            <button
              onClick={() => {
                setDashboardViewMode('calendar');
                setCalendarViewMode('day');
                setCalendarDate(new Date());
              }}
              className="h-11 bg-slate-900 text-white px-3 md:px-6 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center justify-center gap-2 active:scale-95"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              <span className="hidden sm:inline">Organizar</span>
            </button>
          </div>
        </div>
      </div>

      {dashboardViewMode === 'calendar' ? (
        <CalendarView
          tasks={filteredAndSortedTarefas}
          googleEvents={primaryCalendarEvents}
          viewMode={calendarViewMode}
          currentDate={calendarDate}
          onDateChange={setCalendarDate}
          onTaskClick={setSelectedTask}
          onViewModeChange={setCalendarViewMode}
          onTaskUpdate={handleUpdateTarefa}
          onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
          onReorderTasks={handleReorderTasks}
          showToast={showToast}
        />
      ) : (
        <>
          {searchTerm === 'filter:unclassified' ? (
            <div className="animate-in bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl">
              <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h3 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                  <span className="w-2 h-8 bg-rose-600 rounded-full"></span>
                  Organização Rápida
                </h3>

                {selectedTaskIds.length > 0 && (
                  <div className="flex items-center gap-2 bg-slate-900 p-2 rounded-none md:rounded-2xl animate-in slide-in-from-top-4">
                    <span className="text-[9px] font-black text-white uppercase tracking-widest px-4">Classificar ({selectedTaskIds.length}):</span>
                    <button onClick={() => handleBatchTag('CLC')} className="bg-blue-600 hover:bg-blue-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">CLC</button>
                    <button onClick={() => handleBatchTag('ASSISTÊNCIA')} className="bg-emerald-600 hover:bg-emerald-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">Assistência</button>
                    <button onClick={() => handleBatchTag('GERAL')} className="bg-slate-500 hover:bg-slate-600 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">Geral</button>
                  </div>
                )}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left hidden md:table">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="px-8 py-4 w-12 text-center text-[10px] font-black text-slate-400 uppercase tracking-widest italic">#</th>
                      <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Descrição da Tarefa</th>
                      <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-40 text-center">Data Limite</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {filteredAndSortedTarefas.map((task) => (
                      <tr
                        key={task.id}
                        onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                        className={`hover:bg-slate-50 transition-colors cursor-pointer ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}
                      >
                        <td className="px-8 py-4 text-center">
                          <input
                            type="checkbox"
                            checked={selectedTaskIds.includes(task.id)}
                            onChange={(e) => {
                              e.stopPropagation();
                              setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id]);
                            }}
                            className="w-5 h-5 rounded-lg border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
                          />
                        </td>
                        <td className="px-8 py-4">
                          <div className="flex items-center gap-2 flex-wrap">
                            <div className="text-[13px] font-bold text-slate-800 hover:text-blue-600 transition-colors leading-snug">
                              {task.titulo}
                            </div>
                            {task.sync_status === 'new' && (
                              <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse">Novo</span>
                            )}
                            {task.sync_status === 'updated' && (
                              <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">Atualizada</span>
                            )}
                          </div>
                        </td>
                        <td className="px-8 py-4 text-center text-[10px] font-black text-slate-400 uppercase">
                          {formatDate(task.data_limite)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="md:hidden divide-y divide-slate-50">
                  {filteredAndSortedTarefas.map((task) => (
                    <div
                      key={task.id}
                      onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                      className={`p-6 space-y-4 hover:bg-slate-50 transition-colors cursor-pointer ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}
                    >
                      <div className="flex items-start gap-4">
                        <input
                          type="checkbox"
                          checked={selectedTaskIds.includes(task.id)}
                          onChange={(e) => {
                            e.stopPropagation();
                            setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id]);
                          }}
                          className="w-6 h-6 rounded-lg border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer shrink-0 mt-1"
                        />
                        <div className="flex-1 space-y-2">
                          <div className="text-sm font-bold text-slate-800 leading-snug">{task.titulo}</div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest bg-slate-100 px-2 py-0.5 rounded">
                              {formatDate(task.data_limite)}
                            </div>
                            {task.sync_status === 'new' && (
                              <span className="text-[7px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse">Novo</span>
                            )}
                            {task.sync_status === 'updated' && (
                              <span className="text-[7px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">Atualizada</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {filteredAndSortedTarefas.length === 0 && (
                  <div className="py-20 text-center text-slate-300 font-black uppercase tracking-widest italic border-t border-slate-50">
                    Tudo classificado! Bom trabalho.
                  </div>
                )}
              </div>
            </div>

          ) : (
            <div className="animate-in border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl bg-white">
              {Object.keys(tarefasAgrupadas).length > 0 ? (
                Object.entries(tarefasAgrupadas).map(([label, tasks]: [string, Tarefa[]]) => (
                  <div
                    key={label}
                    className="border-b last:border-b-0 border-slate-200 transition-colors"
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
                    }}
                    onDragLeave={(e) => {
                      e.currentTarget.style.backgroundColor = '';
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.currentTarget.style.backgroundColor = '';
                      const taskId = e.dataTransfer.getData('task-id');
                      if (taskId) {
                        if (label === 'Ações em Stand-by') {
                          handleUpdateTarefa(taskId, { status: 'stand-by' as any });
                          return;
                        }
                        const date = getBucketStartDate(label);
                        if (date) handleUpdateTarefa(taskId, { data_limite: date });
                      }
                    }}
                  >
                    <button
                      onClick={() => toggleSection(label)}
                      className="w-full px-6 py-3 bg-transparent border-b border-slate-100 flex items-center justify-between hover:bg-slate-50 transition-colors group"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-black text-slate-400 uppercase tracking-[0.2em]">{label}</span>
                        <span className="text-[10px] font-bold text-slate-300">({tasks.length})</span>
                      </div>
                      <svg className={`w-4 h-4 text-slate-300 transition-transform duration-300 ${expandedSections.includes(label) ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>

                    {expandedSections.includes(label) && (
                      <div className="animate-in origin-top">
                        {tasks.map(task => (
                          <div
                            key={task.id}
                            draggable
                            onDragStart={(e) => {
                              e.dataTransfer.setData('task-id', task.id);
                              e.currentTarget.style.opacity = '0.5';
                            }}
                            onDragEnd={(e) => {
                              e.currentTarget.style.opacity = '1';
                            }}
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              const draggedId = e.dataTransfer.getData('task-id');
                              if (draggedId && draggedId !== task.id) {
                                handleReorderTasks(draggedId, task.id, label);
                              }
                            }}
                          >
                            <RowCard
                              task={task}
                              highlighted={label === 'Hoje' && tasks.filter(t => normalizeStatus(t.status) !== 'concluido')[0]?.id === task.id}
                              onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                              onToggle={handleToggleTarefaStatus}
                              onDelete={handleDeleteTarefa}
                              onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                              onUpdateToToday={handleUpdateToToday}
                              onUpdateTask={handleUpdateTarefa}
                            />
                          </div>
                        ))}
                        {tasks.length === 0 && (
                          <div className="p-8 text-center border-t border-slate-50 bg-slate-50/30">
                            <p className="text-[10px] font-black text-slate-300 uppercase tracking-widest italic">
                              {label === 'Ações em Stand-by' ? 'Arraste ações aqui para pausar' : 'Nenhuma ação nesta seção'}
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <div className="py-24 text-center bg-white">
                  <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Sem demandas encontradas</p>
                </div>
              )}
            </div>
          )}

          <div className="mt-12 space-y-6">
            <button
              onClick={() => setIsCompletedTasksOpen(!isCompletedTasksOpen)}
              className="w-full flex items-center gap-4 group cursor-pointer"
            >
              <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
              <div className="flex items-center gap-2 text-slate-400 group-hover:text-slate-600 transition-colors">
                <h3 className="text-[10px] font-black uppercase tracking-[0.3em]">Concluídas Recentemente</h3>
                <svg className={`w-4 h-4 transition-transform duration-300 ${isCompletedTasksOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                </svg>
              </div>
              <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
            </button>

            {isCompletedTasksOpen && (
              <div className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-sm opacity-60 hover:opacity-100 transition-opacity animate-in slide-in-from-top-4 duration-300">
                {tarefas.filter(t => normalizeStatus(t.status) === 'concluido' && t.status !== 'excluído' as any).length > 0 ? (
                  tarefas
                    .filter(t => normalizeStatus(t.status) === 'concluido' && t.status !== 'excluído' as any)
                    .sort((a, b) => (b.data_conclusao || '').localeCompare(a.data_conclusao || ''))
                    .slice(0, 10)
                    .map(t => (
                      <RowCard
                        key={t.id}
                        task={t}
                        onClick={() => { setSelectedTask(t); setTaskModalMode('execute'); }}
                        onToggle={handleToggleTarefaStatus}
                        onDelete={handleDeleteTarefa}
                        onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                        onUpdateToToday={handleUpdateToToday}
                      />
                    ))
                ) : (
                  <div className="py-12 text-center">
                    <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhuma tarefa concluída</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
