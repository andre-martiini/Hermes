import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions, db } from '@/firebase';
import { collection, addDoc, getDocs, query, orderBy, limit, doc, setDoc, getDoc } from 'firebase/firestore';

export interface TranscriptionEntry {
  id: string;
  speaker: 'Você' | 'Reunião';
  text: string;
  timestamp: Date;
}

export interface RegistroConsentimento {
  terceirosPresentes: boolean;
  avisoConfirmado: boolean;
  confirmadoEm: string;
}

export interface MeetingHistoryEntry {
  id: string;
  titulo: string;
  startedAt: string;
  endedAt: string;
  transcriptCount: number;
  chatCount: number;
  transcripts: Array<{ speaker: 'Você' | 'Reunião'; text: string; timestamp: string }>;
  chats: Array<{ role: 'user' | 'assistant'; content: string; timestamp: string }>;
  firestoreId?: string;
  driveWebViewLink?: string;
  consentimentoAviso?: RegistroConsentimento | null;
  eventoCalendarId?: string | null;
}

export interface RecordingMeta {
  eventoId: string | null;
  eventoTitulo: string | null;
  bancoId: string | null;
}

const HISTORY_MAX_ITEMS = 30;
const HISTORY_STORAGE_KEY = 'hermes_meeting_history_v1';
const SYSTEM_AUDIO_SILENCE_WARNING_MS = 12000;
const SYSTEM_AUDIO_ACTIVITY_THRESHOLD = 0.004;
const DEEPGRAM_STORAGE_KEY = 'DEEPGRAM_API_KEY';
const DEEPGRAM_CONFIG_COLLECTION = 'public_configs';
const DEEPGRAM_CONFIG_DOC = 'integracoes';
const GROUP_WINDOW_MS = 7000;
const SHORT_FRAGMENT_WORDS = 6;
const MAX_GROUPED_WORDS = 64;

type DisplayMediaTrackSettings = MediaTrackSettings & {
  displaySurface?: 'application' | 'browser' | 'monitor' | 'window';
};

/**
 * Traduz o fechamento do WebSocket do Deepgram em algo acionável.
 *
 * Antes, qualquer queda virava "verifique a chave do Deepgram ou a conexão" —
 * a mesma frase para chave revogada, internet caída, crédito no fim e áudio em
 * formato recusado. Em 28/08/2026 isso custou uma investigação inteira: a chave
 * ESTAVA configurada, com formato correto, e o Deepgram a recusava com 401.
 * "Configurada" e "válida" pareciam a mesma coisa, e a mensagem não separava.
 *
 * Os códigos vêm da faixa 4000+ do Deepgram e dos códigos padrão de WebSocket.
 */
const motivoDaQueda = (code: number, reason: string): string => {
  const detalhe = reason?.trim() ? ` (${reason.trim()})` : '';
  switch (code) {
    case 4001:
      return `a chave do Deepgram foi REJEITADA${detalhe}. Ela existe, mas não é aceita — `
        + 'gere outra em console.deepgram.com › API Keys.';
    case 4000:
      return `o Deepgram recusou os parâmetros da conexão${detalhe}.`;
    case 4008:
      return `o Deepgram não recebeu áudio a tempo e encerrou${detalhe} — `
        + 'verifique se a aba compartilhada está com som.';
    case 4009:
      return `o formato do áudio enviado não foi aceito${detalhe}.`;
    case 4010:
    case 4029:
      return `limite ou crédito da conta Deepgram esgotado${detalhe}.`;
    case 1006:
      return 'a conexão caiu sem resposta do servidor — rede, proxy ou firewall '
        + 'bloqueando wss://api.deepgram.com.';
    case 1011:
      return `erro interno do Deepgram${detalhe}; tente de novo em instantes.`;
    default:
      return `a conexão fechou com código ${code}${detalhe}.`;
  }
};

const normalizeText = (value: string): string => value.replace(/\s+/g, ' ').trim();
const countWords = (value: string): number => normalizeText(value).split(' ').filter(Boolean).length;

const mergeTranscriptTexts = (previousText: string, newText: string): string => {
  const previous = normalizeText(previousText);
  const incoming = normalizeText(newText);
  if (!previous) return incoming;
  if (!incoming) return previous;

  const previousLower = previous.toLowerCase();
  const incomingLower = incoming.toLowerCase();

  if (previousLower === incomingLower || previousLower.endsWith(incomingLower)) return previous;
  if (incomingLower.startsWith(previousLower)) return incoming;

  return `${previous} ${incoming}`.replace(/\s+/g, ' ').trim();
};

const comparableWord = (token: string): string =>
  token.toLowerCase().replace(/^[^\wÀ-ÿ]+|[^\wÀ-ÿ]+$/g, '');

const collapseConsecutiveWordRepeats = (value: string, maxRepeat = 3): string => {
  const tokens = normalizeText(value).split(' ').filter(Boolean);
  if (tokens.length <= 1) return normalizeText(value);

  const result: string[] = [];
  let previousKey = '';
  let streak = 0;

  for (const token of tokens) {
    const key = comparableWord(token);
    if (!key) {
      result.push(token);
      continue;
    }

    if (key === previousKey) {
      streak += 1;
      if (streak <= maxRepeat) result.push(token);
      continue;
    }

    previousKey = key;
    streak = 1;
    result.push(token);
  }

  return normalizeText(result.join(' '));
};

/**
 * Motor de gravação da reunião: WebSockets do Deepgram, MediaRecorder,
 * acúmulo de transcrição e persistência (Firestore + localStorage).
 *
 * Instanciado UMA VEZ no nível raiz do app (index.tsx), não dentro da
 * ferramenta "Transcrição de Reunião" — é isso que faz a gravação sobreviver
 * a trocar de aba/ferramenta: o componente que troca é só a "view" (UI), o
 * motor continua rodando porque quem o criou (o app raiz) nunca desmonta.
 */
export function useMeetingRecordingEngine(
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void,
  // Instanciado incondicionalmente no componente raiz (App), inclusive na tela
  // de login — sem essa trava, o efeito de carregar chave/histórico dispararia
  // leituras no Firestore antes de existir um usuário autenticado.
  enabled: boolean = true,
) {
  const [isRecording, setIsRecording] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptionEntry[]>([]);
  const [meetingStartedAt, setMeetingStartedAt] = useState<Date | null>(null);
  const [meetingEndedAt, setMeetingEndedAt] = useState<Date | null>(null);
  const [meetingHistory, setMeetingHistory] = useState<MeetingHistoryEntry[]>([]);
  const [isTitleGenerating, setIsTitleGenerating] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [deepgramKey, setDeepgramKey] = useState<string | null>(null);
  const [chaveRejeitada, setChaveRejeitada] = useState(false);
  const [registroConsentimento, setRegistroConsentimento] = useState<RegistroConsentimento | null>(null);

  const micRecorderRef = useRef<MediaRecorder | null>(null);
  const systemRecorderRef = useRef<MediaRecorder | null>(null);
  const micWsRef = useRef<WebSocket | null>(null);
  const systemWsRef = useRef<WebSocket | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const systemStreamRef = useRef<MediaStream | null>(null);
  const systemAudioContextRef = useRef<AudioContext | null>(null);
  const systemAudioMonitorRef = useRef<number | null>(null);
  const systemAudioMonitorIntervalRef = useRef<number | null>(null);
  const transcriptsRef = useRef<TranscriptionEntry[]>([]);
  const meetingStartedAtRef = useRef<Date | null>(null);
  const meetingHistoryRef = useRef<MeetingHistoryEntry[]>([]);
  const lastPersistedMeetingIdRef = useRef<string | null>(null);
  const firestorePersistedMeetingIdRef = useRef<string | null>(null);
  const systemAudioActivityDetectedRef = useRef(false);
  const isRecordingRef = useRef(false);
  const driveLinkByMeetingIdRef = useRef<Record<string, string>>({});
  const registroConsentimentoRef = useRef<RegistroConsentimento | null>(null);
  // Contexto (evento de agenda / banco de respostas) escolhido na view no momento
  // de iniciar — capturado aqui para o motor não precisar depender de estado da
  // view, que pode estar desmontada quando a gravação termina.
  const recordingMetaRef = useRef<RecordingMeta>({ eventoId: null, eventoTitulo: null, bancoId: null });

  useEffect(() => {
    transcriptsRef.current = transcripts;
  }, [transcripts]);

  useEffect(() => {
    meetingStartedAtRef.current = meetingStartedAt;
  }, [meetingStartedAt]);

  useEffect(() => {
    meetingHistoryRef.current = meetingHistory;
  }, [meetingHistory]);

  useEffect(() => {
    isRecordingRef.current = isRecording;
  }, [isRecording]);

  // Cronômetro da gravação
  useEffect(() => {
    if (!isRecording) return;
    const interval = window.setInterval(() => {
      const started = meetingStartedAtRef.current;
      if (started) setElapsedMs(Date.now() - started.getTime());
    }, 1000);
    return () => window.clearInterval(interval);
  }, [isRecording]);

  // ── Chave Deepgram persistida ──
  useEffect(() => {
    if (!enabled) return;
    const envKey = (import.meta.env.VITE_DEEPGRAM_API_KEY as string | undefined) || '';
    if (envKey.trim()) {
      setDeepgramKey(envKey.trim());
      return;
    }
    const localKey = localStorage.getItem(DEEPGRAM_STORAGE_KEY) || localStorage.getItem('deepgram_api_key');
    if (localKey && localKey.trim()) {
      setDeepgramKey(localKey.trim());
      // Sincroniza para o Firestore para persistir entre navegadores/dispositivos.
      setDoc(doc(db, DEEPGRAM_CONFIG_COLLECTION, DEEPGRAM_CONFIG_DOC), { deepgramApiKey: localKey.trim() }, { merge: true }).catch(() => undefined);
      return;
    }
    getDoc(doc(db, DEEPGRAM_CONFIG_COLLECTION, DEEPGRAM_CONFIG_DOC))
      .then(snapshot => {
        const remoteKey = (snapshot.data()?.deepgramApiKey as string | undefined) || '';
        if (remoteKey.trim()) {
          localStorage.setItem(DEEPGRAM_STORAGE_KEY, remoteKey.trim());
          setDeepgramKey(remoteKey.trim());
        }
      })
      .catch(e => console.warn('Não foi possível carregar a chave Deepgram do Firestore:', e));
  }, [enabled]);

  const saveDeepgramKey = useCallback(async (rawKey: string) => {
    const trimmed = rawKey.trim();
    if (!trimmed) {
      showToast('Informe uma chave válida do Deepgram.', 'error');
      return false;
    }
    localStorage.setItem(DEEPGRAM_STORAGE_KEY, trimmed);
    setDeepgramKey(trimmed);
    setChaveRejeitada(false);
    try {
      await setDoc(doc(db, DEEPGRAM_CONFIG_COLLECTION, DEEPGRAM_CONFIG_DOC), { deepgramApiKey: trimmed }, { merge: true });
      showToast('Chave Deepgram salva. Não será pedida novamente.', 'success');
    } catch (e) {
      console.error('Erro ao salvar chave no Firestore:', e);
      showToast('Chave salva neste navegador, mas houve erro ao sincronizar na nuvem.', 'info');
    }
    return true;
  }, [showToast]);

  // ── Histórico: Firestore com fallback em localStorage ──
  useEffect(() => {
    if (!enabled) return;
    const loadHistory = async () => {
      try {
        const q = query(collection(db, 'reunioes'), orderBy('startedAt', 'desc'), limit(HISTORY_MAX_ITEMS));
        const snapshot = await getDocs(q);
        if (!snapshot.empty) {
          const firestoreMeetings: MeetingHistoryEntry[] = snapshot.docs.map(docSnap => ({
            id: docSnap.data().startedAt as string,
            titulo: (docSnap.data().titulo as string) || 'Reunião sem título',
            startedAt: docSnap.data().startedAt as string,
            endedAt: docSnap.data().endedAt as string,
            transcriptCount: (docSnap.data().transcriptCount as number) || 0,
            chatCount: (docSnap.data().chatCount as number) || 0,
            transcripts: (docSnap.data().transcripts as MeetingHistoryEntry['transcripts']) || [],
            chats: (docSnap.data().chats as MeetingHistoryEntry['chats']) || [],
            firestoreId: docSnap.id,
            driveWebViewLink: (docSnap.data().driveWebViewLink as string) || undefined,
            consentimentoAviso: (docSnap.data().consentimentoAviso as RegistroConsentimento) || null,
            eventoCalendarId: (docSnap.data().eventoCalendarId as string) || null,
          }));
          setMeetingHistory(firestoreMeetings);
          return;
        }
      } catch (e) {
        console.error('Erro ao carregar reuniões do Firestore:', e);
      }
      try {
        const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
        if (!raw) return;
        const parsed = JSON.parse(raw) as MeetingHistoryEntry[];
        if (Array.isArray(parsed)) {
          setMeetingHistory(parsed.filter(item => item?.id && item?.startedAt && item?.endedAt).slice(0, HISTORY_MAX_ITEMS));
        }
      } catch (e) {
        console.error('Erro ao carregar histórico local de reuniões:', e);
      }
    };
    loadHistory();
  }, [enabled]);

  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(meetingHistory.slice(0, HISTORY_MAX_ITEMS)));
    } catch (e) {
      console.error('Erro ao persistir histórico de reuniões:', e);
    }
  }, [meetingHistory]);

  const persistCurrentMeetingToHistory = useCallback((endedAt: Date) => {
    const startedAt = meetingStartedAtRef.current;
    if (!startedAt) return;

    const meetingId = startedAt.toISOString();
    if (lastPersistedMeetingIdRef.current === meetingId) return;

    const transcriptSnapshot = transcriptsRef.current;

    const newEntry: MeetingHistoryEntry = {
      id: meetingId,
      titulo: `Reunião ${new Date(meetingId).toLocaleDateString('pt-BR')} ${new Date(meetingId).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`,
      startedAt: startedAt.toISOString(),
      endedAt: endedAt.toISOString(),
      transcriptCount: transcriptSnapshot.length,
      chatCount: 0,
      transcripts: transcriptSnapshot.map(t => ({
        speaker: t.speaker,
        text: t.text,
        timestamp: t.timestamp.toISOString(),
      })),
      chats: [],
      driveWebViewLink: driveLinkByMeetingIdRef.current[meetingId],
    };

    setMeetingHistory(prev => [newEntry, ...prev.filter(item => item.id !== newEntry.id)].slice(0, HISTORY_MAX_ITEMS));
    lastPersistedMeetingIdRef.current = meetingId;
  }, []);

  const appendTranscriptEntry = useCallback((speaker: 'Você' | 'Reunião', rawText: string, entryTime = new Date()) => {
    const normalizedIncoming = collapseConsecutiveWordRepeats(rawText);
    if (!normalizedIncoming) return;

    setTranscripts(prev => {
      if (prev.length === 0) {
        return [
          {
            id: `${entryTime.getTime()}-${Math.random().toString(36).slice(2)}`,
            speaker,
            text: normalizedIncoming,
            timestamp: entryTime,
          },
        ];
      }

      const next = [...prev];
      const last = next[next.length - 1];
      const gapMs = entryTime.getTime() - last.timestamp.getTime();
      const incomingLower = normalizedIncoming.toLowerCase();
      const lastLower = normalizeText(last.text).toLowerCase();

      if (last.speaker === speaker && incomingLower === lastLower && gapMs <= 15000) {
        return next;
      }

      if (last.speaker === speaker && gapMs <= GROUP_WINDOW_MS) {
        const lastWords = countWords(last.text);
        const incomingWords = countWords(normalizedIncoming);
        const shouldMergeShort = incomingWords <= SHORT_FRAGMENT_WORDS || lastWords <= 12;
        const isSentenceStillOpen = !/[.!?]$/.test(last.text.trim());
        const totalWords = lastWords + incomingWords;

        if ((shouldMergeShort || isSentenceStillOpen) && totalWords <= MAX_GROUPED_WORDS) {
          next[next.length - 1] = {
            ...last,
            text: mergeTranscriptTexts(last.text, normalizedIncoming),
            timestamp: entryTime,
          };
          return next;
        }
      }

      next.push({
        id: `${entryTime.getTime()}-${Math.random().toString(36).slice(2)}`,
        speaker,
        text: normalizedIncoming,
        timestamp: entryTime,
      });
      return next;
    });
  }, []);

  const stopSystemAudioMonitor = useCallback(() => {
    if (systemAudioMonitorRef.current !== null) {
      window.clearTimeout(systemAudioMonitorRef.current);
      systemAudioMonitorRef.current = null;
    }

    if (systemAudioMonitorIntervalRef.current !== null) {
      window.clearInterval(systemAudioMonitorIntervalRef.current);
      systemAudioMonitorIntervalRef.current = null;
    }

    if (systemAudioContextRef.current) {
      systemAudioContextRef.current.close().catch(() => undefined);
      systemAudioContextRef.current = null;
    }
  }, []);

  const startSystemAudioMonitor = useCallback((stream: MediaStream) => {
    stopSystemAudioMonitor();
    systemAudioActivityDetectedRef.current = false;

    try {
      const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioContextClass) return;

      const audioContext = new AudioContextClass();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;

      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      systemAudioContextRef.current = audioContext;

      const inspect = () => {
        analyser.getByteTimeDomainData(samples);
        let sum = 0;
        for (const sample of samples) {
          const normalized = (sample - 128) / 128;
          sum += normalized * normalized;
        }
        const rms = Math.sqrt(sum / samples.length);
        if (rms > SYSTEM_AUDIO_ACTIVITY_THRESHOLD) {
          systemAudioActivityDetectedRef.current = true;
        }
      };

      systemAudioMonitorIntervalRef.current = window.setInterval(() => {
        if (systemAudioActivityDetectedRef.current) {
          if (systemAudioMonitorIntervalRef.current !== null) {
            window.clearInterval(systemAudioMonitorIntervalRef.current);
            systemAudioMonitorIntervalRef.current = null;
          }
          return;
        }
        inspect();
      }, 300);

      systemAudioMonitorRef.current = window.setTimeout(() => {
        if (systemAudioMonitorIntervalRef.current !== null) {
          window.clearInterval(systemAudioMonitorIntervalRef.current);
          systemAudioMonitorIntervalRef.current = null;
        }
        if (!systemAudioActivityDetectedRef.current) {
          showToast('Ainda não detectei áudio do Teams. Confirme se a tela inteira foi compartilhada com "Compartilhar áudio do sistema" ativo.', 'info');
        }
      }, SYSTEM_AUDIO_SILENCE_WARNING_MS);
    } catch (error) {
      console.warn('Não foi possível monitorar o áudio do sistema:', error);
    }
  }, [showToast, stopSystemAudioMonitor]);

  const generateMeetingTitle = useCallback(async (transcriptSnapshot: TranscriptionEntry[]): Promise<string> => {
    if (transcriptSnapshot.length === 0) return 'Reunião sem transcrição';
    const sample = transcriptSnapshot.slice(0, 15).map(t => `${t.speaker}: ${t.text}`).join('\n');
    const prompt = `Com base nesta transcrição de reunião, gere um título curto e descritivo (máximo 8 palavras, sem aspas). Responda APENAS com o título:\n\n${sample}`;
    try {
      const askChatbotFunc = httpsCallable(functions, 'askChatbot');
      const response = await askChatbotFunc({ prompt });
      const data = response.data as { result?: string };
      return data?.result?.trim().slice(0, 80) || 'Reunião sem título';
    } catch {
      return 'Reunião sem título';
    }
  }, []);

  const finalizeAndPersistMeeting = useCallback(async (ended: Date) => {
    const startedAt = meetingStartedAtRef.current;
    if (!startedAt) return;
    const meetingId = startedAt.toISOString();
    if (firestorePersistedMeetingIdRef.current === meetingId) return;
    firestorePersistedMeetingIdRef.current = meetingId;
    const transcriptSnapshot = [...transcriptsRef.current];

    if (transcriptSnapshot.length === 0) return;

    setIsTitleGenerating(true);
    const titulo = await generateMeetingTitle(transcriptSnapshot);

    setMeetingHistory(prev => prev.map(entry =>
      entry.id === meetingId ? { ...entry, titulo } : entry
    ));

    const consent = registroConsentimentoRef.current;
    const { eventoId, eventoTitulo, bancoId } = recordingMetaRef.current;

    try {
      const docRef = await addDoc(collection(db, 'reunioes'), {
        titulo,
        startedAt: startedAt.toISOString(),
        endedAt: ended.toISOString(),
        transcriptCount: transcriptSnapshot.length,
        chatCount: 0,
        transcripts: transcriptSnapshot.map(t => ({
          speaker: t.speaker,
          text: t.text,
          timestamp: t.timestamp.toISOString(),
        })),
        chats: [],
        consentimentoAviso: consent ? {
          terceirosPresentes: consent.terceirosPresentes,
          avisoConfirmado: consent.avisoConfirmado,
          confirmadoEm: consent.confirmadoEm,
        } : null,
        eventoCalendarId: eventoId,
        eventoCalendarTitulo: eventoTitulo,
        bancoRespostasId: bancoId,
        driveWebViewLink: driveLinkByMeetingIdRef.current[meetingId] || null,
        data_criacao: new Date().toISOString(),
      });
      setMeetingHistory(prev => prev.map(entry =>
        entry.id === meetingId ? {
          ...entry,
          titulo,
          firestoreId: docRef.id,
          consentimentoAviso: consent,
          eventoCalendarId: eventoId,
        } : entry
      ));
    } catch (err) {
      console.error('Erro ao salvar reunião no Firestore:', err);
    } finally {
      setIsTitleGenerating(false);
    }
  }, [generateMeetingTitle]);

  const finalizeAndPersistMeetingRef = useRef(finalizeAndPersistMeeting);
  useEffect(() => {
    finalizeAndPersistMeetingRef.current = finalizeAndPersistMeeting;
  }, [finalizeAndPersistMeeting]);

  const stopRecording = useCallback(
    (persistHistory = true) => {
      if (micRecorderRef.current && micRecorderRef.current.state !== 'inactive') micRecorderRef.current.stop();
      if (systemRecorderRef.current && systemRecorderRef.current.state !== 'inactive') systemRecorderRef.current.stop();

      if (micWsRef.current) micWsRef.current.close();
      if (systemWsRef.current) systemWsRef.current.close();

      if (micStreamRef.current) micStreamRef.current.getTracks().forEach(t => t.stop());
      if (systemStreamRef.current) systemStreamRef.current.getTracks().forEach(t => t.stop());
      stopSystemAudioMonitor();

      micRecorderRef.current = null;
      systemRecorderRef.current = null;
      micWsRef.current = null;
      systemWsRef.current = null;
      micStreamRef.current = null;
      systemStreamRef.current = null;

      const ended = new Date();
      setMeetingEndedAt(ended);
      setIsRecording(false);

      if (persistHistory) {
        persistCurrentMeetingToHistory(ended);
        finalizeAndPersistMeetingRef.current?.(ended);
      }
    },
    [persistCurrentMeetingToHistory, stopSystemAudioMonitor]
  );

  const startRecording = useCallback(async (consentimentoInfo?: RegistroConsentimento, meta?: RecordingMeta) => {
    if (!deepgramKey) {
      showToast('Configure a chave do Deepgram antes de gravar.', 'error');
      return;
    }

    const consent = consentimentoInfo ?? registroConsentimento;
    if (consent) {
      registroConsentimentoRef.current = consent;
      setRegistroConsentimento(consent);
    }
    recordingMetaRef.current = meta ?? { eventoId: null, eventoTitulo: null, bancoId: null };

    let micStream: MediaStream | null = null;
    let systemStream: MediaStream | null = null;

    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

      try {
        systemStream = await navigator.mediaDevices.getDisplayMedia({
          audio: {
            autoGainControl: false,
            echoCancellation: false,
            noiseSuppression: false,
            suppressLocalAudioPlayback: false,
          },
          video: {
            displaySurface: 'monitor',
          },
          systemAudio: 'include',
          surfaceSwitching: 'exclude',
        } as DisplayMediaStreamOptions);

        if (systemStream.getAudioTracks().length === 0) {
          systemStream.getTracks().forEach(track => track.stop());
          systemStream = null;
          showToast('Áudio da reunião não capturado (selecione "Tela inteira" e marque "Compartilhar áudio do sistema"). Gravando só o seu microfone por enquanto.', 'info');
        } else {
          const displayTrack = systemStream.getVideoTracks()[0];
          const displaySettings = displayTrack?.getSettings() as DisplayMediaTrackSettings | undefined;
          if (displaySettings?.displaySurface && displaySettings.displaySurface !== 'monitor') {
            showToast('Para reuniões no Teams ou Meet, prefira "Tela inteira"; janelas ou abas individuais normalmente não entregam o áudio do sistema.', 'info');
          }
        }
      } catch (displayErr) {
        console.warn('Áudio da reunião não compartilhado:', displayErr);
        systemStream = null;
        showToast('Áudio da reunião não compartilhado. Gravando só o seu microfone.', 'info');
      }

      const startedNow = new Date();
      setTranscripts([]);
      setMeetingStartedAt(startedNow);
      setMeetingEndedAt(null);
      setElapsedMs(0);
      meetingStartedAtRef.current = startedNow;
      lastPersistedMeetingIdRef.current = null;
      firestorePersistedMeetingIdRef.current = null;

      micStreamRef.current = micStream;
      systemStreamRef.current = systemStream;
      if (systemStream) startSystemAudioMonitor(systemStream);

      const wsUrl = 'wss://api.deepgram.com/v1/listen?model=nova-2&language=pt-BR';
      const protocols = ['token', deepgramKey];
      const micWs = new WebSocket(wsUrl, protocols);
      micWsRef.current = micWs;

      micWs.onopen = () => {
        const recorder = new MediaRecorder(micStream!);
        recorder.ondataavailable = event => {
          if (event.data.size > 0 && micWs.readyState === WebSocket.OPEN) {
            micWs.send(event.data);
          }
        };
        recorder.start(250);
        micRecorderRef.current = recorder;
      };

      micWs.onmessage = message => {
        const received = JSON.parse(message.data);
        const transcript = received?.channel?.alternatives?.[0]?.transcript;
        const hasFinalFlag = typeof received?.is_final === 'boolean' || typeof received?.speech_final === 'boolean';
        const isFinal = Boolean(received?.is_final ?? received?.speech_final);

        if (hasFinalFlag && !isFinal) return;
        if (typeof transcript !== 'string' || !transcript.trim()) return;
        appendTranscriptEntry('Você', transcript, new Date());
      };

      micWs.onerror = event => {
        console.error('Erro na conexão com Deepgram (microfone):', event);
      };

      micWs.onclose = event => {
        if (!event.wasClean) {
          console.error('Conexão com Deepgram (microfone) encerrada inesperadamente:', event.code, event.reason);
          showToast(`Transcrição do microfone caiu: ${motivoDaQueda(event.code, event.reason)}`, 'error');
          if (event.code === 4001) setChaveRejeitada(true);
        }
      };

      if (systemStream) {
        const activeSystemStream = systemStream;
        const systemWs = new WebSocket(wsUrl, protocols);
        systemWsRef.current = systemWs;

        systemWs.onopen = () => {
          const recorder = new MediaRecorder(activeSystemStream);
          recorder.ondataavailable = event => {
            if (event.data.size > 0 && systemWs.readyState === WebSocket.OPEN) {
              systemWs.send(event.data);
            }
          };
          recorder.start(250);
          systemRecorderRef.current = recorder;
        };

        systemWs.onmessage = message => {
          const received = JSON.parse(message.data);
          const transcript = received?.channel?.alternatives?.[0]?.transcript;
          const hasFinalFlag = typeof received?.is_final === 'boolean' || typeof received?.speech_final === 'boolean';
          const isFinal = Boolean(received?.is_final ?? received?.speech_final);

          if (hasFinalFlag && !isFinal) return;
          if (typeof transcript !== 'string' || !transcript.trim()) return;
          systemAudioActivityDetectedRef.current = true;
          appendTranscriptEntry('Reunião', transcript, new Date());
        };

        systemWs.onerror = event => {
          console.error('Erro na conexão com Deepgram (áudio da reunião):', event);
        };

        systemWs.onclose = event => {
          if (!event.wasClean) {
            console.error('Conexão com Deepgram (áudio da reunião) encerrada inesperadamente:', event.code, event.reason);
            showToast(`Transcrição do áudio da reunião caiu: ${motivoDaQueda(event.code, event.reason)}`, 'error');
            if (event.code === 4001) setChaveRejeitada(true);
          }
        };

        activeSystemStream.getVideoTracks().forEach(track => {
          track.onended = () => {
            stopRecording(true);
          };
        });
      }

      setIsRecording(true);
      showToast(
        systemStream ? 'Gravação e transcrição iniciadas.' : 'Gravação do microfone iniciada (sem áudio da reunião).',
        'info'
      );
    } catch (err) {
      console.error('Erro ao acessar mídias:', err);
      if (micStream) micStream.getTracks().forEach(track => track.stop());
      if (systemStream) systemStream.getTracks().forEach(track => track.stop());
      stopSystemAudioMonitor();
      showToast('Permissão negada ou hardware indisponível.', 'error');
    }
  }, [deepgramKey, registroConsentimento, showToast, startSystemAudioMonitor, stopSystemAudioMonitor, appendTranscriptEntry, stopRecording]);

  // Rede de segurança: só dispara se o próprio motor (montado no app raiz)
  // for desmontado — o que não acontece por navegação normal entre
  // ferramentas/abas, só em casos extremos (ex.: HMR em desenvolvimento).
  // Sem isso, uma gravação em andamento nesse cenário seria descartada em
  // vez de salva.
  useEffect(() => {
    return () => {
      stopRecording(true);
    };
  }, [stopRecording]);

  return {
    // estado
    isRecording,
    transcripts,
    setTranscripts,
    meetingStartedAt,
    setMeetingStartedAt,
    meetingEndedAt,
    setMeetingEndedAt,
    meetingHistory,
    setMeetingHistory,
    isTitleGenerating,
    elapsedMs,
    setElapsedMs,
    deepgramKey,
    chaveRejeitada,
    setChaveRejeitada,
    registroConsentimento,
    setRegistroConsentimento,
    // refs (leitura ao vivo sem re-render; escrita pontual pela view em pontos específicos)
    transcriptsRef,
    meetingStartedAtRef,
    meetingHistoryRef,
    isRecordingRef,
    registroConsentimentoRef,
    driveLinkByMeetingIdRef,
    // ações
    startRecording,
    stopRecording,
    saveDeepgramKey,
  };
}

export type MeetingRecordingEngine = ReturnType<typeof useMeetingRecordingEngine>;

/**
 * Instanciado uma vez no componente raiz do app (index.tsx) e fornecido aqui
 * para qualquer lugar que monte <MeetingTranscriptionTool> — inclusive
 * caminhos que não recebem props diretas dele, como o card de ferramenta
 * embutida no chat do Copiloto (HermesCopilotoDrawer). Sem isso, cada ponto
 * de montagem precisaria de sua própria instância do motor, quebrando a
 * garantia de que existe só UMA gravação ativa compartilhada.
 */
export const MeetingRecordingEngineContext = createContext<MeetingRecordingEngine | null>(null);

/**
 * Usa o motor compartilhado do Provider quando disponível; senão, cria uma
 * instância própria (mesmo comportamento de antes da extração) — rede de
 * segurança para qualquer ponto de montagem fora da árvore do app raiz.
 */
export function useSharedMeetingRecordingEngine(showToast: (msg: string, type: 'success' | 'error' | 'info') => void): MeetingRecordingEngine {
  const shared = useContext(MeetingRecordingEngineContext);
  const own = useMeetingRecordingEngine(showToast);
  return shared ?? own;
}
