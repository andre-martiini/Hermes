import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Tarefa, Status, EntregaInstitucional, Prioridade, AtividadeRealizada,
  Afastamento, PlanoTrabalho, PlanoTrabalhoItem, Categoria, Acompanhamento,
  BrainstormIdea, FinanceTransaction, FinanceGoal, FinanceSettings,
  FixedBill, BillRubric, IncomeEntry, IncomeRubric, HealthWeight,
  DailyHabits, HealthSettings, HermesNotification, AppSettings,
  formatDate, formatDateLocalISO, Sistema, SistemaStatus, WorkItem, WorkItemPhase,
  WorkItemPriority, QualityLog, WorkItemAudit, GoogleCalendarEvent,
  PoolItem, CustomNotification, HealthExam, ConhecimentoItem, UndoAction, HermesModalProps,
  ShoppingLocation, ShoppingItem
} from './types';
import HealthView from './views/HealthView';
import { STATUS_COLORS, PROJECT_COLORS } from './constants';
import { db, functions, messaging, auth, googleProvider, signInWithPopup, signOut, browserLocalPersistence, browserSessionPersistence, setPersistence } from './firebase';
import { onAuthStateChanged, User } from 'firebase/auth';
import { collection, onSnapshot, query, updateDoc, doc, addDoc, deleteDoc, setDoc, arrayUnion, arrayRemove } from 'firebase/firestore';
import { getToken, onMessage } from 'firebase/messaging';
import { httpsCallable } from 'firebase/functions';
import FinanceView from './views/FinanceView';
import DashboardView from './views/DashboardView';
import KnowledgeView from './views/KnowledgeView';
import ProjectsView from './views/ProjectsView';

// Importações dos módulos extraídos
import {
  DEFAULT_APP_SETTINGS, getDaysInMonth, isWorkDay, callScrapeSipac,
  getMonthWorkDays, normalizeStatus, formatWhatsAppText,
  formatInlineWhatsAppText, detectAreaFromTitle
} from './utils/helpers';
import {
  ToastContainer, FilterChip, PgcMiniTaskCard, PgcAuditRow,
  RowCard, WysiwygEditor, NotificationCenter, AutoExpandingTextarea
} from './components/ui/UIComponents';
import {
  HermesModal, SettingsModal, DailyHabitsModal,
  TaskCreateModal, TaskEditModal
} from './components/modals/Modals';
import { DayView } from './views/DayView';
import { CalendarView } from './views/CalendarView';
import { CategoryView } from './views/CategoryView';
import { TaskExecutionView } from './views/TaskExecutionView';
import { PublicScholarshipRegistration } from './components/public/PublicScholarshipRegistration';

// Import Tools & Modals
import { FerramentasView } from './components/tools/FerramentasView';
import { SistemasDevView } from './views/SistemasDevView';
import { QuickNoteModal } from './components/modals/QuickNoteModal';
import { QuickLogModal } from './components/modals/QuickLogModal';
import { ShoppingAIModal } from './components/modals/ShoppingAIModal';

// Import Custom Hooks
import { useAuth } from './hooks/useAuth';
import { useTasks } from './hooks/useTasks';
import { useFinance } from './hooks/useFinance';
import { useHealth } from './hooks/useHealth';
import { useSystemSync } from './hooks/useSystemSync';
import { useNotifications } from './hooks/useNotifications';
import { useToast } from './hooks/useToast';


type SortOption = 'date-asc' | 'date-desc' | 'priority-high' | 'priority-low';

const getBucketStartDate = (label: string): string => {
  const now = new Date();
  now.setHours(0, 0, 0, 0);

  if (label === 'Hoje') return now.toLocaleDateString('en-CA');

  if (label === 'Amanhã') {
    const d = new Date(now);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  if (label === 'Esta Semana') {
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const d = new Date(tomorrow);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  if (label === 'Este Mês') {
    const endOfWeek = new Date(now);
    endOfWeek.setDate(now.getDate() + (6 - now.getDay()));
    const d = new Date(endOfWeek);
    d.setDate(d.getDate() + 1);
    return d.toLocaleDateString('en-CA');
  }

  const meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  const lowerLabel = label.toLowerCase();

  const mesIndex = meses.findIndex(m => lowerLabel.includes(m));
  if (mesIndex >= 0) {
    const anoMatch = lowerLabel.match(/\d{4}/);
    if (anoMatch) {
      const ano = parseInt(anoMatch[0]);
      const d = new Date(ano, mesIndex, 1);
      return d.toLocaleDateString('en-CA');
    }
  }

  if (label === 'Atrasadas') {
    const d = new Date(now);
    d.setDate(d.getDate() - 1);
    return d.toLocaleDateString('en-CA');
  }

  return '';
};

const App: React.FC = () => {
  // Public Route Interception
  if (window.location.pathname.startsWith('/join/')) {
    return <PublicScholarshipRegistration />;
  }

  // Toast Hook (Global Feedback)
  const { toasts, showToast, removeToast } = useToast();

  // 1. Auth Hook
  const { user, authLoading, rememberMe, setRememberMe, handleLogin, handleLogout } = useAuth(showToast);

  // 2. Task Hook
  const {
    tarefas,
    brainstormIdeas,
    undoStack,
    loading: tasksLoading,
    convertingIdea,
    setConvertingIdea,
    taskInitialData,
    setTaskInitialData,
    isCreateModalOpen,
    setIsCreateModalOpen,
    handleCreateTarefa,
    handleUpdateTarefa,
    handleDeleteTarefa,
    handleToggleTarefaStatus,
    handleUndo,
    pushToUndoStack,
    handleReorderTasks,
    handleDeleteIdea,
    handleArchiveIdea,
    handleAddTextIdea,
    handleUpdateIdea
  } = useTasks(showToast);

  // 3. Finance Hook
  const {
    financeTransactions,
    financeGoals,
    financeSettings,
    fixedBills,
    billRubrics,
    incomeEntries,
    incomeRubrics,
    loading: financeLoading,
    handleUpdateFinanceGoal,
    handleDeleteFinanceGoal,
    handleReorderFinanceGoals,
    handleAddTransaction,
    handleUpdateTransaction,
    handleDeleteTransaction,
    handleUpdateSettings,
    handleAddRubric,
    handleUpdateRubric,
    handleDeleteRubric,
    handleAddBill,
    handleUpdateBill,
    handleDeleteBill,
    handleAddIncomeRubric,
    handleUpdateIncomeRubric,
    handleDeleteIncomeRubric,
    handleAddIncomeEntry,
    handleUpdateIncomeEntry,
    handleDeleteIncomeEntry
  } = useFinance(tarefas, showToast);

  // 4. Health Hook
  const {
    healthWeights,
    healthDailyHabits,
    healthSettings,
    exams,
    loading: healthLoading,
    handleUpdateHealthSettings,
    handleAddHealthWeight,
    handleDeleteHealthWeight,
    handleUpdateHealthHabits,
    handleAddExam,
    handleUpdateExam,
    handleDeleteExam
  } = useHealth(showToast);

  // 5. System Sync Hook
  const {
    sistemasDetalhes,
    workItems,
    googleCalendarEvents,
    atividadesPGC,
    afastamentos,
    entregas,
    unidades,
    planosTrabalho,
    knowledgeItems,
    syncData,
    isSyncing,
    sistemasAtivos,
    loading: syncLoading,
    handleUpdateSistema,
    handleAddUnidade,
    handleDeleteUnidade,
    handleUpdateUnidade,
    handleCreateWorkItem,
    handleUpdateWorkItem,
    handleDeleteWorkItem
  } = useSystemSync(showToast);

  // 6. Notifications Hook
  const {
    notifications,
    appSettings,
    activePopup,
    isHabitsReminderOpen,
    setIsHabitsReminderOpen,
    setActivePopup,
    emitNotification,
    handleMarkNotificationRead,
    handleDismissNotification,
    handleUpdateAppSettings
  } = useNotifications(tarefas, showToast);

  // UI State
  const [modalState, setModalState] = useState<HermesModalProps>({
    isOpen: false,
    title: '',
    message: '',
    type: 'alert',
    onConfirm: () => { }
  });

  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [isCompletedLogsOpen, setIsCompletedLogsOpen] = useState(false);

  // Dashboard states
  const [dashboardViewMode, setDashboardViewMode] = useState<'list' | 'calendar'>('list');
  const [calendarViewMode, setCalendarViewMode] = useState<'month' | 'week' | 'day'>('month');
  const [calendarDate, setCalendarDate] = useState(new Date());

  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeModule, setActiveModule] = useState<'home' | 'dashboard' | 'acoes' | 'financeiro' | 'saude' | 'projetos'>('dashboard');
  const [viewMode, setViewMode] = useState<'dashboard' | 'gallery' | 'pgc' | 'licitacoes' | 'assistencia' | 'sistemas' | 'finance' | 'saude' | 'ferramentas' | 'sistemas-dev' | 'knowledge' | 'projects'>('dashboard');
  const [selectedTask, setSelectedTask] = useState<Tarefa | null>(null);
  const [isSidebarRetracted, setIsSidebarRetracted] = useState(false);
  const [financeActiveTab, setFinanceActiveTab] = useState<'dashboard' | 'fixed'>('dashboard');
  const [isFinanceSettingsOpen, setIsFinanceSettingsOpen] = useState(false);

  // Modal Mode State
  const [taskModalMode, setTaskModalMode] = useState<'default' | 'edit' | 'execute'>('default');
  const [statusFilter, setStatusFilter] = useState<Status[]>(['em andamento']);
  const [areaFilter, setAreaFilter] = useState<string>('TODAS');
  const [sortOption, setSortOption] = useState<SortOption>('date-asc');
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [isNotificationCenterOpen, setIsNotificationCenterOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [lastBackPress, setLastBackPress] = useState(0);
  const [settingsTab, setSettingsTab] = useState<'notifications' | 'context' | 'sistemas'>('notifications');

  // Specific UI State from original file
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [selectedWorkItem, setSelectedWorkItem] = useState<WorkItem | null>(null);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [isModalCompletedLogsOpen, setIsModalCompletedLogsOpen] = useState(false);
  const [isQuickLogModalOpen, setIsQuickLogModalOpen] = useState(false);
  const [isShoppingAIModalOpen, setIsShoppingAIModalOpen] = useState(false);
  const [editingResource, setEditingResource] = useState<{ field: string, label: string, value: string } | null>(null);
  const [newLogText, setNewLogText] = useState('');
  const [newLogTipo, setNewLogTipo] = useState<'desenvolvimento' | 'ajuste' | 'geral'>('geral');
  const [newLogAttachments, setNewLogAttachments] = useState<PoolItem[]>([]);
  const [editingWorkItem, setEditingWorkItem] = useState<WorkItem | null>(null);
  const [editingWorkItemText, setEditingWorkItemText] = useState('');
  const [editingWorkItemAttachments, setEditingWorkItemAttachments] = useState<PoolItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isRecordingLog, setIsRecordingLog] = useState(false);
  const [isProcessingLog, setIsProcessingLog] = useState(false);
  const logMediaRecorderRef = useRef<MediaRecorder | null>(null);
  const logAudioChunksRef = useRef<Blob[]>([]);

  const [isQuickNoteModalOpen, setIsQuickNoteModalOpen] = useState(false);
  const [hasAutoExpanded, setHasAutoExpanded] = useState(false);
  const [pgcSubView, setPgcSubView] = useState<'audit' | 'heatmap' | 'config' | 'plano'>('audit');
  const [isImportPlanOpen, setIsImportPlanOpen] = useState(false);
  const [isCompletedTasksOpen, setIsCompletedTasksOpen] = useState(false);
  const [activeFerramenta, setActiveFerramenta] = useState<'brainstorming' | 'slides' | 'shopping' | null>(null);
  const [isBrainstormingAddingText, setIsBrainstormingAddingText] = useState(false);
  const [confirmDeleteLogId, setConfirmDeleteLogId] = useState<string | null>(null);
  const [isSystemSelectorOpen, setIsSystemSelectorOpen] = useState(false);

  // Sync selectedTask with updated data
  useEffect(() => {
    if (!selectedTask) {
      setTaskModalMode('default');
    }
  }, [selectedTask]);

  useEffect(() => {
    if (selectedTask) {
      const updated = tarefas.find(t => t.id === selectedTask.id);
      if (updated && JSON.stringify(updated) !== JSON.stringify(selectedTask)) {
        setSelectedTask(updated);
      }
    }
  }, [tarefas, selectedTask]);

  const showAlert = (title: string, message: string, onConfirm?: () => void) => {
    setModalState({
      isOpen: true,
      title,
      message,
      type: 'alert',
      onConfirm: () => {
        setModalState(prev => ({ ...prev, isOpen: false }));
        if (onConfirm) onConfirm();
      }
    });
  };

  const showConfirm = (title: string, message: string, onConfirm: () => void, onCancel?: () => void) => {
    setModalState({
      isOpen: true,
      title,
      message,
      type: 'confirm',
      onConfirm: () => {
        setModalState(prev => ({ ...prev, isOpen: false }));
        onConfirm();
      },
      onCancel: () => {
        setModalState(prev => ({ ...prev, isOpen: false }));
        if (onCancel) onCancel();
      }
    });
  };

  const handleCopyBacklog = async () => {
    const activeItems = workItems.filter(w => !w.concluido);
    if (activeItems.length === 0) {
      showToast("Nenhum item pendente para copiar.", "info");
      return;
    }

    const text = activeItems.map(item => {
      const systemName = unidades.find(u => u.id === item.sistema_id)?.nome.replace('SISTEMA:', '').trim() || 'Sistema Desconhecido';
      return `[${systemName}] ${item.descricao}`;
    }).join('\n');

    try {
      await navigator.clipboard.writeText(text);
      showToast("Backlog copiado para a área de transferência!", "success");
    } catch (err) {
      console.error('Failed to copy: ', err);
      showToast("Erro ao copiar.", "error");
    }
  };

  const startLogRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      logMediaRecorderRef.current = mediaRecorder;
      logAudioChunksRef.current = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) logAudioChunksRef.current.push(event.data);
      };
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(logAudioChunksRef.current, { type: 'audio/m4a' });
        await handleProcessLogAudio(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };
      mediaRecorder.start();
      setIsRecordingLog(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      showAlert("Erro", "Permissão de microfone negada ou não disponível.");
    }
  };

  const stopLogRecording = () => {
    if (logMediaRecorderRef.current && isRecordingLog) {
      logMediaRecorderRef.current.stop();
      setIsRecordingLog(false);
    }
  };

  const handleProcessLogAudio = async (audioBlob: Blob) => {
    setIsProcessingLog(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };
          if (data.refined) {
            if (viewMode === 'sistemas-dev' && selectedSystemId) {
              await handleCreateWorkItem(selectedSystemId, newLogTipo, data.refined, newLogAttachments);
              setNewLogText('');
              setNewLogAttachments([]);
              showToast("Log registrado via IA!", "success");
            } else {
              setNewLogText(prev => prev ? prev + '\n' + data.refined : data.refined);
            }
          }
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          showToast("Erro ao processar áudio via Hermes AI.", "error");
        } finally {
          setIsProcessingLog(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessingLog(false);
    }
  };

  const handleFileUploadToDrive = async (file: File) => {
    try {
      setIsUploading(true);
      const reader = new FileReader();
      const base64Promise = new Promise<string>((resolve) => {
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1];
          resolve(base64);
        };
      });
      reader.readAsDataURL(file);
      const fileContent = await base64Promise;

      const uploadFunc = httpsCallable(functions, 'upload_to_drive');
      const result = await uploadFunc({
        fileName: file.name,
        fileContent: fileContent,
        mimeType: file.type,
        folderId: appSettings.googleDriveFolderId
      });

      const data = result.data as { fileId: string, webViewLink: string };

      const newItem: PoolItem = {
        id: data.fileId,
        tipo: 'arquivo',
        valor: data.webViewLink,
        nome: file.name,
        data_criacao: new Date().toISOString()
      };

      return newItem;
    } catch (err) {
      console.error(err);
      showToast("Erro ao carregar para o Drive.", "error");
      return null;
    } finally {
      setIsUploading(false);
    }
  };

  const handleDashboardNavigate = (view: 'gallery' | 'finance' | 'saude' | 'sistemas-dev') => {
    setViewMode(view);
    if (view === 'gallery' || view === 'sistemas-dev') setActiveModule('acoes');
    else if (view === 'finance') setActiveModule('financeiro');
    else if (view === 'saude') setActiveModule('saude');
  };

  const handleNotificationNavigate = (link: string) => {
    if (!link) return;

    switch (link) {
      case 'acoes':
        setActiveModule('acoes');
        setViewMode('gallery');
        break;
      case 'financeiro':
        setActiveModule('financeiro');
        setViewMode('finance');
        break;
      case 'pgc':
        setActiveModule('acoes');
        setViewMode('pgc');
        break;
      case 'saude':
        setActiveModule('saude');
        setViewMode('saude');
        break;
      case 'sistemas':
        setActiveModule('acoes');
        setViewMode('sistemas-dev');
        break;
      default:
        break;
    }
  };

  // Sync state changes with history to enable back button
  useEffect(() => {
    if (activeModule !== 'dashboard' || viewMode !== 'dashboard' || selectedSystemId || isLogsModalOpen || activeFerramenta) {
      window.history.pushState({ activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta }, "", window.location.pathname);
    }
  }, [activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta]);

  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      if (isLogsModalOpen) {
        setIsLogsModalOpen(false);
        e.preventDefault();
      } else if (selectedSystemId) {
        setSelectedSystemId(null);
        e.preventDefault();
      } else if (activeFerramenta) {
        setActiveFerramenta(null);
        e.preventDefault();
      } else if (viewMode !== 'dashboard') {
        setActiveModule('dashboard');
        setViewMode('dashboard');
        e.preventDefault();
      } else {
        const now = Date.now();
        if (now - lastBackPress < 2000) return;
        e.preventDefault();
        setLastBackPress(now);
        showToast("Pressione voltar novamente para minimizar", "info");
        window.history.pushState(null, "", window.location.pathname);
      }
    };

    if (window.history.state === null) {
      window.history.pushState({}, "", window.location.pathname);
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta, lastBackPress]);

  const handleUpdateOverdueTasks = async () => {
    const todayStr = formatDateLocalISO(new Date());
    const overdue = tarefas.filter(t =>
      normalizeStatus(t.status) !== 'concluido' &&
      (t.status as any) !== 'excluído' &&
      t.data_limite && t.data_limite !== "-" && t.data_limite !== "0000-00-00" &&
      t.data_limite < todayStr
    );

    if (overdue.length === 0) return;

    try {
      const promises = overdue.map(t => updateDoc(doc(db, 'tarefas', t.id), {
        data_limite: todayStr,
        horario_inicio: null,
        horario_fim: null,
        data_atualizacao: new Date().toISOString()
      }));
      await Promise.all(promises);
      showToast(`${overdue.length} ações atualizadas para hoje!`, 'success');
      const targetNotif = notifications.find(n => n.title === "Ações Vencidas");
      if (targetNotif) handleDismissNotification(targetNotif.id);
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar tarefas.", 'error');
    }
  };

  const handleUpdateToToday = async (task: Tarefa) => {
    const todayStr = formatDateLocalISO(new Date());
    try {
      await updateDoc(doc(db, 'tarefas', task.id), {
        data_limite: todayStr,
        horario_inicio: null,
        horario_fim: null,
        data_atualizacao: new Date().toISOString()
      });
      showToast("Ação atualizada para hoje!", 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar ação.", 'error');
    }
  };

  const handleBatchTag = async (categoria: Categoria) => {
    if (selectedTaskIds.length === 0) return;
    try {
      setLoading(true);
      const batchSize = selectedTaskIds.length;

      const promises = selectedTaskIds.map(async (id) => {
        const t = tarefas.find(task => task.id === id);
        if (!t) return;

        let finalNotes = t.notas || '';
        const tagStr = `Tag: ${categoria}`;
        finalNotes = finalNotes.replace(/Tag:\s*(CLC|ASSISTÊNCIA|GERAL|NÃO CLASSIFICADA)/gi, '').trim();
        finalNotes = finalNotes ? `${finalNotes}\n\n${tagStr}` : tagStr;

        return updateDoc(doc(db, 'tarefas', id), {
          categoria: categoria,
          notas: finalNotes,
          data_atualizacao: new Date().toISOString()
        });
      });

      await Promise.all(promises);
      setSelectedTaskIds([]);
      showToast(`${batchSize} tarefas atualizadas!`, 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar em lote.", 'error');
    } finally {
      setLoading(false);
    }
  };

  const toggleSection = (label: string) => {
    setExpandedSections(prev => {
      if (prev.includes(label)) return prev.filter(s => s !== label);
      return [...prev, label];
    });
  };

  // Convert Idea to Task (Helper)
  const handleFinalizeIdeaConversion = (sistemaId: string) => {
    if (!convertingIdea) return;
    handleCreateWorkItem(sistemaId, 'ideia' as any, convertingIdea.text);
    handleDeleteIdea(convertingIdea.id);
    setConvertingIdea(null);
    setIsSystemSelectorOpen(false);
    setActiveFerramenta(null);
    showToast("Ideia convertida em item de backlog!", "success");
  };

  const handleConvertToTask = (idea: BrainstormIdea) => {
    setConvertingIdea(idea);
    setTaskInitialData({ titulo: idea.text });
    setIsCreateModalOpen(true);
  };

  const handleAddQuickLog = (text: string, systemId: string) => {
     handleCreateWorkItem(systemId, 'log', text);
  };

  const handleShoppingAIInput = (text: string) => {
    const candidates = text.split(/,|\be\b|\n|\+ /).map(s => s.trim()).filter(s => s.length > 1);

    if (candidates.length === 0) {
      showToast("Não consegui identificar itens na sua fala.", "info");
      return;
    }

    try {
      const itemsJson = localStorage.getItem('hermes_shopping_items');
      const items: ShoppingItem[] = itemsJson ? JSON.parse(itemsJson) : [];

      if (items.length === 0) {
        showToast("Sua base de itens de compra está vazia. Cadastre primeiro os itens nas listas.", "info");
        return;
      }

      let matchedCount = 0;
      const updatedItems = items.map(item => {
        const itemLower = item.nome.toLowerCase();
        const isMatched = candidates.some(c => {
           return itemLower.includes(c.toLowerCase());
        });

        if (isMatched && !item.isPlanned) {
            matchedCount++;
            return { ...item, isPlanned: true };
        }
        return item;
      });

      if (matchedCount > 0) {
        localStorage.setItem('hermes_shopping_items', JSON.stringify(updatedItems));
        showToast(`${matchedCount} itens marcados para compra!`, "success");
        // Force refresh if tool is open is tricky without global state for tools, but View will remount or use storage event if implemented
        // For now, toast confirms action.
      } else {
        showToast("Nenhum item correspondente encontrado na sua lista.", "warning");
      }
    } catch (e) {
      console.error(e);
      showToast("Erro ao processar itens.", "error");
    }
  };

  // Derived State: PGC
  const pgcTasks = useMemo(() => tarefas.filter(t => t.categoria === 'CLC' && (t.status as any) !== 'excluído'), [tarefas]);
  const pgcTasksAguardando = useMemo(() => pgcTasks.filter(t => (!t.entregas_relacionadas || t.entregas_relacionadas.length === 0) && normalizeStatus(t.status) !== 'concluido'), [pgcTasks]);
  const pgcEntregas = useMemo(() => entregas.filter(e => e.ano === currentYear && e.mes === currentMonth + 1), [entregas, currentYear, currentMonth]);

  // Derived State: Tarefas Agrupadas
  const tarefasAgrupadas = useMemo(() => {
    // Implement grouping logic similar to original index.tsx
    const groups: { [key: string]: Tarefa[] } = {};
    const todayStr = formatDateLocalISO(new Date());

    filteredAndSortedTarefas.forEach(t => {
       // ... existing grouping logic ...
       let bucket = 'Sem Prazo Definido';
       if (t.data_limite) {
          if (t.data_limite < todayStr) bucket = 'Atrasadas';
          else if (t.data_limite === todayStr) bucket = 'Hoje';
          else {
              const d = new Date(t.data_limite);
              const now = new Date();
              const diffTime = d.getTime() - now.getTime();
              const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
              if (diffDays <= 7) bucket = 'Esta Semana';
              else if (d.getMonth() === now.getMonth()) bucket = 'Este Mês';
              else bucket = d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
          }
       }
       if (!groups[bucket]) groups[bucket] = [];
       groups[bucket].push(t);
    });

    // Sort logic within buckets
    Object.keys(groups).forEach(key => {
        groups[key].sort((a, b) => {
            if (a.ordem !== undefined && b.ordem !== undefined) return a.ordem - b.ordem;
            if (a.prioridade !== b.prioridade) {
                const p = { 'alta': 3, 'média': 2, 'baixa': 1 };
                return (p[b.prioridade] || 0) - (p[a.prioridade] || 0);
            }
            return 0;
        });
    });

    return groups;
  }, [tarefas, searchTerm, statusFilter, areaFilter, sortOption]); // Note: using filteredAndSortedTarefas logic inside

  // Helper for filtered tasks (needed for aggregation above)
  const filteredAndSortedTarefas = useMemo(() => {
    let result = [...tarefas];
    if (searchTerm) {
      const s = searchTerm.toLowerCase();
      if (s === 'filter:unclassified') {
        result = result.filter(t => (!t.categoria || t.categoria === 'NÃO CLASSIFICADA') && normalizeStatus(t.status) !== 'concluido');
      } else if (s === 'categoria:geral') {
        result = result.filter(t => t.categoria === 'GERAL');
      } else {
        result = result.filter(t => t.titulo?.toLowerCase().includes(s) || t.projeto?.toLowerCase().includes(s) || t.notas?.toLowerCase().includes(s));
      }
    }
    if (statusFilter.length > 0) {
      result = result.filter(t => statusFilter.some(sf => normalizeStatus(t.status) === normalizeStatus(sf)));
    }

    if (areaFilter !== 'TODAS') {
      const norm = (val: any) => (val || '').toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
      const filterNorm = norm(areaFilter);
      result = result.filter(t => {
        const cat = norm(t.categoria);
        if (filterNorm === 'CLC') return cat === 'CLC';
        if (filterNorm === 'ASSISTENCIA') return cat === 'ASSISTENCIA' || cat === 'ASSISTENCIA ESTUDANTIL';
        if (filterNorm === 'NAO CLASSIFICADA') return !t.categoria || cat === 'NAO CLASSIFICADA';
        return cat === filterNorm;
      });
    }

    return result;
  }, [tarefas, searchTerm, statusFilter, areaFilter]);

  // Handle Link Tarefa (PGC)
  const handleLinkTarefa = async (tarefaId: string, entregaId: string) => {
    try {
      await updateDoc(doc(db, 'tarefas', tarefaId), {
        entregas_relacionadas: arrayUnion(entregaId),
        data_atualizacao: new Date().toISOString()
      });
      showToast("Vínculo criado!", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao vincular.", "error");
    }
  };

  const handleUnlinkTarefa = async (tarefaId: string, entregaId: string) => {
    try {
      await updateDoc(doc(db, 'tarefas', tarefaId), {
        entregas_relacionadas: arrayRemove(entregaId),
        data_atualizacao: new Date().toISOString()
      });
      showToast("Vínculo removido.", "info");
    } catch (e) {
      console.error(e);
      showToast("Erro ao desvincular.", "error");
    }
  };

  const handleCreateEntregaFromPlan = async (item: PlanoTrabalhoItem) => {
    try {
      const docRef = await addDoc(collection(db, 'atividades'), {
        entrega: item.entrega,
        area: item.unidade, // Adapting
        descricao_trabalho: item.descricao,
        mes: currentMonth + 1,
        ano: currentYear
      });
      return docRef.id;
    } catch (e) {
      console.error(e);
      return null;
    }
  };

  // Login View
  if (!user && !authLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="bg-white p-8 rounded-[2.5rem] shadow-2xl max-w-md w-full text-center space-y-8 animate-in zoom-in-95 duration-500">
          <div className="w-24 h-24 bg-slate-900 rounded-[2rem] mx-auto flex items-center justify-center shadow-2xl shadow-slate-200">
            <svg className="w-12 h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </div>
          <div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tighter mb-2">Hermes</h1>
            <p className="text-slate-400 font-bold uppercase tracking-widest text-xs">Sistema de Gestão Integrada</p>
          </div>
          <div className="space-y-4 pt-4">
            <button
              onClick={handleLogin}
              className="w-full bg-slate-900 text-white p-5 rounded-2xl font-black uppercase tracking-widest text-xs hover:bg-slate-800 transition-all shadow-xl hover:shadow-2xl hover:scale-[1.02] active:scale-95 flex items-center justify-center gap-3"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M12.545,10.239v3.821h5.445c-0.712,2.315-2.647,3.972-5.445,3.972c-3.332,0-6.033-2.701-6.033-6.032s2.701-6.032,6.033-6.032c1.498,0,2.866,0.549,3.921,1.453l2.814-2.814C17.503,2.988,15.139,2,12.545,2C7.021,2,2.543,6.477,2.543,12s4.478,10,10.002,10c8.396,0,10.249-7.85,9.426-11.748L12.545,10.239z" /></svg>
              Entrar com Google
            </button>
            <div className="flex items-center justify-center gap-2 cursor-pointer group" onClick={() => setRememberMe(!rememberMe)}>
              <div className={`w-5 h-5 rounded-lg border-2 flex items-center justify-center transition-all ${rememberMe ? 'bg-blue-600 border-blue-600' : 'border-slate-300'}`}>
                {rememberMe && <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>}
              </div>
              <span className="text-xs font-bold text-slate-400 group-hover:text-slate-600 transition-colors">Manter conectado neste dispositivo</span>
            </div>
          </div>
          <p className="text-[10px] text-slate-300 font-bold uppercase tracking-widest pt-8">Versão 3.5.0 • Build 2024</p>
        </div>
        <ToastContainer toasts={toasts} removeToast={removeToast} />
      </div>
    );
  }

  // Main App Render
  return (
    <div className="flex h-screen bg-slate-50 font-sans text-slate-900 overflow-hidden selection:bg-blue-100 selection:text-blue-900">
      {/* Sidebar */}
      <aside className={`${isSidebarRetracted ? 'w-20' : 'w-72'} bg-slate-900 text-white flex flex-col transition-all duration-300 ease-in-out relative z-50 flex-shrink-0 shadow-2xl hidden md:flex`}>
        <div className={`p-6 flex items-center ${isSidebarRetracted ? 'justify-center' : 'justify-between'}`}>
          {!isSidebarRetracted && (
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-900/50">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              </div>
              <span className="text-lg font-black tracking-tighter">Hermes</span>
            </div>
          )}
          <button onClick={() => setIsSidebarRetracted(!isSidebarRetracted)} className="p-2 bg-white/5 rounded-xl hover:bg-white/10 transition-colors">
            <svg className={`w-4 h-4 transition-transform duration-300 ${isSidebarRetracted ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
          </button>
        </div>

        <nav className="flex-1 px-4 space-y-2 overflow-y-auto custom-scrollbar-dark py-4">
          {[
            { id: 'dashboard', label: 'Visão Geral', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /> },
            { id: 'acoes', label: 'Ações', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /> },
            { id: 'financeiro', label: 'Financeiro', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /> },
            { id: 'saude', label: 'Saúde', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /> },
            { id: 'projetos', label: 'Projetos', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /> },
          ].map(item => (
            <button
              key={item.id}
              onClick={() => {
                setActiveModule(item.id as any);
                if (item.id === 'acoes') setViewMode('gallery');
                else if (item.id === 'financeiro') setViewMode('finance');
                else if (item.id === 'saude') setViewMode('saude');
                else if (item.id === 'projetos') setViewMode('projects');
                else setViewMode('dashboard');
              }}
              className={`w-full flex items-center gap-4 p-4 rounded-2xl transition-all group ${activeModule === item.id ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/50' : 'text-slate-400 hover:bg-white/5 hover:text-white'}`}
            >
              <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">{item.icon}</svg>
              {!isSidebarRetracted && <span className="text-sm font-bold tracking-wide">{item.label}</span>}
              {isSidebarRetracted && activeModule === item.id && <div className="absolute left-16 bg-blue-600 text-white text-xs font-bold px-3 py-1.5 rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-50">{item.label}</div>}
            </button>
          ))}

          <div className="pt-4 mt-4 border-t border-white/10">
            <p className={`px-4 text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2 ${isSidebarRetracted ? 'hidden' : 'block'}`}>Ferramentas</p>
            {[
              { id: 'brainstorming', label: 'Brainstorm', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /> },
              { id: 'sistemas', label: 'Sistemas', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /> },
              { id: 'conhecimento', label: 'Conhecimento', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /> },
            ].map(item => (
              <button
                key={item.id}
                onClick={() => {
                  if (item.id === 'brainstorming') { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta(null); }
                  else if (item.id === 'sistemas') { setActiveModule('acoes'); setViewMode('sistemas-dev'); }
                  else if (item.id === 'conhecimento') { setActiveModule('acoes'); setViewMode('knowledge'); }
                }}
                className={`w-full flex items-center gap-4 p-4 rounded-2xl transition-all group ${viewMode === (item.id === 'sistemas' ? 'sistemas-dev' : item.id === 'conhecimento' ? 'knowledge' : 'ferramentas') && activeModule === 'acoes' ? 'bg-white/10 text-white' : 'text-slate-400 hover:bg-white/5 hover:text-white'}`}
              >
                <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">{item.icon}</svg>
                {!isSidebarRetracted && <span className="text-sm font-bold tracking-wide">{item.label}</span>}
              </button>
            ))}
          </div>
        </nav>

        <div className="p-4 border-t border-white/10">
          <button onClick={() => setIsSettingsModalOpen(true)} className="w-full flex items-center gap-4 p-4 rounded-2xl text-slate-400 hover:bg-white/5 hover:text-white transition-all">
            <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
            {!isSidebarRetracted && <span className="text-sm font-bold tracking-wide">Configurações</span>}
          </button>
          <div className={`mt-4 flex items-center gap-3 ${isSidebarRetracted ? 'justify-center' : ''}`}>
            {user.photoURL ? (
              <img src={user.photoURL} alt={user.displayName || 'User'} className="w-10 h-10 rounded-full border-2 border-white/10" />
            ) : (
              <div className="w-10 h-10 bg-white/10 rounded-full flex items-center justify-center text-white font-bold">{user.email?.charAt(0).toUpperCase()}</div>
            )}
            {!isSidebarRetracted && (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold truncate">{user.displayName || 'Usuário'}</p>
                <p className="text-xs text-slate-400 truncate cursor-pointer hover:text-white transition-colors" onClick={handleLogout}>Sair</p>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-slate-50 relative">
        {/* Mobile Header */}
        <header className="bg-white border-b border-slate-200 p-4 flex items-center justify-between md:hidden z-40 sticky top-0 safe-area-top">
          <div className="flex items-center gap-3">
            <button onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)} className="p-2 -ml-2 text-slate-600">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
            </button>
            <span className="text-lg font-black tracking-tight text-slate-900">Hermes</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsNotificationCenterOpen(true)}
              className="p-2 relative text-slate-400 hover:text-slate-600 transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
              {notifications.filter(n => !n.isRead).length > 0 && (
                <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-rose-500 rounded-full border-2 border-white"></span>
              )}
            </button>
            <div className="w-8 h-8 bg-slate-200 rounded-full overflow-hidden">
              {user.photoURL ? <img src={user.photoURL} className="w-full h-full object-cover" /> : <div className="w-full h-full flex items-center justify-center text-slate-500 font-bold text-xs">{user.email?.charAt(0)}</div>}
            </div>
          </div>
        </header>

        {/* Mobile Menu Overlay */}
        {isMobileMenuOpen && (
          <div className="fixed inset-0 z-[60] bg-slate-900/90 backdrop-blur-sm md:hidden animate-in fade-in duration-200" onClick={() => setIsMobileMenuOpen(false)}>
            <div className="bg-white w-3/4 h-full shadow-2xl p-6 flex flex-col animate-in slide-in-from-left duration-300" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-8">
                <span className="text-2xl font-black text-slate-900">Hermes</span>
                <button onClick={() => setIsMobileMenuOpen(false)} className="p-2 bg-slate-100 rounded-full">
                  <svg className="w-6 h-6 text-slate-900" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
              <nav className="space-y-2 flex-1 overflow-y-auto">
                {[
                  { id: 'dashboard', label: 'Visão Geral' },
                  { id: 'acoes', label: 'Ações' },
                  { id: 'financeiro', label: 'Financeiro' },
                  { id: 'saude', label: 'Saúde' },
                  { id: 'projetos', label: 'Projetos' },
                ].map(item => (
                  <button
                    key={item.id}
                    onClick={() => {
                      setActiveModule(item.id as any);
                      if (item.id === 'acoes') setViewMode('gallery');
                      else if (item.id === 'financeiro') setViewMode('finance');
                      else if (item.id === 'saude') setViewMode('saude');
                      else if (item.id === 'projetos') setViewMode('projects');
                      else setViewMode('dashboard');
                      setIsMobileMenuOpen(false);
                    }}
                    className={`w-full text-left p-4 rounded-xl font-bold text-lg ${activeModule === item.id ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-50'}`}
                  >
                    {item.label}
                  </button>
                ))}
                <div className="pt-6 mt-6 border-t border-slate-100">
                  <p className="px-4 text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Ferramentas</p>
                  <button onClick={() => { setActiveModule('acoes'); setViewMode('ferramentas'); setIsMobileMenuOpen(false); }} className="w-full text-left p-4 rounded-xl font-bold text-lg text-slate-500 hover:bg-slate-50">Brainstorm</button>
                  <button onClick={() => { setActiveModule('acoes'); setViewMode('sistemas-dev'); setIsMobileMenuOpen(false); }} className="w-full text-left p-4 rounded-xl font-bold text-lg text-slate-500 hover:bg-slate-50">Sistemas</button>
                  <button onClick={() => { setActiveModule('acoes'); setViewMode('knowledge'); setIsMobileMenuOpen(false); }} className="w-full text-left p-4 rounded-xl font-bold text-lg text-slate-500 hover:bg-slate-50">Conhecimento</button>
                </div>
              </nav>
              <div className="pt-6 border-t border-slate-100">
                <button onClick={handleLogout} className="w-full bg-rose-50 text-rose-600 p-4 rounded-xl font-black uppercase tracking-widest text-xs">Sair</button>
              </div>
            </div>
          </div>
        )}

        <>
          {viewMode === 'dashboard' && (
            <DashboardView
              user={user}
              notifications={notifications}
              isNotificationCenterOpen={isNotificationCenterOpen}
              setIsNotificationCenterOpen={setIsNotificationCenterOpen}
              onNavigate={handleDashboardNavigate}
              stats={{
                total: tarefas.length,
                emAndamento: tarefas.filter(t => normalizeStatus(t.status) === 'em andamento').length,
                concluidas: tarefas.filter(t => normalizeStatus(t.status) === 'concluido').length,
                clc: tarefas.filter(t => t.categoria === 'CLC' && normalizeStatus(t.status) !== 'concluido').length,
                assistencia: tarefas.filter(t => t.categoria === 'ASSISTÊNCIA' && normalizeStatus(t.status) !== 'concluido').length,
                geral: tarefas.filter(t => t.categoria === 'GERAL' && normalizeStatus(t.status) !== 'concluido').length,
                semTag: tarefas.filter(t => (t.categoria === 'NÃO CLASSIFICADA' || !t.categoria) && normalizeStatus(t.status) !== 'concluido' && t.status !== 'excluído' as any).length,
              }}
              prioridadesHoje={tarefas.filter(t => {
                if (normalizeStatus(t.status) === 'concluido' || (t.status as any) === 'excluído') return false;
                if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") return false;
                return t.data_limite === formatDateLocalISO(new Date());
              })}
              onTaskClick={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
              onUpdateOverdue={handleUpdateOverdueTasks}
              onMarkNotificationRead={handleMarkNotificationRead}
              onDismissNotification={handleDismissNotification}
              onNotificationNavigate={handleNotificationNavigate}
              setIsSettingsModalOpen={setIsSettingsModalOpen}
              setIsMobileMenuOpen={setIsMobileMenuOpen}
              activePopup={activePopup}
              setActivePopup={setActivePopup}
              isSidebarRetracted={isSidebarRetracted}
              isMobileMenuOpen={isMobileMenuOpen}
              setIsQuickNoteModalOpen={setIsQuickNoteModalOpen}
              setIsQuickLogModalOpen={setIsQuickLogModalOpen}
              setIsShoppingAIModalOpen={setIsShoppingAIModalOpen}
              setIsCreateModalOpen={setIsCreateModalOpen}
              setIsTerminalOpen={setIsTerminalOpen}
              financeData={{
                  totalBalance: financeTransactions.filter(t => t.status !== 'deleted').reduce((acc, curr) => acc + curr.amount, 0)
              }}
            />
          )}

          <div className={`flex-1 overflow-y-auto overflow-x-hidden bg-slate-50 ${viewMode === 'dashboard' ? 'hidden' : 'block'}`}>
            <main className="p-4 md:p-8 max-w-[1600px] mx-auto w-full pb-32 md:pb-8">
              {/* Header Contextual (Desktop) */}
              <div className="hidden md:flex items-center justify-between mb-8 animate-in fade-in slide-in-from-top-4 duration-500">
                <div>
                  <h2 className="text-3xl font-black text-slate-900 tracking-tighter">
                    {activeModule === 'acoes' && (viewMode === 'gallery' ? 'Central de Ação' : viewMode === 'ferramentas' ? 'Ferramentas' : viewMode === 'sistemas-dev' ? 'Sistemas' : viewMode === 'knowledge' ? 'Conhecimento' : 'Ações')}
                    {activeModule === 'financeiro' && 'Controle Financeiro'}
                    {activeModule === 'saude' && 'Saúde & Bem-estar'}
                    {activeModule === 'projetos' && 'Gestão de Projetos'}
                  </h2>
                  <p className="text-slate-500 font-medium mt-1">
                    {activeModule === 'acoes' && 'Gerencie suas tarefas e prioridades.'}
                    {activeModule === 'financeiro' && 'Acompanhe gastos, metas e orçamentos.'}
                    {activeModule === 'saude' && 'Monitore hábitos, peso e exames.'}
                    {activeModule === 'projetos' && 'Administre bolsas, orçamentos e equipes.'}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <div className="relative">
                    <button onClick={() => setIsNotificationCenterOpen(!isNotificationCenterOpen)} className="w-12 h-12 bg-white rounded-2xl flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-300 transition-all shadow-sm">
                      <div className="relative">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                        {notifications.filter(n => !n.isRead).length > 0 && (
                          <span className="absolute -top-1 -right-1 w-3 h-3 bg-rose-500 rounded-full border-2 border-white animate-pulse"></span>
                        )}
                      </div>
                    </button>
                    <NotificationCenter
                      isOpen={isNotificationCenterOpen}
                      onClose={() => setIsNotificationCenterOpen(false)}
                      notifications={notifications}
                      onMarkRead={handleMarkNotificationRead}
                      onDismiss={handleDismissNotification}
                      onNavigate={handleNotificationNavigate}
                    />
                  </div>
                  <button onClick={() => setIsCreateModalOpen(true)} className="h-12 bg-slate-900 text-white px-6 rounded-2xl font-black uppercase tracking-widest text-xs hover:bg-slate-800 transition-all shadow-lg hover:shadow-xl hover:scale-105 active:scale-95 flex items-center gap-3">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                    Nova Ação
                  </button>
                </div>
              </div>

              {/* Views */}
              {viewMode === 'gallery' ? (
                <>
                  <div className="flex flex-col md:flex-row gap-4 mb-8 overflow-x-auto pb-2 md:pb-0 scrollbar-hide">
                    {['dashboard', 'calendar', 'day', 'pgc', 'licitacoes', 'assistencia'].map(mode => (
                      <button
                        key={mode}
                        onClick={() => {
                          if (mode === 'dashboard') setDashboardViewMode('list');
                          else if (mode === 'calendar') { setDashboardViewMode('calendar'); setCalendarViewMode('month'); }
                          else if (mode === 'day') { setDashboardViewMode('calendar'); setCalendarViewMode('day'); }
                          else setViewMode(mode as any);
                        }}
                        className={`px-6 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all whitespace-nowrap ${
                          (dashboardViewMode === 'list' && mode === 'dashboard') ||
                          (dashboardViewMode === 'calendar' && calendarViewMode === 'month' && mode === 'calendar') ||
                          (dashboardViewMode === 'calendar' && calendarViewMode === 'day' && mode === 'day') ||
                          viewMode === mode
                            ? 'bg-slate-900 text-white shadow-lg'
                            : 'bg-white text-slate-400 hover:text-slate-900 hover:bg-slate-50'
                        }`}
                      >
                        {mode === 'dashboard' ? 'Listagem' : mode === 'calendar' ? 'Calendário' : mode === 'day' ? 'Dia' : mode === 'pgc' ? 'PGC' : mode === 'licitacoes' ? 'Licitações' : 'Assistência'}
                      </button>
                    ))}
                  </div>

                  {dashboardViewMode === 'calendar' ? (
                    calendarViewMode === 'day' ? (
                      <DayView
                        tasks={tarefas}
                        googleEvents={googleCalendarEvents}
                        currentDate={calendarDate}
                        onTaskClick={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                        onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
                        onTaskUpdate={handleUpdateTarefa}
                        showToast={showToast}
                        onReorderTasks={handleReorderTasks}
                      />
                    ) : (
                      <CalendarView
                        tasks={tarefas}
                        googleEvents={googleCalendarEvents}
                        currentDate={calendarDate}
                        viewMode={calendarViewMode}
                        onDateChange={setCalendarDate}
                        onViewModeChange={setCalendarViewMode}
                        onTaskClick={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                        onTaskUpdate={handleUpdateTarefa}
                      />
                    )
                  ) : (
                    <>
                      <div className="bg-white p-4 rounded-[2rem] shadow-sm mb-8 flex flex-col md:flex-row gap-4 items-center">
                        <div className="flex-1 w-full bg-slate-50 rounded-xl px-4 py-3 flex items-center gap-3 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
                          <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                          <input
                            type="text"
                            placeholder="Pesquisar tarefas..."
                            className="bg-transparent border-none outline-none text-sm font-bold text-slate-700 placeholder:text-slate-300 w-full"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                          />
                        </div>
                        <div className="flex gap-2 w-full md:w-auto overflow-x-auto pb-2 md:pb-0 scrollbar-hide">
                          <FilterChip label="Em Andamento" active={statusFilter.includes('em andamento')} onClick={() => setStatusFilter(prev => prev.includes('em andamento') ? prev.filter(s => s !== 'em andamento') : [...prev, 'em andamento'])} />
                          <FilterChip label="Concluídas" active={statusFilter.includes('concluído')} onClick={() => setStatusFilter(prev => prev.includes('concluído') ? prev.filter(s => s !== 'concluído') : [...prev, 'concluído'])} />
                          <select
                            className="bg-slate-50 text-slate-600 text-[10px] font-black uppercase tracking-widest px-4 py-2.5 rounded-xl border-none outline-none cursor-pointer hover:bg-slate-100 transition-colors"
                            value={areaFilter}
                            onChange={(e) => setAreaFilter(e.target.value)}
                          >
                            <option value="TODAS">Todas Áreas</option>
                            <option value="CLC">CLC</option>
                            <option value="ASSISTENCIA">Assistência</option>
                            <option value="NAO CLASSIFICADA">Não Classificadas</option>
                            {/* Dynamic Areas */}
                            {Array.from(new Set(tarefas.map(t => t.categoria).filter(c => c && !['CLC', 'ASSISTÊNCIA', 'GERAL', 'NÃO CLASSIFICADA'].includes(c)))).map(c => (
                              <option key={c} value={c}>{c}</option>
                            ))}
                          </select>
                        </div>
                      </div>

                      {selectedTaskIds.length > 0 && (
                        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-6 py-4 rounded-2xl shadow-2xl z-50 flex items-center gap-6 animate-in slide-in-from-bottom-10">
                          <span className="font-bold text-sm">{selectedTaskIds.length} selecionadas</span>
                          <div className="h-4 w-px bg-white/20"></div>
                          <div className="flex gap-2">
                            <button onClick={() => handleBatchTag('CLC')} className="hover:text-blue-400 text-xs font-black uppercase transition-colors">Tag CLC</button>
                            <button onClick={() => handleBatchTag('ASSISTÊNCIA')} className="hover:text-emerald-400 text-xs font-black uppercase transition-colors">Tag Assistência</button>
                            <button onClick={() => setSelectedTaskIds([])} className="ml-4 text-slate-400 hover:text-white transition-colors">
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                          </div>
                        </div>
                      )}

                      {/* CLASSIFICAÇÃO PENDENTE - Novo Bloco */}
                      {searchTerm === 'filter:unclassified' ? (
                        <div className="animate-in fade-in slide-in-from-bottom-8 duration-500">
                          <div className="bg-white border-2 border-dashed border-slate-200 rounded-[2.5rem] p-8 mb-12">
                            <div className="flex items-center justify-between mb-8">
                              <div>
                                <h3 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                                  <span className="w-3 h-3 bg-amber-500 rounded-full animate-pulse"></span>
                                  Classificação Pendente
                                </h3>
                                <p className="text-slate-400 font-bold mt-1 text-sm">Estas tarefas precisam de categoria para organização correta.</p>
                              </div>
                              <div className="flex gap-2">
                                <button
                                  onClick={() => {
                                    if (window.confirm("Classificar automaticamente todas as visíveis?")) {
                                      filteredAndSortedTarefas.forEach(t => {
                                        const detected = detectAreaFromTitle(t.titulo);
                                        if (detected !== 'GERAL') {
                                          handleUpdateTarefa(t.id, { categoria: detected });
                                        }
                                      });
                                    }
                                  }}
                                  className="bg-amber-100 text-amber-700 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-amber-200 transition-colors"
                                >
                                  Auto-Classificar
                                </button>
                              </div>
                            </div>

                            {/* Desktop Table View */}
                            <table className="w-full text-left hidden md:table">
                              <thead className="bg-slate-50 border-b border-slate-100">
                                <tr>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-12">
                                    <input
                                      type="checkbox"
                                      onChange={(e) => setSelectedTaskIds(e.target.checked ? filteredAndSortedTarefas.map(t => t.id) : [])}
                                      checked={selectedTaskIds.length > 0 && selectedTaskIds.length === filteredAndSortedTarefas.length}
                                      className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
                                    />
                                  </th>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Tarefa</th>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-center">Sugestão IA</th>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-center w-64">Ação Rápida</th>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-center w-32">Status Sync</th>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-center w-32">Data</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-50">
                                {filteredAndSortedTarefas.map((task) => {
                                  const suggestion = detectAreaFromTitle(task.titulo);
                                  return (
                                    <tr key={task.id} className={`hover:bg-slate-50 transition-colors group ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}>
                                      <td className="px-8 py-4">
                                        <input
                                          type="checkbox"
                                          checked={selectedTaskIds.includes(task.id)}
                                          onChange={() => setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id])}
                                          className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
                                        />
                                      </td>
                                      <td className="px-8 py-4">
                                        <div onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }} className="font-bold text-slate-800 text-sm cursor-pointer hover:text-blue-600 transition-colors">
                                          {task.titulo}
                                        </div>
                                      </td>
                                      <td className="px-8 py-4 text-center">
                                        {suggestion !== 'GERAL' && (
                                          <span className="bg-amber-100 text-amber-700 px-2 py-1 rounded text-[9px] font-black uppercase tracking-wider">
                                            {suggestion}
                                          </span>
                                        )}
                                      </td>
                                      <td className="px-8 py-4">
                                        <div className="flex justify-center gap-2 opacity-100 md:opacity-0 group-hover:opacity-100 transition-opacity">
                                          <button
                                            onClick={() => handleUpdateTarefa(task.id, { categoria: 'CLC' })}
                                            className="bg-blue-100 text-blue-700 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase hover:bg-blue-200 transition-colors"
                                          >
                                            CLC
                                          </button>
                                          <button
                                            onClick={() => handleUpdateTarefa(task.id, { categoria: 'ASSISTÊNCIA' })}
                                            className="bg-emerald-100 text-emerald-700 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase hover:bg-emerald-200 transition-colors"
                                          >
                                            Assist.
                                          </button>
                                          <button
                                            onClick={() => handleUpdateTarefa(task.id, { categoria: 'GERAL' })}
                                            className="bg-slate-100 text-slate-600 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase hover:bg-slate-200 transition-colors"
                                          >
                                            Geral
                                          </button>
                                        </div>
                                      </td>
                                      <td className="px-8 py-4 text-center">
                                        <div className="flex justify-center">
                                          {task.sync_status === 'new' && (
                                            <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse">
                                              Novo
                                            </span>
                                          )}
                                          {task.sync_status === 'updated' && (
                                            <span className="text-[8px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">
                                              Atualizada
                                            </span>
                                          )}
                                        </div>
                                      </td>
                                      <td className="px-8 py-4 text-center text-[10px] font-black text-slate-400 uppercase">
                                        {formatDate(task.data_limite)}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>

                            {/* Mobile Card View */}
                            <div className="md:hidden divide-y divide-slate-50">
                              {filteredAndSortedTarefas.map((task) => (
                                <div
                                  key={task.id}
                                  onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                                  className={`p-6 space-y-4 hover:bg-slate-50 transition-colors cursor-pointer ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}
                                >
                                  <div className="flex items-start gap-4">
                                    <input
                                      type="checkbox"
                                      checked={selectedTaskIds.includes(task.id)}
                                      onChange={(e) => {
                                        e.stopPropagation();
                                        setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id]);
                                      }}
                                      className="w-6 h-6 rounded-lg border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer shrink-0 mt-1"
                                    />
                                    <div className="flex-1 space-y-2">
                                      <div className="text-sm font-bold text-slate-800 leading-snug">
                                        {task.titulo}
                                      </div>
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest bg-slate-100 px-2 py-0.5 rounded">
                                          {formatDate(task.data_limite)}
                                        </div>
                                        {task.sync_status === 'new' && (
                                          <span className="text-[7px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse">
                                            Novo
                                          </span>
                                        )}
                                        {task.sync_status === 'updated' && (
                                          <span className="text-[7px] font-black px-1.5 py-0.5 rounded uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">
                                            Atualizada
                                          </span>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>

                            {filteredAndSortedTarefas.length === 0 && (
                              <div className="py-20 text-center text-slate-300 font-black uppercase tracking-widest italic border-t border-slate-50">
                                Tudo classificado! Bom trabalho.
                              </div>
                            )}
                          </div>
                        </div>

                      ) : (
                        <div className="animate-in border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl bg-white">
                          {Object.keys(tarefasAgrupadas).length > 0 ? (
                            Object.entries(tarefasAgrupadas).map(([label, tasks]: [string, Tarefa[]]) => (
                              <div
                                key={label}
                                className="border-b last:border-b-0 border-slate-200 transition-colors"
                                onDragOver={(e) => {
                                  e.preventDefault();
                                  e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
                                }}
                                onDragLeave={(e) => {
                                  e.currentTarget.style.backgroundColor = '';
                                }}
                                onDrop={(e) => {
                                  e.preventDefault();
                                  e.currentTarget.style.backgroundColor = '';
                                  const taskId = e.dataTransfer.getData('task-id');
                                  if (taskId) {
                                    const date = getBucketStartDate(label);
                                    if (date || label === 'Sem Prazo Definido') {
                                      handleUpdateTarefa(taskId, { data_limite: date });
                                    }
                                  }
                                }}
                              >
                                <button
                                  onClick={() => toggleSection(label)}
                                  className="w-full px-6 py-3 bg-transparent border-b border-slate-100 flex items-center justify-between hover:bg-slate-50 transition-colors group"
                                >
                                  <div className="flex items-center gap-3">
                                    <span className="text-xs font-black text-slate-400 uppercase tracking-[0.2em]">{label}</span>
                                    <span className="text-[10px] font-bold text-slate-300">({tasks.length})</span>
                                  </div>
                                  <svg className={`w-4 h-4 text-slate-300 transition-transform duration-300 ${expandedSections.includes(label) ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                                  </svg>
                                </button>

                                {expandedSections.includes(label) && (
                                  <div className="animate-in origin-top">
                                    {tasks.map(task => (
                                      <div
                                        key={task.id}
                                        draggable
                                        onDragStart={(e) => {
                                          e.dataTransfer.setData('task-id', task.id);
                                          e.currentTarget.style.opacity = '0.5';
                                        }}
                                        onDragEnd={(e) => {
                                          e.currentTarget.style.opacity = '1';
                                        }}
                                        onDragOver={(e) => e.preventDefault()}
                                        onDrop={(e) => {
                                          e.preventDefault();
                                          e.stopPropagation();
                                          const draggedId = e.dataTransfer.getData('task-id');
                                          if (draggedId && draggedId !== task.id) {
                                            handleReorderTasks(draggedId, task.id, label, tarefasAgrupadas);
                                          }
                                        }}
                                      >
                                        <RowCard
                                          task={task}
                                          highlighted={label === 'Hoje' && tasks.filter(t => normalizeStatus(t.status) !== 'concluido')[0]?.id === task.id}
                                          onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                                          onToggle={handleToggleTarefaStatus}
                                          onDelete={handleDeleteTarefa}
                                          onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                          onUpdateToToday={handleUpdateToToday}
                                        />
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))
                          ) : (
                            <div className="py-24 text-center bg-white">
                              <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Sem demandas encontradas</p>
                            </div>
                          )}
                        </div>
                      )}

                      <div className="mt-12 space-y-6">
                        <button
                          onClick={() => setIsCompletedTasksOpen(!isCompletedTasksOpen)}
                          className="w-full flex items-center gap-4 group cursor-pointer"
                        >
                          <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
                          <div className="flex items-center gap-2 text-slate-400 group-hover:text-slate-600 transition-colors">
                            <h3 className="text-[10px] font-black uppercase tracking-[0.3em]">Concluídas Recentemente</h3>
                            <svg className={`w-4 h-4 transition-transform duration-300 ${isCompletedTasksOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                            </svg>
                          </div>
                          <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
                        </button>

                        {isCompletedTasksOpen && (
                          <div className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-sm opacity-60 hover:opacity-100 transition-opacity animate-in slide-in-from-top-4 duration-300">
                            {tarefas.filter(t => normalizeStatus(t.status) === 'concluido' && (t.status as any) !== 'excluído').length > 0 ? (
                              tarefas
                                .filter(t => normalizeStatus(t.status) === 'concluido' && (t.status as any) !== 'excluído')
                                .sort((a, b) => (b.data_conclusao || '').localeCompare(a.data_conclusao || ''))
                                .slice(0, 10)
                                .map(t => (
                                  <RowCard
                                    key={t.id}
                                    task={t}
                                    onClick={() => { setSelectedTask(t); setTaskModalMode('execute'); }}
                                    onToggle={handleToggleTarefaStatus}
                                    onDelete={handleDeleteTarefa}
                                    onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                    onUpdateToToday={handleUpdateToToday}
                                  />
                                ))
                            ) : (
                              <div className="py-12 text-center">
                                <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhuma tarefa concluída</p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </>
              ) : (viewMode === 'licitacoes' || viewMode === 'assistencia') ? (
                <CategoryView
                  tasks={tarefas}
                  viewMode={viewMode}
                  onSelectTask={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                  onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
                />
              ) : viewMode === 'sistemas' ? (
                <div className="animate-in space-y-8">
                  <div className="bg-white p-8 rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl">
                    <h3 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                      <span className="w-2 h-8 bg-amber-500 rounded-full"></span>
                      Desenvolvimento de Sistemas
                    </h3>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {(sistemasAtivos.length > 0
                      ? sistemasAtivos
                      : Array.from(new Set(tarefas.filter(t => t.categoria === 'SISTEMAS').map(t => t.sistema || 'OUTROS')))
                    ).map(sistema => (
                      <div key={sistema} className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-lg flex flex-col">
                        <div className="p-6 bg-slate-900 text-white flex justify-between items-center">
                          <h4 className="text-xs font-black uppercase tracking-[0.2em]">{sistema}</h4>
                          <span className="bg-white/20 px-3 py-1 rounded-full text-[10px] font-black">{tarefas.filter(t => t.categoria === 'SISTEMAS' && (t.sistema || 'OUTROS') === sistema).length}</span>
                        </div>
                        <div className="p-6 space-y-4 flex-1 bg-slate-50/50">
                          {tarefas.filter(t => t.categoria === 'SISTEMAS' && (t.sistema || 'OUTROS') === sistema).map(t => (
                            <div key={t.id} className="bg-white p-4 rounded-lg md:rounded-xl border border-slate-200 shadow-sm hover:border-amber-400 transition-all cursor-pointer" onClick={() => setSelectedTask(t)}>
                              <div className={`text-[8px] font-black mb-1.5 uppercase ${STATUS_COLORS[normalizeStatus(t.status)] || ''} border-none p-0 bg-transparent`}>
                                {t.status}
                              </div>
                              <div className="text-[11px] font-bold text-slate-700 leading-tight">{t.titulo}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

              ) : viewMode === 'saude' ? (
                <HealthView
                  weights={healthWeights}
                  dailyHabits={healthDailyHabits}
                  settings={healthSettings}
                  onUpdateSettings={handleUpdateHealthSettings}
                  onAddWeight={handleAddHealthWeight}
                  onDeleteWeight={handleDeleteHealthWeight}
                  onUpdateHabits={handleUpdateHealthHabits}
                  exams={exams}
                  onAddExam={handleAddExam}
                  onDeleteExam={async (id) => {
                    showConfirm("Confirmar Exclusão", "Deseja realmente remover este registro de saúde?", async () => {
                      await handleDeleteExam(id);
                    });
                  }}
                  onUpdateExam={handleUpdateExam}
                />
              ) : viewMode === 'ferramentas' ? (
                <FerramentasView
                  ideas={brainstormIdeas}
                  onDeleteIdea={handleDeleteIdea}
                  onArchiveIdea={handleArchiveIdea}
                  onAddTextIdea={handleAddTextIdea}
                  onUpdateIdea={handleUpdateIdea}
                  onConvertToLog={(idea) => {
                    setConvertingIdea(idea);
                    setIsSystemSelectorOpen(true);
                  }}
                  onConvertToTask={handleConvertToTask}
                  activeTool={activeFerramenta}
                  setActiveTool={setActiveFerramenta}
                  isAddingText={isBrainstormingAddingText}
                  setIsAddingText={setIsBrainstormingAddingText}
                  showToast={showToast}
                  showAlert={showAlert}
                />
              ) : viewMode === 'projects' ? (
                <ProjectsView />
              ) : viewMode === 'finance' ? (
                <FinanceView
                  transactions={financeTransactions}
                  goals={(() => {
                    const totalSavings = fixedBills
                      .filter(b => b.category === 'Poupança' && b.isPaid)
                      .reduce((acc, curr) => acc + curr.amount, 0);

                    const emergencyCurrent = financeSettings.emergencyReserveCurrent || 0;

                    const isEmergencyFull = emergencyCurrent >= (financeSettings.emergencyReserveTarget || 0);
                    let availableForGoals = isEmergencyFull ? totalSavings : 0;

                    return [...financeGoals].sort((a, b) => a.priority - b.priority).map(goal => {
                      const allocated = Math.min(availableForGoals, goal.targetAmount);
                      availableForGoals -= allocated;
                      return { ...goal, currentAmount: allocated };
                    });
                  })()}
                  emergencyReserve={{
                    target: financeSettings.emergencyReserveTarget || 0,
                    current: financeSettings.emergencyReserveCurrent || 0
                  }}
                  settings={financeSettings}
                  currentMonth={currentMonth}
                  currentYear={currentYear}
                  onMonthChange={(m, y) => {
                    setCurrentMonth(m);
                    setCurrentYear(y);
                  }}
                  currentMonthTotal={financeTransactions.filter(t => {
                    const d = new Date(t.date);
                    return d.getMonth() === currentMonth && d.getFullYear() === currentYear;
                  }).reduce((acc, curr) => acc + curr.amount, 0)}
                  currentMonthIncome={incomeEntries.filter(e => {
                    return e.month === currentMonth && e.year === currentYear;
                  }).reduce((acc, curr) => acc + curr.amount, 0)}
                  fixedBills={fixedBills}
                  billRubrics={billRubrics}
                  incomeEntries={incomeEntries}
                  incomeRubrics={incomeRubrics}
                  onAddRubric={handleAddRubric}
                  onUpdateRubric={handleUpdateRubric}
                  onDeleteRubric={handleDeleteRubric}
                  onAddIncomeRubric={handleAddIncomeRubric}
                  onUpdateIncomeRubric={handleUpdateIncomeRubric}
                  onDeleteIncomeRubric={handleDeleteIncomeRubric}
                  onAddIncomeEntry={handleAddIncomeEntry}
                  onUpdateIncomeEntry={handleUpdateIncomeEntry}
                  onDeleteIncomeEntry={handleDeleteIncomeEntry}
                  onUpdateSettings={handleUpdateSettings}
                  onAddGoal={(goal) => addDoc(collection(db, 'finance_goals'), { ...goal, priority: financeGoals.length + 1 })}
                  onUpdateGoal={handleUpdateFinanceGoal}
                  onDeleteGoal={handleDeleteFinanceGoal}
                  onReorderGoals={handleReorderFinanceGoals}
                  onAddBill={handleAddBill}
                  onUpdateBill={handleUpdateBill}
                  onDeleteBill={handleDeleteBill}
                  onAddTransaction={handleAddTransaction}
                  onUpdateTransaction={handleUpdateTransaction}
                  onDeleteTransaction={handleDeleteTransaction}
                  activeTab={financeActiveTab}
                  setActiveTab={setFinanceActiveTab}
                  isSettingsOpen={isFinanceSettingsOpen}
                  setIsSettingsOpen={setIsFinanceSettingsOpen}
                />

              ) : viewMode === 'knowledge' ? (
                <KnowledgeView
                  items={knowledgeItems}
                  onDeleteItem={async (id) => { await deleteDoc(doc(db, 'conhecimento', id)); }}
                  onUploadFile={handleFileUploadToDrive}
                  onAddLink={async (item) => { await addDoc(collection(db, 'conhecimento'), item); }}
                  onSaveItem={async (id, updates) => { await updateDoc(doc(db, 'conhecimento', id), updates); }}
                  onProcessWithAI={async () => { /* Logic integrated in KnowledgeView or can be extracted */ }}
                  onGenerateSlides={async () => { /* Logic integrated in KnowledgeView or can be extracted */ }}
                  showConfirm={showConfirm}
                  allTasks={tarefas}
                  allWorkItems={workItems}
                />
              ) : viewMode === 'sistemas-dev' ? (
                <SistemasDevView
                  unidades={unidades}
                  sistemasDetalhes={sistemasDetalhes}
                  workItems={workItems}
                  selectedSystemId={selectedSystemId}
                  setSelectedSystemId={setSelectedSystemId}
                  newLogText={newLogText}
                  setNewLogText={setNewLogText}
                  newLogTipo={newLogTipo}
                  setNewLogTipo={setNewLogTipo}
                  newLogAttachments={newLogAttachments}
                  setNewLogAttachments={setNewLogAttachments}
                  isRecordingLog={isRecordingLog}
                  isProcessingLog={isProcessingLog}
                  startLogRecording={startLogRecording}
                  stopLogRecording={stopLogRecording}
                  isUploading={isUploading}
                  handleFileUploadToDrive={handleFileUploadToDrive}
                  handleCreateWorkItem={handleCreateWorkItem}
                  handleUpdateWorkItem={handleUpdateWorkItem}
                  handleDeleteWorkItem={handleDeleteWorkItem}
                  handleUpdateSistema={handleUpdateSistema}
                  setIsSettingsModalOpen={setIsSettingsModalOpen}
                />
              ) : (
                <div className="space-y-3 md:space-y-10">
                  {/* PGC View Logic from index.tsx */}
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-6 bg-white p-3 md:p-8 rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl">
                      {/* ... PGC Header ... */}
                  </div>
                  {/* ... PGC Content ... */}
                </div>
              )}
            </main>
          </div>
        </>
      </div>

      <ToastContainer toasts={toasts} removeToast={removeToast} />
      <HermesModal {...modalState} />

      {
        isCreateModalOpen && (
          <TaskCreateModal
            unidades={unidades}
            onSave={handleCreateTarefa}
            onClose={() => {
              setIsCreateModalOpen(false);
              setTaskInitialData(null);
            }}
            showAlert={showAlert}
            initialData={taskInitialData || undefined}
          />
        )
      }

      {
        selectedTask && (
          (taskModalMode === 'execute' || (taskModalMode === 'default' && selectedTask.categoria === 'CLC')) ? (
            <TaskExecutionView
              task={selectedTask}
              tarefas={tarefas}
              appSettings={appSettings}
              onSave={handleUpdateTarefa}
              onClose={() => setSelectedTask(null)}
              showToast={showToast}
            />
          ) : (
            <TaskEditModal
              unidades={unidades}
              task={selectedTask}
              onSave={handleUpdateTarefa}
              onDelete={handleDeleteTarefa}
              onClose={() => setSelectedTask(null)}
              showAlert={showAlert}
              showConfirm={showConfirm}
              pgcEntregas={pgcEntregas}
            />
          )
        )
      }

      {
        isSettingsModalOpen && (
          <SettingsModal
            settings={appSettings}
            unidades={unidades}
            initialTab={settingsTab}
            onSave={handleUpdateAppSettings}
            onClose={() => {
              setIsSettingsModalOpen(false);
              setSettingsTab('notifications');
            }}
            onAddUnidade={handleAddUnidade}
            onDeleteUnidade={handleDeleteUnidade}
            onUpdateUnidade={handleUpdateUnidade}
            onEmitNotification={emitNotification}
            showConfirm={showConfirm}
          />
        )
      }

      {
        isHabitsReminderOpen && (
          <DailyHabitsModal
            habits={healthDailyHabits.find(h => h.id === formatDateLocalISO(new Date())) || {
              id: formatDateLocalISO(new Date()),
              noSugar: false,
              noAlcohol: false,
              noSnacks: false,
              workout: false,
              eatUntil18: false,
              eatSlowly: false
            }}
            onUpdateHabits={handleUpdateHealthHabits}
            onClose={() => setIsHabitsReminderOpen(false)}
          />
        )
      }

      {
        isImportPlanOpen && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
             {/* Import Plan Modal Content */}
          </div>
        )
      }

      {isSystemSelectorOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
             {/* System Selector Modal Content */}
        </div>
      )}

      {isQuickNoteModalOpen && (
        <QuickNoteModal
          isOpen={isQuickNoteModalOpen}
          onClose={() => setIsQuickNoteModalOpen(false)}
          onAddIdea={handleAddTextIdea}
          showAlert={showAlert}
        />
      )}

      {isQuickLogModalOpen && (
        <QuickLogModal
          isOpen={isQuickLogModalOpen}
          onClose={() => setIsQuickLogModalOpen(false)}
          onAddLog={handleAddQuickLog}
          unidades={unidades}
        />
      )}

      {isShoppingAIModalOpen && (
        <ShoppingAIModal
          isOpen={isShoppingAIModalOpen}
          onClose={() => setIsShoppingAIModalOpen(false)}
          onProcessItems={handleShoppingAIInput}
          onViewList={() => {
            setActiveFerramenta('shopping');
            setIsShoppingAIModalOpen(false);
          }}
        />
      )}
    </div>
  );
};

export default App;
