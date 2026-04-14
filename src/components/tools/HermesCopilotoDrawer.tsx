
import React, { useState, useEffect, useRef } from 'react';
import { db, functions } from '@/firebase';
import { httpsCallable } from 'firebase/functions';
import { collection, onSnapshot, query, orderBy, where, addDoc, doc, updateDoc, getDoc, limit, Timestamp } from 'firebase/firestore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { formatDate } from '@/types';

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
}

export const HermesCopilotoDrawer: React.FC<HermesCopilotoDrawerProps> = ({
    isOpen, onClose, taskId, systemId, isDark = false, userId
}) => {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    const chatEndRef = useRef<HTMLDivElement>(null);

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

    const sendMessage = async (text: string, sessionId?: string) => {
        const sId = sessionId || currentSessionId;
        if (!sId || !text.trim()) return;

        setInput(''); // Limpa o campo imediatamente para melhor UX
        setIsLoading(true);
        try {
            // 1. Save user message
            await addDoc(collection(db, 'sessoes_copiloto', sId, 'mensagens'), {
                role: 'user',
                content: text,
                timestamp: Timestamp.now()
            });

            // 2. Call Cloud Function
            const askCopiloto = httpsCallable(functions, 'askCopilotoHermes');
            const response = await askCopiloto({
                sessionId: sId,
                prompt: text,
                taskId: taskId || null,
                systemId: systemId || null
            });

            const data = response.data as any;

            // 3. Update session title if it's the first message
            if (messages.length === 0 && !sessionId) {
                await updateDoc(doc(db, 'sessoes_copiloto', sId), {
                    title: data.suggestedTitle || text.slice(0, 40) + '...',
                    lastMessageAt: Timestamp.now()
                });
            } else {
                await updateDoc(doc(db, 'sessoes_copiloto', sId), {
                    lastMessageAt: Timestamp.now()
                });
            }

        } catch (err) {
            console.error("Erro no Copiloto:", err);
        } finally {
            setIsLoading(false);
        }
    };

    if (!isOpen) return null;

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
                        <p className={`text-[10px] font-black uppercase tracking-widest ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Estrategista Sênior</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button onClick={() => setShowHistory(!showHistory)} className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </button>
                    <button onClick={onClose} className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}>
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-hidden flex relative">
                {/* History Sidebar (Overlay logic or persistent) */}
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
                                            a: ({ node, ...props }) => <a className="text-blue-600 underline hover:text-blue-800" target="_blank" rel="noopener noreferrer" {...props} />,
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

                        {isLoading && (
                            <div className="flex justify-start">
                                <div className="px-4 py-3 rounded-2xl rounded-bl-none bg-slate-100 flex gap-1.5 items-center">
                                    <span className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" />
                                    <span className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                                    <span className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                                </div>
                            </div>
                        )}
                        <div ref={chatEndRef} />
                    </div>

                    {/* Footer Input */}
                    <div className={`shrink-0 p-6 border-t ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                        <div className="flex gap-3">
                            <textarea
                                value={input}
                                onChange={e => setInput(e.target.value)}
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
                                placeholder="Estrategize com Hermes…"
                                className={`flex-1 min-h-[50px] max-h-[150px] px-5 py-3.5 rounded-2xl text-sm font-medium outline-none border transition-all resize-none ${isDark ? 'bg-white/5 border-white/10 text-white placeholder:text-white/20 focus:border-blue-500' : 'bg-slate-50 border-slate-200 text-slate-700 placeholder:text-slate-400 focus:border-blue-500'}`}
                            />
                            <button
                                onClick={() => {
                                    if (!currentSessionId) {
                                        handleCreateSession(input);
                                    } else {
                                        sendMessage(input);
                                    }
                                }}
                                disabled={isLoading || !input.trim()}
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
