import { describe, it, expect } from 'vitest';
import { gastoAvulsoCentavos, hojeBrt, mesBrt, orcamentoCentavos, resumoDoMes } from './gastoAvulso';

/** A MESMA fixture de `functions/test_gasto_avulso.py` (caso de 30/10/2026). */
const SETTINGS = { monthlyBudget: 5000, monthlyBudgets: { '2026-08': 4529.31, '2026-09': 4848.93 } };

const P = 'picpay';
const TRANSACOES = [
    { amount: 503.56, date: '2026-10-28', category: 'Geral', status: 'active', conta: P },
    { amount: 36.99, date: '2026-10-30T14:17:27+00:00', category: 'Geral', google_message_id: 'm1', conta: P },
    { amount: 79.0, date: '2026-10-30T14:45:18+00:00', category: 'Geral', google_message_id: 'm2', conta: P },
    { amount: 79.0, date: '2026-10-30T14:45:18+00:00', category: 'Geral', google_message_id: 'm2', conta: P }, // duplicata
    { amount: 2000, date: '2026-10-26', category: 'Reserva', status: 'active', conta: P },
    { amount: 300, date: '2026-10-15', category: 'Transferência', conta: P },
    { amount: 310, date: '2026-10-10T12:00:00+00:00', category: 'Conta Fixa', conta: P },
    { amount: 999, date: '2026-10-20', category: 'Geral', status: 'deleted', conta: P },
    { amount: 10, date: '2026-10-31T23:30:00+00:00', category: 'Geral', conta: P },
    { amount: 20, date: '2026-11-01T01:30:00+00:00', category: 'Geral', conta: P },
    { amount: 40, date: '2026-11-01', category: 'Geral', conta: P },
    { amount: 50, date: '2026-10-01T02:00:00+00:00', category: 'Geral', conta: P },
    { amount: 200, date: '2026-11-01T00:00:00.000Z', category: 'Geral', conta: P }, // campo de data do app: dia 1º/11
    { amount: 150, date: '2026-10-12', category: 'Investimentos', conta: P },
    { amount: 5, date: '2026-10-30T10:00:00+00:00', category: 'Geral', pix_id: 7, conta: P },
    { amount: 5, date: '2026-10-30T10:00:00+00:00', category: 'Geral', pix_id: '7', conta: P }, // mesmo Pix, outro tipo
    { amount: 3, date: '2026-10-29', category: 'Geral', conta: ' PicPay ' },
    { amount: 2450, date: '2026-10-28', category: 'Geral', conta: 'xp' }, // saiu da XP: fora do teto
    { amount: 1224.69, date: '2026-10-28', category: 'Geral' }, // resumo mensal sem conta: fora
    { amount: 7811.24, date: '2026-10-28', category: 'Geral', conta: 'mista' },
];

const GASTO_OUTUBRO = 65755;

describe('gastoAvulso (teto do PicPay)', () => {
    it('caso real: só PicPay, sem reserva, transferência, conta fixa, duplicata e deletado', () => {
        expect(resumoDoMes(TRANSACOES, SETTINGS, 2026, 10)).toEqual({ gasto: GASTO_OUTUBRO, orcamento: 500000, saldo: 500000 - GASTO_OUTUBRO });
    });

    it('virada de mês em Brasília', () => {
        expect(gastoAvulsoCentavos(TRANSACOES, 2026, 11)).toBe(24000);
        expect(gastoAvulsoCentavos(TRANSACOES, 2026, 9)).toBe(5000);
    });

    it('mesBrt', () => {
        expect(mesBrt('2026-11-01')).toEqual([2026, 11]);
        expect(mesBrt('2026-11-01T02:59:00')).toEqual([2026, 10]);
        expect(mesBrt('2026-10-31T22:00:00-03:00')).toEqual([2026, 10]);
        expect(mesBrt('2026-11-01T00:30:00.123Z')).toEqual([2026, 10]);
        expect(mesBrt('2026-11-01T00:00:00.000Z')).toEqual([2026, 11]);
        expect(mesBrt('2026-11-01T00:00:00.001Z')).toEqual([2026, 10]);
        expect(mesBrt('٢٠٢٦-10-01')).toBeNull();
        expect(mesBrt('ontem')).toBeNull();
        expect(mesBrt(undefined)).toBeNull();
    });

    it('orçamento do mês vence o geral; ausente vira null', () => {
        expect(orcamentoCentavos({ ...SETTINGS, monthlyBudgets: { '2026-10': 4000 } }, 2026, 10)).toBe(400000);
        expect(orcamentoCentavos(SETTINGS, 2026, 9)).toBe(484893);
        expect(orcamentoCentavos({ ...SETTINGS, monthlyBudgets: { '2026-10': 0 } }, 2026, 10)).toBeNull();
        const r = resumoDoMes(TRANSACOES, {}, 2026, 10);
        expect([r.orcamento, r.saldo]).toEqual([null, null]);
    });

    it('hojeBrt', () => {
        expect(hojeBrt(new Date('2026-11-01T02:30:00Z'))).toEqual([2026, 10, 31]);
    });
});
