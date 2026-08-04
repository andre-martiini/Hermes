import { httpsCallable } from 'firebase/functions';
import { ref, uploadBytesResumable } from 'firebase/storage';
import { auth, functions, storage } from '@/firebase';

export interface AudioTranscriptionResult {
  raw: string;
  refined: string;
}

const MIME_EXTENSION_MAP: Record<string, string> = {
  'audio/aac': 'aac',
  'audio/flac': 'flac',
  'audio/mp4': 'm4a',
  'audio/m4a': 'm4a',
  'audio/x-m4a': 'm4a',
  'audio/mpeg': 'mp3',
  'audio/mp3': 'mp3',
  'audio/ogg': 'ogg',
  'audio/opus': 'opus',
  'audio/wav': 'wav',
  'audio/webm': 'webm',
  'video/mp4': 'mp4',
  'video/webm': 'webm',
};

const EXTENSION_MIME_MAP: Record<string, string> = {
  aac: 'audio/aac',
  aif: 'audio/aiff',
  aiff: 'audio/aiff',
  amr: 'audio/amr',
  caf: 'audio/x-caf',
  flac: 'audio/flac',
  m4a: 'audio/mp4',
  mp3: 'audio/mpeg',
  oga: 'audio/ogg',
  ogg: 'audio/ogg',
  opus: 'audio/opus',
  wav: 'audio/wav',
  webm: 'audio/webm',
  mp4: 'video/mp4',
  mov: 'video/quicktime',
  mpeg: 'video/mpeg',
  mpg: 'video/mpeg',
  '3gp': 'video/3gpp',
  '3gpp': 'video/3gpp',
};

const normalizeExtension = (extension?: string): string | null => {
  const clean = (extension || '').trim().toLowerCase().replace(/^\./, '').replace(/[^a-z0-9]/g, '');
  return clean || null;
};

export const getAudioExtension = (blob: Blob, extensionHint?: string): string => {
  const mime = (blob.type || '').toLowerCase().split(';', 1)[0].trim();
  return MIME_EXTENSION_MAP[mime] || normalizeExtension(extensionHint) || 'webm';
};

export const getMediaContentType = (blob: Blob, extensionHint?: string): string => {
  const declaredType = (blob.type || '').trim();
  if (/^(audio|video)\//i.test(declaredType)) return declaredType;
  return EXTENSION_MIME_MAP[getAudioExtension(blob, extensionHint)] || 'audio/webm';
};

export const buildRecordedAudioBlob = (chunks: Blob[], recorder?: MediaRecorder | null): Blob => {
  const mimeType = recorder?.mimeType || chunks.find((chunk) => chunk.type)?.type || 'audio/webm';
  return new Blob(chunks, { type: mimeType });
};

/**
 * Envia o áudio diretamente ao Storage antes de chamar o backend. Assim o corpo
 * da callable contém apenas um caminho curto e não cresce 4/3 por causa de Base64.
 */
export const transcribeAudioViaStorage = async (
  blob: Blob,
  extensionHint?: string,
): Promise<AudioTranscriptionResult> => {
  const uid = auth.currentUser?.uid;
  if (!uid) throw new Error('Você precisa estar autenticado para transcrever.');
  if (!blob.size) throw new Error('A gravação de áudio está vazia.');

  const extension = getAudioExtension(blob, extensionHint);
  const uniqueId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const storagePath = `quick_transcriptions/${uid}/${uniqueId}.${extension}`;

  await new Promise<void>((resolve, reject) => {
    const upload = uploadBytesResumable(ref(storage, storagePath), blob, {
      contentType: getMediaContentType(blob, extension),
    });
    upload.on('state_changed', undefined, reject, resolve);
  });

  const transcribe = httpsCallable(functions, 'transcreverAudio');
  const response = await transcribe({ storagePath, extension: `.${extension}` });
  return response.data as AudioTranscriptionResult;
};
