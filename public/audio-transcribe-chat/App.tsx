
import React, { useState, useRef, useEffect } from 'react';
import { Message, SenderType, ChatSession } from './types';
import { transcribeAudio } from './services/geminiService';
import { ChatBubble } from './components/ChatBubble';
import { AudioRecorder } from './components/AudioRecorder';

const STORAGE_KEY = 'audio_transcribe_sessions';

const App: React.FC = () => {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Carrega as sessões do localStorage na montagem do componente
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setSessions(parsed);
        if (parsed.length > 0) {
          loadSession(parsed[0].id);
        } else {
          startNewChat();
        }
      } catch (e) {
        console.error("Erro ao carregar sessões", e);
        startNewChat();
      }
    } else {
      startNewChat();
    }
  }, []);

  // Salva a sessão atual sempre que as mensagens mudam
  useEffect(() => {
    if (!currentSessionId || messages.length === 0) return;

    const firstSystemMsg = messages.find(m => m.sender === SenderType.SYSTEM && m.content && !m.id.startsWith('welcome'));
    const title = firstSystemMsg?.content?.substring(0, 30) + (firstSystemMsg?.content?.length && firstSystemMsg.content.length > 30 ? '...' : '') || 'Nova Conversa';
    
    setSessions(prev => {
      const existingIdx = prev.findIndex(s => s.id === currentSessionId);
      let updatedSessions;
      
      if (existingIdx >= 0) {
        updatedSessions = [...prev];
        updatedSessions[existingIdx] = {
          ...updatedSessions[existingIdx],
          messages,
          title: messages.length > 1 ? title : updatedSessions[existingIdx].title,
          updatedAt: new Date()
        };
      } else {
        updatedSessions = [{
          id: currentSessionId,
          title: 'Conversa Iniciada',
          messages,
          updatedAt: new Date()
        }, ...prev];
      }
      
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedSessions));
      return updatedSessions;
    });
  }, [messages, currentSessionId]);

  const startNewChat = () => {
    const newId = Date.now().toString();
    setCurrentSessionId(newId);
    setMessages([
      {
        id: 'welcome-' + newId,
        sender: SenderType.SYSTEM,
        content: 'Bem-vindo! Clique no ícone do microfone abaixo para gravar um áudio e eu farei a transcrição automática para você.',
        timestamp: new Date(),
      }
    ]);
    setDeleteConfirm(false);
    setIsSidebarOpen(false);
  };

  const loadSession = (id: string) => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed: ChatSession[] = JSON.parse(saved);
      const session = parsed.find(s => s.id === id);
      if (session) {
        setCurrentSessionId(session.id);
        setMessages(session.messages);
        setIsSidebarOpen(false);
      }
    }
  };

  const deleteSession = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = sessions.filter(s => s.id !== id);
    setSessions(updated);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    if (currentSessionId === id) {
      startNewChat();
    }
  };

  const handleMessageDelete = (messageId: string) => {
    setMessages(prev => prev.filter(m => m.id !== messageId));
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleAudioReady = async (blob: Blob, base64: string, url: string) => {
    const userId = Date.now().toString();
    const userMessage: Message = {
      id: userId,
      sender: SenderType.USER,
      content: "Mensagem de áudio enviada.",
      audioUrl: url,
      timestamp: new Date(),
    };

    const systemId = (Date.now() + 1).toString();
    const systemMessage: Message = {
      id: systemId,
      sender: SenderType.SYSTEM,
      content: "",
      timestamp: new Date(),
      isTranscribing: true,
    };

    setMessages(prev => [...prev, userMessage, systemMessage]);
    setIsProcessing(true);

    try {
      const transcription = await transcribeAudio(base64, blob.type);
      setMessages(prev => prev.map(msg => 
        msg.id === systemId 
          ? { ...msg, content: transcription, isTranscribing: false } 
          : msg
      ));
    } catch (error: any) {
      setMessages(prev => prev.map(msg => 
        msg.id === systemId 
          ? { ...msg, content: error.message || "Erro inesperado.", isTranscribing: false } 
          : msg
      ));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleNewChatClick = () => {
    if (deleteConfirm) {
      startNewChat();
    } else {
      setDeleteConfirm(true);
      setTimeout(() => setDeleteConfirm(false), 3000); 
    }
  };

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden font-sans">
      {/* Sidebar Histórico */}
      <aside className={`fixed inset-y-0 left-0 z-30 w-72 bg-white border-r border-gray-200 transform ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'} lg:relative lg:translate-x-0 transition-transform duration-300 ease-in-out shadow-lg lg:shadow-none`}>
        <div className="h-full flex flex-col">
          <div className="p-6 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
            <h2 className="text-lg font-bold text-gray-800">Histórico</h2>
            <button onClick={() => setIsSidebarOpen(false)} className="lg:hidden p-2 text-gray-500 hover:bg-gray-200 rounded-full transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {sessions.map(s => (
              <div 
                key={s.id}
                onClick={() => loadSession(s.id)}
                className={`group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all ${currentSessionId === s.id ? 'bg-blue-600 text-white shadow-md' : 'hover:bg-gray-100'}`}
              >
                <div className="flex-1 min-w-0 pr-2">
                  <p className={`text-sm font-semibold truncate ${currentSessionId === s.id ? 'text-white' : 'text-gray-700'}`}>
                    {s.title}
                  </p>
                  <p className={`text-[10px] mt-1 ${currentSessionId === s.id ? 'text-blue-100' : 'text-gray-400'}`}>
                    {new Date(s.updatedAt).toLocaleDateString()} {new Date(s.updatedAt).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                  </p>
                </div>
                <button 
                  onClick={(e) => deleteSession(s.id, e)}
                  className={`opacity-0 group-hover:opacity-100 p-1.5 rounded-lg transition-all ${currentSessionId === s.id ? 'text-blue-100 hover:text-white hover:bg-blue-500' : 'text-gray-400 hover:text-red-500 hover:bg-red-50'}`}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                </button>
              </div>
            ))}
            {sessions.length === 0 && (
              <div className="flex flex-col items-center justify-center h-40 opacity-40">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <p className="text-center text-sm font-medium">Nenhuma conversa salva.</p>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Main Chat Content */}
      <div className="flex-1 flex flex-col h-full relative overflow-hidden">
        {/* Header */}
        <header className="bg-white/80 backdrop-blur-md border-b border-gray-200 py-4 px-6 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center space-x-3">
            <button 
              onClick={() => setIsSidebarOpen(true)}
              className="lg:hidden p-2 bg-gray-100 rounded-lg text-gray-600 hover:bg-gray-200 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="bg-blue-600 rounded-xl p-2.5 shadow-lg shadow-blue-200">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-extrabold text-gray-900 tracking-tight leading-none">Transcribe AI</h1>
              <p className="text-[11px] text-green-500 font-bold flex items-center mt-1 uppercase tracking-wider">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-1.5 animate-pulse"></span>
                Online
              </p>
            </div>
          </div>
          
          <button 
            onClick={handleNewChatClick}
            className={`flex items-center space-x-2 px-5 py-2.5 rounded-xl transition-all font-bold text-sm shadow-sm ${deleteConfirm ? 'bg-red-500 text-white animate-pulse' : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'}`}
          >
            {deleteConfirm ? (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
                <span>Confirmar Novo Chat</span>
              </>
            ) : (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                <span>Nova Conversa</span>
              </>
            )}
          </button>
        </header>

        {/* Chat Area */}
        <main className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 max-w-4xl w-full mx-auto scroll-smooth">
          {messages.map((message) => (
            <ChatBubble key={message.id} message={message} onDelete={handleMessageDelete} />
          ))}
          <div ref={messagesEndRef} className="h-4" />
        </main>

        {/* Controls */}
        <footer className="bg-white border-t border-gray-100 p-6 md:p-8 shadow-[0_-4px_20px_-10px_rgba(0,0,0,0.1)] z-20">
          <div className="max-w-3xl mx-auto flex flex-col items-center">
            <div className="flex items-center justify-center space-x-8 w-full">
              <AudioRecorder onAudioReady={handleAudioReady} disabled={isProcessing} />
              
              <div className="flex items-center space-x-4">
                 <label className={`cursor-pointer group bg-gray-50 hover:bg-blue-600 text-gray-500 hover:text-white p-4 rounded-full transition-all border border-gray-100 hover:border-blue-500 hover:shadow-lg hover:shadow-blue-200 ${isProcessing ? 'opacity-30 pointer-events-none' : ''}`} title="Upload de arquivo de áudio">
                   <input 
                     type="file" 
                     accept="audio/*" 
                     className="hidden" 
                     onChange={(e) => {
                       const file = e.target.files?.[0];
                       if (file) {
                         const url = URL.createObjectURL(file);
                         const reader = new FileReader();
                         reader.readAsDataURL(file);
                         reader.onloadend = () => {
                           const base64String = (reader.result as string).split(',')[1];
                           handleAudioReady(file, base64String, url);
                         };
                       }
                     }}
                     disabled={isProcessing}
                   />
                   <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                   </svg>
                 </label>
              </div>
            </div>
            <p className="text-center text-[11px] text-gray-400 mt-6 uppercase tracking-widest font-bold opacity-60">
              Sua privacidade é respeitada: áudios são processados de forma privada
            </p>
          </div>
        </footer>
        
        {/* Overlay mobile sidebar */}
        {isSidebarOpen && (
          <div 
            className="fixed inset-0 bg-gray-900/40 backdrop-blur-sm z-20 lg:hidden transition-all duration-300"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}
      </div>
    </div>
  );
};

export default App;
