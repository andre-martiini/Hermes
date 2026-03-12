import type {
  AssistantConversationMessage,
  WhatsAppAttachmentRef,
  WhatsAppAssistantContext,
  WhatsAppAssistantResponse,
} from '@/utils/whatsappAssistant';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
  attachments?: WhatsAppAttachmentRef[];
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  draft: string;
  status: 'idle' | 'loading';
  lastError?: string;
  context: WhatsAppAssistantContext;
  messages: ChatMessage[];
}

export interface WhatsAppAssistantState {
  sessions: ChatSession[];
  activeSessionId: string;
}

export type WhatsAppAssistantAction =
  | { type: 'hydrate'; sessions: ChatSession[] }
  | { type: 'createSession'; now?: string }
  | { type: 'setActiveSession'; sessionId: string }
  | { type: 'selectChat'; sessionId: string; chatId: string; chatName: string }
  | { type: 'updateDraft'; sessionId: string; value: string }
  | { type: 'submitPrompt'; sessionId: string; text: string; now?: string; messageId?: string }
  | { type: 'resolvePrompt'; sessionId: string; response: WhatsAppAssistantResponse; now?: string; messageId?: string }
  | { type: 'rejectPrompt'; sessionId: string; error: string }
  | { type: 'clearContext'; sessionId: string };

export const STORAGE_KEY = 'hermes_whatsapp_assistant_sessions_v2';

const DEFAULT_TITLE = 'Nova conversa';
const DEFAULT_WELCOME_MESSAGE =
  'Oi. Posso localizar mensagens, anexos e contexto de grupos do WhatsApp sem perder o fio da conversa. Diga o grupo, assunto ou periodo que voce quer consultar.';
const MAX_PERSISTED_SESSIONS = 12;
const MAX_PERSISTED_MESSAGES = 80;
const MAX_HISTORY_MESSAGES = 14;

const hasOwn = <T extends object>(value: T, key: PropertyKey): boolean =>
  Object.prototype.hasOwnProperty.call(value, key);

const buildId = (prefix: string, now: string): string => {
  const compactNow = now.replace(/[^0-9]/g, '').slice(0, 14);
  const random = Math.random().toString(36).slice(2, 8);
  return `${prefix}_${compactNow}_${random}`;
};

const trimText = (value: string, maxLength = 96): string => {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }

  return `${normalized.slice(0, maxLength - 1).trimEnd()}…`;
};

const normalizeContext = (
  previous: WhatsAppAssistantContext = {},
  next: WhatsAppAssistantContext = {},
): WhatsAppAssistantContext => {
  const merged: WhatsAppAssistantContext = { ...previous };

  if (hasOwn(next, 'selectedChatId')) {
    if (next.selectedChatId) {
      merged.selectedChatId = next.selectedChatId;
    } else {
      delete merged.selectedChatId;
    }
  }

  if (hasOwn(next, 'selectedChatName')) {
    if (next.selectedChatName) {
      merged.selectedChatName = next.selectedChatName;
    } else {
      delete merged.selectedChatName;
    }
  }

  if (hasOwn(next, 'candidateChats')) {
    merged.candidateChats = Array.isArray(next.candidateChats) ? next.candidateChats.slice(0, 6) : [];
  }

  if (hasOwn(next, 'memorySummary')) {
    if (next.memorySummary) {
      merged.memorySummary = trimText(next.memorySummary, 280);
    } else {
      delete merged.memorySummary;
    }
  }

  if (hasOwn(next, 'lastSearchKeywords')) {
    merged.lastSearchKeywords = Array.isArray(next.lastSearchKeywords)
      ? next.lastSearchKeywords.filter(Boolean).slice(0, 8)
      : [];
  }

  if (hasOwn(next, 'lastMessageIds')) {
    merged.lastMessageIds = Array.isArray(next.lastMessageIds) ? next.lastMessageIds.slice(0, 24) : [];
  }

  if (hasOwn(next, 'searchScopeLabel')) {
    if (next.searchScopeLabel) {
      merged.searchScopeLabel = next.searchScopeLabel;
    } else {
      delete merged.searchScopeLabel;
    }
  }

  if (hasOwn(next, 'resultCount')) {
    if (typeof next.resultCount === 'number' && Number.isFinite(next.resultCount)) {
      merged.resultCount = next.resultCount;
    } else {
      delete merged.resultCount;
    }
  }

  if (hasOwn(next, 'pendingDisambiguation')) {
    merged.pendingDisambiguation = Boolean(next.pendingDisambiguation);
  }

  return merged;
};

const moveSessionToFront = (sessions: ChatSession[], updatedSession: ChatSession): ChatSession[] => [
  updatedSession,
  ...sessions.filter((session) => session.id !== updatedSession.id),
];

const updateSession = (
  state: WhatsAppAssistantState,
  sessionId: string,
  updater: (session: ChatSession) => ChatSession,
): WhatsAppAssistantState => {
  const session = state.sessions.find((item) => item.id === sessionId);
  if (!session) {
    return state;
  }

  const updatedSession = updater(session);
  return {
    ...state,
    activeSessionId: state.activeSessionId,
    sessions: moveSessionToFront(state.sessions, updatedSession),
  };
};

export const createAssistantSession = (now = new Date().toISOString()): ChatSession => ({
  id: buildId('chat', now),
  title: DEFAULT_TITLE,
  createdAt: now,
  updatedAt: now,
  draft: '',
  status: 'idle',
  context: {},
  messages: [
    {
      id: buildId('msg', now),
      role: 'assistant',
      text: DEFAULT_WELCOME_MESSAGE,
      timestamp: now,
    },
  ],
});

export const createInitialAssistantState = (): WhatsAppAssistantState => {
  const session = createAssistantSession();
  return {
    sessions: [session],
    activeSessionId: session.id,
  };
};

const sanitizeMessage = (value: unknown): ChatMessage | null => {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const message = value as Partial<ChatMessage>;
  if ((message.role !== 'user' && message.role !== 'assistant') || typeof message.text !== 'string') {
    return null;
  }

  const timestamp =
    typeof message.timestamp === 'string' && message.timestamp.trim()
      ? message.timestamp
      : new Date().toISOString();

  return {
    id: typeof message.id === 'string' && message.id.trim() ? message.id : buildId('msg', timestamp),
    role: message.role,
    text: message.text,
    timestamp,
    attachments: Array.isArray(message.attachments) ? message.attachments.slice(0, 8) : undefined,
  };
};

const sanitizeSession = (value: unknown): ChatSession | null => {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const session = value as Partial<ChatSession>;
  const sanitizedMessages = Array.isArray(session.messages)
    ? session.messages.map(sanitizeMessage).filter((message): message is ChatMessage => Boolean(message))
    : [];

  const fallbackNow = new Date().toISOString();
  const createdAt =
    typeof session.createdAt === 'string' && session.createdAt.trim() ? session.createdAt : fallbackNow;
  const updatedAt =
    typeof session.updatedAt === 'string' && session.updatedAt.trim() ? session.updatedAt : createdAt;

  return {
    id: typeof session.id === 'string' && session.id.trim() ? session.id : buildId('chat', createdAt),
    title: typeof session.title === 'string' && session.title.trim() ? session.title : DEFAULT_TITLE,
    createdAt,
    updatedAt,
    draft: typeof session.draft === 'string' ? session.draft : '',
    status: session.status === 'loading' ? 'loading' : 'idle',
    lastError: typeof session.lastError === 'string' ? session.lastError : undefined,
    context: normalizeContext({}, session.context ?? {}),
    messages: sanitizedMessages.length > 0 ? sanitizedMessages : createAssistantSession(createdAt).messages,
  };
};

export const parseStoredAssistantSessions = (raw: string | null): ChatSession[] => {
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed
      .map(sanitizeSession)
      .filter((session): session is ChatSession => Boolean(session))
      .slice(0, MAX_PERSISTED_SESSIONS);
  } catch {
    return [];
  }
};

export const prepareSessionsForStorage = (sessions: ChatSession[]): ChatSession[] =>
  sessions.slice(0, MAX_PERSISTED_SESSIONS).map((session) => ({
    ...session,
    status: 'idle',
    lastError: undefined,
    draft: session.draft.slice(0, 4000),
    messages: session.messages.slice(-MAX_PERSISTED_MESSAGES),
    context: normalizeContext({}, session.context),
  }));

export const getActiveAssistantSession = (state: WhatsAppAssistantState): ChatSession =>
  state.sessions.find((session) => session.id === state.activeSessionId) ?? state.sessions[0];

export const getSessionPreview = (session: ChatSession): string => {
  const recentMessage = [...session.messages].reverse().find((message) => Boolean(message.text.trim()));
  return recentMessage ? trimText(recentMessage.text, 72) : 'Sem atividade recente';
};

export const toConversationHistory = (messages: ChatMessage[]): AssistantConversationMessage[] =>
  messages
    .slice(-MAX_HISTORY_MESSAGES)
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .map((message) => ({ role: message.role, text: message.text }));

export const whatsappAssistantReducer = (
  state: WhatsAppAssistantState,
  action: WhatsAppAssistantAction,
): WhatsAppAssistantState => {
  switch (action.type) {
    case 'hydrate': {
      if (!action.sessions.length) {
        return createInitialAssistantState();
      }

      return {
        sessions: action.sessions,
        activeSessionId: action.sessions[0].id,
      };
    }

    case 'createSession': {
      const newSession = createAssistantSession(action.now);
      return {
        sessions: [newSession, ...state.sessions].slice(0, MAX_PERSISTED_SESSIONS),
        activeSessionId: newSession.id,
      };
    }

    case 'setActiveSession': {
      if (!state.sessions.some((session) => session.id === action.sessionId)) {
        return state;
      }

      return {
        ...state,
        activeSessionId: action.sessionId,
      };
    }

    case 'selectChat':
      return updateSession(state, action.sessionId, (session) => ({
        ...session,
        context: normalizeContext(session.context, {
          selectedChatId: action.chatId,
          selectedChatName: action.chatName,
          pendingDisambiguation: false,
        }),
      }));

    case 'updateDraft':
      return updateSession(state, action.sessionId, (session) => ({
        ...session,
        draft: action.value,
      }));

    case 'submitPrompt': {
      const now = action.now ?? new Date().toISOString();
      const text = action.text.trim();
      if (!text) {
        return state;
      }

      return updateSession(state, action.sessionId, (session) => ({
        ...session,
        status: 'loading',
        lastError: undefined,
        draft: '',
        updatedAt: now,
        title: session.title === DEFAULT_TITLE ? trimText(text, 48) : session.title,
        messages: [
          ...session.messages,
          {
            id: action.messageId ?? buildId('msg', now),
            role: 'user',
            text,
            timestamp: now,
          },
        ],
      }));
    }

    case 'resolvePrompt': {
      const now = action.now ?? new Date().toISOString();

      return updateSession(state, action.sessionId, (session) => ({
        ...session,
        status: 'idle',
        lastError: undefined,
        updatedAt: now,
        context: normalizeContext(session.context, action.response.context ?? {}),
        messages: [
          ...session.messages,
          {
            id: action.messageId ?? buildId('msg', now),
            role: 'assistant',
            text: action.response.markdown || 'Sem resposta textual do modelo.',
            timestamp: now,
            attachments: Array.isArray(action.response.attachments)
              ? action.response.attachments.slice(0, 8)
              : undefined,
          },
        ],
      }));
    }

    case 'rejectPrompt':
      return updateSession(state, action.sessionId, (session) => ({
        ...session,
        status: 'idle',
        lastError: action.error,
      }));

    case 'clearContext':
      return updateSession(state, action.sessionId, (session) => ({
        ...session,
        context: {},
      }));

    default:
      return state;
  }
};
