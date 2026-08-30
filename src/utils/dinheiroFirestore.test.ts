import { describe, it, expect } from 'vitest';
import { comDinheiro } from './dinheiroFirestore';

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

    it('normaliza mais de um campo', () => {
        const doc = comDinheiro(
            { emergencyReserveCurrent: '1000', emergencyReserveTarget: 20000, outro: 'x' },
            ['emergencyReserveCurrent', 'emergencyReserveTarget'],
        );
        expect(doc.emergencyReserveCurrent).toBe(1000);
        expect(doc.emergencyReserveTarget).toBe(20000);
        expect(doc.outro).toBe('x');
    });
});
