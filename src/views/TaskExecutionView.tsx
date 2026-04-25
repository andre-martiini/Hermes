import React, { useState, useEffect, useMemo, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Tarefa, AppSettings, PoolItem, ConhecimentoItem, Acompanhamento, ActionPlanItem,
  ChatMessage, BaseConhecimento, formatDate, formatDateLocalISO, TaskReminder
} from '../../types';
import { normalizeStatus } from '../utils/helpers';
import { buildDiaryRichNote, ensureHttpUrl, getRenamedFileName, parseDiaryRichNote } from '../utils/diaryEntries';
import { NotificationCenter } from '../components/ui/UIComponents';
import { db, functions } from '../../firebase';
import { httpsCallable } from 'firebase/functions';
import { getAuth } from 'firebase/auth';
import { setDoc, doc, onSnapshot } from 'firebase/firestore';
import { DiarioBordoUI } from './DiarioBordoUI';
import { SpeedDialMenu } from '../components/ui/SpeedDialMenu';
import { HermesCopilotoDrawer } from '../components/tools/HermesCopilotoDrawer';

const getPendingFileKey = (file: File) => `${file.name}-${file.size}-${file.lastModified}`;

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
  onOpenLog: () => void;
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
    reminder_at: nextReminder?.reminder_at || null,
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
  onOpenLog,
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
}: TaskExecutionViewProps) => {

  // ─── Derived Data ─────────────────────────────────────────────
  const currentTaskData = useMemo(() =>
    tarefas.find(t => t.id === task.id) || task,
    [tarefas, task.id, task]
  );

  // ─── States ───────────────────────────────────────────────────
  const [mobileTab, setMobileTab] = useState<MobileTab>('diario');
  const [desktopViewportWidth, setDesktopViewportWidth] = useState(() => window.innerWidth);
  const [planPanelWidth, setPlanPanelWidth] = useState(PLAN_PANEL_DEFAULT_WIDTH);
  const [copilotPanelWidth, setCopilotPanelWidth] = useState(COPILOT_PANEL_DEFAULT_WIDTH);
  const [isPlanCollapsed, setIsPlanCollapsed] = useState(false);
  const [isCopilotCollapsed, setIsCopilotCollapsed] = useState(false);
  const [newFollowUp, setNewFollowUp] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [showPool, setShowPool] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Chat & Artifacts
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(currentTaskData.chat_history || []);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [pendingDeepResearchId, setPendingDeepResearchId] = useState<string | null>(null);
  const [isDeepResearching, setIsDeepResearching] = useState(false);
  const [deepResearchTopic, setDeepResearchTopic] = useState('');
  const [showDeepResearchModal, setShowDeepResearchModal] = useState(false);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [copiedArtifactId, setCopiedArtifactId] = useState<string | null>(null);
  const [isChatFocused, setIsChatFocused] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!pendingDeepResearchId) return;

    // Fallback timer aligned with backend runtime envelope.
    const fallbackTimer = setTimeout(() => {
      setIsDeepResearching(false);
      showToast('A pesquisa profunda pode ter falhado por timeout (mais de 12 minutos).', 'error');
      setPendingDeepResearchId(null);
    }, 12 * 60 * 1000);

    const unsub = onSnapshot(doc(db, 'deep_research_tasks', pendingDeepResearchId), (docSnap) => {
      if (docSnap.exists()) {
        const data = docSnap.data();
        if (data.status === 'COMPLETED' || data.status === 'FAILED' || data.status === 'CANCELLED') {
           setIsDeepResearching(false);
           if (data.status === 'COMPLETED') {
             showToast('Pesquisa Profunda concluída! Verifique o acervo global.', 'success');
           } else if (data.status === 'CANCELLED') {
             showToast('Pesquisa Profunda cancelada.', 'info');
           } else {
             showToast('Pesquisa Profunda falhou.', 'error');
           }
           setPendingDeepResearchId(null);
           clearTimeout(fallbackTimer);
        }
      }
    });

    return () => {
       unsub();
       clearTimeout(fallbackTimer);
    };
  }, [pendingDeepResearchId, showToast]);

  useEffect(() => {
    setChatMessages(currentTaskData.chat_history || []);
  }, [currentTaskData.id]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // Inline editing
  const [editingStatus, setEditingStatus] = useState(false);
  const [pendingStatus, setPendingStatus] = useState(task.status);

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
  const [showReminderHistory, setShowReminderHistory] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [pendingFileNames, setPendingFileNames] = useState<Record<string, string>>({});
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  const streamRef = useRef<MediaStream | null>(null);

  // Plan modal
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [planDraft, setPlanDraft] = useState<ActionPlanItem[]>([]);
  const [newPlanItemText, setNewPlanItemText] = useState('');
  const newPlanItemRef = useRef<HTMLInputElement>(null);

  // Proposal editing (Feature 1 & 2)
  const [editingProposal, setEditingProposal] = useState<{ msgIndex: number; items: ActionPlanItem[] } | null>(null);

  // Progressive plan adjustment (Feature 3)
  const [showPlanSuggestion, setShowPlanSuggestion] = useState(false);

  // Plan history viewer (Feature 5)
  const [showPlanHistory, setShowPlanHistory] = useState(false);

  // Tags
  const [tagInput, setTagInput] = useState('');
  const [isGeneratingTags, setIsGeneratingTags] = useState(false);
  const existingTags = useMemo(() => Array.from(new Set(tarefas.flatMap(t => t.tags || []))), [tarefas]);

  // Knowledge Graph citations: msgIndex → lista de nós do grafo retornados pelo backend
  const [kgNodesByMsg, setKgNodesByMsg] = useState<Record<number, Array<{ node_id: string; titulo: string; resumo?: string; n_tasks?: number }>>>({});

  // Knowledge panel
  const [showKnowledgePanel, setShowKnowledgePanel] = useState(false);
  const [sessionExtraFiles, setSessionExtraFiles] = useState<{ id: string; name: string; status: 'uploading' | 'ready' | 'error' }[]>([]);
  const [isUploadingExtra, setIsUploadingExtra] = useState(false);
  const extraFileInputRef = useRef<HTMLInputElement>(null);

  // Audio / transcription
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessingTranscription, setIsProcessingTranscription] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const diaryEndRef = useRef<HTMLDivElement>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);

  const isBreakActive = false;
  const isDesktopViewport = desktopViewportWidth >= DESKTOP_BREAKPOINT;

  const progressPercent = useMemo(() => {
    const items = currentTaskData.plano_acao || [];
    if (items.length === 0) return 0;
    const done = items.filter(i => i.completed).length;
    return Math.round((done / items.length) * 100);
  }, [currentTaskData.plano_acao]);

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

    onSave(task.id, {
      plano_acao: updated,
      acompanhamento: updatedAcompanhamento
    });

    // Feature 3: sugere revisão do plano restante quando uma etapa é concluída
    if (newCompleted) {
      const remaining = updated.filter(i => !i.completed);
      if (remaining.length > 0) setShowPlanSuggestion(true);
    }
  };

  const openReminderModal = (reminder?: TaskReminder) => {
    const baseIso = reminder?.reminder_at || nextPendingReminder?.reminder_at;
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

  // Feature 3: envia mensagem ao copiloto para revisar etapas restantes
  const handleSuggestPlanAdjustment = () => {
    const completed = (currentTaskData.plano_acao || []).filter(i => i.completed);
    const remaining = (currentTaskData.plano_acao || []).filter(i => !i.completed);
    const msg = `Revisar plano: concluí ${completed.map(i => `"${i.text}"`).join(', ')}. Etapas restantes: ${remaining.map((i, idx) => `${idx + 1}. ${i.text}`).join('; ')}. O plano restante ainda faz sentido ou deve ser ajustado com base no que foi feito?`;
    setShowPlanSuggestion(false);
    sendChatMessage(msg);
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
  const handleFileUpload = async (files: Array<{ file: File; customName?: string }>) => {
    if (files.length === 0) return [];
    setIsUploading(true);
    const uploadFunc = httpsCallable(functions, 'upload_to_drive');
    const uploadedItems: PoolItem[] = [];
    try {
      for (const { file, customName } of files) {
        const finalName = getRenamedFileName(file.name, customName);
        const b64 = await new Promise<string>((res, rej) => {
          const r = new FileReader();
          r.onload = () => res((r.result as string).split(',')[1]);
          r.onerror = rej;
          r.readAsDataURL(file);
        });
        const result = await uploadFunc({ fileName: finalName, fileContent: b64, mimeType: file.type, folderId: appSettings.googleDriveFolderId });
        const d = result.data as any;
        const item: PoolItem = { id: Math.random().toString(36).substring(2, 11), tipo: 'arquivo', valor: d.webViewLink, nome: finalName, data_criacao: new Date().toISOString() };
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
      showToast('Erro ao carregar para o Drive.', 'error');
      return [];
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileUploadInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files ? Array.from(e.target.files) : [];
    if (selectedFiles.length === 0) return;
    handleDiaryFilesSelected(selectedFiles);
    e.target.value = '';
  };

  const handleDiaryFilesSelected = (selectedFiles: File[]) => {
    if (selectedFiles.length === 0) return;
    const initialNames = selectedFiles.reduce((acc, f) => { acc[getPendingFileKey(f)] = f.name; return acc; }, {} as Record<string, string>);
    setPendingFiles(selectedFiles);
    setPendingFileNames(initialNames);
    setModalConfig({ type: 'file_upload', isOpen: true });
    setShowAttachMenu(false);
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
        const blob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
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
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const b64 = (reader.result as string).split(',')[1];
          const fn = httpsCallable(functions, 'transcreverAudio');
          const res = await fn({ audioBase64: b64 });
          const data = res.data as { raw: string; refined: string };
          if (data.refined) setter(prev => prev + (prev ? '\n' : '') + data.refined);
        } catch { showToast('Erro ao processar áudio.', 'error'); }
        finally { setIsProcessingTranscription(false); }
      };
    } catch { setIsProcessingTranscription(false); }
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
          };
          onSave(task.id, buildReminderPayload([...taskReminders.filter(reminder => reminder.id !== 'legacy-reminder'), newReminder]));
          showToast('Lembrete agendado!', 'success');
        }
        break;
      case 'file_upload':
        if (pendingFiles.length > 0) {
          const filesToUpload = pendingFiles.map(f => ({ file: f, customName: pendingFileNames[getPendingFileKey(f)] }));
          setModalConfig({ ...modalConfig, isOpen: false });
          setPendingFiles([]);
          setPendingFileNames({});
          handleFileUpload(filesToUpload);
          return;
        }
        break;
    }
    setModalConfig({ ...modalConfig, isOpen: false });
    setModalInputValue('');
    setModalInputName('');
    setPendingFiles([]);
    setPendingFileNames({});
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
    const appliedPlan = customPlan || msg.proposedPlan!;

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

    onSave(task.id, {
      plano_acao: appliedPlan,
      plano_acao_historico: updatedHistory,
      chat_history: newHistory
    });
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
          proposedPlan = JSON.parse(proposalMatch[1].trim());
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

    if (msg.startsWith('/pesquisa-profunda')) {
      const topic = msg.replace('/pesquisa-profunda', '').trim();
      if (!topic) {
        showToast('Por favor, informe um tema. Ex: /pesquisa-profunda Inteligência Artificial', 'warning');
        return;
      }
      setDeepResearchTopic(topic);
      setShowDeepResearchModal(true);
      return;
    }

    if (msg.startsWith('/cancelar-pesquisa')) {
      const parts = msg.split(' ');
      const idToCancel = parts.length > 1 ? parts[1] : pendingDeepResearchId;
      if (!idToCancel) {
         showToast('Nenhuma pesquisa em andamento ou ID inválido.', 'warning');
         return;
      }
      try {
         const fn = httpsCallable(functions, 'cancelDeepResearch');
         await fn({ taskId: idToCancel });
         showToast('Solicitação de cancelamento enviada.', 'success');
      } catch (e) {
         console.error('Erro ao cancelar:', e);
         showToast('Erro ao cancelar pesquisa.', 'error');
      }
      return;
    }

    sendChatMessage(msg);
  };

  const confirmDeepResearch = async () => {
    const topic = deepResearchTopic.trim();
    if (!topic) {
      setShowDeepResearchModal(false);
      showToast('Por favor, informe um tema para a pesquisa profunda.', 'warning');
      return;
    }

    const auth = getAuth();
    const currentUser = auth.currentUser;
    if (!currentUser) {
      setShowDeepResearchModal(false);
      showToast('Você precisa estar autenticado para iniciar a pesquisa profunda.', 'error');
      return;
    }

    setShowDeepResearchModal(false);
    setIsDeepResearching(true);

    // Add to chat immediately
    const userMsg: ChatMessage = { role: 'user', content: `/pesquisa-profunda ${topic}` };
    const sysMsg: ChatMessage = { role: 'assistant', content: `Iniciando pesquisa profunda sobre: "${topic}". Isso pode levar cerca de 8 a 9 minutos. Use /cancelar-pesquisa para interromper.` };
    const updatedHistory = [...chatMessages, userMsg, sysMsg];
    setChatMessages(updatedHistory);
    onSave(task.id, { chat_history: updatedHistory });

    try {
      const fn = httpsCallable(functions, 'startDeepResearch');
      const res = await fn({ topic });
      const data = res.data as { taskId: string };
      setPendingDeepResearchId(data.taskId);
      showToast(`Pesquisa iniciada. ID: ${data.taskId}`, 'success');
      setDeepResearchTopic('');
    } catch (e) {
      console.error(e);
      showToast('Erro ao iniciar pesquisa profunda.', 'error');
      setIsDeepResearching(false);
    }
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
    setPlanDraft((currentTaskData.plano_acao || []).map(i => ({ ...i })));
    setNewPlanItemText('');
    setShowPlanModal(true);
  };

  const addPlanDraftItem = () => {
    const text = newPlanItemText.trim();
    if (!text) return;
    setPlanDraft(prev => [...prev, { id: crypto.randomUUID(), text, completed: false }]);
    setNewPlanItemText('');
    setTimeout(() => newPlanItemRef.current?.focus(), 50);
  };

  const savePlanDraft = () => {
    onSave(task.id, { plano_acao: planDraft });
    setShowPlanModal(false);
    showToast('Plano atualizado!', 'success');
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
  const bg = isDark ? 'bg-[#050505] text-white' : 'bg-[#F0F2F5] text-slate-900';
  const cardBg = isDark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200';
  const mutedText = isDark ? 'text-white/40' : 'text-slate-400';
  const labelCls = `text-[9px] font-black uppercase tracking-widest ${mutedText}`;

  // ─── Status color ─────────────────────────────────────────────
  const statusColor = (s: string) => {
    if (s === 'em andamento') return 'bg-blue-500/15 text-blue-400 border-blue-500/30';
    if (s === 'stand-by') return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
    return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
  };

  // ─── Columns visibility (mobile tabs) ────────────────────────
  const showMapa = mobileTab === 'mapa';
  const showDiario = mobileTab === 'diario';
  const showCopiloto = mobileTab === 'copiloto';

  // ─── Derived knowledge base from area_tematica ───────────────
  const derivedKnowledgeBase = (() => {
    const area = (currentTaskData.area_tematica || '').toUpperCase();
    if (!area || area === 'GERAL' || area === 'NÃO CLASSIFICADA') return null;
    const unit = unidades.find(u => u.nome.toUpperCase() === area);
    return unit ? (knowledgeBases.find(b => b.sistema_id === unit.id) ?? null) : null;
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
    <div className={`hidden lg:flex h-full shrink-0 flex-col items-center justify-between rounded-2xl border px-2 py-4 ${cardBg}`}>
      <button
        onClick={onExpand}
        className={`flex h-8 w-8 items-center justify-center rounded-xl border transition-all ${isDark ? 'border-white/10 text-white/70 hover:bg-white/10 hover:text-white' : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-900'}`}
        title={`Expandir ${title}`}
      >
        <svg className={`h-4 w-4 ${panel === 'plan' ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <div className="flex flex-1 flex-col items-center justify-center gap-3">
        <span className={`text-[8px] font-black uppercase tracking-[0.35em] [writing-mode:vertical-rl] rotate-180 ${mutedText}`}>{subtitle}</span>
        <span className={`text-[9px] font-black uppercase tracking-widest [writing-mode:vertical-rl] rotate-180 ${isDark ? 'text-white/80' : 'text-slate-700'}`}>{title}</span>
      </div>
      <div className={`h-8 w-1 rounded-full ${isDark ? 'bg-white/10' : 'bg-slate-200'}`} />
    </div>
  );

  const renderResizeHandle = (panel: DesktopPanel) => (
    <div
      onMouseDown={(event) => startDesktopResize(panel, event)}
      className="group hidden lg:flex w-3 shrink-0 cursor-ew-resize items-center justify-center"
      title="Arrastar para redimensionar"
    >
      <div className={`h-14 w-1 rounded-full transition-all ${isDark ? 'bg-white/10 group-hover:bg-blue-400/60' : 'bg-slate-300 group-hover:bg-blue-500/60'}`} />
    </div>
  );

  // ─── Render ───────────────────────────────────────────────────
  return (
    <div className={`fixed inset-0 z-[200] flex flex-col overflow-hidden transition-colors duration-700 ${bg} ${isBreakActive ? '!bg-[#1a0b0b]' : ''}`}>

      {/* ══════════════════════════════════════════════════════════
          HEADER BAR
      ══════════════════════════════════════════════════════════ */}
      <header className={`shrink-0 px-4 md:px-6 py-3 border-b flex flex-col gap-2 ${isDark ? 'border-white/10 bg-black/30' : 'border-slate-200 bg-white/80 backdrop-blur-sm'}`}>
        {/* Row 1: nav + title + controls */}
        <div className="hidden">
          {/* Back */}
          <div className="flex items-start justify-between gap-4">

          {/* Label + Title */}
          <div className="order-3 sm:order-2 flex-1 min-w-0 w-full sm:w-auto">
            <p className={`text-[8px] font-black uppercase tracking-[0.3em] ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Sala de Operações</p>
            <h1 className={`text-base md:text-xl font-black tracking-tight leading-tight break-words whitespace-normal ${isDark ? 'text-white' : 'text-slate-900'}`}>
              {currentTaskData.titulo}
            </h1>
          </div>

          <div className="order-2 sm:order-3 shrink-0 flex items-center gap-2">
            <SpeedDialMenu
              notifications={notifications}
              isSyncing={isSyncing}
              isNotificationCenterOpen={isNotificationCenterOpen}
              onOpenNotes={onOpenNotes}
              onOpenLog={onOpenLog}
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
              direction="down"
            />
            {/* Status inline selector */}
            <select
              value={currentTaskData.status}
              onChange={e => handleStatusChange(e.target.value)}
              className={`shrink-0 text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-xl border appearance-none cursor-pointer outline-none focus:ring-2 focus:ring-blue-500 transition-all ${statusColor(currentTaskData.status)} ${isDark ? 'bg-transparent' : 'bg-white'}`}
            >
              <option value="em andamento">Em Andamento</option>
              <option value="stand-by">Stand-by</option>
              <option value="conclu?do">Conclu?do</option>
            </select>
          </div>

        </div>
        </div>

        <div className="sm:hidden flex flex-col gap-4 py-1">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <p className={`text-[10px] font-black uppercase tracking-[0.22em] ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>{'Sala de Opera\u00e7\u00f5es'}</p>
              <h1 className={`mt-2 text-[1rem] font-black leading-[1.12] tracking-tight break-words ${isDark ? 'text-white' : 'text-slate-900'}`}>
                {currentTaskData.titulo}
              </h1>
            </div>

            <div className="shrink-0 pt-1">
              <SpeedDialMenu
                notifications={notifications}
                isSyncing={isSyncing}
                isNotificationCenterOpen={isNotificationCenterOpen}
                onOpenNotes={onOpenNotes}
                onOpenLog={onOpenLog}
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
                direction="down"
                triggerClassName="flex h-12 w-12 items-center justify-center rounded-[1.2rem] bg-white text-slate-700 border border-slate-200 shadow-[0_8px_18px_rgba(15,23,42,0.18)]"
                triggerIconClassName="h-5 w-5"
              />
            </div>
          </div>

          <div className="relative flex min-h-[44px] items-center justify-center">
            <button onClick={onClose} className={`absolute left-0 top-1/2 shrink-0 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-2xl transition-all ${isDark ? 'text-white/30 hover:text-white hover:bg-white/10' : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'}`}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>

            <select
              value={currentTaskData.status}
              onChange={e => handleStatusChange(e.target.value)}
              className={`mx-auto min-w-[92px] max-w-full text-center text-[8px] font-black uppercase tracking-[0.16em] px-3 py-1.5 rounded-full border appearance-none cursor-pointer outline-none focus:ring-2 focus:ring-blue-500 transition-all ${statusColor(currentTaskData.status)} ${isDark ? 'bg-transparent' : 'bg-white'}`}
            >
              <option value="em andamento">Em Andamento</option>
              <option value="stand-by">Stand-by</option>
              <option value="conclu?do">Conclu?do</option>
            </select>
          </div>
        </div>

        <div className="hidden sm:flex flex-wrap items-center gap-x-3 gap-y-2">
          <button onClick={onClose} className={`order-1 shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${isDark ? 'text-white/40 hover:text-white hover:bg-white/10' : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'}`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            <span className="hidden sm:inline">Voltar</span>
          </button>

          <div className="order-3 sm:order-2 flex-1 min-w-0 w-full sm:w-auto">
            <p className={`text-[8px] font-black uppercase tracking-[0.3em] ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Sala de Operações</p>
            <h1 className={`text-base md:text-xl font-black tracking-tight leading-tight break-words whitespace-normal ${isDark ? 'text-white' : 'text-slate-900'}`}>
              {currentTaskData.titulo}
            </h1>
          </div>

          <div className="order-2 sm:order-3 shrink-0 flex items-center gap-2">
            <SpeedDialMenu
              notifications={notifications}
              isSyncing={isSyncing}
              isNotificationCenterOpen={isNotificationCenterOpen}
              onOpenNotes={onOpenNotes}
              onOpenLog={onOpenLog}
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
              direction="down"
            />
            <select
              value={currentTaskData.status}
              onChange={e => handleStatusChange(e.target.value)}
              className={`shrink-0 text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-xl border appearance-none cursor-pointer outline-none focus:ring-2 focus:ring-blue-500 transition-all ${statusColor(currentTaskData.status)} ${isDark ? 'bg-transparent' : 'bg-white'}`}
            >
              <option value="em andamento">Em Andamento</option>
              <option value="stand-by">Stand-by</option>
              <option value="conclu?do">Conclu?do</option>
            </select>
          </div>
        </div>

        {/* Row 2: Progress bar */}
        {(currentTaskData.plano_acao || []).length > 0 && (
          <div className="flex items-center gap-3">
            <div className={`flex-1 h-1.5 rounded-full overflow-hidden ${isDark ? 'bg-white/10' : 'bg-slate-200'}`}>
              <div
                className={`h-full rounded-full transition-all duration-500 ${progressPercent === 100 ? 'bg-emerald-500' : 'bg-blue-500'}`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <span className={`text-[9px] font-black uppercase tracking-widest shrink-0 ${progressPercent === 100 ? (isDark ? 'text-emerald-400' : 'text-emerald-600') : mutedText}`}>
              {progressPercent}%
            </span>
          </div>
        )}
      </header>

      {/* ══════════════════════════════════════════════════════════
          MOBILE TAB BAR
      ══════════════════════════════════════════════════════════ */}
      <nav className={`lg:hidden shrink-0 flex border-b ${isDark ? 'border-white/10 bg-black/20' : 'border-slate-200 bg-white/60'}`}>
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
              className={`flex-1 flex flex-col items-center gap-1 py-2.5 text-[9px] font-black uppercase tracking-widest transition-all border-b-2 ${active
                ? isDark ? 'border-blue-400 text-blue-400' : 'border-blue-600 text-blue-600'
                : `border-transparent ${mutedText}`
                }`}
            >
              {icons[tab]}
              {labels[tab]}
            </button>
          );
        })}
      </nav>

      {/* ══════════════════════════════════════════════════════════
          MAIN CONTENT — 3-column desktop / single tab mobile
      ══════════════════════════════════════════════════════════ */}
      <div ref={workspaceRef} className="flex-1 min-h-0 flex flex-col gap-0 overflow-hidden lg:flex-row lg:gap-0 lg:p-4">

        {/* LEFT COLUMN — Mapa Operacional */}
        {isPlanPanelCollapsed ? (
          renderCollapsedPanelRail('plan', 'Plano', 'Sala de Operações', () => setIsPlanCollapsed(false))
        ) : (
        <>
        <div className={`flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4 lg:flex-none lg:p-0 ${!showMapa ? 'hidden lg:flex' : 'flex'} shrink-0`}
          style={{ scrollbarWidth: 'thin', scrollbarColor: '#CBD5E0 transparent', width: isDesktopViewport ? mapPanelDesktopWidth : undefined }}>
          <div className="hidden lg:flex items-center justify-between px-1 pb-1">
            <div>
              <p className={labelCls}>Plano de Ação</p>
              <p className={`text-[11px] font-bold ${isDark ? 'text-white/70' : 'text-slate-700'}`}>Mapa operacional da ação</p>
            </div>
            <button
              onClick={() => setIsPlanCollapsed(true)}
              className={`flex h-8 w-8 items-center justify-center rounded-xl border transition-all ${isDark ? 'border-white/10 text-white/50 hover:bg-white/10 hover:text-white' : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-900'}`}
              title="Retrair plano de ação"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          </div>

          {/* Síntese / Descrição */}
          {currentTaskData.descricao && (
            <div className={`rounded-2xl border p-4 ${cardBg}`}>
              <p className={`${labelCls} mb-2`}>Síntese da Demanda</p>
              <p className={`text-xs leading-relaxed ${isDark ? 'text-white/70' : 'text-slate-600'}`}>
                {currentTaskData.descricao}
              </p>
            </div>
          )}

          {/* Área Temática */}
          <div className={`rounded-2xl border p-4 ${cardBg}`}>
            <p className={`${labelCls} mb-2`}>Área Temática</p>
            <select
              value={currentTaskData.area_tematica || 'NÃO CLASSIFICADA'}
              onChange={e => {
                const newArea = e.target.value as any;
                const unit = unidades.find(u => u.nome.toUpperCase() === (newArea || '').toUpperCase());
                const baseId = unit ? (knowledgeBases.find(b => b.sistema_id === unit.id)?.id ?? undefined) : undefined;
                onSave(task.id, { area_tematica: newArea, base_conhecimento: baseId });
              }}
              style={{ colorScheme: isDark ? 'dark' : 'light' }}
              className={`w-full border-none p-0 text-xs font-black uppercase tracking-widest focus:ring-0 cursor-pointer ${isDark ? 'bg-slate-900 text-white' : 'bg-transparent text-slate-900'}`}
            >
              <option className={isDark ? 'bg-slate-900 text-white' : 'bg-white text-slate-900'} value="GERAL">Geral</option>
              <option className={isDark ? 'bg-slate-900 text-white' : 'bg-white text-slate-900'} value="NÃO CLASSIFICADA">Não Classificada</option>
              {unidades.map(u => (
                <option className={isDark ? 'bg-slate-900 text-white' : 'bg-white text-slate-900'} key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
              ))}
            </select>
          </div>

          {/* Tags Dinâmicas */}
          <div className={`rounded-2xl border p-4 ${cardBg}`}>
            <div className="flex items-center justify-between mb-3">
              <p className={labelCls}>Tags Dinâmicas</p>
              <button
                onClick={handleAutoClassifyTags}
                disabled={isGeneratingTags}
                className="flex items-center gap-1.5 px-2 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg transition-colors text-[9px] font-black uppercase tracking-widest border border-indigo-100 disabled:opacity-50"
              >
                {isGeneratingTags ? '...' : '✨ Auto'}
              </button>
            </div>
            <div className="flex flex-wrap gap-2 mb-3">
              {(currentTaskData.tags || []).map(tag => (
                <span key={tag} className="flex items-center gap-1 bg-indigo-50 text-indigo-600 px-2.5 py-1 rounded-lg text-[10px] font-bold border border-indigo-100">
                  #{tag}
                  <button onClick={(e) => {
                    e.preventDefault();
                    const newTags = (currentTaskData.tags || []).filter(t => t !== tag);
                    onSave(task.id, { tags: newTags });
                  }} className="text-indigo-400 hover:text-rose-500 scale-125 ml-1 transition-colors">&times;</button>
                </span>
              ))}
              {(currentTaskData.tags || []).length === 0 && (
                <span className="text-[10px] text-slate-400 font-medium italic">Nenhuma tag...</span>
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
                  className={`flex-1 border rounded-lg px-3 py-1.5 text-[11px] font-medium focus:ring-1 focus:ring-indigo-500 outline-none ${isDark ? 'bg-black/50 border-white/10 text-white' : 'bg-slate-50 border-slate-200 text-slate-700'}`}
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
                  className={`px-3 py-1.5 rounded-lg transition-all text-[10px] font-bold border ${isDark ? 'bg-white/10 text-white/70 border-white/20 hover:bg-white/20' : 'bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200'}`}
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

          {/* Plano de Ação */}
          <div className={`rounded-2xl border ${cardBg}`}>
            <div className="px-4 pt-4 pb-2 flex items-center justify-between">
              <p className={labelCls}>Plano de Ação</p>
              <div className="flex items-center gap-2">
                <span className={`text-[9px] font-black ${progressPercent === 100 ? 'text-emerald-500' : mutedText}`}>
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
            <div className="px-3 pb-3 space-y-1.5">
              {(currentTaskData.plano_acao || []).length === 0 ? (
                <p className={`text-xs text-center py-4 ${mutedText}`}>Nenhum passo no plano.</p>
              ) : (
                (currentTaskData.plano_acao || []).map(item => (
                  <button
                    key={item.id}
                    onClick={() => handleToggleChecklistItem(item.id)}
                    className={`w-full flex items-start gap-3 p-2.5 rounded-xl text-left transition-all group ${isDark ? 'hover:bg-white/5' : 'hover:bg-slate-50'}`}
                  >
                    <div className={`w-4 h-4 mt-0.5 rounded border-2 flex items-center justify-center shrink-0 transition-all ${item.completed
                      ? 'bg-emerald-500 border-emerald-500'
                      : isDark ? 'border-white/30 group-hover:border-emerald-400' : 'border-slate-300 group-hover:border-emerald-500'
                      }`}>
                      {item.completed && (
                        <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                    <span className={`text-xs font-medium leading-snug transition-all ${item.completed
                      ? isDark ? 'text-white/30 line-through' : 'text-slate-300 line-through'
                      : isDark ? 'text-white/80' : 'text-slate-700'
                      }`}>
                      {item.text}
                    </span>
                  </button>
                ))
              )}
            </div>

            {/* Feature 3: sugestão de revisão após concluir etapa */}
            {showPlanSuggestion && (
              <div className={`mx-3 mb-3 flex items-center gap-2 p-2 rounded-xl border ${isDark ? 'bg-blue-500/10 border-blue-500/20' : 'bg-blue-50 border-blue-200'}`}>
                <svg className="w-3 h-3 text-blue-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                <span className={`flex-1 text-[9px] ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>Revisar plano com base no progresso?</span>
                <button onClick={handleSuggestPlanAdjustment} className="text-[9px] font-black text-blue-400 hover:text-blue-300 uppercase tracking-widest px-2">Sim</button>
                <button onClick={() => setShowPlanSuggestion(false)} className={`text-[9px] ${isDark ? 'text-white/30 hover:text-white/50' : 'text-slate-400 hover:text-slate-600'}`}>Ignorar</button>
              </div>
            )}

            {/* Feature 5: histórico de versões do plano */}
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
                      <div key={vIdx} className={`p-2 rounded-xl border ${isDark ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-200'}`}>
                        <div className="flex items-center justify-between mb-1.5">
                          <p className={`text-[8px] font-black uppercase tracking-widest ${mutedText}`}>
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

          {/* Pool de Dados */}
          <div className={`rounded-2xl border ${cardBg} shrink-0`}>
            <button onClick={() => setShowPool(!showPool)} className="w-full flex items-center gap-2 px-4 py-3">
              <svg className={`w-3.5 h-3.5 ${mutedText}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
              <span className={`${labelCls} flex-1 text-left`}>Pool de Dados</span>
              <span className={`text-[9px] font-bold ${mutedText}`}>{(currentTaskData.pool_dados || []).length}</span>
              <svg className={`w-3 h-3 transition-transform ${mutedText} ${showPool ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" strokeWidth="2.5" /></svg>
            </button>
            {showPool && (
              <div className="px-3 pb-3 flex flex-wrap gap-2 max-h-36 overflow-y-auto">
                {(currentTaskData.pool_dados || []).length === 0 ? (
                  <p className={`text-xs ${mutedText} w-full text-center py-2`}>Nenhum item no pool.</p>
                ) : (
                  (currentTaskData.pool_dados || []).map(item => (
                    <button key={item.id} onClick={() => window.open(item.valor, '_blank')}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all ${isDark ? 'bg-white/10 border-white/10 text-white/70 hover:bg-white/20' : 'bg-slate-50 border-slate-100 text-slate-700 hover:bg-blue-50 hover:border-blue-200'}`}>
                      <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                      <span className="truncate max-w-[120px]">{item.nome || item.valor}</span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Planejamento compacto */}
          <div className={`rounded-2xl border p-4 ${cardBg}`}>
            <p className={`${labelCls} mb-3`}>Planejamento</p>
            <div className="space-y-3">
              <div>
                <p className={`${labelCls} mb-1`}>Prazo Final</p>
                <input type="date" value={currentTaskData.data_limite || ''} onChange={e => onSave(task.id, { data_limite: e.target.value })}
                  className={`w-full px-3 py-2 rounded-xl text-xs font-bold outline-none focus:ring-2 focus:ring-blue-500 border transition-all ${isDark ? 'bg-white/10 border-white/10 text-white' : 'bg-slate-50 border-slate-100 text-slate-900'}`} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <p className={`${labelCls} mb-1`}>Início</p>
                  <input type="time" value={currentTaskData.horario_inicio || ''} onChange={e => onSave(task.id, { horario_inicio: e.target.value })}
                    className={`w-full px-3 py-2 rounded-xl text-xs font-bold outline-none focus:ring-2 focus:ring-blue-500 border transition-all ${isDark ? 'bg-white/10 border-white/10 text-white' : 'bg-slate-50 border-slate-100 text-slate-900'}`} />
                </div>
                <div>
                  <p className={`${labelCls} mb-1`}>Fim</p>
                  <input type="time" value={currentTaskData.horario_fim || ''} onChange={e => onSave(task.id, { horario_fim: e.target.value })}
                    className={`w-full px-3 py-2 rounded-xl text-xs font-bold outline-none focus:ring-2 focus:ring-blue-500 border transition-all ${isDark ? 'bg-white/10 border-white/10 text-white' : 'bg-slate-50 border-slate-100 text-slate-900'}`} />
                </div>
              </div>
              {taskReminders.length > 0 && (
                <div className={`rounded-xl border px-3 py-2 ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-200 bg-slate-50'}`}>
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
                      <p className={`text-[10px] font-black uppercase tracking-widest ${isDark ? 'text-white/75' : 'text-slate-700'}`}>Lembretes</p>
                      <p className={`text-[10px] truncate ${mutedText}`}>
                        {nextPendingReminder
                          ? `Próximo: ${new Date(nextPendingReminder.reminder_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}`
                          : 'Todos os lembretes já foram enviados'}
                      </p>
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-[9px] font-black ${pendingReminderCount > 0
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
                          className={`flex items-center gap-2 rounded-xl border px-2.5 py-2 ${reminder.reminder_sent
                            ? isDark ? 'border-white/10 bg-white/5 text-white/45' : 'border-slate-200 bg-white text-slate-400'
                            : isDark ? 'border-amber-500/20 bg-amber-500/10 text-white' : 'border-amber-200 bg-amber-50 text-slate-700'
                            }`}
                        >
                          <div className={`w-2 h-2 rounded-full shrink-0 ${reminder.reminder_sent ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                          <div className="min-w-0 flex-1">
                            <p className="text-[11px] font-bold">
                              {new Date(reminder.reminder_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}
                            </p>
                            <p className={`text-[9px] ${reminder.reminder_sent ? mutedText : isDark ? 'text-amber-200' : 'text-amber-700'}`}>
                              {reminder.reminder_sent ? 'Enviado' : 'Agendado'}
                            </p>
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
                className={`w-full flex items-center justify-center gap-2 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-all ${pendingReminderCount > 0
                  ? isDark ? 'border-amber-500/20 text-amber-300 hover:bg-amber-500/10' : 'border-amber-200 text-amber-700 hover:bg-amber-50'
                  : isDark ? 'border-white/10 text-white/40 hover:bg-white/5 hover:text-white/70' : 'border-slate-200 text-slate-400 hover:bg-slate-50 hover:text-slate-700'
                  }`}>
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                {taskReminders.length > 0 ? 'Novo Lembrete' : 'Agendar Lembrete'}
              </button>
            </div>
          </div>

          {/* Fontes de Conhecimento */}
          <div className={`rounded-2xl border ${cardBg} shrink-0`}>
            <button onClick={() => setShowKnowledgePanel(!showKnowledgePanel)} className="w-full flex items-center gap-2 px-4 py-3">
              <svg className={`w-3.5 h-3.5 ${mutedText}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
              <span className={`${labelCls} flex-1 text-left`}>Fontes de Conhecimento</span>
              {(currentTaskData.base_conhecimento || currentTaskData.extra_context_id) && (
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
              )}
              <svg className={`w-3 h-3 transition-transform ${mutedText} ${showKnowledgePanel ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" strokeWidth="2.5" /></svg>
            </button>
            {showKnowledgePanel && (
              <div className="px-4 pb-4 space-y-4">

                {/* Base RAG — derivada automaticamente da Área Temática */}
                <div>
                  <p className={`${labelCls} mb-1.5`}>Base de Conhecimento (RAG)</p>
                  {derivedKnowledgeBase ? (
                    <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-bold ${isDark ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`}>
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
                  <p className={`${labelCls} mb-1.5`}>Contexto Complementar</p>

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
                    className={`w-full flex items-center justify-center gap-2 py-2 rounded-xl border border-dashed text-[10px] font-black uppercase tracking-widest transition-all disabled:opacity-40 ${isDark ? 'border-white/20 text-white/40 hover:border-blue-400/40 hover:text-blue-300 hover:bg-blue-500/5' : 'border-slate-300 text-slate-400 hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50'}`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>
                    {isUploadingExtra ? 'Processando…' : 'Adicionar arquivo'}
                  </button>
                  <p className={`text-[8px] text-center mt-1 ${mutedText}`}>PDF · TXT · MD — isolado da Base RAG</p>
                  <input ref={extraFileInputRef} type="file" accept=".pdf,.txt,.md" className="hidden" onChange={handleUploadExtraContextFile} />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* CENTER COLUMN — Diário de Missão */}
        </>
        )}

        {!isPlanPanelCollapsed && renderResizeHandle('plan')}

        <div className={`flex min-w-0 flex-1 flex-col overflow-hidden ${!showDiario ? 'hidden lg:flex' : 'flex'} min-h-0`}>
          <div className={`flex-1 flex flex-col rounded-none lg:rounded-2xl border overflow-hidden ${isDark ? 'bg-[#0f1724] border-white/10' : 'bg-white border-slate-200'}`}>
            {/* Diary header */}
            <div className={`shrink-0 px-4 py-3 flex items-center justify-between border-b ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
              <div className="flex items-center gap-2">
                <svg className={`w-4 h-4 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
                <span className={labelCls}>Diário de Missão</span>
              </div>
              <button onClick={handleSummarizeWithAI}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all ${isDark ? 'bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500/30' : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100 border border-indigo-200'}`}>
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                Resumir com IA
              </button>
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
              isTimerRunning={isDark}
              diaryEndRef={diaryEndRef}
              handleDiaryScroll={() => { }}
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
            className={`${showCopiloto ? 'flex' : 'hidden'} lg:flex min-h-0 shrink-0 flex-col`}
            style={{ width: isDesktopViewport ? copilotoDesktopWidth : undefined }}
          >
            <HermesCopilotoDrawer
              isOpen
              onClose={() => setIsCopilotCollapsed(true)}
              isDark={isDark}
              variant="embedded"
              taskId={task.id}
              systemId={currentTaskData.sistema_id}
              userId={copilotoUserId}
              onOpenTask={onOpenCopilotoTask}
              onOpenTool={onOpenCopilotoTool}
            />
          </div>
        )}

      </div>

      {/* ══════════════════════════════════════════════════════════
          PLAN EDIT MODAL
      ══════════════════════════════════════════════════════════ */}
      {showPlanModal && (
        <div className="fixed inset-0 z-[350] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className={`w-full max-w-lg rounded-3xl shadow-2xl flex flex-col max-h-[85vh] ${isDark ? 'bg-[#0f0f1a] border border-white/10 text-white' : 'bg-white text-slate-900'}`}>

            {/* Header */}
            <div className={`shrink-0 px-6 py-5 border-b flex items-center justify-between ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
              <div>
                <h3 className="text-base font-black tracking-tight">Editar Plano de Ação</h3>
                <p className={`text-[10px] mt-0.5 ${mutedText}`}>{planDraft.length} {planDraft.length === 1 ? 'passo' : 'passos'} · clique no texto para editar</p>
              </div>
              <button onClick={() => setShowPlanModal(false)} className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10 text-white/40' : 'hover:bg-slate-100 text-slate-400'}`}>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Items list */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2" style={{ scrollbarWidth: 'thin' }}>
              {planDraft.length === 0 && (
                <p className={`text-xs text-center py-6 ${mutedText}`}>Nenhum passo ainda. Adicione abaixo.</p>
              )}
              {planDraft.map((item, idx) => (
                <div key={item.id} className={`flex items-center gap-3 px-3 py-2.5 rounded-2xl border group transition-all ${isDark ? 'bg-white/5 border-white/10 hover:border-white/20' : 'bg-slate-50 border-slate-100 hover:border-slate-200'}`}>
                  {/* Index badge */}
                  <span className={`shrink-0 w-5 h-5 rounded-lg flex items-center justify-center text-[9px] font-black ${item.completed ? 'bg-emerald-500 text-white' : isDark ? 'bg-white/10 text-white/40' : 'bg-slate-200 text-slate-500'}`}>
                    {item.completed ? <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : idx + 1}
                  </span>

                  {/* Editable text */}
                  <input
                    value={item.text}
                    onChange={e => setPlanDraft(prev => prev.map(i => i.id === item.id ? { ...i, text: e.target.value } : i))}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); newPlanItemRef.current?.focus(); } }}
                    className={`flex-1 text-xs font-medium bg-transparent outline-none min-w-0 ${item.completed ? isDark ? 'text-white/30 line-through' : 'text-slate-300 line-through' : isDark ? 'text-white/80' : 'text-slate-700'}`}
                    placeholder="Descreva o passo…"
                  />

                  {/* Delete */}
                  <button
                    onClick={() => setPlanDraft(prev => prev.filter(i => i.id !== item.id))}
                    className={`shrink-0 p-1 rounded-lg opacity-0 group-hover:opacity-100 transition-all ${isDark ? 'text-rose-400 hover:bg-rose-500/20' : 'text-rose-400 hover:bg-rose-50'}`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </button>
                </div>
              ))}
            </div>

            {/* Add new item */}
            <div className={`shrink-0 px-4 py-3 border-t ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
              <div className={`flex items-center gap-2 px-3 py-2.5 rounded-2xl border ${isDark ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-200'}`}>
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
                  <button onClick={addPlanDraftItem} className="shrink-0 px-2.5 py-1 rounded-lg bg-blue-600 text-white text-[9px] font-black uppercase tracking-widest">
                    Add
                  </button>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className={`shrink-0 px-6 py-4 border-t flex items-center justify-between gap-3 ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
              <p className={`text-[9px] ${mutedText}`}>Itens já concluídos são preservados</p>
              <div className="flex gap-3">
                <button onClick={() => setShowPlanModal(false)} className={`px-4 py-2 text-sm font-bold rounded-xl transition-all ${isDark ? 'text-white/40 hover:text-white/70' : 'text-slate-400 hover:text-slate-600'}`}>
                  Cancelar
                </button>
                <button onClick={savePlanDraft} className="px-6 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-black shadow-lg transition-all">
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
      {showDeepResearchModal && (
        <div className="fixed inset-0 z-[340] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className={`w-full max-w-lg rounded-3xl shadow-2xl border p-6 ${isDark ? 'bg-[#10131d] border-white/10 text-white' : 'bg-white border-slate-200 text-slate-900'}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-base font-black tracking-tight">Iniciar Pesquisa Profunda</h3>
                <p className={`mt-1 text-xs leading-relaxed ${mutedText}`}>
                  A execução é assíncrona e pode levar cerca de 8 a 9 minutos. O resultado será salvo no acervo global.
                </p>
              </div>
              <button
                onClick={() => setShowDeepResearchModal(false)}
                className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10 text-white/40' : 'hover:bg-slate-100 text-slate-400'}`}
                aria-label="Fechar modal"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="mt-5 space-y-2">
              <label className={labelCls}>Tema da Pesquisa</label>
              <textarea
                value={deepResearchTopic}
                onChange={e => setDeepResearchTopic(e.target.value)}
                placeholder="Ex.: panorama regulatório e jurisprudencial sobre uso de IA generativa na administração pública"
                className={`min-h-[140px] w-full resize-y rounded-2xl border p-4 text-sm outline-none transition-all ${isDark ? 'bg-white/5 border-white/10 text-white placeholder:text-white/25' : 'bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-400'}`}
              />
              <p className={`text-[10px] ${mutedText}`}>
                Use um tema específico. Quanto melhor o escopo, melhor o relatório final.
              </p>
            </div>

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                onClick={() => setShowDeepResearchModal(false)}
                className={`px-4 py-2 text-sm font-bold rounded-xl transition-all ${isDark ? 'text-white/40 hover:text-white/70' : 'text-slate-400 hover:text-slate-600'}`}
              >
                Cancelar
              </button>
              <button
                onClick={confirmDeepResearch}
                disabled={isDeepResearching || !deepResearchTopic.trim()}
                className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-black shadow-lg transition-all"
              >
                Iniciar pesquisa
              </button>
            </div>
          </div>
        </div>
      )}

      {isNotificationCenterOpen && (
        <div className="absolute top-20 right-6 z-[300] w-80 md:w-96 shadow-2xl animate-in slide-in-from-right-4 duration-300">
          <NotificationCenter notifications={notifications} onMarkAsRead={onMarkAsRead} onDismiss={onDismiss} isOpen={isNotificationCenterOpen} onClose={onCloseNotifications} />
        </div>
      )}


      {/* ══════════════════════════════════════════════════════════
          MODAL SYSTEM (link / contact / edit / delete / upload / reminder)
      ══════════════════════════════════════════════════════════ */}
      {modalConfig.isOpen && (
        <div className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className={`w-full ${modalConfig.type === 'edit_diary' ? 'max-w-4xl max-h-[90vh]' : 'max-w-md'} p-6 rounded-3xl shadow-2xl overflow-hidden ${isDark ? 'bg-[#1A1A2E] text-white border border-white/10' : 'bg-white text-slate-900'}`}>
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
                className={`w-full p-4 rounded-xl border outline-none min-h-[45vh] max-h-[65vh] overflow-y-auto resize-y ${isDark ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-slate-200 text-slate-900'}`}
              />
            )}
            {(modalConfig.type === 'link') && (
              <div className="flex flex-col gap-3">
                <input placeholder="Nome" value={modalInputName} onChange={e => setModalInputName(e.target.value)} className={`w-full p-3 rounded-xl border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`} />
                <input placeholder="URL" value={modalInputValue} onChange={e => setModalInputValue(e.target.value)} className={`w-full p-3 rounded-xl border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`} />
              </div>
            )}
            {(modalConfig.type === 'contact') && (
              <div className="flex flex-col gap-3">
                <input placeholder="Nome do Contato" value={modalInputName} onChange={e => setModalInputName(e.target.value)} className={`w-full p-3 rounded-xl border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`} />
                <input placeholder="Telefone / Info" value={modalInputValue} onChange={e => setModalInputValue(e.target.value)} className={`w-full p-3 rounded-xl border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`} />
              </div>
            )}
            {modalConfig.type === 'reminder' && (
              <div className="flex flex-col gap-3">
                <input type="date" value={reminderDate} onChange={e => setReminderDate(e.target.value)} className={`w-full p-3 rounded-xl border outline-none ${isDark ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-slate-200'}`} />
                <input type="time" value={reminderTime} onChange={e => setReminderTime(e.target.value)} className={`w-full p-3 rounded-xl border outline-none ${isDark ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-slate-200'}`} />
              </div>
            )}
            {modalConfig.type === 'confirm_delete' && (
              <p className={`text-sm mb-4 ${isDark ? 'text-white/50' : 'text-slate-500'}`}>Tem certeza que deseja excluir este registro do diário?</p>
            )}
            {modalConfig.type === 'file_upload' && (
              <div className="flex flex-col gap-3">
                {pendingFiles.map((file, i) => {
                  const key = getPendingFileKey(file);
                  return (
                    <div key={key}>
                      <p className={`text-[9px] font-black uppercase tracking-widest mb-1 ${mutedText}`}>Arquivo {i + 1}</p>
                      <input value={pendingFileNames[key] || ''} onChange={e => setPendingFileNames(prev => ({ ...prev, [key]: e.target.value }))}
                        className={`w-full p-3 rounded-xl border outline-none ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`} />
                      <p className={`text-[10px] mt-0.5 ${mutedText}`}>Original: {file.name}</p>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex gap-3 mt-6 justify-end">
              <button onClick={() => { setModalConfig({ ...modalConfig, isOpen: false }); setModalInputValue(''); setModalInputName(''); setPendingFiles([]); setPendingFileNames({}); }}
                className={`px-4 py-2 font-bold ${isDark ? 'text-white/40' : 'text-slate-400'}`}>Cancelar</button>
              <button onClick={handleModalConfirm}
                className={`px-6 py-2 rounded-xl font-black text-white shadow-lg transition-all ${modalConfig.type === 'confirm_delete' ? 'bg-rose-600 hover:bg-rose-700' : 'bg-blue-600 hover:bg-blue-700'}`}>
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

