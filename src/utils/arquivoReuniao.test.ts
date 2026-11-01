import { describe, expect, it } from 'vitest';
import { montarTextoReuniao, nomeArquivoReuniao } from './arquivoReuniao';

describe('nomeArquivoReuniao', () => {
  const inicio = new Date(2026, 10, 1, 14, 5);

  it('sem título mantém o nome de sempre', () => {
    expect(nomeArquivoReuniao(inicio)).toBe('Reuniao_2026-11-01_14-05.txt');
  });

  it('com título acrescenta o título sem caracteres que o Drive recusa', () => {
    expect(nomeArquivoReuniao(inicio, 'Alinhamento: PROAD / e-PROAD?')).toBe('Reuniao_2026-11-01_14-05 - Alinhamento PROAD e-PROAD.txt');
  });
});

describe('montarTextoReuniao', () => {
  it('põe título, consentimento e falas na ordem', () => {
    const t = new Date(2026, 10, 1, 14, 5, 10);
    const texto = montarTextoReuniao(t, t, [{ speaker: 'Reunião', text: 'qual o prazo?', timestamp: t }], 'Aviso de Privacidade: X', [], 'Reunião PROAD');
    const linhas = texto.split('\n');
    expect(linhas[0]).toBe('TRANSCRIÇÃO DE REUNIÃO');
    expect(linhas[1]).toBe('Reunião PROAD');
    expect(texto).toContain('Aviso de Privacidade: X');
    expect(texto).toMatch(/\] Reunião: qual o prazo\?/);
  });

  it('sem falas avisa em vez de deixar vazio', () => {
    const t = new Date();
    expect(montarTextoReuniao(t, t, [], 'c')).toContain('(Sem falas transcritas)');
  });
});
