/**
 * A regra de espera é uma só: etapa corrente aguardando terceiro.
 */
import { describe, expect, it } from 'vitest';

import type { ResumoAcao, ResumoMatinal, Tarefa } from '../../types';
import { classificarAcoesDoDia } from './acoesDoDia';

const HOJE = '2026-10-27';

const acao = (id: string, extra: Partial<ResumoAcao> = {}): ResumoAcao => ({
    id, titulo: `Ação ${id}`, horario_inicio: null, horario_fim: null, execution_lane: 'avanco',
    degradation_count: 0, herdada: false, cobrar: false, atrasada: false, data_limite: HOJE, prazo_final: null,
    proximo_passo: null, etapas_feitas: 0, etapas_totais: 0, estrategia_objetivo_id: null,
    subtarefa_do_dia: null, aguardando_terceiro: [], ...extra,
});

const resumo = (avanco: ResumoAcao[], extra: Partial<ResumoMatinal['hoje']> = {}): ResumoMatinal =>
    ({ data: HOJE, hoje: { avanco, continuo: [], aguardando_terceiro: [], atrasadas: [], ...extra } } as ResumoMatinal);

const tarefa = (extra: Record<string, any> = {}): Tarefa =>
    ({ id: 'x', titulo: 'T', status: 'em andamento', data_limite: HOJE, plano_acao: [], ...extra } as unknown as Tarefa);

const etapa = (id: string, extra: Record<string, any> = {}) =>
    ({ id, text: `Passo ${id}`, completed: false, estado: 'pendente', ...extra });

describe('classificarAcoesDoDia', () => {
    it('sem resumo: nada', () => {
        expect(classificarAcoesDoDia(null, {}, HOJE)).toEqual({ ativas: [], emEspera: [] });
    });

    it('sem tarefa viva usa o que o resumo disse (espera pelo subtarefa_do_dia)', () => {
        const r = resumo([
            acao('a'),
            acao('b', { subtarefa_do_dia: { id: 'e', texto: 't', estado: 'aguardando_terceiro', data_prevista: null, aguardando_de: 'FAPES', degradation_count: 0 } }),
        ]);
        const { ativas, emEspera } = classificarAcoesDoDia(r, {}, HOJE);
        expect(ativas.map(a => a.id)).toEqual(['a']);
        expect(emEspera.map(a => a.id)).toEqual(['b']);
    });

    it('a espera segue a tarefa viva: o agente marcou a etapa e a ação muda de lugar sem recarregar', () => {
        const r = resumo([acao('a')]);
        expect(classificarAcoesDoDia(r, { a: tarefa({ plano_acao: [etapa('e1')] }) }, HOJE).ativas).toHaveLength(1);
        const viva = tarefa({ plano_acao: [etapa('e1', { estado: 'aguardando_terceiro', aguardando_de: 'Hildo' })] });
        const { ativas, emEspera } = classificarAcoesDoDia(r, { a: viva }, HOJE);
        expect(ativas).toEqual([]);
        expect(emEspera[0].subtarefa_do_dia?.aguardando_de).toBe('Hildo');
    });

    it('usa a etapa corrente do backend (menor data), não a primeira da lista', () => {
        const plano = [
            etapa('e1', { estado: 'aguardando_terceiro', aguardando_de: 'FAPES', data_prevista: '2026-10-30' }),
            etapa('e2', { data_prevista: '2026-10-28' }),
        ];
        const { ativas, emEspera } = classificarAcoesDoDia(resumo([acao('a')]), { a: tarefa({ plano_acao: plano }) }, HOJE);
        expect(emEspera).toEqual([]);
        expect(ativas[0].subtarefa_do_dia?.id).toBe('e2');
    });

    it('conta etapas feitas e totais a partir do plano vivo', () => {
        const plano = [etapa('e1', { completed: true, estado: 'feito' }), etapa('e2'), etapa('e3')];
        const [a] = classificarAcoesDoDia(resumo([acao('a')]), { a: tarefa({ plano_acao: plano }) }, HOJE).ativas;
        expect([a.etapas_feitas, a.etapas_totais]).toEqual([1, 3]);
    });

    it('ação concluída, excluída ou reagendada para frente sai', () => {
        const r = resumo([acao('a'), acao('b'), acao('c')]);
        const vivas = {
            a: tarefa({ status: 'concluído' }), b: tarefa({ status: 'excluído' }), c: tarefa({ data_limite: '2026-10-30' }),
        };
        expect(classificarAcoesDoDia(r, vivas, HOJE)).toEqual({ ativas: [], emEspera: [] });
    });

    it('atrasada que também está na faixa conta uma vez só', () => {
        const a = acao('a');
        expect(classificarAcoesDoDia(resumo([a], { atrasadas: [a] }), {}, HOJE).ativas).toHaveLength(1);
    });

    it('ação toda feita continua ativa (a barra do dia a conta como concluída)', () => {
        const plano = [etapa('e1', { completed: true, estado: 'feito' })];
        const { ativas } = classificarAcoesDoDia(resumo([acao('a')]), { a: tarefa({ plano_acao: plano }) }, HOJE);
        expect(ativas).toHaveLength(1);
        expect(ativas[0].subtarefa_do_dia).toBeNull();
    });
});
