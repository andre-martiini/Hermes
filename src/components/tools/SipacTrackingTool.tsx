import React, { useState, useEffect } from 'react';
import { db, auth, functions } from '@/firebase';
import { httpsCallable } from 'firebase/functions';
import { collection, doc, setDoc, getDoc, query, where, getDocs } from 'firebase/firestore';

interface SipacTrackingToolProps {
  onBack: () => void;
  isDark?: boolean;
}

interface Interessado {
  tipo: string;
  nome: string;
}

interface Documento {
  ordem: string;
  tipo: string;
  data: string;
  unidadeOrigem: string;
  natureza: string;
  statusVisualizacao: string;
  url: string;
}

interface Movimentacao {
  data: string;
  horario: string;
  unidadeOrigem: string;
  unidadeDestino: string;
  usuarioRemetente: string;
  dataRecebimento: string;
  horarioRecebimento: string;
  usuarioRecebedor: string;
  urgente: string;
}

interface Incidente {
  numeroDocumento: string;
  tipoDocumento: string;
  usuarioSolicitacao: string;
  dataSolicitacao: string;
  usuarioCancelamento: string;
  dataCancelamento: string;
  justificativa: string;
}

interface SIPACProcess {
  numeroProcesso: string;
  dataAutuacion: string;
  horarioAutuacion: string;
  usuarioAutuacion: string;
  natureza: string;
  status: string;
  dataCadastro: string;
  unidadeOrigem: string;
  unidadeAtual: string;
  totalDocumentos: string;
  observacao: string;
  assuntoCodigo: string;
  assuntoDescricao: string;
  assuntoDetalhado: string;
  interessados: Interessado[];
  documentos: Documento[];
  movimentacoes: Movimentacao[];
  incidentes: Incidente[];
  scraping_last_error?: string | null;
  detailUrl?: string;
}

interface SavedProcess {
  numeroProcesso: string;
  status: string;
  unidadeAtual: string;
  natureza: string;
  assuntoDescricao: string;
  ultimaConsulta: string;
}

export const SipacTrackingTool: React.FC<SipacTrackingToolProps> = ({ onBack, isDark = false }) => {
  const [protocolo, setProtocolo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [processData, setProcessData] = useState<SIPACProcess | null>(null);
  const [recentQueries, setRecentQueries] = useState<SavedProcess[]>([]);
  const [isTracking, setIsTracking] = useState(false);

  useEffect(() => {
    loadRecentQueries();
  }, []);

  const loadRecentQueries = async () => {
    try {
      const uid = auth.currentUser?.uid;
      if (!uid) return;

      const q = query(
        collection(db, 'sipac_processos'),
        where('uid', '==', uid)
      );

      const snap = await getDocs(q);
      const list = snap.docs
        .map(d => d.data() as SavedProcess & { uid: string })
        .sort((a, b) => new Date(b.ultimaConsulta).getTime() - new Date(a.ultimaConsulta).getTime())
        .slice(0, 10);

      setRecentQueries(list);
    } catch (err) {
      console.error('Erro ao carregar histórico:', err);
    }
  };

  const loadSavedProcess = async (numeroProcesso: string) => {
    setLoading(true);
    setError(null);
    try {
      const uid = auth.currentUser?.uid;
      if (!uid) return false;
      const ref = doc(db, 'sipac_processos', `${uid}_${numeroProcesso.replace(/[^\d]/g, '')}`);
      const snap = await getDoc(ref);
      if (snap.exists()) {
        const data = snap.data();
        if (data.documentos && data.movimentacoes) {
          setProcessData(data as SIPACProcess);
          setIsTracking(!!data.acompanhar);
          setProtocolo(data.numeroProcesso);
          return true;
        }
      }
      return false;
    } catch (err: any) {
      console.error('Erro ao carregar processo do Firestore:', err);
      return false;
    } finally {
      setLoading(false);
    }
  };

  const saveQueryToFirestore = async (process: SIPACProcess) => {
    try {
      const uid = auth.currentUser?.uid;
      if (!uid) return;

      const ref = doc(db, 'sipac_processos', `${uid}_${process.numeroProcesso.replace(/[^\d]/g, '')}`);
      const saved = {
        ...process,
        ultimaConsulta: new Date().toISOString(),
        uid: uid
      };

      await setDoc(ref, saved, { merge: true });
      loadRecentQueries();
    } catch (err) {
      console.error('Erro ao salvar no histórico do Firestore:', err);
    }
  };

  const formatProtocol = (val: string) => {
    const numbers = val.replace(/\D/g, '');
    let masked = numbers;
    if (numbers.length > 5) masked = numbers.slice(0, 5) + '.' + numbers.slice(5);
    if (numbers.length > 11) masked = masked.slice(0, 12) + '/' + masked.slice(12);
    if (numbers.length > 15) masked = masked.slice(0, 17) + '-' + masked.slice(17, 19);
    return masked.slice(0, 20);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setProtocolo(formatProtocol(e.target.value));
  };

  const checkTrackingStatus = async (numeroProcesso: string) => {
    try {
      const uid = auth.currentUser?.uid;
      if (!uid) return;
      const ref = doc(db, 'sipac_processos', `${uid}_${numeroProcesso.replace(/[^\d]/g, '')}`);
      const snap = await getDoc(ref);
      if (snap.exists()) {
        setIsTracking(!!snap.data().acompanhar);
      } else {
        setIsTracking(false);
      }
    } catch (err) {
      console.error('Erro ao verificar status de monitoramento:', err);
    }
  };

  const handleToggleTracking = async () => {
    if (!processData) return;
    try {
      const uid = auth.currentUser?.uid;
      if (!uid) return;
      const newTracking = !isTracking;
      setIsTracking(newTracking);

      const ref = doc(db, 'sipac_processos', `${uid}_${processData.numeroProcesso.replace(/[^\d]/g, '')}`);
      await setDoc(ref, {
        acompanhar: newTracking,
        uid: uid
      }, { merge: true });

      loadRecentQueries();
    } catch (err) {
      console.error('Erro ao atualizar monitoramento:', err);
    }
  };

  const handleSearch = async (procNum?: string, forceRefresh = false) => {
    const targetProtocol = procNum || protocolo;
    if (!targetProtocol.trim()) return;

    if (!forceRefresh) {
      const loaded = await loadSavedProcess(targetProtocol);
      if (loaded) return;
    }

    setLoading(true);
    setError(null);
    setProcessData(null);

    try {
      const consultarSipac = httpsCallable<{ numeroProcesso: string }, SIPACProcess>(functions, 'consultarProcessoSipac');
      const response = await consultarSipac({ numeroProcesso: targetProtocol });
      const data = response.data;

      if (data.scraping_last_error) {
        throw new Error(data.scraping_last_error);
      }

      setProcessData(data);
      saveQueryToFirestore(data);
      checkTrackingStatus(data.numeroProcesso);
    } catch (err: any) {
      console.error('Erro ao consultar processo:', err);
      setError(err.message || 'Falha de conexão com a Cloud Function de consulta.');
    } finally {
      setLoading(false);
    }
  };

  // Cores de status de trâmite
  const getStatusColorClasses = (status: string) => {
    const norm = status.toUpperCase();
    if (norm.includes('ERRO')) return 'bg-rose-500/10 text-rose-500 border border-rose-500/20';
    if (norm.includes('CONCLU') || norm.includes('ARQUIV')) return 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20';
    if (norm.includes('MESA') || norm.includes('EM TRAM')) return 'bg-blue-500/10 text-blue-500 border border-blue-500/20';
    return 'bg-amber-500/10 text-amber-500 border border-amber-500/20';
  };

  return (
    <div className={`flex flex-col h-full ${isDark ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-800'}`}>
      {/* Header */}
      <div className={`flex items-center justify-between px-6 py-4 border-b shrink-0 ${isDark ? 'border-slate-800 bg-slate-900' : 'border-slate-200 bg-white'}`}>
        <div className="flex items-center gap-3">
          <button onClick={onBack} className={`p-2 rounded-none-none transition-colors ${isDark ? 'hover:bg-slate-800 text-slate-400 hover:text-slate-100' : 'hover:bg-slate-100 text-slate-500 hover:text-slate-950'}`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div>
            <p className="text-[10px] font-mono font-black text-emerald-500 uppercase tracking-widest leading-none mb-1">FERRAMENTA DE RASPAGEM</p>
            <h3 className="text-lg font-mono font-black uppercase tracking-tight">Acompanhamento SIPAC</h3>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex flex-col md:flex-row">
        {/* Painel Lateral - Histórico */}
        <div className={`w-full md:w-80 border-b md:border-b-0 md:border-r overflow-y-auto flex-shrink-0 p-4 space-y-4 ${isDark ? 'border-slate-800 bg-slate-900/40' : 'border-slate-200 bg-slate-100/30'}`}>
          <div className="flex items-center gap-2 text-slate-400">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-xs font-mono font-black uppercase tracking-widest">Buscas Recentes</span>
          </div>

          <div className="space-y-2">
            {recentQueries.map((item, idx) => (
              <button
                key={idx}
                onClick={() => { setProtocolo(item.numeroProcesso); handleSearch(item.numeroProcesso); }}
                className={`w-full text-left p-3 rounded-none-none border transition-all flex flex-col gap-1.5 ${
                  isDark
                    ? 'bg-slate-900 border-slate-800 hover:bg-slate-800 hover:border-slate-700'
                    : 'bg-white border-slate-200 hover:bg-slate-50 hover:border-slate-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-black tracking-tight">{item.numeroProcesso}</span>
                  <span className={`text-[8px] font-mono font-black px-1.5 py-0.5 uppercase tracking-wider rounded-none ${getStatusColorClasses(item.status)}`}>
                    {item.status}
                  </span>
                </div>
                <div className="text-[10px] text-slate-400 font-bold line-clamp-1 uppercase">
                  {item.unidadeAtual || 'Sem localização'}
                </div>
              </button>
            ))}

            {recentQueries.length === 0 && (
              <div className="text-center py-8 text-slate-400 font-mono text-xs italic">
                Nenhuma busca recente.
              </div>
            )}
          </div>
        </div>

        {/* Painel Central - Conteúdo */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Caixa de Busca */}
          <div className={`p-6 rounded-none-none border ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
            <h4 className="text-xs font-mono font-black uppercase tracking-widest text-slate-400 mb-3">Buscar Novo Processo</h4>
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                placeholder="00000.000000/0000-00"
                value={protocolo}
                onChange={handleInputChange}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className={`flex-1 font-mono text-sm px-4 py-3 rounded-none-none border outline-none transition-all ${
                  isDark
                    ? 'bg-slate-950 border-slate-800 focus:border-emerald-500 text-slate-100 placeholder:text-slate-600'
                    : 'bg-slate-50 border-slate-200 focus:border-emerald-600 text-slate-800 placeholder:text-slate-300'
                }`}
              />
              <button
                onClick={() => handleSearch()}
                disabled={loading || !protocolo.trim()}
                className={`h-[46px] px-6 rounded-none-none font-mono text-xs font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50`}
              >
                {loading ? (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                  </svg>
                )}
                <span>{loading ? 'Buscando...' : 'Consultar'}</span>
              </button>
            </div>

            {error && (
              <div className="mt-4 p-4 border border-rose-500/20 bg-rose-500/5 text-rose-500 text-xs font-mono font-bold flex items-center gap-2">
                <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>{error}</span>
              </div>
            )}
          </div>

          {/* Estado de Espera Inicial */}
          {!processData && !loading && (
            <div className={`py-20 text-center border-2 border-dashed rounded-none-none ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <svg className="w-10 h-10 text-slate-400 mx-auto mb-3" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.375c1.08 0 1.958-.88 1.958-1.958V13.5m-3.375 5.25h4.875c.621 0 1.125-.504 1.125-1.125v-9.75c0-.621-.504-1.125-1.125-1.125h-9.75c-.621 0-1.125.504-1.125 1.125v9.75c0 .621.504 1.125 1.125 1.125z" />
              </svg>
              <p className="text-slate-400 font-mono text-[10px] font-black uppercase tracking-[0.2em]">Aguardando Consulta</p>
              <p className="text-slate-500 text-xs mt-1">Insira um número de processo ou clique em um histórico lateral.</p>
            </div>
          )}

          {/* Dados do Processo Sincronizados */}
          {processData && (
            <div className="space-y-6 animate-in fade-in duration-300">
              {/* Card Dados Gerais */}
              <div className={`p-6 rounded-none-none border ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
                  <h4 className="text-xs font-mono font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
                    <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    Identificação e Status Geral
                  </h4>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSearch(processData.numeroProcesso, true)}
                      disabled={loading}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 font-mono text-[9px] font-black uppercase tracking-wider transition-all border ${
                        isDark
                          ? 'bg-slate-800 text-slate-300 border-slate-700 hover:text-white hover:bg-slate-700'
                          : 'bg-slate-100 text-slate-600 border-slate-200 hover:text-slate-900 hover:bg-slate-200'
                      } disabled:opacity-50`}
                    >
                      {loading ? (
                        <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                      ) : (
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                        </svg>
                      )}
                      <span>{loading ? 'Sincronizando...' : 'Sincronizar'}</span>
                    </button>

                    <button
                      onClick={handleToggleTracking}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 font-mono text-[9px] font-black uppercase tracking-wider transition-all border ${
                        isTracking
                          ? 'bg-emerald-600/10 text-emerald-500 border-emerald-500/20 hover:bg-emerald-600/20'
                          : isDark
                            ? 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                            : 'bg-slate-100 text-slate-500 border-slate-200 hover:text-slate-900 hover:bg-slate-200'
                      }`}
                    >
                      {isTracking ? (
                        <>
                          <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                            <path d="M12 22a2.98 2.98 0 0 0 2.818-2H9.182A2.98 2.98 0 0 0 12 22zm7-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C8.63 5.36 7 7.92 7 11v5l-2 2v1h14v-1l-2-2z"/>
                          </svg>
                          <span>Acompanhando</span>
                        </>
                      ) : (
                        <>
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
                          </svg>
                          <span>Acompanhar</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                  <div>
                    <span className="block text-[9px] font-mono font-black text-slate-400 uppercase tracking-wider">Número do Processo</span>
                    <span className="font-mono text-base font-black text-slate-900 dark:text-slate-100">{processData.numeroProcesso}</span>
                  </div>
                  <div>
                    <span className="block text-[9px] font-mono font-black text-slate-400 uppercase tracking-wider">Status Oficial</span>
                    <span className={`inline-flex font-mono text-[10px] font-black px-2 py-0.5 uppercase tracking-wide rounded-none ${getStatusColorClasses(processData.status)}`}>
                      {processData.status}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[9px] font-mono font-black text-slate-400 uppercase tracking-wider">Localização Atual</span>
                    <span className="text-xs font-mono font-black text-slate-700 dark:text-slate-300 uppercase leading-none">{processData.unidadeAtual}</span>
                  </div>
                  <div>
                    <span className="block text-[9px] font-mono font-black text-slate-400 uppercase tracking-wider">Autuação</span>
                    <span className="text-xs font-bold text-slate-600 dark:text-slate-400">{processData.dataAutuacion} {processData.horarioAutuacion && `às ${processData.horarioAutuacion}`}</span>
                  </div>
                  <div>
                    <span className="block text-[9px] font-mono font-black text-slate-400 uppercase tracking-wider">Natureza do Objeto</span>
                    <span className="text-xs font-bold text-slate-600 dark:text-slate-400">{processData.natureza}</span>
                  </div>
                  <div>
                    <span className="block text-[9px] font-mono font-black text-slate-400 uppercase tracking-wider">Total de Documentos</span>
                    <span className="text-xs font-bold text-slate-600 dark:text-slate-400">{processData.totalDocumentos} documentos oficiais</span>
                  </div>
                </div>
              </div>

              {/* Assunto e Observação */}
              <div className={`p-6 rounded-none-none border ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                <h4 className="text-xs font-mono font-black uppercase tracking-widest text-slate-400 mb-4 flex items-center gap-2">
                  <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                  </svg>
                  Assunto & Detalhes Operacionais
                </h4>
                <div className="space-y-4">
                  <div>
                    <span className="block text-[9px] font-mono font-black text-slate-400 uppercase tracking-wider">Assunto Principal</span>
                    <p className="text-xs font-bold text-slate-800 dark:text-slate-200">
                      {processData.assuntoCodigo && `${processData.assuntoCodigo} - `}{processData.assuntoDescricao}
                    </p>
                  </div>
                  {processData.assuntoDetalhado && processData.assuntoDetalhado !== 'Não informado' && (
                    <div>
                      <span className="block text-[9px] font-mono font-black text-slate-400 uppercase tracking-wider">Assunto Detalhado</span>
                      <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed font-mono">
                        {processData.assuntoDetalhado}
                      </p>
                    </div>
                  )}
                  {processData.observacao && processData.observacao !== 'Não informado' && (
                    <div className={`p-4 border ${isDark ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
                      <span className="block text-[9px] font-mono font-black text-amber-500 uppercase tracking-wider mb-1">Nota Complementar / Observação</span>
                      <p className="text-xs italic text-slate-700 dark:text-slate-300 font-medium">"{processData.observacao}"</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Interessados */}
              {processData.interessados && processData.interessados.length > 0 && (
                <div className={`p-6 rounded-none-none border ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                  <h4 className="text-xs font-mono font-black uppercase tracking-widest text-slate-400 mb-4 flex items-center gap-2">
                    <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    Interessados / Partes Relacionadas
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {processData.interessados.map((item, idx) => (
                      <div key={idx} className={`p-3 border flex flex-col gap-1 ${isDark ? 'bg-slate-950 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
                        <span className="text-[8px] font-mono font-black text-slate-400 uppercase tracking-widest">{item.tipo}</span>
                        <span className="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase">{item.nome}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Acervo de Documentos */}
              {processData.documentos && processData.documentos.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-xs font-mono font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
                    <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2" />
                    </svg>
                    Acervo de Documentos Públicos ({processData.documentos.length})
                  </h4>

                  <div className={`border rounded-none-none overflow-hidden ${isDark ? 'border-slate-800 bg-slate-900' : 'border-slate-200 bg-white'}`}>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse">
                        <thead>
                          <tr className={`border-b text-[9px] font-mono font-black uppercase tracking-wider text-slate-400 ${isDark ? 'border-slate-800 bg-slate-950/40' : 'border-slate-200 bg-slate-50'}`}>
                            <th className="px-4 py-3 text-center w-12">Seq</th>
                            <th className="px-4 py-3">Tipologia do Documento</th>
                            <th className="px-4 py-3 w-28">Data</th>
                            <th className="px-4 py-3">Unidade Emissora</th>
                            <th className="px-4 py-3 text-center w-24">Link</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                          {processData.documentos.map((doc, idx) => (
                            <tr key={idx} className={`text-xs hover:bg-emerald-500/5 transition-colors`}>
                              <td className="px-4 py-3 text-center font-mono font-black text-slate-400">#{doc.ordem}</td>
                              <td className="px-4 py-3 font-mono font-black text-slate-700 dark:text-slate-200">{doc.tipo}</td>
                              <td className="px-4 py-3 text-slate-500 font-medium">{doc.data}</td>
                              <td className="px-4 py-3 text-slate-500 font-mono uppercase tracking-tighter text-[10px]">{doc.unidadeOrigem}</td>
                              <td className="px-4 py-3 text-center">
                                {doc.url ? (
                                  <a
                                    href={doc.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 font-mono text-[9px] font-black uppercase tracking-wider transition-all rounded-none ${
                                      isDark 
                                        ? 'bg-slate-800 hover:bg-emerald-600 text-slate-100' 
                                        : 'bg-slate-100 hover:bg-emerald-600 hover:text-white text-slate-700'
                                    }`}
                                  >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                                    </svg>
                                    Acessar
                                  </a>
                                ) : (
                                  <span className="text-[10px] italic text-slate-400">Restrito</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {/* Movimentações / Linha do Tempo */}
              {processData.movimentacoes && processData.movimentacoes.length > 0 && (
                <div className="space-y-4">
                  <h4 className="text-xs font-mono font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
                    <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Histórico de Trâmite e Movimentações
                  </h4>

                  <div className="relative pl-4 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-[1px] before:bg-slate-300 dark:before:bg-slate-800">
                    {processData.movimentacoes.map((mov, idx) => (
                      <div key={idx} className="relative pl-6">
                        {/* Dot */}
                        <div className={`absolute left-0 top-1.5 w-4 h-4 rounded-none-none border-4 ${
                          isDark ? 'border-slate-900' : 'border-white'
                        } ${
                          idx === processData.movimentacoes.length - 1
                            ? 'bg-emerald-500 animate-pulse'
                            : 'bg-slate-300 dark:bg-slate-700'
                        }`} />

                        <div className={`p-4 border transition-all ${
                          isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-850' : 'bg-white border-slate-200 hover:bg-slate-50'
                        }`}>
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
                            <span className="font-mono text-xs font-black text-emerald-500">
                              {mov.data} {mov.horario && `às ${mov.horario}`}
                            </span>
                            <div className="flex items-center gap-2">
                              {mov.urgente && mov.urgente.toLowerCase().includes('sim') && (
                                <span className="text-[8px] font-mono font-black bg-rose-600 text-white px-1.5 py-0.5 rounded-none tracking-widest animate-bounce">
                                  URGENTE
                                </span>
                              )}
                              <span className="text-[10px] text-slate-400 font-mono">Remetente: {mov.usuarioRemetente || 'Portal'}</span>
                            </div>
                          </div>

                          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 text-xs font-mono">
                            <div className="flex-1">
                              <span className="block text-[8px] font-black text-slate-400 uppercase mb-0.5">Origem</span>
                              <span className="text-[11px] font-black text-slate-600 dark:text-slate-400 uppercase leading-snug">{mov.unidadeOrigem}</span>
                            </div>
                            <div className="text-slate-300 dark:text-slate-700 hidden sm:block">
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                              </svg>
                            </div>
                            <div className="flex-1">
                              <span className="block text-[8px] font-black text-emerald-500 uppercase mb-0.5 tracking-wider">Destino</span>
                              <span className="text-[11px] font-black text-emerald-600 dark:text-emerald-400 uppercase leading-snug">{mov.unidadeDestino}</span>
                            </div>
                            {mov.usuarioRecebedor && (
                              <div className="mt-2 sm:mt-0 p-2 bg-slate-50 dark:bg-slate-950/60 border dark:border-slate-800 rounded-none-none text-[9px] text-slate-500 flex flex-col">
                                <span className="text-[7px] text-slate-400 font-black uppercase tracking-tight">Recebido em {mov.dataRecebimento} por</span>
                                <span className="font-bold uppercase tracking-tight">{mov.usuarioRecebedor}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
