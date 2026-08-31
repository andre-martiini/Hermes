import { describe, expect, it } from 'vitest';
import {
  interpretarDesdobramento,
  montarPromptDesdobramento,
  transcricaoParaDesdobramento,
} from './desdobramentoReuniao';

const json = (obj: unknown) => JSON.stringify(obj);

describe('interpretarDesdobramento', () => {
  it('lê decisões e ações completas', () => {
    const r = interpretarDesdobramento(
      json({
        decisoes: [{ texto: 'Adiar o piloto', trecho: 'vamos adiar o piloto para outubro' }],
        acoes: [
          {
            titulo: 'Enviar a minuta ao jurídico',
            responsavel: 'André',
            prazo: '2026-09-05',
            minha: true,
            trecho: 'eu mando a minuta pro jurídico até sexta',
          },
        ],
      }),
    );
    expect(r.decisoes).toHaveLength(1);
    expect(r.acoes[0]?.prazo).toBe('2026-09-05');
    expect(r.acoes[0]?.minha).toBe(true);
    expect(r.recusados).toEqual([]);
  });

  it('RECUSA item sem trecho literal, em vez de aceitar', () => {
    const r = interpretarDesdobramento(
      json({
        decisoes: [{ texto: 'Algo que ninguém disse' }],
        acoes: [{ titulo: 'Tarefa inventada', minha: true }],
      }),
    );
    expect(r.decisoes).toEqual([]);
    expect(r.acoes).toEqual([]);
    expect(r.recusados).toHaveLength(2);
    expect(r.recusados[0]?.motivo).toContain('sem trecho literal');
  });

  it('aceita a ação mas descarta prazo que não é data, avisando', () => {
    const r = interpretarDesdobramento(
      json({ acoes: [{ titulo: 'T', minha: true, trecho: 'x', prazo: 'semana que vem' }] }),
    );
    expect(r.acoes).toHaveLength(1);
    expect(r.acoes[0]?.prazo).toBeUndefined();
    expect(r.recusados[0]?.motivo).toContain('não é uma data');
  });

  it('trata minha como verdadeiro por omissão e falso quando explícito', () => {
    const r = interpretarDesdobramento(
      json({
        acoes: [
          { titulo: 'A', trecho: 'x' },
          { titulo: 'B', trecho: 'y', minha: false },
        ],
      }),
    );
    expect(r.acoes[0]?.minha).toBe(true);
    expect(r.acoes[1]?.minha).toBe(false);
  });

  it('desembrulha JSON vindo em cerca de código', () => {
    const r = interpretarDesdobramento('```json\n{"decisoes":[{"texto":"D","trecho":"t"}]}\n```');
    expect(r.decisoes).toHaveLength(1);
  });

  it('reunião sem desdobramento é resultado legítimo, não erro', () => {
    const r = interpretarDesdobramento(json({ decisoes: [], acoes: [] }));
    expect(r).toEqual({ decisoes: [], acoes: [], recusados: [] });
  });

  it('avisa quando a resposta não é JSON', () => {
    expect(interpretarDesdobramento('não consegui').recusados[0]?.motivo).toContain('não veio em JSON');
  });

  it('não quebra com campos ausentes ou nulos', () => {
    expect(interpretarDesdobramento('{}')).toEqual({ decisoes: [], acoes: [], recusados: [] });
  });
});

describe('montarPromptDesdobramento', () => {
  it('leva a transcrição e o título, e proíbe inventar', () => {
    const p = montarPromptDesdobramento('Reunião X', 'Você: oi');
    expect(p).toContain('Reunião X');
    expect(p).toContain('Você: oi');
    expect(p).toContain('NÃO INVENTE');
  });
});

describe('transcricaoParaDesdobramento', () => {
  it('junta as falas identificando quem falou', () => {
    expect(
      transcricaoParaDesdobramento([
        { speaker: 'Você', text: 'oi' },
        { speaker: 'Reunião', text: 'olá' },
      ]),
    ).toBe('Você: oi\nReunião: olá');
  });
});
