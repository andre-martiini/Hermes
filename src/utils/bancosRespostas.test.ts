import { describe, expect, it } from 'vitest';
import {
  conferirBanco,
  gatilhosDeTexto,
  limparCartao,
  linhasDeTexto,
} from './bancosRespostas';
import type { CartaoResposta } from './cartoesReuniao';

const cartao = (p: Partial<CartaoResposta> & { id: string }): CartaoResposta => ({
  pergunta: 'Pergunta',
  gatilhos: ['gatilho unico'],
  resposta: ['Resposta'],
  ...p,
});

describe('gatilhosDeTexto', () => {
  it('aceita vírgula e quebra de linha na mesma entrada', () => {
    expect(gatilhosDeTexto('quanto custa,\n qual o valor \n\n')).toEqual([
      'quanto custa',
      'qual o valor',
    ]);
  });
});

describe('linhasDeTexto', () => {
  it('descarta linhas em branco', () => {
    expect(linhasDeTexto('uma\n\n  duas  \n')).toEqual(['uma', 'duas']);
  });
});

describe('conferirBanco', () => {
  it('não reclama de banco íntegro', () => {
    expect(conferirBanco([cartao({ id: 'a' }), cartao({ id: 'b', gatilhos: ['outro'] })])).toEqual([]);
  });

  it('acusa cartão sem pergunta, sem gatilho e sem resposta', () => {
    const problemas = conferirBanco([
      cartao({ id: 'a', pergunta: '   ', gatilhos: [], resposta: [] }),
    ]);
    expect(problemas.map((p) => p.campo).sort()).toEqual(['gatilhos', 'pergunta', 'resposta']);
  });

  it('acusa gatilho repetido entre cartões diferentes', () => {
    const problemas = conferirBanco([
      cartao({ id: 'a', gatilhos: ['quanto custa'] }),
      cartao({ id: 'b', gatilhos: ['Quanto Custa?'] }),
    ]);
    expect(problemas).toHaveLength(1);
    expect(problemas[0]?.campo).toBe('gatilho-repetido');
    expect(problemas[0]?.cartaoId).toBe('b');
  });

  it('não acusa repetição do gatilho dentro do mesmo cartão', () => {
    expect(conferirBanco([cartao({ id: 'a', gatilhos: ['custa', 'custa'] })])).toEqual([]);
  });
});

describe('limparCartao', () => {
  it('tira espaços, vazios e campos opcionais ausentes', () => {
    const limpo = limparCartao({
      id: 'a',
      pergunta: '  Quanto custa?  ',
      gatilhos: [' quanto custa ', '', '  '],
      resposta: [' R$ 210 mil ', ''],
      numeros: ['   '],
      naoDizer: '   ',
    });
    expect(limpo).toEqual({
      id: 'a',
      pergunta: 'Quanto custa?',
      gatilhos: ['quanto custa'],
      resposta: ['R$ 210 mil'],
    });
    expect('numeros' in limpo).toBe(false);
    expect('naoDizer' in limpo).toBe(false);
  });

  it('mantém números e não-dizer quando existem', () => {
    const limpo = limparCartao({
      id: 'a',
      pergunta: 'p',
      gatilhos: ['g'],
      resposta: ['r'],
      numeros: [' R$ 1,00 '],
      naoDizer: ' cuidado ',
    });
    expect(limpo.numeros).toEqual(['R$ 1,00']);
    expect(limpo.naoDizer).toBe('cuidado');
  });
});
