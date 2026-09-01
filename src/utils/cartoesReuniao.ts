// src/utils/cartoesReuniao.ts
// Casador de cartões para a assistência ao vivo em reuniões.
//
// POR QUE LOCAL E SEM REDE: casar fala com cartão chamando um LLM seria lento
// (a resposta chega depois que o assunto passou), caro por minuto de reunião e
// não-determinístico — a mesma pergunta traria cartões diferentes em dias
// diferentes. Aqui a decisão é por frases-gatilho, com correspondência
// aproximada, e roda em milissegundos no próprio navegador.
//
// O escalonamento para o LLM continua existindo, mas por decisão de quem está
// na reunião: é o botão de perguntar sobre os últimos segundos, não o casador.

export interface CartaoResposta {
  id: string;
  /** Título curto — é o que aparece primeiro, e às vezes é só o que dá tempo de ler. */
  pergunta: string;
  /** Frases que costumam anunciar a pergunta. Uma só já basta para casar. */
  gatilhos: string[];
  /** O que dizer, em voz alta. Frases curtas: ninguém lê parágrafo falando. */
  resposta: string[];
  /** Números que não podem sair errados. Ficam separados para bater o olho. */
  numeros?: string[];
  /** O que NÃO dizer. É o campo que evita o estrago, e por isso vem destacado. */
  naoDizer?: string;
}

export interface CartaoCasado {
  cartao: CartaoResposta;
  /** 0 a 1 — quanto do gatilho apareceu na fala. Serve para ordenar, não para exibir. */
  score: number;
  gatilhoQueCasou: string;
}

/**
 * Palavras que aparecem em qualquer frase e não distinguem nada. Sem esta
 * lista, "o que é isso" casaria com metade dos cartões.
 */
const VAZIAS = new Set([
  'a', 'ao', 'aos', 'as', 'como', 'com', 'da', 'das', 'de', 'do', 'dos', 'e',
  'em', 'essa', 'esse', 'esta', 'este', 'eu', 'foi', 'isso', 'ja', 'la', 'mais',
  'mas', 'me', 'na', 'nas', 'no', 'nos', 'o', 'os', 'ou', 'para', 'pra', 'por',
  'que', 'se', 'ser', 'seu', 'sua', 'tem', 'um', 'uma', 'voce', 'vai', 'vou',
  'ta', 'the', 'of',
]);

export const normalizar = (texto: string): string =>
  texto
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const tokensUteis = (texto: string): string[] =>
  normalizar(texto)
    .split(' ')
    .filter((t) => t.length > 1 && !VAZIAS.has(t));

/**
 * Quanto do gatilho aparece na fala, de 0 a 1.
 *
 * Duas formas de casar, e a primeira é a que pega o caso real. Se o gatilho
 * inteiro aparece como trecho contínuo, é casamento certo (1). Senão, mede-se
 * quantas das palavras úteis do gatilho estão na fala, em qualquer ordem —
 * porque ninguém pergunta com as palavras exatas que a gente previu.
 */
export const pontuarGatilho = (falaNormalizada: string, gatilho: string): number => {
  const alvo = normalizar(gatilho);
  if (!alvo) return 0;
  if (falaNormalizada.includes(alvo)) return 1;

  const palavras = tokensUteis(gatilho);
  if (palavras.length === 0) return 0;

  const naFala = new Set(tokensUteis(falaNormalizada));
  const presentes = palavras.filter((p) => naFala.has(p)).length;

  // Gatilho de palavra única (SUAP, LGPD, INPI) só vale se a palavra estiver
  // literalmente lá. Meio termo aqui produziria falso positivo em série.
  if (palavras.length === 1) return presentes === 1 ? 1 : 0;

  return presentes / palavras.length;
};

export interface OpcoesCasamento {
  /** Abaixo disto não sobe cartão. 0.7 exige que a maior parte do gatilho apareça. */
  limite?: number;
  /** Quantos cartões no máximo. Mais de três na tela ninguém lê. */
  maximo?: number;
}

/**
 * Devolve os cartões que a fala convoca, do mais provável para o menos.
 *
 * Recebe a fala já concatenada pelo chamador — a decisão de quanto tempo de
 * conversa entra na janela é dele, não daqui.
 */
export const casarCartoes = (
  fala: string,
  cartoes: readonly CartaoResposta[],
  opcoes: OpcoesCasamento = {},
): CartaoCasado[] => {
  const limite = opcoes.limite ?? 0.7;
  const maximo = opcoes.maximo ?? 3;
  const falaNormalizada = normalizar(fala);
  if (!falaNormalizada) return [];

  const casados: CartaoCasado[] = [];
  for (const cartao of cartoes) {
    let melhor = 0;
    let gatilhoQueCasou = '';
    for (const gatilho of cartao.gatilhos) {
      const score = pontuarGatilho(falaNormalizada, gatilho);
      if (score > melhor) {
        melhor = score;
        gatilhoQueCasou = gatilho;
      }
    }
    if (melhor >= limite) casados.push({ cartao, score: melhor, gatilhoQueCasou });
  }

  return casados.sort((a, b) => b.score - a.score).slice(0, maximo);
};

/**
 * Cartão que subiu há pouco não sobe de novo.
 *
 * Sem isto, uma conversa que volta ao mesmo assunto faz o mesmo cartão piscar
 * a cada frase — e cartão que pisca vira ruído que a pessoa aprende a ignorar,
 * justamente quando ele importa.
 */
export const filtrarRecentes = (
  casados: readonly CartaoCasado[],
  exibidosEm: ReadonlyMap<string, number>,
  agora: number,
  janelaMs = 5 * 60 * 1000,
): CartaoCasado[] =>
  casados.filter(({ cartao }) => {
    const ultimo = exibidosEm.get(cartao.id);
    return ultimo === undefined || agora - ultimo >= janelaMs;
  });
