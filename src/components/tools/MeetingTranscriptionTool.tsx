import React, { useState, useRef, useEffect, useCallback } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions, db } from '@/firebase';
import { collection, addDoc, getDocs, query, orderBy, limit } from 'firebase/firestore';

export interface TranscriptionEntry {
  id: string;
  speaker: 'Você' | 'Reunião';
  text: string;
  timestamp: Date;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface MeetingTranscriptionToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
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
}

const GROUP_WINDOW_MS = 7000;
const SHORT_FRAGMENT_WORDS = 6;
const MAX_GROUPED_WORDS = 64;
const HISTORY_MAX_ITEMS = 30;
const HISTORY_STORAGE_KEY = 'hermes_meeting_history_v1';
const SYSTEM_AUDIO_SILENCE_WARNING_MS = 12000;
const SYSTEM_AUDIO_ACTIVITY_THRESHOLD = 0.004;

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

export const MeetingTranscriptionTool: React.FC<MeetingTranscriptionToolProps> = ({ onBack, showToast }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isSavingToDrive, setIsSavingToDrive] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptionEntry[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isChatting, setIsChatting] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [isHistoryOpen, setIsHistoryOpen] = useState(true);
  const [meetingStartedAt, setMeetingStartedAt] = useState<Date | null>(null);
  const [meetingEndedAt, setMeetingEndedAt] = useState<Date | null>(null);
  const [meetingHistory, setMeetingHistory] = useState<MeetingHistoryEntry[]>([]);
  const [isTitleGenerating, setIsTitleGenerating] = useState(false);
  const [showShareGuide, setShowShareGuide] = useState(false);

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
  const chatEndRef = useRef<HTMLDivElement>(null);
  const transcriptsRef = useRef<TranscriptionEntry[]>([]);
  const chatMessagesRef = useRef<ChatMessage[]>([]);
  const meetingStartedAtRef = useRef<Date | null>(null);
  const lastPersistedMeetingIdRef = useRef<string | null>(null);
  const systemAudioActivityDetectedRef = useRef(false);

  const scrollToBottomTranscripts = () => {
    transcriptsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const scrollToBottomChat = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottomTranscripts();
  }, [transcripts]);

  useEffect(() => {
    scrollToBottomChat();
  }, [chatMessages]);

  useEffect(() => {
    transcriptsRef.current = transcripts;
  }, [transcripts]);

  useEffect(() => {
    chatMessagesRef.current = chatMessages;
  }, [chatMessages]);

  useEffect(() => {
    meetingStartedAtRef.current = meetingStartedAt;
  }, [meetingStartedAt]);

  useEffect(() => {
    // Load from Firestore first, fallback to localStorage
    const loadHistory = async () => {
      try {
        const q = query(collection(db, 'reunioes'), orderBy('startedAt', 'desc'), limit(HISTORY_MAX_ITEMS));
        const snapshot = await getDocs(q);
        if (!snapshot.empty) {
          const firestoreMeetings: MeetingHistoryEntry[] = snapshot.docs.map(doc => ({
            id: doc.data().startedAt as string,
            titulo: (doc.data().titulo as string) || 'Reunião sem título',
            startedAt: doc.data().startedAt as string,
            endedAt: doc.data().endedAt as string,
            transcriptCount: (doc.data().transcriptCount as number) || 0,
            chatCount: (doc.data().chatCount as number) || 0,
            transcripts: (doc.data().transcripts as MeetingHistoryEntry['transcripts']) || [],
            chats: (doc.data().chats as MeetingHistoryEntry['chats']) || [],
            firestoreId: doc.id,
          }));
          setMeetingHistory(firestoreMeetings);
          return;
        }
      } catch (e) {
        console.error('Erro ao carregar reuniões do Firestore:', e);
      }
      // Fallback: localStorage
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
    const chatSnapshot = chatMessagesRef.current;

    const newEntry: MeetingHistoryEntry = {
      id: meetingId,
      titulo: `Reunião ${new Date(meetingId).toLocaleDateString('pt-BR')} ${new Date(meetingId).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`,
      startedAt: startedAt.toISOString(),
      endedAt: endedAt.toISOString(),
      transcriptCount: transcriptSnapshot.length,
      chatCount: chatSnapshot.length,
      transcripts: transcriptSnapshot.map(t => ({
        speaker: t.speaker,
        text: t.text,
        timestamp: t.timestamp.toISOString(),
      })),
      chats: chatSnapshot.map(c => ({
        role: c.role,
        content: c.content,
        timestamp: c.timestamp.toISOString(),
      })),
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
    let micStream: MediaStream | null = null;
    let systemStream: MediaStream | null = null;

    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
        showToast('Áudio não capturado. Selecione "Tela inteira" e marque "Compartilhar áudio do sistema".', 'error');
        systemStream.getTracks().forEach(track => track.stop());
        micStream.getTracks().forEach(track => track.stop());
        return;
      }

      const displayTrack = systemStream.getVideoTracks()[0];
      const displaySettings = displayTrack?.getSettings() as DisplayMediaTrackSettings | undefined;
      if (displaySettings?.displaySurface && displaySettings.displaySurface !== 'monitor') {
        showToast('Para reuniões no Teams, prefira "Tela inteira"; janelas individuais normalmente não entregam o áudio do sistema.', 'info');
      }

      const startedNow = new Date();
      setTranscripts([]);
      setChatMessages([]);
      setMeetingStartedAt(startedNow);
      setMeetingEndedAt(null);
      meetingStartedAtRef.current = startedNow;
      lastPersistedMeetingIdRef.current = null;

      micStreamRef.current = micStream;
      systemStreamRef.current = systemStream;
      startSystemAudioMonitor(systemStream);

      const wsUrl = 'wss://api.deepgram.com/v1/listen?model=nova-2&language=pt-BR';
      const apiKey = import.meta.env.VITE_DEEPGRAM_API_KEY;

      if (!apiKey) {
        showToast('Chave API do Deepgram não configurada.', 'error');
        systemStream.getTracks().forEach(track => track.stop());
        micStream.getTracks().forEach(track => track.stop());
        stopSystemAudioMonitor();
        return;
      }

      const protocols = ['token', apiKey];
      const micWs = new WebSocket(wsUrl, protocols);
      const systemWs = new WebSocket(wsUrl, protocols);
      micWsRef.current = micWs;
      systemWsRef.current = systemWs;

      micWs.onopen = () => {
        const recorder = new MediaRecorder(micStream);
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

      systemWs.onopen = () => {
        const recorder = new MediaRecorder(systemStream);
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

      systemStream.getVideoTracks().forEach(track => {
        track.onended = () => {
          stopRecording(true);
        };
      });

      setIsRecording(true);
      showToast('Gravação e transcrição iniciadas.', 'info');
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

  const buildMeetingSummaryContent = useCallback(
    (endedAtOverride?: Date, customTranscripts?: TranscriptionEntry[], customChats?: ChatMessage[], customStartedAt?: Date) => {
      const effectiveTranscripts = customTranscripts ?? transcripts;
      const effectiveChats = customChats ?? chatMessages;
      const started = customStartedAt ?? meetingStartedAt ?? effectiveTranscripts[0]?.timestamp ?? new Date();
      const ended = endedAtOverride ?? meetingEndedAt ?? effectiveTranscripts[effectiveTranscripts.length - 1]?.timestamp ?? new Date();

      const transcriptionLines =
        effectiveTranscripts.length > 0
          ? effectiveTranscripts.map(t => `[${t.timestamp.toLocaleTimeString('pt-BR')}] ${t.speaker}: ${t.text}`)
          : ['(Sem falas transcritas)'];

      const chatLines =
        effectiveChats.length > 0
          ? effectiveChats.map(m => `[${m.timestamp.toLocaleTimeString('pt-BR')}] ${m.role === 'user' ? 'Você' : 'Assistente'}: ${m.content}`)
          : ['(Sem interações no chatbot)'];

      return [
        'TRANSCRIÇÃO DE REUNIÃO',
        '',
        `Início: ${started.toLocaleString('pt-BR')}`,
        `Fim: ${ended.toLocaleString('pt-BR')}`,
        '',
        '=== TRANSCRIÇÃO ===',
        ...transcriptionLines,
        '',
        '=== CHAT ASSISTENTE ===',
        ...chatLines,
        '',
      ].join('\n');
    },
    [meetingStartedAt, meetingEndedAt, transcripts, chatMessages]
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
    const chatSnapshot = [...chatMessagesRef.current];

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
        chatCount: chatSnapshot.length,
        transcripts: transcriptSnapshot.map(t => ({
          speaker: t.speaker,
          text: t.text,
          timestamp: t.timestamp.toISOString(),
        })),
        chats: chatSnapshot.map(c => ({
          role: c.role,
          content: c.content,
          timestamp: c.timestamp.toISOString(),
        })),
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
    if (transcripts.length === 0 && chatMessages.length === 0) {
      showToast('Não há conteúdo para copiar.', 'info');
      return;
    }

    try {
      const content = buildMeetingSummaryContent();
      await navigator.clipboard.writeText(content);
      showToast('Conteúdo da reunião copiado.', 'success');
    } catch (error) {
      console.error(error);
      showToast('Falha ao copiar conteúdo da reunião.', 'error');
    }
  };

  const handleFinalizeAndSaveToDrive = async () => {
    if (transcripts.length === 0 && chatMessages.length === 0) {
      showToast('Sem conteúdo para salvar no Drive.', 'info');
      return;
    }

    setIsSavingToDrive(true);
    try {
      if (isRecording) {
        stopRecording(true);
        await new Promise(resolve => setTimeout(resolve, 700));
      }

      const endedAt = new Date();
      setMeetingEndedAt(endedAt);

      const startedAt = meetingStartedAt ?? transcripts[0]?.timestamp ?? endedAt;
      const content = buildMeetingSummaryContent(endedAt);
      const fileName = buildMeetingFileName(startedAt);

      const saveMeetingFunc = httpsCallable(functions, 'salvarTranscricaoReuniao');
      const result = await saveMeetingFunc({
        startedAt: startedAt.toISOString(),
        endedAt: endedAt.toISOString(),
        fileName,
        content,
      });

      const data = result.data as { success?: boolean };
      if (data?.success) {
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
    setTranscripts(
      entry.transcripts.map(t => ({
        id: `${t.timestamp}-${Math.random().toString(36).slice(2)}`,
        speaker: t.speaker,
        text: t.text,
        timestamp: new Date(t.timestamp),
      }))
    );
    setChatMessages(
      entry.chats.map(c => ({
        id: `${c.timestamp}-${Math.random().toString(36).slice(2)}`,
        role: c.role,
        content: c.content,
        timestamp: new Date(c.timestamp),
      }))
    );
    setMeetingStartedAt(new Date(entry.startedAt));
    setMeetingEndedAt(new Date(entry.endedAt));
    showToast('Sessão carregada do histórico.', 'info');
  };

  const handleCopyHistoryEntry = async (entry: MeetingHistoryEntry) => {
    try {
      const historyTranscripts: TranscriptionEntry[] = entry.transcripts.map(t => ({
        id: `${t.timestamp}-${Math.random().toString(36).slice(2)}`,
        speaker: t.speaker,
        text: t.text,
        timestamp: new Date(t.timestamp),
      }));
      const historyChats: ChatMessage[] = entry.chats.map(c => ({
        id: `${c.timestamp}-${Math.random().toString(36).slice(2)}`,
        role: c.role,
        content: c.content,
        timestamp: new Date(c.timestamp),
      }));

      const text = buildMeetingSummaryContent(new Date(entry.endedAt), historyTranscripts, historyChats, new Date(entry.startedAt));
      await navigator.clipboard.writeText(text);
      showToast('Sessão do histórico copiada.', 'success');
    } catch (e) {
      console.error(e);
      showToast('Erro ao copiar sessão do histórico.', 'error');
    }
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: chatInput,
      timestamp: new Date(),
    };

    setChatMessages(prev => [...prev, userMessage]);
    setChatInput('');
    setIsChatting(true);

    try {
      const contextSnapshot = transcripts
        .map(t => `[${t.timestamp.toLocaleTimeString()}] ${t.speaker}: ${t.text}`)
        .join('\n');

      const fullPrompt =
        `Contexto da reunião em andamento:\n\n${contextSnapshot || 'Ainda sem transcrição.'}` +
        `\n\nPergunta/comando do usuário: ${userMessage.content}`;

      const askChatbotFunc = httpsCallable(functions, 'askChatbot');
      let reply = 'Não consegui gerar uma resposta agora.';

      try {
        const response = await askChatbotFunc({ prompt: fullPrompt });
        const data = response.data as { result?: string };
        if (data?.result?.trim()) reply = data.result.trim();
      } catch (e) {
        console.error('AI Error:', e);
        showToast('Assistente indisponível no momento.', 'error');
      }

      setChatMessages(prev => [
        ...prev,
        {
          id: `${Date.now()}-bot`,
          role: 'assistant',
          content: reply,
          timestamp: new Date(),
        },
      ]);
    } catch (error) {
      console.error(error);
      showToast('Erro ao comunicar com a IA.', 'error');
    } finally {
      setIsChatting(false);
    }
  };

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 h-full flex flex-col pb-20 relative">
      <div className="flex items-center gap-6 mb-8 flex-shrink-0">
        <button
          onClick={onBack}
          className="w-12 h-12 bg-white rounded-none-none flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-900 transition-all shadow-none"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex-1">
          <h2 className="text-3xl font-mono font-bold uppercase tracking-tight text-slate-900">Transcrição de Reuniões</h2>
          <p className="text-slate-500 font-medium">Capture e interaja com o áudio da sua reunião em tempo real via IA.</p>
        </div>
      </div>

      <div className="flex-1 min-h-[600px]">
        <div className="bg-white rounded-none-none border border-slate-200 shadow-xl flex flex-col overflow-hidden h-full">
          <div className="p-6 border-b border-slate-200 flex justify-between items-center bg-slate-50 shrink-0 gap-3">
            <h3 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              Transcrição
              {isRecording && (
                <span className="flex h-3 w-3 relative ml-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-none-none bg-rose-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-none-none h-3 w-3 bg-rose-500"></span>
                </span>
              )}
            </h3>
            <div className="flex items-center justify-end gap-2 flex-wrap">
              <button
                onClick={handleCopyMeetingContent}
                disabled={transcripts.length === 0 && chatMessages.length === 0}
                className="px-4 py-2 rounded-none-none text-[10px] font-bold uppercase tracking-wider transition-all shadow-none bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-40"
              >
                Copiar Conteúdo
              </button>
              <button
                onClick={handleFinalizeAndSaveToDrive}
                disabled={isSavingToDrive || (transcripts.length === 0 && chatMessages.length === 0)}
                className="px-4 py-2 rounded-none-none text-[10px] font-bold uppercase tracking-wider transition-all shadow-none bg-emerald-100 text-emerald-700 hover:bg-emerald-200 disabled:opacity-40"
              >
                {isSavingToDrive ? 'Salvando...' : 'Finalizar e Salvar no Drive'}
              </button>
              <button
                onClick={() => setIsChatOpen(prev => !prev)}
                className="px-4 py-2 rounded-none-none text-[10px] font-bold uppercase tracking-wider transition-all shadow-none bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
              >
                {isChatOpen ? 'Minimizar Chat' : 'Abrir Chat'}
              </button>
              <button
                onClick={() => (isRecording ? stopRecording(true) : setShowShareGuide(true))}
                disabled={isSavingToDrive}
                className={`px-6 py-2 rounded-none-none text-xs font-bold uppercase tracking-wider transition-all shadow-none disabled:opacity-50 ${
                  isRecording ? 'bg-rose-100 text-rose-600 hover:bg-rose-200' : 'bg-slate-900 text-white hover:bg-blue-600'
                }`}
              >
                {isRecording ? 'Parar Gravação' : 'Iniciar Gravação'}
              </button>
            </div>
          </div>

          {meetingHistory.length > 0 && (
            <div className="px-6 py-4 border-b border-slate-200 bg-white">
              <button
                onClick={() => setIsHistoryOpen(prev => !prev)}
                className="w-full flex items-center justify-between text-left"
              >
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Histórico de Reuniões ({meetingHistory.length})
                </span>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  {isHistoryOpen ? 'Ocultar' : 'Mostrar'}
                </span>
              </button>

              {isHistoryOpen && (
                <div className="mt-3 max-h-40 overflow-y-auto custom-scrollbar space-y-2">
                  {meetingHistory.map(entry => {
                    const started = new Date(entry.startedAt);
                    const ended = new Date(entry.endedAt);
                    return (
                      <div key={entry.id} className="border border-slate-200 rounded-none-none p-3 flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-xs font-bold text-slate-800 truncate flex items-center gap-1">
                            {entry.titulo || `${started.toLocaleDateString('pt-BR')} ${started.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`}
                            {isTitleGenerating && entry.id === meetingStartedAt?.toISOString() && (
                              <span className="w-3 h-3 border border-slate-300 border-t-blue-500 rounded-none-none animate-spin inline-block ml-1" />
                            )}
                          </p>
                          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                            {started.toLocaleDateString('pt-BR')} • {started.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })} - {ended.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })} • {entry.transcriptCount} falas
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            onClick={() => handleCopyHistoryEntry(entry)}
                            className="px-3 py-2 rounded-none-none text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-700 hover:bg-slate-200"
                          >
                            Copiar
                          </button>
                          <button
                            onClick={() => handleLoadHistoryEntry(entry)}
                            className="px-3 py-2 rounded-none-none text-[10px] font-bold uppercase tracking-wider bg-blue-50 text-blue-700 hover:bg-blue-100"
                          >
                            Carregar
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          <div className="flex-1 p-6 overflow-y-auto custom-scrollbar space-y-4">
            {transcripts.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center opacity-40">
                <svg className="w-16 h-16 text-slate-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.5"
                    d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
                  />
                </svg>
                <p className="text-slate-400 font-bold">Inicie a gravação para ver a transcrição.</p>
              </div>
            ) : (
              transcripts.map(t => (
                <div key={t.id} className={`flex flex-col ${t.speaker === 'Você' ? 'items-end' : 'items-start'}`}>
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1 mx-1">
                    {t.speaker} • {t.timestamp.toLocaleTimeString()}
                  </span>
                  <div
                    className={`px-4 py-3 rounded-none-none max-w-[85%] ${
                      t.speaker === 'Você' ? 'bg-blue-600 text-white rounded-none-tr-sm' : 'bg-slate-100 text-slate-800 rounded-none-tl-sm'
                    }`}
                  >
                    <p className="text-sm font-medium">{t.text}</p>
                  </div>
                </div>
              ))
            )}
            <div ref={transcriptsEndRef} />
          </div>
        </div>
      </div>

      {isChatOpen ? (
        <div className="absolute bottom-4 right-4 md:bottom-6 md:right-6 z-30 w-[calc(100%-2rem)] sm:w-[420px] h-[68%] min-h-[340px] max-h-[560px] bg-white rounded-none-3xl border border-slate-200 shadow-none flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-200 bg-slate-50 shrink-0 flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-slate-900">Chatbot Assistente</h3>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mt-1">
                Baseado no contexto da reunião
              </p>
            </div>
            <button
              onClick={() => setIsChatOpen(false)}
              className="w-9 h-9 rounded-none-none border border-slate-200 text-slate-500 hover:text-slate-900 hover:border-slate-300 transition-all"
              aria-label="Minimizar chat"
              title="Minimizar chat"
            >
              <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M20 12H4" />
              </svg>
            </button>
          </div>

          <div className="flex-1 p-4 overflow-y-auto custom-scrollbar space-y-4">
            {chatMessages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center opacity-40">
                <svg className="w-14 h-14 text-slate-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.5"
                    d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                  />
                </svg>
                <p className="text-slate-400 font-bold">Pergunte algo sobre a reunião.</p>
              </div>
            ) : (
              chatMessages.map(msg => (
                <div key={msg.id} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1 mx-1">
                    {msg.role === 'user' ? 'Você' : 'Assistente'} • {msg.timestamp.toLocaleTimeString()}
                  </span>
                  <div
                    className={`px-4 py-3 rounded-none-none max-w-[90%] ${
                      msg.role === 'user'
                        ? 'bg-emerald-600 text-white rounded-none-tr-sm'
                        : 'bg-slate-100 text-slate-800 rounded-none-tl-sm border border-slate-200'
                    }`}
                  >
                    <p className="text-sm font-medium whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              ))
            )}
            {isChatting && (
              <div className="flex flex-col items-start mt-4">
                <div className="px-4 py-3 rounded-none-none bg-slate-100 text-slate-500 rounded-none-tl-sm border border-slate-200 flex items-center gap-2 w-16 justify-center">
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-none-none animate-bounce"></span>
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-none-none animate-bounce" style={{ animationDelay: '0.2s' }}></span>
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-none-none animate-bounce" style={{ animationDelay: '0.4s' }}></span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="p-4 bg-white border-t border-slate-200 shrink-0">
            <div className="flex gap-2">
              <input
                type="text"
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                placeholder="Pergunte sobre a reunião..."
                disabled={isChatting}
                className="flex-1 bg-slate-50 border border-slate-200 rounded-none-none px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all disabled:opacity-50"
              />
              <button
                onClick={handleSendMessage}
                disabled={isChatting || !chatInput.trim()}
                className="bg-slate-900 text-white p-3 rounded-none-none hover:bg-blue-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setIsChatOpen(true)}
          className="absolute bottom-4 right-4 md:bottom-6 md:right-6 z-30 bg-slate-900 text-white rounded-none-none px-5 py-3 shadow-xl hover:bg-blue-600 transition-all text-xs font-bold uppercase tracking-wider"
        >
          Chat da Reunião
        </button>
      )}

      {showShareGuide && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-white rounded-none-3xl shadow-none max-w-md w-full mx-4 p-8 flex flex-col gap-6">
            <div>
              <h3 className="text-2xl font-bold text-slate-900 tracking-tight mb-1">Como compartilhar o áudio</h3>
              <p className="text-slate-500 text-sm font-medium">Siga esses passos no diálogo que vai abrir para capturar o áudio da sua reunião.</p>
            </div>

            <ol className="flex flex-col gap-4">
              <li className="flex items-start gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-none-none bg-slate-900 text-white text-xs font-bold flex items-center justify-center mt-0.5">1</span>
                <div>
                  <p className="font-bold text-slate-900 text-sm">Selecione "Tela inteira"</p>
                  <p className="text-slate-500 text-xs mt-0.5">Não escolha a janela do Teams — escolha a aba <strong>Tela inteira</strong> para que o áudio do sistema fique disponível.</p>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-none-none bg-slate-900 text-white text-xs font-bold flex items-center justify-center mt-0.5">2</span>
                <div>
                  <p className="font-bold text-slate-900 text-sm">Ative "Compartilhar áudio do sistema"</p>
                  <p className="text-slate-500 text-xs mt-0.5">Marque a opção na parte inferior do diálogo antes de clicar em Compartilhar.</p>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-none-none bg-slate-900 text-white text-xs font-bold flex items-center justify-center mt-0.5">3</span>
                <div>
                  <p className="font-bold text-slate-900 text-sm">Clique em "Compartilhar"</p>
                  <p className="text-slate-500 text-xs mt-0.5">A gravação começa automaticamente após o compartilhamento.</p>
                </div>
              </li>
            </ol>

            <div className="bg-amber-50 border border-amber-200 rounded-none-none px-4 py-3 text-xs text-amber-800 font-medium">
              <strong>Dica para Teams:</strong> O Teams desktop bloqueia o áudio quando apenas a janela é compartilhada. Compartilhe a tela inteira para contornar essa restrição.
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowShareGuide(false)}
                className="flex-1 px-4 py-3 rounded-none-none text-sm font-bold uppercase tracking-wider bg-slate-100 text-slate-600 hover:bg-slate-200 transition-all"
              >
                Cancelar
              </button>
              <button
                onClick={() => { setShowShareGuide(false); startRecording(); }}
                className="flex-1 px-4 py-3 rounded-none-none text-sm font-bold uppercase tracking-wider bg-slate-900 text-white hover:bg-blue-600 transition-all"
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
