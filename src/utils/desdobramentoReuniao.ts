// src/utils/desdobramentoReuniao.ts
// Desdobramento da reunião: o que ficou decidido e o que virou tarefa.
//
// Camada oposta à assistência ao vivo. Lá o inimigo é a latência — aqui não há
// pressa nenhuma: a reunião acabou, o modelo pode levar trinta segundos e ler
// a transcrição inteira. O que importa aqui é OUTRA coisa: não inventar.
//
// Por isso todo item carrega o TRECHO LITERAL que o sustenta. Sem o trecho,
// revisar dez itens exigiria reler a reunião inteira, e ninguém revisa nessas
// condições — aceita tudo e descobre o erro quando a tarefa errada cobra.

export interface DecisaoReuniao {
  texto: string;
  /** Trecho literal da transcrição que sustenta a decisão. */
  trecho: string;
}

export interface AcaoReuniao {
  titulo: string;
  descricao?: string;
  /** Quem ficou de fazer. Vazio quando a transcrição não diz. */
  responsavel?: string;
  /** ISO (aaaa-mm-dd) quando a reunião deu data; vazio quando não deu. */
  prazo?: string;
  /** true quando é do próprio usuário; false quando se espera de terceiro. */
  minha: boolean;
  trecho: string;
}

export interface Desdobramento {
  decisoes: DecisaoReuniao[];
  acoes: AcaoReuniao[];
  /** O que o modelo devolveu fora do formato. Nunca engolir em silêncio. */
  recusados: { posicao: number; motivo: string }[];
}

export const DESDOBRAMENTO_VAZIO: Desdobramento = { decisoes: [], acoes: [], recusados: [] };

/**
 * O que se pede ao modelo depois da reunião.
 *
 * Duas restrições valem mais que todo o resto: nada entra sem trecho literal,
 * e o que não foi dito não existe. Um desdobramento que "melhora" o que foi
 * combinado é pior que nenhum — vira tarefa que ninguém reconhece.
 */
export const montarPromptDesdobramento = (titulo: string, transcricao: string): string =>
  `Você vai ler a transcrição de uma reunião e extrair o que ficou decidido e o que virou tarefa.

Título da reunião: ${titulo || 'sem título'}

REGRAS, e a primeira vale mais que as outras:
1. NÃO INVENTE. Só entra o que foi dito. Se ficou vago na reunião, fica vago aqui — não complete, não deduza, não melhore a redação a ponto de mudar o sentido.
2. Todo item precisa do campo "trecho": as palavras LITERAIS da transcrição que sustentam aquele item. Sem trecho, o item não entra.
3. "decisoes" são coisas que ficaram resolvidas. Não têm responsável nem prazo.
4. "acoes" são coisas que alguém ficou de fazer. "minha": true quando é de quem gravou a reunião, false quando se espera de outra pessoa.
5. "prazo" só quando a reunião disse uma data ou um prazo convertível em data (aaaa-mm-dd). "semana que vem" sem data de referência não vira prazo — deixe vazio.
6. "responsavel" só quando a transcrição nomear alguém. Não atribua por dedução.
7. Conversa social, atraso de participante e problema de áudio não são decisão nem ação.
8. Se a reunião não produziu nada disso, devolva as duas listas vazias. É um resultado legítimo e frequente.

Responda APENAS com o JSON, sem texto antes ou depois:

{
  "decisoes": [
    { "texto": "O que ficou decidido, numa frase", "trecho": "palavras literais da transcrição" }
  ],
  "acoes": [
    {
      "titulo": "O que fazer, começando por um verbo",
      "descricao": "Contexto, só se a transcrição der",
      "responsavel": "Nome como foi dito, ou vazio",
      "prazo": "aaaa-mm-dd ou vazio",
      "minha": true,
      "trecho": "palavras literais da transcrição"
    }
  ]
}

TRANSCRIÇÃO:
${transcricao}`;

const texto = (valor: unknown): string => (valor == null ? '' : String(valor).trim());

/** O modelo às vezes embrulha o JSON em cerca de código. Não é erro de ninguém. */
const desembrulhar = (bruto: string): string => {
  const semCerca = bruto.replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  const inicio = semCerca.indexOf('{');
  const fim = semCerca.lastIndexOf('}');
  return inicio >= 0 && fim > inicio ? semCerca.slice(inicio, fim + 1) : semCerca;
};

/**
 * Lê a resposta do modelo.
 *
 * Item sem trecho literal é RECUSADO, e não corrigido. É a única salvaguarda
 * automática contra invenção que existe aqui — relaxá-la esvazia a revisão.
 */
export const interpretarDesdobramento = (bruto: string): Desdobramento => {
  let cru: unknown;
  try {
    cru = JSON.parse(desembrulhar(bruto));
  } catch {
    return { ...DESDOBRAMENTO_VAZIO, recusados: [{ posicao: 0, motivo: 'A resposta não veio em JSON.' }] };
  }

  const obj = (cru ?? {}) as { decisoes?: unknown; acoes?: unknown };
  const decisoes: DecisaoReuniao[] = [];
  const acoes: AcaoReuniao[] = [];
  const recusados: Desdobramento['recusados'] = [];

  (Array.isArray(obj.decisoes) ? obj.decisoes : []).forEach((item, i) => {
    const d = (item ?? {}) as Record<string, unknown>;
    const conteudo = texto(d.texto);
    const trecho = texto(d.trecho);
    if (!conteudo) return void recusados.push({ posicao: i + 1, motivo: 'Decisão sem texto.' });
    if (!trecho) return void recusados.push({ posicao: i + 1, motivo: `Decisão sem trecho literal: "${conteudo}".` });
    decisoes.push({ texto: conteudo, trecho });
  });

  (Array.isArray(obj.acoes) ? obj.acoes : []).forEach((item, i) => {
    const a = (item ?? {}) as Record<string, unknown>;
    const titulo = texto(a.titulo);
    const trecho = texto(a.trecho);
    if (!titulo) return void recusados.push({ posicao: i + 1, motivo: 'Ação sem título.' });
    if (!trecho) return void recusados.push({ posicao: i + 1, motivo: `Ação sem trecho literal: "${titulo}".` });

    const acao: AcaoReuniao = { titulo, minha: a.minha !== false, trecho };
    const descricao = texto(a.descricao);
    if (descricao) acao.descricao = descricao;
    const responsavel = texto(a.responsavel);
    if (responsavel) acao.responsavel = responsavel;
    const prazo = texto(a.prazo);
    if (/^\d{4}-\d{2}-\d{2}$/.test(prazo)) acao.prazo = prazo;
    else if (prazo) recusados.push({ posicao: i + 1, motivo: `Prazo "${prazo}" não é uma data; a ação entrou sem prazo.` });

    acoes.push(acao);
  });

  return { decisoes, acoes, recusados };
};

/** Só faz sentido pedir desdobramento de reunião que produziu conversa. */
export const transcricaoParaDesdobramento = (
  falas: readonly { speaker: string; text: string }[],
): string => falas.map((f) => `${f.speaker}: ${f.text}`).join('\n');
