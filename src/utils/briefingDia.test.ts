/**
 * Regras de leitura do briefing_dia.
 *
 * O que protege: item da IA que a origem já resolveu NÃO fica na tela só porque
 * o briefing das 05:00 ainda o lista, e o "Feito" do André sobrevive.
 */
import { describe, expect, it } from 'vitest';

import type { BriefingDecidirItem, BriefingDia } from '../../types';
import {
    agentePreparaHoje, alternarItemDecidir, descreverDias, diasEntre, focoPorAcao, origemResolvida, preparoDosProximosDias,
    prepararDecidir, resumoDecidir, type OrigemViva,
} from './briefingDia';

const item = (over: Partial<BriefingDecidirItem> = {}): BriefingDecidirItem => ({
    id: 'd1', quem: 'Enfermaria', texto: 'Converter para UNIDADE', origem: 'fila_atencao', ref: 'a1', ...over,
});

const vivoBase = (over: Partial<OrigemViva> = {}): OrigemViva => ({
    tarefas: {}, tarefasCarregadas: true, atencao: {}, ...over,
});

describe('origemResolvida', () => {
    it('ação concluída ou excluída resolve (com e sem acento)', () => {
        for (const status of ['concluído', 'concluido', 'excluído']) {
            const vivo = vivoBase({ tarefas: { t1: { status } } });
            expect(origemResolvida(item({ origem: 'acao', ref: 't1' }), vivo)).toBe(true);
        }
    });
    it('ação em andamento não resolve', () => {
        const vivo = vivoBase({ tarefas: { t1: { status: 'em andamento' } } });
        expect(origemResolvida(item({ origem: 'acao', ref: 't1' }), vivo)).toBe(false);
    });
    it('ação apagada resolve, mas só depois de a lista chegar', () => {
        expect(origemResolvida(item({ origem: 'acao', ref: 't9' }), vivoBase())).toBe(true);
        expect(origemResolvida(item({ origem: 'acao', ref: 't9' }), vivoBase({ tarefasCarregadas: false }))).toBe(false);
    });
    it('etapa feita, removida ou ação encerrada resolvem; etapa aberta não', () => {
        const plano = [
            { id: 'e1', text: 'a', completed: false, estado: 'pendente' as const },
            { id: 'e2', text: 'b', completed: true, estado: 'feito' as const },
        ];
        const vivo = vivoBase({ tarefas: { t1: { status: 'em andamento', plano_acao: plano } } });
        const etapa = (ref: string) => item({ origem: 'etapa', ref, acao_id: 't1' });
        expect(origemResolvida(etapa('e1'), vivo)).toBe(false);
        expect(origemResolvida(etapa('e2'), vivo)).toBe(true);
        expect(origemResolvida(etapa('removida'), vivo)).toBe(true);
        expect(origemResolvida(etapa('e1'), vivoBase({ tarefas: { t1: { status: 'concluído', plano_acao: plano } } }))).toBe(true);
    });
    it('item da fila resolvido ou descartado resolve; aberto, delegado ou ainda não lido não', () => {
        const com = (estado?: string | null) => vivoBase({ atencao: { a1: estado === null ? null : { estado } } });
        expect(origemResolvida(item(), com('resolvido'))).toBe(true);
        expect(origemResolvida(item(), com('descartado'))).toBe(true);
        expect(origemResolvida(item(), com('aberto'))).toBe(false);
        expect(origemResolvida(item(), com('delegado_ao_agente'))).toBe(false);
        expect(origemResolvida(item(), com(null))).toBe(false);
        expect(origemResolvida(item(), vivoBase())).toBe(false);
    });
    it('whatsapp não é conferido ao vivo', () => {
        expect(origemResolvida(item({ origem: 'whatsapp', ref: 'x' }), vivoBase())).toBe(false);
    });
});

describe('prepararDecidir', () => {
    const briefing = (decidir: BriefingDecidirItem[]): BriefingDia => ({ data: '2026-10-27', decidir });
    const tres = [
        item({ id: 'd1', ref: 'a1' }), item({ id: 'd2', ref: 'a2', quem: 'Hildo' }), item({ id: 'd3', ref: 'a3', quem: 'Raquel' }),
    ];

    it('sem briefing: nada', () => {
        expect(prepararDecidir(undefined, vivoBase())).toEqual({ linhas: [], pendentes: 0 });
        expect(prepararDecidir({ data: 'x' }, vivoBase())).toEqual({ linhas: [], pendentes: 0 });
    });

    it('mantém a ordem do briefing e numera pela posição', () => {
        const r = prepararDecidir(briefing(tres), vivoBase());
        expect(r.linhas.map(l => [l.numero, l.item.id])).toEqual([[1, 'd1'], [2, 'd2'], [3, 'd3']]);
        expect(r.pendentes).toBe(3);
    });

    it('respeita `ordem` quando vem', () => {
        const r = prepararDecidir(briefing([item({ id: 'x', ordem: 2 }), item({ id: 'y', ordem: 1 })]), vivoBase());
        expect(r.linhas.map(l => l.item.id)).toEqual(['y', 'x']);
    });

    it('feito desce, fica marcado e não conta como pendência; o número não muda', () => {
        const r = prepararDecidir(briefing([
            item({ id: 'd1', status: 'feito', resolvido_em: '2026-10-27T09:00:00Z' }), tres[1], tres[2],
        ]), vivoBase());
        expect(r.linhas.map(l => [l.item.id, l.feito, l.numero])).toEqual([
            ['d2', false, 2], ['d3', false, 3], ['d1', true, 1],
        ]);
        expect(r.pendentes).toBe(2);
    });

    it('dispensado some', () => {
        const r = prepararDecidir(briefing([item({ id: 'd1', status: 'dispensado' }), tres[1]]), vivoBase());
        expect(r.linhas.map(l => l.item.id)).toEqual(['d2']);
    });

    it('concluir a ação ou resolver o item da fila tira o item sem mexer no briefing', () => {
        const b = briefing([
            item({ id: 'd1', origem: 'acao', ref: 't1' }),
            item({ id: 'd2', origem: 'fila_atencao', ref: 'a2' }),
            item({ id: 'd3', origem: 'fila_atencao', ref: 'a3' }),
        ]);
        const antes = prepararDecidir(b, vivoBase({ tarefas: { t1: { status: 'em andamento' } }, atencao: { a2: { estado: 'aberto' }, a3: { estado: 'aberto' } } }));
        expect(antes.pendentes).toBe(3);
        const depois = prepararDecidir(b, vivoBase({ tarefas: { t1: { status: 'concluído' } }, atencao: { a2: { estado: 'resolvido' }, a3: { estado: 'aberto' } } }));
        expect(depois.linhas.map(l => l.item.id)).toEqual(['d3']);
        expect(depois.pendentes).toBe(1);
    });

    it('resumo', () => {
        expect(resumoDecidir(0)).toBe('tudo decidido');
        expect(resumoDecidir(1)).toBe('1 pendência');
        expect(resumoDecidir(3)).toBe('3 pendências');
    });
});

describe('foco, agente prepara e preparo', () => {
    it('foco por ação', () => {
        const mapa = focoPorAcao({ data: 'x', hoje: [{ acao_id: 't1', motivo: 'prazo 31/10' }, { acao_id: 't2' }] });
        expect(mapa.get('t1')).toBe('prazo 31/10');
        expect(mapa.get('t2')).toBe('');
        expect(mapa.has('t3')).toBe(false);
        expect(focoPorAcao(undefined).size).toBe(0);
    });

    it('O agente prepara hoje: só proposto/aprovado de ação viva', () => {
        const b: BriefingDia = { data: 'x', eu_faco: [
            { acao_id: 't1', texto: 'ler o relatório', status: 'proposto' },
            { acao_id: 't2', texto: 'pronto', status: 'pronto' },
            { acao_id: 't3', texto: 'ação encerrada', status: 'aprovado' },
            { acao_id: 't4', texto: 'recusado', status: 'recusado' },
        ] };
        const vivo = vivoBase({ tarefas: {
            t1: { status: 'em andamento', titulo: 'Sispnaes' }, t2: { status: 'em andamento' },
            t3: { status: 'concluído' }, t4: { status: 'em andamento' },
        } });
        expect(agentePreparaHoje(b, vivo)).toEqual([{ acaoId: 't1', acao: 'Sispnaes', texto: 'ler o relatório' }]);
    });

    it('Preparo: só dias depois de hoje, em ordem, até 3, com o "em N dias" calculado', () => {
        const b: BriefingDia = { data: 'x', preparo: [
            { dia: '2026-10-30', texto: 'folga' }, { dia: '2026-10-27', texto: 'hoje não conta' },
            { dia: '2026-10-28', texto: 'retirar o carro' }, { dia: '2026-10-29', texto: 'devolver' },
            { dia: '2026-11-02', texto: 'corte' }, { dia: 'ontem', texto: 'inválido' },
        ] };
        const itens = preparoDosProximosDias(b, '2026-10-27');
        expect(itens.map(i => [i.rotulo, i.data, i.texto])).toEqual([
            ['Qua', '28/10', 'retirar o carro'], ['Qui', '29/10', 'devolver'], ['Sex', '30/10', 'folga'],
        ]);
        expect(itens.every(i => !('dias' in i))).toBe(true);
    });

    it('dias entre datas e rótulo', () => {
        expect(diasEntre('2026-10-27', '2026-10-31')).toBe(4);
        expect(diasEntre('2026-10-27', '2026-10-26')).toBe(-1);
        expect(descreverDias(0)).toBe('hoje');
        expect(descreverDias(1)).toBe('amanhã');
        expect(descreverDias(4)).toBe('em 4 dias');
        expect(descreverDias(-1)).toBe('venceu ontem');
        expect(descreverDias(-3)).toBe('venceu há 3 dias');
    });
});

describe('alternarItemDecidir — o Feito do André', () => {
    const lista = [
        { id: 'd1', quem: 'A', texto: 'x', origem: 'acao' as const, ref: 't1', status: 'pendente' as const, resolvido_em: null },
        { id: 'd2', quem: 'B', texto: 'y', origem: 'acao' as const, ref: 't2' },
    ];
    it('marca feito com a hora e mexe só nesse item', () => {
        const novo = alternarItemDecidir(lista, 'd1', '2026-10-27T09:00:00.000Z');
        expect(novo[0]).toMatchObject({ status: 'feito', resolvido_em: '2026-10-27T09:00:00.000Z' });
        expect(novo[1]).toBe(lista[1]);
    });
    it('Desfazer volta a pendente e limpa a hora', () => {
        const feito = alternarItemDecidir(lista, 'd2', '2026-10-27T09:00:00.000Z');
        const desfeito = alternarItemDecidir(feito, 'd2', '2026-10-27T10:00:00.000Z');
        expect(desfeito[1]).toMatchObject({ status: 'pendente', resolvido_em: null });
    });
    it('id desconhecido não muda nada', () => {
        expect(alternarItemDecidir(lista, 'zz', 'x')).toEqual(lista);
    });
});
