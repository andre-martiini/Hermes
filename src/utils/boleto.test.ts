import { describe, expect, it } from 'vitest';

import { analisarBoleto, descreverBoleto, larguraItf, LARGA_ITF, vencimentoDoFator } from './boleto';

// Exemplos sintéticos (nenhum boleto real), gerados por uma implementação
// independente em Python dos mesmos algoritmos Febraban, para que o teste
// confira uma contra a outra e não o código contra ele mesmo.
const BANCARIO = {
    linha: '34191.09008 00012.345674 89012.345677 1 15950000012345',
    codigo: '34191159500000123451090000012345678901234567',
};
const BANCARIO_SEM_VALOR = {
    linha: '00190000090234567890412345678903900000000000000',
    codigo: '00199000000000000000000002345678901234567890',
};
const ARRECADACAO_MOD10 = {
    linha: '82620000000-6 89900000123-5 45678901234-5 56789012345-6',
    codigo: '82620000000899000001234567890123456789012345',
};
const ARRECADACAO_MOD11 = {
    linha: '828600000029500000009875654321098762543210987656',
    codigo: '82860000002500000009876543210987654321098765',
};
const ARRECADACAO_REFERENCIA = {
    linha: '827300000003432100001119112222233333344444555553',
    codigo: '82730000000432100001111122222333334444455555',
};

const HOJE = new Date('2026-10-01T12:00:00Z');

const trocarDigito = (texto: string, posicaoDoDigito: number) => {
    let visto = -1;
    return texto.replace(/\d/g, (d) => {
        visto += 1;
        return visto === posicaoDoDigito ? String((Number(d) + 1) % 10) : d;
    });
};

describe('analisarBoleto — boleto bancário (47 dígitos)', () => {
    it('monta o código de barras, o valor e o vencimento', () => {
        const a = analisarBoleto(BANCARIO.linha, HOJE)!;
        expect(a.valido).toBe(true);
        expect(a.tipo).toBe('bancario');
        expect(a.codigoBarras).toBe(BANCARIO.codigo);
        expect(a.valor).toBe(123.45);
        expect(a.vencimento).toBe('2026-10-10');
    });

    it('fator e valor zerados ficam sem vencimento e sem valor', () => {
        const a = analisarBoleto(BANCARIO_SEM_VALOR.linha, HOJE)!;
        expect(a.valido).toBe(true);
        expect(a.codigoBarras).toBe(BANCARIO_SEM_VALOR.codigo);
        expect(a.valor).toBeUndefined();
        expect(a.vencimento).toBeUndefined();
    });

    it('um dígito trocado em qualquer campo é recusado', () => {
        for (const posicao of [2, 15, 25, 32, 40]) {
            const a = analisarBoleto(trocarDigito(BANCARIO.linha, posicao), HOJE)!;
            expect(a.valido, `posição ${posicao}`).toBe(false);
            expect(a.erro).toMatch(/verificadores não conferem/);
            expect(a.codigoBarras).toBeUndefined();
        }
    });

    it('aceita o próprio código de barras de 44 dígitos', () => {
        const a = analisarBoleto(BANCARIO.codigo, HOJE)!;
        expect(a.valido).toBe(true);
        expect(a.codigoBarras).toBe(BANCARIO.codigo);
        expect(a.valor).toBe(123.45);
    });
});

describe('analisarBoleto — conta de consumo ou tributo (48 dígitos)', () => {
    it('módulo 10 (identificador 6) traz o valor', () => {
        const a = analisarBoleto(ARRECADACAO_MOD10.linha, HOJE)!;
        expect(a.valido).toBe(true);
        expect(a.tipo).toBe('arrecadacao');
        expect(a.codigoBarras).toBe(ARRECADACAO_MOD10.codigo);
        expect(a.valor).toBe(89.9);
        expect(a.vencimento).toBeUndefined();
    });

    it('módulo 11 (identificador 8) traz o valor', () => {
        const a = analisarBoleto(ARRECADACAO_MOD11.linha, HOJE)!;
        expect(a.valido).toBe(true);
        expect(a.codigoBarras).toBe(ARRECADACAO_MOD11.codigo);
        expect(a.valor).toBe(250);
    });

    it('valor de referência (identificador 7) não vira dinheiro', () => {
        const a = analisarBoleto(ARRECADACAO_REFERENCIA.linha, HOJE)!;
        expect(a.valido).toBe(true);
        expect(a.valor).toBeUndefined();
    });

    it('um dígito trocado é recusado', () => {
        for (const linha of [ARRECADACAO_MOD10.linha, ARRECADACAO_MOD11.linha]) {
            expect(analisarBoleto(trocarDigito(linha, 20), HOJE)!.valido).toBe(false);
        }
    });

    it('identificador fora de 6 a 9 é recusado', () => {
        const a = analisarBoleto('825' + ARRECADACAO_MOD10.codigo.slice(3), HOJE)!;
        expect(a.valido).toBe(false);
        expect(a.erro).toMatch(/6, 7, 8 ou 9/);
    });
});

describe('analisarBoleto — entradas fora do formato', () => {
    it('vazio ou sem dígito devolve null', () => {
        expect(analisarBoleto('', HOJE)).toBeNull();
        expect(analisarBoleto(undefined, HOJE)).toBeNull();
        expect(analisarBoleto('abc', HOJE)).toBeNull();
    });

    it('comprimento errado diz quantos dígitos chegaram', () => {
        const a = analisarBoleto(BANCARIO.linha.slice(0, -5), HOJE)!;
        expect(a.valido).toBe(false);
        expect(a.erro).toMatch(/47 dígitos/);
        expect(a.erro).toMatch(/tem 42\./);
    });
});

describe('vencimentoDoFator', () => {
    it('ciclo novo: fator 1000 é 22/02/2025', () => {
        expect(vencimentoDoFator(1000, HOJE)).toBe('2025-02-22');
        expect(vencimentoDoFator(1595, HOJE)).toBe('2026-10-10');
    });

    it('ciclo antigo vale quando é o mais próximo de hoje', () => {
        expect(vencimentoDoFator(1000, new Date('2000-07-01T00:00:00Z'))).toBe('2000-07-03');
        expect(vencimentoDoFator(9999, new Date('2025-02-20T00:00:00Z'))).toBe('2025-02-21');
    });

    it('fator zero não tem vencimento', () => {
        expect(vencimentoDoFator(0, HOJE)).toBeUndefined();
    });
});

describe('larguraItf (Intercalado 2 de 5)', () => {
    it('par "12": o 1 nas barras e o 2 nos espaços', () => {
        const w = LARGA_ITF;
        expect(larguraItf('12')).toEqual([1, 1, 1, 1, w, 1, 1, w, 1, 1, 1, 1, w, w, w, 1, 1]);
    });

    it('44 dígitos dão 405 módulos com início e fim', () => {
        const larguras = larguraItf(BANCARIO.codigo);
        expect(larguras).toHaveLength(4 + 22 * 10 + 3);
        expect(larguras.reduce((a, b) => a + b, 0)).toBe(4 + 22 * 2 * (3 + 2 * LARGA_ITF) + LARGA_ITF + 2);
    });

    it('número ímpar de dígitos é erro', () => {
        expect(() => larguraItf('123')).toThrow();
    });
});

describe('descreverBoleto', () => {
    it('resume tipo, valor e vencimento', () => {
        expect(descreverBoleto(analisarBoleto(BANCARIO.linha, HOJE)!)).toBe('Boleto bancário · R$ 123,45 · vence 10/10/2026');
        expect(descreverBoleto(analisarBoleto(ARRECADACAO_REFERENCIA.linha, HOJE)!)).toBe('Conta de consumo ou tributo');
    });
});
