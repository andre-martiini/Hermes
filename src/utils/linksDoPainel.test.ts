import { describe, expect, it } from 'vitest';
import { subtituloFinanceiro, subtituloSaude } from './linksDoPainel';

describe('links discretos', () => {
    it('financeiro', () => {
        expect(subtituloFinanceiro(0)).toBe('Sem pendências nas contas');
        expect(subtituloFinanceiro(1)).toBe('1 conta vencendo');
        expect(subtituloFinanceiro(3)).toBe('3 contas vencendo');
        expect(subtituloFinanceiro(null)).toBe('Contas, cartão e investimentos');
    });
    it('saúde', () => {
        expect(subtituloSaude({ pesagemRegistrada: false, checkinManha: false, checkinNoite: false, dorOntem: 0 }))
            .toBe('Pesagem e 2 check-ins de hoje pendentes · dor ontem 0');
        expect(subtituloSaude({ pesagemRegistrada: true, checkinManha: true, checkinNoite: false, dorOntem: null }))
            .toBe('1 check-in de hoje pendente');
        expect(subtituloSaude({ pesagemRegistrada: true, checkinManha: true, checkinNoite: true, dorOntem: 4 }))
            .toBe('Tudo registrado hoje · dor ontem 4');
    });
});
