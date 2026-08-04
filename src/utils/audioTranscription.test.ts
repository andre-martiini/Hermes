import { describe, expect, it } from 'vitest';
import { buildRecordedAudioBlob, getAudioExtension, getMediaContentType } from './audioTranscription';

describe('audioTranscription', () => {
  it('preserva o contêiner real informado pelo MediaRecorder móvel', () => {
    const blob = new Blob(['audio'], { type: 'audio/mp4;codecs=mp4a.40.2' });
    expect(getAudioExtension(blob, '.webm')).toBe('m4a');
  });

  it('usa a extensão sugerida quando o navegador omite o MIME type', () => {
    const blob = new Blob(['audio']);
    expect(getAudioExtension(blob, '.ogg')).toBe('ogg');
    expect(getMediaContentType(blob, '.ogg')).toBe('audio/ogg');
  });

  it('não rotula WebM como M4A ao juntar os chunks', () => {
    const chunks = [new Blob(['audio'], { type: 'audio/webm;codecs=opus' })];
    const blob = buildRecordedAudioBlob(chunks);
    expect(blob.type).toBe('audio/webm;codecs=opus');
    expect(getAudioExtension(blob)).toBe('webm');
  });
});
