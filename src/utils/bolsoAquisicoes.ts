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
    const emergenciaAtual = settings.emergencyReserveCurrent || 0;
    const emergenciaAlvo = settings.emergencyReserveTarget || 0;
    const poupado = (contasDoMes || [])
        .filter(c => c.category === CATEGORIA_POUPANCA && c.isPaid)
        .reduce((acc, c) => acc + (c.amount || 0), 0);
    const investimento = settings.investmentReserveCurrent || 0;
    return investimento + (emergenciaAtual >= emergenciaAlvo ? poupado : 0);
}

/**
 * Quanto do bolso este item consome se for comprado sozinho. Meta concluída não
 * recalcula: o valor gravado nela é o que ela custou de fato.
 */
export function cobertura(meta: MetaBolso, disponivel: number): number {
    if (meta.status === 'completed') return meta.currentAmount || 0;
    const alvo = meta.targetAmount || 0;
    return alvo > 0 ? Math.min(alvo, disponivel) : 0;
}

export interface MetaComCobertura extends MetaBolso {
    currentAmount: number;
    coberturaPct: number;
    /** Se dá para comprar este item JUNTO com os que vêm antes dele na fila. */
    cabeNaFila: boolean;
}

export interface ResumoDoBolso {
    bolso: number;
    itensQueCabem: number;
    metas: MetaComCobertura[];
}

/**
 * O bolso, a cobertura individual de cada meta e até onde ele alcança na fila.
 *
 * A cobertura individual responde "dá para comprar este?". A fila responde "dá
 * para comprar este junto com os que vêm antes?" — que é a pergunta real quando
 * vários selos de 100% aparecem ao mesmo tempo. É também o único uso efetivo que
 * o campo `priority` ganha.
 */
export function resumoDoBolso(
    metas: MetaBolso[],
    settings: SettingsBolso,
    contasDoMes: ContaDoMes[],
): ResumoDoBolso {
    const disponivel = bolso(settings, contasDoMes);

    const ativas = (metas || [])
        .filter(m => m.status !== 'completed')
        .sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99));

    const cabe = new Map<string, boolean>();
    let acumulado = 0;
    let itensQueCabem = 0;
    for (const meta of ativas) {
        const alvo = meta.targetAmount || 0;
        if (alvo <= 0) {
            cabe.set(meta.id, false);
            continue;
        }
        acumulado += alvo;
        const entra = acumulado <= disponivel;
        cabe.set(meta.id, entra);
        if (entra) itensQueCabem += 1;
    }

    return {
        bolso: disponivel,
        itensQueCabem,
        metas: (metas || []).map(meta => {
            const atual = cobertura(meta, disponivel);
            const alvo = meta.targetAmount || 0;
            return {
                ...meta,
                currentAmount: atual,
                coberturaPct: alvo > 0 ? Math.min(100, (atual / alvo) * 100) : 0,
                cabeNaFila: cabe.get(meta.id) ?? false,
            };
        }),
    };
}
