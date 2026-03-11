import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  askWhatsAppAssistant,
  type AssistantConversationMessage,
  type WhatsAppAttachmentRef,
  type WhatsAppAssistantContext,
} from '../../utils/whatsappAssistant';

interface WhatsAppAssistantToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
  attachments?: WhatsAppAttachmentRef[];
}

interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  context: WhatsAppAssistantContext;
  messages: ChatMessage[];
}

const STORAGE_KEY = 'hermes_whatsapp_assistant_sessions_v1';

const createSession = (): ChatSession => {
  const now = new Date().toISOString();
  return {
    id: `chat_${Date.now()}`,
    title: 'Nova conversa',
    createdAt: now,
    updatedAt: now,
    context: {},
    messages: [
      {
        id: `msg_${Date.now()}`,
        role: 'assistant',
        text: 'Oi. Posso achar grupos por nome aproximado e manter o contexto da conversa. Diga o que voce quer buscar.',
        timestamp: now,
      },
    ],
  };
};

const escapeHtml = (value: string): string =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

const markdownToHtml = (markdown: string): string => {
  const escaped = escapeHtml(markdown);
  const linked = escaped.replace(
    /\[(.*?)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-600 underline">$1</a>',
  );
  const urlified = linked.replace(
    /(^|\s)(https?:\/\/[^\s<]+)/g,
    '$1<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-600 underline">$2</a>',
  );
  const strong = urlified.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  const italic = strong.replace(/\*(.*?)\*/g, '<em>$1</em>');

  return italic
    .split('\n')
    .map((line) => {
      if (line.startsWith('### ')) return `<h3 class="text-base font-bold mt-3">${line.replace('### ', '')}</h3>`;
      if (line.startsWith('## ')) return `<h2 class="text-lg font-bold mt-3">${line.replace('## ', '')}</h2>`;
      if (line.startsWith('# ')) return `<h1 class="text-xl font-bold mt-3">${line.replace('# ', '')}</h1>`;
      if (line.startsWith('- ')) return `<li>${line.replace('- ', '')}</li>`;
      if (!line.trim()) return '<br/>';
      return `<p>${line}</p>`;
    })
    .join('')
    .replace(/(<li>.*?<\/li>)/g, '<ul class="list-disc ml-5">$1</ul>');
};

const toConversationHistory = (messages: ChatMessage[]): AssistantConversationMessage[] =>
  messages
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    .map((item) => ({ role: item.role, text: item.text }));

export const WhatsAppAssistantTool: React.FC<WhatsAppAssistantToolProps> = ({ onBack, showToast }) => {
  const [command, setCommand] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as ChatSession[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setSessions(parsed);
          setActiveSessionId(parsed[0].id);
          return;
        }
      }
    } catch (error) {
      console.error(error);
    }

    const first = createSession();
    setSessions([first]);
    setActiveSessionId(first.id);
  }, []);

  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    }
  }, [sessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [sessions, activeSessionId, isLoading]);

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? sessions[0],
    [sessions, activeSessionId],
  );

  const updateActiveSession = (updater: (session: ChatSession) => ChatSession): void => {
    if (!activeSession) {
      return;
    }

    setSessions((prev) => prev.map((session) => (session.id === activeSession.id ? updater(session) : session)));
  };

  const handleNewSession = (): void => {
    const newSession = createSession();
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  };

  const handleSubmit = async (): Promise<void> => {
    if (!command.trim() || isLoading || !activeSession) {
      return;
    }

    const userText = command.trim();
    setCommand('');

    const userMessage: ChatMessage = {
      id: `msg_${Date.now()}_u`,
      role: 'user',
      text: userText,
      timestamp: new Date().toISOString(),
    };

    const optimisticMessages = [...activeSession.messages, userMessage];
    updateActiveSession((session) => ({
      ...session,
      updatedAt: new Date().toISOString(),
      title: session.title === 'Nova conversa' ? userText.slice(0, 48) : session.title,
      messages: optimisticMessages,
    }));

    setIsLoading(true);
    try {
      const response = await askWhatsAppAssistant(
        userText,
        activeSession.context,
        toConversationHistory(optimisticMessages),
      );

      const assistantMessage: ChatMessage = {
        id: `msg_${Date.now()}_a`,
        role: 'assistant',
        text: response.markdown || 'Sem resposta textual do modelo.',
        timestamp: new Date().toISOString(),
        attachments: response.attachments,
      };

      updateActiveSession((session) => ({
        ...session,
        updatedAt: new Date().toISOString(),
        context: response.context,
        messages: [...session.messages, assistantMessage],
      }));
    } catch (error) {
      console.error(error);
      showToast('Falha ao consultar mensagens do WhatsApp.', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  if (!activeSession) {
    return null;
  }

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="p-3 bg-white border border-slate-200 rounded-2xl text-slate-500 hover:text-slate-900">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
          </button>
          <h3 className="text-sm md:text-base font-black uppercase tracking-widest text-slate-700">Chat WhatsApp</h3>
        </div>
        <button
          onClick={handleNewSession}
          className="bg-slate-900 text-white px-3 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest"
        >
          Nova conversa
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {sessions.slice(0, 8).map((session) => (
          <button
            key={session.id}
            onClick={() => setActiveSessionId(session.id)}
            className={`px-3 py-1.5 rounded-full text-[11px] font-bold border transition-colors ${
              activeSession.id === session.id
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
            }`}
          >
            {session.title || 'Conversa'}
          </button>
        ))}
      </div>

      <div className="bg-white border border-slate-200 rounded-3xl p-4 md:p-6 shadow-sm space-y-3">
        <div className="flex items-center justify-between gap-3 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2">
          <p className="text-xs font-semibold text-slate-600">
            Contexto atual: <span className="text-slate-900">{activeSession.context.selectedChatName || 'Nenhum grupo selecionado'}</span>
          </p>
          <button
            onClick={() => updateActiveSession((session) => ({ ...session, context: {} }))}
            className="text-[10px] font-black uppercase tracking-widest text-slate-500 hover:text-slate-800"
          >
            Limpar contexto
          </button>
        </div>

        <div className="border border-slate-200 rounded-2xl p-4 h-[460px] overflow-y-auto space-y-3 bg-slate-50/40">
          {activeSession.messages.map((message) => (
            <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[82%] rounded-2xl px-4 py-3 ${
                  message.role === 'user' ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-700'
                }`}
              >
                {message.role === 'assistant' ? (
                  <div dangerouslySetInnerHTML={{ __html: markdownToHtml(message.text) }} />
                ) : (
                  <p className="text-sm font-medium whitespace-pre-wrap">{message.text}</p>
                )}

                {message.attachments && message.attachments.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {message.attachments.slice(0, 8).map((attachment) => (
                      <a
                        key={`${message.id}_${attachment.referenceId}`}
                        href={attachment.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-blue-700 hover:border-blue-300"
                      >
                        [{attachment.referenceId}] {attachment.fileName}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white border border-slate-200 rounded-2xl px-4 py-3 text-sm text-slate-500">Consultando...</div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="flex gap-3">
          <input
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSubmit();
              }
            }}
            placeholder="Ex.: encontre o grupo da obra e me diga o que ficou pendente hoje"
            className="flex-1 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium outline-none focus:ring-2 focus:ring-blue-100"
          />
          <button
            onClick={() => void handleSubmit()}
            disabled={isLoading}
            className="bg-blue-600 text-white px-4 py-3 rounded-xl text-xs font-black uppercase tracking-widest disabled:opacity-60"
          >
            {isLoading ? 'Enviando...' : 'Enviar'}
          </button>
        </div>
      </div>
    </div>
  );
};
