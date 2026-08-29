import { describe, it, expect } from 'vitest';
import { bolso, resumoDoBolso, centavos, numero } from './bolsoAquisicoes';

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

// A MESMA tabela existe em `functions/test_bolso_aquisicoes.py`. Se um lado
// mudar de gramática, o outro quebra — a única defesa que este módulo tem contra
// as duas linguagens divergirem em silêncio.
//
// Cada linha é um texto que UMA das duas linguagens aceitaria sozinha e a outra
// não, ou que as duas aceitariam com resultados diferentes:
//   '0x1'       Number dá 1,   float levanta
//   '1_0'       float dá 10,   Number dá NaN
//   'NaN'       float dá nan,  e math.floor levanta e derruba a tool
//   'Infinity'  float dá inf,  Number dá Infinity — nenhum dos dois serve
//   '1e400'     os dois dão infinito sem erro
//   'abc'       float levanta sem ninguém pegar
const GRAMATICA_RECUSA: unknown[] = ['0x1', '1_0', 'NaN', 'Infinity', '1e400', 'abc',
    '', '  ', 'R$ 5', '5,5', null, true, false];
const GRAMATICA_ACEITA: [unknown, number][] = [['500', 500], [' 2 ', 2], ['+2', 2],
    ['-3', -3], ['.5', 0.5], ['5.', 5], ['1e3', 1000], [500, 500], [2.5, 2.5], [0, 0]];

describe('uma gramática só', () => {
    // `Number()` e `float()` aceitam conjuntos diferentes de texto, e o Firestore
    // não tipa o que grava. Enquanto a coerção fosse a nativa de cada linguagem,
    // "uma regra nos dois lados" era só uma frase.

    it('o que a gramática recusa vira o padrão', () => {
        for (const bruto of GRAMATICA_RECUSA) {
            expect(numero(bruto), String(bruto)).toBe(0);
            expect(numero(bruto, 99), String(bruto)).toBe(99);
        }
    });

    it('o que a gramática aceita é o mesmo número', () => {
        for (const [bruto, esperado] of GRAMATICA_ACEITA) {
            expect(numero(bruto), String(bruto)).toBe(esperado);
        }
    });

    it('dinheiro mal gravado não vira NaN', () => {
        // Do lado Python isso levantava e derrubava a tool; deste lado o NaN se
        // propagava em silêncio e contaminava o cofre inteiro.
        for (const bruto of GRAMATICA_RECUSA) {
            expect(centavos(bruto), String(bruto)).toBe(0);
        }
    });

    it('conta mal gravada não contamina o cofre', () => {
        const settings = { emergencyReserveCurrent: 0, emergencyReserveTarget: 0,
                           investmentReserveCurrent: 100 };
        const contas = [
            { category: 'Poupança', amount: 'NaN' as any, isPaid: true },
            { category: 'Poupança', amount: '50' as any, isPaid: true },
        ];
        expect(bolso(settings, contas)).toBe(150);
    });
});

describe('empate de prioridade', () => {
    // O mesmo caso de `functions/test_bolso_aquisicoes.py`. Duas metas de mesma
    // `priority` ficavam na ordem de ENTRADA, e os dois lados recebem a lista de
    // fontes diferentes — o MCP do Firestore, a tela do snapshot.

    const SETTINGS = { emergencyReserveCurrent: 0, emergencyReserveTarget: 0, investmentReserveCurrent: 1000 };
    const cabe = (metas: any[]) =>
        Object.fromEntries(resumoDoBolso(metas, SETTINGS, []).metas.map(m => [m.id, m.cabeNaFila]));

    it('a ordem de entrada não muda quem cabe', () => {
        const metas = [
            { id: 'z', targetAmount: 600, priority: 2, status: 'active' },
            { id: 'a', targetAmount: 600, priority: 2, status: 'active' },
        ];
        expect(cabe(metas)).toEqual(cabe([...metas].reverse()));
    });

    it('o desempate é pelo id e é estável', () => {
        const metas = [
            { id: 'z', targetAmount: 600, priority: 2, status: 'active' },
            { id: 'a', targetAmount: 600, priority: 2, status: 'active' },
        ];
        expect(cabe(metas)).toEqual({ a: true, z: false });
    });

    it('caixa mista desempata por ordinal, e não por locale', () => {
        // O caso que `localeCompare` errava: ele põe 'a' antes de 'B', e o Python
        // põe 'B' antes de 'a'. Id do Firestore mistura as duas caixas, então com
        // o bolso cobrindo só uma das metas cada lado apontaria uma diferente.
        // Os MESMOS ids e números estão no arquivo espelho.
        const metas = [
            { id: 'a1', targetAmount: 600, priority: 2, status: 'active' },
            { id: 'B1', targetAmount: 600, priority: 2, status: 'active' },
        ];
        expect(cabe(metas)).toEqual({ B1: true, a1: false });
    });

    it('a ordem devolvida é a ordem em que a fila foi avaliada', () => {
        // Se o consumidor reordenasse por fora, os selos de "cabe" apareceriam
        // fora de ordem em relação à lista lida. O módulo devolve ordenado.
        const metas = [
            { id: 'a1', targetAmount: 600, priority: 2, status: 'active' },
            { id: 'B1', targetAmount: 600, priority: 2, status: 'active' },
            { id: 'z', targetAmount: 600, priority: 1, status: 'active' },
        ];
        expect(resumoDoBolso(metas, SETTINGS, []).metas.map(m => m.id))
            .toEqual(['z', 'B1', 'a1']);
    });

    it('prioridade inválida cai para o fim, como no Python', () => {
        // O mesmo caso do arquivo espelho, com os MESMOS ids. `?? 99` cobria
        // null e ausente e deixava passar os dois que importam: `'alta' - 1` dá
        // NaN, o comparador devolve NaN e o `sort` não troca nada; e `'' - 1` dá
        // -1, mandando a meta sem prioridade para o PRIMEIRO lugar. O Python
        // levanta ValueError nos dois e cai para 99. `'2'` não serve de fixture
        // aqui: o JavaScript coage numericamente e os dois lados concordam.
        const metas = [
            { id: 'nan', targetAmount: 600, priority: 'NaN' as any, status: 'active' },
            { id: 'vazio', targetAmount: 600, priority: '' as any, status: 'active' },
            { id: 'alta', targetAmount: 600, priority: 'alta' as any, status: 'active' },
            { id: 'inf', targetAmount: 600, priority: 'Infinity' as any, status: 'active' },
            { id: 'nulo', targetAmount: 600, priority: null as any, status: 'active' },
            { id: 'um', targetAmount: 600, priority: 1, status: 'active' },
        ];
        expect(resumoDoBolso(metas, SETTINGS, []).metas.map(m => m.id))
            .toEqual(['um', 'alta', 'inf', 'nan', 'nulo', 'vazio']);
    });

    it('prioridade ausente vai para o fim', () => {
        const metas = [
            { id: 'sem', targetAmount: 600, status: 'active' },
            { id: 'com', targetAmount: 600, priority: 1, status: 'active' },
        ];
        expect(cabe(metas)).toEqual({ com: true, sem: false });
    });
});

describe('dinheiro não é float', () => {
    // Os MESMOS casos de `functions/test_bolso_aquisicoes.py`. Se um lado mudar
    // de convenção, o outro quebra.

    it('fronteira exata não vira "não cabe"', () => {
        // 0,10 + 0,70 dá 0.7999999999999999 em float; a meta de 0,80 cabe.
        const settings = { emergencyReserveCurrent: 0, emergencyReserveTarget: 0, investmentReserveCurrent: 0.1 };
        const contas = [{ category: 'Poupança', amount: 0.7, isPaid: true }];
        const metas = [{ id: 'x', targetAmount: 0.8, priority: 1, status: 'active' }];
        const r = resumoDoBolso(metas, settings, contas);
        expect(r.bolso).toBe(0.8);
        expect(r.metas[0].coberturaPct).toBe(100);
        expect(r.metas[0].cabeNaFila).toBe(true);
        expect(r.itensQueCabem).toBe(1);
    });

    it('empate no arredondamento vai para cima', () => {
        // `round` do Python iria para PAR e o JavaScript para cima: 12,25 -> 12,3.
        const settings = { emergencyReserveCurrent: 0, emergencyReserveTarget: 0, investmentReserveCurrent: 49 };
        const metas = [{ id: 'x', targetAmount: 400, priority: 1, status: 'active' }];
        expect(resumoDoBolso(metas, settings, []).metas[0].coberturaPct).toBe(12.3);
    });

    it('centavos arredondam meio-para-cima', () => {
        expect(centavos(0.005)).toBe(1);
        expect(centavos(0.015)).toBe(2);
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
