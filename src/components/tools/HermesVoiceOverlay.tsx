import React, { useEffect, useRef, useState } from 'react';
import { useHermesVoiceStream } from '../../hooks/useHermesVoiceStream';

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

/**
 * Modo de conversa por voz "flutuante": em vez de abrir o copiloto inteiro,
 * a bolinha do canto vira um indicador de gravacao ao vivo e os turnos da
 * conversa (usuario e Hermes) aparecem como baloes sobrepostos ao sistema,
 * proximos ao canto inferior direito. O usuario continua navegando livremente
 * — o container nao captura cliques fora dos proprios baloes/botoes.
 */
export const HermesVoiceOverlay: React.FC<HermesVoiceOverlayProps> = ({ isDark, onExit, onUICommand, uiContext }) => {
    const [bubbles, setBubbles] = useState<VoiceBubbleItem[]>([]);
    const [statusMessage, setStatusMessage] = useState('');
    const [errorMessage, setErrorMessage] = useState('');
    const nextIdRef = useRef(1);
    const startedRef = useRef(false);

    const pushBubble = (role: 'user' | 'assistant', text: string) => {
        setBubbles(prev => [...prev.slice(-(MAX_VISIBLE_BUBBLES - 1)), { id: nextIdRef.current++, role, text }]);
    };

    const voiceStream = useHermesVoiceStream({
        onUserTranscript: (text) => pushBubble('user', text),
        onAssistantTranscript: (text) => pushBubble('assistant', text),
        onStatus: (message) => { setStatusMessage(message); setErrorMessage(''); },
        onError: (message) => { setErrorMessage(message); setStatusMessage(''); },
        onUICommand,
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

    const isLive = voiceStream.status === 'live';
    const isConnecting = voiceStream.status === 'connecting';
    const isError = voiceStream.status === 'error';

    const assistantBubbleClass = isDark
        ? 'bg-slate-800/95 text-slate-100 border border-white/10'
        : 'bg-white/95 text-slate-800 border border-slate-200 shadow-sm';
    const userBubbleClass = 'bg-indigo-600/95 text-white';

    return (
        <div className="pointer-events-none fixed bottom-6 right-6 z-[650] flex w-[min(20rem,calc(100vw-3rem))] flex-col items-end gap-2">
            {/* Baloes da conversa (ultimos turnos), do mais antigo para o mais recente */}
            {bubbles.length > 0 && (
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

            {/* Chip de status/erro */}
            {(errorMessage || statusMessage || isConnecting) && (
                <div
                    className={`pointer-events-auto max-w-full truncate rounded-full px-3 py-1 text-[11px] font-medium backdrop-blur-sm ${
                        errorMessage
                            ? 'bg-rose-600/90 text-white'
                            : isDark ? 'bg-white/10 text-slate-200' : 'bg-slate-900/80 text-white'
                    }`}
                    title={errorMessage || statusMessage}
                >
                    {errorMessage || statusMessage || 'Conectando à voz ao vivo…'}
                </div>
            )}

            <div className="flex items-center gap-2">
                {/* Tentar de novo apos erro */}
                {isError && (
                    <button
                        type="button"
                        onClick={() => { setErrorMessage(''); voiceStream.start(); }}
                        className="pointer-events-auto rounded-full bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-lg transition-all hover:bg-indigo-500 active:scale-95"
                    >
                        Tentar de novo
                    </button>
                )}

                {/* Bolinha em modo gravacao — clicar encerra a conversa */}
                <button
                    type="button"
                    aria-label="Encerrar conversa por voz"
                    title="Encerrar conversa por voz"
                    onClick={onExit}
                    className={`pointer-events-auto relative flex h-14 w-14 items-center justify-center rounded-full text-white shadow-lg transition-all hover:-translate-y-0.5 active:scale-95 sm:h-16 sm:w-16 ${
                        isError
                            ? 'bg-rose-600 shadow-rose-600/40'
                            : isConnecting
                                ? 'bg-amber-500 shadow-amber-500/40'
                                : 'bg-emerald-600 shadow-emerald-600/40'
                    }`}
                >
                    {/* Aneis pulsantes indicando gravacao ativa */}
                    {isLive && (
                        <>
                            <span className="absolute inset-0 animate-ping rounded-full bg-emerald-500/40" />
                            <span className="absolute -inset-1.5 animate-pulse rounded-full border-2 border-emerald-400/50" />
                        </>
                    )}
                    {isConnecting ? (
                        <svg className="h-6 w-6 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                        </svg>
                    ) : (
                        <svg className="relative h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 10v2a7 7 0 01-14 0v-2" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19v3" />
                        </svg>
                    )}
                </button>
            </div>
        </div>
    );
};
