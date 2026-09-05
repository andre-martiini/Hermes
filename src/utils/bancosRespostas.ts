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
  eventoCalendarId?: string;
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

// ── Troca com o mundo de fora: JSON ────────────────────────────────────────
//
// Enquanto a geração de cartões pelo próprio Hermes não existe, o caminho
// prático é pedir a uma IA externa e colar o resultado aqui. Para isso duas
// coisas precisam existir: um formato que ela saiba produzir e uma importação
// que não engula erro em silêncio.

export interface ResultadoImportacao {
  cartoes: CartaoResposta[];
  /** O que foi recusado e por quê. Nunca descartar em silêncio. */
  recusados: { posicao: number; motivo: string }[];
}

/**
 * Lê um campo que pode vir como lista ou como texto solto.
 *
 * `porVirgula` existe porque gatilho e resposta se quebram de formas
 * diferentes, e confundi-las estraga as duas. Gatilhos são frases curtas que
 * quem escreve enfileira com vírgula — "quanto custa, qual o valor" são DOIS.
 * Já uma resposta é frase inteira, e vírgula dentro dela é pontuação: quebrar
 * por vírgula picaria a fala em pedaços sem sentido.
 */
const comoLista = (valor: unknown, porVirgula = false): string[] => {
  if (Array.isArray(valor)) return valor.map((v) => String(v).trim()).filter(Boolean);
  if (typeof valor === 'string') return porVirgula ? gatilhosDeTexto(valor) : linhasDeTexto(valor);
  return [];
};

/**
 * Lê cartões de um JSON colado.
 *
 * Deliberadamente TOLERANTE na forma e EXIGENTE no conteúdo: uma IA externa
 * entrega ora um array, ora um objeto com `cartoes`, ora gatilhos como texto
 * separado por vírgula. Nada disso é erro de quem colou. Já cartão sem
 * pergunta, sem gatilho ou sem resposta é recusado com o motivo à vista —
 * importar pela metade e não avisar seria pior do que não importar.
 */
export const importarCartoesDeJson = (texto: string): ResultadoImportacao => {
  let cru: unknown;
  try {
    cru = JSON.parse(texto);
  } catch {
    return { cartoes: [], recusados: [{ posicao: 0, motivo: 'O texto não é um JSON válido.' }] };
  }

  const lista = Array.isArray(cru)
    ? cru
    : Array.isArray((cru as { cartoes?: unknown })?.cartoes)
      ? ((cru as { cartoes: unknown[] }).cartoes)
      : null;

  if (!lista) {
    return {
      cartoes: [],
      recusados: [{ posicao: 0, motivo: 'Esperava uma lista de cartões, ou um objeto com a chave "cartoes".' }],
    };
  }

  const cartoes: CartaoResposta[] = [];
  const recusados: ResultadoImportacao['recusados'] = [];

  lista.forEach((item, indice) => {
    const posicao = indice + 1;
    if (!item || typeof item !== 'object') {
      recusados.push({ posicao, motivo: 'Item não é um objeto.' });
      return;
    }
    const obj = item as Record<string, unknown>;
    const pergunta = String(obj.pergunta ?? '').trim();
    const gatilhos = comoLista(obj.gatilhos, true);
    const resposta = comoLista(obj.resposta);

    const faltando: string[] = [];
    if (!pergunta) faltando.push('pergunta');
    if (gatilhos.length === 0) faltando.push('gatilhos');
    if (resposta.length === 0) faltando.push('resposta');
    if (faltando.length > 0) {
      recusados.push({ posicao, motivo: `Sem ${faltando.join(', ')}.` });
      return;
    }

    const cartao: CartaoResposta = {
      id: String(obj.id ?? '').trim() || idDeCartao(),
      pergunta,
      gatilhos,
      resposta,
    };
    const numeros = comoLista(obj.numeros);
    if (numeros.length > 0) cartao.numeros = numeros;
    const naoDizer = String(obj.naoDizer ?? '').trim();
    if (naoDizer) cartao.naoDizer = naoDizer;

    cartoes.push(cartao);
  });

  return { cartoes, recusados };
};

export const exportarCartoesParaJson = (cartoes: readonly CartaoResposta[]): string =>
  JSON.stringify(cartoes.map(limparCartao), null, 2);

/**
 * O que se cola numa IA externa para ela devolver cartões utilizáveis.
 *
 * As instruções aqui não são estilo: cada uma corresponde a uma limitação real
 * de quem lê um cartão no meio de uma frase, em pé, falando com outra pessoa.
 */
export const MODELO_PARA_IA = `Você vai preparar CARTÕES DE RESPOSTA para eu consultar durante uma reunião, enquanto falo.

Contexto da reunião: [DESCREVA AQUI: com quem, sobre o quê, o que está em jogo]
Documentos de apoio: [COLE AQUI o material]

Como o cartão é usado: ele sobe sozinho na tela quando o interlocutor faz a pergunta. Eu leio de relance, sem parar de falar. Isso determina tudo abaixo.

Regras:
1. Um cartão por PERGUNTA que possam me fazer. Não por assunto.
2. "gatilhos" são as frases como a pergunta é feita EM VOZ ALTA, não como se escreve. Varie: 3 a 6 por cartão. Uma palavra sozinha só se for termo inconfundível (uma sigla, um nome próprio).
3. "resposta" são frases CURTAS, uma por item, do jeito que se fala. Nada de parágrafo: ninguém lê parágrafo falando.
4. "numeros" só para valores que não podem sair errados. Ficam separados para bater o olho.
5. "naoDizer" é o campo mais importante: o que me faria estragar a resposta — afirmar coisa não confirmada, atribuir dado à fonte errada, entrar em disputa. Só preencha quando houver risco real.
6. Não invente número, data ou nome. Se não estiver nos documentos, não entra.
7. Inclua as perguntas INCÔMODAS. Cartão só para pergunta fácil não serve para nada.
8. Depois de cada cartão, pergunte-se: "o que a pessoa pergunta DEPOIS de ouvir esta resposta?" — e faça esse cartão também.

Responda APENAS com o JSON, sem texto antes ou depois, neste formato:

[
  {
    "pergunta": "Quanto custa?",
    "gatilhos": ["quanto custa", "qual o custo", "qual o valor", "quanto sai"],
    "resposta": [
      "A Rede não está comprando hospedagem. Está custeando uma equipe.",
      "70,8% é equipe, 14,3% infraestrutura, 13% a taxa da Fundação."
    ],
    "numeros": ["R$ 210.220,00 por ano", "R$ 427,28 por instituição/mês"],
    "naoDizer": "Não afirme rubrica orçamentária sem confirmar com a área."
  }
]

Os campos "numeros" e "naoDizer" são opcionais. Os outros três são obrigatórios.`;
