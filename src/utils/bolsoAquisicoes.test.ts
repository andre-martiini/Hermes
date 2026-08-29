import { describe, it, expect } from 'vitest';
import { bolso, resumoDoBolso } from './bolsoAquisicoes';

/**
 * A MESMA fixture de `functions/test_bolso_aquisicoes.py`, com os números reais
 * de 29/08/2026 — o estado em que a tela mostrava bicicleta 48,4%, T-Cross 3,9%
 * e os dois ar-condicionados a 100%, enquanto o `consultar_financas_v2`
 * devolvia 2.827,38, 0, 0 e 2.827,38.
 *
 * Se as duas implementações divergirem, um destes dois arquivos quebra. É a
 * única defesa possível quando a mesma regra precisa existir em duas linguagens.
 */

const BOLSO = 3870.97;

const SETTINGS = {
    emergencyReserveCurrent: 10000,
    emergencyReserveTarget: 10000,
    investmentReserveCurrent: 3870.97,
};

const CONTAS: any[] = [];

const METAS = [
    { id: 'bike', targetAmount: 8000, priority: 1, status: 'active', currentAmount: 0 },
    { id: 'ar_quarto', targetAmount: 2000, priority: 3, status: 'active', currentAmount: 2827.38 },
    { id: 'ar_escritorio', targetAmount: 2000, priority: 4, status: 'active', currentAmount: 0 },
    { id: 'tcross', targetAmount: 100000, priority: 5, status: 'active', currentAmount: 2827.38 },
];

const pct = (id: string) =>
    Math.round(resumoDoBolso(METAS, SETTINGS, CONTAS).metas.find(m => m.id === id)!.coberturaPct * 10) / 10;

describe('bolso de aquisições', () => {
    it('é a reserva de investimento quando não há poupança do mês', () => {
        expect(bolso(SETTINGS, CONTAS)).toBeCloseTo(BOLSO, 2);
    });

    it('só soma a poupança do mês com a emergência completa', () => {
        // Poupança com emergência incompleta está indo para a emergência.
        const contas = [{ category: 'Poupança', amount: 500, isPaid: true }];
        expect(bolso(SETTINGS, contas)).toBeCloseTo(BOLSO + 500, 2);
        expect(bolso({ ...SETTINGS, emergencyReserveCurrent: 1 }, contas)).toBeCloseTo(BOLSO, 2);
    });

    it('expõe o bolso em campo próprio, sem obrigar a inferir pelas coberturas', () => {
        expect(resumoDoBolso(METAS, SETTINGS, CONTAS).bolso).toBeCloseTo(BOLSO, 2);
    });
});

describe('cobertura individual — os números que a tela já mostrava', () => {
    it('bicicleta 48,4%', () => expect(pct('bike')).toBe(48.4));
    it('T-Cross 3,9%', () => expect(pct('tcross')).toBe(3.9));
    it('os dois ar-condicionados batem no teto', () => {
        expect(pct('ar_quarto')).toBe(100);
        expect(pct('ar_escritorio')).toBe(100);
    });

    it('ignora o currentAmount gravado, que era o que divergia', () => {
        const comLixo = METAS.map(m => ({ ...m, currentAmount: 99999 }));
        const r = resumoDoBolso(comLixo, SETTINGS, CONTAS);
        expect(Object.fromEntries(r.metas.map(m => [m.id, m.currentAmount]))).toEqual({
            bike: BOLSO, ar_quarto: 2000, ar_escritorio: 2000, tcross: BOLSO,
        });
    });

    it('meta concluída preserva o que custou, e não o bolso de hoje', () => {
        const r = resumoDoBolso(
            [{ id: 'x', targetAmount: 500, priority: 1, status: 'completed', currentAmount: 480 }],
            SETTINGS, CONTAS);
        expect(r.metas[0].currentAmount).toBe(480);
    });
});

describe('as coberturas não são somáveis', () => {
    it('os dois ar-condicionados não cabem juntos', () => {
        // 2.000 + 2.000 = 4.000, e o bolso tem 3.870,97 — faltam 129,03.
        const r = resumoDoBolso(METAS, SETTINGS, CONTAS);
        const cabe = Object.fromEntries(r.metas.map(m => [m.id, m.cabeNaFila]));
        expect(cabe.ar_quarto).toBe(false);
        expect(cabe.ar_escritorio).toBe(false);
    });

    it('a fila respeita a prioridade — o único uso real que o campo ganha', () => {
        const metas = [
            { id: 'b', targetAmount: 3000, priority: 2, status: 'active' },
            { id: 'a', targetAmount: 500, priority: 1, status: 'active' },
            { id: 'c', targetAmount: 500, priority: 3, status: 'active' },
        ];
        const r = resumoDoBolso(metas, SETTINGS, CONTAS);
        // 500 + 3000 = 3500 cabe; somando 500 daria 4000, que estoura.
        expect(Object.fromEntries(r.metas.map(m => [m.id, m.cabeNaFila])))
            .toEqual({ a: true, b: true, c: false });
        expect(r.itensQueCabem).toBe(2);
    });
});
