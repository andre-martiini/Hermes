import React, { useEffect, useRef, useState } from 'react';
import { db, functions, auth } from '@/firebase';
import { httpsCallable } from 'firebase/functions';
import {
  addDoc,
  collection,
  deleteDoc,
  deleteField,
  doc,
  getDocs,
  limit,
  onSnapshot,
  orderBy,
  query,
  setDoc,
  Timestamp,
  updateDoc,
  where,
  writeBatch,
} from 'firebase/firestore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import MermaidBlock from './MermaidBlock';
import { getRoutingIndex, toolsRegistry } from './toolRegistry';
import { isInternalAppHref, navigateWithinApp } from '../../utils/internalNavigation';
import { buildRecordedAudioBlob, transcribeAudioViaStorage } from '../../utils/audioTranscription';
import { useHermesVoiceStream } from '@/src/hooks/useHermesVoiceStream';

export const UPLOAD_ENDPOINT = 'https://us-central1-gestao-hermes.cloudfunctions.net/uploadFileForCopiloto';
const LARGE_PASTE_THRESHOLD = 1500;
const COMPOSER_MAX_LINES = 8;
export const COPILOTO_SUPPORTED_FILE_EXTENSIONS = [
  '.pdf',
  '.doc',
  '.docx',
  '.xls',
  '.xlsx',
  '.csv',
  '.txt',
  '.json',
  '.xml',
  '.eml',
  '.md',
  '.markdown',
  '.html',
  '.htm',
  '.pptx',
  '.png',
  '.jpg',
  '.jpeg',
  '.webp',
] as const;
export const COPILOTO_FILE_ACCEPT = COPILOTO_SUPPORTED_FILE_EXTENSIONS.join(',');
export const COPILOTO_SUPPORTED_FORMATS_LABEL = 'PDF, DOC/DOCX, XLS/XLSX, CSV, TXT, JSON, XML, EML, Markdown, HTML, PPTX e imagens';

const TOOL_LABELS: Record<string, string> = {
  consultar_historico_acoes: 'Histórico',
  buscar_arquivos_acervo: 'Acervo',
  obter_contexto_tela: 'Contexto',
  pesquisar_internet: 'Internet',
  ler_pagina_web: 'Página',
  ler_documento_na_integra: 'Documento',
  salvar_memoria_global: 'Memória',
  salvar_pop_global: 'POP',
  atualizar_personalidade: 'Personalidade',
  resolver_conflito_procedimento: 'Conflito',
  criar_acao_no_sistema: 'Criar ação',
  agendar_lembrete_acao: 'Lembrete',
  editar_plano_acao: 'Plano',
  preparar_edicao_acao: 'Edição',
  preparar_reagendamento_em_lote: 'Reagendamento',
  gerar_relatorio: 'Relatório',
  registrar_no_diario: 'Diário',
  buscar_e_analisar_email: 'Email',
  gerar_rascunho_formulario: 'Formulário',
  consultar_agenda: 'Agenda',
  encontrar_slot_livre: 'Slot livre',
  consultar_financas_v2: 'Finanças',
  registrar_item_financeiro_v2: 'Item financeiro',
  criar_objetivo_estrategico: 'Objetivo criado',
  editar_objetivo_estrategico: 'Objetivo editado',
  gerenciar_item_estrategico: 'Item da estratégia',
  excluir_objetivo_estrategico: 'Objetivo excluído',
};

// Ponto 3: ferramentas usadas colapsadas por padrão — um resumo de uma linha que
// expande os chips ao clicar, para não ocupar espaço no chat.
const ToolsUsedBadges: React.FC<{ tools: string[]; isDark?: boolean }> = ({ tools, isDark }) => {
  const [expanded, setExpanded] = useState(false);
  const unique = [...new Set(tools)].filter((t) => TOOL_LABELS[t]);
  if (unique.length === 0) return null;

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className={`inline-flex items-center gap-1.5 font-mono text-[8px] font-black uppercase tracking-widest transition-colors ${isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-400 hover:text-slate-600'}`}
        title={expanded ? 'Recolher ferramentas' : 'Ver ferramentas usadas'}
      >
        <span>🔧 {unique.length} {unique.length === 1 ? 'ferramenta' : 'ferramentas'}</span>
        <svg className={`h-2.5 w-2.5 shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
      </button>
      {expanded && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {unique.map((tool) => (
            <span key={tool} className={`border px-2 py-1 font-mono text-[8px] font-black uppercase tracking-widest ${isDark ? 'border-white/10 bg-white/5 text-slate-300' : 'border-border-grid bg-white text-slate-500'}`}>
              {TOOL_LABELS[tool]}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

type CopilotMode = 'default' | 'finance' | 'saude' | 'estrategia';
type UploadPhase = 'idle' | 'uploading' | 'processing';

interface FieldChange {
  original: string;
  novo: string;
  novo_raw?: any;
}

interface PendingEdit {
  task_id: string;
  titulo: string;
  alteracoes: Record<string, FieldChange>;
  justificativa: string;
  snapshot_ts: string;
  status: 'pending' | 'completed' | 'invalidated' | 'cancelled' | 'error';
  errorMessage?: string;
}

const FIELD_LABELS: Record<string, string> = {
  titulo: 'Título',
  descricao: 'Descrição',
  data_limite: 'Data de Execução',
  prazo_final: 'Prazo Final',
  data_inicio: 'Data Início',
  horario_inicio: 'Horário Início',
  horario_fim: 'Horário Fim',
  status: 'Status',
  tags: 'Tags',
  area_tematica: 'Área Temática',
  tipo_acao: 'Tipo de Ação',
  notas: 'Notas',
  email_trigger: 'Gatilho de E-mail',
};

interface Session {
  id: string;
  title: string;
  createdAt: any;
  lastMessageAt: any;
  taskId?: string | null;
  systemId?: string | null;
  copilotMode?: CopilotMode;
  copilotScope?: 'global' | string;
  copilotStatus?: string;
}

interface Message {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: any;
  toolsUsed?: string[];
  pendingEdit?: PendingEdit;
}

interface HermesGlobalChatProps {
  isOpen: boolean;
  onClose: () => void;
  isDark?: boolean;
  userId: string;
  autoStartMic?: boolean;
  copilotMode?: CopilotMode;
  layout?: 'overlay' | 'inline';
  onOpenTask?: (taskId: string) => void;
  onOpenTool?: (tool: string, id: string) => void;
  initialPrompt?: string | null;
  onInitialPromptConsumed?: () => void;
}

const getCopilotoErrorMessage = (err: any) => {
  const raw = err?.message || err?.details || String(err) || '';
  const code = String(err?.code || '').toLowerCase();
  if (code.includes('deadline-exceeded') || /deadline|timed out|timeout/i.test(raw)) {
    return 'O copiloto demorou demais para responder. Tente dividir o pedido em partes menores.';
  }
  if (code.includes('permission-denied')) {
    return 'O copiloto não conseguiu acessar um dado necessário por falta de permissão.';
  }
  return raw || 'Erro desconhecido ao consultar o copiloto.';
};

export const isCopilotoFileSupported = (file: File) => {
  const fileName = file.name.toLowerCase();
  const hasSupportedExtension = COPILOTO_SUPPORTED_FILE_EXTENSIONS.some((extension) => fileName.endsWith(extension));
  return hasSupportedExtension || ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'].includes(file.type);
};

const formatSessionTime = (value: any) => {
  const date = value?.toDate ? value.toDate() : value instanceof Date ? value : null;
  if (!date) return '';
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
};

const formatMessageTime = (value: any) => {
  const date = value?.toDate ? value.toDate() : value instanceof Date ? value : null;
  if (!date) return '';
  return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
};

export const HermesGlobalChat: React.FC<HermesGlobalChatProps> = ({
  isOpen,
  onClose,
  isDark = false,
  userId,
  autoStartMic = false,
  copilotMode = 'default',
  layout = 'overlay',
  onOpenTask,
  onOpenTool,
  initialPrompt,
  onInitialPromptConsumed,
}) => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isComposingNewSession, setIsComposingNewSession] = useState(false);
  const [input, setInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const [popsList, setPopsList] = useState<{ id: string; titulo: string; gatilhos: string[] }[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showMobileHistory, setShowMobileHistory] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const attachedFile = attachedFiles[0] || null;
  const setAttachedFile = (file: File | null) => setAttachedFiles(file ? [file] : []);
  const [pastedContext, setPastedContext] = useState<{ text: string; name: string } | null>(null);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>('idle');
  const [footerError, setFooterError] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessingMic, setIsProcessingMic] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);

  // ── Conversa por voz em tempo real (Gemini Live via hermes-voice-bridge) ──
  const [voiceStreamStatusMessage, setVoiceStreamStatusMessage] = useState('');
  const currentSessionIdRef = useRef<string | null>(null);
  currentSessionIdRef.current = currentSessionId;

  const voiceStream = useHermesVoiceStream({
    onUserTranscript: (text) => {
      const sId = currentSessionIdRef.current;
      if (!sId) return;
      addDoc(collection(db, 'sessoes_copiloto', sId, 'mensagens'), {
        role: 'user',
        content: text,
        timestamp: Timestamp.now(),
      }).catch(() => {});
    },
    onAssistantTranscript: (text) => {
      const sId = currentSessionIdRef.current;
      if (!sId) return;
      addDoc(collection(db, 'sessoes_copiloto', sId, 'mensagens'), {
        role: 'assistant',
        content: text,
        timestamp: Timestamp.now(),
      }).catch(() => {});
    },
    onStatus: (message) => setVoiceStreamStatusMessage(message),
    onError: (message) => { setFooterError(message); setVoiceStreamStatusMessage(''); },
  });
  const [sessionPendingDeleteId, setSessionPendingDeleteId] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [copiedMessageKey, setCopiedMessageKey] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const [loadingEditId, setLoadingEditId] = useState<string | null>(null);
  const [strategyDirectives, setStrategyDirectives] = useState<string[]>([]);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toolMenuRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const micStreamRef = useRef<MediaStream | null>(null);
  const dragCounterRef = useRef(0);

  const activeSession = sessions.find((session) => session.id === currentSessionId);
  const activeCopilotStatus = activeSession?.copilotStatus;
  const isWaitingForCopilot = isLoading || !!activeCopilotStatus;
  const isBlocked = isWaitingForCopilot || uploadPhase !== 'idle' || isProcessingMic || isTranscribing;
  const modeLabel = copilotMode === 'finance' ? 'Financeiro' : copilotMode === 'saude' ? 'Saúde' : copilotMode === 'estrategia' ? 'Estratégia' : 'Global';

  const shellClass = isDark ? 'bg-[#151c27] text-[#ebf1ff]' : 'bg-[#ffffff] text-[#151c27]';
  const sidebarClass = isDark ? 'bg-[#111827] border-white/10' : 'bg-[#ffffff] border-[#e5e7eb]';
  const panelClass = isDark ? 'bg-[#151c27] border-white/10' : 'bg-[#ffffff] border-[#e5e7eb]';
  const raisedClass = isDark ? 'bg-slate-900 border-white/10 rounded-xl' : 'bg-white border-[#e5e7eb] rounded-xl shadow-sm';
  const mutedClass = isDark ? 'text-slate-500' : 'text-slate-400';
  const textSoftClass = isDark ? 'text-slate-300' : 'text-slate-600';
  const hoverClass = isDark ? 'hover:bg-white/5 rounded-lg' : 'hover:bg-slate-50 rounded-lg';

  const touchSession = async (sessionId: string, updates: Partial<Session> = {}) => {
    const sessionRef = doc(db, 'sessoes_copiloto', sessionId);
    const payload = {
      userId,
      taskId: null,
      systemId: null,
      copilotMode,
      copilotScope: 'global',
      ...updates,
      lastMessageAt: updates.lastMessageAt || Timestamp.now(),
    };

    Object.keys(payload).forEach((key) => {
      if ((payload as Record<string, any>)[key] === undefined) {
        delete (payload as Record<string, any>)[key];
      }
    });

    await setDoc(sessionRef, payload, { merge: true });
  };

  const createSession = async (initialPrompt?: string) => {
    const sessRef = await addDoc(collection(db, 'sessoes_copiloto'), {
      userId,
      title: initialPrompt ? `${initialPrompt.slice(0, 46)}${initialPrompt.length > 46 ? '...' : ''}` : 'Nova conversa',
      createdAt: Timestamp.now(),
      lastMessageAt: Timestamp.now(),
      taskId: null,
      systemId: null,
      copilotMode,
      copilotScope: 'global',
    });
    setIsComposingNewSession(false);
    setCurrentSessionId(sessRef.id);
    return sessRef.id;
  };

  useEffect(() => {
    if (!isOpen || !userId) return;
    const q = query(
      collection(db, 'sessoes_copiloto'),
      where('userId', '==', userId),
      orderBy('lastMessageAt', 'desc'),
      limit(80),
    );
    return onSnapshot(
      q,
      (snapshot) => {
        const globalSessions = snapshot.docs
          .map((sessionDoc) => ({ id: sessionDoc.id, ...sessionDoc.data() }) as Session)
          .filter((session) => session.copilotScope === 'global' || (!session.taskId && (!session.copilotMode || session.copilotMode === 'default' || session.copilotMode === copilotMode)));
        setSessions(globalSessions);
      },
      (error) => setFooterError(error?.message || 'Erro ao carregar histórico do copiloto.'),
    );
  }, [isOpen, userId, copilotMode]);

  useEffect(() => {
    if (!isOpen || !userId || copilotMode !== 'default') {
      setStrategyDirectives([]);
      return;
    }
    let cancelled = false;
    const loadStrategyDirectives = async () => {
      try {
        const snap = await getDocs(query(
          collection(db, 'estrategia_pessoal'),
          where('userId', '==', userId),
          where('status', '==', 'ativo')
        ));
        if (cancelled) return;
        const directives = snap.docs.flatMap((strategyDoc) => {
          const data = strategyDoc.data() as any;
          return Array.isArray(data.diretrizesDerivadas) ? data.diretrizesDerivadas : [];
        }).map(value => String(value || '').trim()).filter(Boolean);
        setStrategyDirectives(Array.from(new Set(directives)).slice(0, 24));
      } catch (error) {
        console.warn('[HermesGlobalChat] Falha ao carregar diretrizes estratégicas', error);
        if (!cancelled) setStrategyDirectives([]);
      }
    };
    loadStrategyDirectives();
    return () => {
      cancelled = true;
    };
  }, [isOpen, userId, copilotMode]);

  useEffect(() => {
    if (!isOpen) return;
    setIsComposingNewSession(true);
    setCurrentSessionId(null);
    setMessages([]);
    setInput('');
    setAttachedFile(null);
    setPastedContext(null);
    setFooterError(null);
    setShowTools(false);
    setShowMobileHistory(false);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !initialPrompt) return;
    sendMessage(initialPrompt);
    onInitialPromptConsumed?.();
  }, [isOpen, initialPrompt]);

  useEffect(() => {
    if (!currentSessionId) {
      setMessages([]);
      return;
    }
    const q = query(
      collection(db, 'sessoes_copiloto', currentSessionId, 'mensagens'),
      orderBy('timestamp', 'asc'),
    );
    return onSnapshot(
      q,
      (snapshot) => setMessages(snapshot.docs.map((messageDoc) => ({ id: messageDoc.id, ...messageDoc.data() }) as Message)),
      (error) => setFooterError(error?.message || 'Erro ao carregar mensagens.'),
    );
  }, [currentSessionId]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const timer = setTimeout(() => textareaRef.current?.focus(), 120);
    return () => clearTimeout(timer);
  }, [isOpen, currentSessionId]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = 'auto';
    const computedStyle = window.getComputedStyle(textarea);
    const lineHeight = parseFloat(computedStyle.lineHeight) || 20;
    const paddingY = parseFloat(computedStyle.paddingTop) + parseFloat(computedStyle.paddingBottom);
    const maxHeight = lineHeight * COMPOSER_MAX_LINES + paddingY;
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight);

    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, [input, isOpen, attachedFile, pastedContext, isProcessingMic, isTranscribing, isRecording]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isWaitingForCopilot]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (toolMenuRef.current && !toolMenuRef.current.contains(event.target as Node)) {
        setShowTools(false);
      }
    };
    window.addEventListener('mousedown', handleClickOutside);
    return () => window.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (!isOpen || !autoStartMic) return;
    const timer = setTimeout(() => startRecording(), 400);
    return () => clearTimeout(timer);
  }, [isOpen, autoStartMic]);

  // Encerra a sessao de voz ao vivo se o painel fechar (costuma so ficar
  // oculto, nao desmontar, entao o cleanup de unmount abaixo nao cobre isso).
  useEffect(() => {
    if (!isOpen) {
      voiceStream.stop();
      setIsMinimized(false);
    }
  }, [isOpen]);

  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') mediaRecorderRef.current.stop();
      if (micStreamRef.current) micStreamRef.current.getTracks().forEach((track) => track.stop());
      voiceStream.stop();
    };
  }, []);

  const resetComposer = () => {
    setInput('');
    setAttachedFile(null);
    setPastedContext(null);
    setFooterError(null);
    setShowTools(false);
  };

  const startNewConversation = () => {
    setIsComposingNewSession(true);
    setCurrentSessionId(null);
    setMessages([]);
    resetComposer();
    setShowMobileHistory(false);
    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const insertToolShortcut = (tag: string) => {
    setInput((prev) => {
      const trimmedStart = prev.trimStart();
      if (trimmedStart.startsWith(tag)) return prev;
      return prev.trim().length > 0 ? `${tag} ${prev}` : `${tag} `;
    });
    setShowTools(false);
    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  useEffect(() => {
    if (!isOpen) return;
    const q = collection(db, 'pops_diretrizes');
    return onSnapshot(
      q,
      (snapshot) => {
        const data = snapshot.docs.map((docItem) => ({ id: docItem.id, ...docItem.data() }) as { id: string; titulo: string; gatilhos: string[] });
        setPopsList(data);
      },
      (error) => console.error('Erro ao buscar POPs:', error),
    );
  }, [isOpen]);

  const insertPopShortcut = (pop: { titulo: string; gatilhos?: string[] }) => {
    const gatilhoPrincipal = (pop.gatilhos && pop.gatilhos.length > 0 && pop.gatilhos[0]) ? pop.gatilhos[0] : pop.titulo;
    setInput((prev) => {
      const trimmedStart = prev.trimStart();
      if (trimmedStart.toLowerCase().startsWith(gatilhoPrincipal.toLowerCase())) return prev;
      return prev.trim().length > 0 ? `${gatilhoPrincipal} ${prev}` : `${gatilhoPrincipal} `;
    });
    setShowTools(false);
    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const attachFiles = (files: File | File[] | null) => {
    if (!files) return;
    const fileList = Array.isArray(files) ? files : [files];
    const validFiles: File[] = [];

    for (const file of fileList) {
      if (!isCopilotoFileSupported(file)) {
        setFooterError(`Formato de "${file.name}" ainda não suportado no copiloto. Use ${COPILOTO_SUPPORTED_FORMATS_LABEL}.`);
        continue;
      }
      validFiles.push(file);
    }

    if (validFiles.length === 0) return;

    setFooterError(null);
    setAttachedFiles(prev => {
      const combined = [...prev, ...validFiles];
      if (combined.length > 10) {
        setFooterError(`Você pode anexar no máximo 10 documentos por mensagem. Mantive os 10 primeiros.`);
        return combined.slice(0, 10);
      }
      return combined;
    });
  };

  const attachFile = (file: File | null) => {
    attachFiles(file);
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files ? Array.from(event.target.files) : [];
    attachFiles(files);
    event.target.value = '';
  };

  const handleRemoveFile = (indexToRemove?: number) => {
    if (typeof indexToRemove === 'number') {
      setAttachedFiles(prev => prev.filter((_, i) => i !== indexToRemove));
    } else {
      setAttachedFiles([]);
      setPastedContext(null);
    }
  };

  const handlePaste = async (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.files);
    if (files.length > 0) {
      const audioFile = files.find((file) => file.type.startsWith('audio/'));
      if (audioFile) {
        event.preventDefault();
        transcribeAudioFile(audioFile);
        return;
      }
      const supportedFiles = files.filter((file) => isCopilotoFileSupported(file));
      if (supportedFiles.length > 0) {
        event.preventDefault();
        attachFiles(supportedFiles);
        return;
      }
    }
    const pastedText = event.clipboardData.getData('text');
    if (pastedText.length > LARGE_PASTE_THRESHOLD) {
      event.preventDefault();
      const dateStr = new Date().toISOString().slice(0, 10);
      setPastedContext({ text: pastedText, name: `contexto-${dateStr}.txt` });
    }
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    if (!Array.from(event.dataTransfer.types).includes('Files') || isBlocked) return;
    event.preventDefault();
    event.stopPropagation();
    dragCounterRef.current = 0;
    setIsDragActive(false);
    const droppedFiles = Array.from(event.dataTransfer.files || []);
    if (droppedFiles.length > 1) {
      setFooterError(`O copiloto aceita um arquivo por vez. Mantive apenas "${droppedFiles[0].name}".`);
    }
    attachFile(droppedFiles[0] ?? null);
  };

  const transcribeBlob = async (blob: Blob, extension = '.m4a') => {
    setIsProcessingMic(true);
    setFooterError(null);
    try {
      const data = await transcribeAudioViaStorage(blob, extension);
      if (data.refined) setInput((prev) => prev + (prev ? '\n' : '') + data.refined);
    } catch (err: any) {
      setFooterError('Erro ao transcrever áudio: ' + (err?.message || 'Tente novamente.'));
    } finally {
      setIsProcessingMic(false);
      setIsTranscribing(false);
    }
  };

  const transcribeAudioFile = (file: File) => {
    setIsTranscribing(true);
    const nameParts = file.name.split('.');
    const extension = nameParts.length > 1 ? `.${nameParts.pop()}` : `.${file.type.split('/')[1]?.split(';')[0] || 'm4a'}`;
    transcribeBlob(file, extension);
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
      setFooterError('Erro ao acessar microfone. Verifique as permissões.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const sendMessage = async (text: string) => {
    const hasFiles = attachedFiles.length > 0;
    const hasPaste = !!pastedContext;
    if (!text.trim() && !hasFiles && !hasPaste) return;

    setIsLoading(true);
    setFooterError(null);
    const filesToSend = [...attachedFiles];
    const pasteToSend = pastedContext;

    const filesHeader = filesToSend.length === 1
      ? `Arquivo anexado: ${filesToSend[0].name}`
      : filesToSend.length > 1
      ? `Arquivos anexados (${filesToSend.length}): ${filesToSend.map(f => f.name).join(', ')}`
      : '';

    const userMessageContent = hasFiles
      ? `${filesHeader}${text.trim() ? `\n\n${text.trim()}` : ''}`
      : hasPaste && pasteToSend
        ? `Contexto anexado: ${pasteToSend.name}${text.trim() ? `\n\n${text.trim()}` : ''}`
        : text.trim();

    setInput('');
    setAttachedFiles([]);
    setPastedContext(null);
    setShowTools(false);

    let sessionId = currentSessionId;
    try {
      if (!sessionId) sessionId = await createSession(text.trim() || filesToSend[0]?.name || pasteToSend?.name || 'Nova conversa');

      const driveFiles: Array<{ driveFileId: string; driveFileName: string }> = [];

      if (filesToSend.length > 0) {
        setUploadPhase('uploading');
        const idToken = await auth.currentUser?.getIdToken();
        if (!idToken) throw new Error('Usuário não autenticado.');

        const uploadResults = await Promise.all(
          filesToSend.map(async (file) => {
            const formData = new FormData();
            formData.append('file', file, file.name);
            const uploadRes = await fetch(UPLOAD_ENDPOINT, {
              method: 'POST',
              headers: { Authorization: `Bearer ${idToken}` },
              body: formData,
            });
            if (!uploadRes.ok) {
              const errBody = await uploadRes.json().catch(() => ({}));
              throw new Error(errBody.error || `Erro no upload de "${file.name}": HTTP ${uploadRes.status}`);
            }
            const uploadData = await uploadRes.json();
            return {
              driveFileId: uploadData.driveFileId as string,
              driveFileName: (uploadData.fileName || file.name) as string,
            };
          })
        );

        driveFiles.push(...uploadResults);
        setUploadPhase('processing');
      }

      await addDoc(collection(db, 'sessoes_copiloto', sessionId, 'mensagens'), {
        role: 'user',
        content: userMessageContent,
        timestamp: Timestamp.now(),
      });

      const sessionUpdates: Partial<Session> = {
        copilotMode,
        copilotScope: 'global',
        taskId: null,
        systemId: null,
        lastMessageAt: Timestamp.now(),
      };
      if (messages.length === 0) {
        sessionUpdates.title = `${userMessageContent.slice(0, 46)}${userMessageContent.length > 46 ? '...' : ''}`;
      }
      sessionUpdates.copilotStatus = 'Solicitação enfileirada...';
      await touchSession(sessionId, sessionUpdates);

      const pastePrefix = pasteToSend ? `[CONTEXTO COLADO]\n${pasteToSend.text}\n[/CONTEXTO]\n\n` : '';
      await addDoc(collection(db, 'copilot_jobs'), {
        userId,
        sessionId,
        status: 'queued',
        source: 'HermesGlobalChat',
        createdAt: Timestamp.now(),
        updatedAt: Timestamp.now(),
        payload: {
          sessionId,
          prompt: pastePrefix + (text.trim() || (hasFiles || hasPaste ? '' : text)),
          taskId: null,
          systemId: null,
          driveFiles,
          driveFileId: driveFiles[0]?.driveFileId || null,
          driveFileName: driveFiles[0]?.driveFileName || null,
          copilotMode,
          copilotScope: 'global',
          strategyDirectives,
          routingIndex: getRoutingIndex(),
        },
      });
    } catch (err: any) {
      const errMsg = getCopilotoErrorMessage(err);
      setFooterError(errMsg);
      const targetSessionId = sessionId || currentSessionId;
      if (targetSessionId) {
        await updateDoc(doc(db, 'sessoes_copiloto', targetSessionId), {
          copilotStatus: deleteField(),
          copilotStatusAt: deleteField(),
        }).catch(() => undefined);
        await addDoc(collection(db, 'sessoes_copiloto', targetSessionId, 'mensagens'), {
          role: 'assistant',
          content: `**Erro ao processar a solicitação:**\n\`${errMsg}\``,
          timestamp: Timestamp.now(),
        }).catch(() => undefined);
      }
    } finally {
      setUploadPhase('idle');
      setIsLoading(false);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (deletingSessionId) return;
    if (sessionPendingDeleteId !== sessionId) {
      setSessionPendingDeleteId(sessionId);
      return;
    }
    setDeletingSessionId(sessionId);
    setSessionPendingDeleteId(null);
    try {
      const messagesRef = collection(db, 'sessoes_copiloto', sessionId, 'mensagens');
      const messagesSnapshot = await getDocs(messagesRef);
      const batch = writeBatch(db);
      messagesSnapshot.docs.forEach((messageDoc) => batch.delete(messageDoc.ref));
      if (!messagesSnapshot.empty) await batch.commit();
      await deleteDoc(doc(db, 'sessoes_copiloto', sessionId));
      if (currentSessionId === sessionId) {
        const nextSession = sessions.find((session) => session.id !== sessionId);
        setCurrentSessionId(nextSession?.id ?? null);
      }
    } catch (err: any) {
      setFooterError(err?.message || 'Erro ao excluir conversa.');
    } finally {
      setDeletingSessionId(null);
    }
  };

  const handleConfirmEdit = async (messageId: string, pendingEdit: PendingEdit) => {
    if (!currentSessionId || loadingEditId) return;
    setLoadingEditId(messageId);
    try {
      const alteracoes = Object.fromEntries(
        Object.entries(pendingEdit.alteracoes).map(([campo, change]) => [
          campo,
          change.novo_raw !== undefined ? change.novo_raw : change.novo,
        ]),
      );
      const fn = httpsCallable(functions, 'confirmarEdicaoAcao');
      await fn({
        sessionId: currentSessionId,
        messageId,
        taskId: pendingEdit.task_id,
        alteracoes,
        snapshotTs: pendingEdit.snapshot_ts,
      });
    } catch (err: any) {
      setFooterError(err?.message || 'Erro ao confirmar edição.');
    } finally {
      setLoadingEditId(null);
    }
  };

  const handleCancelEdit = async (messageId: string) => {
    if (!currentSessionId || loadingEditId) return;
    setLoadingEditId(messageId);
    try {
      const msgRef = doc(db, 'sessoes_copiloto', currentSessionId, 'mensagens', messageId);
      await updateDoc(msgRef, { 'pendingEdit.status': 'cancelled' });
    } catch (err: any) {
      setFooterError(err?.message || 'Erro ao cancelar edição.');
    } finally {
      setLoadingEditId(null);
    }
  };

  const handleCopyMessage = async (key: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content || '');
      setCopiedMessageKey(key);
      setTimeout(() => setCopiedMessageKey(null), 1400);
    } catch {
      setFooterError('Não foi possível copiar a mensagem.');
    }
  };

  const filteredSessions = sessions.filter((session) => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return true;
    return String(session.title || '').toLowerCase().includes(term);
  });

  const renderMarkdown = (msg: Message, messageKey: string) => (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      urlTransform={(url) => url}
      components={{
        p: ({ node, ...props }) => <p className="mb-3 last:mb-0 leading-7" {...props} />,
        ul: ({ node, ...props }) => <ul className="mb-3 ml-5 list-disc space-y-1" {...props} />,
        ol: ({ node, ...props }) => <ol className="mb-3 ml-5 list-decimal space-y-1" {...props} />,
        li: ({ node, ...props }) => <li className="leading-7" {...props} />,
        strong: ({ node, ...props }) => <strong className={isDark ? 'font-black text-slate-100' : 'font-black text-slate-900'} {...props} />,
        pre: ({ node, children, ...props }) => (
          <pre className={`my-3 max-w-full overflow-x-auto whitespace-pre-wrap border p-4 font-mono text-xs ${isDark ? 'border-white/10 bg-black/20' : 'border-border-grid bg-slate-50'}`} {...props}>
            {children}
          </pre>
        ),
        code: ({ node, className, children, ...props }) => {
          if (className === 'language-mermaid') return <MermaidBlock code={String(children).trim()} isDark={isDark} />;
          return <code className={`${className || ''} font-mono text-[0.92em]`} {...props}>{children}</code>;
        },
        a: ({ node, ...props }) => {
          const href = props.href || '';
          if (isInternalAppHref(href)) {
            return (
              <a
                {...props}
                href={href}
                className={isDark ? 'text-blue-300 underline' : 'text-blue-700 underline'}
                onClick={(event) => {
                  event.preventDefault();
                  navigateWithinApp(href);
                  onClose();
                }}
              />
            );
          }
          if (href.includes('task:')) {
            const id = href.split('task:')[1];
            return (
              <button
                type="button"
                onClick={() => {
                  onOpenTask?.(id);
                  onClose();
                }}
                className="mx-1 inline-flex items-center border border-border-grid px-2 py-1 font-mono text-[10px] font-black uppercase tracking-widest text-blue-600"
              >
                {props.children}
              </button>
            );
          }
          if (href.includes('tool:diagnosis:')) {
            const id = href.split('tool:diagnosis:')[1];
            return <button type="button" onClick={() => onOpenTool?.('diagnostico', id)} className="mx-1 inline-flex border border-border-grid px-2 py-1 font-mono text-[10px] font-black uppercase tracking-widest text-blue-600">{props.children}</button>;
          }
          return <a {...props} target="_blank" rel="noopener noreferrer" className={isDark ? 'text-blue-300 underline' : 'text-blue-700 underline'} />;
        },
      }}
    >
      {msg.content}
    </ReactMarkdown>
  );

  if (!isOpen) return null;

  if (isMinimized) {
    const lastMessage = messages[messages.length - 1];
    const isVoiceLive = voiceStream.status === 'live' || voiceStream.status === 'connecting';
    const subtitle = isVoiceLive
      ? (voiceStream.status === 'live' ? '🔊 Conversa por voz ao vivo' : '🔊 Conectando à voz…')
      : isWaitingForCopilot
        ? 'Pensando…'
        : lastMessage?.content
          ? lastMessage.content.slice(0, 60)
          : 'Conversa em segundo plano';

    return (
      <button
        type="button"
        onClick={() => setIsMinimized(false)}
        className={`fixed bottom-5 right-5 z-[700] flex max-w-[280px] items-center gap-3 border px-4 py-3 text-left shadow-2xl transition-all hover:-translate-y-0.5 rounded-full ${
          isDark ? 'border-white/10 bg-[#191c1c] text-slate-100' : 'border-[#e5e7eb] bg-white text-slate-900'
        }`}
        aria-label="Reabrir conversa com o Hermes"
        title="Reabrir conversa"
      >
        <span className={`relative flex h-9 w-9 shrink-0 items-center justify-center border p-1.5 rounded-full ${isDark ? 'border-white/10 bg-white' : 'border-[#e5e7eb] bg-white'}`}>
          <img src="/logo.png" alt="Hermes" className="h-full w-full object-contain" />
          {isVoiceLive && (
            <span className="absolute -right-0.5 -top-0.5 h-3 w-3 animate-pulse rounded-full border-2 border-white bg-emerald-500" />
          )}
        </span>
        <span className="min-w-0">
          <span className="block truncate font-sans text-[10px] font-bold uppercase tracking-wider">Hermes</span>
          <span className={`block truncate font-sans text-[10px] font-medium ${mutedClass}`}>{subtitle}</span>
        </span>
      </button>
    );
  }

  const isInline = layout === 'inline';

  return (
    <div
      className={isInline ? 'absolute inset-y-0 right-0 flex min-h-0 justify-end transition-[width] duration-300' : 'fixed inset-0 z-[700] flex justify-end'}
      style={isInline ? { width: showHistory ? 'min(760px, calc(100vw - 2rem))' : '100%' } : undefined}
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
      {!isInline && <div className="absolute inset-0 bg-slate-950/50" onClick={onClose} aria-hidden="true" />}
      <div className={`relative flex h-full w-full ${isInline ? 'max-w-none rounded-2xl border shadow-sm' : `${showHistory ? 'max-w-[920px]' : 'max-w-[640px]'} shadow-2xl animate-in slide-in-from-right`} duration-300 ${shellClass}`}>
      {isDragActive && (
        <div className={`pointer-events-none absolute inset-0 z-[900] flex items-center justify-center border-4 ${isDark ? 'border-blue-400 bg-blue-500/10' : 'border-blue-500 bg-blue-50/80'}`}>
          <div className={`border px-8 py-6 text-center ${raisedClass}`}>
            <p className="font-mono text-[10px] font-black uppercase tracking-[0.25em] text-blue-500">Solte para anexar</p>
            <p className={`mt-2 text-xs font-bold ${textSoftClass}`}>O arquivo será enviado como contexto desta conversa.</p>
          </div>
        </div>
      )}

      <aside className={`${showMobileHistory ? 'fixed inset-0 z-[820] flex' : showHistory ? 'hidden md:flex' : 'hidden'} md:relative md:z-auto md:w-[300px] lg:w-[340px] shrink-0 flex-col border-r ${sidebarClass}`}>
        <div className={`flex h-16 shrink-0 items-center justify-between border-b px-4 ${isDark ? 'border-white/10' : 'border-[#e5e7eb]'}`}>
          <div className="flex min-w-0 items-center gap-3">
            <div className={`flex h-9 w-9 items-center justify-center border p-1.5 rounded-lg ${isDark ? 'border-white/10 bg-white' : 'border-[#e5e7eb] bg-surface'}`}>
              <img src="/logo.png" alt="Hermes" className="h-full w-full object-contain" />
            </div>
            <div className="min-w-0">
              <p className={`truncate font-sans text-xs font-bold uppercase tracking-wider ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Hermes</p>
              <p className={`truncate font-sans text-[9px] font-semibold uppercase tracking-wider ${mutedClass}`}>Histórico global</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setShowMobileHistory(false);
              setShowHistory(false);
            }}
            className={`shrink-0 p-2 ${hoverClass}`}
            aria-label="Fechar histórico"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="space-y-3 p-4">
          <button
            type="button"
            onClick={startNewConversation}
            className={`flex w-full items-center justify-center gap-2 px-4 py-3 font-sans text-[10px] font-bold uppercase tracking-wider transition-all rounded-lg ${
              isDark
                ? 'border border-white/10 bg-white text-slate-950 hover:bg-slate-200'
                : 'bg-[#7800ce] hover:bg-[#9333ea] text-white border-none'
            }`}
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
            Nova conversa
          </button>
          <div className={`flex items-center border px-3 py-2 ${raisedClass}`}>
            <svg className={`h-4 w-4 shrink-0 ${mutedClass}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Buscar conversas"
              className={`min-w-0 flex-1 bg-transparent px-2 py-1 font-sans text-[11px] font-medium outline-none ${isDark ? 'placeholder:text-slate-600' : 'placeholder:text-slate-400'}`}
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
          {filteredSessions.length === 0 ? (
            <div className={`border p-4 text-center font-sans text-[10px] font-bold uppercase tracking-wider ${raisedClass} ${mutedClass}`}>
              Sem conversas
            </div>
          ) : (
            <div className="space-y-1">
              {filteredSessions.map((session) => {
                const isActive = currentSessionId === session.id;
                return (
                  <div key={session.id} className="group flex items-stretch gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        setIsComposingNewSession(false);
                        setCurrentSessionId(session.id);
                        setShowMobileHistory(false);
                      }}
                      className={`min-w-0 flex-1 border px-3 py-3 text-left transition-all rounded-lg ${
                        isActive
                          ? (isDark ? 'border-transparent bg-[#ddb8ff]/10 text-white font-semibold' : 'border-transparent bg-[#f3e8ff] text-[#7800ce] font-semibold')
                          : `border-transparent hover:border-[#e5e7eb] dark:hover:border-white/10 ${hoverClass}`
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className={`truncate text-xs font-semibold ${isActive ? 'text-[#7800ce]' : 'text-slate-800 dark:text-slate-200'}`}>{session.title || 'Nova conversa'}</p>
                        <span className={`shrink-0 font-sans text-[8px] font-bold uppercase ${mutedClass}`}>{formatSessionTime(session.lastMessageAt)}</span>
                      </div>
                      <p className={`mt-1 font-sans text-[8px] font-bold uppercase tracking-wider ${mutedClass}`}>{session.copilotMode === 'finance' ? 'Financeiro' : session.copilotMode === 'saude' ? 'Saúde' : session.copilotMode === 'estrategia' ? 'Estratégia' : 'Global'}</p>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteSession(session.id)}
                      className={`w-9 shrink-0 border text-[10px] opacity-0 transition-all group-hover:opacity-100 rounded-lg ${
                        sessionPendingDeleteId === session.id
                          ? 'border-rose-500 bg-rose-600 text-white opacity-100'
                          : `border-[#e5e7eb] dark:border-white/10 text-slate-350 hover:text-rose-600 dark:hover:text-rose-300 ${hoverClass}`
                      }`}
                      title={sessionPendingDeleteId === session.id ? 'Confirmar exclusão' : 'Excluir conversa'}
                    >
                      <svg className="mx-auto h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M4 7h16" /></svg>
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </aside>

      <main className={`flex min-w-[min(420px,100%)] flex-1 flex-col border-l-0 ${panelClass}`}>
        <header className={`flex h-16 shrink-0 items-center justify-between border-b px-4 md:px-6 ${isDark ? 'border-white/10' : 'border-[#e5e7eb]'}`}>
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => {
                if (window.innerWidth < 768) {
                  setShowMobileHistory(true);
                  return;
                }
                setShowHistory(prev => !prev);
              }}
              className={`relative z-10 shrink-0 border px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider transition-all rounded-lg ${
                showHistory
                  ? (isDark ? 'border-blue-400/40 bg-blue-500/10 text-blue-200' : 'border-[#7800ce] bg-[#f5f3ff] text-[#7800ce]')
                  : (isDark ? 'border-white/10 text-slate-400 hover:bg-white/5 hover:text-white' : 'border-[#e5e7eb] text-slate-500 hover:bg-slate-50 hover:text-slate-900')
              }`}
              aria-label={showHistory || showMobileHistory ? 'Fechar histórico' : 'Abrir histórico'}
              aria-pressed={showHistory}
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
            </button>
            <div className={`hidden h-9 w-9 items-center justify-center border p-1.5 md:flex rounded-lg ${isDark ? 'border-white/10 bg-white' : 'border-[#e5e7eb] bg-white'}`}>
              <img src="/logo.png" alt="Hermes" className="h-full w-full object-contain" />
            </div>
            <div className="min-w-0">
              <h2 className={`truncate font-sans text-sm font-bold uppercase tracking-wider ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Copiloto Hermes</h2>
              <p className={`truncate font-sans text-[9px] font-semibold uppercase tracking-wider ${mutedClass}`}>Chat {modeLabel} · {currentSessionId ? 'conversa ativa' : 'nova conversa'}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={startNewConversation}
              className={`${showHistory ? 'hidden lg:inline-flex' : 'hidden sm:inline-flex'} border px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider transition-all rounded-lg ${
                isDark ? 'border-white/10 text-slate-300 hover:bg-white/5 hover:text-white' : 'border-[#e5e7eb] text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              Nova conversa
            </button>
            <button
              type="button"
              onClick={() => setIsMinimized(true)}
              className={`border p-2 font-sans text-[10px] font-semibold uppercase tracking-wider transition-all rounded-lg ${
                isDark ? 'border-white/10 text-slate-400 hover:bg-white/5 hover:text-white' : 'border-[#e5e7eb] text-slate-500 hover:bg-slate-50 hover:text-slate-900'
              }`}
              aria-label="Minimizar conversa"
              title="Minimizar (continua ativa em segundo plano)"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 12h14" /></svg>
            </button>
            <button
              type="button"
              onClick={onClose}
              className={`border px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider transition-all rounded-lg ${
                isDark ? 'border-white/10 text-slate-400 hover:bg-white/5 hover:text-white' : 'border-[#e5e7eb] text-slate-500 hover:bg-slate-50 hover:text-[#ba1a1a]'
              }`}
            >
              Fechar
            </button>
          </div>
        </header>

        <div className={`min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-8 ${isDark ? 'bg-[#191c1c]' : 'bg-white'}`}>
          <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col">
            {messages.length === 0 && !isLoading ? (
              <div className="flex flex-1 flex-col justify-center py-10">
                <div className="mb-8 flex items-center gap-4">
                  <div className={`flex h-14 w-14 items-center justify-center border p-2.5 rounded-xl ${isDark ? 'bg-white border-white/10' : 'bg-white border-[#e5e7eb] shadow-sm'}`}>
                    <img src="/logo.png" alt="Hermes" className="h-full w-full object-contain" />
                  </div>
                  <div>
                    <p className={`font-sans text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>{copilotMode === 'estrategia' ? 'Copiloto de estratégia' : 'Copiloto global'}</p>
                    <h3 className={`mt-1 text-2xl font-bold tracking-tight ${isDark ? 'text-white' : 'text-slate-900'}`}>Como posso ajudar?</h3>
                  </div>
                </div>
                <p className={`max-w-xl text-sm font-medium leading-relaxed ${textSoftClass}`}>{copilotMode === 'estrategia' ? 'Foco nos seus objetivos, pilares, diretrizes, indicadores e marcos. Posso analisar coerência de longo prazo e criar, alterar ou excluir itens da sua estratégia.' : 'Pronto para conversar.'}</p>
              </div>
            ) : (
              <div className="space-y-8">
                {messages.map((msg, index) => {
                  const messageKey = msg.id || `${msg.role}-${index}`;
                  const isUser = msg.role === 'user';
                  return (
                    <div key={messageKey} className={`group flex gap-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
                      {!isUser && (
                        <div className={`mt-1 hidden h-8 w-8 shrink-0 items-center justify-center border p-1.5 md:flex rounded-lg ${isDark ? 'bg-white border-white/10' : 'bg-white border-[#e5e7eb] shadow-sm'}`}>
                          <img src="/logo.png" alt="" className="h-full w-full object-contain" />
                        </div>
                      )}
                      <article className={`min-w-0 max-w-[min(100%,48rem)] ${
                        isUser
                          ? 'rounded-2xl px-4 py-3 font-sans text-sm font-medium leading-relaxed'
                          : 'text-sm leading-relaxed font-sans'
                      } ${
                        isUser
                          ? (isDark
                              ? 'border border-[#ddb8ff]/20 bg-[#ddb8ff]/10 text-white'
                              : 'bg-[#7800ce] text-white border-none')
                          : ''
                      }`}>
                        <div className={`mb-2 flex items-center gap-2 font-sans text-[8px] font-bold uppercase tracking-wider ${isUser ? 'text-current opacity-60' : mutedClass}`}>
                          <span>{isUser ? 'Você' : 'Hermes'}</span>
                          <span>{formatMessageTime(msg.timestamp)}</span>
                          <button
                            type="button"
                            onClick={() => handleCopyMessage(messageKey, msg.content || '')}
                            className={`ml-auto opacity-0 transition-opacity group-hover:opacity-100 ${isUser ? 'text-current' : mutedClass}`}
                          >
                            {copiedMessageKey === messageKey ? 'Copiado' : 'Copiar'}
                          </button>
                        </div>
                        {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                          <ToolsUsedBadges tools={msg.toolsUsed} isDark={isDark} />
                        )}
                        <div className="break-words [overflow-wrap:anywhere]">
                          {renderMarkdown(msg, messageKey)}
                        </div>
                        {msg.pendingEdit && msg.id && (() => {
                          const pe = msg.pendingEdit!;
                          const mid = msg.id!;
                          const isProcessing = loadingEditId === mid;

                          if (pe.status === 'completed') {
                            return (
                              <div className={`mt-3 border p-3 ${isDark ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-border-grid bg-emerald-50'}`}>
                                <p className={`mb-2 flex items-center gap-1.5 font-mono text-[10px] font-black uppercase tracking-widest ${isDark ? 'text-emerald-300' : 'text-emerald-700'}`}>
                                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                  Edição confirmada
                                </p>
                                <p className={`truncate text-[10px] font-semibold ${isDark ? 'text-emerald-200' : 'text-emerald-700'}`}>{pe.titulo}</p>
                                <div className="mt-1.5 space-y-1">
                                  {Object.entries(pe.alteracoes).map(([campo, change]) => (
                                    <div key={campo} className={`flex flex-wrap gap-1 text-[9px] ${isDark ? 'text-emerald-300' : 'text-emerald-600'}`}>
                                      <span className="font-black">{FIELD_LABELS[campo] ?? campo}:</span>
                                      <span className="opacity-60 line-through">{change.original || '—'}</span>
                                      <span>→</span>
                                      <span className="font-semibold">{change.novo || '—'}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            );
                          }

                          if (pe.status === 'invalidated' || pe.status === 'error') {
                            return (
                              <div className={`mt-3 border p-3 ${isDark ? 'border-rose-500/40 bg-rose-500/10' : 'border-red-200 bg-red-50'}`}>
                                <p className={`mb-1 flex items-center gap-1.5 font-mono text-[10px] font-black uppercase tracking-widest ${isDark ? 'text-rose-300' : 'text-red-600'}`}>
                                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                                  {pe.status === 'error' ? 'Erro na edição' : 'Edição bloqueada'}
                                </p>
                                <p className={`text-[10px] ${isDark ? 'text-rose-300' : 'text-red-600'}`}>{pe.errorMessage ?? 'Operação indisponível.'}</p>
                              </div>
                            );
                          }

                          if (pe.status === 'cancelled') {
                            return (
                              <div className={`mt-3 border p-3 ${isDark ? 'border-white/10 bg-white/5' : 'border-border-grid bg-slate-50'}`}>
                                <p className={`flex items-center gap-1.5 font-mono text-[10px] font-black uppercase tracking-widest ${mutedClass}`}>
                                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                  Edição cancelada
                                </p>
                              </div>
                            );
                          }

                          return (
                            <div className={`mt-3 border p-3 ${raisedClass}`}>
                              <p className={`mb-2 flex items-center gap-1.5 font-mono text-[10px] font-black uppercase tracking-widest ${isDark ? 'text-amber-300' : 'text-amber-700'}`}>
                                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                Edição pendente
                              </p>
                              <p className={`mb-2 truncate text-[10px] font-semibold ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>{pe.titulo}</p>
                              <div className="mb-3 space-y-1.5">
                                {Object.entries(pe.alteracoes).map(([campo, change]) => (
                                  <div key={campo} className="grid grid-cols-[80px_1fr_1fr] gap-1 text-[9px]">
                                    <span className={`font-black uppercase ${mutedClass}`}>{FIELD_LABELS[campo] ?? campo}</span>
                                    <span className={`truncate line-through ${mutedClass}`}>{change.original || '—'}</span>
                                    <span className={`truncate font-semibold ${isDark ? 'text-emerald-300' : 'text-emerald-700'}`}>{change.novo || '—'}</span>
                                  </div>
                                ))}
                              </div>
                              <div className={`flex gap-2 border-t pt-2 ${isDark ? 'border-white/10' : 'border-amber-100'}`}>
                                <button
                                  type="button"
                                  onClick={() => handleConfirmEdit(mid, pe)}
                                  disabled={isProcessing}
                                  className="inline-flex items-center gap-1.5 bg-emerald-600 px-3 py-1.5 font-mono text-[10px] font-black uppercase tracking-widest text-white shadow-sm transition-all hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {isProcessing ? (
                                    <span className="h-2.5 w-2.5 animate-spin border-2 border-white/40 border-t-white" />
                                  ) : (
                                    <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                  )}
                                  Confirmar
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleCancelEdit(mid)}
                                  disabled={isProcessing}
                                  className={`inline-flex items-center gap-1.5 border px-3 py-1.5 font-mono text-[10px] font-black uppercase tracking-widest shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-50 ${isDark ? 'border-white/10 bg-transparent text-slate-400 hover:bg-white/5 hover:text-slate-200' : 'border-border-grid bg-white text-slate-400 hover:bg-slate-100 hover:text-slate-600'}`}
                                >
                                  <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                  Cancelar
                                </button>
                              </div>
                            </div>
                          );
                        })()}
                      </article>
                    </div>
                  );
                })}
                {isWaitingForCopilot && (
                  <div className="flex items-center gap-3">
                    <div className={`h-8 w-8 border p-1.5 ${isDark ? 'bg-white border-white/10' : 'bg-white border-border-grid shadow-soft-touch'}`}>
                      <img src="/logo.png" alt="" className="h-full w-full object-contain" />
                    </div>
                    <div className={`border px-4 py-3 font-mono text-[10px] font-black uppercase tracking-widest ${raisedClass} ${mutedClass}`}>
                      {uploadPhase === 'uploading' ? 'Enviando arquivo...' : uploadPhase === 'processing' ? 'Processando contexto...' : (activeCopilotStatus || 'Pensando...')}
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}
          </div>
        </div>

        <footer className={`shrink-0 border-t px-4 py-4 md:px-8 ${isDark ? 'border-white/10 bg-[#151c27]' : 'border-[#e5e7eb] bg-white'}`}>
          <div className="mx-auto w-full max-w-4xl">
            {footerError && (
              <div className="mb-3 flex items-start gap-2 border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-bold text-rose-700 rounded-lg">
                <span className="flex-1">{footerError}</span>
                <button type="button" onClick={() => setFooterError(null)} className="font-sans text-[9px] font-bold uppercase">Fechar</button>
              </div>
            )}
            {(attachedFiles.length > 0 || pastedContext || isTranscribing || isProcessingMic) && (
              <div className="mb-3 flex flex-wrap items-center gap-1.5 max-h-32 overflow-y-auto">
                {attachedFiles.map((file, idx) => (
                  <div key={`${file.name}-${idx}`} className={`flex items-center gap-1.5 border px-2.5 py-1 font-sans text-[10px] font-bold ${raisedClass}`}>
                    <span className={mutedClass}>Anexo {idx + 1}</span>
                    <span className="max-w-[150px] truncate" title={file.name}>{file.name}</span>
                    <button type="button" onClick={() => handleRemoveFile(idx)} className="font-bold uppercase tracking-wider text-rose-500 hover:text-rose-600 ml-1">×</button>
                  </div>
                ))}
                {pastedContext && (
                  <div className={`flex items-center gap-1.5 border px-2.5 py-1 font-sans text-[10px] font-bold ${raisedClass}`}>
                    <span className={mutedClass}>Contexto</span>
                    <span className="max-w-[150px] truncate" title={pastedContext.name}>{pastedContext.name}</span>
                    <button type="button" onClick={() => setPastedContext(null)} className="font-bold uppercase tracking-wider text-rose-500 hover:text-rose-600 ml-1">×</button>
                  </div>
                )}
                {(isTranscribing || isProcessingMic) && (
                  <div className={`flex items-center gap-1.5 border px-2.5 py-1 font-sans text-[10px] font-bold ${raisedClass}`}>
                    <span className={mutedClass}>Microfone</span>
                    <span>Transcrevendo áudio...</span>
                  </div>
                )}
              </div>
            )}
            <div className={`relative flex items-end gap-1 border px-2 py-2 ${raisedClass}`}>
              <input ref={fileInputRef} type="file" multiple accept={COPILOTO_FILE_ACCEPT} className="hidden" onChange={handleFileSelect} />
              <button type="button" disabled={isBlocked || attachedFiles.length >= 10} onClick={() => fileInputRef.current?.click()} title={attachedFiles.length >= 10 ? "Limite máximo de 10 arquivos atingido" : "Anexar arquivo(s)"} className={`flex h-10 w-10 shrink-0 items-center justify-center transition-all ${hoverClass} disabled:opacity-30`}>
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v14m-7-7h14" /></svg>
              </button>
              <div className="relative shrink-0" ref={toolMenuRef}>
                <button type="button" disabled={isBlocked} onClick={() => setShowTools((prev) => !prev)} title="POPs Cadastrados" className={`flex h-10 w-10 items-center justify-center transition-all ${showTools ? (isDark ? 'bg-white/10' : 'bg-slate-100') : hoverClass} disabled:opacity-30`}>
                  <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><circle cx="5" cy="5" r="1.8" /><circle cx="12" cy="5" r="1.8" /><circle cx="19" cy="5" r="1.8" /><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /><circle cx="5" cy="19" r="1.8" /><circle cx="12" cy="19" r="1.8" /><circle cx="19" cy="19" r="1.8" /></svg>
                </button>
                {showTools && (
                  <div className={`absolute bottom-full left-0 z-[850] mb-3 max-h-[360px] w-[min(24rem,calc(100vw-2rem))] overflow-y-auto border shadow-2xl ${raisedClass}`}>
                    <div className={`sticky top-0 border-b px-3 py-2 font-sans text-[10px] font-bold uppercase tracking-wider ${isDark ? 'border-white/10 bg-slate-900 text-slate-500' : 'border-[#e5e7eb] bg-white text-slate-400'}`}>POPs Cadastrados</div>
                    <div className="p-2">
                      {popsList.length === 0 ? (
                        <div className={`px-3 py-4 text-center text-xs font-medium ${mutedClass}`}>Nenhum POP cadastrado</div>
                      ) : (
                        popsList.map((pop) => {
                          const gatilho = pop.gatilhos && pop.gatilhos.length > 0 ? pop.gatilhos[0] : pop.titulo;
                          return (
                            <button key={pop.id} type="button" onClick={() => insertPopShortcut(pop)} className={`w-full px-3 py-2.5 text-left transition-all ${hoverClass}`}>
                              <div className={`text-xs font-bold leading-normal ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{pop.titulo}</div>
                              <div className="mt-1.5 flex items-center">
                                <span className={`inline-block max-w-full truncate rounded px-1.5 py-0.5 font-mono text-[9px] font-bold ${isDark ? 'bg-blue-500/10 text-blue-400' : 'bg-blue-50 text-blue-600'}`}>{gatilho}</span>
                              </div>
                              {pop.gatilhos && pop.gatilhos.length > 1 && (
                                <p className={`mt-1 text-[10px] leading-relaxed truncate ${mutedClass}`}>
                                  Gatilhos: {pop.gatilhos.join(', ')}
                                </p>
                              )}
                            </button>
                          );
                        })
                      )}
                    </div>
                  </div>
                )}
              </div>
              <textarea
                ref={textareaRef}
                rows={1}
                value={input}
                onPaste={handlePaste}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey && window.innerWidth >= 640) {
                    event.preventDefault();
                    sendMessage(input);
                  }
                }}
                disabled={isBlocked}
                placeholder={voiceStream.status === 'live' ? `🔊 ${voiceStreamStatusMessage || 'Conversa ao vivo — pode falar'}` : voiceStream.status === 'connecting' ? '🔊 Conectando à voz ao vivo…' : isRecording ? 'Gravando... clique no microfone para parar' : isProcessingMic || isTranscribing ? 'Transcrevendo áudio...' : attachedFile || pastedContext ? 'Pergunte sobre o contexto anexado...' : copilotMode === 'estrategia' ? 'Converse sobre seus objetivos e diretrizes...' : 'Mensagem para o Hermes'}
                className={`min-h-10 flex-1 resize-none overflow-y-hidden bg-transparent px-2 py-2.5 text-sm font-medium leading-5 outline-none disabled:opacity-40 ${isDark ? 'text-slate-100 placeholder:text-slate-600' : 'text-slate-900 placeholder:text-slate-400'}`}
              />
              <button
                type="button"
                disabled={isRecording}
                onClick={async () => {
                  if (voiceStream.status === 'idle' || voiceStream.status === 'error') {
                    if (!currentSessionIdRef.current) {
                      await createSession();
                    }
                    voiceStream.start();
                  } else {
                    voiceStream.stop();
                  }
                }}
                title={voiceStream.status === 'live' ? 'Encerrar conversa por voz' : voiceStream.status === 'connecting' ? 'Conectando…' : 'Conversar por voz (tempo real)'}
                className={`flex h-10 w-10 shrink-0 items-center justify-center transition-all disabled:opacity-30 ${
                  voiceStream.status === 'live'
                    ? 'bg-emerald-600 text-white animate-pulse rounded-lg'
                    : voiceStream.status === 'connecting'
                      ? 'bg-amber-500 text-white rounded-lg'
                      : hoverClass
                }`}
              >
                {voiceStream.status === 'connecting' ? (
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" /></svg>
                ) : (
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4h16v11H7.17L4 18.17V4Zm2 2v8.17L6.17 13H18V6H6Z" /></svg>
                )}
              </button>
              <button type="button" disabled={isBlocked && !isRecording} onClick={() => isRecording ? stopRecording() : startRecording()} title={isRecording ? 'Parar gravação' : 'Gravar áudio'} className={`flex h-10 w-10 shrink-0 items-center justify-center transition-all disabled:opacity-30 ${isRecording ? 'bg-rose-600 text-white animate-pulse rounded-lg' : hoverClass}`}>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 10v2a7 7 0 01-14 0v-2m14 0h2m-16 0H3m9 10v3m-3 0h6" /></svg>
              </button>
              {(input.trim() || attachedFile || pastedContext) && !isRecording && (
                <button type="button" disabled={isBlocked} onClick={() => sendMessage(input)} title="Enviar" className="flex h-10 w-10 shrink-0 items-center justify-center bg-[#7800ce] text-white transition-all hover:bg-[#9333ea] rounded-lg disabled:opacity-30">
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                </button>
              )}
            </div>
          </div>
        </footer>
      </main>
      </div>
    </div>
  );
};
