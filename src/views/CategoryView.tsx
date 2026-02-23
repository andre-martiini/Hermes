import React from 'react';
import { Tarefa, formatDate, formatDateLocalISO } from '../../types';
import { normalizeStatus } from '../utils/helpers';

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
