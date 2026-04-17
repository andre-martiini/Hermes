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
}

export const DiagnosticoTool: React.FC<DiagnosticoToolProps> = ({ onBack, initialDiagnosisId }) => {
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
        <div className="flex flex-col h-full bg-white">
            {/* Header */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 shrink-0">
                <button onClick={onBack} className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors">
                    <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
                    </svg>
                </button>
                <div>
                    <p className="text-xs font-black uppercase tracking-widest text-slate-800">Diagnósticos de Código</p>
                    <p className="text-[10px] text-slate-400">{diagnosticos.length} registro(s)</p>
                </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {isLoading && (
                    <div className="flex justify-center py-12">
                        <div className="w-5 h-5 border-2 border-slate-200 border-t-blue-500 rounded-full animate-spin" />
                    </div>
                )}

                {!isLoading && diagnosticos.length === 0 && (
                    <div className="text-center py-12">
                        <div className="w-12 h-12 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-3">
                            <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                            </svg>
                        </div>
                        <p className="text-xs font-bold text-slate-400">Nenhum diagnóstico ainda</p>
                        <p className="text-[10px] text-slate-300 mt-1">Use o Copiloto para diagnosticar um bug</p>
                    </div>
                )}

                {diagnosticos.map(item => (
                    <div key={item.id} className="border border-slate-200 rounded-xl overflow-hidden">
                        {/* Card header */}
                        <button
                            onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                            className="w-full text-left p-3 hover:bg-slate-50 transition-colors"
                        >
                            <div className="flex items-start justify-between gap-2">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-1.5 mb-1">
                                        <span className="text-[9px] font-black uppercase tracking-widest text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
                                            {item.sistemaId}
                                        </span>
                                        <span className="text-[9px] text-slate-400 font-mono truncate">{item.nomeRepositorio}</span>
                                    </div>
                                    <p className="text-[11px] font-bold text-slate-700 leading-tight line-clamp-2">{item.descricaoProblema}</p>
                                    <div className="flex items-center gap-3 mt-1.5">
                                        <span className="text-[9px] text-slate-400">{formatTs(item.criadoEm)}</span>
                                        <span className="text-[9px] text-slate-400">{item.arquivosAnalisados?.length ?? 0} arq.</span>
                                        <span className="text-[9px] font-bold text-emerald-600">{item.blocosSR?.length ?? 0} correção(ões)</span>
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
                            <div className="border-t border-slate-100 p-3 space-y-4 bg-slate-50/60">
                                {/* Diagnosis text */}
                                <div>
                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-500 mb-1.5">Diagnóstico</p>
                                    <p className="text-[11px] text-slate-600 leading-relaxed whitespace-pre-wrap">{item.diagnostico}</p>
                                </div>

                                {/* Files analyzed */}
                                {item.arquivosAnalisados?.length > 0 && (
                                    <div>
                                        <p className="text-[9px] font-black uppercase tracking-widest text-slate-500 mb-1.5">Arquivos Analisados</p>
                                        <div className="flex flex-wrap gap-1">
                                            {item.arquivosAnalisados.map((f, i) => (
                                                <span key={i} className="text-[9px] font-mono bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
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
                                                <div key={idx} className="border border-slate-200 rounded-lg overflow-hidden bg-white">
                                                    <div className="px-3 py-1.5 bg-slate-100 border-b border-slate-200">
                                                        <p className="text-[9px] font-black text-slate-600">{idx + 1}. {bloco.descricao}</p>
                                                        <p className="text-[9px] text-slate-400 font-mono">{bloco.arquivo}</p>
                                                    </div>
                                                    <div className="p-2 space-y-2">
                                                        <div>
                                                            <p className="text-[8px] font-black text-red-500 uppercase mb-1">SEARCH</p>
                                                            <pre className="text-[9px] text-slate-600 bg-red-50 border border-red-100 p-2 rounded overflow-x-auto font-mono leading-relaxed whitespace-pre">{bloco.search}</pre>
                                                        </div>
                                                        <div>
                                                            <p className="text-[8px] font-black text-emerald-600 uppercase mb-1">REPLACE</p>
                                                            <pre className="text-[9px] text-slate-600 bg-emerald-50 border border-emerald-100 p-2 rounded overflow-x-auto font-mono leading-relaxed whitespace-pre">{bloco.replace}</pre>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Impact alert */}
                                {item.alertaImpacto && (
                                    <div className="bg-amber-50 border border-amber-200 rounded-lg p-2.5">
                                        <p className="text-[9px] font-black uppercase tracking-widest text-amber-600 mb-1">Alerta de Impacto</p>
                                        <p className="text-[10px] text-amber-700 leading-relaxed">{item.alertaImpacto}</p>
                                    </div>
                                )}

                                {/* Download */}
                                <button
                                    onClick={() => handleDownload(item)}
                                    className="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-[10px] font-black uppercase tracking-widest transition-all"
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
