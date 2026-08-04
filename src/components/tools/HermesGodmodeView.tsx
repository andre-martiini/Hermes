import React, { useEffect, useRef, useState } from 'react';
import { db, functions, auth } from '@/firebase';
import { httpsCallable } from 'firebase/functions';
import { collection, query, orderBy, onSnapshot, where, limit } from 'firebase/firestore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { formatDate } from '@/types';
import { AutoExpandingTextarea } from '../ui/UIComponents';
import { buildRecordedAudioBlob, transcribeAudioViaStorage } from '@/src/utils/audioTranscription';
import {
    UPLOAD_ENDPOINT,
    COPILOTO_FILE_ACCEPT,
    COPILOTO_SUPPORTED_FORMATS_LABEL,
    isCopilotoFileSupported,
} from './HermesGlobalChat';

const GODMODE_CALLABLE_TIMEOUT_MS = 240000;

interface GodmodeMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    toolsUsed?: string[];
    modelUsed?: string;
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
    const [attachedFile, setAttachedFile] = useState<File | null>(null);
    const [uploadPhase, setUploadPhase] = useState<'idle' | 'uploading' | 'processing'>('idle');
    const [isRecording, setIsRecording] = useState(false);
    const [isProcessingMic, setIsProcessingMic] = useState(false);
    const [isDragActive, setIsDragActive] = useState(false);
    const messagesScrollRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);
    const micStreamRef = useRef<MediaStream | null>(null);
    const dragCounterRef = useRef(0);

    const isBlocked = isSending || uploadPhase !== 'idle' || isProcessingMic;

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
        // Rola apenas a lista interna de mensagens — scrollIntoView rolaria a
        // página inteira em mobile, escondendo o cabeçalho fixo do módulo.
        const el = messagesScrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages, isSending]);

    useEffect(() => {
        return () => {
            if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') mediaRecorderRef.current.stop();
            if (micStreamRef.current) micStreamRef.current.getTracks().forEach((track) => track.stop());
        };
    }, []);

    const attachFile = (file: File | null) => {
        if (!file) {
            setAttachedFile(null);
            return;
        }
        if (!isCopilotoFileSupported(file)) {
            setAttachedFile(null);
            showToast(`Formato ainda não suportado. Use ${COPILOTO_SUPPORTED_FORMATS_LABEL}.`, 'error');
            return;
        }
        setAttachedFile(file);
    };

    const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
        attachFile(event.target.files?.[0] ?? null);
        event.target.value = '';
    };

    const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
        const files = Array.from(event.clipboardData.files);
        const firstSupported = files.find((file) => isCopilotoFileSupported(file));
        if (firstSupported) {
            event.preventDefault();
            attachFile(firstSupported);
        }
    };

    const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
        if (!Array.from(event.dataTransfer.types).includes('Files') || isBlocked) return;
        event.preventDefault();
        event.stopPropagation();
        dragCounterRef.current = 0;
        setIsDragActive(false);
        attachFile(event.dataTransfer.files?.[0] ?? null);
    };

    const transcribeBlob = async (blob: Blob, extension = '.m4a') => {
        setIsProcessingMic(true);
        try {
            const data = await transcribeAudioViaStorage(blob, extension);
            if (data.refined) setInput((prev) => prev + (prev ? '\n' : '') + data.refined);
        } catch (err: any) {
            showToast('Erro ao transcrever áudio: ' + (err?.message || 'Tente novamente.'), 'error');
        } finally {
            setIsProcessingMic(false);
        }
    };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            micStreamRef.current = stream;
            const recorder = new MediaRecorder(stream);
            mediaRecorderRef.current = recorder;
            audioChunksRef.current = [];
            recorder.ondataavailable = (event) => {
                if (event.data.size > 0) audioChunksRef.current.push(event.data);
            };
            recorder.onstop = async () => {
                const blob = buildRecordedAudioBlob(audioChunksRef.current, recorder);
                if (micStreamRef.current) {
                    micStreamRef.current.getTracks().forEach((track) => track.stop());
                    micStreamRef.current = null;
                }
                await transcribeBlob(blob);
            };
            recorder.start();
            setIsRecording(true);
        } catch {
            showToast('Erro ao acessar microfone. Verifique as permissões.', 'error');
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop();
            setIsRecording(false);
        }
    };

    const handleSend = async () => {
        const prompt = input.trim();
        const fileToSend = attachedFile;
        if (!prompt && !fileToSend) return;
        if (isSending) return;

        setInput('');
        setAttachedFile(null);
        setIsSending(true);
        try {
            let driveFileId: string | undefined;
            let driveFileName: string | undefined;

            if (fileToSend) {
                setUploadPhase('uploading');
                const idToken = await auth.currentUser?.getIdToken();
                if (!idToken) throw new Error('Usuário não autenticado.');
                const formData = new FormData();
                formData.append('file', fileToSend, fileToSend.name);
                const uploadRes = await fetch(UPLOAD_ENDPOINT, {
                    method: 'POST',
                    headers: { Authorization: `Bearer ${idToken}` },
                    body: formData,
                });
                if (!uploadRes.ok) {
                    const errBody = await uploadRes.json().catch(() => ({}));
                    throw new Error(errBody.error || `Erro no upload: HTTP ${uploadRes.status}`);
                }
                const uploadData = await uploadRes.json();
                driveFileId = uploadData.driveFileId;
                driveFileName = uploadData.fileName || fileToSend.name;
                setUploadPhase('processing');
            }

            const askGodmode = httpsCallable(functions, 'askHermesGodmode', { timeout: GODMODE_CALLABLE_TIMEOUT_MS });
            const response = await askGodmode({
                prompt,
                sessionId: sessionId || undefined,
                driveFileId,
                driveFileName,
            });
            const data = response.data as { sessionId: string };
            if (data.sessionId && data.sessionId !== sessionId) {
                setSessionId(data.sessionId);
                localStorage.setItem('hermes-godmode-session', data.sessionId);
            }
        } catch (error: any) {
            showToast(error?.message || 'Falha ao consultar o Hermes Godmode.', 'error');
        } finally {
            setUploadPhase('idle');
            setIsSending(false);
        }
    };

    const handleNewSession = () => {
        setSessionId('');
        setMessages([]);
        setAttachedFile(null);
        setInput('');
        localStorage.removeItem('hermes-godmode-session');
        setIsHistoryOpen(false);
    };

    const handleSelectSession = (id: string) => {
        setSessionId(id);
        localStorage.setItem('hermes-godmode-session', id);
        setIsHistoryOpen(false);
    };

    return (
        <div
            className={`relative flex flex-col h-[calc(100dvh-7.5rem)] min-h-[520px] rounded-2xl border overflow-hidden ${
                isDark
                    ? 'border-violet-400/20 bg-gradient-to-br from-[#0b0714] via-[#160c2e] to-[#1c0f3b]'
                    : 'border-violet-200 bg-gradient-to-br from-white via-[#faf7ff] to-[#f0e6ff]'
            }`}
            onDragEnter={(event) => {
                if (!Array.from(event.dataTransfer.types).includes('Files') || isBlocked) return;
                event.preventDefault();
                dragCounterRef.current += 1;
                setIsDragActive(true);
            }}
            onDragOver={(event) => {
                if (!Array.from(event.dataTransfer.types).includes('Files') || isBlocked) return;
                event.preventDefault();
            }}
            onDragLeave={(event) => {
                if (!Array.from(event.dataTransfer.types).includes('Files')) return;
                event.preventDefault();
                dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
                if (dragCounterRef.current === 0) setIsDragActive(false);
            }}
            onDrop={handleDrop}
        >
            {/* Glow decorativo — sutil, não interativo */}
            <div className="pointer-events-none absolute -top-24 -right-24 h-72 w-72 rounded-full bg-violet-500/20 blur-3xl" aria-hidden="true" />
            <div className="pointer-events-none absolute -bottom-32 -left-16 h-64 w-64 rounded-full bg-fuchsia-400/10 blur-3xl" aria-hidden="true" />

            {isDragActive && (
                <div className={`pointer-events-none absolute inset-0 z-[30] flex items-center justify-center border-4 border-dashed ${isDark ? 'border-violet-400 bg-violet-950/40' : 'border-violet-400 bg-violet-50/80'}`}>
                    <div className={`rounded-xl border px-8 py-6 text-center backdrop-blur-sm ${isDark ? 'border-violet-400/30 bg-black/40' : 'border-violet-200 bg-white/80'}`}>
                        <p className="font-mono text-[10px] font-black uppercase tracking-[0.25em] text-violet-500">Solte para anexar</p>
                        <p className={`mt-2 text-xs font-bold ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>O arquivo será enviado como contexto desta conversa.</p>
                    </div>
                </div>
            )}

            <div className={`relative flex items-center justify-between px-5 py-4 border-b backdrop-blur-sm ${isDark ? 'border-violet-400/10' : 'border-violet-200/70'}`}>
                <div className="flex items-center gap-3 min-w-0">
                    <button
                        onClick={() => setIsHistoryOpen(prev => !prev)}
                        className={`shrink-0 p-2 rounded-xl border transition-all ${isDark ? 'border-violet-400/20 text-violet-200 hover:bg-violet-500/10' : 'border-violet-200 text-violet-700 hover:bg-violet-50'}`}
                        aria-label="Histórico de conversas"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h7" /></svg>
                    </button>
                    <div className="min-w-0">
                        <h2 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest font-mono">
                            <span className="relative flex h-2 w-2">
                                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-violet-400 opacity-60" />
                                <span className="relative inline-flex h-2 w-2 rounded-full bg-violet-500" />
                            </span>
                            <span className="bg-gradient-to-r from-violet-600 via-fuchsia-500 to-violet-400 bg-clip-text text-transparent">
                                Hermes Godmode
                            </span>
                        </h2>
                        <p className={`text-xs mt-0.5 truncate ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                            Conselheiro adversário — auditoria de premissas com dados reais do sistema.
                        </p>
                    </div>
                </div>
                <button
                    onClick={handleNewSession}
                    className={`shrink-0 text-[11px] font-black uppercase tracking-widest px-3 py-2 rounded-xl border transition-all ${isDark ? 'border-violet-400/20 text-violet-200 hover:bg-violet-500/10' : 'border-violet-200 text-violet-700 hover:bg-violet-50'}`}
                >
                    Nova sessão
                </button>
            </div>

            {isHistoryOpen && (
                <div className="absolute inset-0 z-20 flex">
                    <div
                        className={`w-full sm:w-80 h-full flex flex-col border-r animate-in slide-in-from-left duration-200 backdrop-blur-md ${
                            isDark ? 'bg-[#0b0714]/95 border-violet-400/10' : 'bg-white/95 border-violet-200'
                        }`}
                    >
                        <div className={`flex items-center justify-between px-4 py-4 border-b ${isDark ? 'border-violet-400/10' : 'border-violet-200'}`}>
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
                                            ? (isDark ? 'bg-violet-500/10' : 'bg-violet-50')
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

            <div ref={messagesScrollRef} className="relative flex-1 overflow-y-auto overscroll-contain px-5 py-4 space-y-4">
                {messages.length === 0 && (
                    <div className={`text-sm ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                        Faça uma pergunta estratégica — tarefas, financeiro, saúde, metas. O Godmode vai buscar os dados reais antes de responder.
                    </div>
                )}
                {messages.map(msg => (
                    <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                            msg.role === 'user'
                                ? 'bg-gradient-to-br from-violet-600 to-fuchsia-500 text-white shadow-lg shadow-violet-500/20'
                                : (isDark ? 'border border-violet-400/10 bg-white/[0.04] text-slate-100' : 'border border-violet-100 bg-white/70 text-slate-800 backdrop-blur-sm')
                        }`}>
                            <div className="prose prose-sm max-w-none dark:prose-invert">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                            </div>
                            {(!!msg.toolsUsed?.length || msg.modelUsed) && (
                                <div className={`mt-2 text-[10px] uppercase tracking-widest font-mono ${msg.role === 'user' ? 'text-white/70' : (isDark ? 'text-slate-500' : 'text-slate-400')}`}>
                                    {msg.modelUsed && <span>Modelo: {msg.modelUsed}</span>}
                                    {!!msg.toolsUsed?.length && <span>{msg.modelUsed ? ' · ' : ''}Ferramentas: {msg.toolsUsed.join(', ')}</span>}
                                </div>
                            )}
                        </div>
                    </div>
                ))}
                {isSending && (
                    <div className={`flex items-center gap-2 text-xs italic ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet-500" />
                        {uploadPhase === 'uploading' ? 'Enviando arquivo...' : uploadPhase === 'processing' ? 'Processando anexo...' : 'Godmode está analisando…'}
                    </div>
                )}
            </div>

            <div className={`relative px-5 py-4 border-t backdrop-blur-sm ${isDark ? 'border-violet-400/10' : 'border-violet-200/70'}`}>
                {(attachedFile || isProcessingMic) && (
                    <div className={`mb-3 flex items-center gap-2 rounded-xl border px-3 py-2 text-[11px] font-bold ${isDark ? 'border-violet-400/20 bg-violet-500/5 text-slate-200' : 'border-violet-200 bg-violet-50 text-slate-700'}`}>
                        <span className={isDark ? 'text-slate-400' : 'text-slate-500'}>{isProcessingMic ? 'Transcrevendo áudio' : 'Anexo pronto'}</span>
                        <span className="min-w-0 flex-1 truncate">{attachedFile?.name || 'Microfone'}</span>
                        {attachedFile && (
                            <button type="button" onClick={() => setAttachedFile(null)} className="font-black uppercase tracking-wider text-rose-500">Remover</button>
                        )}
                    </div>
                )}
                <div className={`flex items-end gap-1.5 rounded-2xl border px-2 py-2 transition-shadow ${
                    isDark ? 'border-violet-400/20 bg-white/[0.03] focus-within:shadow-[0_0_0_1px_rgba(167,139,250,0.4)]' : 'border-violet-200 bg-white/80 focus-within:shadow-[0_0_0_1px_rgba(139,92,246,0.35)]'
                }`}>
                    <input ref={fileInputRef} type="file" accept={COPILOTO_FILE_ACCEPT} className="hidden" onChange={handleFileSelect} />
                    <button
                        type="button"
                        disabled={isBlocked}
                        onClick={() => fileInputRef.current?.click()}
                        title="Anexar arquivo"
                        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all disabled:opacity-30 ${isDark ? 'text-violet-200 hover:bg-violet-500/10' : 'text-violet-700 hover:bg-violet-50'}`}
                    >
                        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v14m-7-7h14" /></svg>
                    </button>
                    <AutoExpandingTextarea
                        value={input}
                        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
                        onPaste={handlePaste}
                        onKeyDown={(e: React.KeyboardEvent) => {
                            if (e.key === 'Enter' && !e.shiftKey && window.innerWidth >= 640) {
                                e.preventDefault();
                                handleSend();
                            }
                        }}
                        disabled={isBlocked}
                        placeholder={isRecording ? 'Gravando... clique no microfone para parar' : isProcessingMic ? 'Transcrevendo áudio...' : attachedFile ? 'Pergunte sobre o anexo...' : 'Pergunte ao Godmode...'}
                        className={`min-h-10 flex-1 resize-none bg-transparent px-2 py-2.5 text-sm disabled:opacity-40 ${isDark ? 'text-white placeholder:text-slate-500' : 'text-slate-900 placeholder:text-slate-400'}`}
                    />
                    <button
                        type="button"
                        disabled={isBlocked && !isRecording}
                        onClick={() => isRecording ? stopRecording() : startRecording()}
                        title={isRecording ? 'Parar gravação' : 'Gravar áudio'}
                        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all disabled:opacity-30 ${
                            isRecording
                                ? 'animate-pulse bg-rose-600 text-white'
                                : (isDark ? 'text-violet-200 hover:bg-violet-500/10' : 'text-violet-700 hover:bg-violet-50')
                        }`}
                    >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 10v2a7 7 0 01-14 0v-2m14 0h2m-16 0H3m9 10v3m-3 0h6" /></svg>
                    </button>
                    <button
                        onClick={handleSend}
                        disabled={isBlocked || (!input.trim() && !attachedFile)}
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-fuchsia-500 text-white shadow-md shadow-violet-500/30 transition-all hover:brightness-110 disabled:opacity-30 disabled:shadow-none"
                        title="Enviar"
                    >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                    </button>
                </div>
            </div>
        </div>
    );
};

export default HermesGodmodeView;
