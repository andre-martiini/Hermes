import React, { useState } from 'react';
import {
  Sistema, Tarefa, BaseConhecimento, ConhecimentoItem,
  PoolItem, SistemaStatus, WorkItem
} from '../../types';
import { normalizeStatus } from '../utils/helpers';
import { STATUS_COLORS } from '../../constants';

// ─── Types ────────────────────────────────────────────────────────────────────

type Unidade = { id: string; nome: string };

interface EditingResource {
  field: string;
  label: string;
  value: string;
}

interface SistemaExecutionViewProps {
  unit: Unidade;
  sysDetails: Sistema;
  workItems: WorkItem[];
  tarefas: Tarefa[];
  knowledgeBases: BaseConhecimento[];
  knowledgeItems: ConhecimentoItem[];
  onClose: () => void;
  onUpdateSistema: (id: string, updates: Partial<Sistema>) => void;
  onCreateWorkItem: (sistemaId: string, tipo: 'desenvolvimento' | 'ajuste' | 'log' | 'geral', text: string, attachments: PoolItem[]) => void | Promise<void>;
  onUpdateWorkItem: (id: string, updates: Partial<WorkItem>) => void;
  onDeleteWorkItem: (id: string) => void;
  onSyncGithubRepo: (sistemaId: string, repoUrl: string) => void;
  isSyncingGithub: boolean;
  onSelectTask: (task: Tarefa) => void;
  showToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
  handleFileUploadToDrive: (file: File) => Promise<PoolItem | null>;
  isUploading: boolean;
  isDark?: boolean;
}

// ─── Component ────────────────────────────────────────────────────────────────

export const SistemaExecutionView: React.FC<SistemaExecutionViewProps> = ({
  unit,
  sysDetails,
  tarefas,
  knowledgeBases,
  knowledgeItems,
  onClose,
  onUpdateSistema,
  onSyncGithubRepo,
  isSyncingGithub,
  onSelectTask,
  isDark = false,
}) => {
  const systemName = unit.nome.replace('SISTEMA:', '').trim();

  const systemBaseIds = knowledgeBases.filter(b => b.sistema_id === unit.id).map(b => b.id);
  const systemKnowledgeIds = new Set(
    knowledgeItems.filter(item => item.base_id && systemBaseIds.includes(item.base_id)).map(item => item.id)
  );
  const linkedTasks = tarefas.filter(t =>
    (t.base_conhecimento && systemBaseIds.includes(t.base_conhecimento)) ||
    (t.knowledge_item_ids || []).some(id => systemKnowledgeIds.has(id)) ||
    t.sistema === systemName
  );

  const [editingResource, setEditingResource] = useState<EditingResource | null>(null);

  // Formatação de data industrial
  const formatTime = (dateStr?: string) => {
    if (!dateStr) return 'NEVER_SYNCED';
    const date = new Date(dateStr);
    return date.toLocaleString('pt-BR', { 
      day: '2-digit', 
      month: '2-digit', 
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }).replace(',', '');
  };

  return (
    <div className={`fixed inset-0 z-[300] bg-surface flex flex-col font-mono overflow-hidden animate-in fade-in duration-300 ${isDark ? 'dark bg-slate-950 text-white' : 'text-slate-900'}`}>
      {/* Background Industrial (Dot Grid) */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none" style={{ backgroundImage: 'radial-gradient(#000 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>
      
      {/* ═══ HEADER INDUSTRIAL ═══ */}
      <header className="relative z-10 shrink-0 p-6 md:p-8 border-b-4 border-slate-900 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-2 h-10 bg-primary-tactile" />
            <div>
              <h1 className="text-2xl font-black tracking-tighter uppercase leading-none">
                SYS_EXECUTION::{systemName.replace(/\s+/g, '_')}
              </h1>
              <p className="text-[10px] font-bold text-slate-400 mt-1 uppercase tracking-widest">
                Kernel_Version: 2.0.4 // Instance_ID: {unit.id.slice(0, 8)}
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="px-6 py-2 bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest hover:bg-slate-700 transition-all active:scale-95"
          >
            [ ESCAPE_VIEW ]
          </button>
        </div>

        {/* TOP STATS - DENSIDADE MÁXIMA */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border-2 border-slate-900 p-4 flex items-center justify-between bg-slate-50 dark:bg-slate-800">
            <div>
              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Linked_Actions_Count</p>
              <p className="text-3xl font-black text-primary-tactile mt-1">
                {String(linkedTasks.length).padStart(3, '0')}
              </p>
            </div>
            <div className="text-right">
              <span className="text-[8px] font-black px-2 py-1 bg-emerald-100 text-emerald-700 uppercase">Status: OK</span>
            </div>
          </div>

          <div className="border-2 border-slate-900 p-4 bg-slate-900 text-white flex flex-col justify-center">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">DB_Last_Update</p>
              <p className="text-[9px] font-black text-primary-tactile">{formatTime(sysDetails.data_atualizacao)}</p>
            </div>
            <div className="flex items-center justify-between">
              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">RAG_Sync_Timestamp</p>
              <p className="text-[9px] font-black text-emerald-500">{formatTime(sysDetails.github_rag_synced_at)}</p>
            </div>
          </div>
        </div>
      </header>

      {/* ═══ CONTENT AREA ═══ */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8 bg-surface">
        
        {/* RESOURCES SECTION - STACKED */}
        <section className="space-y-4">
          <div className="flex items-center gap-2 border-b-2 border-border-grid pb-2">
            <h2 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">Resource_Nodes</h2>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {[
              { field: 'repositorio_principal', label: 'REPO_ORIGIN', icon: 'M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z' },
              { field: 'link_documentacao', label: 'DOCS_MANUAL', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
              { field: 'link_google_ai_studio', label: 'AI_WORKSPACE', icon: 'M13 10V3L4 14h7v7l9-11h-7z' },
              { field: 'link_hospedado', label: 'DEPLOY_ENDPOINT', icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9' }
            ].map(res => (
              <button
                key={res.field}
                onClick={() => setEditingResource({ field: res.field, label: res.label, value: (sysDetails as any)[res.field] || '' })}
                className="flex items-center justify-between p-4 border-2 border-border-grid bg-white hover:border-slate-900 hover:bg-slate-50 transition-all text-left"
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="p-2 bg-slate-100 border border-border-grid shrink-0">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" dangerouslySetInnerHTML={{ __html: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="${res.icon}" />` }} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">{res.label}</p>
                    <p className="text-[10px] font-bold text-slate-900 truncate">
                      {(sysDetails as any)[res.field] || 'NOT_DEFINED'}
                    </p>
                  </div>
                </div>
                <span className="text-[8px] font-black text-primary-tactile uppercase ml-2">[EDIT]</span>
              </button>
            ))}
          </div>

          {/* SYNC RAG BUTTON - INDUSTRIAL */}
          {sysDetails.repositorio_principal && (
            <button
              onClick={() => onSyncGithubRepo(unit.id, sysDetails.repositorio_principal!)}
              disabled={isSyncingGithub}
              className="w-full flex items-center justify-center gap-4 p-4 border-2 border-dashed border-primary-tactile text-primary-tactile hover:bg-primary-tactile/5 transition-all disabled:opacity-50"
            >
              {isSyncingGithub ? (
                <div className="w-4 h-4 border-2 border-primary-tactile border-t-transparent animate-spin" />
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              )}
              <span className="text-[10px] font-black uppercase tracking-[0.3em]">Force_RAG_Sync_Kernel</span>
            </button>
          )}
        </section>

        {/* LINKED ACTIONS - HIGH DENSITY */}
        <section className="space-y-4">
          <div className="flex items-center justify-between border-b-2 border-border-grid pb-2">
            <h2 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">Active_Operations_Queue</h2>
            <span className="text-[9px] font-black bg-slate-900 text-white px-2 py-0.5">COUNT: {linkedTasks.length}</span>
          </div>
          
          <div className="grid grid-cols-1 gap-2">
            {linkedTasks.length > 0 ? (
              linkedTasks
                .sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime())
                .map(task => (
                  <button
                    key={task.id}
                    onClick={() => onSelectTask(task)}
                    className="flex items-center justify-between p-4 border-2 border-border-grid bg-white hover:border-primary-tactile transition-all text-left group"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-[8px] font-black px-2 py-0.5 border uppercase ${STATUS_COLORS[normalizeStatus(task.status)] || 'border-slate-200 text-slate-500'}`}>
                          {task.status.replace(/\s+/g, '_')}
                        </span>
                        {task.base_conhecimento && (
                          <span className="text-[8px] font-black bg-primary-tactile text-white px-2 py-0.5 uppercase tracking-tighter">RAG_LINK</span>
                        )}
                      </div>
                      <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-tight truncate group-hover:text-primary-tactile transition-colors">
                        {task.titulo}
                      </h3>
                      <p className="text-[8px] font-bold text-slate-400 mt-1 uppercase">
                        Deadline: {task.data_limite ? new Date(task.data_limite).toLocaleDateString('pt-BR') : 'UNSET'} // Created: {new Date(task.data_criacao).toLocaleDateString('pt-BR')}
                      </p>
                    </div>
                    <div className="ml-4 p-2 bg-slate-50 border border-border-grid group-hover:bg-primary-tactile group-hover:text-white transition-all">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </button>
                ))
            ) : (
              <div className="py-12 border-2 border-dashed border-border-grid text-center">
                <p className="text-[10px] font-black text-slate-300 uppercase tracking-widest italic">Empty_Queue_Null_Actions</p>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* ═══ FOOTER DE STATUS ═══ */}
      <footer className="shrink-0 p-4 border-t-4 border-slate-900 bg-slate-50 flex items-center justify-between">
        <p className="text-[8px] font-bold text-slate-400 uppercase tracking-widest">
          Auth: {sysDetails.id} // Mode: PRODUCTION_READ_ONLY
        </p>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[8px] font-black text-slate-900 uppercase">System_Online</span>
        </div>
      </footer>

      {/* ═══ RESOURCE EDIT MODAL ═══ */}
      {editingResource && (
        <div className="fixed inset-0 z-[400] bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in zoom-in-95 duration-200">
          <div className="bg-white w-full max-w-md border-4 border-slate-900 shadow-2xl overflow-hidden">
            <div className="p-6 border-b-2 border-slate-900 bg-slate-50 flex items-center justify-between">
              <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest">Update_Resource::{editingResource.label}</h3>
              <button onClick={() => setEditingResource(null)} className="p-2 hover:bg-slate-200 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Target_URL_Endpoint</label>
                <input
                  type="text"
                  value={editingResource.value}
                  onChange={e => setEditingResource({ ...editingResource, value: e.target.value })}
                  placeholder="https://..."
                  className="w-full bg-slate-50 border-2 border-slate-200 px-5 py-4 text-xs font-black text-slate-900 outline-none focus:border-primary-tactile transition-all"
                  autoFocus
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      onUpdateSistema(unit.id, { [editingResource.field]: editingResource.value });
                      setEditingResource(null);
                    }
                  }}
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setEditingResource(null)}
                  className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-100 transition-all border-2 border-transparent"
                >
                  Cancel_Cmd
                </button>
                <button
                  onClick={() => {
                    onUpdateSistema(unit.id, { [editingResource.field]: editingResource.value });
                    setEditingResource(null);
                  }}
                  className="flex-1 bg-slate-900 text-white py-4 text-[10px] font-black uppercase tracking-widest hover:bg-slate-700 transition-all shadow-lg"
                >
                  Confirm_Update
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
