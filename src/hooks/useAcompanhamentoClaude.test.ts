import { describe, expect, it, vi } from 'vitest';

vi.mock('@/firebase', () => ({ db: {} }));

import { claudeEstaAcompanhando } from './useAcompanhamentoClaude';

describe('claudeEstaAcompanhando', () => {
  const agora = Date.parse('2026-11-01T14:00:00Z');

  it('sinal recente e ativo: acompanhando', () => {
    expect(claudeEstaAcompanhando({ ativo: true, visto_em: '2026-11-01T13:59:20Z' }, agora)).toBe(true);
  });

  it('sinal velho: o Claude parou de ler, mesmo com ativo=true', () => {
    expect(claudeEstaAcompanhando({ ativo: true, visto_em: '2026-11-01T13:58:00Z' }, agora)).toBe(false);
  });

  it('leitor encerrou (ativo=false) ou sem documento', () => {
    expect(claudeEstaAcompanhando({ ativo: false, visto_em: '2026-11-01T13:59:50Z' }, agora)).toBe(false);
    expect(claudeEstaAcompanhando(null, agora)).toBe(false);
  });

  it('aceita o Timestamp do Firestore', () => {
    expect(claudeEstaAcompanhando({ ativo: true, visto_em: { toMillis: () => agora - 10_000 } }, agora)).toBe(true);
  });
});
