import React, { useState, useRef, useEffect } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '@/firebase';

interface TranscriptionToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
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

export const TranscriptionTool: React.FC<TranscriptionToolProps> = ({ onBack, showToast }) => {
  const [file, setFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcription, setTranscription] = useState<{ raw: string, refined: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [history, setHistory] = useState<TranscriptionHistoryEntry[]>([]);
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
    const ext = selectedFile.name.split('.').pop()?.toLowerCase();
    if (selectedFile.size > 25 * 1024 * 1024) {
        if (selectedFile.size > 6 * 1024 * 1024) {
          showToast("Arquivo muito grande. Limite sugerido: 6MB.", "error");
          return;
        }
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

    setIsProcessing(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const extension = `.${file.name.split('.').pop()?.toLowerCase() || 'm4a'}`;

          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({
            audioBase64: base64String,
            extension: extension
          });

          const data = response.data as { raw: string, refined: string };
          setTranscription(data);
          saveToHistory(data, file.name, file.size);
          showToast("Transcrição concluída!", "success");
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          showToast("Erro ao processar áudio.", "error");
        } finally {
          setIsProcessing(false);
        }
      };
      reader.onerror = () => {
        showToast("Erro ao ler arquivo.", "error");
        setIsProcessing(false);
      }
    } catch (error) {
      console.error(error);
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

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-8 pb-32">
      {/* Header */}
      <div className="flex items-center gap-6 mb-4">
        <button onClick={onBack} className="w-12 h-12 bg-white rounded-2xl flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-900 transition-all shadow-sm">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div className="flex-1">
          <h2 className="text-3xl font-black text-slate-900 tracking-tighter">Transcrição de Áudio</h2>
          <p className="text-slate-500 font-medium">Transcreva áudios do WhatsApp e outros formatos com IA.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
            <div className="space-y-6">
              {/* File Upload Area */}
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                className={`border-4 border-dashed rounded-[2.5rem] p-10 transition-all flex flex-col items-center justify-center text-center gap-4 min-h-[300px] relative ${
                  dragOver ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-white hover:border-blue-300'
                }`}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  accept="audio/*,video/mp4,video/mpeg"
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      handleFileSelection(e.target.files[0]);
                    }
                  }}
                />

                {file ? (
                  <>
                     <div className="w-20 h-20 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center">
                        <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                     </div>
                     <div>
                       <p className="text-lg font-black text-slate-900">{file.name}</p>
                       <p className="text-slate-500 text-sm font-bold">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                     </div>
                     {audioUrl && (
                       <audio controls src={audioUrl} className="w-full max-w-sm mt-4" />
                     )}
                     <div className="flex gap-4 mt-4">
                       <button
                         onClick={() => { setFile(null); setAudioUrl(null); setTranscription(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                         className="px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition-all"
                       >
                         Remover
                       </button>
                       <button
                         onClick={handleTranscribe}
                         disabled={isProcessing}
                         className={`px-8 py-3 bg-slate-900 text-white rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-xl hover:bg-blue-600 transition-all ${isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
                       >
                         {isProcessing ? 'Processando...' : 'Transcrever Agora'}
                       </button>
                     </div>
                  </>
                ) : (
                  <>
                    <div className="w-20 h-20 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center">
                       <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                    </div>
                    <div>
                      <p className="text-lg font-black text-slate-900">Arraste e solte o áudio aqui</p>
                      <p className="text-slate-400 text-sm font-medium">Ou clique para selecionar (MP3, OGG, WAV, MP4)</p>
                      <p className="text-slate-300 text-xs font-bold mt-2">Você também pode colar (Ctrl+V) o arquivo direto.</p>
                    </div>
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="px-8 py-3 bg-white border border-slate-200 text-slate-600 rounded-2xl text-[10px] font-black uppercase tracking-widest hover:border-blue-400 hover:text-blue-600 transition-all"
                    >
                      Selecionar Arquivo
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Result Area */}
            <div className="bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-xl flex flex-col h-[600px]">
               <div className="flex items-center justify-between mb-6">
                 <h3 className="text-xl font-black text-slate-900">Resultado</h3>
                 {transcription && (
                   <button
                     onClick={() => copyToClipboard()}
                     className="flex items-center gap-2 px-4 py-2 bg-emerald-50 text-emerald-600 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-emerald-100 transition-all"
                   >
                     <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                     Copiar
                   </button>
                 )}
               </div>

               {transcription ? (
                 <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-6">
                   <div className="space-y-2">
                     <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Texto Refinado</label>
                     <p className="text-slate-800 text-base leading-relaxed whitespace-pre-wrap">{transcription.refined}</p>
                   </div>

                   <div className="pt-6 border-t border-slate-100 space-y-2 opacity-60 hover:opacity-100 transition-opacity">
                     <label className="text-[10px] font-black text-slate-300 uppercase tracking-widest">Transcrição Bruta</label>
                     <p className="text-slate-500 text-sm leading-relaxed whitespace-pre-wrap">{transcription.raw}</p>
                   </div>
                 </div>
               ) : (
                 <div className="flex-1 flex flex-col items-center justify-center text-center space-y-4 opacity-40">
                   <svg className="w-16 h-16 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                   <p className="text-slate-400 font-bold">A transcrição aparecerá aqui.</p>
                 </div>
               )}
            </div>
          </div>
        </div>

        {/* History Area */}
        <div className="bg-slate-50 p-8 rounded-[2.5rem] border border-slate-200 flex flex-col h-[600px] lg:h-auto">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-black text-slate-900">Histórico</h3>
            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest bg-white px-3 py-1 rounded-full shadow-sm">{history.length}</span>
          </div>

          <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-4">
            {history.length > 0 ? (
              history.map(entry => (
                <div key={entry.id} className="bg-white p-4 rounded-2xl border border-slate-200 hover:border-blue-400 transition-all group relative">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1 min-w-0 pr-8">
                      <p className="text-sm font-black text-slate-900 truncate">{entry.fileName}</p>
                      <p className="text-[10px] font-bold text-slate-400">
                        {new Date(entry.date).toLocaleDateString('pt-BR')} • {(entry.fileSize / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                    <button
                      onClick={() => deleteFromHistory(entry.id)}
                      className="absolute top-4 right-4 text-slate-300 hover:text-rose-500 transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    </button>
                  </div>
                  <p className="text-xs text-slate-600 line-clamp-2 mb-3 italic">{entry.refined}</p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => loadFromHistory(entry)}
                      className="flex-1 py-2 bg-slate-900 text-white text-[9px] font-black uppercase tracking-widest rounded-lg hover:bg-blue-600 transition-all"
                    >
                      Ver Detalhes
                    </button>
                    <button
                      onClick={() => copyToClipboard(entry.refined)}
                      className="px-3 py-2 bg-slate-100 text-slate-600 text-[9px] font-black uppercase tracking-widest rounded-lg hover:bg-slate-200 transition-all"
                    >
                      Copiar
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center opacity-40 py-10">
                <svg className="w-12 h-12 text-slate-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <p className="text-xs font-bold text-slate-400">Nenhum histórico disponível.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
