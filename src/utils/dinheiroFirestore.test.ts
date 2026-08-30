import { describe, it, expect } from 'vitest';
import { comDinheiro, comDinheiroNaLista } from './dinheiroFirestore';

describe('dinheiro na fronteira do Firestore', () => {
    it('numero gravado como string vira numero', () => {
        // O caso real: `"500" + "500"` dá "500500" e `"500".toFixed` nem existe.
        const doc = comDinheiro({ amount: '500', description: 'Conta' }, ['amount']);
        expect(doc.amount).toBe(500);
        expect(doc.amount + doc.amount).toBe(1000);
    });

    it('valor ilegivel vira zero em vez de NaN ou excecao', () => {
        for (const bruto of ['abc', 'NaN', 'R$ 5', '', null]) {
            expect(comDinheiro({ amount: bruto }, ['amount']).amount, String(bruto)).toBe(0);
        }
    });

    it('campo ausente continua ausente', () => {
        // `defaultAmount` e opcional nas rubricas: virar 0 seria inventar dado.
        const doc = comDinheiro({ nome: 'Aluguel' }, ['defaultAmount']);
        expect('defaultAmount' in doc).toBe(false);
    });

    it('nao mexe nos outros campos e nao muta a entrada', () => {
        const bruto = { amount: '10', description: 'X', isPaid: true, month: 7 };
        const doc = comDinheiro(bruto, ['amount']);
        expect(doc).toEqual({ amount: 10, description: 'X', isPaid: true, month: 7 });
        expect(bruto.amount).toBe('10');
    });

    it('normaliza os valores dentro de um mapa', () => {
        // `monthlyBudgets` e um valor por mes; uma string ali faz a divisao do
        // orcamento dar NaN e a barra virar `width: NaN%`, sem erro no console.
        const doc = comDinheiro(
            { monthlyBudgets: { '2026-02': '5000', '2026-03': 4000, '2026-04': 'abc' } },
            [], ['monthlyBudgets'],
        );
        expect(doc.monthlyBudgets).toEqual({ '2026-02': 5000, '2026-03': 4000, '2026-04': 0 });
    });

    it('mapa ausente ou de outro tipo nao vira objeto vazio', () => {
        expect('monthlyBudgets' in comDinheiro({}, [], ['monthlyBudgets'])).toBe(false);
        expect(comDinheiro({ monthlyBudgets: null }, [], ['monthlyBudgets']).monthlyBudgets).toBe(null);
    });

    it('normaliza mais de um campo', () => {
        const doc = comDinheiro(
            { emergencyReserveCurrent: '1000', emergencyReserveTarget: 20000, outro: 'x' },
            ['emergencyReserveCurrent', 'emergencyReserveTarget'],
        );
        expect(doc.emergencyReserveCurrent).toBe(1000);
        expect(doc.emergencyReserveTarget).toBe(20000);
        expect(doc.outro).toBe('x');
    });

    it('normaliza os valores de uma lista de sub-objetos', () => {
        // As parcelas de um servico. Com o `valor` string de um lado e o
        // `amount` da renda normalizado do outro, a sincronia entra em loop de
        // escrita: `!==` nunca da falso.
        const parcelas = comDinheiroNaLista(
            [{ id: 'a', valor: '5000', status: 'pago' }, { id: 'b', valor: 300 }],
            ['valor'],
        );
        expect(parcelas).toEqual([
            { id: 'a', valor: 5000, status: 'pago' },
            { id: 'b', valor: 300 },
        ]);
    });

    it('lista ausente ou de outro tipo passa intacta', () => {
        expect(comDinheiroNaLista(undefined, ['valor'])).toBe(undefined);
        expect(comDinheiroNaLista(null, ['valor'])).toBe(null);
        expect(comDinheiroNaLista([null, 'x'], ['valor'])).toEqual([null, 'x']);
    });
});
