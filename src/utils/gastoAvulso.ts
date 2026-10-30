/**
 * Gasto avulso do mês e saldo do orçamento — espelho de `functions/gasto_avulso.py`.
 *
 * A notificação "Gasto Realizado via Pix" (Telegram) e o "Alerta de Orçamento"
 * do app têm de mostrar o mesmo número. Os testes dos dois lados usam a MESMA
 * fixture; mudou a regra aqui, muda lá. A regra e o que ela não resolve estão
 * no docstring do módulo Python.
 */
import { centavos, numero } from './bolsoAquisicoes';

const BRT_MS = -3 * 3600 * 1000; // offset fixo: sem horário de verão desde 2019

const CATEGORIAS_FORA_DO_CONSUMO = new Set(['transferencia', 'investimento', 'poupanca', 'reserva', 'conta fixa']);

const DATA = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/;

export interface LancamentoAvulso {
    amount?: unknown;
    date?: unknown;
    status?: unknown;
    category?: unknown;
    google_message_id?: unknown;
    pix_id?: unknown;
}

export interface SettingsOrcamento {
    monthlyBudget?: unknown;
    monthlyBudgets?: Record<string, unknown>;
}

function normal(texto: unknown): string {
    return String(texto ?? '').normalize('NFKD').replace(/[̀-ͯ]/g, '').trim().toLowerCase();
}

/** [ano, mês 1-12] do lançamento no fuso de Brasília, ou null se ilegível. */
export function mesBrt(data: unknown): [number, number] | null {
    const m = DATA.exec(String(data ?? '').trim());
    if (!m) return null;
    const [, ano, mes, dia, hora, minuto, seg, fuso] = m;
    if (hora === undefined) return [Number(ano), Number(mes)];
    let utc = Date.UTC(Number(ano), Number(mes) - 1, Number(dia), Number(hora), Number(minuto), Number(seg ?? 0));
    if (fuso && fuso !== 'Z') {
        const sinal = fuso[0] === '-' ? -1 : 1;
        utc -= sinal * (Number(fuso.slice(1, 3)) * 60 + Number(fuso.slice(-2))) * 60000;
    }
    const local = new Date(utc + BRT_MS);
    return [local.getUTCFullYear(), local.getUTCMonth() + 1];
}

export function gastoAvulsoCentavos(transacoes: LancamentoAvulso[], ano: number, mes: number): number {
    let total = 0;
    const vistos = new Set<string>();
    for (const t of transacoes) {
        if (t.status === 'deleted') continue;
        if (CATEGORIAS_FORA_DO_CONSUMO.has(normal(t.category))) continue;
        const m = mesBrt(t.date);
        if (!m || m[0] !== ano || m[1] !== mes) continue;
        const chaves = [['g', t.google_message_id], ['p', t.pix_id]]
            .filter(([, v]) => v !== undefined && v !== null && v !== '')
            .map(([k, v]) => `${k}:${v}`);
        if (chaves.some(c => vistos.has(c))) continue;
        chaves.forEach(c => vistos.add(c));
        total += centavos(t.amount);
    }
    return total;
}

/** Orçamento do mês (o do mês, senão o geral), ou null quando não há. */
export function orcamentoCentavos(settings: SettingsOrcamento | null | undefined, ano: number, mes: number): number | null {
    const doMes = numero(settings?.monthlyBudgets?.[`${ano}-${String(mes).padStart(2, '0')}`]);
    const valor = doMes > 0 ? doMes : numero(settings?.monthlyBudget);
    return valor > 0 ? centavos(valor) : null;
}

export function resumoDoMes(transacoes: LancamentoAvulso[], settings: SettingsOrcamento | null | undefined, ano: number, mes: number) {
    const gasto = gastoAvulsoCentavos(transacoes, ano, mes);
    const orcamento = orcamentoCentavos(settings, ano, mes);
    return { gasto, orcamento, saldo: orcamento === null ? null : orcamento - gasto };
}

export function mesAtualBrt(agora: Date = new Date()): [number, number] {
    const local = new Date(agora.getTime() + BRT_MS);
    return [local.getUTCFullYear(), local.getUTCMonth() + 1];
}
