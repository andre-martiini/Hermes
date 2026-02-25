import React, { useState } from 'react';
import {
  Sistema, SistemaStatus, WorkItem, PoolItem, formatDate, formatDateLocalISO
} from '../types';
import { WysiwygEditor, AutoExpandingTextarea } from '../components/ui/UIComponents';

interface SistemasDevViewProps {
  unidades: { id: string, nome: string }[];
  sistemasDetalhes: Sistema[];
  workItems: WorkItem[];
  selectedSystemId: string | null;
  setSelectedSystemId: (id: string | null) => void;
  newLogText: string;
  setNewLogText: (text: string) => void;
  newLogTipo: 'desenvolvimento' | 'ajuste' | 'geral';
  setNewLogTipo: (t: 'desenvolvimento' | 'ajuste' | 'geral') => void;
  newLogAttachments: PoolItem[];
  setNewLogAttachments: React.Dispatch<React.SetStateAction<PoolItem[]>>;
  isRecordingLog: boolean;
  isProcessingLog: boolean;
  startLogRecording: () => void;
  stopLogRecording: () => void;
  isUploading: boolean;
  handleFileUploadToDrive: (file: File) => Promise<PoolItem | null>;
  handleCreateWorkItem: (sysId: string, tipo: 'desenvolvimento' | 'ajuste' | 'geral' | 'ideia' | 'log', desc: string, pool?: PoolItem[]) => void;
  handleUpdateWorkItem: (id: string, updates: Partial<WorkItem>) => void;
  handleDeleteWorkItem: (id: string) => void;
  handleUpdateSistema: (id: string, updates: Partial<Sistema>) => void;
  setIsSettingsModalOpen: (open: boolean) => void;
}

export const SistemasDevView: React.FC<SistemasDevViewProps> = ({
  unidades,
  sistemasDetalhes,
  workItems,
  selectedSystemId,
  setSelectedSystemId,
  newLogText,
  setNewLogText,
  newLogTipo,
  setNewLogTipo,
  newLogAttachments,
  setNewLogAttachments,
  isRecordingLog,
  isProcessingLog,
  startLogRecording,
  stopLogRecording,
  isUploading,
  handleFileUploadToDrive,
  handleCreateWorkItem,
  handleUpdateWorkItem,
  handleDeleteWorkItem,
  handleUpdateSistema,
  setIsSettingsModalOpen
}) => {
  const [editingResource, setEditingResource] = useState<{ field: string, label: string, value: string } | null>(null);
  const [editingWorkItem, setEditingWorkItem] = useState<WorkItem | null>(null);
  const [editingWorkItemText, setEditingWorkItemText] = useState('');
  const [editingWorkItemAttachments, setEditingWorkItemAttachments] = useState<PoolItem[]>([]);
  const [confirmDeleteLogId, setConfirmDeleteLogId] = useState<string | null>(null);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [isCompletedLogsOpen, setIsCompletedLogsOpen] = useState(false);
  const [isModalCompletedLogsOpen, setIsModalCompletedLogsOpen] = useState(false);

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      {!selectedSystemId ? (
        /* VISÃO GERAL - LISTA DE SISTEMAS */
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-8 p-3 md:p-0 pt-8">
            {unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(unit => {
              const sysDetails = sistemasDetalhes.find(s => s.id === unit.id) || {
                id: unit.id,
                nome: unit.nome.replace('SISTEMA:', '').trim(),
                status: 'ideia' as SistemaStatus,
                data_criacao: new Date().toISOString(),
                data_atualizacao: new Date().toISOString()
              };
              const systemName = unit.nome.replace('SISTEMA:', '').trim();
              const ajustesPendentes = workItems.filter(w => w.sistema_id === unit.id && !w.concluido).length;

              return (
                <button
                  key={unit.id}
                  onClick={() => setSelectedSystemId(unit.id)}
                  className="bg-white border border-slate-200 rounded-2xl md:rounded-[2.5rem] p-6 md:p-8 text-left shadow-sm md:shadow-xl hover:shadow-md md:hover:shadow-2xl hover:border-violet-300 transition-all group relative overflow-hidden"
                >
                  <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                  <div className="relative z-10 space-y-6">
                    <div className="flex justify-between items-start">
                      <div className="w-14 h-14 bg-violet-100 text-violet-600 rounded-none md:rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform">
                        <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                      </div>
                      <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest ${sysDetails.status === 'producao' ? 'bg-emerald-100 text-emerald-700' :
                        sysDetails.status === 'desenvolvimento' ? 'bg-blue-100 text-blue-700' :
                          sysDetails.status === 'testes' ? 'bg-amber-100 text-amber-700' :
                            'bg-slate-100 text-slate-500'
                        }`}>
                        {sysDetails.status === 'prototipacao' ? 'Prototipação' :
                          sysDetails.status === 'producao' ? 'Produção' :
                            sysDetails.status}
                      </span>
                    </div>
                    <div>
                      <h3 className="text-xl font-black text-slate-900 mb-1 group-hover:text-violet-700 transition-colors">{systemName}</h3>
                      <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                        Atualizado em {formatDate(sysDetails.data_atualizacao?.split('T')[0] || formatDateLocalISO(new Date()))}
                      </p>
                    </div>
                    <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-500">{ajustesPendentes} ajustes pendentes</span>
                      <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center group-hover:bg-violet-500 group-hover:text-white transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}

            {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length === 0 && (
              <div className="col-span-full text-center py-20 bg-slate-50 rounded-none md:rounded-[2.5rem] border-2 border-dashed border-slate-200">
                <p className="text-slate-400 font-bold text-lg mb-2">Nenhum sistema cadastrado</p>
                <button onClick={() => { setIsSettingsModalOpen(true); }} className="bg-slate-900 text-white px-6 py-3 rounded-lg md:rounded-xl font-bold uppercase tracking-widest text-xs hover:bg-slate-800 transition-all mt-4">
                  Ir para Configurações
                </button>
              </div>
            )}
          </div>
        </>
      ) : (
        /* VISÃO DETALHADA - SISTEMA SELECIONADO */
        (() => {
          const unit = unidades.find(u => u.id === selectedSystemId);
          if (!unit) return null;

          const sysDetails = sistemasDetalhes.find(s => s.id === unit.id) || {
            id: unit.id,
            nome: unit.nome.replace('SISTEMA:', '').trim(),
            status: 'ideia' as SistemaStatus,
            data_criacao: new Date().toISOString(),
            data_atualizacao: new Date().toISOString()
          };

          const systemName = unit.nome.replace('SISTEMA:', '').trim();
          const systemWorkItems = workItems.filter(w => w.sistema_id === unit.id);
          const ajustesPendentesCount = systemWorkItems.filter(w => !w.concluido).length;

          const steps: SistemaStatus[] = ['ideia', 'prototipacao', 'desenvolvimento', 'testes', 'producao'];

          return (
            <div className="animate-in fade-in slide-in-from-bottom-8 duration-500">
              {/* Navigation */}
              <button
                onClick={() => setSelectedSystemId(null)}
                className="mb-8 px-6 md:px-0 flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold text-xs uppercase tracking-widest transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
                Voltar para Lista
              </button>

              <div className="bg-white border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden shadow-xl">
                {/* Header Detalhado */}
                <div className="hidden md:block bg-slate-900 p-8 md:p-12 text-white relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/20 rounded-full -mr-20 -mt-20 blur-3xl"></div>
                  <div className="relative z-10 flex flex-col md:flex-row md:items-end justify-between gap-8">
                    <div className="space-y-4">
                      <div className="inline-flex items-center gap-2 bg-white/10 px-3 py-1 rounded-lg backdrop-blur-sm border border-white/10">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                        <span className="text-[10px] font-black uppercase tracking-widest">
                          {sysDetails.status === 'prototipacao' ? 'Prototipação' :
                            sysDetails.status === 'producao' ? 'Produção' :
                              sysDetails.status}
                        </span>
                      </div>
                      <h2 className="text-4xl md:text-5xl font-black tracking-tight">{systemName}</h2>
                    </div>
                    <div className="text-right">
                      <div className="text-3xl font-black text-violet-400">{ajustesPendentesCount}</div>
                      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Ajustes Pendentes</div>
                    </div>
                  </div>
                </div>

                {/* Status Stepper */}
                <div className="bg-slate-50 border-b border-slate-100 p-4 md:p-10 flex flex-col items-center gap-4 md:gap-8">
                  <div className="text-center">
                    <h2 className="text-lg md:text-3xl font-black text-slate-900 tracking-tight uppercase">{systemName}</h2>
                    <div className="w-8 h-1 bg-violet-500 mx-auto mt-2 rounded-full"></div>
                  </div>

                  <div className="flex flex-wrap items-center justify-center bg-slate-200/50 p-1 rounded-xl md:rounded-2xl gap-1 w-full md:w-auto">
                    {steps.map((step, idx) => {
                      const isActive = sysDetails.status === step;
                      const stepLabels: Record<string, string> = {
                        ideia: 'Ideia',
                        prototipacao: 'Protótipo',
                        desenvolvimento: 'Dev',
                        testes: 'Testes',
                        producao: 'Produção'
                      };
                      return (
                        <React.Fragment key={step}>
                          <button
                            onClick={() => handleUpdateSistema(unit.id, { status: step })}
                            className={`flex-1 md:flex-none px-2 md:px-4 py-2 rounded-lg md:rounded-xl text-[8px] md:text-[9px] font-black uppercase tracking-widest transition-all ${isActive
                              ? 'bg-violet-600 text-white shadow-lg'
                              : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'
                              }`}
                          >
                            {stepLabels[step]}
                          </button>
                          {idx < steps.length - 1 && (
                            <div className="hidden md:flex items-center text-slate-300 px-1">
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                            </div>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </div>
                </div>

                <div className="p-0 md:p-8 grid grid-cols-1 lg:grid-cols-3 gap-0 md:gap-12">
                  {/* Coluna 2: Links e Recursos (Topo no mobile) */}
                  <div className="lg:col-span-1 order-1 md:order-1 space-y-0 md:space-y-8">
                    <div className="p-4 md:p-0">
                      <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 flex items-center gap-2">
                        <span className="w-1 h-3 bg-violet-500 rounded-full"></span>
                        Recursos
                      </h4>
                    </div>

                    <div className="grid grid-cols-4 md:grid-cols-1 gap-2 md:gap-6 px-4 md:px-0 mb-8 md:mb-0">
                      {/* Repositório */}
                      <button
                        onClick={() => setEditingResource({ field: 'repositorio_principal', label: 'Repositório', value: sysDetails.repositorio_principal || '' })}
                        className="group bg-slate-900 p-4 md:p-6 rounded-2xl md:rounded-3xl border border-slate-800 hover:border-slate-600 hover:shadow-xl transition-all text-center md:text-left flex flex-col items-center md:items-stretch justify-center md:justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden"
                      >
                        <div className="absolute top-0 right-0 w-24 h-24 bg-violet-500/10 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                        <div className="relative z-10 space-y-2 md:space-y-3">
                          <div className="w-8 h-8 md:w-10 md:h-10 bg-white/10 text-white rounded-lg flex items-center justify-center mx-auto md:mx-0">
                            <svg className="w-4 h-4 md:w-5 md:h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" /></svg>
                          </div>
                          <h5 className="text-[8px] md:text-xs font-black text-white uppercase tracking-widest leading-none">Repo</h5>
                        </div>
                        <div className="hidden md:block relative z-10">
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{sysDetails.repositorio_principal ? 'Editar' : 'Configurar'}</span>
                        </div>
                      </button>

                      {/* Other buttons (Documentação, AI Studio, Hospedagem) omitted for brevity but logic is same */}
                      {/* ... */}
                    </div>
                  </div>

                  {/* Coluna 1: Logs de Trabalho (Abaixo no mobile) */}
                  <div className="lg:col-span-2 order-2 md:order-2 space-y-0 md:space-y-6">
                    <div className="bg-white border-0 md:border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden flex flex-col min-h-[400px] md:min-h-[600px] shadow-none md:shadow-sm">
                      {/* Novo Log Input */}
                      <div className="p-6 md:p-8 border-b border-slate-100 bg-slate-50">
                        <div className="flex flex-col gap-6">
                          <div className="flex items-center justify-between gap-4">
                            <div className="flex items-center gap-2">
                              <div className="p-1.5 bg-violet-600 text-white rounded-lg">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                              </div>
                              <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Dev Log</h4>
                            </div>
                          </div>

                          <div className="flex flex-col gap-4">
                            <div className="relative">
                              <WysiwygEditor
                                value={newLogText}
                                onChange={setNewLogText}
                                placeholder="O que foi feito no sistema?"
                                className="bg-white min-h-[120px] pb-10"
                              />
                              <div className="absolute right-4 top-4 flex flex-col gap-2">
                                <button
                                  onClick={isRecordingLog ? stopLogRecording : startLogRecording}
                                  disabled={isProcessingLog}
                                  className={`p-3 rounded-xl transition-all ${
                                    isRecordingLog
                                      ? 'bg-emerald-600 text-white animate-pulse shadow-lg'
                                      : isProcessingLog
                                        ? 'bg-violet-100 text-violet-600 cursor-wait'
                                        : 'bg-slate-100 text-slate-400 hover:text-violet-600'
                                  }`}
                                  title="Transcrever áudio"
                                >
                                  {isProcessingLog ? (
                                    <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                  ) : isRecordingLog ? (
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                                  ) : (
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                                  )}
                                </button>
                              </div>

                              <label className={`absolute left-3 bottom-2 p-2 rounded-xl transition-all ${isUploading ? 'bg-violet-100 animate-pulse pointer-events-none' : 'text-slate-400 hover:text-violet-600 hover:bg-violet-50'} cursor-pointer`}>
                                <input
                                  type="file"
                                  accept="image/*"
                                  className="hidden"
                                  onChange={async (e) => {
                                    const file = e.target.files?.[0];
                                    if (file) {
                                      const item = await handleFileUploadToDrive(file);
                                      if (item) setNewLogAttachments(prev => [...prev, item]);
                                    }
                                  }}
                                />
                                {isUploading ? (
                                  <div className="w-4 h-4 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                ) : (
                                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                                )}
                              </label>
                            </div>
                            <button
                              onClick={() => {
                                handleCreateWorkItem(unit.id, newLogTipo, newLogText, newLogAttachments);
                                setNewLogText('');
                                setNewLogAttachments([]);
                              }}
                              disabled={!newLogText.trim()}
                              className="w-full bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 disabled:grayscale"
                            >
                              Registrar
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Listagem de Logs */}
                      <div className="block flex-1 overflow-y-auto p-4 md:p-8 bg-white space-y-8 pb-32">
                        {/* Ativos (Não concluídos) */}
                        <div className="space-y-4">
                          <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-violet-500 pl-3">Logs Ativos</h5>
                          {systemWorkItems.filter(w => !w.concluido).sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime()).map(log => (
                            <div key={log.id} className="group bg-slate-50 border border-slate-100 rounded-none md:rounded-3xl p-6 hover:border-violet-200 hover:bg-white transition-all">
                              <div className="flex flex-col md:flex-row items-start justify-between gap-4 md:gap-6">
                                <div className="flex-1 space-y-2 w-full">
                                  <div className="flex items-center gap-3">
                                    <span className={`text-[8px] font-black px-2 py-0.5 rounded uppercase tracking-wider ${log.tipo === 'desenvolvimento' ? 'bg-violet-100 text-violet-700' : log.tipo === 'ajuste' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>
                                      {log.tipo}
                                    </span>
                                    <span className="text-[8px] font-black text-slate-300 uppercase">{new Date(log.data_criacao).toLocaleDateString('pt-BR')}</span>
                                  </div>
                                  <p className="text-sm font-medium text-slate-700 leading-relaxed break-words">{log.descricao}</p>
                                </div>
                                <div className="flex gap-1 items-center opacity-0 group-hover:opacity-100 transition-opacity">
                                  <button
                                    onClick={() => {
                                      setEditingWorkItem(log);
                                      setEditingWorkItemText(log.descricao);
                                      setEditingWorkItemAttachments(log.pool_dados || []);
                                    }}
                                    className="p-2 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-all"
                                    title="Editar"
                                  >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                  </button>
                                  <button
                                    onClick={() => {
                                      if (confirmDeleteLogId === log.id) {
                                        handleDeleteWorkItem(log.id);
                                        setConfirmDeleteLogId(null);
                                      } else {
                                        setConfirmDeleteLogId(log.id);
                                        setTimeout(() => setConfirmDeleteLogId(null), 3000);
                                      }
                                    }}
                                    className={`p-2 rounded-lg transition-colors ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50'}`}
                                    title="Excluir"
                                  >
                                    {confirmDeleteLogId === log.id ? (
                                      <svg className="w-4 h-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                    ) : (
                                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                    )}
                                  </button>
                                  <button
                                    onClick={() => handleUpdateWorkItem(log.id, { concluido: true, data_conclusao: new Date().toISOString() })}
                                    className="w-10 h-10 rounded-full border-2 border-slate-200 flex items-center justify-center text-slate-300 hover:border-emerald-500 hover:text-emerald-500 hover:bg-emerald-50 transition-all group/check ml-2"
                                  >
                                    <svg className="w-5 h-5 opacity-0 group-hover/check:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                  </button>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {editingResource && (
                  <div className="fixed inset-0 z-[400] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 md:p-8 animate-in zoom-in-95 duration-300">
                    <div className="bg-white w-full max-w-lg rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden">
                      <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                        <h3 className="text-xl font-black text-slate-900 tracking-tight">Editar {editingResource.label}</h3>
                        <button onClick={() => setEditingResource(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </div>
                      <div className="p-8 space-y-6">
                        <div className="space-y-2">
                          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">URL do Recurso</label>
                          <input
                            type="text"
                            value={editingResource.value}
                            onChange={(e) => setEditingResource({ ...editingResource, value: e.target.value })}
                            placeholder="https://..."
                            className="w-full bg-slate-50 border border-slate-200 rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-violet-500 transition-all"
                          />
                        </div>
                        <div className="flex gap-4">
                          <button
                            onClick={() => setEditingResource(null)}
                            className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all"
                          >
                            Cancelar
                          </button>
                          <button
                            onClick={() => {
                              handleUpdateSistema(unit.id, { [editingResource.field]: editingResource.value });
                              setEditingResource(null);
                            }}
                            className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
                          >
                            Salvar Link
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {editingWorkItem && (
                  <div className="fixed inset-0 z-[500] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 md:p-8 animate-in zoom-in-95 duration-300">
                    <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden">
                      <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                        <h3 className="text-xl font-black text-slate-900 tracking-tight">Editar Registro</h3>
                        <button onClick={() => setEditingWorkItem(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors text-slate-400">
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </div>
                      <div className="p-8 space-y-6">
                        <div className="space-y-4">
                          <div className="space-y-2">
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Descrição</label>
                            <WysiwygEditor
                              value={editingWorkItemText}
                              onChange={setEditingWorkItemText}
                              className="bg-slate-50 min-h-[120px]"
                            />
                          </div>
                        </div>
                        <div className="flex gap-4 pt-4">
                          <button
                            onClick={() => setEditingWorkItem(null)}
                            className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-[1.5rem] transition-all"
                          >
                            Cancelar
                          </button>
                          <button
                            onClick={() => {
                              handleUpdateWorkItem(editingWorkItem.id, {
                                descricao: editingWorkItemText,
                                tipo: editingWorkItem.tipo,
                                pool_dados: editingWorkItemAttachments
                              });
                              setEditingWorkItem(null);
                              setEditingWorkItemAttachments([]);
                            }}
                            disabled={!editingWorkItemText.trim()}
                            className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-[1.5rem] text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50"
                          >
                            Salvar Alterações
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })()
      )}
    </div>
  );
};
