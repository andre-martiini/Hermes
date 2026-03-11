import type { Message } from 'whatsapp-web.js';
import { saveMessageRecord, uploadMediaToStorage } from './firebase.js';
import { transcribeAudioWithGroq } from './groq.js';
import type { SupportedMessageType, WhatsAppMessageRecord } from './types.js';

const urlRegex = /(https?:\/\/[^\s]+)/gi;

const normalizeName = (name: string): string => name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

const parseMessageType = (message: Message): SupportedMessageType => {
  if (message.type === 'chat') {
    return message.body.match(urlRegex) ? 'link' : 'text';
  }
  if (message.type === 'image') {
    return 'image';
  }
  if (message.type === 'audio' || message.type === 'ptt') {
    return 'audio';
  }
  if (message.type === 'document') {
    return 'document';
  }
  if (message.type === 'video') {
    return 'video';
  }
  return 'other';
};

const extractLinks = (text: string): string[] => {
  const matches = text.match(urlRegex) ?? [];
  return Array.from(new Set(matches));
};

const safeDocId = (id: string): string => id.replace(/[\/\s]/g, '_');

export const processIncomingMessage = async (message: Message): Promise<void> => {
  if (message.fromMe) {
    return;
  }

  const chat = await message.getChat();
  const contact = await message.getContact();
  const contactName = contact.pushname || contact.name || chat.name || message.from;
  const chatName = chat.name || contactName;
  const isGroup = Boolean(chat.isGroup);
  const authorId = typeof message.author === 'string' ? message.author : undefined;
  let authorName: string | undefined;

  if (isGroup && authorId) {
    try {
      const authorContact = await message.getContact();
      authorName = authorContact.pushname || authorContact.name || authorId;
    } catch {
      authorName = authorId;
    }
  }
  const messageType = parseMessageType(message);
  const timestampIso = new Date(message.timestamp * 1000).toISOString();
  const messageId = safeDocId(message.id._serialized);

  const baseRecord: WhatsAppMessageRecord = {
    id: messageId,
    wa_message_id: message.id._serialized,
    chat_id: chat.id._serialized,
    chat_name: chatName,
    chat_name_normalized: normalizeName(chatName),
    is_group: isGroup,
    author_id: authorId,
    author_name: authorName,
    author_name_normalized: authorName ? normalizeName(authorName) : undefined,
    contact_name: contactName,
    contact_name_normalized: normalizeName(contactName),
    contact_id: contact.id._serialized,
    from: message.from,
    timestamp: timestampIso,
    message_type: messageType,
    content: message.body ?? '',
    links: extractLinks(message.body ?? ''),
    created_at: new Date().toISOString(),
  };

  if (!message.hasMedia) {
    await saveMessageRecord(baseRecord);
    return;
  }

  const media = await message.downloadMedia();
  if (!media) {
    await saveMessageRecord(baseRecord);
    return;
  }

  const payload = Buffer.from(media.data, 'base64');
  const extension = media.mimetype.split('/')[1] ?? 'bin';
  const fileName = media.filename || `${messageId}.${extension}`;

  const storedMedia = await uploadMediaToStorage(messageId, fileName, media.mimetype, payload);
  const enrichedRecord: WhatsAppMessageRecord = {
    ...baseRecord,
    media: storedMedia,
  };

  if (messageType === 'audio') {
    const transcription = await transcribeAudioWithGroq(payload, fileName, media.mimetype);
    enrichedRecord.transcription_text = transcription;
    enrichedRecord.transcription_model = 'whisper-large-v3-turbo';
    if (!enrichedRecord.content) {
      enrichedRecord.content = transcription;
    }
  }

  await saveMessageRecord(enrichedRecord);
};
