import React, { useState, useRef } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../firebase';

export const QuickNoteModal = ({ isOpen, onClose, onAddIdea, showAlert }: { isOpen: boolean, onClose: () => void, onAddIdea: (text: string) => void, showAlert: (t: string, m: string) => void }) => {
  const [textInput, setTextInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  if (!isOpen) return null;

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
      showAlert("Erro", "Permissão de microfone negada ou não disponível.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessing(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };
          if (data.refined) onAddIdea(data.refined);
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          showAlert("Erro", "Erro ao processar áudio via Hermes AI.");
        } finally {
          setIsProcessing(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 animate-in fade-in">
      <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight">Nota Rápida</h3>
            <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-1">Captação Instantânea</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="p-8 space-y-6">
          <div className="bg-slate-50 p-2 rounded-none md:rounded-2xl border-2 border-slate-100 flex items-center gap-4 focus-within:border-blue-500 transition-all">
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessing}
              className={`p-4 rounded-none md:rounded-xl transition-all flex-shrink-0 ${
                isRecording
                  ? 'bg-rose-600 text-white animate-pulse shadow-lg'
                  : isProcessing
                    ? 'bg-blue-100 text-blue-600 cursor-wait'
                    : 'bg-white border border-slate-200 text-slate-400 hover:text-blue-600'
              }`}
            >
              {isProcessing ? (
                <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
              ) : isRecording ? (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
              )}
            </button>
            <input
              autoFocus
              type="text"
              disabled={isRecording || isProcessing}
              placeholder={isRecording ? "Gravando..." : isProcessing ? "Processando..." : "O que está pensando?"}
              className="flex-1 bg-transparent border-none outline-none py-4 text-base font-bold text-slate-800 placeholder:text-slate-300"
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && textInput.trim()) {
                  onAddIdea(textInput);
                  setTextInput('');
                  onClose();
                }
              }}
            />
          </div>
          <div className="flex gap-4">
            <button onClick={onClose} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-none md:rounded-2xl transition-all">Cancelar</button>
            <button
              onClick={() => {
                if (textInput.trim()) {
                  onAddIdea(textInput);
                  setTextInput('');
                  onClose();
                }
              }}
              disabled={!textInput.trim()}
              className="flex-none w-12 md:w-auto md:flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5 md:hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
              <span className="hidden md:inline">Salvar Ideia</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
