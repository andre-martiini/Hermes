import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions, db, auth } from '@/firebase';
import { collection, getDocs, updateDoc, deleteDoc, doc } from 'firebase/firestore';
import { HermesGlobalChat } from './HermesGlobalChat';
import {
  useSharedMeetingRecordingEngine,
  type TranscriptionEntry,
  type RegistroConsentimento,
  type MeetingHistoryEntry,
  type RecordingMeta,
} from '../../hooks/useMeetingRecordingEngine';
import { casarCartoes, filtrarRecentes, type CartaoCasado } from '../../utils/cartoesReuniao';
import { BancoRespostasEditor } from './BancoRespostasEditor';
import { DesdobramentoReuniaoModal } from './DesdobramentoReuniaoModal';
import { listarBancos } from '../../services/bancosRespostasService';
import type { BancoRespostas } from '../../utils/bancosRespostas';
import {
  buscarEventoReuniaoAtivoOuProximo,
  casarBancoComEvento,
  resolverBancoAutomatico,
  type ReuniaoAtivaOuProxima,
  validarInicioGravacao,
  formatarCabecalhoConsentimento,
  extrairFalasJanelaTempo,
  montarPromptUltimosSegundos,
  montarPromptConsultaAcervo,
} from '../../utils/reuniaoAgenda';
import type { GoogleCalendarEvent } from '@/types';

// Reexportados para não quebrar quem já importava esses tipos daqui
// (ex.: Modals.tsx) — a definição real agora vive junto do motor de
// gravação, que passou a rodar no nível raiz do app em vez de aqui.
export type { TranscriptionEntry, RegistroConsentimento, MeetingHistoryEntry };

interface MeetingTranscriptionToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
  isDark?: boolean;
  googleEvents?: GoogleCalendarEvent[];
}

// Quanto de fala recente entra no casamento. Curto demais perde a pergunta
// partida em duas frases; longo demais faz cartão subir por assunto que já passou.
const JANELA_CARTAO_MS = 25000;
// Três é o que cabe num olhar de relance no meio de uma frase.
const MAX_CARTOES_VISIVEIS = 3;
const LIVE_CONTEXT_MAX_CHARS = 9000;

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

export const MeetingTranscriptionTool: React.FC<MeetingTranscriptionToolProps> = ({
  onBack,
  showToast,
  isDark = false,
  googleEvents,
}) => {
  // Motor de gravação: compartilhado com o resto do app via Context (ver
  // useSharedMeetingRecordingEngine) — instanciado uma vez no componente raiz
  // (index.tsx), não aqui. É isso que faz a gravação sobreviver a esta view
  // sendo desmontada quando o usuário troca de aba/ferramenta.
  const engine = useSharedMeetingRecordingEngine(showToast);
  const {
    isRecording,
    transcripts, setTranscripts,
    meetingStartedAt, setMeetingStartedAt,
    meetingEndedAt, setMeetingEndedAt,
    meetingHistory, setMeetingHistory,
    isTitleGenerating,
    elapsedMs,
    deepgramKey,
    chaveRejeitada,
    registroConsentimento, setRegistroConsentimento,
    transcriptsRef,
    meetingStartedAtRef,
    meetingHistoryRef,
    isRecordingRef,
    registroConsentimentoRef,
    driveLinkByMeetingIdRef,
    stopRecording,
  } = engine;
  const [isSavingToDrive, setIsSavingToDrive] = useState(false);

  // ── Banco de respostas escolhido para esta reunião ─────────────────────
  // O banco é DADO, não código: cada reunião tem o seu, criado antes no editor.
  // Sem banco escolhido a coluna de cartões simplesmente não aparece — assistência
  // ao vivo é opcional, e reunião sem preparação continua funcionando como sempre.
  const [bancos, setBancos] = useState<BancoRespostas[]>([]);
  const [bancoSelecionadoId, setBancoSelecionadoId] = useState<string>('');
  const [editorBancosAberto, setEditorBancosAberto] = useState(false);
  const [desdobramentoAberto, setDesdobramentoAberto] = useState(false);

  // ── Vínculo Banco ↔ Reunião Google Calendar ────────────────────────────
  const [eventosAgenda, setEventosAgenda] = useState<GoogleCalendarEvent[]>(googleEvents ?? []);
  const [reuniaoAgendaAtiva, setReuniaoAgendaAtiva] = useState<ReuniaoAtivaOuProxima | null>(null);
  const [bancoSugeridoAgendaId, setBancoSugeridoAgendaId] = useState<string | null>(null);
  const [escolhaManualBanco, setEscolhaManualBanco] = useState(false);

  // ── Aviso e Consentimento de Gravação (Terceiros Presentes) ─────────────
  const [terceirosPresentes, setTerceirosPresentes] = useState(false);
  const [avisoConsentimento, setAvisoConsentimento] = useState(false);

  // O título definitivo só é gerado ao gravar a reunião. Para o desdobramento
  // basta um rótulo que identifique de qual reunião a ação veio, e o horário
  // da primeira fala serve — vem do estado, então acompanha a tela.
  const tituloDaReuniaoCorrente = useMemo(() => {
    const inicio = transcripts[0]?.timestamp;
    if (!inicio) return '';
    return `Reunião ${inicio.toLocaleDateString('pt-BR')} ${inicio.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
  }, [transcripts]);

  const carregarBancos = useCallback(async () => {
    try {
      setBancos(await listarBancos());
    } catch (e) {
      console.error('Erro ao carregar bancos de resposta', e);
    }
  }, []);

  useEffect(() => {
    void carregarBancos();
  }, [carregarBancos]);

  useEffect(() => {
    if (googleEvents && googleEvents.length > 0) {
      setEventosAgenda(googleEvents);
      return;
    }
    const carregarEventos = async () => {
      try {
        const snap = await getDocs(collection(db, 'google_calendar_events'));
        const evs = snap.docs.map(d => ({ id: d.id, ...d.data() } as GoogleCalendarEvent));
        setEventosAgenda(evs);
      } catch (err) {
        console.error('Erro ao carregar eventos da agenda no MeetingTranscriptionTool', err);
      }
    };
    void carregarEventos();
  }, [googleEvents]);

  // Pré-seleciona automaticamente o banco associado ao evento em curso/próximo
  useEffect(() => {
    if (bancos.length === 0 || eventosAgenda.length === 0) return;
    const { bancoSugerido, eventoAtivo } = resolverBancoAutomatico(bancos, eventosAgenda);
    setReuniaoAgendaAtiva(eventoAtivo);

    if (bancoSugerido) {
      setBancoSugeridoAgendaId(bancoSugerido.id);
      if (!escolhaManualBanco && !bancoSelecionadoId) {
        setBancoSelecionadoId(bancoSugerido.id);
      }
    } else {
      setBancoSugeridoAgendaId(null);
    }
  }, [bancos, eventosAgenda, escolhaManualBanco, bancoSelecionadoId]);

  const cartoesDoBanco = useMemo(
    () => bancos.find(b => b.id === bancoSelecionadoId)?.cartoes ?? [],
    [bancos, bancoSelecionadoId],
  );

  // ── Cartões de resposta ao vivo ────────────────────────────────────────
  // Casamento LOCAL: nenhuma chamada de rede, nenhuma chamada de LLM. Ver
  // src/utils/cartoesReuniao.ts para o porquê.
  const [cartoesVisiveis, setCartoesVisiveis] = useState<CartaoCasado[]>([]);
  const cartoesExibidosEmRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    if (!isRecording || cartoesDoBanco.length === 0) return;
    const agora = Date.now();
    // Só a fala do OUTRO convoca cartão. Se a própria fala convocasse, o
    // cartão subiria enquanto ele já está respondendo — tarde e no caminho.
    const janela = transcripts
      .filter(t => t.speaker === 'Reunião' && agora - t.timestamp.getTime() <= JANELA_CARTAO_MS)
      .map(t => t.text)
      .join(' ');
    if (!janela) return;

    const casados = filtrarRecentes(
      casarCartoes(janela, cartoesDoBanco, { maximo: MAX_CARTOES_VISIVEIS }),
      cartoesExibidosEmRef.current,
      agora,
    );
    if (casados.length === 0) return;

    casados.forEach(({ cartao }) => cartoesExibidosEmRef.current.set(cartao.id, agora));
    setCartoesVisiveis(anteriores => {
      const novos = [...casados, ...anteriores.filter(a => !casados.some(c => c.cartao.id === a.cartao.id))];
      return novos.slice(0, MAX_CARTOES_VISIVEIS);
    });
  }, [transcripts, isRecording, cartoesDoBanco]);

  useEffect(() => {
    // Reunião nova começa sem cartão na tela e sem memória da anterior.
    if (isRecording) {
      setCartoesVisiveis([]);
      cartoesExibidosEmRef.current = new Map();
    }
  }, [isRecording]);

  const [showShareGuide, setShowShareGuide] = useState(false);
  const [showHistoryPanel, setShowHistoryPanel] = useState(false);
  const [confirmDeleteEntryId, setConfirmDeleteEntryId] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [autoFollow, setAutoFollow] = useState(true);
  const [viewingEntryId, setViewingEntryId] = useState<string | null>(null);
  const [driveSaveInfo, setDriveSaveInfo] = useState<{ meetingId: string; webViewLink: string } | null>(null);

  const [showKeyModal, setShowKeyModal] = useState(false);
  const [keyDraft, setKeyDraft] = useState('');
  const [showKeyValue, setShowKeyValue] = useState(false);

  // Copiloto embutido
  const [isDesktopSplit, setIsDesktopSplit] = useState(() => typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches);
  const [isCopilotCollapsed, setIsCopilotCollapsed] = useState(false);
  const [isMobileCopilotOpen, setIsMobileCopilotOpen] = useState(false);
  const [copilotPrompt, setCopilotPrompt] = useState<string | null>(null);
  // Guardada aqui (fora do HermesGlobalChat) para que a conversa sobreviva caso o painel
  // desktop/mobile seja desmontado e remontado — ex.: ao mover, minimizar ou redimensionar
  // a janela, o que cruza o breakpoint de 1024px e troca qual instância fica montada.
  const [copilotSessionId, setCopilotSessionId] = useState<string | null>(null);

  // Escalonamento de assistência: últimos 30 segundos
  const [sugestaoUltimos30s, setSugestaoUltimos30s] = useState<string | null>(null);
  const [isEscalandoUltimos30s, setIsEscalandoUltimos30s] = useState(false);

  // Cartões em dispositivos móveis (drawer/bottom sheet)
  const [isMobileCardsOpen, setIsMobileCardsOpen] = useState(false);

  // Busca e consulta semântica ao acervo de reuniões gravadas
  const [termoBuscaAcervo, setTermoBuscaAcervo] = useState('');
  const [isBuscandoAcervo, setIsBuscandoAcervo] = useState(false);
  const [respostaAcervo, setRespostaAcervo] = useState<string | null>(null);

  const transcriptsEndRef = useRef<HTMLDivElement>(null);
  const transcriptsContainerRef = useRef<HTMLDivElement>(null);
  const autoFollowRef = useRef(true);

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

  const saveDeepgramKey = async () => {
    const ok = await engine.saveDeepgramKey(keyDraft);
    if (ok) {
      setShowKeyModal(false);
      setKeyDraft('');
    }
  };

  // Inicia a gravação via motor compartilhado, capturando o contexto de
  // agenda/banco de respostas escolhido nesta view (o motor não tem acesso a
  // esse estado, que é só da tela) e resetando o estado de navegação local.
  const startRecording = useCallback(async (consentimentoInfo?: RegistroConsentimento) => {
    setSearchTerm('');
    setAutoFollow(true);
    setViewingEntryId(null);
    setDriveSaveInfo(null);
    const meta: RecordingMeta = {
      eventoId: reuniaoAgendaAtiva?.evento.id || reuniaoAgendaAtiva?.evento.google_id || null,
      eventoTitulo: reuniaoAgendaAtiva?.evento.titulo || null,
      bancoId: bancoSelecionadoId || null,
    };
    await engine.startRecording(consentimentoInfo, meta);
  }, [engine, reuniaoAgendaAtiva, bancoSelecionadoId]);

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

      const consentLine = formatarCabecalhoConsentimento(registroConsentimentoRef.current);

      return [
        'TRANSCRIÇÃO DE REUNIÃO',
        '',
        `Início: ${started.toLocaleString('pt-BR')}`,
        `Fim: ${ended.toLocaleString('pt-BR')}`,
        consentLine,
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

  // ── Escalonamento: O que responder nos últimos 30 segundos ───────────────
  const handleEscalarUltimos30s = useCallback(async () => {
    if (transcripts.length === 0) {
      showToast?.('Nenhuma fala recente detectada ainda para analisar.', 'info');
      return;
    }
    setIsEscalandoUltimos30s(true);
    setSugestaoUltimos30s(null);
    try {
      const falasRecentes = extrairFalasJanelaTempo(transcripts, 30);
      const prompt = montarPromptUltimosSegundos(
        falasRecentes.map(f => ({ speaker: f.speaker, text: f.text })),
        reuniaoAgendaAtiva?.evento.titulo
      );
      const askChatbotFunc = httpsCallable(functions, 'askChatbot');
      const response = await askChatbotFunc({ prompt });
      const data = response.data as { result?: string };
      const texto = data?.result?.trim();
      if (texto) {
        setSugestaoUltimos30s(texto);
      } else {
        showToast?.('Não foi possível obter sugestão imediata do copiloto.', 'error');
      }
    } catch (err) {
      console.error('Erro ao acionar assistência de 30s:', err);
      showToast?.('Erro ao consultar assistência imediata.', 'error');
    } finally {
      setIsEscalandoUltimos30s(false);
    }
  }, [transcripts, reuniaoAgendaAtiva, showToast]);

  // ── Consulta ao Acervo de Reuniões Gravadas via IA ──────────────────────
  const handleConsultarAcervo = useCallback(async () => {
    const termo = termoBuscaAcervo.trim();
    if (!termo) return;
    setIsBuscandoAcervo(true);
    setRespostaAcervo(null);
    try {
      const prompt = montarPromptConsultaAcervo(
        termo,
        meetingHistory.map(m => ({
          titulo: m.titulo || 'Reunião sem título',
          startedAt: m.startedAt,
          transcripts: m.transcripts || [],
        }))
      );
      const askChatbotFunc = httpsCallable(functions, 'askChatbot');
      const response = await askChatbotFunc({ prompt });
      const data = response.data as { result?: string };
      const texto = data?.result?.trim();
      if (texto) {
        setRespostaAcervo(texto);
      } else {
        setRespostaAcervo('Nenhuma informação relevante encontrada no acervo de reuniões.');
      }
    } catch (err) {
      console.error('Erro ao consultar acervo de reuniões:', err);
      showToast?.('Erro ao pesquisar no acervo de reuniões via IA.', 'error');
    } finally {
      setIsBuscandoAcervo(false);
    }
  }, [termoBuscaAcervo, meetingHistory, showToast]);


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
  const copilotEmptyDescription = 'Respondo com base no que já foi transcrito. Também busco ações, conhecimento e histórico do Gaspar quando for útil — e você pode colar prints para dar mais contexto.';

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
          <p className={`truncate text-sm font-medium ${mutedClass}`}>Transcrição ao vivo com o Copiloto Gaspar ao lado.</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={() => { setKeyDraft(''); setShowKeyValue(false); setShowKeyModal(true); }}
            className={`flex h-10 items-center gap-2 rounded-xl border px-3 text-[10px] font-bold uppercase tracking-wider transition-all ${ghostButtonClass}`}
            title={
              chaveRejeitada
                ? 'Chave Deepgram REJEITADA pelo Deepgram — clique para trocar'
                : deepgramKey ? 'Chave Deepgram configurada — clique para alterar'
                : 'Configurar chave Deepgram'
            }
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            <span className="hidden sm:inline">Chave API</span>
            <span className={`h-2 w-2 rounded-full ${
              chaveRejeitada ? 'bg-rose-500 animate-pulse' : deepgramKey ? 'bg-emerald-500' : 'bg-rose-500'
            }`} />
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
              onClick={() => {
                if (isRecording) {
                  stopRecording(true);
                } else if (!deepgramKey) {
                  setShowKeyModal(true);
                } else {
                  if (reuniaoAgendaAtiva) {
                    setTerceirosPresentes(true);
                  }
                  setShowShareGuide(true);
                }
              }}
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
              <>
                <span className={`flex items-center gap-2 rounded-xl border px-3 py-2 font-mono text-xs font-bold ${isDark ? 'border-rose-500/30 bg-rose-500/10 text-rose-300' : 'border-rose-200 bg-rose-50 text-rose-600'}`}>
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-rose-500" />
                  </span>
                  {formatClock(elapsedMs)}
                </span>

                {/* Badge visível de consentimento e aviso durante gravação */}
                {registroConsentimento?.terceirosPresentes ? (
                  <span className={`flex items-center gap-1.5 rounded-xl border px-2.5 py-2 text-[10px] font-bold ${isDark ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`} title="Todos os participantes foram informados e consentiram com a gravação">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    Terceiros avisados (consentimento OK)
                  </span>
                ) : (
                  <span className={`flex items-center gap-1.5 rounded-xl border px-2.5 py-2 text-[10px] font-semibold ${isDark ? 'border-slate-700 bg-slate-800 text-slate-300' : 'border-slate-200 bg-slate-100 text-slate-600'}`} title="Gravação individual de notas pessoais">
                    <span className="h-2 w-2 rounded-full bg-slate-400" />
                    Individual / pessoal
                  </span>
                )}
              </>
            )}

            {/* Vínculo detectado com reunião do Google Calendar */}
            {reuniaoAgendaAtiva && (
              <div className={`flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-[11px] font-medium ${isDark ? 'border-indigo-500/30 bg-indigo-500/10 text-indigo-300' : 'border-indigo-200 bg-indigo-50 text-indigo-700'}`}>
                <span>📅</span>
                <span className="max-w-[160px] truncate sm:max-w-[220px]" title={reuniaoAgendaAtiva.evento.titulo}>
                  {reuniaoAgendaAtiva.emCurso ? 'Em curso: ' : `Em ${reuniaoAgendaAtiva.minutosParaInicio}m: `}
                  <strong>{reuniaoAgendaAtiva.evento.titulo}</strong>
                </span>
                {bancoSugeridoAgendaId && bancoSelecionadoId === bancoSugeridoAgendaId && (
                  <span className="text-[9px] font-bold uppercase tracking-wider opacity-85" title="Banco vinculado automaticamente à reunião">
                    ★ Vinculado
                  </span>
                )}
              </div>
            )}

            {hasContent && (
              <span className={`hidden items-center gap-1 text-[10px] font-bold uppercase tracking-wider md:flex ${subtleClass}`}>
                {transcripts.length} falas
              </span>
            )}

            {/* Escolha do banco. Fica ao lado do botão de gravar porque é decisão
                de ANTES da reunião — depois que a fala começa, ninguém para para configurar. */}
            <div className="flex items-center gap-1">
              <select
                value={bancoSelecionadoId}
                onChange={e => {
                  setBancoSelecionadoId(e.target.value);
                  setEscolhaManualBanco(true);
                }}
                disabled={isRecording}
                title={isRecording ? 'Escolha o banco antes de começar a gravar.' : 'Cartões que sobem sozinhos quando a pergunta aparecer'}
                className={`h-10 rounded-xl border px-2 text-[11px] font-semibold outline-none disabled:opacity-50 ${inputClass}`}
              >
                <option value="">Sem cartões</option>
                {bancos.map(banco => (
                  <option key={banco.id} value={banco.id}>
                    {banco.nome} ({banco.cartoes.length}){banco.id === bancoSugeridoAgendaId ? ' ★ (Agenda)' : ''}
                  </option>
                ))}
              </select>
              <button
                onClick={() => setEditorBancosAberto(true)}
                className={`flex h-10 items-center rounded-xl border px-2.5 text-[10px] font-bold uppercase tracking-wider transition-all ${ghostButtonClass}`}
                title="Criar e editar bancos de resposta"
              >
                Cartões
              </button>
            </div>

            {/* Desdobramento: só depois de a reunião ter conversa e ter parado.
                Durante a gravação, oferecer isso seria convidar a sair da reunião. */}
            {!isRecording && hasContent && (
              <button
                onClick={() => setDesdobramentoAberto(true)}
                className={`flex h-10 items-center rounded-xl border px-2.5 text-[10px] font-bold uppercase tracking-wider transition-all ${ghostButtonClass}`}
                title="Extrair decisões e ações desta reunião, para revisão"
              >
                Desdobramento
              </button>
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

        {/* Coluna dos cartões. A coluna nasce junto com a gravação, mesmo vazia:
            se ela aparecesse só quando o primeiro cartão casa, a transcrição
            inteira daria um pulo lateral no meio de uma frase do interlocutor —
            que é exatamente o tipo de movimento que o cartão não pode causar.
            Sem som, sem badge, sem animação: quem está falando decide se olha. */}
        {isDesktopSplit && isRecording && cartoesDoBanco.length > 0 && (
          <aside className="flex w-[300px] shrink-0 flex-col gap-2 xl:w-[340px]">
            <div className="flex items-center justify-between px-1">
              <span className={`text-[10px] font-bold uppercase tracking-wider ${subtleClass}`}>
                Cartões
              </span>
              <button
                onClick={handleEscalarUltimos30s}
                disabled={isEscalandoUltimos30s || transcripts.length === 0}
                className={`flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${
                  isDark ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30' : 'bg-amber-100 text-amber-900 hover:bg-amber-200'
                }`}
                title="Sugerir resposta objetiva para o que foi dito nos últimos 30 segundos"
              >
                <span>⚡</span>
                <span>{isEscalandoUltimos30s ? 'Analisando...' : 'Últimos 30s'}</span>
              </button>
            </div>

            {/* Sugestão imediata para os últimos 30 segundos */}
            {sugestaoUltimos30s && (
              <div className={`rounded-2xl border p-3 shadow-md animate-in fade-in duration-200 ${isDark ? 'border-amber-500/40 bg-amber-500/10' : 'border-amber-300 bg-amber-50/90'}`}>
                <div className="flex items-center justify-between gap-1 mb-1.5">
                  <span className="flex items-center gap-1 text-[10px] font-black uppercase tracking-wider text-amber-500">
                    <span>💡</span>
                    <span>O que responder agora:</span>
                  </span>
                  <button
                    onClick={() => setSugestaoUltimos30s(null)}
                    className={`text-[10px] font-bold ${subtleClass} hover:text-rose-500`}
                    title="Dispensar sugestão"
                  >
                    ✕
                  </button>
                </div>
                <p className={`text-xs font-semibold leading-relaxed ${isDark ? 'text-amber-100' : 'text-amber-950'}`}>
                  {sugestaoUltimos30s}
                </p>
                <div className="mt-2 flex items-center justify-end gap-2 border-t pt-1.5 border-amber-500/20">
                  <button
                    onClick={() => {
                      void navigator.clipboard.writeText(sugestaoUltimos30s);
                      showToast?.('Sugestão copiada!', 'success');
                    }}
                    className="text-[9px] font-bold uppercase tracking-wider text-amber-600 hover:underline"
                  >
                    Copiar
                  </button>
                </div>
              </div>
            )}

            <div className="custom-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto">
              {cartoesVisiveis.length === 0 ? (
                <div className="space-y-2 px-1">
                  <p className={`text-[11px] leading-relaxed ${subtleClass}`}>
                    Nenhum cartão ainda. Eles sobem sozinhos quando a pergunta aparecer na fala do outro lado.
                  </p>
                  <p className={`text-[10px] leading-relaxed ${subtleClass}`}>
                    Não encontrou o que precisa? Use o botão <strong>Últimos 30s</strong> acima para assistência imediata.
                  </p>
                </div>
              ) : (
                cartoesVisiveis.map(({ cartao }) => (
                  <article
                    key={cartao.id}
                    className={`rounded-2xl border p-3 shadow-sm ${panelClass}`}
                  >
                    <h4 className={`text-xs font-bold leading-snug ${titleClass}`}>{cartao.pergunta}</h4>
                    <ul className={`mt-2 space-y-1.5 text-[12px] leading-relaxed ${mutedClass}`}>
                      {cartao.resposta.map((linha, i) => (
                        <li key={i}>{linha}</li>
                      ))}
                    </ul>
                    {cartao.numeros && cartao.numeros.length > 0 && (
                      <ul className={`mt-2 space-y-1 border-t pt-2 text-[12px] font-bold ${isDark ? 'border-white/10 text-slate-100' : 'border-slate-200 text-slate-900'}`}>
                        {cartao.numeros.map((n, i) => (
                          <li key={i}>{n}</li>
                        ))}
                      </ul>
                    )}
                    {cartao.naoDizer && (
                      <p className={`mt-2 rounded-xl px-2 py-1.5 text-[11px] font-semibold leading-snug ${isDark ? 'bg-rose-500/10 text-rose-300' : 'bg-rose-50 text-rose-700'}`}>
                        Não diga: {cartao.naoDizer}
                      </p>
                    )}
                    <button
                      onClick={() => setCartoesVisiveis(atuais => atuais.filter(c => c.cartao.id !== cartao.id))}
                      className={`mt-2 text-[10px] font-bold uppercase tracking-wider ${subtleClass} hover:text-rose-500`}
                    >
                      Dispensar
                    </button>
                  </article>
                ))
              )}
            </div>
          </aside>
        )}

        {/* Coluna do Copiloto (desktop). O HermesGlobalChat fica sempre montado — recolher/expandir
            só alterna o prop isOpen (que internamente renderiza null), preservando a conversa única
            da reunião em vez de recriá-la a cada toggle. */}
        {isDesktopSplit && (
          <aside className={`relative z-20 flex shrink-0 flex-col gap-2 transition-all duration-300 ${isCopilotCollapsed ? 'w-12' : 'w-[400px] xl:w-[440px]'}`}>
            {isCopilotCollapsed && (
              <button
                onClick={() => setIsCopilotCollapsed(false)}
                className={`flex h-full w-12 flex-col items-center justify-center gap-3 rounded-2xl border transition-all ${ghostButtonClass} ${panelClass}`}
                title="Abrir Copiloto Gaspar"
              >
                <img src="/logo.png" alt="Gaspar" className="h-6 w-6 object-contain" />
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
                initialSessionId={copilotSessionId}
                onSessionChange={setCopilotSessionId}
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

      {desdobramentoAberto && (
        <DesdobramentoReuniaoModal
          isDark={isDark}
          titulo={tituloDaReuniaoCorrente}
          falas={transcripts.map(t => ({ speaker: t.speaker, text: t.text }))}
          onClose={() => setDesdobramentoAberto(false)}
          showToast={showToast}
        />
      )}

      {editorBancosAberto && (
        <BancoRespostasEditor
          isDark={isDark}
          onClose={() => setEditorBancosAberto(false)}
          onBancosMudaram={() => void carregarBancos()}
        />
      )}

      {/* Copiloto e Cartões em overlay/drawer (mobile/tablet) */}
      {!isDesktopSplit && (
        <>
          {/* Botão flutuante de Cartões no mobile */}
          {isRecording && cartoesDoBanco.length > 0 && !isMobileCardsOpen && (
            <button
              onClick={() => setIsMobileCardsOpen(true)}
              className={`fixed bottom-24 right-6 z-[600] flex h-12 items-center gap-2 rounded-full px-4 text-xs font-bold uppercase tracking-wider shadow-lg border transition-all active:scale-95 ${
                isDark ? 'bg-slate-900 border-white/20 text-white hover:bg-slate-800' : 'bg-white border-slate-300 text-slate-900 hover:bg-slate-100 shadow-slate-900/10'
              }`}
              aria-label="Abrir cartões de resposta"
            >
              <span>🃏</span>
              <span>Cartões {cartoesVisiveis.length > 0 ? `(${cartoesVisiveis.length})` : ''}</span>
            </button>
          )}

          {/* Drawer / Painel de Cartões no mobile */}
          {isMobileCardsOpen && (
            <div className="fixed inset-0 z-[650] flex justify-end">
              <div className="absolute inset-0 bg-slate-950/50 backdrop-blur-sm" onClick={() => setIsMobileCardsOpen(false)} aria-hidden="true" />
              <div className={`relative flex h-full w-full max-w-md flex-col border-l shadow-2xl animate-in slide-in-from-right duration-300 ${panelClass}`}>
                <div className={`flex h-16 flex-shrink-0 items-center justify-between border-b px-5 ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
                  <div className="flex items-center gap-2">
                    <span className="text-base">🃏</span>
                    <div>
                      <h3 className={`text-sm font-bold uppercase tracking-wider ${titleClass}`}>Cartões da Reunião</h3>
                      <p className={`text-[10px] font-semibold uppercase tracking-wider ${subtleClass}`}>
                        {cartoesVisiveis.length} {cartoesVisiveis.length === 1 ? 'cartão ativo' : 'cartões ativos'}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => setIsMobileCardsOpen(false)}
                    className={`flex h-9 w-9 items-center justify-center rounded-xl border transition-all ${ghostButtonClass}`}
                    aria-label="Fechar cartões"
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <div className={`flex items-center justify-between gap-2 border-b p-3 ${isDark ? 'bg-slate-900/40' : 'bg-slate-50'}`}>
                  <span className={`text-[11px] font-medium ${subtleClass}`}>Assistência rápida:</span>
                  <button
                    onClick={handleEscalarUltimos30s}
                    disabled={isEscalandoUltimos30s || transcripts.length === 0}
                    className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${
                      isDark ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30' : 'bg-amber-100 text-amber-900 hover:bg-amber-200'
                    }`}
                  >
                    <span>⚡</span>
                    <span>{isEscalandoUltimos30s ? 'Analisando...' : 'O que responder (30s)'}</span>
                  </button>
                </div>

                {sugestaoUltimos30s && (
                  <div className={`m-3 rounded-2xl border p-3.5 shadow-md ${isDark ? 'border-amber-500/40 bg-amber-500/10' : 'border-amber-300 bg-amber-50/90'}`}>
                    <div className="flex items-center justify-between gap-1 mb-1.5">
                      <span className="flex items-center gap-1 text-[10px] font-black uppercase tracking-wider text-amber-500">
                        <span>💡</span>
                        <span>O que responder agora:</span>
                      </span>
                      <button
                        onClick={() => setSugestaoUltimos30s(null)}
                        className={`text-[10px] font-bold ${subtleClass} hover:text-rose-500`}
                      >
                        ✕
                      </button>
                    </div>
                    <p className={`text-xs font-semibold leading-relaxed ${isDark ? 'text-amber-100' : 'text-amber-950'}`}>
                      {sugestaoUltimos30s}
                    </p>
                    <div className="mt-2 flex justify-end">
                      <button
                        onClick={() => {
                          void navigator.clipboard.writeText(sugestaoUltimos30s);
                          showToast?.('Sugestão copiada!', 'success');
                        }}
                        className="text-[9px] font-bold uppercase tracking-wider text-amber-600 hover:underline"
                      >
                        Copiar
                      </button>
                    </div>
                  </div>
                )}

                <div className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
                  {cartoesVisiveis.length === 0 ? (
                    <div className="py-8 text-center px-2 space-y-2">
                      <p className={`text-xs leading-relaxed ${subtleClass}`}>
                        Nenhum cartão ativo no momento. Eles sobem automaticamente quando o interlocutor faz perguntas mapeadas no banco.
                      </p>
                      <p className={`text-[11px] ${subtleClass}`}>
                        Use o botão <strong>O que responder (30s)</strong> acima se precisar de ajuda com o que acabou de ser falado.
                      </p>
                    </div>
                  ) : (
                    cartoesVisiveis.map(({ cartao }) => (
                      <article
                        key={cartao.id}
                        className={`rounded-2xl border p-4 shadow-sm ${panelClass}`}
                      >
                        <h4 className={`text-xs font-bold leading-snug ${titleClass}`}>{cartao.pergunta}</h4>
                        <ul className={`mt-2 space-y-1.5 text-[12px] leading-relaxed ${mutedClass}`}>
                          {cartao.resposta.map((linha, i) => (
                            <li key={i}>{linha}</li>
                          ))}
                        </ul>
                        {cartao.numeros && cartao.numeros.length > 0 && (
                          <ul className={`mt-2 space-y-1 border-t pt-2 text-[12px] font-bold ${isDark ? 'border-white/10 text-slate-100' : 'border-slate-200 text-slate-900'}`}>
                            {cartao.numeros.map((n, i) => (
                              <li key={i}>{n}</li>
                            ))}
                          </ul>
                        )}
                        {cartao.naoDizer && (
                          <p className={`mt-2 rounded-xl px-2.5 py-1.5 text-[11px] font-semibold leading-snug ${isDark ? 'bg-rose-500/10 text-rose-300' : 'bg-rose-50 text-rose-700'}`}>
                            Não diga: {cartao.naoDizer}
                          </p>
                        )}
                        <button
                          onClick={() => setCartoesVisiveis(atuais => atuais.filter(c => c.cartao.id !== cartao.id))}
                          className={`mt-3 text-[10px] font-bold uppercase tracking-wider ${subtleClass} hover:text-rose-500`}
                        >
                          Dispensar
                        </button>
                      </article>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

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
            initialSessionId={copilotSessionId}
            onSessionChange={setCopilotSessionId}
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
              {/* ── Consulta ao Acervo com IA ── */}
              <div className={`rounded-2xl border p-3.5 shadow-sm ${isDark ? 'border-indigo-500/30 bg-indigo-950/20' : 'border-indigo-200 bg-indigo-50/70'}`}>
                <div className="flex items-center gap-1.5 mb-1 text-[11px] font-bold uppercase tracking-wider text-indigo-500">
                  <span>🔍</span>
                  <span>Consultar Acervo via IA</span>
                </div>
                <p className={`text-[11px] mb-2 leading-relaxed ${mutedClass}`}>
                  Pergunte sobre acordos e temas tratados nas reuniões gravadas anteriores.
                </p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={termoBuscaAcervo}
                    onChange={e => setTermoBuscaAcervo(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') void handleConsultarAcervo(); }}
                    placeholder="Ex: O que ficou combinado com fulano?"
                    className={`min-w-0 flex-1 rounded-xl border px-3 py-2 text-xs font-medium outline-none ${inputClass}`}
                  />
                  <button
                    onClick={() => void handleConsultarAcervo()}
                    disabled={isBuscandoAcervo || !termoBuscaAcervo.trim()}
                    className={`rounded-xl px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${
                      isDark ? 'bg-white text-slate-950 hover:bg-slate-200' : 'bg-slate-900 text-white hover:bg-indigo-600'
                    }`}
                  >
                    {isBuscandoAcervo ? 'Buscando...' : 'Perguntar'}
                  </button>
                </div>

                {respostaAcervo && (
                  <div className={`mt-3 rounded-xl border p-3 ${isDark ? 'border-white/10 bg-slate-900/80' : 'border-slate-200 bg-white'}`}>
                    <div className="flex items-center justify-between gap-1 mb-1.5">
                      <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-indigo-500">
                        <span>💡</span>
                        <span>Resposta do Acervo:</span>
                      </span>
                      <button
                        onClick={() => setRespostaAcervo(null)}
                        className={`text-[10px] font-bold ${subtleClass} hover:text-rose-500`}
                        title="Fechar resposta"
                      >
                        ✕
                      </button>
                    </div>
                    <p className={`text-xs leading-relaxed whitespace-pre-wrap ${titleClass}`}>
                      {respostaAcervo}
                    </p>
                  </div>
                )}
              </div>

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

      {/* ── Modal: guia de compartilhamento e consentimento ── */}
      {showShareGuide && (
        <div className="fixed inset-0 z-[655] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className={`flex w-full max-w-lg max-h-[90vh] overflow-y-auto flex-col gap-5 rounded-2xl border p-6 sm:p-8 shadow-2xl ${panelClass}`}>
            <div>
              <h3 className={`mb-1 text-xl font-bold tracking-tight sm:text-2xl ${titleClass}`}>Preparação para Gravação</h3>
              <p className={`text-xs sm:text-sm font-medium ${mutedClass}`}>Compartilhamento de áudio e consentimento de privacidade.</p>
            </div>

            {/* ── Seção 1: Aviso e Consentimento com Terceiros ── */}
            <div className={`rounded-xl border p-4 ${isDark ? 'border-indigo-500/30 bg-indigo-950/20' : 'border-indigo-200 bg-indigo-50/70'}`}>
              <h4 className={`text-xs font-bold uppercase tracking-wider mb-2 ${titleClass}`}>
                1. Participantes e Consentimento Ético
              </h4>
              <p className={`text-xs mb-3 leading-relaxed ${mutedClass}`}>
                O Gaspar transcreve as falas e extrai automaticamente compromissos e tarefas com o nome dos participantes.
              </p>

              <div className="flex flex-col gap-2">
                <label className="flex items-center gap-2 cursor-pointer text-xs font-medium">
                  <input
                    type="radio"
                    name="consentimento_tipo"
                    checked={!terceirosPresentes}
                    onChange={() => {
                      setTerceirosPresentes(false);
                      setAvisoConsentimento(false);
                    }}
                    className="h-4 w-4 text-indigo-600"
                  />
                  <span>Gravação individual / notas pessoais (sem terceiros presentes)</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer text-xs font-medium">
                  <input
                    type="radio"
                    name="consentimento_tipo"
                    checked={terceirosPresentes}
                    onChange={() => setTerceirosPresentes(true)}
                    className="h-4 w-4 text-indigo-600"
                  />
                  <span>Há terceiros presentes na reunião</span>
                </label>
              </div>

              {terceirosPresentes && (
                <div className={`mt-3 rounded-lg border p-3 ${isDark ? 'border-amber-500/30 bg-amber-500/10 text-amber-300' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>
                  <p className="text-xs font-bold flex items-center gap-1.5">
                    <span>⚠️</span>
                    <span>Requisito de Privacidade:</span>
                  </p>
                  <p className="text-[11px] mt-1 leading-relaxed">
                    Não grave terceiros em silêncio. Informe aos participantes que a reunião está sendo gravada e que os compromissos serão documentados.
                  </p>
                  <label className="mt-2.5 flex items-start gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={avisoConsentimento}
                      onChange={(e) => setAvisoConsentimento(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded text-indigo-600"
                    />
                    <span className="text-xs font-bold">
                      Confirmo que os participantes foram avisados e consentiram com a gravação.
                    </span>
                  </label>
                </div>
              )}
            </div>

            {/* ── Seção 2: Compartilhamento do Áudio ── */}
            <div>
              <h4 className={`text-xs font-bold uppercase tracking-wider mb-2 ${titleClass}`}>
                2. Compartilhar áudio da reunião
              </h4>
              <ol className="flex flex-col gap-3">
                {[
                  { step: 'A', title: 'Selecione "Tela inteira"', desc: 'Não escolha apenas a janela — escolha a aba Tela inteira para que o áudio do sistema fique disponível.' },
                  { step: 'B', title: 'Ative "Compartilhar áudio do sistema"', desc: 'Marque a opção na parte inferior do diálogo antes de clicar em Compartilhar.' },
                  { step: 'C', title: 'Clique em "Compartilhar"', desc: 'A gravação começa automaticamente após a seleção.' },
                ].map(item => (
                  <li key={item.step} className="flex items-start gap-2.5">
                    <span className={`mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg text-xs font-bold ${isDark ? 'bg-white text-slate-950' : 'bg-slate-900 text-white'}`}>{item.step}</span>
                    <div>
                      <p className={`text-xs font-bold ${titleClass}`}>{item.title}</p>
                      <p className={`mt-0.5 text-[11px] ${mutedClass}`}>{item.desc}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>

            <div className={`rounded-xl border px-4 py-2.5 text-xs font-medium ${isDark ? 'border-amber-500/30 bg-amber-500/10 text-amber-300' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
              <strong>Dica para Teams:</strong> O Teams desktop bloqueia o áudio quando apenas a janela é compartilhada. Compartilhe a tela inteira para contornar essa restrição.
            </div>

            <div className="flex gap-3 pt-1">
              <button
                onClick={() => setShowShareGuide(false)}
                className={`flex-1 rounded-xl border px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-all ${ghostButtonClass}`}
              >
                Cancelar
              </button>
              <button
                disabled={!validarInicioGravacao(terceirosPresentes, avisoConsentimento).podeIniciar}
                onClick={() => {
                  const consent: RegistroConsentimento = {
                    terceirosPresentes,
                    avisoConfirmado: terceirosPresentes ? avisoConsentimento : false,
                    confirmadoEm: new Date().toISOString(),
                  };
                  setRegistroConsentimento(consent);
                  setShowShareGuide(false);
                  void startRecording(consent);
                }}
                className={`flex-1 rounded-xl px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-40 disabled:cursor-not-allowed ${isDark ? 'bg-white text-slate-950 hover:bg-slate-200' : 'bg-slate-900 text-white hover:bg-indigo-600'}`}
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
