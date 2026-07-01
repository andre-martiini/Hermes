import React, { useState, useEffect, useRef } from 'react';
import { db, functions } from '@/firebase';
import { httpsCallable } from 'firebase/functions';
import { collection, query, orderBy, onSnapshot, where, limit } from 'firebase/firestore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { formatDate } from '@/types';
import { AutoExpandingTextarea } from '../ui/UIComponents';

const GODMODE_CALLABLE_TIMEOUT_MS = 240000;

interface GodmodeMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    toolsUsed?: string[];
    timestamp?: { seconds: number };
}

interface GodmodeSession {
    id: string;
    titulo?: string;
    lastMessageAt?: { seconds: number };
}

interface HermesGodmodeViewProps {
    userId: string;
    isDark?: boolean;
    showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
}

export const HermesGodmodeView: React.FC<HermesGodmodeViewProps> = ({ userId, isDark, showToast }) => {
    const [sessionId, setSessionId] = useState<string>(() => localStorage.getItem('hermes-godmode-session') || '');
    const [messages, setMessages] = useState<GodmodeMessage[]>([]);
    const [sessions, setSessions] = useState<GodmodeSession[]>([]);
    const [isHistoryOpen, setIsHistoryOpen] = useState(false);
    const [input, setInput] = useState('');
    const [isSending, setIsSending] = useState(false);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!sessionId) {
            setMessages([]);
            return;
        }
        const q = query(
            collection(db, 'sessoes_godmode', sessionId, 'mensagens'),
            orderBy('timestamp', 'asc')
        );
        const unsub = onSnapshot(q, (snapshot) => {
            setMessages(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as GodmodeMessage)));
        });
        return () => unsub();
    }, [sessionId]);

    useEffect(() => {
        if (!userId) return;
        const q = query(
            collection(db, 'sessoes_godmode'),
            where('userId', '==', userId),
            orderBy('lastMessageAt', 'desc'),
            limit(30)
        );
        const unsub = onSnapshot(q, (snapshot) => {
            setSessions(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as GodmodeSession)));
        });
        return () => unsub();
    }, [userId]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSend = async () => {
        const prompt = input.trim();
        if (!prompt || isSending) return;

        setInput('');
        setIsSending(true);
        try {
            const askGodmode = httpsCallable(functions, 'askHermesGodmode', { timeout: GODMODE_CALLABLE_TIMEOUT_MS });
            const response = await askGodmode({ prompt, sessionId: sessionId || undefined });
            const data = response.data as { sessionId: string };
            if (data.sessionId && data.sessionId !== sessionId) {
                setSessionId(data.sessionId);
                localStorage.setItem('hermes-godmode-session', data.sessionId);
            }
        } catch (error: any) {
            showToast(error?.message || 'Falha ao consultar o Hermes Godmode.', 'error');
        } finally {
            setIsSending(false);
        }
    };

    const handleNewSession = () => {
        setSessionId('');
        setMessages([]);
        localStorage.removeItem('hermes-godmode-session');
        setIsHistoryOpen(false);
    };

    const handleSelectSession = (id: string) => {
        setSessionId(id);
        localStorage.setItem('hermes-godmode-session', id);
        setIsHistoryOpen(false);
    };

    return (
        <div className={`relative flex flex-col h-[calc(100vh-7.5rem)] min-h-[520px] rounded-2xl border overflow-hidden ${isDark ? 'border-white/10 bg-black/20' : 'border-slate-200 bg-white'}`}>
            <div className={`flex items-center justify-between px-5 py-4 border-b ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
                <div className="flex items-center gap-3 min-w-0">
                    <button
                        onClick={() => setIsHistoryOpen(prev => !prev)}
                        className={`shrink-0 p-2 rounded-xl border transition-all ${isDark ? 'border-white/10 text-slate-300 hover:bg-white/5' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                        aria-label="Histórico de conversas"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h7" /></svg>
                    </button>
                    <div className="min-w-0">
                        <h2 className="text-sm font-black uppercase tracking-widest font-mono">Hermes Godmode</h2>
                        <p className={`text-xs mt-0.5 truncate ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                            Conselheiro adversário — auditoria de premissas com dados reais do sistema.
                        </p>
                    </div>
                </div>
                <button
                    onClick={handleNewSession}
                    className={`shrink-0 text-[11px] font-black uppercase tracking-widest px-3 py-2 rounded-xl border ${isDark ? 'border-white/10 text-slate-300 hover:bg-white/5' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                >
                    Nova sessão
                </button>
            </div>

            {isHistoryOpen && (
                <div className="absolute inset-0 z-20 flex">
                    <div
                        className="w-full sm:w-80 h-full flex flex-col border-r animate-in slide-in-from-left duration-200"
                        style={isDark ? { background: '#0a0f1a', borderColor: 'rgba(255,255,255,0.1)' } : { background: '#ffffff', borderColor: '#e2e8f0' }}
                    >
                        <div className={`flex items-center justify-between px-4 py-4 border-b ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
                            <h3 className="text-xs font-black uppercase tracking-widest font-mono">Histórico</h3>
                            <button
                                onClick={() => setIsHistoryOpen(false)}
                                className={`p-1.5 rounded-lg ${isDark ? 'text-slate-400 hover:bg-white/5' : 'text-slate-500 hover:bg-slate-100'}`}
                                aria-label="Fechar histórico"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto">
                            {sessions.length === 0 && (
                                <div className={`px-4 py-6 text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                    Nenhuma conversa anterior ainda.
                                </div>
                            )}
                            {sessions.map(s => (
                                <button
                                    key={s.id}
                                    onClick={() => handleSelectSession(s.id)}
                                    className={`w-full text-left px-4 py-3 border-b transition-colors ${isDark ? 'border-white/5' : 'border-slate-100'} ${
                                        s.id === sessionId
                                            ? (isDark ? 'bg-white/[0.06]' : 'bg-slate-50')
                                            : (isDark ? 'hover:bg-white/[0.03]' : 'hover:bg-slate-50/60')
                                    }`}
                                >
                                    <p className={`text-sm font-semibold truncate ${isDark ? 'text-slate-100' : 'text-slate-800'}`}>
                                        {s.titulo || 'Conversa sem título'}
                                    </p>
                                    <p className={`text-[10px] mt-1 uppercase tracking-widest font-mono ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                        {s.lastMessageAt ? formatDate(s.lastMessageAt) : ''}
                                    </p>
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="flex-1 h-full bg-black/40" onClick={() => setIsHistoryOpen(false)} />
                </div>
            )}

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
                {messages.length === 0 && (
                    <div className={`text-sm ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                        Faça uma pergunta estratégica — tarefas, financeiro, saúde, metas. O Godmode vai buscar os dados reais antes de responder.
                    </div>
                )}
                {messages.map(msg => (
                    <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                            msg.role === 'user'
                                ? (isDark ? 'bg-primary-tactile/20 text-white' : 'bg-primary-tactile/10 text-slate-900')
                                : (isDark ? 'bg-white/[0.04] text-slate-100' : 'bg-slate-50 text-slate-800')
                        }`}>
                            <div className="prose prose-sm max-w-none dark:prose-invert">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                            </div>
                            {!!msg.toolsUsed?.length && (
                                <div className={`mt-2 text-[10px] uppercase tracking-widest font-mono ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                    Ferramentas: {msg.toolsUsed.join(', ')}
                                </div>
                            )}
                        </div>
                    </div>
                ))}
                {isSending && (
                    <div className={`text-xs italic ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Godmode está analisando…</div>
                )}
                <div ref={bottomRef} />
            </div>

            <div className={`px-5 py-4 border-t ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
                <div className="flex items-end gap-3">
                    <AutoExpandingTextarea
                        value={input}
                        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
                        onKeyDown={(e: React.KeyboardEvent) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSend();
                            }
                        }}
                        placeholder="Pergunte ao Godmode..."
                        className={`flex-1 resize-none rounded-xl border px-4 py-3 text-sm ${isDark ? 'border-white/10 bg-white/[0.03] text-white placeholder:text-slate-500' : 'border-slate-200 bg-white text-slate-900 placeholder:text-slate-400'}`}
                    />
                    <button
                        onClick={handleSend}
                        disabled={isSending || !input.trim()}
                        className="px-5 py-3 rounded-xl bg-primary-tactile text-white text-xs font-black uppercase tracking-widest disabled:opacity-40"
                    >
                        Enviar
                    </button>
                </div>
            </div>
        </div>
    );
};

export default HermesGodmodeView;
