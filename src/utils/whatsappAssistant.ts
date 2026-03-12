import { httpsCallable } from 'firebase/functions';
import { functions } from '@/firebase';

export interface WhatsAppAttachmentRef {
  referenceId: string;
  messageId: string;
  fileName: string;
  mimeType: string;
  url: string;
  contactName: string;
  timestamp: string;
}

export interface WhatsAppAssistantContext {
  selectedChatId?: string;
  selectedChatName?: string;
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

export const askWhatsAppAssistant = async (
  command: string,
  context: WhatsAppAssistantContext = {},
  conversationHistory: AssistantConversationMessage[] = [],
): Promise<WhatsAppAssistantResponse> => {
  const fn = httpsCallable(functions, 'askWhatsAppAssistantSecure');
  const response = await fn({
    command,
    context,
    conversationHistory,
  });

  const data = response.data as WhatsAppAssistantResponse;
  return {
    markdown: data.markdown || '',
    attachments: Array.isArray(data.attachments) ? data.attachments : [],
    context: data.context || {},
  };
};
