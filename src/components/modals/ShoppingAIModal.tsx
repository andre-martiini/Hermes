import React, { useState, useRef } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../firebase';

const ShoppingAIModal = ({ isOpen, onClose, onProcessItems, onViewList }: { isOpen: boolean, onClose: () => void, onProcessItems: (text: string) => void, onViewList: () => void }) => {
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
      alert("Permissão de microfone negada ou não disponível.");
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
          if (data.refined) {
             const newText = textInput ? textInput + ', ' + data.refined : data.refined;
             setTextInput(newText);
          }
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          alert("Erro ao processar áudio via Hermes AI.");
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
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-md animate-in fade-in">
      <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[3rem] shadow-[0_40px_80px_-20px_rgba(0,0,0,0.3)] overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-10 border-b border-slate-100 bg-gradient-to-br from-emerald-50 to-white flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 bg-emerald-600 rounded-[1.5rem] flex items-center justify-center shadow-lg shadow-emerald-200">
              <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
            </div>
            <div>
              <h3 className="text-2xl font-black text-slate-900 tracking-tight">Assistente de Compras</h3>
              <p className="text-emerald-600 text-[10px] font-black uppercase tracking-[0.2em] mt-1">Processamento via Gemini 2.5</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onViewList}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-100 text-emerald-700 rounded-none md:rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-emerald-200 transition-all border border-emerald-200"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 10h16M4 14h16M4 18h16" /></svg>
              Ver Listas
            </button>
            <button onClick={onClose} className="p-3 hover:bg-slate-100 rounded-2xl transition-all group">
              <svg className="w-6 h-6 text-slate-300 group-hover:text-slate-600 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        <div className="p-10 space-y-8">
          <div className="bg-slate-50 p-3 rounded-[2rem] border-2 border-slate-100 flex items-center gap-5 focus-within:border-emerald-500 transition-all shadow-inner">
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessing}
              className={`w-16 h-16 rounded-2xl transition-all flex-shrink-0 flex items-center justify-center ${
                isRecording
                  ? 'bg-rose-600 text-white animate-pulse shadow-xl shadow-rose-200'
                  : isProcessing
                    ? 'bg-emerald-100 text-emerald-600 cursor-wait'
                    : 'bg-white border-2 border-slate-100 text-slate-400 hover:text-emerald-600 hover:border-emerald-100 hover:shadow-lg transition-all'
              }`}
            >
              {isProcessing ? (
                <div className="w-6 h-6 border-3 border-emerald-600 border-t-transparent rounded-full animate-spin"></div>
              ) : isRecording ? (
                <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
              ) : (
                <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
              )}
            </button>
            <textarea
              autoFocus
              disabled={isRecording || isProcessing}
              placeholder={isRecording ? "Fale os itens que deseja comprar..." : isProcessing ? "O Hermes está organizando sua lista..." : "Digite os itens que deseja planejar..."}
              className="flex-1 bg-transparent border-none outline-none py-4 text-lg font-bold text-slate-800 placeholder:text-slate-300 resize-none min-h-[100px]"
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
            />
          </div>

          <div className="bg-emerald-50/50 p-6 rounded-2xl border border-emerald-100/50 flex gap-4">
             <div className="w-10 h-10 bg-emerald-100 rounded-xl flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
             </div>
             <p className="text-[11px] font-bold text-emerald-800 leading-relaxed">
               Diga o que você precisa e o Hermes buscará em todas as listas cadastradas, marcando os itens automaticamente.
             </p>
          </div>

          <div className="flex gap-6">
            <button onClick={onClose} className="flex-1 py-5 text-[11px] font-black uppercase tracking-[0.2em] text-slate-400 hover:bg-slate-50 rounded-2xl transition-all">Descartar</button>
            <button
              onClick={() => {
                if (textInput.trim()) {
                  onProcessItems(textInput);
                  setTextInput('');
                  onClose();
                }
              }}
              disabled={!textInput.trim() || isProcessing || isRecording}
              className="flex-[2] bg-slate-900 text-white py-5 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] shadow-2xl shadow-slate-200 hover:bg-emerald-600 transition-all disabled:opacity-50 disabled:grayscale flex items-center justify-center gap-3"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
              Marcar Itens
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export { ShoppingAIModal };
