import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { httpsCallable } from 'firebase/functions';
import { functions } from '@/firebase'; 

interface SourceMetadata {
  id: string;
  title: string;
  type: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sourcesMetadata?: SourceMetadata[];
}

interface KnowledgeChatModalProps {
  isOpen: boolean;
  onClose: () => void;
  isDark: boolean;
  onNavigateTask?: (id: string) => void;
  onNavigateSystem?: (id: string) => void;
  onNavigateFile?: (url: string) => void;
}

export const KnowledgeChatModal = ({ 
  isOpen, 
  onClose, 
  isDark,
  onNavigateTask,
  onNavigateSystem,
  onNavigateFile
}: KnowledgeChatModalProps) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  if (!isOpen) return null;

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    const currentInput = input;
    setInput('');
    setIsLoading(true);

    try {
      const askIntelligence = httpsCallable(functions, 'askHermesIntelligence');
      const history = messages.slice(-5).map(m => ({ role: m.role, content: m.content }));
      const result = await askIntelligence({ prompt: currentInput, history });
      const data = result.data as any;

      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: data.result || 'Não consegui processar a resposta.',
        sourcesMetadata: data.sources
      }]);
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Erro ao conectar ao Cérebro Hermes. Verifique sua conexão.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Componente customizado para renderizar links hermes://
  const MarkdownLink = ({ href, children }: any) => {
    if (href?.startsWith('hermes://')) {
      return (
        <button
          onClick={(e) => {
            e.preventDefault();
            const url = href.replace('hermes://', '');
            const [type, id] = url.split('/');
            if (type === 'action' || type === 'act') onNavigateTask?.(id);
            else if (type === 'system' || type === 'sys') onNavigateSystem?.(id);
            else if (type === 'file' || type === 'item') onNavigateFile?.(id);
          }}
          className="text-indigo-500 hover:text-indigo-400 font-black underline decoration-indigo-500/30 underline-offset-4 transition-all"
        >
          {children}
        </button>
      );
    }
    return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
  };

  return (
    <div className="fixed inset-0 z-[400] bg-black/70 backdrop-blur-md flex items-center justify-center p-4" onClick={onClose}>
      <div 
        className={`w-full max-w-2xl h-[80vh] flex flex-col rounded-3xl shadow-2xl overflow-hidden border ${isDark ? 'bg-[#0f0f1a] border-white/10' : 'bg-white border-slate-200'}`}
        onClick={e => e.stopPropagation()}
      >
        
        {/* Header */}
        <div className={`px-6 py-4 flex items-center justify-between border-b ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-lg">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            </div>
            <div>
              <h3 className={`text-sm font-black uppercase tracking-tighter ${isDark ? 'text-white' : 'text-slate-900'}`}>Cérebro Hermes</h3>
              <p className={`text-[10px] font-bold ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`}>Inteligência Relacional Ativa</p>
            </div>
          </div>
          <button onClick={onClose} className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10 text-white/40' : 'hover:bg-slate-100 text-slate-400'}`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-6" style={{ scrollbarWidth: 'thin' }}>
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center opacity-20">
              <svg className="w-16 h-16 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              <p className="text-sm font-black uppercase tracking-widest">Inicie uma conversa relacional</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] p-5 rounded-3xl ${
                m.role === 'user' 
                  ? 'bg-indigo-600 text-white rounded-br-none shadow-lg' 
                  : isDark ? 'bg-white/5 text-white/90 border border-white/10 rounded-bl-none' : 'bg-slate-50 text-slate-800 border border-slate-200 rounded-bl-none'
              }`}>
                <div className={`text-xs leading-relaxed max-w-none ${m.role === 'user' ? 'text-white' : isDark ? 'prose-invert text-slate-300' : 'text-slate-700'}`}>
                  <ReactMarkdown 
                    remarkPlugins={[remarkGfm]}
                    components={{
                      a: MarkdownLink,
                      p: ({children}) => <p className="mb-4 last:mb-0">{children}</p>
                    }}
                  >
                    {m.content}
                  </ReactMarkdown>
                </div>
                
                {m.sourcesMetadata && m.sourcesMetadata.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-white/5 space-y-2">
                    <p className="text-[10px] font-black uppercase tracking-widest opacity-40">Contexto Analisado:</p>
                    <div className="flex flex-wrap gap-2">
                      {m.sourcesMetadata.map((s, idx) => (
                        <button
                          key={s.id}
                          onClick={() => {
                            if (s.type === 'action' || s.type === 'act') onNavigateTask?.(s.id);
                            else if (s.type === 'system' || s.type === 'sys') onNavigateSystem?.(s.id);
                          }}
                          className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border transition-all hover:scale-105 active:scale-95 ${
                            isDark ? 'bg-white/5 border-white/10 hover:bg-white/10' : 'bg-white border-slate-200 hover:border-indigo-300 shadow-sm'
                          }`}
                        >
                          <span className="text-[9px] font-black text-indigo-500">FONTE {idx + 1}</span>
                          <span className={`text-[10px] font-bold truncate max-w-[150px] ${isDark ? 'text-white/70' : 'text-slate-600'}`}>{s.title}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className={`p-5 rounded-3xl rounded-bl-none flex gap-1.5 items-center ${isDark ? 'bg-white/5' : 'bg-slate-50'}`}>
                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className={`p-6 border-t ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
          <div className="flex gap-3">
            <input
              autoFocus
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              placeholder="Pergunte sobre CLC, IRP ou qualquer histórico…"
              className={`flex-1 px-5 py-4 rounded-2xl text-sm font-medium outline-none border transition-all ${
                isDark ? 'bg-white/5 border-white/10 text-white focus:border-indigo-500' : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-indigo-600'
              }`}
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="px-8 rounded-2xl bg-indigo-600 hover:bg-indigo-700 text-white font-black shadow-xl shadow-indigo-500/20 transition-all disabled:opacity-30 disabled:hover:bg-indigo-600 flex items-center justify-center gap-2"
            >
              <span>ENVIAR</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
