import React, { useState, useRef, useEffect } from 'react';
import { httpsCallable } from 'firebase/functions';
import { ref, uploadBytesResumable } from 'firebase/storage';
import { functions, storage, auth } from '@/firebase';

// A partir deste tempo de processamento no backend (upload já concluído),
// exibimos um aviso de que o processo continua em andamento (e não travou).
const PROCESSING_STILL_RUNNING_THRESHOLD_MS = 15000;

interface TranscriptionToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
  initialText?: string;
  isEmbedded?: boolean;
  initialFile?: File | null;
  onInitialFileConsumed?: () => void;
  onSendToCopiloto?: (text: string) => void;
}

const TRANSCRIPTION_HISTORY_KEY = 'hermes_transcription_history';

interface TranscriptionHistoryEntry {
  id: string;
  fileName: string;
  fileSize: number;
  date: string;
  raw: string;
  refined: string;
}

type ThemeMode = 'light' | 'dark' | 'system';

export const TranscriptionTool: React.FC<TranscriptionToolProps> = ({ onBack, showToast, initialText, isEmbedded, initialFile, onInitialFileConsumed, onSendToCopiloto }) => {
  const [file, setFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcription, setTranscription] = useState<{ raw: string, refined: string } | null>(initialText ? { raw: initialText, refined: '' } : null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [isStillProcessing, setIsStillProcessing] = useState(false);
  const [history, setHistory] = useState<TranscriptionHistoryEntry[]>([]);
  const [pendingDeleteHistoryId, setPendingDeleteHistoryId] = useState<string | null>(null);
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem('hermes-theme-mode');
    return saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'system';
  });
  const [prefersDark, setPrefersDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Load history
    const saved = localStorage.getItem(TRANSCRIPTION_HISTORY_KEY);
    if (saved) {
      try {
        setHistory(JSON.parse(saved));
      } catch (e) {
        console.error("Erro ao carregar histórico:", e);
      }
    }

    // Paste handler
    const handlePaste = (e: ClipboardEvent) => {
      if (e.clipboardData && e.clipboardData.files.length > 0) {
        const pastedFile = e.clipboardData.files[0];
        if (pastedFile.type.startsWith('audio/') || pastedFile.type.startsWith('video/')) {
          handleFileSelection(pastedFile);
        } else {
          showToast("Arquivo colado não é áudio ou vídeo.", "error");
        }
      }
    };
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, []);

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const handleMediaChange = (event: MediaQueryListEvent) => setPrefersDark(event.matches);
    const handleStorage = () => {
      const saved = localStorage.getItem('hermes-theme-mode');
      setThemeMode(saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'system');
    };

    setPrefersDark(media.matches);
    media.addEventListener('change', handleMediaChange);
    window.addEventListener('storage', handleStorage);

    return () => {
      media.removeEventListener('change', handleMediaChange);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  useEffect(() => {
    const handleSharedAudio = (e: Event) => {
      const customEvent = e as CustomEvent<File>;
      if (customEvent.detail instanceof File) {
        handleFileSelection(customEvent.detail);
      }
    };

    window.addEventListener('hermes-shared-audio', handleSharedAudio);
    return () => window.removeEventListener('hermes-shared-audio', handleSharedAudio);
  }, []);

  useEffect(() => {
    if (initialFile) {
      handleFileSelection(initialFile);
      onInitialFileConsumed?.();
    }
  }, [initialFile]);

  const saveToHistory = (data: { raw: string, refined: string }, fileName: string, fileSize: number) => {
    const newEntry: TranscriptionHistoryEntry = {
      id: Date.now().toString(),
      fileName,
      fileSize,
      date: new Date().toISOString(),
      raw: data.raw,
      refined: data.refined
    };
    const updatedHistory = [newEntry, ...history].slice(0, 50); // Keep last 50
    setHistory(updatedHistory);
    localStorage.setItem(TRANSCRIPTION_HISTORY_KEY, JSON.stringify(updatedHistory));
  };

  const deleteFromHistory = (id: string) => {
    const updatedHistory = history.filter(h => h.id !== id);
    setHistory(updatedHistory);
    localStorage.setItem(TRANSCRIPTION_HISTORY_KEY, JSON.stringify(updatedHistory));
    showToast("Transcrição removida do histórico.", "info");
  };

  const loadFromHistory = (entry: TranscriptionHistoryEntry) => {
    setTranscription({ raw: entry.raw, refined: entry.refined });
    setFile(null);
    setAudioUrl(null);
    showToast("Transcrição carregada do histórico.", "success");
  };

  const handleFileSelection = (selectedFile: File) => {
    if (selectedFile.size > 200 * 1024 * 1024) {
      showToast("Arquivo muito grande (máx. 200MB). Para vídeos/áudios muito longos, use Transcrições Longas.", "error");
      return;
    }
    setFile(selectedFile);
    setAudioUrl(URL.createObjectURL(selectedFile));
    setTranscription(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  };

  const handleTranscribe = async () => {
    if (!file) return;

    const uid = auth.currentUser?.uid;
    if (!uid) {
      showToast("Você precisa estar autenticado para transcrever.", "error");
      return;
    }

    setIsProcessing(true);
    setUploadProgress(0);
    setIsStillProcessing(false);
    let stillProcessingTimer: ReturnType<typeof setTimeout> | null = null;
    try {
      const extension = `.${file.name.split('.').pop()?.toLowerCase() || 'm4a'}`;
      const storagePath = `quick_transcriptions/${uid}/${Date.now()}${extension}`;

      // Upload direto pro Storage: evita o limite de 32MB de payload das Cloud Functions.
      await new Promise<void>((resolve, reject) => {
        const task = uploadBytesResumable(ref(storage, storagePath), file, { contentType: file.type || 'application/octet-stream' });
        task.on(
          'state_changed',
          (snapshot) => {
            setUploadProgress(Math.round((snapshot.bytesTransferred / snapshot.totalBytes) * 100));
          },
          (error) => reject(error),
          () => resolve(),
        );
      });

      // Upload concluído: a partir daqui o backend processa (extração de áudio, Groq, Gemini).
      setUploadProgress(null);
      stillProcessingTimer = setTimeout(() => setIsStillProcessing(true), PROCESSING_STILL_RUNNING_THRESHOLD_MS);

      const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
      const response = await transcribeFunc({ storagePath, extension });

      const data = response.data as { raw: string, refined: string };
      setTranscription(data);
      saveToHistory(data, file.name, file.size);
      showToast("Transcrição concluída!", "success");
    } catch (error: any) {
      console.error("Erro ao transcrever:", error);
      showToast(error?.message || "Erro ao processar áudio.", "error");
    } finally {
      if (stillProcessingTimer) clearTimeout(stillProcessingTimer);
      setUploadProgress(null);
      setIsStillProcessing(false);
      setIsProcessing(false);
    }
  };

  const copyToClipboard = (text?: string) => {
    const target = text || transcription?.refined;
    if (target) {
      navigator.clipboard.writeText(target);
      showToast("Texto copiado!", "success");
    }
  };

  const sendToCopiloto = (text?: string) => {
    const target = text || transcription?.refined;
    if (target && onSendToCopiloto) {
      onSendToCopiloto(target);
      showToast("Texto enviado ao Copiloto Hermes!", "success");
    }
  };

  const isDarkTheme = themeMode === 'dark' || (themeMode === 'system' && prefersDark);
  const panelClass = isDarkTheme
    ? 'bg-[#121826] border-slate-700/80 text-slate-100 shadow-[0_20px_60px_rgba(2,6,23,0.45)]'
    : 'bg-white border-slate-200 text-slate-900 shadow-none md:shadow-xl';
  const softPanelClass = isDarkTheme
    ? 'bg-[#0f1724] border-slate-800 text-slate-100'
    : 'bg-slate-50 border-slate-200 text-slate-900';
  const uploadIdleClass = isDarkTheme
    ? 'border-slate-700 bg-[#121826] hover:border-blue-400'
    : 'border-slate-200 bg-white hover:border-blue-300';
  const uploadDragClass = isDarkTheme
    ? 'border-blue-400 bg-blue-500/10'
    : 'border-blue-500 bg-blue-50';
  const titleClass = isDarkTheme ? 'text-slate-100' : 'text-slate-900';
  const primaryTextClass = isDarkTheme ? 'text-slate-100' : 'text-slate-900';
  const secondaryTextClass = isDarkTheme ? 'text-slate-300' : 'text-slate-500';
  const tertiaryTextClass = isDarkTheme ? 'text-slate-400' : 'text-slate-400';
  const subtleTextClass = isDarkTheme ? 'text-slate-500' : 'text-slate-300';
  const borderSoftClass = isDarkTheme ? 'border-slate-800' : 'border-slate-200';
  const buttonNeutralClass = isDarkTheme
    ? 'border-slate-600 bg-slate-900/70 text-slate-300 hover:bg-slate-800 hover:text-white'
    : 'border-slate-200 text-slate-500 hover:text-rose-500 hover:bg-rose-50';
  const fileButtonClass = isDarkTheme
    ? 'bg-slate-900/70 border-slate-600 text-slate-200 hover:border-blue-400 hover:text-blue-300'
    : 'bg-white border-slate-200 text-slate-600 hover:border-blue-400 hover:text-blue-600';
  const historyItemClass = isDarkTheme
    ? 'bg-slate-900/70 border-slate-700 hover:border-blue-400'
    : 'bg-white border-slate-200 hover:border-blue-400';

  return (
    <div className={`animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-6 md:space-y-8 ${isEmbedded ? 'pb-10' : 'pb-24 md:pb-32'}`}>
      {/* Header */}
      <div className="flex items-start gap-3 md:gap-6 mb-2 md:mb-4">
        <button onClick={onBack} className="w-11 h-11 md:w-12 md:h-12 bg-white rounded-none-none md:rounded-none-none flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-900 transition-all shadow-none shrink-0">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div className="flex-1 min-w-0 pt-1">
          <h2 className="text-2xl md:text-3xl font-bold text-slate-50 tracking-tight leading-none">Transcrição de Áudio</h2>
          <p className="mt-2 text-slate-300 font-mono text-xs uppercase font-bold md:text-base leading-relaxed max-w-2xl">Transcreva áudios do WhatsApp e outros formatos com IA.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-8">
        <div className="lg:col-span-2 space-y-4 md:space-y-8">
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 md:gap-8">
            <div className="space-y-4 md:space-y-6">
              {/* File Upload Area */}
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                className={`border-2 md:border-4 border-dashed rounded-none-none md:rounded-none-none px-5 py-8 md:p-10 transition-all flex flex-col items-center justify-center text-center gap-4 md:gap-5 min-h-[320px] md:min-h-[300px] relative shadow-none ${
                  dragOver ? uploadDragClass : uploadIdleClass
                }`}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  accept="audio/*,video/*"
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      handleFileSelection(e.target.files[0]);
                    }
                  }}
                />

                {file ? (
                  <>
                     <div className={`w-16 h-16 md:w-20 md:h-20 rounded-none-none flex items-center justify-center ${isDarkTheme ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-100 text-emerald-600'}`}>
                        <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                     </div>
                     <div className="min-w-0 w-full">
                       <p className={`text-base md:text-lg font-bold break-words ${primaryTextClass}`}>{file.name}</p>
                       <p className={`text-sm font-bold ${secondaryTextClass}`}>{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                     </div>
                     {audioUrl && (
                       file.type.startsWith('video/') ? (
                         <video controls src={audioUrl} className="w-full mt-2 max-h-48 rounded-none-none" />
                       ) : (
                         <audio controls src={audioUrl} className="w-full mt-2" />
                       )
                     )}
                     {isProcessing && (
                       <div className="w-full space-y-1.5">
                         {uploadProgress !== null ? (
                           <>
                             <div className={`h-1.5 w-full rounded-none-none overflow-hidden ${isDarkTheme ? 'bg-slate-800' : 'bg-slate-200'}`}>
                               <div className="h-full bg-blue-500 transition-all" style={{ width: `${uploadProgress}%` }} />
                             </div>
                             <p className={`text-[10px] font-bold ${tertiaryTextClass}`}>Enviando arquivo... {uploadProgress}%</p>
                           </>
                         ) : (
                           <p className={`text-[10px] font-bold ${tertiaryTextClass}`}>
                             {isStillProcessing ? 'Ainda processando... arquivos maiores podem levar mais tempo, não travou.' : 'Processando transcrição...'}
                           </p>
                         )}
                       </div>
                     )}
                     <div className="flex flex-col sm:flex-row w-full gap-3 mt-2">
                       <button
                         onClick={() => { setFile(null); setAudioUrl(null); setTranscription(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                         disabled={isProcessing}
                         className={`flex-1 px-5 py-3 rounded-none-none md:rounded-none-none text-[10px] font-bold uppercase tracking-wider transition-all border ${buttonNeutralClass} ${isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
                       >
                         Remover
                       </button>
                       <button
                         onClick={handleTranscribe}
                         disabled={isProcessing}
                         className={`flex-1 px-5 py-3 bg-slate-900 text-white rounded-none-none md:rounded-none-none text-[10px] font-bold uppercase tracking-wider shadow-none hover:bg-blue-600 transition-all ${isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
                       >
                         {isProcessing ? 'Processando...' : 'Transcrever Agora'}
                       </button>
                     </div>
                  </>
                ) : (
                  <>
                    <div className={`w-16 h-16 md:w-20 md:h-20 rounded-none-none flex items-center justify-center ${isDarkTheme ? 'bg-slate-800 text-slate-400' : 'bg-slate-100 text-slate-400'}`}>
                       <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                    </div>
                    <div className="space-y-1">
                      <p className={`text-lg md:text-xl font-bold leading-tight ${primaryTextClass}`}>Arraste e solte o áudio ou vídeo aqui</p>
                      <p className={`text-sm md:text-base font-medium ${secondaryTextClass}`}>Ou clique para selecionar (MP3, OGG, WAV, MP4, MOV...)</p>
                      <p className={`text-xs md:text-sm font-semibold mt-2 ${tertiaryTextClass}`}>Você também pode colar (`Ctrl+V`) o arquivo direto.</p>
                    </div>
                    <label className={`w-full sm:w-auto px-6 py-3 border rounded-none-none md:rounded-none-none text-[10px] font-bold uppercase tracking-wider transition-all cursor-pointer select-none text-center ${fileButtonClass}`}><input type="file" className="hidden" accept="audio/*,video/*" onChange={(e) => { if (e.target.files && e.target.files.length > 0) handleFileSelection(e.target.files[0]); }} />Selecionar Arquivo</label>
                  </>
                )}
              </div>
            </div>

            {/* Result Area */}
            <div className={`p-5 md:p-8 rounded-none-none md:rounded-none-none border flex flex-col min-h-[360px] md:h-[600px] ${panelClass}`}>
               <div className="flex items-center justify-between gap-3 mb-5 md:mb-6">
                 <h3 className={`text-xl font-bold ${titleClass}`}>Resultado</h3>
                 {transcription && (
                   <div className="flex items-center gap-2 shrink-0">
                     {onSendToCopiloto && (
                       <button
                         onClick={() => sendToCopiloto()}
                         className="flex items-center gap-2 px-3 py-2 bg-blue-50 text-blue-600 rounded-none-none text-[10px] font-bold uppercase tracking-wider hover:bg-blue-100 transition-all"
                       >
                         <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                         Enviar ao Copiloto
                       </button>
                     )}
                     <button
                       onClick={() => copyToClipboard()}
                       className="flex items-center gap-2 px-3 py-2 bg-emerald-50 text-emerald-600 rounded-none-none text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-100 transition-all"
                     >
                       <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                       Copiar
                     </button>
                   </div>
                 )}
               </div>

               {transcription ? (
                 <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-6">
                   <div className="space-y-2">
                     <label className={`text-[10px] font-bold uppercase tracking-wider ${tertiaryTextClass}`}>Texto Refinado</label>
                     <p className={`text-base leading-relaxed whitespace-pre-wrap ${isDarkTheme ? 'text-slate-100' : 'text-slate-800'}`}>{transcription.refined}</p>
                   </div>

                   <div className={`pt-6 border-t space-y-2 opacity-60 hover:opacity-100 transition-opacity ${borderSoftClass}`}>
                     <label className={`text-[10px] font-bold uppercase tracking-wider ${subtleTextClass}`}>Transcrição Bruta</label>
                     <p className={`text-sm leading-relaxed whitespace-pre-wrap ${secondaryTextClass}`}>{transcription.raw}</p>
                   </div>
                 </div>
               ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-center space-y-4 opacity-40">
                   <svg className={`w-16 h-16 ${isDarkTheme ? 'text-slate-600' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                   <p className={`font-bold ${tertiaryTextClass}`}>A transcrição aparecerá aqui.</p>
                 </div>
               )}
            </div>
          </div>
        </div>

        {/* History Area */}
        <div className={`p-5 md:p-8 rounded-none-none md:rounded-none-none border flex flex-col min-h-[280px] md:h-[600px] lg:h-auto ${softPanelClass}`}>
          <div className="flex items-center justify-between mb-6">
            <h3 className={`text-xl font-bold ${titleClass}`}>Histórico</h3>
            <span className={`text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-none-none shadow-none ${isDarkTheme ? 'bg-slate-900 text-slate-300' : 'bg-white text-slate-400'}`}>{history.length}</span>
          </div>

          <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-4">
            {history.length > 0 ? (
              history.map(entry => (
                <div key={entry.id} className={`p-4 rounded-none-none md:rounded-none-none border transition-all group relative ${historyItemClass}`}>
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1 min-w-0 pr-8">
                      <p className={`text-sm font-bold truncate ${primaryTextClass}`}>{entry.fileName}</p>
                      <p className={`text-[10px] font-bold ${tertiaryTextClass}`}>
                        {new Date(entry.date).toLocaleDateString('pt-BR')} • {(entry.fileSize / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                    <button
                      onClick={() => {
                        if (pendingDeleteHistoryId !== entry.id) {
                          setPendingDeleteHistoryId(entry.id);
                          window.setTimeout(() => setPendingDeleteHistoryId((current) => (current === entry.id ? null : current)), 3500);
                          return;
                        }
                        setPendingDeleteHistoryId(null);
                        deleteFromHistory(entry.id);
                      }}
                      className={`absolute top-4 right-4 rounded-none-none p-1 transition-colors ${pendingDeleteHistoryId === entry.id ? 'bg-rose-500 text-white' : isDarkTheme ? 'text-slate-500 hover:text-rose-300' : 'text-slate-300 hover:text-rose-500'}`}
                    >
                      {pendingDeleteHistoryId === entry.id ? (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                      )}
                    </button>
                  </div>
                  <p className={`text-xs line-clamp-2 mb-3 italic break-words ${secondaryTextClass}`}>{entry.refined}</p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => loadFromHistory(entry)}
                      className="flex-1 py-2 bg-slate-900 text-white text-[9px] font-bold uppercase tracking-wider rounded-none-none hover:bg-blue-600 transition-all"
                    >
                      Ver Detalhes
                    </button>
                    <button
                      onClick={() => copyToClipboard(entry.refined)}
                      className={`px-3 py-2 text-[9px] font-bold uppercase tracking-wider rounded-none-none transition-all ${isDarkTheme ? 'bg-slate-800 text-slate-300 hover:bg-slate-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                    >
                      Copiar
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center opacity-40 py-10">
                <svg className={`w-12 h-12 mb-4 ${isDarkTheme ? 'text-slate-600' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <p className={`text-xs font-bold ${tertiaryTextClass}`}>Nenhum histórico disponível.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

