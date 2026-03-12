import React, { startTransition, useEffect, useEffectEvent, useReducer, useRef } from 'react';
import {
  askWhatsAppAssistant,
  type WhatsAppAttachmentRef,
  type WhatsAppChatCandidate,
} from '../../utils/whatsappAssistant';
import { AutoExpandingTextarea } from '../ui/UIComponents';
import { WhatsAppAssistantMarkdown } from './whatsappAssistantMarkdown';
import {
  STORAGE_KEY,
  createInitialAssistantState,
  getActiveAssistantSession,
  getSessionPreview,
  parseStoredAssistantSessions,
  prepareSessionsForStorage,
  toConversationHistory,
  whatsappAssistantReducer,
} from './whatsappAssistantState';

interface WhatsAppAssistantToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
}

const QUICK_PROMPTS = [
  'Encontre o grupo da obra e resuma o que ficou pendente hoje.',
  'Mostre os ultimos anexos enviados no grupo do financeiro.',
  'No mesmo grupo, o que responderam depois disso?',
];

const formatSessionTime = (timestamp: string): string => {
  try {
    return new Intl.DateTimeFormat('pt-BR', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(timestamp));
  } catch {
    return timestamp;
  }
};

const formatMessageTime = (timestamp: string): string => {
  try {
    return new Intl.DateTimeFormat('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(timestamp));
  } catch {
    return timestamp;
  }
};

const TypingIndicator: React.FC = () => (
  <div
    role="status"
    aria-label="Hermes esta respondendo"
    className="inline-flex items-center gap-2 rounded-[1.75rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 shadow-sm"
  >
    <span className="flex items-center gap-1.5">
      <span className="h-2.5 w-2.5 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.2s]" />
      <span className="h-2.5 w-2.5 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.1s]" />
      <span className="h-2.5 w-2.5 rounded-full bg-blue-500 animate-bounce" />
    </span>
    Consultando o historico
  </div>
);

const AttachmentCard: React.FC<{ attachment: WhatsAppAttachmentRef }> = ({ attachment }) => {
  const isImage = attachment.mimeType.startsWith('image/');
  const isAudio = attachment.mimeType.startsWith('audio/');
  const toneClass = isImage
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : isAudio
      ? 'border-violet-200 bg-violet-50 text-violet-700'
      : 'border-sky-200 bg-sky-50 text-sky-700';

  return (
    <a
      href={attachment.url}
      target="_blank"
      rel="noopener noreferrer"
      className={`block rounded-2xl border px-4 py-3 transition-all hover:-translate-y-0.5 hover:shadow-md ${toneClass}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] font-black uppercase tracking-[0.2em] opacity-70">
            [{attachment.referenceId}]
          </div>
          <div className="truncate text-sm font-bold">{attachment.fileName}</div>
          <div className="truncate text-[11px] font-medium opacity-80">{attachment.contactName}</div>
        </div>
        <div className="rounded-xl bg-white/70 px-2 py-1 text-[10px] font-black uppercase tracking-widest">
          Abrir
        </div>
      </div>
    </a>
  );
};

const CandidateChip: React.FC<{
  candidate: WhatsAppChatCandidate;
  isActive: boolean;
  onClick: () => void;
}> = ({ candidate, isActive, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded-full border px-3 py-2 text-left text-[11px] font-bold transition-all ${
      isActive
        ? 'border-blue-600 bg-blue-600 text-white shadow-lg shadow-blue-100'
        : 'border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:text-blue-700'
    }`}
  >
    {candidate.chatName}
  </button>
);

const createAssistantToolInitialState = () => {
  if (typeof window !== 'undefined') {
    try {
      const storedSessions = parseStoredAssistantSessions(localStorage.getItem(STORAGE_KEY));
      if (storedSessions.length > 0) {
        return {
          sessions: storedSessions,
          activeSessionId: storedSessions[0].id,
        };
      }
    } catch (error) {
      console.error(error);
    }
  }

  return createInitialAssistantState();
};

export const WhatsAppAssistantTool: React.FC<WhatsAppAssistantToolProps> = ({ onBack, showToast }) => {
  const [state, dispatch] = useReducer(whatsappAssistantReducer, undefined, createAssistantToolInitialState);
  const activeSession = getActiveAssistantSession(state);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prepareSessionsForStorage(state.sessions)));
  }, [state.sessions]);

  const scrollToBottom = useEffectEvent(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  });

  useEffect(() => {
    scrollToBottom();
  }, [activeSession.id, activeSession.messages.length, activeSession.status, scrollToBottom]);

  const handleNewSession = (): void => {
    dispatch({ type: 'createSession' });
  };

  const handleSubmit = async (): Promise<void> => {
    const draft = activeSession.draft.trim();
    if (!draft || activeSession.status === 'loading') {
      return;
    }

    const sessionId = activeSession.id;
    const now = new Date().toISOString();
    const optimisticHistory = toConversationHistory([
      ...activeSession.messages,
      {
        id: `optimistic_${now}`,
        role: 'user',
        text: draft,
        timestamp: now,
      },
    ]);

    dispatch({
      type: 'submitPrompt',
      sessionId,
      text: draft,
      now,
    });

    try {
      const response = await askWhatsAppAssistant(draft, activeSession.context, optimisticHistory);
      startTransition(() => {
        dispatch({
          type: 'resolvePrompt',
          sessionId,
          response,
          now: new Date().toISOString(),
        });
      });
    } catch (error) {
      console.error(error);
      dispatch({
        type: 'rejectPrompt',
        sessionId,
        error: 'Falha ao consultar mensagens do WhatsApp.',
      });
      showToast('Falha ao consultar mensagens do WhatsApp.', 'error');
    }
  };

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="rounded-2xl border border-slate-200 bg-white p-3 text-slate-500 transition-colors hover:text-slate-900"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div>
            <h3 className="text-sm font-black uppercase tracking-[0.25em] text-slate-700">Chat WhatsApp</h3>
            <p className="text-xs font-medium text-slate-500">
              Memoria de sessao persistente, busca contextual e leitura segura de anexos.
            </p>
          </div>
        </div>

        <button
          onClick={handleNewSession}
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-4 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-white shadow-lg shadow-slate-200 transition-all hover:-translate-y-0.5"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
          </svg>
          Nova conversa
        </button>
      </div>

      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <div className="overflow-hidden rounded-[2rem] border border-slate-200 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 p-5 text-white shadow-xl shadow-slate-200">
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-blue-200">Memoria de sessao</div>
            <div className="mt-3 text-xl font-black tracking-tight">
              {activeSession.context.selectedChatName || 'Nenhum grupo fixado'}
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-200">
              {activeSession.context.memorySummary ||
                'Abra um grupo ou faça uma pergunta contextual. O assistente vai reter o chat ativo e o foco recente da busca.'}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {activeSession.context.searchScopeLabel && (
                <span className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-blue-100">
                  Recorte: {activeSession.context.searchScopeLabel}
                </span>
              )}
              {typeof activeSession.context.resultCount === 'number' && (
                <span className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-blue-100">
                  {activeSession.context.resultCount} mensagens
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => dispatch({ type: 'clearContext', sessionId: activeSession.id })}
              className="mt-5 text-[10px] font-black uppercase tracking-[0.22em] text-slate-300 transition-colors hover:text-white"
            >
              Limpar contexto
            </button>
          </div>

          <div className="rounded-[2rem] border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h4 className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">Conversas</h4>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500">
                {state.sessions.length}
              </span>
            </div>

            <div className="max-h-[360px] space-y-2 overflow-y-auto pr-1">
              {state.sessions.map((session) => {
                const isActive = session.id === activeSession.id;
                return (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => dispatch({ type: 'setActiveSession', sessionId: session.id })}
                    className={`w-full rounded-[1.5rem] border px-4 py-3 text-left transition-all ${
                      isActive
                        ? 'border-blue-200 bg-blue-50 shadow-md shadow-blue-100'
                        : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="truncate text-sm font-black text-slate-900">{session.title}</div>
                      {session.status === 'loading' && (
                        <span className="rounded-full bg-blue-600 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-white">
                          ativo
                        </span>
                      )}
                    </div>
                    <div className="mt-2 line-clamp-2 text-xs font-medium leading-5 text-slate-500">
                      {getSessionPreview(session)}
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-300">
                      <span>{session.context.selectedChatName || 'Sem grupo fixo'}</span>
                      <span>{formatSessionTime(session.updatedAt)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="rounded-[2rem] border border-slate-200 bg-white p-4 shadow-sm">
            <h4 className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">Atalhos uteis</h4>
            <div className="mt-3 space-y-2">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() =>
                    dispatch({
                      type: 'updateDraft',
                      sessionId: activeSession.id,
                      value: prompt,
                    })
                  }
                  className="w-full rounded-[1.35rem] border border-slate-200 bg-slate-50 px-4 py-3 text-left text-xs font-bold leading-5 text-slate-600 transition-all hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <section className="overflow-hidden rounded-[2.5rem] border border-slate-200 bg-white shadow-xl shadow-slate-100">
          <div className="border-b border-slate-200 bg-slate-50/80 px-5 py-4 backdrop-blur md:px-6">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">Contexto atual</div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-white px-3 py-1 text-sm font-black text-slate-900 shadow-sm">
                    {activeSession.context.selectedChatName || 'Busca ampla'}
                  </span>
                  {activeSession.context.pendingDisambiguation && (
                    <span className="rounded-full bg-amber-100 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-amber-700">
                      confirmacao pendente
                    </span>
                  )}
                </div>
              </div>
              <div className="text-xs font-medium text-slate-500">
                {activeSession.context.lastSearchKeywords?.length
                  ? `Foco recente: ${activeSession.context.lastSearchKeywords.slice(0, 4).join(', ')}`
                  : 'Sem foco fixado ainda'}
              </div>
            </div>

            {activeSession.context.candidateChats && activeSession.context.candidateChats.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {activeSession.context.candidateChats.map((candidate) => (
                  <CandidateChip
                    key={candidate.chatId}
                    candidate={candidate}
                    isActive={candidate.chatId === activeSession.context.selectedChatId}
                    onClick={() => {
                      dispatch({
                        type: 'selectChat',
                        sessionId: activeSession.id,
                        chatId: candidate.chatId,
                        chatName: candidate.chatName,
                      });
                      showToast(`Contexto fixado em ${candidate.chatName}.`, 'info');
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          <div className="h-[520px] overflow-y-auto bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.08),_transparent_45%),linear-gradient(180deg,_rgba(248,250,252,0.95),_rgba(255,255,255,1))] px-4 py-5 md:px-6">
            <div className="space-y-4">
              {activeSession.messages.map((message) => {
                const isUser = message.role === 'user';
                return (
                  <div key={message.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[92%] rounded-[1.75rem] px-4 py-4 md:max-w-[82%] ${
                        isUser
                          ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-100'
                          : 'border border-slate-200 bg-white text-slate-700 shadow-sm'
                      }`}
                    >
                      {isUser ? (
                        <p className="whitespace-pre-wrap break-words text-sm font-medium leading-7">{message.text}</p>
                      ) : (
                        <WhatsAppAssistantMarkdown markdown={message.text} />
                      )}

                      {message.attachments && message.attachments.length > 0 && (
                        <div className="mt-4 space-y-2">
                          {message.attachments.map((attachment) => (
                            <AttachmentCard
                              key={`${message.id}_${attachment.referenceId}`}
                              attachment={attachment}
                            />
                          ))}
                        </div>
                      )}

                      <div
                        className={`mt-3 flex items-center justify-between gap-3 text-[10px] font-black uppercase tracking-[0.18em] ${
                          isUser ? 'text-blue-100/80' : 'text-slate-300'
                        }`}
                      >
                        <span>{isUser ? 'Voce' : 'Hermes'}</span>
                        <span>{formatMessageTime(message.timestamp)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}

              {activeSession.status === 'loading' && (
                <div className="flex justify-start">
                  <TypingIndicator />
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="border-t border-slate-200 bg-white px-4 py-4 md:px-6">
            {activeSession.lastError && (
              <div className="mb-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
                {activeSession.lastError}
              </div>
            )}

            <div className="rounded-[1.9rem] border border-slate-200 bg-slate-50 p-3 shadow-inner shadow-slate-100">
              <AutoExpandingTextarea
                rows={1}
                value={activeSession.draft}
                onChange={(event) =>
                  dispatch({
                    type: 'updateDraft',
                    sessionId: activeSession.id,
                    value: event.target.value,
                  })
                }
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void handleSubmit();
                  }
                }}
                placeholder="Ex.: encontre o grupo da obra e me diga o que ficou pendente hoje"
                className="min-h-[52px] w-full bg-transparent px-3 py-2 text-sm font-medium text-slate-700 outline-none placeholder:text-slate-400"
              />

              <div className="mt-3 flex flex-col gap-3 border-t border-slate-200 pt-3 md:flex-row md:items-center md:justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-300">
                  Enter envia · Shift+Enter quebra linha
                </div>
                <button
                  type="button"
                  onClick={() => void handleSubmit()}
                  disabled={activeSession.status === 'loading' || !activeSession.draft.trim()}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white shadow-lg shadow-blue-100 transition-all hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {activeSession.status === 'loading' ? 'Consultando...' : 'Enviar'}
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 12h14m-6-6 6 6-6 6" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};
