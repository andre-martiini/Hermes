import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    QueryDocumentSnapshot, Timestamp, addDoc, arrayUnion, collection, doc, getDocs, limit,
    onSnapshot, orderBy, query, serverTimestamp, startAfter, updateDoc, where, writeBatch
} from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { getDownloadURL, ref as storageRef } from 'firebase/storage';
import { db, functions, storage } from './firebase';
import { PerfilPessoa, Tarefa, WhatsappConsolidacao, WhatsappMessageDoc } from './types';
import { buildDiaryWhatsappNote } from './src/utils/diaryEntries';
import { HermesGlobalChat } from './src/components/tools/HermesGlobalChat';
import { parseWhatsappExportTxt } from './src/utils/whatsappExportParser';

interface WhatsappChatOption {
    chat_id: string;
    chat_name: string;
    is_group: boolean;
    monitored?: boolean;
    last_activity_ts?: string | null;
}

interface WhatsappInboxViewProps {
    tarefas: Tarefa[];
    userId: string;
    isDark?: boolean;
    onOpenContact?: (id: string) => void;
}

const PAGE_SIZE = 30;
const MAX_SELECTION = 200; // mesmo cap validado no backend (whatsapp_consolidation.py)
const AUDIO_TYPES = new Set(['ptt', 'audio']);
const IMAGE_TYPES = new Set(['image', 'sticker']);
const VIDEO_TYPES = new Set(['video']);
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

const formatLastActivity = (iso?: string | null): string => {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
        return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) {
        return 'Ontem';
    }
    if (d.getFullYear() === now.getFullYear()) {
        return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
    }
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' });
};

const WhatsappInboxView: React.FC<WhatsappInboxViewProps> = ({ tarefas, userId, isDark = false, onOpenContact }) => {
    // Lista de chats
    const [chats, setChats] = useState<WhatsappChatOption[]>([]);
    const [isLoadingChats, setIsLoadingChats] = useState(true);
    const [chatsError, setChatsError] = useState<string | null>(null);
    const [chatSearch, setChatSearch] = useState('');
    const [chatFilterTab, setChatFilterTab] = useState<'all' | 'monitored' | 'groups' | 'direct'>('all');
    const [visibleChatsCount, setVisibleChatsCount] = useState(25);
    const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
    const [linkedPerson, setLinkedPerson] = useState<PerfilPessoa | null>(null);

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

    // Indicador de mensagem nova (bolinha verde): timestamp (ms) da última mensagem por chat monitorado.
    useEffect(() => {
        const activeChats = chats.filter(c => c.monitored !== false);
        if (activeChats.length === 0) return;
        const unsubs = activeChats.map(chat => {
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

    // Toggle de captura ativa/inativa
    const [isTogglingMonitored, setIsTogglingMonitored] = useState(false);

    // Importar histórico (.txt)
    const [showImportModal, setShowImportModal] = useState(false);
    const [importFile, setImportFile] = useState<File | null>(null);
    const [importUserName, setImportUserName] = useState('André Martini');
    const [isImporting, setIsImporting] = useState(false);
    const [importProgress, setImportProgress] = useState<{ current: number; total: number } | null>(null);
    const [importResult, setImportResult] = useState<{ count: number; startDate?: string; endDate?: string } | null>(null);
    const [importError, setImportError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Auto-scroll e refs da timeline
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const messagesContainerRef = useRef<HTMLDivElement>(null);
    const shouldAutoScrollRef = useRef(true);

    const selectedChat = useMemo(() => chats.find(c => c.chat_id === selectedChatId) || null, [chats, selectedChatId]);

    const resetImportModal = () => {
        setShowImportModal(false);
        setImportFile(null);
        setIsImporting(false);
        setImportProgress(null);
        setImportResult(null);
        setImportError(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setImportFile(file);
            setImportError(null);
            setImportResult(null);
        }
    };

    const handleStartImport = async () => {
        if (!importFile || !selectedChat) {
            setImportError('Selecione um arquivo .txt de exportação do WhatsApp.');
            return;
        }

        setIsImporting(true);
        setImportError(null);
        setImportProgress({ current: 0, total: 0 });

        try {
            const rawText = await importFile.text();
            const parsed = parseWhatsappExportTxt(
                rawText,
                selectedChat.chat_id,
                selectedChat.chat_name,
                selectedChat.is_group,
                importUserName
            );

            if (parsed.length === 0) {
                setImportError('Nenhuma mensagem válida foi encontrada no arquivo. Verifique se é um arquivo .txt de exportação do WhatsApp.');
                setIsImporting(false);
                return;
            }

            setImportProgress({ current: 0, total: parsed.length });

            const BATCH_SIZE = 450;
            let batch = writeBatch(db);
            let inBatch = 0;
            let totalSaved = 0;

            let minDate: Date | null = null;
            let maxDate: Date | null = null;

            for (let i = 0; i < parsed.length; i++) {
                const msg = parsed[i];
                if (!minDate || msg.timestamp < minDate) minDate = msg.timestamp;
                if (!maxDate || msg.timestamp > maxDate) maxDate = msg.timestamp;

                const docRef = doc(db, 'whatsapp_messages', msg.id);
                const payload = {
                    ...msg,
                    timestamp: Timestamp.fromDate(msg.timestamp),
                    ingested_at: serverTimestamp()
                };

                batch.set(docRef, payload, { merge: true });
                inBatch++;
                totalSaved++;

                if (inBatch >= BATCH_SIZE) {
                    await batch.commit();
                    batch = writeBatch(db);
                    inBatch = 0;
                    setImportProgress({ current: totalSaved, total: parsed.length });
                }
            }

            if (inBatch > 0) {
                await batch.commit();
            }

            // Atualiza last_activity_ts no chat
            if (maxDate) {
                try {
                    await updateDoc(doc(db, 'whatsapp_chats', selectedChat.chat_id), {
                        last_activity_ts: Timestamp.fromDate(maxDate),
                        last_synced_at: serverTimestamp()
                    });
                } catch {
                    // Chat pode não existir ainda em whatsapp_chats
                }
            }

            setImportResult({
                count: totalSaved,
                startDate: minDate ? minDate.toLocaleDateString('pt-BR') : undefined,
                endDate: maxDate ? maxDate.toLocaleDateString('pt-BR') : undefined
            });
        } catch (err: any) {
            console.error('[Import WhatsApp] Erro na importação:', err);
            setImportError(`Erro ao importar: ${err?.message || err}`);
        } finally {
            setIsImporting(false);
        }
    };

    const handleToggleMonitored = async (chatId: string, currentMonitored: boolean) => {
        const nextMonitored = !currentMonitored;
        setChats(prev => prev.map(c => c.chat_id === chatId ? { ...c, monitored: nextMonitored } : c));
        setIsTogglingMonitored(true);
        try {
            const fn = httpsCallable(functions, 'toggleWhatsappChatMonitored');
            await fn({ chat_id: chatId, monitored: nextMonitored });
        } catch (err: any) {
            console.error('[WhatsappInbox] Erro ao alterar monitoramento do chat:', err);
            setChats(prev => prev.map(c => c.chat_id === chatId ? { ...c, monitored: currentMonitored } : c));
            alert(`Erro ao alterar captura do chat: ${err?.message || err}`);
        } finally {
            setIsTogglingMonitored(false);
        }
    };

    // ── Chats ────────────────────────────────────────────────────────────────
    useEffect(() => {
        let cancelled = false;
        (async () => {
            setIsLoadingChats(true);
            setChatsError(null);
            try {
                const fn = httpsCallable(functions, 'listWhatsappChats');
                const res = await fn({ include_all: true });
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

    // Busca contato vinculado em perfil_pessoas quando um chat 1:1 é selecionado
    useEffect(() => {
        if (!selectedChatId || selectedChatId.endsWith('@g.us')) {
            setLinkedPerson(null);
            return;
        }
        let cancelled = false;
        (async () => {
            try {
                const q = query(
                    collection(db, 'perfil_pessoas'),
                    where('whatsapp_chat_id', '==', selectedChatId),
                    limit(1)
                );
                const snap = await getDocs(q);
                if (cancelled) return;
                if (!snap.empty) {
                    const docSnap = snap.docs[0];
                    setLinkedPerson({ id: docSnap.id, ...docSnap.data() } as PerfilPessoa);
                } else {
                    setLinkedPerson(null);
                }
            } catch (e) {
                console.error('[WhatsappInbox] Falha ao buscar contato vinculado:', e);
                if (!cancelled) setLinkedPerson(null);
            }
        })();
        return () => { cancelled = true; };
    }, [selectedChatId]);

    // ── Timeline do chat selecionado ─────────────────────────────────────────
    useEffect(() => {
        setLiveDocs([]);
        setOlderDocs([]);
        setSelection(new Set());
        setActiveJobId(null);
        setThirdColumnTab('copilot');
        setTimelineError(null);
        setMediaUrls({});
        shouldAutoScrollRef.current = true;
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

    const handleLoadMore = async () => {
        if (isLoadingMore || !selectedChatId) return;
        shouldAutoScrollRef.current = false;
        const container = messagesContainerRef.current;
        const prevScrollHeight = container ? container.scrollHeight : 0;
        const prevScrollTop = container ? container.scrollTop : 0;

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

            // Preserva a posição visual do scroll após carregar mensagens anteriores no topo
            requestAnimationFrame(() => {
                if (container) {
                    const newScrollHeight = container.scrollHeight;
                    container.scrollTop = prevScrollTop + (newScrollHeight - prevScrollHeight);
                }
            });
        } finally {
            setIsLoadingMore(false);
        }
    };

    // Mensagens em ordem cronológica (mais antiga primeiro) para exibição estilo chat,
    // com deduplicação inteligente para mesclar mensagens do worker em tempo real com histórico .txt.
    const messages: WhatsappMessageDoc[] = useMemo(() => {
        const all = [...olderDocs.slice().reverse(), ...liveDocs.slice().reverse()];
        const docsList = all.map(d => ({ id: d.id, ...(d.data() as any) })) as WhatsappMessageDoc[];

        const seenIds = new Set<string>();
        const seenSignatures = new Set<string>();
        const deduplicated: WhatsappMessageDoc[] = [];

        for (const msg of docsList) {
            if (seenIds.has(msg.id)) continue;
            seenIds.add(msg.id);

            const tsDate = tsToDate(msg.timestamp);
            const minuteKey = tsDate ? Math.floor(tsDate.getTime() / 60000) : 0;
            const contentKey = (msg.content || '').trim().slice(0, 100);
            const authorKey = (msg.author_name || '').trim().toLowerCase();
            const sig = `${msg.chat_id}_${authorKey}_${minuteKey}_${contentKey}`;

            // Se for duplicata de mesmo autor, minuto e conteúdo entre worker e .txt, mantém a primeira
            if (contentKey && seenSignatures.has(sig)) {
                continue;
            }
            if (contentKey) {
                seenSignatures.add(sig);
            }
            deduplicated.push(msg);
        }

        return deduplicated;
    }, [liveDocs, olderDocs]);

    // Contagem por tipo da seleção atual — ajuda a confirmar a mistura antes de consolidar.
    const selectionBreakdown = useMemo(() => {
        let nAudio = 0, nVideo = 0, nOutro = 0;
        for (const m of messages) {
            if (!selection.has(m.id)) continue;
            if (AUDIO_TYPES.has(m.message_type)) nAudio++;
            else if (VIDEO_TYPES.has(m.message_type)) nVideo++;
            else nOutro++;
        }
        return { nAudio, nVideo, nOutro };
    }, [messages, selection]);

    // Auto-scroll para as mensagens mais recentes (fim da lista)
    useEffect(() => {
        if (messages.length > 0 && shouldAutoScrollRef.current) {
            requestAnimationFrame(() => {
                messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
            });
        }
    }, [messages, selectedChatId]);

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

    // Reset de paginação ao trocar filtro ou termo de busca
    useEffect(() => {
        setVisibleChatsCount(25);
    }, [chatSearch, chatFilterTab]);

    const filteredChats = useMemo(() => {
        let list = chats;
        if (chatFilterTab === 'monitored') {
            list = list.filter(c => c.monitored !== false);
        } else if (chatFilterTab === 'groups') {
            list = list.filter(c => c.is_group);
        } else if (chatFilterTab === 'direct') {
            list = list.filter(c => !c.is_group);
        }
        const s = chatSearch.trim().toLowerCase();
        if (!s) return list;
        return list.filter(c => c.chat_name.toLowerCase().includes(s) || c.chat_id.toLowerCase().includes(s));
    }, [chats, chatSearch, chatFilterTab]);

    const visibleChats = useMemo(() => {
        return filteredChats.slice(0, visibleChatsCount);
    }, [filteredChats, visibleChatsCount]);

    const cardCls = isDark ? 'border-white/10 bg-white/5' : 'border-slate-100 bg-white shadow-sm';
    const mutedCls = isDark ? 'text-white/40' : 'text-slate-400';

    const monitoredCount = useMemo(() => chats.filter(c => c.monitored !== false).length, [chats]);
    const groupCount = useMemo(() => chats.filter(c => c.is_group).length, [chats]);
    const directCount = useMemo(() => chats.filter(c => !c.is_group).length, [chats]);

    // ── Render ───────────────────────────────────────────────────────────────
    const renderChatList = () => (
        <div className={`flex flex-col rounded-2xl border overflow-hidden ${cardCls}`}>
            <div className={`shrink-0 p-3 border-b space-y-2.5 ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                {/* Abas / Filtros rápidos */}
                <div className={`flex rounded-lg p-0.5 border gap-0.5 ${isDark ? 'bg-slate-900 border-white/10' : 'bg-slate-100 border-slate-200'}`}>
                    <button
                        onClick={() => setChatFilterTab('all')}
                        className={`flex-1 py-1 text-[9px] font-bold rounded uppercase tracking-wider transition-all ${
                            chatFilterTab === 'all'
                                ? (isDark ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white text-slate-800 shadow-xs')
                                : mutedCls
                        }`}
                        title="Todas as conversas"
                    >
                        Todos ({chats.length})
                    </button>
                    <button
                        onClick={() => setChatFilterTab('monitored')}
                        className={`flex-1 py-1 text-[9px] font-bold rounded uppercase tracking-wider transition-all ${
                            chatFilterTab === 'monitored'
                                ? (isDark ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white text-slate-800 shadow-xs')
                                : mutedCls
                        }`}
                        title="Conversas na allowlist de captura contínua"
                    >
                        Ativos ({monitoredCount})
                    </button>
                    <button
                        onClick={() => setChatFilterTab('direct')}
                        className={`flex-1 py-1 text-[9px] font-bold rounded uppercase tracking-wider transition-all ${
                            chatFilterTab === 'direct'
                                ? (isDark ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white text-slate-800 shadow-xs')
                                : mutedCls
                        }`}
                        title="Contatos individuais"
                    >
                        1:1 ({directCount})
                    </button>
                    <button
                        onClick={() => setChatFilterTab('groups')}
                        className={`flex-1 py-1 text-[9px] font-bold rounded uppercase tracking-wider transition-all ${
                            chatFilterTab === 'groups'
                                ? (isDark ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white text-slate-800 shadow-xs')
                                : mutedCls
                        }`}
                        title="Grupos"
                    >
                        Grupos ({groupCount})
                    </button>
                </div>
                <input
                    type="text"
                    value={chatSearch}
                    onChange={e => setChatSearch(e.target.value)}
                    placeholder="Buscar conversa ou contato..."
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
                        <p className={`text-xs font-bold ${isDark ? 'text-white/70' : 'text-slate-600'}`}>Nenhuma conversa encontrada.</p>
                        <p className={`text-[10px] ${mutedCls}`}>Tente outro termo na busca acima.</p>
                    </div>
                ) : (
                    <>
                        {visibleChats.map(chat => {
                            const unread = chat.chat_id !== selectedChatId
                                && !!lastMessageAt[chat.chat_id]
                                && lastMessageAt[chat.chat_id] > getLastSeen(chat.chat_id);
                            const lastTimeStr = formatLastActivity(chat.last_activity_ts);

                            return (
                                <button
                                    key={chat.chat_id}
                                    onClick={() => setSelectedChatId(chat.chat_id)}
                                    className={`w-full flex items-start gap-2.5 px-3 py-2.5 text-left transition-colors border-b last:border-b-0 ${
                                        selectedChatId === chat.chat_id
                                            ? (isDark ? 'bg-green-500/15 border-green-500/20' : 'bg-green-50 border-green-100')
                                            : (isDark ? 'border-white/5 hover:bg-white/5' : 'border-slate-100 hover:bg-slate-50')
                                    }`}
                                >
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm shrink-0 mt-0.5 ${
                                        chat.is_group
                                            ? (isDark ? 'bg-indigo-500/20 text-indigo-300' : 'bg-indigo-100 text-indigo-700')
                                            : (isDark ? 'bg-slate-800 text-slate-300' : 'bg-slate-100 text-slate-600')
                                    }`}>
                                        {chat.is_group ? '👥' : '👤'}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center justify-between gap-1">
                                            <span className={`text-xs font-bold truncate font-sans ${isDark ? 'text-white/90' : 'text-slate-800'}`}>
                                                {chat.chat_name}
                                            </span>
                                            {lastTimeStr && (
                                                <span className={`text-[10px] font-mono shrink-0 ${unread ? 'text-green-500 font-bold' : mutedCls}`}>
                                                    {lastTimeStr}
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex items-center justify-between gap-1 mt-0.5">
                                            <div className="flex items-center gap-1">
                                                {chat.monitored !== false ? (
                                                    <span className={`px-1 py-0.2 rounded text-[8px] font-bold uppercase tracking-wider ${isDark ? 'bg-emerald-500/20 text-emerald-300' : 'bg-emerald-50 text-emerald-700'}`}>
                                                        ativa
                                                    </span>
                                                ) : (
                                                    <span className={`px-1 py-0.2 rounded text-[8px] font-semibold uppercase tracking-wider ${isDark ? 'bg-white/10 text-white/40' : 'bg-slate-100 text-slate-400'}`}>
                                                        histórico
                                                    </span>
                                                )}
                                                {chat.is_group && (
                                                    <span className={`px-1 py-0.2 rounded text-[8px] font-semibold uppercase tracking-wider ${isDark ? 'bg-indigo-500/20 text-indigo-300' : 'bg-indigo-50 text-indigo-700'}`}>
                                                        grupo
                                                    </span>
                                                )}
                                            </div>
                                            {unread && (
                                                <span className="shrink-0 w-2 h-2 rounded-full bg-green-500" title="Mensagem nova" />
                                            )}
                                        </div>
                                    </div>
                                </button>
                            );
                        })}

                        {filteredChats.length > visibleChatsCount && (
                            <div className={`p-3 text-center border-t ${isDark ? 'border-white/10 bg-white/2' : 'border-slate-100 bg-slate-50'}`}>
                                <button
                                    onClick={() => setVisibleChatsCount(prev => Math.min(prev + 25, filteredChats.length))}
                                    className={`w-full py-1.5 px-3 rounded-lg text-[10px] font-bold uppercase tracking-wider border transition-all ${
                                        isDark
                                            ? 'border-white/15 text-white/80 hover:bg-white/10'
                                            : 'border-slate-200 text-slate-700 hover:bg-slate-100'
                                    }`}
                                >
                                    Carregar mais ({Math.min(25, filteredChats.length - visibleChatsCount)} restantes)
                                </button>
                                <p className={`text-[9px] mt-1.5 font-mono ${mutedCls}`}>
                                    Exibindo {visibleChats.length} de {filteredChats.length} conversas
                                </p>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );

    const renderMessageBubble = (msg: WhatsappMessageDoc, prevMsg: WhatsappMessageDoc | null) => {
        const showDay = !prevMsg || fmtDay(prevMsg.timestamp) !== fmtDay(msg.timestamp);
        const isAudio = AUDIO_TYPES.has(msg.message_type);
        const isImage = IMAGE_TYPES.has(msg.message_type);
        const isVideo = VIDEO_TYPES.has(msg.message_type);
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
                        ) : isVideo ? (
                            <div className="space-y-1">
                                {storagePath ? (
                                    mediaUrls[storagePath] ? (
                                        <video controls src={mediaUrls[storagePath]} className="max-w-full max-h-64 rounded-lg" />
                                    ) : (
                                        <button onClick={() => loadMedia(storagePath)} className={`text-[10px] font-bold underline ${isDark ? 'text-green-300' : 'text-green-700'}`}>
                                            {loadingMedia.has(storagePath) ? 'Carregando vídeo...' : '▶ Carregar vídeo'}
                                        </button>
                                    )
                                ) : (
                                    <span className={`italic text-[10px] ${mutedCls}`}>[vídeo não capturado]</span>
                                )}
                                {msg.content && <p className="whitespace-pre-line break-words">{msg.content}</p>}
                                {msg.transcription_text && (
                                    <p className={`text-[10px] leading-relaxed border-l-2 pl-2 ${isDark ? 'border-green-500/30 text-white/60' : 'border-green-200 text-slate-500'}`}>
                                        {msg.transcription_text}
                                    </p>
                                )}
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
                <div className="flex items-center gap-2 min-w-0 flex-1">
                    <button onClick={() => setSelectedChatId(null)} className={`md:hidden text-xs font-bold ${mutedCls}`}>←</button>
                    <span className="text-base">{selectedChat?.is_group ? '👥' : '👤'}</span>
                    <span className={`text-sm font-black truncate ${isDark ? 'text-white' : 'text-slate-800'}`}>{selectedChat?.chat_name}</span>
                    {selectedChat && (
                        <button
                            onClick={() => handleToggleMonitored(selectedChat.chat_id, selectedChat.monitored !== false)}
                            disabled={isTogglingMonitored}
                            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold border transition-all shrink-0 ${
                                selectedChat.monitored !== false
                                    ? (isDark
                                        ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300 hover:bg-rose-500/15 hover:border-rose-500/30 hover:text-rose-300'
                                        : 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-rose-50 hover:border-rose-200 hover:text-rose-700')
                                    : (isDark
                                        ? 'bg-white/5 border-white/15 text-white/60 hover:bg-emerald-500/15 hover:border-emerald-500/30 hover:text-emerald-300'
                                        : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-emerald-50 hover:border-emerald-200 hover:text-emerald-700')
                            }`}
                            title={
                                selectedChat.monitored !== false
                                    ? 'Captura contínua ATIVADA pelo worker local. Clique para desativar.'
                                    : 'Captura contínua DESATIVADA. Clique para ATIVAR captura de novas mensagens pelo worker.'
                            }
                        >
                            <span className={`w-1.5 h-1.5 rounded-full ${selectedChat.monitored !== false ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
                            <span>{selectedChat.monitored !== false ? 'Captura Ativa' : 'Ativar Captura'}</span>
                        </button>
                    )}
                    {linkedPerson && (
                        <div className="flex items-center gap-1.5 ml-2 pl-2 border-l border-slate-200 dark:border-white/10 shrink-0">
                            <div
                                className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-black text-white shrink-0"
                                style={{ backgroundColor: linkedPerson.avatar_color || '#6366f1' }}
                            >
                                {linkedPerson.avatar_initials || linkedPerson.nome?.substring(0, 2).toUpperCase() || '👤'}
                            </div>
                            <span className={`text-xs font-bold truncate max-w-[120px] ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>
                                {linkedPerson.nome}
                            </span>
                            {onOpenContact && (
                                <button
                                    onClick={() => onOpenContact(linkedPerson.id)}
                                    className="text-[10px] font-bold text-indigo-500 hover:text-indigo-400 hover:underline flex items-center gap-0.5"
                                    title="Abrir perfil em Contatos"
                                >
                                    Ver contato ↗
                                </button>
                            )}
                        </div>
                    )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    <button
                        onClick={() => {
                            setImportFile(null);
                            setImportError(null);
                            setImportResult(null);
                            setShowImportModal(true);
                        }}
                        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold border transition-colors ${
                            isDark
                                ? 'border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10'
                                : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
                        }`}
                        title="Importar histórico de mensagens a partir de arquivo .txt exportado do WhatsApp"
                    >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                        </svg>
                        Carregar Histórico
                    </button>
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
            <div
                ref={messagesContainerRef}
                onScroll={(e) => {
                    const el = e.currentTarget;
                    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
                    shouldAutoScrollRef.current = isAtBottom;
                }}
                className="flex-1 overflow-y-auto px-4 py-3 space-y-1.5"
            >
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
                                onClick={handleLoadMore}
                                disabled={isLoadingMore}
                                className={`mx-auto block rounded-lg border px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition disabled:opacity-50 ${isDark ? 'border-white/10 text-white/60 hover:bg-white/5' : 'border-slate-200 text-slate-500 hover:bg-slate-50'}`}
                            >
                                {isLoadingMore ? 'Carregando...' : 'Carregar mensagens anteriores'}
                            </button>
                        )}
                        {messages.map((m, i) => renderMessageBubble(m, i > 0 ? messages[i - 1] : null))}
                        <div ref={messagesEndRef} className="h-0 w-0" />
                    </>
                )}
            </div>

            {/* Barra de seleção/consolidação */}
            <div className={`shrink-0 px-4 py-3 border-t flex items-center justify-between gap-3 ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                <div className="flex items-center gap-3">
                    <span className={`text-[10px] font-bold ${selection.size >= MAX_SELECTION ? 'text-amber-500' : mutedCls}`}>
                        {selection.size} selecionada(s){selection.size >= MAX_SELECTION ? ` (máx. ${MAX_SELECTION})` : ''}
                        {(selectionBreakdown.nAudio > 0 || selectionBreakdown.nVideo > 0) && (
                            <span className={`font-normal ${mutedCls}`}>
                                {' '}({selectionBreakdown.nOutro} texto/outro · {selectionBreakdown.nAudio} áudio · {selectionBreakdown.nVideo} vídeo)
                            </span>
                        )}
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
                                {(activeJob.n_audios_ignorados || 0) > 0 ? ` · ${activeJob.n_audios_ignorados} áudio(s) ignorado(s)` : ''}
                                {((activeJob.n_videos_transcritos || 0) > 0 || (activeJob.n_videos_ignorados || 0) > 0) ? ` · ${activeJob.n_videos_transcritos || 0} vídeo(s) transcrito(s)` : ''}
                                {(activeJob.n_videos_ignorados || 0) > 0 ? ` · ${activeJob.n_videos_ignorados} vídeo(s) ignorado(s)` : ''}
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
        <div className={`p-2 sm:p-3 ${isDark ? 'bg-[#0f1724]' : ''}`}>
            <div className="flex gap-2.5 sm:gap-3 h-[calc(100vh-88px)] min-h-[500px]">
                {/* Lista de chats: escondida no mobile quando um chat está aberto */}
                <div className={`w-full md:w-80 shrink-0 ${selectedChatId ? 'hidden md:flex md:flex-col' : 'flex flex-col'}`}>
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

            {/* Modal de Importação de Histórico (.txt) */}
            {showImportModal && (
                <div className="fixed inset-0 z-[300] flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={() => !isImporting && resetImportModal()} />
                    <div className={`w-full max-w-lg rounded-2xl border shadow-xl p-6 relative z-10 space-y-4 font-sans ${
                        isDark ? 'bg-slate-950 border-white/10 text-white' : 'bg-white border-slate-200 text-slate-800'
                    }`}>
                        <div className="flex items-center justify-between border-b pb-3 border-slate-100 dark:border-white/10">
                            <div>
                                <h3 className="text-sm font-black flex items-center gap-2">
                                    <span>📥</span> Carregar Histórico do WhatsApp
                                </h3>
                                <p className={`text-[11px] font-medium mt-0.5 ${mutedCls}`}>
                                    Conversa: <strong className={isDark ? 'text-white' : 'text-slate-900'}>{selectedChat?.chat_name}</strong>
                                </p>
                            </div>
                            {!isImporting && (
                                <button onClick={resetImportModal} className={`text-base font-bold ${mutedCls} hover:text-rose-500`}>
                                    &times;
                                </button>
                            )}
                        </div>

                        {importResult ? (
                            <div className="space-y-4 text-center py-4">
                                <div className="w-12 h-12 rounded-full bg-emerald-500/15 text-emerald-500 mx-auto flex items-center justify-center text-xl font-black">
                                    ✓
                                </div>
                                <div>
                                    <h4 className="text-base font-black text-emerald-500">Histórico Importado com Sucesso!</h4>
                                    <p className={`text-xs mt-1 ${mutedCls}`}>
                                        <strong>{importResult.count.toLocaleString('pt-BR')}</strong> mensagens foram carregadas e salvas na conversa.
                                    </p>
                                    {importResult.startDate && importResult.endDate && (
                                        <p className={`text-[11px] font-mono mt-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                            Período: {importResult.startDate} até {importResult.endDate}
                                        </p>
                                    )}
                                </div>
                                <button
                                    onClick={resetImportModal}
                                    className="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold uppercase tracking-wider transition-all"
                                >
                                    Concluir e Ver Mensagens
                                </button>
                            </div>
                        ) : isImporting ? (
                            <div className="space-y-4 py-6 text-center">
                                <div className="w-10 h-10 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto" />
                                <div>
                                    <h4 className="text-sm font-black">Gravando Mensagens no Firestore...</h4>
                                    {importProgress && importProgress.total > 0 && (
                                        <div className="mt-3 space-y-2">
                                            <div className="w-full bg-slate-200 dark:bg-white/10 rounded-full h-2 overflow-hidden">
                                                <div
                                                    className="bg-emerald-500 h-2 rounded-full transition-all duration-200"
                                                    style={{ width: `${Math.round((importProgress.current / importProgress.total) * 100)}%` }}
                                                />
                                            </div>
                                            <p className={`text-xs font-mono ${mutedCls}`}>
                                                {importProgress.current.toLocaleString('pt-BR')} / {importProgress.total.toLocaleString('pt-BR')} ({Math.round((importProgress.current / importProgress.total) * 100)}%)
                                            </p>
                                        </div>
                                    )}
                                </div>
                                <p className={`text-[11px] ${mutedCls}`}>
                                    Lotes de 450 mensagens com verificação de idempotência (sem duplicações).
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                <div
                                    onClick={() => fileInputRef.current?.click()}
                                    className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                                        importFile
                                            ? (isDark ? 'border-emerald-500/50 bg-emerald-950/20' : 'border-emerald-400 bg-emerald-50/50')
                                            : (isDark ? 'border-white/20 hover:border-white/40 hover:bg-white/5' : 'border-slate-300 hover:border-slate-400 hover:bg-slate-50')
                                    }`}
                                >
                                    <input
                                        type="file"
                                        ref={fileInputRef}
                                        onChange={handleFileChange}
                                        accept=".txt,text/plain"
                                        className="hidden"
                                    />
                                    {importFile ? (
                                        <div className="space-y-1">
                                            <span className="text-2xl">📄</span>
                                            <p className="text-xs font-bold truncate max-w-xs mx-auto">{importFile.name}</p>
                                            <p className={`text-[10px] ${mutedCls}`}>
                                                {(importFile.size / (1024 * 1024)).toFixed(2)} MB • Clique para trocar
                                            </p>
                                        </div>
                                    ) : (
                                        <div className="space-y-1">
                                            <span className="text-2xl">📂</span>
                                            <p className="text-xs font-bold">Clique para selecionar o arquivo .txt</p>
                                            <p className={`text-[10px] ${mutedCls}`}>
                                                Exporte a conversa no WhatsApp (sem mídia) e selecione o .txt gerado.
                                            </p>
                                        </div>
                                    )}
                                </div>

                                <div>
                                    <label className={`text-[10px] font-bold uppercase tracking-wider block mb-1 ${mutedCls}`}>
                                        Seu nome no WhatsApp (para identificar suas mensagens como "Eu")
                                    </label>
                                    <input
                                        type="text"
                                        value={importUserName}
                                        onChange={e => setImportUserName(e.target.value)}
                                        placeholder="Ex: André Martini"
                                        className={`w-full px-3 py-2 rounded-lg border text-xs font-bold outline-none ${
                                            isDark ? 'bg-white/5 border-white/10 text-white focus:border-emerald-500' : 'bg-slate-50 border-slate-200 text-slate-800 focus:border-emerald-500'
                                        }`}
                                    />
                                    <p className={`text-[10px] mt-1 ${mutedCls}`}>
                                        Mensagens com esse remetente serão marcadas com balão verde à direita ("Eu").
                                    </p>
                                </div>

                                {importError && (
                                    <div className={`p-3 rounded-lg text-xs font-bold border ${isDark ? 'bg-rose-950/30 border-rose-500/40 text-rose-300' : 'bg-rose-50 border-rose-200 text-rose-700'}`}>
                                        {importError}
                                    </div>
                                )}

                                <div className="flex gap-2 pt-2">
                                    <button
                                        type="button"
                                        onClick={resetImportModal}
                                        className={`flex-1 py-2 rounded-xl border text-xs font-bold uppercase tracking-wider transition ${
                                            isDark ? 'border-white/10 hover:bg-white/5 text-white/70' : 'border-slate-200 hover:bg-slate-100 text-slate-700'
                                        }`}
                                    >
                                        Cancelar
                                    </button>
                                    <button
                                        type="button"
                                        onClick={handleStartImport}
                                        disabled={!importFile}
                                        className="flex-1 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold uppercase tracking-wider transition shadow-sm"
                                    >
                                        Carregar Histórico
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default WhatsappInboxView;
