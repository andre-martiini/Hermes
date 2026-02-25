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
import { STATUS_COLORS, PROJECT_COLORS } from './constants';

import DashboardView from './views/DashboardView';
import FinanceView from './views/FinanceView';
import HealthView from './views/HealthView';
import KnowledgeView from './views/KnowledgeView';
import ProjectsView from './views/ProjectsView';
import { DayView } from './views/DayView';
import { CalendarView } from './views/CalendarView';
import { CategoryView } from './views/CategoryView';
import { TaskExecutionView } from './views/TaskExecutionView';
import { PublicScholarshipRegistration } from './components/public/PublicScholarshipRegistration';

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

import { SlidesTool } from './components/tools/SlidesTool';
import { ShoppingListTool } from './components/tools/ShoppingListTool';
import { FerramentasView } from './components/tools/FerramentasView';
import { QuickNoteModal } from './components/modals/QuickNoteModal';
import { QuickLogModal } from './components/modals/QuickLogModal';
import { ShoppingAIModal } from './components/modals/ShoppingAIModal';

import { useAuth } from './hooks/useAuth';
import { useTasks } from './hooks/useTasks';
import { useFinance } from './hooks/useFinance';
import { useHealth } from './hooks/useHealth';
import { useSystemSync } from './hooks/useSystemSync';
import { useNotifications } from './hooks/useNotifications';
import { useToast } from './hooks/useToast';

type SortOption = 'date-asc' | 'date-desc' | 'priority-high' | 'priority-low';
type DateFilter = 'today' | 'week' | 'month';

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
  if (window.location.pathname.startsWith('/join/')) {
    return <PublicScholarshipRegistration />;
  }

  const { toasts, showToast, removeToast } = useToast();
  const { user, authLoading, rememberMe, setRememberMe, handleLogin, handleLogout } = useAuth(showToast);

  const {
    tarefas, brainstormIdeas, undoStack, loading: tasksLoading, error: tasksError,
    convertingIdea, setConvertingIdea, taskInitialData, setTaskInitialData,
    isCreateModalOpen, setIsCreateModalOpen,
    handleCreateTarefa, handleUpdateTarefa, handleDeleteTarefa, handleToggleTarefaStatus,
    handleUndo, pushToUndoStack, handleReorderTasks,
    handleDeleteIdea, handleArchiveIdea, handleAddTextIdea, handleUpdateIdea
  } = useTasks(showToast);

  const {
    financeTransactions, financeGoals, financeSettings, fixedBills, billRubrics,
    incomeEntries, incomeRubrics, activeTab: financeActiveTab, setActiveTab: setFinanceActiveTab,
    isSettingsOpen: isFinanceSettingsOpen, setIsSettingsOpen: setIsFinanceSettingsOpen,
    handleUpdateFinanceGoal, handleDeleteFinanceGoal, handleReorderFinanceGoals
  } = useFinance(tarefas, showToast);

  const {
    healthWeights, healthDailyHabits, healthSettings, exams,
    handleUpdateHealthSettings, handleAddHealthWeight, handleDeleteHealthWeight, handleUpdateHealthHabits
  } = useHealth(showToast);

  const {
    sistemasDetalhes, workItems, unidades, planosTrabalho, atividadesPGC, afastamentos, sistemasAtivos, googleCalendarEvents, isUploading,
    handleCreateWorkItem, handleUpdateWorkItem, handleDeleteWorkItem, handleUpdateSistema,
    handleAddUnidade, handleDeleteUnidade, handleUpdateUnidade, handleFileUploadToDrive,
    handleUploadKnowledgeFile, handleDeleteKnowledgeItem, handleAddKnowledgeLink, handleSaveKnowledgeItem,
    handleProcessarIA, handleGenerateSlides, knowledgeItems, entregas, syncData
  } = useSystemSync(showToast, pushToUndoStack);

  const {
    notifications, activePopup, setActivePopup, isNotificationCenterOpen, setIsNotificationCenterOpen,
    appSettings, isHabitsReminderOpen, setIsHabitsReminderOpen,
    emitNotification, handleMarkNotificationRead, handleDismissNotification, handleUpdateAppSettings
  } = useNotifications(tarefas, showToast);

  // App UI State
  const [modalState, setModalState] = useState<HermesModalProps>({
    isOpen: false,
    title: '',
    message: '',
    type: 'alert',
    onConfirm: () => { }
  });

  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [isCompletedLogsOpen, setIsCompletedLogsOpen] = useState(false);

  const [dashboardViewMode, setDashboardViewMode] = useState<'list' | 'calendar'>('list');
  const [calendarViewMode, setCalendarViewMode] = useState<'month' | 'week' | 'day'>('month');
  const [calendarDate, setCalendarDate] = useState(new Date());

  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [searchTerm, setSearchTerm] = useState('');
  const [activeModule, setActiveModule] = useState<'home' | 'dashboard' | 'acoes' | 'financeiro' | 'saude' | 'projetos'>('dashboard');
  const [viewMode, setViewMode] = useState<'dashboard' | 'gallery' | 'pgc' | 'licitacoes' | 'assistencia' | 'sistemas' | 'finance' | 'saude' | 'ferramentas' | 'sistemas-dev' | 'knowledge' | 'projects'>('dashboard');
  const [selectedTask, setSelectedTask] = useState<Tarefa | null>(null);
  const [isSidebarRetracted, setIsSidebarRetracted] = useState(false);

  const [taskModalMode, setTaskModalMode] = useState<'default' | 'edit' | 'execute'>('default');
  const [statusFilter, setStatusFilter] = useState<Status[]>(['em andamento']);
  const [areaFilter, setAreaFilter] = useState<string>('TODAS');
  const [sortOption, setSortOption] = useState<SortOption>('date-asc');
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'notifications' | 'context' | 'sistemas'>('notifications');
  const [isImportPlanOpen, setIsImportPlanOpen] = useState(false);
  const [isCompletedTasksOpen, setIsCompletedTasksOpen] = useState(false);

  const [activeFerramenta, setActiveFerramenta] = useState<'brainstorming' | 'slides' | 'shopping' | null>(null);
  const [isBrainstormingAddingText, setIsBrainstormingAddingText] = useState(false);
  const [confirmDeleteLogId, setConfirmDeleteLogId] = useState<string | null>(null);
  const [isSystemSelectorOpen, setIsSystemSelectorOpen] = useState(false);

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
  const [isRecordingLog, setIsRecordingLog] = useState(false);
  const [isProcessingLog, setIsProcessingLog] = useState(false);
  const logMediaRecorderRef = useRef<MediaRecorder | null>(null);
  const logAudioChunksRef = useRef<Blob[]>([]);
  const [isQuickNoteModalOpen, setIsQuickNoteModalOpen] = useState(false);
  const [hasAutoExpanded, setHasAutoExpanded] = useState(false);
  const [pgcSubView, setPgcSubView] = useState<'audit' | 'heatmap' | 'config' | 'plano'>('audit');

  const [lastBackPress, setLastBackPress] = useState(0);

  // Sync selectedTask
  useEffect(() => {
    if (selectedTask) {
      const updated = tarefas.find(t => t.id === selectedTask.id);
      if (updated && JSON.stringify(updated) !== JSON.stringify(selectedTask)) {
        setSelectedTask(updated);
      }
    }
  }, [tarefas, selectedTask]);

  // Modal Mode Reset
  useEffect(() => {
    if (!selectedTask) {
      setTaskModalMode('default');
    }
  }, [selectedTask]);

  const handleDashboardNavigate = (view: 'gallery' | 'finance' | 'saude' | 'sistemas-dev') => {
    setViewMode(view);
    if (view === 'gallery' || view === 'sistemas-dev') setActiveModule('acoes');
    else if (view === 'finance') setActiveModule('financeiro');
    else if (view === 'saude') setActiveModule('saude');
  };

  // History / Back Button
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
  }, [activeModule, viewMode, selectedSystemId, isLogsModalOpen, activeFerramenta, lastBackPress, showToast]);

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

  const handleAddQuickLog = async (text: string, systemId: string) => {
    try {
      await handleCreateWorkItem(systemId, 'desenvolvimento', text, [], true);
      showToast("Log registrado!", "success", {
        label: "Ver",
        onClick: () => {
          setSelectedSystemId(systemId);
          setViewMode('sistemas-dev');
          setActiveModule('acoes');
        }
      });
    } catch (err) {
      console.error(err);
      showToast("Erro ao registrar log.", "error");
    }
  };

  const handleFinalizeIdeaConversion = async (sistemaId: string) => {
    if (!convertingIdea) return;
    const unit = unidades.find(u => u.id === sistemaId);
    if (!unit) return;

    await handleCreateWorkItem(sistemaId, 'ajuste', convertingIdea.text, [], true);
    await handleDeleteIdea(convertingIdea.id); // Assuming this is passed from useTasks

    setIsSystemSelectorOpen(false);
    setConvertingIdea(null);
    showToast("Nota convertida em log do sistema com sucesso!", "success");
  };

  const handleConvertToTask = (idea: BrainstormIdea) => {
    const timeMatch = idea.text.match(/\[Horário:\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\]/);
    const start = timeMatch ? timeMatch[1] : '';
    const end = timeMatch ? timeMatch[2] : '';

    setTaskInitialData({
      titulo: idea.text.replace(/\[Horário:\s*\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\]/g, '').trim(),
      notas: idea.text,
      horario_inicio: start,
      horario_fim: end,
      data_inicio: formatDateLocalISO(new Date()),
      data_limite: formatDateLocalISO(new Date())
    });
    setConvertingIdea(idea);
    setIsCreateModalOpen(true);
  };

  const handleShoppingAIInput = (text: string) => {
    // This requires Shopping List logic which is in ShoppingListTool component.
    // The original app seemed to handle this in ShoppingAIModal prop onProcessItems.
    // In original code (index.tsx), handleShoppingAIInput logic accessed localStorage.
    // I should move this logic to useFinance? No, shopping list tool is separate.
    // ShoppingListTool manages its own state via localStorage.
    // So handleShoppingAIInput logic should read/write localStorage directly.
    // I'll define it here.

    // Logic from index.tsx:
    const SHOPPING_ITEMS_KEY = 'hermes_shopping_items';
    const items = JSON.parse(localStorage.getItem(SHOPPING_ITEMS_KEY) || '[]');
    // ... matching logic ...
    // Since this is tool specific, maybe I should have put it in ShoppingListTool?
    // But ShoppingAIModal is global (in App).
    // I'll include the logic here.
    
    try {
      const storedItems: ShoppingItem[] = JSON.parse(localStorage.getItem('hermes_shopping_items') || '[]');
      const userItems = text.split(/[\n,]+/).map(s => s.trim().toLowerCase()).filter(s => s);
      let matchedCount = 0;

      const updatedItems = storedItems.map(item => {
        if (userItems.some(ui => item.nome.toLowerCase().includes(ui) || ui.includes(item.nome.toLowerCase()))) {
          matchedCount++;
          return { ...item, isPlanned: true };
        }
        return item;
      });

      if (matchedCount > 0) {
        localStorage.setItem('hermes_shopping_items', JSON.stringify(updatedItems));
        showToast(`${matchedCount} itens adicionados ao seu planejamento!`, "success", { label: "Ver Lista", onClick: () => setActiveFerramenta('shopping') });
        if (activeFerramenta === 'shopping') {
           setActiveFerramenta(null);
           setTimeout(() => setActiveFerramenta('shopping'), 50);
        }
      } else {
        showToast("Não encontramos itens correspondentes nas suas listas.", "info");
      }
    } catch (err) {
      console.error(err);
      showToast("Erro ao processar compras via IA.", "error");
    }
  };

  const handleUpdateToToday = (t: Tarefa) => {
    handleUpdateTarefa(t.id, {
      data_limite: formatDateLocalISO(new Date()),
      horario_inicio: '',
      horario_fim: ''
    });
  };

  const handleNavigateToOrigin = (modulo: string, id: string) => {
    switch (modulo) {
      case 'tarefas':
        const task = tarefas.find(t => t.id === id);
        if (task) {
          setSelectedTask(task);
          if (task.categoria === 'CLC') setViewMode('licitacoes');
          else if (task.categoria === 'ASSISTÊNCIA') setViewMode('assistencia');
          else setViewMode('gallery');
          setActiveModule('acoes');
        } else {
          showToast("Ação não encontrada.", "error");
        }
        break;
      case 'sistemas':
        const workItem = workItems.find(w => w.id === id);
        if (workItem) {
          setSelectedSystemId(workItem.sistema_id);
          setViewMode('sistemas-dev');
          setActiveModule('acoes');
        } else {
          showToast("Log de sistema não encontrado.", "error");
        }
        break;
      case 'saude':
        const exam = exams.find(e => e.id === id);
        if (exam) {
          setViewMode('saude');
          setActiveModule('saude');
        } else {
          showToast("Exame não encontrado.", "error");
        }
        break;
      default:
        showToast("Módulo não mapeado para navegação.", "info");
    }
  };

  // --- Render ---
  // I need to use the large JSX from index.tsx but replacing state/handlers.
  // Since I cannot copy-paste 2000 lines of JSX blindly, and I don't have it fully in memory (sed output was truncated).
  // I must read the JSX part of App.
  // App render starts after hooks/logic.
  // I'll need to use the `sed` output of `App` I got earlier but stitch it together.
  // Or I can just read the whole file content to a temporary file, then cat it?
  // `read_file` failed because file is too large? No, it just said "truncated".
  // I can use `split` to read it in chunks if I really need to copy it exactly.
  // Or I can try to construct the App structure.

  // The user wants me to refactor. Re-writing the JSX is part of it.
  // I will assume the structure:
  // <div className="flex h-screen ...">
  //   Sidebar
  //   Main Content
  //     Header
  //     Views (Dashboard, Finance, etc)
  //   Modals
  // </div>

  // I will create `src/App.tsx` with placeholders for the huge JSX, then I will use `sed` to extract the JSX from `index.tsx` and append it/inject it.
  // `index.tsx` JSX starts around line 2730 (based on logic ending).

  // Actually, I can just use `cp index.tsx src/App.tsx` then edit it.
  // 1. Copy `index.tsx` to `src/App.tsx`.
  // 2. Remove imports and top level definitions (replace with new imports).
  // 3. Remove `SlidesTool`, `ShoppingListTool`, etc components definitions.
  // 4. Remove `App` logic that was moved to hooks.
  // 5. Replace state declarations with hook calls.
  // 6. Fix `root.render` at the end (remove it, export App instead).

  // This seems safer than retyping.

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col md:flex-row relative">

      {/* Pop-up de Notificação */}
      {activePopup && (
        <div className="fixed bottom-8 left-4 right-4 md:left-8 md:right-auto z-[200] max-w-sm ml-auto mr-auto md:ml-0 md:mr-0 bg-white rounded-none md:rounded-[2.5rem] shadow-[0_30px_60px_rgba(0,0,0,0.25)] border border-slate-100 overflow-hidden animate-in slide-in-from-bottom-12 duration-500">
          <div className={`h-2 w-full ${activePopup.type === 'success' ? 'bg-emerald-500' :
            activePopup.type === 'warning' ? 'bg-amber-500' :
              activePopup.type === 'error' ? 'bg-rose-500' : 'bg-blue-600'
            }`} />
          <div className="p-8">
            <div className="flex justify-between items-start mb-3">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em]">{activePopup.title}</span>
                <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse"></span>
              </div>
              <button onClick={() => setActivePopup(null)} className="text-slate-300 hover:text-slate-600 transition-colors p-1">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed font-bold">{activePopup.message}</p>
            <div className="mt-6 flex gap-3">
              <button
                onClick={() => setActivePopup(null)}
                className="flex-1 px-5 py-3 bg-slate-100 text-slate-500 rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-widest transition-all hover:bg-slate-200"
              >
                Entendido
              </button>
              {activePopup.link && (
                <button
                  onClick={() => {
                    handleNotificationNavigate(activePopup.link);
                    setActivePopup(null);
                  }}
                  className="flex-1 px-5 py-3 bg-slate-900 text-white rounded-lg md:rounded-xl text-[9px] font-black uppercase tracking-widest transition-all hover:bg-slate-800 shadow-lg shadow-slate-200"
                >
                  Ver Agora
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Sidebar Desktop */}
      <aside className={`hidden md:flex ${isSidebarRetracted ? 'w-24' : 'w-72'} bg-slate-900 text-white flex-col h-screen sticky top-0 overflow-y-auto shrink-0 z-50 shadow-2xl transition-all duration-300`}>
        <div className={`p-8 flex flex-col h-full ${isSidebarRetracted ? 'gap-8 items-center pt-10' : 'gap-10'}`}>
          <div 
            className={`flex items-center gap-4 cursor-pointer hover:opacity-80 transition-opacity ${isSidebarRetracted ? 'flex-col' : ''}`}
            onClick={() => setIsSidebarRetracted(!isSidebarRetracted)}
          >
            <img src="/logo.png" alt="Hermes" className={`${isSidebarRetracted ? 'w-14 h-14' : 'w-12 h-12'} object-contain`} />
            {!isSidebarRetracted && (
              <div>
                <h1 className="text-2xl font-black tracking-tighter">HERMES</h1>
                <p className="text-[8px] font-black text-slate-500 uppercase tracking-widest leading-none">Management System</p>
              </div>
            )}
          </div>

          <nav className="flex flex-col gap-2">
            {[
              { id: 'dashboard', label: 'Dashboard', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>, active: viewMode === 'dashboard', onClick: () => { setActiveModule('dashboard'); setViewMode('dashboard'); } },
              { id: 'acoes', label: 'Ações', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>, active: activeModule === 'acoes' && (viewMode === 'gallery' || viewMode === 'pgc' || viewMode === 'licitacoes' || viewMode === 'assistencia'), onClick: () => { setActiveModule('acoes'); setViewMode('gallery'); } },
              { id: 'projetos', label: 'Projetos', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>, active: activeModule === 'projetos' && viewMode === 'projects', onClick: () => { setActiveModule('projetos'); setViewMode('projects'); } },
              { id: 'finance', label: 'Financeiro', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>, active: activeModule === 'financeiro', onClick: () => { setActiveModule('financeiro'); setViewMode('finance'); } },
              { id: 'saude', label: 'Saúde', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>, active: activeModule === 'saude', onClick: () => { setActiveModule('saude'); setViewMode('saude'); } },
              { id: 'sistemas', label: 'Sistemas', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>, active: viewMode === 'sistemas-dev', onClick: () => { setActiveModule('acoes'); setViewMode('sistemas-dev'); } },
              { id: 'conhecimento', label: 'Conhecimento', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>, active: viewMode === 'knowledge', onClick: () => { setActiveModule('acoes'); setViewMode('knowledge'); } },
              { id: 'ferramentas', label: 'Ferramentas', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>, active: viewMode === 'ferramentas', onClick: () => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta(null); } },
            ].map(item => (
              <button
                key={item.id}
                onClick={item.onClick}
                className={`flex items-center gap-4 px-6 py-4 rounded-2xl transition-all duration-300 group ${item.active ? 'bg-white text-slate-900 shadow-xl' : 'text-slate-400 hover:text-white hover:bg-white/5'} ${isSidebarRetracted ? 'justify-center' : ''}`}
                title={isSidebarRetracted ? item.label : ''}
              >
                <div className={`${item.active ? 'text-slate-900' : 'group-hover:scale-110 transition-transform duration-300'}`}>
                  {item.icon}
                </div>
                {!isSidebarRetracted && <span className="text-[11px] font-black uppercase tracking-widest">{item.label}</span>}
              </button>
            ))}
          </nav>

          <div className="mt-auto flex flex-col gap-6">
            <div className={`flex items-center gap-3 bg-white/5 p-4 rounded-2xl border border-white/5 ${isSidebarRetracted ? 'flex-col gap-4' : ''}`}>
              {isSidebarRetracted ? (
                <>
                  <div 
                    className="w-10 h-10 rounded-xl bg-slate-800 flex items-center justify-center font-black text-[10px] text-white border border-white/10 shadow-lg"
                    title={user?.displayName || "Usuário"}
                  >
                    {user?.displayName ? user.displayName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) : 'A'}
                  </div>
                  <button
                    onClick={handleLogout}
                    className="p-2 text-slate-500 hover:text-rose-400 transition-colors"
                    title="Sair do Sistema"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                  </button>
                </>
              ) : (
                <>
                  {user?.photoURL ? (
                    <img src={user.photoURL} alt="Profile" className="w-10 h-10 rounded-xl shadow-sm border border-white/10" />
                  ) : (
                    <div className="w-10 h-10 rounded-xl bg-slate-800 flex items-center justify-center font-black text-xs text-white border border-white/10">
                      {user?.displayName ? user.displayName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) : 'A'}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] font-black uppercase tracking-tight text-white truncate">{user?.displayName}</p>
                    <button
                      onClick={handleLogout}
                      className="text-[8px] font-black text-slate-500 hover:text-rose-400 uppercase tracking-widest transition-colors"
                    >
                      Sair do Sistema
                    </button>
                  </div>
                </>
              )}
            </div>
            {!isSidebarRetracted && (
              <p className="text-center text-[8px] font-black text-slate-700 uppercase tracking-widest">
                Hermes v2.5.0 • 2024
              </p>
            )}
          </div>
        </div>
      </aside>

      {/* Conteúdo Principal */}
      <div className="flex-1 flex flex-col relative min-h-screen">
        <>
          <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
            <div className="max-w-[1400px] mx-auto px-4 md:px-8 py-3 md:py-4">
              {/* Mobile Header */}
              <div className="flex md:hidden items-center justify-between">
                <div className="flex items-center gap-4">
                  <button
                    onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                    className="p-2 text-slate-700 hover:bg-slate-100 rounded-lg transition-all active:scale-95"
                    aria-label="Menu"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      {isMobileMenuOpen ? (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                      ) : (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" />
                      )}
                    </svg>
                  </button>
                  <div 
                    onClick={() => { setActiveModule('dashboard'); setViewMode('dashboard'); }}
                    className="flex items-center cursor-pointer hover:opacity-80 transition-opacity"
                  >
                    <img src="/logo.png" alt="Hermes" className="w-9 h-9 object-contain" />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <button
                      onClick={() => setIsQuickNoteModalOpen(true)}
                      className="p-1.5 rounded-lg md:rounded-xl hover:bg-slate-100 transition-colors text-amber-500"
                      aria-label="Notas Rápidas"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => {
                        setIsQuickLogModalOpen(true);
                        setIsMobileMenuOpen(false);
                      }}
                      className="p-1.5 rounded-lg md:rounded-xl hover:bg-slate-100 transition-colors text-violet-600"
                      aria-label="Log Rápido de Sistema"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => {
                        setIsShoppingAIModalOpen(true);
                        setIsMobileMenuOpen(false);
                      }}
                      className="p-1.5 rounded-lg md:rounded-xl hover:bg-slate-100 transition-colors text-emerald-600"
                      aria-label="Inteligência de Compras"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsSettingsModalOpen(true)}
                      className="p-1.5 rounded-lg md:rounded-xl hover:bg-slate-100 transition-colors"
                      aria-label="Configurações"
                    >
                      <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsNotificationCenterOpen(!isNotificationCenterOpen)}
                      className="p-1.5 rounded-lg md:rounded-xl hover:bg-slate-100 transition-colors relative notification-trigger"
                      aria-label="Notificações"
                    >
                      <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                      {notifications.some(n => !n.isRead) && (
                        <span className="absolute top-2.5 right-2.5 w-2.5 h-2.5 bg-rose-500 border-2 border-white rounded-full"></span>
                      )}
                    </button>
                    <NotificationCenter
                      notifications={notifications}
                      onMarkAsRead={handleMarkNotificationRead}
                      onDismiss={handleDismissNotification}
                      isOpen={isNotificationCenterOpen}
                      onClose={() => setIsNotificationCenterOpen(false)}
                      onUpdateOverdue={handleUpdateOverdueTasks}
                      onNavigate={handleNotificationNavigate}
                    />
                  </div>
                  <div className="relative">
                    <button
                      onClick={handleSync}
                      className="p-1.5 rounded-lg md:rounded-xl hover:bg-slate-100 transition-colors text-slate-700 relative"
                      aria-label="Sincronizar"
                      title={isSyncing ? 'Monitorar Sync' : 'Sync Google'}
                    >
                      <svg className={`w-5 h-5 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                      {isSyncing && (
                        <span className="absolute top-2.5 right-2.5 w-2.5 h-2.5 bg-blue-500 border-2 border-white rounded-full animate-ping"></span>
                      )}
                    </button>
                  </div>
                  {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && viewMode !== 'knowledge' && viewMode !== 'saude' && viewMode !== 'finance' && viewMode !== 'dashboard' && viewMode !== 'projects' && (
                    <button
                      onClick={() => setIsCreateModalOpen(true)}
                      className="bg-slate-900 text-white p-1.5 rounded-lg md:rounded-xl shadow-lg hover:bg-slate-800 transition-all active:scale-95"
                      aria-label="Criar Ação"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                    </button>
                  )}
                </div>
              </div>

              {/* Opções de Sub-módulo para Mobile (Ações / PGC) */}
              {(viewMode === 'gallery' || viewMode === 'pgc') && activeModule === 'acoes' && (
                <div className="flex md:hidden items-center gap-2 mt-3 pt-3 border-t border-slate-100 animate-in slide-in-from-top-2 duration-300">
                  <button
                    onClick={() => {
                      setViewMode('gallery');
                      setSearchTerm('');
                    }}
                    className={`flex-1 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'gallery' ? 'bg-slate-900 text-white shadow-lg' : 'bg-slate-50 text-slate-500 hover:bg-slate-100'}`}
                  >
                    Ações
                  </button>
                  <button
                    onClick={() => setViewMode('pgc')}
                    className={`flex-1 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'pgc' ? 'bg-slate-900 text-white shadow-lg' : 'bg-slate-50 text-slate-500 hover:bg-slate-100'}`}
                  >
                    PGC
                  </button>
                </div>
              )}

              {/* Opções de Financeiro para Mobile */}
              {viewMode === 'finance' && (
                <div className="flex flex-col md:hidden gap-3 mt-3 pt-3 border-t border-slate-100 animate-in slide-in-from-top-2 duration-300">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 flex bg-slate-100 p-1 rounded-xl border border-slate-200">
                      <button
                        onClick={() => setFinanceActiveTab('dashboard')}
                        className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'dashboard' ? 'bg-white text-slate-900 shadow-sm border border-slate-100' : 'text-slate-400 hover:text-slate-600'}`}
                      >
                        Visão Geral
                      </button>
                      <button
                        onClick={() => setFinanceActiveTab('fixed')}
                        className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'fixed' ? 'bg-white text-slate-900 shadow-sm border border-slate-100' : 'text-slate-400 hover:text-slate-600'}`}
                      >
                        Obrigações
                      </button>
                    </div>
                    <button
                      onClick={() => setIsFinanceSettingsOpen(!isFinanceSettingsOpen)}
                      className={`p-2.5 rounded-xl transition-all border ${isFinanceSettingsOpen ? 'bg-slate-900 text-white border-slate-900 shadow-lg' : 'bg-white text-slate-400 border-slate-200 hover:bg-slate-50 hover:text-slate-900 shadow-sm'}`}
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                    </button>
                  </div>
                  
                  <div className="flex items-center justify-between bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden h-11">
                    <button
                      onClick={() => {
                        const newMonth = currentMonth === 0 ? 11 : currentMonth - 1;
                        const newYear = currentMonth === 0 ? currentYear - 1 : currentYear;
                        setCurrentMonth(newMonth);
                        setCurrentYear(newYear);
                      }}
                      className="px-4 h-full flex items-center hover:bg-slate-50 text-slate-400 hover:text-slate-900 transition-all border-r border-slate-100"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" /></svg>
                    </button>
                    <div className="px-4 text-center">
                        <div className="text-xs font-black text-slate-900 capitalize tracking-tight">
                            {new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}
                        </div>
                    </div>
                    <button
                      onClick={() => {
                        const newMonth = currentMonth === 11 ? 0 : currentMonth + 1;
                        const newYear = currentMonth === 11 ? currentYear + 1 : currentYear;
                        setCurrentMonth(newMonth);
                        setCurrentYear(newYear);
                      }}
                      className="px-4 h-full flex items-center hover:bg-slate-50 text-slate-400 hover:text-slate-900 transition-all border-l border-slate-100"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                    </button>
                  </div>
                </div>
              )}

              {/* Desktop Header */}
              <div className="hidden md:flex items-center justify-between gap-4">
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-3">
                    {/* Botão de voltar removido pois agora temos sidebar */}
                    <div 
                      onClick={() => { setActiveModule('dashboard'); setViewMode('dashboard'); }}
                      className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity"
                    >
                      <h1 className="text-xl font-black tracking-tighter text-slate-900 uppercase">
                        {viewMode === 'projects' ? 'Projetos' :
                         viewMode === 'knowledge' ? 'Conhecimento' : 
                         viewMode === 'sistemas-dev' ? 'Sistemas' :
                         viewMode === 'ferramentas' ? 'Ferramentas' :
                         activeModule === 'dashboard' ? 'Dashboard' : 
                         activeModule === 'acoes' ? 'Ações' : 
                         activeModule === 'financeiro' ? 'Financeiro' : 
                         activeModule === 'saude' ? 'Saúde' : 'Hermes'}
                      </h1>
                    </div>
                  </div>
                  {viewMode === 'projects' && (
                    <div className="flex items-center gap-3 animate-in fade-in slide-in-from-left duration-500">
                      <button 
                        onClick={() => setIsCreateModalOpen(true)} 
                        className="p-2 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200"
                        title="Novo Projeto"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                      </button>
                      <button className="p-2 bg-white border border-slate-200 text-slate-400 rounded-xl hover:bg-slate-50 transition-all shadow-sm">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 4.5h18m-18 5h18m-18 5h18m-18 5h18" /></svg>
                      </button>
                    </div>
                  )}

                  {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && viewMode !== 'knowledge' && viewMode !== 'projects' && activeModule !== 'financeiro' && activeModule !== 'saude' && activeModule !== 'dashboard' && (
                    <nav className="flex bg-slate-100 p-1 rounded-lg md:rounded-xl border border-slate-200">
                      <button
                        onClick={() => {
                          setViewMode('gallery');
                          setSearchTerm('');
                        }}
                        className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'gallery' && !searchTerm ? 'bg-white text-slate-900 shadow-sm border border-slate-100' : 'text-slate-500 hover:text-slate-800'}`}
                      >
                        Ações
                      </button>
                      <button onClick={() => setViewMode('pgc')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${viewMode === 'pgc' ? 'bg-slate-900 text-white shadow-lg' : 'text-slate-500 hover:text-slate-800'}`}>PGC</button>
                    </nav>
                  )}
                </div>

                {viewMode === 'sistemas-dev' && !selectedSystemId && (
                  <div className="flex items-center gap-3">
                    <button
                      onClick={handleCopyBacklog}
                      className="bg-violet-600 text-white px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-violet-700 transition-all flex items-center gap-3"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                      Copiar <span className="hidden lg:inline">Tudo</span>
                    </button>
                    <button
                      onClick={() => {
                        setSettingsTab('sistemas');
                        setIsSettingsModalOpen(true);
                      }}
                      className="bg-slate-900 text-white px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                      Novo <span className="hidden lg:inline">Sistema</span>
                    </button>
                  </div>
                )}


                {/* Finance Controls */}
                {viewMode === 'finance' && (
                  <div className="flex items-center gap-4">
                     <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200">
                        <button
                          onClick={() => setFinanceActiveTab('dashboard')}
                          className={`px-4 py-1.5 text-[10px] uppercase font-black rounded-lg transition-all ${financeActiveTab === 'dashboard' ? 'bg-white shadow-sm text-slate-900 border border-slate-100' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Visão Geral
                        </button>
                        <button
                          onClick={() => setFinanceActiveTab('fixed')}
                          className={`px-4 py-1.5 text-[10px] uppercase font-black rounded-lg transition-all ${financeActiveTab === 'fixed' ? 'bg-white shadow-sm text-slate-900 border border-slate-100' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Rendas e Obrigações
                        </button>
                     </div>

                     <div className="flex items-center bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                        <button
                          onClick={() => {
                            const newMonth = currentMonth === 0 ? 11 : currentMonth - 1;
                            const newYear = currentMonth === 0 ? currentYear - 1 : currentYear;
                            setCurrentMonth(newMonth);
                            setCurrentYear(newYear);
                          }}
                          className="p-2 hover:bg-slate-50 text-slate-400 hover:text-slate-900 transition-all border-r border-slate-100"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" /></svg>
                        </button>
                        <div className="px-3 text-center min-w-[100px]">
                            <div className="text-[10px] font-black text-slate-900 capitalize leading-none tracking-tight">
                                {new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}
                            </div>
                        </div>
                        <button
                          onClick={() => {
                            const newMonth = currentMonth === 11 ? 0 : currentMonth + 1;
                            const newYear = currentMonth === 11 ? currentYear + 1 : currentYear;
                            setCurrentMonth(newMonth);
                            setCurrentYear(newYear);
                          }}
                          className="p-2 hover:bg-slate-50 text-slate-400 hover:text-slate-900 transition-all border-l border-slate-100"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                        </button>
                     </div>

                     <button
                        onClick={() => setIsFinanceSettingsOpen(!isFinanceSettingsOpen)}
                        className={`p-2 rounded-xl transition-all border ${isFinanceSettingsOpen ? 'bg-slate-900 text-white border-slate-900 shadow-lg' : 'bg-white text-slate-400 border-slate-200 hover:bg-slate-50 hover:text-slate-900 shadow-sm'}`}
                        title="Configurações Financeiras"
                     >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                     </button>
                  </div>
                )}

                {/* Standard Action Buttons (Search, Sync, Create) */}
                {viewMode !== 'ferramentas' && viewMode !== 'sistemas-dev' && viewMode !== 'knowledge' && viewMode !== 'saude' && viewMode !== 'finance' && viewMode !== 'dashboard' && viewMode !== 'projects' && (
                  <div className="flex items-center gap-4">
                    {activeModule !== 'dashboard' && (
                      <div className="hidden lg:flex items-center bg-slate-50 border border-slate-200 rounded-lg md:rounded-xl px-4 py-2 w-64 group focus-within:ring-2 focus-within:ring-blue-500 focus-within:bg-white transition-all">
                        <svg className="w-4 h-4 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        <input type="text" placeholder="Pesquisar..." className="bg-transparent border-none outline-none text-xs font-bold text-slate-900 w-full" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
                      </div>
                    )}
                    <button
                      onClick={() => setIsCreateModalOpen(true)}
                      className="bg-slate-900 text-white px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 shadow-lg hover:bg-slate-800 transition-all active:scale-95"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                      Criar Ação
                    </button>
                  </div>
                )}
                {/* Global Header Actions (Notes, Backlog, Notifs, Sync) - Persistent at Right */}
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <button
                      onClick={() => setIsQuickNoteModalOpen(true)}
                      className="bg-white border border-slate-200 text-amber-500 p-2 rounded-lg md:rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative"
                      aria-label="Notas Rápidas"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsQuickLogModalOpen(true)}
                      className="bg-white border border-slate-200 text-violet-600 p-2 rounded-lg md:rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative"
                      aria-label="Log Rápido de Sistema"
                      title="Registrar Ajuste em Sistema"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsShoppingAIModalOpen(true)}
                      className="bg-white border border-slate-200 text-emerald-600 p-2 rounded-lg md:rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative"
                      aria-label="Inteligência de Compras"
                      title="Assistente de Compras IA"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
                      <span className="absolute -top-1 -right-1 flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                      </span>
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsNotificationCenterOpen(!isNotificationCenterOpen)}
                      className="bg-white border border-slate-200 text-slate-700 p-2 rounded-lg md:rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative notification-trigger"
                      aria-label="Notificações"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                      {notifications.some(n => !n.isRead) && (
                        <span className="absolute top-2 right-2 w-2.5 h-2.5 bg-rose-500 border-2 border-white rounded-full"></span>
                      )}
                    </button>
                    <NotificationCenter
                      notifications={notifications}
                      onMarkAsRead={handleMarkNotificationRead}
                      onDismiss={handleDismissNotification}
                      isOpen={isNotificationCenterOpen}
                      onClose={() => setIsNotificationCenterOpen(false)}
                      onUpdateOverdue={handleUpdateOverdueTasks}
                      onNavigate={handleNotificationNavigate}
                    />
                  </div>
                  <div className="relative">
                    <button
                      onClick={handleSync}
                      className="bg-white border border-slate-200 text-slate-700 p-2 rounded-lg md:rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative"
                      aria-label="Sincronizar"
                      title={isSyncing ? 'Monitorar Sync' : 'Sync Google'}
                    >
                      <svg className={`w-5 h-5 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                      {isSyncing && (
                        <span className="absolute top-2 right-2 w-2.5 h-2.5 bg-blue-500 border-2 border-white rounded-full animate-ping"></span>
                      )}
                    </button>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setIsSettingsModalOpen(true)}
                      className="bg-white border border-slate-200 text-slate-700 p-2 rounded-lg md:rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95 relative"
                      aria-label="Configurações Gerais"
                      title="Configurações"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Mobile Menu Drawer */}
            {isMobileMenuOpen && (
              <div className="md:hidden border-t border-slate-200 bg-white shadow-2xl animate-in slide-in-from-top-4 duration-300">
                <nav className="flex flex-col p-4 gap-2">
                  {[
                    { label: '🏠 Dashboard', active: viewMode === 'dashboard', onClick: () => { setActiveModule('dashboard'); setViewMode('dashboard'); } },
                    { label: '📊 Ações', active: activeModule === 'acoes' && (viewMode === 'gallery' || viewMode === 'licitacoes' || viewMode === 'assistencia'), onClick: () => { setActiveModule('acoes'); setViewMode('gallery'); } },
                    { label: '🚀 Projetos', active: activeModule === 'projetos' && viewMode === 'projects', onClick: () => { setActiveModule('projetos'); setViewMode('projects'); } },
                    { label: '📋 PGC', active: activeModule === 'acoes' && viewMode === 'pgc', onClick: () => { setActiveModule('acoes'); setViewMode('pgc'); } },
                    { label: '💰 Financeiro', active: activeModule === 'financeiro', onClick: () => { setActiveModule('financeiro'); setViewMode('finance'); } },
                    { label: '❤️ Saúde', active: activeModule === 'saude', onClick: () => { setActiveModule('saude'); setViewMode('saude'); } },
                    { label: '💻 Sistemas', active: viewMode === 'sistemas-dev', onClick: () => { setActiveModule('acoes'); setViewMode('sistemas-dev'); } },
                    { label: '📚 Conhecimento', active: viewMode === 'knowledge', onClick: () => { setActiveModule('acoes'); setViewMode('knowledge'); } },
                    { label: '🛠️ Ferramentas', active: viewMode === 'ferramentas', onClick: () => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta(null); } },
                  ].map((item, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        item.onClick();
                        setIsMobileMenuOpen(false);
                      }}
                      className={`px-6 py-4 rounded-2xl text-sm font-black uppercase tracking-widest transition-all ${item.active ? 'bg-slate-900 text-white shadow-lg' : 'bg-slate-50 text-slate-600'}`}
                    >
                      {item.label}
                    </button>
                  ))}

                  <div className="grid grid-cols-2 gap-2 mt-4 pt-4 border-t border-slate-100">
                    <button
                      onClick={() => {
                        handleSync();
                        setIsMobileMenuOpen(false);
                      }}
                      className="px-4 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest bg-blue-50 text-blue-700 flex items-center justify-center gap-2"
                    >
                      <svg className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                      {isSyncing ? 'Sync...' : 'Sync'}
                    </button>
                    <button
                      onClick={() => {
                        setIsSettingsModalOpen(true);
                        setIsMobileMenuOpen(false);
                      }}
                      className="px-4 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest bg-slate-100 text-slate-600 flex items-center justify-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                      Config
                    </button>
                    <button
                      onClick={handleLogout}
                      className="col-span-2 px-4 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest bg-rose-50 text-rose-600 flex items-center justify-center gap-2 mt-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
                      Sair da Conta
                    </button>
                  </div>
                </nav>
              </div>
            )}
          </header>

          <div className="max-w-[1400px] mx-auto w-full px-0 md:px-8 py-6">
            {/* Painel de Estatísticas e Filtros - APENAS NA VISÃO GERAL */}
            <main className="mb-20">
              {viewMode === 'dashboard' ? (
                <DashboardView
                  tarefas={tarefas}
                  financeTransactions={financeTransactions}
                  financeSettings={financeSettings}
                  fixedBills={fixedBills}
                  incomeEntries={incomeEntries}
                  healthWeights={healthWeights}
                  healthDailyHabits={healthDailyHabits}
                  healthSettings={healthSettings}
                  unidades={unidades}
                  sistemasDetalhes={sistemasDetalhes}
                  workItems={workItems}
                  currentMonth={currentMonth}
                  currentYear={currentYear}
                  onNavigate={handleDashboardNavigate}
                  onOpenBacklog={handleCopyBacklog}
                />
              ) : viewMode === 'gallery' ? (
                <>
                  {/* Mobile Search Bar */}
                  <div className="lg:hidden px-4 mb-6">
                    <div className="flex items-center bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm focus-within:ring-2 focus-within:ring-blue-500 transition-all">
                      <svg className="w-5 h-5 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                      <input
                        type="text"
                        placeholder="Pesquisar ações..."
                        className="bg-transparent border-none outline-none text-sm font-bold text-slate-900 w-full placeholder:text-slate-400"
                        value={searchTerm === 'filter:unclassified' ? '' : searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                      />
                      {searchTerm && searchTerm !== 'filter:unclassified' && (
                        <button onClick={() => setSearchTerm('')} className="ml-2 text-slate-400 hover:text-slate-600">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-col md:flex-row items-center justify-between mb-8 gap-4 px-4 md:px-0">
                    {/* Linha de Filtros e Ações Globais */}
                    <div className="flex items-center justify-between w-full gap-2">
                      {/* Lado Esquerdo: Filtro de Área */}
                      <div className="relative group flex-shrink-1 min-w-0 max-w-[140px] md:max-w-none md:min-w-[180px]">
                        <select
                          value={areaFilter}
                          onChange={(e) => setAreaFilter(e.target.value)}
                          className="h-11 w-full appearance-none bg-white pl-3 md:pl-4 pr-8 md:pr-10 rounded-xl border border-slate-200 text-[10px] font-black uppercase tracking-tight md:tracking-widest text-slate-700 outline-none focus:ring-2 focus:ring-slate-900 shadow-sm hover:border-slate-300 transition-all cursor-pointer truncate"
                        >
                          <option value="TODAS">TODAS</option>
                          <option value="CLC">CLC</option>
                          <option value="ASSISTÊNCIA">ASSISTÊNCIA</option>
                          <option value="GERAL">GERAL</option>
                          <option value="NÃO CLASSIFICADA">PENDENTES</option>
                          {unidades.filter(u => !['CLC', 'ASSISTÊNCIA', 'ASSISTÊNCIA ESTUDANTIL'].includes(u.nome.toUpperCase())).map(u => (
                            <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                          ))}
                        </select>
                        <div className="absolute inset-y-0 right-0 flex items-center px-2 md:px-3 pointer-events-none text-slate-400">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
                        </div>
                      </div>

                      {/* Lado Direito: Modos de Visualização e Organizar Dia */}
                      <div className="flex items-center gap-1 md:gap-2 flex-shrink-0">
                        {searchTerm !== 'filter:unclassified' && (
                          <div className="h-11 bg-slate-100 p-1 rounded-xl shadow-inner inline-flex border border-slate-200">
                            <button
                              onClick={() => setDashboardViewMode('list')}
                              className={`px-2 md:px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${dashboardViewMode === 'list' ? 'bg-white shadow-md text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
                              <span className="hidden lg:inline">Lista</span>
                            </button>
                            <button
                              onClick={() => setDashboardViewMode('calendar')}
                              className={`px-2 md:px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${dashboardViewMode === 'calendar' ? 'bg-white shadow-md text-slate-900' : 'text-slate-400 hover:text-slate-600'}`}
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2-2v12a2 2 0 002 2z" /></svg>
                              <span className="hidden lg:inline">Calendário</span>
                            </button>
                          </div>
                        )}

                        <button
                          onClick={() => {
                            setDashboardViewMode('calendar');
                            setCalendarViewMode('day');
                            setCalendarDate(new Date());
                          }}
                          className="h-11 bg-slate-900 text-white px-3 md:px-6 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center justify-center gap-2 active:scale-95"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                          <span className="hidden sm:inline">Organizar</span>
                        </button>
                      </div>
                    </div>
                  </div>

                  {dashboardViewMode === 'calendar' ? (
                    <CalendarView
                      tasks={filteredAndSortedTarefas}
                      googleEvents={googleCalendarEvents}
                      viewMode={calendarViewMode}
                      currentDate={calendarDate}
                      onDateChange={setCalendarDate}
                      onTaskClick={setSelectedTask}
                      onViewModeChange={setCalendarViewMode}
                      onTaskUpdate={handleUpdateTarefa}
                      onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
                      onReorderTasks={handleReorderTasks}
                      showToast={showToast}
                    />
                  ) : (
                    <>
                      {searchTerm === 'filter:unclassified' ? (
                        <div className="animate-in bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl">
                          <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex flex-col md:flex-row md:items-center justify-between gap-4">
                            <h3 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                              <span className="w-2 h-8 bg-rose-600 rounded-full"></span>
                              Organização Rápida
                            </h3>

                            {selectedTaskIds.length > 0 && (
                              <div className="flex items-center gap-2 bg-slate-900 p-2 rounded-none md:rounded-2xl animate-in slide-in-from-top-4">
                                <span className="text-[9px] font-black text-white uppercase tracking-widest px-4">Classificar ({selectedTaskIds.length}):</span>
                                <button onClick={() => handleBatchTag('CLC')} className="bg-blue-600 hover:bg-blue-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">CLC</button>
                                <button onClick={() => handleBatchTag('ASSISTÊNCIA')} className="bg-emerald-600 hover:bg-emerald-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">Assistência</button>
                                <button onClick={() => handleBatchTag('GERAL')} className="bg-slate-500 hover:bg-slate-600 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-lg md:rounded-xl transition-all">Geral</button>
                              </div>
                            )}
                          </div>

                          <div className="overflow-x-auto">
                            {/* Desktop Table */}
                            <table className="w-full text-left hidden md:table">
                              <thead className="bg-slate-50 border-b border-slate-200">
                                <tr>
                                  <th className="px-8 py-4 w-12 text-center text-[10px] font-black text-slate-400 uppercase tracking-widest italic">#</th>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Descrição da Tarefa</th>
                                  <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-40 text-center">Data Limite</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-50">
                                {filteredAndSortedTarefas.map((task) => (
                                  <tr
                                    key={task.id}
                                    onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); }}
                                    className={`hover:bg-slate-50 transition-colors cursor-pointer ${selectedTaskIds.includes(task.id) ? 'bg-blue-50/30' : ''}`}
                                  >
                                    <td className="px-8 py-4 text-center">
                                      <input
                                        type="checkbox"
                                        checked={selectedTaskIds.includes(task.id)}
                                        onChange={(e) => {
                                          e.stopPropagation();
                                          setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id]);
                                        }}
                                        className="w-5 h-5 rounded-lg border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
                                      />
                                    </td>
                                    <td className="px-8 py-4">
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <div className="text-[13px] font-bold text-slate-800 hover:text-blue-600 transition-colors leading-snug">
                                          {task.titulo}
                                        </div>
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
                                ))}
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
                                            handleReorderTasks(draggedId, task.id, label);
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
                            {tarefas.filter(t => normalizeStatus(t.status) === 'concluido' && t.status !== 'excluído' as any).length > 0 ? (
                              tarefas
                                .filter(t => normalizeStatus(t.status) === 'concluido' && t.status !== 'excluído' as any)
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
                  onAddExam={async (exam, files) => {
                     let poolItems: PoolItem[] = [];
                     
                     if (files.length > 0 && appSettings.googleDriveFolderId) {
                        try {
                           showToast("Enviando arquivos para o Drive...", "info");
                           for (const file of files) {
                              const item = await handleFileUploadToDrive(file);
                              if (item) poolItems.push(item);
                           }
                        } catch (e) {
                           console.error(e);
                           showToast("Erro no upload de um ou mais arquivos.", "error");
                        }
                     }

                      const examDoc = await addDoc(collection(db, 'exames'), {
                         ...exam,
                         pool_dados: poolItems,
                         data_criacao: new Date().toISOString()
                      });

                      // Mirror to Knowledge base
                      if (poolItems.length > 0) {
                         for (const item of poolItems) {
                            const knowledgeItem: ConhecimentoItem = {
                               id: item.id,
                               titulo: item.nome || 'Sem título',
                               tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
                               url_drive: item.valor,
                               tamanho: 0,
                               data_criacao: item.data_criacao,
                               origem: { modulo: 'saude', id_origem: examDoc.id },
                               categoria: 'Saúde'
                            };
                            await setDoc(doc(db, 'conhecimento', item.id), knowledgeItem);
                         }
                      }

                      showToast("Registro de saúde adicionado e indexado ao Drive.", "success");
                   }}
                  onDeleteExam={async (id) => {
                    showConfirm("Confirmar Exclusão", "Deseja realmente remover este registro de saúde?", async () => {
                      await deleteDoc(doc(db, 'exames', id));
                      showToast("Registro removido.", "info");
                    });
                  }}
                  onUpdateExam={async (id, updates) => {
                     await updateDoc(doc(db, 'exames', id), updates);
                     showToast("Registro atualizado.", "success");
                  }}
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
                    let remaining = Math.max(0, totalSavings + emergencyCurrent - (financeSettings.emergencyReserveTarget || 0));
                    // Note: The logic here is a bit tricky. If "Poupança" bills are the ONLY thing that fills goals,
                    // and emergency reserve is a manual pot, then typically goals = totalSavings if emergency is full.
                    // But if emergency is manual, maybe the user wants: Remaining = total_saved_in_savings_bills.
                    // Let's assume goals are filled by "Poupança" items, but only if the manual emergency reserve is >= target.

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
                  onAddRubric={async (rubric) => { await addDoc(collection(db, 'bill_rubrics'), rubric); }}
                  onUpdateRubric={async (rubric) => { await updateDoc(doc(db, 'bill_rubrics', rubric.id), rubric as any); }}
                  onDeleteRubric={async (id) => { await deleteDoc(doc(db, 'bill_rubrics', id)); }}
                  onAddIncomeRubric={async (rubric) => { await addDoc(collection(db, 'income_rubrics'), rubric); }}
                  onUpdateIncomeRubric={async (rubric) => { await updateDoc(doc(db, 'income_rubrics', rubric.id), rubric as any); }}
                  onDeleteIncomeRubric={async (id) => { await deleteDoc(doc(db, 'income_rubrics', id)); }}
                  onAddIncomeEntry={async (entry) => { await addDoc(collection(db, 'income_entries'), { ...entry, month: currentMonth, year: currentYear, status: 'active' }); }}
                  onUpdateIncomeEntry={async (entry) => { await updateDoc(doc(db, 'income_entries', entry.id), entry as any); }}
                  onDeleteIncomeEntry={async (id) => { await updateDoc(doc(db, 'income_entries', id), { status: 'deleted' }); }}
                  onUpdateSettings={(newSettings) => setDoc(doc(db, 'finance_settings', 'config'), newSettings)}
                  onAddGoal={(goal) => addDoc(collection(db, 'finance_goals'), { ...goal, priority: financeGoals.length + 1 })}
                  onUpdateGoal={handleUpdateFinanceGoal}
                  onDeleteGoal={handleDeleteFinanceGoal}
                  onReorderGoals={handleReorderFinanceGoals}
                  onAddBill={async (bill) => { await addDoc(collection(db, 'fixed_bills'), { ...bill, month: currentMonth, year: currentYear }); }}
                  onUpdateBill={async (bill) => { await updateDoc(doc(db, 'fixed_bills', bill.id), bill as any); }}
                  onDeleteBill={async (id) => { await deleteDoc(doc(db, 'fixed_bills', id)); }}
                  onAddTransaction={async (t) => { await addDoc(collection(db, 'finance_transactions'), { ...t, status: 'active' }); }}
                  onUpdateTransaction={async (t) => { await updateDoc(doc(db, 'finance_transactions', t.id), t as any); }}
                  onDeleteTransaction={async (id) => { await updateDoc(doc(db, 'finance_transactions', id), { status: 'deleted' }); }}
                  activeTab={financeActiveTab}
                  setActiveTab={setFinanceActiveTab}
                  isSettingsOpen={isFinanceSettingsOpen}
                  setIsSettingsOpen={setIsFinanceSettingsOpen}
                />

              ) : viewMode === 'knowledge' ? (
                <KnowledgeView
                  items={knowledgeItems}
                  onDeleteItem={async (id) => { await deleteDoc(doc(db, 'conhecimento', id)); }}
                  onUploadFile={handleUploadKnowledgeFile}
                  onAddLink={handleAddKnowledgeLink}
                  onSaveItem={handleSaveKnowledgeItem}
                  onProcessWithAI={handleProcessWithAI}
                  onGenerateSlides={handleGenerateSlides}
                  showConfirm={showConfirm}
                  allTasks={tarefas}
                  allWorkItems={workItems}
                />
              ) : viewMode === 'sistemas-dev' ? (
                <div className="space-y-8 animate-in fade-in duration-500 pb-20">
                  {!selectedSystemId ? (
                    /* VISÃO GERAL - LISTA DE SISTEMAS */
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-8 p-3 md:p-0 pt-8">
                        {unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(unit => {
                          const sysDetails = sistemasDetalhes.find(s => s.id === unit.id) || {
                            id: unit.id,
                            nome: unit.nome.replace('SISTEMA:', '').trim(),
                            status: 'ideia' as SistemaStatus,
                            data_criacao: new Date().toISOString(),
                            data_atualizacao: new Date().toISOString()
                          };
                          const systemName = unit.nome.replace('SISTEMA:', '').trim();
                          const ajustesPendentes = workItems.filter(w => w.sistema_id === unit.id && !w.concluido).length;

                          return (
                            <button
                              key={unit.id}
                              onClick={() => setSelectedSystemId(unit.id)}
                              className="bg-white border border-slate-200 rounded-2xl md:rounded-[2.5rem] p-6 md:p-8 text-left shadow-sm md:shadow-xl hover:shadow-md md:hover:shadow-2xl hover:border-violet-300 transition-all group relative overflow-hidden"
                            >
                              <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-500"></div>
                              <div className="relative z-10 space-y-6">
                                <div className="flex justify-between items-start">
                                  <div className="w-14 h-14 bg-violet-100 text-violet-600 rounded-none md:rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform">
                                    <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                                  </div>
                                  <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest ${sysDetails.status === 'producao' ? 'bg-emerald-100 text-emerald-700' :
                                    sysDetails.status === 'desenvolvimento' ? 'bg-blue-100 text-blue-700' :
                                      sysDetails.status === 'testes' ? 'bg-amber-100 text-amber-700' :
                                        'bg-slate-100 text-slate-500'
                                    }`}>
                                    {sysDetails.status === 'prototipacao' ? 'Prototipação' :
                                      sysDetails.status === 'producao' ? 'Produção' :
                                        sysDetails.status}
                                  </span>
                                </div>
                                <div>
                                  <h3 className="text-xl font-black text-slate-900 mb-1 group-hover:text-violet-700 transition-colors">{systemName}</h3>
                                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                                    Atualizado em {formatDate(sysDetails.data_atualizacao?.split('T')[0] || formatDateLocalISO(new Date()))}
                                  </p>
                                </div>
                                <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                                  <span className="text-xs font-bold text-slate-500">{ajustesPendentes} ajustes pendentes</span>
                                  <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center group-hover:bg-violet-500 group-hover:text-white transition-colors">
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
                                  </div>
                                </div>
                              </div>
                            </button>
                          );
                        })}

                        {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length === 0 && (
                          <div className="col-span-full text-center py-20 bg-slate-50 rounded-none md:rounded-[2.5rem] border-2 border-dashed border-slate-200">
                            <p className="text-slate-400 font-bold text-lg mb-2">Nenhum sistema cadastrado</p>
                            <button onClick={() => { setIsSettingsModalOpen(true); }} className="bg-slate-900 text-white px-6 py-3 rounded-lg md:rounded-xl font-bold uppercase tracking-widest text-xs hover:bg-slate-800 transition-all mt-4">
                              Ir para Configurações
                            </button>
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    /* VISÃO DETALHADA - SISTEMA SELECIONADO */
                    (() => {
                      const unit = unidades.find(u => u.id === selectedSystemId);
                      if (!unit) return null;

                      const sysDetails = sistemasDetalhes.find(s => s.id === unit.id) || {
                        id: unit.id,
                        nome: unit.nome.replace('SISTEMA:', '').trim(),
                        status: 'ideia' as SistemaStatus,
                        data_criacao: new Date().toISOString(),
                        data_atualizacao: new Date().toISOString()
                      };

                      const systemName = unit.nome.replace('SISTEMA:', '').trim();
                      const systemWorkItems = workItems.filter(w => w.sistema_id === unit.id);
                      const ajustesPendentesCount = systemWorkItems.filter(w => !w.concluido).length;

                      const steps: SistemaStatus[] = ['ideia', 'prototipacao', 'desenvolvimento', 'testes', 'producao'];
                      const currentStepIndex = steps.indexOf(sysDetails.status);

                      return (
                        <div className="animate-in fade-in slide-in-from-bottom-8 duration-500">
                          {/* Navigation */}
                          <button
                            onClick={() => setSelectedSystemId(null)}
                            className="mb-8 px-6 md:px-0 flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold text-xs uppercase tracking-widest transition-colors"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
                            Voltar para Lista
                          </button>

                          <div className="bg-white border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden shadow-xl">
                            {/* Header Detalhado */}
                            <div className="hidden md:block bg-slate-900 p-8 md:p-12 text-white relative overflow-hidden">
                              <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/20 rounded-full -mr-20 -mt-20 blur-3xl"></div>
                              <div className="relative z-10 flex flex-col md:flex-row md:items-end justify-between gap-8">
                                <div className="space-y-4">
                                  <div className="inline-flex items-center gap-2 bg-white/10 px-3 py-1 rounded-lg backdrop-blur-sm border border-white/10">
                                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                                    <span className="text-[10px] font-black uppercase tracking-widest">
                                      {sysDetails.status === 'prototipacao' ? 'Prototipação' :
                                        sysDetails.status === 'producao' ? 'Produção' :
                                          sysDetails.status}
                                    </span>
                                  </div>
                                  <h2 className="text-4xl md:text-5xl font-black tracking-tight">{systemName}</h2>
                                </div>
                                <div className="text-right">
                                  <div className="text-3xl font-black text-violet-400">{ajustesPendentesCount}</div>
                                  <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Ajustes Pendentes</div>
                                </div>
                              </div>
                            </div>

                            {/* Status Stepper */}
                            <div className="bg-slate-50 border-b border-slate-100 p-4 md:p-10 flex flex-col items-center gap-4 md:gap-8">
                              <div className="text-center">
                                <h2 className="text-lg md:text-3xl font-black text-slate-900 tracking-tight uppercase">{systemName}</h2>
                                <div className="w-8 h-1 bg-violet-500 mx-auto mt-2 rounded-full"></div>
                              </div>

                              <div className="flex flex-wrap items-center justify-center bg-slate-200/50 p-1 rounded-xl md:rounded-2xl gap-1 w-full md:w-auto">
                                {steps.map((step, idx) => {
                                  const isActive = sysDetails.status === step;
                                  const stepLabels: Record<string, string> = {
                                    ideia: 'Ideia',
                                    prototipacao: 'Protótipo',
                                    desenvolvimento: 'Dev',
                                    testes: 'Testes',
                                    producao: 'Produção'
                                  };
                                  return (
                                    <React.Fragment key={step}>
                                      <button
                                        onClick={() => handleUpdateSistema(unit.id, { status: step })}
                                        className={`flex-1 md:flex-none px-2 md:px-4 py-2 rounded-lg md:rounded-xl text-[8px] md:text-[9px] font-black uppercase tracking-widest transition-all ${isActive
                                          ? 'bg-violet-600 text-white shadow-lg'
                                          : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'
                                          }`}
                                      >
                                        {stepLabels[step]}
                                      </button>
                                      {idx < steps.length - 1 && (
                                        <div className="hidden md:flex items-center text-slate-300 px-1">
                                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                                        </div>
                                      )}
                                    </React.Fragment>
                                  );
                                })}
                              </div>
                            </div>

                            <div className="p-0 md:p-8 grid grid-cols-1 lg:grid-cols-3 gap-0 md:gap-12">
                              {/* Coluna 2: Links e Recursos (Topo no mobile) */}
                              <div className="lg:col-span-1 order-1 md:order-1 space-y-0 md:space-y-8">
                                <div className="p-4 md:p-0">
                                  <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 flex items-center gap-2">
                                    <span className="w-1 h-3 bg-violet-500 rounded-full"></span>
                                    Recursos
                                  </h4>
                                </div>

                                <div className="grid grid-cols-4 md:grid-cols-1 gap-2 md:gap-6 px-4 md:px-0 mb-8 md:mb-0">
                                  {/* Repositório */}
                                  <button
                                    onClick={() => setEditingResource({ field: 'repositorio_principal', label: 'Repositório', value: sysDetails.repositorio_principal || '' })}
                                    className="group bg-slate-900 p-4 md:p-6 rounded-2xl md:rounded-3xl border border-slate-800 hover:border-slate-600 hover:shadow-xl transition-all text-center md:text-left flex flex-col items-center md:items-stretch justify-center md:justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden"
                                  >
                                    <div className="absolute top-0 right-0 w-24 h-24 bg-violet-500/10 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                    <div className="relative z-10 space-y-2 md:space-y-3">
                                      <div className="w-8 h-8 md:w-10 md:h-10 bg-white/10 text-white rounded-lg flex items-center justify-center mx-auto md:mx-0">
                                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" /></svg>
                                      </div>
                                      <h5 className="text-[8px] md:text-xs font-black text-white uppercase tracking-widest leading-none">Repo</h5>
                                    </div>
                                    <div className="hidden md:block relative z-10">
                                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{sysDetails.repositorio_principal ? 'Editar' : 'Configurar'}</span>
                                    </div>
                                  </button>

                                  {/* Documentação */}
                                  <button
                                    onClick={() => setEditingResource({ field: 'link_documentacao', label: 'Documentação', value: sysDetails.link_documentacao || '' })}
                                    className="group bg-white p-4 md:p-6 rounded-2xl md:rounded-3xl border border-slate-200 hover:border-violet-300 hover:shadow-xl transition-all text-center md:text-left flex flex-col items-center md:items-stretch justify-center md:justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden"
                                  >
                                    <div className="absolute top-0 right-0 w-24 h-24 bg-violet-500/5 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                    <div className="relative z-10 space-y-2 md:space-y-3">
                                      <div className="w-8 h-8 md:w-10 md:h-10 bg-violet-100 text-violet-600 rounded-lg flex items-center justify-center mx-auto md:mx-0">
                                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                      </div>
                                      <h5 className="text-[8px] md:text-xs font-black text-slate-900 uppercase tracking-widest leading-none">Docs</h5>
                                    </div>
                                    <div className="hidden md:block relative z-10">
                                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{sysDetails.link_documentacao ? 'Editar' : 'Configurar'}</span>
                                    </div>
                                  </button>

                                  {/* AI Studio */}
                                  <button
                                    onClick={() => setEditingResource({ field: 'link_google_ai_studio', label: 'AI Studio', value: sysDetails.link_google_ai_studio || '' })}
                                    className="group bg-white p-4 md:p-6 rounded-2xl md:rounded-3xl border border-slate-200 hover:border-blue-300 hover:shadow-xl transition-all text-center md:text-left flex flex-col items-center md:items-stretch justify-center md:justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden"
                                  >
                                    <div className="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                    <div className="relative z-10 space-y-2 md:space-y-3">
                                      <div className="w-8 h-8 md:w-10 md:h-10 bg-blue-100 text-blue-600 rounded-lg flex items-center justify-center mx-auto md:mx-0">
                                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                      </div>
                                      <h5 className="text-[8px] md:text-xs font-black text-slate-900 uppercase tracking-widest leading-none">AI</h5>
                                    </div>
                                    <div className="hidden md:block relative z-10">
                                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{sysDetails.link_google_ai_studio ? 'Editar' : 'Configurar'}</span>
                                    </div>
                                  </button>

                                  {/* Link Hospedado */}
                                  <button
                                    onClick={() => setEditingResource({ field: 'link_hospedado', label: 'Hospedagem', value: sysDetails.link_hospedado || '' })}
                                    className="group bg-emerald-50 p-4 md:p-6 rounded-2xl md:rounded-3xl border border-emerald-100 hover:border-emerald-300 hover:shadow-xl transition-all text-center md:text-left flex flex-col items-center md:items-stretch justify-center md:justify-between aspect-square md:aspect-auto md:min-h-[120px] relative overflow-hidden"
                                  >
                                    <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-500"></div>
                                    <div className="relative z-10 space-y-2 md:space-y-3">
                                      <div className="w-8 h-8 md:w-10 md:h-10 bg-emerald-100 text-emerald-600 rounded-lg flex items-center justify-center mx-auto md:mx-0">
                                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>
                                      </div>
                                      <h5 className="text-[8px] md:text-xs font-black text-emerald-900 uppercase tracking-widest leading-none">App</h5>
                                    </div>
                                    <div className="hidden md:block relative z-10">
                                      <span className="text-[10px] font-bold text-emerald-600/60 uppercase tracking-widest">{sysDetails.link_hospedado ? 'Editar' : 'Configurar'}</span>
                                    </div>
                                  </button>
                                </div>
                              </div>

                              {/* Coluna 1: Logs de Trabalho (Abaixo no mobile) */}
                              <div className="lg:col-span-2 order-2 md:order-2 space-y-0 md:space-y-6">
                                <div className="bg-white border-0 md:border border-slate-200 rounded-none md:rounded-[2.5rem] overflow-hidden flex flex-col min-h-[400px] md:min-h-[600px] shadow-none md:shadow-sm">
                                  {/* Novo Log Input */}
                                  <div className="p-6 md:p-8 border-b border-slate-100 bg-slate-50">
                                    <div className="flex flex-col gap-6">
                                      <div className="flex items-center justify-between gap-4">
                                        <div className="flex items-center gap-2">
                                          <div className="p-1.5 bg-violet-600 text-white rounded-lg">
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                          </div>
                                          <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Dev Log</h4>
                                        </div>
                                      </div>

                                      <div className="flex flex-col gap-4">
                                        <div className="relative">
                                          <WysiwygEditor
                                            value={newLogText}
                                            onChange={setNewLogText}
                                            placeholder="O que foi feito no sistema?"
                                            className="bg-white min-h-[120px] pb-10"
                                          />
                                          <div className="absolute right-4 top-4 flex flex-col gap-2">
                                            <button
                                              onClick={isRecordingLog ? stopLogRecording : startLogRecording}
                                              disabled={isProcessingLog}
                                              className={`p-3 rounded-xl transition-all ${
                                                isRecordingLog
                                                  ? 'bg-emerald-600 text-white animate-pulse shadow-lg'
                                                  : isProcessingLog
                                                    ? 'bg-violet-100 text-violet-600 cursor-wait'
                                                    : 'bg-slate-100 text-slate-400 hover:text-violet-600'
                                              }`}
                                              title="Transcrever áudio"
                                            >
                                              {isProcessingLog ? (
                                                <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                              ) : isRecordingLog ? (
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                                              ) : (
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                                              )}
                                            </button>
                                          </div>

                                          <label className={`absolute left-3 bottom-2 p-2 rounded-xl transition-all ${isUploading ? 'bg-violet-100 animate-pulse pointer-events-none' : 'text-slate-400 hover:text-violet-600 hover:bg-violet-50'} cursor-pointer`}>
                                            <input
                                              type="file"
                                              accept="image/*"
                                              className="hidden"
                                              onChange={async (e) => {
                                                const file = e.target.files?.[0];
                                                if (file) {
                                                  const item = await handleFileUploadToDrive(file);
                                                  if (item) setNewLogAttachments(prev => [...prev, item]);
                                                }
                                              }}
                                            />
                                            {isUploading ? (
                                              <div className="w-4 h-4 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                            ) : (
                                              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                                            )}
                                          </label>
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                          {newLogAttachments.map((at, i) => (
                                            <div key={i} className="relative group/at">
                                              <img src={at.valor} alt="preview" className="w-16 h-16 object-cover rounded-lg border border-slate-200" />
                                              <button
                                                onClick={() => setNewLogAttachments(prev => prev.filter((_, idx) => idx !== i))}
                                                className="absolute -top-1 -right-1 bg-rose-500 text-white rounded-full p-0.5 opacity-0 group-hover/at:opacity-100 transition-all z-10"
                                              >
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                              </button>
                                            </div>
                                          ))}
                                          <label className={`w-16 h-16 border-2 border-dashed border-slate-200 rounded-lg hidden md:flex items-center justify-center cursor-pointer hover:border-violet-400 hover:bg-violet-50 transition-all ${isUploading ? 'animate-pulse pointer-events-none' : ''}`}>
                                            <input
                                              type="file"
                                              accept="image/*"
                                              className="hidden"
                                              onChange={async (e) => {
                                                const file = e.target.files?.[0];
                                                if (file) {
                                                  const item = await handleFileUploadToDrive(file);
                                                  if (item) setNewLogAttachments(prev => [...prev, item]);
                                                }
                                              }}
                                            />
                                            {isUploading ? (
                                              <div className="w-4 h-4 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                            ) : (
                                              <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                            )}
                                          </label>
                                        </div>
                                        <button
                                          onClick={() => {
                                            handleCreateWorkItem(unit.id, newLogTipo, newLogText, newLogAttachments);
                                            setNewLogText('');
                                            setNewLogAttachments([]);
                                          }}
                                          disabled={!newLogText.trim()}
                                          className="w-full bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 disabled:grayscale"
                                        >
                                          Registrar
                                        </button>
                                      </div>
                                    </div>
                                  </div>

                                  {/* Listagem de Logs */}
                                  <div className="block flex-1 overflow-y-auto p-4 md:p-8 bg-white space-y-8 pb-32">
                                    {/* Ativos (Não concluídos) */}
                                    <div className="space-y-4">
                                      <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-violet-500 pl-3">Logs Ativos</h5>
                                      {systemWorkItems.filter(w => !w.concluido).sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime()).map(log => (
                                        <div key={log.id} className="group bg-slate-50 border border-slate-100 rounded-none md:rounded-3xl p-6 hover:border-violet-200 hover:bg-white transition-all">
                                          <div className="flex flex-col md:flex-row items-start justify-between gap-4 md:gap-6">
                                            <div className="flex-1 space-y-2 w-full">
                                              <div className="flex items-center gap-3">
                                                <span className={`text-[8px] font-black px-2 py-0.5 rounded uppercase tracking-wider ${log.tipo === 'desenvolvimento' ? 'bg-violet-100 text-violet-700' : log.tipo === 'ajuste' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>
                                                  {log.tipo}
                                                </span>
                                                <span className="text-[8px] font-black text-slate-300 uppercase">{new Date(log.data_criacao).toLocaleDateString('pt-BR')}</span>
                                              </div>
                                              <p className="text-sm font-medium text-slate-700 leading-relaxed break-words">{log.descricao}</p>
                                              {log.pool_dados && log.pool_dados.length > 0 && (
                                                <div className="flex flex-wrap gap-2 mt-3">
                                                  {log.pool_dados.map((at, i) => (
                                                    <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block">
                                                      <img src={at.valor} alt="preview" className="w-20 h-20 object-cover rounded-lg border border-slate-100 hover:scale-105 transition-transform shadow-sm" />
                                                    </a>
                                                  ))}
                                                </div>
                                              )}
                                            </div>
                                            <div className="flex gap-1 items-center opacity-0 group-hover:opacity-100 transition-opacity">
                                              <button
                                                onClick={() => {
                                                  setEditingWorkItem(log);
                                                  setEditingWorkItemText(log.descricao);
                                                  setEditingWorkItemAttachments(log.pool_dados || []);
                                                }}
                                                className="p-2 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-all"
                                                title="Editar"
                                              >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                              </button>
                                              <button
                                                onClick={() => {
                                                  if (confirmDeleteLogId === log.id) {
                                                    handleDeleteWorkItem(log.id);
                                                    setConfirmDeleteLogId(null);
                                                  } else {
                                                    setConfirmDeleteLogId(log.id);
                                                    setTimeout(() => setConfirmDeleteLogId(null), 3000);
                                                  }
                                                }}
                                                className={`p-2 rounded-lg transition-colors ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50'}`}
                                                title="Excluir"
                                              >
                                                {confirmDeleteLogId === log.id ? (
                                                  <svg className="w-4 h-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                ) : (
                                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                )}
                                              </button>
                                              <button
                                                onClick={() => handleUpdateWorkItem(log.id, { concluido: true, data_conclusao: new Date().toISOString() })}
                                                className="w-10 h-10 rounded-full border-2 border-slate-200 flex items-center justify-center text-slate-300 hover:border-emerald-500 hover:text-emerald-500 hover:bg-emerald-50 transition-all group/check ml-2"
                                              >
                                                <svg className="w-5 h-5 opacity-0 group-hover/check:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                              </button>
                                            </div>
                                          </div>
                                        </div>
                                      ))}
                                      {systemWorkItems.filter(w => !w.concluido).length === 0 && (
                                        <div className="text-center py-12 bg-slate-50/50 rounded-none md:rounded-3xl border-2 border-dashed border-slate-100">
                                          <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhum log ativo</p>
                                        </div>
                                      )}
                                    </div>
                                    {/* Concluídos */}
                                    {systemWorkItems.filter(w => w.concluido).length > 0 && (
                                      <div className="space-y-4 pt-8">
                                        <button 
                                          onClick={() => setIsCompletedLogsOpen(!isCompletedLogsOpen)}
                                          className="w-full flex items-center justify-between group cursor-pointer"
                                        >
                                          <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-emerald-500 pl-3">Concluídos ({systemWorkItems.filter(w => w.concluido).length})</h5>
                                          <svg className={`w-4 h-4 text-slate-300 transition-transform ${isCompletedLogsOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                                        </button>

                                        {isCompletedLogsOpen && (
                                          <div className="space-y-3 opacity-60 animate-in slide-in-from-top-2 duration-200">
                                            {systemWorkItems.filter(w => w.concluido).sort((a, b) => new Date(b.data_conclusao!).getTime() - new Date(a.data_conclusao!).getTime()).map(log => (
                                              <div key={log.id} className="bg-white border border-slate-100 rounded-none md:rounded-2xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 md:gap-4">
                                                <div className="flex-1 flex items-center gap-4 w-full">
                                                  <div className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                  </div>
                                                    <p className="text-xs font-medium text-slate-500 line-clamp-1">{log.descricao}</p>
                                                    {log.pool_dados && log.pool_dados.length > 0 && (
                                                      <div className="flex flex-wrap gap-1 mt-1">
                                                        {log.pool_dados.map((at, i) => (
                                                          <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block">
                                                            <img src={at.valor} alt="preview" className="w-8 h-8 object-cover rounded border border-slate-100 opacity-60 hover:opacity-100 transition-opacity" />
                                                          </a>
                                                        ))}
                                                      </div>
                                                    )}
                                                  </div>
                                                  <div className="flex gap-2 items-center">
                                                    <button
                                                      onClick={() => {
                                                        setEditingWorkItem(log);
                                                        setEditingWorkItemText(log.descricao);
                                                      }}
                                                      className="p-1.5 text-slate-300 hover:text-violet-600 rounded-lg transition-all"
                                                      title="Editar"
                                                    >
                                                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                    </button>
                                                    <button
                                                      onClick={() => {
                                                        if (confirmDeleteLogId === log.id) {
                                                          handleDeleteWorkItem(log.id);
                                                          setConfirmDeleteLogId(null);
                                                        } else {
                                                          setConfirmDeleteLogId(log.id);
                                                          setTimeout(() => setConfirmDeleteLogId(null), 3000);
                                                        }
                                                      }}
                                                      className={`p-1.5 rounded-lg transition-colors ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-300 hover:text-rose-600'}`}
                                                      title="Excluir"
                                                    >
                                                      {confirmDeleteLogId === log.id ? (
                                                        <svg className="w-3.5 h-3.5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                      ) : (
                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                      )}
                                                    </button>
                                                    <button
                                                      onClick={() => handleUpdateWorkItem(log.id, { concluido: false })}
                                                      className="text-[9px] font-black text-slate-300 hover:text-violet-600 uppercase ml-2"
                                                    >
                                                      Reabrir
                                                    </button>
                                                  </div>
                                               </div>
                                              ))}
                                            </div>
                                          )}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* Modal de Edição de Recurso (Link) */}
                            {editingResource && (
                              <div className="fixed inset-0 z-[400] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 md:p-8 animate-in zoom-in-95 duration-300">
                                <div className="bg-white w-full max-w-lg rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden">
                                  <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                                    <h3 className="text-xl font-black text-slate-900 tracking-tight">Editar {editingResource.label}</h3>
                                    <button onClick={() => setEditingResource(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                    </button>
                                  </div>
                                  <div className="p-8 space-y-6">
                                    <div className="space-y-2">
                                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">URL do Recurso</label>
                                      <input
                                        type="text"
                                        value={editingResource.value}
                                        onChange={(e) => setEditingResource({ ...editingResource, value: e.target.value })}
                                        placeholder="https://..."
                                        className="w-full bg-slate-50 border border-slate-200 rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-violet-500 transition-all"
                                      />
                                    </div>
                                    <div className="flex gap-4">
                                      <button
                                        onClick={() => setEditingResource(null)}
                                        className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all"
                                      >
                                        Cancelar
                                      </button>
                                      <button
                                        onClick={() => {
                                          handleUpdateSistema(unit.id, { [editingResource.field]: editingResource.value });
                                          setEditingResource(null);
                                        }}
                                        className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
                                      >
                                        Salvar Link
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Modal de Logs Full-screen */}
                            {isLogsModalOpen && (
                              <div className={`fixed inset-0 z-[35] bg-white flex flex-col ${isSidebarRetracted ? 'md:pl-24' : 'md:pl-72'} pt-[60px] md:pt-[72px] animate-in fade-in duration-300`}>
                                <div className="bg-white w-full h-full flex flex-col overflow-hidden shadow-2xl">
                                  <div className="p-6 md:p-10 border-b border-slate-100 flex items-center justify-between bg-white sticky top-0 z-10">
                                    <div className="flex items-center gap-4">
                                      <div className="p-3 bg-violet-100 text-violet-600 rounded-none md:rounded-2xl">
                                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                      </div>
                                      <div>
                                        <h3 className="text-2xl font-black text-slate-900 tracking-tight">Registro de Atividades</h3>
                                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">{systemName}</p>
                                      </div>
                                    </div>
                                    <button
                                      onClick={() => setIsLogsModalOpen(false)}
                                      className="p-3 bg-slate-100 text-slate-500 rounded-full hover:bg-slate-200 transition-all active:scale-95"
                                    >
                                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                    </button>
                                  </div>

                                  <div className="flex-1 overflow-y-auto p-6 md:p-12 space-y-12">
                                    <div className="space-y-6">
                                      <div className="flex items-center justify-between">
                                        <h5 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] border-l-4 border-violet-500 pl-4">Logs em Aberto</h5>
                                        <span className="bg-violet-100 text-violet-600 text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-widest">
                                          {systemWorkItems.filter(w => !w.concluido).length} Pendentes
                                        </span>
                                      </div>
                                        <div className="grid grid-cols-1 gap-6">
                                          {systemWorkItems.filter(w => !w.concluido).sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime()).map(log => (
                                            <div key={log.id} className="bg-slate-50 border border-slate-100 rounded-none md:rounded-[2.5rem] p-8 md:p-10 hover:shadow-xl hover:bg-white transition-all group relative overflow-hidden">
                                              {/* Decorative accent */}
                                              <div className="absolute top-0 left-0 w-1.5 h-full bg-violet-500 opacity-20 group-hover:opacity-100 transition-opacity"></div>
                                              
                                              <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-8">
                                                <div className="flex-1 min-w-0 space-y-4">
                                                  <div className="flex items-center flex-wrap gap-3">
                                                    <span className={`text-[9px] font-black px-3 py-1.5 rounded-full uppercase tracking-widest shadow-sm ${log.tipo === 'desenvolvimento' ? 'bg-violet-600 text-white' : log.tipo === 'ajuste' ? 'bg-amber-500 text-white' : 'bg-slate-200 text-slate-700'}`}>
                                                      {log.tipo}
                                                    </span>
                                                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{new Date(log.data_criacao).toLocaleDateString('pt-BR')}</span>
                                                  </div>
                                                  
                                                  <div className="space-y-4">
                                                    <p className="text-base md:text-xl font-bold text-slate-800 leading-[1.6] tracking-tight">{log.descricao}</p>
                                                    
                                                    {log.pool_dados && log.pool_dados.length > 0 && (
                                                      <div className="flex flex-wrap gap-3 mt-6">
                                                        {log.pool_dados.map((at, i) => (
                                                          <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block relative group/preview">
                                                            <div className="absolute inset-0 bg-violet-600/20 opacity-0 group-hover/preview:opacity-100 rounded-2xl transition-all z-10 flex items-center justify-center">
                                                              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                                                            </div>
                                                            <img src={at.valor} alt="preview" className="w-24 h-24 object-cover rounded-2xl border-2 border-white shadow-md hover:scale-105 transition-transform" />
                                                          </a>
                                                        ))}
                                                      </div>
                                                    )}
                                                  </div>
                                                </div>

                                                <div className="flex items-center gap-3 shrink-0 self-end lg:self-start bg-white lg:bg-transparent p-2 lg:p-0 rounded-2xl shadow-sm lg:shadow-none border lg:border-none border-slate-100">
                                                  <button
                                                    onClick={() => {
                                                      setEditingWorkItem(log);
                                                      setEditingWorkItemText(log.descricao);
                                                      setEditingWorkItemAttachments(log.pool_dados || []);
                                                    }}
                                                    className="p-4 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-2xl transition-all"
                                                    title="Editar"
                                                  >
                                                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                  </button>
                                                  <button
                                                    onClick={() => {
                                                      if (confirmDeleteLogId === log.id) {
                                                        handleDeleteWorkItem(log.id);
                                                        setConfirmDeleteLogId(null);
                                                      } else {
                                                        setConfirmDeleteLogId(log.id);
                                                        setTimeout(() => setConfirmDeleteLogId(null), 3000);
                                                      }
                                                    }}
                                                    className={`p-4 rounded-2xl transition-all ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white shadow-lg shadow-rose-200' : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50'}`}
                                                    title="Excluir"
                                                  >
                                                    {confirmDeleteLogId === log.id ? (
                                                      <svg className="w-6 h-6 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                    ) : (
                                                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                    )}
                                                  </button>
                                                  <button
                                                    onClick={() => handleUpdateWorkItem(log.id, { concluido: true, data_conclusao: new Date().toISOString() })}
                                                    className="w-16 h-16 rounded-full bg-white border-2 border-slate-200 flex items-center justify-center text-slate-300 hover:border-emerald-500 hover:text-emerald-500 hover:bg-emerald-50 transition-all shadow-sm ml-2 group/check"
                                                  >
                                                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                  </button>
                                                </div>
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                    </div>

                                    {systemWorkItems.filter(w => w.concluido).length > 0 && (
                                      <div className="space-y-6">
                                        <button 
                                          onClick={() => setIsModalCompletedLogsOpen(!isModalCompletedLogsOpen)}
                                          className="w-full flex items-center justify-between group cursor-pointer"
                                        >
                                          <h5 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] border-l-4 border-emerald-500 pl-4">Concluídos ({systemWorkItems.filter(w => w.concluido).length})</h5>
                                          <svg className={`w-5 h-5 text-slate-300 transition-transform ${isModalCompletedLogsOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                                        </button>
                                        
                                        {isModalCompletedLogsOpen && (
                                          <div className="grid grid-cols-1 gap-4 opacity-80 animate-in slide-in-from-top-4 duration-300">
                                            {systemWorkItems.filter(w => w.concluido).sort((a, b) => new Date(b.data_conclusao!).getTime() - new Date(a.data_conclusao!).getTime()).map(log => (
                                              <div key={log.id} className="bg-white border border-slate-100 rounded-none md:rounded-[2rem] p-8 flex flex-col md:flex-row md:items-center justify-between gap-6 hover:shadow-md transition-all">
                                                <div className="flex-1 min-w-0 space-y-3">
                                                  <div className="flex items-center gap-3">
                                                    <span className="text-[10px] font-black text-emerald-500 bg-emerald-50 px-3 py-1 rounded-full uppercase tracking-widest">Concluído em {new Date(log.data_conclusao!).toLocaleDateString('pt-BR')}</span>
                                                  </div>
                                                  <p className="text-base font-bold text-slate-500 leading-relaxed line-clamp-2 hover:line-clamp-none transition-all">{log.descricao}</p>
                                                  {log.pool_dados && log.pool_dados.length > 0 && (
                                                    <div className="flex flex-wrap gap-2 mt-3">
                                                      {log.pool_dados.map((at, i) => (
                                                        <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer" className="block relative group/preview">
                                                          <img src={at.valor} alt="preview" className="w-12 h-12 object-cover rounded-xl border border-slate-100 opacity-60 hover:opacity-100 transition-opacity shadow-sm" />
                                                        </a>
                                                      ))}
                                                    </div>
                                                  )}
                                                </div>
                                                  <div className="flex gap-4 items-center shrink-0">
                                                    <button
                                                      onClick={() => {
                                                        setEditingWorkItem(log);
                                                        setEditingWorkItemText(log.descricao);
                                                      }}
                                                      className="p-3 text-slate-300 hover:text-violet-600 hover:bg-violet-50 rounded-xl transition-all"
                                                      title="Editar"
                                                    >
                                                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                    </button>
                                                    <button
                                                      onClick={() => {
                                                        if (confirmDeleteLogId === log.id) {
                                                          handleDeleteWorkItem(log.id);
                                                          setConfirmDeleteLogId(null);
                                                        } else {
                                                          setConfirmDeleteLogId(log.id);
                                                          setTimeout(() => setConfirmDeleteLogId(null), 3000);
                                                        }
                                                      }}
                                                      className={`p-3 rounded-xl transition-all ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white shadow-lg' : 'text-slate-300 hover:text-rose-600 hover:bg-rose-50'}`}
                                                      title="Excluir"
                                                    >
                                                      {confirmDeleteLogId === log.id ? (
                                                        <svg className="w-5 h-5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                      ) : (
                                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                      )}
                                                    </button>
                                                    <button
                                                      onClick={() => handleUpdateWorkItem(log.id, { concluido: false })}
                                                      className="px-6 py-3 bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-violet-600 transition-all shadow-md active:scale-95 ml-2"
                                                    >
                                                      Reabrir
                                                    </button>
                                                  </div>
                                              </div>
                                            ))}
                                          </div>
                                      )}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )}
                            {/* Modal de Edição de Log */}
                            {editingWorkItem && (
                              <div className="fixed inset-0 z-[500] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 md:p-8 animate-in zoom-in-95 duration-300">
                                <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden">
                                  <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                                    <div className="flex items-center gap-4">
                                       <div className="p-3 bg-violet-100 text-violet-600 rounded-2xl">
                                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                       </div>
                                       <h3 className="text-xl font-black text-slate-900 tracking-tight">Editar Registro</h3>
                                    </div>
                                    <button onClick={() => setEditingWorkItem(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors text-slate-400">
                                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                    </button>
                                  </div>
                                  <div className="p-8 space-y-6">
                                    <div className="space-y-4">
                                      <div className="space-y-2">
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Descrição</label>
                                        <WysiwygEditor
                                          value={editingWorkItemText}
                                          onChange={setEditingWorkItemText}
                                          className="bg-slate-50 min-h-[120px]"
                                        />
                                      </div>

                                      <div className="space-y-2">
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Anexos (Drive)</label>
                                        <div className="flex flex-wrap gap-2">
                                          {editingWorkItemAttachments.map((at, i) => (
                                            <div key={i} className="relative group/at">
                                              <img src={at.valor} alt="preview" className="w-20 h-20 object-cover rounded-xl border border-slate-200" />
                                              <button
                                                onClick={() => setEditingWorkItemAttachments(prev => prev.filter((_, idx) => idx !== i))}
                                                className="absolute -top-2 -right-2 bg-rose-500 text-white rounded-full p-1 opacity-0 group-hover/at:opacity-100 transition-all z-10 shadow-lg"
                                              >
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                              </button>
                                            </div>
                                          ))}
                                          <label className={`w-20 h-20 border-2 border-dashed border-slate-200 rounded-xl flex items-center justify-center cursor-pointer hover:border-violet-400 hover:bg-violet-50 transition-all ${isUploading ? 'animate-pulse pointer-events-none' : ''}`}>
                                            <input
                                              type="file"
                                              accept="image/*"
                                              className="hidden"
                                              onChange={async (e) => {
                                                const file = e.target.files?.[0];
                                                if (file) {
                                                  const item = await handleFileUploadToDrive(file);
                                                  if (item) setEditingWorkItemAttachments(prev => [...prev, item]);
                                                }
                                              }}
                                            />
                                            {isUploading ? (
                                              <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
                                            ) : (
                                              <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                            )}
                                          </label>
                                        </div>
                                      </div>
                                    </div>
                                    
                                    <div className="flex gap-4 pt-4">
                                      <button
                                        onClick={() => setEditingWorkItem(null)}
                                        className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-[1.5rem] transition-all"
                                      >
                                        Cancelar
                                      </button>
                                      <button
                                        onClick={() => {
                                          handleUpdateWorkItem(editingWorkItem.id, { 
                                            descricao: editingWorkItemText,
                                            tipo: editingWorkItem.tipo,
                                            pool_dados: editingWorkItemAttachments
                                          });
                                          setEditingWorkItem(null);
                                          setEditingWorkItemAttachments([]);
                                        }}
                                        disabled={!editingWorkItemText.trim()}
                                        className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-[1.5rem] text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50"
                                      >
                                        Salvar Alterações
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })()
                  )}
                </div>



              ) : (
                <div className="space-y-3 md:space-y-10">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-6 bg-white p-3 md:p-8 rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl">
                    <div className="hidden md:block">
                      <h3 className="text-4xl font-black text-slate-900 tracking-tighter">Gestão PGC</h3>
                      <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">{new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}</p>
                    </div>
                    <div className="flex items-center gap-3 md:gap-4">
                      {pgcSubView === 'plano' && (
                        <button
                          onClick={() => setIsImportPlanOpen(true)}
                          className="bg-slate-900 text-white px-4 md:px-6 py-2 md:py-3 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center gap-2 md:gap-3"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                          Importar <span className="hidden md:inline">Planilha</span>
                        </button>
                      )}

                      <select
                        value={currentMonth}
                        onChange={(e) => setCurrentMonth(Number(e.target.value))}
                        className="flex-1 md:flex-none text-[10px] font-black uppercase bg-slate-100 px-4 py-2 rounded-lg md:rounded-xl border-none outline-none focus:ring-2 focus:ring-slate-900"
                      >
                        {['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'].map((m, i) => (
                          <option key={i} value={i}>{m}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="flex border-b border-slate-200 gap-4 md:gap-8">
                    <button
                      onClick={() => setPgcSubView('audit')}
                      className={`px-2 py-3 md:py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 ${pgcSubView === 'audit' ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                    >
                      Resumo
                    </button>
                    <button
                      onClick={() => setPgcSubView('plano')}
                      className={`px-2 py-3 md:py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 ${pgcSubView === 'plano' ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                    >
                      Plano
                    </button>
                  </div>

                  {pgcSubView === 'audit' && (
                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 md:gap-6 h-[calc(100vh-180px)] pb-4">
                      <div className="lg:col-span-3 bg-white rounded-none md:rounded-[2rem] border border-slate-200 shadow-xl flex flex-col overflow-hidden h-full">
                        <div className="p-4 md:p-6 border-b border-slate-100 flex-shrink-0 bg-slate-50/50">
                          <div className="flex items-center justify-between">
                            <h4 className="text-sm font-black text-slate-900 tracking-tight">Pendentes</h4>
                            <span className="bg-slate-900 text-white text-[9px] font-black px-2 py-1 rounded-full">{pgcTasksAguardando.length}</span>
                          </div>
                          <p className="text-slate-400 text-[9px] font-black uppercase tracking-widest mt-1">Arraste p/ vincular</p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                          {pgcTasksAguardando.map(task => (
                            <PgcMiniTaskCard key={task.id} task={task} onClick={() => setSelectedTask(task)} />
                          ))}
                          {pgcTasksAguardando.length === 0 && (
                            <div className="py-10 text-center">
                              <p className="text-slate-300 font-black text-[9px] uppercase tracking-widest italic">Tudo limpo!</p>
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="lg:col-span-9 bg-white rounded-none md:rounded-[2rem] border border-slate-200 overflow-hidden shadow-xl flex flex-col h-full">
                        <div className="flex-1 overflow-y-auto divide-y divide-slate-100 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                          {(() => {
                            const currentPlan = planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`);

                            if (!currentPlan) return <div className="p-12 text-center h-full flex items-center justify-center"><p className="text-slate-300 font-black text-sm uppercase tracking-widest italic">Nenhum plano definido.</p></div>;

                            return currentPlan.itens.map((item, index) => {
                              const entregaEntity = pgcEntregas.find(e => e.entrega === item.entrega);
                              const entregaId = entregaEntity?.id;

                              const atividadesRelacionadas: AtividadeRealizada[] = entregaId ? atividadesPGC.filter(a => a.entrega_id === entregaId) : [];
                              const tarefasRelacionadas: Tarefa[] = entregaId ? pgcTasks.filter(t => t.entregas_relacionadas?.includes(entregaId)) : [];

                              return (
                                <React.Fragment key={String(index)}>
                                  <PgcAuditRow
                                    item={item}
                                    entregaEntity={entregaEntity}
                                    atividadesRelacionadas={atividadesRelacionadas}
                                    tarefasRelacionadas={tarefasRelacionadas}
                                    onDrop={async (tarefaId) => {
                                      let targetId = entregaId;
                                      if (!targetId) {
                                        const newId = await handleCreateEntregaFromPlan(item);
                                        if (newId) targetId = newId;
                                      }
                                      if (targetId) handleLinkTarefa(tarefaId, targetId);
                                    }}
                                    onUnlinkTarefa={handleUnlinkTarefa}
                                    onSelectTask={setSelectedTask}
                                  />
                                </React.Fragment>
                              );
                            });
                          })()}
                        </div>
                      </div>
                    </div>
                  )}

                  {pgcSubView === 'plano' && (
                    <div className="animate-in space-y-8">
                      <div className="bg-white border border-slate-200 rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl">
                        {/* Desktop Table */}
                        <table className="w-full text-left min-w-[800px] hidden md:table">
                          <thead className="bg-slate-50 border-b border-slate-200">
                            <tr>
                              <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Origem / Unidade</th>
                              <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Entrega Institucional</th>
                              <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Descrição</th>
                              <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-[200px]">% Carga Horária</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)?.itens.map((item, i) => (
                              <tr key={i} className="hover:bg-slate-50 transition-colors">
                                <td className="px-8 py-6">
                                  <div className="text-[10px] font-black text-slate-400 uppercase mb-1">{item.origem}</div>
                                  <div className="text-xs font-black text-slate-900">{item.unidade}</div>
                                </td>
                                <td className="px-8 py-6 text-sm font-black text-slate-900">{item.entrega}</td>
                                <td className="px-8 py-6 text-xs font-medium text-slate-600 leading-relaxed max-w-xs">{item.descricao}</td>
                                <td className="px-8 py-6">
                                  <div className="flex items-center gap-4">
                                    <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                                      <div className="h-full bg-indigo-500 rounded-full transition-all duration-1000" style={{ width: `${item.percentual}%` }}></div>
                                    </div>
                                    <span className="text-[10px] font-black text-slate-900 w-10">{item.percentual}%</span>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>

                        {/* Mobile Card View */}
                        <div className="md:hidden divide-y divide-slate-100">
                          {planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)?.itens.map((item, i) => (
                            <div key={i} className="p-6 space-y-4">
                              <div className="flex justify-between items-start gap-4">
                                <div className="flex-1">
                                  <div className="text-[8px] font-black text-slate-400 uppercase mb-1">{item.origem} • {item.unidade}</div>
                                  <div className="text-sm font-black text-slate-900 leading-tight">{item.entrega}</div>
                                </div>
                                <div className="bg-indigo-50 text-indigo-600 px-2 py-1 rounded text-[10px] font-black">{item.percentual}%</div>
                              </div>
                              <p className="text-xs text-slate-500 leading-relaxed">{item.descricao}</p>
                              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                                <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${item.percentual}%` }}></div>
                              </div>
                            </div>
                          ))}
                        </div>

                        {(!planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)) && (
                          <div className="px-8 py-20 text-center">
                            <p className="text-slate-300 font-black text-sm uppercase tracking-widest italic">Nenhum plano de trabalho configurado para este período.</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
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
        isTerminalOpen && (
          <div className="fixed inset-0 z-[150] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-md animate-in fade-in duration-300">
            <div className="bg-[#0C0C0C] w-full max-w-2xl rounded-none md:rounded-[2rem] shadow-[0_0_100px_rgba(37,99,235,0.2)] border border-white/10 overflow-hidden flex flex-col h-[500px] animate-in zoom-in-95">
              <div className="p-6 bg-white/5 border-b border-white/5 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.5)]"></div>
                    <div className="w-3 h-3 rounded-full bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]"></div>
                    <div className="w-3 h-3 rounded-full bg-emerald-500 shadow-[0_0_100px_rgba(16,185,129,0.5)]"></div>
                  </div>
                  <h3 className="text-[10px] font-black text-white/40 uppercase tracking-[0.3em] ml-2">Google Sync Console v2</h3>
                </div>
                <div className="flex items-center gap-4">
                  {isSyncing && (
                    <button
                      onClick={async () => {
                        await setDoc(doc(db, 'system', 'sync'), { status: 'idle', logs: [...(syncData?.logs || []), "--- INTERROMPIDO PELO USUÁRIO ---"] });
                        setIsSyncing(false);
                      }}
                      className="text-[9px] font-bold text-rose-500/60 hover:text-rose-400 bg-rose-500/10 border border-rose-500/20 px-3 py-1 rounded-full transition-all"
                    >
                      FORÇAR INTERRUPÇÃO
                    </button>
                  )}
                  <button onClick={() => setIsTerminalOpen(false)} className="text-white/40 hover:text-white transition-colors">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-6 font-mono text-[11px] space-y-2 selection:bg-blue-500/30">
                <div className="text-blue-400 opacity-60"># hermes_cli.py --sync-mode automatic</div>
                {syncData?.logs?.map((log: string, i: number) => (
                  <div key={i} className={`flex gap-3 ${log.includes('ERRO') ? 'text-rose-400' : log.includes('PUSH') ? 'text-blue-400' : log.includes('PULL') ? 'text-emerald-400' : 'text-slate-400'}`}>
                    <span className="opacity-30 shrink-0">[{i}]</span>
                    <span className="leading-relaxed">{log}</span>
                  </div>
                ))}
                {isSyncing && (
                  <div className="flex items-center gap-2 text-white/50 animate-pulse">
                    <span className="w-1.5 h-1.5 bg-blue-500 rounded-full"></span>
                    <span>Processando transações em tempo real...</span>
                  </div>
                )}
                {!isSyncing && syncData?.status === 'completed' && (
                  <div className="pt-4 border-t border-white/5 text-emerald-400 font-bold">
                    ✓ SINCROIZAÇÃO CONCLUÍDA COM SUCESSO.
                  </div>
                )}
                {syncData?.status === 'error' && (
                  <div className="pt-4 border-t border-white/5 text-rose-500 font-bold">
                    ⚠ FALHA NO PROCESSAMENTO: {syncData.error_message}
                  </div>
                )}
              </div>

              <div className="p-4 bg-white/5 text-[9px] font-bold text-white/20 uppercase tracking-widest flex justify-between items-center">
                <span>Core: Firebase Firestore + Google Tasks API</span>
                <span>Encerrado: {syncData?.last_success ? formatDate(syncData.last_success.split('T')[0]) : '-'}</span>
              </div>
            </div>
          </div>
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
            <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
              <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
                <div>
                  <h3 className="text-2xl font-black text-slate-900 tracking-tight">Importar Plano Mensal</h3>
                  <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">Cole o JSON do plano de trabalho abaixo</p>
                </div>
                <button onClick={() => setIsImportPlanOpen(false)} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
                  <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>

              <div className="p-8 space-y-6">
                <div className="grid grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Ano</label>
                    <input type="number" id="import-year" defaultValue={currentYear} className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900" />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Mês</label>
                    <select id="import-month" defaultValue={currentMonth + 1} className="w-full bg-slate-100 border-none rounded-none md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900">
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Dump JSON</label>
                  <textarea
                    id="import-json"
                    rows={10}
                    className="w-full bg-slate-900 text-blue-400 border-none rounded-none md:rounded-2xl px-6 py-4 text-[10px] font-mono focus:ring-2 focus:ring-blue-500 transition-all resize-none"
                    placeholder='[ { "entrega": "Exemplo", "percentual": 50 }, ... ]'
                  />
                </div>
              </div>

              <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4">
                <button
                  onClick={() => setIsImportPlanOpen(false)}
                  className="flex-1 px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all"
                >
                  Cancelar
                </button>
                <button
                  onClick={async () => {
                    try {
                      const year = (document.getElementById('import-year') as HTMLInputElement).value;
                      const month = (document.getElementById('import-month') as HTMLSelectElement).value.padStart(2, '0');
                      const rawText = (document.getElementById('import-json') as HTMLTextAreaElement).value;

                      let items: PlanoTrabalhoItem[] = [];

                      // Tenta detectar se é JSON ou o formato de texto/tabela
                      if (rawText.trim().startsWith('[') || rawText.trim().startsWith('{')) {
                        items = JSON.parse(rawText);
                      } else {
                        // Parser para o formato de tabela de texto
                        const lines = rawText.split('\n').map(l => l.trim()).filter(l => l !== '');
                        for (let i = 0; i < lines.length; i++) {
                          const line = lines[i];
                          if (line === 'Própria Unidade' || line === 'Outra Unidade') {
                            const item: Partial<PlanoTrabalhoItem> = { origem: line };
                            item.unidade = lines[++i] || '';
                            item.entrega = lines[++i] || '';
                            // Opcional: pular "Curtir"
                            if (lines[i + 1] === 'Curtir') i++;
                            const pctStr = lines[++i] || '0';
                            item.percentual = parseFloat(pctStr.replace('%', '')) || 0;
                            item.descricao = lines[++i] || '';
                            items.push(item as PlanoTrabalhoItem);
                          }
                        }
                      }

                      if (items.length === 0) throw new Error("Nenhum item identificado no texto colado.");

                      const docId = `${year}-${month}`;
                      await setDoc(doc(db, 'planos_trabalho', docId), {
                        mes_ano: docId,
                        itens: items,
                        data_atualizacao: new Date().toISOString()
                      });

                      setIsImportPlanOpen(false);
                      showAlert("Sucesso", `Sucesso! ${items.length} entregas importadas para o plano ${docId}.`);
                    } catch (err: any) {
                      showAlert("Erro", "Erro ao processar dados: " + err.message);
                    }
                  }}
                  className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
                >
                  Processar e Gravar
                </button>
              </div>
            </div>
          </div>
        )
      }

      {isSystemSelectorOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white w-full max-w-md rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
            <div className="p-8 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-xl font-black text-slate-900">Selecionar Sistema</h3>
              <button onClick={() => setIsSystemSelectorOpen(false)} className="p-2 hover:bg-slate-100 rounded-full">
                <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="p-8 space-y-3 max-h-[400px] overflow-y-auto custom-scrollbar">
              {unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(sistema => (
                <button
                  key={sistema.id}
                  onClick={() => handleFinalizeIdeaConversion(sistema.id)}
                  className="w-full text-left p-4 rounded-none md:rounded-2xl border-2 border-slate-100 hover:border-violet-500 hover:bg-violet-50 transition-all flex items-center gap-3 group"
                >
                  <div className="w-10 h-10 bg-slate-100 group-hover:bg-violet-500 group-hover:text-white rounded-lg md:rounded-xl flex items-center justify-center transition-colors">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                  </div>
                  <span className="font-bold text-slate-700 group-hover:text-violet-700">{sistema.nome.replace('SISTEMA:', '').trim()}</span>
                </button>
              ))}
              {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length === 0 && (
                <p className="text-center text-slate-400 py-8 italic text-sm">Nenhum sistema cadastrado.</p>
              )}
            </div>
          </div>
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
