import React, { useState, useEffect, useMemo, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Tarefa, AppSettings, PoolItem, ConhecimentoItem, Acompanhamento, ActionPlanItem,
  ChatMessage, BaseConhecimento, formatDate, formatDateLocalISO, TaskReminder
} from '../../types';
import { normalizeStatus } from '../utils/helpers';
import { buildDiaryRichNote, ensureHttpUrl, getRenamedFileName, parseDiaryRichNote } from '../utils/diaryEntries';
import { isOperationalArea, STRATEGIC_AREA_OPTIONS } from '../utils/strategicAreas';
import { buildRecordedAudioBlob, transcribeAudioViaStorage } from '../utils/audioTranscription';
import { NotificationCenter } from '../components/ui/UIComponents';
import { db, functions } from '../../firebase';
import { httpsCallable } from 'firebase/functions';
import { setDoc, doc, addDoc, collection, serverTimestamp, query, where, orderBy, limit, getDocs } from 'firebase/firestore';
import { DiarioBordoUI } from './DiarioBordoUI';
import { SpeedDialMenu } from '../components/ui/SpeedDialMenu';
import { HermesCopilotoDrawer } from '../components/tools/HermesCopilotoDrawer';

const DocumentViewer = ({ file, onClose, isDark }: {
  file: { url: string; nome: string; tipo: 'link' | 'file' | 'image'; driveFileId?: string };
  onClose: () => void;
  isDark: boolean;
}) => {
  const isGoogleDrive = file.url.includes('drive.google.com') || file.url.includes('docs.google.com');

  let finalUrl = file.url;
  let canEmbed = !isGoogleDrive;
  let imageUrl = file.url;

  if (isGoogleDrive) {
    const fileId = file.driveFileId || file.url.match(/\/d\/([a-zA-Z0-9_-]+)/)?.[1] || file.url.match(/[?&]id=([a-zA-Z0-9_-]+)/)?.[1];
    if (fileId) {
      finalUrl = `https://drive.google.com/file/d/${fileId}/preview`;
      canEmbed = true;
      if (file.tipo === 'image') {
        imageUrl = `https://drive.google.com/thumbnail?id=${fileId}&sz=w1600`;
      }
    }
  }

  return (
    <div className={`flex flex-col flex-1 h-full overflow-hidden rounded-lg border ${isDark ? 'bg-[#050505] border-white/10' : 'bg-white border-[#e5e7eb] dark:border-white/10'}`}>
      <div className={`shrink-0 px-6 py-4 flex items-center justify-between border-b ${isDark ? 'border-white/10' : 'border-[#e5e7eb] dark:border-white/10'}`}>
        <div className="flex items-center gap-3">
          <button onClick={onClose} className={`p-2 rounded-lg transition-all ${isDark ? 'hover:bg-white/10 text-white/50' : 'hover:bg-slate-100 text-slate-400'}`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
          </button>
          <div>
            <h3 className={`text-sm font-black tracking-tight font-sans ${isDark ? 'text-white' : 'text-slate-900'}`}>{file.nome}</h3>
            <p className={`text-[10px] font-bold uppercase tracking-widest font-sans ${isDark ? 'text-white/40' : 'text-slate-400'}`}>Modo de Foco</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <a href={file.url} target="_blank" rel="noreferrer" className={`px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all font-sans ${isDark ? 'bg-white/5 text-white/70 hover:bg-white/10' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
            Abrir Original
          </a>
        </div>
      </div>
      <div className="flex-1 bg-black/5 relative">
        {file.tipo === 'image' ? (
          <div className="w-full h-full flex items-center justify-center p-8">
            <img src={imageUrl} alt={file.nome} className="max-w-full max-h-full object-contain rounded-lg shadow-lg transition-all hover:scale-[1.01]" />
          </div>
        ) : canEmbed ? (
          <iframe src={finalUrl} className="w-full h-full border-none" title={file.nome} />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-5 p-8 text-center">
            <div className={`w-16 h-16 rounded-lg flex items-center justify-center ${isDark ? 'bg-white/5' : 'bg-slate-100'}`}>
              <svg className={`w-8 h-8 ${isDark ? 'text-white/30' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <p className={`text-sm font-bold font-sans ${isDark ? 'text-white/70' : 'text-slate-700'}`}>Pré-visualização não disponível</p>
              <p className={`text-xs mt-1 font-sans ${isDark ? 'text-white/40' : 'text-slate-400'}`}>O arquivo não pode ser incorporado aqui</p>
            </div>
            <a href={file.url} target="_blank" rel="noreferrer" className={`px-5 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all font-sans ${isDark ? 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30' : 'bg-blue-50 text-blue-600 hover:bg-blue-100'}`}>
              Abrir no Google Drive
            </a>
          </div>
        )}
      </div>
    </div>
  );
};

type PendingUploadFile = {
  id: string;
  file: File;
  customName: string;
};

const createPendingUploadFile = (file: File): PendingUploadFile => ({
  id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 10)}`,
  file,
  customName: file.name,
});

interface Artifact {
  id: string;
  title: string;
  content: string;
  createdAt: string;
}

interface TaskExecutionViewProps {
  task: Tarefa;
  tarefas: Tarefa[];
  isDark?: boolean;
  appSettings: AppSettings;
  knowledgeBases?: BaseConhecimento[];
  onSave: (id: string, updates: Partial<Tarefa>) => void;
  unidades?: { id: string, nome: string }[];
  onClose: () => void;
  showToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
  notifications: any[];
  isSyncing: boolean;
  isNotificationCenterOpen: boolean;
  onOpenNotes: () => void;
  onOpenShopping: () => void;
  onOpenTranscription: () => void;
  onOpenMeetingTranscription: () => void;
  onToggleNotifications: () => void;
  onSync: () => void;
  onOpenSettings: () => void;
  onCloseNotifications: () => void;
  onMarkAsRead: (id: string) => void;
  onDismiss: (id: string) => void;
  onOpenCopiloto: () => void;
  copilotoUserId: string;
  onOpenCopilotoTask?: (taskId: string) => void;
  onOpenCopilotoTool?: (tool: string, id: string) => void;
  onCreateAction: () => void;
  onUICommand?: (command: string, params: any) => void;
}

type MobileTab = 'mapa' | 'diario' | 'copiloto';
type DesktopPanel = 'plan' | 'copilot';

const OPS_LAYOUT_KEY = 'hermes-ops-layout-v1';
const DESKTOP_BREAKPOINT = 1024;
const PANEL_COLLAPSED_WIDTH = 52;
const PLAN_PANEL_MIN_WIDTH = 280;
const COPILOT_PANEL_MIN_WIDTH = 320;
const DIARY_PANEL_MIN_WIDTH = 480;
const PLAN_PANEL_DEFAULT_WIDTH = 360;
const COPILOT_PANEL_DEFAULT_WIDTH = 440;

const sortTaskReminders = (reminders: TaskReminder[] = []) =>
  [...reminders].sort((a, b) => new Date(a.reminder_at).getTime() - new Date(b.reminder_at).getTime());

const getNextPendingReminder = (reminders: TaskReminder[] = []) =>
  sortTaskReminders(reminders).find(reminder => !reminder.reminder_sent);

const buildReminderPayload = (reminders: TaskReminder[]) => {
  const sortedReminders = sortTaskReminders(reminders);
  const nextReminder = getNextPendingReminder(sortedReminders);
  return {
    reminders: sortedReminders,
    reminder_at: nextReminder?.reminder_at || undefined,
    reminder_sent: nextReminder ? nextReminder.reminder_sent : true,
  };
};

export const TaskExecutionView = ({
  task,
  tarefas,
  isDark = false,
  appSettings,
  knowledgeBases = [],
  onSave,
  unidades = [],
  onClose,
  showToast,
  notifications,
  isSyncing,
  isNotificationCenterOpen,
  onOpenNotes,
  onOpenShopping,
  onOpenTranscription,
  onOpenMeetingTranscription,
  onToggleNotifications,
  onSync,
  onOpenSettings,
  onCloseNotifications,
  onMarkAsRead,
  onDismiss,
  onOpenCopiloto,
  copilotoUserId,
  onOpenCopilotoTask,
  onOpenCopilotoTool,
  onCreateAction,
  onUICommand,
}: TaskExecutionViewProps) => {

  // ─── Derived Data ─────────────────────────────────────────────
  const currentTaskData = useMemo(() => {
    const found = tarefas.find(t => t.id === task.id) || task;
    if (found.plano_acao) {
      const seenIds = new Set<string>();
      let hasDuplicates = false;
      const sanitized = found.plano_acao.map((item, idx) => {
        let newId = item.id;
        if (!newId || String(newId).includes('uuid') || seenIds.has(newId)) {
          newId = `plan-${Date.now()}-${idx}-${Math.random().toString(36).substring(2, 7)}`;
          hasDuplicates = true;
        }
        seenIds.add(newId);
        return { ...item, id: newId };
      });
      if (hasDuplicates) {
        return {
          ...found,
          plano_acao: sanitized
        };
      }
    }
    return found;
  }, [tarefas, task.id, task]);

  // ─── States ───────────────────────────────────────────────────
  const [mobileTab, setMobileTab] = useState<MobileTab>('diario');
  const [desktopViewportWidth, setDesktopViewportWidth] = useState(() => window.innerWidth);
  const isDesktopViewport = desktopViewportWidth >= 1024;
  const isCompactMobileViewport = desktopViewportWidth < 640;
  const [isMobileHeaderHidden, setIsMobileHeaderHidden] = useState(false);
  const [mobileHeaderHeight, setMobileHeaderHeight] = useState(0);
  const [planPanelWidth, setPlanPanelWidth] = useState(PLAN_PANEL_DEFAULT_WIDTH);
  const [copilotPanelWidth, setCopilotPanelWidth] = useState(COPILOT_PANEL_DEFAULT_WIDTH);
  const [isPlanCollapsed, setIsPlanCollapsed] = useState(false);
  const [isCopilotCollapsed, setIsCopilotCollapsed] = useState(false);
  const [focusedFile, setFocusedFile] = useState<{ url: string; nome: string; tipo: 'link' | 'file' | 'image'; driveFileId?: string } | null>(null);
  const [tempSessionId, setTempSessionId] = useState<string | null>(null);

  useEffect(() => {
    if (focusedFile && isDesktopViewport && !tempSessionId) {
      setIsCopilotCollapsed(false);

      const createTempSession = async () => {
        try {
          const documentId = focusedFile.driveFileId || focusedFile.nome;

          // Reuse existing focus session for this document if one exists
          const existingQ = query(
            collection(db, 'sessoes_copiloto'),
            where('taskId', '==', task.id),
            where('isTemporary', '==', true),
            where('documentId', '==', documentId),
            orderBy('createdAt', 'desc'),
            limit(1)
          );
          const existingSnap = await getDocs(existingQ);
          if (!existingSnap.empty) {
            setTempSessionId(existingSnap.docs[0].id);
            return;
          }

          const sessRef = await addDoc(collection(db, 'sessoes_copiloto'), {
            title: `[ANÁLISE] ${focusedFile.nome}`,
            userId: copilotoUserId,
            taskId: task.id,
            systemId: currentTaskData.sistema || null,
            isTemporary: true,
            documentId,
            createdAt: serverTimestamp(),
            lastMessageAt: serverTimestamp()
          });

          await addDoc(collection(db, 'sessoes_copiloto', sessRef.id, 'mensagens'), {
            role: 'assistant',
            content: `Foco total ativado para o documento: **${focusedFile.nome}**. Estou pronto para analisar o conteúdo e ajudar você com dúvidas técnicas, resumos ou extração de informações. Como posso ser útil?`,
            source: 'web_task_view',
            timestamp: serverTimestamp()
          });

          setTempSessionId(sessRef.id);
        } catch (err) {
          console.error("Erro ao criar sessão temporária:", err);
        }
      };
      createTempSession();
    }
  }, [focusedFile, isDesktopViewport, tempSessionId, copilotoUserId, task.id, currentTaskData.sistema]);
  const [localDataLimite, setLocalDataLimite] = useState(currentTaskData.data_limite || '');
  const [localPrazoFinal, setLocalPrazoFinal] = useState(currentTaskData.prazo_final || '');
  const [localHorarioInicio, setLocalHorarioInicio] = useState(currentTaskData.horario_inicio || '');
  const [localHorarioFim, setLocalHorarioFim] = useState(currentTaskData.horario_fim || '');

  const [localEmailLinkOptout, setLocalEmailLinkOptout] = useState(currentTaskData.email_link_optout || false);

  useEffect(() => {
    setLocalDataLimite(currentTaskData.data_limite || '');
    setLocalPrazoFinal(currentTaskData.prazo_final || '');
    setLocalHorarioInicio(currentTaskData.horario_inicio || '');
    setLocalHorarioFim(currentTaskData.horario_fim || '');
  }, [currentTaskData.data_limite, currentTaskData.prazo_final, currentTaskData.horario_inicio, currentTaskData.horario_fim]);

  useEffect(() => {
    setLocalEmailLinkOptout(currentTaskData.email_link_optout || false);
  }, [currentTaskData.email_link_optout]);

  const getTodayIso = () => {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const handleBlurDataLimite = () => {
    let finalDate = localDataLimite;
    const today = getTodayIso();
    if (finalDate && finalDate < today) {
      finalDate = today;
      setLocalDataLimite(finalDate);
      showToast("Data de execução ajustada para hoje (não é permitido agendar no passado)", "info");
    }
    onSave(task.id, {
      data_limite: finalDate,
      data_inicio: finalDate,
      horario_inicio: null as any,
      horario_fim: null as any
    });
  };

  const handleBlurPrazoFinal = () => {
    let finalDate = localPrazoFinal;
    const today = getTodayIso();
    if (finalDate && finalDate < today) {
      finalDate = today;
      setLocalPrazoFinal(finalDate);
      showToast("Prazo final ajustado para hoje (não é permitido agendar no passado)", "info");
    }
    onSave(task.id, { prazo_final: finalDate });
  };

  const handleToggleEmailLinkOptout = (optout: boolean) => {
    setLocalEmailLinkOptout(optout);
    onSave(task.id, { email_link_optout: optout });
  };

  const [newFollowUp, setNewFollowUp] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null!);

  // Chat & Artifacts
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(currentTaskData.chat_history || []);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [copiedArtifactId, setCopiedArtifactId] = useState<string | null>(null);
  const [isChatFocused, setIsChatFocused] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null!);

  useEffect(() => {
    setChatMessages(currentTaskData.chat_history || []);
  }, [currentTaskData.id]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const insightDiarioSignature = useMemo(
    () => JSON.stringify((currentTaskData.acompanhamento || []).slice(-3).map(e => e.nota)),
    [currentTaskData.acompanhamento]
  );
  const insightPlanoSignature = useMemo(
    () => JSON.stringify((currentTaskData.plano_acao || []).map(i => `${i.text}|${i.completed}`)),
    [currentTaskData.plano_acao]
  );

  // Proactive insight: debounce 10s after diary or plan changes
  useEffect(() => {
    if (!insightMountedRef.current) {
      insightMountedRef.current = true;
      return;
    }
    if (insightApplyingRef.current) return;

    if (insightDebounceRef.current) clearTimeout(insightDebounceRef.current);

    insightDebounceRef.current = setTimeout(async () => {
      if (isAnalyzingInsight) return;
      // Não emitir manifestação automática quando a alteração veio do próprio
      // copiloto. Durante uma resposta longa, o backend pode atualizar plano/diário
      // antes da resposta final chegar ao navegador; por isso a guarda cobre o
      // turno inteiro, não só uma janela fixa desde o envio.
      const insightGuard = copilotInsightGuardRef.current;
      if (insightGuard.inFlight || Date.now() < insightGuard.suppressUntil) return;
      setIsAnalyzingInsight(true);
      setInsightState(null);
      try {
        const fn = httpsCallable(functions, 'analisarInsightProativo');
        const res = await fn({
          taskId: task.id,
          titulo: currentTaskData.titulo,
          status: currentTaskData.status,
          dataLimite: currentTaskData.data_limite || null,
          prazoFinal: currentTaskData.prazo_final || null,
          planoAcao: (currentTaskData.plano_acao || []).map(i => ({ id: i.id, text: i.text, completed: i.completed })),
          acompanhamentoRecente: (currentTaskData.acompanhamento || []).slice(-10).map(e => ({ data: e.data, nota: e.nota })),
          insightsIgnorados: currentTaskData.insights_ignorados || [],
        });
        const d = res.data as any;
        if (d.nivel != null && d.texto) {
          const nextInsight = {
            nivel: d.nivel,
            texto: d.texto,
            alvo: d.alvo,
            planoProposto: d.planoProposto,
            acoesPropostas: d.acoesPropostas
          } as NonNullable<InsightState>;
          setInsightState(nextInsight);
          await persistProactiveInsight(nextInsight);
        }
      } catch {
        // silent fail — insight is non-critical
      } finally {
        setIsAnalyzingInsight(false);
      }
    }, 10000);

    return () => { if (insightDebounceRef.current) clearTimeout(insightDebounceRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insightDiarioSignature, insightPlanoSignature, newFollowUp]);

  // Inline editing
  const [editingStatus, setEditingStatus] = useState(false);
  const [pendingStatus, setPendingStatus] = useState(task.status);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editedTitle, setEditedTitle] = useState(currentTaskData.titulo);

  useEffect(() => {
    setEditedTitle(currentTaskData.titulo);
  }, [currentTaskData.titulo, currentTaskData.id]);

  const handleSaveTitle = () => {
    if (editedTitle.trim() && editedTitle !== currentTaskData.titulo) {
      onSave(task.id, { titulo: editedTitle.trim() });
      showToast('Título da ação atualizado!', 'success');
    }
    setIsEditingTitle(false);
  };


  // Modal system
  const [modalConfig, setModalConfig] = useState<{
    type: 'link' | 'contact' | 'edit_diary' | 'confirm_delete' | 'file_upload' | 'reminder';
    data?: any;
    isOpen: boolean;
  }>({ type: 'link', isOpen: false });
  const [modalInputValue, setModalInputValue] = useState('');
  const [modalInputName, setModalInputName] = useState('');
  const [reminderDate, setReminderDate] = useState('');
  const [reminderTime, setReminderTime] = useState('');
  const [reminderMessage, setReminderMessage] = useState('');
  const [showReminderHistory, setShowReminderHistory] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingUploadFile[]>([]);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  const streamRef = useRef<MediaStream | null>(null);

  // Plan modal
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [planDraft, setPlanDraft] = useState<ActionPlanItem[]>([]);
  const [newPlanItemText, setNewPlanItemText] = useState('');
  const newPlanItemRef = useRef<HTMLInputElement>(null);
  const [isHandlePressed, setIsHandlePressed] = useState(false);
  const [dragSourceIdx, setDragSourceIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const getPlanDraftTextRows = (text: string) => Math.max(2, Math.ceil((text || '').length / 58));

  // Proposal editing (Feature 1 & 2)
  const [editingProposal, setEditingProposal] = useState<{ msgIndex: number; items: ActionPlanItem[] } | null>(null);



  // Plan history viewer (Feature 5)
  const [showPlanHistory, setShowPlanHistory] = useState(false);
  const [showCompletedPlanItems, setShowCompletedPlanItems] = useState(false);

  useEffect(() => {
    setShowCompletedPlanItems(false);
  }, [currentTaskData.id]);

  // Proactive insight system
  type ProposedActionIdea = { titulo: string; descricao: string; tags: string[] };
  type InsightState = { nivel: 1 | 2 | 3; texto: string; alvo: 'diario' | 'plano' | 'acoes'; planoProposto?: ActionPlanItem[]; acoesPropostas?: ProposedActionIdea[] } | null;
  const [insightState, setInsightState] = useState<InsightState>(null);
  const [isAnalyzingInsight, setIsAnalyzingInsight] = useState(false);
  const [showInsightModal, setShowInsightModal] = useState(false);
  const [isContextModalOpen, setIsContextModalOpen] = useState(false);
  const [contextSearchQuery, setContextSearchQuery] = useState('');
  const [contextTypeFilter, setContextTypeFilter] = useState<'all' | 'link' | 'pdf' | 'excel' | 'word' | 'image' | 'other'>('all');
  const [contextSortOption, setContextSortOption] = useState<'name-asc' | 'name-desc' | 'date-desc' | 'date-asc'>('name-asc');
  const insightDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const insightMountedRef = useRef(false);
  const insightApplyingRef = useRef(false);
  const lastPersistedInsightSignatureRef = useRef<string | null>(null);
  // Origem explícita da mutação: enquanto um turno do copiloto está em andamento,
  // plano/diário podem mudar pelo backend antes da resposta final voltar. Mantemos
  // uma janela curta após o fim para absorver a latência do snapshot do Firestore.
  const copilotInsightGuardRef = useRef<{ inFlight: boolean; suppressUntil: number }>({
    inFlight: false,
    suppressUntil: 0,
  });

  const markCopilotActivity = (phase: 'started' | 'completed' | 'failed' | 'cancelled') => {
    const now = Date.now();
    if (phase === 'started') {
      copilotInsightGuardRef.current = {
        inFlight: true,
        suppressUntil: now + 10 * 60 * 1000,
      };
      return;
    }

    copilotInsightGuardRef.current = {
      inFlight: false,
      suppressUntil: now + 90 * 1000,
    };
  };

  const ensureTaskCopilotSession = async () => {
    const existingQ = query(
      collection(db, 'sessoes_copiloto'),
      where('userId', '==', copilotoUserId),
      orderBy('lastMessageAt', 'desc'),
      limit(50)
    );
    const existingSnap = await getDocs(existingQ);
    const existingTaskSession = existingSnap.docs.find(sessionDoc => {
      const data = sessionDoc.data();
      return data.taskId === task.id && !data.isTemporary;
    });
    if (existingTaskSession) return existingTaskSession.id;

    const sessRef = await addDoc(collection(db, 'sessoes_copiloto'), {
      title: currentTaskData.titulo ? `Acao: ${currentTaskData.titulo}`.slice(0, 80) : 'Acao em acompanhamento',
      userId: copilotoUserId,
      taskId: task.id,
      systemId: currentTaskData.sistema || null,
      isTemporary: false,
      createdAt: serverTimestamp(),
      lastMessageAt: serverTimestamp()
    });
    return sessRef.id;
  };

  const persistProactiveInsight = async (insight: NonNullable<InsightState>) => {
    const signature = JSON.stringify({
      taskId: task.id,
      nivel: insight.nivel,
      alvo: insight.alvo,
      texto: insight.texto,
      diario: insightDiarioSignature,
      plano: insightPlanoSignature,
    });
    if (lastPersistedInsightSignatureRef.current === signature) return;
    lastPersistedInsightSignatureRef.current = signature;

    try {
      const sessionId = await ensureTaskCopilotSession();
      await addDoc(collection(db, 'sessoes_copiloto', sessionId, 'mensagens'), {
        role: 'assistant',
        subtype: 'proactive_insight',
        insightNivel: insight.nivel,
        insightAlvo: insight.alvo,
        content: insight.texto,
        source: 'web_task_view',
        timestamp: serverTimestamp()
      });
      await setDoc(doc(db, 'sessoes_copiloto', sessionId), {
        lastMessageAt: serverTimestamp()
      }, { merge: true });
    } catch (err) {
      console.error('[Insight] Erro ao registrar insight no chat:', err);
    }
  };

  // Tags
  const [tagInput, setTagInput] = useState('');
  const [isGeneratingTags, setIsGeneratingTags] = useState(false);
  const existingTags = useMemo(() => Array.from(new Set(tarefas.flatMap(t => t.tags || []))), [tarefas]);

  // Knowledge Graph citations: msgIndex → lista de nós do grafo retornados pelo backend
  const [kgNodesByMsg, setKgNodesByMsg] = useState<Record<number, Array<{ node_id: string; titulo: string; resumo?: string; n_tasks?: number }>>>({});

  // Knowledge panel
  const [showKnowledgePanel, setShowKnowledgePanel] = useState(true);
  const [sessionExtraFiles, setSessionExtraFiles] = useState<{ id: string; name: string; status: 'uploading' | 'ready' | 'error' }[]>([]);
  const [isUploadingExtra, setIsUploadingExtra] = useState(false);
  const [isContextDropActive, setIsContextDropActive] = useState(false);
  const extraFileInputRef = useRef<HTMLInputElement>(null);

  // Audio / transcription
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessingTranscription, setIsProcessingTranscription] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const diaryEndRef = useRef<HTMLDivElement>(null!);
  const workspaceRef = useRef<HTMLDivElement>(null!);
  const mobileHeaderRef = useRef<HTMLElement>(null!);
  const lastMobileScrollTopRef = useRef(0);
  const headerToggleCooldownRef = useRef(false);



  const progressPercent = useMemo(() => {
    const items = currentTaskData.plano_acao || [];
    if (items.length === 0) return 0;
    const done = items.filter(i => i.completed).length;
    return Math.round((done / items.length) * 100);
  }, [currentTaskData.plano_acao]);

  const pendingPlanItems = useMemo(
    () => (currentTaskData.plano_acao || []).filter(item => !item.completed),
    [currentTaskData.plano_acao]
  );

  const completedPlanItems = useMemo(
    () => (currentTaskData.plano_acao || []).filter(item => item.completed),
    [currentTaskData.plano_acao]
  );


  const taskReminders = useMemo(() => {
    const reminders = Array.isArray(currentTaskData.reminders) ? currentTaskData.reminders : [];
    if (reminders.length > 0) {
      return sortTaskReminders(reminders);
    }
    if (currentTaskData.reminder_at) {
      return [{
        id: 'legacy-reminder',
        reminder_at: currentTaskData.reminder_at,
        reminder_sent: Boolean(currentTaskData.reminder_sent),
        created_at: currentTaskData.data_atualizacao || currentTaskData.data_criacao || currentTaskData.reminder_at,
      }] satisfies TaskReminder[];
    }
    return [];
  }, [currentTaskData.data_atualizacao, currentTaskData.data_criacao, currentTaskData.reminder_at, currentTaskData.reminder_sent, currentTaskData.reminders]);

  const pendingReminderCount = useMemo(
    () => taskReminders.filter(reminder => !reminder.reminder_sent).length,
    [taskReminders]
  );

  const nextPendingReminder = useMemo(
    () => getNextPendingReminder(taskReminders),
    [taskReminders]
  );

  useEffect(() => {
    const handleViewportResize = () => setDesktopViewportWidth(window.innerWidth);
    handleViewportResize();
    window.addEventListener('resize', handleViewportResize);
    return () => window.removeEventListener('resize', handleViewportResize);
  }, []);

  useEffect(() => {
    if (!isCompactMobileViewport) {
      setIsMobileHeaderHidden(false);
      lastMobileScrollTopRef.current = 0;
    }
  }, [isCompactMobileViewport]);

  useEffect(() => {
    setIsMobileHeaderHidden(false);
    lastMobileScrollTopRef.current = 0;
  }, [mobileTab]);

  useEffect(() => {
    const header = mobileHeaderRef.current;
    if (!header) return;

    const updateHeaderHeight = () => setMobileHeaderHeight(header.offsetHeight);
    updateHeaderHeight();

    if (typeof ResizeObserver === 'undefined') return;
    const resizeObserver = new ResizeObserver(updateHeaderHeight);
    resizeObserver.observe(header);

    return () => resizeObserver.disconnect();
  }, []);

  const handleMobileHeaderScroll = (scrollTop: number) => {
    if (!isCompactMobileViewport) return;

    const previousScrollTop = lastMobileScrollTopRef.current;
    const delta = scrollTop - previousScrollTop;
    // Always update position so delta is correct after cooldown ends
    lastMobileScrollTopRef.current = Math.max(0, scrollTop);

    // Block toggles during CSS transition (300ms) to prevent layout-shift feedback loop
    if (headerToggleCooldownRef.current) return;

    if (scrollTop <= 12) {
      setIsMobileHeaderHidden(false);
      return;
    }

    if (delta > 6) {
      headerToggleCooldownRef.current = true;
      setTimeout(() => { headerToggleCooldownRef.current = false; }, 350);
      setIsMobileHeaderHidden(true);
      return;
    }

    if (delta < -6) {
      headerToggleCooldownRef.current = true;
      setTimeout(() => { headerToggleCooldownRef.current = false; }, 350);
      setIsMobileHeaderHidden(false);
    }
  };

  useEffect(() => {
    try {
      const savedLayout = localStorage.getItem(OPS_LAYOUT_KEY);
      if (!savedLayout) return;
      const parsed = JSON.parse(savedLayout);
      if (typeof parsed.planWidth === 'number') setPlanPanelWidth(parsed.planWidth);
      if (typeof parsed.copilotWidth === 'number') setCopilotPanelWidth(parsed.copilotWidth);
      if (typeof parsed.isPlanCollapsed === 'boolean') setIsPlanCollapsed(parsed.isPlanCollapsed);
      if (typeof parsed.isCopilotCollapsed === 'boolean') setIsCopilotCollapsed(parsed.isCopilotCollapsed);
    } catch (error) {
      console.warn('[TaskExecutionView] Falha ao carregar layout da sala de operações', error);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(OPS_LAYOUT_KEY, JSON.stringify({
      planWidth: planPanelWidth,
      copilotWidth: copilotPanelWidth,
      isPlanCollapsed,
      isCopilotCollapsed,
    }));
  }, [copilotPanelWidth, isCopilotCollapsed, isPlanCollapsed, planPanelWidth]);

  const getPanelMaxWidth = (panel: DesktopPanel) => {
    const workspaceWidth = workspaceRef.current?.clientWidth || desktopViewportWidth;
    const otherPanelWidth = panel === 'plan'
      ? (isCopilotCollapsed ? PANEL_COLLAPSED_WIDTH : copilotPanelWidth)
      : (isPlanCollapsed ? PANEL_COLLAPSED_WIDTH : planPanelWidth);
    const panelMinWidth = panel === 'plan' ? PLAN_PANEL_MIN_WIDTH : COPILOT_PANEL_MIN_WIDTH;
    return Math.max(panelMinWidth, workspaceWidth - otherPanelWidth - DIARY_PANEL_MIN_WIDTH);
  };

  const startDesktopResize = (panel: DesktopPanel, event: React.MouseEvent) => {
    if (!isDesktopViewport) return;

    event.preventDefault();
    const startX = event.clientX;
    const initialWidth = panel === 'plan' ? planPanelWidth : copilotPanelWidth;
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';

    const onMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const rawWidth = panel === 'plan' ? initialWidth + deltaX : initialWidth - deltaX;
      const nextWidth = Math.max(
        panel === 'plan' ? PLAN_PANEL_MIN_WIDTH : COPILOT_PANEL_MIN_WIDTH,
        Math.min(rawWidth, getPanelMaxWidth(panel))
      );

      if (panel === 'plan') {
        setPlanPanelWidth(nextWidth);
      } else {
        setCopilotPanelWidth(nextWidth);
      }
    };

    const onMouseUp = () => {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  // ─── Checklist Toggle (with auto-diary entry) ─────────────────
  const handleToggleChecklistItem = (itemId: string) => {
    const items = currentTaskData.plano_acao || [];
    const item = items.find(i => i.id === itemId);
    if (!item) return;
    const newCompleted = !item.completed;
    const updated = items.map(i => i.id === itemId ? { ...i, completed: newCompleted } : i);
    const sorted = [
      ...updated.filter(i => i.completed),
      ...updated.filter(i => !i.completed)
    ];

    let updatedAcompanhamento = [...(currentTaskData.acompanhamento || [])];

    if (newCompleted) {
      const systemEntry: Acompanhamento = {
        data: new Date().toISOString(),
        nota: `✅ Sistema: Subtarefa "${item.text}" concluída.`
      };
      updatedAcompanhamento.push(systemEntry);
    } else {
      const targetNote = `✅ Sistema: Subtarefa "${item.text}" concluída.`;
      const lastIndex = updatedAcompanhamento.map(e => e.nota).lastIndexOf(targetNote);
      if (lastIndex !== -1) {
        updatedAcompanhamento.splice(lastIndex, 1);
      }
    }

    const allCompleted = sorted.length > 0 && sorted.every(i => i.completed);

    onSave(task.id, {
      plano_acao: sorted,
      acompanhamento: updatedAcompanhamento,
      ...(allCompleted && { status: 'concluído' })
    });

    if (allCompleted) {
      showToast('Status atualizado para Concluído!', 'success');
    }


  };

  const openReminderModal = (reminder?: TaskReminder) => {
    const baseIso = reminder?.reminder_at || nextPendingReminder?.reminder_at;
    setReminderMessage(reminder?.message || '');
    if (baseIso) {
      const [date, time] = baseIso.split('T');
      setReminderDate(date || '');
      setReminderTime((time || '').slice(0, 5));
    } else {
      const now = new Date();
      setReminderDate(now.toISOString().split('T')[0]);
      setReminderTime(now.toTimeString().slice(0, 5));
    }
    setModalConfig({ type: 'reminder', isOpen: true });
  };

  const handleDeleteReminder = (reminderId: string) => {
    const updatedReminders = taskReminders.filter(reminder => reminder.id !== reminderId && reminder.id !== 'legacy-reminder');
    onSave(task.id, buildReminderPayload(updatedReminders));
    showToast('Lembrete removido.', 'success');
  };



  // ─── Diary Handlers ───────────────────────────────────────────
  const handleAddFollowUp = () => {
    if (!newFollowUp.trim()) return;
    const entry: Acompanhamento = { data: new Date().toISOString(), nota: newFollowUp };
    onSave(task.id, { acompanhamento: [...(currentTaskData.acompanhamento || []), entry] });
    setNewFollowUp('');
    setShouldAutoScroll(true);
  };

  const handleCopyAllHistory = () => {
    const entries = currentTaskData.acompanhamento || [];
    const assets = currentTaskData.pool_dados || [];
    if (entries.length === 0 && assets.length === 0) { showToast('Nenhum histórico para copiar.', 'info'); return; }
    const text = [
      `Ação: ${currentTaskData.titulo}`,
      `Status: ${currentTaskData.status}`,
      `Prazo: ${currentTaskData.data_limite || 'Sem prazo'}`,
      '',
      'DIÁRIO DE BORDO',
      entries.length > 0
        ? entries.map(e => {
          const p = parseDiaryRichNote(e.nota || '');
          const content = p ? `${p.type}: ${p.name || p.value}` : e.nota;
          return `[${new Date(e.data).toLocaleString('pt-BR')}] ${content}`;
        }).join('\n\n')
        : 'Sem registros.',
      '',
      'POOL DE DADOS',
      assets.length > 0
        ? assets.map(i => `- ${i.nome || 'Sem nome'} | ${i.tipo} | ${i.valor}`).join('\n')
        : 'Nenhum item.'
    ].join('\n');
    navigator.clipboard.writeText(text);
    showToast('Diário copiado!', 'success');
  };

  // ─── File Upload ──────────────────────────────────────────────
  const readFileAsBase64 = (file: File) => new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });

  const handleFileUpload = async (files: Array<{ file: File; customName?: string }>) => {
    if (files.length === 0) return [];
    setIsUploading(true);
    const uploadFunc = httpsCallable(functions, 'upload_to_drive');
    const uploadedItems: PoolItem[] = [];
    try {
      for (const { file, customName } of files) {
        const finalName = getRenamedFileName(file.name, customName);
        const b64 = await readFileAsBase64(file);
        const result = await uploadFunc({ fileName: finalName, fileContent: b64, mimeType: file.type, folderId: appSettings.googleDriveFolderId });
        const d = result.data as any;
        const item: PoolItem = { id: Math.random().toString(36).substring(2, 11), tipo: 'arquivo', valor: d.webViewLink, nome: finalName, data_criacao: new Date().toISOString(), drive_file_id: d.fileId };
        uploadedItems.push(item);
      }
      const newEntries = uploadedItems.map(i => ({ data: new Date().toISOString(), nota: buildDiaryRichNote('FILE', i.nome || 'Arquivo', i.valor) }));
      onSave(task.id, {
        pool_dados: [...(currentTaskData.pool_dados || []), ...uploadedItems],
        acompanhamento: [...(currentTaskData.acompanhamento || []), ...newEntries]
      });
      for (const item of uploadedItems) {
        const ki: ConhecimentoItem = { id: item.id, titulo: item.nome || 'Sem título', tipo_arquivo: item.nome?.split('.').pop()?.toLowerCase() || 'unknown', url_drive: item.valor, tamanho: 0, data_criacao: item.data_criacao, origem: { modulo: 'tarefas', id_origem: task.id } };
        setDoc(doc(db, 'conhecimento', item.id), ki).catch(console.error);
      }
      showToast(`${uploadedItems.length} arquivo(s) carregado(s).`, 'success');
      return uploadedItems;
    } catch (err) {
      const errorCode = typeof (err as any)?.code === 'string' ? (err as any).code : '';
      const message = err instanceof Error ? err.message : '';
      const shouldShowBackendMessage = errorCode.includes('failed-precondition') || message.includes('Autenticacao Google');
      showToast(shouldShowBackendMessage && message ? message : 'Erro ao carregar para o Drive.', 'error');
      return [];
    } finally {
      setIsUploading(false);
    }
  };

  const getPoolItemCategory = (item: PoolItem): 'link' | 'pdf' | 'excel' | 'word' | 'image' | 'other' => {
    if (item.tipo === 'link') return 'link';
    const name = item.nome || '';
    const ext = name.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return 'pdf';
    if (['xlsx', 'xls', 'csv'].includes(ext || '')) return 'excel';
    if (['docx', 'doc', 'txt', 'md'].includes(ext || '')) return 'word';
    if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext || '')) return 'image';
    return 'other';
  };

  const formatContextDate = (dateStr?: string) => {
    if (!dateStr) return '---';
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return dateStr;
      return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return dateStr;
    }
  };

  const handleRemovePoolItem = (itemId: string) => {
    const updatedPool = (currentTaskData.pool_dados || []).filter(item => item.id !== itemId);
    onSave(task.id, { pool_dados: updatedPool });
    showToast('Documento desvinculado com sucesso.', 'info');
  };

  const renderContextModal = () => {
    const poolItems = currentTaskData.pool_dados || [];
    const counts = {
      all: poolItems.length,
      link: poolItems.filter(i => getPoolItemCategory(i) === 'link').length,
      pdf: poolItems.filter(i => getPoolItemCategory(i) === 'pdf').length,
      excel: poolItems.filter(i => getPoolItemCategory(i) === 'excel').length,
      word: poolItems.filter(i => getPoolItemCategory(i) === 'word').length,
      image: poolItems.filter(i => getPoolItemCategory(i) === 'image').length,
      other: poolItems.filter(i => getPoolItemCategory(i) === 'other').length,
    };

    const sortedAndFilteredItems = [...poolItems]
      .filter(item => {
        const name = (item.nome || item.valor).toLowerCase();
        if (contextSearchQuery && !name.includes(contextSearchQuery.toLowerCase())) {
          return false;
        }
        const category = getPoolItemCategory(item);
        if (contextTypeFilter !== 'all') {
          if (contextTypeFilter === 'link') return category === 'link';
          if (contextTypeFilter === 'pdf') return category === 'pdf';
          if (contextTypeFilter === 'excel') return category === 'excel';
          if (contextTypeFilter === 'word') return category === 'word';
          if (contextTypeFilter === 'image') return category === 'image';
          if (contextTypeFilter === 'other') return category === 'other';
        }
        return true;
      })
      .sort((a, b) => {
        const aName = a.nome || a.valor;
        const bName = b.nome || b.valor;
        if (contextSortOption === 'name-asc') {
          return aName.localeCompare(bName, 'pt-BR');
        }
        if (contextSortOption === 'name-desc') {
          return bName.localeCompare(aName, 'pt-BR');
        }
        const aTime = a.data_criacao ? new Date(a.data_criacao).getTime() : 0;
        const bTime = b.data_criacao ? new Date(b.data_criacao).getTime() : 0;
        if (contextSortOption === 'date-desc') {
          return bTime - aTime;
        }
        if (contextSortOption === 'date-asc') {
          return aTime - bTime;
        }
        return 0;
      });

    return (
      <div className="fixed inset-0 z-[320] bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 lg:p-6 animate-in fade-in duration-200">
        <div className={`w-full max-w-6xl h-[85vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden border ${isDark ? 'bg-[#0b0c16] border-white/10 text-white' : 'bg-white border-slate-200 text-slate-900'}`}>
          
          {/* Header */}
          <div className={`shrink-0 px-6 py-4 border-b flex items-center justify-between ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
            <div>
              <h3 className="text-base font-black tracking-tight font-sans flex items-center gap-2">
                <svg className="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Painel de Contexto Expandido
              </h3>
              <p className={`text-[10px] mt-0.5 font-sans ${mutedText}`}>Gerenciamento e detalhamento de demanda, base temática e documentos anexados.</p>
            </div>
            <button 
              onClick={() => setIsContextModalOpen(false)} 
              className={`p-2 rounded-lg transition-all ${isDark ? 'hover:bg-white/10 text-white/40 hover:text-white' : 'hover:bg-slate-100 text-slate-400 hover:text-slate-600'}`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>

          {/* Split Content */}
          <div className="flex-1 min-h-0 flex flex-col md:flex-row">
            
            {/* Left Column: Demand, Area, Tags */}
            <div className={`w-full md:w-80 shrink-0 p-6 border-b md:border-b-0 md:border-r overflow-y-auto flex flex-col gap-6 ${isDark ? 'border-white/10 bg-white/[0.01]' : 'border-slate-100 bg-slate-50/50'}`} style={{ scrollbarWidth: 'thin' }}>
              
              {/* Demand Synthesis */}
              {currentTaskData.descricao && (
                <div className="space-y-2">
                  <h4 className={`text-[9px] font-black uppercase tracking-wider ${mutedText}`}>Síntese da Demanda</h4>
                  <div className={`p-3 rounded-lg border text-xs leading-relaxed font-sans max-h-36 overflow-y-auto ${isDark ? 'bg-white/5 border-white/10 text-white/80' : 'bg-white border-slate-200 text-slate-600'}`}>
                    {currentTaskData.descricao}
                  </div>
                </div>
              )}

              {/* Area Tematica */}
              <div className="space-y-2">
                <h4 className={`text-[9px] font-black uppercase tracking-wider ${mutedText}`}>Área Temática</h4>
                <div className={`p-3 rounded-lg border ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`}>
                  <select
                    value={currentTaskData.area_tematica || 'NÃO CLASSIFICADA'}
                    onChange={e => {
                      const newArea = e.target.value;
                      const base = (knowledgeBases || []).find(b => b.nome.toUpperCase() === (newArea || '').toUpperCase());
                      const baseId = base ? base.id : undefined;
                      onSave(task.id, { area_tematica: newArea, base_conhecimento: baseId });
                    }}
                    style={{ colorScheme: isDark ? 'dark' : 'light' }}
                    className={`w-full border-none p-0 text-xs font-bold uppercase tracking-wider focus:ring-0 cursor-pointer font-sans bg-transparent ${isDark ? 'text-white' : 'text-slate-900'}`}
                  >
                    <option className={isDark ? 'bg-slate-900 text-white' : 'bg-white text-slate-900'} value="GERAL">Geral</option>
                    <option className={isDark ? 'bg-slate-900 text-white' : 'bg-white text-slate-900'} value="NÃO CLASSIFICADA">Não Classificada</option>
                    <optgroup label="Estratégicas">
                      {STRATEGIC_AREA_OPTIONS.map(option => (
                        <option className={isDark ? 'bg-slate-900 text-white' : 'bg-white text-slate-900'} key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Operacionais">
                      {(unidades || []).filter(u => isOperationalArea(u.nome)).map(u => (
                        <option className={isDark ? 'bg-slate-900 text-white' : 'bg-white text-slate-900'} key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                      ))}
                    </optgroup>
                  </select>
                </div>
                {derivedKnowledgeBase && (
                  <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-[10px] font-bold ${isDark ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`}>
                    <span>{derivedKnowledgeBase.emoji || '📚'}</span>
                    <span className="truncate">Base: {derivedKnowledgeBase.nome}</span>
                  </div>
                )}
              </div>

              {/* Dynamic Tags */}
              <div className="space-y-3 flex-1 flex flex-col">
                <div className="flex items-center justify-between shrink-0">
                  <h4 className={`text-[9px] font-black uppercase tracking-wider ${mutedText}`}>Tags Dinâmicas</h4>
                  <button
                    onClick={handleAutoClassifyTags}
                    disabled={isGeneratingTags}
                    className="flex items-center gap-1.5 px-2 py-0.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg transition-colors text-[9px] font-bold uppercase tracking-wider border border-indigo-100 disabled:opacity-50"
                  >
                    {isGeneratingTags ? '...' : '✨ Auto'}
                  </button>
                </div>
                
                {/* Badges Container */}
                <div className={`flex-1 min-h-[100px] p-3 rounded-lg border overflow-y-auto flex flex-wrap content-start gap-1.5 ${isDark ? 'bg-black/20 border-white/5' : 'bg-white border-slate-200'}`} style={{ scrollbarWidth: 'thin' }}>
                  {(currentTaskData.tags || []).map(tag => (
                    <span key={tag} className="flex items-center gap-1 bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded text-[9px] font-bold border border-indigo-100 font-sans">
                      #{tag}
                      <button onClick={(e) => {
                        e.preventDefault();
                        const newTags = (currentTaskData.tags || []).filter(t => t !== tag);
                        onSave(task.id, { tags: newTags });
                      }} className="text-indigo-400 hover:text-rose-500 scale-110 ml-0.5 transition-colors">&times;</button>
                    </span>
                  ))}
                  {(currentTaskData.tags || []).length === 0 && (
                    <span className="text-[10px] text-slate-400 font-medium italic font-sans">Nenhuma tag registrada.</span>
                  )}
                </div>

                {/* Add Tag Section */}
                <div className="space-y-1.5 shrink-0">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={tagInput}
                      onChange={e => setTagInput(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          if (tagInput.trim() && !(currentTaskData.tags || []).includes(tagInput.trim())) {
                            onSave(task.id, { tags: [...(currentTaskData.tags || []), tagInput.trim()] });
                            setTagInput('');
                          }
                        }
                      }}
                      className={`flex-1 border rounded-lg px-2.5 py-1 text-[11px] font-medium focus:ring-1 focus:ring-indigo-500 outline-none font-sans ${isDark ? 'bg-black/50 border-white/10 text-white' : 'bg-slate-50 border-slate-200 text-slate-700'}`}
                      placeholder="Nova tag..."
                    />
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        if (tagInput.trim() && !(currentTaskData.tags || []).includes(tagInput.trim())) {
                          onSave(task.id, { tags: [...(currentTaskData.tags || []), tagInput.trim()] });
                          setTagInput('');
                        }
                      }}
                      className={`px-3 py-1 rounded-lg transition-all text-[10px] font-bold border ${isDark ? 'bg-white/10 text-white/70 border-white/20 hover:bg-white/20' : 'bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200'}`}
                    >
                      Add
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Knowledge / Documents Manager */}
            <div className="flex-1 flex flex-col p-6 min-h-0">
              
              {/* Search & Sort Panel */}
              <div className="flex flex-col sm:flex-row gap-3 mb-6 shrink-0">
                <div className="relative flex-1">
                  <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <svg className={`w-4 h-4 ${isDark ? 'text-white/40' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                  </span>
                  <input
                    type="text"
                    placeholder="Buscar documentos por nome..."
                    value={contextSearchQuery}
                    onChange={e => setContextSearchQuery(e.target.value)}
                    className={`w-full pl-9 pr-4 py-2 rounded-xl border text-xs outline-none focus:ring-1 focus:ring-blue-500 font-sans transition-all ${
                      isDark ? 'bg-slate-900 border-white/10 text-white placeholder:text-white/30' : 'bg-slate-50 border-slate-200 text-slate-800 placeholder:text-slate-400'
                    }`}
                  />
                  {contextSearchQuery && (
                    <button 
                      onClick={() => setContextSearchQuery('')}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-white"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span className={`text-[10px] font-bold uppercase tracking-wider ${mutedText}`}>Ordenar:</span>
                  <select
                    value={contextSortOption}
                    onChange={e => setContextSortOption(e.target.value as any)}
                    style={{ colorScheme: isDark ? 'dark' : 'light' }}
                    className={`px-3 py-2 border rounded-xl text-xs font-bold outline-none cursor-pointer focus:ring-0 ${
                      isDark ? 'bg-slate-900 border-white/10 text-white' : 'bg-slate-50 border-slate-200 text-slate-700'
                    }`}
                  >
                    <option value="name-asc">Nome (A-Z)</option>
                    <option value="name-desc">Nome (Z-A)</option>
                    <option value="date-desc">Mais Recentes</option>
                    <option value="date-asc">Mais Antigos</option>
                  </select>
                </div>
              </div>

              {/* Categories / Type Filters Bar */}
              <div className="flex flex-wrap gap-1.5 mb-5 shrink-0 border-b pb-3 border-slate-100 dark:border-white/5 overflow-x-auto" style={{ scrollbarWidth: 'none' }}>
                {[
                  { value: 'all', label: 'Todos', count: counts.all, icon: '📂' },
                  { value: 'link', label: 'Links', count: counts.link, icon: '🔗' },
                  { value: 'pdf', label: 'PDFs', count: counts.pdf, icon: '📄' },
                  { value: 'excel', label: 'Planilhas', count: counts.excel, icon: '📊' },
                  { value: 'word', label: 'Documentos', count: counts.word, icon: '📝' },
                  { value: 'image', label: 'Imagens', count: counts.image, icon: '🖼️' },
                  { value: 'other', label: 'Outros', count: counts.other, icon: '🗄️' },
                ].map(opt => {
                  const isActive = contextTypeFilter === opt.value;
                  return (
                    <button
                      key={opt.value}
                      onClick={() => setContextTypeFilter(opt.value as any)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-extrabold uppercase tracking-wider transition-all border ${
                        isActive
                          ? 'bg-blue-600 border-blue-600 text-white shadow-sm'
                          : isDark
                            ? 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10 hover:text-white'
                            : 'bg-slate-100 border-slate-200 text-slate-600 hover:bg-slate-200 hover:text-slate-800'
                      }`}
                    >
                      <span>{opt.icon}</span>
                      <span>{opt.label}</span>
                      <span className={`px-1.5 py-0.2 rounded-full text-[8px] font-black ${
                        isActive
                          ? 'bg-white/20 text-white'
                          : isDark ? 'bg-white/10 text-white/50' : 'bg-slate-200 text-slate-500'
                      }`}>
                        {opt.count}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Documents Grid / Main Section */}
              <div className="flex-1 overflow-y-auto min-h-0" style={{ scrollbarWidth: 'thin' }}>
                {sortedAndFilteredItems.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 text-center">
                    <div className="w-16 h-16 rounded-full bg-slate-100 dark:bg-slate-900 flex items-center justify-center mb-3">
                      <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" /></svg>
                    </div>
                    <h5 className="text-sm font-bold">Nenhum documento encontrado</h5>
                    <p className={`text-xs mt-1 max-w-xs ${mutedText}`}>Tente alterar os filtros de categoria ou limpar sua pesquisa.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pb-4">
                    {sortedAndFilteredItems.map(item => {
                      const category = getPoolItemCategory(item);
                      
                      // Custom styled visual representations for each document type
                      let badgeBg = '';
                      let badgeText = '';
                      let iconSvg = null;
                      let typeLabel = '';

                      if (category === 'link') {
                        badgeBg = isDark ? 'bg-indigo-500/10 border-indigo-500/20' : 'bg-indigo-50 border-indigo-100';
                        badgeText = 'text-indigo-500 dark:text-indigo-400';
                        typeLabel = 'LINK';
                        iconSvg = (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                          </svg>
                        );
                      } else if (category === 'pdf') {
                        badgeBg = isDark ? 'bg-red-500/10 border-red-500/20' : 'bg-red-50 border-red-100';
                        badgeText = 'text-red-500 dark:text-red-400';
                        typeLabel = 'PDF';
                        iconSvg = (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2zM9 9h1.5m-1.5 4h5m-5 4h5" />
                          </svg>
                        );
                      } else if (category === 'excel') {
                        badgeBg = isDark ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-emerald-50 border-emerald-100';
                        badgeText = 'text-emerald-600 dark:text-emerald-400';
                        typeLabel = item.nome?.split('.').pop()?.toUpperCase() || 'XLSX';
                        iconSvg = (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                        );
                      } else if (category === 'word') {
                        badgeBg = isDark ? 'bg-blue-500/10 border-blue-500/20' : 'bg-blue-50 border-blue-100';
                        badgeText = 'text-blue-500 dark:text-blue-400';
                        typeLabel = item.nome?.split('.').pop()?.toUpperCase() || 'DOC';
                        iconSvg = (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                        );
                      } else if (category === 'image') {
                        badgeBg = isDark ? 'bg-amber-500/10 border-amber-500/20' : 'bg-amber-50 border-amber-100';
                        badgeText = 'text-amber-500 dark:text-amber-400';
                        typeLabel = item.nome?.split('.').pop()?.toUpperCase() || 'IMG';
                        iconSvg = (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                          </svg>
                        );
                      } else {
                        badgeBg = isDark ? 'bg-slate-500/10 border-slate-500/20' : 'bg-slate-100 border-slate-200';
                        badgeText = 'text-slate-500 dark:text-slate-400';
                        typeLabel = item.nome?.split('.').pop()?.toUpperCase() || 'ARQ';
                        iconSvg = (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2" />
                          </svg>
                        );
                      }

                      return (
                        <div 
                          key={item.id} 
                          className={`group relative flex flex-col justify-between p-4 rounded-2xl border transition-all ${
                            isDark 
                              ? 'bg-white/[0.02] border-white/10 hover:border-blue-500/50 hover:bg-white/[0.04]' 
                              : 'bg-slate-50 border-slate-100 hover:border-blue-500/30 hover:bg-white'
                          } hover:shadow-lg`}
                        >
                          <div>
                            {/* Top Bar inside Card */}
                            <div className="flex items-start justify-between gap-3">
                              <div className={`p-2 rounded-xl border flex items-center justify-center shrink-0 ${badgeBg} ${badgeText}`}>
                                {iconSvg}
                              </div>
                              <span className={`px-2 py-0.5 rounded-md text-[8px] font-black tracking-widest border shrink-0 ${badgeBg} ${badgeText}`}>
                                {typeLabel}
                              </span>
                            </div>

                            {/* Title / Name */}
                            <h4 
                              onClick={() => window.open(item.valor, '_blank')}
                              className={`text-xs font-black tracking-tight line-clamp-2 mt-4 cursor-pointer hover:underline ${
                                isDark ? 'text-white' : 'text-slate-800'
                              }`}
                              title={item.nome || item.valor}
                            >
                              {item.nome || item.valor}
                            </h4>

                            {/* Meta Details */}
                            <p className={`text-[9px] mt-2 font-medium ${mutedText}`}>
                              Adicionado em: {formatContextDate(item.data_criacao)}
                            </p>
                          </div>

                          {/* Actions Footer inside Card */}
                          <div className="flex items-center gap-2 mt-5 pt-3 border-t border-slate-100 dark:border-white/5">
                            <button
                              onClick={() => window.open(item.valor, '_blank')}
                              className={`flex-1 py-1.5 rounded-lg text-[9px] font-bold uppercase tracking-wider text-center transition-all ${
                                isDark ? 'bg-white/5 hover:bg-white/10 text-white' : 'bg-slate-200/50 hover:bg-slate-200 text-slate-700'
                              }`}
                            >
                              Abrir
                            </button>
                            
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(item.valor);
                                showToast('Link copiado para a área de transferência.', 'success');
                              }}
                              title="Copiar link"
                              className={`p-1.5 rounded-lg transition-all ${
                                isDark ? 'bg-white/5 hover:bg-white/10 text-white/70' : 'bg-slate-200/50 hover:bg-slate-200 text-slate-600'
                              }`}
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 002 2h2a2 2 0 002-2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                            </button>

                            <button
                              onClick={() => {
                                if (window.confirm(`Deseja realmente desvincular o documento "${item.nome || item.valor}" desta ação?`)) {
                                  handleRemovePoolItem(item.id);
                                }
                              }}
                              title="Remover"
                              className={`p-1.5 rounded-lg transition-all ${
                                isDark ? 'bg-rose-500/10 hover:bg-rose-500/20 text-rose-400' : 'bg-rose-50 hover:bg-rose-100 text-rose-600'
                              }`}
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

          </div>
        </div>
      </div>
    );
  };

  const handleFileUploadInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files ? Array.from(e.target.files) : [];
    if (selectedFiles.length === 0) return;
    handleDiaryFilesSelected(selectedFiles);
    e.target.value = '';
  };

  const handleDiaryFilesSelected = (selectedFiles: File[]) => {
    if (selectedFiles.length === 0) return;
    setPendingFiles(selectedFiles.map(createPendingUploadFile));
    setModalConfig({ type: 'file_upload', isOpen: true });
    setShowAttachMenu(false);
  };

  const processKnowledgeFiles = async (selectedFiles: File[]) => {
    const files = selectedFiles.filter(file => file.size > 0);
    if (files.length === 0 || isUploading || isUploadingExtra) return;

    const extraContextId = currentTaskData.extra_context_id || crypto.randomUUID();
    const tempFiles = files.map(file => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
      name: file.name,
      status: 'uploading' as const,
    }));

    setSessionExtraFiles(prev => [...prev, ...tempFiles]);
    setIsUploadingExtra(true);
    setShowKnowledgePanel(true);

    try {
      await handleFileUpload(files.map(file => ({ file, customName: file.name })));
      const fn = httpsCallable(functions, 'processExtraContextFile');

      for (let i = 0; i < files.length; i += 1) {
        const file = files[i];
        const temp = tempFiles[i];
        try {
          const fileBase64 = await readFileAsBase64(file);
          const result = await fn({ fileBase64, filename: file.name, mimeType: file.type, extraContextId });
          const docId = (result.data as any)?.docId || temp.id;
          setSessionExtraFiles(prev => prev.map(item => item.id === temp.id ? { ...item, id: docId, status: 'ready' } : item));
        } catch {
          setSessionExtraFiles(prev => prev.map(item => item.id === temp.id ? { ...item, status: 'error' } : item));
        }
      }

      if (!currentTaskData.extra_context_id) {
        onSave(task.id, { extra_context_id: extraContextId });
      }
      showToast('Conhecimento da ação atualizado.', 'success');
    } finally {
      setIsUploadingExtra(false);
      setIsContextDropActive(false);
    }
  };

  const handleKnowledgeInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files ? Array.from(event.target.files) : [];
    event.target.value = '';
    processKnowledgeFiles(selectedFiles);
  };

  const handleKnowledgeDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsContextDropActive(false);
    processKnowledgeFiles(Array.from(event.dataTransfer.files));
  };

  // ─── Audio Recording ──────────────────────────────────────────
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];
      mr.ondataavailable = e => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        const blob = buildRecordedAudioBlob(audioChunksRef.current, mr);
        // Stop hardware immediately instead of waiting for transcription processing
        if (stream) stream.getTracks().forEach(t => t.stop());
        streamRef.current = null;
        await handleProcessAudio(blob);
      };
      mr.start();
      setIsRecording(true);
    } catch { showToast('Erro ao acessar microfone.', 'error'); }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      // Tracks will be stopped in onstop callback
    }
  };

  // Cleanup on unmount - Ensure microphone is released
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
    };
  }, []);

  const handleProcessAudio = async (audioBlob: Blob, target: 'diary' | 'chat' = 'diary') => {
    setIsProcessingTranscription(true);
    const setter = target === 'chat' ? setChatInput : setNewFollowUp;
    try {
      const data = await transcribeAudioViaStorage(audioBlob);
      if (data.refined) setter(prev => prev + (prev ? '\n' : '') + data.refined);
    } catch (error: any) {
      showToast(error?.message || 'Erro ao processar áudio.', 'error');
    } finally {
      setIsProcessingTranscription(false);
    }
  };

  // ─── Modal Confirm ────────────────────────────────────────────
  const handleModalConfirm = async () => {
    switch (modalConfig.type) {
      case 'confirm_delete':
        if (modalConfig.data?.index !== undefined) {
          const upd = [...(currentTaskData.acompanhamento || [])];
          upd.splice(modalConfig.data.index, 1);
          onSave(task.id, { acompanhamento: upd });
        }
        break;
      case 'edit_diary':
        if (modalConfig.data?.index !== undefined && modalInputValue.trim()) {
          const upd = [...(currentTaskData.acompanhamento || [])];
          upd[modalConfig.data.index] = { ...upd[modalConfig.data.index], nota: modalInputValue };
          onSave(task.id, { acompanhamento: upd });
        }
        break;
      case 'link':
        if (modalInputValue.trim()) {
          const url = ensureHttpUrl(modalInputValue);
          const name = modalInputName.trim() || url;
          const item: PoolItem = { id: Math.random().toString(36).substring(2, 11), tipo: 'link', valor: url, nome: name, data_criacao: new Date().toISOString() };
          onSave(task.id, { pool_dados: [...(currentTaskData.pool_dados || []), item], acompanhamento: [...(currentTaskData.acompanhamento || []), { data: new Date().toISOString(), nota: buildDiaryRichNote('LINK', name, url) }] });
        }
        break;
      case 'contact':
        if (modalInputValue.trim()) {
          const name = modalInputName.trim() || modalInputValue;
          const item: PoolItem = { id: Math.random().toString(36).substring(2, 11), tipo: 'telefone', valor: modalInputValue, nome: name, data_criacao: new Date().toISOString() };
          onSave(task.id, { pool_dados: [...(currentTaskData.pool_dados || []), item], acompanhamento: [...(currentTaskData.acompanhamento || []), { data: new Date().toISOString(), nota: buildDiaryRichNote('CONTACT', name, modalInputValue) }] });
        }
        break;
      case 'reminder':
        if (reminderDate && reminderTime) {
          const newReminder: TaskReminder = {
            id: crypto.randomUUID(),
            reminder_at: `${reminderDate}T${reminderTime}:00`,
            reminder_sent: false,
            created_at: new Date().toISOString(),
            ...(reminderMessage.trim() ? { message: reminderMessage.trim() } : {}),
          };
          onSave(task.id, buildReminderPayload([...taskReminders.filter(reminder => reminder.id !== 'legacy-reminder'), newReminder]));
          showToast('Lembrete agendado!', 'success');
        }
        break;
      case 'file_upload':
        if (pendingFiles.length > 0) {
          const filesToUpload = pendingFiles.map(({ file, customName }) => ({ file, customName }));
          setModalConfig({ ...modalConfig, isOpen: false });
          setPendingFiles([]);
          handleFileUpload(filesToUpload);
          return;
        }
        break;
    }
    setModalConfig({ ...modalConfig, isOpen: false });
    setModalInputValue('');
    setModalInputName('');
    setReminderMessage('');
    setPendingFiles([]);
  };

  // ─── Chat / Copilot ───────────────────────────────────────────
  const buildHistoryContext = () => [
    `TÍTULO: ${currentTaskData.titulo}`,
    `DESCRIÇÃO: ${currentTaskData.descricao || 'N/A'}`,
    `STATUS: ${currentTaskData.status}`,
    `PRAZO: ${currentTaskData.data_limite || 'N/A'}`,
    '',
    'PLANO DE AÇÃO:',
    (currentTaskData.plano_acao || []).map((p, i) => `${i + 1}. [${p.completed ? 'X' : ' '}] ${p.text}`).join('\n'),
    '',
    'DIÁRIO DE BORDO (últimos 20 registros):',
    (currentTaskData.acompanhamento || []).slice(-20).map(a => `[${new Date(a.data).toLocaleString('pt-BR')}] ${a.nota}`).join('\n')
  ].join('\n');

  const handleApplyProposedPlan = (index: number, customPlan?: ActionPlanItem[]) => {
    const msg = chatMessages[index];
    if (!msg || (!msg.proposedPlan && !customPlan)) return;
    const planToSanitize = customPlan || msg.proposedPlan!;

    // Ensure all applied plan items have unique IDs
    const seenIds = new Set<string>();
    const appliedPlan = planToSanitize.map((item, idx) => {
      let newId = item.id;
      if (!newId || String(newId).includes('uuid') || seenIds.has(newId)) {
        newId = `plan-${Date.now()}-${idx}-${Math.random().toString(36).substring(2, 7)}`;
      }
      seenIds.add(newId);
      return { ...item, id: newId };
    });

    // Feature 5: salva versão atual no histórico antes de sobrescrever
    const currentPlan = currentTaskData.plano_acao || [];
    const existingHistory = currentTaskData.plano_acao_historico || [];
    const updatedHistory = currentPlan.length > 0
      ? [...existingHistory.slice(-4), { data: new Date().toISOString(), items: currentPlan }]
      : existingHistory;

    const updatedMessages = [...chatMessages];
    const { proposedPlan: _removed, ...rest } = updatedMessages[index];
    updatedMessages[index] = rest;

    const successMsg: ChatMessage = { role: 'assistant', content: '✅ Plano de ação atualizado com sucesso!' };
    const newHistory = [...updatedMessages, successMsg];

    const allCompleted = appliedPlan.length > 0 && appliedPlan.every(i => i.completed);

    onSave(task.id, {
      plano_acao: appliedPlan,
      plano_acao_historico: updatedHistory,
      chat_history: newHistory,
      ...(allCompleted && { status: 'concluído' })
    });

    if (allCompleted) {
      showToast('Status atualizado para Concluído!', 'success');
    }
    setChatMessages(newHistory);
    setEditingProposal(null);
    setShowPlanHistory(false);
    showToast('Plano de ação atualizado!', 'success');
  };

  const sendChatMessage = async (messageText: string, asArtifact = false) => {
    if (!messageText.trim() || isChatLoading) return;

    const userMsg: ChatMessage = { role: 'user', content: messageText };
    const historyWithUser = [...chatMessages, userMsg];
    setChatMessages(historyWithUser);
    setIsChatLoading(true);

    try {
      const fn = httpsCallable(functions, 'askTaskAssistant');

      const customPrompt = `
        Comando: ${messageText}
        ---
        IMPORTANTE: Se o usuário pedir para criar, alterar ou sugerir um plano de ação, retorne sua sugestão normal no texto E TAMBÉM inclua no final da sua resposta um bloco JSON exatamente assim:
        [PROPOSAL]
        [
          {"id": "uuid1", "text": "Passo 1", "completed": false},
          {"id": "uuid2", "text": "Passo 2", "completed": false}
        ]
        [/PROPOSAL]
        Use IDs únicos (pode ser timestamps ou strings aleatórias). Preserve os itens que já estão concluídos se fizer sentido. O plano deve ter no máximo 5 etapas — priorize as mais relevantes e agrupe ações similares quando necessário.
      `;

      const res = await fn({
        prompt: customPrompt,
        historyContext: buildHistoryContext(),
        area_tematica: task.area_tematica,
        ragContext: currentTaskData.base_conhecimento,
        extraContextId: currentTaskData.extra_context_id,
        knowledgeItemIds: currentTaskData.knowledge_item_ids || [],
        kgTags: currentTaskData.kg_tags || [],
      });

      const resData = res.data as any;
      let result = resData.result || '';
      const kgNodes: Array<{ node_id: string; titulo: string; resumo?: string; n_tasks?: number }> = resData.kg_nodes || [];
      let proposedPlan: ActionPlanItem[] | undefined = undefined;

      // Detect proposal
      const proposalMatch = result.match(/\[PROPOSAL\]([\s\S]*?)\[\/PROPOSAL\]/);
      if (proposalMatch) {
        try {
          const parsed = JSON.parse(proposalMatch[1].trim());
          if (Array.isArray(parsed)) {
            const seenIds = new Set<string>();
            proposedPlan = parsed.map((item: any, idx: number) => {
              let newId = item.id;
              if (!newId || String(newId).includes('uuid') || seenIds.has(newId)) {
                newId = `plan-${Date.now()}-${idx}-${Math.random().toString(36).substring(2, 7)}`;
              }
              seenIds.add(newId);
              return {
                id: newId,
                text: item.text || '',
                completed: !!item.completed
              };
            });
          }
          result = result.replace(/\[PROPOSAL\][\s\S]*?\[\/PROPOSAL\]/, '').trim();
        } catch (e) {
          console.error("Erro ao processar proposta de plano:", e);
        }
      }

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: asArtifact ? '📄 Artefato gerado e salvo no painel de Artefatos.' + (proposedPlan ? '\n\nO copiloto também sugeriu uma atualização no plano de ação.' : '') : result,
        ...(proposedPlan ? { proposedPlan } : {})
      };

      // Salva os nós do grafo indexados pela posição desta mensagem assistente
      if (kgNodes.length > 0) {
        const assistantMsgIndex = historyWithUser.length; // índice após user msg
        setKgNodesByMsg(prev => ({ ...prev, [assistantMsgIndex]: kgNodes }));
      }

      if (asArtifact) {
        const artifact: Artifact = {
          id: Date.now().toString(),
          title: messageText.length > 60 ? messageText.substring(0, 60) + '…' : messageText,
          content: result,
          createdAt: new Date().toLocaleString('pt-BR')
        };
        setArtifacts(prev => [...prev, artifact]);
        setShowArtifacts(true);

        const aiEntry: Acompanhamento = {
          data: new Date().toISOString(),
          nota: `🤖 IA: ${artifact.title} — documento gerado pelo copiloto.`
        };

        onSave(task.id, {
          acompanhamento: [...(currentTaskData.acompanhamento || []), aiEntry],
          chat_history: [...historyWithUser, assistantMsg]
        });
      } else {
        onSave(task.id, {
          chat_history: [...historyWithUser, assistantMsg]
        });
      }
      setChatMessages([...historyWithUser, assistantMsg]);
    } catch {
      showToast('Erro ao consultar o Copiloto.', 'error');
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleSendMessage = async () => {
    const msg = chatInput.trim();
    if (!msg) return;
    setChatInput('');

    sendChatMessage(msg);
  };

  const handleSummarizeWithAI = async () => {
    const prompt = 'Faça um resumo executivo desta ação: o que foi feito, decisões tomadas, pendências e próximos passos recomendados.';
    setChatMessages(prev => [...prev, { role: 'user', content: '📋 Resumir com IA' }]);
    setIsChatLoading(true);
    try {
      const fn = httpsCallable(functions, 'askTaskAssistant');
      const res = await fn({
        prompt,
        historyContext: buildHistoryContext(),
        area_tematica: task.area_tematica,
        ragContext: currentTaskData.base_conhecimento,
        extraContextId: currentTaskData.extra_context_id,
        knowledgeItemIds: currentTaskData.knowledge_item_ids || [],
      });
      const result = (res.data as any).result || '';
      const artifact: Artifact = {
        id: Date.now().toString(),
        title: `Resumo Executivo — ${new Date().toLocaleDateString('pt-BR')}`,
        content: result,
        createdAt: new Date().toLocaleString('pt-BR')
      };
      setArtifacts(prev => [...prev, artifact]);
      setShowArtifacts(true);
      setChatMessages(prev => [...prev, { role: 'assistant', content: '📄 Resumo gerado e salvo em Artefatos.', isArtifact: true }]);
      const aiEntry: Acompanhamento = { data: new Date().toISOString(), nota: `🤖 IA: Resumo executivo gerado pelo Copiloto.` };
      onSave(task.id, { acompanhamento: [...(currentTaskData.acompanhamento || []), aiEntry] });
    } catch {
      showToast('Erro ao gerar resumo.', 'error');
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleCopyArtifact = (artifact: Artifact) => {
    navigator.clipboard.writeText(artifact.content);
    setCopiedArtifactId(artifact.id);
    setTimeout(() => setCopiedArtifactId(null), 2000);
    showToast('Artefato copiado!', 'success');
  };

  // ─── Plan Modal ───────────────────────────────────────────────
  const openPlanModal = () => {
    const rawPlan = (currentTaskData.plano_acao || []).map(i => ({ ...i }));
    const sorted = [
      ...rawPlan.filter(i => i.completed),
      ...rawPlan.filter(i => !i.completed)
    ];
    setPlanDraft(sorted);
    setNewPlanItemText('');
    setShowPlanModal(true);
  };

  const addPlanDraftItem = () => {
    const text = newPlanItemText.trim();
    if (!text) return;
    setPlanDraft(prev => {
      const updated = [...prev, { id: crypto.randomUUID(), text, completed: false }];
      return [
        ...updated.filter(i => i.completed),
        ...updated.filter(i => !i.completed)
      ];
    });
    setNewPlanItemText('');
    setTimeout(() => newPlanItemRef.current?.focus(), 50);
  };

  const savePlanDraft = () => {
    const sorted = [
      ...planDraft.filter(i => i.completed),
      ...planDraft.filter(i => !i.completed)
    ];
    const allCompleted = sorted.length > 0 && sorted.every(i => i.completed);
    onSave(task.id, { 
      plano_acao: sorted,
      ...(allCompleted && { status: 'concluído' })
    });
    setShowPlanModal(false);
    showToast('Plano atualizado!', 'success');
    if (allCompleted) {
      showToast('Status atualizado para Concluído!', 'success');
    }
  };

  const handleDragStart = (e: React.DragEvent, index: number) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', index.toString());
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    if (dragSourceIdx === null || dragSourceIdx === index) return;
    setDragOverIdx(index);
  };

  const handleDragEnd = () => {
    if (dragSourceIdx !== null && dragOverIdx !== null && dragSourceIdx !== dragOverIdx) {
      const newItems = [...planDraft];
      const [removed] = newItems.splice(dragSourceIdx, 1);
      newItems.splice(dragOverIdx, 0, removed);

      const sorted = [
        ...newItems.filter(i => i.completed),
        ...newItems.filter(i => !i.completed)
      ];

      setPlanDraft(sorted);
    }
    setDragSourceIdx(null);
    setDragOverIdx(null);
    setIsHandlePressed(false);
  };

  const handleInsightApply = () => {
    if (!insightState) return;
    insightApplyingRef.current = true;

    if (insightState.alvo === 'diario') {
      const aiEntry: Acompanhamento = {
        data: new Date().toISOString(),
        nota: `[🤖 Insight] ${insightState.texto}`
      };
      onSave(task.id, { acompanhamento: [...(currentTaskData.acompanhamento || []), aiEntry] });
      showToast('Insight registrado no Diário!', 'success');
    } else if (insightState.alvo === 'plano' && insightState.planoProposto) {
      const currentPlan = currentTaskData.plano_acao || [];
      const existingHistory = currentTaskData.plano_acao_historico || [];
      const updatedHistory = currentPlan.length > 0
        ? [...existingHistory.slice(-4), { data: new Date().toISOString(), items: currentPlan }]
        : existingHistory;
      const allCompleted = insightState.planoProposto.length > 0 && insightState.planoProposto.every(i => i.completed);
      onSave(task.id, { 
        plano_acao: insightState.planoProposto, 
        plano_acao_historico: updatedHistory,
        ...(allCompleted && { status: 'concluído' })
      });
      showToast('Plano atualizado com o insight!', 'success');
      if (allCompleted) {
        showToast('Status atualizado para Concluído!', 'success');
      }
    }

    setInsightState(null);
    setShowInsightModal(false);
    setTimeout(() => { insightApplyingRef.current = false; }, 3000);
  };

  const handleCreateProposedAction = async (idea: ProposedActionIdea) => {
    try {
      const sanitizedPayload = {
        titulo: idea.titulo,
        descricao: idea.descricao,
        status: 'em andamento',
        data_criacao: new Date().toISOString(),
        data_atualizacao: new Date().toISOString(),
        tags: idea.tags || [],
        origem: 'ai_insight',
        projeto: currentTaskData.projeto || 'GERAL',
      };

      await addDoc(collection(db, 'tarefas'), sanitizedPayload);
      showToast(`Ação "${idea.titulo}" criada com sucesso!`, 'success');

      // Also log this in the diary
      const systemEntry: Acompanhamento = {
        data: new Date().toISOString(),
        nota: `🚀 Sistema: Nova ação criada a partir de insight: "${idea.titulo}"`
      };
      onSave(task.id, { acompanhamento: [...(currentTaskData.acompanhamento || []), systemEntry] });

    } catch (err) {
      console.error("Erro ao criar ação via insight:", err);
      showToast('Erro ao criar ação.', 'error');
    }
  };

  const handleInsightDiscard = () => {
    setInsightState(null);
    setShowInsightModal(false);
  };

  // Ignorar permanentemente: registra o texto da opinião em insights_ignorados
  // para que o backend não volte a reiterar essa mesma manifestação.
  const handleInsightIgnore = () => {
    if (!insightState) return;
    const texto = insightState.texto.trim();
    if (texto) {
      const atuais = currentTaskData.insights_ignorados || [];
      if (!atuais.includes(texto)) {
        // Mantém só as últimas 30 para o array não crescer indefinidamente.
        const proximos = [...atuais, texto].slice(-30);
        onSave(task.id, { insights_ignorados: proximos });
      }
      showToast('Opinião ignorada. O Hermes não vai mais sugerir isto.', 'success');
    }
    handleInsightDiscard();
  };

  // ─── Extra Context File Upload ────────────────────────────────
  const handleUploadExtraContextFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    const tempId = Math.random().toString(36).substring(2, 9);
    setSessionExtraFiles(prev => [...prev, { id: tempId, name: file.name, status: 'uploading' }]);
    setIsUploadingExtra(true);
    try {
      const extraContextId = currentTaskData.extra_context_id || crypto.randomUUID();
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve((reader.result as string).split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      const fn = httpsCallable(functions, 'processExtraContextFile');
      const result = await fn({ fileBase64: base64, filename: file.name, mimeType: file.type, extraContextId });
      const docId = (result.data as any).docId;
      setSessionExtraFiles(prev => prev.map(f => f.id === tempId ? { ...f, id: docId, status: 'ready' } : f));
      if (!currentTaskData.extra_context_id) {
        onSave(task.id, { extra_context_id: extraContextId });
      }
      showToast(`"${file.name}" adicionado ao contexto.`, 'success');
    } catch {
      setSessionExtraFiles(prev => prev.map(f => f.id === tempId ? { ...f, status: 'error' } : f));
      showToast('Erro ao processar o arquivo.', 'error');
    } finally {
      setIsUploadingExtra(false);
    }
  };

  const handleAutoClassifyTags = async () => {
    if (isGeneratingTags) return;
    setIsGeneratingTags(true);
    try {
      const prompt = `Analise a seguinte tarefa e forneça até 5 tags curtas e altamente relevantes (1 a 2 palavras) para caracterizá-la. Use o formato de resposta estrito: [TAGS] tag1, tag2, tag3 [/TAGS].\n\nTítulo: ${currentTaskData.titulo}\nDescrição: ${currentTaskData.descricao || ''}\nÁrea Temática: ${currentTaskData.area_tematica || ''}`;

      const fn = httpsCallable(functions, 'askTaskAssistant');
      const res = await fn({
        prompt,
        historyContext: buildHistoryContext(),
        area_tematica: task.area_tematica,
        ragContext: currentTaskData.base_conhecimento,
        extraContextId: currentTaskData.extra_context_id,
        knowledgeItemIds: currentTaskData.knowledge_item_ids || [],
      });

      const result = (res.data as any).result || '';
      const tagsMatch = result.match(/\[TAGS\]([\s\S]*?)\[\/TAGS\]/);
      if (tagsMatch) {
        const newTagsRaw = tagsMatch[1].split(',').map((t: string) => t.trim().replace(/^#/, '')).filter((t: string) => t.length > 0);
        if (newTagsRaw.length > 0) {
          const currentTagList = currentTaskData.tags || [];
          const mergedTags = Array.from(new Set([...currentTagList, ...newTagsRaw]));
          onSave(task.id, { tags: mergedTags });
          showToast('Tags geradas com sucesso!', 'success');
        } else {
          showToast('A inteligência não conseguiu extrair tags.', 'info');
        }
      } else {
        showToast('Erro ao obter formato de tags.', 'error');
      }
    } catch {
      showToast('Erro ao invocar copiloto para gerar tags.', 'error');
    } finally {
      setIsGeneratingTags(false);
    }
  };

  // ─── Status Save ──────────────────────────────────────────────
  const handleStatusChange = (status: string) => {
    onSave(task.id, { status: status as any });
    showToast('Status atualizado!', 'success');
  };

  // ─── Citation renderer ────────────────────────────────────────
  // Substitui [N] no texto da IA por badges clicáveis com tooltip mostrando
  // o título e resumo do Nó Conceitual correspondente no Grafo de Conhecimento.
  const renderWithCitations = (text: string, msgIndex: number) => {
    const nodes = kgNodesByMsg[msgIndex];
    if (!nodes || nodes.length === 0) return text;

    return text.replace(/\[(\d+)\]/g, (match, numStr) => {
      const idx = parseInt(numStr, 10) - 1;
      const node = nodes[idx];
      if (!node) return match;
      // Retorna um marcador especial que o ReactMarkdown vai renderizar via componente customizado
      return `[${numStr}](kg-cite:${encodeURIComponent(JSON.stringify({ titulo: node.titulo, resumo: node.resumo || '', n_tasks: node.n_tasks || 0, node_id: node.node_id }))})`;
    });
  };

  // ─── Theme classes ────────────────────────────────────────────
  const bg = isDark ? 'bg-[#050505] text-white' : 'bg-slate-50 dark:bg-slate-950/40-low text-slate-900';
  const cardBg = isDark ? 'bg-white/5 border-white/10' : 'bg-white border-[#e5e7eb] dark:border-white/10';
  const mutedText = isDark ? 'text-white/40' : 'text-slate-400';
  const labelCls = `text-[9px] font-bold uppercase tracking-wider font-sans ${mutedText}`;

  // ─── Status color ─────────────────────────────────────────────
  const statusColor = (s: string) => {
    if (s === 'em andamento') return 'bg-blue-500/15 text-blue-400 border-blue-500/30 font-sans';
    if (s === 'stand-by') return 'bg-amber-500/15 text-amber-400 border-amber-500/30 font-sans';
    return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 font-sans';
  };

  const renderPlanItem = (item: ActionPlanItem) => (
    <button
      key={item.id}
      onClick={() => handleToggleChecklistItem(item.id)}
      className={`w-full flex items-start gap-3 p-2.5 rounded-lg text-left transition-all group ${isDark ? 'hover:bg-white/5' : 'hover:bg-slate-50'}`}
    >
      <div className={`w-4 h-4 mt-0.5 rounded-lg border-2 flex items-center justify-center shrink-0 transition-all ${item.completed
        ? 'bg-emerald-500 border-emerald-500'
        : isDark ? 'border-white/30 group-hover:border-emerald-400' : 'border-slate-300 group-hover:border-emerald-500'
        }`}>
        {item.completed && (
          <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M5 13l4 4L19 7" />
          </svg>
        )}
      </div>
      <span className={`text-xs font-medium leading-snug transition-all font-sans ${item.completed
        ? isDark ? 'text-white/30 line-through' : 'text-slate-300 line-through'
        : isDark ? 'text-white/80' : 'text-slate-700'
        }`}>
        {item.text}
      </span>
    </button>
  );

  // ─── Columns visibility (mobile tabs) ────────────────────────
  const showMapa = mobileTab === 'mapa';
  const showDiario = mobileTab === 'diario';
  const showCopiloto = mobileTab === 'copiloto';

  // ─── Derived knowledge base from area_tematica ───────────────
  const derivedKnowledgeBase = (() => {
    if (currentTaskData.base_conhecimento) {
      const base = (knowledgeBases || []).find(b => b.id === currentTaskData.base_conhecimento);
      if (base) return base;
    }
    const area = (currentTaskData.area_tematica || '').toUpperCase();
    if (!area || area === 'GERAL' || area === 'NÃO CLASSIFICADA') return null;
    return (knowledgeBases || []).find(b => b.nome.toUpperCase() === area) ?? null;
  })();
  const isPlanPanelCollapsed = isDesktopViewport && isPlanCollapsed;
  const isCopilotPanelCollapsed = isDesktopViewport && isCopilotCollapsed;
  const mapPanelDesktopWidth = isPlanPanelCollapsed ? PANEL_COLLAPSED_WIDTH : planPanelWidth;
  const copilotoDesktopWidth = isCopilotPanelCollapsed ? PANEL_COLLAPSED_WIDTH : copilotPanelWidth;

  const renderCollapsedPanelRail = (
    panel: DesktopPanel,
    title: string,
    subtitle: string,
    onExpand: () => void
  ) => (
    <div className={`hidden lg:flex h-full shrink-0 flex-col items-center justify-between rounded-lg px-2 py-4 ${isDark ? 'bg-[#0f1724]' : 'bg-white'} ${panel === 'plan' ? 'border-r' : 'border-l'} ${isDark ? 'border-white/10' : 'border-[#e5e7eb] dark:border-white/10'}`}>
      <button
        onClick={onExpand}
        className={`flex h-8 w-8 items-center justify-center rounded-lg border transition-all font-sans ${isDark ? 'border-white/10 text-white/70 hover:bg-white/10 hover:text-white' : 'border-[#e5e7eb] dark:border-white/10 text-slate-500 hover:bg-slate-100 hover:text-slate-900'}`}
        title={`Expandir ${title}`}
      >
        <svg className={`h-4 w-4 ${panel === 'plan' ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <div className="flex flex-1 flex-col items-center justify-center gap-3">
        <span className={`text-[8px] font-black uppercase tracking-[0.35em] [writing-mode:vertical-rl] rotate-180 ${mutedText}`}>{subtitle}</span>
        <span className={`text-[9px] font-bold uppercase tracking-wider [writing-mode:vertical-rl] rotate-180 ${isDark ? 'text-white/80' : 'text-slate-700'}`}>{title}</span>
      </div>
      <div className={`h-8 w-1 rounded-lg ${isDark ? 'bg-white/10' : 'bg-slate-200'}`} />
    </div>
  );

  const renderResizeHandle = (panel: DesktopPanel) => (
    <div
      onMouseDown={(event) => startDesktopResize(panel, event)}
      className={`group hidden lg:flex w-2 shrink-0 cursor-ew-resize items-center justify-center z-10 transition-colors ${isDark ? 'bg-[#0f1724] hover:bg-blue-500/10' : 'bg-white hover:bg-blue-500/5'}`}
      title="Arrastar para redimensionar"
    >
      <div className={`h-full w-[1px] transition-all ${isDark ? 'bg-white/10 group-hover:bg-blue-400' : 'bg-slate-200 group-hover:bg-blue-500'}`} />
    </div>
  );

  // ─── Render ───────────────────────────────────────────────────
  return (
    <div className={`fixed inset-0 z-[200] flex flex-col overflow-hidden transition-colors duration-700 ${bg}`}>

      {/* ══════════════════════════════════════════════════════════
          HEADER BAR
      ══════════════════════════════════════════════════════════ */}
      <header
        ref={mobileHeaderRef}
        style={{ marginTop: isCompactMobileViewport && isMobileHeaderHidden ? -mobileHeaderHeight : 0 }}
        className={`shrink-0 px-4 py-2 sm:py-3 border-b flex flex-col gap-2 transition-[transform,margin,opacity] duration-300 ease-out max-sm:will-change-transform ${isCompactMobileViewport && isMobileHeaderHidden ? 'max-sm:-translate-y-full max-sm:opacity-0 max-sm:pointer-events-none' : 'max-sm:translate-y-0 max-sm:opacity-100'} ${isDark ? 'border-white/10 bg-[#050505]' : 'border-[#e5e7eb] dark:border-white/10 bg-white'}`}
      >
        <div className="sm:hidden flex flex-col gap-3 py-0.5">
          {/* Linha 1: Título livre */}
          <div className="min-w-0 w-full">
            {isEditingTitle ? (
              <input
                type="text"
                value={editedTitle}
                onChange={e => setEditedTitle(e.target.value)}
                onBlur={handleSaveTitle}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleSaveTitle();
                  if (e.key === 'Escape') {
                    setEditedTitle(currentTaskData.titulo);
                    setIsEditingTitle(false);
                  }
                }}
                className={`w-full bg-transparent border-b border-blue-500/50 outline-none text-xl font-black leading-tight tracking-tight break-words font-sans ${isDark ? 'text-white' : 'text-slate-900'}`}
                autoFocus
              />
            ) : (
              <h1
                onClick={() => setIsEditingTitle(true)}
                className={`text-xl font-black leading-tight tracking-tight break-words cursor-pointer hover:text-blue-600 transition-colors font-sans ${isDark ? 'text-white' : 'text-slate-900'}`}
                title="Clique para alterar o título"
              >
                {currentTaskData.titulo}
              </h1>
            )}
          </div>

          {/* Linha 2: Voltar + Atalhos */}
          <div className="flex items-center justify-between">
            <button onClick={onClose} className={`shrink-0 flex h-8 w-8 items-center justify-center rounded-lg transition-all ${isDark ? 'text-white/30 hover:text-white hover:bg-white/10' : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'}`}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <div className="shrink-0">
              <SpeedDialMenu
                notifications={notifications}
                isSyncing={isSyncing}
                isNotificationCenterOpen={isNotificationCenterOpen}
                onOpenNotes={onOpenNotes}
                onOpenCopiloto={() => {
                  if (isDesktopViewport) {
                    setIsCopilotCollapsed(false);
                    return;
                  }
                  onOpenCopiloto();
                }}
                onOpenShopping={onOpenShopping}
                onOpenTranscription={onOpenTranscription}
                onOpenMeetingTranscription={onOpenMeetingTranscription}
                onToggleNotifications={onToggleNotifications}
                onSync={onSync}
                onOpenSettings={onOpenSettings}
                onCloseNotifications={onCloseNotifications}
                onMarkAsRead={onMarkAsRead}
                onDismiss={onDismiss}
                onCreateAction={onCreateAction}
                isDark={isDark}
                direction="down"
                triggerLabel="Atalhos"
                triggerClassName={`flex px-2.5 py-1 items-center justify-center rounded-lg border shadow-[0_4px_12px_rgba(15,23,42,0.15)] ${isDark ? 'bg-slate-950 text-slate-300 border-slate-800' : 'bg-white text-slate-700 border-[#e5e7eb] dark:border-white/10'}`}
                triggerIconClassName="h-3 w-3"
              />
            </div>
          </div>

        </div>

        <div className="hidden sm:flex items-center gap-4">
          <button onClick={onClose} className={`shrink-0 flex h-8 w-8 items-center justify-center rounded-lg transition-all ${isDark ? 'text-white/40 hover:text-white hover:bg-white/10' : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'}`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
          </button>

          <div className="flex-1 min-w-0">
            {isEditingTitle ? (
              <input
                type="text"
                value={editedTitle}
                onChange={e => setEditedTitle(e.target.value)}
                onBlur={handleSaveTitle}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleSaveTitle();
                  if (e.key === 'Escape') {
                    setEditedTitle(currentTaskData.titulo);
                    setIsEditingTitle(false);
                  }
                }}
                className={`w-full bg-transparent border-b border-blue-500/50 outline-none text-xl md:text-3xl font-black tracking-tight leading-tight break-words font-sans ${isDark ? 'text-white' : 'text-slate-900'}`}
                autoFocus
              />
            ) : (
              <h1
                onClick={() => setIsEditingTitle(true)}
                className={`text-xl md:text-3xl font-black tracking-tight leading-tight break-words whitespace-normal cursor-pointer hover:text-blue-600 transition-colors font-sans ${isDark ? 'text-white' : 'text-slate-900'}`}
                title="Clique para alterar o título"
              >
                {currentTaskData.titulo}
              </h1>
            )}
          </div>

          <div className="shrink-0">
            <SpeedDialMenu
              notifications={notifications}
              isSyncing={isSyncing}
              isNotificationCenterOpen={isNotificationCenterOpen}
              onOpenNotes={onOpenNotes}
              onOpenCopiloto={() => {
                if (isDesktopViewport) {
                  setIsCopilotCollapsed(false);
                  return;
                }
                onOpenCopiloto();
              }}
              onOpenShopping={onOpenShopping}
              onOpenTranscription={onOpenTranscription}
              onOpenMeetingTranscription={onOpenMeetingTranscription}
              onToggleNotifications={onToggleNotifications}
              onSync={onSync}
              onOpenSettings={onOpenSettings}
              onCloseNotifications={onCloseNotifications}
              onMarkAsRead={onMarkAsRead}
              onDismiss={onDismiss}
              onCreateAction={onCreateAction}
              isDark={isDark}
              direction="down"
              triggerLabel="Atalhos"
              triggerClassName={`px-3 py-1.5 rounded-lg border shadow-[0_4px_12px_rgba(15,23,42,0.15)] ${isDark ? 'bg-slate-950 text-slate-300 border-slate-800' : 'bg-white text-slate-700 border-[#e5e7eb] dark:border-white/10'}`}
              triggerIconClassName="h-3.5 w-3.5"
            />
          </div>
        </div>
      </header>

      {/* ══════════════════════════════════════════════════════════
          MOBILE TAB BAR
      ══════════════════════════════════════════════════════════ */}
      <nav className={`lg:hidden shrink-0 flex border-b ${isDark ? 'border-white/10 bg-[#050505]' : 'border-[#e5e7eb] dark:border-white/10 bg-white'}`}>
        {(['mapa', 'diario', 'copiloto'] as MobileTab[]).map(tab => {
          const labels: Record<MobileTab, string> = { mapa: 'Mapa', diario: 'Diário', copiloto: 'Copiloto' };
          const icons: Record<MobileTab, React.ReactNode> = {
            mapa: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg>,
            diario: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>,
            copiloto: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>,
          };
          const active = mobileTab === tab;
          return (
            <button
              key={tab}
              onClick={() => setMobileTab(tab)}
              title={labels[tab]}
              className={`flex-1 flex items-center justify-center py-2 transition-all border-b-2 ${active
                ? isDark ? 'border-blue-400 text-blue-400' : 'border-blue-600 text-blue-600'
                : `border-transparent ${mutedText}`
                }`}
            >
              {icons[tab]}
            </button>
          );
        })}
      </nav>

      {/* ══════════════════════════════════════════════════════════
          MAIN CONTENT — 3-column desktop / single tab mobile
      ══════════════════════════════════════════════════════════ */}
      <div ref={workspaceRef} className="flex-1 min-h-0 flex flex-col gap-0 overflow-hidden lg:flex-row lg:gap-0 p-0">

        {focusedFile && isDesktopViewport ? (
          <div className="flex-1 min-h-0 flex flex-col lg:flex-row overflow-hidden">
            <div className="flex-1 flex flex-col min-w-0">
              <DocumentViewer
                file={focusedFile}
                onClose={() => {
                  setTempSessionId(null);
                  setFocusedFile(null);
                }}
                isDark={isDark}
              />
            </div>
            {/* Copiloto em Modo de Foco lateral */}
            <div 
              className="w-full lg:w-[440px] shrink-0 border-l border-[#e5e7eb] dark:border-white/10 flex flex-col min-h-0 overflow-hidden bg-[#050505]"
              style={{ width: isDesktopViewport ? copilotPanelWidth : '100%' }}
            >
              <HermesCopilotoDrawer
                isOpen
                onClose={() => setFocusedFile(null)}
                isDark={isDark}
                variant="embedded"
                taskId={task.id}
                systemId={currentTaskData.sistema}
                userId={copilotoUserId}
                activeDocument={focusedFile}
                isTemporary={!!tempSessionId}
                sessionId={tempSessionId}
                onOpenTask={onOpenCopilotoTask}
                onOpenTool={onOpenCopilotoTool}
                onUICommand={onUICommand}
                onCopilotActivity={markCopilotActivity}
              />
            </div>
          </div>
        ) : (
          <>

            {/* LEFT COLUMN — Mapa Operacional */}
            {isPlanPanelCollapsed ? (
              renderCollapsedPanelRail('plan', 'Plano', 'Sala de Operações', () => setIsPlanCollapsed(false))
            ) : (
              <>
                <div
                  onScroll={(event) => handleMobileHeaderScroll(event.currentTarget.scrollTop)}
                  className={`flex min-h-0 flex-1 flex-col gap-0 overflow-y-auto lg:flex-none ${isDark ? 'bg-[#0f1724]' : 'bg-white'} ${!showMapa ? 'hidden lg:flex' : 'flex'} shrink-0`}
                  style={{ scrollbarWidth: 'thin', scrollbarColor: '#CBD5E0 transparent', width: isDesktopViewport ? mapPanelDesktopWidth : undefined }}>
                  
                  {/* Header do Painel de Plano */}
                  <div className={`shrink-0 px-4 py-2 flex items-center justify-between border-b ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                    <div className="flex items-center gap-2">
                      <svg className={`w-4 h-4 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                      </svg>
                      <span className={labelCls}>Plano de Ação</span>
                    </div>
                    <button
                      onClick={() => setIsPlanCollapsed(true)}
                      className={`flex h-7 w-7 items-center justify-center rounded-lg border transition-all ${isDark ? 'border-white/10 text-white/50 hover:bg-white/10 hover:text-white' : 'border-[#e5e7eb] dark:border-white/10 text-slate-500 hover:bg-slate-100 hover:text-slate-900'}`}
                      title="Retrair plano de ação"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" />
                      </svg>
                    </button>
                  </div>

                  <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
                    {/* 1. PLANO DE AÇÃO */}
                    <div className={`rounded-lg border ${cardBg}`}>
                      <div className="px-4 pt-4 pb-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <svg className={`w-3.5 h-3.5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                          </svg>
                          <p className={labelCls}>STATUS DA AÇÃO</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={`text-[9px] font-black font-sans ${progressPercent === 100 ? 'text-emerald-500' : mutedText}`}>
                            {(currentTaskData.plano_acao || []).filter(i => i.completed).length}/{(currentTaskData.plano_acao || []).length}
                          </span>
                          <button
                            onClick={openPlanModal}
                            title="Editar plano de ação"
                            className={`p-1 rounded-lg transition-all ${isDark ? 'text-white/30 hover:text-white/70 hover:bg-white/10' : 'text-slate-300 hover:text-slate-600 hover:bg-slate-100'}`}
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                          </button>
                        </div>
                      </div>
                      
                      {/* Status da Ação */}
                      <div className="px-4 mb-3">
                        <select
                          value={currentTaskData.status}
                          onChange={e => handleStatusChange(e.target.value)}
                          className={`w-full text-center text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg border appearance-none cursor-pointer outline-none focus:ring-2 focus:ring-blue-500 transition-all font-sans ${statusColor(currentTaskData.status)} ${isDark ? 'bg-transparent' : 'bg-white'}`}
                        >
                          <option value="em andamento">Em Andamento</option>
                          <option value="stand-by">Stand-by</option>
                          <option value="concluído">Concluído</option>
                        </select>
                      </div>

                      {/* Barra de progresso interna */}
                      {(currentTaskData.plano_acao || []).length > 0 && (
                        <div className="px-4 mb-3 flex items-center gap-3">
                          <div className={`flex-1 h-1.5 rounded-lg overflow-hidden ${isDark ? 'bg-white/10' : 'bg-slate-100'}`}>
                            <div
                              className={`h-full rounded-lg transition-all duration-500 ${progressPercent === 100 ? 'bg-emerald-500' : 'bg-blue-500'}`}
                              style={{ width: `${progressPercent}%` }}
                            />
                          </div>
                          <span className={`text-[9px] font-bold uppercase tracking-wider shrink-0 font-sans ${progressPercent === 100 ? (isDark ? 'text-emerald-400' : 'text-emerald-600') : mutedText}`}>
                            {progressPercent}%
                          </span>
                        </div>
                      )}

                      <div className="px-3 pb-3">
                        {(currentTaskData.plano_acao || []).length === 0 ? (
                          <p className={`text-xs text-center py-4 ${mutedText}`}>Nenhum passo no plano.</p>
                        ) : (
                          <>
                            <div className="space-y-1.5">
                              <div className="flex items-center justify-between px-2.5 py-1">
                                <div className="flex items-center gap-2">
                                  <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                                  <span className={`text-[9px] font-bold uppercase tracking-wider font-sans ${isDark ? 'text-blue-300' : 'text-blue-600'}`}>
                                    Em andamento
                                  </span>
                                </div>
                                <span className={`text-[9px] font-bold font-sans ${mutedText}`}>
                                  {pendingPlanItems.length}
                                </span>
                              </div>

                              {pendingPlanItems.length > 0 ? (
                                pendingPlanItems.map(renderPlanItem)
                              ) : (
                                <p className={`px-2.5 py-2 text-[10px] font-medium font-sans ${mutedText}`}>
                                  Nenhuma etapa em andamento.
                                </p>
                              )}
                            </div>

                            {completedPlanItems.length > 0 && (
                              <div className={`mt-2 border-t pt-2 ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                                <button
                                  type="button"
                                  onClick={() => setShowCompletedPlanItems(current => !current)}
                                  aria-expanded={showCompletedPlanItems}
                                  className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left transition-all ${isDark ? 'hover:bg-white/5' : 'hover:bg-slate-50'}`}
                                >
                                  <div className="flex items-center gap-2">
                                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-500">
                                      <svg className="h-2.5 w-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M5 13l4 4L19 7" />
                                      </svg>
                                    </span>
                                    <span className={`text-[9px] font-bold uppercase tracking-wider font-sans ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                                      Concluídas
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <span className={`text-[9px] font-bold font-sans ${mutedText}`}>
                                      {completedPlanItems.length}
                                    </span>
                                    <svg
                                      className={`h-3 w-3 transition-transform ${showCompletedPlanItems ? 'rotate-180' : ''} ${mutedText}`}
                                      fill="none"
                                      stroke="currentColor"
                                      viewBox="0 0 24 24"
                                    >
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                                    </svg>
                                  </div>
                                </button>

                                {showCompletedPlanItems && (
                                  <div className="mt-1 space-y-1.5">
                                    {completedPlanItems.map(renderPlanItem)}
                                  </div>
                                )}
                              </div>
                            )}
                          </>
                        )}
                      </div>



                      {(currentTaskData.plano_acao_historico || []).length > 0 && (
                        <div className="px-3 mb-3">
                          <button
                            onClick={() => setShowPlanHistory(!showPlanHistory)}
                            className={`text-[9px] font-bold flex items-center gap-1 ${isDark ? 'text-white/30 hover:text-white/50' : 'text-slate-400 hover:text-slate-600'}`}
                          >
                            <svg className={`w-3 h-3 transition-transform ${showPlanHistory ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
                            Histórico de versões ({(currentTaskData.plano_acao_historico || []).length})
                          </button>
                          {showPlanHistory && (
                            <div className="mt-2 space-y-2">
                              {[...(currentTaskData.plano_acao_historico || [])].reverse().map((version, vIdx) => (
                                <div key={vIdx} className={`p-2 rounded-lg border ${isDark ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10'}`}>
                                  <div className="flex items-center justify-between mb-1.5">
                                    <p className={`text-[8px] font-bold uppercase tracking-wider ${mutedText}`}>
                                      Versão {(currentTaskData.plano_acao_historico || []).length - vIdx}
                                      {version.data && ` — ${formatDate(version.data)}`}
                                    </p>
                                  </div>
                                  <div className="space-y-1">
                                    {version.items.map((item, iIdx) => (
                                      <p key={iIdx} className={`text-[9px] flex gap-1.5 ${isDark ? 'text-white/40' : 'text-slate-500'}`}>
                                        <span className="shrink-0">{iIdx + 1}.</span>{item.text}
                                      </p>
                                    ))}
                                  </div>
                                  <button
                                    onClick={() => {
                                      onSave(task.id, { plano_acao: version.items });
                                      setShowPlanHistory(false);
                                      showToast('Plano restaurado!', 'success');
                                    }}
                                    className={`mt-1.5 text-[8px] font-bold ${isDark ? 'text-blue-400 hover:text-blue-300' : 'text-blue-600 hover:text-blue-800'}`}
                                  >
                                    Restaurar esta versão
                                  </button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* 2. AGENDAMENTO */}
                    <div className={`rounded-lg border p-4 ${cardBg}`}>
                      <div className="flex items-center gap-2 mb-3">
                        <svg className={`w-3.5 h-3.5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        <p className={labelCls}>Agendamento</p>
                      </div>
                      <div className="space-y-3">
                        <div>
                          <p className={`${labelCls} mb-1 opacity-60`}>Data de Execução</p>
                          <input type="date" min={getTodayIso()} value={localDataLimite} onChange={e => { setLocalDataLimite(e.target.value); setLocalHorarioInicio(''); setLocalHorarioFim(''); }} onBlur={handleBlurDataLimite}
                            style={{ colorScheme: isDark ? 'dark' : 'light' }}
                            className={`w-full px-3 py-2 rounded-lg text-xs font-bold outline-none focus:ring-1 focus:ring-primary-tactile border transition-all font-sans mb-3 ${isDark ? 'bg-white/10 border-white/10 text-white' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10 text-slate-900'}`} />
                            
                          <p className={`${labelCls} mb-1 opacity-60`}>Prazo Final (Opcional)</p>
                          <input type="date" min={getTodayIso()} value={localPrazoFinal} onChange={e => setLocalPrazoFinal(e.target.value)} onBlur={handleBlurPrazoFinal}
                            style={{ colorScheme: isDark ? 'dark' : 'light' }}
                            className={`w-full px-3 py-2 rounded-lg text-xs font-bold outline-none focus:ring-1 focus:ring-primary-tactile border transition-all font-sans ${isDark ? 'bg-white/10 border-white/10 text-white' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10 text-slate-900'}`} />
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <p className={`${labelCls} mb-1 opacity-60`}>Início</p>
                            <input type="time" value={localHorarioInicio} onChange={e => setLocalHorarioInicio(e.target.value)} onBlur={() => onSave(task.id, { horario_inicio: localHorarioInicio })}
                              style={{ colorScheme: isDark ? 'dark' : 'light' }}
                              className={`w-full px-3 py-2 rounded-lg text-xs font-bold outline-none focus:ring-1 focus:ring-primary-tactile border transition-all font-sans ${isDark ? 'bg-white/10 border-white/10 text-white' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10 text-slate-900'}`} />
                          </div>
                          <div>
                            <p className={`${labelCls} mb-1 opacity-60`}>Fim</p>
                            <input type="time" value={localHorarioFim} onChange={e => setLocalHorarioFim(e.target.value)} onBlur={() => onSave(task.id, { horario_fim: localHorarioFim })}
                              style={{ colorScheme: isDark ? 'dark' : 'light' }}
                              className={`w-full px-3 py-2 rounded-lg text-xs font-bold outline-none focus:ring-1 focus:ring-primary-tactile border transition-all font-sans ${isDark ? 'bg-white/10 border-white/10 text-white' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10 text-slate-900'}`} />
                          </div>
                        </div>
                        {taskReminders.length > 0 && (
                          <div className={`rounded-lg border px-3 py-2 ${isDark ? 'border-white/10 bg-white/5' : 'border-[#e5e7eb] dark:border-white/10 bg-slate-50'}`}>
                            <button
                              onClick={() => setShowReminderHistory(prev => !prev)}
                              className="w-full flex items-center gap-2 text-left"
                            >
                              <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${pendingReminderCount > 0
                                ? isDark ? 'bg-amber-500/15 text-amber-300' : 'bg-amber-100 text-amber-700'
                                : isDark ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-100 text-emerald-700'
                                }`}>
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                              </div>
                              <div className="min-w-0 flex-1">
                                <p className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-white/75' : 'text-slate-700'}`}>Lembretes</p>
                                <p className={`text-[10px] truncate ${mutedText}`}>
                                  {nextPendingReminder
                                    ? `Próximo: ${new Date(nextPendingReminder.reminder_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}`
                                    : 'Todos os lembretes já foram enviados'}
                                </p>
                              </div>
                              <span className={`px-2 py-0.5 rounded-lg text-[9px] font-black ${pendingReminderCount > 0
                                ? isDark ? 'bg-amber-500/15 text-amber-300' : 'bg-amber-100 text-amber-700'
                                : isDark ? 'bg-white/10 text-white/45' : 'bg-slate-200 text-slate-500'
                                }`}>
                                {taskReminders.length}
                              </span>
                              <svg className={`w-3 h-3 transition-transform ${mutedText} ${showReminderHistory ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" strokeWidth="2.5" /></svg>
                            </button>
                            {showReminderHistory && (
                              <div className="mt-3 space-y-2">
                                {taskReminders.map(reminder => (
                                  <div
                                    key={reminder.id}
                                    className={`flex items-center gap-2 rounded-lg border px-2.5 py-2 ${reminder.reminder_sent
                                      ? isDark ? 'border-white/10 bg-white/5 text-white/45' : 'border-[#e5e7eb] dark:border-white/10 bg-white text-slate-400'
                                      : isDark ? 'border-amber-500/20 bg-amber-500/10 text-white' : 'border-amber-200 bg-amber-50 text-slate-700'
                                      }`}
                                  >
                                    <div className={`w-2 h-2 rounded-lg shrink-0 ${reminder.reminder_sent ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                                    <div className="min-w-0 flex-1">
                                      <p className="text-[11px] font-bold">
                                        {new Date(reminder.reminder_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}
                                      </p>
                                      <p className={`text-[9px] ${reminder.reminder_sent ? mutedText : isDark ? 'text-amber-200' : 'text-amber-700'}`}>
                                        {reminder.reminder_sent ? 'Enviado' : 'Agendado'}
                                      </p>
                                      {reminder.message && (
                                        <p className={`mt-0.5 text-[10px] leading-snug line-clamp-2 ${isDark ? 'text-white/55' : 'text-slate-500'}`}>
                                          {reminder.message}
                                        </p>
                                      )}
                                    </div>
                                    <button
                                      onClick={() => handleDeleteReminder(reminder.id)}
                                      className={`w-7 h-7 rounded-lg flex items-center justify-center transition-all ${isDark ? 'hover:bg-white/10 text-white/40 hover:text-rose-300' : 'hover:bg-white text-slate-400 hover:text-rose-600'}`}
                                      aria-label="Excluir lembrete"
                                    >
                                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M6 18L18 6M6 6l12 12" /></svg>
                                    </button>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                        <button
                          onClick={() => openReminderModal()}
                          className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg border text-[10px] font-bold uppercase tracking-wider transition-all ${pendingReminderCount > 0
                            ? isDark ? 'border-amber-500/20 text-amber-300 hover:bg-amber-500/10' : 'border-amber-200 text-amber-700 hover:bg-amber-50'
                            : isDark ? 'border-white/10 text-white/40 hover:bg-white/5 hover:text-white/70' : 'border-[#e5e7eb] dark:border-white/10 text-slate-400 hover:bg-slate-50 hover:text-slate-700'
                            }`}>
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                          {taskReminders.length > 0 ? 'Novo Lembrete' : 'Agendar Lembrete'}
                        </button>

                        {/* Linha separadora */}
                        <div className="border-t border-[#e5e7eb] dark:border-white/10 my-2" />

                        {/* Vínculo automático de e-mail (email_action_linker.py) */}
                        <div className="space-y-1">
                          <label className="flex items-center gap-2 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={localEmailLinkOptout}
                              onChange={e => handleToggleEmailLinkOptout(e.target.checked)}
                              className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900"
                            />
                            <span className="text-[10px] font-black uppercase tracking-wider opacity-70">Silenciar vínculo de e-mail</span>
                          </label>
                          <p className={`text-[10px] pl-6 ${isDark ? 'text-white/40' : 'text-slate-400'}`}>
                            Por padrão, o Hermes verifica se e-mails recebidos têm relação com esta ação e sugere
                            registrar no diário via Telegram. Marque para não receber essas sugestões nesta ação.
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* 3. CONTEXTO (Agrupado) */}
                    <div className={`rounded-lg border ${cardBg}`}>
                      <div className="px-4 py-3 border-b border-[#e5e7eb] dark:border-white/10 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <svg className={`w-3.5 h-3.5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          <p className={labelCls}>Contexto</p>
                        </div>
                        <button
                          onClick={() => setIsContextModalOpen(true)}
                          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-bold uppercase tracking-wider transition-all border ${
                            isDark
                              ? 'bg-blue-500/10 border-blue-500/30 text-blue-300 hover:bg-blue-500/20'
                              : 'bg-blue-50 border-blue-200 text-blue-600 hover:bg-blue-100'
                          }`}
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
                          </svg>
                          Expandir
                        </button>
                      </div>
                      
                      <div className="p-4 flex flex-col gap-6">
                        {/* Síntese / Descrição */}
                        {currentTaskData.descricao && (
                          <div className="space-y-2">
                            <p className={`${labelCls} opacity-60`}>Síntese da Demanda</p>
                            <p className={`text-xs leading-relaxed font-sans ${isDark ? 'text-white/70' : 'text-slate-600'}`}>
                              {currentTaskData.descricao}
                            </p>
                          </div>
                        )}

                        {/* Área Temática */}
                        <div className="space-y-2">
                          <p className={`${labelCls} opacity-60`}>Área Temática</p>
                          <select
                            value={currentTaskData.area_tematica || 'NÃO CLASSIFICADA'}
                            onChange={e => {
                              const newArea = e.target.value;
                              const base = (knowledgeBases || []).find(b => b.nome.toUpperCase() === (newArea || '').toUpperCase());
                              const baseId = base ? base.id : undefined;
                              onSave(task.id, { area_tematica: newArea, base_conhecimento: baseId });
                            }}
                            style={{ colorScheme: isDark ? 'dark' : 'light' }}
                            className={`w-full border-none p-0 text-xs font-bold uppercase tracking-wider focus:ring-0 cursor-pointer font-sans ${isDark ? 'bg-slate-900 text-white' : 'bg-transparent text-slate-900'}`}
                          >
                            <option className={isDark ? 'bg-slate-900 text-white font-sans' : 'bg-white text-slate-900 font-sans'} value="GERAL">Geral</option>
                            <option className={isDark ? 'bg-slate-900 text-white font-sans' : 'bg-white text-slate-900 font-sans'} value="NÃO CLASSIFICADA">Não Classificada</option>
                            <optgroup label="Estratégicas">
                              {STRATEGIC_AREA_OPTIONS.map(option => (
                                <option className={isDark ? 'bg-slate-900 text-white font-sans' : 'bg-white text-slate-900 font-sans'} key={option.value} value={option.value}>{option.label}</option>
                              ))}
                            </optgroup>
                            <optgroup label="Operacionais">
                              {(unidades || []).filter(u => isOperationalArea(u.nome)).map(u => (
                                <option className={isDark ? 'bg-slate-900 text-white font-sans' : 'bg-white text-slate-900 font-sans'} key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                              ))}
                            </optgroup>
                          </select>
                        </div>

                        {/* Tags Dinâmicas */}
                        <div className="space-y-3 order-last">
                          <div className="flex items-center justify-between">
                            <p className={`${labelCls} opacity-60`}>Tags Dinâmicas</p>
                            <button
                              onClick={handleAutoClassifyTags}
                              disabled={isGeneratingTags}
                              className="flex items-center gap-1.5 px-2 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg transition-colors text-[9px] font-bold uppercase tracking-wider border border-indigo-100 disabled:opacity-50"
                            >
                              {isGeneratingTags ? '...' : '✨ Auto'}
                            </button>
                          </div>
                          <div className="flex flex-wrap gap-2 mb-3 font-sans">
                            {(currentTaskData.tags || []).map(tag => (
                              <span key={tag} className="flex items-center gap-1 bg-indigo-50 text-indigo-600 px-2.5 py-1 rounded-lg text-[10px] font-bold border border-indigo-100 font-sans">
                                #{tag}
                                <button onClick={(e) => {
                                  e.preventDefault();
                                  const newTags = (currentTaskData.tags || []).filter(t => t !== tag);
                                  onSave(task.id, { tags: newTags });
                                }} className="text-indigo-400 hover:text-rose-500 scale-125 ml-1 transition-colors">&times;</button>
                              </span>
                            ))}
                            {(currentTaskData.tags || []).length === 0 && (
                              <span className="text-[10px] text-slate-400 font-medium italic font-sans">Nenhuma tag...</span>
                            )}
                          </div>
                          <div>
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={tagInput}
                                onChange={e => setTagInput(e.target.value)}
                                onKeyDown={e => {
                                  if (e.key === 'Enter') {
                                    e.preventDefault();
                                    if (tagInput.trim() && !(currentTaskData.tags || []).includes(tagInput.trim())) {
                                      onSave(task.id, { tags: [...(currentTaskData.tags || []), tagInput.trim()] });
                                      setTagInput('');
                                    }
                                  }
                                }}
                                className={`flex-1 border rounded-lg px-3 py-1.5 text-[11px] font-medium focus:ring-1 focus:ring-indigo-500 outline-none font-sans ${isDark ? 'bg-black/50 border-white/10 text-white' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10 text-slate-700'}`}
                                placeholder="Adicionar nova tag (Enter)..."
                              />
                              <button
                                onClick={(e) => {
                                  e.preventDefault();
                                  if (tagInput.trim() && !(currentTaskData.tags || []).includes(tagInput.trim())) {
                                    onSave(task.id, { tags: [...(currentTaskData.tags || []), tagInput.trim()] });
                                    setTagInput('');
                                  }
                                }}
                                className={`px-3 py-1.5 rounded-lg transition-all text-[10px] font-bold border ${isDark ? 'bg-white/10 text-white/70 border-white/20 hover:bg-white/20' : 'bg-slate-100 text-slate-600 border-[#e5e7eb] dark:border-white/10 hover:bg-slate-200'}`}
                              >
                                Add
                              </button>
                            </div>
                            {tagInput.trim() && existingTags.filter(t => t.toLowerCase().includes(tagInput.trim().toLowerCase()) && !(currentTaskData.tags || []).includes(t)).length > 0 && (
                              <div className="flex flex-wrap items-center gap-1.5 mt-2 pl-1">
                                <span className={`text-[9px] font-bold uppercase tracking-widest ${mutedText}`}>Sugestões:</span>
                                {existingTags
                                  .filter(t => t.toLowerCase().includes(tagInput.trim().toLowerCase()) && !(currentTaskData.tags || []).includes(t))
                                  .slice(0, 5)
                                  .map(sug => (
                                    <button
                                      key={sug}
                                      onClick={(e) => {
                                        e.preventDefault();
                                        onSave(task.id, { tags: [...(currentTaskData.tags || []), sug] });
                                        setTagInput('');
                                      }}
                                      className="text-[9px] bg-indigo-50 hover:bg-indigo-100 text-indigo-500 font-bold px-1.5 py-0.5 rounded cursor-pointer transition-colors"
                                    >
                                      {sug}
                                    </button>
                                  ))}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Conhecimento */}
                        <div className="space-y-3">
                          <button onClick={() => setShowKnowledgePanel(!showKnowledgePanel)} className="w-full flex items-center gap-2">
                            <p className={`${labelCls} flex-1 text-left opacity-60`}>Conhecimento</p>
                            <span className={`text-[9px] font-bold ${mutedText}`}>{(currentTaskData.pool_dados || []).length}</span>
                            {(derivedKnowledgeBase || currentTaskData.extra_context_id || (currentTaskData.pool_dados || []).length > 0) && (
                              <span className="w-1.5 h-1.5 rounded-lg bg-emerald-500 shrink-0" />
                            )}
                            <svg className={`w-3 h-3 transition-transform ${mutedText} ${showKnowledgePanel ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" strokeWidth="2.5" /></svg>
                          </button>
                          {showKnowledgePanel && (
                            <div className="space-y-3 animate-in fade-in duration-300">
                              {derivedKnowledgeBase ? (
                                <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-bold ${isDark ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`}>
                                  <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                  <span className="truncate">{derivedKnowledgeBase.emoji || '📚'} {derivedKnowledgeBase.nome}</span>
                                </div>
                              ) : (
                                <p className={`text-[10px] px-1 ${isDark ? 'text-white/30' : 'text-slate-400'}`}>
                                  Sem base vinculada: defina a Área Temática acima.
                                </p>
                              )}

                              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                                {(currentTaskData.pool_dados || []).length === 0 ? (
                                  <p className={`text-xs ${mutedText} w-full text-center py-2 italic`}>Nenhum arquivo carregado.</p>
                                ) : (
                                  (currentTaskData.pool_dados || []).map((item, index) => (
                                    <button key={item.id || `pool-${index}`} onClick={() => {
                                      window.open(item.valor, '_blank');
                                    }}
                                      className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg border text-[10px] font-bold transition-all ${isDark ? 'bg-white/5 border-white/10 text-white/70 hover:bg-white/10' : 'bg-slate-50 border-slate-100 text-slate-700 hover:bg-blue-50 hover:border-blue-200'}`}>
                                      <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                      <span className="min-w-0 flex-1 truncate text-left">{item.nome || item.valor}</span>
                                      <span className={`shrink-0 text-[8px] uppercase ${mutedText}`}>{item.tipo}</span>
                                    </button>
                                  ))
                                )}
                              </div>

                              {sessionExtraFiles.length > 0 && (
                                <div className="space-y-1">
                                  {sessionExtraFiles.map(f => (
                                    <div key={f.id} className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-[10px] font-medium border ${f.status === 'ready'
                                      ? isDark ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'
                                      : f.status === 'uploading'
                                        ? isDark ? 'bg-blue-500/10 border-blue-500/20 text-blue-300' : 'bg-blue-50 border-blue-200 text-blue-600'
                                        : isDark ? 'bg-rose-500/10 border-rose-500/20 text-rose-300' : 'bg-rose-50 border-rose-200 text-rose-600'
                                      }`}>
                                      {f.status === 'ready' && <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>}
                                      {f.status === 'uploading' && <svg className="w-3 h-3 shrink-0 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>}
                                      {f.status === 'error' && <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>}
                                      <span className="truncate">{f.name}</span>
                                    </div>
                                  ))}
                                </div>
                              )}

                              {currentTaskData.extra_context_id && sessionExtraFiles.length === 0 && (
                                <p className={`text-[9px] ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                                  Contexto processado vinculado a esta ação.
                                </p>
                              )}

                              <div
                                onDragEnter={(event) => { event.preventDefault(); setIsContextDropActive(true); }}
                                onDragOver={(event) => { event.preventDefault(); setIsContextDropActive(true); }}
                                onDragLeave={(event) => { event.preventDefault(); setIsContextDropActive(false); }}
                                onDrop={handleKnowledgeDrop}
                                className={`border border-dashed p-4 text-center transition-all ${isContextDropActive
                                  ? isDark ? 'border-blue-400 bg-blue-500/10 text-blue-200' : 'border-blue-500 bg-blue-50 text-blue-700'
                                  : isDark ? 'border-white/20 text-white/45 hover:border-blue-400/40 hover:text-blue-300 hover:bg-blue-500/5' : 'border-slate-300 text-slate-400 hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50'
                                  }`}
                              >
                                <button
                                  type="button"
                                  onClick={() => extraFileInputRef.current?.click()}
                                  disabled={isUploading || isUploadingExtra}
                                  className="w-full flex flex-col items-center justify-center gap-2 disabled:opacity-40"
                                >
                                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>
                                  <span className="font-sans text-[10px] font-bold uppercase tracking-wider">
                                    {isUploading || isUploadingExtra ? 'Processando conhecimento...' : 'Adicionar ou arrastar arquivos'}
                                  </span>
                                  <span className={`text-[8px] font-bold ${mutedText}`}>Qualquer arquivo aceito</span>
                                </button>
                                <input ref={extraFileInputRef} type="file" multiple className="hidden" onChange={handleKnowledgeInputChange} />
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Fontes de Conhecimento */}
                        <div className="hidden">
                          <button onClick={() => setShowKnowledgePanel(!showKnowledgePanel)} className="w-full flex items-center gap-2">
                            <p className={`${labelCls} flex-1 text-left opacity-60`}>Fontes de Conhecimento</p>
                            {(currentTaskData.base_conhecimento || currentTaskData.extra_context_id) && (
                              <span className="w-1.5 h-1.5 rounded-lg bg-emerald-500 shrink-0" />
                            )}
                            <svg className={`w-3 h-3 transition-transform ${mutedText} ${showKnowledgePanel ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" strokeWidth="2.5" /></svg>
                          </button>
                          {showKnowledgePanel && (
                            <div className="space-y-4 animate-in fade-in duration-300">
                              {/* Base RAG — derivada automaticamente da Área Temática */}
                              <div>
                                <p className={`${labelCls} mb-1.5 opacity-40`}>Base de Conhecimento (RAG)</p>
                                {derivedKnowledgeBase ? (
                                  <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-bold ${isDark ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`}>
                                    <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                    <span className="truncate">{derivedKnowledgeBase.emoji || '📚'} {derivedKnowledgeBase.nome}</span>
                                  </div>
                                ) : (
                                  <p className={`text-[10px] px-1 ${isDark ? 'text-white/30' : 'text-slate-400'}`}>
                                    Sem base vinculada — defina a Área Temática acima.
                                  </p>
                                )}
                              </div>

                              {/* Contexto Complementar */}
                              <div>
                                <p className={`${labelCls} mb-1.5 opacity-40`}>Contexto Complementar</p>

                                {sessionExtraFiles.length > 0 && (
                                  <div className="space-y-1 mb-2">
                                    {sessionExtraFiles.map(f => (
                                      <div key={f.id} className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-[10px] font-medium border ${f.status === 'ready'
                                        ? isDark ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'
                                        : f.status === 'uploading'
                                          ? isDark ? 'bg-blue-500/10 border-blue-500/20 text-blue-300' : 'bg-blue-50 border-blue-200 text-blue-600'
                                          : isDark ? 'bg-rose-500/10 border-rose-500/20 text-rose-300' : 'bg-rose-50 border-rose-200 text-rose-600'
                                        }`}>
                                        {f.status === 'ready' && <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>}
                                        {f.status === 'uploading' && <svg className="w-3 h-3 shrink-0 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>}
                                        {f.status === 'error' && <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>}
                                        <span className="truncate">{f.name}</span>
                                      </div>
                                    ))}
                                  </div>
                                )}

                                {currentTaskData.extra_context_id && sessionExtraFiles.length === 0 && (
                                  <p className={`text-[9px] mb-2 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                                    ✓ Contexto complementar vinculado
                                  </p>
                                )}

                                <button
                                  onClick={() => extraFileInputRef.current?.click()}
                                  disabled={isUploadingExtra}
                                  className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg border border-dashed text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-40 ${isDark ? 'border-white/20 text-white/40 hover:border-blue-400/40 hover:text-blue-300 hover:bg-blue-500/5' : 'border-slate-300 text-slate-400 hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50'}`}
                                >
                                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>
                                  {isUploadingExtra ? 'Processando…' : 'Adicionar arquivo'}
                                </button>
                                <p className={`text-[8px] text-center mt-1 ${mutedText}`}>PDF · DOCX · TXT · MD</p>
                                <input type="file" accept=".pdf,.docx,.txt,.md" className="hidden" onChange={handleUploadExtraContextFile} />
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

              {/* CENTER COLUMN — Diário de Missão */}
              </>
            )}

            {!isPlanPanelCollapsed && renderResizeHandle('plan')}

            <div className={`flex min-w-0 flex-1 flex-col overflow-hidden ${!showDiario ? 'hidden lg:flex' : 'flex'} min-h-0`}>
              <div className={`flex-1 flex flex-col rounded-lg lg:rounded-lg overflow-hidden ${isDark ? 'bg-[#0f1724]' : 'bg-white'}`}>
                {/* Diary header */}
                <div className={`shrink-0 px-4 py-2 flex items-center justify-between border-b ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                  <div className="flex items-center gap-2">
                    <svg className={`w-4 h-4 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                    </svg>
                    <span className={labelCls}>Diário de Missão</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {/* Proactive insight indicator — Always visible for better feedback */}
                    <button
                      onClick={() => insightState && setShowInsightModal(true)}
                      title={
                        isAnalyzingInsight ? 'O Hermes está analisando seu progresso...' :
                          insightState ? (insightState.nivel === 1 ? 'Insight Crítico detectado!' : insightState.nivel === 3 ? 'Ideia Criativa disponível!' : 'Sugestão de Otimização personalizada.') :
                            'O Hermes está observando em busca de insights...'
                      }
                      className={`flex items-center justify-center w-7 h-7 rounded-lg transition-all relative ${isAnalyzingInsight
                        ? `animate-pulse ${isDark ? 'bg-indigo-500/20 text-indigo-400' : 'bg-indigo-50 text-indigo-500'}`
                        : insightState
                          ? insightState.nivel === 1
                            ? 'bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 animate-pulse shadow-[0_0_15px_rgba(251,191,36,0.3)]'
                            : insightState.nivel === 3
                              ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 animate-bounce'
                              : `${isDark ? 'bg-blue-500/10 text-blue-400 hover:bg-blue-500/20' : 'bg-blue-50 text-blue-500 hover:bg-blue-100'}`
                          : `opacity-20 hover:opacity-100 ${isDark ? 'text-white/30' : 'text-slate-400'}`
                        }`}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                      </svg>
                      {/* Analysis ring (discreet) */}
                      {isAnalyzingInsight && (
                        <div className="absolute inset-0 rounded-lg border-2 border-indigo-400/30 border-t-transparent animate-spin" />
                      )}
                    </button>
                    <button onClick={handleSummarizeWithAI}
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-bold uppercase tracking-wider transition-all ${isDark ? 'bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500/30' : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100 border border-indigo-200'}`}>
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                      Resumir
                    </button>
                  </div>
                </div>

                {/* Diary body — uses DiarioBordoUI unchanged */}
                <DiarioBordoUI
                  task={task}
                  currentTaskData={currentTaskData}
                  newFollowUp={newFollowUp}
                  setNewFollowUp={setNewFollowUp}
                  handleAddFollowUp={handleAddFollowUp}
                  handleCopyMessage={(txt) => { navigator.clipboard.writeText(txt); showToast('Copiado!', 'success'); }}
                  handleCopyAllHistory={handleCopyAllHistory}
                  isRecording={isRecording}
                  startRecording={startRecording}
                  stopRecording={stopRecording}
                  isProcessingTranscription={isProcessingTranscription}
                  showAttachMenu={showAttachMenu}
                  setShowAttachMenu={setShowAttachMenu}
                  fileInputRef={fileInputRef}
                  handleFileUploadInput={handleFileUploadInput}
                  handleDroppedFiles={handleDiaryFilesSelected}
                  setModalConfig={setModalConfig}
                  applyFormatting={() => { }}
                  isDark={isDark}
                  diaryEndRef={diaryEndRef}
                  handleDiaryScroll={(event) => handleMobileHeaderScroll(event.currentTarget.scrollTop)}
                  handleEditDiaryEntry={(index) => {
                    setModalInputValue(currentTaskData.acompanhamento![index].nota);
                    setModalConfig({ type: 'edit_diary', data: { index }, isOpen: true });
                  }}
                  handleDeleteDiaryEntry={(index) => setModalConfig({ type: 'confirm_delete', data: { index }, isOpen: true })}
                  isUploading={isUploading}
                  notifications={notifications}
                  handleProcessAudio={handleProcessAudio}
                />
              </div>
            </div>

            {!isCopilotPanelCollapsed && renderResizeHandle('copilot')}

            {isCopilotPanelCollapsed ? (
              renderCollapsedPanelRail('copilot', 'Copiloto', 'Hermes', () => setIsCopilotCollapsed(false))
            ) : (
              <div
                onScrollCapture={(event) => {
                  if (event.target instanceof HTMLElement) {
                    handleMobileHeaderScroll(event.target.scrollTop);
                  }
                }}
                className={`${showCopiloto ? 'flex' : 'hidden'} lg:flex min-h-0 flex-1 lg:flex-none flex-col overflow-hidden`}
                style={{ width: isDesktopViewport ? copilotoDesktopWidth : undefined }}
              >
                <HermesCopilotoDrawer
                  isOpen
                  onClose={() => setIsCopilotCollapsed(true)}
                  isDark={isDark}
                  variant="embedded"
                  taskId={task.id}
                  systemId={currentTaskData.sistema}
                  userId={copilotoUserId}
                  activeDocument={focusedFile}
                  isTemporary={!!tempSessionId}
                  sessionId={tempSessionId}
                  onOpenTask={onOpenCopilotoTask}
                  onOpenTool={onOpenCopilotoTool}
                  onUICommand={onUICommand}
                  onCopilotActivity={markCopilotActivity}
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* ══════════════════════════════════════════════════════════
          PLAN EDIT MODAL
      ══════════════════════════════════════════════════════════ */}
      {showPlanModal && (
        <div className="fixed inset-0 z-[350] bg-slate-950/90 flex items-center justify-center p-4">
          <div className={`w-full max-w-lg rounded-lg shadow-lg flex flex-col max-h-[85vh] ${isDark ? 'bg-[#0f0f1a] border border-white/10 text-white' : 'bg-white text-slate-900'}`}>

            {/* Header */}
            <div className={`shrink-0 px-6 py-5 border-b flex items-center justify-between ${isDark ? 'border-white/10' : 'border-[#e5e7eb] dark:border-white/10'}`}>
              <div>
                <h3 className="text-base font-black tracking-tight font-sans">Editar Plano de Ação</h3>
                <p className={`text-[10px] mt-0.5 font-sans ${mutedText}`}>{planDraft.length} {planDraft.length === 1 ? 'passo' : 'passos'} · clique no texto para editar</p>
              </div>
              <button onClick={() => setShowPlanModal(false)} className={`p-2 rounded-lg transition-all ${isDark ? 'hover:bg-white/10 text-white/40' : 'hover:bg-slate-100 text-slate-400'}`}>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Items list */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2" style={{ scrollbarWidth: 'thin' }}>
              {planDraft.length === 0 && (
                <p className={`text-xs text-center py-6 ${mutedText}`}>Nenhum passo ainda. Adicione abaixo.</p>
              )}
              {planDraft.map((item, idx) => (
                <div
                  key={item.id}
                  draggable={isHandlePressed && dragSourceIdx === idx}
                  onDragStart={(e) => handleDragStart(e, idx)}
                  onDragOver={(e) => handleDragOver(e, idx)}
                  onDragEnd={handleDragEnd}
                  className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border group transition-all 
                    ${dragSourceIdx === idx ? 'opacity-40 bg-blue-500/10' : ''} 
                    ${dragOverIdx === idx ? 'border-blue-500 border-dashed' : ''}
                    ${isDark ? 'bg-white/5 border-white/10 hover:border-white/20' : 'bg-slate-50 border-slate-100 hover:border-[#e5e7eb] dark:border-white/10'}
                  `}
                >
                  {/* Drag Handle */}
                  <span
                    onMouseDown={() => {
                      setIsHandlePressed(true);
                      setDragSourceIdx(idx);
                    }}
                    onMouseUp={() => setIsHandlePressed(false)}
                    className={`mt-1 shrink-0 cursor-grab active:cursor-grabbing p-1 text-slate-400 hover:text-slate-600 transition-colors ${isDark ? 'text-white/40 hover:text-white/70' : ''}`}
                    title="Arrastar para reordenar"
                  >
                    <svg className="w-3 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M9 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm0 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm0 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm10-14a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm0 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm0 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0z" />
                    </svg>
                  </span>

                  {/* Toggle Index / Completed Badge */}
                  <button
                    onClick={() => {
                      const newCompleted = !item.completed;
                      const updated = planDraft.map(i => i.id === item.id ? { ...i, completed: newCompleted } : i);
                      const sorted = [
                        ...updated.filter(i => i.completed),
                        ...updated.filter(i => !i.completed)
                      ];
                      setPlanDraft(sorted);
                    }}
                    title={item.completed ? "Marcar como não concluído" : "Marcar como concluído"}
                    className={`mt-1 shrink-0 w-5 h-5 rounded-lg flex items-center justify-center text-[9px] font-black transition-all ${item.completed ? 'bg-emerald-500 text-white' : isDark ? 'bg-white/10 text-white/40 hover:bg-white/20' : 'bg-slate-200 text-slate-500 hover:bg-slate-300'}`}
                  >
                    {item.completed ? <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : idx + 1}
                  </button>

                  {/* Editable text */}
                  <textarea
                    value={item.text}
                    onChange={e => setPlanDraft(prev => prev.map(i => i.id === item.id ? { ...i, text: e.target.value } : i))}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); newPlanItemRef.current?.focus(); } }}
                    rows={getPlanDraftTextRows(item.text)}
                    className={`flex-1 min-w-0 resize-none overflow-hidden bg-transparent py-1 text-xs font-medium leading-relaxed outline-none whitespace-pre-wrap break-words ${item.completed ? isDark ? 'text-white/30 line-through' : 'text-slate-300 line-through' : isDark ? 'text-white/80' : 'text-slate-700'}`}
                    placeholder="Descreva o passo…"
                  />

                  {/* Delete */}
                  <button
                    onClick={() => setPlanDraft(prev => prev.filter(i => i.id !== item.id))}
                    className={`mt-1 shrink-0 p-1 rounded-lg opacity-0 group-hover:opacity-100 transition-all ${isDark ? 'text-rose-400 hover:bg-rose-500/20' : 'text-rose-400 hover:bg-rose-50'}`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </button>
                </div>
              ))}
            </div>

            {/* Add new item */}
            <div className={`shrink-0 px-4 py-3 border-t ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
              <div className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border ${isDark ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10'}`}>
                <svg className={`w-3.5 h-3.5 shrink-0 ${mutedText}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                <input
                  ref={newPlanItemRef}
                  value={newPlanItemText}
                  onChange={e => setNewPlanItemText(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addPlanDraftItem(); } }}
                  placeholder="Adicionar novo passo… (Enter para confirmar)"
                  className={`flex-1 text-xs font-medium bg-transparent outline-none ${isDark ? 'text-white placeholder:text-white/25' : 'text-slate-700 placeholder:text-slate-400'}`}
                />
                {newPlanItemText.trim() && (
                  <button onClick={addPlanDraftItem} className="shrink-0 px-2.5 py-1 rounded-lg bg-blue-600 text-white text-[9px] font-bold uppercase tracking-wider">
                    Add
                  </button>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className={`shrink-0 px-6 py-4 border-t flex items-center justify-between gap-3 ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
              <p className={`text-[9px] ${mutedText}`}>Itens já concluídos são preservados</p>
              <div className="flex gap-3">
                <button onClick={() => setShowPlanModal(false)} className={`px-4 py-2 text-sm font-bold rounded-lg transition-all ${isDark ? 'text-white/40 hover:text-white/70' : 'text-slate-400 hover:text-slate-600'}`}>
                  Cancelar
                </button>
                <button onClick={savePlanDraft} className="px-6 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-black shadow-lg transition-all">
                  Salvar plano
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          NOTIFICATION CENTER
      ══════════════════════════════════════════════════════════ */}
      {/* ══════════════════════════════════════════════════════════
          INSIGHT MODAL
      ══════════════════════════════════════════════════════════ */}
      {showInsightModal && insightState && (
        <div className="fixed inset-0 z-[400] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={handleInsightDiscard} />
          <div className={`relative w-full max-w-md max-h-[90vh] overflow-y-auto custom-scrollbar rounded-2xl border shadow-lg p-6 ${isDark ? 'bg-[#0f1724] border-white/10' : 'bg-white border-[#e5e7eb] dark:border-white/10'}`}>

            {/* Header */}
            <div className="flex items-center gap-3 mb-5">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${insightState.nivel === 1
                ? 'bg-amber-500/20 text-amber-400'
                : insightState.nivel === 3
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : isDark ? 'bg-blue-500/10 text-blue-400' : 'bg-blue-50 text-blue-600'
                }`}>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <div>
                <p className={`text-[9px] font-bold uppercase tracking-wider ${insightState.nivel === 1 ? 'text-amber-400' : insightState.nivel === 3 ? 'text-emerald-400' : isDark ? 'text-blue-400' : 'text-blue-600'}`}>
                  {insightState.nivel === 1 ? 'Insight Crítico' : insightState.nivel === 3 ? 'Laboratório de Ideias' : 'Sugestão de Otimização'}
                </p>
                <p className={`text-[10px] font-bold ${isDark ? 'text-white/50' : 'text-slate-500'}`}>
                  {insightState.alvo === 'diario' ? 'Aplicar ao Diário de Bordo' : insightState.alvo === 'plano' ? 'Aplicar ao Plano de Ação' : 'Explorar Novas Ações'}
                </p>
              </div>
              <button
                onClick={handleInsightDiscard}
                className={`ml-auto p-1.5 rounded-lg transition-all ${isDark ? 'text-white/30 hover:text-white/60 hover:bg-white/10' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'}`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Insight text */}
            <div className={`rounded-lg p-4 mb-4 ${isDark ? 'bg-white/5 border border-white/10' : 'bg-slate-50 border border-[#e5e7eb] dark:border-white/10'}`}>
              <p className={`text-sm leading-relaxed ${isDark ? 'text-white/80' : 'text-slate-700'}`}>
                {insightState.texto}
              </p>
            </div>

            {/* Proposed plan preview (when alvo = plano) */}
            {insightState.alvo === 'plano' && insightState.planoProposto && insightState.planoProposto.length > 0 && (
              <div className={`rounded-lg p-3 mb-4 ${isDark ? 'bg-blue-500/5 border border-blue-500/10' : 'bg-blue-50 border border-blue-100'}`}>
                <p className={`text-[9px] font-bold uppercase tracking-wider mb-2 ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>
                  Plano Proposto
                </p>
                <div className="space-y-1.5">
                  {insightState.planoProposto.map((item, idx) => (
                    <div key={item.id || idx} className={`flex gap-2 text-[11px] ${isDark ? 'text-white/70' : 'text-slate-600'}`}>
                      <span className={`shrink-0 font-black ${isDark ? 'text-blue-400' : 'text-blue-500'}`}>{idx + 1}.</span>
                      <span className={item.completed ? 'line-through opacity-40' : ''}>{item.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Proposed actions (when alvo = acoes) */}
            {insightState.alvo === 'acoes' && insightState.acoesPropostas && insightState.acoesPropostas.length > 0 && (
              <div className="space-y-3 mb-5">
                <p className={`text-[9px] font-bold uppercase tracking-wider ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                  Ideias de Novas Ações
                </p>
                {insightState.acoesPropostas.map((idea, idx) => (
                  <div key={idx} className={`rounded-lg border p-3 flex items-start justify-between gap-3 ${isDark ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10'}`}>
                    <div className="flex-1">
                      <p className={`text-[11px] font-black ${isDark ? 'text-white' : 'text-slate-900'}`}>{idea.titulo}</p>
                      <p className={`text-[10px] leading-relaxed mt-1 ${isDark ? 'text-white/40' : 'text-slate-500'}`}>{idea.descricao}</p>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {idea.tags?.map(tag => (
                          <span key={tag} className={`text-[8px] px-1.5 py-0.5 rounded-lg font-bold uppercase ${isDark ? 'bg-emerald-500/10 text-emerald-400' : 'bg-emerald-50 text-emerald-600'}`}>
                            #{tag}
                          </span>
                        ))}
                      </div>
                    </div>
                    <button
                      onClick={() => handleCreateProposedAction(idea)}
                      className={`shrink-0 p-2 rounded-lg transition-all ${isDark ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30' : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100'}`}
                      title="Criar esta ação agora"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3">
              {insightState.alvo !== 'acoes' && (
                <button
                  onClick={handleInsightApply}
                  className="flex-1 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-bold uppercase tracking-wider transition-all shadow-lg"
                >
                  Aplicar
                </button>
              )}
              {insightState.alvo === 'acoes' && (
                <button
                  onClick={handleInsightDiscard}
                  className="flex-1 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-bold uppercase tracking-wider transition-all shadow-lg"
                >
                  Entendido
                </button>
              )}
              <button
                onClick={handleInsightDiscard}
                className={`flex-1 py-2.5 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-all border ${isDark ? 'border-white/10 text-white/50 hover:bg-white/10' : 'border-[#e5e7eb] dark:border-white/10 text-slate-500 hover:bg-slate-50'}`}
              >
                {insightState.alvo === 'acoes' ? 'Fechar' : 'Descartar'}
              </button>
            </div>

            {/* Ignorar permanentemente — discreto */}
            <div className="mt-3 text-center">
              <button
                onClick={handleInsightIgnore}
                title="O Hermes não voltará a sugerir esta opinião específica nesta ação"
                className={`text-[10px] font-medium transition-all inline-flex items-center gap-1 ${isDark ? 'text-white/30 hover:text-white/60' : 'text-slate-400 hover:text-slate-600'}`}
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" /></svg>
                Não sugerir isto novamente
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          PANEL DE CONTEXTO MODAL (LARGE & QUALIFIED)
      ══════════════════════════════════════════════════════════ */}
      {isContextModalOpen && renderContextModal()}

      {/* ══════════════════════════════════════════════════════════
          MODAL SYSTEM (link / contact / edit / delete / upload / reminder)
      ══════════════════════════════════════════════════════════ */}
      {modalConfig.isOpen && (
        <div className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className={`w-full ${modalConfig.type === 'edit_diary' ? 'max-w-4xl max-h-[90vh]' : 'max-w-md'} p-8 rounded-lg shadow-lg overflow-hidden border-2 ${isDark ? 'bg-[#0a0a0a] text-white border-white/20' : 'bg-white text-slate-900 border-slate-900'}`}>
            <h3 className="text-base font-black mb-4 tracking-tighter">
              {modalConfig.type === 'confirm_delete' ? 'Excluir Registro'
                : modalConfig.type === 'reminder' ? 'Agendar Lembrete'
                  : modalConfig.type === 'edit_diary' ? 'Editar Registro'
                    : modalConfig.type === 'file_upload' ? 'Renomear Arquivos'
                      : modalConfig.type === 'link' ? 'Inserir Link'
                        : 'Inserir Contato'}
            </h3>

            {modalConfig.type === 'edit_diary' && (
              <textarea
                value={modalInputValue}
                onChange={e => setModalInputValue(e.target.value)}
                className={`w-full p-4 rounded-lg border outline-none min-h-[45vh] max-h-[65vh] overflow-y-auto resize-y ${isDark ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10 text-slate-900'}`}
              />
            )}
            {(modalConfig.type === 'link') && (
              <div className="flex flex-col gap-3">
                <input placeholder="Nome" value={modalInputName} onChange={e => setModalInputName(e.target.value)} className={`w-full p-3 rounded-lg border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-[#e5e7eb] dark:border-white/10'}`} />
                <input placeholder="URL" value={modalInputValue} onChange={e => setModalInputValue(e.target.value)} className={`w-full p-3 rounded-lg border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-[#e5e7eb] dark:border-white/10'}`} />
              </div>
            )}
            {(modalConfig.type === 'contact') && (
              <div className="flex flex-col gap-3">
                <input placeholder="Nome do Contato" value={modalInputName} onChange={e => setModalInputName(e.target.value)} className={`w-full p-3 rounded-lg border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-[#e5e7eb] dark:border-white/10'}`} />
                <input placeholder="Telefone / Info" value={modalInputValue} onChange={e => setModalInputValue(e.target.value)} className={`w-full p-3 rounded-lg border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-[#e5e7eb] dark:border-white/10'}`} />
              </div>
            )}
            {modalConfig.type === 'reminder' && (
              <div className="flex flex-col gap-3">
                <input type="date" value={reminderDate} onChange={e => setReminderDate(e.target.value)} className={`w-full p-3 rounded-lg border outline-none ${isDark ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10'}`} />
                <input type="time" value={reminderTime} onChange={e => setReminderTime(e.target.value)} className={`w-full p-3 rounded-lg border outline-none ${isDark ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10'}`} />
                <textarea
                  value={reminderMessage}
                  onChange={e => setReminderMessage(e.target.value)}
                  rows={3}
                  maxLength={500}
                  placeholder="Texto personalizado do lembrete (opcional)"
                  className={`w-full p-3 rounded-lg border outline-none resize-none text-sm ${isDark ? 'bg-white/5 border-white/10 text-white placeholder:text-white/30' : 'bg-slate-50 border-[#e5e7eb] dark:border-white/10 text-slate-900 placeholder:text-slate-400'}`}
                />
              </div>
            )}
            {modalConfig.type === 'confirm_delete' && (
              <p className={`text-sm mb-4 ${isDark ? 'text-white/50' : 'text-slate-500'}`}>Tem certeza que deseja excluir este registro do diário?</p>
            )}
            {modalConfig.type === 'file_upload' && (
              <div className="flex flex-col gap-3">
                {pendingFiles.map((pendingFile, i) => {
                  return (
                    <div key={pendingFile.id}>
                      <p className={`text-[9px] font-bold uppercase tracking-wider mb-1 ${mutedText}`}>Arquivo {i + 1}</p>
                      <input value={pendingFile.customName} onChange={e => setPendingFiles(prev => prev.map(item => item.id === pendingFile.id ? { ...item, customName: e.target.value } : item))}
                        className={`w-full p-3 rounded-lg border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-[#e5e7eb] dark:border-white/10'}`} />
                      <p className={`text-[10px] mt-0.5 ${mutedText}`}>Original: {pendingFile.file.name}</p>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex gap-3 mt-6 justify-end">
              <button onClick={() => { setModalConfig({ ...modalConfig, isOpen: false }); setModalInputValue(''); setModalInputName(''); setReminderMessage(''); setPendingFiles([]); }}
                className={`px-4 py-2 font-bold ${isDark ? 'text-white/40' : 'text-slate-400'}`}>Cancelar</button>
              <button onClick={handleModalConfirm}
                className={`px-6 py-2 rounded-lg font-black text-white shadow-lg transition-all ${modalConfig.type === 'confirm_delete' ? 'bg-rose-600 hover:bg-rose-700' : 'bg-blue-600 hover:bg-blue-700'}`}>
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

