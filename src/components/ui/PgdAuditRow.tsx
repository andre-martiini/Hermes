import React, { useEffect, useState } from 'react';
import { AtividadeRealizada, EntregaInstitucional, PlanoTrabalhoItem, Tarefa, formatDate } from '@/types';

interface PgdAuditRowProps {
  item: PlanoTrabalhoItem;
  entregaEntity?: EntregaInstitucional;
  atividadesRelacionadas: AtividadeRealizada[];
  tarefasRelacionadas: Tarefa[];
  onDrop: (tarefaId: string) => void;
  onUnlinkTarefa: (tarefaId: string, entregaId: string) => void;
  onSelectTask: (t: Tarefa) => void;
  onCreateActivity: (draft: Partial<AtividadeRealizada>) => void;
  onUpdateActivity: (id: string, updates: Partial<AtividadeRealizada>) => void;
  onDeleteActivity: (id: string) => void;
  onGenerateWithAI: () => void;
  onProcessRawText: (rawText: string) => void;
  isGeneratingAI?: boolean;
  isProcessingRawText?: boolean;
}

export const PgdAuditRow = ({
  item,
  entregaEntity,
  atividadesRelacionadas,
  tarefasRelacionadas,
  onDrop,
  onUnlinkTarefa,
  onSelectTask,
  onCreateActivity,
  onUpdateActivity,
  onDeleteActivity,
  onGenerateWithAI,
  onProcessRawText,
  isGeneratingAI,
  isProcessingRawText
}: PgdAuditRowProps) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const entregaId = entregaEntity?.id;
  const [drafts, setDrafts] = useState<Record<string, { descricao_atividade: string; data_inicio: string; data_fim: string; status_atividade: string }>>({});
  const [editingById, setEditingById] = useState<Record<string, boolean>>({});
  const [newRegistro, setNewRegistro] = useState({
    descricao_atividade: '',
    data_inicio: new Date().toLocaleDateString('en-CA'),
    data_fim: new Date().toLocaleDateString('en-CA')
  });
  const [rawTextInput, setRawTextInput] = useState('');
  const linkedActionsCount = tarefasRelacionadas.length;
  const executionRecordsCount = atividadesRelacionadas.length;

  useEffect(() => {
    const next: Record<string, { descricao_atividade: string; data_inicio: string; data_fim: string; status_atividade: string }> = {};
    atividadesRelacionadas.forEach((at) => {
      next[at.id] = {
        descricao_atividade: at.descricao_atividade || '',
        data_inicio: (at.data_inicio || '').split('T')[0] || '',
        data_fim: (at.data_fim || at.data_inicio || '').split('T')[0] || '',
        status_atividade: at.status_atividade || 'rascunho'
      };
    });
    setDrafts(next);
    setEditingById((prev) => {
      const nextEdit: Record<string, boolean> = {};
      atividadesRelacionadas.forEach((at) => {
        nextEdit[at.id] = prev[at.id] ?? false;
      });
      return nextEdit;
    });
  }, [atividadesRelacionadas]);

  const sortedAtividades = [...atividadesRelacionadas].sort((a, b) => {
    const ad = (a.data_inicio || '').split('T')[0];
    const bd = (b.data_inicio || '').split('T')[0];
    return ad.localeCompare(bd);
  });

  const updateDraft = (
    id: string,
    field: 'descricao_atividade' | 'data_inicio' | 'data_fim' | 'status_atividade',
    value: string
  ) => {
    setDrafts(prev => ({
      ...prev,
      [id]: {
        ...(prev[id] || { descricao_atividade: '', data_inicio: '', data_fim: '', status_atividade: 'rascunho' }),
        [field]: value
      }
    }));
  };

  const isDraftDirty = (
    at: AtividadeRealizada,
    draft: { descricao_atividade: string; data_inicio: string; data_fim: string; status_atividade: string }
  ) => {
    const srcDesc = (at.descricao_atividade || '').trim();
    const srcStart = (at.data_inicio || '').split('T')[0] || '';
    const srcEnd = (at.data_fim || at.data_inicio || '').split('T')[0] || '';
    const srcStatus = at.status_atividade || 'rascunho';

    return (
      draft.descricao_atividade.trim() !== srcDesc ||
      draft.data_inicio !== srcStart ||
      draft.data_fim !== srcEnd ||
      draft.status_atividade !== srcStatus
    );
  };

  const resetDraftFromSource = (at: AtividadeRealizada) => {
    setDrafts((prev) => ({
      ...prev,
      [at.id]: {
        descricao_atividade: at.descricao_atividade || '',
        data_inicio: (at.data_inicio || '').split('T')[0] || '',
        data_fim: (at.data_fim || at.data_inicio || '').split('T')[0] || '',
        status_atividade: at.status_atividade || 'rascunho'
      }
    }));
  };

  const formatDateBr = (dateText: string) => {
    const pure = String(dateText || '').split('T')[0];
    const iso = pure.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;

    const parsed = new Date(pure);
    if (!isNaN(parsed.getTime())) return parsed.toLocaleDateString('pt-BR');

    return pure || '--/--/----';
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        e.currentTarget.classList.add('bg-blue-50');
      }}
      onDragLeave={(e) => {
        e.currentTarget.classList.remove('bg-blue-50');
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.currentTarget.classList.remove('bg-blue-50');
        const tarefaId = e.dataTransfer.getData('tarefaId');
        if (tarefaId) onDrop(tarefaId);
      }}
      className="group border-b border-slate-100 hover:bg-slate-50 transition-all p-4 md:p-8 flex flex-col gap-3 md:gap-4"
    >
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-[10px] font-black text-blue-600 uppercase tracking-widest">{item.unidade}</span>
          {entregaEntity?.processo_sei && (
            <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest font-mono border border-slate-200 px-1.5 rounded">
              SEI: {entregaEntity.processo_sei}
            </span>
          )}
        </div>
        <h4 className="text-xl font-black text-slate-900 tracking-tight leading-snug">
          {item.entrega}
        </h4>
        <p className="text-xs font-medium text-slate-500 leading-relaxed mt-1">
          {item.descricao}
        </p>
      </div>

      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-[10px] font-black text-slate-400 uppercase">
            <div className="w-1.5 h-1.5 bg-blue-500 rounded-full"></div>
            {linkedActionsCount} ação(ões) vinculada(s)
          </div>
          <div className="flex items-center gap-2 text-[10px] font-black text-slate-300 uppercase">
            <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full"></div>
            {executionRecordsCount} registro(s) de execução
          </div>
        </div>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="px-4 py-2 bg-white border border-slate-200 text-slate-600 rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-wider hover:bg-slate-50 transition-colors flex items-center gap-2 shadow-sm"
        >
          {isExpanded ? 'Ocultar Detalhes' : 'Ver Detalhes'}
          <svg className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {isExpanded && (
        <div className="mt-4 space-y-4 animate-in slide-in-from-top-2 duration-300">
          <div className="rounded-none md:rounded-2xl border border-slate-200 bg-slate-50/60 p-3 md:p-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div>
                <p className="text-[9px] font-black text-slate-600 uppercase tracking-widest">Registros de execucao PGD</p>
                <p className="text-[11px] text-slate-500">Voce pode gerar via IA, editar, excluir e criar registros manuais.</p>
              </div>
              <button
                onClick={onGenerateWithAI}
                disabled={!entregaId || isGeneratingAI || tarefasRelacionadas.length === 0}
                className="px-3 py-2 rounded-lg bg-slate-900 text-white text-[9px] font-black uppercase tracking-widest disabled:opacity-40"
              >
                {isGeneratingAI ? 'Gerando...' : 'Gerar com IA'}
              </button>
            </div>

            <div className="mt-3 grid grid-cols-1 md:grid-cols-12 gap-2">
              <textarea
                value={newRegistro.descricao_atividade}
                onChange={(e) => setNewRegistro(prev => ({ ...prev, descricao_atividade: e.target.value }))}
                placeholder="Adicionar registro manual (descricao do trabalho executado)"
                className="md:col-span-7 p-2.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-700 outline-none min-h-[44px]"
              />
              <input
                type="date"
                value={newRegistro.data_inicio}
                onChange={(e) => setNewRegistro(prev => ({ ...prev, data_inicio: e.target.value, data_fim: prev.data_fim || e.target.value }))}
                className="md:col-span-2 h-11 px-2 rounded-lg border border-slate-200 bg-white text-[11px] font-bold text-slate-700 outline-none"
              />
              <input
                type="date"
                value={newRegistro.data_fim}
                onChange={(e) => setNewRegistro(prev => ({ ...prev, data_fim: e.target.value }))}
                className="md:col-span-2 h-11 px-2 rounded-lg border border-slate-200 bg-white text-[11px] font-bold text-slate-700 outline-none"
              />
              <div className="md:col-span-1 flex items-start justify-end">
                <button
                  onClick={() => {
                    if (!newRegistro.descricao_atividade.trim()) return;
                    onCreateActivity({
                      descricao_atividade: newRegistro.descricao_atividade.trim(),
                      data_inicio: newRegistro.data_inicio,
                      data_fim: newRegistro.data_fim,
                      status_atividade: 'rascunho',
                      origem: 'manual'
                    });
                    setNewRegistro({
                      descricao_atividade: '',
                      data_inicio: new Date().toLocaleDateString('en-CA'),
                      data_fim: new Date().toLocaleDateString('en-CA')
                    });
                  }}
                  disabled={!entregaId || !newRegistro.descricao_atividade.trim()}
                  className="h-11 w-11 self-start rounded-lg bg-emerald-600 text-white text-[14px] font-black uppercase tracking-widest disabled:opacity-40"
                  title="Adicionar registro"
                >
                  +
                </button>
              </div>
            </div>

            <div className="mt-3 border border-slate-200 bg-white rounded-lg p-2.5 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Processar texto bruto com datas</p>
                <button
                  onClick={() => onProcessRawText(rawTextInput)}
                  disabled={!entregaId || !rawTextInput.trim() || isProcessingRawText}
                  className="px-3 py-2 rounded-lg bg-blue-600 text-white text-[9px] font-black uppercase tracking-widest disabled:opacity-40"
                >
                  {isProcessingRawText ? 'Processando...' : 'Processar texto'}
                </button>
              </div>
              <textarea
                value={rawTextInput}
                onChange={(e) => setRawTextInput(e.target.value)}
                placeholder="Cole aqui o texto bruto com datas (ex.: 02/02/2026 ...)"
                className="w-full p-2.5 rounded-lg border border-slate-200 bg-slate-50 text-xs font-medium text-slate-700 outline-none min-h-[110px]"
              />
            </div>

            <div className="mt-3 space-y-2">
              {sortedAtividades.map((at) => {
                const draft = drafts[at.id] || {
                  descricao_atividade: at.descricao_atividade || '',
                  data_inicio: (at.data_inicio || '').split('T')[0] || '',
                  data_fim: (at.data_fim || at.data_inicio || '').split('T')[0] || '',
                  status_atividade: at.status_atividade || 'rascunho'
                };
                const isEditing = !!editingById[at.id];
                const dirty = isDraftDirty(at, draft);
                const startDate = formatDateBr(draft.data_inicio);
                const endDate = formatDateBr(draft.data_fim || draft.data_inicio);

                if (!isEditing) {
                  return (
                    <div key={at.id} className="p-3 rounded-lg border border-slate-200 bg-white">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className={`text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded ${at.origem === 'ia' ? 'bg-blue-50 text-blue-700' : 'bg-emerald-50 text-emerald-700'}`}>
                            {at.origem === 'ia' ? 'Gerado por IA' : 'Manual'}
                          </span>
                          <span className="text-[8px] font-black uppercase tracking-widest text-emerald-700 bg-emerald-50 px-2 py-1 rounded">
                            Salvo
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => setEditingById((prev) => ({ ...prev, [at.id]: true }))}
                            className="p-1.5 rounded border border-slate-200 text-slate-500 hover:text-blue-700 hover:border-blue-200"
                            title="Editar registro"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.3-7.7a2.1 2.1 0 113 3L12 17l-4 1 1-4 8.7-8.7z" />
                            </svg>
                          </button>
                          <button
                            onClick={() => onDeleteActivity(at.id)}
                            className="p-1.5 rounded border border-rose-200 text-rose-600 hover:bg-rose-50"
                            title="Excluir registro"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M19 7l-.9 12.1a2 2 0 01-2 1.9H7.9a2 2 0 01-2-1.9L5 7m4 4v6m6-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      </div>

                      <p className="mt-2 text-[11px] leading-snug text-slate-700 line-clamp-2">
                        {draft.descricao_atividade}
                      </p>

                      <div className="mt-2 flex items-center gap-1.5 text-[9px] font-bold text-slate-500">
                        <span className="px-2 py-1 rounded border border-slate-200 bg-slate-50">
                          Inicio: {startDate}
                        </span>
                        <svg className="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 12h14m-4-4l4 4-4 4" />
                        </svg>
                        <span className="px-2 py-1 rounded border border-slate-200 bg-slate-50">
                          Termino: {endDate}
                        </span>
                      </div>
                    </div>
                  );
                }

                return (
                  <div key={at.id} className="p-3 rounded-lg border border-slate-200 bg-white">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className={`text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded ${at.origem === 'ia' ? 'bg-blue-50 text-blue-700' : 'bg-emerald-50 text-emerald-700'}`}>
                          {at.origem === 'ia' ? 'Gerado por IA' : 'Manual'}
                        </span>
                        <span className={`text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded ${dirty ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>
                          {dirty ? 'Alteracoes pendentes' : 'Sem alteracoes'}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => {
                            onUpdateActivity(at.id, {
                              descricao_atividade: draft.descricao_atividade.trim(),
                              data_inicio: draft.data_inicio,
                              data_fim: draft.data_fim,
                              status_atividade: draft.status_atividade
                            });
                            setEditingById((prev) => ({ ...prev, [at.id]: false }));
                          }}
                          disabled={!draft.descricao_atividade.trim()}
                          className="px-2 py-1 rounded bg-slate-900 text-white text-[8px] font-black uppercase tracking-widest disabled:opacity-40"
                        >
                          Salvar
                        </button>
                        <button
                          onClick={() => {
                            resetDraftFromSource(at);
                            setEditingById((prev) => ({ ...prev, [at.id]: false }));
                          }}
                          className="px-2 py-1 rounded border border-slate-200 text-slate-500 text-[8px] font-black uppercase tracking-widest"
                        >
                          Fechar
                        </button>
                        <button
                          onClick={() => onDeleteActivity(at.id)}
                          className="px-2 py-1 rounded border border-rose-200 text-rose-600 text-[8px] font-black uppercase tracking-widest"
                        >
                          Excluir
                        </button>
                      </div>
                    </div>
                    <textarea
                      value={draft.descricao_atividade}
                      onChange={(e) => updateDraft(at.id, 'descricao_atividade', e.target.value)}
                      className="w-full p-2 rounded border border-slate-200 bg-slate-50 text-xs font-medium text-slate-700 outline-none min-h-[64px]"
                    />
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <input
                        type="date"
                        value={draft.data_inicio}
                        onChange={(e) => updateDraft(at.id, 'data_inicio', e.target.value)}
                        className="p-2 rounded border border-slate-200 bg-white text-[10px] font-black text-slate-700 outline-none"
                      />
                      <input
                        type="date"
                        value={draft.data_fim}
                        onChange={(e) => updateDraft(at.id, 'data_fim', e.target.value)}
                        className="p-2 rounded border border-slate-200 bg-white text-[10px] font-black text-slate-700 outline-none"
                      />
                    </div>
                  </div>
                );
              })}
              {sortedAtividades.length === 0 && (
                <div className="py-5 text-center bg-white rounded-lg border border-dashed border-slate-200">
                  <p className="text-slate-300 text-[10px] font-black uppercase tracking-widest italic">Nenhum registro de execucao nesta entrega</p>
                </div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {tarefasRelacionadas.map(t => (
              <div
                key={t.id}
                onClick={() => onSelectTask(t)}
                className="p-4 rounded-none md:rounded-2xl bg-blue-50/30 border border-blue-100 shadow-sm hover:border-blue-300 hover:bg-blue-50/50 transition-all cursor-pointer group/task relative pr-10"
              >
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (entregaId) onUnlinkTarefa(t.id, entregaId);
                  }}
                  className="absolute top-3 right-3 p-1.5 text-slate-300 hover:text-rose-500 hover:bg-white rounded-lg opacity-0 group-hover/task:opacity-100 transition-all shadow-sm"
                  title="Desvincular"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-[8px] font-black text-blue-500 uppercase tracking-widest">Acao vinculada</p>
                  <p className="text-[8px] font-black text-slate-400 uppercase tracking-widest">{formatDate(t.data_limite)}</p>
                </div>
                <p className="text-xs font-bold text-slate-800 leading-snug group-hover/task:text-blue-700 transition-colors">{t.titulo}</p>
              </div>
            ))}
            {tarefasRelacionadas.length === 0 && (
              <div className="col-span-full py-8 text-center bg-slate-50/50 rounded-none md:rounded-2xl border-2 border-dashed border-slate-100">
                <p className="text-slate-300 text-[10px] font-black uppercase tracking-widest italic">Nenhuma acao vinculada a esta entrega</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
