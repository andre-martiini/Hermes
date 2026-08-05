import React, { useCallback, useEffect, useRef, useState } from 'react';
import { auth } from '@/firebase';
import { useHermesVoiceStream, VoiceDocumentPayload } from '../../hooks/useHermesVoiceStream';

interface VoiceBubbleItem {
    id: number;
    role: 'user' | 'assistant';
    text: string;
}

interface HermesVoiceOverlayProps {
    isDark: boolean;
    /** Encerra o modo de voz e devolve a bolinha normal do copiloto. */
    onExit: () => void;
    onUICommand?: (command: string, params: any) => void;
    uiContext?: any;
}

const MAX_VISIBLE_BUBBLES = 6;
const MAX_FILES = 10;
const MAX_FILE_SIZE_MB = 20;
const ACCEPTED_TYPES = '.pdf,.doc,.docx,.txt,.csv,.xlsx,.md';
const UPLOAD_ENDPOINT = 'https://us-central1-gestao-hermes.cloudfunctions.net/uploadFileForCopiloto';
const EXTRACT_ENDPOINT = 'https://us-central1-gestao-hermes.cloudfunctions.net/extractDocumentTextForVoice';

type DocProcessingStatus = 'idle' | 'uploading' | 'extracting' | 'sending' | 'done';

/**
 * Modo de conversa por voz "flutuante" com suporte a ingestão de documentos.
 * O usuário pode arrastar arquivos ou clicar no botão 📎 para enviar até 10
 * documentos que serão processados e injetados como contexto na sessão Gemini Live.
 */
export const HermesVoiceOverlay: React.FC<HermesVoiceOverlayProps> = ({ isDark, onExit, onUICommand, uiContext }) => {
    const [bubbles, setBubbles] = useState<VoiceBubbleItem[]>([]);
    const [statusMessage, setStatusMessage] = useState('');
    const [errorMessage, setErrorMessage] = useState('');
    const [isMinimized, setIsMinimized] = useState(false);
    const [isDragOver, setIsDragOver] = useState(false);
    const [docStatus, setDocStatus] = useState<DocProcessingStatus>('idle');
    const [docProgress, setDocProgress] = useState('');
    const [ingestedDocs, setIngestedDocs] = useState<string[]>([]);

    const nextIdRef = useRef(1);
    const startedRef = useRef(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const dragCounterRef = useRef(0);
    const processFilesRef = useRef<(files: File[]) => void>(() => {});
    const documentAckTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const pushBubble = (role: 'user' | 'assistant', text: string) => {
        setBubbles(prev => [...prev.slice(-(MAX_VISIBLE_BUBBLES - 1)), { id: nextIdRef.current++, role, text }]);
    };

    const handleDocumentIngested = useCallback((fileNames: string[]) => {
        if (documentAckTimerRef.current) {
            clearTimeout(documentAckTimerRef.current);
            documentAckTimerRef.current = null;
        }
        setIngestedDocs(prev => [...prev, ...fileNames]);
        setDocStatus('done');
        setDocProgress('');
        const names = fileNames.join(', ');
        pushBubble('assistant', `📄 Recebi ${fileNames.length > 1 ? 'os documentos' : 'o documento'}: ${names}. Pode perguntar sobre ${fileNames.length > 1 ? 'eles' : 'ele'}!`);
        // Reset to idle after a beat
        setTimeout(() => setDocStatus('idle'), 500);
    }, []);

    const handleDocumentError = useCallback((message: string) => {
        if (documentAckTimerRef.current) {
            clearTimeout(documentAckTimerRef.current);
            documentAckTimerRef.current = null;
        }
        setDocStatus('idle');
        setDocProgress('');
        setErrorMessage(message);
    }, []);

    const voiceStream = useHermesVoiceStream({
        onUserTranscript: (text) => pushBubble('user', text),
        onAssistantTranscript: (text) => pushBubble('assistant', text),
        onStatus: (message) => { setStatusMessage(message); setErrorMessage(''); },
        onError: (message) => { setErrorMessage(message); setStatusMessage(''); },
        onUICommand,
        onDocumentIngested: handleDocumentIngested,
        onDocumentError: handleDocumentError,
    });

    const voiceStreamRef = useRef(voiceStream);
    voiceStreamRef.current = voiceStream;

    useEffect(() => {
        if (!startedRef.current) {
            startedRef.current = true;
            voiceStreamRef.current.start();
        }
        return () => { voiceStreamRef.current.stop(); };
    }, []);

    const sendUIContextRef = useRef(voiceStream.sendUIContext);
    sendUIContextRef.current = voiceStream.sendUIContext;

    useEffect(() => {
        if (voiceStream.status === 'live' && uiContext) {
            sendUIContextRef.current(uiContext);
        }
    }, [uiContext, voiceStream.status]);

    // ── Document processing pipeline ─────────────────────────────────────────

    const processFiles = useCallback(async (files: File[]) => {
        if (files.length === 0) return;

        // Validate
        const valid = files.slice(0, MAX_FILES).filter(f => {
            if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
                setErrorMessage(`"${f.name}" excede ${MAX_FILE_SIZE_MB} MB e foi ignorado.`);
                return false;
            }
            return true;
        });
        if (valid.length === 0) return;

        setDocStatus('uploading');
        setDocProgress(`Enviando ${valid.length} arquivo(s)…`);
        setErrorMessage('');

        try {
            const idToken = await auth.currentUser?.getIdToken();
            if (!idToken) throw new Error('Usuário não autenticado.');

            // 1. Upload each file
            const uploaded: Array<{ driveFileId: string; fileName: string }> = [];
            for (let i = 0; i < valid.length; i++) {
                const file = valid[i];
                setDocProgress(`Enviando ${i + 1}/${valid.length}: ${file.name}…`);

                const formData = new FormData();
                formData.append('file', file, file.name);
                const uploadRes = await fetch(UPLOAD_ENDPOINT, {
                    method: 'POST',
                    headers: { Authorization: `Bearer ${idToken}` },
                    body: formData,
                });
                if (!uploadRes.ok) {
                    const body = await uploadRes.json().catch(() => ({}));
                    throw new Error(body.error || `Erro no upload: HTTP ${uploadRes.status}`);
                }
                const uploadData = await uploadRes.json();
                uploaded.push({ driveFileId: uploadData.driveFileId, fileName: uploadData.fileName || file.name });
            }

            // 2. Extract text for each file
            setDocStatus('extracting');
            const documents: VoiceDocumentPayload[] = [];
            for (let i = 0; i < uploaded.length; i++) {
                const { driveFileId, fileName } = uploaded[i];
                setDocProgress(`Processando ${i + 1}/${uploaded.length}: ${fileName}…`);

                const extractRes = await fetch(EXTRACT_ENDPOINT, {
                    method: 'POST',
                    headers: {
                        Authorization: `Bearer ${idToken}`,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ driveFileId, fileName }),
                });
                if (!extractRes.ok) {
                    const body = await extractRes.json().catch(() => ({}));
                    throw new Error(body.error || `Erro ao processar: HTTP ${extractRes.status}`);
                }
                const extractData = await extractRes.json();
                documents.push({
                    name: extractData.fileName || fileName,
                    text: extractData.text || '',
                    driveFileId,
                });
            }

            // 3. Envia ao voice bridge. A interface so conclui quando o bridge
            // confirma que o contexto foi efetivamente injetado no Gemini Live.
            setDocStatus('sending');
            setDocProgress('Injetando contexto…');
            const sent = voiceStreamRef.current.sendDocumentContext(documents);
            if (!sent) {
                throw new Error('A sessão de voz não está conectada. Reconecte e envie o documento novamente.');
            }

            documentAckTimerRef.current = setTimeout(() => {
                documentAckTimerRef.current = null;
                setDocStatus('idle');
                setDocProgress('');
                setErrorMessage('O servidor de voz não confirmou a leitura do documento. Reinicie a sessão de voz e tente novamente.');
            }, 15000);

        } catch (err: any) {
            setDocStatus('idle');
            setDocProgress('');
            setErrorMessage(err?.message || 'Erro ao processar o documento.');
        }
    }, []);

    useEffect(() => () => {
        if (documentAckTimerRef.current) clearTimeout(documentAckTimerRef.current);
    }, []);

    // ── Drag & Drop — listeners no window para funcionar com pointer-events-none ──

    // Mantém processFilesRef atualizado para usar nos listeners do window
    useEffect(() => { processFilesRef.current = processFiles; }, [processFiles]);

    useEffect(() => {
        const onDragEnter = (e: DragEvent) => {
            if (!e.dataTransfer?.types.includes('Files')) return;
            e.preventDefault();
            dragCounterRef.current++;
            setIsDragOver(true);
        };
        const onDragLeave = (e: DragEvent) => {
            e.preventDefault();
            dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
            if (dragCounterRef.current === 0) setIsDragOver(false);
        };
        const onDragOver = (e: DragEvent) => { e.preventDefault(); };
        const onDrop = (e: DragEvent) => {
            e.preventDefault();
            dragCounterRef.current = 0;
            setIsDragOver(false);
            const files = Array.from(e.dataTransfer?.files || []);
            if (files.length > 0) processFilesRef.current(files);
        };

        window.addEventListener('dragenter', onDragEnter);
        window.addEventListener('dragleave', onDragLeave);
        window.addEventListener('dragover', onDragOver);
        window.addEventListener('drop', onDrop);
        return () => {
            window.removeEventListener('dragenter', onDragEnter);
            window.removeEventListener('dragleave', onDragLeave);
            window.removeEventListener('dragover', onDragOver);
            window.removeEventListener('drop', onDrop);
        };
    }, []);

    const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        if (files.length > 0) processFiles(files);
        // Reset input so same file can be re-selected
        e.target.value = '';
    }, [processFiles]);

    // ── Derived state ─────────────────────────────────────────────────────────

    const isLive = voiceStream.status === 'live';
    const isConnecting = voiceStream.status === 'connecting';
    const isError = voiceStream.status === 'error';
    const isProcessingDocs = docStatus === 'uploading' || docStatus === 'extracting' || docStatus === 'sending';

    const assistantBubbleClass = isDark
        ? 'bg-slate-800/95 text-slate-100 border border-white/10'
        : 'bg-white/95 text-slate-800 border border-slate-200 shadow-sm';
    const userBubbleClass = 'bg-indigo-600/95 text-white';

    // Orb appearance
    const orbColor = isError
        ? 'bg-rose-600 shadow-rose-600/40'
        : isProcessingDocs
            ? 'bg-violet-600 shadow-violet-500/50'
            : isConnecting
                ? 'bg-amber-500 shadow-amber-500/40'
                : 'bg-emerald-600 shadow-emerald-600/40';

    const displayStatus = isProcessingDocs ? docProgress : errorMessage || statusMessage;
    const displayStatusType = isProcessingDocs ? 'processing' : errorMessage ? 'error' : 'info';

    return (
        <div className="pointer-events-none fixed inset-0 z-[650] flex items-end justify-end">
            {/* Drag overlay hint */}
            {isDragOver && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                    <div className="rounded-3xl border-2 border-dashed border-violet-400/70 bg-violet-900/40 px-10 py-8 text-center backdrop-blur-md">
                        <div className="mb-2 text-4xl">📄</div>
                        <p className="text-base font-semibold text-violet-200">Solte para enviar ao Hermes</p>
                        <p className="mt-1 text-xs text-violet-300/70">Até {MAX_FILES} arquivos · máx. {MAX_FILE_SIZE_MB} MB cada</p>
                    </div>
                </div>
            )}

            {/* Main overlay panel — bottom-right */}
            <div className={`pointer-events-none mb-6 mr-6 flex flex-col items-end gap-2 ${isMinimized ? '' : 'w-[min(20rem,calc(100vw-3rem))]'}`}>
                {/* Conversation bubbles */}
                {!isMinimized && bubbles.length > 0 && (
                    <div className="flex w-full flex-col items-end gap-1.5">
                        {bubbles.map(bubble => (
                            <div
                                key={bubble.id}
                                className={`pointer-events-auto max-w-full break-words rounded-2xl px-3.5 py-2 text-sm leading-snug backdrop-blur-sm animate-in fade-in slide-in-from-bottom-2 ${
                                    bubble.role === 'user'
                                        ? `${userBubbleClass} rounded-br-md self-end`
                                        : `${assistantBubbleClass} rounded-bl-md self-start`
                                }`}
                            >
                                {bubble.text}
                            </div>
                        ))}
                    </div>
                )}

                {/* Status / error / progress chip */}
                {!isMinimized && (displayStatus || isConnecting) && (
                    <div
                        className={`pointer-events-auto max-w-full truncate rounded-full px-3 py-1 text-[11px] font-medium backdrop-blur-sm ${
                            displayStatusType === 'error'
                                ? 'bg-rose-600/90 text-white'
                                : displayStatusType === 'processing'
                                    ? 'bg-violet-600/90 text-white'
                                    : isDark ? 'bg-white/10 text-slate-200' : 'bg-slate-900/80 text-white'
                        }`}
                        title={displayStatus}
                    >
                        {displayStatus || 'Conectando à voz ao vivo…'}
                    </div>
                )}

                {/* Ingested docs chip */}
                {!isMinimized && ingestedDocs.length > 0 && (
                    <div
                        className="pointer-events-auto max-w-full truncate rounded-full bg-violet-700/80 px-3 py-1 text-[11px] font-medium text-violet-100 backdrop-blur-sm"
                        title={`Documentos carregados: ${ingestedDocs.join(', ')}`}
                    >
                        📄 {ingestedDocs.length} doc{ingestedDocs.length > 1 ? 's' : ''} carregado{ingestedDocs.length > 1 ? 's' : ''}
                    </div>
                )}

                {/* Action row */}
                <div className="flex items-center gap-2">
                    {/* Retry after error */}
                    {isError && (
                        <button
                            type="button"
                            onClick={() => { setErrorMessage(''); voiceStream.start(); }}
                            className="pointer-events-auto rounded-full bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-lg transition-all hover:bg-indigo-500 active:scale-95"
                        >
                            Tentar de novo
                        </button>
                    )}

                    {/* 📎 Attach documents button */}
                    <button
                        type="button"
                        aria-label="Enviar documento para o Hermes"
                        title={isProcessingDocs ? docProgress : 'Enviar documento para o Hermes (PDF, DOCX, TXT…)'}
                        disabled={isProcessingDocs}
                        onClick={() => fileInputRef.current?.click()}
                        className={`pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full text-white shadow-lg transition-all hover:-translate-y-0.5 active:scale-95 disabled:cursor-wait disabled:opacity-60 ${
                            isProcessingDocs
                                ? 'bg-violet-600'
                                : isDark ? 'bg-slate-700 hover:bg-violet-600' : 'bg-slate-500 hover:bg-violet-600'
                        }`}
                    >
                        {isProcessingDocs ? (
                            <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                            </svg>
                        ) : (
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                            </svg>
                        )}
                    </button>

                    {/* Hidden file input */}
                    <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        accept={ACCEPTED_TYPES}
                        className="hidden"
                        onChange={handleFileInputChange}
                    />

                    {/* Voice orb — click to minimize/expand */}
                    <button
                        type="button"
                        aria-label={isMinimized ? 'Expandir conversa por voz' : 'Minimizar conversa por voz'}
                        title={isMinimized ? 'Expandir conversa por voz' : 'Minimizar conversa por voz'}
                        onClick={() => setIsMinimized(prev => !prev)}
                        className={`pointer-events-auto relative flex h-14 w-14 items-center justify-center rounded-full text-white shadow-lg transition-all hover:-translate-y-0.5 active:scale-95 sm:h-16 sm:w-16 ${orbColor}`}
                    >
                        {/* Pulsing rings — live */}
                        {isLive && !isProcessingDocs && (
                            <>
                                <span className="absolute inset-0 animate-ping rounded-full bg-emerald-500/40" />
                                <span className="absolute -inset-1.5 animate-pulse rounded-full border-2 border-emerald-400/50" />
                            </>
                        )}
                        {/* Processing rings — violet */}
                        {isProcessingDocs && (
                            <>
                                <span className="absolute inset-0 animate-ping rounded-full bg-violet-400/40" />
                                <span className="absolute -inset-1.5 animate-pulse rounded-full border-2 border-violet-300/60" />
                            </>
                        )}

                        {/* Orb icon */}
                        {isConnecting ? (
                            <svg className="h-6 w-6 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                            </svg>
                        ) : isProcessingDocs ? (
                            <svg className="relative h-6 w-6 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                        ) : (
                            <svg className="relative h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 10v2a7 7 0 01-14 0v-2" />
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19v3" />
                            </svg>
                        )}
                    </button>

                    {/* Exit button */}
                    <button
                        type="button"
                        aria-label="Encerrar conversa por voz"
                        title="Encerrar conversa por voz"
                        onClick={onExit}
                        className={`pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full text-white shadow-lg transition-all hover:-translate-y-0.5 active:scale-95 ${
                            isDark ? 'bg-slate-700 hover:bg-rose-600' : 'bg-slate-500 hover:bg-rose-600'
                        }`}
                    >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    );
};
