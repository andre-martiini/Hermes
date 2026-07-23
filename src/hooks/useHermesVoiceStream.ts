import { useCallback, useRef, useState } from 'react';
import { auth } from '@/firebase';

export type VoiceStreamStatus = 'idle' | 'connecting' | 'live' | 'error';

interface UseHermesVoiceStreamOptions {
    onUserTranscript: (text: string) => void;
    onAssistantTranscript: (text: string) => void;
    onStatus?: (message: string) => void;
    onError?: (message: string) => void;
    /** Se a sessao de voz nasce dentro de uma acao, o bridge recebe o id e
     * injeta contexto + ferramentas de escrita daquela acao. */
    taskId?: string | null;
}

const MIC_SAMPLE_RATE = 16000;
const PROCESSOR_BUFFER_SIZE = 4096;
// Nivel de energia (RMS) acima do qual consideramos que o usuario comecou a
// falar por cima do Hermes — usado so para cortar a reproducao local na hora
// (o barge-in "de verdade" ja e nativo do Gemini Live do lado do servidor).
const BARGE_IN_RMS_THRESHOLD = 0.02;

function resolveBridgeUrl(): string {
    const configured = (import.meta as any).env?.VITE_HERMES_VOICE_BRIDGE_URL;
    return (configured || 'http://localhost:3002').replace(/\/$/, '');
}

function toWebSocketUrl(httpUrl: string): string {
    return httpUrl.replace(/^http/, 'ws') + '/browser-voice-stream';
}

// O Gemini Live manda a transcricao em fragmentos (por token/palavra) que nem
// sempre incluem o espaco separador — concatenar direto gruda as palavras
// ("uminstante"). So insere espaco quando nenhum dos dois lados ja resolve a
// separacao sozinho (espaco existente, ou pontuacao que naturalmente cola).
function appendTranscriptFragment(existing: string, fragment: string): string {
    if (!fragment) return existing;
    if (!existing) return fragment;

    const lastChar = existing[existing.length - 1];
    const firstChar = fragment[0];
    const noSpaceNeeded =
        /\s/.test(lastChar) ||
        /\s/.test(firstChar) ||
        /[.,!?;:)\]}%]/.test(firstChar) ||
        /[([{]/.test(lastChar);

    return existing + (noSpaceNeeded ? '' : ' ') + fragment;
}

// O transcritor do Gemini Live ocasionalmente degenera e emite o mesmo token
// centenas de vezes ("y y y y..."). Colapsa repeticoes longas preservando
// gaguejos curtos genuinos da fala, e descarta transcricoes que eram so ruido.
function sanitizeTranscript(raw: string): string {
    const text = raw.trim();
    if (!text) return '';

    const tokens = text.split(/\s+/);
    const distinct = new Set(tokens.map(t => t.toLowerCase()));
    if (tokens.length >= 20 && distinct.size <= 2) return '';

    const collapsed: string[] = [];
    let runLength = 0;
    for (const token of tokens) {
        if (collapsed.length > 0 && collapsed[collapsed.length - 1].toLowerCase() === token.toLowerCase()) {
            runLength += 1;
            if (runLength >= 4) continue;
        } else {
            runLength = 1;
        }
        collapsed.push(token);
    }
    return collapsed.join(' ');
}

function base64ToInt16(base64: string): Int16Array {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Int16Array(bytes.buffer);
}

function int16ToBase64(int16: Int16Array): string {
    const bytes = new Uint8Array(int16.buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
}

/**
 * Conversa por voz em tempo real com o copiloto Hermes via Gemini Live,
 * atraves do hermes-voice-bridge. Sem push-to-talk: o microfone fica aberto
 * continuamente enquanto a sessao estiver ativa — VAD, turn-taking e barge-in
 * sao nativos do Gemini Live do lado do servidor.
 */
export function useHermesVoiceStream(options: UseHermesVoiceStreamOptions) {
    const [status, setStatus] = useState<VoiceStreamStatus>('idle');

    const wsRef = useRef<WebSocket | null>(null);
    const micStreamRef = useRef<MediaStream | null>(null);
    const micAudioContextRef = useRef<AudioContext | null>(null);
    const micProcessorRef = useRef<ScriptProcessorNode | null>(null);
    const micSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
    const micGainSinkRef = useRef<GainNode | null>(null);

    const playbackContextRef = useRef<AudioContext | null>(null);
    const nextPlaybackTimeRef = useRef(0);
    const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);

    const userTranscriptRef = useRef('');
    const assistantTranscriptRef = useRef('');
    // Guarda se a captura de mic ja foi iniciada nesta sessao: o servidor manda
    // varias mensagens de status ao longo da conversa (uma por tool call, por
    // exemplo) e re-iniciar a captura a cada uma criaria processadores de audio
    // duplicados mandando audio embaralhado pro Gemini.
    const micStartedRef = useRef(false);
    const statusRef = useRef<VoiceStreamStatus>('idle');

    const stopAssistantPlayback = useCallback(() => {
        for (const source of activeSourcesRef.current) {
            try { source.stop(); } catch { /* ja pode ter terminado sozinho */ }
        }
        activeSourcesRef.current = [];
        if (playbackContextRef.current) {
            nextPlaybackTimeRef.current = playbackContextRef.current.currentTime;
        }
    }, []);

    const playAudioChunk = useCallback((base64Payload: string, sampleRate: number) => {
        const int16 = base64ToInt16(base64Payload);
        if (int16.length === 0) return;

        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x8000;

        if (!playbackContextRef.current) {
            playbackContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
            nextPlaybackTimeRef.current = playbackContextRef.current.currentTime;
        }
        const audioCtx = playbackContextRef.current;
        const buffer = audioCtx.createBuffer(1, float32.length, sampleRate);
        buffer.copyToChannel(float32, 0);

        const source = audioCtx.createBufferSource();
        source.buffer = buffer;
        source.connect(audioCtx.destination);
        activeSourcesRef.current.push(source);
        source.addEventListener('ended', () => {
            activeSourcesRef.current = activeSourcesRef.current.filter(s => s !== source);
        });

        const startAt = Math.max(audioCtx.currentTime, nextPlaybackTimeRef.current);
        source.start(startAt);
        nextPlaybackTimeRef.current = startAt + buffer.duration;
    }, []);

    const teardownMic = useCallback(() => {
        if (micProcessorRef.current) {
            micProcessorRef.current.disconnect();
            micProcessorRef.current.onaudioprocess = null;
            micProcessorRef.current = null;
        }
        if (micSourceRef.current) { micSourceRef.current.disconnect(); micSourceRef.current = null; }
        if (micGainSinkRef.current) { micGainSinkRef.current.disconnect(); micGainSinkRef.current = null; }
        if (micStreamRef.current) { micStreamRef.current.getTracks().forEach(t => t.stop()); micStreamRef.current = null; }
        if (micAudioContextRef.current) { micAudioContextRef.current.close(); micAudioContextRef.current = null; }
    }, []);

    const stop = useCallback(() => {
        if (wsRef.current) {
            try { wsRef.current.send(JSON.stringify({ type: 'stop' })); } catch { /* socket pode ja ter caido */ }
            wsRef.current.close();
            wsRef.current = null;
        }
        teardownMic();
        stopAssistantPlayback();
        userTranscriptRef.current = '';
        assistantTranscriptRef.current = '';
        micStartedRef.current = false;
        setStatus('idle');
        statusRef.current = 'idle';
    }, [teardownMic, stopAssistantPlayback]);

    const start = useCallback(async () => {
        if (statusRef.current === 'connecting' || statusRef.current === 'live') return;
        setStatus('connecting');
        statusRef.current = 'connecting';

        const idToken = await auth.currentUser?.getIdToken().catch(() => null);
        if (!idToken) {
            setStatus('error');
            statusRef.current = 'error';
            options.onError?.('Usuário não autenticado — não é possível iniciar a sessão de voz.');
            return;
        }

        let micStream: MediaStream;
        try {
            micStream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
            });
        } catch (err: any) {
            setStatus('error');
            statusRef.current = 'error';
            options.onError?.(`Não foi possível acessar o microfone: ${err?.message || err}`);
            return;
        }
        micStreamRef.current = micStream;

        const ws = new WebSocket(toWebSocketUrl(resolveBridgeUrl()));
        wsRef.current = ws;

        const startMicCapture = () => {
            const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: MIC_SAMPLE_RATE });
            micAudioContextRef.current = audioContext;
            const source = audioContext.createMediaStreamSource(micStream);
            micSourceRef.current = source;
            const processor = audioContext.createScriptProcessor(PROCESSOR_BUFFER_SIZE, 1, 1);
            micProcessorRef.current = processor;

            processor.onaudioprocess = (event) => {
                if (ws.readyState !== WebSocket.OPEN) return;
                const input = event.inputBuffer.getChannelData(0);

                if (activeSourcesRef.current.length > 0) {
                    let energy = 0;
                    for (let i = 0; i < input.length; i++) energy += input[i] * input[i];
                    if (Math.sqrt(energy / input.length) > BARGE_IN_RMS_THRESHOLD) {
                        stopAssistantPlayback();
                    }
                }

                const int16 = new Int16Array(input.length);
                for (let i = 0; i < input.length; i++) {
                    const clamped = Math.max(-1, Math.min(1, input[i]));
                    int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
                }
                ws.send(JSON.stringify({
                    type: 'audio',
                    payload: int16ToBase64(int16),
                    mime_type: `audio/pcm;rate=${MIC_SAMPLE_RATE}`,
                }));
            };

            // ScriptProcessorNode so dispara onaudioprocess se conectado a um
            // destino; usamos um GainNode mudo para nao ecoar o mic nos alto-falantes.
            const gain = audioContext.createGain();
            gain.gain.value = 0;
            micGainSinkRef.current = gain;
            source.connect(processor);
            processor.connect(gain);
            gain.connect(audioContext.destination);
        };

        ws.addEventListener('open', () => {
            ws.send(JSON.stringify({ type: 'auth', id_token: idToken, task_id: options.taskId || undefined }));
        });

        ws.addEventListener('error', () => {
            setStatus('error');
            statusRef.current = 'error';
            options.onError?.('Falha de conexão com o servidor de voz (verifique se o hermes-voice-bridge está rodando).');
        });

        ws.addEventListener('close', () => {
            const wasLive = statusRef.current === 'live' || statusRef.current === 'connecting';
            teardownMic();
            micStartedRef.current = false;
            stopAssistantPlayback();
            setStatus(current => (current === 'error' ? current : 'idle'));
            if (statusRef.current !== 'error') statusRef.current = 'idle';
            // Encerramento que nao partiu do usuario (limite de duracao,
            // inatividade, queda do provedor): avisa em vez de so silenciar.
            if (wasLive) {
                options.onError?.('Sessão de voz encerrada. Clique no botão de voz para reconectar.');
            }
        });

        ws.addEventListener('message', (event) => {
            let payload: any;
            try { payload = JSON.parse(event.data); } catch { return; }

            switch (payload.type) {
                case 'status':
                    if (!micStartedRef.current) {
                        micStartedRef.current = true;
                        setStatus('live');
                        statusRef.current = 'live';
                        startMicCapture();
                    }
                    options.onStatus?.(payload.message);
                    break;
                case 'error':
                    setStatus('error');
                    statusRef.current = 'error';
                    options.onError?.(payload.message || 'Erro na sessão de voz.');
                    break;
                case 'audio': {
                    const mime = payload.mime_type || 'audio/pcm;rate=24000';
                    const rateMatch = /rate=(\d+)/.exec(mime);
                    playAudioChunk(payload.payload, rateMatch ? parseInt(rateMatch[1], 10) : 24000);
                    break;
                }
                case 'input_transcript':
                    userTranscriptRef.current = appendTranscriptFragment(userTranscriptRef.current, payload.text || '');
                    break;
                case 'output_transcript':
                    assistantTranscriptRef.current = appendTranscriptFragment(assistantTranscriptRef.current, payload.text || '');
                    break;
                case 'turn_complete': {
                    const userText = sanitizeTranscript(userTranscriptRef.current);
                    const assistantText = sanitizeTranscript(assistantTranscriptRef.current);
                    userTranscriptRef.current = '';
                    assistantTranscriptRef.current = '';
                    if (userText) options.onUserTranscript(userText);
                    if (assistantText) options.onAssistantTranscript(assistantText);
                    break;
                }
                default:
                    break;
            }
        });
    }, [options, playAudioChunk, stopAssistantPlayback, teardownMic]);

    return { status, start, stop };
}
