import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    QueryDocumentSnapshot, addDoc, arrayUnion, collection, doc, getDocs, limit,
    onSnapshot, orderBy, query, serverTimestamp, startAfter, updateDoc, where
} from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { getDownloadURL, ref as storageRef } from 'firebase/storage';
import { db, functions, storage } from './firebase';
import { Tarefa, WhatsappConsolidacao, WhatsappMessageDoc } from './types';
import { buildDiaryWhatsappNote } from './src/utils/diaryEntries';
import { HermesGlobalChat } from './src/components/tools/HermesGlobalChat';

interface WhatsappChatOption {
    chat_id: string;
    chat_name: string;
    is_group: boolean;
}

interface WhatsappInboxViewProps {
    tarefas: Tarefa[];
    userId: string;
    isDark?: boolean;
}

const PAGE_SIZE = 30;
const MAX_SELECTION = 200; // mesmo cap validado no backend (whatsapp_consolidation.py)
const AUDIO_TYPES = new Set(['ptt', 'audio']);
const IMAGE_TYPES = new Set(['image', 'sticker']);
const LIVE_CONTEXT_MAX_CHARS = 9000; // mesmo teto usado pelo Copiloto embutido de Reuniões
const LAST_SEEN_KEY_PREFIX = 'hermes_whatsapp_last_seen:';

const tsToDate = (ts: any): Date | null => (ts && typeof ts.toDate === 'function' ? ts.toDate() : null);

const fmtTime = (ts: any): string => {
    const d = tsToDate(ts);
    return d ? d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '--:--';
};

const fmtDay = (ts: any): string => {
    const d = tsToDate(ts);
    return d ? d.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: 'short' }) : '?';
};

const fmtShortDate = (iso?: string): string => {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d.getTime()) ? '' : d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
};

const WhatsappInboxView: React.FC<WhatsappInboxViewProps> = ({ tarefas, userId, isDark = false }) => {
    // Lista de chats
    const [chats, setChats] = useState<WhatsappChatOption[]>([]);
    const [isLoadingChats, setIsLoadingChats] = useState(true);
    const [chatsError, setChatsError] = useState<string | null>(null);
    const [chatSearch, setChatSearch] = useState('');
    const [selectedChatId, setSelectedChatId] = useState<string | null>(null);

    // Indicador de mensagem nova (bolinha verde): timestamp (ms) da última mensagem por chat,
    // comparado a "última vez que o usuário abriu esse chat" (persistido no localStorage —
    // app de usuário único, não precisa de estado compartilhado no Firestore para isso).
    const [lastMessageAt, setLastMessageAt] = useState<Record<string, number>>({});
    const lastSeenRef = useRef<Record<string, number>>({});
    const [, forceUnreadRerender] = useState(0);

    const getLastSeen = (chatId: string): number => {
        if (lastSeenRef.current[chatId] !== undefined) return lastSeenRef.current[chatId];
        let val = 0;
        try {
            const raw = localStorage.getItem(LAST_SEEN_KEY_PREFIX + chatId);
            val = raw ? parseInt(raw, 10) || 0 : 0;
        } catch { /* localStorage indisponível — trata como nunca visto */ }
        lastSeenRef.current[chatId] = val;
        return val;
    };

    const markSeen = (chatId: string, ts: number) => {
        if (lastSeenRef.current[chatId] === ts) return;
        lastSeenRef.current[chatId] = ts;
        try { localStorage.setItem(LAST_SEEN_KEY_PREFIX + chatId, String(ts)); } catch { /* ignora */ }
        forceUnreadRerender(v => v + 1);
    };

    // Timeline (página 1 viva + páginas antigas sob demanda — precedente PersonalDiaryView)
    const [liveDocs, setLiveDocs] = useState<QueryDocumentSnapshot[]>([]);
    const [olderDocs, setOlderDocs] = useState<QueryDocumentSnapshot[]>([]);
    const [isLoadingMessages, setIsLoadingMessages] = useState(false);
    const [isLoadingMore, setIsLoadingMore] = useState(false);
    const [hasMore, setHasMore] = useState(false);
    const [timelineError, setTimelineError] = useState<string | null>(null);

    // Seleção para consolidar
    const [selection, setSelection] = useState<Set<string>>(new Set());

    // Job/relatório ativo (assinado via onSnapshot) + histórico do chat
    const [activeJobId, setActiveJobId] = useState<string | null>(null);
    const [activeJob, setActiveJob] = useState<WhatsappConsolidacao | null>(null);
    const [pastJobs, setPastJobs] = useState<WhatsappConsolidacao[]>([]);
    const [showTranscript, setShowTranscript] = useState(false);

    // Terceira coluna: Copiloto Hermes (contexto = mensagens carregadas do chat aberto) ou
    // o relatório da consolidação ativa — abas dentro do mesmo painel, não colunas extras.
    const [isCopilotCollapsed, setIsCopilotCollapsed] = useState(false);
    const [thirdColumnTab, setThirdColumnTab] = useState<'copilot' | 'report'>('copilot');

    // Associação a ação
    const [taskSearch, setTaskSearch] = useState('');
    const [isAssociating, setIsAssociating] = useState(false);
    const [associationError, setAssociationError] = useState<string | null>(null);

    // Mídia carregada sob demanda (storage_path -> URL)
    const [mediaUrls, setMediaUrls] = useState<Record<string, string>>({});
    const [loadingMedia, setLoadingMedia] = useState<Set<string>>(new Set());

    const selectedChat = useMemo(() => chats.find(c => c.chat_id === selectedChatId) || null, [chats, selectedChatId]);

    // ── Chats ────────────────────────────────────────────────────────────────
    useEffect(() => {
        let cancelled = false;
        (async () => {
            setIsLoadingChats(true);
            setChatsError(null);
            try {
                const fn = httpsCallable(functions, 'listWhatsappChats');
                const res = await fn();
                if (cancelled) return;
                setChats(((res.data as { chats: WhatsappChatOption[] }).chats || []));
            } catch (e: any) {
                if (!cancelled) setChatsError(e?.message || 'Falha ao carregar conversas.');
            } finally {
                if (!cancelled) setIsLoadingChats(false);
            }
        })();
        return () => { cancelled = true; };
    }, []);

    // Última mensagem de cada chat (ao vivo) — alimenta a bolinha de "mensagem nova". Usa o
    // mesmo índice composto (chat_id+timestamp) já criado para a timeline, então não precisa
    // de nenhum índice novo.
    useEffect(() => {
        if (chats.length === 0) return;
        const unsubs = chats.map(chat => {
            const q = query(
                collection(db, 'whatsapp_messages'),
                where('chat_id', '==', chat.chat_id),
                orderBy('timestamp', 'desc'),
                limit(1)
            );
            return onSnapshot(q, snap => {
                const d = tsToDate(snap.docs[0]?.data()?.timestamp);
                if (!d) return;
                const ms = d.getTime();
                setLastMessageAt(prev => (prev[chat.chat_id] === ms ? prev : { ...prev, [chat.chat_id]: ms }));
            }, () => { /* sem permissão/índice ainda construindo — sem bolinha, sem quebrar a lista */ });
        });
        return () => unsubs.forEach(u => u());
    }, [chats]);

    // ── Timeline do chat selecionado ─────────────────────────────────────────
    useEffect(() => {
        setLiveDocs([]);
        setOlderDocs([]);
        setSelection(new Set());
        setActiveJobId(null);
        setThirdColumnTab('copilot');
        setTimelineError(null);
        setMediaUrls({});
        if (!selectedChatId) return;

        setIsLoadingMessages(true);
        const q = query(
            collection(db, 'whatsapp_messages'),
            where('chat_id', '==', selectedChatId),
            orderBy('timestamp', 'desc'),
            limit(PAGE_SIZE)
        );
        const unsubscribe = onSnapshot(q, snap => {
            setLiveDocs(snap.docs);
            setHasMore(snap.docs.length === PAGE_SIZE);
            setIsLoadingMessages(false);
        }, err => {
            setTimelineError(err?.message || 'Falha ao carregar mensagens.');
            setIsLoadingMessages(false);
        });
        return () => unsubscribe();
    }, [selectedChatId]);

    // Marca o chat aberto como "visto" até a mensagem mais recente conhecida — some a bolinha
    // ao entrar na conversa e some de novo automaticamente se chegar mensagem nova depois.
    useEffect(() => {
        if (!selectedChatId) return;
        const latest = lastMessageAt[selectedChatId];
        if (latest) markSeen(selectedChatId, latest);
    }, [selectedChatId, lastMessageAt[selectedChatId || '']]);

    // Histórico de consolidações do chat
    useEffect(() => {
        setPastJobs([]);
        if (!selectedChatId) return;
        const q = query(
            collection(db, 'whatsapp_consolidacoes'),
            where('chat_id', '==', selectedChatId),
            orderBy('requested_at', 'desc'),
            limit(20)
        );
        const unsubscribe = onSnapshot(q, snap => {
            setPastJobs(snap.docs.map(d => ({ id: d.id, ...(d.data() as any) })) as WhatsappConsolidacao[]);
        }, () => { /* índice ainda construindo — histórico fica vazio, sem quebrar a view */ });
        return () => unsubscribe();
    }, [selectedChatId]);

    // Job ativo (progresso/resultado ao vivo)
    useEffect(() => {
        setActiveJob(null);
        setShowTranscript(false);
        setTaskSearch('');
        setAssociationError(null);
        if (!activeJobId) return;
        const unsubscribe = onSnapshot(doc(db, 'whatsapp_consolidacoes', activeJobId), snap => {
            if (snap.exists()) setActiveJob({ id: snap.id, ...(snap.data() as any) } as WhatsappConsolidacao);
        });
        return () => unsubscribe();
    }, [activeJobId]);

    const loadMore = async () => {
        if (isLoadingMore || !selectedChatId) return;
        const cursor = olderDocs.length > 0 ? olderDocs[olderDocs.length - 1] : liveDocs[liveDocs.length - 1];
        if (!cursor) return;
        setIsLoadingMore(true);
        try {
            const q = query(
                collection(db, 'whatsapp_messages'),
                where('chat_id', '==', selectedChatId),
                orderBy('timestamp', 'desc'),
                startAfter(cursor),
                limit(PAGE_SIZE)
            );
            const snap = await getDocs(q);
            setOlderDocs(prev => [...prev, ...snap.docs]);
            setHasMore(snap.docs.length === PAGE_SIZE);
        } finally {
            setIsLoadingMore(false);
        }
    };

    // Mensagens em ordem cronológica (mais antiga primeiro) para exibição estilo chat.
    const messages: WhatsappMessageDoc[] = useMemo(() => {
        const all = [...olderDocs.slice().reverse(), ...liveDocs.slice().reverse()];
        return all.map(d => ({ id: d.id, ...(d.data() as any) })) as WhatsappMessageDoc[];
    }, [liveDocs, olderDocs]);

    // Refs para o Copiloto embutido: liveContextProvider precisa ser estável (useCallback com
    // deps vazias, mesmo padrão do MeetingTranscriptionTool) e ler sempre o valor mais recente
    // via ref — não pode depender de `messages`/`selectedChat` diretamente, porque essa função
    // não remonta quando o chat muda (só o HermesGlobalChat remonta, via `key`).
    const messagesRef = useRef<WhatsappMessageDoc[]>([]);
    useEffect(() => { messagesRef.current = messages; }, [messages]);
    const selectedChatRef = useRef<WhatsappChatOption | null>(null);
    useEffect(() => { selectedChatRef.current = selectedChat; }, [selectedChat]);

    const liveContextProvider = useCallback((): string | null => {
        const msgs = messagesRef.current;
        if (msgs.length === 0) return null;
        const chatName = selectedChatRef.current?.chat_name || '';
        const header = `Conversa do WhatsApp com "${chatName}". Mensagens já carregadas nesta tela (Você = usuário; demais nomes = contato/grupo):`;
        const lines = msgs.map(m => {
            const d = tsToDate(m.timestamp);
            const time = d ? d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '?';
            const author = m.from_me ? 'Você' : (m.author_name || 'Contato');
            const text = m.transcription_text || m.content || `[${m.message_type}]`;
            return `[${time}] ${author}: ${text}`;
        });
        let body = lines.join('\n');
        if (body.length > LIVE_CONTEXT_MAX_CHARS) {
            body = `(...mensagens mais antigas omitidas por tamanho...)\n${body.slice(body.length - LIVE_CONTEXT_MAX_CHARS)}`;
        }
        return `${header}\n${body}`;
    }, []);

    const toggleSelect = (id: string) => {
        setSelection(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else if (next.size < MAX_SELECTION) next.add(id);
            return next;
        });
    };

    const selectAllVisible = () => {
        setSelection(prev => {
            const next = new Set(prev);
            for (const m of messages) {
                if (next.size >= MAX_SELECTION) break;
                next.add(m.id);
            }
            return next;
        });
    };

    const loadMedia = async (path: string) => {
        if (mediaUrls[path] || loadingMedia.has(path)) return;
        setLoadingMedia(prev => new Set(prev).add(path));
        try {
            const url = await getDownloadURL(storageRef(storage, path));
            setMediaUrls(prev => ({ ...prev, [path]: url }));
        } catch { /* mídia indisponível — botão continua, sem crash */ }
        finally {
            setLoadingMedia(prev => { const next = new Set(prev); next.delete(path); return next; });
        }
    };

    const openJob = (jobId: string) => {
        setActiveJobId(jobId);
        setThirdColumnTab('report');
        setIsCopilotCollapsed(false);
    };

    const startConsolidation = async () => {
        if (!selectedChat || selection.size === 0) return;
        const refDoc = await addDoc(collection(db, 'whatsapp_consolidacoes'), {
            chat_id: selectedChat.chat_id,
            chat_name: selectedChat.chat_name,
            is_group: selectedChat.is_group,
            message_ids: Array.from(selection),
            status: 'queued',
            requested_at: serverTimestamp(),
        });
        setSelection(new Set());
        openJob(refDoc.id);
    };

    // Pré-sugestões: ações com este chat vinculado (tarefas.whatsapp_vinculos).
    const suggestedTasks = useMemo(() => {
        if (!selectedChatId) return [] as Tarefa[];
        return tarefas.filter(t => t.status !== 'concluído' && (t.whatsapp_vinculos || []).some(v => v.chat_id === selectedChatId));
    }, [tarefas, selectedChatId]);

    const searchedTasks = useMemo(() => {
        const s = taskSearch.trim().toLowerCase();
        if (!s) return [] as Tarefa[];
        return tarefas
            .filter(t => t.status !== 'concluído' && t.titulo.toLowerCase().includes(s))
            .slice(0, 8);
    }, [tarefas, taskSearch]);

    const associateToTask = async (t: Tarefa) => {
        if (!activeJob || activeJob.status !== 'completed' || isAssociating) return;
        setIsAssociating(true);
        setAssociationError(null);
        try {
            const nowIso = new Date().toISOString();
            const periodo = [fmtShortDate(activeJob.periodo_inicio), fmtShortDate(activeJob.periodo_fim)]
                .filter(Boolean).join('–');
            const origem = `${activeJob.n_mensagens || 0} mensagem(ns)${periodo ? ` · ${periodo}` : ''}`;
            const nota = buildDiaryWhatsappNote(
                activeJob.chat_name,
                origem,
                activeJob.resumo || '',
                activeJob.itens_de_acao || [],
                activeJob.decisoes || [],
                activeJob.periodo_inicio,
                activeJob.periodo_fim,
                []
            );
            await updateDoc(doc(db, 'tarefas', t.id), {
                acompanhamento: arrayUnion({ data: nowIso, nota }),
                data_atualizacao: nowIso,
            });
            await updateDoc(doc(db, 'whatsapp_consolidacoes', activeJob.id), {
                task_id: t.id,
                task_titulo: t.titulo,
                applied_at: nowIso,
            });
            setTaskSearch('');
        } catch (e: any) {
            setAssociationError(e?.message || 'Falha ao registrar no diário da ação.');
        } finally {
            setIsAssociating(false);
        }
    };

    const filteredChats = useMemo(() => {
        const s = chatSearch.trim().toLowerCase();
        if (!s) return chats;
        return chats.filter(c => c.chat_name.toLowerCase().includes(s) || c.chat_id.toLowerCase().includes(s));
    }, [chats, chatSearch]);

    const cardCls = isDark ? 'border-white/10 bg-white/5' : 'border-slate-100 bg-white shadow-sm';
    const mutedCls = isDark ? 'text-white/40' : 'text-slate-400';

    // ── Render ───────────────────────────────────────────────────────────────
    const renderChatList = () => (
        <div className={`flex flex-col rounded-2xl border overflow-hidden ${cardCls}`}>
            <div className={`shrink-0 p-3 border-b ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                <input
                    type="text"
                    value={chatSearch}
                    onChange={e => setChatSearch(e.target.value)}
                    placeholder="Buscar conversa..."
                    className={`w-full px-3 py-2 rounded-xl border text-xs outline-none focus:ring-1 focus:ring-green-500 font-sans ${isDark ? 'bg-white/10 border-white/10 text-white placeholder:text-white/30' : 'bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-400'}`}
                />
            </div>
            <div className="flex-1 overflow-y-auto">
                {isLoadingChats ? (
                    <p className={`p-4 text-xs font-mono ${mutedCls}`}>Carregando conversas...</p>
                ) : chatsError ? (
                    <p className="p-4 text-xs text-rose-500">{chatsError}</p>
                ) : filteredChats.length === 0 ? (
                    <div className="p-4 space-y-1">
                        <p className={`text-xs font-bold ${isDark ? 'text-white/70' : 'text-slate-600'}`}>Nenhuma conversa monitorada.</p>
                        <p className={`text-[10px] ${mutedCls}`}>Adicione chats na allowlist em Configurações → Automações.</p>
                    </div>
                ) : (
                    filteredChats.map(chat => {
                        const unread = chat.chat_id !== selectedChatId
                            && !!lastMessageAt[chat.chat_id]
                            && lastMessageAt[chat.chat_id] > getLastSeen(chat.chat_id);
                        return (
                            <button
                                key={chat.chat_id}
                                onClick={() => setSelectedChatId(chat.chat_id)}
                                className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-colors ${selectedChatId === chat.chat_id
                                    ? (isDark ? 'bg-green-500/15' : 'bg-green-50')
                                    : (isDark ? 'hover:bg-white/5' : 'hover:bg-slate-50')}`}
                            >
                                <span className="text-base shrink-0">{chat.is_group ? '👥' : '👤'}</span>
                                <span className={`text-xs font-bold truncate font-sans flex-1 ${isDark ? 'text-white/90' : 'text-slate-800'}`}>{chat.chat_name}</span>
                                {unread && (
                                    <span className="shrink-0 w-2 h-2 rounded-full bg-green-500" title="Mensagem nova" />
                                )}
                            </button>
                        );
                    })
                )}
            </div>
        </div>
    );

    const renderMessageBubble = (msg: WhatsappMessageDoc, prevMsg: WhatsappMessageDoc | null) => {
        const showDay = !prevMsg || fmtDay(prevMsg.timestamp) !== fmtDay(msg.timestamp);
        const isAudio = AUDIO_TYPES.has(msg.message_type);
        const isImage = IMAGE_TYPES.has(msg.message_type);
        const storagePath = msg.media?.storage_path;
        const selected = selection.has(msg.id);
        const consolidated = (msg.consolidation_ids || []).length > 0;

        return (
            <React.Fragment key={msg.id}>
                {showDay && (
                    <p className={`text-center text-[10px] font-black uppercase tracking-[0.15em] py-2 ${mutedCls}`}>
                        {fmtDay(msg.timestamp)}
                    </p>
                )}
                <div className={`flex items-start gap-2 ${msg.from_me ? 'flex-row-reverse' : ''}`}>
                    <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleSelect(msg.id)}
                        className="mt-2 w-3.5 h-3.5 shrink-0 rounded border-slate-300 text-green-600 focus:ring-green-500 cursor-pointer"
                    />
                    <div className={`max-w-[78%] rounded-2xl px-3 py-2 text-xs font-sans border ${msg.from_me
                        ? (isDark ? 'bg-green-500/15 border-green-500/20 text-white/90' : 'bg-green-50 border-green-100 text-slate-800')
                        : (isDark ? 'bg-white/10 border-white/10 text-white/90' : 'bg-white border-slate-150 text-slate-800 shadow-sm')}
                        ${selected ? 'ring-1 ring-green-500' : ''}`}
                    >
                        <div className="flex items-center gap-2 mb-0.5">
                            <span className={`text-[10px] font-black ${isDark ? 'text-green-300' : 'text-green-700'}`}>
                                {msg.from_me ? 'Eu' : (msg.author_name || 'Contato')}
                            </span>
                            <span className={`text-[9px] ${mutedCls}`}>{fmtTime(msg.timestamp)}</span>
                            {consolidated && (
                                <span className="text-[8px] font-black uppercase tracking-wider px-1 py-0.5 rounded bg-indigo-500/15 text-indigo-400">consolidada</span>
                            )}
                        </div>

                        {isAudio ? (
                            <div className="space-y-1">
                                {storagePath ? (
                                    mediaUrls[storagePath] ? (
                                        <audio controls src={mediaUrls[storagePath]} className="max-w-full h-8" />
                                    ) : (
                                        <button onClick={() => loadMedia(storagePath)} className={`text-[10px] font-bold underline ${isDark ? 'text-green-300' : 'text-green-700'}`}>
                                            {loadingMedia.has(storagePath) ? 'Carregando áudio...' : '▶ Carregar áudio'}
                                        </button>
                                    )
                                ) : (
                                    <span className={`italic text-[10px] ${mutedCls}`}>[áudio não capturado]</span>
                                )}
                                {msg.transcription_text && (
                                    <p className={`text-[10px] leading-relaxed border-l-2 pl-2 ${isDark ? 'border-green-500/30 text-white/60' : 'border-green-200 text-slate-500'}`}>
                                        {msg.transcription_text}
                                    </p>
                                )}
                            </div>
                        ) : isImage ? (
                            <div className="space-y-1">
                                {storagePath ? (
                                    mediaUrls[storagePath] ? (
                                        <a href={mediaUrls[storagePath]} target="_blank" rel="noreferrer">
                                            <img src={mediaUrls[storagePath]} alt="imagem" className="max-h-48 rounded-lg" />
                                        </a>
                                    ) : (
                                        <button onClick={() => loadMedia(storagePath)} className={`text-[10px] font-bold underline ${isDark ? 'text-green-300' : 'text-green-700'}`}>
                                            {loadingMedia.has(storagePath) ? 'Carregando imagem...' : '🖼 Carregar imagem'}
                                        </button>
                                    )
                                ) : (
                                    <span className={`italic text-[10px] ${mutedCls}`}>[imagem não capturada]</span>
                                )}
                                {msg.content && <p className="whitespace-pre-line break-words">{msg.content}</p>}
                            </div>
                        ) : (
                            <p className="whitespace-pre-line break-words">
                                {msg.content || <span className={`italic ${mutedCls}`}>[{msg.message_type}]</span>}
                            </p>
                        )}
                    </div>
                </div>
            </React.Fragment>
        );
    };

    const renderTimeline = () => (
        <div className={`flex-1 flex flex-col rounded-2xl border overflow-hidden ${cardCls}`}>
            {/* Header do chat */}
            <div className={`shrink-0 px-4 py-3 border-b flex items-center justify-between gap-2 ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                <div className="flex items-center gap-2 min-w-0">
                    <button onClick={() => setSelectedChatId(null)} className={`md:hidden text-xs font-bold ${mutedCls}`}>←</button>
                    <span className="text-base">{selectedChat?.is_group ? '👥' : '👤'}</span>
                    <span className={`text-sm font-black truncate ${isDark ? 'text-white' : 'text-slate-800'}`}>{selectedChat?.chat_name}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    {isCopilotCollapsed && (
                        <button
                            onClick={() => setIsCopilotCollapsed(false)}
                            className={`hidden lg:flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-bold border ${isDark ? 'border-indigo-500/30 text-indigo-300 hover:bg-indigo-500/10' : 'border-indigo-200 text-indigo-700 hover:bg-indigo-50'}`}
                        >
                            <img src="/logo.png" alt="" className="h-3.5 w-3.5 object-contain" /> Copiloto
                        </button>
                    )}
                    {pastJobs.length > 0 && (
                        <select
                            value=""
                            onChange={e => { if (e.target.value) openJob(e.target.value); }}
                            className={`text-[10px] font-bold rounded-lg border px-1.5 py-1 max-w-[140px] ${isDark ? 'bg-white/10 border-white/10 text-white/70' : 'bg-slate-50 border-slate-200 text-slate-600'}`}
                        >
                            <option value="">Consolidações ({pastJobs.length})</option>
                            {pastJobs.map(j => {
                                const d = tsToDate(j.requested_at);
                                const label = `${d ? d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) : '?'} · ${j.n_mensagens || j.message_ids?.length || 0} msg${j.task_titulo ? ' ✓' : ''}`;
                                return <option key={j.id} value={j.id}>{label}</option>;
                            })}
                        </select>
                    )}
                </div>
            </div>

            {/* Mensagens */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1.5">
                {isLoadingMessages ? (
                    <p className={`text-xs font-mono ${mutedCls}`}>Carregando mensagens...</p>
                ) : timelineError ? (
                    <p className="text-xs text-rose-500">{timelineError}</p>
                ) : messages.length === 0 ? (
                    <p className={`text-xs ${mutedCls}`}>Nenhuma mensagem capturada nesta conversa ainda.</p>
                ) : (
                    <>
                        {hasMore && (
                            <button
                                onClick={loadMore}
                                disabled={isLoadingMore}
                                className={`mx-auto block rounded-lg border px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition disabled:opacity-50 ${isDark ? 'border-white/10 text-white/60 hover:bg-white/5' : 'border-slate-200 text-slate-500 hover:bg-slate-50'}`}
                            >
                                {isLoadingMore ? 'Carregando...' : 'Carregar mensagens anteriores'}
                            </button>
                        )}
                        {messages.map((m, i) => renderMessageBubble(m, i > 0 ? messages[i - 1] : null))}
                    </>
                )}
            </div>

            {/* Barra de seleção/consolidação */}
            <div className={`shrink-0 px-4 py-3 border-t flex items-center justify-between gap-3 ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                <div className="flex items-center gap-3">
                    <span className={`text-[10px] font-bold ${selection.size >= MAX_SELECTION ? 'text-amber-500' : mutedCls}`}>
                        {selection.size} selecionada(s){selection.size >= MAX_SELECTION ? ` (máx. ${MAX_SELECTION})` : ''}
                    </span>
                    <button onClick={selectAllVisible} className={`text-[10px] font-bold underline ${mutedCls}`}>Selecionar visíveis</button>
                    {selection.size > 0 && (
                        <button onClick={() => setSelection(new Set())} className={`text-[10px] font-bold underline ${mutedCls}`}>Limpar</button>
                    )}
                </div>
                <button
                    onClick={startConsolidation}
                    disabled={selection.size === 0}
                    className="px-4 py-2 rounded-xl text-xs font-black text-white bg-green-600 hover:bg-green-700 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                    Consolidar {selection.size > 0 ? `(${selection.size})` : ''}
                </button>
            </div>
        </div>
    );

    const renderReportBody = () => {
        if (!activeJob) {
            return <p className={`p-4 text-xs ${mutedCls}`}>Nenhuma consolidação selecionada.</p>;
        }
        const isDone = activeJob.status === 'completed';
        const isError = activeJob.status === 'error';
        const alreadyApplied = !!activeJob.task_id;

        return (
            <div className="flex-1 overflow-y-auto p-4 space-y-3 text-xs font-sans">
                {!isDone && !isError && (
                    <div className="flex items-center gap-2">
                        <span className="w-3 h-3 rounded-full border-2 border-green-500 border-t-transparent animate-spin" />
                        <span className={isDark ? 'text-white/70' : 'text-slate-600'}>{activeJob.progress || 'Na fila...'}</span>
                    </div>
                )}
                {isError && (
                    <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 text-rose-500 px-3 py-2">
                        {activeJob.error || 'Falha na consolidação.'}
                    </div>
                )}

                {isDone && (
                    <>
                        <div>
                            <p className={`text-[10px] font-black uppercase tracking-wider mb-1 ${mutedCls}`}>
                                Síntese (IA) · {activeJob.n_mensagens} msg · {activeJob.n_audios_transcritos || 0} áudio(s) transcrito(s)
                                {(activeJob.n_audios_ignorados || 0) > 0 ? ` · ${activeJob.n_audios_ignorados} ignorado(s)` : ''}
                            </p>
                            <p className={`leading-relaxed ${isDark ? 'text-white/85' : 'text-slate-700'}`}>{activeJob.resumo || '(sem resumo)'}</p>
                        </div>

                        {(activeJob.itens_de_acao || []).length > 0 && (
                            <div>
                                <p className={`text-[10px] font-black uppercase tracking-wider mb-1 ${mutedCls}`}>Itens de ação</p>
                                <ul className="space-y-1">
                                    {(activeJob.itens_de_acao || []).map((it, i) => (
                                        <li key={i} className={isDark ? 'text-white/80' : 'text-slate-700'}>
                                            • {it.descricao}{it.responsavel ? ` — ${it.responsavel}` : ''}{it.prazo ? ` (prazo ${it.prazo})` : ''}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {(activeJob.decisoes || []).length > 0 && (
                            <div>
                                <p className={`text-[10px] font-black uppercase tracking-wider mb-1 ${mutedCls}`}>Decisões</p>
                                <ul className="space-y-1">
                                    {(activeJob.decisoes || []).map((d, i) => (
                                        <li key={i} className={isDark ? 'text-white/80' : 'text-slate-700'}>• {d}</li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {(activeJob.attachments || []).length > 0 && (
                            <p className={`text-[10px] ${mutedCls}`}>{(activeJob.attachments || []).length} anexo(s) na seleção (visíveis na timeline).</p>
                        )}

                        <div>
                            <button onClick={() => setShowTranscript(s => !s)} className={`text-[10px] font-bold underline ${mutedCls}`}>
                                {showTranscript ? 'Ocultar transcript literal' : 'Ver transcript literal'}
                            </button>
                            {showTranscript && (
                                <pre className={`mt-2 p-2 rounded-lg text-[10px] leading-relaxed whitespace-pre-wrap break-words border ${isDark ? 'bg-black/30 border-white/10 text-white/70' : 'bg-slate-50 border-slate-150 text-slate-600'}`}>
                                    {activeJob.transcript_literal}
                                </pre>
                            )}
                        </div>

                        {/* Associação a ação */}
                        <div className={`pt-3 border-t space-y-2 ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                            {alreadyApplied ? (
                                <p className={`text-[11px] font-bold ${isDark ? 'text-green-300' : 'text-green-700'}`}>
                                    ✓ Registrada no diário de: {activeJob.task_titulo}
                                </p>
                            ) : (
                                <>
                                    <p className={`text-[10px] font-black uppercase tracking-wider ${mutedCls}`}>Registrar no diário de uma ação</p>
                                    {suggestedTasks.length > 0 && (
                                        <div className="space-y-1">
                                            {suggestedTasks.map(t => (
                                                <button
                                                    key={t.id}
                                                    onClick={() => associateToTask(t)}
                                                    disabled={isAssociating}
                                                    className={`w-full text-left px-2.5 py-1.5 rounded-lg border text-[11px] font-bold transition-colors disabled:opacity-50 ${isDark ? 'border-green-500/30 bg-green-500/10 text-green-300 hover:bg-green-500/20' : 'border-green-200 bg-green-50 text-green-700 hover:bg-green-100'}`}
                                                >
                                                    ⭐ {t.titulo}
                                                    <span className={`block text-[9px] font-medium ${mutedCls}`}>vinculada a esta conversa</span>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                    <input
                                        type="text"
                                        value={taskSearch}
                                        onChange={e => setTaskSearch(e.target.value)}
                                        placeholder="Buscar outra ação..."
                                        className={`w-full px-2.5 py-1.5 rounded-lg border text-[11px] outline-none focus:ring-1 focus:ring-green-500 ${isDark ? 'bg-white/10 border-white/10 text-white placeholder:text-white/30' : 'bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-400'}`}
                                    />
                                    {searchedTasks.length > 0 && (
                                        <div className={`rounded-lg border max-h-40 overflow-y-auto ${isDark ? 'border-white/10' : 'border-slate-150'}`}>
                                            {searchedTasks.map(t => (
                                                <button
                                                    key={t.id}
                                                    onClick={() => associateToTask(t)}
                                                    disabled={isAssociating}
                                                    className={`w-full text-left px-2.5 py-1.5 text-[11px] transition-colors disabled:opacity-50 ${isDark ? 'text-white/80 hover:bg-white/5' : 'text-slate-700 hover:bg-slate-50'}`}
                                                >
                                                    {t.titulo}
                                                    <span className={`ml-1.5 text-[9px] uppercase font-bold ${t.status === 'em andamento' ? 'text-green-500' : 'text-amber-500'}`}>{t.status}</span>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                    {associationError && <p className="text-[10px] text-rose-500">{associationError}</p>}
                                    {isAssociating && <p className={`text-[10px] ${mutedCls}`}>Registrando...</p>}
                                </>
                            )}
                        </div>
                    </>
                )}
            </div>
        );
    };

    // Terceira coluna: Copiloto Hermes (padrão) ou Relatório da consolidação ativa, em abas —
    // mesma "coluna do Copiloto" do split view de Reuniões (MeetingTranscriptionTool.tsx),
    // com liveContextProvider trocado pelas mensagens do WhatsApp em vez da transcrição ao vivo.
    const renderThirdColumn = () => {
        if (isCopilotCollapsed) return null; // botão de reabrir já fica no header da timeline

        return (
            <div className={`hidden lg:flex w-[26rem] shrink-0 flex-col rounded-2xl border overflow-hidden ${cardCls}`}>
                <div className={`shrink-0 px-3 py-2 border-b flex items-center justify-between gap-2 ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => setThirdColumnTab('copilot')}
                            className={`px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-wider transition-all ${thirdColumnTab === 'copilot' ? (isDark ? 'bg-indigo-500/20 text-indigo-300' : 'bg-indigo-100 text-indigo-700') : mutedCls}`}
                        >
                            Copiloto
                        </button>
                        {activeJobId && (
                            <button
                                onClick={() => setThirdColumnTab('report')}
                                className={`px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-wider transition-all ${thirdColumnTab === 'report' ? (isDark ? 'bg-green-500/20 text-green-300' : 'bg-green-100 text-green-700') : mutedCls}`}
                            >
                                Relatório
                            </button>
                        )}
                    </div>
                    <button onClick={() => setIsCopilotCollapsed(true)} className={`text-sm font-bold ${mutedCls} hover:text-rose-500`} title="Recolher">
                        &times;
                    </button>
                </div>

                {/* HermesGlobalChat fica sempre montado (troca só isOpen) enquanto o chat do WhatsApp
                    não muda — preserva a conversa do Copiloto ao alternar para a aba Relatório e
                    voltar. `key={selectedChatId}` força uma sessão nova ao trocar de contato, para
                    não misturar contexto/histórico entre conversas diferentes. */}
                <div className={`relative min-h-0 flex-1 ${thirdColumnTab === 'copilot' ? '' : 'hidden'}`}>
                    <HermesGlobalChat
                        key={selectedChatId}
                        isOpen={thirdColumnTab === 'copilot'}
                        onClose={() => setIsCopilotCollapsed(true)}
                        layout="inline"
                        isDark={isDark}
                        userId={userId}
                        liveContextProvider={liveContextProvider}
                        historyEnabled={false}
                        showToolsMenu={false}
                        showMinimizeButton={false}
                        resetSessionOnOpen={false}
                        headerTitle={`Copiloto — ${selectedChat?.chat_name || ''}`}
                        headerSubtitle={`${messages.length} mensagem(ns) carregada(s) nesta tela`}
                        emptyStateTitle="Pergunte sobre esta conversa"
                        emptyStateDescription="Uso as mensagens já carregadas desta conversa como contexto — carregue mais acima para ampliar o histórico disponível."
                        composerPlaceholder="Pergunte sobre esta conversa..."
                    />
                </div>
                {thirdColumnTab === 'report' && renderReportBody()}
            </div>
        );
    };

    return (
        <div className={`p-4 lg:p-8 ${isDark ? 'bg-[#0f1724]' : ''}`}>
            <div className="flex gap-4 h-[calc(100vh-140px)] min-h-[420px]">
                {/* Lista de chats: escondida no mobile quando um chat está aberto */}
                <div className={`w-full md:w-72 shrink-0 ${selectedChatId ? 'hidden md:flex md:flex-col' : 'flex flex-col'}`}>
                    {renderChatList()}
                </div>

                {selectedChatId ? (
                    <>
                        {renderTimeline()}
                        {renderThirdColumn()}
                    </>
                ) : (
                    <div className={`hidden md:flex flex-1 items-center justify-center rounded-2xl border ${cardCls}`}>
                        <p className={`text-xs ${mutedCls}`}>Selecione uma conversa para ver as mensagens.</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default WhatsappInboxView;
