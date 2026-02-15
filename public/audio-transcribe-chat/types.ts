
export enum SenderType {
  USER = 'user',
  SYSTEM = 'system'
}

export interface Message {
  id: string;
  sender: SenderType;
  content: string;
  timestamp: Date;
  audioUrl?: string;
  isTranscribing?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: Date;
}

export interface TranscriptionResponse {
  text: string;
  error?: string;
}
