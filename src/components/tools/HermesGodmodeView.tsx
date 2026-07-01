import React, { useState, useEffect, useRef } from 'react';
import { db, functions } from '@/firebase';
import { httpsCallable } from 'firebase/functions';
import { collection, query, orderBy, onSnapshot } from 'firebase/firestore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AutoExpandingTextarea } from '../ui/UIComponents';

const GODMODE_CALLABLE_TIMEOUT_MS = 240000;

interface GodmodeMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    toolsUsed?: string[];
    modelUsed?: string;
    timestamp?: { seconds: number };
}

interface HermesGodmodeViewProps {
    isDark?: boolean;
    showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
}

export const HermesGodmodeView: React.FC<HermesGodmodeViewProps> = ({ isDark, showToast }) => {
    const [sessionId, setSessionId] = useState<string>(() => localStorage.getItem('hermes-godmode-session') || '');
    const [messages, setMessages] = useState<GodmodeMessage[]>([]);
    const [input, setInput] = useState('');
    const [isSending, setIsSending] = useState(false);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!sessionId) return;
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
    };

    return (
        <div className={`flex flex-col h-[calc(100vh-7.5rem)] min-h-[520px] rounded-2xl border ${isDark ? 'border-white/10 bg-black/20' : 'border-slate-200 bg-white'}`}>
            <div className={`flex items-center justify-between px-5 py-4 border-b ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
                <div>
                    <h2 className="text-sm font-black uppercase tracking-widest font-mono">Hermes Godmode</h2>
                    <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                        Conselheiro adversário — auditoria de premissas com dados reais do sistema.
                    </p>
                </div>
                <button
                    onClick={handleNewSession}
                    className={`text-[11px] font-black uppercase tracking-widest px-3 py-2 rounded-xl border ${isDark ? 'border-white/10 text-slate-300 hover:bg-white/5' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                >
                    Nova sessão
                </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
                {messages.length === 0 && (
                    <div className={`text-sm ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                        Faça uma pergunta estratégica — orçamento, projetos, bolsistas, metas. O Godmode vai buscar os dados reais antes de responder.
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
                            {(!!msg.toolsUsed?.length || msg.modelUsed) && (
                                <div className={`mt-2 text-[10px] uppercase tracking-widest font-mono ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                    {msg.modelUsed && <span>Modelo: {msg.modelUsed}</span>}
                                    {!!msg.toolsUsed?.length && <span>{msg.modelUsed ? ' · ' : ''}Ferramentas: {msg.toolsUsed.join(', ')}</span>}
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
