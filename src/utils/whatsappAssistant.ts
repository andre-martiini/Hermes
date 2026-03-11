import { GoogleGenerativeAI, type FunctionDeclaration } from '@google/generative-ai';
import { collection, doc, getDoc, getDocs, limit, orderBy, query } from 'firebase/firestore';
import { db } from '@/firebase';

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

interface QueryWhatsAppMessagesArgs {
  contact_name?: string;
  chat_name?: string;
  chat_id?: string;
  start_iso?: string;
  end_iso?: string;
  keywords?: string[];
  intent?: string;
  max_results?: number;
  use_session_chat?: boolean;
  user_query?: string;
}

interface WhatsAppMessageDoc {
  id: string;
  chat_id?: string;
  chat_name?: string;
  chat_name_normalized?: string;
  is_group?: boolean;
  author_name?: string;
  author_name_normalized?: string;
  contact_name: string;
  contact_name_normalized?: string;
  timestamp: string;
  message_type: string;
  content: string;
  links?: string[];
  transcription_text?: string;
  media?: {
    url?: string;
    fileName?: string;
    mimeType?: string;
  };
}

interface ChatCandidate {
  chatId: string;
  chatName: string;
  isGroup: boolean;
  score: number;
}

const normalizeText = (value: string): string =>
  value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const tokens = (value: string): string[] => normalizeText(value).split(' ').filter(Boolean);

const fuzzyScore = (candidate: string, queryValue: string): number => {
  const a = normalizeText(candidate);
  const b = normalizeText(queryValue);
  if (!a || !b) {
    return 0;
  }

  if (a === b) {
    return 1;
  }

  if (a.includes(b)) {
    return 0.95;
  }

  const aTokens = new Set(tokens(a));
  const bTokens = tokens(b);
  if (bTokens.length === 0) {
    return 0;
  }

  let overlap = 0;
  for (const token of bTokens) {
    if (aTokens.has(token)) {
      overlap += 1;
      continue;
    }

    for (const candidateToken of aTokens) {
      if (candidateToken.startsWith(token) || token.startsWith(candidateToken)) {
        overlap += 0.65;
        break;
      }
    }
  }

  return overlap / bTokens.length;
};

const extractChatKeywordFromText = (text: string): string | undefined => {
  const normalized = normalizeText(text);
  if (!normalized) {
    return undefined;
  }

  const match = normalized.match(/(?:grupo|chat)\s+(?:do|da|de)?\s*([a-z0-9\s]{2,})/);
  if (match?.[1]) {
    return match[1].trim();
  }

  const stopwords = new Set([
    'quais', 'qual', 'como', 'quando', 'onde', 'porque', 'pra', 'para', 'com', 'sem', 'hoje', 'amanha', 'ontem',
    'tarde', 'manha', 'noite', 'mensagem', 'mensagens', 'pedido', 'pediu', 'grupo', 'chat', 'nesse', 'nessa', 'neste',
    'naquele', 'sobre', 'dos', 'das', 'de', 'do', 'da', 'e', 'ou', 'a', 'o', 'as', 'os', 'um', 'uma',
  ]);

  const useful = tokens(normalized).filter((token) => token.length > 2 && !stopwords.has(token));
  if (useful.length === 0) {
    return undefined;
  }

  return useful.slice(0, 4).join(' ');
};

const getGeminiApiKey = async (): Promise<string> => {
  let apiKey = process.env.GEMINI_API_KEY || import.meta.env.VITE_GEMINI_API_KEY || '';

  if (!apiKey) {
    const keyDoc = await getDoc(doc(db, 'system', 'api_keys'));
    if (keyDoc.exists()) {
      apiKey = keyDoc.data()?.gemini_api_key || '';
    }
  }

  if (!apiKey) {
    throw new Error('Chave do Gemini nao configurada. Defina VITE_GEMINI_API_KEY ou system/api_keys.gemini_api_key.');
  }

  return apiKey;
};

const getRecentMessages = async (maxResults: number): Promise<WhatsAppMessageDoc[]> => {
  const messagesRef = collection(db, 'whatsapp_messages');
  const q = query(messagesRef, orderBy('timestamp', 'desc'), limit(maxResults));
  const snapshot = await getDocs(q);
  return snapshot.docs.map((docSnap) => ({ id: docSnap.id, ...(docSnap.data() as any) }));
};

const findBestChatCandidates = (messages: WhatsAppMessageDoc[], chatKeyword: string): ChatCandidate[] => {
  const byChat = new Map<string, ChatCandidate>();

  for (const item of messages) {
    const chatId = item.chat_id;
    const chatName = item.chat_name;
    if (!chatId || !chatName) {
      continue;
    }

    const score = fuzzyScore(chatName, chatKeyword);
    const existing = byChat.get(chatId);
    const next: ChatCandidate = {
      chatId,
      chatName,
      isGroup: Boolean(item.is_group),
      score,
    };

    if (!existing || existing.score < next.score) {
      byChat.set(chatId, next);
    }
  }

  return Array.from(byChat.values())
    .filter((item) => item.score >= 0.32)
    .sort((a, b) => b.score - a.score)
    .slice(0, 6);
};

const applyKeywordFilter = (items: WhatsAppMessageDoc[], keywords: string[]): WhatsAppMessageDoc[] => {
  const normalizedKeywords = keywords.map(normalizeText).filter(Boolean);
  if (normalizedKeywords.length === 0) {
    return items;
  }

  return items.filter((item) => {
    const searchable = normalizeText(
      [
        item.content,
        item.transcription_text ?? '',
        ...(item.links ?? []),
        item.author_name ?? '',
        item.contact_name ?? '',
        item.chat_name ?? '',
      ].join(' '),
    );

    return normalizedKeywords.every((keyword) => searchable.includes(keyword));
  });
};

const queryWhatsAppMessages = async (
  args: QueryWhatsAppMessagesArgs,
  context: WhatsAppAssistantContext,
  userCommand: string,
): Promise<{ items: WhatsAppMessageDoc[]; resolvedContext: WhatsAppAssistantContext; candidates: ChatCandidate[] }> => {
  const maxResults = Math.min(Math.max(args.max_results ?? 70, 10), 180);
  const recent = await getRecentMessages(600);

  let selectedChatId = args.chat_id || (args.use_session_chat === false ? undefined : context.selectedChatId);
  let selectedChatName = args.use_session_chat === false ? undefined : context.selectedChatName;
  let candidates: ChatCandidate[] = [];

  const chatNeedle = args.chat_name || extractChatKeywordFromText(args.user_query || userCommand);

  if (!selectedChatId && chatNeedle) {
    candidates = findBestChatCandidates(recent, chatNeedle);
    if (candidates.length > 0) {
      selectedChatId = candidates[0].chatId;
      selectedChatName = candidates[0].chatName;
    }
  }

  let items = recent;

  if (selectedChatId) {
    items = items.filter((item) => item.chat_id === selectedChatId);
    if (!selectedChatName) {
      selectedChatName = items[0]?.chat_name;
    }
  }

  if (args.start_iso) {
    items = items.filter((item) => item.timestamp >= args.start_iso!);
  }

  if (args.end_iso) {
    items = items.filter((item) => item.timestamp <= args.end_iso!);
  }

  if (args.contact_name) {
    const contactNeedle = normalizeText(args.contact_name);
    items = items.filter((item) => {
      const values = [item.contact_name, item.author_name, item.contact_name_normalized, item.author_name_normalized]
        .filter(Boolean)
        .map((v) => normalizeText(String(v)));

      return values.some((value) => fuzzyScore(value, contactNeedle) >= 0.62);
    });
  }

  items = applyKeywordFilter(items, args.keywords ?? []);
  items = items.slice(0, maxResults);

  return {
    items,
    resolvedContext: {
      selectedChatId,
      selectedChatName,
    },
    candidates,
  };
};

const searchMessagesDeclaration: FunctionDeclaration = {
  name: 'search_whatsapp_messages',
  description:
    'Busca mensagens do WhatsApp com tolerancia a nomes de grupo/contato aproximados. Use chat_name quando o usuario pedir para localizar um grupo.',
  parameters: {
    type: 'OBJECT',
    properties: {
      contact_name: { type: 'STRING', description: 'Nome de contato ou autor no grupo.' },
      chat_name: { type: 'STRING', description: 'Nome aproximado do grupo/chat.' },
      chat_id: { type: 'STRING', description: 'ID do chat se ja conhecido.' },
      start_iso: { type: 'STRING', description: 'Data inicial ISO-8601.' },
      end_iso: { type: 'STRING', description: 'Data final ISO-8601.' },
      keywords: { type: 'ARRAY', items: { type: 'STRING' }, description: 'Termos essenciais da busca.' },
      intent: { type: 'STRING', description: 'Intencao inferida do pedido.' },
      max_results: { type: 'NUMBER', description: 'Limite de mensagens retornadas.' },
      use_session_chat: { type: 'BOOLEAN', description: 'Se true, reaproveita o chat da conversa ativa.' },
      user_query: { type: 'STRING', description: 'Copia da pergunta original para buscas fuzzy complementares.' },
    },
  },
};

const toContextBlock = (messages: WhatsAppMessageDoc[]): { context: string; attachments: WhatsAppAttachmentRef[] } => {
  const attachments: WhatsAppAttachmentRef[] = [];

  const context = messages
    .map((message, index) => {
      const attachmentRef = message.media?.url
        ? {
            referenceId: `ARQ-${index + 1}`,
            messageId: message.id,
            fileName: message.media.fileName || `arquivo-${index + 1}`,
            mimeType: message.media.mimeType || 'application/octet-stream',
            url: message.media.url,
            contactName: message.author_name || message.contact_name,
            timestamp: message.timestamp,
          }
        : null;

      if (attachmentRef) {
        attachments.push(attachmentRef);
      }

      const mediaLine = attachmentRef
        ? `anexo_ref=${attachmentRef.referenceId} anexo_nome=${attachmentRef.fileName} anexo_url=${attachmentRef.url}`
        : 'anexo_ref=none';

      return [
        `id=${message.id}`,
        `chat=${message.chat_name || '(sem chat)'}`,
        `contato=${message.contact_name}`,
        `autor=${message.author_name || message.contact_name}`,
        `timestamp=${message.timestamp}`,
        `tipo=${message.message_type}`,
        `conteudo=${message.content || '(vazio)'}`,
        `transcricao=${message.transcription_text || '(sem transcricao)'}`,
        `links=${(message.links ?? []).join(', ') || '(sem links)'}`,
        mediaLine,
      ].join(' | ');
    })
    .join('\n');

  return { context, attachments };
};

const serializeConversation = (history: AssistantConversationMessage[]): string =>
  history
    .slice(-12)
    .map((item) => `${item.role === 'user' ? 'Usuario' : 'Assistente'}: ${item.text}`)
    .join('\n');

export const askWhatsAppAssistant = async (
  command: string,
  context: WhatsAppAssistantContext = {},
  conversationHistory: AssistantConversationMessage[] = [],
): Promise<WhatsAppAssistantResponse> => {
  const apiKey = await getGeminiApiKey();
  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({
    model: 'gemini-2.5-flash-lite',
    tools: [{ functionDeclarations: [searchMessagesDeclaration] }],
  });

  const recentConversation = serializeConversation(conversationHistory);

  const chat = model.startChat({
    history: [
      {
        role: 'user',
        parts: [
          {
            text:
              'Voce e o assistente de consulta de WhatsApp do Hermes. Sempre chame search_whatsapp_messages antes de responder. Seja tolerante a nomes aproximados e erros de digitacao. Se houver contexto de chat ativo, use-o para continuar a conversa.',
          },
          {
            text: `Contexto atual de chat: ${context.selectedChatName || 'nenhum'} (${context.selectedChatId || 'sem id'})`,
          },
          {
            text: `Conversa recente:\n${recentConversation || '(sem historico)'}`,
          },
        ],
      },
    ],
  });

  const firstPass = await chat.sendMessage(command);
  const functionCall = firstPass.response.functionCalls()?.[0];

  if (!functionCall || functionCall.name !== 'search_whatsapp_messages') {
    return { markdown: firstPass.response.text(), attachments: [], context };
  }

  const toolArgs = {
    ...(functionCall.args ?? {}),
    user_query: command,
  } as QueryWhatsAppMessagesArgs;

  const { items: messages, resolvedContext, candidates } = await queryWhatsAppMessages(toolArgs, context, command);
  const { context: messageContext, attachments } = toContextBlock(messages);

  await chat.sendMessage([
    {
      functionResponse: {
        name: functionCall.name,
        response: {
          matched_count: messages.length,
          selected_chat: resolvedContext,
          candidates,
          items: messages,
          note:
            'Se houver multiplos grupos parecidos, mostre opcoes curtas e peca confirmacao. Se um grupo foi assumido por score, informe qual foi usado.',
        },
      },
    },
  ]);

  const secondPass = await chat.sendMessage(`Contexto legivel para sintese final:\n${messageContext || '(sem resultados)'}`);

  return {
    markdown: secondPass.response.text(),
    attachments,
    context: resolvedContext,
  };
};
