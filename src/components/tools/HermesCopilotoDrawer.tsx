
import React, { useState, useEffect, useRef } from 'react';
import { db, functions, auth } from '@/firebase';
import { httpsCallable } from 'firebase/functions';
import { collection, onSnapshot, query, orderBy, where, addDoc, doc, updateDoc, getDoc, limit, Timestamp } from 'firebase/firestore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { formatDate } from '@/types';

// URL do endpoint HTTP de upload (Node.js Functions)
const UPLOAD_ENDPOINT = 'https://us-central1-gestao-hermes.cloudfunctions.net/uploadFileForCopiloto';

interface Message {
    role: 'user' | 'assistant';
    content: string;
    isArtifact?: boolean;
    proposedPlan?: any[];
    timestamp: any;
    type?: 'text' | 'plan_proposal';
}

interface Session {
    id: string;
    title: string;
    createdAt: any;
    lastMessageAt: any;
    taskId?: string;
    systemId?: string;
}

interface HermesCopilotoDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    taskId?: string;
    systemId?: string;
    isDark?: boolean;
    userId: string;
    onOpenTask?: (taskId: string) => void;
}

type UploadPhase = 'idle' | 'uploading' | 'processing';

export const HermesCopilotoDrawer: React.FC<HermesCopilotoDrawerProps> = ({
    isOpen, onClose, taskId, systemId, isDark = false, userId, onOpenTask
}) => {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    const chatEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [isFocused, setIsFocused] = useState(false);

    // Estado de anexo
    const [attachedFile, setAttachedFile] = useState<File | null>(null);
    const [uploadPhase, setUploadPhase] = useState<UploadPhase>('idle');
    // Controla a largura da barra de progresso via CSS transition
    const [progressWidth, setProgressWidth] = useState<number>(0);
    const progressTransition = useRef<string>('none');
    // Erro inline no footer (erros antes do Firestore não ficam visíveis no chat)
    const [footerError, setFooterError] = useState<string | null>(null);

    // Auto-resize textarea logic
    useEffect(() => {
        const handleResize = () => {
            if (textareaRef.current) {
                textareaRef.current.style.height = 'auto';
                const minH = isFocused ? 250 : 50;
                const scrollH = textareaRef.current.scrollHeight;
                textareaRef.current.style.height = `${Math.max(minH, Math.min(scrollH, 400))}px`;
            }
        };

        handleResize();

        const handleClickOutside = (e: MouseEvent) => {
            if (textareaRef.current && !textareaRef.current.contains(e.target as Node)) {
                setIsFocused(false);
            }
        };

        if (isFocused) {
            window.addEventListener('mousedown', handleClickOutside);
        }

        return () => window.removeEventListener('mousedown', handleClickOutside);
    }, [input, isFocused]);

    // Load Sessions
    useEffect(() => {
        if (!userId) return;
        const q = query(
            collection(db, 'sessoes_copiloto'),
            where('userId', '==', userId),
            orderBy('lastMessageAt', 'desc'),
            limit(20)
        );

        return onSnapshot(q, (snapshot) => {
            const sessList = snapshot.docs.map(doc => ({
                id: doc.id,
                ...doc.data()
            })) as Session[];
            setSessions(sessList);
        });
    }, [userId]);

    // Load Messages for current session
    useEffect(() => {
        if (!currentSessionId) {
            setMessages([]);
            return;
        }

        const q = query(
            collection(db, 'sessoes_copiloto', currentSessionId, 'mensagens'),
            orderBy('timestamp', 'asc')
        );

        return onSnapshot(q, (snapshot) => {
            const msgList = snapshot.docs.map(doc => doc.data()) as Message[];
            setMessages(msgList);
        });
    }, [currentSessionId]);

    // Scroll to bottom
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // ── Helpers de progresso ──────────────────────────────────────────────────
    const startProgressAnimation = () => {
        // Reset sem transição num frame, depois anima 0 → 90% em 15 s
        progressTransition.current = 'none';
        setProgressWidth(0);
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                progressTransition.current = 'width 15s linear';
                setProgressWidth(90);
            });
        });
    };

    // Caminho de SUCESSO: salta para 100% e limpa suavemente.
    // Só deve ser chamado dentro do bloco try, após resposta confirmada.
    const completeProgress = (): Promise<void> => {
        return new Promise((resolve) => {
            progressTransition.current = 'width 0.3s ease';
            setProgressWidth(100);
            setTimeout(() => {
                progressTransition.current = 'none';
                setProgressWidth(0);
                resolve();
            }, 350);
        });
    };

    // Caminho de ERRO: zera a barra instantaneamente, sem animação de conclusão.
    // Evita que o usuário veja "100% concluído" enquanto um banner de erro aparece.
    const abortProgress = () => {
        progressTransition.current = 'none';
        setProgressWidth(0);
    };

    // ── Seleção de arquivo ────────────────────────────────────────────────────
    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0] ?? null;
        setAttachedFile(file);
        // Reset o input para permitir re-selecionar o mesmo arquivo
        e.target.value = '';
    };

    const handleRemoveFile = () => {
        setAttachedFile(null);
    };

    // ── Criação de sessão ─────────────────────────────────────────────────────
    const handleCreateSession = async (initialPrompt?: string) => {
        setIsLoading(true);
        try {
            const sessRef = await addDoc(collection(db, 'sessoes_copiloto'), {
                userId,
                title: initialPrompt ? initialPrompt.slice(0, 40) + '...' : 'Nova Conversa',
                createdAt: Timestamp.now(),
                lastMessageAt: Timestamp.now(),
                taskId: taskId || null,
                systemId: systemId || null
            });

            setCurrentSessionId(sessRef.id);
            if (initialPrompt) {
                await sendMessage(initialPrompt, sessRef.id);
            }
        } catch (err) {
            console.error("Erro ao criar sessão:", err);
        } finally {
            setIsLoading(false);
        }
    };

    // ── Envio de mensagem (com ou sem arquivo) ────────────────────────────────
    const sendMessage = async (text: string, sessionId?: string) => {
        const sId = sessionId || currentSessionId;
        const hasFile = !!attachedFile;

        if (!sId || (!text.trim() && !hasFile)) return;

        const fileToSend = attachedFile;
        setInput('');
        setAttachedFile(null);
        setFooterError(null);
        setIsLoading(true);

        try {
            let driveFileId: string | null = null;
            let driveFileName: string | null = null;

            // ── FASE 1: Upload para o Drive via endpoint HTTP ─────────────────
            if (fileToSend) {
                setUploadPhase('uploading');

                const idToken = await auth.currentUser?.getIdToken();
                if (!idToken) throw new Error("Usuário não autenticado.");

                const formData = new FormData();
                formData.append('file', fileToSend, fileToSend.name);

                const uploadRes = await fetch(UPLOAD_ENDPOINT, {
                    method: 'POST',
                    headers: { Authorization: `Bearer ${idToken}` },
                    body: formData
                });

                if (!uploadRes.ok) {
                    const errBody = await uploadRes.json().catch(() => ({}));
                    throw new Error(errBody.error || `Erro no upload: HTTP ${uploadRes.status}`);
                }

                const uploadData = await uploadRes.json();
                driveFileId = uploadData.driveFileId;
                driveFileName = uploadData.fileName || fileToSend.name;

                // Transição para Fase 2
                setUploadPhase('processing');
                startProgressAnimation();
            }

            // Constrói o conteúdo da mensagem do usuário para o histórico
            const userMessageContent = hasFile && fileToSend
                ? `📎 ${fileToSend.name}${text.trim() ? `\n\n${text.trim()}` : ''}`
                : text;

            // 1. Salva mensagem do usuário no Firestore
            await addDoc(collection(db, 'sessoes_copiloto', sId, 'mensagens'), {
                role: 'user',
                content: userMessageContent,
                timestamp: Timestamp.now()
            });

            // 2. Chama a Cloud Function
            const askCopiloto = httpsCallable(functions, 'askCopilotoHermes');
            const response = await askCopiloto({
                sessionId: sId,
                prompt: text.trim() || (hasFile ? '' : text),
                taskId: taskId || null,
                systemId: systemId || null,
                driveFileId: driveFileId || null,
                driveFileName: driveFileName || null
            });

            const data = response.data as any;

            // 3. Atualiza título da sessão se for a primeira mensagem
            if (messages.length === 0 && !sessionId) {
                await updateDoc(doc(db, 'sessoes_copiloto', sId), {
                    title: data.suggestedTitle || userMessageContent.slice(0, 40) + '...',
                    lastMessageAt: Timestamp.now()
                });
            } else {
                await updateDoc(doc(db, 'sessoes_copiloto', sId), {
                    lastMessageAt: Timestamp.now()
                });
            }

            // Caminho de sucesso: anima para 100% antes de liberar o input.
            // Só executa aqui — nunca no finally — para não colidir com erros.
            await completeProgress();

        } catch (err: any) {
            console.error("Erro no Copiloto:", err);

            const errMsg: string = err?.message || String(err) || 'Erro desconhecido.';

            // Aborta a barra instantaneamente: impede que o usuário veja "100%"
            // enquanto um banner de erro vermelho é exibido simultaneamente.
            abortProgress();
            setFooterError(errMsg);

            // Persiste no histórico da sessão se ela já existir.
            const sId2 = sessionId || currentSessionId;
            if (sId2) {
                await addDoc(collection(db, 'sessoes_copiloto', sId2, 'mensagens'), {
                    role: 'assistant',
                    content: `⚠️ **Erro ao processar a solicitação:**\n\`${errMsg}\``,
                    timestamp: Timestamp.now()
                }).catch(() => {});
            }

        } finally {
            // O finally só faz reset de estado — nunca dispara animação.
            // A animação de sucesso já aconteceu no try; a de erro foi abortada no catch.
            setUploadPhase('idle');
            setIsLoading(false);
        }
    };

    if (!isOpen) return null;

    // ── Labels da barra de status por fase ───────────────────────────────────
    const uploadPhaseLabel: Record<UploadPhase, string> = {
        idle: '',
        uploading: 'Enviando arquivo seguro para o servidor...',
        processing: 'Extraindo contexto e atualizando Acervo...'
    };

    const isBlocked = isLoading || uploadPhase !== 'idle';

    return (
        <div className={`fixed inset-y-0 right-0 z-[500] w-full md:w-[450px] shadow-2xl transition-transform duration-300 transform translate-x-0 flex flex-col ${isDark ? 'bg-[#0f0f1a] text-white' : 'bg-white text-slate-900 border-l border-slate-200'}`}>

            {/* Header */}
            <div className={`shrink-0 p-6 flex items-center justify-between border-b ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-lg">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                    </div>
                    <div>
                        <h3 className="text-lg font-black tracking-tight">Copiloto Hermes</h3>
                        <div className="flex items-center gap-3">
                            <p className={`text-[10px] font-black uppercase tracking-widest ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Estrategista Sênior</p>
                            {taskId && (
                                <div className="flex items-center gap-1.5">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.6)]"></span>
                                    <span className="text-[9px] font-black text-emerald-500 uppercase tracking-tight">Contexto da Ação Ativo</span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => handleCreateSession()}
                        className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}
                        title="Nova Conversa"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                    </button>
                    <button onClick={() => setShowHistory(!showHistory)} className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </button>
                    <button onClick={onClose} className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}>
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-hidden flex relative">
                {/* History Sidebar */}
                {showHistory && (
                    <div className="absolute inset-0 z-10 bg-inherit flex flex-col border-r border-slate-200/50">
                        <div className="p-4 border-b border-slate-100/50 flex items-center justify-between">
                            <span className="text-[10px] font-black uppercase tracking-widest">Histórico de Sessões</span>
                            <button onClick={() => handleCreateSession()} className="text-[10px] bg-blue-600 text-white px-3 py-1.5 rounded-lg font-black uppercase tracking-widest">+ Nova</button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 space-y-2">
                            {sessions.map(s => (
                                <button
                                    key={s.id}
                                    onClick={() => { setCurrentSessionId(s.id); setShowHistory(false); }}
                                    className={`w-full text-left p-4 rounded-2xl border transition-all ${currentSessionId === s.id ? 'bg-blue-50 border-blue-200' : 'bg-white border-transparent hover:border-slate-200'}`}
                                >
                                    <p className="text-xs font-bold truncate">{s.title}</p>
                                    <p className="text-[9px] text-slate-400 mt-1">{s.lastMessageAt?.toDate()?.toLocaleDateString()}</p>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Chat Area */}
                <div className="flex-1 flex flex-col min-w-0">
                    <div className="flex-1 overflow-y-auto p-6 space-y-6" style={{ scrollbarWidth: 'thin' }}>
                        {messages.length === 0 && !isLoading && (
                            <div className="h-full flex flex-col items-center justify-center text-center opacity-30 gap-4">
                                <div className="w-20 h-20 rounded-[2.5rem] bg-slate-100 flex items-center justify-center">
                                    <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
                                </div>
                                <div>
                                    <p className="text-sm font-black uppercase tracking-widest">Inicie uma consultoria</p>
                                    <p className="text-xs mt-1">Conectando Grafo de Execução e Acervo Global</p>
                                </div>
                                <div className="flex flex-wrap gap-2 justify-center mt-4">
                                    <button onClick={() => handleCreateSession("Quais são os próximos passos estratégicos?")} className="px-4 py-2 bg-slate-100 rounded-xl text-[10px] font-bold hover:bg-slate-200 transition-all">🚀 Próximos passos</button>
                                    <button onClick={() => handleCreateSession("Analise conflitos entre o manual e a execução.")} className="px-4 py-2 bg-slate-100 rounded-xl text-[10px] font-bold hover:bg-slate-200 transition-all">🔍 Conflitos Teoria/Prática</button>
                                </div>
                            </div>
                        )}

                        {messages.map((msg, i) => (
                            <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                                <div className={`max-w-[90%] px-4 py-3 rounded-2xl text-xs font-medium leading-relaxed shadow-sm ${msg.role === 'user'
                                    ? 'bg-blue-600 text-white rounded-br-none'
                                    : 'bg-slate-100 text-slate-700 rounded-bl-none'
                                    }`}>
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm]}
                                        components={{
                                            p: ({ node, ...props }) => <p className="mb-2 last:mb-0" {...props} />,
                                            ul: ({ node, ...props }) => <ul className="list-disc ml-4 mb-2" {...props} />,
                                            li: ({ node, ...props }) => <li className="mb-0.5" {...props} />,
                                            strong: ({ node, ...props }) => <strong className="font-bold text-blue-600" {...props} />,
                                            a: ({ node, ...props }) => {
                                                const href = props.href || '';
                                                if (href.startsWith('task:')) {
                                                    const id = href.split(':')[1];
                                                    return (
                                                        <button
                                                            onClick={() => onOpenTask?.(id)}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-blue-600 hover:text-white text-blue-400 rounded-xl border border-blue-500/30 transition-all font-black text-[10px] uppercase tracking-tighter mx-1 shadow-sm group/btn"
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                                            <span className="group-hover/btn:underline">{props.children}</span>
                                                            <svg className="w-3 h-3 opacity-0 group-hover/btn:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                                                        </button>
                                                    );
                                                }
                                                return <a className="text-blue-600 underline hover:text-blue-800" target="_blank" rel="noopener noreferrer" {...props} />;
                                            },
                                        }}
                                    >
                                        {msg.content}
                                    </ReactMarkdown>

                                    {msg.proposedPlan && (
                                        <div className="mt-4 p-4 bg-white rounded-xl border border-blue-200 shadow-sm">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-600 flex items-center gap-2 mb-3">
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                                                Proposta de Ajuste de Plano
                                            </p>
                                            <div className="space-y-2 mb-4">
                                                {msg.proposedPlan.map((item, idx) => (
                                                    <div key={idx} className="flex gap-2 text-[11px] text-slate-600">
                                                        <span className="font-black text-blue-400">{idx + 1}.</span>
                                                        <span>{item.text}</span>
                                                    </div>
                                                ))}
                                            </div>
                                            <div className="flex gap-2">
                                                <button className="flex-1 bg-emerald-600 text-white py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-emerald-700 transition-all">Aceitar</button>
                                                <button className="flex-1 bg-slate-100 text-slate-400 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-slate-200 transition-all">Recusar</button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}

                        {/* Indicador de loading com mensagem de fase */}
                        {isBlocked && (
                            <div className="flex justify-start flex-col gap-2">
                                <div className="px-4 py-3 rounded-2xl rounded-bl-none bg-slate-100 flex flex-col gap-2">
                                    <div className="flex gap-1.5 items-center">
                                        <span className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" />
                                        <span className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                                        <span className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                                        {uploadPhase !== 'idle' && (
                                            <span className="text-[10px] font-bold text-slate-500 ml-2">
                                                {uploadPhaseLabel[uploadPhase]}
                                            </span>
                                        )}
                                    </div>
                                    {/* Barra de progresso — visível apenas nas fases de upload/processamento */}
                                    {uploadPhase !== 'idle' && (
                                        <div className="w-48 h-1 bg-slate-200 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-blue-500 rounded-full"
                                                style={{
                                                    width: `${progressWidth}%`,
                                                    transition: progressTransition.current
                                                }}
                                            />
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                        <div ref={chatEndRef} />
                    </div>

                    {/* Footer Input */}
                    <div className={`shrink-0 p-6 border-t ${isDark ? 'border-white/10' : 'border-slate-100'}`}>

                        {/* Banner de erro inline */}
                        {footerError && (
                            <div className="flex items-start gap-2 mb-3 px-3 py-2.5 rounded-xl text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                                <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                                </svg>
                                <span className="flex-1 leading-relaxed break-words">{footerError}</span>
                                <button
                                    onClick={() => setFooterError(null)}
                                    className="shrink-0 hover:text-red-900 transition-colors mt-0.5"
                                    title="Fechar"
                                >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>
                        )}

                        {/* Badge de arquivo anexado */}
                        {attachedFile && !isBlocked && (
                            <div className={`flex items-center gap-2 mb-3 px-3 py-2 rounded-xl text-xs font-semibold ${isDark ? 'bg-blue-900/40 text-blue-300' : 'bg-blue-50 text-blue-700 border border-blue-200'}`}>
                                <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                                </svg>
                                <span className="truncate flex-1">{attachedFile.name}</span>
                                <button
                                    onClick={handleRemoveFile}
                                    className="shrink-0 hover:text-red-500 transition-colors"
                                    title="Remover arquivo"
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>
                        )}

                        <div className="flex gap-3 items-end">
                            {/* Botão de clipe */}
                            <button
                                onClick={() => !isBlocked && fileInputRef.current?.click()}
                                disabled={isBlocked}
                                title="Anexar arquivo"
                                className={`shrink-0 w-10 h-10 flex items-center justify-center rounded-2xl border transition-all ${
                                    attachedFile
                                        ? 'bg-blue-600 text-white border-blue-600'
                                        : isDark
                                            ? 'border-white/10 text-white/40 hover:text-white/80 hover:border-white/30'
                                            : 'border-slate-200 text-slate-400 hover:text-slate-600 hover:border-slate-300'
                                } disabled:opacity-30 disabled:cursor-not-allowed`}
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                                </svg>
                            </button>

                            {/* Input de arquivo oculto */}
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.png,.jpg,.jpeg,.webp"
                                className="hidden"
                                onChange={handleFileSelect}
                            />

                            <textarea
                                ref={textareaRef}
                                value={input}
                                onChange={e => setInput(e.target.value)}
                                onFocus={() => setIsFocused(true)}
                                disabled={isBlocked}
                                onKeyDown={e => {
                                    if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault();
                                        if (!currentSessionId) {
                                            handleCreateSession(input);
                                        } else {
                                            sendMessage(input);
                                        }
                                    }
                                }}
                                placeholder={attachedFile ? 'Pergunte sobre o arquivo ou envie sem texto…' : 'Estrategize com Hermes…'}
                                className={`flex-1 px-5 py-3.5 rounded-2xl text-sm font-medium outline-none border resize-none overflow-y-auto ${isDark ? 'bg-white/5 border-white/10 text-white placeholder:text-white/20 focus:border-blue-500' : 'bg-slate-50 border-slate-200 text-slate-700 placeholder:text-slate-400 focus:border-blue-500'} transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed`}
                            />
                            <button
                                onClick={() => {
                                    if (!currentSessionId) {
                                        handleCreateSession(input);
                                    } else {
                                        sendMessage(input);
                                    }
                                }}
                                disabled={isBlocked || (!input.trim() && !attachedFile)}
                                className="w-12 h-12 shrink-0 bg-blue-600 text-white rounded-2xl flex items-center justify-center shadow-lg hover:bg-blue-700 disabled:opacity-40 transition-all"
                            >
                                <svg className="w-6 h-6 rotate-45" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
