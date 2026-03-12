import { httpsCallable } from 'firebase/functions';
import { auth, functions } from '@/firebase';

export interface WhatsAppAttachmentRef {
  referenceId: string;
  messageId: string;
  fileName: string;
  mimeType: string;
  url: string;
  contactName: string;
  timestamp: string;
}

export interface WhatsAppChatCandidate {
  chatId: string;
  chatName: string;
  isGroup: boolean;
  score: number;
}

export interface WhatsAppAssistantContext {
  selectedChatId?: string;
  selectedChatName?: string;
  candidateChats?: WhatsAppChatCandidate[];
  memorySummary?: string;
  lastSearchKeywords?: string[];
  lastMessageIds?: string[];
  searchScopeLabel?: string;
  resultCount?: number;
  pendingDisambiguation?: boolean;
}

export interface AssistantConversationMessage {
  role: 'user' | 'assistant';
  text: string;
}

export interface WhatsAppAssistantResponse {
  markdown: string;
  attachments: WhatsAppAttachmentRef[];
  context: WhatsAppAssistantContext;
}

const normalizeAssistantResponse = (payload: unknown): WhatsAppAssistantResponse => {
  const data = (payload ?? {}) as Partial<WhatsAppAssistantResponse>;
  return {
    markdown: data.markdown || '',
    attachments: Array.isArray(data.attachments) ? data.attachments : [],
    context: data.context || {},
  };
};

export const askWhatsAppAssistant = async (
  command: string,
  context: WhatsAppAssistantContext = {},
  conversationHistory: AssistantConversationMessage[] = [],
): Promise<WhatsAppAssistantResponse> => {
  const payload = {
    command,
    context,
    conversationHistory,
  };

  if (import.meta.env.DEV) {
    const currentUser = auth.currentUser;
    const idToken = currentUser ? await currentUser.getIdToken() : null;

    if (!idToken) {
      throw new Error('Usuário não autenticado para consultar o assistente WhatsApp em desenvolvimento.');
    }

    const response = await fetch('/proxy-functions/askWhatsAppAssistantSecure', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${idToken}`,
      },
      body: JSON.stringify({ data: payload }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`askWhatsAppAssistantSecure proxy falhou (${response.status}): ${errorText}`);
    }

    const json = await response.json();
    return normalizeAssistantResponse((json as { result?: unknown }).result ?? json);
  }

  const fn = httpsCallable(functions, 'askWhatsAppAssistantSecure');
  const response = await fn(payload);

  return normalizeAssistantResponse(response.data);
};
