// src/utils/bancosRespostas.ts
// Regras puras dos bancos de resposta: montagem, normalização e conferência.
//
// Fica separado do acesso ao Firestore de propósito — é o que dá para testar
// sem rede, e é onde mora a única regra que protege a qualidade do banco: a
// conferência de gatilhos repetidos entre cartões.

import { normalizar, type CartaoResposta } from './cartoesReuniao';

export interface BancoRespostas {
  id: string;
  nome: string;
  descricao?: string;
  cartoes: CartaoResposta[];
  criadoEm: string;
  atualizadoEm: string;
}

/** Uma linha por item, ignorando linhas em branco. É como a pessoa digita. */
export const linhasDeTexto = (valor: string): string[] =>
  valor
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);

/** Gatilhos vêm separados por vírgula ou por linha — aceitar os dois. */
export const gatilhosDeTexto = (valor: string): string[] =>
  valor
    .split(/[\n,]/)
    .map((g) => g.trim())
    .filter(Boolean);

export const idDeCartao = (): string =>
  `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;

export const cartaoVazio = (): CartaoResposta => ({
  id: idDeCartao(),
  pergunta: '',
  gatilhos: [],
  resposta: [],
});

export interface ProblemaBanco {
  cartaoId: string;
  campo: 'pergunta' | 'gatilhos' | 'resposta' | 'gatilho-repetido';
  mensagem: string;
}

/**
 * Confere o banco antes de ele valer numa reunião.
 *
 * O caso que realmente importa aqui é o GATILHO REPETIDO entre cartões
 * diferentes. Ele não quebra nada — o casador escolhe um e segue —, mas
 * escolhe em silêncio, e quem está falando recebe o cartão quase-certo sem
 * saber que existia outro. É o defeito mais caro possível num banco grande,
 * e o mais fácil de criar sem perceber.
 */
export const conferirBanco = (cartoes: readonly CartaoResposta[]): ProblemaBanco[] => {
  const problemas: ProblemaBanco[] = [];
  const donoDoGatilho = new Map<string, string>();

  for (const cartao of cartoes) {
    if (!cartao.pergunta.trim()) {
      problemas.push({
        cartaoId: cartao.id,
        campo: 'pergunta',
        mensagem: 'Cartão sem pergunta: é o título que você lê primeiro.',
      });
    }
    if (cartao.gatilhos.length === 0) {
      problemas.push({
        cartaoId: cartao.id,
        campo: 'gatilhos',
        mensagem: 'Cartão sem gatilho nunca vai subir.',
      });
    }
    if (cartao.resposta.length === 0) {
      problemas.push({
        cartaoId: cartao.id,
        campo: 'resposta',
        mensagem: 'Cartão sem resposta sobe e não ajuda.',
      });
    }

    for (const gatilho of cartao.gatilhos) {
      const chave = normalizar(gatilho);
      if (!chave) continue;
      const dono = donoDoGatilho.get(chave);
      if (dono && dono !== cartao.id) {
        problemas.push({
          cartaoId: cartao.id,
          campo: 'gatilho-repetido',
          mensagem: `O gatilho "${gatilho}" já pertence a outro cartão. Só um dos dois vai subir, e não dá para saber qual.`,
        });
      } else {
        donoDoGatilho.set(chave, cartao.id);
      }
    }
  }

  return problemas;
};

/** Remove o que o Firestore não aceita (undefined) e o que só atrapalha (espaço à toa). */
export const limparCartao = (cartao: CartaoResposta): CartaoResposta => {
  const limpo: CartaoResposta = {
    id: cartao.id,
    pergunta: cartao.pergunta.trim(),
    gatilhos: cartao.gatilhos.map((g) => g.trim()).filter(Boolean),
    resposta: cartao.resposta.map((r) => r.trim()).filter(Boolean),
  };
  const numeros = (cartao.numeros ?? []).map((n) => n.trim()).filter(Boolean);
  if (numeros.length > 0) limpo.numeros = numeros;
  const naoDizer = cartao.naoDizer?.trim();
  if (naoDizer) limpo.naoDizer = naoDizer;
  return limpo;
};
