import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Tarefa, AppSettings, PoolItem, ConhecimentoItem, Acompanhamento,
  formatDate, formatDateLocalISO
} from '../../types';
import { normalizeStatus } from '../utils/helpers';
import { buildDiaryRichNote, ensureHttpUrl, getRenamedFileName } from '../utils/diaryEntries';
import { AutoExpandingTextarea, NotificationCenter } from '../components/ui/UIComponents';
import { db, functions } from '../../firebase';
import { httpsCallable } from 'firebase/functions';
import { setDoc, doc } from 'firebase/firestore';
import { DiarioBordoUI } from './DiarioBordoUI';
import { PainelControleUI } from './PainelControleUI';
import { SpeedDialMenu } from '../components/ui/SpeedDialMenu';

const getPendingFileKey = (file: File) => `${file.name}-${file.size}-${file.lastModified}`;

interface TaskExecutionViewProps {
  task: Tarefa;
  tarefas: Tarefa[];
  appSettings: AppSettings;
  onSave: (id: string, updates: Partial<Tarefa>) => void;
  onClose: () => void;
  showToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
  // SpeedDial Props
  notifications: any[];
  isSyncing: boolean;
  isNotificationCenterOpen: boolean;
  onOpenNotes: () => void;
  onOpenLog: () => void;
  onOpenShopping: () => void;
  onOpenTranscription: () => void;
  onToggleNotifications: () => void;
  onSync: () => void;
  onOpenSettings: () => void;
  onCloseNotifications: () => void;
  onMarkAsRead: (id: string) => void;
  onDismiss: (id: string) => void;
  onCreateAction: () => void;
}

export const TaskExecutionView = ({
  task,
  tarefas,
  appSettings,
  onSave,
  onClose,
  showToast,
  notifications,
  isSyncing,
  isNotificationCenterOpen,
  onOpenNotes,
  onOpenLog,
  onOpenShopping,
  onOpenTranscription,
  onToggleNotifications,
  onSync,
  onOpenSettings,
  onCloseNotifications,
  onMarkAsRead,
  onDismiss,
  onCreateAction
}: TaskExecutionViewProps) => {
  // --- States ---
  const [newFollowUp, setNewFollowUp] = useState('');
  const [newPoolItem, setNewPoolItem] = useState('');
  const [showPool, setShowPool] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [chatUrl, setChatUrl] = useState(task.chat_gemini_url || '');
  const [isTimerRunning, setIsTimerRunning] = useState(false);
  const [pomodoroMode, setPomodoroMode] = useState<'focus' | 'break'>('focus');
  const [seconds, setSeconds] = useState(0);
  const [modalConfig, setModalConfig] = useState<{
    type: 'link' | 'contact' | 'edit_diary' | 'confirm_delete' | 'reset_timer' | 'file_upload' | 'reminder';
    data?: any;
    isOpen: boolean;
  }>({ type: 'link', isOpen: false });
  const [modalInputValue, setModalInputValue] = useState('');
  const [modalInputName, setModalInputName] = useState('');
  const [reminderDate, setReminderDate] = useState('');
  const [reminderTime, setReminderTime] = useState('');
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [pendingFileNames, setPendingFileNames] = useState<Record<string, string>>({});
  const [sessionTotalSeconds, setSessionTotalSeconds] = useState(task.tempo_total_segundos || 0);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editedTitle, setEditedTitle] = useState(task.titulo);
  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  // --- Transcription states ---
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessingTranscription, setIsProcessingTranscription] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const diaryEndRef = useRef<HTMLDivElement>(null);
  const diaryMobileEndRef = useRef<HTMLDivElement>(null);

  // --- Memos & Data ---
  const currentTaskData = useMemo(() => 
    tarefas.find(t => t.id === task.id) || task, 
    [tarefas, task.id, task]
  );

  const nextTask = useMemo(() => {
    const now = new Date();
    const todayStr = formatDateLocalISO(now);
    const currentTimeInMinutes = now.getHours() * 60 + now.getMinutes();

    const todayTasks = tarefas
      .filter(t => t.data_limite === todayStr && normalizeStatus(t.status) !== 'concluido' && t.horario_inicio && t.id !== task.id)
      .sort((a, b) => {
        const [ha, ma] = a.horario_inicio!.split(':').map(Number);
        const [hb, mb] = b.horario_inicio!.split(':').map(Number);
        return (ha * 60 + ma) - (hb * 60 + mb);
      });

    return todayTasks.find(t => {
      const [h, m] = t.horario_inicio!.split(':').map(Number);
      return (h * 60 + m) > currentTimeInMinutes;
    });
  }, [tarefas, task.id]);

  // --- Audio Recording Logic ---
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        await handleProcessAudio(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      showToast("Erro ao acessar microfone.", "error");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessingTranscription(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string; refined: string };
          if (data.refined) {
            setNewFollowUp(prev => prev + (prev ? '\n' : '') + data.refined);
          }
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          showToast("Erro ao processar áudio.", "error");
        } finally {
          setIsProcessingTranscription(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessingTranscription(false);
    }
  };

  // --- Timer & Pomodoro Logic ---
  useEffect(() => {
    let interval: number | null = null;
    if (isTimerRunning) {
      interval = window.setInterval(() => {
        setSeconds(prev => {
          const next = prev + 1;
          const pomodoro = appSettings.pomodoro;

          if (pomodoro?.enabled) {
            const focusTimeSeconds = (pomodoro.focusTime || 10) * 60;
            const breakTimeSeconds = (pomodoro.breakTime || 5) * 60;
            const currentTimeTarget = pomodoroMode === 'focus' ? focusTimeSeconds : breakTimeSeconds;

            const remaining = currentTimeTarget - next;
            if (remaining > 0 && remaining <= 3 && pomodoro.enableBeep) {
              try {
                const audio = new Audio('https://assets.mixkit.co/active_storage/sfx/2571/2571-preview.mp3');
                audio.volume = 0.3;
                audio.play().catch(() => { });
              } catch (e) { }
            }

            if (next >= currentTimeTarget) {
              const newMode = pomodoroMode === 'focus' ? 'break' : 'focus';
              setPomodoroMode(newMode);

              // Play transition sound
              try {
                const audio = new Audio(newMode === 'break'
                  ? 'https://assets.mixkit.co/active_storage/sfx/1112/1112-preview.mp3' // Success/Break
                  : 'https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3'); // Start/Focus
                audio.volume = 0.5;
                audio.play().catch(() => {});
              } catch (e) {}

              if (newMode === 'break') {
                showToast("Hora do descanso! Relaxe um pouco.", "info");
              } else {
                showToast("De volta ao trabalho! Foco total.", "success");
              }
              return 0;
            }
          }
          return next;
        });

        if (!appSettings.pomodoro?.enabled || pomodoroMode === 'focus') {
          setSessionTotalSeconds(prev => prev + 1);
        }
      }, 1000);
    }
    return () => { if (interval) clearInterval(interval); };
  }, [isTimerRunning, pomodoroMode, appSettings.pomodoro, showToast]);

  // --- Action Handlers ---
  const handleToggleTimer = () => {
    if (isTimerRunning) {
      onSave(task.id, { tempo_total_segundos: sessionTotalSeconds });
    }
    setIsTimerRunning(!isTimerRunning);
  };

  const handleSkipPhase = () => {
    setSeconds(0);
    const newMode = pomodoroMode === 'focus' ? 'break' : 'focus';
    setPomodoroMode(newMode);

    // Play sound
    try {
      const audio = new Audio(newMode === 'break'
        ? 'https://assets.mixkit.co/active_storage/sfx/1112/1112-preview.mp3'
        : 'https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3');
      audio.volume = 0.5;
      audio.play().catch(() => {});
    } catch (e) {}

    showToast(newMode === 'break' ? "Descanso iniciado (Skip)." : "Foco iniciado (Skip).", "info");
  };

  const formatTime = (totalSeconds: number) => {
    const hrs = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleAddFollowUp = () => {
    if (!newFollowUp.trim()) return;
    const newEntry: Acompanhamento = {
      data: new Date().toISOString(),
      nota: newFollowUp
    };
    const updatedAcompanhamento = [...(currentTaskData.acompanhamento || []), newEntry];
    onSave(task.id, { acompanhamento: updatedAcompanhamento });
    setNewFollowUp('');
    setShouldAutoScroll(true);
  };

  const handleCopyAllHistory = () => {
    if (!task.acompanhamento) return;
    const history = task.acompanhamento
      .map(entry => `[${new Date(entry.data).toLocaleString('pt-BR')}] ${entry.nota}`)
      .join('\n\n');
    navigator.clipboard.writeText(history);
    showToast("Histórico completo copiado!", "success");
  };

  const handleFileUpload = async (files: Array<{ file: File; customName?: string }>) => {
    if (files.length === 0) return [];
    setIsUploading(true);
    const uploadFunc = httpsCallable(functions, 'upload_to_drive');
    const uploadedItems: PoolItem[] = [];

    try {
      for (const { file, customName } of files) {
        const finalFileName = getRenamedFileName(file.name, customName);
        const reader = new FileReader();
        const fileContentB64 = await new Promise<string>((resolve, reject) => {
          reader.onload = () => resolve((reader.result as string).split(',')[1]);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });

        const result = await uploadFunc({
          fileName: finalFileName,
          fileContent: fileContentB64,
          mimeType: file.type,
          folderId: appSettings.googleDriveFolderId
        });

        const data = result.data as any;
        const newItem: PoolItem = {
          id: Math.random().toString(36).substring(2, 11),
          tipo: 'arquivo',
          valor: data.webViewLink,
          nome: finalFileName,
          data_criacao: new Date().toISOString()
        };
        uploadedItems.push(newItem);
      }

      const newEntries = uploadedItems.map(item => ({
        data: new Date().toISOString(),
        nota: buildDiaryRichNote('FILE', item.nome || 'Arquivo', item.valor)
      }));

      onSave(task.id, {
        pool_dados: [...(currentTaskData.pool_dados || []), ...uploadedItems],
        acompanhamento: [...(currentTaskData.acompanhamento || []), ...newEntries]
      });

      // Sync Knowledge module
      for (const item of uploadedItems) {
        const knowledgeItem: ConhecimentoItem = {
          id: item.id,
          titulo: item.nome || 'Sem título',
          tipo_arquivo: item.nome?.split('.').pop()?.toLowerCase() || 'unknown',
          url_drive: item.valor,
          tamanho: 0,
          data_criacao: item.data_criacao,
          origem: { modulo: 'tarefas', id_origem: task.id }
        };
        setDoc(doc(db, 'conhecimento', item.id), knowledgeItem).catch(console.error);
      }

      showToast(`${uploadedItems.length} arquivo(s) carregado(s).`, "success");
      return uploadedItems;
    } catch (err) {
      console.error(err);
      showToast("Erro ao carregar para o Drive.", "error");
      return [];
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileUploadInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files ? Array.from(e.target.files) : [];
    if (selectedFiles.length === 0) return;

    const initialNames = selectedFiles.reduce((acc, file) => {
      acc[getPendingFileKey(file)] = file.name;
      return acc;
    }, {} as Record<string, string>);

    setPendingFiles(selectedFiles);
    setPendingFileNames(initialNames);
    setModalConfig({ type: 'file_upload', isOpen: true });
    setShowAttachMenu(false);
    e.target.value = '';
  };

  const handleModalConfirm = async () => {
    switch (modalConfig.type) {
      case 'reset_timer':
        setSeconds(0);
        setSessionTotalSeconds(0);
        onSave(task.id, { tempo_total_segundos: 0 });
        setIsTimerRunning(false);
        break;
      case 'confirm_delete':
        if (modalConfig.data?.index !== undefined) {
          const updated = [...(currentTaskData.acompanhamento || [])];
          updated.splice(modalConfig.data.index, 1);
          onSave(task.id, { acompanhamento: updated });
        }
        break;
      case 'edit_diary':
        if (modalConfig.data?.index !== undefined && modalInputValue.trim()) {
          const updated = [...(currentTaskData.acompanhamento || [])];
          updated[modalConfig.data.index] = { ...updated[modalConfig.data.index], nota: modalInputValue };
          onSave(task.id, { acompanhamento: updated });
        }
        break;
      case 'link':
        if (modalInputValue.trim()) {
          const normalizedLink = ensureHttpUrl(modalInputValue);
          const displayName = modalInputName.trim() || normalizedLink;
          const newItem: PoolItem = {
            id: Math.random().toString(36).substring(2, 11),
            tipo: 'link',
            valor: normalizedLink,
            nome: displayName,
            data_criacao: new Date().toISOString()
          };
          onSave(task.id, { 
            pool_dados: [...(currentTaskData.pool_dados || []), newItem],
            acompanhamento: [...(currentTaskData.acompanhamento || []), { data: new Date().toISOString(), nota: buildDiaryRichNote('LINK', newItem.nome || newItem.valor, newItem.valor) }]
          });
        }
        break;
      case 'reminder':
        if (reminderDate && reminderTime) {
          onSave(task.id, { reminder_at: `${reminderDate}T${reminderTime}:00`, reminder_sent: false });
          showToast("Lembrete agendado!", "success");
        }
        break;
      case 'contact':
        if (modalInputValue.trim()) {
          const displayName = modalInputName.trim() || modalInputValue;
          const newItem: PoolItem = {
            id: Math.random().toString(36).substring(2, 11),
            tipo: 'telefone',
            valor: modalInputValue,
            nome: displayName,
            data_criacao: new Date().toISOString()
          };
          onSave(task.id, { 
            pool_dados: [...(currentTaskData.pool_dados || []), newItem],
            acompanhamento: [...(currentTaskData.acompanhamento || []), { data: new Date().toISOString(), nota: buildDiaryRichNote('CONTACT', newItem.nome || newItem.valor, newItem.valor) }]
          });
        }
        break;
      case 'file_upload':
        if (pendingFiles.length > 0) {
          await handleFileUpload(
            pendingFiles.map(file => ({
              file,
              customName: pendingFileNames[getPendingFileKey(file)]
            }))
          );
        }
        break;
    }
    setModalConfig({ ...modalConfig, isOpen: false });
    setModalInputValue('');
    setModalInputName('');
    setPendingFiles([]);
    setPendingFileNames({});
  };

  const isBreakActive = appSettings.pomodoro?.enabled && pomodoroMode === 'break' && isTimerRunning;

  return (
    <div className={`fixed inset-0 z-[200] flex flex-col overflow-hidden transition-all duration-1000 ${isBreakActive ? 'bg-[#1a0b0b] text-white' : isTimerRunning ? 'bg-[#050505] text-white' : 'bg-[#F2F4F7] text-slate-900'}`}>
      
      {/* Header - Mais compacto no mobile */}
      <div className="p-3 md:p-10 pb-2 md:pb-4 flex items-center justify-between shrink-0">
        <div className="flex flex-col">
          <span className="text-blue-500 text-[8px] md:text-[10px] font-black uppercase tracking-[0.3em] mb-1 md:mb-2 block">Central de Execução</span>
          {isEditingTitle ? (
            <div className="flex items-center gap-2">
              <input
                type="text" autoFocus
                value={editedTitle}
                onChange={e => setEditedTitle(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    onSave(task.id, { titulo: editedTitle });
                    setIsEditingTitle(false);
                    showToast("Título atualizado!", "success");
                  }
                }}
                className={`text-xl md:text-2xl lg:text-4xl font-black tracking-tighter bg-transparent border-b-2 outline-none w-full max-w-2xl ${isTimerRunning ? 'text-white border-white/20' : 'text-slate-900 border-slate-200'}`}
              />
            </div>
          ) : (
            <div className="group flex items-center gap-4">
              <h1 className={`text-xl md:text-2xl lg:text-4xl font-black tracking-tighter leading-tight ${isTimerRunning ? 'text-white' : 'text-slate-900'}`}>
                {task.titulo}
              </h1>
              <button onClick={() => setIsEditingTitle(true)} className="p-2 opacity-0 group-hover:opacity-100 transition-all text-slate-400 hover:text-blue-500">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" strokeWidth="2" /></svg>
              </button>
            </div>
          )}
        </div>
        <button onClick={() => { if (isTimerRunning) handleToggleTimer(); onClose(); }} className="p-3 rounded-xl border border-slate-200 hover:bg-white text-slate-400">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" strokeWidth="2.5" /></svg>
        </button>
      </div>

      {/* Main Grid - Otimizado para Mobile: Flex no mobile, Grid no Desktop */}
      <div className="flex-1 flex flex-col lg:grid lg:grid-cols-12 gap-3 md:gap-6 p-2 md:p-10 pt-0 md:pt-4 overflow-y-auto lg:overflow-hidden">
        
        {/* Control Panel (Ordem 1 no mobile para ficar no topo) */}
        <div className="lg:col-span-4 flex flex-col gap-3 order-1 lg:order-2 shrink-0">
          <PainelControleUI
            task={currentTaskData}
            chatUrl={chatUrl}
            setChatUrl={setChatUrl}
            handleSaveChatUrl={() => { onSave(task.id, { chat_gemini_url: chatUrl }); showToast("Link salvo!", "success"); }}
            isTimerRunning={isTimerRunning}
            sessionTotalSeconds={sessionTotalSeconds}
            seconds={seconds}
            pomodoroMode={pomodoroMode}
            setPomodoroMode={setPomodoroMode}
            handleToggleTimer={handleToggleTimer}
            handleResetTimer={() => setModalConfig({ type: 'reset_timer', isOpen: true })}
            handleSkipPhase={handleSkipPhase}
            handleCompleteTaskRequest={() => setIsConfirmModalOpen(true)}
            appSettings={appSettings}
            currentTime={currentTime}
            formatTime={formatTime}
            isBreakActive={isBreakActive}
            setModalConfig={setModalConfig}
            setReminderDate={setReminderDate}
            setReminderTime={setReminderTime}
          />

          {/* Date/Time Inputs */}
          <div className={`border rounded-2xl p-4 space-y-4 transition-all ${isTimerRunning ? 'bg-white/5 border-white/10 text-white' : 'bg-white border-slate-200 text-slate-900'}`}>
            <h4 className="text-[10px] font-black uppercase tracking-widest opacity-50">Planejamento</h4>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-[9px] font-bold uppercase opacity-60">Início</label>
                <input
                  type="date"
                  value={task.data_inicio || ''}
                  onChange={e => onSave(task.id, { data_inicio: e.target.value })}
                  className={`w-full bg-transparent border-b text-xs font-bold outline-none ${isTimerRunning ? 'border-white/20 focus:border-white' : 'border-slate-200 focus:border-blue-500'}`}
                />
                <input
                  type="time"
                  value={task.horario_inicio || ''}
                  onChange={e => onSave(task.id, { horario_inicio: e.target.value })}
                  className={`w-full bg-transparent border-b text-xs font-bold outline-none ${isTimerRunning ? 'border-white/20 focus:border-white' : 'border-slate-200 focus:border-blue-500'}`}
                />
              </div>
              <div className="space-y-1">
                <label className="text-[9px] font-bold uppercase opacity-60">Término</label>
                <input
                  type="date"
                  value={task.data_limite || ''}
                  onChange={e => onSave(task.id, { data_limite: e.target.value })}
                  className={`w-full bg-transparent border-b text-xs font-bold outline-none ${isTimerRunning ? 'border-white/20 focus:border-white' : 'border-slate-200 focus:border-blue-500'}`}
                />
                <input
                  type="time"
                  value={task.horario_fim || ''}
                  onChange={e => onSave(task.id, { horario_fim: e.target.value })}
                  className={`w-full bg-transparent border-b text-xs font-bold outline-none ${isTimerRunning ? 'border-white/20 focus:border-white' : 'border-slate-200 focus:border-blue-500'}`}
                />
              </div>
            </div>
          </div>

          {/* Notificação Compacta do Sistema */}
          {notifications.length > 0 && notifications.some(n => !n.isRead) && (
            <div className={`mt-3 p-3 rounded-2xl border animate-in fade-in slide-in-from-top-2 duration-500 ${isTimerRunning ? 'bg-blue-500/5 border-blue-500/20' : 'bg-blue-50/50 border-blue-100'}`}>
              {(() => {
                const latest = [...notifications].filter(n => !n.isRead).reverse()[0];
                return (
                  <div className="flex items-center gap-3">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 animate-pulse ${latest.type === 'error' ? 'bg-rose-500' : latest.type === 'warning' ? 'bg-amber-500' : 'bg-blue-500'}`}></span>
                    <div className="min-w-0">
                      <p className={`text-[9px] font-black uppercase tracking-wider truncate ${isTimerRunning ? 'text-blue-300' : 'text-blue-600'}`}>
                        {latest.title}
                      </p>
                      <p className={`text-[10px] font-medium truncate opacity-70 ${isTimerRunning ? 'text-blue-100' : 'text-blue-900'}`}>
                        {latest.message}
                      </p>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
        </div>

        {/* Diary Column (Ordem 2 no mobile) */}
        <div className="lg:col-span-8 flex flex-col gap-3 order-2 lg:order-1 flex-1 min-h-[500px] lg:overflow-hidden">
          {/* Data Pool */}
          <div className={`shrink-0 rounded-none md:rounded-2xl border transition-all ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`}>
            <button onClick={() => setShowPool(!showPool)} className="w-full flex items-center gap-2 px-4 py-3">
              <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 flex-1 text-left">Pool de Dados</span>
              <svg className={`w-3 h-3 transition-transform ${showPool ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" strokeWidth="2.5" /></svg>
            </button>
            {showPool && (
              <div className="px-4 pb-4 flex flex-wrap gap-2 max-h-40 overflow-y-auto">
                {(currentTaskData.pool_dados || []).map((item) => (
                  <div key={item.id} className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold ${isTimerRunning ? 'bg-white/10 border-white/10 text-white' : 'bg-slate-50 border-slate-100 text-slate-700'}`}>
                    <span className="truncate max-w-[150px]">{item.nome}</span>
                    <button onClick={() => window.open(item.valor, '_blank')} className={`${isTimerRunning ? 'text-blue-300 hover:text-blue-200' : 'text-blue-500 hover:text-blue-700'}`}>
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" strokeWidth="2" /></svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Diary */}
          <div className={`flex-1 flex flex-col rounded-none md:rounded-[2.5rem] border overflow-hidden ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`}>
             <DiarioBordoUI
                task={task}
                currentTaskData={currentTaskData}
                newFollowUp={newFollowUp}
                setNewFollowUp={setNewFollowUp}
                handleAddFollowUp={handleAddFollowUp}
                handleCopyMessage={(txt) => { navigator.clipboard.writeText(txt); showToast("Copiado!", "success"); }}
                handleCopyAllHistory={handleCopyAllHistory}
                isRecording={isRecording}
                startRecording={startRecording}
                stopRecording={stopRecording}
                isProcessingTranscription={isProcessingTranscription}
                showAttachMenu={showAttachMenu}
                setShowAttachMenu={setShowAttachMenu}
                fileInputRef={fileInputRef}
                handleFileUploadInput={handleFileUploadInput}
                setModalConfig={setModalConfig}
                applyFormatting={() => {}} // Implementação simplificada para o exemplo
                isTimerRunning={isTimerRunning}
                diaryEndRef={diaryEndRef}
                handleDiaryScroll={() => {}}
                handleEditDiaryEntry={(index) => {
                  setModalInputValue(currentTaskData.acompanhamento![index].nota);
                  setModalConfig({ type: 'edit_diary', data: { index }, isOpen: true });
                }}
                handleDeleteDiaryEntry={(index) => setModalConfig({ type: 'confirm_delete', data: { index }, isOpen: true })}
                isUploading={isUploading}
                notifications={notifications}
              />
          </div>
        </div>

      </div>

      {/* Confirmation Modal */}
      {isConfirmModalOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <div className="bg-[#111] border border-white/10 w-full max-w-sm rounded-none md:rounded-[2.5rem] p-10 text-center">
            <h3 className="text-white font-black text-2xl mb-2">Concluir Tarefa?</h3>
            <p className="text-slate-400 text-sm mb-8">Confirma a conclusão de: {task.titulo}?</p>
            <div className="flex gap-4">
              <button onClick={() => setIsConfirmModalOpen(false)} className="flex-1 py-4 text-[10px] font-black uppercase text-slate-500">Agora não</button>
              <button onClick={() => { onSave(task.id, { status: 'concluído' }); onClose(); }} className="flex-1 bg-emerald-500 text-white py-4 rounded-2xl text-[10px] font-black uppercase shadow-xl shadow-emerald-500/20">Sim, concluída</button>
            </div>
          </div>
        </div>
      )}

      {/* Notifications Panel */}
      {isNotificationCenterOpen && (
        <div className="absolute top-20 right-6 z-[300] w-80 md:w-96 shadow-2xl animate-in slide-in-from-right-4 duration-300">
          <NotificationCenter
            notifications={notifications}
            onMarkAsRead={onMarkAsRead}
            onDismiss={onDismiss}
            isOpen={isNotificationCenterOpen}
            onClose={onCloseNotifications}
          />
        </div>
      )}

      {/* Speed Dial */}
      <div className="fixed bottom-6 right-6 z-[250]">
        <SpeedDialMenu
          notifications={notifications}
          isSyncing={isSyncing}
          isNotificationCenterOpen={isNotificationCenterOpen}
          onOpenNotes={onOpenNotes}
          onOpenLog={onOpenLog}
          onOpenShopping={onOpenShopping}
          onOpenTranscription={onOpenTranscription}
          onToggleNotifications={onToggleNotifications}
          onSync={onSync}
          onOpenSettings={onOpenSettings}
          onCloseNotifications={onCloseNotifications}
          onMarkAsRead={onMarkAsRead}
          onDismiss={onDismiss}
          onCreateAction={onCreateAction}
          direction="up"
        />
      </div>

      {/* Dynamic Modal (CRUD/Settings) */}
      {modalConfig.isOpen && (
        <div className="fixed inset-0 z-[300] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className={`w-full max-w-md p-6 rounded-none md:rounded-3xl shadow-2xl ${isTimerRunning ? 'bg-[#1A1A1A] text-white' : 'bg-white text-slate-900'}`}>
            <h3 className="text-lg font-black mb-4 uppercase tracking-tighter">
              {modalConfig.type === 'confirm_delete' ? 'Excluir Registro' : 
               modalConfig.type === 'reset_timer' ? 'Zerar Cronômetro' : 
               modalConfig.type === 'reminder' ? 'Agendar Lembrete' : 'Configuração'}
            </h3>
            
            {modalConfig.type === 'edit_diary' && (
              <AutoExpandingTextarea
                value={modalInputValue}
                onChange={e => setModalInputValue(e.target.value)}
                className={`w-full p-4 rounded-none md:rounded-xl border outline-none min-h-[150px] ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-slate-50 border-slate-200'}`}
              />
            )}

            {modalConfig.type === 'link' && (
              <div className="flex flex-col gap-3">
                <input placeholder="Nome" value={modalInputName} onChange={e => setModalInputName(e.target.value)} className={`w-full p-3 rounded-none md:rounded-xl border outline-none ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`} />
                <input placeholder="URL" value={modalInputValue} onChange={e => setModalInputValue(e.target.value)} className={`w-full p-3 rounded-none md:rounded-xl border outline-none ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`} />
              </div>
            )}

            {modalConfig.type === 'reminder' && (
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-black uppercase tracking-widest opacity-50">Data</label>
                  <input 
                    type="date" 
                    value={reminderDate} 
                    onChange={e => setReminderDate(e.target.value)} 
                    className={`w-full p-3 rounded-none md:rounded-xl border outline-none ${isTimerRunning ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-slate-200 text-slate-900'}`}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-black uppercase tracking-widest opacity-50">Hora</label>
                  <input 
                    type="time" 
                    value={reminderTime} 
                    onChange={e => setReminderTime(e.target.value)} 
                    className={`w-full p-3 rounded-none md:rounded-xl border outline-none ${isTimerRunning ? 'bg-white/5 border-white/10 text-white' : 'bg-slate-50 border-slate-200 text-slate-900'}`}
                  />
                </div>
              </div>
            )}

            {modalConfig.type === 'contact' && (
              <div className="flex flex-col gap-3">
                <input placeholder="Nome do Contato" value={modalInputName} onChange={e => setModalInputName(e.target.value)} className={`w-full p-3 rounded-none md:rounded-xl border outline-none ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`} />
                <input placeholder="Telefone / Info" value={modalInputValue} onChange={e => setModalInputValue(e.target.value)} className={`w-full p-3 rounded-none md:rounded-xl border outline-none ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`} />
              </div>
            )}

            {modalConfig.type === 'confirm_delete' && (
              <p className="text-slate-500 mb-4">Tem certeza que deseja excluir este registro do diário de bordo?</p>
            )}

            {modalConfig.type === 'reset_timer' && (
              <p className="text-slate-500 mb-4">Deseja zerar o cronômetro desta sessão? Esta ação não pode ser desfeita.</p>
            )}

            {modalConfig.type === 'file_upload' && (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-slate-500 mb-2">Renomeie os arquivos antes de carregar (opcional):</p>
                {pendingFiles.map((file, index) => {
                  const key = getPendingFileKey(file);
                  return (
                    <div key={key} className="flex flex-col gap-1">
                      <label className="text-[10px] font-black uppercase tracking-widest opacity-50">
                        Arquivo {index + 1}
                      </label>
                      <input
                        placeholder="Nome do arquivo"
                        value={pendingFileNames[key] || ''}
                        onChange={e => setPendingFileNames(prev => ({ ...prev, [key]: e.target.value }))}
                        className={`w-full p-3 rounded-none md:rounded-xl border outline-none ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200'}`}
                      />
                      <p className="text-[11px] text-slate-400">Original: {file.name}</p>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex gap-3 mt-6 justify-end">
              <button 
                onClick={() => {
                  setModalConfig({ ...modalConfig, isOpen: false });
                  setModalInputValue('');
                  setModalInputName('');
                  setPendingFiles([]);
                  setPendingFileNames({});
                }} 
                className="px-4 py-2 font-bold text-slate-400"
              >
                Cancelar
              </button>
              <button 
                onClick={handleModalConfirm} 
                className={`px-6 py-2 rounded-none md:rounded-xl font-bold shadow-lg transition-all ${modalConfig.type === 'confirm_delete' ? 'bg-rose-600' : 'bg-blue-600'} text-white hover:brightness-110`}
              >
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
