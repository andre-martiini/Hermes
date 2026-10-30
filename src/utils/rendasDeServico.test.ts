import { describe, expect, it } from 'vitest';
import type { IncomeEntry, ParcelaServico, Servico } from '../../types';
import { dataDaParcela, idRendaServico, planejarRendasDeServicos, type PlanoRendasDeServicos } from './rendasDeServico';

// Brasília é onde a data virava 31/10: o teste só protege se o fuso for UTC-3.
process.env.TZ = 'America/Sao_Paulo';

const AGORA = new Date('2026-10-30T10:59:22.044Z');

const parcela = (id: string, data: string, status: ParcelaServico['status'] = 'pendente'): ParcelaServico =>
    ({ id, descricao: `Parcela ${id}`, valor: 3500, data_prevista: data, status });

const servico = (parcelas: ParcelaServico[], extras: Partial<Servico> = {}): Servico =>
    ({ id: 'svc1', titulo: 'Clínica Integrare', status: 'Ativo', parcelas, ...extras }) as Servico;

const renda = (id: string, parcelaId: string, extras: Partial<IncomeEntry> = {}): IncomeEntry => ({
    id, parcela_id: parcelaId, service_id: 'svc1', description: `Clínica Integrare - Parcela ${parcelaId}`,
    amount: 3500, day: 1, month: 10, year: 2026, category: 'Serviço Particular', isReceived: false, status: 'active',
    ...extras,
});

const vazio = (plano: PlanoRendasDeServicos) =>
    plano.criar.length === 0 && plano.atualizar.length === 0 && plano.retirar.length === 0;

/** Aplica o plano numa lista, como o Firestore faria, para provar que replanejar não muda mais nada. */
const aplicar = (rendas: IncomeEntry[], plano: PlanoRendasDeServicos): IncomeEntry[] => {
    const lista = rendas.map(r => ({ ...r }));
    plano.criar.forEach(({ id, dados }) => { if (!lista.some(r => r.id === id)) lista.push({ id, ...dados }); });
    plano.atualizar.forEach(({ id, dados }) => Object.assign(lista.find(r => r.id === id)!, dados));
    plano.retirar.forEach(id => Object.assign(lista.find(r => r.id === id)!, { status: 'deleted', retirada_por: 'previsao' }));
    return lista;
};

describe('dataDaParcela', () => {
    it('lê o texto, sem passar pelo fuso: 1º de novembro continua em novembro', () => {
        expect(dataDaParcela('2026-11-01')).toEqual({ year: 2026, month: 10, day: 1 });
        expect(dataDaParcela('2026-11-01T00:00:00.000Z')).toEqual({ year: 2026, month: 10, day: 1 });
        // O que a sincronia antiga fazia, em Brasília:
        const antigo = new Date('2026-11-01T00:00:00.000Z');
        expect([antigo.getMonth(), antigo.getDate()]).toEqual([9, 31]);
    });

    it('data vazia ou impossível é sem data', () => {
        for (const ruim of ['', undefined, 'abc', '2026-02-30', '2026-13-01']) expect(dataDaParcela(ruim)).toBeNull();
    });
});

describe('planejarRendasDeServicos', () => {
    it('cria a renda na competência da parcela, com id fixo (Integrare: 01/11 não vira 31/10)', () => {
        const plano = planejarRendasDeServicos([servico([parcela('p1', '2026-11-01T00:00:00.000Z')])], [], AGORA);
        expect(plano.criar).toHaveLength(1);
        expect(plano.criar[0].id).toBe(idRendaServico('svc1', 'p1'));
        expect(plano.criar[0].dados).toMatchObject({ month: 10, year: 2026, day: 1, status: 'active', isReceived: false,
            data_criacao: '2026-10-30T10:59:22.044Z' });
    });

    it('renda excluída pelo usuário não é recriada nem reativada', () => {
        const excluida = renda('x', 'p1', { status: 'deleted' });
        const plano = planejarRendasDeServicos([servico([parcela('p1', '2026-11-01')])], [excluida], AGORA);
        expect(vazio(plano)).toBe(true);
    });

    it('com a cópia excluída ao lado da ativa, só atualiza a ativa', () => {
        const rendas = [renda('x', 'p1', { status: 'deleted' }), renda('y', 'p1', { amount: 100 })];
        const plano = planejarRendasDeServicos([servico([parcela('p1', '2026-11-01')])], rendas, AGORA);
        expect(plano.criar).toEqual([]);
        expect(plano.atualizar.map(a => a.id)).toEqual(['y']);
    });

    it('vários clientes com a mesma lista velha criam no máximo uma renda ativa', async () => {
        const contrato = [servico([parcela('p1', '2026-11-01'), parcela('p1', '2026-11-01')])]; // até a parcela repetida
        const banco = new Map<string, unknown>();
        const cliente = async () => {
            // Mesma foto do banco (vazia) para todos, como duas abas que abrem juntas.
            const plano = planejarRendasDeServicos(contrato, [], AGORA);
            await Promise.resolve();
            plano.criar.forEach(({ id, dados }) => { if (!banco.has(id)) banco.set(id, dados); }); // create-if-not-exists
        };
        await Promise.all(Array.from({ length: 6 }, cliente));
        expect([...banco.keys()]).toEqual([idRendaServico('svc1', 'p1')]);
    });

    it('excluir e sincronizar em paralelo várias vezes resulta em zero rendas ativas', async () => {
        const banco: IncomeEntry[] = [renda('x', 'p1', { status: 'deleted' })];
        const contrato = [servico([parcela('p1', '2026-11-01')])];
        const cliente = async () => {
            const plano = planejarRendasDeServicos(contrato, banco.map(r => ({ ...r })), AGORA);
            await Promise.resolve();
            plano.criar.forEach(({ id, dados }) => { if (!banco.some(r => r.id === id)) banco.push({ id, ...dados }); });
        };
        await Promise.all(Array.from({ length: 6 }, cliente));
        expect(banco.filter(r => r.status !== 'deleted')).toEqual([]);
    });

    it('parcela sem_previsao tira a renda ativa e não cria outra', () => {
        const contrato = [servico([parcela('p1', '2026-11-01', 'sem_previsao')])];
        expect(planejarRendasDeServicos(contrato, [renda('y', 'p1')], AGORA)).toEqual({ criar: [], atualizar: [], retirar: ['y'] });
        expect(vazio(planejarRendasDeServicos(contrato, [], AGORA))).toBe(true);
    });

    it('parcela pendente sem data sai da renda do mês; paga sem data fica como está', () => {
        const sem = [servico([parcela('p1', ''), parcela('p2', '', 'pago')])];
        const plano = planejarRendasDeServicos(sem, [renda('a', 'p1'), renda('b', 'p2', { isReceived: true })], AGORA);
        expect(plano).toEqual({ criar: [], atualizar: [], retirar: ['a'] });
    });

    it('a renda que a previsão tirou volta com a parcela; exclusão do usuário e duplicata não', () => {
        const contrato = [servico([parcela('p1', '2026-11-01'), parcela('p2', '2026-12-01'), parcela('p3', '2027-01-01')])];
        const rendas = [
            renda('a', 'p1', { status: 'deleted', retirada_por: 'previsao' }),
            renda('b', 'p2', { status: 'deleted' }),
            renda('c', 'p3', { status: 'deleted', retirada_por: 'duplicata', duplicata_de: 'z' }),
        ];
        const plano = planejarRendasDeServicos(contrato, rendas, AGORA);
        expect(plano.criar).toEqual([]);
        expect(plano.atualizar).toHaveLength(1);
        expect(plano.atualizar[0]).toMatchObject({ id: 'a', dados: { status: 'active', retirada_por: null, month: 10 } });
    });

    it('parcela que sumiu ou contrato pausado retira a renda ativa', () => {
        const rendas = [renda('a', 'p1'), renda('b', 'sumiu')];
        const pausado = planejarRendasDeServicos([servico([parcela('p1', '2026-11-01')], { status: 'Em Pausa' })], rendas, AGORA);
        expect(pausado.retirar.sort()).toEqual(['a', 'b']);
        const sumiu = planejarRendasDeServicos([servico([parcela('p1', '2026-11-01')])], rendas, AGORA);
        expect(sumiu.retirar).toEqual(['b']);
    });

    it('corrige o dia e a competência que a sincronia antiga gravou em Brasília', () => {
        const errada = renda('i', 'p1', { month: 9, day: 31 });
        const plano = planejarRendasDeServicos([servico([parcela('p1', '2026-11-01T00:00:00.000Z')])], [errada], AGORA);
        expect(plano.atualizar).toEqual([expect.objectContaining({ id: 'i', dados: expect.objectContaining({ month: 10, day: 1 }) })]);
    });

    it('converge: depois de aplicar o plano, replanejar não muda mais nada', () => {
        const contrato = [servico([
            parcela('p1', '2026-11-01'), parcela('p2', '2026-12-01', 'sem_previsao'), parcela('p3', '2027-01-01', 'pago'),
        ])];
        const inicio = [renda('a', 'p1', { amount: 1 }), renda('b', 'p2'), renda('c', 'velha')];
        const depois = aplicar(inicio, planejarRendasDeServicos(contrato, inicio, AGORA));
        expect(vazio(planejarRendasDeServicos(contrato, depois, AGORA))).toBe(true);
        expect(depois.filter(r => r.status !== 'deleted').map(r => r.parcela_id).sort()).toEqual(['p1', 'p3']);
    });
});
