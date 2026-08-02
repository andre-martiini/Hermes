import React, { useState, useEffect, useMemo, useRef } from 'react';
import { createRoot, Root } from 'react-dom/client';
import {
  Tarefa, Status, EntregaInstitucional, AtividadeRealizada,
  Afastamento, PlanoTrabalho, PlanoTrabalhoItem, Categoria, Acompanhamento,
  BrainstormIdea, FinanceTransaction, FinanceGoal, FinanceSettings,
  FixedBill, BillRubric, IncomeEntry, IncomeRubric, HealthWeight,
  HealthSettings, ExerciseLog, ExerciseSettings, PullupPhase, HermesNotification, AppSettings,
  formatDate, formatDateLocalISO,
  GoogleCalendarEvent,
  PoolItem, CustomNotification, HealthExam, ConhecimentoItem, UndoAction, HermesModalProps,
  ShoppingItem, Projeto, BaseConhecimento, TipoAcao, Servico, Toast,
  HealthTelegramReminder, EstrategiaPessoal, EstrategiaIndicadorSucesso
} from './types';
import HealthView from './HealthView';
import { MeetingTranscriptionTool } from './src/components/tools/MeetingTranscriptionTool';
import { STATUS_COLORS, PROJECT_COLORS } from './constants';
import { db, functions, auth, storage, googleProvider, signInWithPopup, signOut, browserLocalPersistence, browserSessionPersistence, setPersistence } from './firebase';
import { onAuthStateChanged, User } from 'firebase/auth';
import { collection, onSnapshot, query, orderBy, updateDoc, doc, addDoc, deleteDoc, setDoc, arrayUnion, arrayRemove, writeBatch, getDoc, getDocs, where } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { ref, uploadBytes } from 'firebase/storage';
import FinanceView from './FinanceView';
import DashboardView from './DashboardView';
import { MobileShortcutsView } from './src/views/MobileShortcutsView';
import KnowledgeView from './KnowledgeView';
import ProjectsView from './ProjectsView';
import RAGBasesView from './src/views/RAGBasesView';
import { ServicesView } from './src/views/ServicesView';
import ContactsView from './ContactsView';
import { INTERNAL_NAVIGATION_EVENT } from './src/utils/internalNavigation';
// Importações dos módulos extraídos pelo split.js
import {
  DEFAULT_APP_SETTINGS, getDaysInMonth, isWorkDay, callScrapeSipac,
  getMonthWorkDays, normalizeStatus, formatWhatsAppText,
  formatInlineWhatsAppText, detectAreaFromTitle, isStandbyStatus,
  applyStandbyDateRules, buildGravityMap, computeGravidade,
  computeScoreGUT
} from './src/utils/helpers';
import {
  ToastContainer, FilterChip, PgcMiniTaskCard,
  RowCard, WysiwygEditor, NotificationCenter, AutoExpandingTextarea
} from './src/components/ui/UIComponents';
import { PgdAuditRow } from './src/components/ui/PgdAuditRow';
import { CreatePgdPlanModal } from './src/components/pgd/CreatePgdPlanModal';
import { CreatePgdPlanPayload } from './src/utils/pgdPlanAutomation';
import {
  HermesModal, SettingsModal,
  TaskCreateModal, TaskEditModal
} from './src/components/modals/Modals';
import { DayView } from './src/views/DayView';
import { CalendarView } from './src/views/CalendarView';
import { CategoryView } from './src/views/CategoryView';
import { TaskExecutionView } from './src/views/TaskExecutionView';
import { StrategyDashboardView } from './src/views/StrategyDashboardView';
import PublicFinancePortal from './src/components/public/PublicFinancePortal';
import PublicShoppingPortal from './src/components/public/PublicShoppingPortal';
import { TranscriptionTool } from './src/components/tools/TranscriptionTool';
import { ShoppingListTool } from './src/components/tools/ShoppingListTool';
import { FerramentasView } from './src/components/tools/FerramentasView';
import { HermesGodmodeView } from './src/components/tools/HermesGodmodeView';
import { QuickNoteModal } from './src/components/modals/QuickNoteModal';
import { SpeedDialMenu } from './src/components/ui/SpeedDialMenu';
import { HermesCopilotoDrawer } from './src/components/tools/HermesCopilotoDrawer';
import { HermesGlobalChat } from './src/components/tools/HermesGlobalChat';
import { HermesVoiceOverlay } from './src/components/tools/HermesVoiceOverlay';
import { generateMarkdown, generateActionsMarkdown, downloadMarkdown } from './src/utils/markdownGenerator';
import {
  ROOT_ACTIONS_FOLDER_ID,
  ROOT_HEALTH_FOLDER_ID,
  ROOT_PROJECTS_FOLDER_ID,
  getTaskIdFromActionFolderId
} from './src/utils/knowledgeLogic';
import { parseDiaryRichNote } from './src/utils/diaryEntries';
import { getAreaForStrategyPillar, normalizeAreaName } from './src/utils/strategicAreas';
type SortOption = 'date-asc' | 'date-desc' | 'priority-high' | 'priority-low';
type DateFilter = 'today' | 'week' | 'month';
type ThemeMode = 'system' | 'dark' | 'light';
const isLocalAuthBypassEnabled = import.meta.env.DEV && import.meta.env.VITE_BYPASS_AUTH === 'true';
const localDevUser = {
  uid: 'local-dev-user',
  displayName: 'Desenvolvimento Local',
  email: 'local@hermes.dev',
  photoURL: null,
  getIdToken: async () => ''
} as unknown as User;
// --- Utilitários ---
// --- Modais ---
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

const hasValidActionDate = (task: Pick<Tarefa, 'data_limite'>): boolean => {
  return Boolean(task.data_limite && task.data_limite !== '-' && task.data_limite !== '0000-00-00' && /^\d{4}-\d{2}-\d{2}$/.test(task.data_limite));
};

const shouldShowInStandbyBucket = (task: Tarefa): boolean => {
  return isStandbyStatus(task.status) || !hasValidActionDate(task);
};
// -----------------------------------------------------------------------------

const TranscriptionAIModal = ({ isOpen, onClose, showToast }: { isOpen: boolean, onClose: () => void, showToast: (m: string, t: 'success' | 'error' | 'info') => void }) => {
  const [file, setFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcription, setTranscription] = useState<{ raw: string, refined: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isMobileViewport, setIsMobileViewport] = useState(() => window.innerWidth < 768);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  useEffect(() => {
    if (!isOpen) {
      setFile(null);
      setTranscription(null);
      setIsRecording(false);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      return;
    }
    const handlePaste = (e: ClipboardEvent) => {
      if (e.clipboardData && e.clipboardData.files.length > 0) {
        const pastedFile = e.clipboardData.files[0];
        if (pastedFile.type.startsWith('audio/') || pastedFile.type.startsWith('video/')) {
          handleFileSelection(pastedFile);
        }
      }
    };
    const handleResize = () => setIsMobileViewport(window.innerWidth < 768);
    window.addEventListener('paste', handlePaste);
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('paste', handlePaste);
      window.removeEventListener('resize', handleResize);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
    };
  }, [isOpen]);
  const handleFileSelection = (f: File) => {
    if (f.size > 25 * 1024 * 1024) {
      if (f.size > 6 * 1024 * 1024) {
        showToast("Arquivo muito grande. Limite: 6MB.", "error");
        return;
      }
    }
    setFile(f);
    setTranscription(null);
    void handleTranscribe(f);
  };
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      mediaRecorder.onstop = async () => {
        setIsRecording(false);
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => track.stop());
          streamRef.current = null;
        }
        const mimeType = audioChunksRef.current[0]?.type || 'audio/webm';
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        const audioFile = new File([audioBlob], `gravacao-${Date.now()}.webm`, { type: mimeType });
        handleFileSelection(audioFile);
      };
      mediaRecorder.start();
      setFile(null);
      setTranscription(null);
      setIsRecording(true);
      showToast("Gravando áudio...", "info");
    } catch (error) {
      console.error("Erro ao acessar microfone:", error);
      showToast("Permissão de microfone negada ou indisponível.", "error");
    }
  };
  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
  };
  useEffect(() => {
    const handleSharedAudio = (e: any) => {
      if (e.detail && e.detail instanceof File) {
        handleFileSelection(e.detail);
      }
    };
    window.addEventListener('hermes-shared-audio', handleSharedAudio);
    return () => window.removeEventListener('hermes-shared-audio', handleSharedAudio);
  }, []);
  const handleTranscribe = async (selectedFile: File | null = file) => {
    if (!selectedFile) return;
    const uid = auth.currentUser?.uid;
    if (!uid) {
      showToast("Você precisa estar autenticado para transcrever.", "error");
      return;
    }
    setIsProcessing(true);
    try {
      const extension = `.${selectedFile.name.split('.').pop()?.toLowerCase() || 'm4a'}`;
      const storagePath = `quick_transcriptions/${uid}/${Date.now()}${extension}`;
      await uploadBytes(ref(storage, storagePath), selectedFile, { contentType: selectedFile.type || 'application/octet-stream' });
      const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
      const response = await transcribeFunc({ storagePath, extension });
      const data = response.data as { raw: string, refined: string };
      setTranscription(data);
      // Also save to history for compatibility with the tool
      const saved = localStorage.getItem('hermes_transcription_history');
      const history = saved ? JSON.parse(saved) : [];
      const newEntry = {
        id: Date.now().toString(),
        fileName: selectedFile.name,
        fileSize: selectedFile.size,
        date: new Date().toISOString(),
        raw: data.raw,
        refined: data.refined
      };
      localStorage.setItem('hermes_transcription_history', JSON.stringify([newEntry, ...history].slice(0, 50)));
      try {
        await navigator.clipboard.writeText(data.refined || data.raw || '');
        showToast("Transcrição copiada!", "success");
        if (isMobileViewport) {
          window.setTimeout(() => {
            setFile(null);
            setTranscription(null);
          }, 450);
        }
      } catch (clipboardError) {
        console.error('Erro ao copiar transcrição:', clipboardError);
        showToast("Transcrição pronta, mas não foi possível copiar.", "error");
      }
    } catch (error) {
      console.error(error);
      showToast("Erro ao processar áudio.", "error");
    } finally {
      setIsProcessing(false);
    }
  };
  if (!isOpen) return null;
  if (isMobileViewport) {
    return (
      <div className="fixed inset-0 z-[250] flex items-center justify-center bg-slate-950/10 backdrop-blur-md p-0">
        <div className="flex items-center justify-center gap-3 w-full px-4">
          <button
            onClick={onClose}
            aria-label="Cancelar transcrição"
            className="flex items-center justify-center shrink-0 w-[15vw] h-[15vw] min-w-[52px] min-h-[52px] max-w-[64px] max-h-[64px] rounded-[1.15rem] border-2 border-white/80 bg-slate-900/65 text-white shadow-xl transition-all active:scale-95 hover:bg-slate-800/80"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.6" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
          <button
            onClick={isProcessing ? undefined : (isRecording ? stopRecording : startRecording)}
            disabled={isProcessing}
            aria-label={isProcessing ? 'Processando transcrição' : isRecording ? 'Parar gravação' : 'Iniciar gravação'}
            className={`relative flex items-center justify-center shadow-2xl transition-all active:scale-95 w-[62vw] h-[18vw] min-w-[180px] min-h-[58px] max-w-[320px] max-h-[76px] rounded-[1.6rem] border-4 border-white ${isProcessing
              ? 'bg-indigo-600 text-white'
              : isRecording
                ? 'bg-rose-700 text-white animate-pulse'
                : 'bg-rose-600 text-white hover:bg-rose-700'
              }`}
          >
            {isProcessing ? (
              <span className="inline-flex h-9 w-9 rounded-full border-4 border-white border-t-transparent animate-spin" />
            ) : isRecording ? (
              <svg className="w-9 h-9" fill="currentColor" viewBox="0 0 24 24"><path d="M7 7h10v10H7z" /></svg>
            ) : (
              <svg className="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 18a6 6 0 006-6V8a6 6 0 10-12 0v4a6 6 0 006 6zm0 0v3m-4 0h8" /></svg>
            )}
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center bg-slate-950/90 animate-in fade-in p-4">
      <div className="bg-white w-full max-w-md rounded-none shadow-2xl overflow-hidden animate-in slide-in-from-bottom-4 md:zoom-in-95 my-auto border border-border-grid">
        <div className="px-5 py-4 md:px-6 md:py-5 border-b border-border-grid bg-white flex items-center justify-between">
          <div>
            <h3 className="text-lg md:text-xl font-black text-slate-900 tracking-tight font-mono">Transcrição IA</h3>
            <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-1 font-mono">Ãudio rápido com cópia automática</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-none transition-colors">
            <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="p-5 md:p-6 space-y-4">
          {!transcription ? (
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files.length) handleFileSelection(e.dataTransfer.files[0]); }}
              className={`border border-dashed rounded-none p-5 md:p-6 flex flex-col items-center justify-center text-center gap-4 transition-all min-h-[340px] md:min-h-0 ${dragOver ? 'border-primary-tactile bg-amber-50' : 'border-border-grid bg-slate-50'}`}
            >
              {isProcessing ? (
                <div className="flex flex-col items-center gap-4 py-8">
                  <div className="w-12 h-12 border-4 border-primary-tactile border-t-transparent rounded-none animate-spin" />
                  <p className="text-primary-tactile font-black uppercase tracking-widest text-[10px] font-mono">Processando e copiando...</p>
                </div>
              ) : file ? (
                <div className="space-y-4 py-2 w-full">
                  <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-none flex items-center justify-center mx-auto border border-emerald-200">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                  </div>
                  <p className="text-sm font-black text-slate-900 truncate px-4 font-mono">{file.name}</p>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 font-mono">Transcrição automática em andamento</p>
                </div>
              ) : (
                <div className="py-4 w-full flex flex-col items-center justify-center gap-5 md:gap-4">
                  <button
                    onClick={isRecording ? stopRecording : startRecording}
                    className={`mx-auto relative shadow-lg transition-all active:scale-95 w-[80vw] max-w-[320px] h-[16vw] max-h-[76px] min-h-[60px] rounded-none md:w-24 md:h-24 ${isRecording ? 'bg-rose-700 text-white animate-pulse' : 'bg-rose-600 text-white hover:bg-rose-700'}`}
                  >
                    <span className="absolute inset-0 flex items-center justify-center">
                      {isRecording ? (
                        <svg className="w-8 h-8 block" fill="currentColor" viewBox="0 0 24 24"><path d="M7 7h10v10H7z" /></svg>
                      ) : (
                        <svg className="w-8 h-8 block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 18a6 6 0 006-6V8a6 6 0 10-12 0v4a6 6 0 006 6zm0 0v3m-4 0h8" /></svg>
                      )}
                    </span>
                  </button>
                  <div className="space-y-1">
                    <p className="font-black text-slate-900 font-mono">{isRecording ? 'Toque novamente para encerrar' : 'Toque para gravar o áudio'}</p>
                    <p className="text-slate-400 text-xs font-medium md:hidden font-mono">Use o botão central para iniciar a gravação.</p>
                    <p className="text-slate-400 text-xs font-medium hidden md:block font-mono">Também funciona com colar, arrastar ou selecionar arquivo.</p>
                  </div>
                  <div className="mt-2 hidden md:block">
                    <label htmlFor="mobile-transcription-upload" className="bg-white border border-border-grid text-slate-700 px-4 py-3 rounded-none font-black uppercase tracking-widest text-[10px] shadow-sm hover:border-primary-tactile hover:text-primary-tactile transition-all cursor-pointer flex items-center gap-2 mx-auto w-fit font-mono">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                      Selecionar Arquivo
                    </label>
                    <input
                      id="mobile-transcription-upload"
                      type="file"
                      className="hidden"
                      accept="audio/*,video/*"
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                        if (e.target.files && e.target.files.length > 0) {
                          handleFileSelection(e.target.files[0]);
                          e.target.value = '';
                        }
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4 animate-in slide-in-from-bottom-4">
              <div className="bg-emerald-50 px-4 py-3 rounded-none border border-emerald-100">
                <label className="text-[10px] font-black text-emerald-600 uppercase tracking-widest block font-mono">Copiado automaticamente</label>
              </div>
              <div className="bg-slate-50 p-4 md:p-5 rounded-none border border-border-grid max-h-[280px] overflow-y-auto custom-scrollbar">
                <label className="text-[10px] font-black text-primary-tactile uppercase tracking-widest block mb-2 font-mono">Resultado Final</label>
                <p className="text-slate-800 text-base font-bold leading-relaxed whitespace-pre-wrap font-mono">{transcription.refined}</p>
              </div>
              <div className="flex gap-4">
                <button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(transcription.refined);
                      showToast("Transcrição copiada!", "success");
                    } catch (clipboardError) {
                      console.error('Erro ao copiar transcrição:', clipboardError);
                      showToast("Não foi possível copiar a transcrição.", "error");
                    }
                  }}
                  className="flex-1 bg-slate-900 text-white py-3 rounded-none text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all flex items-center justify-center gap-2 font-mono"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                  Copiar Novamente
                </button>
                <button onClick={() => { setFile(null); setTranscription(null); }} className="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none transition-all font-mono">Novo</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
interface AIMatchedItem {
  id: string;
  nome: string;
  categoria: string;
  quantidade: string;
  unit: string;
  confirmed: boolean; // user can uncheck
  isNew?: boolean;    // not in catalog yet
}
interface ShoppingAIImage {
  id: string;
  name: string;
  mimeType: string;
  base64: string;
  previewUrl: string;
}
interface ShoppingAIConfirmItem {
  id?: string;
  nome?: string;
  categoria?: string;
  quantidade: string;
  unit?: string;
  isNew?: boolean;
}
const ShoppingAIModal = ({
  isOpen, onClose, catalogItems, onConfirmItems, onViewList, plannedCount
}: {
  isOpen: boolean;
  onClose: () => void;
  catalogItems: ShoppingItem[];
  onConfirmItems: (items: ShoppingAIConfirmItem[]) => void;
  onViewList: () => void;
  plannedCount: number;
}) => {
  const [step, setStep] = useState<'input' | 'processing' | 'validation'>('input');
  const [textInput, setTextInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [matchedItems, setMatchedItems] = useState<AIMatchedItem[]>([]);
  const [errorMsg, setErrorMsg] = useState('');
  const [attachedImages, setAttachedImages] = useState<ShoppingAIImage[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const imageUrlsRef = useRef<string[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const resetToInput = () => { setStep('input'); setMatchedItems([]); setErrorMsg(''); };
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      imageUrlsRef.current.forEach(url => URL.revokeObjectURL(url));
    };
  }, []);
  const handleImageFiles = async (files: File[]) => {
    const imageFiles = files.filter(file => file.type.startsWith('image/'));
    if (imageFiles.length === 0) return;
    const availableSlots = Math.max(0, 4 - attachedImages.length);
    if (availableSlots === 0) {
      setErrorMsg('Limite de 4 imagens por processamento.');
      return;
    }
    const acceptedFiles = imageFiles.slice(0, availableSlots);
    const oversized = acceptedFiles.find(file => file.size > 4 * 1024 * 1024);
    if (oversized) {
      setErrorMsg('Use imagens de atÃÂ© 4 MB cada.');
      return;
    }
    const images = await Promise.all(acceptedFiles.map(file => new Promise<ShoppingAIImage>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = String(reader.result || '');
        const previewUrl = URL.createObjectURL(file);
        imageUrlsRef.current.push(previewUrl);
        resolve({
          id: `${Date.now()}_${Math.random()}`,
          name: file.name || 'imagem-colada',
          mimeType: file.type || 'image/png',
          base64: dataUrl.split(',')[1] || '',
          previewUrl,
        });
      };
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    })));
    setErrorMsg('');
    setAttachedImages(prev => [...prev, ...images]);
  };
  const removeImage = (id: string) => {
    setAttachedImages(prev => {
      const target = prev.find(image => image.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter(image => image.id !== id);
    });
  };
  useEffect(() => {
    if (!isOpen) return;
    const handlePaste = (e: ClipboardEvent) => {
      const files = Array.from(e.clipboardData?.files || []).filter(file => file.type.startsWith('image/'));
      if (files.length === 0) return;
      e.preventDefault();
      handleImageFiles(files);
    };
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, [isOpen, attachedImages.length]);
  if (!isOpen) return null;
  // --- Recording ---
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        stream.getTracks().forEach(t => t.stop());
        // Transcribe then process
        setStep('processing');
        try {
          const reader = new FileReader();
          reader.readAsDataURL(blob);
          reader.onloadend = async () => {
            try {
              const base64 = (reader.result as string).split(',')[1];
              const fn = httpsCallable(functions, 'transcreverAudio');
              const res = await fn({ audioBase64: base64 });
              const data = res.data as { refined: string };
              const transcript = data.refined || '';
              if (transcript) {
                await processWithGemini(transcript);
              } else {
                setErrorMsg('Não consegui transcrever o áudio. Tente digitar.');
                setStep('input');
              }
            } catch {
              setErrorMsg('Erro ao transcrever áudio.');
              setStep('input');
            }
          };
        } catch {
          setErrorMsg('Erro ao ler áudio.');
          setStep('input');
        }
      };
      streamRef.current = stream;
      mr.start();
      setIsRecording(true);
    } catch {
      alert('Permissão de microfone negada.');
    }
  };
  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };
  // --- Gemini matching ---
  const processWithGemini = async (text: string, images: ShoppingAIImage[] = attachedImages) => {
    setStep('processing');
    setErrorMsg('');
    try {
      const catalog = catalogItems.map(i => `ID:${i.id}|NOME:${i.nome}|CAT:${i.categoria}`).join('\n');
      const prompt = `Você é um assistente de lista de compras. O usuário descreveu itens que deseja comprar.
CATÃLOGO DISPONÃVEL (id|nome|categoria):
${catalog || '(vazio)'}
PEDIDO DO USUÃRIO:
"${text}"
Sua tarefa:
1. Para cada item mencionado pelo usuário, encontre o item mais próximo no catálogo (matching fuzzy/semÃ¢ntico tolerante a abreviações, sinônimos e erros). Ex: "ricota" pode corresponder a "Queijo Ricota".
2. Identifique a quantidade mencionada (número + unidade se houver). Se não mencionado, use "1 un".
3. Se não houver correspondência razoável no catálogo, marque isNew=true com o nome como o usuário falou.
Responda SOMENTE com JSON válido no formato abaixo, sem markdown, sem explicações:
{
  "itens": [
    { "catalogId": "ID_DO_ITEM_OU_null_SE_NOVO", "nomeExibido": "Nome para exibir", "quantidade": "2", "unit": "kg", "isNew": false }
  ]
}`;
      const fn = httpsCallable(functions, 'matchShoppingItemsAI');
      const result = await fn({
        text,
        images: images.map(image => ({
          mimeType: image.mimeType,
          base64: image.base64,
          name: image.name,
        })),
        catalogItems: catalogItems.map((item) => ({
          id: item.id,
          nome: item.nome,
          categoria: item.categoria,
        })),
      });
      const parsed = result.data as { itens?: any[] };
      const resolved: AIMatchedItem[] = (parsed.itens || []).map((it: any) => {
        const catalogItem = it.catalogId ? catalogItems.find(c => c.id === it.catalogId) : null;
        return {
          id: catalogItem?.id || `new_${Date.now()}_${Math.random()}`,
          nome: it.nomeExibido || catalogItem?.nome || 'Item desconhecido',
          categoria: catalogItem?.categoria || 'Geral',
          quantidade: String(it.quantidade || '1'),
          unit: it.unit || 'un',
          confirmed: true,
          isNew: !!it.isNew || !catalogItem,
        };
      });
      if (resolved.length === 0) {
        setErrorMsg('Não identifiquei itens no pedido. Tente descrever de forma diferente.');
        setStep('input');
        return;
      }
      setMatchedItems(resolved);
      setStep('validation');
    } catch (e) {
      console.error(e);
      setErrorMsg('Erro ao processar com IA. Verifique a conexão.');
      setStep('input');
    }
  };
  const handleSubmitText = async () => {
    if (!textInput.trim() && attachedImages.length === 0) return;
    await processWithGemini(textInput.trim(), attachedImages);
  };
  const toggleItem = (id: string) => {
    setMatchedItems(prev => prev.map(i => i.id === id ? { ...i, confirmed: !i.confirmed } : i));
  };
  const updateQtd = (id: string, val: string) => {
    setMatchedItems(prev => prev.map(i => i.id === id ? { ...i, quantidade: val } : i));
  };
  const updateMatchedItem = (id: string, updates: Partial<AIMatchedItem>) => {
    setMatchedItems(prev => prev.map(i => i.id === id ? { ...i, ...updates } : i));
  };
  const handleConfirm = () => {
    const toAdd = matchedItems.filter(i => i.confirmed && (!i.isNew || i.nome.trim()));
    if (toAdd.length === 0) { onClose(); return; }
    onConfirmItems(toAdd.map(i => ({
      id: i.isNew ? undefined : i.id,
      nome: i.nome.trim(),
      categoria: i.categoria.trim() || 'Geral',
      quantidade: i.quantidade || '1',
      unit: i.unit || 'un',
      isNew: i.isNew,
    })));
    setTextInput('');
    attachedImages.forEach(image => URL.revokeObjectURL(image.previewUrl));
    setAttachedImages([]);
    setMatchedItems([]);
    setStep('input');
    onClose();
  };
  const confirmedCount = matchedItems.filter(i => i.confirmed && (!i.isNew || i.nome.trim())).length;
  const newCount = matchedItems.filter(i => i.isNew).length;
  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-0 md:p-4 bg-slate-900/70 dark:bg-black/80 backdrop-blur-md animate-in fade-in">
      <div className="bg-white dark:bg-slate-950 w-full max-w-2xl h-full md:h-auto md:max-h-[92vh] rounded-none md:rounded-[2.5rem] shadow-[0_40px_80px_-20px_rgba(0,0,0,0.35)] dark:shadow-[0_40px_100px_-20px_rgba(0,0,0,0.8)] flex flex-col overflow-hidden animate-in zoom-in-95 duration-300">
        {/* Header */}
        <div className="p-7 md:p-8 border-b border-border-grid bg-white flex items-center gap-4 flex-shrink-0">
          <div className="w-12 h-12 bg-slate-900 rounded-none flex items-center justify-center shadow-lg flex-shrink-0">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-xl font-black text-slate-900 tracking-tight font-mono uppercase">Assistente de Compras IA</h3>
            <p className="text-primary-tactile text-[10px] font-black uppercase tracking-[0.2em] mt-0.5 font-mono">
              {step === 'input' ? 'Diga o que você quer comprar' : step === 'processing' ? 'Buscando no catálogo...' : 'Valide os itens identificados'}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-none transition-all flex-shrink-0">
            <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        {/* Body */}
        <div className="flex-1 overflow-y-auto p-7 md:p-8 space-y-5">
          {/* === INPUT STEP === */}
          {step === 'input' && (
            <>
              {errorMsg && (
                <div className="bg-rose-50 dark:bg-rose-950/35 border border-rose-100 dark:border-rose-900/60 rounded-2xl px-5 py-3 flex items-center gap-3">
                  <svg className="w-4 h-4 text-rose-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  <p className="text-rose-700 dark:text-rose-200 text-sm font-bold">{errorMsg}</p>
                </div>
              )}
              <div className="bg-slate-50 rounded-none border border-border-grid focus-within:border-primary-tactile transition-all shadow-inner overflow-hidden">
                <div className="flex items-start gap-3 p-4">
                  <button
                    onClick={isRecording ? stopRecording : startRecording}
                    className={`mt-1 w-12 h-12 rounded-none flex items-center justify-center flex-shrink-0 transition-all ${isRecording ? 'bg-rose-500 text-white animate-pulse shadow-lg' : 'bg-white border border-border-grid text-slate-400 hover:text-emerald-600 hover:border-emerald-200 hover:shadow-md'}`}
                    title={isRecording ? 'Parar gravação' : 'Gravar áudio'}
                  >
                    {isRecording
                      ? <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
                      : <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>}
                  </button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="mt-1 w-12 h-12 rounded-none flex items-center justify-center flex-shrink-0 transition-all bg-white border border-border-grid text-slate-400 hover:text-emerald-600 hover:border-emerald-200 hover:shadow-md"
                    title="Carregar imagem"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-8h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    multiple
                    className="hidden"
                    onChange={e => {
                      handleImageFiles(Array.from(e.target.files || []));
                      e.currentTarget.value = '';
                    }}
                  />
                  <textarea
                    autoFocus
                    className="flex-1 bg-transparent border-none outline-none py-3 text-base font-bold text-slate-800 placeholder:text-slate-300 resize-none min-h-[120px] font-mono"
                    placeholder={isRecording ? 'Gravando... Fale os itens que deseja comprar...' : 'Ex: "2 kg de arroz, 1 caixa de leite, ricota, sabão em pó e 3 iogurtes"'}
                    value={textInput}
                    disabled={isRecording}
                    onChange={e => setTextInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) handleSubmitText(); }}
                  />
                </div>
                {isRecording && (
                  <div className="px-5 pb-4 flex items-center gap-2">
                    <div className="flex gap-0.5">
                      {[...Array(8)].map((_, i) => (
                        <div key={i} className="w-1 bg-rose-500 rounded-none animate-pulse" style={{ height: `${8 + Math.random() * 16}px`, animationDelay: `${i * 100}ms` }} />
                      ))}
                    </div>
                    <span className="text-rose-600 text-[11px] font-black uppercase tracking-widest font-mono">Gravando</span>
                  </div>
                )}
                {attachedImages.length > 0 && (
                  <div className="px-5 pb-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {attachedImages.map(image => (
                      <div key={image.id} className="relative overflow-hidden rounded-none border border-border-grid bg-white">
                        <img src={image.previewUrl} alt={image.name} className="h-24 w-full object-cover" />
                        <button
                          onClick={() => removeImage(image.id)}
                          className="absolute right-2 top-2 w-7 h-7 rounded-none bg-slate-950/80 text-white flex items-center justify-center hover:bg-rose-500 transition-colors"
                          title="Remover imagem"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                        <div className="px-3 py-2">
                          <p className="truncate text-[10px] font-black uppercase tracking-widest text-slate-500 font-mono">{image.name}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="bg-emerald-50/60 dark:bg-emerald-950/25 rounded-2xl border border-emerald-100/60 dark:border-emerald-900/50 px-5 py-4 flex gap-3">
                <svg className="w-4 h-4 text-emerald-600 dark:text-emerald-300 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <p className="text-[11px] font-bold text-emerald-800 dark:text-emerald-100 leading-relaxed">
                  O Hermes vai buscar os itens no seu catálogo usando IA. "Ricota" pode corresponder a "Queijo Ricota", "Bombril" a "Palha de Aço", etc.
                </p>
              </div>
              <button
                onClick={onViewList}
                className="w-full flex items-center gap-4 px-5 py-4 rounded-none border border-border-grid hover:border-primary-tactile bg-white transition-all group"
              >
                <div className="w-9 h-9 rounded-none bg-slate-50 flex items-center justify-center flex-shrink-0 border border-border-grid">
                  <svg className="w-5 h-5 text-slate-900" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                  </svg>
                </div>
                <div className="flex-1 text-left">
                  <p className="text-[11px] font-black uppercase tracking-widest text-slate-700 font-mono">Ver lista completa</p>
                  <p className={`text-[10px] font-bold mt-0.5 font-mono ${plannedCount > 0 ? 'text-primary-tactile' : 'text-slate-400'}`}>
                    {plannedCount > 0 ? `${plannedCount} ${plannedCount === 1 ? 'item na lista' : 'itens na lista'}` : 'Nenhum item na lista ainda'}
                  </p>
                </div>
                {plannedCount > 0 && (
                  <span className="bg-slate-900 text-white text-xs font-black rounded-none min-w-[1.5rem] h-6 px-1.5 flex items-center justify-center flex-shrink-0 font-mono">
                    {plannedCount}
                  </span>
                )}
                <svg className="w-4 h-4 text-slate-300 group-hover:text-primary-tactile transition-colors flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </>
          )}
          {/* === PROCESSING STEP === */}
          {step === 'processing' && (
            <div className="py-20 flex flex-col items-center justify-center gap-6 text-center">
              <div className="relative w-20 h-20">
                <div className="w-20 h-20 rounded-full border-4 border-emerald-100 dark:border-emerald-950 animate-spin border-t-emerald-500 dark:border-t-emerald-300" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <svg className="w-8 h-8 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                </div>
              </div>
              <div>
                <p className="font-black text-slate-800 text-lg">Hermes está pensando...</p>
                <p className="text-slate-400 text-sm font-medium mt-1">Buscando correspondências no catálogo</p>
              </div>
            </div>
          )}
          {/* === VALIDATION STEP === */}
          {step === 'validation' && (
            <div className="space-y-4 animate-in fade-in duration-300">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-black text-slate-800 dark:text-slate-100">{matchedItems.filter(i => !i.isNew).length} itens identificados</p>
                  {newCount > 0 && <p className="text-[10px] text-amber-600 font-black uppercase tracking-widest mt-0.5">{newCount} não encontrado{newCount > 1 ? 's' : ''} no catálogo</p>}
                </div>
                <button onClick={resetToInput} className="text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-slate-700 transition-colors">
                  ? Refazer
                </button>
              </div>
              <div className="space-y-2">
                {matchedItems.map(item => (
                  <div
                    key={item.id}
                    onClick={() => toggleItem(item.id)}
                    className={`rounded-2xl border px-5 py-4 flex items-center gap-4 transition-all ${item.isNew ? 'bg-amber-50/70 dark:bg-amber-950/20 border-amber-100 dark:border-amber-900/50' : item.confirmed ? 'bg-emerald-50/40 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900/60 cursor-pointer hover:bg-emerald-50 dark:hover:bg-emerald-950/35' : 'bg-slate-50 dark:bg-slate-900 border-slate-100 dark:border-slate-800 cursor-pointer opacity-50 hover:opacity-70'}`}
                  >
                    {/* Checkbox */}
                    <div className={`w-7 h-7 rounded-xl border-2 flex items-center justify-center flex-shrink-0 transition-all ${item.confirmed ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-950'}`}>
                      {item.confirmed ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : null}
                    </div>
                    {/* Item info */}
                    <div className="flex-1 min-w-0" onClick={e => item.isNew && e.stopPropagation()}>
                      {item.isNew ? (
                        <div className="grid grid-cols-1 sm:grid-cols-[1fr_9rem] gap-2">
                          <input
                            value={item.nome}
                            onChange={e => updateMatchedItem(item.id, { nome: e.target.value })}
                            className="w-full rounded-xl border border-amber-200 dark:border-amber-900/60 bg-white dark:bg-slate-950 px-3 py-2 text-sm font-black text-amber-800 dark:text-amber-100 outline-none focus:border-emerald-400"
                            placeholder="Nome do item"
                          />
                          <input
                            value={item.categoria}
                            onChange={e => updateMatchedItem(item.id, { categoria: e.target.value })}
                            className="w-full rounded-xl border border-amber-200 dark:border-amber-900/60 bg-white dark:bg-slate-950 px-3 py-2 text-sm font-bold text-slate-700 dark:text-slate-200 outline-none focus:border-emerald-400"
                            placeholder="Categoria"
                          />
                          <p className="sm:col-span-2 text-[10px] font-black uppercase tracking-widest text-amber-600 dark:text-amber-300">Novo item: serÃÂ¡ cadastrado no catÃÂ¡logo e adicionado ao planejamento</p>
                        </div>
                      ) : (
                        <>
                      <p className="font-black text-sm truncate text-slate-900 dark:text-slate-100">{item.nome}</p>
                      <p className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest mt-0.5">
                        {item.isNew ? '? Não no catálogo' : item.categoria}
                      </p>
                        </>
                      )}
                    </div>
                    {/* Quantity editor */}
                    <div onClick={e => e.stopPropagation()} className="flex items-center gap-2 bg-white dark:bg-slate-950 border border-slate-100 dark:border-slate-800 rounded-xl px-3 py-2 shadow-sm">
                      <button onClick={() => updateQtd(item.id, String(Math.max(0.5, (parseFloat(item.quantidade) || 1) - 1)))} className="w-5 h-5 rounded-lg bg-slate-100 dark:bg-slate-800 font-black flex items-center justify-center text-slate-600 dark:text-slate-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/50 transition-all text-sm leading-none">-</button>
                      <span className="w-12 text-center font-black text-slate-800 dark:text-slate-100 text-sm">
                        {item.quantidade} <span className="text-slate-400 dark:text-slate-500 font-medium text-[10px]">{item.unit}</span>
                      </span>
                      <button onClick={() => updateQtd(item.id, String((parseFloat(item.quantidade) || 0) + 1))} className="w-5 h-5 rounded-lg bg-slate-100 dark:bg-slate-800 font-black flex items-center justify-center text-slate-600 dark:text-slate-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/50 transition-all text-sm leading-none">+</button>
                    </div>
                  </div>
                ))}
              </div>
              {newCount > 0 && (
                <div className="bg-amber-50 dark:bg-amber-950/25 border border-amber-100 dark:border-amber-900/50 rounded-2xl px-5 py-3 flex gap-3">
                  <svg className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  <p className="text-[11px] font-bold text-amber-800 dark:text-amber-100 leading-relaxed">
                    {newCount} item(ns) nÃÂ£o foram encontrados no catÃÂ¡logo. Revise o nome e a categoria aqui; ao confirmar, eles serÃÂ£o cadastrados e adicionados ao planejamento.
                  </p>
                  <p className="hidden">
                    {newCount} item(ns) não foram encontrados no catálogo. Cadastre-os primeiro na aba "Cadastro" e o assistente os reconhecerá na próxima vez.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
        {/* Footer */}
        <div className="flex-shrink-0 p-6 md:p-8 pt-0 space-y-3">
          {step === 'input' && (
            <div className="flex gap-4">
              <button onClick={onClose} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-900 rounded-2xl transition-all">Fechar</button>
              <button
                onClick={handleSubmitText}
                disabled={(!textInput.trim() && attachedImages.length === 0) || isRecording}
                className="flex-[2] bg-emerald-600 dark:bg-emerald-500 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg shadow-emerald-100 dark:shadow-emerald-950/40 hover:bg-emerald-700 dark:hover:bg-emerald-400 transition-all disabled:opacity-50 disabled:grayscale flex items-center justify-center gap-2 active:scale-[0.98]"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                Processar com IA
              </button>
            </div>
          )}
          {step === 'validation' && (
            <div className="flex gap-4">
              <button onClick={resetToInput} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-900 rounded-2xl transition-all">Voltar</button>
              <button
                onClick={handleConfirm}
                disabled={confirmedCount === 0}
                className="flex-[2] bg-slate-900 dark:bg-emerald-500 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-xl hover:bg-emerald-600 dark:hover:bg-emerald-400 transition-all disabled:opacity-50 disabled:grayscale flex items-center justify-center gap-2 active:scale-[0.98]"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                Confirmar {confirmedCount} iten{confirmedCount !== 1 ? 's' : ''}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const isBlankActionDescription = (value?: string | null) => !value || /^[\s\-_–—]*$/.test(value);

const hasActionDescriptionContext = (task: Tarefa) => {
  const hasDiary = (task.acompanhamento || []).some(entry => String(entry?.nota || '').trim().length > 0);
  const hasPlan = (task.plano_acao || []).some(item => String(item?.text || '').trim().length > 0);
  return hasDiary || hasPlan;
};

const App: React.FC = () => {
  const [routeTick, setRouteTick] = useState(0);
  const pathname = window.location.pathname;
  useEffect(() => {
    const syncRoute = () => setRouteTick((current) => current + 1);
    window.addEventListener('popstate', syncRoute);
    window.addEventListener(INTERNAL_NAVIGATION_EVENT, syncRoute as EventListener);
    return () => {
      window.removeEventListener('popstate', syncRoute);
      window.removeEventListener(INTERNAL_NAVIGATION_EVENT, syncRoute as EventListener);
    };
  }, []);
  if (pathname.startsWith('/gastos-externos')) {
    return <PublicFinancePortal />;
  }
  if (pathname.startsWith('/compras-externas')) {
    return <PublicShoppingPortal />;
  }
  const [user, setUser] = useState<User | null>(isLocalAuthBypassEnabled ? localDevUser : null);
  const [authLoading, setAuthLoading] = useState(!isLocalAuthBypassEnabled);
  const [rememberMe, setRememberMe] = useState(true);
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [undoStack, setUndoStack] = useState<UndoAction[]>([]);
  const [modalState, setModalState] = useState<HermesModalProps>({
    isOpen: false,
    title: '',
    message: '',
    type: 'alert',
    onConfirm: () => { }
  });
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState<GoogleCalendarEvent[]>([]);
  const [entregas, setEntregas] = useState<EntregaInstitucional[]>([]);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [isCompletedLogsOpen, setIsCompletedLogsOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Finance State
  const [financeTransactions, setFinanceTransactions] = useState<FinanceTransaction[]>([]);
  const [financeGoals, setFinanceGoals] = useState<FinanceGoal[]>([]);
  const [fixedBills, setFixedBills] = useState<FixedBill[]>([]);
  const [billRubrics, setBillRubrics] = useState<BillRubric[]>([]);
  const [incomeEntries, setIncomeEntries] = useState<IncomeEntry[]>([]);
  const [incomeRubrics, setIncomeRubrics] = useState<IncomeRubric[]>([]);
  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [financeSettings, setFinanceSettings] = useState<FinanceSettings>({
    monthlyBudget: 5000,
    monthlyBudgets: {},
    sprintDates: { 1: "08", 2: "15", 3: "22", 4: "01" },
    emergencyReserveTarget: 0,
    emergencyReserveCurrent: 0,
    investmentReserveTarget: 50000,
    investmentReserveCurrent: 0,
    defaultPrincipalIncome: 0,
    billCategories: ['Conta Fixa', 'Poupança', 'Investimento'],
    incomeCategories: ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']
  });
  // Health State
  const [healthWeights, setHealthWeights] = useState<HealthWeight[]>([]);
  const [healthSettings, setHealthSettings] = useState<HealthSettings>({ targetWeight: 0 });
  const [exerciseLogs, setExerciseLogs] = useState<ExerciseLog[]>([]);
  const [exerciseSettings, setExerciseSettings] = useState<ExerciseSettings>({});
  const [healthTelegramReminders, setHealthTelegramReminders] = useState<HealthTelegramReminder[]>([]);
  // Systems State
  const [isPgdTerminalOpen, setIsPgdTerminalOpen] = useState(false);
  const [pgdTerminalLogs, setPgdTerminalLogs] = useState<string[]>([]);
  const [isCreatePgdPlanOpen, setIsCreatePgdPlanOpen] = useState(false);
  const [isShoppingAIModalOpen, setIsShoppingAIModalOpen] = useState(false);
  const [isTranscriptionAIModalOpen, setIsTranscriptionAIModalOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isRecordingLog, setIsRecordingLog] = useState(false);
  const [isProcessingLog, setIsProcessingLog] = useState(false);
  const logMediaRecorderRef = useRef<MediaRecorder | null>(null);
  const logAudioChunksRef = useRef<Blob[]>([]);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [descriptionSynthesisTaskId, setDescriptionSynthesisTaskId] = useState<string | null>(null);
  const [isBatchDescriptionSynthesisRunning, setIsBatchDescriptionSynthesisRunning] = useState(false);
  const [isCopilotoOpen, setIsCopilotoOpen] = useState(false);
  const [isCopilotoLauncherOpen, setIsCopilotoLauncherOpen] = useState(false);
  const [isVoiceLiveActive, setIsVoiceLiveActive] = useState(false);
  const [copilotoAutoStartMic, setCopilotoAutoStartMic] = useState(false);
  const [copilotoMode, setCopilotoMode] = useState<'default' | 'finance' | 'saude' | 'estrategia'>('default');
  const [copilotoInitialPrompt, setCopilotoInitialPrompt] = useState<string | null>(null);
  const [isQuickNoteModalOpen, setIsQuickNoteModalOpen] = useState(false);
  const [hasAutoExpanded, setHasAutoExpanded] = useState(false);
  // Estados PGC
  const [atividadesPGC, setAtividadesPGC] = useState<AtividadeRealizada[]>([]);
  const [afastamentos, setAfastamentos] = useState<Afastamento[]>([]);
  const [pgcSubView, setPgcSubView] = useState<'audit' | 'heatmap' | 'config' | 'plano' | 'status' | 'automatizadas'>('audit');
  const [pgdGeneratingByEntrega, setPgdGeneratingByEntrega] = useState<Record<string, boolean>>({});
  const [pgdRawTextProcessingByEntrega, setPgdRawTextProcessingByEntrega] = useState<Record<string, boolean>>({});
  const [unidades, setUnidades] = useState<{ id: string, nome: string, palavras_chave?: string[], peso_gravidade?: number }[]>([]);
  // Knowledge State
  const [knowledgeItems, setKnowledgeItems] = useState<ConhecimentoItem[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<BaseConhecimento[]>([]);
  const [isKnowledgeBasesLoaded, setIsKnowledgeBasesLoaded] = useState(false);
  const [masterKnowledge, setMasterKnowledge] = useState<any[]>([]);
  // Shopping State
  const [shoppingItems, setShoppingItems] = useState<ShoppingItem[]>([]);
  // Services State
  const [services, setServices] = useState<Servico[]>([]);
  const [isImportPlanOpen, setIsImportPlanOpen] = useState(false);
  const [isCompletedTasksOpen, setIsCompletedTasksOpen] = useState(false);
  const [brainstormIdeas, setBrainstormIdeas] = useState<BrainstormIdea[]>([]);
  const [activeFerramenta, setActiveFerramenta] = useState<'brainstorming' | 'shopping' | 'transcription' | 'batch_transcription' | 'meeting_transcription' | 'whatsapp_assistant' | 'diagnostico' | 'pop_manager' | 'sipac_tracking' | null>(null);
  const [initialDiagnosisId, setInitialDiagnosisId] = useState<string | undefined>(undefined);
  const [isBrainstormingAddingText, setIsBrainstormingAddingText] = useState(false);
  const [confirmDeleteLogId, setConfirmDeleteLogId] = useState<string | null>(null);
  const [convertingIdea, setConvertingIdea] = useState<BrainstormIdea | null>(null);
  const [isSystemSelectorOpen, setIsSystemSelectorOpen] = useState(false);
  const [taskInitialData, setTaskInitialData] = useState<Partial<Tarefa> | null>(null);

  const handleSnapshotError = (label: string) => (err: any) => {
    console.error(`[Firestore] Listener falhou (${label}):`, err);
  };
  useEffect(() => {
    if (isLocalAuthBypassEnabled) {
      setUser(localDevUser);
      setAuthLoading(false);
      return;
    }
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setAuthLoading(false);
    });
    return () => unsubscribe();
  }, []);
  const handleLogin = async () => {
    try {
      await setPersistence(auth, rememberMe ? browserLocalPersistence : browserSessionPersistence);
      await signInWithPopup(auth, googleProvider);
      showToast("Login realizado com sucesso!", "success");
    } catch (error) {
      console.error("Erro ao fazer login:", error);
      showToast("Erro ao fazer login com Google.", "error");
    }
  };
  const handleLogout = async () => {
    if (isLocalAuthBypassEnabled) {
      showToast("Auth desativada no ambiente local.", "info");
      return;
    }
    try {
      await signOut(auth);
      showToast("Sessão encerrada.", "info");
    } catch (error) {
      console.error("Erro ao fazer logout:", error);
    }
  };
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
  const pushToUndoStack = (label: string, undo: () => Promise<void> | void) => {
    const action: UndoAction = {
      id: Math.random().toString(36).substr(2, 9),
      label,
      undo,
      timestamp: Date.now()
    };
    setUndoStack(prev => [action, ...prev].slice(0, 10));
  };
  const handleUndo = async () => {
    if (undoStack.length === 0) return;
    const [action, ...rest] = undoStack;
    await action.undo();
    setUndoStack(rest);
    showToast(`Desfeito: ${action.label}`, "info");
  };
  const getUndoToastAction = () => ({
    label: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 10h10a4 4 0 110 8H9" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 10l4-4m-4 4l4 4" />
      </svg>
    ),
    onClick: () => {
      void handleUndo();
    }
  });
  useEffect(() => {
    const handleOpenKnowledgeNode = (e: any) => {
      const kgId = e.detail;
      if (kgId) {
        setActiveModule('acoes');
        setViewMode('knowledge');
        setTimeout(() => {
          // Trigger the specific node opening inside KnowledgeView.
          // Since KnowledgeView uses internal state, we can pass it via another event
          // or just navigate to knowledge.
          window.dispatchEvent(new CustomEvent('knowledge-view-open-node', { detail: kgId }));
        }, 100);
      }
    };
    window.addEventListener('open-knowledge-node', handleOpenKnowledgeNode);
    return () => window.removeEventListener('open-knowledge-node', handleOpenKnowledgeNode);
  }, []);
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        const target = e.target as HTMLElement;
        const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
        if (!isInput) {
          e.preventDefault();
          handleUndo();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undoStack]);
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
        // Stop audio tracks immediately to release hardware
        if (stream) stream.getTracks().forEach(track => track.stop());
        await handleProcessLogAudio(audioBlob);
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
  // Finance Sync
  useEffect(() => {
    if (!user) return;
    const unsubGoogleCalendar = onSnapshot(collection(db, 'google_calendar_events'), (snapshot) => {
      setGoogleCalendarEvents(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as GoogleCalendarEvent)));
    }, handleSnapshotError('google_calendar_events'));
    const unsubTransactions = onSnapshot(collection(db, 'finance_transactions'), (snapshot) => {
      setFinanceTransactions(snapshot.docs
        .map(d => ({ id: d.id, ...d.data() } as FinanceTransaction))
        .filter(t => t.status !== 'deleted')
      );
    }, handleSnapshotError('finance_transactions'));
    const unsubGoals = onSnapshot(collection(db, 'finance_goals'), (snapshot) => {
      setFinanceGoals(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as FinanceGoal)));
    }, handleSnapshotError('finance_goals'));
    const unsubSettings = onSnapshot(doc(db, 'finance_settings', 'config'), (doc) => {
      if (doc.exists()) {
        setFinanceSettings(doc.data() as FinanceSettings);
      }
    }, handleSnapshotError('finance_settings/config'));
    const qFixedBills = query(collection(db, 'fixed_bills'));
    const unsubFixedBills = onSnapshot(qFixedBills, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as FixedBill));
      setFixedBills(data);
    }, handleSnapshotError('fixed_bills'));
    const unsubRubrics = onSnapshot(collection(db, 'bill_rubrics'), (snapshot) => {
      setBillRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as BillRubric)));
    }, handleSnapshotError('bill_rubrics'));
    const unsubIncomeEntries = onSnapshot(collection(db, 'income_entries'), (snapshot) => {
      setIncomeEntries(snapshot.docs
        .map(d => ({ id: d.id, ...d.data() } as IncomeEntry))
        .filter(e => e.status !== 'deleted')
      );
    }, handleSnapshotError('income_entries'));
    const unsubIncomeRubrics = onSnapshot(collection(db, 'income_rubrics'), (snapshot) => {
      setIncomeRubrics(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as IncomeRubric)));
    }, handleSnapshotError('income_rubrics'));
    const unsubShopping = onSnapshot(collection(db, 'shopping_items'), (snapshot) => {
      setShoppingItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as ShoppingItem)));
    }, handleSnapshotError('shopping_items'));
    // Services Sync
    const qServices = query(collection(db, 'servicos'), orderBy('data_criacao', 'desc'));
    const unsubProjects = onSnapshot(qServices, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })) as Servico[];
      setServices(data);
    }, handleSnapshotError('servicos'));
    // Health Sync
    const unsubHealthWeights = onSnapshot(collection(db, 'health_weights'), (snapshot) => {
      setHealthWeights(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as HealthWeight)));
    }, handleSnapshotError('health_weights'));
    const unsubHealthSettings = onSnapshot(doc(db, 'health_settings', 'config'), (doc) => {
      if (doc.exists()) setHealthSettings(doc.data() as HealthSettings);
    }, handleSnapshotError('health_settings/config'));
    const unsubExerciseLogs = onSnapshot(collection(db, 'health_exercise_logs'), (snapshot) => {
      setExerciseLogs(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as ExerciseLog)));
    }, handleSnapshotError('health_exercise_logs'));
    const unsubExerciseSettings = onSnapshot(doc(db, 'health_exercise_settings', 'config'), (snap) => {
      if (snap.exists()) setExerciseSettings(snap.data() as ExerciseSettings);
    }, handleSnapshotError('health_exercise_settings/config'));
    const unsubHealthTelegramReminders = onSnapshot(collection(db, 'health_telegram_reminders'), (snapshot) => {
      setHealthTelegramReminders(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as HealthTelegramReminder)));
    }, handleSnapshotError('health_telegram_reminders'));
    const unsubKnowledge = onSnapshot(collection(db, 'conhecimento'), (snapshot) => {
      setKnowledgeItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as ConhecimentoItem)));
    }, handleSnapshotError('conhecimento'));
    const unsubMasterKnowledge = onSnapshot(collection(db, 'conhecimento_mestre'), (snapshot) => {
      setMasterKnowledge(snapshot.docs.map(d => ({ id: d.id, ...d.data() })));
    }, handleSnapshotError('conhecimento_mestre'));
    const unsubKnowledgeBases = onSnapshot(collection(db, 'knowledge_bases'), (snapshot) => {
      const allBases = snapshot.docs.map(d => ({ id: d.id, ...d.data() } as BaseConhecimento));
      const uniqueBases = allBases.filter((b, i, arr) => arr.findIndex(x => x.nome === b.nome) === i);
      setKnowledgeBases(uniqueBases);
      setIsKnowledgeBasesLoaded(true);
    }, handleSnapshotError('knowledge_bases'));
    return () => {
      unsubGoogleCalendar();
      unsubTransactions();
      unsubGoals();
      unsubSettings();
      unsubFixedBills();
      unsubRubrics();
      unsubIncomeEntries();
      unsubIncomeRubrics();
      unsubShopping();
      unsubProjects();
      unsubHealthWeights();
      unsubHealthSettings();
      unsubExerciseLogs();
      unsubExerciseSettings();
      unsubHealthTelegramReminders();
      unsubKnowledge();
      unsubMasterKnowledge();
      unsubKnowledgeBases();
    };
  }, [user]);

  const hasSeededRef = useRef(false);
  // Seeding Default Knowledge Bases: Serviços, Saúde, Financeira
  useEffect(() => {
    if (!user || !isKnowledgeBasesLoaded || hasSeededRef.current) return;
    hasSeededRef.current = true;

    const defaultBases = [
      { nome: 'Serviços', emoji: '💼', cor: '#3b82f6', descricao: 'Base integrada com todos os serviços e portfólio' },
      { nome: 'Saúde', emoji: '❤️', cor: '#ef4444', descricao: 'Base integrada com exames, peso e dados de saúde' },
      { nome: 'Financeira', emoji: '💰', cor: '#10b981', descricao: 'Base integrada com transações, contas fixas e planejamento financeiro' }
    ];

    defaultBases.forEach(async (dbase) => {
      const exists = knowledgeBases.some(b => b.nome.toLowerCase() === dbase.nome.toLowerCase());
      if (!exists) {
        try {
          await addDoc(collection(db, 'knowledge_bases'), {
            nome: dbase.nome,
            descricao: dbase.descricao,
            cor: dbase.cor,
            emoji: dbase.emoji,
            data_criacao: new Date().toISOString(),
            data_atualizacao: new Date().toISOString(),
            configuracao_rag: {
              incluir_diarios: true,
              incluir_manual: true,
              categorias_vinculadas: [],
              tags_vinculadas: [],
            },
          });
          console.log(`Base padrão criada: ${dbase.nome}`);
        } catch (e) {
          console.error(`Erro ao criar base padrão ${dbase.nome}:`, e);
        }
      }
    });
  }, [isKnowledgeBasesLoaded, knowledgeBases, user]);

  // Finance Processing Logic (The Listener)
  useEffect(() => {
    const processFinanceTasks = async () => {
      // Monitora TODAS as tarefas de Gasto Semanal (ativas ou concluídas) para garantir sincronia
      const financeTasks = tarefas.filter(t =>
        t.status !== 'excluído' as any &&
        t.titulo.toLowerCase().includes('gasto semanal') &&
        t.notas && /Tag:\s*GASTO\s*SEMANAL/i.test(t.notas)
      );
      let syncedLaunches = 0;
      let syncedMovement = 0;
      for (const task of financeTasks) {
        const valueMatch = task.notas?.match(/Valor:\s*R\$\s*([\d\.,]+)/i);
        if (valueMatch) {
          try {
            // Normaliza valor (formato BR: 1.000,00 -> 1000.00)
            const amountStr = valueMatch[1].replace(/\./g, '').replace(',', '.');
            const amount = parseFloat(amountStr);
            if (isNaN(amount)) continue;
            // Recalcula dados (Data, Sprint)
            const dateMatch = task.titulo.match(/(\d{2}\/\d{2}\/\d{4})/);
            let transactionDate = new Date().toISOString();
            if (dateMatch) {
              const [d, m, y] = dateMatch[1].split('/').map(Number);
              transactionDate = new Date(y, m - 1, d).toISOString();
            }
            const day = new Date(transactionDate).getDate();
            // Lógica original de sprint: < 8, < 15, < 22, resto (4)
            const sprintOriginal = day < 8 ? 1 : day < 15 ? 2 : day < 22 ? 3 : 4;
            // Busca por ID original ou por período (título idêntico para Gasto Semanal)
            // Isso garante que se uma tarefa for apagada e recriada, ela atualize a transação existente em vez de duplicar
            const existingTransaction = financeTransactions.find(ft =>
              ft.originalTaskId === task.id ||
              (ft.category === 'Gasto Semanal' && ft.description.toLowerCase() === task.titulo.toLowerCase())
            );
            if (existingTransaction) {
              // UPDATE: Se já existe, verifica se houve mudança significativa
              const hasChanged = existingTransaction.amount !== amount ||
                existingTransaction.date !== transactionDate ||
                existingTransaction.originalTaskId !== task.id;
              const hasMovementChange = existingTransaction.amount !== amount ||
                existingTransaction.date !== transactionDate;
              if (hasChanged) {
                await updateDoc(doc(db, 'finance_transactions', existingTransaction.id), {
                  amount,
                  date: transactionDate,
                  sprint: sprintOriginal,
                  description: task.titulo,
                  originalTaskId: task.id // Atualiza o vínculo para a tarefa mais recente
                });
                if (hasMovementChange) {
                  syncedLaunches += 1;
                  syncedMovement += amount;
                }
              }
            } else {
              // CREATE: Se não existe transação para este período/tarefa, cria uma nova
              await addDoc(collection(db, 'finance_transactions'), {
                description: task.titulo,
                amount,
                date: transactionDate,
                sprint: sprintOriginal,
                category: 'Gasto Semanal',
                originalTaskId: task.id
              });
              syncedLaunches += 1;
              syncedMovement += amount;
              // Marca como concluída apenas se ainda não estiver
              if (normalizeStatus(task.status) !== 'concluido') {
                await updateDoc(doc(db, 'tarefas', task.id), {
                  status: 'concluído',
                  data_conclusao: formatDateLocalISO(new Date())
                });
              }
            }
          } catch (error) {
            console.error("Erro ao processar tarefa financeira:", error);
          }
        }
      }
      if (syncedLaunches === 1) {
        showToast(`Lançamento sincronizado: R$ ${syncedMovement.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`, 'success');
      } else if (syncedLaunches > 1) {
        showToast(
          `${syncedLaunches} lançamentos sincronizados. Movimentação total: R$ ${syncedMovement.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`,
          'info'
        );
      }
    };
    if (tarefas.length > 0) {
      processFinanceTasks();
    }
  }, [tarefas, financeTransactions]); // Adicionado financeTransactions para garantir consistência
  // Auto-generate Fixed Bills from Rubrics
  useEffect(() => {
    if (billRubrics.length === 0) return;
    const missingBills: any[] = [];
    billRubrics.forEach(rubric => {
      const exists = fixedBills.some(b =>
        b.rubricId === rubric.id &&
        b.month === currentMonth &&
        b.year === currentYear
      );
      if (!exists) {
        missingBills.push({
          description: rubric.description,
          amount: rubric.defaultAmount || 0,
          dueDay: rubric.dueDay,
          month: currentMonth,
          year: currentYear,
          category: rubric.category,
          isPaid: false,
          rubricId: rubric.id
        });
      }
    });
    if (missingBills.length > 0) {
      const batch = writeBatch(db);
      missingBills.forEach(bill => {
        const ref = doc(collection(db, 'fixed_bills'));
        batch.set(ref, bill);
      });
      batch.commit().then(() => {
        showToast(`${missingBills.length} contas fixas geradas para este mês.`, 'info');
      }).catch(err => console.error("Erro ao gerar contas fixas:", err));
    }
  }, [billRubrics, fixedBills, currentMonth, currentYear]);
  // --- Service Installments Synchronization to Finance ---
  useEffect(() => {
    if (!services) return;
    const syncServicesToIncome = async () => {
      // 1. Parcelas that SHOULD exist (Active/Completed services)
      const activeOrCompleted = services.filter(s => s.status === 'Ativo' || s.status === 'Concluído');
      const expectedIncomes: Partial<IncomeEntry>[] = [];
      activeOrCompleted.forEach(service => {
        (service.parcelas || []).forEach(p => {
          const date = new Date(p.data_prevista);
          expectedIncomes.push({
            parcela_id: p.id,
            service_id: service.id,
            description: `${service.titulo} - ${p.descricao}`,
            amount: p.valor,
            day: date.getDate(),
            month: date.getMonth(), // Use 0-11 as per currentMonth state
            year: date.getFullYear(),
            category: service.categoria_financeira || 'Serviço Particular',
            isReceived: p.status === 'pago',
            status: 'active'
          });
        });
      });
      // 2. Diff and Update
      const batch = writeBatch(db);
      let changes = 0;
      // Create or Update
      for (const expected of expectedIncomes) {
        const existing = incomeEntries.find(ie => ie.parcela_id === expected.parcela_id);
        if (!existing) {
          const newRef = doc(collection(db, 'income_entries'));
          batch.set(newRef, {
            ...expected,
            data_criacao: new Date().toISOString()
          });
          changes++;
        } else {
          const hasChanged =
            existing.amount !== expected.amount ||
            existing.description !== expected.description ||
            existing.day !== expected.day ||
            existing.month !== expected.month ||
            existing.year !== expected.year ||
            existing.category !== expected.category ||
            existing.isReceived !== expected.isReceived ||
            existing.status !== 'active';
          if (hasChanged) {
            batch.update(doc(db, 'income_entries', existing.id), expected);
            changes++;
          }
        }
      }
      // Delete (Software delete) if parcela is gone or service no longer eligible
      const linkedIncomes = incomeEntries.filter(ie => ie.parcela_id && ie.service_id);
      for (const linked of linkedIncomes) {
        const stillExists = expectedIncomes.some(e => e.parcela_id === linked.parcela_id);
        if (!stillExists && linked.status !== 'deleted') {
          batch.update(doc(db, 'income_entries', linked.id), { status: 'deleted' });
          changes++;
        }
      }
      if (changes > 0) {
        await batch.commit();
        console.log(`[Finance Sync] ${changes} changes synchronized from services.`);
      }
    };
    const timer = setTimeout(() => {
      syncServicesToIncome();
    }, 1000); // Debounce to avoid slamming Firestore
    return () => clearTimeout(timer);
  }, [services, incomeEntries, db]);
  const showToast = (message: string, type: 'success' | 'error' | 'info' | 'warning' = 'success', action?: { label: string | React.ReactNode, onClick: () => void }, actions?: { label: string | React.ReactNode, onClick: () => void }[]) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => {
      const hasInteractiveAction = Boolean(action || (actions && actions.length > 0));
      if (!hasInteractiveAction && prev.some(t => t.message === message)) return prev;
      if (prev.length > 0 && !hasInteractiveAction) {
        const last = prev[prev.length - 1];
        const lastPrefix = last.message.split(' ')[0];
        const newPrefix = message.split(' ')[0];
        if (lastPrefix === newPrefix && last.type === type && message.length > 10) {
          return [...prev.slice(0, -1), { id, message, type, action, actions }];
        }
      }
      const base = prev.length >= 2 ? prev.slice(1) : prev;
      return [...base, { id, message, type, action, actions }];
    });
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, action || (actions && actions.length > 0) ? 8000 : 5000);
  };
  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };
  const handleExportModule = () => {
    let md = '';
    let filename = 'hermes_export';
    if (viewMode === 'services') {
      const serviceData = services.map(p => ({
        'Nome': p.titulo,
        'Descrição': p.descricao || '-',
        'Cliente': p.cliente,
        'Status': p.status,
        'Valor Total': `R$ ${p.valor_total.toLocaleString('pt-BR')}`,
        'Data Criação': new Date(p.data_criacao).toLocaleDateString()
      }));
      md = generateMarkdown(
        'Módulo de Serviços',
        'Listagem detalhada de todos os serviços cadastrados no sistema.',
        {
          'Nome': 'Nome do serviço',
          'Descrição': 'Escopo do serviço',
          'Cliente': 'Cliente ou Instituição',
          'Status': 'Situação atual',
          'Valor Total': 'Valor total contratado',
          'Data Criação': 'Data de registro'
        },
        [{ title: 'Serviços Detalhados', data: serviceData }]
      );
      filename = 'hermes_servicos';
    } else if (viewMode === 'finance') {
      md = generateMarkdown(
        'Módulo Financeiro',
        'Transações, Metas e Obrigações.',
        { 'Data': 'Data da transação', 'Valor': 'Montante em BRL', 'Descrição': 'Detalhes' },
        [
          { title: 'Transações Recentes', data: financeTransactions.map(t => ({ Data: new Date(t.date).toLocaleDateString(), Descrição: t.description, Valor: t.amount })) },
          { title: 'Contas Fixas', data: fixedBills.filter(b => b.month === currentMonth && b.year === currentYear).map(b => ({ Descrição: b.description, Valor: b.amount, Status: b.isPaid ? 'Pago' : 'Pendente' })) }
        ]
      );
      filename = 'hermes_financeiro';
    } else if (viewMode === 'saude') {
      md = generateMarkdown(
        'Módulo de Saúde',
        'Registros de peso e hábitos.',
        { 'Data': 'Data do registro', 'Peso': 'Peso em kg' },
        [{ title: 'Histórico de Peso', data: healthWeights.map(w => ({ Data: new Date(w.date).toLocaleDateString(), Peso: w.weight })) }]
      );
      filename = 'hermes_saude';
    } else if (viewMode === 'gallery') {
      md = generateActionsMarkdown(tarefas.filter(t => t.status !== 'excluído' as any));
      filename = 'hermes_acoes';
    }
    if (md) downloadMarkdown(filename, md);
    else showToast('Exportação não disponível para esta visão.', 'info');
  };
  const handleCreateProject = async (name: string, desc: string) => {
    try {
      await addDoc(collection(db, 'projetos'), {
        nome: name,
        descricao: desc,
        data_criacao: new Date().toISOString()
      });
      setIsCreateModalOpen(false);
      showToast("Projeto criado com sucesso!", "success");
    } catch (error) {
      console.error("Error creating project:", error);
      showToast("Erro ao criar projeto.", "error");
    }
  };
  const handleCreateService = async (service: Omit<Servico, 'id' | 'data_criacao' | 'data_atualizacao'>) => {
    try {
      const now = new Date().toISOString();
      await addDoc(collection(db, 'servicos'), { ...service, data_criacao: now, data_atualizacao: now });
      showToast("Serviço criado com sucesso!", "success");
    } catch (error) {
      console.error("Error creating service:", error);
      showToast("Erro ao criar serviço.", "error");
    }
  };
  const handleUpdateService = async (id: string, service: Partial<Servico>) => {
    try {
      await updateDoc(doc(db, 'servicos', id), { ...service, data_atualizacao: new Date().toISOString() });
      showToast("Serviço atualizado!", "success");
    } catch (error) {
      console.error("Error updating service:", error);
      showToast("Erro ao atualizar serviço.", "error");
    }
  };
  const handleDeleteService = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'servicos', id));
      showToast("Serviço removido.", "success");
    } catch (error) {
      console.error("Error deleting service:", error);
      showToast("Erro ao remover serviço.", "error");
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
        finalNotes = finalNotes.replace(/Tag:\s*(CLC|ASSISTÃŠNCIA|GERAL|NÃO CLASSIFICADA)/gi, '').trim();
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
  // Dashboard states
  const [dashboardViewMode, setDashboardViewMode] = useState<'list' | 'calendar'>('list');
  const [groupByDate, setGroupByDate] = useState<boolean>(() => {
    const saved = localStorage.getItem('hermes-group-by-date');
    return saved !== 'false';
  });
  useEffect(() => {
    localStorage.setItem('hermes-group-by-date', String(groupByDate));
  }, [groupByDate]);
  const [calendarViewMode, setCalendarViewMode] = useState<'month' | 'week' | 'day'>('month');
  const [calendarDate, setCalendarDate] = useState(new Date());
  const [loading, setLoading] = useState<boolean>(false);
  const [isInitialDataLoading, setIsInitialDataLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [completedLimit, setCompletedLimit] = useState(10);
  const [activeModule, setActiveModule] = useState<'home' | 'dashboard' | 'acoes' | 'financeiro' | 'saude' | 'servicos' | 'estrategia'>('dashboard');
  const [viewMode, setViewMode] = useState<'dashboard' | 'gallery' | 'pgc' | 'licitacoes' | 'assistencia' | 'finance' | 'saude' | 'ferramentas' | 'knowledge' | 'services' | 'rag-bases' | 'concluidas' | 'strategy' | 'godmode'>('dashboard');
  const [selectedTask, setSelectedTask] = useState<Tarefa | null>(null);
  const [isSidebarRetracted, setIsSidebarRetracted] = useState(false);
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem('hermes-theme-mode');
    if (saved === 'dark' || saved === 'light' || saved === 'system') return saved;
    return 'system';
  });
  const [prefersDark, setPrefersDark] = useState(false);
  const [financeActiveTab, setFinanceActiveTab] = useState<'dashboard' | 'income' | 'expense'>('dashboard');
  const [isFinanceSettingsOpen, setIsFinanceSettingsOpen] = useState(false);
  // Modal Mode State
  const [taskModalMode, setTaskModalMode] = useState<'default' | 'edit' | 'execute'>('default');
  // Reset modal mode when selected task is cleared
  useEffect(() => {
    if (!selectedTask) {
      setTaskModalMode('default');
    }
  }, [selectedTask]);
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const syncPreference = (event?: MediaQueryList | MediaQueryListEvent) => {
      setPrefersDark(event ? event.matches : media.matches);
    };
    syncPreference();
    media.addEventListener('change', syncPreference);
    return () => media.removeEventListener('change', syncPreference);
  }, []);
  useEffect(() => {
    localStorage.setItem('hermes-theme-mode', themeMode);
    const shouldUseDark = themeMode === 'dark' || (themeMode === 'system' && prefersDark);
    document.documentElement.classList.toggle('dark', shouldUseDark);
  }, [themeMode, prefersDark]);
  // Sync selectedTask with updated data from Firestore to ensure components have latest data
  useEffect(() => {
    if (selectedTask) {
      const updated = tarefas.find(t => t.id === selectedTask.id);
      if (updated && JSON.stringify(updated) !== JSON.stringify(selectedTask)) {
        setSelectedTask(updated);
      }
    }
  }, [tarefas, selectedTask]);
  const [planosTrabalho, setPlanosTrabalho] = useState<PlanoTrabalho[]>([]);
  const [statusFilter, setStatusFilter] = useState<Status[]>(['em andamento', 'stand-by', 'cgby' as any]);
  const [areaFilter, setAreaFilter] = useState<string[]>([]);
  const [sortOption, setSortOption] = useState<SortOption>('date-asc');
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [notifications, setNotifications] = useState<HermesNotification[]>([]);
  const [isNotificationCenterOpen, setIsNotificationCenterOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [syncData, setSyncData] = useState<any>(null);
  const [activePopup, setActivePopup] = useState<HermesNotification | null>(null);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [exams, setExams] = useState<HealthExam[]>([]);
  const [lastBackPress, setLastBackPress] = useState(0);
  // Escuta o redirecionamento do Share Target (Android Share Intent PWA).
  // Os itens compartilhados ficam persistidos no IndexedDB 'hermes-share-db' e são
  // drenados pelo próprio BatchTranscriptionTool, permitindo acumular vários
  // compartilhamentos (áudio/vídeo/texto) antes de processar o lote.
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('sharedIntent') === 'true') {
      setActiveModule('acoes');
      setViewMode('ferramentas');
      setActiveFerramenta('batch_transcription');
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);
  // Escuta abertura de tarefa via URL (?task=ID)
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const taskId = urlParams.get('task');
    if (taskId) {
      const loadTask = async () => {
        // Tenta achar na lista local primeiro
        const local = tarefas.find(t => t.id === taskId);
        if (local) {
          setSelectedTask(local);
          setTaskModalMode('execute');
        } else {
          // Busca no Firestore
          try {
            const snap = await getDoc(doc(db, 'tarefas', taskId));
            if (snap.exists()) {
              const data = snap.data();
              setSelectedTask({
                id: snap.id,
                ...data,
                area_tematica: data.area_tematica || data.categoria,
                data_limite: data.data_limite || data.data_inicio || '',
                data_inicio: data.data_limite || data.data_inicio || '',
              } as Tarefa);
              setTaskModalMode('execute');
            }
          } catch (err) {
            console.error("Erro ao carregar tarefa da URL:", err);
          }
        }
        // Limpa a URL sem dar reload para não reabrir ao atualizar
        window.history.replaceState({}, document.title, window.location.pathname);
      };
      // Se tarefas já carregou, executa. Se não, espera um pouco para garantir que o onSnapshot rodou.
      if (tarefas.length > 0) {
        loadTask();
      } else {
        const timer = setTimeout(loadTask, 2000);
        return () => clearTimeout(timer);
      }
    }
  }, [tarefas.length > 0]);
  const handleDashboardNavigate = (view: 'gallery' | 'finance' | 'saude') => {
    setViewMode(view);
    if (view === 'gallery') setActiveModule('acoes');
    else if (view === 'finance') setActiveModule('financeiro');
    else if (view === 'saude') setActiveModule('saude');
  };
  // Sync state changes with history to enable back button
  useEffect(() => {
    // Only push if we are NOT at dashboard (root)
    if (activeModule !== 'dashboard' || viewMode !== 'dashboard' || activeFerramenta) {
      window.history.pushState({ activeModule, viewMode, activeFerramenta }, "", window.location.pathname);
    }
  }, [activeModule, viewMode, activeFerramenta]);
  // Handle hardware/browser back button
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      if (isPgdTerminalOpen) {
        setIsPgdTerminalOpen(false);
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
        // Maintain the history entry to wait for second press
        window.history.pushState(null, "", window.location.pathname);
      }
    };
    // Initial dummy state to capture back press
    if (window.history.state === null) {
      window.history.pushState({}, "", window.location.pathname);
    }
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [activeModule, viewMode, isPgdTerminalOpen, activeFerramenta, lastBackPress]);
  useEffect(() => {
    let eventSource: EventSource | null = null;
    if (isPgdTerminalOpen) {
      eventSource = new EventSource('http://127.0.0.1:8000/api/automations/logs');
      eventSource.onmessage = (e) => {
        setPgdTerminalLogs((prev) => [...prev, e.data]);
      };
      eventSource.onerror = () => {
        // Ignora erros para reconectar suavemente
      };
    }
    return () => {
      if (eventSource) eventSource.close();
    };
  }, [isPgdTerminalOpen]);
  const handleCreatePgdPlan = async (payload: CreatePgdPlanPayload) => {
    const response = await fetch('http://127.0.0.1:8000/api/automations/criar-plano-pgd', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      let message = 'O servidor local não conseguiu iniciar a criação do plano.';
      try {
        const errorData = await response.json();
        if (errorData?.detail) message = String(errorData.detail);
      } catch {
        // Mantém a mensagem padrão quando a resposta não for JSON.
      }
      throw new Error(message);
    }
    setPgdTerminalLogs([]);
    setIsPgdTerminalOpen(true);
    setIsCreatePgdPlanOpen(false);
    showToast('Automação iniciada. Conclua o login no Petrvs, se solicitado.', 'success');
  };
  const [appSettings, setAppSettings] = useState<AppSettings>(DEFAULT_APP_SETTINGS);
  const [settingsTab, setSettingsTab] = useState<'notifications' | 'context'>('notifications');
  // --- HermesNotification System & App Settings ---
  const emitNotification = async (title: string, message: string, type: 'info' | 'warning' | 'success' | 'error' = 'info', link?: string, id?: string) => {
    const newNotif: HermesNotification = {
      id: id || Math.random().toString(36).substr(2, 9),
      title,
      message,
      type,
      timestamp: new Date().toISOString(),
      isRead: false,
      link: link || ""
    };
    // Notificações agora são exclusivas do Telegram, salvamos no Firestore para disparar o webhook
    try {
      if (!user) return;
      const firestoreData = { ...JSON.parse(JSON.stringify(newNotif)), uid: user.uid };
      await setDoc(doc(db, 'notificacoes', newNotif.id), firestoreData);
    } catch (err) {
      console.error("Erro ao persistir notificação:", err);
      showToast(`Erro no sistema de notificação: ${err}`, "error");
    }
  };
  useEffect(() => {
    if (!user) return;
    const unsub = onSnapshot(doc(db, 'configuracoes', 'geral'), (snap) => {
      if (snap.exists()) {
        setAppSettings(snap.data() as AppSettings);
      }
    }, handleSnapshotError('configuracoes/geral'));
    return () => unsub();
  }, [user]);
  const handleUpdateAppSettings = async (newSettings: AppSettings) => {
    try {
      await setDoc(doc(db, 'configuracoes', 'geral'), newSettings);
      showToast("Configurações atualizadas!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao salvar configurações.", "error");
    }
  };
  const handleUpdateOverdueTasks = async (notificationId?: string) => {
    const todayStr = formatDateLocalISO(new Date());
    const overdue = tarefas.filter(t =>
      normalizeStatus(t.status) !== 'concluido' &&
      t.status !== 'excluído' as any &&
      !isStandbyStatus(t.status) &&
      t.data_limite && t.data_limite !== "-" && t.data_limite !== "0000-00-00" &&
      t.data_limite < todayStr
    );
    if (overdue.length === 0) {
      showToast("Nenhuma ação atrasada encontrada.", 'info');
      if (notificationId) handleDismissNotification(notificationId);
      return;
    }
    try {
      const batch = writeBatch(db);
      overdue.forEach(t => {
        batch.update(doc(db, 'tarefas', t.id), {
          data_limite: todayStr,
          data_inicio: todayStr,
          horario_inicio: null,
          horario_fim: null,
          data_atualizacao: new Date().toISOString()
        });
      });
      await batch.commit();
      showToast(`${overdue.length} ações atualizadas para hoje!`, 'success');
      if (notificationId) {
        handleDismissNotification(notificationId);
      } else {
        const targetNotif = notifications.find(n => n.title === "Ações Vencidas");
        if (targetNotif) handleDismissNotification(targetNotif.id);
      }
    } catch (err) {
      console.error("Erro ao atualizar tarefas:", err);
      showToast("Erro ao atualizar tarefas.", 'error');
    }
  };
  const handleUpdateToToday = async (task: Tarefa) => {
    const todayStr = formatDateLocalISO(new Date());
    try {
      await handleUpdateTarefa(task.id, {
        data_limite: todayStr,
        data_inicio: todayStr,
        horario_inicio: null as any,
        horario_fim: null as any
      }, true);
      showToast("Ação atualizada para hoje!", 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar ação.", 'error');
    }
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
      case '@SipacTrackingTool':
        setActiveModule('acoes');
        setViewMode('ferramentas');
        setActiveFerramenta('sipac_tracking');
        break;
      default:
        break;
    }
  };
  // HermesNotification System Triggers (Time-based: Weigh-in, Task Reminders)
  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date();
      const current_time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      const todayStr = formatDateLocalISO(now);
      // 1. Weigh-in Reminder (Bell HermesNotification)
      if (appSettings.notifications.weighInReminder.enabled) {
        const lastWeighInRemind = localStorage.getItem('lastWeighInRemindDate');
        if (lastWeighInRemind !== todayStr && current_time >= appSettings.notifications.weighInReminder.time) {
          const dayMatch = now.getDay() === appSettings.notifications.weighInReminder.dayOfWeek;
          let shouldRemind = false;
          if (appSettings.notifications.weighInReminder.frequency === 'weekly' && dayMatch) {
            shouldRemind = true;
          } else if (appSettings.notifications.weighInReminder.frequency === 'biweekly') {
            const weekRef = Math.floor(now.getTime() / (7 * 24 * 60 * 60 * 1000));
            if (dayMatch && weekRef % 2 === 0) shouldRemind = true;
          } else if (appSettings.notifications.weighInReminder.frequency === 'monthly' && now.getDate() === 1) {
            shouldRemind = true;
          }
          if (shouldRemind) {
            emitNotification(
              "Lembrete de Pesagem",
              "Hora de registrar seu peso para acompanhar sua evolução no módulo Saúde!",
              'info',
              'saude',
              `weigh_in_${todayStr}`
            );
            localStorage.setItem('lastWeighInRemindDate', todayStr);
          }
        }
      }
      // 2. Task Reminders (Scheduled via TaskExecutionView)
      // Delegated to backend Cloud Function to prevent duplicate triggering
      // and ensure execution when frontend is offline.
      // 3. Daily Task Notifications (Legacy / Overdue)
      const currentTimeInMinutes = now.getHours() * 60 + now.getMinutes();
      tarefas.forEach(t => {
        if (t.status === 'concluído' || t.data_limite !== todayStr) return;
        if (t.horario_inicio) {
          const [h, m] = t.horario_inicio.split(':').map(Number);
          const startMin = h * 60 + m;
          const diff = startMin - currentTimeInMinutes;
          const lastReminded = localStorage.getItem(`lastStartRemind_${t.id}`);
          if (diff === 15 && lastReminded !== todayStr) {
            const msg = `Sua tarefa "${t.titulo}" inicia em 15 minutos!`;
            emitNotification("Hermes: Próxima Tarefa", msg, 'info', '', `task_start_${t.id}_${todayStr}`);
            localStorage.setItem(`lastStartRemind_${t.id}`, todayStr);
          }
        }
        if (t.horario_fim) {
          const [h, m] = t.horario_fim.split(':').map(Number);
          const endMin = h * 60 + m;
          const diff = endMin - currentTimeInMinutes;
          const lastReminded = localStorage.getItem(`lastEndRemind_${t.id}`);
          if (diff === 15 && lastReminded !== todayStr) {
            const msg = `Sua tarefa "${t.titulo}" encerra em 15 minutos!`;
            emitNotification("Hermes: Encerramento de Tarefa", msg, 'info', '', `task_end_${t.id}_${todayStr}`);
            localStorage.setItem(`lastEndRemind_${t.id}`, todayStr);
          }
        }
      });
      // 4. Custom Notifications
      const customNotifs = appSettings.notifications.custom || [];
      customNotifs.forEach((notif: CustomNotification) => {
        if (!notif.enabled) return;
        if (notif.time === current_time) {
          const NOTIF_KEY = `lastCustomNotif_${notif.id}`;
          const lastSent = localStorage.getItem(NOTIF_KEY);
          if (lastSent === todayStr) return;
          let shouldSend = false;
          if (notif.frequency === 'daily') {
            shouldSend = true;
          } else if (notif.frequency === 'weekly') {
            const dayOfWeek = now.getDay(); // 0-6
            if (notif.daysOfWeek && notif.daysOfWeek.includes(dayOfWeek)) {
              shouldSend = true;
            }
          } else if (notif.frequency === 'monthly') {
            const dayOfMonth = now.getDate();
            if (dayOfMonth === notif.dayOfMonth) {
              shouldSend = true;
            }
          }
          if (shouldSend) {
            emitNotification("Lembrete Personalizado", notif.message, 'info', '', `custom_${notif.id}_${todayStr}`);
            localStorage.setItem(NOTIF_KEY, todayStr);
          }
        }
      });
    }, 10000); // Check every 10 seconds to ensure we don't miss the minute
    return () => clearInterval(interval);
  }, [appSettings.notifications, tarefas]);
  // Data-driven Notifications (Budget, Overdue, PGC)
  useEffect(() => {
    const todayStr = formatDateLocalISO(new Date());
    // 2. Budget Risk (Whenever data changes, throttled to once per day notification AND real spending increase)
    if (appSettings.notifications.budgetRisk.enabled) {
      const now = new Date();
      const currentMonthStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
      const monthlyBudget = financeSettings.monthlyBudgets?.[currentMonthStr] || financeSettings.monthlyBudget;
      const totalSpend = financeTransactions.filter(t => {
        const d = new Date(t.date);
        return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
      }).reduce((acc, t) => acc + t.amount, 0);
      if (monthlyBudget > 0) {
        const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
        const currentDay = now.getDate();
        const budgetRatio = totalSpend / monthlyBudget;
        const timeRatio = currentDay / daysInMonth;
        // Condition: Over budget velocity AND (New day OR spending increased since last notification)
        const lastNotifiedSpend = parseFloat(localStorage.getItem(`lastBudgetRiskNotifiedSpend_${currentMonthStr}`) || '0');
        const isNewDay = localStorage.getItem('lastBudgetRiskNotifyDate') !== todayStr;
        const hasSpendIncreased = totalSpend > lastNotifiedSpend;
        if (budgetRatio > timeRatio * 1.15 && budgetRatio > 0.1 && hasSpendIncreased && isNewDay) {
          const saldoDisponivel = monthlyBudget - totalSpend;
          emitNotification(
            "Alerta de Orçamento",
            `Você já utilizou ${(budgetRatio * 100).toFixed(0)}% do orçamento em ${(timeRatio * 100).toFixed(0)}% do mês.\nSaldo disponível atual R$ ${saldoDisponivel.toFixed(2)}`,
            'warning',
            'financeiro',
            `budget-${todayStr}`
          );
          localStorage.setItem('lastBudgetRiskNotifyDate', todayStr);
          localStorage.setItem(`lastBudgetRiskNotifiedSpend_${currentMonthStr}`, totalSpend.toString());
        }
      }
    }
    // 3. Audit PGC
    if (appSettings.notifications.pgcAudit.enabled && localStorage.getItem('lastPgcNotifyDate') !== todayStr) {
      const now = new Date();
      const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
      if ((daysInMonth - now.getDate()) <= appSettings.notifications.pgcAudit.daysBeforeEnd) {
        emitNotification(
          "Auditoria PGD",
          "O mês está acabando. Verifique no módulo PGD se todas as entregas possuem ações vinculadas.",
          'info',
          'pgc',
          `pgc-${todayStr}`
        );
        localStorage.setItem('lastPgcNotifyDate', todayStr);
      }
    }
  }, [tarefas, financeTransactions, financeSettings, planosTrabalho, appSettings.notifications]);
  // Welcome HermesNotification
  useEffect(() => {
    if (!user) return;
    const hasSeenWelcome = localStorage.getItem('hasSeenWelcome');
    if (!hasSeenWelcome && notifications.length === 0) {
      emitNotification(
        'Bem-vindo ao Hermes',
        'Sistema de notificações ativo. Configure suas preferências no ícone de engrenagem.',
        'info',
        undefined,
        'welcome'
      );
      localStorage.setItem('hasSeenWelcome', 'true');
    }
  }, [user]);
  // Sync Logic
  useEffect(() => {
    if (!user) return;
    const unsub = onSnapshot(doc(db, 'system', 'sync'), (snap) => {
      if (snap.exists()) {
        const data = snap.data();
        setSyncData(data);
        if (data.status === 'processing' || data.status === 'requested') setIsSyncing(true);
        if (data.status === 'completed' || data.status === 'error') setIsSyncing(false);
      }
    }, handleSnapshotError('system/sync'));
    return () => unsub();
  }, [user]);
  const handleSync = async () => {
    if (isSyncing) {
      setIsTerminalOpen(true);
      return;
    }
    setIsTerminalOpen(true);
    setIsSyncing(true);
    showToast("Iniciando Sincronização Profunda...", "info");
    // 1. Deep System Sync (requested via Bot)
    try {
      await setDoc(doc(db, 'system', 'sync'), {
        status: 'requested',
        timestamp: new Date().toISOString(),
        logs: ["Aguardando resposta do Bot..."]
      });
    } catch (e) {
      console.error(e);
      showToast("Erro ao solicitar sincronização profunda.", "error");
    }

    setIsSyncing(false);
  };
  const normalizeTaskTitle = (value?: string) => {
    if (typeof value !== 'string') return value;
    const compact = value.trim().replace(/\s+/g, ' ');
    if (!compact) return compact;
    const smallWords = new Set([
      'de', 'da', 'do', 'das', 'dos',
      'e', 'em', 'na', 'no', 'nas', 'nos',
      'a', 'o', 'as', 'os',
      'para', 'por', 'com'
    ]);
    const capitalizeToken = (token: string, isFirst: boolean) => {
      if (!token) return token;
      if (/^[A-Z0-9]{2,5}$/.test(token)) return token; // Preserve short acronyms (CLC, SEI, IFES, etc.)
      const lower = token.toLocaleLowerCase('pt-BR');
      if (!isFirst && smallWords.has(lower)) return lower;
      return lower.charAt(0).toLocaleUpperCase('pt-BR') + lower.slice(1);
    };
    return compact
      .split(' ')
      .map((word, wordIndex) => {
        const parts = word.split(/([/-])/);
        let pieceIndex = 0;
        return parts.map((part) => {
          if (part === '/' || part === '-') return part;
          const normalized = capitalizeToken(part, wordIndex === 0 && pieceIndex === 0);
          pieceIndex += 1;
          return normalized;
        }).join('');
      })
      .join(' ');
  };
  const handleUpdateTarefa = async (id: string, updates: Partial<Tarefa>, suppressToast = false) => {
    const previousTask = tarefas.find(t => t.id === id);
    try {
      const docRef = doc(db, 'tarefas', id);
      const now = new Date().toISOString();
      let payload: Record<string, any> = {
        ...updates,
        data_atualizacao: now
      };
      payload = applyStandbyDateRules(payload, previousTask);

      if (payload.pool_dados && Array.isArray(payload.pool_dados)) {
        payload.pool_dados = payload.pool_dados.map((item: any) => {
          if (!item.id || !item.data_criacao) {
            return {
              ...item,
              id: item.id || Math.random().toString(36).substring(2, 11),
              data_criacao: item.data_criacao || now
            };
          }
          return item;
        });
      }

      if (previousTask) {
        const dateChanged = (updates.data_limite && updates.data_limite !== previousTask.data_limite) ||
                            (updates.data_inicio && updates.data_inicio !== previousTask.data_inicio);
        const timeExplicitlyUpdated = (Object.prototype.hasOwnProperty.call(updates, 'horario_inicio') && updates.horario_inicio !== undefined) ||
                                      (Object.prototype.hasOwnProperty.call(updates, 'horario_fim') && updates.horario_fim !== undefined);
        if (dateChanged && !timeExplicitlyUpdated) {
          payload.horario_inicio = null;
          payload.horario_fim = null;
        }
      }
      if (Object.prototype.hasOwnProperty.call(payload, 'is_single_day')) {
        delete payload.is_single_day;
      }
      if (Object.prototype.hasOwnProperty.call(payload, 'titulo') && typeof payload.titulo === 'string') {
        payload.titulo = normalizeTaskTitle(payload.titulo);
      }
      const oldStatusNormalized = normalizeStatus(previousTask?.status || '');
      const newStatusNormalized = Object.prototype.hasOwnProperty.call(payload, 'status') ? normalizeStatus(String(payload.status)) : oldStatusNormalized;
      const statusChanged = Boolean(previousTask && Object.prototype.hasOwnProperty.call(payload, 'status') && newStatusNormalized !== oldStatusNormalized);
      if (statusChanged) {
        if (newStatusNormalized === 'concluido' && !Object.prototype.hasOwnProperty.call(payload, 'data_conclusao')) {
          payload.data_conclusao = now;
        }
        if (newStatusNormalized !== 'concluido' && oldStatusNormalized === 'concluido' && !Object.prototype.hasOwnProperty.call(payload, 'data_conclusao')) {
          payload.data_conclusao = null;
        }
      }
      // Cleanup payload for Firestore (remove undefined values)
      const cleanPayload = JSON.parse(JSON.stringify(payload));
      await updateDoc(docRef, cleanPayload);
      if (payload.pool_dados && payload.pool_dados.length > 0) {
        for (const item of payload.pool_dados) {
          const knowledgeItem: ConhecimentoItem = {
            id: item.id,
            titulo: item.nome || 'Sem título',
            tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
            url_drive: item.valor,
            tamanho: 0,
            data_criacao: item.data_criacao,
            origem: { modulo: 'tarefas', id_origem: id },
            categoria: 'Ações'
          };
          setDoc(doc(db, 'conhecimento', item.id), knowledgeItem).catch(console.error);
        }
      }
      if (statusChanged && previousTask) {
        pushToUndoStack(newStatusNormalized === 'concluido' ? 'Conclusão da ação' : 'Alteração de status', async () => {
          await updateDoc(doc(db, 'tarefas', id), {
            status: previousTask.status,
            data_conclusao: previousTask.data_conclusao || null,
            data_limite: previousTask.data_limite || '',
            data_inicio: previousTask.data_inicio || '',
            horario_inicio: previousTask.horario_inicio || null,
            horario_fim: previousTask.horario_fim || null,
            data_atualizacao: new Date().toISOString()
          });
        });
        if (!suppressToast) {
          if (newStatusNormalized === 'concluido') showToast('Tarefa concluída!', 'success', getUndoToastAction());
          else if (newStatusNormalized === 'stand-by') showToast('Ação movida para stand-by.', 'info', getUndoToastAction());
          else showToast('Tarefa reaberta!', 'success', getUndoToastAction());
        }
        return;
      }
      if (!suppressToast) showToast('Tarefa atualizada!', 'success');
    } catch (err) {
      console.error('Erro ao atualizar tarefa:', err);
      showToast('Erro ao salvar alterações.', 'error');
    }
  };

  const handleSynthesizeTaskDescription = async (task: Tarefa) => {
    if (descriptionSynthesisTaskId || isBatchDescriptionSynthesisRunning) return;
    if (!isBlankActionDescription(task.descricao) || !hasActionDescriptionContext(task)) {
      showToast('Esta ação não possui contexto suficiente para sintetizar.', 'info');
      return;
    }
    setDescriptionSynthesisTaskId(task.id);
    showToast('Gerando descrição executiva...', 'info');
    try {
      const fn = httpsCallable(functions, 'sintetizarDescricaoAcao', { timeout: 300000 });
      const result = await fn({ taskId: task.id });
      const data = result.data as any;
      if (data?.status === 'completed') {
        showToast('Descrição sintetizada com sucesso.', 'success');
      } else {
        showToast('A ação não atende mais aos critérios de síntese.', 'warning');
      }
    } catch (err: any) {
      console.error('Erro ao sintetizar descrição:', err);
      showToast(err?.message || 'Erro ao gerar descrição com IA.', 'error');
    } finally {
      setDescriptionSynthesisTaskId(null);
    }
  };

  const runBatchDescriptionSynthesis = async (limit: number) => {
    setIsBatchDescriptionSynthesisRunning(true);
    showToast('Síntese em lote iniciada...', 'info');
    try {
      const fn = httpsCallable(functions, 'sintetizarDescricaoAcao', { timeout: 300000 });
      const result = await fn({ batch: true, limit });
      const data = result.data as any;
      const processed = Number(data?.processed || 0);
      const failed = Array.isArray(data?.failed) ? data.failed.length : 0;
      const remaining = Number(data?.remainingEligible || 0);
      if (processed > 0) {
        showToast(`${processed} descrição(ões) sintetizada(s).${failed ? ` ${failed} falha(s).` : ''}${remaining ? ` ${remaining} restante(s).` : ''}`, failed ? 'warning' : 'success');
      } else if (failed > 0) {
        showToast('Nenhuma descrição foi sintetizada no lote.', 'error');
      } else {
        showToast('Nenhuma ação elegível foi encontrada.', 'info');
      }
    } catch (err: any) {
      console.error('Erro na síntese em lote:', err);
      showToast(err?.message || 'Erro ao sintetizar descrições em lote.', 'error');
    } finally {
      setIsBatchDescriptionSynthesisRunning(false);
    }
  };

  const handleBatchSynthesizeDescriptions = async () => {
    if (isBatchDescriptionSynthesisRunning || descriptionSynthesisTaskId) return;
    setIsBatchDescriptionSynthesisRunning(true);
    try {
      const fn = httpsCallable(functions, 'sintetizarDescricaoAcao', { timeout: 300000 });
      showToast('Verificando ações elegíveis...', 'info');
      const result = await fn({ dryRun: true, limit: 50 });
      const data = result.data as any;
      const eligibleCount = Number(data?.eligibleCount || 0);
      const limit = Math.min(Number(data?.limit || 50), eligibleCount);
      setIsBatchDescriptionSynthesisRunning(false);
      if (eligibleCount === 0) {
        showToast('Nenhuma ação com descrição vazia e contexto útil foi encontrada.', 'info');
        return;
      }
      showConfirm(
        'Sintetizar descrições vazias',
        `Foram identificadas ${eligibleCount} ações elegíveis no banco de dados. O processamento iniciará ${limit} ação(ões) agora e atualizará a tela via Firestore.`,
        () => { void runBatchDescriptionSynthesis(limit); },
        () => setIsBatchDescriptionSynthesisRunning(false)
      );
    } catch (err: any) {
      setIsBatchDescriptionSynthesisRunning(false);
      console.error('Erro ao contar ações elegíveis:', err);
      showToast(err?.message || 'Erro ao verificar ações elegíveis.', 'error');
    }
  };

  const handleReorderTasks = async (taskId: string, targetTaskId: string, label?: string) => {
    let currentLabel = label;
    if (!currentLabel) {
      // Encontra em qual bucket o target está
      for (const [l, ts] of Object.entries(tarefasAgrupadas)) {
        if (ts.some(t => t.id === targetTaskId)) {
          currentLabel = l;
          break;
        }
      }
    }
    if (!currentLabel) return;
    const tasksInBucket = [...(tarefasAgrupadas[currentLabel] || [])];
    if (tasksInBucket.length === 0) return;
    const oldIndex = tasksInBucket.findIndex(t => t.id === taskId);
    const newIndex = tasksInBucket.findIndex(t => t.id === targetTaskId);
    // Se estiver movendo dentro do mesmo bucket
    if (oldIndex !== -1) {
      if (oldIndex === newIndex) return;
      const [removed] = tasksInBucket.splice(oldIndex, 1);
      tasksInBucket.splice(newIndex, 0, removed);
    } else {
      // Movendo de outro bucket para este
      const draggedTask = tarefas.find(t => t.id === taskId);
      if (!draggedTask) return;
      const targetTask = tasksInBucket[newIndex];
      // Atualiza a data da tarefa arrastada para coincidir com o bucket de destino
      const newDate = targetTask.data_limite || formatDateLocalISO(new Date());
      await handleUpdateTarefa(taskId, {
        data_limite: newDate,
        data_inicio: newDate
      }, true);
      // Insere na posição correta para o remapeamento de ordem
      tasksInBucket.splice(newIndex, 0, { ...draggedTask, data_limite: newDate, data_inicio: newDate });
    }
    // Reatribui ordens
    const promises = tasksInBucket.map((t, i) => {
      if (t.ordem !== i) {
        return updateDoc(doc(db, 'tarefas', t.id), { ordem: i, data_atualizacao: new Date().toISOString() });
      }
      return null;
    }).filter(Boolean);
    if (promises.length > 0) {
      await Promise.all(promises);
      showToast("Ordem atualizada!", "success");
    }
  };
  const handleToggleTarefaStatus = async (id: string, currentStatus: string) => {
    const isConcluido = normalizeStatus(currentStatus) === 'concluido';
    const newStatus: Status = isConcluido ? 'em andamento' : 'concluído';
    await handleUpdateTarefa(id, { status: newStatus });
  };
  const handleDeleteTarefa = async (id: string) => {
    const tarefa = tarefas.find(t => t.id === id);
    if (!tarefa) return;
    try {
      setLoading(true);
      const docRef = doc(db, 'tarefas', id);
      // Marcamos como excluída para o push-tasks remover do Google
      await updateDoc(docRef, {
        status: 'excluído' as any,
        data_atualizacao: new Date().toISOString()
      });
      pushToUndoStack("Excluir Tarefa", async () => {
        await updateDoc(docRef, {
          status: tarefa.status,
          data_atualizacao: new Date().toISOString()
        });
      });
      showToast('Tarefa excluída!', 'success');
    } catch (err) {
      console.error("Erro ao excluir tarefa:", err);
      showToast("Erro ao excluir.", 'error');
    } finally {
      setLoading(false);
    }
  };
  const handleUpdateIdea = async (id: string, text: string) => {
    try {
      await updateDoc(doc(db, 'brainstorm_ideas', id), { text });
      showToast("Nota atualizada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar nota.", "error");
    }
  };
  const handleDeleteKnowledgeItem = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'conhecimento', id));
      showToast("Arquivo removido do repositório.", "info");
    } catch (e) {
      showToast("Erro ao remover arquivo.", "error");
    }
  };
  const resolveKnowledgeDestinationMetadata = (
    destinationFolderId?: string | null
  ): { parent_id: string | null; categoria?: string; origem?: ConhecimentoItem['origem'] } => {
    if (!destinationFolderId || destinationFolderId === 'biblioteca') return { parent_id: 'biblioteca' };
    if (destinationFolderId === ROOT_ACTIONS_FOLDER_ID) {
      return { parent_id: null as string | null, categoria: 'Ações' };
    }
    if (destinationFolderId === ROOT_HEALTH_FOLDER_ID) {
      return { parent_id: null as string | null, categoria: 'Saúde' };
    }
    if (destinationFolderId === ROOT_PROJECTS_FOLDER_ID) {
      return { parent_id: null as string | null, categoria: 'Projetos' };
    }
    const actionTaskId = getTaskIdFromActionFolderId(destinationFolderId);
    if (actionTaskId) {
      return {
        parent_id: null as string | null,
        categoria: 'Ações',
        origem: { modulo: 'tarefas', id_origem: actionTaskId }
      };
    }
    return { parent_id: destinationFolderId };
  };
  const handleUploadKnowledgeFile = async (file: File, destinationFolderId?: string | null): Promise<ConhecimentoItem | null> => {
    const item = await handleFileUploadToDrive(file);
    if (item) {
      const destinationMetadata = resolveKnowledgeDestinationMetadata(destinationFolderId);
      const knowledgeItem: ConhecimentoItem = {
        id: item.id,
        titulo: item.nome || 'Sem título',
        tipo_arquivo: (file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() : 'unknown') || 'unknown',
        url_drive: item.valor,
        tamanho: 0,
        data_criacao: item.data_criacao,
        origem: destinationMetadata.origem || null,
        parent_id: destinationMetadata.parent_id,
        ...(destinationMetadata.categoria ? { categoria: destinationMetadata.categoria } : {})
      };
      await setDoc(doc(db, 'conhecimento', item.id), knowledgeItem);
      showToast("Arquivo enviado e indexação iniciada.", "success");
      return knowledgeItem;
    }
    return null;
  };
  const handleProcessarIA = async (itemId: string) => {
    try {
      const processarIA = httpsCallable(functions, 'processarArquivoIA');
      showToast("Solicitando processamento Ã  IA...", "info");
      const result = await processarIA({ itemId });
      const data = result.data as any;
      if (data.success) {
        showToast("Arquivo processado com sucesso!", "success");
      } else {
        showToast("Erro ao processar: " + (data.error || "Erro desconhecido"), "error");
      }
    } catch (err) {
      console.error(err);
      showToast("Falha na comunicação com a IA.", "error");
    }
  };
  const handleAnalysePatterns = async (categoria: string) => {
    try {
      showToast(`Iniciando análise de padrões em ${categoria}...`, "info");
      const analyseFunc = httpsCallable(functions, 'analisarPadroesCategoriaIA');
      const response = await analyseFunc({ categoria });
      const data = response.data as any;
      if (data.success) {
        showToast("Análise concluída! Novos conhecimentos disponíveis no Manual.", "success");
      } else {
        showToast(`Aviso: ${data.message || 'Sem novos padrões detectados.'}`, "info");
      }
    } catch (error) {
      console.error("Erro ao analisar padrões:", error);
      showToast("Erro ao invocar Memória Mestra.", "error");
    }
  };
  const handleNavigateToOrigin = (modulo: string, id: string) => {
    switch (modulo) {
      case 'acoes':
      case 'tarefas':
        const task = tarefas.find(t => t.id === id);
        if (task) {
          const taskArea = normalizeAreaName(task.area_tematica);
          setSelectedTask(task);
          if (taskArea === 'CLC') setViewMode('licitacoes');
          else if (taskArea === 'ASSISTENCIA' || taskArea === 'ASSISTENCIA ESTUDANTIL') setViewMode('assistencia');
          else setViewMode('gallery');
          setActiveModule('acoes');
        } else {
          showToast("Ação não encontrada.", "error");
        }
        break;
      case 'saude':
        setViewMode('saude');
        setActiveModule('saude');
        break;
      case 'servicos':
        setViewMode('services');
        setActiveModule('servicos');
        break;
      case 'financeiro':
        setViewMode('finance');
        setActiveModule('financeiro');
        break;
      default:
        showToast("Módulo não mapeado para navegação.", "info");
    }
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
    setConvertingIdea(idea); // To delete after save
    setIsCreateModalOpen(true);
  };
  const handleCreateIndicadorAction = (objective: EstrategiaPessoal, indicator: EstrategiaIndicadorSucesso) => {
    const today = formatDateLocalISO(new Date());
    setConvertingIdea(null);
    setTaskInitialData({
      titulo: indicator.descricao ? `Acao: ${indicator.descricao}` : 'Acao de indicador estrategico',
      notas: `Objetivo estrategico: ${objective.objetivoMacro}\nIndicador continuo: ${indicator.descricao}`,
      descricao: `Registro qualitativo do indicador continuo "${indicator.descricao}" no objetivo "${objective.objetivoMacro}".`,
      data_inicio: today,
      data_limite: today,
      area_tematica: getAreaForStrategyPillar(objective.pilar),
      status: 'em andamento',
      tags: ['estrategia', 'indicador-continuo'],
      estrategia_objetivo_id: objective.id,
      estrategia_indicador_id: indicator.id,
    });
    setIsCreateModalOpen(true);
  };
  const handleShoppingAIConfirm = async (confirmedItems: ShoppingAIConfirmItem[]) => {
    try {
      const batch = writeBatch(db);
      let count = 0;
      confirmedItems.forEach(c => {
        const exists = c.id ? shoppingItems.find(i => i.id === c.id) : null;
        if (exists) {
          batch.update(doc(db, 'shopping_items', c.id!), { isPlanned: true, quantidade: c.quantidade, isPurchased: false });
          count++;
          return;
        }
        if (c.isNew && c.nome?.trim()) {
          const duplicate = shoppingItems.find(i => i.nome.trim().toLowerCase() === c.nome!.trim().toLowerCase());
          if (duplicate) {
            batch.update(doc(db, 'shopping_items', duplicate.id), { isPlanned: true, quantidade: c.quantidade, isPurchased: false });
          } else {
            const ref = doc(collection(db, 'shopping_items'));
            batch.set(ref, {
              nome: c.nome.trim(),
              categoria: c.categoria?.trim() || 'Geral',
              quantidade: c.quantidade || '1',
              unit: c.unit || 'un',
              isPlanned: true,
              isPurchased: false,
            });
          }
          count++;
        }
      });
      if (count > 0) {
        await batch.commit();
        showToast(`${count} iten${count !== 1 ? 's' : ''} adicionado${count !== 1 ? 's' : ''} ao planejamento!`, 'success', {
          label: 'Ver Lista',
          onClick: () => {
            setActiveModule('acoes');
            setViewMode('ferramentas');
            setActiveFerramenta('shopping');
          }
        });
      } else {
        showToast('Nenhum item atualizado.', 'info');
      }
    } catch (err) {
      console.error(err);
      showToast('Erro ao atualizar planejamento.', 'error');
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
  useEffect(() => {
    if (!user) {
      setExams([]);
      return;
    }
    const unsub = onSnapshot(collection(db, 'exames'), (snap) => {
      const data = snap.docs.map(d => ({ id: d.id, ...d.data() } as HealthExam));
      setExams(data);
    }, handleSnapshotError('exames'));
    return () => unsub();
  }, [user]);
  const handleArchiveIdea = async (id: string) => {
    try {
      const idea = brainstormIdeas.find(i => i.id === id);
      if (!idea) return;
      const newStatus = idea.status === 'archived' ? 'active' : 'archived';
      await updateDoc(doc(db, 'brainstorm_ideas', id), {
        status: newStatus
      });
      showToast(newStatus === 'archived' ? "Nota concluída e arquivada!" : "Nota restaurada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao processar nota.", "error");
    }
  };
  const handleAddTextIdea = async (text: string) => {
    try {
      await addDoc(collection(db, 'brainstorm_ideas'), {
        text,
        timestamp: new Date().toISOString(),
        status: 'active'
      });
      showToast("Nota registrada!", "success", undefined, [
        {
          // Ãcone de Copiar
          label: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3" /></svg>,
          onClick: () => {
            navigator.clipboard.writeText(text);
            showToast("Conteúdo copiado!", "info");
          }
        },
        {
          // Ãcone de Ir para Notas (Link Externo style)
          label: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>,
          onClick: () => {
            setActiveModule('acoes');
            setViewMode('ferramentas');
            setActiveFerramenta('brainstorming');
          }
        }
      ]);
    } catch (err) {
      console.error(err);
      showToast("Erro ao salvar nota.", "error");
    }
  };
  const handleUploadToRAGBase = async (file: File, baseId: string): Promise<void> => {
    const item = await handleFileUploadToDrive(file);
    if (item) {
      const knowledgeItem: ConhecimentoItem = {
        id: item.id,
        titulo: item.nome || 'Sem título',
        tipo_arquivo: (file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() : 'unknown') || 'unknown',
        url_drive: item.valor,
        tamanho: 0,
        data_criacao: item.data_criacao,
        origem: null,
        parent_id: null,
        base_id: baseId,
      };
      await setDoc(doc(db, 'conhecimento', item.id), knowledgeItem);
      showToast("Arquivo enviado â€” extraindo texto e vetorizandoâ€¦", "info");
      // Auto-vectorize: extract text and embed in background
      try {
        const base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve((reader.result as string).split(',')[1]);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });
        const fn = httpsCallable(functions, 'extractAndVectorizeRAGItem');
        const result = await fn({ fileBase64: base64, filename: file.name, mimeType: file.type, knowledgeId: item.id });
        const data = result.data as any;
        if (data.vectorized) {
          showToast("Arquivo indexado e vetorizado com sucesso!", "success");
        } else {
          showToast(data.message || "Texto extraído, mas vetorização falhou.", "error");
        }
      } catch (err: any) {
        showToast(err?.message || "Arquivo salvo no Drive. Vetorização automática falhou â€” tente manualmente.", "error");
      }
    }
  };
  const handleAddRAGBaseLink = async (url: string, title: string, baseId: string): Promise<void> => {
    try {
      await addDoc(collection(db, 'conhecimento'), {
        titulo: title,
        tipo_arquivo: 'link',
        url_drive: url,
        tamanho: 0,
        data_criacao: new Date().toISOString(),
        origem: null,
        parent_id: null,
        base_id: baseId,
      });
      showToast("Link salvo na base RAG.", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao salvar link.", "error");
    }
  };
  const handleAddKnowledgeLink = async (url: string, title: string, destinationFolderId?: string | null) => {
    try {
      const destinationMetadata = resolveKnowledgeDestinationMetadata(destinationFolderId);
      await addDoc(collection(db, 'conhecimento'), {
        titulo: title,
        tipo_arquivo: 'link',
        url_drive: url,
        tamanho: 0,
        data_criacao: new Date().toISOString(),
        origem: destinationMetadata.origem || null,
        parent_id: destinationMetadata.parent_id,
        ...(destinationMetadata.categoria ? { categoria: destinationMetadata.categoria } : {})
      });
      showToast("Link salvo com sucesso.", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao salvar link.", "error");
    }
  };
  const handleSaveKnowledgeItem = async (item: Partial<ConhecimentoItem>) => {
    try {
      const cleanItem = JSON.parse(JSON.stringify(item));
      if (item.id) {
        await setDoc(doc(db, 'conhecimento', item.id), cleanItem, { merge: true });
        showToast("Item salvo.", "success");
      } else {
        await addDoc(collection(db, 'conhecimento'), {
          ...cleanItem,
          data_criacao: new Date().toISOString()
        });
        showToast("Item salvo.", "success");
      }
    } catch (e) {
      console.error(e);
      showToast("Erro ao salvar item.", "error");
    }
  };
  const handleCreateBase = async (nome: string) => {
    try {
      await addDoc(collection(db, 'knowledge_bases'), {
        nome,
        descricao: '',
        cor: '',
        emoji: '',
        data_criacao: new Date().toISOString(),
        data_atualizacao: new Date().toISOString(),
        configuracao_rag: {
          incluir_diarios: true,
          incluir_manual: true,
          categorias_vinculadas: [],
          tags_vinculadas: [],
        },
      });
      showToast("Base de conhecimento criada!", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao criar base de conhecimento.", "error");
    }
  };
  const handleUpdateBase = async (id: string, updates: Partial<BaseConhecimento>) => {
    try {
      await updateDoc(doc(db, 'knowledge_bases', id), {
        ...updates,
        data_atualizacao: new Date().toISOString(),
      });
      showToast("Base de conhecimento atualizada!", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao atualizar base de conhecimento.", "error");
    }
  };
  const handleDeleteBase = async (id: string) => {
    showConfirm(
      "Confirmar Exclusão",
      "Deseja realmente remover esta base de conhecimento?",
      async () => {
        try {
          await deleteDoc(doc(db, 'knowledge_bases', id));
          showToast("Base de conhecimento removida.", "info");
        } catch (e) {
          console.error(e);
          showToast("Erro ao remover base de conhecimento.", "error");
        }
      }
    );
  };
  const handleRenameActionFromKnowledge = async (taskId: string, title: string) => {
    const trimmedTitle = title.trim();
    if (!trimmedTitle) return;
    try {
      const taskExists = tarefas.some(task => task.id === taskId);
      if (taskExists) {
        await updateDoc(doc(db, 'tarefas', taskId), {
          titulo: trimmedTitle,
          data_atualizacao: new Date().toISOString()
        });
        showToast("Ação renomeada.", "success");
        return;
      }
      // Ação órfã: persiste o título customizado nos documentos vinculados do Conhecimento.
      const orphanDocsSnapshot = await getDocs(
        query(collection(db, 'conhecimento'), where('origem.id_origem', '==', taskId))
      );
      const actionDocs = orphanDocsSnapshot.docs.filter((docSnap) => {
        const data = docSnap.data() as any;
        const modulo = data?.origem?.modulo;
        return modulo === 'tarefas' || modulo === 'acoes';
      });
      if (actionDocs.length === 0) {
        showToast("Nenhum documento vinculado encontrado para essa ação sem cadastro.", "info");
        return;
      }
      const batch = writeBatch(db);
      actionDocs.forEach((docSnap) => {
        batch.update(doc(db, 'conhecimento', docSnap.id), {
          orphan_action_title: trimmedTitle
        });
      });
      await batch.commit();
      showToast("Pasta da ação sem cadastro renomeada.", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao renomear ação.", "error");
      throw e;
    }
  };
  const handleProcessWithAI = async (id: string) => {
    const processarArquivoIA = httpsCallable(functions, 'processarArquivoIA');
    try {
      const result = await processarArquivoIA({ itemId: id });
      return result.data;
    } catch (error: any) {
      console.error("Erro no processamento IA:", error);
      return { success: false, error: error.message };
    }
  };
  const generateDynamicTagsForTask = async (
    taskId: string,
    taskData: Partial<Tarefa>,
    options?: { suppressSuccessToast?: boolean }
  ) => {
    const prompt =
      `Analise a seguinte tarefa e forneca ate 5 tags curtas e altamente relevantes ` +
      `(1 a 2 palavras) para caracteriza-la. Use o formato de resposta estrito: ` +
      `[TAGS] tag1, tag2, tag3 [/TAGS].\n\n` +
      `Titulo: ${taskData.titulo || ''}\n` +
      `Descricao: ${taskData.descricao || ''}\n` +
      `Area Tematica: ${taskData.area_tematica || ''}`;
    const fn = httpsCallable(functions, 'askTaskAssistant');
    const res = await fn({
      prompt,
      area_tematica: taskData.area_tematica,
      ragContext: taskData.base_conhecimento,
      extraContextId: taskData.extra_context_id,
      knowledgeItemIds: taskData.knowledge_item_ids || [],
    });
    const result = (res.data as any).result || '';
    const tagsMatch = result.match(/\[TAGS\]([\s\S]*?)\[\/TAGS\]/);
    if (!tagsMatch) throw new Error('Formato de tags invalido.');
    const existingTags = Array.isArray(taskData.tags) ? taskData.tags : [];
    const generatedTags = tagsMatch[1]
      .split(',')
      .map((tag: string) => tag.trim().replace(/^#/, ''))
      .filter((tag: string) => tag.length > 0);
    if (generatedTags.length === 0) throw new Error('Nenhuma tag foi retornada.');
    const mergedTags = Array.from(new Set([...existingTags, ...generatedTags]));
    await updateDoc(doc(db, 'tarefas', taskId), {
      tags: mergedTags,
      data_atualizacao: new Date().toISOString(),
    });
    if (!options?.suppressSuccessToast) {
      showToast('Tags dinÃ¢micas geradas com sucesso!', 'success');
    }
    return mergedTags;
  };
  const handleDeleteIdea = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'brainstorm_ideas', id));
      showToast("Nota removida.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover.", "error");
    }
  };
  const handleCreateTarefa = async (data: Partial<Tarefa>) => {
    try {
      setLoading(true);
      const { is_single_day: _ignoredSingleDay, ...inputData } = data as any;
      const isStandByTask = isStandbyStatus(inputData.status || 'em andamento');
      const singleDate = inputData.data_limite || inputData.data_inicio || (isStandByTask ? '' : formatDateLocalISO(new Date()));
      const normalizedTitle = normalizeTaskTitle(inputData.titulo || '');
      const taskPayload: Record<string, any> = applyStandbyDateRules({
        ...inputData,
        titulo: normalizedTitle,
        status: inputData.status || 'em andamento',
        data_limite: singleDate,
        data_inicio: singleDate,
        google_id: "", // Sinaliza que precisa de PUSH
        data_atualizacao: new Date().toISOString(),
        projeto: 'Google Tasks',
        contabilizar_meta: ['CLC', 'ASSISTENCIA', 'ASSISTENCIA ESTUDANTIL'].includes(normalizeAreaName(inputData.area_tematica)),
        acompanhamento: [],
        entregas_relacionadas: []
      }, null);
      // Sanitiza: remove campos com valor undefined (Firestore não aceita undefined)
      const sanitizedPayload = Object.fromEntries(
        Object.entries(taskPayload).filter(([, v]) => v !== undefined)
      );
      const docRef = await addDoc(collection(db, 'tarefas'), sanitizedPayload);
      let finalTaskPayload: Record<string, any> = { ...taskPayload };
      try {
        const generatedTags = await generateDynamicTagsForTask(docRef.id, taskPayload, { suppressSuccessToast: true });
        finalTaskPayload = { ...finalTaskPayload, tags: generatedTags };
      } catch (tagErr) {
        console.warn("Erro ao gerar tags dinÃ¢micas automaticamente:", tagErr);
      }
      if (convertingIdea) {
        await deleteDoc(doc(db, 'brainstorm_ideas', convertingIdea.id));
        setConvertingIdea(null);
        setTaskInitialData(null);
      }
      showToast("Nova ação criada!", 'success', {
        label: "Ver Ação",
        onClick: () => {
          setSelectedTask({
            id: docRef.id,
            ...finalTaskPayload
          } as Tarefa);
          setTaskModalMode('execute');
        }
      });
    } catch (err) {
      console.error("Erro ao criar tarefa:", err);
      showToast("Erro ao criar ação.", 'error');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (!user) return;
    setLoading(true);
    setError(null);
    // Listener para Tarefas
    const qTarefas = query(collection(db, 'tarefas'));
    const unsubscribeTarefas = onSnapshot(qTarefas, (snapshot) => {
      const normalized: Tarefa[] = snapshot.docs.map(taskDoc => {
        const raw = { id: taskDoc.id, ...taskDoc.data() } as any;
        const singleDate = isStandbyStatus(raw.status) ? '' : (raw.data_limite || raw.data_inicio || '');
        return {
          ...raw,
          area_tematica: raw.area_tematica || raw.categoria,
          data_limite: singleDate,
          data_inicio: singleDate
        } as Tarefa;
      });
      setTarefas(normalized);
      // Migração leve: força dados legados de intervalo para data única (usa término como fonte da verdade)
      const legacyWithRange = snapshot.docs
        .map(taskDoc => ({ id: taskDoc.id, ...taskDoc.data() } as Tarefa))
        .filter(task => !isStandbyStatus(task.status) && !!task.data_limite && task.data_limite !== '-' && task.data_limite !== '0000-00-00' && task.data_limite !== task.data_inicio);
      if (legacyWithRange.length > 0) {
        const batch = writeBatch(db);
        const now = new Date().toISOString();
        legacyWithRange.forEach(task => {
          batch.update(doc(db, 'tarefas', task.id), {
            data_inicio: task.data_limite,
            data_limite: task.data_limite,
            data_atualizacao: now
          });
        });
        batch.commit().catch((migrationErr) => console.error('Erro ao normalizar tarefas legadas:', migrationErr));
      }
      const standbyWithDates = snapshot.docs
        .map(taskDoc => ({ id: taskDoc.id, ...taskDoc.data() } as Tarefa))
        .filter(task => isStandbyStatus(task.status) && Boolean(
          (task.data_limite && task.data_limite !== '-' && task.data_limite !== '0000-00-00') ||
          (task.data_inicio && task.data_inicio !== '-' && task.data_inicio !== '0000-00-00') ||
          task.horario_inicio ||
          task.horario_fim
        ));
      if (standbyWithDates.length > 0) {
        const batch = writeBatch(db);
        const now = new Date().toISOString();
        standbyWithDates.forEach(task => {
          batch.update(doc(db, 'tarefas', task.id), {
            data_inicio: '',
            data_limite: '',
            horario_inicio: null,
            horario_fim: null,
            data_atualizacao: now
          });
        });
        batch.commit().catch((migrationErr) => console.error('Erro ao limpar datas de standby:', migrationErr));
      }
      setLoading(false);
      setIsInitialDataLoading(false);
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Tarefas).");
      setLoading(false);
      setIsInitialDataLoading(false);
    });
    // Listener para Atividades PGC
    const qAtividadesPGC = query(collection(db, 'atividades_pgc'));
    const unsubscribeAtividadesPGC = onSnapshot(qAtividadesPGC, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as AtividadeRealizada));
      setAtividadesPGC(data);
    }, handleSnapshotError('atividades_pgc'));
    // Listener para Afastamentos
    const qAfastamentos = query(collection(db, 'afastamentos'));
    const unsubscribeAfastamentos = onSnapshot(qAfastamentos, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Afastamento));
      setAfastamentos(data);
    }, handleSnapshotError('afastamentos'));
    // Listeners para Entregas (coleção atual + legado)
    let entregasMain: EntregaInstitucional[] = [];
    let entregasLegacy: EntregaInstitucional[] = [];
    const syncEntregas = () => {
      const merged = [...entregasMain, ...entregasLegacy];
      const dedup = new Map<string, EntregaInstitucional>();
      merged.forEach((e) => dedup.set(e.id, e));
      setEntregas(Array.from(dedup.values()));
    };
    const qEntregas = query(collection(db, 'entregas'));
    const unsubscribeEntregas = onSnapshot(qEntregas, (snapshot) => {
      entregasMain = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as EntregaInstitucional));
      syncEntregas();
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Entregas).");
    });
    const qAtividadesLegacy = query(collection(db, 'atividades'));
    const unsubscribeAtividadesLegacy = onSnapshot(qAtividadesLegacy, (snapshot) => {
      entregasLegacy = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as EntregaInstitucional));
      syncEntregas();
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Entregas Legado).");
    });
    const qUnidades = query(collection(db, 'unidades'));
    const unsubscribeUnidades = onSnapshot(qUnidades, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as { id: string, nome: string, palavras_chave?: string[], peso_gravidade?: number }));
      setUnidades(data);
    }, handleSnapshotError('unidades'));
    return () => {
      unsubscribeTarefas();
      unsubscribeEntregas();
      unsubscribeAtividadesLegacy();
      unsubscribeAtividadesPGC();
      unsubscribeAfastamentos();
      unsubscribeUnidades();
    };
  }, [user]);
  const handleAddUnidade = async (nome: string) => {
    try {
      await addDoc(collection(db, 'unidades'), {
        nome: nome,
        palavras_chave: [],
        peso_gravidade: 1
      });
      showToast(`Ãrea ${nome} adicionada!`, 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao adicionar área.", 'error');
    }
  };
  const handleDeleteUnidade = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'unidades', id));
      showToast("Ã rea removida.", 'info');
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover área.", 'error');
    }
  };
  const handleUpdateUnidade = async (id: string, updates: any) => {
    try {
      await updateDoc(doc(db, 'unidades', id), updates);
      showToast("Ã rea atualizada!", 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar área.", 'error');
    }
  };
  useEffect(() => {
    if (!user) return;
    const qPlanos = query(collection(db, 'planos_trabalho'));
    const unsubscribePlanos = onSnapshot(qPlanos, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as PlanoTrabalho));
      setPlanosTrabalho(data);
    }, handleSnapshotError('planos_trabalho'));
    return () => unsubscribePlanos();
  }, [user]);
  useEffect(() => {
    if (!user) return;
    const qNotif = query(
      collection(db, 'notificacoes'),
      where('uid', '==', user.uid)
    );
    const unsubscribeNotif = onSnapshot(qNotif, (snapshot) => {
      // Notificações agora são exclusivas do Telegram, limpamos o painel local do sistema
      setNotifications([]);
    }, (err) => {
      console.error("Erro ao escutar notificações:", err);
    });
    return () => unsubscribeNotif();
  }, [user]);
  useEffect(() => {
    if (!user) return;
    const qBrainstorm = query(collection(db, 'brainstorm_ideas'));
    const unsubscribeBrainstorm = onSnapshot(qBrainstorm, (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as BrainstormIdea));
      setBrainstormIdeas(data.sort((a, b) => b.timestamp.localeCompare(a.timestamp)));
    }, handleSnapshotError('brainstorm_ideas'));
    const unsubscribeKnowledge = onSnapshot(collection(db, 'conhecimento'), (snapshot) => {
      const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as ConhecimentoItem));
      setKnowledgeItems(data);
    }, handleSnapshotError('conhecimento'));
    return () => {
      unsubscribeBrainstorm();
      unsubscribeKnowledge();
    };
  }, [user]);
  const handleLinkTarefa = async (tarefaId: string, entregaId: string) => {
    try {
      const docRef = doc(db, 'tarefas', tarefaId);
      await updateDoc(docRef, {
        entregas_relacionadas: arrayUnion(entregaId)
      });
      showToast("Vínculo criado com sucesso!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao vincular tarefa.", "error");
    }
  };
  const handleUnlinkTarefa = async (tarefaId: string, entregaId: string) => {
    try {
      const docRef = doc(db, 'tarefas', tarefaId);
      await updateDoc(docRef, {
        entregas_relacionadas: arrayRemove(entregaId)
      });
      showToast("Vínculo removido!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover vínculo.", "error");
    }
  };
  const handleCreateEntregaFromPlan = async (item: PlanoTrabalhoItem): Promise<string | null> => {
    try {
      const docRef = await addDoc(collection(db, 'entregas'), {
        entrega: item.entrega,
        area: item.origem,
        unidade: item.unidade,
        mes: currentMonth,
        ano: currentYear
      });
      return docRef.id;
    } catch (err) {
      console.error(err);
      return null;
    }
  };
  const normalizeISODate = (value: any, fallback?: string): string => {
    const text = String(value || '').trim();
    if (!text) return fallback || formatDateLocalISO(new Date());
    const direct = text.match(/^(\d{4}-\d{2}-\d{2})/);
    if (direct) return direct[1];
    const parsed = new Date(text);
    if (!isNaN(parsed.getTime())) {
      return parsed.toLocaleDateString('en-CA');
    }
    const br = text.match(/(\d{2})\/(\d{2})\/(\d{4})/);
    if (br) return `${br[3]}-${br[2]}-${br[1]}`;
    return fallback || formatDateLocalISO(new Date());
  };
  const handleCreatePgdActivity = async (entregaId: string, draft: Partial<AtividadeRealizada>) => {
    if (!entregaId) return;
    const start = normalizeISODate(draft.data_inicio);
    const end = normalizeISODate(draft.data_fim || draft.data_inicio || start, start);
    try {
      await addDoc(collection(db, 'atividades_pgc'), {
        entrega_id: entregaId,
        descricao_atividade: (draft.descricao_atividade || '').trim(),
        data_inicio: start,
        data_fim: end,
        status_atividade: draft.status_atividade || 'rascunho',
        usuario: user?.displayName || 'Usuário',
        origem: draft.origem || 'manual',
        task_ids: draft.task_ids || [],
        data_criacao: new Date().toISOString(),
        data_atualizacao: new Date().toISOString()
      });
      showToast('Registro PGD adicionado.', 'success');
    } catch (err) {
      console.error(err);
      showToast('Erro ao adicionar registro PGD.', 'error');
    }
  };
  const handleUpdatePgdActivity = async (id: string, updates: Partial<AtividadeRealizada>) => {
    try {
      const payload: Record<string, any> = {
        data_atualizacao: new Date().toISOString()
      };
      if (typeof updates.descricao_atividade === 'string') payload.descricao_atividade = updates.descricao_atividade;
      if (typeof updates.status_atividade === 'string') payload.status_atividade = updates.status_atividade;
      if (updates.data_inicio) payload.data_inicio = normalizeISODate(updates.data_inicio);
      if (updates.data_fim) payload.data_fim = normalizeISODate(updates.data_fim);
      if (updates.origem) payload.origem = updates.origem;
      if (updates.task_ids) payload.task_ids = updates.task_ids;
      await updateDoc(doc(db, 'atividades_pgc', id), payload);
      showToast('Registro PGD atualizado.', 'success');
    } catch (err) {
      console.error(err);
      showToast('Erro ao atualizar registro PGD.', 'error');
    }
  };
  const handleDeletePgdActivity = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'atividades_pgc', id));
      showToast('Registro PGD removido.', 'info');
    } catch (err) {
      console.error(err);
      showToast('Erro ao remover registro PGD.', 'error');
    }
  };
  const handleGeneratePgdFromDiaries = async (
    entregaId: string,
    item: PlanoTrabalhoItem,
    tarefasRelacionadas: Tarefa[]
  ) => {
    if (!entregaId) return;
    setPgdGeneratingByEntrega(prev => ({ ...prev, [entregaId]: true }));
    try {
      const diaryEntries = tarefasRelacionadas.flatMap(task =>
        (task.acompanhamento || [])
          .map(entry => ({
            task_id: task.id,
            task_titulo: task.titulo,
            data: normalizeISODate(entry.data),
            nota: (entry.nota || '').trim()
          }))
          .filter(entry => {
            if (!entry.nota) return false;
            if (parseDiaryRichNote(entry.nota)) return false;
            return true;
          })
      ).sort((a, b) => a.data.localeCompare(b.data));
      if (diaryEntries.length === 0) {
        showToast('Sem diário de bordo textual para gerar registros desta entrega.', 'info');
        return;
      }
      const fn = httpsCallable(functions, 'generatePgdFromDiariesAI');
      const response = await fn({
        entrega: item.entrega,
        descricaoEntrega: item.descricao || '',
        yearMonth: `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`,
        entries: diaryEntries,
      });
      const parsed = response.data as { registros?: any[] };
      const aiRows = Array.isArray(parsed?.registros) ? parsed.registros : [];
      const normalizedRows = aiRows
        .map((r: any) => {
          const start = normalizeISODate(r?.data_inicio);
          const end = normalizeISODate(r?.data_fim || r?.data_inicio || start, start);
          const desc = String(r?.descricao_atividade || '').trim();
          const taskIds = Array.isArray(r?.task_ids) ? r.task_ids.filter((id: any) => typeof id === 'string') : [];
          return {
            descricao_atividade: desc,
            data_inicio: start,
            data_fim: end,
            task_ids: taskIds
          };
        })
        .filter((r: any) => r.descricao_atividade.length >= 12);
      const fallbackRows = diaryEntries.reduce((acc: any[], entry) => {
        const existing = acc.find(i => i.data_inicio === entry.data && i.data_fim === entry.data);
        if (existing) {
          existing.descricao_atividade += `\n- ${entry.nota}`;
          if (!existing.task_ids.includes(entry.task_id)) existing.task_ids.push(entry.task_id);
          return acc;
        }
        acc.push({
          descricao_atividade: `Atividades executadas em ${entry.data}:\n- ${entry.nota}`,
          data_inicio: entry.data,
          data_fim: entry.data,
          task_ids: [entry.task_id]
        });
        return acc;
      }, []).slice(0, 12);
      const finalRows = normalizedRows.length > 0 ? normalizedRows : fallbackRows;
      if (finalRows.length === 0) {
        showToast('Não foi possível gerar registros PGD para esta entrega.', 'error');
        return;
      }
      const batch = writeBatch(db);
      atividadesPGC
        .filter(a => a.entrega_id === entregaId && a.origem === 'ia')
        .forEach(a => batch.delete(doc(db, 'atividades_pgc', a.id)));
      finalRows.forEach((row: any) => {
        const ref = doc(collection(db, 'atividades_pgc'));
        batch.set(ref, {
          entrega_id: entregaId,
          descricao_atividade: row.descricao_atividade,
          data_inicio: row.data_inicio,
          data_fim: row.data_fim,
          status_atividade: 'rascunho',
          usuario: user?.displayName || 'Usuário',
          origem: 'ia',
          task_ids: row.task_ids || [],
          data_criacao: new Date().toISOString(),
          data_atualizacao: new Date().toISOString()
        });
      });
      await batch.commit();
      showToast(`${finalRows.length} registro(s) PGD gerado(s) com IA.`, 'success');
    } catch (err) {
      console.error(err);
      showToast('Erro ao gerar registros PGD com IA.', 'error');
    } finally {
      setPgdGeneratingByEntrega(prev => ({ ...prev, [entregaId]: false }));
    }
  };
  const parsePgdRawTextFallback = (rawText: string) => {
    const lines = rawText
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean);
    const groupedByDate = new Map<string, string[]>();
    let currentDate = '';
    lines.forEach((line) => {
      const dateMatch = line.match(/^(\d{2}\/\d{2}\/\d{4})/);
      if (dateMatch) {
        currentDate = normalizeISODate(dateMatch[1]);
        if (!groupedByDate.has(currentDate)) groupedByDate.set(currentDate, []);
        return;
      }
      if (!currentDate) return;
      const cleaned = line.replace(/^[-*â€¢]\s*/, '').trim();
      if (!cleaned) return;
      groupedByDate.get(currentDate)!.push(cleaned);
    });
    return Array.from(groupedByDate.entries())
      .map(([date, tasks]) => {
        const items = tasks.filter(t => t.length > 3);
        const descricao = items.length <= 1 ? (items[0] || '') : items.map(t => `- ${t}`).join('\n');
        return {
          descricao_atividade: descricao,
          data_inicio: date,
          data_fim: date
        };
      })
      .filter(r => r.descricao_atividade.length > 6)
      .sort((a, b) => a.data_inicio.localeCompare(b.data_inicio));
  };
  const collapsePgdRowsByPeriod = (rows: { descricao_atividade: string; data_inicio: string; data_fim: string }[]) => {
    const grouped = new Map<string, { data_inicio: string; data_fim: string; items: string[] }>();
    rows.forEach((row) => {
      const start = normalizeISODate(row.data_inicio);
      const end = normalizeISODate(row.data_fim || row.data_inicio || start, start);
      const desc = String(row.descricao_atividade || '').trim();
      if (!desc) return;
      const key = `${start}|${end}`;
      if (!grouped.has(key)) {
        grouped.set(key, { data_inicio: start, data_fim: end, items: [] });
      }
      grouped.get(key)!.items.push(desc);
    });
    return Array.from(grouped.values())
      .map((g) => {
        const uniqueItems = Array.from(new Set(g.items.map(i => i.trim()).filter(Boolean)));
        const descricao = uniqueItems.length <= 1 ? (uniqueItems[0] || '') : uniqueItems.map(i => `- ${i}`).join('\n');
        return {
          descricao_atividade: descricao,
          data_inicio: g.data_inicio,
          data_fim: g.data_fim
        };
      })
      .filter(r => r.descricao_atividade.length > 6)
      .sort((a, b) => {
        const k1 = `${a.data_inicio}|${a.data_fim}`;
        const k2 = `${b.data_inicio}|${b.data_fim}`;
        return k1.localeCompare(k2);
      });
  };
  const handleGeneratePgdFromRawText = async (
    entregaId: string,
    item: PlanoTrabalhoItem,
    rawText: string
  ) => {
    if (!entregaId || !rawText.trim()) return;
    setPgdRawTextProcessingByEntrega(prev => ({ ...prev, [entregaId]: true }));
    try {
      let finalRows: { descricao_atividade: string; data_inicio: string; data_fim: string }[] = [];
      try {
        const fn = httpsCallable(functions, 'generatePgdFromRawTextAI');
        const response = await fn({
          entrega: item.entrega,
          descricaoEntrega: item.descricao || '',
          rawText,
        });
        const parsed = response.data as { registros?: any[] };
        const aiRows = Array.isArray(parsed?.registros) ? parsed.registros : [];
        finalRows = aiRows
          .map((r: any) => {
            const start = normalizeISODate(r?.data_inicio);
            const end = normalizeISODate(r?.data_fim || r?.data_inicio || start, start);
            const descricao = String(r?.descricao_atividade || '').trim();
            return { descricao_atividade: descricao, data_inicio: start, data_fim: end };
          })
          .filter((r: any) => r.descricao_atividade.length >= 8);
      } catch (aiErr) {
        console.error(aiErr);
      }
      if (finalRows.length === 0) finalRows = parsePgdRawTextFallback(rawText);
      finalRows = collapsePgdRowsByPeriod(finalRows);
      if (finalRows.length === 0) {
        showToast('Não foi possível extrair registros do texto enviado.', 'error');
        return;
      }
      const batch = writeBatch(db);
      atividadesPGC
        .filter(a => a.entrega_id === entregaId && a.origem === 'ia')
        .forEach(a => batch.delete(doc(db, 'atividades_pgc', a.id)));
      finalRows.forEach((row) => {
        const ref = doc(collection(db, 'atividades_pgc'));
        batch.set(ref, {
          entrega_id: entregaId,
          descricao_atividade: row.descricao_atividade,
          data_inicio: row.data_inicio,
          data_fim: row.data_fim,
          status_atividade: 'rascunho',
          usuario: user?.displayName || 'Usuário',
          origem: 'ia',
          task_ids: [],
          data_criacao: new Date().toISOString(),
          data_atualizacao: new Date().toISOString()
        });
      });
      await batch.commit();
      showToast(`${finalRows.length} registro(s) gerado(s) a partir do texto bruto.`, 'success');
    } catch (err) {
      console.error(err);
      showToast('Erro ao processar texto bruto.', 'error');
    } finally {
      setPgdRawTextProcessingByEntrega(prev => ({ ...prev, [entregaId]: false }));
    }
  };
  // Health Handlers
  const handleUpdateHealthSettings = async (settings: HealthSettings) => {
    await setDoc(doc(db, 'health_settings', 'config'), settings);
    showToast("Meta de peso atualizada!", "success");
  };
  const handleAddHealthWeight = async (weight: number, date: string) => {
    await addDoc(collection(db, 'health_weights'), { weight, date });
    showToast("Peso registrado com sucesso!", "success");
  };
  const handleDeleteHealthWeight = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'health_weights', id));
      showToast("Registro de peso removido.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover registro.", "error");
    }
  };
  const handleUpdateFinanceGoal = async (goal: FinanceGoal) => {
    try {
      await updateDoc(doc(db, 'finance_goals', goal.id), goal as any);
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar meta.", "error");
    }
  };
  const handleReorderFinanceGoals = async (reorderedGoals: FinanceGoal[]) => {
    try {
      const promises = reorderedGoals.map((goal, index) =>
        updateDoc(doc(db, 'finance_goals', goal.id), { priority: index + 1 })
      );
      await Promise.all(promises);
      showToast("Prioridades atualizadas!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao reordenar metas.", "error");
    }
  };
  const handleDeleteFinanceGoal = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'finance_goals', id));
      showToast("Meta removida!", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover meta.", "error");
    }
  };
  const handleSaveHealthTelegramReminder = async (reminder: HealthTelegramReminder) => {
    const nowIso = new Date().toISOString();
    const payload: HealthTelegramReminder = {
      ...reminder,
      telegramOnly: true,
      created_by_uid: reminder.created_by_uid || user?.uid,
      data_atualizacao: nowIso,
      data_criacao: reminder.data_criacao || nowIso,
    };
    await setDoc(doc(db, 'health_telegram_reminders', reminder.id), payload, { merge: true });
  };
  const handleDeleteHealthTelegramReminder = async (id: string) => {
    await deleteDoc(doc(db, 'health_telegram_reminders', id));
    showToast("Lembrete removido.", "info");
  };
  const handleSaveExerciseLog = async (date: string, data: Partial<ExerciseLog>) => {
    // Save the log
    await setDoc(doc(db, 'health_exercise_logs', date), data, { merge: true });
    // Recalculate goals from last 5 sessions
    const allLogs = [...exerciseLogs.filter(l => l.id !== date), { id: date, ...data }]
      .sort((a, b) => b.id.localeCompare(a.id));
    const newSettings: ExerciseSettings = { ...exerciseSettings };
    // --- Push-ups adaptive goal ---
    if (data.pushups !== undefined) {
      const pushupSessions = allLogs.filter(l => l.pushups !== undefined).slice(0, 5);
      if (pushupSessions.length === 0) {
        newSettings.pushups = { activeGoal: data.pushups.done, floor: 1 };
      } else {
        const currentGoal = newSettings.pushups?.activeGoal ?? data.pushups.goal;
        const floor = newSettings.pushups?.floor ?? 1;
        if (pushupSessions.length === 1) {
          // First log â€” baseline
          newSettings.pushups = { activeGoal: data.pushups.done, floor: 1 };
        } else {
          const hitRate = pushupSessions.filter(l => l.pushups!.done >= l.pushups!.goal).length / pushupSessions.length;
          let nextGoal = currentGoal;
          if (hitRate >= 0.8) nextGoal = currentGoal + 2;
          else if (hitRate < 0.5) nextGoal = Math.max(floor, currentGoal - 2);
          newSettings.pushups = { activeGoal: nextGoal, floor };
        }
      }
    }
    // --- Pull-ups phase progression ---
    if (data.pullups !== undefined) {
      const pullupSessions = allLogs.filter(l => l.pullups !== undefined).slice(0, 5);
      const currentPhase: PullupPhase = newSettings.pullups?.phase ?? 'dead_hang';
      const currentGoal = newSettings.pullups?.activeGoal ?? data.pullups.goal;
      const floor = newSettings.pullups?.floor ?? 1;
      let consecutiveGateMet = newSettings.pullups?.consecutiveGateMet ?? 0;
      if (pullupSessions.length <= 1) {
        // First log â€” baseline for phase 1
        newSettings.pullups = { activeGoal: data.pullups.done || 10, phase: 'dead_hang', consecutiveGateMet: 0, floor: 1 };
      } else {
        const latestLog = pullupSessions[0];
        const done = latestLog.pullups!.done;
        const goal = latestLog.pullups!.goal;
        // Phase gate thresholds
        const phaseGates: Record<PullupPhase, number> = {
          dead_hang: 30,  // seconds
          negative: 5,    // reps
          assisted: 8,    // reps
          full: 999,      // no gate â€” uses adaptive algo
        };
        const phaseNextGoalIncrement: Record<PullupPhase, number> = {
          dead_hang: 5, negative: 1, assisted: 1, full: 1
        };
        const gateValue = phaseGates[currentPhase];
        const metGate = done >= gateValue;
        if (currentPhase === 'full') {
          // Adaptive algorithm for full pull-ups (same as push-ups but smaller increments)
          const hitRate = pullupSessions.filter(l => l.pullups!.done >= l.pullups!.goal).length / pullupSessions.length;
          let nextGoal = currentGoal;
          if (hitRate >= 0.8) nextGoal = currentGoal + 1;
          else if (hitRate < 0.5) nextGoal = Math.max(floor, currentGoal - 1);
          newSettings.pullups = { activeGoal: nextGoal, phase: 'full', consecutiveGateMet: 0, floor };
        } else {
          if (metGate) {
            consecutiveGateMet = Math.min(consecutiveGateMet + 1, 2);
          } else {
            consecutiveGateMet = 0;
          }
          const phaseOrder: PullupPhase[] = ['dead_hang', 'negative', 'assisted', 'full'];
          const currentPhaseIdx = phaseOrder.indexOf(currentPhase);
          let nextPhase: PullupPhase = currentPhase;
          let nextGoal = Math.min(currentGoal + (metGate ? phaseNextGoalIncrement[currentPhase] : 0), gateValue);
          if (consecutiveGateMet >= 2) {
            // Advance to next phase
            nextPhase = phaseOrder[Math.min(currentPhaseIdx + 1, phaseOrder.length - 1)];
            nextGoal = nextPhase === 'full' ? 1 : (nextPhase === 'assisted' ? 3 : nextPhase === 'negative' ? 3 : 10);
            consecutiveGateMet = 0;
          }
          newSettings.pullups = { activeGoal: nextGoal, phase: nextPhase, consecutiveGateMet, floor };
        }
      }
    }
    await setDoc(doc(db, 'health_exercise_settings', 'config'), newSettings, { merge: true });
    if (hasExerciseData) showToast("Exercício registrado!", "success");
  };
  const handleMarkNotificationRead = (id: string) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, isRead: true } : n));
  };
  const handleDismissNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
    if (activePopup?.id === id) setActivePopup(null);
  };
  const stats = useMemo(() => ({
    total: tarefas.length,
    emAndamento: tarefas.filter(t => normalizeStatus(t.status) === 'em andamento').length,
    standBy: tarefas.filter(t => normalizeStatus(t.status) === 'stand-by').length,
    concluidas: tarefas.filter(t => normalizeStatus(t.status) === 'concluido').length,
    clc: tarefas.filter(t => normalizeAreaName(t.area_tematica) === 'CLC' && normalizeStatus(t.status) !== 'concluido').length,
    assistencia: tarefas.filter(t => ['ASSISTENCIA', 'ASSISTENCIA ESTUDANTIL'].includes(normalizeAreaName(t.area_tematica)) && normalizeStatus(t.status) !== 'concluido').length,
    geral: tarefas.filter(t => t.area_tematica === 'GERAL' && normalizeStatus(t.status) !== 'concluido').length,
    semTag: tarefas.filter(t => (t.area_tematica === 'NÃO CLASSIFICADA' || !t.area_tematica) && normalizeStatus(t.status) !== 'concluido' && t.status !== 'excluído' as any).length,
  }), [tarefas]);
  const prioridadesHoje = useMemo(() => {
    const now = new Date();
    const todayStr = formatDateLocalISO(now);
    return tarefas.filter(t => {
      if (normalizeStatus(t.status) === 'concluido' || t.status === 'excluído' as any) return false;
      if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") return false;
      return t.data_limite === todayStr;
    });
  }, [tarefas]);
  const filteredAndSortedTarefas = useMemo(() => {
    let result = [...tarefas];
    if (searchTerm) {
      const s = searchTerm.toLowerCase();
      if (s === 'filter:unclassified') {
        result = result.filter(t => (!t.area_tematica || t.area_tematica === 'NÃO CLASSIFICADA') && normalizeStatus(t.status) !== 'concluido');
      } else if (s === 'categoria:geral') {
        result = result.filter(t => t.area_tematica === 'GERAL');
      } else {
        result = result.filter(t => t.titulo?.toLowerCase().includes(s) || t.projeto?.toLowerCase().includes(s) || t.notas?.toLowerCase().includes(s));
      }
    }
    if (statusFilter.length > 0 && viewMode !== 'licitacoes' && viewMode !== 'assistencia') {
      result = result.filter(t => {
        const tStatus = normalizeStatus(t.status);
        const matchesStatus = statusFilter.some(sf => {
          const sfStatus = normalizeStatus(sf);
          if (sfStatus === 'stand-by' || sfStatus === 'cgby') {
            return tStatus === 'stand-by' || tStatus === 'cgby';
          }
          return tStatus === sfStatus;
        });
        // Se a tarefa não tem data válida, ela é considerada stand-by "na prática"
        const hasNoDate = !t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00" || !/^\d{4}-\d{2}-\d{2}$/.test(t.data_limite);
        const shouldShowAsStandby = hasNoDate && statusFilter.some(sf => normalizeStatus(sf) === 'stand-by' || normalizeStatus(sf) === 'cgby');
        return matchesStatus || shouldShowAsStandby || tStatus === 'concluido';
      });
    }
    if (areaFilter.length > 0) {
      const norm = (val: any) => (val || '').toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
      result = result.filter(t => {
        const cat = norm(t.area_tematica);
        return areaFilter.some(f => {
          const filterNorm = norm(f);
          if (filterNorm === 'NAO CLASSIFICADA') return !t.area_tematica || cat === 'NAO CLASSIFICADA';
          return cat === filterNorm;
        });
      });
    }
    // Sempre remove excluídos
    result = result.filter(t => t.status !== 'excluído' as any);
    // Remove tarefas de Gasto Semanal (exclusivas do Financeiro)
    result = result.filter(t => !t.titulo.toLowerCase().includes('gasto semanal'));
    // Se estiver na visão Geral (que agora é a que mostra tudo ou sem categoria)
    // Se viewMode for gallery (Dashboard), ele mostra tudo filtrado por status.
    // Se criarmos uma visão específica para sem classificação, podemos filtrar aqui.
    if (viewMode === 'gallery' && searchTerm === 'filter:unclassified') {
      result = result.filter(t => (!t.area_tematica || t.area_tematica === 'NÃO CLASSIFICADA') && normalizeStatus(t.status) !== 'concluido');
    }
    result.sort((a, b) => {
      const dVal = (t: Tarefa) => (!t.data_limite || t.data_limite === "-" || t.data_limite.trim() === "") ? (sortOption === 'date-asc' ? Infinity : -Infinity) : new Date(t.data_limite).getTime();
      const dateCompare = sortOption === 'date-asc' ? dVal(a) - dVal(b) : dVal(b) - dVal(a);
      if (dateCompare !== 0) return dateCompare;
      // Se as datas são iguais, priorizamos o horário (conforme solicitação do usuário)
      if (a.horario_inicio && b.horario_inicio) return a.horario_inicio.localeCompare(b.horario_inicio);
      if (a.horario_inicio) return -1; // Tarefa com horário vem primeiro
      if (b.horario_inicio) return 1;  // Tarefa sem horário vai para baixo
      // Se ambas não têm horário, usamos a ordem manual se existir
      if (a.ordem !== undefined && b.ordem !== undefined) return a.ordem - b.ordem;
      return 0;
    });
    return result;
  }, [tarefas, searchTerm, statusFilter, sortOption, areaFilter]);
  // Calcula tarefas não classificadas usando EXATAMENTE o mesmo filtro da exibição
  const unclassifiedTasksCount = useMemo(() => {
    return tarefas.filter(t =>
      (!t.area_tematica || t.area_tematica === 'NÃO CLASSIFICADA') &&
      normalizeStatus(t.status) !== 'concluido' &&
      t.status !== 'excluído' as any
    ).length;
  }, [tarefas]);
  const descriptionSynthesisEligibleCount = useMemo(() => {
    return tarefas.filter(task => isBlankActionDescription(task.descricao) && hasActionDescriptionContext(task)).length;
  }, [tarefas]);
  const tarefasAgrupadas: Record<string, Tarefa[]> = useMemo(() => {
    const buckets = {
      hoje: [] as Tarefa[],
      amanha: [] as Tarefa[],
      estaSemana: [] as Tarefa[],
      esteMes: [] as Tarefa[],
      semData: [] as Tarefa[],
      standBy: [] as Tarefa[],
      concluidas: [] as Tarefa[]
    };
    const mesesFuturos: Record<string, { label: string, tasks: Tarefa[] }> = {};
    const now = new Date();
    // Reset hours to ensure clean comparisons
    now.setHours(0, 0, 0, 0);
    const todayStr = now.toLocaleDateString('en-CA'); // YYYY-MM-DD
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toLocaleDateString('en-CA');
    // End of current week (Saturday)
    const endOfWeek = new Date(now);
    endOfWeek.setDate(now.getDate() + (6 - now.getDay()));
    const endOfWeekStr = endOfWeek.toLocaleDateString('en-CA');
    // End of current month
    const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    const endOfMonthStr = endOfMonth.toLocaleDateString('en-CA');
    filteredAndSortedTarefas.forEach(t => {
      // Se a tarefa está concluída, vai para o bucket de concluídas (útil na pesquisa)
      if (normalizeStatus(t.status) === 'concluido') {
        buckets.concluidas.push(t);
        return;
      }
      const hasValidDate = hasValidActionDate(t);
      // Stand-by e acoes sem data saem do fluxo ativo e entram no backlog pausado.
      if (shouldShowInStandbyBucket(t)) {
        buckets.standBy.push(t);
        return;
      }
      if (t.data_limite < todayStr) {
        buckets.hoje.push(t);
      } else if (t.data_limite === todayStr) {
        buckets.hoje.push(t);
      } else if (t.data_limite === tomorrowStr) {
        buckets.amanha.push(t);
      } else if (t.data_limite <= endOfWeekStr) {
        buckets.estaSemana.push(t);
      } else if (t.data_limite <= endOfMonthStr) {
        buckets.esteMes.push(t);
      } else {
        // Future Months
        const parts = t.data_limite.split('-');
        const key = `${parts[0]}-${parts[1]}`; // sortable key YYYY-MM
        if (!mesesFuturos[key]) {
          const dateObj = new Date(Number(parts[0]), Number(parts[1]) - 1, 2);
          const monthName = dateObj.toLocaleString('pt-BR', { month: 'long', year: 'numeric' });
          const label = monthName.charAt(0).toUpperCase() + monthName.slice(1);
          mesesFuturos[key] = { label, tasks: [] };
        }
        mesesFuturos[key].tasks.push(t);
      }
    });
    // Ações em Stand-by (Backlog) ordenadas por antiguidade
    if (buckets.standBy.length > 0) {
      buckets.standBy.sort((a, b) => {
        const tA = new Date(a.data_criacao).getTime();
        const tB = new Date(b.data_criacao).getTime();
        return tA - tB; // Antigas no topo
      });
    }
    // Build final object preserving desired order
    const finalGroups: Record<string, Tarefa[]> = {};
    if (buckets.hoje.length > 0) finalGroups["Hoje"] = buckets.hoje;
    if (buckets.amanha.length > 0) finalGroups["Amanhã"] = buckets.amanha;
    if (buckets.estaSemana.length > 0) finalGroups["Esta Semana"] = buckets.estaSemana;
    if (buckets.esteMes.length > 0) finalGroups["Este Mês"] = buckets.esteMes;
    // Sort future months chronologically
    Object.keys(mesesFuturos).sort().forEach(key => {
      finalGroups[mesesFuturos[key].label] = mesesFuturos[key].tasks;
    });
    if (buckets.standBy.length > 0) finalGroups["Ações em Stand-by"] = buckets.standBy;
    if (buckets.concluidas.length > 0) {
      buckets.concluidas.sort((a, b) => {
        const tA = a.data_conclusao ? new Date(a.data_conclusao).getTime() : 0;
        const tB = b.data_conclusao ? new Date(b.data_conclusao).getTime() : 0;
        return tB - tA;
      });
      finalGroups["Concluídas"] = buckets.concluidas;
    }
    return finalGroups;
  }, [filteredAndSortedTarefas]);
  const activeTasks = useMemo(() => {
    return filteredAndSortedTarefas.filter(t => normalizeStatus(t.status) !== 'concluido' && !shouldShowInStandbyBucket(t));
  }, [filteredAndSortedTarefas]);

  // Lookup UPPER(nome) -> peso_gravidade (1..5) das Áreas Temáticas (unidades)
  const gravityMap = useMemo(() => buildGravityMap(unidades), [unidades]);

  // Modo Corrido: ordenação por Score GUT (G x U x T) decrescente.
  // Substitui o reordenamento manual por drag.
  const sortedActiveTasks = useMemo(() => {
    if (groupByDate) {
      return activeTasks;
    }
    const now = new Date();
    return [...activeTasks]
      .map((task, idx) => ({ task, idx, score: computeScoreGUT(task, gravityMap, now).score }))
      .sort((a, b) => (b.score - a.score) || (a.idx - b.idx))
      .map(entry => entry.task);
  }, [activeTasks, gravityMap, groupByDate]);

  // Cota Institucional Diária: ao menos uma ação de área G=5 (ex.: CLC /
  // Assistência Estudantil) precisa ter movimentação registrada hoje.
  // Válida apenas de segunda a sexta-feira.
  const cotaInstitucional = useMemo(() => {
    const hoje = new Date();
    const diaSemana = hoje.getDay(); // 0 = domingo, 6 = sábado
    if (diaSemana === 0 || diaSemana === 6) {
      return { hasInstitucional: false, cumprida: true };
    }
    const todayStr = formatDateLocalISO(hoje);
    // Inclui tarefas concluídas para detectar ações institucionais encerradas hoje
    const todasInstitucionais = filteredAndSortedTarefas.filter(t => computeGravidade(t.area_tematica, gravityMap) === 5);
    if (todasInstitucionais.length === 0) {
      return { hasInstitucional: false, cumprida: true };
    }
    const isToday = (val: any) => String(val || '').slice(0, 10) === todayStr;
    const cumprida = todasInstitucionais.some(t =>
      isToday(t.data_conclusao) ||
      (t.acompanhamento || []).some(e => isToday(e?.data)) ||
      (t.plano_acao_historico || []).some(h => isToday(h?.data))
    );
    return { hasInstitucional: true, cumprida };
  }, [filteredAndSortedTarefas, gravityMap]);

  useEffect(() => {
    if (!hasAutoExpanded && Object.keys(tarefasAgrupadas).length > 0) {
      const keys = Object.keys(tarefasAgrupadas);
      let sectionsToExpand: string[] = [];
      if (keys.includes("Hoje")) sectionsToExpand.push("Hoje");
      if (sectionsToExpand.length === 0) {
        const fallback = keys.find(k => k !== "Ações em Stand-by" && k !== "Concluídas");
        if (fallback) sectionsToExpand = [fallback];
      }
      if (sectionsToExpand.length === 0 && keys.includes("Ações em Stand-by")) {
        sectionsToExpand = ["Ações em Stand-by"];
      }
      setExpandedSections(sectionsToExpand);
      setHasAutoExpanded(true);
    }
  }, [tarefasAgrupadas, hasAutoExpanded]);
  // Reseta o limite de concluídas ao iniciar uma nova pesquisa
  useEffect(() => {
    setCompletedLimit(10);
  }, [searchTerm]);
  const toggleSection = (label: string) => {
    setExpandedSections(prev =>
      prev.includes(label) ? prev.filter(s => s !== label) : [...prev, label]
    );
  };
  // Quando há pesquisa ativa, expande todas as seções automaticamente (incluindo Concluídas)
  const effectiveExpandedSections = useMemo(() => {
    if (searchTerm && searchTerm !== 'filter:unclassified') {
      return Object.keys(tarefasAgrupadas);
    }
    return expandedSections;
  }, [searchTerm, tarefasAgrupadas, expandedSections]);
  // No PGC, filtramos as tarefas pelo período selecionado (mês/ano)
  // No PGC, filtramos as tarefas pelo período selecionado (mês/ano)
  const pgcTasks: Tarefa[] = useMemo(() => {
    // Normalização agressiva para comparação de texto
    const norm = (val: any) => {
      if (!val) return "";
      return String(val).toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
    };
    return tarefas.filter(t => {
      if (t.status === 'excluído' as any) return false;
      const proj = norm(t.projeto);
      const cat = norm(t.area_tematica);
      // Identificadores das unidades PGD/PGC - Pelo PROJETO ou CATEGORIA
      const isCLC = proj.includes('CLC') || cat === 'CLC';
      const isASSIST = proj.includes('ASSIST') || proj.includes('ESTUDANTIL') || cat.includes('ASSIST');
      const isPgcUnit = isCLC || isASSIST;
      // Verifica se está vinculada a qualquer entrega institucional
      const linkedIds = Array.isArray(t.entregas_relacionadas) ? t.entregas_relacionadas.filter(id => !!id) : [];
      const isLinkedAtAll = linkedIds.length > 0;
      // Regra fundamental: Se não é unidade PGD e não foi vinculado manualmente, não entra no PGC
      if (!isPgcUnit && !isLinkedAtAll) return false;
      // Se estiver vinculado, aplicamos a regra de exibição temporal (mês atual)
      if (isLinkedAtAll) {
        if (!t.data_limite || t.data_limite === "-" || t.data_limite === "0000-00-00") return true;
        const parts = t.data_limite.split(/[-/]/);
        if (parts.length < 3) return true;
        let taskYear = parseInt(parts[0]);
        let taskMonth = parseInt(parts[1]) - 1;
        if (taskYear < 1000) {
          taskYear = parseInt(parts[2]);
          taskMonth = parseInt(parts[1]) - 1;
        }
        return taskMonth === currentMonth && taskYear === currentYear;
      }
      // Se for unidade PGD mas ainda não vinculado, aparece no PGC (staging area)
      return isPgcUnit;
    });
  }, [tarefas, currentMonth, currentYear]);
  const pgcEntregas: EntregaInstitucional[] = useMemo(() => entregas.filter(e => {
    return e.mes === currentMonth && e.ano === currentYear;
  }), [entregas, currentMonth, currentYear]);
  const primaryCalendarEvents = useMemo(() => {
    return googleCalendarEvents.filter(event => !event.calendar_id || event.calendar_id === 'primary');
  }, [googleCalendarEvents]);
  const pgcTasksAguardando: Tarefa[] = useMemo(() => {
    const currentDeliveryIds = pgcEntregas.map(e => e.id);
    const norm = (val: any) => (val || '').toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
    return pgcTasks.filter(t => {
      // Regra 1: Deve ser da categoria CLC ou ASSISTÊNCIA
      const isCLC = norm(t.area_tematica) === 'CLC' || (t.projeto && norm(t.projeto).includes('CLC'));
      const isAssist = norm(t.area_tematica).includes('ASSIST') || (t.projeto && (norm(t.projeto).includes('ASSIST') || norm(t.projeto).includes('ESTUDANTIL')));
      if (!isCLC && !isAssist) return false;
      // Regra de Filtro por Data (Visualização Diária)
      // Se estiver na visão de dia, mostra APENAS o que está agendado para aquele dia específico
      if (calendarViewMode === 'day') {
        const targetDateStr = calendarDate.toLocaleDateString('en-CA');
        if (t.data_limite !== targetDateStr) return false;
      }
      // Regra 2: Verifica vínculos com entregas DO MÃŠS ATUAL
      const linkedIds = Array.isArray(t.entregas_relacionadas) ? t.entregas_relacionadas : [];
      const isLinkedToCurrent = linkedIds.some(id => currentDeliveryIds.includes(id));
      // Se JÃ estiver vinculado a uma entrega deste mês, não precisa aparecer na lista de "Aguardando"
      // POIS ela já aparecerá dentro do card da entrega correspondente.
      // Se estiver vinculado a entrega de OUTRO mês, deve aparecer aqui?
      // O usuário disse: "todas as tarefas que tem a tag CLC ou a tag assistência estudantil devam constar nessa aba Audit PGC"
      // E "Se ela estiver vinculada a uma das atividades já cadastradas, ótimo, senão o sistema deve proporcionar uma forma inteligente de fazer essa vinculação."
      return !isLinkedToCurrent;
    });
  }, [pgcTasks, pgcEntregas, calendarViewMode, calendarDate]);
  const allUnidades = useMemo(() => {
    const fixed = ['CLC', 'Assistência Estudantil'];
    const dbUnidades = unidades.map(u => u.nome);
    return Array.from(new Set([...fixed, ...dbUnidades]));
  }, [unidades]);
  // Auditoria PGC - Heatmap de lacunas de registro
  const pgcAudit = useMemo(() => {
    const now = new Date();
    const workDays = getMonthWorkDays(currentYear, currentMonth);
    const gaps: Date[] = [];
    workDays.forEach(day => {
      // Ignorar dias futuros
      if (day > now) return;
      const dayStr = formatDateLocalISO(day);
      const hasActivity = atividadesPGC.some(a => {
        const start = a.data_inicio.split('T')[0];
        const end = a.data_fim?.split('T')[0] || start;
        return dayStr >= start && dayStr <= end;
      });
      const isAfastado = afastamentos.some(af => {
        const start = af.data_inicio.split('T')[0];
        const end = af.data_fim.split('T')[0];
        return dayStr >= start && dayStr <= end;
      });
      if (!hasActivity && !isAfastado) gaps.push(new Date(day));
    });
    return { gaps, totalWorkDays: workDays.length };
  }, [atividadesPGC, afastamentos]);
  const pgdStatus = useMemo(() => {
    const planKey = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
    const currentPlan = planosTrabalho.find(p => p.mes_ano === planKey);
    const planItems = currentPlan?.itens || [];
    const entregaStatus = planItems.map((item, index) => {
      const entregaEntity = pgcEntregas.find(e => e.entrega === item.entrega);
      const entregaId = entregaEntity?.id;
      const tarefasCount = entregaId ? pgcTasks.filter(t => t.entregas_relacionadas?.includes(entregaId)).length : 0;
      const registrosCount = entregaId ? atividadesPGC.filter(a => a.entrega_id === entregaId).length : 0;
      return {
        key: `${index}-${item.entrega}`,
        entrega: item.entrega,
        unidade: item.unidade,
        percentual: item.percentual,
        entregaId,
        tarefasCount,
        registrosCount
      };
    });
    const entregaIds = new Set(
      entregaStatus
        .map(s => s.entregaId)
        .filter((id): id is string => !!id)
    );
    const scopeActivities = atividadesPGC.filter(a => {
      if (entregaIds.size === 0) return true;
      return entregaIds.has(a.entrega_id);
    });
    const workDaysInMonth = getMonthWorkDays(currentYear, currentMonth);
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    const isCurrentMonth = now.getFullYear() === currentYear && now.getMonth() === currentMonth;
    const consideredWorkDays = workDaysInMonth.filter(day => {
      if (!isCurrentMonth) return true;
      return day <= now;
    });
    const expectedDays = consideredWorkDays.filter(day => {
      const dayStr = formatDateLocalISO(day);
      const isAfastado = afastamentos.some(af => {
        const start = af.data_inicio.split('T')[0];
        const end = af.data_fim.split('T')[0];
        return dayStr >= start && dayStr <= end;
      });
      return !isAfastado;
    });
    const volumeByDayMap = new Map<string, number>();
    scopeActivities.forEach((a) => {
      const startIso = (a.data_inicio || '').split('T')[0];
      const endIso = (a.data_fim || a.data_inicio || '').split('T')[0];
      if (!startIso) return;
      const cursor = new Date(`${startIso}T00:00:00`);
      const end = new Date(`${endIso}T00:00:00`);
      if (isNaN(cursor.getTime()) || isNaN(end.getTime())) return;
      while (cursor <= end) {
        if (cursor.getFullYear() === currentYear && cursor.getMonth() === currentMonth) {
          const dayStr = formatDateLocalISO(cursor);
          volumeByDayMap.set(dayStr, (volumeByDayMap.get(dayStr) || 0) + 1);
        }
        cursor.setDate(cursor.getDate() + 1);
      }
    });
    const volumeByDay = expectedDays.map((day) => {
      const dayStr = formatDateLocalISO(day);
      return {
        dayStr,
        label: day.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }),
        volume: volumeByDayMap.get(dayStr) || 0
      };
    });
    const workedDays = volumeByDay.filter(d => d.volume > 0);
    const notWorkedDays = volumeByDay.filter(d => d.volume === 0);
    const coveragePct = expectedDays.length > 0
      ? Math.round((workedDays.length / expectedDays.length) * 100)
      : 100;
    const maxVolume = Math.max(1, ...volumeByDay.map(d => d.volume));
    return {
      hasPlan: !!currentPlan,
      planItemsCount: planItems.length,
      totalWorkDaysInMonth: workDaysInMonth.length,
      expectedDaysCount: expectedDays.length,
      workedDaysCount: workedDays.length,
      notWorkedDaysCount: notWorkedDays.length,
      coveragePct,
      maxVolume,
      volumeByDay,
      notWorkedDays,
      entregasSemVinculo: entregaStatus.filter(s => s.tarefasCount === 0),
      entregasSemRegistros: entregaStatus.filter(s => s.registrosCount === 0),
      entregasSemCadastro: entregaStatus.filter(s => !s.entregaId)
    };
  }, [planosTrabalho, currentYear, currentMonth, pgcEntregas, pgcTasks, atividadesPGC, afastamentos]);

  const currentUIContext = useMemo(() => {
    return {
      activeModule,
      viewMode,
      selectedTask: selectedTask ? {
        id: selectedTask.id,
        titulo: selectedTask.titulo,
        area_tematica: selectedTask.area_tematica,
        status: selectedTask.status,
        prioridade: selectedTask.prioridade,
        data_limite: selectedTask.data_limite,
        responsavel: selectedTask.responsavel || (selectedTask as any).responsavel_nome,
        descricao: selectedTask.descricao || selectedTask.notas,
        solucao_sugerida: selectedTask.solucao_sugerida || selectedTask.auto_resumo_executivo,
        processo_sei: selectedTask.processo_sei || undefined,
        tags: selectedTask.tags || [],
        pool_dados: selectedTask.pool_dados?.map(p => ({
          id: p.id,
          nome: p.nome || (p as any).titulo || 'Anexo',
          tipo: p.tipo || 'arquivo',
          valor: p.valor,
          resumo: (p as any).resumo || (p as any).descricao || undefined,
        })) || [],
        plano_acao: selectedTask.plano_acao?.map(p => ({
          item: p.item,
          concluido: !!p.concluido,
          responsavel: p.responsavel,
        })) || [],
        acompanhamento: selectedTask.acompanhamento?.slice(-5).map(a => ({
          data: a.data,
          nota: a.nota,
          autor: a.autor,
        })) || [],
      } : null,
      taskModalMode: selectedTask ? taskModalMode : null,
      activeFerramenta,
      searchTerm: searchTerm || undefined,
    };
  }, [activeModule, viewMode, selectedTask, taskModalMode, activeFerramenta, searchTerm]);

  const isDarkTheme = themeMode === 'dark' || (themeMode === 'system' && prefersDark);
  const appBgClass = isDarkTheme ? 'bg-[#0f172a] text-[#f8fafc]' : 'bg-[#f9fafb] text-on-surface';
  const loginPanelClass = isDarkTheme
    ? 'bg-slate-900 border-white/10 shadow-[0_30px_60px_rgba(0,0,0,0.55)]'
    : 'bg-white border-border-grid shadow-soft-touch';
  const loginLogoTileClass = isDarkTheme
    ? 'bg-white border-white/10'
    : 'bg-surface border-border-grid';
  const loginTitleClass = isDarkTheme ? 'text-slate-100' : 'text-slate-900';
  const loginMutedClass = isDarkTheme ? 'text-slate-400' : 'text-slate-500';
  const loginSubtleClass = isDarkTheme ? 'text-slate-500' : 'text-slate-400';
  const loginPrimaryButtonClass = isDarkTheme
    ? 'bg-slate-100 text-slate-950 hover:bg-white focus-visible:ring-slate-100'
    : 'bg-slate-900 text-white hover:bg-slate-800 focus-visible:ring-slate-900';
  const loginCheckboxClass = isDarkTheme
    ? 'bg-slate-950 border-slate-700 text-slate-100 focus:ring-slate-100'
    : 'bg-white border-border-grid text-slate-900 focus:ring-slate-900';
  const loadingSpinnerClass = isDarkTheme
    ? 'border-slate-700 border-t-slate-100'
    : 'border-slate-200 border-t-slate-900';
  if (authLoading) {
    return (
      <div className={`min-h-screen flex items-center justify-center ${appBgClass}`}>
        <div className="flex flex-col items-center gap-4">
          <div className={`h-12 w-12 animate-spin rounded-none border-4 ${loadingSpinnerClass}`}></div>
          <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">Hermes está carregando...</p>
        </div>
      </div>
    );
  }
  if (!user) {
    return (
      <div className={`min-h-screen flex flex-col items-center justify-center p-6 transition-colors ${appBgClass}`}>
        <div className={`w-full max-w-md animate-in zoom-in-95 border p-8 text-center md:p-10 rounded-none ${loginPanelClass}`}>
          <div className={`mx-auto mb-8 flex h-20 w-20 items-center justify-center border p-3 rounded-none ${loginLogoTileClass}`}>
            <img src="/logo.png" alt="Hermes" className="h-full w-full object-contain" />
          </div>
          <h1 className={`mb-2 font-mono text-3xl font-black uppercase tracking-tight ${loginTitleClass}`}>Hermes</h1>
          <p className={`mb-10 text-sm font-medium leading-relaxed ${loginMutedClass}`}>
            Bem-vindo ao seu ecossistema de produtividade e gestão à vista.
          </p>
          <button
            onClick={handleLogin}
            className={`flex w-full items-center justify-center gap-4 rounded-none py-4 font-mono text-[10px] font-black uppercase tracking-[0.2em] transition-all active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${isDarkTheme ? 'focus-visible:ring-offset-slate-900' : 'focus-visible:ring-offset-white'} ${loginPrimaryButtonClass}`}
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.908 3.152-2.112 4.076-1.028.724-2.48 1.408-5.728 1.408-5.104 0-9.272-4.144-9.272-9.232s4.168-9.232 9.272-9.232c2.808 0 4.58 1.104 5.612 2.056l2.312-2.312c-1.936-1.824-4.52-3.112-7.924-3.112-6.524 0-12 5.424-12 12s5.476 12 12 12c3.552 0 6.228-1.172 8.528-3.564 2.376-2.376 3.128-5.704 3.128-8.32 0-.824-.068-1.552-.2-2.224h-11.456z" />
            </svg>
            Entrar com Google
          </button>
          <div className="mt-6 flex items-center justify-center gap-3">
            <input
              type="checkbox"
              id="remember-me"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className={`h-4 w-4 cursor-pointer rounded-none ${loginCheckboxClass}`}
            />
            <label htmlFor="remember-me" className={`cursor-pointer select-none font-mono text-[10px] font-black uppercase tracking-widest transition-colors ${loginSubtleClass} ${isDarkTheme ? 'hover:text-slate-200' : 'hover:text-slate-700'}`}>
              Mantenha-me conectado
            </label>
          </div>
          <p className={`mt-8 font-mono text-[8px] font-black uppercase tracking-widest ${loginSubtleClass}`}>Secure Authentication via Firebase</p>
        </div>
      </div>
    );
  }
  if (isInitialDataLoading) {
    return (
      <div className={`min-h-screen flex items-center justify-center ${appBgClass}`}>
        <div className="flex flex-col items-center gap-4">
          <div className={`h-12 w-12 animate-spin rounded-none border-4 ${loadingSpinnerClass}`}></div>
          <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">Carregando seus dados...</p>
        </div>
      </div>
    );
  }
  const sidebarClass = isDarkTheme
    ? 'bg-[#111827] text-[#f8fafc] border-r border-white/10'
    : 'bg-white/95 text-on-surface border-r border-border-grid shadow-[1px_0_0_rgba(21,28,39,0.03)]';
  const headerClass = isDarkTheme
    ? 'bg-[#111827]/90 border-white/10'
    : 'bg-white/85 border-b border-border-grid shadow-[0_1px_0_rgba(21,28,39,0.03)]';
  const mutedTextClass = isDarkTheme ? 'text-slate-500' : 'text-slate-400';
  const subtleBorderClass = isDarkTheme ? 'border-white/10' : 'border-border-grid';
  const inputSurfaceClass = isDarkTheme
    ? 'bg-slate-900 border-white/10 text-white placeholder:text-slate-600'
    : 'bg-white border-border-grid text-on-surface placeholder:text-slate-400';
  const isStrategySplitCopilot = viewMode === 'strategy' && isCopilotoOpen && copilotoMode === 'estrategia';
  const closeCopiloto = () => {
    setIsCopilotoOpen(false);
    setCopilotoAutoStartMic(false);
    setCopilotoMode('default');
    setCopilotoInitialPrompt(null);
  };
  const handleCopilotoOpenTask = async (id: string) => {
    const task = tarefas.find(t => t.id === id);
    if (task) {
      setSelectedTask(task);
      setTaskModalMode('execute');
    } else {
      const snap = await getDoc(doc(db, 'tarefas', id));
      if (snap.exists()) {
        setSelectedTask({ id: snap.id, ...snap.data() } as any);
        setTaskModalMode('execute');
      }
    }
  };
  const handleCopilotoOpenTool = (tool: string, id: string) => {
    setIsCopilotoOpen(false);
    setCopilotoMode('default');
    setActiveModule('acoes');
    setViewMode('ferramentas');
    if (tool === 'diagnostico') {
      setActiveFerramenta('diagnostico');
      setInitialDiagnosisId(id);
    }
  };

  const handleVoiceUICommand = async (command: string, params: any) => {
    console.log('[Hermes Voice UI Command]', command, params);
    if (command === 'navegar_sistema') {
      // Ao navegar para qualquer módulo ou página inicial, fecha o modal de detalhamento de ação se estiver aberto
      setSelectedTask(null);

      const mod = String(params?.modulo || '').toLowerCase().trim();
      let label = 'Dashboard';
      if (mod.includes('finan')) {
        setActiveModule('financeiro');
        setViewMode('finance');
        label = 'Financeiro';
      } else if (mod.includes('saud') || mod.includes('saú')) {
        setActiveModule('saude');
        setViewMode('saude');
        label = 'Saúde';
      } else if (mod.includes('serv')) {
        setActiveModule('servicos');
        setViewMode('services');
        label = 'Serviços';
      } else if (mod.includes('estrat') || mod.includes('okr')) {
        setActiveModule('estrategia');
        setViewMode('strategy');
        label = 'Estratégia';
      } else if (mod.includes('godmode') || mod.includes('god')) {
        setActiveModule('estrategia');
        setViewMode('godmode');
        label = 'Godmode';
      } else if (mod.includes('conhec') || mod.includes('wiki')) {
        setActiveModule('acoes');
        setViewMode('knowledge');
        label = 'Conhecimento';
      } else if (mod.includes('contat') || mod.includes('pess')) {
        setActiveModule('acoes');
        setViewMode('contacts');
        label = 'Contatos';
      } else if (mod.includes('rag') || mod.includes('area') || mod.includes('área')) {
        setActiveModule('acoes');
        setViewMode('rag-bases');
        label = 'Áreas Temáticas';
      } else if (mod.includes('ferram')) {
        setActiveModule('acoes');
        setViewMode('ferramentas');
        label = 'Ferramentas';
      } else if (mod.includes('licit') || mod.includes('licitacao') || mod.includes('licitação')) {
        setActiveModule('acoes');
        setViewMode('licitacoes');
        label = 'Licitações';
      } else if (mod.includes('assist')) {
        setActiveModule('acoes');
        setViewMode('assistencia');
        label = 'Assistência';
      } else if (mod.includes('pgd') || mod.includes('pgc')) {
        setActiveModule('acoes');
        setViewMode('pgc');
        label = 'PGD';
      } else if (mod.includes('conclu')) {
        setActiveModule('acoes');
        setViewMode('concluidas');
        label = 'Concluídas';
      } else if (mod.includes('acoe') || mod.includes('ações') || mod.includes('galer') || mod.includes('lista')) {
        setActiveModule('acoes');
        setViewMode('gallery');
        label = 'Ações';
      } else {
        // Página Inicial / Dashboard / Home
        setActiveModule('dashboard');
        setViewMode('dashboard');
        label = 'Página Inicial';
      }
      showToast?.(`Navegando: ${label}`, 'info');
    } else if (command === 'fechar_detalhe_acao' || command === 'fechar_modal') {
      setSelectedTask(null);
      showToast?.('Detalhamento da ação fechado.', 'info');
    } else if (command === 'abrir_detalhe_acao') {
      const rawTarget = String(params?.id_ou_termo || '').trim();
      if (!rawTarget) return;

      // Se estivemos fora do módulo de ações, vamos abrir o módulo de ações para contexto
      if (activeModule !== 'acoes' && activeModule !== 'dashboard') {
        setActiveModule('acoes');
      }

      const cleanedTarget = rawTarget
        .toLowerCase()
        .replace(/^(abrir|ver|detalhar|mostrar|acesse|acessar|ação|acao|tarefa|sobre)\s+/gi, '')
        .trim();

      const targetLower = cleanedTarget || rawTarget.toLowerCase();

      // 1. Procurar por ID exato ou título idêntico
      let matchedTask = tarefas.find(t => t.id === rawTarget || t.id === cleanedTarget || t.titulo.toLowerCase() === targetLower);

      // 2. Procurar por correspondência parcial contínua de título
      if (!matchedTask) {
        matchedTask = tarefas.find(t => t.titulo.toLowerCase().includes(targetLower));
      }

      // 3. Procurar por correspondência de palavras-chave (token matching)
      if (!matchedTask) {
        const keywords = targetLower.split(/\s+/).filter(w => w.length > 2);
        if (keywords.length > 0) {
          matchedTask = tarefas.find(t => {
            const titleLower = t.titulo.toLowerCase();
            return keywords.every(kw => titleLower.includes(kw));
          });
        }
        if (!matchedTask && keywords.length > 1) {
          matchedTask = tarefas.find(t => {
            const titleLower = t.titulo.toLowerCase();
            return keywords.some(kw => titleLower.includes(kw));
          });
        }
      }

      if (matchedTask) {
        setSelectedTask(matchedTask);
        setTaskModalMode('execute');
        showToast?.(`Abrindo ação: ${matchedTask.titulo}`, 'info');
        return;
      }

      // 4. Se não achou no estado local, busca no Firestore por ID
      try {
        const snap = await getDoc(doc(db, 'tarefas', rawTarget));
        if (snap.exists()) {
          const tData = { id: snap.id, ...snap.data() } as Tarefa;
          setSelectedTask(tData);
          setTaskModalMode('execute');
          showToast?.(`Abrindo ação: ${tData.titulo}`, 'info');
        } else {
          showToast?.(`Ação "${rawTarget}" não foi encontrada.`, 'warning');
        }
      } catch (e) {
        console.error('[Hermes Voice UI] Erro ao buscar tarefa no Firestore:', e);
      }
    } else if (command === 'abrir_ferramenta') {
      const toolId = String(params?.ferramenta_id || '').toLowerCase();
      setActiveModule('acoes');
      setViewMode('ferramentas');
      if (toolId) {
        setActiveFerramenta(toolId as any);
      }
    } else if (command === 'filtrar_acoes') {
      if (params?.termo_busca !== undefined) {
        setSearchTerm(String(params.termo_busca));
      }
      if (params?.status !== undefined) {
        setStatusFilter([String(params.status)]);
      }
    }
  };

  return (
    <>
      <div className={`min-h-screen flex flex-col md:flex-row relative transition-colors ${appBgClass}`}>
        {/* Pop-up de Notificação */}
        {activePopup && (
          <div className={`fixed bottom-8 left-4 right-4 md:left-8 md:right-auto z-[200] max-w-sm ml-auto mr-auto md:ml-0 md:mr-0 rounded-none border overflow-hidden animate-in slide-in-from-bottom-12 duration-500 ${isDarkTheme ? 'bg-slate-900 border-white/10 shadow-[0_30px_60px_rgba(0,0,0,0.7)]' : 'bg-white border-border-grid shadow-[0_30px_60px_rgba(0,0,0,0.25)]'}`}>
            <div className={`h-2 w-full ${activePopup.type === 'success' ? 'bg-emerald-500' :
              activePopup.type === 'warning' ? 'bg-amber-500' :
                activePopup.type === 'error' ? 'bg-rose-500' : 'bg-blue-600'
              }`} />
            <div className="p-8">
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-black uppercase tracking-[0.2em] ${isDarkTheme ? 'text-slate-100' : 'text-slate-900'}`}>{activePopup.title}</span>
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse"></span>
                </div>
                <button onClick={() => setActivePopup(null)} className={`transition-colors p-1 ${isDarkTheme ? 'text-slate-400 hover:text-slate-200' : 'text-slate-300 hover:text-slate-600'}`}>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
              <p className={`text-[11px] leading-relaxed font-bold ${isDarkTheme ? 'text-slate-300' : 'text-slate-500'}`}>{activePopup.message}</p>
              <div className="mt-6 flex gap-3">
                <button
                  onClick={() => setActivePopup(null)}
                  className={`flex-1 px-5 py-3 rounded-none text-[9px] font-black uppercase tracking-widest transition-all ${isDarkTheme ? 'bg-slate-800 text-slate-300 hover:bg-slate-700' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                >
                  Entendido
                </button>
                {activePopup.link && (
                  <button
                    onClick={() => {
                      handleNotificationNavigate(activePopup.link!);
                      setActivePopup(null);
                    }}
                    className="flex-1 px-5 py-3 bg-slate-900 text-white rounded-none text-[9px] font-black uppercase tracking-widest transition-all hover:bg-slate-800 shadow-lg shadow-slate-200"
                  >
                    Ver Agora
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
        {/* Sidebar Desktop */}
        <aside className={`hidden md:flex ${isSidebarRetracted ? 'w-20' : 'w-80'} ${sidebarClass} flex-col h-screen sticky top-0 overflow-y-auto shrink-0 z-50 transition-all duration-300`}>
          <div className={`px-4 py-6 flex flex-col h-full ${isSidebarRetracted ? 'gap-6 items-center pt-8' : 'gap-8'}`}>
            <div
              className={`flex items-center gap-4 cursor-pointer hover:opacity-80 transition-opacity ${isSidebarRetracted ? 'flex-col' : ''}`}
              onClick={() => setIsSidebarRetracted(!isSidebarRetracted)}
            >
              <img src="/logo.png" alt="Hermes" className={`${isSidebarRetracted ? 'w-12 h-12' : 'w-11 h-11'} object-contain ${isDarkTheme ? 'bg-white rounded p-1' : ''}`} />
              {!isSidebarRetracted && (
                <div>
                  <h1 className="text-xl font-black tracking-tight font-mono uppercase">Hermes</h1>
                </div>
              )}
            </div>
            <nav className="flex flex-col gap-1.5">
              {[
                { id: 'dashboard', label: 'Dashboard', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>, active: viewMode === 'dashboard', onClick: () => { setActiveModule('dashboard'); setViewMode('dashboard'); } },
                { id: 'acoes', label: 'Ações', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>, active: activeModule === 'acoes' && (viewMode === 'gallery' || viewMode === 'pgc' || viewMode === 'licitacoes' || viewMode === 'assistencia' || viewMode === 'concluidas'), onClick: () => { setActiveModule('acoes'); setViewMode('gallery'); } },
                { id: 'servicos', label: 'Serviços', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>, active: activeModule === 'servicos' && viewMode === 'services', onClick: () => { setActiveModule('servicos'); setViewMode('services'); } },
                { id: 'finance', label: 'Financeiro', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>, active: activeModule === 'financeiro', onClick: () => { setActiveModule('financeiro'); setViewMode('finance'); } },
                { id: 'saude', label: 'Saúde', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>, active: activeModule === 'saude', onClick: () => { setActiveModule('saude'); setViewMode('saude'); } },
                { id: 'strategy', label: 'Estratégia', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 6.75V15m6-6v8.25M4.5 19.5h15M6 19.5V4.5h12v15" /></svg>, active: activeModule === 'estrategia' && viewMode === 'strategy', onClick: () => { setActiveModule('estrategia'); setViewMode('strategy'); } },
                { id: 'godmode', label: 'Godmode', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>, active: viewMode === 'godmode', onClick: () => { setActiveModule('estrategia'); setViewMode('godmode'); } },
                { id: 'contacts', label: 'Contatos', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>, active: viewMode === 'contacts', onClick: () => { setActiveModule('acoes'); setViewMode('contacts'); } },
                { id: 'conhecimento', label: 'Conhecimento', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>, active: viewMode === 'knowledge', onClick: () => { setActiveModule('acoes'); setViewMode('knowledge'); } },
                { id: 'rag-bases', label: 'Áreas Temáticas', icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>, active: viewMode === 'rag-bases', onClick: () => { setActiveModule('acoes'); setViewMode('rag-bases'); } },
              ].map(item => (
                <button
                  key={item.id}
                  onClick={item.onClick}
                  className={`flex items-center gap-3 px-4 py-3 rounded-none border-b border-transparent transition-all duration-200 group ${item.active ? (isDarkTheme ? 'bg-white/10 text-white' : 'bg-primary-tactile/10 text-primary-tactile border-primary-tactile') : (isDarkTheme ? 'text-slate-400 hover:text-white hover:bg-white/[0.03]' : 'text-slate-500 hover:text-primary-tactile hover:bg-primary-tactile/5')} ${isSidebarRetracted ? 'justify-center' : ''}`}
                  title={isSidebarRetracted ? item.label : ''}
                >
                  <div className={`${item.active ? (isDarkTheme ? 'text-white' : 'text-primary-tactile') : 'group-hover:scale-105 transition-transform duration-200'}`}>
                    {item.icon}
                  </div>
                  {!isSidebarRetracted && <span className="text-[11px] font-black uppercase tracking-widest font-mono">{item.label}</span>}
                </button>
              ))}
            </nav>
            <div className="mt-auto flex flex-col gap-4">
              {!isSidebarRetracted && (
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-1 grid grid-cols-3 gap-1">
                  <button
                    onClick={() => setThemeMode('system')}
                    className={`flex-1 px-3 py-2 rounded-xl text-[9px] font-black uppercase tracking-[0.18em] transition-all ${themeMode === 'system' ? 'bg-white text-slate-900' : 'text-slate-400 hover:text-white'}`}
                  >
                    Sistema
                  </button>
                  <button
                    onClick={() => setThemeMode('light')}
                    className={`flex-1 px-3 py-2 rounded-xl text-[9px] font-black uppercase tracking-[0.18em] transition-all ${themeMode === 'light' ? 'bg-white text-slate-900' : 'text-slate-400 hover:text-white'}`}
                  >
                    Light
                  </button>
                  <button
                    onClick={() => setThemeMode('dark')}
                    className={`flex-1 px-3 py-2 rounded-xl text-[9px] font-black uppercase tracking-[0.18em] transition-all ${themeMode === 'dark' ? 'bg-white text-slate-900' : 'text-slate-400 hover:text-white'}`}
                  >
                    Dark
                  </button>
                </div>
              )}
              <div className={`flex items-center gap-3 bg-white/[0.03] p-3 rounded-2xl border border-white/10 ${isSidebarRetracted ? 'flex-col gap-4' : ''}`}>
                {isSidebarRetracted ? (
                  <>
                    <div
                      className="w-10 h-10 rounded-xl bg-slate-800 flex items-center justify-center font-black text-[10px] text-white border border-white/10"
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
                      <img src={user.photoURL} alt="Profile" className="w-10 h-10 rounded-xl border border-white/10" />
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
            </div>
          </div>
        </aside>
        {/* Conteúdo Principal */}
        <div className="flex-1 flex flex-col relative min-h-screen overflow-hidden">
          <>
            <header className={`sticky top-0 z-40 backdrop-blur-xl transition-colors ${headerClass} border-b`}>
              <div className="w-full px-4 md:px-8 py-3 md:py-4">
                {/* Mobile Header */}
                <div className="flex md:hidden items-center justify-between">
                  <div className="flex items-center gap-4">
                    <button
                      onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                      className={`p-2 rounded-lg transition-all active:scale-95 ${isDarkTheme ? 'text-slate-200 hover:bg-white/5' : 'text-slate-700 hover:bg-slate-100'}`}
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
                      <img src="/logo.png" alt="Hermes" className={`w-9 h-9 object-contain ${isDarkTheme ? 'bg-white rounded p-1' : ''}`} />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <SpeedDialMenu
                      notifications={notifications}
                      isSyncing={isSyncing}
                      isNotificationCenterOpen={isNotificationCenterOpen}
                      onOpenCopiloto={() => setIsCopilotoOpen(true)}
                      onOpenNotes={() => setIsQuickNoteModalOpen(true)}
                      onOpenShopping={() => { setIsShoppingAIModalOpen(true); setIsMobileMenuOpen(false); }}
                      onOpenTranscription={() => { setIsTranscriptionAIModalOpen(true); setIsMobileMenuOpen(false); }}
                      onOpenWhatsAppTranscription={() => {
                        setActiveModule('acoes');
                        setViewMode('ferramentas');
                        setActiveFerramenta('batch_transcription');
                        setIsMobileMenuOpen(false);
                      }}
                      onOpenMeetingTranscription={() => {
                        setActiveModule('acoes');
                        setViewMode('ferramentas');
                        setActiveFerramenta('meeting_transcription');
                        setIsMobileMenuOpen(false);
                      }}
                      onOpenBrainstorming={() => {
                        setActiveModule('acoes');
                        setViewMode('ferramentas');
                        setActiveFerramenta('brainstorming');
                        setIsMobileMenuOpen(false);
                      }}
                      onOpenPopManager={() => {
                        setActiveModule('acoes');
                        setViewMode('ferramentas');
                        setActiveFerramenta('pop_manager');
                        setIsMobileMenuOpen(false);
                      }}
                      onOpenSipacTracking={() => {
                        setActiveModule('acoes');
                        setViewMode('ferramentas');
                        setActiveFerramenta('sipac_tracking');
                        setIsMobileMenuOpen(false);
                      }}
                      onOpenMonitorPaginas={() => {
                        setActiveModule('acoes');
                        setViewMode('ferramentas');
                        setActiveFerramenta('monitor_paginas');
                        setIsMobileMenuOpen(false);
                      }}
                      onOpenLongTranscription={() => {
                        setActiveModule('acoes');
                        setViewMode('ferramentas');
                        setActiveFerramenta('long_transcription');
                        setIsMobileMenuOpen(false);
                      }}
                      onOpenBatchTranscription={() => {
                        setActiveModule('acoes');
                        setViewMode('ferramentas');
                        setActiveFerramenta('batch_transcription');
                        setIsMobileMenuOpen(false);
                      }}
                      onToggleNotifications={() => setIsNotificationCenterOpen(prev => !prev)}
                      onSync={handleSync}
                      onOpenSettings={() => setIsSettingsModalOpen(true)}
                      onCloseNotifications={() => setIsNotificationCenterOpen(false)}
                      onMarkAsRead={handleMarkNotificationRead}
                      onDismiss={handleDismissNotification}
                      onUpdateOverdue={handleUpdateOverdueTasks}
                      onNavigate={handleNotificationNavigate}
                      onCreateAction={() => setIsCreateModalOpen(true)}
                      isDark={isDarkTheme}
                    />
                    {viewMode !== 'ferramentas' && viewMode !== 'knowledge' && viewMode !== 'rag-bases' && viewMode !== 'saude' && viewMode !== 'finance' && viewMode !== 'dashboard' && viewMode !== 'services' && viewMode !== 'strategy' && viewMode !== 'godmode' && (
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
                {/* Opções de Sub-módulo para Mobile (Ações / PGD / Concluídas) */}
                {(viewMode === 'gallery' || viewMode === 'licitacoes' || viewMode === 'assistencia' || viewMode === 'pgc' || viewMode === 'concluidas') && activeModule === 'acoes' && !(selectedTask && (taskModalMode === 'execute' || (taskModalMode === 'default' && selectedTask.area_tematica === 'CLC'))) && (
                  <div className="flex md:hidden items-center gap-1 mt-3 pt-3 border-t animate-in slide-in-from-top-2 duration-300 border-border-grid">
                    <button
                      onClick={() => {
                        setViewMode('gallery');
                        setSearchTerm('');
                      }}
                      className={`flex-1 py-1.5 rounded-none text-xs font-black uppercase tracking-widest transition-all font-mono ${(viewMode === 'gallery' || viewMode === 'licitacoes' || viewMode === 'assistencia') ? 'bg-slate-900 text-white' : isDarkTheme ? 'text-slate-300 hover:bg-white/10' : 'text-slate-500 hover:bg-slate-200/50'}`}
                    >
                      Ações
                    </button>
                    <button
                      onClick={() => setViewMode('pgc')}
                      className={`flex-1 py-1.5 rounded-none text-xs font-black uppercase tracking-widest transition-all font-mono ${viewMode === 'pgc' ? 'bg-slate-900 text-white' : isDarkTheme ? 'text-slate-300 hover:bg-white/10' : 'text-slate-500 hover:bg-slate-200/50'}`}
                    >
                      PGD
                    </button>
                    <button
                      onClick={() => { setViewMode('concluidas'); setCompletedLimit(10); }}
                      className={`flex-1 py-1.5 rounded-none text-xs font-black uppercase tracking-widest transition-all font-mono ${viewMode === 'concluidas' ? 'bg-slate-900 text-white' : isDarkTheme ? 'text-slate-300 hover:bg-white/10' : 'text-slate-500 hover:bg-slate-200/50'}`}
                    >
                      Concluídas
                    </button>
                  </div>
                )}
                {/* Opções de Financeiro para Mobile */}
                {viewMode === 'finance' && (
                  <div className="flex flex-col md:hidden gap-3 mt-3 pt-3 border-t border-slate-100 animate-in slide-in-from-top-2 duration-300">
                    <div className="flex items-center gap-2">
                      <div className={`flex-1 flex p-1 rounded-xl border ${isDarkTheme ? 'bg-slate-900 border-slate-800' : 'bg-slate-100 border-slate-200'}`}>
                        <button
                          onClick={() => setFinanceActiveTab('dashboard')}
                          className={`flex-1 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'dashboard' ? (isDarkTheme ? 'bg-slate-800 text-white shadow-sm border border-slate-700' : 'bg-white text-slate-900 shadow-sm border border-slate-100') : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Visão Geral
                        </button>
                        <button
                          onClick={() => setFinanceActiveTab('income')}
                          className={`flex-1 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'income' ? (isDarkTheme ? 'bg-slate-800 text-white shadow-sm border border-slate-700' : 'bg-white text-slate-900 shadow-sm border border-slate-100') : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Entrada
                        </button>
                        <button
                          onClick={() => setFinanceActiveTab('expense')}
                          className={`flex-1 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'expense' ? (isDarkTheme ? 'bg-slate-800 text-white shadow-sm border border-slate-700' : 'bg-white text-slate-900 shadow-sm border border-slate-100') : 'text-slate-400 hover:text-slate-600'}`}
                        >
                          Saída
                        </button>
                      </div>
                      <button
                        onClick={() => setIsFinanceSettingsOpen(!isFinanceSettingsOpen)}
                        className={`p-2.5 rounded-xl transition-all border ${isFinanceSettingsOpen ? (isDarkTheme ? 'bg-blue-600 text-white border-blue-600 shadow-lg' : 'bg-slate-900 text-white border-slate-900 shadow-lg') : (isDarkTheme ? 'bg-slate-900 text-slate-400 border-slate-800 hover:bg-slate-800 hover:text-white shadow-sm' : 'bg-white text-slate-400 border-slate-200 hover:bg-slate-50 hover:text-slate-900 shadow-sm')}`}
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                      </button>
                    </div>
                    <div className={`flex items-center justify-between rounded-xl border shadow-sm overflow-hidden h-11 ${isDarkTheme ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                      <button
                        onClick={() => {
                          const newMonth = currentMonth === 0 ? 11 : currentMonth - 1;
                          const newYear = currentMonth === 0 ? currentYear - 1 : currentYear;
                          setCurrentMonth(newMonth);
                          setCurrentYear(newYear);
                        }}
                        className={`px-4 h-full flex items-center transition-all border-r ${isDarkTheme ? 'hover:bg-slate-800 text-slate-400 hover:text-white border-slate-800' : 'hover:bg-slate-50 text-slate-400 hover:text-slate-900 border-slate-100'}`}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" /></svg>
                      </button>
                      <div className="px-4 text-center">
                        <div className={`text-xs font-black capitalize tracking-tight ${isDarkTheme ? 'text-white' : 'text-slate-900'}`}>
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
                        className={`px-4 h-full flex items-center transition-all border-l ${isDarkTheme ? 'hover:bg-slate-800 text-slate-400 hover:text-white border-slate-800' : 'hover:bg-slate-50 text-slate-400 hover:text-slate-900 border-slate-100'}`}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                      </button>
                    </div>
                  </div>
                )}
                {/* Desktop Header */}
                <div className="hidden md:flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
                  <div className="flex min-w-[420px] flex-1 items-center gap-6">
                    <div className="flex items-center gap-3">
                      {/* Botão de voltar removido pois agora temos sidebar */}
                      <div
                        onClick={() => { setActiveModule('dashboard'); setViewMode('dashboard'); }}
                        className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity"
                      >
                        <h1 className={`text-xl font-black tracking-tight uppercase font-mono ${isDarkTheme ? 'text-slate-100' : 'text-slate-900'}`}>
                          {viewMode === 'services' ? 'Serviços' :
                            viewMode === 'rag-bases' ? 'Áreas Temáticas' :
                              viewMode === 'knowledge' ? 'Conhecimento' :
                                viewMode === 'ferramentas' ? 'Ferramentas' :
                                  viewMode === 'godmode' ? 'Godmode' :
                                  activeModule === 'dashboard' ? 'Dashboard' :
                                      activeModule === 'acoes' ? 'Ações' :
                                        activeModule === 'financeiro' ? 'Financeiro' :
                                        activeModule === 'saude' ? 'Saúde' :
                                          activeModule === 'estrategia' ? 'Estratégia' : 'Hermes'}
                        </h1>
                      </div>
                    </div>
                    {viewMode !== 'ferramentas' && viewMode !== 'knowledge' && viewMode !== 'rag-bases' && viewMode !== 'services' && viewMode !== 'strategy' && viewMode !== 'godmode' && activeModule !== 'financeiro' && activeModule !== 'saude' && activeModule !== 'dashboard' && (
                      <nav className={`flex flex-wrap items-center gap-1`}>
                        <button
                          onClick={() => {
                            setViewMode('gallery');
                            setSearchTerm('');
                          }}
                          className={`px-4 py-1.5 rounded-none text-[10px] font-black uppercase tracking-widest transition-all font-mono ${viewMode === 'gallery' && !searchTerm ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-200/50'}`}
                        >
                          Ações
                        </button>
                        <button onClick={() => setViewMode('licitacoes')} className={`px-4 py-1.5 rounded-none text-[10px] font-black uppercase tracking-widest transition-all font-mono ${viewMode === 'licitacoes' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-200/50'}`}>Licitações</button>
                        <button onClick={() => setViewMode('assistencia')} className={`px-4 py-1.5 rounded-none text-[10px] font-black uppercase tracking-widest transition-all font-mono ${viewMode === 'assistencia' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-200/50'}`}>Assistência</button>
                        <button onClick={() => setViewMode('pgc')} className={`px-4 py-1.5 rounded-none text-[10px] font-black uppercase tracking-widest transition-all font-mono ${viewMode === 'pgc' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-200/50'}`}>PGD</button>
                        <button onClick={() => { setViewMode('concluidas'); setCompletedLimit(10); }} className={`px-4 py-1.5 rounded-none text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-1.5 font-mono ${viewMode === 'concluidas' ? 'bg-emerald-600 text-white' : 'text-slate-500 hover:bg-slate-200/50'}`}>
                          Concluídas
                          <span className={`text-[9px] font-black px-1.5 py-0.5 rounded-none ${viewMode === 'concluidas' ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-500'}`}>{stats.concluidas}</span>
                        </button>
                      </nav>
                    )}
                  </div>

                  {/* Área Temática Multi-Filter */}
                  {(viewMode === 'gallery' || viewMode === 'licitacoes' || viewMode === 'assistencia' || viewMode === 'concluidas') && activeModule === 'acoes' && knowledgeBases.length > 0 && (
                    <div className={`order-3 flex basis-full items-center gap-1.5 flex-wrap py-2 px-1 border-t ${isDarkTheme ? 'border-slate-800' : 'border-slate-100'}`}>
                      <span className={`text-[9px] font-mono font-black uppercase tracking-widest mr-1 ${isDarkTheme ? 'text-slate-500' : 'text-slate-400'}`}>Filtrar:</span>
                      {areaFilter.length > 0 && (
                        <button
                          onClick={() => setAreaFilter([])}
                          className={`flex items-center gap-1 px-2.5 py-1 rounded-none text-[9px] font-mono font-black uppercase tracking-widest transition-all border ${isDarkTheme ? 'border-slate-600 bg-slate-700 text-slate-300 hover:bg-slate-600' : 'border-slate-300 bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                        >
                          <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" /></svg>
                          Limpar
                        </button>
                      )}
                      {knowledgeBases.map(base => {
                        const isActive = areaFilter.includes(base.nome);
                        const baseColor = base.cor || '#6b7280';
                        return (
                          <button
                            key={base.id}
                            onClick={() => {
                              setAreaFilter(prev =>
                                prev.includes(base.nome)
                                  ? prev.filter(a => a !== base.nome)
                                  : [...prev, base.nome]
                              );
                            }}
                            className={`px-2.5 py-1 rounded-none text-[9px] font-mono font-black uppercase tracking-widest transition-all border ${isActive ? 'text-white border-transparent' : (isDarkTheme ? 'border-slate-700 text-slate-400 hover:border-slate-500' : 'border-slate-200 text-slate-500 hover:border-slate-400')}`}
                            style={isActive ? { backgroundColor: baseColor, borderColor: baseColor } : {}}
                          >
                            {isActive && <span className="inline-block w-1.5 h-1.5 rounded-full bg-white/70 mr-1.5 align-middle" />}
                            {base.nome}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Finance Controls */}
                  {viewMode === 'finance' && (
                    <div className="ml-auto flex items-center gap-4">
                      <div className={`flex p-1 rounded-xl border ${isDarkTheme ? 'bg-slate-900 border-slate-800' : 'bg-slate-100 border-slate-200'} gap-1`}>
                        <button
                          onClick={() => setFinanceActiveTab('dashboard')}
                          className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'dashboard' ? (isDarkTheme ? 'bg-slate-800 text-white shadow-sm border border-slate-700' : 'bg-white text-slate-900 shadow-sm border border-slate-100') : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'}`}
                        >
                          Visão Geral
                        </button>
                        <button
                          onClick={() => setFinanceActiveTab('income')}
                          className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'income' ? (isDarkTheme ? 'bg-slate-800 text-white shadow-sm border border-slate-700' : 'bg-white text-slate-900 shadow-sm border border-slate-100') : 'text-slate-500 hover:text-slate-750 dark:text-slate-400 dark:hover:text-slate-200'}`}
                        >
                          Entrada
                        </button>
                        <button
                          onClick={() => setFinanceActiveTab('expense')}
                          className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${financeActiveTab === 'expense' ? (isDarkTheme ? 'bg-slate-800 text-white shadow-sm border border-slate-700' : 'bg-white text-slate-900 shadow-sm border border-slate-100') : 'text-slate-500 hover:text-slate-750 dark:text-slate-400 dark:hover:text-slate-200'}`}
                        >
                          Saída
                        </button>
                      </div>
                      <div className={`flex items-center rounded-xl border shadow-sm overflow-hidden ${isDarkTheme ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                        <button
                          onClick={() => {
                            const newMonth = currentMonth === 0 ? 11 : currentMonth - 1;
                            const newYear = currentMonth === 0 ? currentYear - 1 : currentYear;
                            setCurrentMonth(newMonth);
                            setCurrentYear(newYear);
                          }}
                          className={`p-2 transition-all border-r ${isDarkTheme ? 'hover:bg-slate-800 text-slate-400 hover:text-white border-slate-800' : 'hover:bg-slate-50 text-slate-400 hover:text-slate-900 border-slate-100'}`}
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" /></svg>
                        </button>
                        <div className="px-3 text-center min-w-[100px]">
                          <div className={`text-[10px] font-black capitalize leading-none tracking-tight ${isDarkTheme ? 'text-white' : 'text-slate-900'}`}>
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
                          className={`p-2 transition-all border-l ${isDarkTheme ? 'hover:bg-slate-800 text-slate-400 hover:text-white border-slate-800' : 'hover:bg-slate-50 text-slate-400 hover:text-slate-900 border-slate-100'}`}
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                        </button>
                      </div>
                      <button
                        onClick={() => setIsFinanceSettingsOpen(!isFinanceSettingsOpen)}
                        className={`p-2 rounded-xl transition-all border ${isFinanceSettingsOpen ? (isDarkTheme ? 'bg-blue-600 text-white border-blue-600 shadow-lg' : 'bg-slate-900 text-white border-slate-900 shadow-lg') : (isDarkTheme ? 'bg-slate-900 text-slate-400 border-slate-800 hover:bg-slate-800 hover:text-white shadow-sm' : 'bg-white text-slate-400 border-slate-200 hover:bg-slate-50 hover:text-slate-900 shadow-sm')}`}
                        title="Configurações Financeiras"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                      </button>
                    </div>
                  )}
                  {/* Standard Action Buttons (Search, Sync, Create) */}
                  {viewMode !== 'ferramentas' && viewMode !== 'knowledge' && viewMode !== 'saude' && viewMode !== 'finance' && viewMode !== 'dashboard' && viewMode !== 'services' && viewMode !== 'strategy' && viewMode !== 'godmode' && (
                    <div className="ml-auto flex items-center justify-end gap-3">
                      {activeModule !== 'dashboard' && (
                        <div className={`hidden lg:flex h-10 items-center border rounded-lg px-4 w-72 xl:w-80 group focus-within:ring-1 focus-within:ring-primary-tactile transition-all ${inputSurfaceClass} border-[#e5e7eb] dark:border-slate-800`}>
                          <svg className={`w-4 h-4 mr-3 ${mutedTextClass}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                          <input type="text" placeholder="Pesquisar..." className="bg-transparent border-none outline-none text-xs font-medium w-full font-sans flex-1" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
                          {searchTerm && (
                            <button
                              onClick={() => setSearchTerm('')}
                              className="ml-2 text-slate-400 hover:text-slate-600 focus:outline-none transition-colors"
                              title="Limpar pesquisa"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          )}
                        </div>
                      )}
                      <button
                        onClick={() => setIsCreateModalOpen(true)}
                        className="h-10 bg-slate-900 text-white px-5 rounded-lg text-[10px] font-bold uppercase tracking-wider flex items-center gap-2 hover:bg-slate-800 transition-all active:scale-95 font-sans shadow-sm"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        Criar Ação
                      </button>
                      {searchTerm !== 'filter:unclassified' && (
                        <div className={`h-10 p-0.5 rounded-lg inline-flex border ${isDarkTheme ? 'bg-slate-800 border-slate-700' : 'bg-slate-100 border-[#e5e7eb]'} gap-0.5`}>
                          <button
                            onClick={() => setDashboardViewMode('list')}
                            className={`px-3 md:px-4 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-all flex items-center justify-center font-sans ${dashboardViewMode === 'list' ? (isDarkTheme ? 'bg-slate-600 text-white' : 'bg-white text-slate-900 shadow-sm') : (isDarkTheme ? 'text-slate-550 hover:text-slate-800' : 'text-slate-400 hover:text-slate-650')}`}
                            title="Visualização em Lista"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
                          </button>
                          {dashboardViewMode === 'list' && (
                            <button
                              onClick={() => setGroupByDate(prev => !prev)}
                              className={`px-3 md:px-4 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-all flex items-center justify-center font-sans border-x ${isDarkTheme ? 'border-slate-700' : 'border-slate-200'} ${!groupByDate ? 'text-amber-500 font-bold' : (isDarkTheme ? 'text-slate-400 hover:text-slate-350' : 'text-slate-550 hover:text-slate-850')}`}
                              title={groupByDate ? "Desativar Agrupamento por Datas (Ver Lista Corrida)" : "Ativar Agrupamento por Datas"}
                            >
                              <svg className="w-3.5 h-3.5 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2-2v12a2 2 0 002 2z" />
                              </svg>
                              <span>{groupByDate ? "Agrupado" : "Corrido"}</span>
                            </button>
                          )}
                          <button
                            onClick={() => setDashboardViewMode('calendar')}
                            className={`px-3 md:px-4 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-all flex items-center justify-center font-sans ${dashboardViewMode === 'calendar' ? (isDarkTheme ? 'bg-slate-600 text-white' : 'bg-white text-slate-900 shadow-sm') : (isDarkTheme ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600')}`}
                            title="Visualização em Calendário"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2-2v12a2 2 0 002 2z" /></svg>
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                  {/* Global Header Actions â€” Speed Dial */}
                  <SpeedDialMenu
                    notifications={notifications}
                    isSyncing={isSyncing}
                    isNotificationCenterOpen={isNotificationCenterOpen}
                    onOpenCopiloto={() => setIsCopilotoOpen(true)}
                    onOpenNotes={() => setIsQuickNoteModalOpen(true)}
                    onOpenShopping={() => setIsShoppingAIModalOpen(true)}
                    onOpenTranscription={() => setIsTranscriptionAIModalOpen(true)}
                    onOpenWhatsAppTranscription={() => {
                      setActiveModule('acoes');
                      setViewMode('ferramentas');
                      setActiveFerramenta('batch_transcription');
                    }}
                    onOpenMeetingTranscription={() => {
                      setActiveModule('acoes');
                      setViewMode('ferramentas');
                      setActiveFerramenta('meeting_transcription');
                    }}
                    onOpenBrainstorming={() => {
                      setActiveModule('acoes');
                      setViewMode('ferramentas');
                      setActiveFerramenta('brainstorming');
                    }}
                    onOpenPopManager={() => {
                      setActiveModule('acoes');
                      setViewMode('ferramentas');
                      setActiveFerramenta('pop_manager');
                    }}
                    onOpenSipacTracking={() => {
                      setActiveModule('acoes');
                      setViewMode('ferramentas');
                      setActiveFerramenta('sipac_tracking');
                    }}
                    onOpenMonitorPaginas={() => {
                      setActiveModule('acoes');
                      setViewMode('ferramentas');
                      setActiveFerramenta('monitor_paginas');
                    }}
                    onOpenLongTranscription={() => {
                      setActiveModule('acoes');
                      setViewMode('ferramentas');
                      setActiveFerramenta('long_transcription');
                    }}
                    onOpenBatchTranscription={() => {
                      setActiveModule('acoes');
                      setViewMode('ferramentas');
                      setActiveFerramenta('batch_transcription');
                    }}
                    onToggleNotifications={() => setIsNotificationCenterOpen(prev => !prev)}
                    onSync={handleSync}
                    onOpenSettings={() => setIsSettingsModalOpen(true)}
                    onCloseNotifications={() => setIsNotificationCenterOpen(false)}
                    onMarkAsRead={handleMarkNotificationRead}
                    onDismiss={handleDismissNotification}
                    onUpdateOverdue={handleUpdateOverdueTasks}
                    onNavigate={handleNotificationNavigate}
                    onCreateAction={() => setIsCreateModalOpen(true)}
                    isDark={isDarkTheme}
                  />
                </div>
              </div>
              {/* Mobile Menu Drawer */}
              {isMobileMenuOpen && (
                <div className={`md:hidden border-t animate-in slide-in-from-top-4 duration-300 ${isDarkTheme ? 'border-slate-800 bg-slate-950' : 'border-slate-200 bg-white'}`}>
                  <nav className="flex flex-col p-4 gap-2">
                    {[
                      { label: 'Dashboard', active: viewMode === 'dashboard', onClick: () => { setActiveModule('dashboard'); setViewMode('dashboard'); } },
                      { label: 'Ações', active: activeModule === 'acoes' && (viewMode === 'gallery' || viewMode === 'licitacoes' || viewMode === 'assistencia' || viewMode === 'concluidas'), onClick: () => { setActiveModule('acoes'); setViewMode('gallery'); } },
                      { label: 'Serviços', active: activeModule === 'servicos' && viewMode === 'services', onClick: () => { setActiveModule('servicos'); setViewMode('services'); } },
                      { label: 'PGD', active: activeModule === 'acoes' && viewMode === 'pgc', onClick: () => { setActiveModule('acoes'); setViewMode('pgc'); } },
                      { label: 'Financeiro', active: activeModule === 'financeiro', onClick: () => { setActiveModule('financeiro'); setViewMode('finance'); } },
                      { label: 'Saúde', active: activeModule === 'saude', onClick: () => { setActiveModule('saude'); setViewMode('saude'); } },
                      { label: 'Estratégia', active: activeModule === 'estrategia' && viewMode === 'strategy', onClick: () => { setActiveModule('estrategia'); setViewMode('strategy'); } },
                      { label: 'Godmode', active: viewMode === 'godmode', onClick: () => { setActiveModule('estrategia'); setViewMode('godmode'); } },
                      { label: 'Contatos', active: viewMode === 'contacts', onClick: () => { setActiveModule('acoes'); setViewMode('contacts'); } },
                      { label: 'Conhecimento', active: viewMode === 'knowledge', onClick: () => { setActiveModule('acoes'); setViewMode('knowledge'); } },
                      { label: 'Áreas Temáticas', active: viewMode === 'rag-bases', onClick: () => { setActiveModule('acoes'); setViewMode('rag-bases'); } },
                    ].map((item, idx) => (
                      <button
                        key={idx}
                        onClick={() => {
                          item.onClick();
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-2.5 rounded-none text-xs font-black uppercase tracking-widest transition-all font-mono ${item.active ? 'bg-slate-900 text-white' : isDarkTheme ? 'text-slate-300 hover:bg-white/10' : 'text-slate-500 hover:bg-slate-200/50'}`}
                      >
                        {item.label}
                      </button>
                    ))}
                    <div className={`grid grid-cols-2 gap-2 mt-4 pt-4 border-t ${isDarkTheme ? 'border-slate-800' : 'border-slate-100'}`}>
                      <button
                        onClick={() => {
                          handleSync();
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-2.5 rounded-none text-xs font-black uppercase tracking-widest font-mono flex items-center justify-center gap-2 transition-colors ${isDarkTheme ? 'bg-blue-950/40 text-blue-400 hover:bg-blue-900/50 border border-blue-900/40' : 'bg-blue-50 text-blue-700 hover:bg-blue-100'}`}
                      >
                        <svg className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                        {isSyncing ? 'Sync...' : 'Sync'}
                      </button>
                      <button
                        onClick={() => {
                          setIsSettingsModalOpen(true);
                          setIsMobileMenuOpen(false);
                        }}
                        className={`px-4 py-2.5 rounded-none text-xs font-black uppercase tracking-widest font-mono flex items-center justify-center gap-2 transition-colors ${isDarkTheme ? 'bg-slate-900 text-slate-300 hover:bg-slate-800 border border-slate-800' : 'bg-slate-100 text-slate-600 hover:bg-slate-200/50'}`}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                        Config
                      </button>
                      <button
                        onClick={handleLogout}
                        className={`col-span-2 px-4 py-2.5 rounded-none text-xs font-black uppercase tracking-widest font-mono flex items-center justify-center gap-2 mt-2 transition-colors ${isDarkTheme ? 'bg-rose-950/40 text-rose-400 hover:bg-rose-900/50 border border-rose-900/40' : 'bg-rose-50 text-rose-600 hover:bg-rose-100'}`}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
                        Sair da Conta
                      </button>
                    </div>
                  </nav>
                </div>
              )}
            </header>
            <div className={`w-full ${viewMode === 'dashboard' ? 'px-0 py-0' : 'px-0 md:px-8 py-6'}`}>
              {/* Painel de Estatísticas e Filtros - APENAS NA VISÃO GERAL */}
              <main className={(viewMode === 'dashboard' || viewMode === 'godmode') ? '' : 'mb-20'}>
                {viewMode === 'dashboard' ? (
                  <>
                    {/* Mobile: Atalhos Inteligentes */}
                    <div className="sm:hidden">
                      <MobileShortcutsView
                        isDark={isDarkTheme}
                        onOpenCopilotoText={() => { setCopilotoAutoStartMic(false); setIsCopilotoOpen(true); }}
                        onOpenCopilotoAudio={() => { setCopilotoAutoStartMic(true); setIsCopilotoOpen(true); }}
                        onOpenTranscription={() => setIsTranscriptionAIModalOpen(true)}
                        onOpenActions={() => setIsCreateModalOpen(true)}
                        onOpenShopping={() => setIsShoppingAIModalOpen(true)}
                        onOpenMeetingTranscription={() => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta('meeting_transcription'); }}
                        onOpenBrainstorming={() => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta('brainstorming'); }}
                        onOpenPopManager={() => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta('pop_manager'); }}
                        onOpenSipacTracking={() => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta('sipac_tracking'); }}
                        onOpenMonitorPaginas={() => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta('monitor_paginas'); }}
                        onOpenLongTranscription={() => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta('long_transcription'); }}
                        onOpenBatchTranscription={() => { setActiveModule('acoes'); setViewMode('ferramentas'); setActiveFerramenta('batch_transcription'); }}
                        onToggleNotifications={() => setIsNotificationCenterOpen(prev => !prev)}
                        onSync={handleSync}
                        onOpenSettings={() => setIsSettingsModalOpen(true)}
                      />
                    </div>
                    {/* Desktop: Dashboard completo */}
                    <div className="hidden sm:block">
                      <DashboardView
                        tarefas={tarefas}
                        isDark={isDarkTheme}
                        financeTransactions={financeTransactions}
                        financeSettings={financeSettings}
                        fixedBills={fixedBills}
                        incomeEntries={incomeEntries}
                        healthWeights={healthWeights}
                        healthSettings={healthSettings}
                        exerciseLogs={exerciseLogs}
                        onSaveExerciseLog={handleSaveExerciseLog}
                        unidades={unidades}
                        currentMonth={currentMonth}
                        currentYear={currentYear}
                        onNavigate={handleDashboardNavigate}
                      />
                    </div>
                  </>
                ) : viewMode === 'strategy' ? (
                  <div className={isStrategySplitCopilot ? 'flex h-[calc(100vh-7.5rem)] min-h-[640px] gap-4 overflow-hidden' : ''}>
                    <div className={isStrategySplitCopilot ? 'min-w-0 flex-1 overflow-y-auto pr-1' : ''}>
                      <StrategyDashboardView
                        userId={user?.uid || ''}
                        isDark={isDarkTheme}
                        showToast={showToast}
                        tarefas={tarefas}
                        onCreateIndicadorAction={handleCreateIndicadorAction}
                      />
                    </div>
                    {isStrategySplitCopilot && (
                      <aside className="relative z-20 w-[420px] shrink-0">
                        <HermesGlobalChat
                          isOpen={isCopilotoOpen}
                          onClose={closeCopiloto}
                          autoStartMic={copilotoAutoStartMic}
                          copilotMode={copilotoMode}
                          layout="inline"
                          initialPrompt={copilotoInitialPrompt}
                          onInitialPromptConsumed={() => setCopilotoInitialPrompt(null)}
                          isDark={isDarkTheme}
                          userId={user?.uid || ''}
                          onOpenTask={handleCopilotoOpenTask}
                          onOpenTool={handleCopilotoOpenTool}
                        />
                      </aside>
                    )}
                  </div>
                ) : viewMode === 'godmode' ? (
                  <HermesGodmodeView userId={user?.uid || ''} isDark={isDarkTheme} showToast={showToast} />
                ) : viewMode === 'gallery' ? (
                  <>
                    {/* Mobile Search Bar */}
                    <div className="lg:hidden px-4 mb-6">
                      <div className={`flex items-center border rounded-none px-4 py-3 shadow-none focus-within:ring-1 focus-within:ring-primary-tactile transition-all ${isDarkTheme ? 'bg-slate-800 border-slate-700' : 'bg-white border-border-grid'}`}>
                        <svg className={`w-5 h-5 mr-3 ${mutedTextClass}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        <input
                          type="text"
                          placeholder="Pesquisar ações..."
                          className="bg-transparent border-none outline-none text-sm font-bold w-full font-mono"
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
                    <div className="flex flex-col md:flex-row items-center justify-between mb-4 gap-4 px-4 md:px-0 lg:hidden">
                      {/* Linha de Filtros e Ações Globais */}
                      <div className="flex items-center justify-between w-full gap-2">
                        {searchTerm !== 'filter:unclassified' && (
                          <div className={`h-10 p-1 rounded-none inline-flex border w-full justify-between ${isDarkTheme ? 'bg-slate-800 border-slate-700' : 'bg-surface-container border-border-grid'}`}>
                            <button
                              onClick={() => setDashboardViewMode('list')}
                              className={`flex-1 py-1 rounded-none text-[9px] font-black uppercase tracking-widest transition-all flex items-center justify-center font-mono ${dashboardViewMode === 'list' ? (isDarkTheme ? 'bg-slate-600 text-white' : 'bg-slate-900 text-white') : (isDarkTheme ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600')}`}
                            >
                              <svg className="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
                              Lista
                            </button>

                            {dashboardViewMode === 'list' && (
                              <button
                                onClick={() => setGroupByDate(prev => !prev)}
                                className={`flex-1 py-1 rounded-none text-[9px] font-black uppercase tracking-widest transition-all flex items-center justify-center font-mono border-x ${isDarkTheme ? 'border-slate-700' : 'border-slate-200'} ${!groupByDate ? 'text-amber-500 font-bold' : (isDarkTheme ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600')}`}
                              >
                                {groupByDate ? "Agrupado" : "Corrido"}
                              </button>
                            )}

                            <button
                              onClick={() => setDashboardViewMode('calendar')}
                              className={`flex-1 py-1 rounded-none text-[9px] font-black uppercase tracking-widest transition-all flex items-center justify-center font-mono ${dashboardViewMode === 'calendar' ? (isDarkTheme ? 'bg-slate-600 text-white' : 'bg-slate-900 text-white') : (isDarkTheme ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600')}`}
                            >
                              <svg className="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2-2v12a2 2 0 002 2z" /></svg>
                              Calendário
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                    {dashboardViewMode === 'calendar' ? (
                      <CalendarView
                        tasks={filteredAndSortedTarefas}
                        googleEvents={primaryCalendarEvents}
                        viewMode={calendarViewMode}
                        currentDate={calendarDate}
                        onDateChange={setCalendarDate}
                        onTaskClick={setSelectedTask}
                        onViewModeChange={setCalendarViewMode}
                        onTaskUpdate={handleUpdateTarefa}
                        onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
                        onReorderTasks={handleReorderTasks}
                        showToast={showToast}
                        isDark={isDarkTheme}
                      />
                    ) : (
                      <>
                        {searchTerm === 'filter:unclassified' ? (
                          <div className={`animate-in border-2 rounded-none overflow-hidden shadow-2xl ${isDarkTheme ? 'bg-slate-900 border-slate-700' : 'bg-white border-slate-900'}`}>
                            <div className={`p-8 border-b flex flex-col md:flex-row md:items-center justify-between gap-4 ${isDarkTheme ? 'border-slate-800 bg-slate-800/50' : 'border-slate-100 bg-slate-50'}`}>
                              <h3 className={`text-xl font-black tracking-tight flex items-center gap-3 ${isDarkTheme ? 'text-slate-100' : 'text-slate-900'}`}>
                                <span className="w-2 h-8 bg-rose-600 rounded-none"></span>
                                Organização Rápida
                              </h3>
                              {selectedTaskIds.length > 0 && (
                                <div className="flex items-center gap-2 bg-slate-900 p-2 rounded-none animate-in slide-in-from-top-4">
                                  <span className="text-[9px] font-black text-white uppercase tracking-widest px-4">Classificar ({selectedTaskIds.length}):</span>
                                  <button onClick={() => handleBatchTag('CLC')} className="bg-blue-600 hover:bg-blue-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-none transition-all">CLC</button>
                                  <button onClick={() => handleBatchTag('ASSISTÃŠNCIA')} className="bg-emerald-600 hover:bg-emerald-700 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-none transition-all">Assistência</button>
                                  <button onClick={() => handleBatchTag('GERAL')} className="bg-slate-500 hover:bg-slate-600 text-white text-[9px] font-black uppercase px-4 py-1.5 rounded-none transition-all">Geral</button>
                                </div>
                              )}
                            </div>
                            <div className="overflow-x-auto">
                              {/* Desktop Table */}
                              <table className="w-full text-left hidden md:table">
                                <thead className={`border-b ${isDarkTheme ? 'bg-slate-800 border-slate-700' : 'bg-slate-50 border-slate-200'}`}>
                                  <tr>
                                    <th className={`px-8 py-4 w-12 text-center text-[10px] font-black uppercase tracking-widest italic ${isDarkTheme ? 'text-slate-500' : 'text-slate-400'}`}>#</th>
                                    <th className={`px-8 py-4 text-[10px] font-black uppercase tracking-widest ${isDarkTheme ? 'text-slate-500' : 'text-slate-400'}`}>Descrição da Tarefa</th>
                                    <th className={`px-8 py-4 text-[10px] font-black uppercase tracking-widest w-40 text-center ${isDarkTheme ? 'text-slate-500' : 'text-slate-400'}`}>Data Limite</th>
                                  </tr>
                                </thead>
                                <tbody className={`divide-y ${isDarkTheme ? 'divide-slate-800' : 'divide-slate-50'}`}>
                                  {filteredAndSortedTarefas.map((task) => (
                                    <tr
                                      key={task.id}
                                      onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); if (task.auto_data_atualizada) handleUpdateTarefa(task.id, { auto_data_atualizada: false }); }}
                                      className={`transition-colors cursor-pointer ${isDarkTheme ? 'hover:bg-slate-800/50' : 'hover:bg-slate-50'} ${selectedTaskIds.includes(task.id) ? (isDarkTheme ? 'bg-blue-900/20' : 'bg-blue-50/30') : ''}`}
                                    >
                                      <td className="px-8 py-4 text-center">
                                        <input
                                          type="checkbox"
                                          checked={selectedTaskIds.includes(task.id)}
                                          onChange={(e) => {
                                            e.stopPropagation();
                                            setSelectedTaskIds(prev => prev.includes(task.id) ? prev.filter(id => id !== task.id) : [...prev, task.id]);
                                          }}
                                          className="w-5 h-5 rounded-none border-slate-300 text-slate-900 focus:ring-slate-900 cursor-pointer"
                                        />
                                      </td>
                                      <td className="px-8 py-4">
                                        <div className="flex items-center gap-2 flex-wrap">
                                          <div className="text-[13px] font-bold text-slate-800 hover:text-blue-600 transition-colors leading-snug">
                                            {task.titulo}
                                          </div>
                                          {task.sync_status === 'new' && (
                                            <span className="text-[8px] font-black px-1.5 py-0.5 rounded-none uppercase bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm animate-pulse">
                                              Novo
                                            </span>
                                          )}
                                          {task.sync_status === 'updated' && (
                                            <span className="text-[8px] font-black px-1.5 py-0.5 rounded-none uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">
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
                                    onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); if (task.auto_data_atualizada) handleUpdateTarefa(task.id, { auto_data_atualizada: false }); }}
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
                                            <span className="text-[7px] font-black px-1.5 py-0.5 rounded-none uppercase bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm">
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
                                <div className="py-20 text-center text-slate-300 font-black uppercase tracking-widest italic border-t border-border-grid">
                                  Tudo classificado! Bom trabalho.
                                </div>
                              )}
                            </div>
                          </div>
                        ) : (
                          <div className="animate-in">
                            {groupByDate ? (
                              Object.keys(tarefasAgrupadas).length > 0 ? (
                                Object.entries(tarefasAgrupadas).map(([label, tasks]: [string, Tarefa[]]) => (
                                  <div
                                    key={label}
                                    className={`mb-3 border transition-colors rounded-none overflow-visible ${isDarkTheme ? 'bg-slate-900/40 border-slate-800' : 'bg-white border-border-grid'}`}
                                    onDragOver={(e) => {
                                      e.preventDefault();
                                      e.currentTarget.style.borderColor = '#835500';
                                    }}
                                    onDragLeave={(e) => {
                                      e.currentTarget.style.borderColor = '';
                                    }}
                                    onDrop={(e) => {
                                      e.preventDefault();
                                      e.currentTarget.style.borderColor = '';
                                      const taskId = e.dataTransfer.getData('task-id');
                                      if (taskId) {
                                        if (label === 'Ações em Stand-by') {
                                          handleUpdateTarefa(taskId, { status: 'stand-by' as any });
                                          return;
                                        }
                                        const date = getBucketStartDate(label);
                                        if (date) {
                                          handleUpdateTarefa(taskId, { data_limite: date });
                                        }
                                      }
                                    }}
                                  >
                                    <button
                                      onClick={() => toggleSection(label)}
                                      className={`w-full px-4 py-3 bg-transparent flex items-center justify-between transition-colors group ${isDarkTheme ? 'hover:bg-white/[0.02]' : 'hover:bg-slate-50'}`}
                                    >
                                      <div className="flex items-center gap-3">
                                        <span className={`text-xs font-black uppercase tracking-[0.22em] font-mono ${isDarkTheme ? 'text-slate-300' : 'text-slate-500'}`}>{label}</span>
                                        <span className={`text-[10px] font-bold font-mono ${isDarkTheme ? 'text-slate-500' : 'text-slate-300'}`}>({tasks.length})</span>
                                      </div>
                                      <svg className={`w-4 h-4 transition-transform duration-300 ${effectiveExpandedSections.includes(label) ? 'rotate-180' : ''} ${isDarkTheme ? 'text-slate-500' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                                      </svg>
                                    </button>
                                    {effectiveExpandedSections.includes(label) && (
                                      <div className="animate-in origin-top border-t border-border-grid">
                                        {label === "Concluídas" ? (
                                          <>
                                            {tasks.slice(0, completedLimit).map(task => (
                                              <div key={task.id} className="relative">
                                                <RowCard
                                                  task={task}
                                                  isDark={isDarkTheme}
                                                  knowledgeBases={knowledgeBases}
                                                  onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); if (task.auto_data_atualizada) handleUpdateTarefa(task.id, { auto_data_atualizada: false }); }}
                                                  onToggle={handleToggleTarefaStatus}
                                                  onDelete={handleDeleteTarefa}
                                                  onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                                  onUpdateToToday={handleUpdateToToday}
                                                  onUpdateTask={handleUpdateTarefa}
                                                  onSynthesizeDescription={handleSynthesizeTaskDescription}
                                                  isSynthesizingDescription={descriptionSynthesisTaskId === task.id}
                                                />
                                              </div>
                                            ))}
                                            {tasks.length > completedLimit && (
                                              <div className="p-4 flex justify-center">
                                                <button
                                                  onClick={(e) => {
                                                    e.stopPropagation();
                                                    setCompletedLimit(prev => prev + 10);
                                                  }}
                                                  className={`px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${isDarkTheme ? 'bg-slate-900 text-slate-300 hover:bg-slate-800' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'}`}
                                                >
                                                  Ver mais 10 concluídas
                                                </button>
                                              </div>
                                            )}
                                          </>
                                        ) : (
                                          tasks.map(task => (
                                            <div
                                              key={task.id}
                                              className="relative"
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
                                                isDark={isDarkTheme}
                                                knowledgeBases={knowledgeBases}
                                                highlighted={label === 'Hoje' && tasks.filter(t => normalizeStatus(t.status) !== 'concluido')[0]?.id === task.id}
                                                onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); if (task.auto_data_atualizada) handleUpdateTarefa(task.id, { auto_data_atualizada: false }); }}
                                                onToggle={handleToggleTarefaStatus}
                                                onDelete={handleDeleteTarefa}
                                                onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                                onUpdateToToday={handleUpdateToToday}
                                                onUpdateTask={handleUpdateTarefa}
                                                onSynthesizeDescription={handleSynthesizeTaskDescription}
                                                isSynthesizingDescription={descriptionSynthesisTaskId === task.id}
                                              />
                                            </div>
                                          ))
                                        )}
                                        {tasks.length === 0 && (
                                          <div className={`p-8 text-center ${isDarkTheme ? 'bg-slate-950/40' : 'bg-slate-50/30'}`}>
                                            <p className={`text-[10px] font-black uppercase tracking-widest italic ${isDarkTheme ? 'text-slate-500' : 'text-slate-300'}`}>
                                              {label === 'Ações em Stand-by' ? 'Arraste ações aqui para pausar' : 'Nenhuma ação nesta seção'}
                                            </p>
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                ))
                              ) : (
                                <div className="py-24 text-center">
                                  <p className={`font-black text-xl uppercase tracking-widest ${isDarkTheme ? 'text-slate-600' : 'text-slate-300'}`}>Sem demandas encontradas</p>
                                </div>
                              )
                            ) : (
                              <div className="animate-in space-y-4">
                                {/* Trava da Cota Institucional Diária (banner informativo) */}
                                {cotaInstitucional.hasInstitucional && (
                                  cotaInstitucional.cumprida ? (
                                    <div className="border-2 border-emerald-500 bg-emerald-50 text-emerald-800 px-4 py-3 rounded-none flex items-center gap-3 font-black uppercase tracking-widest text-[11px]">
                                      <span className="text-base">🟢</span>
                                      <span>Cota Diária Cumprida! Desempenho Institucional Registrado.</span>
                                    </div>
                                  ) : (
                                    <div className="border-2 border-rose-500 bg-rose-50 text-rose-800 px-4 py-3 rounded-none flex items-center gap-3 font-black uppercase tracking-widest text-[11px] animate-pulse">
                                      <span className="text-base">🚨</span>
                                      <span>Cota Institucional Diária Pendente. Atualize ao menos uma ação de CLC ou Assistência Estudantil hoje.</span>
                                    </div>
                                  )
                                )}
                                {/* Bloco de Ações Ativas */}
                                <div className={`border rounded-none overflow-visible ${isDarkTheme ? 'bg-slate-900/40 border-slate-800' : 'bg-white border-border-grid'}`}>
                                  <div className="divide-y divide-border-grid">
                                    {sortedActiveTasks.map(task => (
                                      <div
                                        key={task.id}
                                        className="relative"
                                      >
                                        <RowCard
                                          task={task}
                                          isDark={isDarkTheme}
                                          knowledgeBases={knowledgeBases}
                                          onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); if (task.auto_data_atualizada) handleUpdateTarefa(task.id, { auto_data_atualizada: false }); }}
                                          onToggle={handleToggleTarefaStatus}
                                          onDelete={handleDeleteTarefa}
                                          onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                          onUpdateToToday={handleUpdateToToday}
                                          onUpdateTask={handleUpdateTarefa}
                                          onSynthesizeDescription={handleSynthesizeTaskDescription}
                                          isSynthesizingDescription={descriptionSynthesisTaskId === task.id}
                                        />
                                      </div>
                                    ))}
                                  </div>
                                  {sortedActiveTasks.length === 0 && (
                                    <div className="py-24 text-center">
                                      <p className={`font-black text-xl uppercase tracking-widest ${isDarkTheme ? 'text-slate-600' : 'text-slate-300'}`}>Sem demandas ativas</p>
                                    </div>
                                  )}
                                </div>

                                {/* Bloco de Ações em Stand-by */}
                                {tarefasAgrupadas["Ações em Stand-by"] && tarefasAgrupadas["Ações em Stand-by"].length > 0 && (
                                  <div className={`border rounded-none overflow-visible ${isDarkTheme ? 'bg-slate-900/40 border-slate-800' : 'bg-white border-border-grid'}`}>
                                    <button
                                      onClick={() => toggleSection("Ações em Stand-by")}
                                      className={`w-full px-4 py-3 bg-transparent flex items-center justify-between transition-colors group ${isDarkTheme ? 'hover:bg-white/[0.02]' : 'hover:bg-slate-50'}`}
                                    >
                                      <div className="flex items-center gap-3">
                                        <span className={`text-xs font-black uppercase tracking-[0.22em] font-mono ${isDarkTheme ? 'text-amber-300' : 'text-amber-700'}`}>Ações em Stand-by</span>
                                        <span className={`text-[10px] font-bold font-mono ${isDarkTheme ? 'text-slate-500' : 'text-slate-300'}`}>({tarefasAgrupadas["Ações em Stand-by"].length})</span>
                                      </div>
                                      <svg className={`w-4 h-4 transition-transform duration-300 ${effectiveExpandedSections.includes("Ações em Stand-by") ? 'rotate-180' : ''} ${isDarkTheme ? 'text-slate-500' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                                      </svg>
                                    </button>
                                    {effectiveExpandedSections.includes("Ações em Stand-by") && (
                                      <div className="animate-in origin-top border-t border-border-grid divide-y divide-border-grid">
                                        {tarefasAgrupadas["Ações em Stand-by"].map(task => (
                                          <div key={task.id} className="relative">
                                            <RowCard
                                              task={task}
                                              isDark={isDarkTheme}
                                              knowledgeBases={knowledgeBases}
                                              onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); if (task.auto_data_atualizada) handleUpdateTarefa(task.id, { auto_data_atualizada: false }); }}
                                              onToggle={handleToggleTarefaStatus}
                                              onDelete={handleDeleteTarefa}
                                              onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                              onUpdateToToday={handleUpdateToToday}
                                              onUpdateTask={handleUpdateTarefa}
                                              onSynthesizeDescription={handleSynthesizeTaskDescription}
                                              isSynthesizingDescription={descriptionSynthesisTaskId === task.id}
                                            />
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                )}

                                {/* Bloco de Concluídas colapsável */}
                                {tarefasAgrupadas["Concluídas"] && tarefasAgrupadas["Concluídas"].length > 0 && (
                                  <div className={`border rounded-none overflow-visible ${isDarkTheme ? 'bg-slate-900/40 border-slate-800' : 'bg-white border-border-grid'}`}>
                                    <button
                                      onClick={() => toggleSection("Concluídas")}
                                      className={`w-full px-4 py-3 bg-transparent flex items-center justify-between transition-colors group ${isDarkTheme ? 'hover:bg-white/[0.02]' : 'hover:bg-slate-50'}`}
                                    >
                                      <div className="flex items-center gap-3">
                                        <span className={`text-xs font-black uppercase tracking-[0.22em] font-mono ${isDarkTheme ? 'text-slate-300' : 'text-slate-500'}`}>Concluídas</span>
                                        <span className={`text-[10px] font-bold font-mono ${isDarkTheme ? 'text-slate-500' : 'text-slate-300'}`}>({tarefasAgrupadas["Concluídas"].length})</span>
                                      </div>
                                      <svg className={`w-4 h-4 transition-transform duration-300 ${effectiveExpandedSections.includes("Concluídas") ? 'rotate-180' : ''} ${isDarkTheme ? 'text-slate-500' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                                      </svg>
                                    </button>
                                    {effectiveExpandedSections.includes("Concluídas") && (
                                      <div className="animate-in origin-top border-t border-border-grid divide-y divide-border-grid">
                                        {tarefasAgrupadas["Concluídas"].slice(0, completedLimit).map(task => (
                                          <div key={task.id} className="relative">
                                            <RowCard
                                              task={task}
                                              isDark={isDarkTheme}
                                              knowledgeBases={knowledgeBases}
                                              onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); if (task.auto_data_atualizada) handleUpdateTarefa(task.id, { auto_data_atualizada: false }); }}
                                              onToggle={handleToggleTarefaStatus}
                                              onDelete={handleDeleteTarefa}
                                              onEdit={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                                              onUpdateToToday={handleUpdateToToday}
                                              onUpdateTask={handleUpdateTarefa}
                                              onSynthesizeDescription={handleSynthesizeTaskDescription}
                                              isSynthesizingDescription={descriptionSynthesisTaskId === task.id}
                                            />
                                          </div>
                                        ))}
                                        {tarefasAgrupadas["Concluídas"].length > completedLimit && (
                                          <div className="p-4 flex justify-center">
                                            <button
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                setCompletedLimit(prev => prev + 10);
                                              }}
                                              className={`px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${isDarkTheme ? 'bg-slate-900 text-slate-300 hover:bg-slate-800' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'}`}
                                            >
                                              Ver mais 10 concluídas
                                            </button>
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                        {/* Completed tasks section removed to unify in the final groups */}
                      </>
                    )}
                  </>
                ) : viewMode === 'concluidas' ? (
                  <div className={`actions-completed-view animate-in border rounded-none md:rounded-[2rem] overflow-hidden shadow-2xl ${isDarkTheme ? 'bg-[#0f172a] border-[#1e293b] actions-view-dark text-slate-100' : 'bg-white border-slate-200 text-slate-900'}`}>
                    <div className={`px-6 py-4 border-b flex items-center justify-between ${isDarkTheme ? 'bg-[#111827] border-[#1e293b]' : 'bg-slate-50 border-slate-100'}`}>
                      <div className="flex items-center gap-3">
                        <span className="w-2 h-6 bg-emerald-500 rounded-full"></span>
                        <span className={`text-sm font-black uppercase tracking-widest ${isDarkTheme ? 'text-slate-100' : 'text-slate-900'}`}>Concluídas</span>
                        <span className={`text-[10px] font-bold ${isDarkTheme ? 'text-slate-400' : 'text-slate-400'}`}>({(tarefasAgrupadas["Concluídas"] || []).length} ações)</span>
                      </div>
                    </div>
                    {(tarefasAgrupadas["Concluídas"] || []).length === 0 ? (
                      <div className="py-24 text-center">
                        <p className={`font-black text-xl uppercase tracking-widest ${isDarkTheme ? 'text-slate-500' : 'text-slate-300'}`}>Nenhuma ação concluída</p>
                      </div>
                    ) : (
                      <>
                        {(tarefasAgrupadas["Concluídas"] || []).slice(0, completedLimit).map(task => (
                          <div key={task.id} className="relative">
                            <RowCard
                              task={task}
                              isDark={isDarkTheme}
                              knowledgeBases={knowledgeBases}
                              onClick={() => { setSelectedTask(task); setTaskModalMode('execute'); if (task.auto_data_atualizada) handleUpdateTarefa(task.id, { auto_data_atualizada: false }); }}
                              onToggle={handleToggleTarefaStatus}
                              onDelete={handleDeleteTarefa}
                              onEdit={(t) => { setSelectedTask(t); setTaskModalMode('default'); }}
                              onUpdateTask={handleUpdateTarefa}
                              onSynthesizeDescription={handleSynthesizeTaskDescription}
                              isSynthesizingDescription={descriptionSynthesisTaskId === task.id}
                            />
                          </div>
                        ))}
                        {(tarefasAgrupadas["Concluídas"] || []).length > completedLimit && (
                          <div className={`p-4 flex justify-center border-t ${isDarkTheme ? 'border-[#1e293b]' : 'border-slate-100'}`}>
                            <button
                              onClick={() => setCompletedLimit(prev => prev + 10)}
                              className={`px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${isDarkTheme ? 'bg-[#1e293b] hover:bg-[#334155] text-[#cbd5e1] hover:text-[#f8fafc]' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'}`}
                            >
                              Ver mais 10 ({(tarefasAgrupadas["Concluídas"] || []).length - completedLimit} restantes)
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ) : (viewMode === 'licitacoes' || viewMode === 'assistencia') ? (
                  <CategoryView
                    tasks={filteredAndSortedTarefas}
                    viewMode={viewMode}
                    onSelectTask={(t) => { setSelectedTask(t); setTaskModalMode('edit'); }}
                    onExecuteTask={(t) => { setSelectedTask(t); setTaskModalMode('execute'); }}
                    onAnalysePatterns={handleAnalysePatterns}
                    isDark={isDarkTheme}
                  />
                ) : viewMode === 'saude' ? (
                  <HealthView
                    weights={healthWeights}
                    settings={healthSettings}
                    onUpdateSettings={handleUpdateHealthSettings}
                    onAddWeight={handleAddHealthWeight}
                    onDeleteWeight={handleDeleteHealthWeight}
                    exerciseLogs={exerciseLogs}
                    exerciseSettings={exerciseSettings}
                    onSaveExerciseLog={handleSaveExerciseLog}
                    telegramReminders={healthTelegramReminders}
                    onSaveTelegramReminder={handleSaveHealthTelegramReminder}
                    onDeleteTelegramReminder={handleDeleteHealthTelegramReminder}
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
                    isDark={isDarkTheme}
                  />
                ) : viewMode === 'contacts' ? (
                  <ContactsView isDark={isDarkTheme} />
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
                    setActiveTool={(tool) => setActiveFerramenta(tool)}
                    isAddingText={isBrainstormingAddingText}
                    setIsAddingText={setIsBrainstormingAddingText}
                    showToast={showToast}
                    showAlert={showAlert}
                    knowledgeItems={knowledgeItems}
                    onUploadFile={handleUploadKnowledgeFile}
                    initialDiagnosisId={initialDiagnosisId}
                    isDark={isDarkTheme}
                    onSendToCopiloto={(text) => {
                      setCopilotoMode('default');
                      setCopilotoAutoStartMic(false);
                      setCopilotoInitialPrompt(text);
                      setIsCopilotoOpen(true);
                    }}
                  />
                ) : viewMode === 'services' ? (
                  <ServicesView
                    services={services}
                    onCreateService={handleCreateService}
                    onUpdateService={handleUpdateService}
                    onDeleteService={handleDeleteService}
                  />
                ) : viewMode === 'finance' ? (
                  <FinanceView
                    transactions={financeTransactions}
                    goals={(() => {
                      const totalSavings = fixedBills
                        .filter(b => b.category === 'Poupança' && b.isPaid)
                        .reduce((acc, curr) => acc + curr.amount, 0);
                      const emergencyCurrent = financeSettings.emergencyReserveCurrent || 0;
                      const isEmergencyFull = emergencyCurrent >= (financeSettings.emergencyReserveTarget || 0);
                      const investmentCurrent = financeSettings.investmentReserveCurrent || 0;
                      const availableForGoals = investmentCurrent + (isEmergencyFull ? totalSavings : 0);

                      return [...financeGoals].sort((a, b) => a.priority - b.priority).map(goal => {
                        if (goal.status === 'completed') return goal;
                        const allocated = goal.targetAmount > 0 ? Math.min(goal.targetAmount, availableForGoals) : 0;
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
                      return e.month === currentMonth && e.year === currentYear && e.isReceived;
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
                    onUpdateIncomeEntry={async (entry) => {
                      await updateDoc(doc(db, 'income_entries', entry.id), entry as any);
                      if (entry.service_id && entry.parcela_id) {
                        const relatedService = services.find(service => service.id === entry.service_id);
                        if (relatedService) {
                          const updatedParcelas = (relatedService.parcelas || []).map(parcela =>
                            parcela.id === entry.parcela_id
                              ? { ...parcela, status: entry.isReceived ? 'pago' : 'pendente' }
                              : parcela
                          );
                          await updateDoc(doc(db, 'servicos', relatedService.id), {
                            parcelas: updatedParcelas,
                            data_atualizacao: new Date().toISOString()
                          });
                        }
                      }
                    }}
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
                    onOpenFinancialCopilot={() => {
                      setCopilotoMode('finance');
                      setCopilotoAutoStartMic(false);
                      setIsCopilotoOpen(true);
                    }}
                  />
                ) : viewMode === 'knowledge' ? (
                  <div className="fixed inset-0 z-[50] bg-slate-50 md:relative md:inset-auto md:z-0 md:bg-transparent">
                    <KnowledgeView
                      onNavigateToOrigin={handleNavigateToOrigin}
                    />
                    <button
                      onClick={() => setViewMode('dashboard')}
                      className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-slate-900 text-white border-2 border-slate-900 px-8 py-4 rounded-none text-[10px] font-mono font-black uppercase tracking-[0.2em] shadow-[4px_4px_0px_rgba(15,23,42,1)] md:hidden z-[60]"
                    >
                      Voltar ao Painel
                    </button>
                  </div>
                ) : viewMode === 'rag-bases' ? ((() => {
                  const servicosBase = knowledgeBases.find(b => b.nome.toLowerCase() === 'serviços');
                  const saudeBase = knowledgeBases.find(b => b.nome.toLowerCase() === 'saúde');
                  const financeiraBase = knowledgeBases.find(b => b.nome.toLowerCase() === 'financeira');

                  const virtualItems: ConhecimentoItem[] = [];

                  if (servicosBase) {
                    services.forEach(s => {
                      virtualItems.push({
                        id: `servico_${s.id}`,
                        titulo: `[Serviço] ${s.titulo} - ${s.cliente}`,
                        tipo_arquivo: 'link',
                        url_drive: '',
                        tamanho: 0,
                        data_criacao: s.data_criacao || s.data_inicio || new Date().toISOString(),
                        texto_bruto: `Serviço: ${s.titulo}\nCliente: ${s.cliente}\nPapel: ${s.papel}\nDescrição: ${s.descricao}\nStatus: ${s.status}\nTipo Contrato: ${s.tipo_contrato}\nValor Total: R$ ${s.valor_total}`,
                        tags: s.tags || [],
                        base_id: servicosBase.id,
                        origem: { modulo: 'servicos', id_origem: s.id }
                      });
                    });
                  }

                  if (saudeBase) {
                    exams.forEach(e => {
                      virtualItems.push({
                        id: `exam_${e.id}`,
                        titulo: `[Exame] ${e.titulo} - ${e.data_exame}`,
                        tipo_arquivo: e.tipo_arquivo || 'pdf',
                        url_drive: e.url_drive || '',
                        tamanho: 0,
                        data_criacao: e.data_exame || new Date().toISOString(),
                        texto_bruto: `Exame de Saúde: ${e.titulo}\nData: ${e.data_exame}\nNotas: ${e.notas || ''}\nLaboratório: ${e.laboratorio || ''}`,
                        tags: ['Saúde', 'Exame'],
                        base_id: saudeBase.id,
                        origem: { modulo: 'saude', id_origem: e.id }
                      });
                    });

                    healthWeights.forEach(w => {
                      virtualItems.push({
                        id: `weight_${w.id}`,
                        titulo: `[Peso] ${w.weight} kg - ${w.date}`,
                        tipo_arquivo: 'link',
                        url_drive: '',
                        tamanho: 0,
                        data_criacao: w.date || new Date().toISOString(),
                        texto_bruto: `Registro de Peso: ${w.weight} kg\nData: ${w.date}\nPercentual de Gordura: ${w.fatPercent || 'N/A'}\nPercentual de Músculo: ${w.musclePercent || 'N/A'}\nNotas: ${w.notes || ''}`,
                        tags: ['Saúde', 'Peso'],
                        base_id: saudeBase.id,
                        origem: { modulo: 'saude', id_origem: w.id }
                      });
                    });

                    exerciseLogs.forEach(l => {
                      virtualItems.push({
                        id: `exercise_${l.id}`,
                        titulo: `[Exercício] ${l.type} - ${l.duration} min`,
                        tipo_arquivo: 'link',
                        url_drive: '',
                        tamanho: 0,
                        data_criacao: l.date || new Date().toISOString(),
                        texto_bruto: `Log de Exercício: ${l.type}\nDuração: ${l.duration} minutos\nData: ${l.date}\nCalorias: ${l.caloriesBurned || 'N/A'} kcal\nIntensidade: ${l.intensity || 'N/A'}\nNotas: ${l.notes || ''}`,
                        tags: ['Saúde', 'Exercício'],
                        base_id: saudeBase.id,
                        origem: { modulo: 'saude', id_origem: l.id }
                      });
                    });
                  }

                  if (financeiraBase) {
                    financeTransactions.forEach(t => {
                      virtualItems.push({
                        id: `transaction_${t.id}`,
                        titulo: `[Transação] ${t.description} - R$ ${t.amount}`,
                        tipo_arquivo: 'link',
                        url_drive: '',
                        tamanho: 0,
                        data_criacao: t.date || new Date().toISOString(),
                        texto_bruto: `Transação Financeira: ${t.description}\nValor: R$ ${t.amount}\nData: ${t.date}\nCategoria: ${t.category}\nTipo: ${t.type}\nStatus: ${t.status}\nNotas: ${t.notes || ''}`,
                        tags: [t.category, t.type],
                        base_id: financeiraBase.id,
                        origem: { modulo: 'financeiro', id_origem: t.id }
                      });
                    });

                    fixedBills.forEach(b => {
                      virtualItems.push({
                        id: `fixed_bill_${b.id}`,
                        titulo: `[Conta Fixa] ${b.name} - R$ ${b.amount}`,
                        tipo_arquivo: 'link',
                        url_drive: '',
                        tamanho: 0,
                        data_criacao: new Date().toISOString(),
                        texto_bruto: `Conta Fixa: ${b.name}\nValor: R$ ${b.amount}\nCategoria: ${b.category}\nDia de Vencimento: ${b.dueDate}\nPago: ${b.isPaid ? 'Sim' : 'Não'}`,
                        tags: [b.category],
                        base_id: financeiraBase.id,
                        origem: { modulo: 'financeiro', id_origem: b.id }
                      });
                    });

                    incomeEntries.forEach(e => {
                      virtualItems.push({
                        id: `income_${e.id}`,
                        titulo: `[Receita] ${e.description} - R$ ${e.amount}`,
                        tipo_arquivo: 'link',
                        url_drive: '',
                        tamanho: 0,
                        data_criacao: e.date || new Date().toISOString(),
                        texto_bruto: `Entrada de Receita: ${e.description}\nValor: R$ ${e.amount}\nData: ${e.date}\nCategoria: ${e.category}\nStatus: ${e.status}`,
                        tags: [e.category],
                        base_id: financeiraBase.id,
                        origem: { modulo: 'financeiro', id_origem: e.id }
                      });
                    });
                  }

                  // Add custom organization linked services
                  services.forEach(s => {
                    if (s.base_id && s.base_id !== servicosBase?.id) {
                      virtualItems.push({
                        id: `servico_org_${s.id}_${s.base_id}`,
                        titulo: `[Serviço] ${s.titulo} - ${s.cliente}`,
                        tipo_arquivo: 'link',
                        url_drive: '',
                        tamanho: 0,
                        data_criacao: s.data_criacao || s.data_inicio || new Date().toISOString(),
                        texto_bruto: `Serviço: ${s.titulo}\nCliente: ${s.cliente}\nPapel: ${s.papel}\nDescrição: ${s.descricao}\nStatus: ${s.status}\nTipo Contrato: ${s.tipo_contrato}\nValor Total: R$ ${s.valor_total}`,
                        tags: s.tags || [],
                        base_id: s.base_id,
                        origem: { modulo: 'servicos', id_origem: s.id }
                      });
                    }
                  });

                  const combinedItems = [...knowledgeItems, ...virtualItems];

                  return (
                    <div className="fixed inset-0 z-[50] md:relative md:inset-auto md:z-0 h-full">
                      <RAGBasesView
                        isDark={isDarkTheme}
                        bases={knowledgeBases}
                        items={combinedItems}
                        onCreateBase={handleCreateBase}
                        onUpdateBase={handleUpdateBase}
                        onDeleteBase={handleDeleteBase}
                        onUploadFile={handleUploadToRAGBase}
                        onAddLink={handleAddRAGBaseLink}
                        onDeleteItem={async (id) => {
                          if (id.startsWith('servico_org_')) {
                            const parts = id.split('_');
                            const realId = parts[2];
                            await handleDeleteService(realId);
                          } else if (id.startsWith('servico_')) {
                            const realId = id.split('_')[1];
                            await handleDeleteService(realId);
                          } else if (id.startsWith('exam_')) {
                            const realId = id.split('_')[1];
                            await deleteDoc(doc(db, 'exames', realId));
                          } else if (id.startsWith('weight_')) {
                            const realId = id.split('_')[1];
                            await deleteDoc(doc(db, 'health_weights', realId));
                          } else if (id.startsWith('exercise_')) {
                            const realId = id.split('_')[1];
                            await deleteDoc(doc(db, 'health_exercise_logs', realId));
                          } else if (id.startsWith('transaction_')) {
                            const realId = id.split('_')[1];
                            await updateDoc(doc(db, 'finance_transactions', realId), { status: 'deleted' });
                          } else if (id.startsWith('fixed_bill_')) {
                            const realId = id.split('_')[1];
                            await deleteDoc(doc(db, 'fixed_bills', realId));
                          } else if (id.startsWith('income_')) {
                            const realId = id.split('_')[1];
                            await updateDoc(doc(db, 'income_entries', realId), { status: 'deleted' });
                          } else {
                            await deleteDoc(doc(db, 'conhecimento', id));
                          }
                        }}
                        onVectorizeItem={async (id) => {
                          if (id.startsWith('servico_') || id.startsWith('exam_') || id.startsWith('weight_') || id.startsWith('exercise_') || id.startsWith('transaction_') || id.startsWith('fixed_bill_') || id.startsWith('income_')) {
                            showToast("Itens virtuais não podem ser vetorizados diretamente. Sincronize o módulo de origem.", "info");
                            return;
                          }
                          try {
                            const fn = httpsCallable(functions, 'vectorizeKnowledgeItemCallable');
                            const result = await fn({ knowledgeId: id });
                            const data = result.data as any;
                            if (data?.success) {
                              showToast("Item vetorizado com sucesso!", "success");
                            } else {
                              showToast(data?.message || "Este item não tem texto extraído para vetorizar.", "error");
                            }
                          } catch (e: any) {
                            showToast(e?.message || "Erro ao vetorizar item.", "error");
                          }
                        }}
                        showConfirm={showAlert}
                        onNavigateToOrigin={handleNavigateToOrigin}
                      />
                    </div>
                  );
                })()
                ) : (
                  <div className={`actions-pgd-view space-y-3 md:space-y-6 ${isDarkTheme ? 'actions-view-dark' : ''}`}>
                    {/* DISPLAY TÃTIL DE CABEÇALHO */}
                    <div className={`flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-6 p-6 md:p-8 rounded-none border-2 ${isDarkTheme ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-900 shadow-sm'}`}>
                      <div className="hidden md:block">
                        <div className="flex items-center gap-3">
                          <div className={`w-1.5 h-6 ${isDarkTheme ? 'bg-blue-500' : 'bg-slate-900'}`}></div>
                          <h3 className={`text-xl font-black tracking-tighter uppercase font-mono ${isDarkTheme ? 'text-white' : 'text-slate-900'}`}>Gestão PGD</h3>
                        </div>
                        <p className="text-slate-400 text-[9px] font-black uppercase tracking-[0.3em] font-mono mt-1.5 ml-4.5">Status: Sincronizado com Petrvs</p>
                      </div>
                      <div className="flex items-center gap-3 md:gap-4">
                        {pgcSubView === 'plano' && (
                          <button
                            onClick={() => setIsImportPlanOpen(true)}
                            className={`px-4 md:px-6 py-2 md:py-3 rounded-none text-[10px] font-black uppercase tracking-widest shadow-lg transition-all flex items-center gap-2 md:gap-3 font-mono ${isDarkTheme ? 'bg-blue-600 text-white hover:bg-blue-500' : 'bg-slate-900 text-white hover:bg-slate-800'}`}
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                            Importar Planilha
                          </button>
                        )}
                        <select
                          value={currentMonth}
                          onChange={(e) => setCurrentMonth(Number(e.target.value))}
                          className={`flex-1 md:flex-none text-[10px] font-black uppercase border-2 px-4 py-2 rounded-none outline-none focus:ring-2 font-mono ${isDarkTheme ? 'bg-slate-800 border-slate-700 text-slate-100 focus:ring-blue-500' : 'bg-slate-50 border-slate-200 text-slate-900 focus:ring-slate-900'}`}
                        >
                          {['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'].map((m, i) => (
                            <option key={i} value={i}>{m}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div className="flex border-b-2 border-border-grid gap-2 md:gap-4">
                      <button
                        onClick={() => setPgcSubView('audit')}
                        className={`px-4 py-3 md:py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 font-mono ${pgcSubView === 'audit' ? 'border-primary-tactile text-primary-tactile' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                      >
                        Resumo
                      </button>
                      <button
                        onClick={() => setPgcSubView('plano')}
                        className={`px-4 py-3 md:py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 font-mono ${pgcSubView === 'plano' ? 'border-primary-tactile text-primary-tactile' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                      >
                        Plano
                      </button>
                      <button
                        onClick={() => setPgcSubView('status')}
                        className={`px-4 py-3 md:py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 font-mono ${pgcSubView === 'status' ? 'border-primary-tactile text-primary-tactile' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                      >
                        Status PGD
                      </button>
                      <button
                        onClick={() => setPgcSubView('automatizadas')}
                        className={`px-4 py-3 md:py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all border-b-4 font-mono ${pgcSubView === 'automatizadas' ? 'border-primary-tactile text-primary-tactile' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                      >
                        Ações
                      </button>
                    </div>
                    {pgcSubView === 'audit' && (
                      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 md:gap-4 h-[calc(100vh-200px)] pb-4">
                        <div className={`lg:col-span-3 rounded-none border-2 flex flex-col overflow-hidden h-full ${isDarkTheme ? 'bg-slate-900 border-border-grid' : 'bg-white border-border-grid shadow-sm'}`}>
                          <div className={`p-4 border-b-2 border-border-grid flex-shrink-0 ${isDarkTheme ? 'bg-slate-800' : 'bg-slate-50'}`}>
                            <div className="flex items-center justify-between">
                              <h4 className="text-[10px] font-black text-slate-900 tracking-widest uppercase font-mono">Pendentes</h4>
                              <span className="bg-slate-900 text-white text-[9px] font-black px-2 py-0.5 rounded-none font-mono">{pgcTasksAguardando.length}</span>
                            </div>
                            <p className="text-slate-400 text-[9px] font-black uppercase tracking-widest mt-1 font-mono">Arraste p/ vincular</p>
                          </div>
                          <div className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-hide">
                            {pgcTasksAguardando.map(task => (
                              <PgcMiniTaskCard key={task.id} task={task} onClick={() => setSelectedTask(task)} />
                            ))}
                            {pgcTasksAguardando.length === 0 && (
                              <div className="py-10 text-center">
                                <p className="text-slate-300 font-black text-[9px] uppercase tracking-widest italic font-mono">Tudo limpo!</p>
                              </div>
                            )}
                          </div>
                        </div>
                        <div className={`lg:col-span-9 rounded-none border-2 overflow-hidden flex flex-col h-full ${isDarkTheme ? 'bg-slate-900 border-border-grid' : 'bg-white border-border-grid shadow-sm'}`}>
                          <div className="flex-1 overflow-y-auto divide-y-2 divide-border-grid scrollbar-hide">
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
                                    <PgdAuditRow
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
                                      onCreateActivity={async (draft) => {
                                        let targetId = entregaId;
                                        if (!targetId) {
                                          targetId = await handleCreateEntregaFromPlan(item) || undefined;
                                        }
                                        if (targetId) handleCreatePgdActivity(targetId, draft);
                                      }}
                                      onUpdateActivity={handleUpdatePgdActivity}
                                      onDeleteActivity={handleDeletePgdActivity}
                                      onGenerateWithAI={() => {
                                        if (!entregaId) return;
                                        handleGeneratePgdFromDiaries(entregaId, item, tarefasRelacionadas);
                                      }}
                                      onProcessRawText={async (rawText) => {
                                        let targetId = entregaId;
                                        if (!targetId) {
                                          targetId = await handleCreateEntregaFromPlan(item) || undefined;
                                        }
                                        if (targetId) handleGeneratePgdFromRawText(targetId, item, rawText);
                                      }}
                                      isGeneratingAI={entregaId ? !!pgdGeneratingByEntrega[entregaId] : false}
                                      isProcessingRawText={entregaId ? !!pgdRawTextProcessingByEntrega[entregaId] : false}
                                    />
                                  </React.Fragment>
                                );
                              });
                            })()}
                          </div>
                        </div>
                      </div>
                    )}
                    {pgcSubView === 'status' && (
                      <div className="animate-in space-y-4">
                        {!pgdStatus.hasPlan ? (
                          <div className={`border-2 border-dashed border-border-grid p-12 text-center ${isDarkTheme ? 'bg-slate-900' : 'bg-white'}`}>
                            <p className="text-slate-400 font-black text-xs uppercase tracking-[0.2em] italic font-mono">
                              [ ERRO: PLANO DE TRABALHO NÃO LOCALIZADO ]
                            </p>
                          </div>
                        ) : (
                          <>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                              <div className={`border-2 border-border-grid p-4 ${isDarkTheme ? 'bg-slate-800' : 'bg-white shadow-sm'}`}>
                                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 font-mono">Úteis (Mês)</p>
                                <p className="mt-2 text-2xl font-black text-slate-900 font-mono">{pgdStatus.totalWorkDaysInMonth}</p>
                                <div className="h-0.5 bg-slate-100 mt-2"></div>
                                <p className="text-[8px] font-black uppercase text-slate-400 mt-1 font-mono">Previstos</p>
                              </div>
                              <div className={`border-2 border-border-grid p-4 ${isDarkTheme ? 'bg-slate-800' : 'bg-white shadow-sm'}`}>
                                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 font-mono">Esperados</p>
                                <p className="mt-2 text-2xl font-black text-slate-900 font-mono">{pgdStatus.expectedDaysCount}</p>
                                <div className="h-0.5 bg-slate-100 mt-2"></div>
                                <p className="text-[8px] font-black uppercase text-slate-400 mt-1 font-mono">Afast. Descontados</p>
                              </div>
                              <div className={`border-2 border-border-grid p-4 ${isDarkTheme ? 'bg-slate-800' : 'bg-white shadow-sm'}`}>
                                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 font-mono">Com Registro</p>
                                <p className="mt-2 text-2xl font-black text-emerald-600 font-mono">{pgdStatus.workedDaysCount}</p>
                                <div className="h-0.5 bg-emerald-50 mt-2"></div>
                                <p className="text-[8px] font-black uppercase text-emerald-500 mt-1 font-mono">Atividades PGD</p>
                              </div>
                              <div className={`border-2 border-border-grid p-4 ${isDarkTheme ? 'bg-slate-800' : 'bg-white shadow-sm'}`}>
                                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 font-mono">Cobertura</p>
                                <p className="mt-2 text-2xl font-black text-primary-tactile font-mono">{pgdStatus.coveragePct}%</p>
                                <div className="h-0.5 bg-amber-50 mt-2"></div>
                                <p className="text-[8px] font-black uppercase text-primary-tactile mt-1 font-mono">{pgdStatus.notWorkedDaysCount} Dias Pendentes</p>
                              </div>
                            </div>
                            <div className={`border-2 border-border-grid p-4 md:p-6 ${isDarkTheme ? 'bg-slate-800' : 'bg-white shadow-sm'}`}>
                              <div className="flex items-center justify-between mb-6 border-b border-border-grid pb-4">
                                <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] font-mono">Monitoramento de Carga Diária</h4>
                                <span className="text-[9px] font-black text-slate-400 uppercase font-mono tracking-widest">
                                  {pgdStatus.volumeByDay.length} Slots de Medição
                                </span>
                              </div>
                              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 xl:grid-cols-9 gap-2">
                                {pgdStatus.volumeByDay.map((d) => {
                                  const widthPct = Math.round((d.volume / pgdStatus.maxVolume) * 100);
                                  return (
                                    <div key={d.dayStr} className="border border-border-grid p-2 bg-slate-50/50">
                                      <p className="text-[10px] font-black text-slate-600 font-mono">{d.label}</p>
                                      <div className="mt-2 h-2 bg-slate-100 rounded-none overflow-hidden border border-border-grid">
                                        <div
                                          className={`h-full ${d.volume > 0 ? 'bg-emerald-500' : 'bg-slate-200'}`}
                                          style={{ width: `${widthPct}%` }}
                                        />
                                      </div>
                                      <p className="mt-1.5 text-[8px] font-black text-slate-400 uppercase font-mono tracking-tighter">{d.volume} Log(s)</p>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                              <div className={`border-2 border-border-grid p-4 ${isDarkTheme ? 'bg-slate-800' : 'bg-white shadow-sm'}`}>
                                <h5 className="text-[10px] font-black uppercase tracking-widest text-rose-500 font-mono">Divergências: Vínculo</h5>
                                <p className="text-[9px] text-slate-400 mt-1 font-mono uppercase tracking-tighter">Entregas sem Ações Associadas</p>
                                <div className="mt-4 space-y-1.5 max-h-64 overflow-y-auto pr-1 scrollbar-hide">
                                  {pgdStatus.entregasSemVinculo.length === 0 ? (
                                    <p className="text-[10px] text-slate-300 font-mono uppercase italic">[ STATUS_OK ]</p>
                                  ) : pgdStatus.entregasSemVinculo.map((e) => (
                                    <div key={`v-${e.key}`} className="p-2 border border-border-grid bg-slate-50/50">
                                      <p className="text-[10px] font-bold text-slate-700 font-mono uppercase">{e.entrega}</p>
                                    </div>
                                  ))}
                                </div>
                              </div>
                              <div className={`border-2 border-border-grid p-4 ${isDarkTheme ? 'bg-slate-800' : 'bg-white shadow-sm'}`}>
                                <h5 className="text-[10px] font-black uppercase tracking-widest text-primary-tactile font-mono">Divergências: Registro</h5>
                                <p className="text-[9px] text-slate-400 mt-1 font-mono uppercase tracking-tighter">Entregas sem Execução PGD</p>
                                <div className="mt-4 space-y-1.5 max-h-64 overflow-y-auto pr-1 scrollbar-hide">
                                  {pgdStatus.entregasSemRegistros.length === 0 ? (
                                    <p className="text-[10px] text-slate-300 font-mono uppercase italic">[ STATUS_OK ]</p>
                                  ) : pgdStatus.entregasSemRegistros.map((e) => (
                                    <div key={`r-${e.key}`} className="p-2 border border-border-grid bg-slate-50/50">
                                      <p className="text-[10px] font-bold text-slate-700 font-mono uppercase">{e.entrega}</p>
                                    </div>
                                  ))}
                                </div>
                              </div>
                              <div className={`border-2 border-border-grid p-4 ${isDarkTheme ? 'bg-slate-800' : 'bg-white shadow-sm'}`}>
                                <h5 className="text-[10px] font-black uppercase tracking-widest text-blue-500 font-mono">Prazos em Aberto</h5>
                                <p className="text-[9px] text-slate-400 mt-1 font-mono uppercase tracking-tighter">Dias úteis s/ apontamento</p>
                                <div className="mt-4 flex flex-wrap gap-1.5 max-h-64 overflow-y-auto pr-1 scrollbar-hide">
                                  {pgdStatus.notWorkedDays.length === 0 ? (
                                    <p className="text-[10px] text-slate-300 font-mono uppercase italic">[ STATUS_OK ]</p>
                                  ) : pgdStatus.notWorkedDays.map((d) => (
                                    <span key={d.dayStr} className="px-2 py-1 border border-border-grid bg-slate-50 text-[10px] font-black text-slate-600 font-mono">
                                      {d.label}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    )}
                    {pgcSubView === 'plano' && (
                      <div className="animate-in space-y-6">
                        <div className={`border-2 border-border-grid overflow-hidden ${isDarkTheme ? 'bg-slate-900' : 'bg-white shadow-md'}`}>
                          {/* Desktop Table */}
                          <table className="w-full text-left min-w-[800px] hidden md:table">
                            <thead className={`border-b-2 border-border-grid ${isDarkTheme ? 'bg-slate-800' : 'bg-slate-50'}`}>
                              <tr>
                                <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] font-mono">Origem / Unidade</th>
                                <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] font-mono">Entrega Institucional</th>
                                <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] font-mono">Descrição Técnica</th>
                                <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] font-mono w-[180px]">Alocação</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y-2 divide-border-grid">
                              {planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)?.itens.map((item, i) => (
                                <tr key={i} className="hover:bg-slate-50 transition-colors">
                                  <td className="px-6 py-4">
                                    <div className="text-[9px] font-black text-primary-tactile uppercase mb-1 font-mono">{item.origem}</div>
                                    <div className="text-[11px] font-black text-slate-900 font-mono">{item.unidade}</div>
                                  </td>
                                  <td className="px-6 py-4 text-[12px] font-black text-slate-900 font-mono uppercase leading-tight">{item.entrega}</td>
                                  <td className="px-6 py-4 text-[10px] font-medium text-slate-500 leading-relaxed max-w-xs font-mono">{item.descricao}</td>
                                  <td className="px-6 py-4">
                                    <div className="flex items-center gap-3">
                                      <div className="flex-1 h-3 bg-slate-100 rounded-none overflow-hidden border border-border-grid">
                                        <div className="h-full bg-slate-900 rounded-none transition-all duration-1000" style={{ width: `${item.percentual}%` }}></div>
                                      </div>
                                      <span className="text-[10px] font-black text-slate-900 w-10 font-mono">{item.percentual}%</span>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {/* Mobile Card View */}
                          <div className="md:hidden divide-y divide-border-grid">
                            {planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)?.itens.map((item, i) => (
                              <div key={i} className="p-4 space-y-3">
                                <div className="flex justify-between items-start gap-4">
                                  <div className="flex-1">
                                    <div className="text-[8px] font-black text-primary-tactile uppercase mb-1 font-mono">{item.origem} â€¢ {item.unidade}</div>
                                    <div className="text-xs font-black text-slate-900 leading-tight font-mono uppercase">{item.entrega}</div>
                                  </div>
                                  <div className="bg-slate-900 text-white px-2 py-0.5 rounded-none text-[9px] font-black font-mono">{item.percentual}%</div>
                                </div>
                                <p className="text-[10px] text-slate-500 leading-relaxed font-mono">{item.descricao}</p>
                                <div className="h-2 bg-slate-100 rounded-none overflow-hidden border border-border-grid">
                                  <div className="h-full bg-slate-900 rounded-none" style={{ width: `${item.percentual}%` }}></div>
                                </div>
                              </div>
                            ))}
                          </div>
                          {(!planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`)) && (
                            <div className="px-8 py-20 text-center">
                              <p className="text-slate-400 font-black text-[10px] uppercase tracking-[0.3em] font-mono italic">[ NENHUM PLANO CONFIGURADO ]</p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                    {pgcSubView === 'automatizadas' && (
                      <div className="animate-in space-y-6">
                        <div className={`border-2 border-border-grid rounded-none overflow-hidden ${isDarkTheme ? 'bg-slate-900' : 'bg-white shadow-xl'} p-4 md:p-8`}>
                          <div className="flex items-center justify-between mb-8 pb-4 border-b-2 border-border-grid">
                            <div>
                              <h3 className="text-xl font-black text-slate-900 tracking-tight font-mono uppercase">Módulos de Automação</h3>
                              <p className="text-[9px] font-black text-slate-400 uppercase tracking-[0.3em] mt-1 font-mono">Hermes R.P.A. Core Engine</p>
                            </div>
                            <div className="bg-slate-900 text-primary-tactile p-3 rounded-none border border-border-grid">
                              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                            </div>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                            {/* Card: Ponto Eletrônico */}
                            <div className="border-2 border-border-grid rounded-none p-6 bg-slate-50 group flex flex-col justify-between h-full relative overflow-hidden transition-all hover:border-emerald-500/50">
                              <div className="absolute top-0 left-0 w-1.5 h-full bg-emerald-500 opacity-20 group-hover:opacity-100 transition-opacity"></div>
                              <div>
                                <div className="flex items-center gap-3 mb-4">
                                  <div className="p-2 bg-emerald-100 text-emerald-600 rounded-none border border-emerald-200">
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                  </div>
                                  <h4 className="text-[11px] font-black text-slate-800 uppercase tracking-widest font-mono">Ponto Eletrônico</h4>
                                </div>
                                <p className="text-[10px] text-slate-500 font-mono leading-relaxed mb-6">
                                  Acesso remoto SIGRH &gt; Preenchimento automático de relógio mensal via PGD.
                                </p>
                              </div>
                              <button
                                onClick={async () => {
                                  showToast('Iniciando automação do ponto eletrônico...', 'info');
                                  try {
                                    const response = await fetch('http://127.0.0.1:8000/api/automations/ponto-eletronico', {
                                      method: 'POST',
                                    });
                                    if (response.ok) {
                                      showToast('Script do Ponto Eletrônico acionado com sucesso!', 'success');
                                    } else {
                                      showToast('Erro ao contatar o servidor local de automação.', 'error');
                                    }
                                  } catch (e) {
                                    showToast('O servidor Python de automação (server.py) não está rodando.', 'error');
                                  }
                                }}
                                className="w-full bg-slate-900 text-white py-3 rounded-none text-[10px] font-black uppercase tracking-[0.2em] hover:bg-emerald-600 transition-all shadow-md font-mono"
                              >
                                Executar Script
                              </button>
                            </div>
                            {/* Card: Criação de Plano PGD */}
                            <div className="border-2 border-border-grid rounded-none p-6 bg-slate-50 group flex flex-col justify-between h-full relative overflow-hidden transition-all hover:border-violet-500/50">
                              <div className="absolute top-0 left-0 w-1.5 h-full bg-violet-500 opacity-20 group-hover:opacity-100 transition-opacity"></div>
                              <div>
                                <div className="flex items-center gap-3 mb-4">
                                  <div className="p-2 bg-violet-100 text-violet-600 rounded-none border border-violet-200">
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
                                    </svg>
                                  </div>
                                  <h4 className="text-[11px] font-black text-slate-800 uppercase tracking-widest font-mono">Criar Plano PGD</h4>
                                </div>
                                <p className="text-[10px] text-slate-500 font-mono leading-relaxed mb-6">
                                  Seleção de entregas, descrições históricas e distribuição automática de carga para o próximo plano mensal.
                                </p>
                                <div className="mb-6 p-3 bg-violet-50 border border-violet-200">
                                  <p className="text-[9px] font-black text-violet-700 leading-tight uppercase font-mono">
                                    Inclui as duas entregas fixas e grava o plano no Petrvs.
                                  </p>
                                </div>
                              </div>
                              <button
                                onClick={() => setIsCreatePgdPlanOpen(true)}
                                className="w-full bg-slate-900 text-white py-3 rounded-none text-[10px] font-black uppercase tracking-[0.2em] hover:bg-violet-600 transition-all shadow-md font-mono"
                              >
                                Preparar novo plano
                              </button>
                            </div>
                            {/* Card: Execução PGD (Petrvs) */}
                            <div className="border-2 border-border-grid rounded-none p-6 bg-slate-50 group flex flex-col justify-between h-full relative overflow-hidden transition-all hover:border-blue-500/50">
                              <div className="absolute top-0 left-0 w-1.5 h-full bg-blue-500 opacity-20 group-hover:opacity-100 transition-opacity"></div>
                              <div>
                                <div className="flex items-center gap-3 mb-4">
                                  <div className="p-2 bg-blue-100 text-blue-600 rounded-none border border-blue-200">
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                  </div>
                                  <h4 className="text-[11px] font-black text-slate-800 uppercase tracking-widest font-mono">Execução PGD</h4>
                                </div>
                                <p className="text-[10px] text-slate-500 font-mono leading-relaxed mb-6">
                                  Push de registros salvos &gt; Petrvs (Entregas Institucionais).
                                </p>
                                {(() => {
                                  const currentPlan = planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`);
                                  if (!currentPlan) return null;
                                  const totalEntregas = currentPlan.itens.length;
                                  const entregasComRegistro = currentPlan.itens.filter(item => {
                                    const entregaEntity = pgcEntregas.find(e => e.entrega === item.entrega);
                                    const registros = entregaEntity ? atividadesPGC.filter(a => a.entrega_id === entregaEntity.id) : [];
                                    return registros.length > 0;
                                  }).length;
                                  const faltaRegistros = entregasComRegistro < totalEntregas;
                                  if (faltaRegistros) {
                                    return (
                                      <div className="mb-6 p-3 bg-amber-50 border border-amber-200 rounded-none flex items-start gap-3 animate-pulse">
                                        <svg className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                                        <p className="text-[9px] font-black text-amber-700 leading-tight uppercase font-mono">
                                          Pendente: {totalEntregas - entregasComRegistro} entrega(s) sem registro.
                                        </p>
                                      </div>
                                    );
                                  }
                                  return (
                                    <div className="mb-6 p-3 bg-emerald-50 border border-emerald-200 rounded-none flex items-start gap-3">
                                      <svg className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                      <p className="text-[9px] font-black text-emerald-700 leading-tight uppercase font-mono">
                                        Data-Ready: Todos os vínculos estabelecidos.
                                      </p>
                                    </div>
                                  );
                                })()}
                              </div>
                              <button
                                onClick={async () => {
                                  const currentPlan = planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`);
                                  if (!currentPlan) {
                                    showToast('Nenhum plano de trabalho encontrado para este mês.', 'error');
                                    return;
                                  }
                                  const allDeliveries = currentPlan.itens.map(item => {
                                    const entregaEntity = pgcEntregas.find(e => e.entrega === item.entrega);
                                    const registros = entregaEntity ? atividadesPGC.filter(a => a.entrega_id === entregaEntity.id) : [];
                                    return {
                                      nome_entrega: item.entrega,
                                      registros: registros.map(r => ({
                                        descricao_atividade: r.descricao_atividade,
                                        data_inicio: r.data_inicio,
                                        data_fim: r.data_fim
                                      }))
                                    };
                                  });
                                  const missingAny = allDeliveries.some(e => e.registros.length === 0);
                                  if (missingAny) {
                                    showToast('Não é possível executar: existem entregas sem registros.', 'error');
                                    return;
                                  }
                                  const payload = {
                                    mes_ano: currentPlan.mes_ano,
                                    entregas: allDeliveries
                                  };
                                  showToast('Iniciando automação do PGD no Petrvs...', 'info');
                                  try {
                                    const response = await fetch('http://127.0.0.1:8000/api/automations/executar-pgd', {
                                      method: 'POST',
                                      headers: { 'Content-Type': 'application/json' },
                                      body: JSON.stringify(payload),
                                    });
                                    if (response.ok) {
                                      showToast('Pacote de dados enviado! Iniciando monitoramento...', 'success');
                                      setPgdTerminalLogs([]);
                                      setIsPgdTerminalOpen(true);
                                    } else {
                                      showToast('Erro no processamento do servidor de automação.', 'error');
                                    }
                                  } catch (e) {
                                    showToast('Servidor de automação não está respondendo.', 'error');
                                  }
                                }}
                                className={`w-full py-3 rounded-none text-[10px] font-black uppercase tracking-[0.2em] transition-all shadow-md font-mono ${(() => {
                                  const currentPlan = planosTrabalho.find(p => p.mes_ano === `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`);
                                  const missing = currentPlan?.itens.some(item => {
                                    const entregaEntity = pgcEntregas.find(e => e.entrega === item.entrega);
                                    const registros = entregaEntity ? atividadesPGC.filter(a => a.entrega_id === entregaEntity.id) : [];
                                    return registros.length === 0;
                                  });
                                  return missing ? 'bg-slate-200 text-slate-400 cursor-not-allowed opacity-60' : 'bg-slate-900 text-white hover:bg-blue-600';
                                })()
                                  }`}
                              >
                                Sincronizar Petrvs
                              </button>
                              {isPgdTerminalOpen && (
                                <div className="mt-6 border-2 border-slate-800 rounded-none overflow-hidden shadow-2xl relative animate-in zoom-in-95 duration-300">
                                  <div className="bg-slate-900 border-b-2 border-slate-800 p-3 flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                      <div className="flex gap-1 group">
                                        <div onClick={() => setIsPgdTerminalOpen(false)} className="w-3 h-3 rounded-none bg-red-600 cursor-pointer flex items-center justify-center transition-all hover:bg-red-500">
                                          <svg className="w-2 h-2 text-white opacity-0 group-hover:opacity-100" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M6 18L18 6M6 6l12 12" /></svg>
                                        </div>
                                        <div className="w-3 h-3 rounded-none bg-slate-700"></div>
                                        <div className="w-3 h-3 rounded-none bg-slate-700"></div>
                                      </div>
                                      <span className="ml-3 text-slate-500 font-mono text-[9px] font-black uppercase tracking-widest">CONSOLE::RPA_ENGINE::STITCH_CORE</span>
                                    </div>
                                    <button onClick={() => setPgdTerminalLogs([])} className="text-slate-500 hover:text-white transition-colors" title="Limpar Terminal">
                                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                    </button>
                                  </div>
                                  <div className="bg-black p-5 h-[320px] overflow-y-auto font-mono text-[11px] leading-relaxed text-emerald-500 flex flex-col justify-end border-t border-slate-800">
                                    <div className="flex-1"></div>
                                    <div className="flex flex-col justify-end">
                                      {pgdTerminalLogs.length === 0 ? (
                                        <div className="text-emerald-900/50 flex items-center gap-2">
                                          <div className="w-2 h-2 rounded-none bg-emerald-500 animate-pulse"></div>
                                          [ INICIALIZANDO SUBSISTEMA DE AUTOMAÇÃO... ]
                                        </div>
                                      ) : (
                                        pgdTerminalLogs.map((log, i) => (
                                          <div key={i} className="whitespace-pre-wrap border-l border-emerald-900/30 pl-3 mb-1">{log}</div>
                                        ))
                                      )}
                                      <div className="mt-1 text-emerald-400 animate-pulse flex items-center gap-1">
                                        <span className="text-[9px] opacity-50">STITCH@HERMES:~$</span>
                                        <span className="w-2 h-4 bg-emerald-500"></span>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </main>
            </div>
          </>
        </div>
        {isCreatePgdPlanOpen && (
          <CreatePgdPlanModal
            plans={planosTrabalho}
            onClose={() => setIsCreatePgdPlanOpen(false)}
            onSubmit={handleCreatePgdPlan}
          />
        )}
        <ToastContainer toasts={toasts} removeToast={removeToast} />
        <HermesModal {...modalState} />
        {
          isCreateModalOpen && (
            <TaskCreateModal
              unidades={unidades}
              knowledgeBases={knowledgeBases}
              knowledgeItems={knowledgeItems}
              onSave={handleCreateTarefa}
              onClose={() => {
                setIsCreateModalOpen(false);
                setTaskInitialData(null);
              }}
              showAlert={showAlert}
              initialData={taskInitialData || undefined}
              existingTags={Array.from(new Set(tarefas.flatMap(t => t.tags || [])))}
            />
          )
        }
        {
          selectedTask && (
            (taskModalMode === 'execute' || (taskModalMode === 'default' && selectedTask.area_tematica === 'CLC')) ? (
              <TaskExecutionView
                task={selectedTask}
                tarefas={tarefas}
                isDark={isDarkTheme}
                appSettings={appSettings}
                knowledgeBases={knowledgeBases}
                onSave={handleUpdateTarefa}
                unidades={unidades}
                onClose={() => setSelectedTask(null)}
                showToast={showToast}
                notifications={notifications}
                isSyncing={isSyncing}
                isNotificationCenterOpen={isNotificationCenterOpen}
                onOpenNotes={() => setIsQuickNoteModalOpen(true)}

                onOpenShopping={() => setIsShoppingAIModalOpen(true)}
                onOpenCopiloto={() => setIsCopilotoOpen(true)}
                onOpenTranscription={() => setIsTranscriptionAIModalOpen(true)}
                onOpenMeetingTranscription={() => {
                  setActiveModule('acoes');
                  setViewMode('ferramentas');
                  setActiveFerramenta('meeting_transcription');
                  setSelectedTask(null);
                }}
                onToggleNotifications={() => setIsNotificationCenterOpen(prev => !prev)}
                onSync={handleSync}
                onOpenSettings={() => setIsSettingsModalOpen(true)}
                onCloseNotifications={() => setIsNotificationCenterOpen(false)}
                onMarkAsRead={handleMarkNotificationRead}
                onDismiss={handleDismissNotification}
                copilotoUserId={user?.uid || ''}
                onOpenCopilotoTask={async (id) => {
                  const task = tarefas.find(t => t.id === id);
                  if (task) {
                    setSelectedTask(task);
                    setTaskModalMode('execute');
                    return;
                  }
                  const snap = await getDoc(doc(db, 'tarefas', id));
                  if (snap.exists()) {
                    setSelectedTask({ id: snap.id, ...snap.data() } as any);
                    setTaskModalMode('execute');
                  }
                }}
                onOpenCopilotoTool={(tool, id) => {
                  setSelectedTask(null);
                  setActiveModule('acoes');
                  setViewMode('ferramentas');
                  if (tool === 'diagnostico') {
                    setActiveFerramenta('diagnostico');
                    setInitialDiagnosisId(id);
                  }
                }}
                onCreateAction={() => setIsCreateModalOpen(true)}
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
                existingTags={Array.from(new Set(tarefas.flatMap(t => t.tags || [])))}
              />
            )
          )
        }
        {/* â”€â”€ Sistema Execution View (full-screen overlay) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}

        {
          isTerminalOpen && (
            <div className="fixed inset-0 z-[150] flex items-center justify-center p-4 bg-slate-950/90 animate-in fade-in duration-300">
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
                          await setDoc(doc(db, 'system', 'sync'), { status: 'idle', logs: [...(syncData?.logs || []), "--- INTERROMPIDO PELO USUÃRIO ---"] });
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
                  {!isSyncing && syncData?.status === 'completed' && (() => {
                    const hasSyncError = (syncData?.logs || []).some((log: string) =>
                      typeof log === 'string' && log.toUpperCase().includes('ERRO')
                    );
                    return (
                      <div className={`pt-4 border-t border-white/5 font-bold ${hasSyncError ? 'text-amber-400' : 'text-emerald-400'}`}>
                        {hasSyncError ? '? SINCRONIZAÇÃO CONCLUÃDA COM ERROS.' : '? SINCRONIZAÇÃO CONCLUÃDA COM SUCESSO.'}
                      </div>
                    );
                  })()}
                  {syncData?.status === 'error' && (
                    <div className="pt-4 border-t border-white/5 text-rose-500 font-bold">
                      ? FALHA NO PROCESSAMENTO: {syncData.error_message}
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
              themeMode={themeMode}
              onThemeModeChange={setThemeMode}
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
          isImportPlanOpen && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/90 animate-in fade-in duration-300">
              <div className="bg-white w-full max-w-2xl rounded-none shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
                <div className="p-8 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
                  <div>
                    <h3 className="text-2xl font-black text-slate-900 tracking-tight">Importar Plano Mensal</h3>
                    <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">Cole o JSON do plano de trabalho abaixo</p>
                  </div>
                  <button onClick={() => setIsImportPlanOpen(false)} className="p-2 hover:bg-slate-200 rounded-none transition-colors">
                    <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>
                <div className="p-8 space-y-6">
                  <div className="grid grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Ano</label>
                      <input type="number" id="import-year" defaultValue={currentYear} className="w-full bg-slate-100 border-none rounded-none px-6 py-4 text-sm font-bold text-slate-900" />
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Mês</label>
                      <select id="import-month" defaultValue={currentMonth + 1} className="w-full bg-slate-100 border-none rounded-none px-6 py-4 text-sm font-bold text-slate-900">
                        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(m => <option key={m} value={m}>{m}</option>)}
                      </select>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Dump JSON</label>
                    <textarea
                      id="import-json"
                      rows={10}
                      className="w-full bg-slate-900 text-blue-400 border-none rounded-none px-6 py-4 text-[10px] font-mono focus:ring-2 focus:ring-blue-500 transition-all resize-none"
                      placeholder='[ { "entrega": "Exemplo", "percentual": 50 }, ... ]'
                    />
                  </div>
                </div>
                <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4">
                    <button
                      onClick={() => setIsImportPlanOpen(false)}
                      className="flex-1 px-8 py-4 rounded-none text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all font-mono"
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
                            const originMarkers = new Set([
                              'Própria Unidade',
                              'Outra Unidade',
                              'Não vinculadas a entregas'
                            ]);
                            const skipMarkers = new Set([
                              'Curtir',
                              'Origem / Unidade',
                              'Entrega Institucional',
                              'Descrição',
                              '% Carga Horária',
                              'Detalhe/Descreva os trabalhos'
                            ]);
                            const isPercentLine = (value: string) => /^\d+(?:[.,]\d+)?%$/.test(value);
                            const parsePercent = (value: string) => parseFloat(value.replace('%', '').replace(',', '.')) || 0;
                            for (let i = 0; i < lines.length; i++) {
                              const line = lines[i];
                              if (!originMarkers.has(line)) continue;
                              const item: Partial<PlanoTrabalhoItem> = {
                                origem: line,
                                unidade: '',
                                entrega: '',
                                percentual: 0,
                                descricao: ''
                              };
                              if (line === 'Não vinculadas a entregas') {
                                item.entrega = line;
                              } else {
                                if (lines[i + 1] && !originMarkers.has(lines[i + 1]) && !isPercentLine(lines[i + 1]) && !skipMarkers.has(lines[i + 1])) {
                                  item.unidade = lines[++i] || '';
                                }
                                if (lines[i + 1] && !originMarkers.has(lines[i + 1]) && !isPercentLine(lines[i + 1]) && !skipMarkers.has(lines[i + 1])) {
                                  item.entrega = lines[++i] || '';
                                }
                              }
                              while (lines[i + 1] && skipMarkers.has(lines[i + 1])) i++;
                              if (lines[i + 1] && isPercentLine(lines[i + 1])) {
                                item.percentual = parsePercent(lines[++i]);
                              }
                              while (lines[i + 1] && skipMarkers.has(lines[i + 1])) i++;
                              if (lines[i + 1] && !originMarkers.has(lines[i + 1]) && !isPercentLine(lines[i + 1]) && !skipMarkers.has(lines[i + 1])) {
                                item.descricao = lines[++i] || '';
                              }
                              items.push(item as PlanoTrabalhoItem);
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
                      className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-none text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all font-mono"
                    >
                      Processar e Gravar
                    </button>
                </div>
              </div>
            </div>
          )
        }
        {
          isSystemSelectorOpen && (
            <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-slate-950/90">
              <div className="bg-white w-full max-w-md rounded-none shadow-2xl overflow-hidden animate-in zoom-in-95 border-2 border-border-grid">
                <div className="p-6 border-b border-border-grid flex items-center justify-between bg-slate-50">
                  <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest font-mono">Selecionar Sistema</h3>
                  <button onClick={() => setIsSystemSelectorOpen(false)} className="p-2 hover:bg-slate-200 rounded-none transition-colors">
                    <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>
                <div className="p-6 space-y-2 max-h-[400px] overflow-y-auto custom-scrollbar">
                  {unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(sistema => (
                    <button
                      key={sistema.id}
                      onClick={() => handleFinalizeIdeaConversion(sistema.id)}
                      className="w-full text-left p-4 rounded-none border-2 border-slate-100 hover:border-primary-tactile hover:bg-amber-50 transition-all flex items-center gap-3 group"
                    >
                      <div className="w-10 h-10 bg-slate-100 group-hover:bg-primary-tactile group-hover:text-white rounded-none flex items-center justify-center transition-colors border border-transparent group-hover:border-primary-tactile">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                      </div>
                      <span className="text-xs font-black text-slate-700 group-hover:text-amber-900 font-mono uppercase">{sistema.nome.replace('SISTEMA:', '').trim()}</span>
                    </button>
                  ))}
                  {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length === 0 && (
                    <p className="text-center text-slate-400 py-8 italic text-[10px] font-mono uppercase tracking-widest">[ NENHUM SISTEMA CADASTRADO ]</p>
                  )}
                </div>
              </div>
            </div>
          )
        }
        {
          isQuickNoteModalOpen && (
            <QuickNoteModal
              isOpen={isQuickNoteModalOpen}
              onClose={() => setIsQuickNoteModalOpen(false)}
              onAddIdea={handleAddTextIdea}
              showAlert={showAlert}
            />
          )
        }
        {
          isShoppingAIModalOpen && (
            <ShoppingAIModal
              isOpen={isShoppingAIModalOpen}
              onClose={() => setIsShoppingAIModalOpen(false)}
              catalogItems={shoppingItems}
              onConfirmItems={handleShoppingAIConfirm}
              plannedCount={shoppingItems.filter(i => i.isPlanned).length}
              onViewList={() => {
                setActiveModule('acoes');
                setViewMode('ferramentas');
                setActiveFerramenta('shopping');
                setIsShoppingAIModalOpen(false);
              }}
            />
          )
        }
        {
          isTranscriptionAIModalOpen && (
            <TranscriptionAIModal
              isOpen={isTranscriptionAIModalOpen}
              onClose={() => setIsTranscriptionAIModalOpen(false)}
              showToast={showToast}
            />
          )
        }
        {!isCopilotoOpen && !isVoiceLiveActive && viewMode !== 'godmode' && !(selectedTask && (taskModalMode === 'execute' || (taskModalMode === 'default' && selectedTask.area_tematica === 'CLC'))) && (
          <>
            {/* Backdrop invisivel: clique fora fecha o menu do launcher */}
            {isCopilotoLauncherOpen && (
              <div className="fixed inset-0 z-[595]" onClick={() => setIsCopilotoLauncherOpen(false)} />
            )}
            {/* Menu speed-dial: conversa por voz ao vivo ou copiloto por texto */}
            {isCopilotoLauncherOpen && (
              <div className="fixed bottom-24 right-6 z-[600] flex flex-col items-end gap-2 sm:bottom-[6.5rem]">
                <button
                  type="button"
                  onClick={() => {
                    setIsCopilotoLauncherOpen(false);
                    setIsVoiceLiveActive(true);
                  }}
                  className={`flex items-center gap-2.5 rounded-full py-2.5 pl-4 pr-5 text-sm font-semibold shadow-lg transition-all hover:-translate-y-0.5 active:scale-95 ${isDarkTheme ? 'bg-slate-800 text-slate-100 border border-white/10' : 'bg-white text-slate-800 border border-slate-200'}`}
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-600 text-white">
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 10v2a7 7 0 01-14 0v-2" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19v3" />
                    </svg>
                  </span>
                  Conversa por voz
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsCopilotoLauncherOpen(false);
                    if (viewMode === 'saude' || activeModule === 'saude') {
                      setCopilotoMode('saude');
                      setCopilotoAutoStartMic(false);
                    } else if (viewMode === 'finance' || activeModule === 'financeiro') {
                      setCopilotoMode('finance');
                      setCopilotoAutoStartMic(false);
                    } else {
                      // No módulo de Estratégia o copiloto abre focado nos objetivos/diretrizes
                      // e com as ferramentas de criação/edição/exclusão habilitadas.
                      setCopilotoMode(viewMode === 'strategy' ? 'estrategia' : 'default');
                    }
                    setIsCopilotoOpen(true);
                  }}
                  className={`flex items-center gap-2.5 rounded-full py-2.5 pl-4 pr-5 text-sm font-semibold shadow-lg transition-all hover:-translate-y-0.5 active:scale-95 ${isDarkTheme ? 'bg-slate-800 text-slate-100 border border-white/10' : 'bg-white text-slate-800 border border-slate-200'}`}
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-white">
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                  </span>
                  Conversa por texto
                </button>
              </div>
            )}
            <button
              type="button"
              aria-label="Copiloto Hermes"
              aria-expanded={isCopilotoLauncherOpen}
              onClick={() => setIsCopilotoLauncherOpen(v => !v)}
              className={`fixed bottom-6 right-6 z-[600] flex h-14 w-14 items-center justify-center rounded-full text-white shadow-lg transition-all hover:-translate-y-0.5 active:scale-95 sm:h-16 sm:w-16 ${
                (viewMode === 'saude' || activeModule === 'saude')
                  ? 'bg-red-600 shadow-red-600/30 hover:bg-red-500'
                  : (viewMode === 'finance' || activeModule === 'financeiro')
                  ? 'bg-emerald-600 shadow-emerald-600/30 hover:bg-emerald-500'
                  : 'bg-indigo-600 shadow-indigo-600/30 hover:bg-indigo-500'
              }`}
            >
              <img
                src="/logo.png"
                alt=""
                aria-hidden="true"
                className={`h-8 w-8 object-contain transition-transform sm:h-9 sm:w-9 ${isCopilotoLauncherOpen ? 'rotate-12 scale-90' : ''}`}
                style={{ filter: 'brightness(0) invert(1)' }}
              />
            </button>
          </>
        )}
        {isVoiceLiveActive && (
          <HermesVoiceOverlay isDark={isDarkTheme} onExit={() => setIsVoiceLiveActive(false)} onUICommand={handleVoiceUICommand} uiContext={currentUIContext} />
        )}
        {!isStrategySplitCopilot && (
        <HermesGlobalChat
          isOpen={isCopilotoOpen}
          onClose={closeCopiloto}
          autoStartMic={copilotoAutoStartMic}
          copilotMode={copilotoMode}
          initialPrompt={copilotoInitialPrompt}
          onInitialPromptConsumed={() => setCopilotoInitialPrompt(null)}
          isDark={isDarkTheme}
          userId={user?.uid || ''}
          onOpenTask={handleCopilotoOpenTask}
          onOpenTool={handleCopilotoOpenTool}
        />
        )}
      </div>
    </>
  );
};
declare global {
  interface Window {
    __hermesReactRoot?: Root;
  }
}
const container = document.getElementById('root');
if (container) {
  if (!window.__hermesReactRoot) {
    window.__hermesReactRoot = createRoot(container);
  }
  window.__hermesReactRoot.render(<App />);
}
