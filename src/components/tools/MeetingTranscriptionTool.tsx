import React, { useState, useRef, useEffect, useCallback } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '@/firebase';

export interface TranscriptionEntry {
  id: string;
  speaker: 'Você' | 'Reunião';
  text: string;
  timestamp: Date;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface MeetingTranscriptionToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
}

export const MeetingTranscriptionTool: React.FC<MeetingTranscriptionToolProps> = ({ onBack, showToast }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptionEntry[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isChatting, setIsChatting] = useState(false);
  const [chatInput, setChatInput] = useState('');

  const micRecorderRef = useRef<MediaRecorder | null>(null);
  const systemRecorderRef = useRef<MediaRecorder | null>(null);
  const micWsRef = useRef<WebSocket | null>(null);
  const systemWsRef = useRef<WebSocket | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const systemStreamRef = useRef<MediaStream | null>(null);
  const transcriptsEndRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottomTranscripts = () => {
    transcriptsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const scrollToBottomChat = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottomTranscripts();
  }, [transcripts]);

  useEffect(() => {
    scrollToBottomChat();
  }, [chatMessages]);

  const startRecording = async () => {
    try {
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const systemStream = await navigator.mediaDevices.getDisplayMedia({ audio: true, video: true });

      systemStream.getVideoTracks().forEach(track => track.stop());

      if (systemStream.getAudioTracks().length === 0) {
         showToast("O áudio do sistema não foi compartilhado.", "error");
         systemStream.getTracks().forEach(track => track.stop());
         micStream.getTracks().forEach(track => track.stop());
         return;
      }

      micStreamRef.current = micStream;
      systemStreamRef.current = systemStream;

      const wsUrl = `wss://api.deepgram.com/v1/listen?model=nova-2&language=pt-BR`;
      const apiKey = import.meta.env.VITE_DEEPGRAM_API_KEY;

      if (!apiKey) {
        showToast("Chave API do Deepgram não configurada.", "error");
        systemStream.getTracks().forEach(track => track.stop());
        micStream.getTracks().forEach(track => track.stop());
        return;
      }

      const protocols = ['token', apiKey];

      const micWs = new WebSocket(wsUrl, protocols);
      const systemWs = new WebSocket(wsUrl, protocols);
      micWsRef.current = micWs;
      systemWsRef.current = systemWs;

      micWs.onopen = () => {
        const recorder = new MediaRecorder(micStream);
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0 && micWs.readyState === WebSocket.OPEN) {
            micWs.send(event.data);
          }
        };
        recorder.start(250);
        micRecorderRef.current = recorder;
      };

      micWs.onmessage = (message) => {
        const received = JSON.parse(message.data);
        const transcript = received.channel?.alternatives[0]?.transcript;
        if (transcript && transcript.trim().length > 0) {
          setTranscripts(prev => [...prev, {
            id: Date.now().toString() + Math.random().toString(),
            speaker: 'Você' as const,
            text: transcript,
            timestamp: new Date()
          }].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime()));
        }
      };

      systemWs.onopen = () => {
        const recorder = new MediaRecorder(systemStream);
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0 && systemWs.readyState === WebSocket.OPEN) {
            systemWs.send(event.data);
          }
        };
        recorder.start(250);
        systemRecorderRef.current = recorder;
      };

      systemWs.onmessage = (message) => {
        const received = JSON.parse(message.data);
        const transcript = received.channel?.alternatives[0]?.transcript;
        if (transcript && transcript.trim().length > 0) {
          setTranscripts(prev => [...prev, {
            id: Date.now().toString() + Math.random().toString(),
            speaker: 'Reunião' as const,
            text: transcript,
            timestamp: new Date()
          }].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime()));
        }
      };

      systemStream.getVideoTracks().forEach(track => {
         track.onended = () => {
             stopRecording();
         };
      });

      setIsRecording(true);
      showToast("Gravação e transcrição iniciadas.", "info");

    } catch (err) {
      console.error("Erro ao acessar mídias:", err);
      showToast("Permissão negada ou hardware indisponível.", "error");
    }
  };

  const stopRecording = useCallback(() => {
     if (micRecorderRef.current) micRecorderRef.current.stop();
     if (systemRecorderRef.current) systemRecorderRef.current.stop();

     if (micWsRef.current) micWsRef.current.close();
     if (systemWsRef.current) systemWsRef.current.close();

     if (micStreamRef.current) micStreamRef.current.getTracks().forEach(t => t.stop());
     if (systemStreamRef.current) systemStreamRef.current.getTracks().forEach(t => t.stop());

     setIsRecording(false);
  }, []);

  useEffect(() => {
    return () => {
      stopRecording();
    };
  }, [stopRecording]);

  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: chatInput,
      timestamp: new Date()
    };

    setChatMessages(prev => [...prev, userMessage]);
    setChatInput('');
    setIsChatting(true);

    try {
      const contextSnapshot = transcripts.map(t => `[${t.timestamp.toLocaleTimeString()}] ${t.speaker}: ${t.text}`).join('\n');

      const fullPrompt = `Contexto da Reunião em andamento:\n\n${contextSnapshot}\n\nPergunta/Comando do Usuário: ${userMessage.content}`;

      const askChatbotFunc = httpsCallable(functions, 'askChatbot');

      let reply = "Desculpe, a IA está indisponível no momento.";
      try {
          const response = await askChatbotFunc({ prompt: fullPrompt });
          const data = response.data as { result: string };
          if (data && data.result) reply = data.result;
      } catch (e) {
          console.error("AI Error:", e);
          reply = `[Simulação] Resposta gerada baseada no contexto fornecido.\nVocê perguntou: ${userMessage.content}`;
      }

      setChatMessages(prev => [...prev, {
        id: Date.now().toString() + 'bot',
        role: 'assistant',
        content: reply,
        timestamp: new Date()
      }]);
    } catch (error) {
       console.error(error);
       showToast("Erro ao comunicar com a IA.", "error");
    } finally {
       setIsChatting(false);
    }
  };

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 h-full flex flex-col pb-20">
      <div className="flex items-center gap-6 mb-8 flex-shrink-0">
        <button onClick={onBack} className="w-12 h-12 bg-white rounded-2xl flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-900 transition-all shadow-sm">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div className="flex-1">
          <h2 className="text-3xl font-black text-slate-900 tracking-tighter">TranscriÃ§ão de ReuniÃµes</h2>
          <p className="text-slate-500 font-medium">Capture e interaja com o áudio da sua reuniÃ£o em tempo real via IA.</p>
        </div>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-8 min-h-[600px]">
        <div className="bg-white rounded-[2.5rem] border border-slate-200 shadow-xl flex flex-col overflow-hidden h-full">
          <div className="p-6 border-b border-slate-100 flex justify-between items-center bg-slate-50 shrink-0">
            <h3 className="text-xl font-black text-slate-900 flex items-center gap-2">
               Transcrição
               {isRecording && <span className="flex h-3 w-3 relative ml-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span><span className="relative inline-flex rounded-full h-3 w-3 bg-rose-500"></span></span>}
            </h3>
            <button
              onClick={isRecording ? stopRecording : startRecording}
              className={`px-6 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-sm ${
                isRecording
                ? 'bg-rose-100 text-rose-600 hover:bg-rose-200'
                : 'bg-slate-900 text-white hover:bg-blue-600'
              }`}
            >
              {isRecording ? 'Parar Gravação' : 'Iniciar Gravação'}
            </button>
          </div>

          <div className="flex-1 p-6 overflow-y-auto custom-scrollbar space-y-4">
             {transcripts.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center opacity-40">
                  <svg className="w-16 h-16 text-slate-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                  <p className="text-slate-400 font-bold">Inicie a gravação para ver a transcrição.</p>
                </div>
             ) : (
                transcripts.map(t => (
                  <div key={t.id} className={`flex flex-col ${t.speaker === 'Você' ? 'items-end' : 'items-start'}`}>
                     <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1 mx-1">
                        {t.speaker} • {t.timestamp.toLocaleTimeString()}
                     </span>
                     <div className={`px-4 py-3 rounded-2xl max-w-[85%] ${t.speaker === 'Você' ? 'bg-blue-600 text-white rounded-tr-sm' : 'bg-slate-100 text-slate-800 rounded-tl-sm'}`}>
                        <p className="text-sm font-medium">{t.text}</p>
                     </div>
                  </div>
                ))
             )}
             <div ref={transcriptsEndRef} />
          </div>
        </div>

        <div className="bg-white rounded-[2.5rem] border border-slate-200 shadow-xl flex flex-col overflow-hidden h-full">
          <div className="p-6 border-b border-slate-100 bg-slate-50 shrink-0">
            <h3 className="text-xl font-black text-slate-900">Chatbot Assistente</h3>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Baseado no contexto da reunião</p>
          </div>

          <div className="flex-1 p-6 overflow-y-auto custom-scrollbar space-y-4">
             {chatMessages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center opacity-40">
                   <svg className="w-16 h-16 text-slate-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
                   <p className="text-slate-400 font-bold">Pergunte algo sobre a reunião.</p>
                </div>
             ) : (
                chatMessages.map(msg => (
                  <div key={msg.id} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                     <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1 mx-1">
                        {msg.role === 'user' ? 'Você' : 'Assistente'} • {msg.timestamp.toLocaleTimeString()}
                     </span>
                     <div className={`px-4 py-3 rounded-2xl max-w-[85%] ${msg.role === 'user' ? 'bg-emerald-600 text-white rounded-tr-sm' : 'bg-slate-100 text-slate-800 rounded-tl-sm border border-slate-200'}`}>
                        <p className="text-sm font-medium whitespace-pre-wrap">{msg.content}</p>
                     </div>
                  </div>
                ))
             )}
             {isChatting && (
                 <div className="flex flex-col items-start mt-4">
                    <div className="px-4 py-3 rounded-2xl bg-slate-100 text-slate-500 rounded-tl-sm border border-slate-200 flex items-center gap-2 w-16 justify-center">
                       <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"></span>
                       <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></span>
                       <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{animationDelay: '0.4s'}}></span>
                    </div>
                 </div>
             )}
             <div ref={chatEndRef} />
          </div>

          <div className="p-4 bg-white border-t border-slate-100 shrink-0">
             <div className="flex gap-2">
                <input
                   type="text"
                   value={chatInput}
                   onChange={e => setChatInput(e.target.value)}
                   onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                   placeholder="Pergunte sobre a reunião..."
                   disabled={isChatting}
                   className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all disabled:opacity-50"
                />
                <button
                   onClick={handleSendMessage}
                   disabled={isChatting || !chatInput.trim()}
                   className="bg-slate-900 text-white p-3 rounded-xl hover:bg-blue-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                >
                   <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 12h14M12 5l7 7-7 7" /></svg>
                </button>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
};
