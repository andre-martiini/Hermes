import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions, db, auth } from '@/firebase';
import { collection, addDoc, getDocs, query, orderBy, limit, doc, setDoc, getDoc, updateDoc, deleteDoc } from 'firebase/firestore';
import { HermesGlobalChat } from './HermesGlobalChat';

export interface TranscriptionEntry {
  id: string;
  speaker: 'Você' | 'Reunião';
  text: string;
  timestamp: Date;
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
}

interface MeetingTranscriptionToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
  isDark?: boolean;
}

const GROUP_WINDOW_MS = 7000;
const SHORT_FRAGMENT_WORDS = 6;
const MAX_GROUPED_WORDS = 64;
const HISTORY_MAX_ITEMS = 30;
const HISTORY_STORAGE_KEY = 'hermes_meeting_history_v1';
const SYSTEM_AUDIO_SILENCE_WARNING_MS = 12000;
const SYSTEM_AUDIO_ACTIVITY_THRESHOLD = 0.004;
const DEEPGRAM_STORAGE_KEY = 'DEEPGRAM_API_KEY';
const DEEPGRAM_CONFIG_COLLECTION = 'public_configs';
const DEEPGRAM_CONFIG_DOC = 'integracoes';
const LIVE_CONTEXT_MAX_CHARS = 9000;

type DisplayMediaTrackSettings = MediaTrackSettings & {
  displaySurface?: 'application' | 'browser' | 'monitor' | 'window';
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

const formatClock = (ms: number): string => {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const mm = String(minutes).padStart(2, '0');
  const ss = String(seconds).padStart(2, '0');
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
};

const formatMeetingDuration = (startedAt: string, endedAt: string): string => {
  const ms = new Date(endedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms) || ms <= 0) return '—';
  const minutes = Math.round(ms / 60000);
  if (minutes < 1) return '<1 min';
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h${String(minutes % 60).padStart(2, '0')}`;
};

const GoogleDriveIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 87.3 78" aria-hidden="true">
    <path fill="#0066da" d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z" />
    <path fill="#00ac47" d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0 -1.2 4.5h27.5z" />
    <path fill="#ea4335" d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.5l5.85 11.5z" />
    <path fill="#00832d" d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z" />
    <path fill="#2684fc" d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z" />
    <path fill="#ffba00" d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z" />
  </svg>
);

const QUICK_PROMPTS: Array<{ label: string; prompt: string }> = [
  {
    label: '📋 Resumo até agora',
    prompt: 'Faça um resumo executivo da reunião até agora: pontos principais discutidos, em tópicos curtos.',
  },
  {
    label: '✅ Decisões e ações',
    prompt: 'Liste as decisões tomadas e as ações/encaminhamentos combinados nesta reunião até agora, com responsáveis e prazos quando citados.',
  },
  {
    label: '💡 O que responder?',
    prompt: 'Com base no que foi dito por último na reunião, sugira uma resposta ou posicionamento objetivo para eu falar agora.',
  },
];

export const MeetingTranscriptionTool: React.FC<MeetingTranscriptionToolProps> = ({ onBack, showToast, isDark = false }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isSavingToDrive, setIsSavingToDrive] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptionEntry[]>([]);
  const [meetingStartedAt, setMeetingStartedAt] = useState<Date | null>(null);
  const [meetingEndedAt, setMeetingEndedAt] = useState<Date | null>(null);
  const [meetingHistory, setMeetingHistory] = useState<MeetingHistoryEntry[]>([]);
  const [isTitleGenerating, setIsTitleGenerating] = useState(false);
  const [showShareGuide, setShowShareGuide] = useState(false);
  const [showHistoryPanel, setShowHistoryPanel] = useState(false);
  const [confirmDeleteEntryId, setConfirmDeleteEntryId] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [elapsedMs, setElapsedMs] = useState(0);
  const [autoFollow, setAutoFollow] = useState(true);
  const [viewingEntryId, setViewingEntryId] = useState<string | null>(null);
  const [driveSaveInfo, setDriveSaveInfo] = useState<{ meetingId: string; webViewLink: string } | null>(null);

  // Chave Deepgram: env → localStorage → Firestore (public_configs/integracoes)
  const [deepgramKey, setDeepgramKey] = useState<string | null>(null);
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [keyDraft, setKeyDraft] = useState('');
  const [showKeyValue, setShowKeyValue] = useState(false);

  // Copiloto embutido
  const [isDesktopSplit, setIsDesktopSplit] = useState(() => typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches);
  const [isCopilotCollapsed, setIsCopilotCollapsed] = useState(false);
  const [isMobileCopilotOpen, setIsMobileCopilotOpen] = useState(false);
  const [copilotPrompt, setCopilotPrompt] = useState<string | null>(null);

  const micRecorderRef = useRef<MediaRecorder | null>(null);
  const systemRecorderRef = useRef<MediaRecorder | null>(null);
  const micWsRef = useRef<WebSocket | null>(null);
  const systemWsRef = useRef<WebSocket | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const systemStreamRef = useRef<MediaStream | null>(null);
  const systemAudioContextRef = useRef<AudioContext | null>(null);
  const systemAudioMonitorRef = useRef<number | null>(null);
  const systemAudioMonitorIntervalRef = useRef<number | null>(null);
  const transcriptsEndRef = useRef<HTMLDivElement>(null);
  const transcriptsContainerRef = useRef<HTMLDivElement>(null);
  const transcriptsRef = useRef<TranscriptionEntry[]>([]);
  const meetingStartedAtRef = useRef<Date | null>(null);
  const meetingHistoryRef = useRef<MeetingHistoryEntry[]>([]);
  const lastPersistedMeetingIdRef = useRef<string | null>(null);
  const systemAudioActivityDetectedRef = useRef(false);
  const isRecordingRef = useRef(false);
  const driveLinkByMeetingIdRef = useRef<Record<string, string>>({});
  const autoFollowRef = useRef(true);

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

  useEffect(() => {
    autoFollowRef.current = autoFollow;
  }, [autoFollow]);

  // Split desktop x overlay mobile do copiloto
  useEffect(() => {
    const media = window.matchMedia('(min-width: 1024px)');
    const handler = (event: MediaQueryListEvent) => setIsDesktopSplit(event.matches);
    media.addEventListener('change', handler);
    return () => media.removeEventListener('change', handler);
  }, []);

  // Cronômetro da gravação
  useEffect(() => {
    if (!isRecording) return;
    const interval = window.setInterval(() => {
      const started = meetingStartedAtRef.current;
      if (started) setElapsedMs(Date.now() - started.getTime());
    }, 1000);
    return () => window.clearInterval(interval);
  }, [isRecording]);

  // Auto-scroll inteligente: segue ao vivo, mas respeita quando o usuário sobe a rolagem
  useEffect(() => {
    if (autoFollowRef.current) {
      transcriptsEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [transcripts]);

  const handleTranscriptsScroll = () => {
    const container = transcriptsContainerRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    setAutoFollow(distanceFromBottom < 80);
  };

  const jumpToLive = () => {
    setAutoFollow(true);
    transcriptsEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  };

  // ── Chave Deepgram persistida ──
  useEffect(() => {
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
  }, []);

  const saveDeepgramKey = async () => {
    const trimmed = keyDraft.trim();
    if (!trimmed) {
      showToast('Informe uma chave válida do Deepgram.', 'error');
      return;
    }
    localStorage.setItem(DEEPGRAM_STORAGE_KEY, trimmed);
    setDeepgramKey(trimmed);
    setShowKeyModal(false);
    setKeyDraft('');
    try {
      await setDoc(doc(db, DEEPGRAM_CONFIG_COLLECTION, DEEPGRAM_CONFIG_DOC), { deepgramApiKey: trimmed }, { merge: true });
      showToast('Chave Deepgram salva. Não será pedida novamente.', 'success');
    } catch (e) {
      console.error('Erro ao salvar chave no Firestore:', e);
      showToast('Chave salva neste navegador, mas houve erro ao sincronizar na nuvem.', 'info');
    }
  };

  // ── Histórico: Firestore com fallback em localStorage ──
  useEffect(() => {
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
  }, []);

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

  const startRecording = async () => {
    if (!deepgramKey) {
      setShowKeyModal(true);
      return;
    }

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
      setSearchTerm('');
      setAutoFollow(true);
      setViewingEntryId(null);
      setDriveSaveInfo(null);
      meetingStartedAtRef.current = startedNow;
      lastPersistedMeetingIdRef.current = null;

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
          showToast('A transcrição do seu microfone caiu (verifique a chave do Deepgram ou a conexão).', 'error');
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
            showToast('A transcrição do áudio da reunião caiu (verifique a chave do Deepgram ou a conexão).', 'error');
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
  };

  useEffect(() => {
    return () => {
      stopRecording(false);
    };
  }, [stopRecording]);

  const buildSummaryContent = useCallback(
    (
      started: Date,
      ended: Date,
      entries: Array<{ speaker: string; text: string; timestamp: Date }>,
      chats: Array<{ role: 'user' | 'assistant'; content: string; timestamp: Date }> = []
    ) => {
      const transcriptionLines =
        entries.length > 0
          ? entries.map(t => `[${t.timestamp.toLocaleTimeString('pt-BR')}] ${t.speaker}: ${t.text}`)
          : ['(Sem falas transcritas)'];

      const chatSection = chats.length > 0
        ? ['', '=== CHAT ASSISTENTE ===', ...chats.map(m => `[${m.timestamp.toLocaleTimeString('pt-BR')}] ${m.role === 'user' ? 'Você' : 'Assistente'}: ${m.content}`)]
        : [];

      return [
        'TRANSCRIÇÃO DE REUNIÃO',
        '',
        `Início: ${started.toLocaleString('pt-BR')}`,
        `Fim: ${ended.toLocaleString('pt-BR')}`,
        '',
        '=== TRANSCRIÇÃO ===',
        ...transcriptionLines,
        ...chatSection,
        '',
      ].join('\n');
    },
    []
  );

  const buildCurrentMeetingContent = useCallback(
    (endedAtOverride?: Date) => {
      const started = meetingStartedAt ?? transcripts[0]?.timestamp ?? new Date();
      const ended = endedAtOverride ?? meetingEndedAt ?? transcripts[transcripts.length - 1]?.timestamp ?? new Date();
      return buildSummaryContent(started, ended, transcripts);
    },
    [meetingStartedAt, meetingEndedAt, transcripts, buildSummaryContent]
  );

  const buildMeetingFileName = useCallback((startedAt: Date) => {
    const year = startedAt.getFullYear();
    const month = String(startedAt.getMonth() + 1).padStart(2, '0');
    const day = String(startedAt.getDate()).padStart(2, '0');
    const hour = String(startedAt.getHours()).padStart(2, '0');
    const minute = String(startedAt.getMinutes()).padStart(2, '0');
    return `Reuniao_${year}-${month}-${day}_${hour}-${minute}.txt`;
  }, []);

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

  const finalizeAndPersistMeetingRef = useRef<((ended: Date) => void) | null>(null);

  const finalizeAndPersistMeeting = useCallback(async (ended: Date) => {
    const startedAt = meetingStartedAtRef.current;
    if (!startedAt) return;
    const meetingId = startedAt.toISOString();
    const transcriptSnapshot = [...transcriptsRef.current];

    setIsTitleGenerating(true);
    const titulo = await generateMeetingTitle(transcriptSnapshot);

    setMeetingHistory(prev => prev.map(entry =>
      entry.id === meetingId ? { ...entry, titulo } : entry
    ));

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
        driveWebViewLink: driveLinkByMeetingIdRef.current[meetingId] || null,
        data_criacao: new Date().toISOString(),
      });
      setMeetingHistory(prev => prev.map(entry =>
        entry.id === meetingId ? { ...entry, titulo, firestoreId: docRef.id } : entry
      ));
    } catch (err) {
      console.error('Erro ao salvar reunião no Firestore:', err);
    } finally {
      setIsTitleGenerating(false);
    }
  }, [generateMeetingTitle]);

  useEffect(() => {
    finalizeAndPersistMeetingRef.current = finalizeAndPersistMeeting;
  }, [finalizeAndPersistMeeting]);

  const handleCopyMeetingContent = async () => {
    if (transcripts.length === 0) {
      showToast('Não há conteúdo para copiar.', 'info');
      return;
    }

    try {
      await navigator.clipboard.writeText(buildCurrentMeetingContent());
      showToast('Conteúdo da reunião copiado.', 'success');
    } catch (error) {
      console.error(error);
      showToast('Falha ao copiar conteúdo da reunião.', 'error');
    }
  };

  const handleDownloadTxt = () => {
    if (transcripts.length === 0) {
      showToast('Não há conteúdo para baixar.', 'info');
      return;
    }
    const started = meetingStartedAt ?? transcripts[0]?.timestamp ?? new Date();
    const blob = new Blob([buildCurrentMeetingContent()], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = buildMeetingFileName(started);
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const currentMeetingId = (meetingStartedAt ?? transcripts[0]?.timestamp)?.toISOString() ?? null;
  const isSavedToDrive = !!driveSaveInfo && driveSaveInfo.meetingId === currentMeetingId;

  const handleFinalizeAndSaveToDrive = async () => {
    if (transcripts.length === 0) {
      showToast('Sem conteúdo para salvar no Drive.', 'info');
      return;
    }
    if (isSavedToDrive) return;

    setIsSavingToDrive(true);
    try {
      if (isRecording) {
        stopRecording(true);
        await new Promise(resolve => setTimeout(resolve, 700));
      }

      const endedAt = new Date();
      setMeetingEndedAt(endedAt);

      const startedAt = meetingStartedAt ?? transcripts[0]?.timestamp ?? endedAt;
      const meetingId = startedAt.toISOString();
      const content = buildCurrentMeetingContent(endedAt);
      const fileName = buildMeetingFileName(startedAt);

      const saveMeetingFunc = httpsCallable(functions, 'salvarTranscricaoReuniao');
      const result = await saveMeetingFunc({
        startedAt: startedAt.toISOString(),
        endedAt: endedAt.toISOString(),
        fileName,
        content,
      });

      const data = result.data as { success?: boolean; webViewLink?: string; fileName?: string };
      if (data?.success) {
        const link = data.webViewLink || '';
        if (link) {
          driveLinkByMeetingIdRef.current[meetingId] = link;
          setDriveSaveInfo({ meetingId, webViewLink: link });
          setMeetingHistory(prev => prev.map(entry =>
            entry.id === meetingId ? { ...entry, driveWebViewLink: link } : entry
          ));
          const historyEntry = meetingHistoryRef.current.find(entry => entry.id === meetingId);
          if (historyEntry?.firestoreId) {
            updateDoc(doc(db, 'reunioes', historyEntry.firestoreId), { driveWebViewLink: link }).catch(() => undefined);
          }
        }
        showToast('Transcrição salva no Google Drive e adicionada ao Conhecimento.', 'success');
      } else {
        showToast('Transcrição enviada, mas sem confirmação completa do backend.', 'info');
      }
    } catch (error) {
      console.error('Erro ao salvar reunião no Drive:', error);
      showToast('Erro ao salvar reunião no Google Drive.', 'error');
    } finally {
      setIsSavingToDrive(false);
    }
  };

  const handleLoadHistoryEntry = (entry: MeetingHistoryEntry) => {
    if (isRecording) {
      showToast('Pare a gravação atual antes de carregar uma reunião do histórico.', 'info');
      return;
    }
    setTranscripts(
      entry.transcripts.map(t => ({
        id: `${t.timestamp}-${Math.random().toString(36).slice(2)}`,
        speaker: t.speaker,
        text: t.text,
        timestamp: new Date(t.timestamp),
      }))
    );
    setMeetingStartedAt(new Date(entry.startedAt));
    setMeetingEndedAt(new Date(entry.endedAt));
    setViewingEntryId(entry.id);
    setSearchTerm('');
    setDriveSaveInfo(entry.driveWebViewLink ? { meetingId: entry.id, webViewLink: entry.driveWebViewLink } : null);
    setShowHistoryPanel(false);
    showToast('Reunião carregada do histórico.', 'info');
  };

  const handleCopyHistoryEntry = async (entry: MeetingHistoryEntry) => {
    try {
      const historyTranscripts = entry.transcripts.map(t => ({
        speaker: t.speaker,
        text: t.text,
        timestamp: new Date(t.timestamp),
      }));
      const historyChats = entry.chats.map(c => ({
        role: c.role,
        content: c.content,
        timestamp: new Date(c.timestamp),
      }));

      const text = buildSummaryContent(new Date(entry.startedAt), new Date(entry.endedAt), historyTranscripts, historyChats);
      await navigator.clipboard.writeText(text);
      showToast('Reunião do histórico copiada.', 'success');
    } catch (e) {
      console.error(e);
      showToast('Erro ao copiar reunião do histórico.', 'error');
    }
  };

  const handleDeleteHistoryEntry = async (entry: MeetingHistoryEntry) => {
    if (confirmDeleteEntryId !== entry.id) {
      setConfirmDeleteEntryId(entry.id);
      return;
    }
    setConfirmDeleteEntryId(null);
    setMeetingHistory(prev => prev.filter(item => item.id !== entry.id));
    if (viewingEntryId === entry.id) {
      setViewingEntryId(null);
      setTranscripts([]);
      setMeetingStartedAt(null);
      setMeetingEndedAt(null);
      setDriveSaveInfo(null);
    }
    if (entry.firestoreId) {
      try {
        await deleteDoc(doc(db, 'reunioes', entry.firestoreId));
      } catch (e) {
        console.error('Erro ao excluir reunião do Firestore:', e);
        showToast('Reunião removida da lista, mas houve erro ao excluir na nuvem.', 'info');
        return;
      }
    }
    showToast('Reunião excluída do histórico.', 'success');
  };

  const clearLoadedEntry = () => {
    setViewingEntryId(null);
    setTranscripts([]);
    setMeetingStartedAt(null);
    setMeetingEndedAt(null);
    setDriveSaveInfo(null);
    setSearchTerm('');
  };

  // ── Contexto ao vivo para o Copiloto Hermes ──
  const liveContextProvider = useCallback((): string | null => {
    const entries = transcriptsRef.current;
    if (entries.length === 0) return null;
    const started = meetingStartedAtRef.current;
    const header = `Reunião ${isRecordingRef.current ? 'EM ANDAMENTO' : 'encerrada/carregada'}${started ? `, iniciada em ${started.toLocaleString('pt-BR')}` : ''}. Transcrição em tempo real (Você = usuário; Reunião = demais participantes):`;
    const lines = entries.map(t => `[${t.timestamp.toLocaleTimeString('pt-BR')}] ${t.speaker}: ${t.text}`);
    let body = lines.join('\n');
    if (body.length > LIVE_CONTEXT_MAX_CHARS) {
      body = `(...transcrição anterior omitida por tamanho...)\n${body.slice(body.length - LIVE_CONTEXT_MAX_CHARS)}`;
    }
    return `${header}\n${body}`;
  }, []);

  const sendQuickPrompt = (prompt: string) => {
    if (transcriptsRef.current.length === 0) {
      showToast('Ainda não há transcrição para analisar.', 'info');
      return;
    }
    if (isDesktopSplit) {
      setIsCopilotCollapsed(false);
    } else {
      setIsMobileCopilotOpen(true);
    }
    setCopilotPrompt(prompt);
  };

  // ── Filtro de busca ──
  const normalizedSearch = searchTerm.trim().toLowerCase();
  const visibleTranscripts = useMemo(
    () => (normalizedSearch
      ? transcripts.filter(t => t.text.toLowerCase().includes(normalizedSearch))
      : transcripts),
    [transcripts, normalizedSearch]
  );

  const highlightMatches = (text: string) => {
    if (!normalizedSearch) return text;
    const parts = text.split(new RegExp(`(${normalizedSearch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig'));
    return parts.map((part, index) =>
      part.toLowerCase() === normalizedSearch
        ? <mark key={index} className="bg-amber-300/70 text-inherit rounded-sm px-0.5">{part}</mark>
        : part
    );
  };

  const hasContent = transcripts.length > 0;
  const viewingEntry = viewingEntryId ? meetingHistory.find(entry => entry.id === viewingEntryId) : null;
  const userId = auth.currentUser?.uid || '';

  const copilotHeaderSubtitle = isRecording ? 'Acompanhando a reunião ao vivo' : 'Baseado na transcrição da reunião';
  const copilotEmptyDescription = 'Respondo com base no que já foi transcrito. Também busco ações, conhecimento e histórico do Hermes quando for útil — e você pode colar prints para dar mais contexto.';

  // ── Tokens de estilo ──
  const panelClass = isDark ? 'bg-slate-900 border-white/10' : 'bg-white border-slate-200';
  const softPanelClass = isDark ? 'bg-slate-950/60 border-white/10' : 'bg-slate-50 border-slate-200';
  const titleClass = isDark ? 'text-slate-100' : 'text-slate-900';
  const mutedClass = isDark ? 'text-slate-400' : 'text-slate-500';
  const subtleClass = isDark ? 'text-slate-500' : 'text-slate-400';
  const ghostButtonClass = isDark
    ? 'border-white/10 text-slate-300 hover:bg-white/5 hover:text-white'
    : 'border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-slate-900';
  const inputClass = isDark
    ? 'bg-slate-950 border-white/10 text-slate-100 placeholder:text-slate-600'
    : 'bg-white border-slate-200 text-slate-900 placeholder:text-slate-400';

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 relative flex h-[calc(100vh-8.5rem)] min-h-[560px] flex-col">
      {/* ── Cabeçalho ── */}
      <div className="mb-4 flex flex-shrink-0 items-center gap-4">
        <button
          onClick={onBack}
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition-all ${ghostButtonClass} ${isDark ? 'bg-slate-900' : 'bg-white'}`}
          aria-label="Voltar"
        >
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="min-w-0 flex-1">
          <h2 className={`truncate text-2xl font-bold tracking-tight ${titleClass}`}>Reuniões em Tempo Real</h2>
          <p className={`truncate text-sm font-medium ${mutedClass}`}>Transcrição ao vivo com o Copiloto Hermes ao lado.</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={() => { setKeyDraft(''); setShowKeyValue(false); setShowKeyModal(true); }}
            className={`flex h-10 items-center gap-2 rounded-xl border px-3 text-[10px] font-bold uppercase tracking-wider transition-all ${ghostButtonClass}`}
            title={deepgramKey ? 'Chave Deepgram configurada — clique para alterar' : 'Configurar chave Deepgram'}
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            <span className="hidden sm:inline">Chave API</span>
            <span className={`h-2 w-2 rounded-full ${deepgramKey ? 'bg-emerald-500' : 'bg-rose-500'}`} />
          </button>
          <button
            onClick={() => setShowHistoryPanel(true)}
            className={`flex h-10 items-center gap-2 rounded-xl border px-3 text-[10px] font-bold uppercase tracking-wider transition-all ${ghostButtonClass}`}
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="hidden sm:inline">Histórico</span>
            {meetingHistory.length > 0 && (
              <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-black ${isDark ? 'bg-white/10 text-slate-200' : 'bg-slate-100 text-slate-600'}`}>{meetingHistory.length}</span>
            )}
          </button>
        </div>
      </div>

      {/* ── Corpo: transcrição + copiloto ── */}
      <div className="flex min-h-0 flex-1 gap-4">
        {/* Coluna da transcrição */}
        <section className={`flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border shadow-sm ${panelClass}`}>
          {/* Barra de controles */}
          <div className={`flex flex-shrink-0 flex-wrap items-center gap-2 border-b px-4 py-3 ${isDark ? 'border-white/10 bg-slate-950/40' : 'border-slate-200 bg-slate-50'}`}>
            <button
              onClick={() => (isRecording ? stopRecording(true) : (deepgramKey ? setShowShareGuide(true) : setShowKeyModal(true)))}
              disabled={isSavingToDrive}
              className={`flex h-10 items-center gap-2 rounded-xl px-4 text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-50 ${
                isRecording
                  ? 'bg-rose-600 text-white hover:bg-rose-500'
                  : isDark ? 'bg-white text-slate-950 hover:bg-slate-200' : 'bg-slate-900 text-white hover:bg-indigo-600'
              }`}
            >
              {isRecording ? (
                <>
                  <span className="h-2.5 w-2.5 rounded-sm bg-white" />
                  Parar
                </>
              ) : (
                <>
                  <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
                  Iniciar Gravação
                </>
              )}
            </button>

            {isRecording && (
              <span className={`flex items-center gap-2 rounded-xl border px-3 py-2 font-mono text-xs font-bold ${isDark ? 'border-rose-500/30 bg-rose-500/10 text-rose-300' : 'border-rose-200 bg-rose-50 text-rose-600'}`}>
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-rose-500" />
                </span>
                {formatClock(elapsedMs)}
              </span>
            )}

            {hasContent && (
              <span className={`hidden items-center gap-1 text-[10px] font-bold uppercase tracking-wider md:flex ${subtleClass}`}>
                {transcripts.length} falas
              </span>
            )}

            <div className="ml-auto flex flex-wrap items-center gap-2">
              <div className={`flex h-10 items-center rounded-xl border px-3 ${inputClass}`}>
                <svg className={`h-3.5 w-3.5 shrink-0 ${subtleClass}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  placeholder="Buscar na transcrição"
                  className="w-28 bg-transparent px-2 text-xs font-medium outline-none sm:w-40"
                />
                {searchTerm && (
                  <button onClick={() => setSearchTerm('')} className={`text-[10px] font-bold ${subtleClass} hover:text-rose-500`}>✕</button>
                )}
              </div>

              <button
                onClick={handleCopyMeetingContent}
                disabled={!hasContent}
                className={`flex h-10 items-center gap-1.5 rounded-xl border px-3 text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${ghostButtonClass}`}
                title="Copiar transcrição"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                <span className="hidden xl:inline">Copiar</span>
              </button>

              <button
                onClick={handleDownloadTxt}
                disabled={!hasContent}
                className={`flex h-10 items-center gap-1.5 rounded-xl border px-3 text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${ghostButtonClass}`}
                title="Baixar .txt"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <span className="hidden xl:inline">Baixar</span>
              </button>

              {isSavedToDrive && driveSaveInfo ? (
                <a
                  href={driveSaveInfo.webViewLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`flex h-10 items-center gap-2 rounded-xl border px-3 text-[10px] font-bold uppercase tracking-wider transition-all ${isDark ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20' : 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}
                  title="Abrir transcrição no Google Drive"
                >
                  <GoogleDriveIcon className="h-4 w-4" />
                  Salvo no Drive
                  <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              ) : (
                <button
                  onClick={handleFinalizeAndSaveToDrive}
                  disabled={isSavingToDrive || !hasContent}
                  className={`flex h-10 items-center gap-2 rounded-xl px-3 text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${isDark ? 'bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 border border-emerald-500/30' : 'bg-emerald-600 text-white hover:bg-emerald-500'}`}
                >
                  {isSavingToDrive ? (
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                  ) : (
                    <GoogleDriveIcon className="h-4 w-4" />
                  )}
                  {isSavingToDrive ? 'Salvando...' : 'Finalizar e Salvar'}
                </button>
              )}
            </div>
          </div>

          {/* Banner de reunião carregada do histórico */}
          {viewingEntry && !isRecording && (
            <div className={`flex flex-shrink-0 items-center gap-3 border-b px-4 py-2 text-xs font-medium ${isDark ? 'border-white/10 bg-indigo-500/10 text-indigo-300' : 'border-slate-200 bg-indigo-50 text-indigo-700'}`}>
              <svg className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="min-w-0 flex-1 truncate">
                Visualizando: <strong>{viewingEntry.titulo}</strong> · {new Date(viewingEntry.startedAt).toLocaleDateString('pt-BR')} · {formatMeetingDuration(viewingEntry.startedAt, viewingEntry.endedAt)}
              </span>
              <button onClick={clearLoadedEntry} className="shrink-0 text-[10px] font-bold uppercase tracking-wider underline-offset-2 hover:underline">
                Fechar
              </button>
            </div>
          )}

          {/* Área da transcrição */}
          <div className="relative min-h-0 flex-1">
            <div
              ref={transcriptsContainerRef}
              onScroll={handleTranscriptsScroll}
              className="custom-scrollbar h-full space-y-4 overflow-y-auto p-5"
            >
              {transcripts.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center text-center">
                  <div className={`mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border ${softPanelClass}`}>
                    <svg className={`h-8 w-8 ${subtleClass}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.5"
                        d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
                      />
                    </svg>
                  </div>
                  <p className={`text-sm font-bold ${mutedClass}`}>Inicie a gravação para ver a transcrição ao vivo.</p>
                  <p className={`mt-1 max-w-sm text-xs font-medium ${subtleClass}`}>
                    O áudio do seu microfone e o áudio do sistema (Teams, Meet…) são transcritos em paralelo.
                  </p>
                </div>
              ) : visibleTranscripts.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center text-center">
                  <p className={`text-sm font-bold ${mutedClass}`}>Nenhuma fala encontrada para "{searchTerm}".</p>
                </div>
              ) : (
                visibleTranscripts.map(t => (
                  <div key={t.id} className={`flex flex-col ${t.speaker === 'Você' ? 'items-end' : 'items-start'}`}>
                    <span className={`mx-1 mb-1 text-[10px] font-bold uppercase tracking-wider ${subtleClass}`}>
                      {t.speaker} · {t.timestamp.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                        t.speaker === 'Você'
                          ? 'rounded-tr-md bg-indigo-600 text-white'
                          : isDark
                            ? 'rounded-tl-md border border-white/10 bg-slate-800 text-slate-100'
                            : 'rounded-tl-md bg-slate-100 text-slate-800'
                      }`}
                    >
                      <p className="text-sm font-medium leading-relaxed">{highlightMatches(t.text)}</p>
                    </div>
                  </div>
                ))
              )}
              <div ref={transcriptsEndRef} />
            </div>

            {/* Pílula "voltar ao vivo" */}
            {!autoFollow && !normalizedSearch && transcripts.length > 0 && (
              <button
                onClick={jumpToLive}
                className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full bg-slate-900/90 px-4 py-2 text-[10px] font-bold uppercase tracking-wider text-white shadow-lg backdrop-blur transition-all hover:bg-indigo-600"
              >
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
                Voltar ao vivo
              </button>
            )}
          </div>
        </section>

        {/* Coluna do Copiloto (desktop). O HermesGlobalChat fica sempre montado — recolher/expandir
            só alterna o prop isOpen (que internamente renderiza null), preservando a conversa única
            da reunião em vez de recriá-la a cada toggle. */}
        {isDesktopSplit && (
          <aside className={`relative z-20 flex shrink-0 flex-col gap-2 transition-all duration-300 ${isCopilotCollapsed ? 'w-12' : 'w-[400px] xl:w-[440px]'}`}>
            {isCopilotCollapsed && (
              <button
                onClick={() => setIsCopilotCollapsed(false)}
                className={`flex h-full w-12 flex-col items-center justify-center gap-3 rounded-2xl border transition-all ${ghostButtonClass} ${panelClass}`}
                title="Abrir Copiloto Hermes"
              >
                <img src="/logo.png" alt="Hermes" className="h-6 w-6 object-contain" />
                <span className={`text-[9px] font-black uppercase tracking-widest ${mutedClass}`} style={{ writingMode: 'vertical-rl' }}>
                  Copiloto
                </span>
              </button>
            )}
            <div className={isCopilotCollapsed ? 'hidden' : `flex flex-shrink-0 flex-wrap items-center gap-1.5 rounded-2xl border px-3 py-2 ${panelClass}`}>
              <span className={`mr-1 text-[9px] font-black uppercase tracking-widest ${subtleClass}`}>Atalhos</span>
              {QUICK_PROMPTS.map(item => (
                <button
                  key={item.label}
                  onClick={() => sendQuickPrompt(item.prompt)}
                  className={`rounded-full border px-2.5 py-1 text-[10px] font-bold transition-all ${isDark ? 'border-white/10 text-slate-300 hover:bg-white/10' : 'border-slate-200 text-slate-600 hover:bg-slate-100'}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className={`relative min-h-0 flex-1 ${isCopilotCollapsed ? 'hidden' : ''}`}>
              <HermesGlobalChat
                isOpen={!isCopilotCollapsed}
                onClose={() => setIsCopilotCollapsed(true)}
                layout="inline"
                isDark={isDark}
                userId={userId}
                liveContextProvider={liveContextProvider}
                initialPrompt={copilotPrompt}
                onInitialPromptConsumed={() => setCopilotPrompt(null)}
                historyEnabled={false}
                showToolsMenu={false}
                showMinimizeButton={false}
                resetSessionOnOpen={false}
                headerTitle="Copiloto da Reunião"
                headerSubtitle={copilotHeaderSubtitle}
                emptyStateTitle="Pergunte sobre a reunião"
                emptyStateDescription={copilotEmptyDescription}
                composerPlaceholder="Pergunte sobre a reunião..."
              />
            </div>
          </aside>
        )}
      </div>

      {/* Copiloto em overlay (mobile/tablet) */}
      {!isDesktopSplit && (
        <>
          {!isMobileCopilotOpen && (
            <button
              onClick={() => setIsMobileCopilotOpen(true)}
              className="fixed bottom-6 right-6 z-[600] flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 transition-all hover:-translate-y-0.5 hover:bg-indigo-500 active:scale-95"
              aria-label="Abrir Copiloto da reunião"
            >
              <img src="/logo.png" alt="" aria-hidden="true" className="h-8 w-8 object-contain" style={{ filter: 'brightness(0) invert(1)' }} />
            </button>
          )}
          <HermesGlobalChat
            isOpen={isMobileCopilotOpen}
            onClose={() => setIsMobileCopilotOpen(false)}
            layout="overlay"
            isDark={isDark}
            userId={userId}
            liveContextProvider={liveContextProvider}
            initialPrompt={copilotPrompt}
            onInitialPromptConsumed={() => setCopilotPrompt(null)}
            historyEnabled={false}
            showToolsMenu={false}
            showMinimizeButton={false}
            resetSessionOnOpen={false}
            headerTitle="Copiloto da Reunião"
            headerSubtitle={copilotHeaderSubtitle}
            emptyStateTitle="Pergunte sobre a reunião"
            emptyStateDescription={copilotEmptyDescription}
            composerPlaceholder="Pergunte sobre a reunião..."
          />
        </>
      )}

      {/* ── Painel lateral: Histórico ── */}
      {showHistoryPanel && (
        <div className="fixed inset-0 z-[650] flex justify-end">
          <div className="absolute inset-0 bg-slate-950/50 backdrop-blur-sm" onClick={() => setShowHistoryPanel(false)} aria-hidden="true" />
          <div className={`relative flex h-full w-full max-w-md flex-col border-l shadow-2xl animate-in slide-in-from-right duration-300 ${panelClass}`}>
            <div className={`flex h-16 flex-shrink-0 items-center justify-between border-b px-5 ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
              <div>
                <h3 className={`text-sm font-bold uppercase tracking-wider ${titleClass}`}>Histórico de Reuniões</h3>
                <p className={`text-[10px] font-semibold uppercase tracking-wider ${subtleClass}`}>{meetingHistory.length} {meetingHistory.length === 1 ? 'reunião' : 'reuniões'}</p>
              </div>
              <button
                onClick={() => setShowHistoryPanel(false)}
                className={`flex h-9 w-9 items-center justify-center rounded-xl border transition-all ${ghostButtonClass}`}
                aria-label="Fechar histórico"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {meetingHistory.length === 0 ? (
                <div className={`rounded-2xl border p-6 text-center text-xs font-bold ${softPanelClass} ${mutedClass}`}>
                  Nenhuma reunião registrada ainda.
                </div>
              ) : (
                meetingHistory.map(entry => {
                  const started = new Date(entry.startedAt);
                  const isViewing = viewingEntryId === entry.id;
                  return (
                    <div
                      key={entry.id}
                      className={`rounded-2xl border p-4 transition-all ${isViewing ? (isDark ? 'border-indigo-400/40 bg-indigo-500/10' : 'border-indigo-300 bg-indigo-50') : softPanelClass}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className={`min-w-0 flex-1 text-sm font-bold leading-snug ${titleClass}`}>
                          {entry.titulo || `${started.toLocaleDateString('pt-BR')} ${started.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`}
                          {isTitleGenerating && entry.id === meetingStartedAt?.toISOString() && (
                            <span className="ml-2 inline-block h-3 w-3 animate-spin rounded-full border border-slate-300 border-t-indigo-500 align-middle" />
                          )}
                        </p>
                        {entry.driveWebViewLink && (
                          <a
                            href={entry.driveWebViewLink}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Abrir no Google Drive"
                            className="shrink-0 rounded-lg p-1.5 transition-all hover:scale-110"
                          >
                            <GoogleDriveIcon className="h-4 w-4" />
                          </a>
                        )}
                      </div>
                      <p className={`mt-1 text-[10px] font-bold uppercase tracking-wider ${subtleClass}`}>
                        {started.toLocaleDateString('pt-BR')} · {started.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })} · {formatMeetingDuration(entry.startedAt, entry.endedAt)} · {entry.transcriptCount} falas
                      </p>
                      <div className="mt-3 flex items-center gap-2">
                        <button
                          onClick={() => handleLoadHistoryEntry(entry)}
                          className={`flex-1 rounded-xl px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all ${isDark ? 'bg-white/10 text-slate-100 hover:bg-white/20' : 'bg-slate-900 text-white hover:bg-indigo-600'}`}
                        >
                          Carregar
                        </button>
                        <button
                          onClick={() => handleCopyHistoryEntry(entry)}
                          className={`rounded-xl border px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all ${ghostButtonClass}`}
                        >
                          Copiar
                        </button>
                        <button
                          onClick={() => handleDeleteHistoryEntry(entry)}
                          className={`rounded-xl border px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all ${
                            confirmDeleteEntryId === entry.id
                              ? 'border-rose-500 bg-rose-600 text-white'
                              : `${ghostButtonClass} hover:text-rose-500`
                          }`}
                          title={confirmDeleteEntryId === entry.id ? 'Clique para confirmar exclusão' : 'Excluir reunião'}
                        >
                          {confirmDeleteEntryId === entry.id ? 'Confirmar?' : (
                            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M4 7h16" />
                            </svg>
                          )}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: chave Deepgram ── */}
      {showKeyModal && (
        <div className="fixed inset-0 z-[660] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className={`flex w-full max-w-md flex-col gap-5 rounded-2xl border p-7 shadow-2xl ${panelClass}`}>
            <div>
              <h3 className={`text-xl font-bold tracking-tight ${titleClass}`}>Chave API do Deepgram</h3>
              <p className={`mt-1 text-sm font-medium ${mutedClass}`}>
                {deepgramKey
                  ? 'Já existe uma chave salva. Preencha abaixo apenas para substituí-la.'
                  : 'Necessária para a transcrição em tempo real. Será salva neste navegador e na nuvem — você só precisa informar uma vez.'}
              </p>
            </div>

            <div className={`flex items-center rounded-xl border px-3 ${inputClass}`}>
              <input
                type={showKeyValue ? 'text' : 'password'}
                value={keyDraft}
                onChange={e => setKeyDraft(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && saveDeepgramKey()}
                placeholder={deepgramKey ? '••••••••••••  (chave já configurada)' : 'Cole sua chave do Deepgram'}
                className="min-w-0 flex-1 bg-transparent py-3 text-sm font-medium outline-none"
                autoFocus
              />
              <button
                onClick={() => setShowKeyValue(v => !v)}
                className={`shrink-0 p-1 text-[10px] font-bold uppercase ${subtleClass} hover:opacity-70`}
              >
                {showKeyValue ? 'Ocultar' : 'Ver'}
              </button>
            </div>

            <p className={`text-xs font-medium ${subtleClass}`}>
              Obtenha ou gerencie chaves em{' '}
              <a href="https://console.deepgram.com" target="_blank" rel="noopener noreferrer" className="font-bold text-indigo-500 underline underline-offset-2">
                console.deepgram.com
              </a>
            </p>

            <div className="flex gap-3">
              <button
                onClick={() => { setShowKeyModal(false); setKeyDraft(''); }}
                className={`flex-1 rounded-xl border px-4 py-3 text-xs font-bold uppercase tracking-wider transition-all ${ghostButtonClass}`}
              >
                Cancelar
              </button>
              <button
                onClick={saveDeepgramKey}
                disabled={!keyDraft.trim()}
                className={`flex-1 rounded-xl px-4 py-3 text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${isDark ? 'bg-white text-slate-950 hover:bg-slate-200' : 'bg-slate-900 text-white hover:bg-indigo-600'}`}
              >
                Salvar chave
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: guia de compartilhamento ── */}
      {showShareGuide && (
        <div className="fixed inset-0 z-[655] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className={`flex w-full max-w-md flex-col gap-6 rounded-2xl border p-8 shadow-2xl ${panelClass}`}>
            <div>
              <h3 className={`mb-1 text-2xl font-bold tracking-tight ${titleClass}`}>Como compartilhar o áudio</h3>
              <p className={`text-sm font-medium ${mutedClass}`}>Siga esses passos no diálogo que vai abrir para capturar o áudio da sua reunião.</p>
            </div>

            <ol className="flex flex-col gap-4">
              {[
                { step: '1', title: 'Selecione "Tela inteira"', desc: 'Não escolha a janela do Teams — escolha a aba Tela inteira para que o áudio do sistema fique disponível.' },
                { step: '2', title: 'Ative "Compartilhar áudio do sistema"', desc: 'Marque a opção na parte inferior do diálogo antes de clicar em Compartilhar.' },
                { step: '3', title: 'Clique em "Compartilhar"', desc: 'A gravação começa automaticamente após o compartilhamento.' },
              ].map(item => (
                <li key={item.step} className="flex items-start gap-3">
                  <span className={`mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg text-xs font-bold ${isDark ? 'bg-white text-slate-950' : 'bg-slate-900 text-white'}`}>{item.step}</span>
                  <div>
                    <p className={`text-sm font-bold ${titleClass}`}>{item.title}</p>
                    <p className={`mt-0.5 text-xs ${mutedClass}`}>{item.desc}</p>
                  </div>
                </li>
              ))}
            </ol>

            <div className={`rounded-xl border px-4 py-3 text-xs font-medium ${isDark ? 'border-amber-500/30 bg-amber-500/10 text-amber-300' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
              <strong>Dica para Teams:</strong> O Teams desktop bloqueia o áudio quando apenas a janela é compartilhada. Compartilhe a tela inteira para contornar essa restrição.
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowShareGuide(false)}
                className={`flex-1 rounded-xl border px-4 py-3 text-sm font-bold uppercase tracking-wider transition-all ${ghostButtonClass}`}
              >
                Cancelar
              </button>
              <button
                onClick={() => { setShowShareGuide(false); startRecording(); }}
                className={`flex-1 rounded-xl px-4 py-3 text-sm font-bold uppercase tracking-wider transition-all ${isDark ? 'bg-white text-slate-950 hover:bg-slate-200' : 'bg-slate-900 text-white hover:bg-indigo-600'}`}
              >
                Entendido, iniciar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
