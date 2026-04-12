import React, { useState, useEffect } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '@/firebase';
import type { TranscriptionResponse } from '../../../types';

interface TranscriptionAIModalProps {
  isOpen: boolean;
  onClose: () => void;
  showToast: (message: string, type: 'success' | 'error' | 'info') => void;
}

export const TranscriptionAIModal = ({ isOpen, onClose, showToast }: TranscriptionAIModalProps) => {
  const [file, setFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcription, setTranscription] = useState<{ raw: string; refined: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setFile(null);
      setTranscription(null);
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
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
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
  };

  useEffect(() => {
    const handleSharedAudio = (e: any) => {
      if (e.detail && e.detail instanceof File) {
        handleFileSelection(e.detail);
        setTimeout(() => document.getElementById('btn-transcribe-now')?.click(), 300);
      }
    };
    window.addEventListener('hermes-shared-audio', handleSharedAudio);
    return () => window.removeEventListener('hermes-shared-audio', handleSharedAudio);
  }, []);

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
          const response = await transcribeFunc({ audioBase64: base64String, extension });
          const data = response.data as TranscriptionResponse;
          setTranscription(data);

          const saved = localStorage.getItem('hermes_transcription_history');
          const history = saved ? JSON.parse(saved) : [];
          const newEntry = {
            id: Date.now().toString(),
            fileName: file.name,
            fileSize: file.size,
            date: new Date().toISOString(),
            raw: data.raw,
            refined: data.refined,
          };
          localStorage.setItem('hermes_transcription_history', JSON.stringify([newEntry, ...history].slice(0, 50)));

          showToast("Transcrição concluída!", "success");
        } catch (error) {
          console.error(error);
          showToast("Erro ao processar áudio.", "error");
        } finally {
          setIsProcessing(false);
        }
      };
    } catch {
      setIsProcessing(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight">Transcrição Rápida</h3>
            <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-1">IA Audio Processing</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-8 space-y-6">
          {!transcription ? (
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files.length) handleFileSelection(e.dataTransfer.files[0]); }}
              className={`border-4 border-dashed rounded-none md:rounded-[2rem] p-10 flex flex-col items-center justify-center text-center gap-4 transition-all ${dragOver ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 bg-slate-50'}`}
            >
              {isProcessing ? (
                <div className="flex flex-col items-center gap-4 py-10">
                  <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                  <p className="text-indigo-600 font-black uppercase tracking-widest text-[10px]">Processando seu áudio...</p>
                </div>
              ) : file ? (
                <div className="space-y-4 py-4 w-full">
                  <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                  </div>
                  <p className="text-lg font-black text-slate-900 truncate px-4">{file.name}</p>
                  <button id="btn-transcribe-now" onClick={handleTranscribe} className="bg-indigo-600 text-white px-8 py-3 rounded-none md:rounded-2xl font-black uppercase tracking-widest text-[10px] shadow-lg hover:bg-indigo-700 transition-all">Transcrever Agora</button>
                </div>
              ) : (
                <div className="py-10">
                  <div className="w-16 h-16 bg-slate-200 text-slate-400 rounded-full flex items-center justify-center mx-auto mb-4">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                  </div>
                  <div className="space-y-1">
                    <p className="font-black text-slate-900">Cole seu áudio aqui (Ctrl+V)</p>
                    <p className="text-slate-400 text-xs font-medium">Ou arraste o arquivo aqui</p>
                  </div>
                  <div className="mt-6 md:hidden">
                    <button
                      onClick={() => document.getElementById('mobile-transcription-upload')?.click()}
                      className="bg-indigo-100 text-indigo-700 px-6 py-3 rounded-xl font-black uppercase tracking-widest text-[10px] shadow-sm hover:bg-indigo-200 transition-all flex items-center gap-2 mx-auto"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                      Selecionar Arquivo
                    </button>
                    <input
                      id="mobile-transcription-upload"
                      type="file"
                      className="hidden"
                      accept="audio/*,video/*"
                      onChange={(e: any) => {
                        if (e.target.files && e.target.files.length > 0) {
                          handleFileSelection(e.target.files[0]);
                        }
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-6 animate-in slide-in-from-bottom-4">
              <div className="bg-slate-50 p-6 rounded-none md:rounded-[2rem] border border-slate-100 max-h-[300px] overflow-y-auto custom-scrollbar">
                <label className="text-[10px] font-black text-indigo-500 uppercase tracking-widest block mb-2">Resultado Final</label>
                <p className="text-slate-800 text-base font-bold leading-relaxed whitespace-pre-wrap">{transcription.refined}</p>
              </div>
              <div className="flex gap-4">
                <button
                  onClick={() => { navigator.clipboard.writeText(transcription.refined); showToast("Texto copiado!", "success"); }}
                  className="flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-indigo-600 transition-all flex items-center justify-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                  Copiar Texto
                </button>
                <button onClick={() => setTranscription(null)} className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all">Novo</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
