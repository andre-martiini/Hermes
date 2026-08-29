/**
 * O bolso de aquisições e a cobertura de cada desejo de compra.
 *
 * Espelho de `functions/bolso_aquisicoes.py`. A regra precisa existir em duas
 * linguagens porque a tela é TypeScript e o MCP é Python, e foi exatamente essa
 * duplicação — antes implícita, com o backend lendo um campo gravado em vez de
 * calcular — que produziu a divergência: a tela mostrava 48,4% na bicicleta e o
 * MCP devolvia zero.
 *
 * **Os dois arquivos têm de andar juntos.** Os testes dos dois lados usam a
 * mesma fixture; se as respostas divergirem, um deles quebra.
 *
 * ## O modelo é deliberado
 *
 * Não há pré-alocação por desejo: um bolso único, e o usuário escolhe o que
 * comprar no momento em que dá. Então a cobertura é individual — "se eu só
 * comprasse este, daria?" — e **não é somável**. Dois itens de R$ 2.000 podem
 * aparecer os dois como cobertos com um bolso de R$ 3.870,97, e comprar os dois
 * não dá. Daí `cabeNaFila`.
 */

export const CATEGORIA_POUPANCA = 'Poupança';

/**
 * A gramática decimal que os dois lados aceitam, escrita uma vez e idêntica em
 * `functions/bolso_aquisicoes.py`. Não é a sintaxe numérica do JavaScript nem a
 * do Python: é a intersecção delas, deliberadamente.
 *
 * `[0-9]` e não `\d` pelo mesmo motivo do outro lado: em padrão de `str` o `\d`
 * do Python casa dígito decimal UNICODE e `float("١")` devolve 1.0, enquanto o
 * `\d` do ECMAScript é só ASCII. Escrito assim, os dois leem a mesma coisa.
 */
const DECIMAL = /^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$/;

/**
 * O que o Firestore devolveu, lido como número por UMA gramática só.
 *
 * Existe porque `Number()` e `float()` aceitam conjuntos DIFERENTES de texto, e
 * o Firestore não tipa o que grava — este módulo já encontrou valor monetário
 * guardado como string mais de uma vez. Confiar na coerção nativa de cada
 * linguagem é ter duas regras achando que são uma:
 *
 * - `Number('0x1')` dá 1 e `float('0x1')` levanta.
 * - `float('1_0')` dá 10 e `Number('1_0')` dá NaN.
 * - `float('NaN')` e `float('Infinity')` passam, e aí `math.floor` levanta e
 *   derruba a tool inteira; deste lado o NaN se propaga em silêncio e corrompe
 *   o cofre exibido.
 *
 * Então nem `Number()` nem `float()` decidem: a gramática decide, e o que não
 * casar com ela vira `padrao` nos dois lados. Zero para dinheiro, 99 para
 * prioridade.
 *
 * `boolean` é recusado de propósito: em Python `bool` é subclasse de `int` e
 * `float(True)` dá 1.0, enquanto aqui `typeof true` não é `'number'`. Aceitar
 * levaria os dois lados a discordar de novo.
 */
export function numero(valor: unknown, padrao = 0): number {
    if (typeof valor === 'number') return Number.isFinite(valor) ? valor : padrao;
    if (typeof valor === 'string' && DECIMAL.test(valor.trim())) {
        const convertido = Number(valor.trim());
        // `Number('1e400')` dá Infinity sem erro nenhum.
        return Number.isFinite(convertido) ? convertido : padrao;
    }
    return padrao;
}

/**
 * Reais para centavos inteiros, com meio-para-cima.
 *
 * Duas razões, e as duas já morderam:
 *
 * - Dinheiro em float compara errado na fronteira. Reserva 0,10 mais poupança
 *   0,70 dá 0.7999999999999999, e uma meta de 0,80 aparece como 100% coberta e
 *   ao mesmo tempo "não cabe".
 * - `round` do Python arredonda meio-para-PAR e o do JavaScript arredonda
 *   meio-para-cima. Como a regra vive nas duas linguagens, a mesma entrada daria
 *   números diferentes nos dois lados — a divergência que este módulo existe
 *   para eliminar. O arredondamento é explícito e igual nos dois, e não o padrão
 *   de cada linguagem.
 *
 * A leitura do valor passa por `numero`, e não por coerção direta: sem isso uma
 * conta gravada como "abc" ou "NaN" virava NaN e contaminava o cofre inteiro,
 * enquanto do lado Python o mesmo valor levantava e derrubava a tool.
 */
export function centavos(valor: unknown): number {
    return Math.floor(numero(valor) * 100 + 0.5);
}

/** Uma casa decimal, meio-para-cima — igual ao lado Python. */
function umaCasa(valor: number): number {
    return Math.floor(valor * 10 + 0.5) / 10;
}

export interface MetaBolso {
    id: string;
    targetAmount: number;
    currentAmount?: number;
    priority?: number;
    status?: string;
}

export interface ContaDoMes {
    category?: string;
    amount?: number;
    isPaid?: boolean;
}

export interface SettingsBolso {
    emergencyReserveCurrent?: number;
    emergencyReserveTarget?: number;
    investmentReserveCurrent?: number;
}

/**
 * Quanto há disponível para aquisições: a reserva de investimento mais — só se a
 * reserva de emergência já estiver completa — o que foi poupado no mês. A
 * condição existe porque poupança do mês com emergência incompleta está indo
 * para a emergência, e não para desejo de compra.
 */
export function bolso(settings: SettingsBolso, contasDoMes: ContaDoMes[]): number {
    const emergenciaAtual = centavos(settings.emergencyReserveCurrent);
    const emergenciaAlvo = centavos(settings.emergencyReserveTarget);
    const poupado = (contasDoMes || [])
        .filter(c => c.category === CATEGORIA_POUPANCA && c.isPaid)
        .reduce((acc, c) => acc + centavos(c.amount), 0);
    const investimento = centavos(settings.investmentReserveCurrent);
    return (investimento + (emergenciaAtual >= emergenciaAlvo ? poupado : 0)) / 100;
}

/**
 * Quanto do bolso este item consome se for comprado sozinho. Meta concluída não
 * recalcula: o valor gravado nela é o que ela custou de fato.
 */
export function cobertura(meta: MetaBolso, disponivel: number): number {
    if (meta.status === 'completed') return numero(meta.currentAmount);
    const alvo = centavos(meta.targetAmount);
    return alvo > 0 ? Math.min(alvo, centavos(disponivel)) / 100 : 0;
}

/**
 * Prioridade, com o id como desempate — e o desempate por **ordinal**, não por
 * `localeCompare`.
 *
 * `localeCompare` usa collation de locale e ignora caixa: `'a'.localeCompare('B')`
 * dá -1, enquanto o Python compara ordinais e põe `'B'` (66) antes de `'a'` (97).
 * Ids do Firestore são alfanuméricos com maiúscula e minúscula misturadas, então
 * duas metas de mesma `priority` seriam ordenadas de um jeito na tela e de outro
 * no MCP — e, com o bolso cobrindo só uma das duas, cada lado apontaria uma
 * diferente como a que cabe. O desempate existe exatamente para eliminar essa
 * divergência; feito com `localeCompare`, ele a reintroduzia por baixo.
 *
 * O limite que sobra, e é o único: `<` compara unidades UTF-16 e o Python compara
 * code points, então os dois só divergiriam com id contendo caractere acima do
 * BMP. Id do Firestore é `[A-Za-z0-9]`.
 */
export function compararMetas(a: MetaBolso, b: MetaBolso): number {
    const porPrioridade = numero(a.priority, 99) - numero(b.priority, 99);
    if (porPrioridade !== 0) return porPrioridade;
    const ia = String(a.id);
    const ib = String(b.id);
    return ia < ib ? -1 : ia > ib ? 1 : 0;
}

/** O que o módulo acrescenta a cada meta. */
export interface ComCobertura {
    currentAmount: number;
    coberturaPct: number;
    /** Se dá para comprar este item JUNTO com os que vêm antes dele na fila. */
    cabeNaFila: boolean;
}

// Interseção e não `extends`: `MetaBolso.currentAmount` é opcional e aqui ele
// deixa de ser, porque o módulo sempre o devolve.
export type MetaComCobertura = MetaBolso & ComCobertura;

export interface ResumoDoBolso<T extends MetaBolso = MetaBolso> {
    bolso: number;
    itensQueCabem: number;
    metas: (T & ComCobertura)[];
}

/**
 * O bolso, a cobertura individual de cada meta e até onde ele alcança na fila.
 *
 * A cobertura individual responde "dá para comprar este?". A fila responde "dá
 * para comprar este junto com os que vêm antes?" — que é a pergunta real quando
 * vários selos de 100% aparecem ao mesmo tempo. É também o único uso efetivo que
 * o campo `priority` ganha.
 */
export function resumoDoBolso<T extends MetaBolso>(
    metas: T[],
    settings: SettingsBolso,
    contasDoMes: ContaDoMes[],
): ResumoDoBolso<T> {
    const disponivel = bolso(settings, contasDoMes);

    // Sem o desempate de `compararMetas`, duas metas de mesma `priority` ficariam
    // na ordem de ENTRADA — e os dois lados recebem a lista de fontes diferentes
    // (o MCP monta do Firestore, a tela do snapshot).
    const ativas = (metas || []).filter(m => m.status !== 'completed').sort(compararMetas);

    // Em centavos inteiros: somar floats e comparar com o bolso erra na
    // fronteira exata, marcando como "não cabe" um item que cabe por zero.
    const teto = centavos(disponivel);
    const cabe = new Map<string, boolean>();
    let acumulado = 0;
    let itensQueCabem = 0;
    for (const meta of ativas) {
        const alvo = centavos(meta.targetAmount);
        if (alvo <= 0) {
            cabe.set(meta.id, false);
            continue;
        }
        acumulado += alvo;
        const entra = acumulado <= teto;
        cabe.set(meta.id, entra);
        if (entra) itensQueCabem += 1;
    }

    return {
        bolso: centavos(disponivel) / 100,
        itensQueCabem,
        // Ordenadas aqui, e não por quem consome. A tela repetia este `sort` por
        // fora e foi assim que o `localeCompare` entrou: a ordem exibida podia
        // divergir da ordem em que a fila foi avaliada, e os selos de "cabe"
        // apareceriam fora de ordem em relação à lista lida. Uma ordenação só.
        metas: [...(metas || [])].sort(compararMetas).map(meta => {
            const atual = cobertura(meta, disponivel);
            const alvo = numero(meta.targetAmount);
            return {
                ...meta,
                // Normalizado na saída, junto com `currentAmount`: quem consome
                // formata este campo e não tem por que repetir a gramática para
                // descobrir se o Firestore guardou "8000" ou 8000.
                targetAmount: alvo,
                currentAmount: centavos(atual) / 100,
                coberturaPct: alvo > 0 ? umaCasa(Math.min(100, (atual / alvo) * 100)) : 0,
                cabeNaFila: cabe.get(meta.id) ?? false,
            };
        }),
    };
}
