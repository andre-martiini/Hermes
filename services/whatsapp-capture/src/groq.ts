import { config } from './config.js';

const GROQ_TRANSCRIPTION_URL = 'https://api.groq.com/openai/v1/audio/transcriptions';

export const transcribeAudioWithGroq = async (
  audioBuffer: Buffer,
  fileName: string,
  mimeType: string,
): Promise<string> => {
  const formData = new FormData();
  const audioBlob = new Blob([audioBuffer], { type: mimeType });

  formData.append('file', audioBlob, fileName);
  formData.append('model', 'whisper-large-v3-turbo');
  formData.append('language', 'pt');
  formData.append('response_format', 'verbose_json');

  const response = await fetch(GROQ_TRANSCRIPTION_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${config.groqApiKey}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Groq transcrição falhou (${response.status}): ${body}`);
  }

  const json = (await response.json()) as { text?: string };
  return (json.text ?? '').trim();
};
