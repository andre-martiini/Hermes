export type SupportedMessageType = 'text' | 'link' | 'audio' | 'image' | 'document' | 'video' | 'other';

export interface StoredMedia {
  path: string;
  url: string;
  mimeType: string;
  fileName: string;
  sizeBytes: number;
}

export interface WhatsAppMessageRecord {
  id: string;
  wa_message_id: string;
  chat_id: string;
  chat_name: string;
  chat_name_normalized: string;
  is_group: boolean;
  author_id?: string;
  author_name?: string;
  author_name_normalized?: string;
  contact_name: string;
  contact_name_normalized: string;
  contact_id: string;
  from: string;
  timestamp: string;
  message_type: SupportedMessageType;
  content: string;
  links: string[];
  media?: StoredMedia;
  transcription_text?: string;
  transcription_model?: string;
  created_at: string;
}
