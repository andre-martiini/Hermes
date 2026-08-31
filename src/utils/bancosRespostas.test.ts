import { describe, expect, it } from 'vitest';
import {
  conferirBanco,
  exportarCartoesParaJson,
  gatilhosDeTexto,
  importarCartoesDeJson,
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

describe('importarCartoesDeJson', () => {
  it('aceita lista direta e objeto com a chave cartoes', () => {
    const item = { pergunta: 'P', gatilhos: ['g'], resposta: ['r'] };
    expect(importarCartoesDeJson(JSON.stringify([item])).cartoes).toHaveLength(1);
    expect(importarCartoesDeJson(JSON.stringify({ cartoes: [item] })).cartoes).toHaveLength(1);
  });

  it('tolera gatilhos e resposta como texto em vez de lista', () => {
    const { cartoes } = importarCartoesDeJson(
      JSON.stringify([{ pergunta: 'P', gatilhos: 'um, dois', resposta: 'linha um\nlinha dois' }]),
    );
    expect(cartoes[0]?.gatilhos).toEqual(['um', 'dois']);
    expect(cartoes[0]?.resposta).toEqual(['linha um', 'linha dois']);
  });

  it('gera id quando a IA não manda um', () => {
    const { cartoes } = importarCartoesDeJson(
      JSON.stringify([{ pergunta: 'P', gatilhos: ['g'], resposta: ['r'] }]),
    );
    expect(cartoes[0]?.id).toBeTruthy();
  });

  it('recusa cartão incompleto dizendo o que faltou, e não engole em silêncio', () => {
    const { cartoes, recusados } = importarCartoesDeJson(
      JSON.stringify([
        { pergunta: 'ok', gatilhos: ['g'], resposta: ['r'] },
        { pergunta: '', gatilhos: [], resposta: ['r'] },
      ]),
    );
    expect(cartoes).toHaveLength(1);
    expect(recusados).toHaveLength(1);
    expect(recusados[0]?.posicao).toBe(2);
    expect(recusados[0]?.motivo).toContain('pergunta');
    expect(recusados[0]?.motivo).toContain('gatilhos');
  });

  it('avisa quando o texto não é JSON', () => {
    const { cartoes, recusados } = importarCartoesDeJson('isto não é json');
    expect(cartoes).toEqual([]);
    expect(recusados[0]?.motivo).toContain('não é um JSON válido');
  });

  it('avisa quando o JSON é válido mas não tem lista de cartões', () => {
    expect(importarCartoesDeJson('{"algo":1}').recusados[0]?.motivo).toContain('lista de cartões');
  });

  it('mantém números e naoDizer quando vierem', () => {
    const { cartoes } = importarCartoesDeJson(
      JSON.stringify([
        { pergunta: 'P', gatilhos: ['g'], resposta: ['r'], numeros: ['R$ 1'], naoDizer: 'cuidado' },
      ]),
    );
    expect(cartoes[0]?.numeros).toEqual(['R$ 1']);
    expect(cartoes[0]?.naoDizer).toBe('cuidado');
  });
});

describe('exportarCartoesParaJson', () => {
  it('exporta o que a importação consegue ler de volta', () => {
    const original = [{ id: 'a', pergunta: 'P', gatilhos: ['g'], resposta: ['r'] }];
    const json = exportarCartoesParaJson(original);
    expect(importarCartoesDeJson(json).cartoes).toEqual(original);
  });
});
