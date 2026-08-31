import { describe, expect, it } from 'vitest';
import {
  casarCartoes,
  filtrarRecentes,
  normalizar,
  pontuarGatilho,
  type CartaoResposta,
} from './cartoesReuniao';

const cartoes: CartaoResposta[] = [
  {
    id: 'suap',
    pergunta: 'Como isso se relaciona com o SUAP?',
    gatilhos: ['suap', 'relacao com o suap', 'por que nao dentro do suap'],
    resposta: ['Sao camadas diferentes.'],
  },
  {
    id: 'custo',
    pergunta: 'Quanto custa?',
    gatilhos: ['quanto custa', 'qual o custo', 'valor por instituicao'],
    resposta: ['R$ 210.220,00 por ano.'],
  },
  {
    id: 'lgpd',
    pergunta: 'E os dados? LGPD?',
    gatilhos: ['lgpd', 'protecao de dados'],
    resposta: ['Isolamento por organizacao.'],
  },
];

describe('normalizar', () => {
  it('tira acento, pontuacao e caixa', () => {
    expect(normalizar('Relação com o SUAP?')).toBe('relacao com o suap');
  });
});

describe('pontuarGatilho', () => {
  it('casa trecho contínuo com nota máxima', () => {
    expect(pontuarGatilho(normalizar('me diz quanto custa isso ai'), 'quanto custa')).toBe(1);
  });

  it('casa palavras fora de ordem proporcionalmente', () => {
    const score = pontuarGatilho(normalizar('qual seria o custo disso'), 'qual o custo');
    expect(score).toBeGreaterThanOrEqual(0.5);
  });

  it('gatilho de palavra única exige a palavra literal', () => {
    expect(pontuarGatilho(normalizar('e o suap nisso tudo'), 'suap')).toBe(1);
    expect(pontuarGatilho(normalizar('e o sistema nisso tudo'), 'suap')).toBe(0);
  });
});

describe('casarCartoes', () => {
  it('sobe o cartão certo quando a pergunta aparece', () => {
    const casados = casarCartoes('André, e como isso se relaciona com o SUAP?', cartoes);
    expect(casados[0]?.cartao.id).toBe('suap');
  });

  it('não sobe nada quando a fala não convoca cartão', () => {
    expect(casarCartoes('bom dia pessoal, todos conseguem me ouvir', cartoes)).toEqual([]);
  });

  it('respeita o máximo de cartões visíveis', () => {
    const fala = 'quanto custa o suap e a lgpd';
    expect(casarCartoes(fala, cartoes, { maximo: 2 }).length).toBeLessThanOrEqual(2);
  });

  it('ordena pelo melhor casamento', () => {
    const casados = casarCartoes('quanto custa isso, e o suap?', cartoes);
    expect(casados.map((c) => c.cartao.id)).toContain('custo');
    expect(casados.map((c) => c.cartao.id)).toContain('suap');
  });
});

describe('filtrarRecentes', () => {
  it('segura cartão que subiu há menos de cinco minutos', () => {
    const casados = casarCartoes('quanto custa', cartoes);
    const agora = 1_000_000;
    const exibidos = new Map([['custo', agora - 60_000]]);
    expect(filtrarRecentes(casados, exibidos, agora)).toEqual([]);
  });

  it('libera de novo depois da janela', () => {
    const casados = casarCartoes('quanto custa', cartoes);
    const agora = 1_000_000;
    const exibidos = new Map([['custo', agora - 6 * 60 * 1000]]);
    expect(filtrarRecentes(casados, exibidos, agora)).toHaveLength(1);
  });
});
