type TranscriptionResponse = {
  result?: {
    raw?: string;
    refined?: string;
    text?: string;
  };
  raw?: string;
  refined?: string;
  text?: string;
};

const DEFAULT_TRANSCRIBE_ENDPOINT = '/proxy-functions/transcreverAudio';

function extensionFromMimeType(mimeType: string): string {
  if (mimeType.includes('webm')) return '.webm';
  if (mimeType.includes('ogg')) return '.ogg';
  if (mimeType.includes('mp4') || mimeType.includes('m4a')) return '.m4a';
  if (mimeType.includes('wav')) return '.wav';
  return '.webm';
}

export async function transcribeAudio(base64Audio: string, mimeType: string): Promise<string> {
  try {
    const endpoint =
      import.meta.env.VITE_TRANSCRIBE_AUDIO_ENDPOINT || DEFAULT_TRANSCRIBE_ENDPOINT;
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        data: {
          audioBase64: base64Audio,
          extension: extensionFromMimeType(mimeType),
        },
      }),
    });

    if (!response.ok) {
      throw new Error(`Backend retornou HTTP ${response.status}`);
    }

    const payload = (await response.json()) as TranscriptionResponse;
    const result = payload.result || payload;
    const text = result.refined || result.raw || result.text;
    if (!text) {
      throw new Error('Backend nao retornou texto de transcricao.');
    }
    return text;
  } catch (error) {
    console.error('Erro na transcricao via backend:', error);
    throw new Error('Falha ao processar o audio. Verifique sua conexao ou tente novamente.');
  }
}
