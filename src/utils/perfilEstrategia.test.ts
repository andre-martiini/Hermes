import { describe, expect, it } from 'vitest';
import F from './perfilEstrategia.fixture.json';
import { avaliarMeta, esperadoEm, hojeBrasilia, idLegado, type MetaPerfil } from './perfilEstrategia';
import { guardadoAcumulado } from './bolsoAquisicoes';

/** A fixture é a MESMA de `functions/test_perfil_estrategia.py`: os dois lados têm de dar o mesmo número. */
const metas = F.metas as unknown as Record<string, MetaPerfil>;

describe('perfil das metas — fixture compartilhada com o Python', () => {
    for (const caso of F.casos as any[]) {
        it(caso.nome, () => {
            const r = avaliarMeta(metas[caso.meta], caso.atuais, caso.hoje);
            expect(r.estado).toBe(caso.estado);
            expect(r.proximo_marco?.data ?? null).toBe(caso.proximo_marco);
            const porChave = Object.fromEntries(r.indicadores.map(i => [i.chave, i]));
            if (caso.indicadores) expect(Object.keys(porChave).sort()).toEqual(Object.keys(caso.indicadores).sort());
            for (const [chave, esperado] of Object.entries<any>(caso.indicadores ?? {})) {
                expect(porChave[chave].esperado_hoje).toBe(esperado.esperado_hoje);
                expect(porChave[chave].estado).toBe(esperado.estado);
                if ('atual' in esperado) expect(porChave[chave].atual).toBe(esperado.atual);
                if ('proximo_valor' in esperado) expect(porChave[chave].proximo_marco?.valor ?? null).toBe(esperado.proximo_valor);
            }
            if (caso.marcos_sem_numero) {
                expect(Object.fromEntries(r.marcos_sem_numero.map(m => [m.id, m.estado]))).toEqual(caso.marcos_sem_numero);
            }
        });
    }

    it('hoje em Brasília na virada UTC', () => {
        for (const caso of F.hoje_brasilia) expect(hojeBrasilia(new Date(caso.utc))).toBe(caso.hoje);
    });

    it('hoje inválido é recusado, como no Python', () => {
        for (const hoje of F.hoje_invalido) expect(() => avaliarMeta(metas.saude, { peso: 90 }, hoje as string)).toThrow();
    });

    it('guardado acumulado: a mesma regra do bolso, igual ao Python', () => {
        for (const caso of F.guardado_acumulado.casos) {
            expect(guardadoAcumulado(F.guardado_acumulado.contas as any[], caso.desde)).toBe(caso.centavos);
        }
        expect(guardadoAcumulado([], '2026-11-02')).toBe(0);
    });

    it('id de item legado é estável e igual ao do Python', () => {
        for (const caso of F.id_legado) expect(idLegado(caso.tipo, caso.indice, caso.descricao)).toBe(caso.id);
    });
});

describe('perfil das metas — regras', () => {
    it('dinheiro sai em centavos inteiros', () => {
        const guardado = avaliarMeta(metas.financeira, { guardado: '1234.565' }, '2026-12-15').indicadores[0];
        expect(Number.isInteger(guardado.atual)).toBe(true);
        expect(Number.isInteger(guardado.esperado_hoje)).toBe(true);
        expect(guardado.atual).toBe(123457);
    });

    it('valor ilegível é sem_dado, nunca zero', () => {
        for (const ruim of [null, undefined, '', 'abc', 'NaN', true]) {
            const peso = avaliarMeta(metas.saude, { peso: ruim, cintura: 107 }, '2026-12-15').indicadores[0];
            expect([peso.estado, peso.atual]).toEqual(['sem_dado', null]);
        }
    });

    it('data com hora é lida pelo texto, sem deslocar para o dia anterior', () => {
        const meta = { ...metas.saude, ciclo: { inicio: '2026-11-02T00:00:00.000Z', fim: '2027-01-30' } };
        expect(esperadoEm(meta, meta.indicadores![0], '2026-12-15T23:59:00-03:00')).toBe(9080);
    });

    it('alvo final fecha o ciclo quando nenhum marco tem número', () => {
        const meta: MetaPerfil = { ciclo: { inicio: '2026-11-02', fim: '2027-01-30' }, indicadores: [{ chave: 'peso', inicial: 93.4, alvoFinal: 88 }] };
        expect(esperadoEm(meta, meta.indicadores![0], '2027-01-30')).toBe(8800);
        expect(esperadoEm(meta, meta.indicadores![0], '2026-11-02')).toBe(9340);
    });
});

describe('valor atual de cada indicador, como no resumo do servidor', () => {
    it('peso da medição, guardado da poupança, manual do histórico', async () => {
        const { atuaisDaMeta } = await import('./perfilEstrategia');
        const meta = {
            ciclo: { inicio: '2026-11-02', fim: '2027-01-30' },
            indicadores: [
                { chave: 'peso', fonte: 'peso' as const },
                { chave: 'guardado', fonte: 'guardado_acumulado' as const },
                { chave: 'renda_produto', fonte: 'manual' as const },
            ],
            historicoMetrica: [{ data: '2026-12-01', valor: 150 }, { data: '2026-11-15', valor: 90 }],
        };
        const r = atuaisDaMeta(meta, { peso: 90.5 }, desde => (desde === '2026-11-02' ? 100000 : null));
        expect(r.atuais).toEqual({ peso: 90.5, guardado: 1000, renda_produto: 150 });
        expect(r.origens).toEqual({ peso: 'automatica', guardado: 'automatica', renda_produto: 'manual' });
        expect(atuaisDaMeta(meta, {}, () => null).atuais).toEqual({ peso: null, guardado: null, renda_produto: 150 });
    });
});
