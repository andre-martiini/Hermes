import React, { useState, useEffect } from 'react';
import { db, auth } from '@/firebase';
import { collection, query, where, orderBy, onSnapshot, Timestamp } from 'firebase/firestore';

interface BlocoSR {
    arquivo: string;
    descricao: string;
    search: string;
    replace: string;
}

interface DiagnosticoItem {
    id: string;
    sistemaId: string;
    nomeRepositorio: string;
    descricaoProblema: string;
    diagnostico: string;
    arquivosAnalisados: string[];
    blocosSR: BlocoSR[];
    alertaImpacto: string;
    markdownContent: string;
    criadoEm: Timestamp;
}

interface DiagnosticoToolProps {
    onBack: () => void;
    initialDiagnosisId?: string;
    initialCode?: string;
    isEmbedded?: boolean;
    isDark?: boolean;
}

export const DiagnosticoTool: React.FC<DiagnosticoToolProps> = ({ onBack, initialDiagnosisId, initialCode, isEmbedded, isDark = false }) => {
    const [diagnosticos, setDiagnosticos] = useState<DiagnosticoItem[]>([]);
    const [expandedId, setExpandedId] = useState<string | null>(initialDiagnosisId || null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const uid = auth.currentUser?.uid;
        if (!uid) { setIsLoading(false); return; }

        const q = query(
            collection(db, 'diagnosticos_codigo'),
            where('uid', '==', uid),
            orderBy('criadoEm', 'desc')
        );

        const unsub = onSnapshot(q, (snap) => {
            const items: DiagnosticoItem[] = snap.docs.map(d => ({
                id: d.id,
                ...(d.data() as Omit<DiagnosticoItem, 'id'>),
            }));
            setDiagnosticos(items);
            setIsLoading(false);
        });

        return () => unsub();
    }, []);

    const handleDownload = (item: DiagnosticoItem) => {
        const blob = new Blob([item.markdownContent], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `hermes_refactor_${item.sistemaId}_${item.id.slice(0, 6)}.md`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const formatTs = (ts: Timestamp) => {
        if (!ts?.toDate) return '';
        return ts.toDate().toLocaleDateString('pt-BR', {
            day: '2-digit', month: '2-digit', year: '2-digit',
            hour: '2-digit', minute: '2-digit',
        });
    };

    return (
        <div className={`flex flex-col h-full ${isDark ? 'bg-slate-950 text-slate-100' : 'bg-white text-slate-900'}`}>
            {/* Header */}
            <div className={`flex items-center gap-3 px-4 py-3 border-b shrink-0 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                <button onClick={onBack} className={`p-1.5 rounded-none hover:bg-opacity-80 transition-colors ${isDark ? 'hover:bg-slate-800 text-slate-400' : 'hover:bg-slate-100 text-slate-500'}`}>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
                    </svg>
                </button>
                <div>
                    <p className={`text-xs font-mono font-black uppercase tracking-widest ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>Diagnósticos de Código</p>
                    <p className="text-[10px] text-slate-400">{diagnosticos.length} registro(s)</p>
                </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {isLoading && (
                    <div className="flex justify-center py-12">
                        <div className={`w-5 h-5 border-2 border-t-blue-500 rounded-none animate-spin ${isDark ? 'border-slate-800' : 'border-slate-200'}`} />
                    </div>
                )}

                {!isLoading && diagnosticos.length === 0 && (
                    <div className="text-center py-12">
                        <div className={`w-12 h-12 rounded-none flex items-center justify-center mx-auto mb-3 ${isDark ? 'bg-slate-900' : 'bg-slate-100'}`}>
                            <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                            </svg>
                        </div>
                        <p className="text-xs font-bold text-slate-400">Nenhum diagnóstico ainda</p>
                        <p className={`text-[10px] mt-1 ${isDark ? 'text-slate-500' : 'text-slate-300'}`}>Use o Copiloto para diagnosticar um bug</p>
                    </div>
                )}

                {diagnosticos.map(item => (
                    <div key={item.id} className={`border rounded-none overflow-hidden ${isDark ? 'border-slate-800 bg-slate-900' : 'border-slate-200 bg-white'}`}>
                        {/* Card header */}
                        <button
                            onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                            className={`w-full text-left p-3 transition-colors ${isDark ? 'hover:bg-slate-800/50' : 'hover:bg-slate-50'}`}
                        >
                            <div className="flex items-start justify-between gap-2">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-1.5 mb-1">
                                        <span className={`text-[9px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded-none border ${isDark ? 'text-blue-400 bg-blue-950/50 border-blue-900' : 'text-blue-600 bg-blue-50 border-blue-200'}`}>
                                            {item.sistemaId}
                                        </span>
                                        <span className="text-[9px] text-slate-400 font-mono truncate">{item.nomeRepositorio}</span>
                                    </div>
                                    <p className={`text-[11px] font-bold leading-tight line-clamp-2 ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>{item.descricaoProblema}</p>
                                    <div className="flex items-center gap-3 mt-1.5">
                                        <span className="text-[9px] text-slate-400">{formatTs(item.criadoEm)}</span>
                                        <span className="text-[9px] text-slate-400">{item.arquivosAnalisados?.length ?? 0} arq.</span>
                                        <span className={`text-[9px] font-bold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{item.blocosSR?.length ?? 0} correção(ões)</span>
                                    </div>
                                </div>
                                <svg
                                    className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform mt-0.5 ${expandedId === item.id ? 'rotate-180' : ''}`}
                                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                                >
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                                </svg>
                            </div>
                        </button>

                        {/* Expanded */}
                        {expandedId === item.id && (
                            <div className={`border-t p-3 space-y-4 ${isDark ? 'border-slate-800 bg-slate-950/40' : 'border-slate-200 bg-slate-50/60'}`}>
                                {/* Diagnosis text */}
                                <div>
                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-500 mb-1.5">Diagnóstico</p>
                                    <p className={`text-[11px] leading-relaxed whitespace-pre-wrap ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>{item.diagnostico}</p>
                                </div>

                                {/* Files analyzed */}
                                {item.arquivosAnalisados?.length > 0 && (
                                    <div>
                                        <p className="text-[9px] font-black uppercase tracking-widest text-slate-500 mb-1.5">Arquivos Analisados</p>
                                        <div className="flex flex-wrap gap-1">
                                            {item.arquivosAnalisados.map((f, i) => (
                                                <span key={i} className={`text-[9px] font-mono px-1.5 py-0.5 rounded-none ${isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-100 text-slate-500'}`}>
                                                    {f.split('/').pop()}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* SEARCH/REPLACE blocks */}
                                {item.blocosSR?.length > 0 && (
                                    <div>
                                        <p className="text-[9px] font-black uppercase tracking-widest text-slate-500 mb-2">Correções</p>
                                        <div className="space-y-3">
                                            {item.blocosSR.map((bloco, idx) => (
                                                <div key={idx} className={`border rounded-none overflow-hidden ${isDark ? 'border-slate-800 bg-slate-900' : 'border-slate-200 bg-white'}`}>
                                                    <div className={`px-3 py-1.5 border-b ${isDark ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-100 border-slate-200'}`}>
                                                        <p className={`text-[9px] font-black ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>{idx + 1}. {bloco.descricao}</p>
                                                        <p className="text-[9px] text-slate-400 font-mono">{bloco.arquivo}</p>
                                                    </div>
                                                    <div className="p-2 space-y-2">
                                                        <div>
                                                            <p className="text-[8px] font-black text-red-500 uppercase mb-1">SEARCH</p>
                                                            <pre className={`text-[9px] border p-2 rounded-none overflow-x-auto font-mono leading-relaxed whitespace-pre ${isDark ? 'text-red-300 bg-red-950/20 border-red-900/50' : 'text-slate-600 bg-red-50 border border-red-100'}`}>{bloco.search}</pre>
                                                        </div>
                                                        <div>
                                                            <p className={`text-[8px] font-black uppercase mb-1 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>REPLACE</p>
                                                            <pre className={`text-[9px] border p-2 rounded-none overflow-x-auto font-mono leading-relaxed whitespace-pre ${isDark ? 'text-emerald-300 bg-emerald-950/20 border-emerald-900/50' : 'text-slate-600 bg-emerald-50 border border-emerald-100'}`}>{bloco.replace}</pre>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Impact alert */}
                                {item.alertaImpacto && (
                                    <div className={`border rounded-none p-2.5 ${isDark ? 'bg-amber-950/20 border-amber-900/50' : 'bg-amber-50 border border-amber-200'}`}>
                                        <p className={`text-[9px] font-black uppercase tracking-widest mb-1 ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>Alerta de Impacto</p>
                                        <p className={`text-[10px] leading-relaxed ${isDark ? 'text-amber-300' : 'text-amber-700'}`}>{item.alertaImpacto}</p>
                                    </div>
                                )}

                                {/* Download */}
                                <button
                                    onClick={() => handleDownload(item)}
                                    className="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-none text-[10px] font-black uppercase tracking-widest transition-all"
                                >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                    </svg>
                                    Baixar hermes_refactor.md
                                </button>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
};
