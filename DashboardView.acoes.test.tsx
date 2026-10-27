/**
 * "Ações de hoje": o selo do executor, o contador "N etapas para o agente", o
 * filtro "Só o que o agente faz" e a correção do André pelo menu da etapa.
 *
 * O resumo das 05:00 define o conjunto de ações; a tarefa viva (onSnapshot) é a
 * fonte do plano. O contador é calculado a cada leitura — se o agente marcar a
 * etapa como feita, o número muda sem recarregar. Firebase é mockado.
 */
// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import { formatDateLocalISO } from './types';

const hoje = formatDateLocalISO(new Date());

const armazem: Record<string, any> = {};
const ouvintes: Record<string, Array<(snap: any) => void>> = {};
const atualizacoes: Array<{ ref: string; dados: any }> = [];

const chave = (ref: any) => `${ref.col}/${ref.id}`;
const snapDe = (ref: any) => ({
    exists: () => armazem[chave(ref)] !== undefined,
    id: ref.id,
    data: () => armazem[chave(ref)],
});

vi.mock('./firebase', () => ({ db: {}, functions: {} }));
vi.mock('firebase/firestore', () => ({
    arrayUnion: vi.fn(),
    collection: vi.fn(() => ({})),
    query: vi.fn(),
    where: vi.fn(),
    updateDoc: vi.fn(),
    getDoc: vi.fn((ref: any) => Promise.resolve(snapDe(ref))),
    doc: vi.fn((_db: any, col: string, id: string) => ({ col, id })),
    onSnapshot: vi.fn((ref: any, onNext: any) => {
        const k = chave(ref);
        (ouvintes[k] ||= []).push(onNext);
        onNext(snapDe(ref));
        return () => {
            ouvintes[k] = (ouvintes[k] || []).filter(f => f !== onNext);
        };
    }),
    runTransaction: vi.fn(async (_db: any, fn: any) =>
        fn({
            get: async (ref: any) => snapDe(ref),
            update: (ref: any, dados: any) => {
                atualizacoes.push({ ref: chave(ref), dados });
                armazem[chave(ref)] = { ...armazem[chave(ref)], ...dados };
            },
        })),
}));

import { AcoesDoDiaCard } from './DashboardView';

const emitir = (k: string) => (ouvintes[k] || []).forEach(f => f(snapDe({ col: k.split('/')[0], id: k.split('/')[1] })));

const resumoAcao = (id: string, titulo: string, extra: Record<string, any> = {}) => ({
    id, titulo, horario_inicio: null, horario_fim: null, execution_lane: 'avanco', degradation_count: 0,
    herdada: false, cobrar: false, atrasada: false, data_limite: hoje, prazo_final: null, proximo_passo: null,
    etapas_feitas: 0, etapas_totais: 3, estrategia_objetivo_id: null, subtarefa_do_dia: null,
    aguardando_terceiro: [], ...extra,
});

const etapa = (id: string, text: string, extra: Record<string, any> = {}) => ({
    id, text, completed: false, estado: 'pendente', ...extra,
});

const planoSispnaes = () => [
    etapa('s1', 'Ler o relatório de lições aprendidas', {
        executor: 'agente', executor_como: 'Ler e montar a versão executiva', executor_definido_por: 'agente',
    }),
    etapa('s2', 'Escrever a mensagem à DAE', { executor: 'agente_aprovado', executor_definido_por: 'agente' }),
    etapa('s3', 'Entregar à DAE'),
];

beforeEach(() => {
    for (const k of Object.keys(armazem)) delete armazem[k];
    for (const k of Object.keys(ouvintes)) delete ouvintes[k];
    atualizacoes.length = 0;
    armazem[`resumo_matinal/${hoje}`] = {
        data: hoje,
        hoje: {
            avanco: [resumoAcao('sisp', 'Sispnaes'), resumoAcao('pagto', 'Folha de pagamento')],
            continuo: [], atrasadas: [], aguardando_terceiro: [],
        },
    };
    armazem['tarefas/sisp'] = { titulo: 'Sispnaes', status: 'em andamento', data_limite: hoje, plano_acao: planoSispnaes() };
    armazem['tarefas/pagto'] = {
        titulo: 'Folha de pagamento', status: 'em andamento', data_limite: hoje,
        plano_acao: [etapa('p1', 'Conferir a folha'), etapa('p2', 'Assinar')],
    };
});
afterEach(cleanup);

const abrir = (titulo: string) => fireEvent.click(screen.getByTitle(titulo));

describe('AcoesDoDiaCard — executor da etapa', () => {
    it('mostra o contador só nas ações com etapa em aberto para o agente', () => {
        render(<AcoesDoDiaCard />);
        const contadores = screen.getAllByTestId('contador-agente');
        expect(contadores).toHaveLength(1);
        expect(contadores[0]).toHaveTextContent('2 etapas para o agente');
    });

    it('usa o singular com uma etapa', () => {
        armazem['tarefas/sisp'].plano_acao[1] = { ...armazem['tarefas/sisp'].plano_acao[1], executor: undefined };
        render(<AcoesDoDiaCard />);
        expect(screen.getByTestId('contador-agente')).toHaveTextContent('1 etapa para o agente');
    });

    it('o contador muda sem recarregar quando o agente conclui uma etapa', () => {
        render(<AcoesDoDiaCard />);
        expect(screen.getByTestId('contador-agente')).toHaveTextContent('2 etapas');
        act(() => {
            armazem['tarefas/sisp'] = {
                ...armazem['tarefas/sisp'],
                plano_acao: armazem['tarefas/sisp'].plano_acao.map((e: any) =>
                    e.id === 's1' ? { ...e, estado: 'feito', completed: true } : e),
            };
            emitir('tarefas/sisp');
        });
        expect(screen.getByTestId('contador-agente')).toHaveTextContent('1 etapa para o agente');
    });

    it('a etapa do agente leva etiqueta e a frase de como; a só do André fica sem selo', () => {
        render(<AcoesDoDiaCard />);
        abrir('Sispnaes');
        const linhaDe = (texto: string) => screen.getByText(texto).parentElement!;
        expect(within(linhaDe('Ler o relatório de lições aprendidas')).getByTestId('etiqueta-executor'))
            .toHaveTextContent('Agente faz');
        expect(within(linhaDe('Escrever a mensagem à DAE')).getByTestId('etiqueta-executor'))
            .toHaveTextContent('Agente prepara, você aprova');
        expect(screen.getByText('Ler e montar a versão executiva')).toBeInTheDocument();
        expect(within(linhaDe('Entregar à DAE')).queryByTestId('etiqueta-executor')).toBeNull();
    });

    it('"Só o que o agente faz" abre as ações e mostra só essas etapas, escondendo as sem etapa do agente', () => {
        render(<AcoesDoDiaCard />);
        const filtro = screen.getByRole('button', { name: 'Só o que o agente faz' });
        expect(filtro).toHaveAttribute('aria-pressed', 'false');
        fireEvent.click(filtro);
        expect(filtro).toHaveAttribute('aria-pressed', 'true');
        expect(screen.getByText('Ler o relatório de lições aprendidas')).toBeInTheDocument();
        expect(screen.getByText('Escrever a mensagem à DAE')).toBeInTheDocument();
        expect(screen.queryByText('Entregar à DAE')).toBeNull();
        expect(screen.queryByTitle('Folha de pagamento')).toBeNull();
        fireEvent.click(filtro);
        expect(screen.getByTitle('Folha de pagamento')).toBeInTheDocument();
    });

    it('o menu da etapa grava a correção do André como "usuario" e preserva as outras etapas', async () => {
        render(<AcoesDoDiaCard />);
        abrir('Sispnaes');
        fireEvent.click(screen.getByRole('button', { name: 'Quem executa: Entregar à DAE' }));
        await act(async () => {
            fireEvent.click(screen.getByRole('menuitemradio', { name: 'Agente faz' }));
        });
        expect(atualizacoes).toHaveLength(1);
        const plano = atualizacoes[0].dados.plano_acao;
        const entregar = plano.find((e: any) => e.id === 's3');
        expect(entregar.executor).toBe('agente');
        expect(entregar.executor_definido_por).toBe('usuario');
        expect(plano.find((e: any) => e.id === 's1').executor_como).toBe('Ler e montar a versão executiva');
        expect(plano).toHaveLength(3);
    });

    it('marcar como "só você" grava humano explícito (a marca precisa sobreviver)', async () => {
        render(<AcoesDoDiaCard />);
        abrir('Sispnaes');
        fireEvent.click(screen.getByRole('button', { name: 'Quem executa: Ler o relatório de lições aprendidas' }));
        await act(async () => {
            fireEvent.click(screen.getByRole('menuitemradio', { name: 'Só você' }));
        });
        const s1 = atualizacoes[0].dados.plano_acao.find((e: any) => e.id === 's1');
        expect(s1.executor).toBe('humano');
        expect(s1.executor_definido_por).toBe('usuario');
        expect(s1.executor_como).toBeUndefined();
    });
});
