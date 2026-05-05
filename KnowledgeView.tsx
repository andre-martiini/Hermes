import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { collection, deleteDoc, doc, onSnapshot, setDoc } from 'firebase/firestore';
import {
    smartSearchKG,
    getArtefatoRawText,
    type KnowledgeResult,
    type KnowledgeFilters,
    type KnowledgeIntent,
    type FileSearchCitation,
} from './src/services/knowledgeService';
import { db } from './firebase';

interface KnowledgeViewProps {
    onNavigateToOrigin?: (modulo: string, id: string) => void;
}

const LOADING_MESSAGES = [
    'Analisando intenção…',
    'Consultando o grafo de conhecimento…',
    'Buscando no acervo global…',
    'Sintetizando resposta…',
    'Organizando fontes…',
];

const AREAS_TEMATICAS = ['CLC', 'ASSISTÊNCIA', 'GERAL'];

const TYPE_LABEL: Record<string, string> = {
    node: 'Nó',
    artefato: 'Documento',
};

interface MemoryAuditItem {
    id: string;
    titulo: string;
    tipo: 'regra_global' | 'fato_isolado';
    texto_memoria: string;
    data_atualizacao?: string;
    memoria_status?: string;
}

// Formata datas ISO/Timestamp em pt-BR; retorna string vazia se inválida.
function formatResultDate(raw: unknown): string {
    if (!raw) return '';
    try {
        const d = new Date(raw as string);
        if (isNaN(d.getTime())) return '';
        return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch {
        return '';
    }
}

// Ícone do tipo — SVG inline para não depender de biblioteca.
const TypeIcon: React.FC<{ type: string; className?: string }> = ({ type, className = 'w-5 h-5' }) => {
    if (type === 'node') {
        return (
            <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3" />
                <circle cx="5" cy="5" r="2" />
                <circle cx="19" cy="5" r="2" />
                <circle cx="5" cy="19" r="2" />
                <circle cx="19" cy="19" r="2" />
                <line x1="7" y1="6" x2="10" y2="10" />
                <line x1="17" y1="6" x2="14" y2="10" />
                <line x1="7" y1="18" x2="10" y2="14" />
                <line x1="17" y1="18" x2="14" y2="14" />
            </svg>
        );
    }
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="8" y1="13" x2="16" y2="13" />
            <line x1="8" y1="17" x2="16" y2="17" />
        </svg>
    );
};

// ─── Chip genérico ───────────────────────────────────────────────────────────

const Chip: React.FC<{
    active?: boolean;
    onClick?: () => void;
    children: React.ReactNode;
}> = ({ active, onClick, children }) => (
    <button
        onClick={onClick}
        className={`px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 ${
            active
                ? 'bg-slate-900 text-white shadow-lg'
                : 'bg-white text-slate-600 border border-slate-200 hover:border-slate-400'
        }`}
    >
        {children}
    </button>
);

// ─── Síntese com citações clicáveis ──────────────────────────────────────────

const SynthesisBlock: React.FC<{
    text: string;
    onCitationClick: (index: number) => void;
}> = ({ text, onCitationClick }) => {
    // Divide o texto em segmentos preservando os marcadores [N]
    const parts = useMemo(() => {
        const segments: Array<{ type: 'text' | 'cite'; value: string; n?: number }> = [];
        const re = /\[(\d+)\]/g;
        let lastIndex = 0;
        let match: RegExpExecArray | null;
        while ((match = re.exec(text)) !== null) {
            if (match.index > lastIndex) {
                segments.push({ type: 'text', value: text.slice(lastIndex, match.index) });
            }
            segments.push({ type: 'cite', value: match[0], n: Number(match[1]) });
            lastIndex = re.lastIndex;
        }
        if (lastIndex < text.length) {
            segments.push({ type: 'text', value: text.slice(lastIndex) });
        }
        return segments;
    }, [text]);

    return (
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 text-white rounded-2xl p-6 md:p-8 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                    <svg className="w-4 h-4 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M12 2L15 9L22 9L16.5 14L18.5 22L12 17L5.5 22L7.5 14L2 9L9 9Z" />
                    </svg>
                </div>
                <span className="text-[10px] font-black uppercase tracking-[0.25em] text-emerald-400">
                    Síntese da IA
                </span>
            </div>
            <p className="text-base md:text-lg leading-relaxed tracking-tight text-slate-100 whitespace-pre-wrap">
                {parts.map((p, i) =>
                    p.type === 'text' ? (
                        <span key={i}>{p.value}</span>
                    ) : (
                        <button
                            key={i}
                            onClick={() => p.n !== undefined && onCitationClick(p.n)}
                            className="inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5 mx-0.5 rounded-md bg-emerald-500/20 hover:bg-emerald-500/40 text-emerald-300 hover:text-white text-xs font-black transition-all align-middle"
                            title={`Abrir fonte ${p.n}`}
                        >
                            {p.n}
                        </button>
                    )
                )}
            </p>
        </div>
    );
};

// ─── Card de resultado ───────────────────────────────────────────────────────

const getCitationMetadata = (citation: FileSearchCitation, key: string): string => {
    const item = citation.custom_metadata?.find((meta) => meta.key === key);
    const value = item?.string_value ?? item?.numeric_value;
    return value === undefined || value === null ? '' : String(value);
};

const FileSearchCitationsBlock: React.FC<{
    citations: FileSearchCitation[];
    results: KnowledgeResult[];
    onOpenResult: (item: KnowledgeResult, index: number) => void;
}> = ({ citations, results, onOpenResult }) => {
    const visible = citations.filter((citation) => citation.title || citation.text || citation.page_number);
    if (visible.length === 0) return null;

    return (
        <section className="mt-4 bg-white rounded-2xl border border-emerald-100 p-5 shadow-sm">
            <div className="flex items-center justify-between gap-3 mb-4">
                <div>
                    <h3 className="text-[10px] font-black uppercase tracking-[0.25em] text-emerald-700">
                        Fontes por página
                    </h3>
                    <p className="text-xs text-slate-400 mt-1">
                        Trechos recuperados pelo Gemini File Search.
                    </p>
                </div>
                <span className="px-2 py-1 rounded-lg bg-emerald-50 text-emerald-700 text-[9px] font-black uppercase tracking-widest">
                    Gemini
                </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {visible.map((citation, i) => {
                    const acervoId = getCitationMetadata(citation, 'acervo_id');
                    const resultIdx = acervoId ? results.findIndex((r) => r.acervo_id === acervoId || r.id === acervoId) : -1;
                    const result = resultIdx >= 0 ? results[resultIdx] : null;
                    const pageLabel = citation.page_number ? `p. ${citation.page_number}` : 'sem página';

                    return (
                        <button
                            key={`${citation.index}-${i}`}
                            onClick={() => result && onOpenResult(result, resultIdx)}
                            disabled={!result}
                            className="text-left rounded-xl border border-slate-200 bg-slate-50 p-4 hover:border-emerald-300 hover:bg-emerald-50 transition-all disabled:hover:border-slate-200 disabled:hover:bg-slate-50 disabled:cursor-default"
                        >
                            <div className="flex items-center justify-between gap-2 mb-2">
                                <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                                    Fonte {citation.index}
                                </span>
                                <span className="px-2 py-0.5 rounded-md bg-white border border-slate-200 text-[9px] font-black uppercase tracking-widest text-slate-600">
                                    {pageLabel}
                                </span>
                            </div>
                            <p className="text-xs font-black text-slate-900 line-clamp-2 mb-2">
                                {citation.title || result?.title || 'Documento recuperado'}
                            </p>
                            {citation.text && (
                                <p className="text-xs leading-relaxed text-slate-600 line-clamp-4">
                                    {citation.text}
                                </p>
                            )}
                            {result && (
                                <span className="inline-flex mt-3 text-[9px] font-black uppercase tracking-widest text-emerald-700">
                                    Abrir documento
                                </span>
                            )}
                        </button>
                    );
                })}
            </div>
        </section>
    );
};

const KnowledgeCard: React.FC<{
    result: KnowledgeResult;
    index: number;
    focused: boolean;
    onClick: () => void;
}> = ({ result, index, focused, onClick }) => (
    <button
        id={`kg-card-${index + 1}`}
        onClick={onClick}
        className={`text-left bg-white rounded-2xl border transition-all p-5 flex flex-col gap-3 hover:-translate-y-0.5 active:scale-[0.99] ${
            focused
                ? 'border-emerald-500 shadow-[0_20px_50px_-10px_rgba(16,185,129,0.35)] ring-2 ring-emerald-300'
                : 'border-slate-200 hover:border-slate-400 hover:shadow-xl'
        }`}
    >
        <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2">
                <div
                    className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                        result.type === 'node' ? 'bg-indigo-50 text-indigo-700' : 'bg-amber-50 text-amber-700'
                    }`}
                >
                    <TypeIcon type={result.type} className="w-4 h-4" />
                </div>
                <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">
                    [{index + 1}] {TYPE_LABEL[result.type] || result.type}
                </span>
            </div>
            {formatResultDate(result.date) && (
                <span className="text-[10px] font-bold text-slate-400 whitespace-nowrap">
                    {formatResultDate(result.date)}
                </span>
            )}
        </div>

        {result.file_search?.store_name && (
            <div className="inline-flex w-fit items-center gap-1.5 rounded-md bg-emerald-50 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-emerald-700">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                File Search
                {result.file_search.status === 'pendente' ? ' pendente' : ''}
            </div>
        )}

        <h3 className="text-sm font-black tracking-tight text-slate-900 line-clamp-2">
            {result.title || '(sem título)'}
        </h3>

        <p className="text-xs text-slate-600 leading-relaxed line-clamp-3">
            {result.snippet}
        </p>

        {(result.tags?.length || result.area_tematica) && (
            <div className="flex flex-wrap gap-1 mt-auto pt-2 border-t border-slate-100">
                {result.area_tematica && (
                    <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[9px] font-black uppercase tracking-widest">
                        {result.area_tematica}
                    </span>
                )}
                {result.tags?.slice(0, 4).map((t) => (
                    <span
                        key={t}
                        className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 text-[9px] font-bold uppercase tracking-wider"
                    >
                        {t}
                    </span>
                ))}
                {result.tags && result.tags.length > 4 && (
                    <span className="text-[9px] font-bold text-slate-400">+{result.tags.length - 4}</span>
                )}
            </div>
        )}
    </button>
);

// ─── Gaveta lateral ──────────────────────────────────────────────────────────

const KnowledgeDrawer: React.FC<{
    item: KnowledgeResult | null;
    onClose: () => void;
    onNavigateToOrigin?: (modulo: string, id: string) => void;
}> = ({ item, onClose, onNavigateToOrigin }) => {
    const [tab, setTab] = useState<'original' | 'raio-x'>('original');
    const [rawText, setRawText] = useState<string | null>(null);
    const [rawAviso, setRawAviso] = useState<string | null>(null);
    const [rawLoading, setRawLoading] = useState(false);
    const [rawError, setRawError] = useState<string | null>(null);

    // Reset ao trocar de item
    useEffect(() => {
        setTab('original');
        setRawText(null);
        setRawAviso(null);
        setRawError(null);
    }, [item?.id]);

    // Lazy-load quando abre o Raio-X
    useEffect(() => {
        if (!item || tab !== 'raio-x' || rawText !== null || rawLoading) return;
        let cancelled = false;
        setRawLoading(true);
        setRawError(null);
        getArtefatoRawText(item.id, item.type)
            .then((res) => {
                if (cancelled) return;
                setRawText(res.texto_bruto || '');
                setRawAviso(res.aviso || null);
            })
            .catch((e) => {
                if (cancelled) return;
                setRawError(e?.message || 'Falha ao carregar texto bruto.');
            })
            .finally(() => {
                if (!cancelled) setRawLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [item, tab, rawText, rawLoading]);

    // Fecha com ESC
    useEffect(() => {
        if (!item) return;
        const handler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [item, onClose]);

    if (!item) return null;

    const drivePreviewUrl =
        item.type === 'artefato' && item.drive_file_id
            ? `https://drive.google.com/file/d/${item.drive_file_id}/preview`
            : null;

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-[70] animate-in fade-in duration-200"
                onClick={onClose}
            />
            {/* Drawer */}
            <aside
                className="fixed top-0 right-0 h-full w-full md:w-[45%] min-w-[320px] max-w-[720px] bg-white z-[71] shadow-[0_0_60px_rgba(0,0,0,0.25)] flex flex-col animate-in slide-in-from-right duration-300"
                role="dialog"
                aria-label="Detalhes do item de conhecimento"
            >
                {/* Header */}
                <header className="px-6 py-4 border-b border-slate-200 flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                            <span
                                className={`px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest ${
                                    item.type === 'node'
                                        ? 'bg-indigo-100 text-indigo-700'
                                        : 'bg-amber-100 text-amber-700'
                                }`}
                            >
                                {TYPE_LABEL[item.type] || item.type}
                            </span>
                            {item.area_tematica && (
                                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[9px] font-black uppercase tracking-widest">
                                    {item.area_tematica}
                                </span>
                            )}
                            {item.file_search?.store_name && (
                                <span className="px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-700 text-[9px] font-black uppercase tracking-widest">
                                    File Search
                                </span>
                            )}
                        </div>
                        <h2 className="text-base font-black tracking-tight text-slate-900 line-clamp-2">
                            {item.title || '(sem título)'}
                        </h2>
                    </div>
                    <button
                        onClick={onClose}
                        className="flex-shrink-0 w-9 h-9 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-all active:scale-95"
                        aria-label="Fechar"
                    >
                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                            <path d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </header>

                {/* Tabs */}
                <div className="flex border-b border-slate-200 px-6">
                    <button
                        onClick={() => setTab('original')}
                        className={`px-4 py-3 text-[10px] font-black uppercase tracking-widest transition-all ${
                            tab === 'original'
                                ? 'text-slate-900 border-b-2 border-slate-900'
                                : 'text-slate-400 hover:text-slate-600'
                        }`}
                    >
                        Documento Original
                    </button>
                    <button
                        onClick={() => setTab('raio-x')}
                        className={`px-4 py-3 text-[10px] font-black uppercase tracking-widest transition-all ${
                            tab === 'raio-x'
                                ? 'text-slate-900 border-b-2 border-slate-900'
                                : 'text-slate-400 hover:text-slate-600'
                        }`}
                    >
                        Raio-X da IA
                    </button>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto">
                    {tab === 'original' && (
                        <div className="h-full flex flex-col">
                            {item.type === 'artefato' && drivePreviewUrl ? (
                                <iframe
                                    src={drivePreviewUrl}
                                    className="w-full flex-1 border-0"
                                    title={item.title}
                                    allow="autoplay"
                                />
                            ) : item.type === 'artefato' ? (
                                <div className="p-6 text-sm text-slate-600">
                                    <p className="mb-3">Não foi possível montar o preview do Drive.</p>
                                    {item.drive_url && (
                                        <a
                                            href={item.drive_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="inline-flex items-center gap-2 text-emerald-700 font-bold hover:underline"
                                        >
                                            Abrir no Drive
                                            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <path d="M7 17L17 7M7 7h10v10" />
                                            </svg>
                                        </a>
                                    )}
                                </div>
                            ) : (
                                // Nó Conceitual
                                <div className="p-6">
                                    <div className="mb-6">
                                        <h3 className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-400 mb-2">
                                            Resumo técnico
                                        </h3>
                                        <p className="text-sm leading-relaxed text-slate-700 whitespace-pre-wrap">
                                            {item.resumo_semantico || item.snippet || '(sem resumo)'}
                                        </p>
                                    </div>

                                    {item.task_ids && item.task_ids.length > 0 && (
                                        <div>
                                            <h3 className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-400 mb-3">
                                                Tarefas que compõem este nó ({item.task_ids.length})
                                            </h3>
                                            <div className="flex flex-col gap-2">
                                                {item.task_ids.map((tid) => (
                                                    <button
                                                        key={tid}
                                                        onClick={() =>
                                                            onNavigateToOrigin?.('acoes', tid)
                                                        }
                                                        className="group flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-slate-200 hover:border-emerald-400 hover:bg-emerald-50 transition-all text-left"
                                                    >
                                                        <span className="text-xs font-bold text-slate-700 group-hover:text-emerald-900 truncate">
                                                            Tarefa #{tid}
                                                        </span>
                                                        <svg
                                                            className="w-4 h-4 text-slate-400 group-hover:text-emerald-600 flex-shrink-0"
                                                            viewBox="0 0 24 24"
                                                            fill="none"
                                                            stroke="currentColor"
                                                            strokeWidth="2.5"
                                                        >
                                                            <path d="M9 5l7 7-7 7" />
                                                        </svg>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {tab === 'raio-x' && (
                        <div className="p-6">
                            <section className="mb-6">
                                <h3 className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-400 mb-2">
                                    Resumo semântico
                                </h3>
                                <p className="text-sm leading-relaxed text-slate-700 whitespace-pre-wrap">
                                    {item.resumo_semantico || item.snippet || '(sem resumo)'}
                                </p>
                            </section>

                            <section>
                                <h3 className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-400 mb-2">
                                    {item.type === 'node' ? 'Texto de base' : 'Texto extraído (OCR)'}
                                </h3>

                                {rawLoading && (
                                    <div className="flex items-center gap-3 text-sm text-slate-500 py-8">
                                        <div className="w-4 h-4 rounded-full border-2 border-slate-300 border-t-slate-900 animate-spin" />
                                        Carregando texto bruto…
                                    </div>
                                )}

                                {rawError && (
                                    <p className="text-sm text-rose-600 py-4">{rawError}</p>
                                )}

                                {rawAviso && (
                                    <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3">
                                        {rawAviso}
                                    </p>
                                )}

                                {rawText !== null && rawText.length > 0 && (
                                    <pre className="text-xs leading-relaxed text-slate-700 whitespace-pre-wrap font-sans bg-slate-50 border border-slate-200 rounded-lg p-4 max-h-[60vh] overflow-y-auto">
                                        {rawText}
                                    </pre>
                                )}

                                {rawText !== null && rawText.length === 0 && !rawAviso && !rawError && (
                                    <p className="text-sm text-slate-400 py-4">
                                        Nenhum texto bruto disponível para este item.
                                    </p>
                                )}
                            </section>
                        </div>
                    )}
                </div>
            </aside>
        </>
    );
};

// ─── KnowledgeView ───────────────────────────────────────────────────────────

const KnowledgeView: React.FC<KnowledgeViewProps> = ({ onNavigateToOrigin }) => {

    useEffect(() => {
        const handleOpenNode = (e: any) => {
            const kgId = e.detail;
            setQuery(`ID_DIRETO_BUSCA:${kgId}`); // Assuming smart search doesn't natively support ID lookup, but we can intercept or just show raw node if we had it.
            // Wait, we can fetch directly from db
            setTimeout(async () => {
                try {
                     const { doc, getDoc } = await import('firebase/firestore');
                     const { db } = await import('./firebase');
                     const nodeRef = doc(db, 'conhecimento_mestre', kgId);
                     const nodeSnap = await getDoc(nodeRef);
                     if (nodeSnap.exists()) {

                         const data = nodeSnap.data() as KnowledgeNode;
                         setDrawerItem({
                            id: data.id || kgId,
                            type: 'node',
                            title: data.titulo,
                            snippet: data.conteudo_regra || '',
                            resumo_semantico: data.conteudo_regra || '',
                            tags: data.tags || [],
                            date: data.data_criacao,
                            area_tematica: data.area_tematica,
                            origem: data.origem,
                            task_id: data.task_origin_id
                         });

                     }
                } catch(err) {
                     console.error("Failed to load specific node via ID", err);
                }
            }, 100);
        };
        window.addEventListener('knowledge-view-open-node', handleOpenNode);
        return () => window.removeEventListener('knowledge-view-open-node', handleOpenNode);
    }, []);

    const [mode, setMode] = useState<'search' | 'audit'>('search');
    const [query, setQuery] = useState('');
    const [filtros, setFiltros] = useState<KnowledgeFilters>({ tipo: 'all' });
    const [tagInput, setTagInput] = useState('');

    const [loading, setLoading] = useState(false);
    const [loadingMsgIdx, setLoadingMsgIdx] = useState(0);
    const [intent, setIntent] = useState<KnowledgeIntent | null>(null);
    const [synthesis, setSynthesis] = useState<string>('');
    const [fileSearchCitations, setFileSearchCitations] = useState<FileSearchCitation[]>([]);
    const [results, setResults] = useState<KnowledgeResult[]>([]);
    const [error, setError] = useState<string | null>(null);

    const [drawerItem, setDrawerItem] = useState<KnowledgeResult | null>(null);
    const [focusedIdx, setFocusedIdx] = useState<number | null>(null);
    const [memoryNodes, setMemoryNodes] = useState<MemoryAuditItem[]>([]);
    const [selectedMemoryId, setSelectedMemoryId] = useState<string | null>(null);
    const [memoryDraft, setMemoryDraft] = useState('');
    const [soulDraft, setSoulDraft] = useState('');
    const [auditStatus, setAuditStatus] = useState<string | null>(null);

    const inputRef = useRef<HTMLInputElement>(null);

    const selectedMemory = useMemo(
        () => memoryNodes.find((item) => item.id === selectedMemoryId) || null,
        [memoryNodes, selectedMemoryId]
    );

    // Rotação de mensagens de loading
    useEffect(() => {
        if (!loading) return;
        const timer = window.setInterval(() => {
            setLoadingMsgIdx((i) => (i + 1) % LOADING_MESSAGES.length);
        }, 1400);
        return () => window.clearInterval(timer);
    }, [loading]);

    useEffect(() => {
        const unsubNodes = onSnapshot(collection(db, 'knowledge_nodes'), (snapshot) => {
            const items = snapshot.docs
                .map((snap) => ({ id: snap.id, ...(snap.data() as any) }))
                .filter((item) => item.tipo === 'regra_global' || item.tipo === 'fato_isolado')
                .sort((a, b) =>
                    String(b.data_atualizacao || b.data_criacao || '').localeCompare(
                        String(a.data_atualizacao || a.data_criacao || '')
                    )
                ) as MemoryAuditItem[];
            setMemoryNodes(items);
            if (!selectedMemoryId && items.length > 0) {
                setSelectedMemoryId(items[0].id);
            }
        });

        const unsubSoul = onSnapshot(doc(db, 'system', 'copilot_soul'), (snap) => {
            const data = snap.data() as any;
            setSoulDraft((data?.content as string) || '');
        });

        return () => {
            unsubNodes();
            unsubSoul();
        };
    }, []);

    useEffect(() => {
        setMemoryDraft(selectedMemory?.texto_memoria || '');
    }, [selectedMemory]);

    const runSearch = useCallback(async () => {
        const q = query.trim();
        if (!q || loading) return;
        setLoading(true);
        setError(null);
        setSynthesis('');
        setFileSearchCitations([]);
        setIntent(null);
        setFocusedIdx(null);
        setLoadingMsgIdx(0);
        try {
            const res = await smartSearchKG(q, filtros);
            setIntent(res.intent);
            setResults(res.results || []);
            setSynthesis(res.synthesis || '');
            setFileSearchCitations(res.file_search?.citations || []);
        } catch (e: any) {
            setError(e?.message || 'Falha na busca.');
            setResults([]);
            setFileSearchCitations([]);
        } finally {
            setLoading(false);
        }
    }, [query, filtros, loading]);

    const handleCitationClick = useCallback(
        (n: number) => {
            const idx = n - 1;
            const item = results[idx];
            if (!item) return;
            setFocusedIdx(idx);
            setDrawerItem(item);
            // Scroll suave até o card (usa requestAnimationFrame para garantir render)
            requestAnimationFrame(() => {
                const el = document.getElementById(`kg-card-${n}`);
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            });
        },
        [results]
    );

    const handleOpenResult = useCallback((item: KnowledgeResult, index: number) => {
        setFocusedIdx(index);
        setDrawerItem(item);
        requestAnimationFrame(() => {
            const el = document.getElementById(`kg-card-${index + 1}`);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
    }, []);

    const handleAddTag = () => {
        const t = tagInput.trim();
        if (!t) return;
        const current = filtros.tags || [];
        if (current.includes(t)) return;
        setFiltros({ ...filtros, tags: [...current, t] });
        setTagInput('');
    };

    const handleRemoveTag = (t: string) => {
        setFiltros({ ...filtros, tags: (filtros.tags || []).filter((x) => x !== t) });
    };

    const setTipo = (tipo: 'all' | 'node' | 'artefato') => {
        setFiltros({ ...filtros, tipo });
    };

    const setArea = (area: string | undefined) => {
        setFiltros({ ...filtros, area_tematica: area });
    };

    const saveSoul = useCallback(async () => {
        await setDoc(
            doc(db, 'system', 'copilot_soul'),
            {
                content: soulDraft.trim(),
                updated_at: new Date().toISOString(),
                source: 'knowledge_view_manual',
            },
            { merge: true }
        );
        setAuditStatus('Personalidade dinâmica atualizada.');
    }, [soulDraft]);

    const saveMemory = useCallback(async () => {
        if (!selectedMemoryId) return;
        await setDoc(
            doc(db, 'knowledge_nodes', selectedMemoryId),
            {
                texto_memoria: memoryDraft.trim(),
                resumo: memoryDraft.trim().slice(0, 600),
                titulo: memoryDraft.trim().slice(0, 72) || 'Memória global',
                data_atualizacao: new Date().toISOString(),
                origem_memoria: 'knowledge_view_manual',
            },
            { merge: true }
        );
        setAuditStatus('Memória global salva manualmente.');
    }, [memoryDraft, selectedMemoryId]);

    const deleteMemory = useCallback(async () => {
        if (!selectedMemoryId) return;
        await deleteDoc(doc(db, 'knowledge_nodes', selectedMemoryId));
        setSelectedMemoryId(null);
        setMemoryDraft('');
        setAuditStatus('Memória removida.');
    }, [selectedMemoryId]);

    return (
        <div className="w-full h-full bg-slate-50 overflow-y-auto">
            <div className="max-w-6xl mx-auto px-4 md:px-8 py-8 md:py-12 pb-32">
                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-2xl md:text-3xl font-black tracking-tight text-slate-900 mb-1">
                        Conhecimento
                    </h1>
                    <p className="text-xs md:text-sm text-slate-500 font-medium">
                        Pergunte ou busque por documentos, procedimentos e tarefas já cristalizadas.
                    </p>
                </div>
                <div className="mb-6 flex gap-2">
                    <Chip active={mode === 'search'} onClick={() => setMode('search')}>
                        Busca Semântica
                    </Chip>
                    <Chip active={mode === 'audit'} onClick={() => setMode('audit')}>
                        Auditoria de Memória
                    </Chip>
                </div>

                {mode === 'search' ? (
                    <>
                        <div className="mb-4">
                            <div className="relative">
                                <svg
                                    className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2.5"
                                >
                                    <circle cx="11" cy="11" r="7" />
                                    <path d="M21 21l-4.3-4.3" />
                                </svg>
                                <input
                                    ref={inputRef}
                                    type="text"
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') runSearch();
                                    }}
                                    placeholder='Ex.: "Como elaboramos o relatório de gestão 2025?" ou "dispensa licitação PNAE"'
                                    className="w-full h-14 md:h-16 pl-14 pr-28 rounded-2xl bg-white border border-slate-200 text-sm md:text-base font-medium tracking-tight text-slate-900 placeholder-slate-400 shadow-sm focus:outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10 transition-all"
                                />
                                <button
                                    onClick={runSearch}
                                    disabled={loading || !query.trim()}
                                    className="absolute right-2 top-1/2 -translate-y-1/2 px-5 h-10 md:h-11 rounded-xl bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-95"
                                >
                                    Buscar
                                </button>
                            </div>
                        </div>

                        <div className="mb-8 flex flex-wrap items-center gap-2">
                            <span className="text-[9px] font-black uppercase tracking-[0.25em] text-slate-400 mr-1">
                                Tipo
                            </span>
                            <Chip active={filtros.tipo === 'all' || !filtros.tipo} onClick={() => setTipo('all')}>
                                Todos
                            </Chip>
                            <Chip active={filtros.tipo === 'node'} onClick={() => setTipo('node')}>
                                Nós
                            </Chip>
                            <Chip active={filtros.tipo === 'artefato'} onClick={() => setTipo('artefato')}>
                                Documentos
                            </Chip>

                            <span className="text-[9px] font-black uppercase tracking-[0.25em] text-slate-400 ml-3 mr-1">
                                Área
                            </span>
                            <Chip active={!filtros.area_tematica} onClick={() => setArea(undefined)}>
                                Todas
                            </Chip>
                            {AREAS_TEMATICAS.map((a) => (
                                <Chip key={a} active={filtros.area_tematica === a} onClick={() => setArea(a)}>
                                    {a}
                                </Chip>
                            ))}

                            <span className="text-[9px] font-black uppercase tracking-[0.25em] text-slate-400 ml-3 mr-1">
                                Data
                            </span>
                            <input
                                type="date"
                                value={filtros.data_inicio || ''}
                                onChange={(e) =>
                                    setFiltros({ ...filtros, data_inicio: e.target.value || undefined })
                                }
                                className="px-3 py-1.5 rounded-full bg-white border border-slate-200 text-[10px] font-bold text-slate-700 focus:outline-none focus:border-slate-900"
                            />
                            <span className="text-[10px] text-slate-400 font-black">→</span>
                            <input
                                type="date"
                                value={filtros.data_fim || ''}
                                onChange={(e) => setFiltros({ ...filtros, data_fim: e.target.value || undefined })}
                                className="px-3 py-1.5 rounded-full bg-white border border-slate-200 text-[10px] font-bold text-slate-700 focus:outline-none focus:border-slate-900"
                            />
                        </div>

                        {(filtros.tags?.length || 0) > 0 && (
                            <div className="mb-6 flex flex-wrap items-center gap-2">
                                <span className="text-[9px] font-black uppercase tracking-[0.25em] text-slate-400 mr-1">
                                    Tags ativas
                                </span>
                                {filtros.tags?.map((t) => (
                                    <span
                                        key={t}
                                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-black uppercase tracking-widest"
                                    >
                                        {t}
                                        <button
                                            onClick={() => handleRemoveTag(t)}
                                            className="hover:text-emerald-900"
                                            aria-label={`Remover tag ${t}`}
                                        >
                                            <svg
                                                className="w-3 h-3"
                                                viewBox="0 0 24 24"
                                                fill="none"
                                                stroke="currentColor"
                                                strokeWidth="3"
                                            >
                                                <path d="M6 18L18 6M6 6l12 12" />
                                            </svg>
                                        </button>
                                    </span>
                                ))}
                            </div>
                        )}
                        <div className="mb-8 flex items-center gap-2">
                            <input
                                type="text"
                                value={tagInput}
                                onChange={(e) => setTagInput(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        e.preventDefault();
                                        handleAddTag();
                                    }
                                }}
                                placeholder="+ adicionar tag"
                                className="px-3 py-1.5 rounded-full bg-white border border-slate-200 text-[10px] font-bold text-slate-700 placeholder-slate-400 focus:outline-none focus:border-slate-900"
                            />
                            <button
                                onClick={handleAddTag}
                                disabled={!tagInput.trim()}
                                className="px-3 py-1.5 rounded-full bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest disabled:opacity-30 transition-all active:scale-95"
                            >
                                Adicionar
                            </button>
                        </div>

                        {loading && (
                            <div className="bg-white rounded-2xl border border-slate-200 p-8 mb-6 flex items-center gap-4 shadow-sm">
                                <div className="w-6 h-6 rounded-full border-2 border-slate-200 border-t-slate-900 animate-spin flex-shrink-0" />
                                <div>
                                    <div className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-400 mb-1">
                                        Processando
                                    </div>
                                    <div className="text-sm font-bold text-slate-900">
                                        {LOADING_MESSAGES[loadingMsgIdx]}
                                    </div>
                                </div>
                            </div>
                        )}

                        {error && !loading && (
                            <div className="bg-rose-50 border border-rose-200 rounded-2xl p-5 mb-6">
                                <p className="text-sm font-bold text-rose-700">{error}</p>
                            </div>
                        )}

                        {!loading && synthesis && (
                            <div className="mb-8">
                                <SynthesisBlock text={synthesis} onCitationClick={handleCitationClick} />
                                <FileSearchCitationsBlock
                                    citations={fileSearchCitations}
                                    results={results}
                                    onOpenResult={handleOpenResult}
                                />
                            </div>
                        )}

                        {!loading && results.length > 0 && (
                            <div>
                                <div className="flex items-center justify-between mb-4">
                                    <h2 className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-500">
                                        {results.length} resultado{results.length === 1 ? '' : 's'}
                                        {intent && (
                                            <span className="ml-2 px-2 py-0.5 rounded-md bg-slate-100 text-slate-600">
                                                {intent === 'SINTESE_PROFUNDA' ? 'síntese' : 'busca'}
                                            </span>
                                        )}
                                    </h2>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {results.map((r, i) => (
                                        <KnowledgeCard
                                            key={r.id}
                                            result={r}
                                            index={i}
                                            focused={focusedIdx === i}
                                            onClick={() => {
                                                setDrawerItem(r);
                                                setFocusedIdx(i);
                                            }}
                                        />
                                    ))}
                                </div>
                            </div>
                        )}

                        {!loading && !error && results.length === 0 && (
                            <div className="text-center py-16 md:py-24">
                                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-slate-100 flex items-center justify-center">
                                    <svg
                                        className="w-8 h-8 text-slate-400"
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="currentColor"
                                        strokeWidth="2"
                                    >
                                        <circle cx="11" cy="11" r="7" />
                                        <path d="M21 21l-4.3-4.3" />
                                    </svg>
                                </div>
                                <p className="text-sm text-slate-500 font-medium">
                                    {query
                                        ? 'Nenhum resultado encontrado. Ajuste a consulta ou os filtros.'
                                        : 'Faça uma pergunta ou busque por palavras-chave.'}
                                </p>
                            </div>
                        )}
                    </>
                ) : (
                    <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-6">
                        <section className="bg-white rounded-3xl border border-slate-200 p-4 shadow-sm">
                            <div className="mb-4">
                                <h2 className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-500">
                                    Memórias globais
                                </h2>
                                <p className="text-xs text-slate-400 mt-1">
                                    Regras e fatos retidos pelo copiloto.
                                </p>
                            </div>
                            <div className="space-y-2 max-h-[65vh] overflow-y-auto pr-1">
                                {memoryNodes.map((item) => (
                                    <button
                                        key={item.id}
                                        onClick={() => setSelectedMemoryId(item.id)}
                                        className={`w-full text-left rounded-2xl border p-3 transition-all ${
                                            selectedMemoryId === item.id
                                                ? 'border-emerald-400 bg-emerald-50'
                                                : 'border-slate-200 hover:border-slate-300 bg-white'
                                        }`}
                                    >
                                        <div className="flex items-center justify-between gap-2 mb-2">
                                            <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">
                                                {item.tipo === 'regra_global' ? 'Regra Global' : 'Fato Isolado'}
                                            </span>
                                            <span className="text-[9px] text-slate-400 font-bold">
                                                {formatResultDate(item.data_atualizacao)}
                                            </span>
                                        </div>
                                        <p className="text-xs font-bold text-slate-800 line-clamp-2">
                                            {item.titulo || '(sem título)'}
                                        </p>
                                        <p className="text-xs text-slate-500 line-clamp-3 mt-1">
                                            {item.texto_memoria}
                                        </p>
                                    </button>
                                ))}
                                {memoryNodes.length === 0 && (
                                    <p className="text-sm text-slate-400 py-8 text-center">
                                        Nenhuma memória global auditável ainda.
                                    </p>
                                )}
                            </div>
                        </section>

                        <section className="space-y-6">
                            <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
                                <div className="flex items-center justify-between gap-4 mb-4">
                                    <div>
                                        <h2 className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-500">
                                            Copilot Soul
                                        </h2>
                                        <p className="text-xs text-slate-400 mt-1">
                                            Personalidade dinâmica editável pelo sistema ou manualmente.
                                        </p>
                                    </div>
                                    <button
                                        onClick={saveSoul}
                                        className="px-4 py-2 rounded-xl bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest"
                                    >
                                        Salvar Soul
                                    </button>
                                </div>
                                <textarea
                                    value={soulDraft}
                                    onChange={(e) => setSoulDraft(e.target.value)}
                                    className="w-full min-h-[180px] rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 focus:outline-none focus:border-slate-900"
                                    placeholder="Descreva o tom, o estilo e o nível de detalhamento desejados para o copiloto."
                                />
                            </div>

                            <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
                                <div className="flex items-center justify-between gap-4 mb-4">
                                    <div>
                                        <h2 className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-500">
                                            Memória Selecionada
                                        </h2>
                                        <p className="text-xs text-slate-400 mt-1">
                                            Edição manual da fonte de verdade global.
                                        </p>
                                    </div>
                                    <div className="flex gap-2">
                                        <button
                                            onClick={saveMemory}
                                            disabled={!selectedMemoryId}
                                            className="px-4 py-2 rounded-xl bg-emerald-600 text-white text-[10px] font-black uppercase tracking-widest disabled:opacity-40"
                                        >
                                            Salvar Memória
                                        </button>
                                        <button
                                            onClick={deleteMemory}
                                            disabled={!selectedMemoryId}
                                            className="px-4 py-2 rounded-xl bg-rose-600 text-white text-[10px] font-black uppercase tracking-widest disabled:opacity-40"
                                        >
                                            Excluir
                                        </button>
                                    </div>
                                </div>
                                <textarea
                                    value={memoryDraft}
                                    onChange={(e) => setMemoryDraft(e.target.value)}
                                    className="w-full min-h-[220px] rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 focus:outline-none focus:border-slate-900"
                                    placeholder="Selecione uma memória para editar o conteúdo consolidado."
                                />
                                {selectedMemory && (
                                    <div className="mt-4 flex flex-wrap gap-2">
                                        <span className="px-3 py-1 rounded-full bg-slate-100 text-[10px] font-black uppercase tracking-widest text-slate-600">
                                            {selectedMemory.id}
                                        </span>
                                        <span className="px-3 py-1 rounded-full bg-emerald-100 text-[10px] font-black uppercase tracking-widest text-emerald-700">
                                            {selectedMemory.tipo === 'regra_global' ? 'Regra Global' : 'Fato Isolado'}
                                        </span>
                                        {selectedMemory.memoria_status && (
                                            <span className="px-3 py-1 rounded-full bg-amber-100 text-[10px] font-black uppercase tracking-widest text-amber-700">
                                                {selectedMemory.memoria_status}
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>

                            {auditStatus && (
                                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-bold text-emerald-700">
                                    {auditStatus}
                                </div>
                            )}
                        </section>
                    </div>
                )}
            </div>

            {/* Drawer */}
            <KnowledgeDrawer
                item={drawerItem}
                onClose={() => setDrawerItem(null)}
                onNavigateToOrigin={onNavigateToOrigin}
            />
        </div>
    );
};

export default KnowledgeView;
