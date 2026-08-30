/**
 * Normalização de valores monetários na FRONTEIRA onde o dado do Firestore
 * entra no app.
 *
 * O padrão `{ id: d.id, ...d.data() } as FixedBill` que as assinaturas usam é
 * uma **afirmação**, não uma conversão: ele promete `amount: number` sobre um
 * documento que o Firestore não tipa. Com `amount` gravado como string — o que
 * já foi encontrado nesta base — `a + b` concatena em vez de somar, e
 * `.toFixed()` nem existe, derrubando a tela inteira.
 *
 * São 25+ leituras de `amount` só na `FinanceView`, entre somas, ordenações,
 * subtrações e formatações. Proteger uma a uma trata o sintoma e reabre o
 * buraco na próxima linha que alguém escrever. Aqui é o único ponto por onde
 * todas passam, e depois dele o tipo deixa de mentir.
 *
 * O lado Python faz o mesmo na fronteira dele, em `consultar_financas_v2`, e
 * pelo mesmo motivo — a lição de que normalizar dentro do módulo não protege
 * quem faz aritmética antes de chamá-lo.
 */
import { numero } from './bolsoAquisicoes';

/**
 * Devolve uma cópia do documento com os campos indicados lidos como número
 * pela gramática compartilhada.
 *
 * Campo ausente é deixado ausente de propósito: `defaultAmount` é opcional nas
 * rubricas, e transformar "não tem padrão" em "padrão zero" seria inventar
 * dado. Campo presente porém ilegível vira zero, que é a regra de `numero`.
 */
export function comDinheiro(
    bruto: Record<string, any>,
    campos: string[],
    camposDeMapa: string[] = [],
): Record<string, any> {
    const saida: Record<string, any> = { ...bruto };
    for (const campo of campos) {
        if (bruto[campo] !== undefined) saida[campo] = numero(bruto[campo]);
    }
    // `monthlyBudgets` guarda um valor por mês (`{"2026-02": 5000}`), e um deles
    // gravado como string faz `currentMonthTotal / orçamento` dar NaN — a barra
    // de orçamento vira `width: NaN%` sem erro nenhum no console. Por isso os
    // valores DENTRO do mapa também passam pela gramática.
    for (const campo of camposDeMapa) {
        const mapa = bruto[campo];
        if (mapa && typeof mapa === 'object' && !Array.isArray(mapa)) {
            const normalizado: Record<string, number> = {};
            for (const chave of Object.keys(mapa)) normalizado[chave] = numero(mapa[chave]);
            saida[campo] = normalizado;
        }
    }
    return saida;
}

/**
 * O mesmo, para uma lista de sub-objetos dentro do documento — `servicos`
 * guarda as parcelas assim, cada uma com o seu `valor`.
 *
 * Existe por causa de um defeito concreto e caro: a sincronia de servicos para
 * rendas compara `existing.amount !== expected.amount` com `!==` estrito. Com
 * o `amount` da renda normalizado nesta fronteira e o `valor` da parcela ainda
 * string, os dois NUNCA sao iguais — a sincronia grava, o snapshot volta
 * normalizado, o efeito re-dispara pela dependencia `incomeEntries` e grava de
 * novo. Loop infinito de escrita no Firestore, contido so pelo debounce de 1s.
 *
 * Normalizar so um dos lados de uma comparacao e pior que nao normalizar
 * nenhum: transforma um dado errado em silencio num ciclo de escrita.
 */
export function comDinheiroNaLista(itens: any, campos: string[]): any {
    if (!Array.isArray(itens)) return itens;
    return itens.map(item =>
        item && typeof item === 'object' && !Array.isArray(item)
            ? comDinheiro(item, campos)
            : item);
}
