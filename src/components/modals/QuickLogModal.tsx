import React, { useState, useRef, useMemo, useEffect } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../firebase';
const QuickLogModal = ({ isOpen, onClose, onAddLog, unidades }: { isOpen: boolean, onClose: () => void, onAddLog: (text: string, systemId: string) => void, unidades: { id: string, nome: string }[] }) => {
  const [textInput, setTextInput] = useState('');
  const [selectedSystem, setSelectedSystem] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const systems = useMemo(() => unidades.filter(u => u.nome.startsWith('SISTEMA:')), [unidades]);

  useEffect(() => {
    if (systems.length > 0 && !selectedSystem) {
        setSelectedSystem(systems[0].id);
    }
  }, [systems, selectedSystem]);

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
             const newText = textInput ? textInput + '\n' + data.refined : data.refined;
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
    <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-white w-full max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight">Log Rápido</h3>
            <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-1">Registro de Sistema</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="p-8 space-y-6">
          <div className="space-y-2">
             <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Sistema</label>
             <select
               value={selectedSystem}
               onChange={(e) => setSelectedSystem(e.target.value)}
               className="w-full bg-slate-50 border border-slate-200 rounded-lg md:rounded-xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-violet-500"
             >
                <option value="" disabled>Selecione um sistema</option>
                {systems.map(s => (
                    <option key={s.id} value={s.id}>{s.nome.replace('SISTEMA:', '').trim()}</option>
                ))}
             </select>
          </div>

          <div className="bg-slate-50 p-2 rounded-none md:rounded-2xl border-2 border-slate-100 flex items-center gap-4 focus-within:border-violet-500 transition-all">
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessing}
              className={`p-4 rounded-none md:rounded-xl transition-all flex-shrink-0 ${
                isRecording
                  ? 'bg-rose-600 text-white animate-pulse shadow-lg'
                  : isProcessing
                    ? 'bg-violet-100 text-violet-600 cursor-wait'
                    : 'bg-white border border-slate-200 text-slate-400 hover:text-violet-600'
              }`}
            >
              {isProcessing ? (
                <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin"></div>
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
              placeholder={isRecording ? "Gravando..." : isProcessing ? "Processando..." : "Descreva o ajuste..."}
              className="flex-1 bg-transparent border-none outline-none py-4 text-base font-bold text-slate-800 placeholder:text-slate-300"
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && textInput.trim() && selectedSystem) {
                  onAddLog(textInput, selectedSystem);
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
                if (textInput.trim() && selectedSystem) {
                  onAddLog(textInput, selectedSystem);
                  setTextInput('');
                  onClose();
                }
              }}
              disabled={!textInput.trim() || !selectedSystem}
              className="flex-none w-16 md:w-auto md:flex-1 bg-slate-900 text-white py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5 md:hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
              <span className="hidden md:inline">Registrar Log</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export { QuickLogModal };
