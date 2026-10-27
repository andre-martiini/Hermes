/**
 * Painel do dia: a tela inteira, com e sem `briefing_dia`.
 *
 * O que protege: (1) sem briefing a tela abre normal, sem os blocos novos e sem
 * erro; (2) item da IA some quando a origem é resolvida, sem recarregar; (3) o
 * Feito do André grava só `decidir`; (4) agenda e espera vêm das fontes vivas.
 * Firebase é mockado; o relógio é o do Vitest.
 */
// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';

const HOJE = '2026-10-27';

const armazem: Record<string, any> = {};
const ouvintes: Array<{ alvo: any; cb: (s: any) => void }> = [];
const gravacoes: Array<{ ref: string; dados: any }> = [];

const chave = (ref: any) => `${ref.col}/${ref.id}`;
const snapDoc = (ref: any) => ({ exists: () => armazem[chave(ref)] !== undefined, id: ref.id, data: () => armazem[chave(ref)] });
const snapQuery = (q: any) => {
    const docs = Object.entries(armazem)
        .filter(([k]) => k.startsWith(`${q.col}/`))
        .map(([k, v]) => ({ id: k.split('/')[1], data: () => v }))
        .filter(d => (q.clausulas || []).every((c: any) => {
            const valor = String(d.data()[c.campo] ?? '');
            return c.op === '>=' ? valor >= c.valor : c.op === '<' ? valor < c.valor : valor === c.valor;
        }));
    return { docs };
};
const notificar = () => ouvintes.forEach(({ alvo, cb }) => cb(alvo.clausulas ? snapQuery(alvo) : snapDoc(alvo)));

vi.mock('./firebase', () => ({ db: {}, functions: {} }));
vi.mock('firebase/firestore', () => ({
    arrayUnion: vi.fn(), updateDoc: vi.fn(), getDoc: vi.fn((ref: any) => Promise.resolve(snapDoc(ref))),
    collection: vi.fn((_db: any, col: string) => ({ col })),
    where: vi.fn((campo: string, op: string, valor: string) => ({ campo, op, valor })),
    query: vi.fn((c: any, ...clausulas: any[]) => ({ col: c.col, clausulas })),
    doc: vi.fn((_db: any, col: string, id: string) => ({ col, id })),
    onSnapshot: vi.fn((alvo: any, cb: any) => {
        const reg = { alvo, cb };
        ouvintes.push(reg);
        cb(alvo.clausulas ? snapQuery(alvo) : snapDoc(alvo));
        return () => { ouvintes.splice(ouvintes.indexOf(reg), 1); };
    }),
    runTransaction: vi.fn(async (_db: any, fn: any) => fn({
        get: async (ref: any) => snapDoc(ref),
        update: (ref: any, dados: any) => {
            gravacoes.push({ ref: chave(ref), dados });
            armazem[chave(ref)] = { ...armazem[chave(ref)], ...dados };
        },
    })),
}));

import DashboardView from './DashboardView';

const acaoResumo = (id: string, titulo: string, extra: Record<string, any> = {}) => ({
    id, titulo, horario_inicio: null, horario_fim: null, execution_lane: 'avanco', degradation_count: 0,
    herdada: false, cobrar: false, atrasada: false, data_limite: HOJE, prazo_final: null, proximo_passo: null,
    etapas_feitas: 0, etapas_totais: 2, estrategia_objetivo_id: null, subtarefa_do_dia: null,
    aguardando_terceiro: [], ...extra,
});
const etapa = (id: string, extra: Record<string, any> = {}) => ({ id, text: `Passo ${id}`, completed: false, estado: 'pendente', ...extra });

const tarefas = () => [
    { id: 'sisp', titulo: 'Sispnaes', status: 'em andamento', data_limite: HOJE, prazo_final: '2026-10-31',
      plano_acao: [etapa('s1', { executor: 'agente' }), etapa('s2')] },
    { id: 'folha', titulo: 'Folha de pagamento', status: 'em andamento', data_limite: HOJE, plano_acao: [etapa('f1'), etapa('f2')] },
    { id: 'rede', titulo: 'Rede Elétrica', status: 'em andamento', data_limite: HOJE,
      plano_acao: [etapa('r1', { estado: 'aguardando_terceiro', aguardando_de: 'Ezequiel' }), etapa('r2')] },
] as any[];

const decidir = (id: string, quem: string, extra: Record<string, any> = {}) => ({
    id, quem, texto: `Texto de ${quem}`, origem: 'whatsapp', ref: `wa-${id}`, status: 'pendente', resolvido_em: null, ...extra,
});

const briefingCompleto = () => ({
    data: HOJE,
    hoje: [{ acao_id: 'sisp', motivo: 'prazo 31/10' }, { acao_id: 'rede', motivo: 'vale até 03/11' }],
    decidir: [decidir('d1', 'Enfermaria', { tag: 'hoje', recomendacao: 'É o que o diário recomenda.' }), decidir('d2', 'Hildo'),
        decidir('d3', 'Raquel'), decidir('d4', 'Geraldo'), decidir('d5', 'Nathália')],
    eu_faco: [{ acao_id: 'sisp', texto: 'ler o relatório e montar a versão executiva em rascunho', status: 'proposto' }],
    preparo: [{ dia: '2026-10-28', texto: 'retirar o carro na Localiza, 9h' }, { dia: '2026-10-29', texto: 'devolver o carro' }],
    fora_da_agenda: [{ titulo: 'Conselho de Escola — EMEF', inicio: '13:50', fim: null, motivo: 'não está na agenda' }],
    avisos: [{ tipo: 'nao_li', texto: 'Não li hoje: e-mail e SIGFAPES.' }],
});

const propsBase = (extra: Record<string, any> = {}) => ({
    tarefas: tarefas(), isDark: false, financeTransactions: [], financeSettings: {} as any, fixedBills: [], incomeEntries: [],
    healthWeights: [], healthSettings: {} as any, exerciseLogs: [], unidades: [], currentMonth: 9, currentYear: 2026,
    onNavigate: vi.fn(), ...extra,
});

const preparar = (briefing: any | null) => {
    armazem[`resumo_matinal/${HOJE}`] = {
        data: HOJE,
        hoje: {
            avanco: [acaoResumo('sisp', 'Sispnaes'), acaoResumo('folha', 'Folha de pagamento')],
            continuo: [], atrasadas: [],
            aguardando_terceiro: [acaoResumo('rede', 'Rede Elétrica')],
        },
        agenda: [], filas: { elevacoes: { total: 3, amostra: [], rota: '' }, contas: { total: 0, amostra: [], rota: '' } },
        avisos_do_sistema: [{ id: 'v1', gravidade: 'atencao', titulo: 'A varredura de elevações está parada', detalhe: 'x', desde: '2026-09-20' }],
    };
    armazem['tarefas/sisp'] = tarefas()[0];
    armazem['tarefas/folha'] = tarefas()[1];
    armazem['tarefas/rede'] = tarefas()[2];
    armazem['google_calendar_events/e1'] = { titulo: 'Sessão de pilates', data_inicio: `${HOJE}T09:00:00-03:00`, data_fim: `${HOJE}T09:50:00-03:00` };
    armazem['google_calendar_events/e2'] = { titulo: 'Acupuntura', data_inicio: `${HOJE}T13:30:00-03:00`, data_fim: `${HOJE}T14:30:00-03:00` };
    armazem['google_calendar_events/ontem'] = { titulo: 'De ontem', data_inicio: '2026-10-26T10:00:00-03:00', data_fim: '2026-10-26T11:00:00-03:00' };
    armazem['atencao/a1'] = { estado: 'aberto' };
    if (briefing) armazem[`briefing_dia/${HOJE}`] = briefing;
};

let erroDoConsole: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    vi.setSystemTime(new Date(2026, 9, 27, 8, 29, 50));
    for (const k of Object.keys(armazem)) delete armazem[k];
    ouvintes.length = 0;
    gravacoes.length = 0;
    erroDoConsole = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});
afterEach(() => {
    cleanup();
    vi.useRealTimers();
    erroDoConsole.mockRestore();
});

const titulos = () => screen.queryAllByRole('heading', { level: 2 }).map(h => h.textContent);

describe('Painel do dia — sem briefing_dia', () => {
    it('abre normal, sem os blocos novos e sem erro', () => {
        preparar(null);
        render(<DashboardView {...propsBase()} />);
        expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('27 de outubro');
        expect(titulos()).toEqual(expect.arrayContaining(['Ações de hoje', 'Agenda de hoje', 'Caminhada']));
        for (const ausente of ['Decidir', 'Avisos do agente']) {
            expect(titulos()).not.toContain(ausente);
        }
        expect(screen.queryByTestId('faixa-preparo')).toBeNull();
        expect(screen.queryByTestId('agente-prepara-hoje')).toBeNull();
        expect(screen.queryByTestId('chip-foco')).toBeNull();
        expect(screen.queryByTestId('linha-decidir')).toBeNull();
        expect(erroDoConsole).not.toHaveBeenCalled();
    });

    it('as ações, a agenda ao vivo e os links continuam lá', () => {
        preparar(null);
        render(<DashboardView {...propsBase()} />);
        expect(screen.getAllByTestId('acao-ativa')).toHaveLength(2);
        expect(screen.getAllByTestId('bloco-agenda')).toHaveLength(2);
        expect(screen.getByRole('button', { name: /Resumo financeiro/ })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Saúde e telemetria/ })).toBeInTheDocument();
    });

    it('o aviso de elevações aparece sozinho (não se perde o antigo "Avisos do sistema")', () => {
        preparar(null);
        render(<DashboardView {...propsBase()} />);
        expect(screen.getByLabelText('Avisos do sistema')).toHaveTextContent('3 sugestões de elevação esperam decisão.');
        expect(screen.getByLabelText('Avisos do sistema')).toHaveTextContent('A varredura de elevações está parada (desde 20/09)');
    });
});

describe('Painel do dia — com briefing_dia', () => {
    beforeEach(() => preparar(briefingCompleto()));

    it('mostra Decidir com 3 linhas, "Ver mais 2" abre o resto', () => {
        render(<DashboardView {...propsBase()} />);
        expect(titulos()).toContain('Decidir');
        expect(screen.getAllByTestId('linha-decidir')).toHaveLength(3);
        const mais = screen.getByRole('button', { name: 'Ver mais 2' });
        expect(mais).toHaveAttribute('aria-expanded', 'false');
        fireEvent.click(mais);
        expect(screen.getAllByTestId('linha-decidir')).toHaveLength(5);
        expect(screen.getByRole('button', { name: 'Mostrar só 3' })).toHaveAttribute('aria-expanded', 'true');
        expect(screen.getByText('5 pendências · do briefing de hoje')).toBeInTheDocument();
    });

    it('Feito grava só `decidir`, o item desce riscado e Desfazer volta a pendente', async () => {
        render(<DashboardView {...propsBase()} />);
        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: 'Marcar como feito: Enfermaria' }));
        });
        expect(gravacoes).toHaveLength(1);
        expect(gravacoes[0].ref).toBe(`briefing_dia/${HOJE}`);
        expect(Object.keys(gravacoes[0].dados)).toEqual(['decidir']);
        const d1 = gravacoes[0].dados.decidir.find((i: any) => i.id === 'd1');
        expect(d1.status).toBe('feito');
        expect(d1.resolvido_em).toMatch(/^2026-10-27T/);
        expect(gravacoes[0].dados.decidir).toHaveLength(5);

        act(() => notificar());
        const linhas = screen.getAllByTestId('linha-decidir');
        expect(linhas.map(l => l.getAttribute('data-feito'))).toEqual(['nao', 'nao', 'nao']);
        fireEvent.click(screen.getByRole('button', { name: 'Ver mais 2' }));
        const todas = screen.getAllByTestId('linha-decidir');
        expect(todas[4]).toHaveAttribute('data-feito', 'sim');
        expect(within(todas[4]).getByText('Enfermaria')).toBeInTheDocument();
        expect(screen.getByText('4 pendências · do briefing de hoje')).toBeInTheDocument();

        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: 'Desfazer: Enfermaria' }));
        });
        expect(gravacoes[1].dados.decidir.find((i: any) => i.id === 'd1')).toMatchObject({ status: 'pendente', resolvido_em: null });
    });

    it('concluir a ação ou resolver o item da fila tira o item de Decidir sem recarregar', () => {
        armazem[`briefing_dia/${HOJE}`] = {
            ...briefingCompleto(),
            decidir: [
                decidir('d1', 'Fila', { origem: 'fila_atencao', ref: 'a1' }),
                decidir('d2', 'Ação', { origem: 'acao', ref: 'folha' }),
                decidir('d3', 'Etapa', { origem: 'etapa', ref: 'f1', acao_id: 'folha' }),
            ],
        };
        const { rerender } = render(<DashboardView {...propsBase()} />);
        expect(screen.getAllByTestId('linha-decidir')).toHaveLength(3);

        act(() => { armazem['atencao/a1'] = { estado: 'resolvido' }; notificar(); });
        expect(screen.getAllByTestId('linha-decidir')).toHaveLength(2);

        const feitaF1 = tarefas();
        feitaF1[1].plano_acao[0] = etapa('f1', { estado: 'feito', completed: true });
        rerender(<DashboardView {...propsBase({ tarefas: feitaF1 })} />);
        expect(screen.getAllByTestId('linha-decidir')).toHaveLength(1);

        const concluida = tarefas();
        concluida[1].status = 'concluído';
        rerender(<DashboardView {...propsBase({ tarefas: concluida })} />);
        expect(screen.queryByTestId('linha-decidir')).toBeNull();
    });

    it('Foco: chip com o motivo na ação ativa e só o ícone com tooltip na linha de espera', () => {
        render(<DashboardView {...propsBase()} />);
        const chip = screen.getByTestId('chip-foco');
        expect(chip).toHaveTextContent('Foco · prazo 31/10');
        const espera = screen.getByTestId('acao-em-espera');
        const icone = within(espera).getByTestId('icone-foco');
        expect(icone).toHaveAttribute('title', 'Foco de hoje · vale até 03/11');
        expect(within(espera).queryByText(/vale até 03\/11/)).toBeNull();
    });

    it('"O agente prepara hoje", Preparo e Avisos do agente aparecem', () => {
        render(<DashboardView {...propsBase()} />);
        const faixa = screen.getByTestId('agente-prepara-hoje');
        expect(faixa).toHaveTextContent('O agente prepara hoje');
        expect(faixa).toHaveTextContent('Sispnaes: ler o relatório e montar a versão executiva em rascunho');
        expect(screen.getByTestId('faixa-preparo')).toHaveTextContent('Qua retirar o carro na Localiza, 9h');
        expect(titulos()).toContain('Avisos do agente');
        expect(screen.getByText('Não li hoje: e-mail e SIGFAPES.')).toBeInTheDocument();
    });

    it('conflito: o compromisso fora da agenda bate com a acupuntura e entra tracejado', () => {
        render(<DashboardView {...propsBase()} />);
        expect(screen.getByTestId('aviso-conflito')).toHaveTextContent('Conselho de Escola — EMEF 13h50 bate com Acupuntura 13h30.');
        expect(screen.getAllByTestId('bloco-agenda')).toHaveLength(3);
    });

    it('a agenda vem do dia de hoje (o compromisso de ontem não entra)', () => {
        render(<DashboardView {...propsBase()} />);
        fireEvent.click(screen.getByRole('button', { name: 'Mostrar ou recolher a agenda completa' }));
        expect(screen.queryByText('De ontem')).toBeNull();
        expect(screen.getByText('Sessão de pilates')).toBeInTheDocument();
    });

    it('a proximidade segue o relógio real, relido a cada 30 s', () => {
        render(<DashboardView {...propsBase()} />);
        // 08:29:50 -> 31 min para as 9h.
        expect(screen.getByTestId('caixa-proximo')).toHaveAttribute('data-nivel', 'normal');
        act(() => { vi.advanceTimersByTime(30_000); }); // 08:30:20 -> 30 min
        expect(screen.getByTestId('caixa-proximo')).toHaveAttribute('data-nivel', 'atencao');
        act(() => { vi.setSystemTime(new Date(2026, 9, 27, 8, 44, 50)); vi.advanceTimersByTime(30_000); }); // 08:45:20 -> 15 min
        expect(screen.getByTestId('caixa-proximo')).toHaveAttribute('data-nivel', 'urgente');
        act(() => { vi.setSystemTime(new Date(2026, 9, 27, 9, 5, 0)); vi.advanceTimersByTime(30_000); });
        expect(screen.getByTestId('caixa-proximo')).toHaveAttribute('data-nivel', 'agora');
    });

    it('cabeçalho: ações do dia e em espera', () => {
        render(<DashboardView {...propsBase()} />);
        expect(screen.getByText('3 ações hoje · 1 em espera')).toBeInTheDocument();
        expect(screen.getByText('0 de 2 concluídas')).toBeInTheDocument();
    });

    it('Em espera compacto: uma linha por ação, com ícones e sem texto repetido', () => {
        render(<DashboardView {...propsBase()} />);
        const linha = screen.getByTestId('acao-em-espera');
        expect(within(linha).getByText('Rede Elétrica')).toBeInTheDocument();
        expect(within(linha).getByTestId('espera-de')).toHaveAttribute('title', 'Aguardando Ezequiel');
        expect(within(linha).getByText('Ezequiel')).toBeInTheDocument();
        expect(within(linha).getByText('0/2')).toBeInTheDocument();
        expect(within(linha).queryByText(/Aguardando/)).toBeNull();
        const seta = within(linha).getByRole('button', { name: 'Ver etapas: Rede Elétrica' });
        expect(seta).toHaveAttribute('aria-expanded', 'false');
        expect(seta).toHaveTextContent('');
        fireEvent.click(seta);
        expect(seta).toHaveAttribute('aria-expanded', 'true');
        expect(within(linha).getByText('Passo r2')).toBeInTheDocument();
    });

    it('a barra do dia conta só as ativas; ação em espera fica embaixo', () => {
        render(<DashboardView {...propsBase()} />);
        const ativas = screen.getAllByTestId('acao-ativa').map(a => within(a).getByRole('heading', { level: 3 }).textContent);
        expect(ativas).toEqual(['Sispnaes', 'Folha de pagamento']);
        expect(screen.queryByText('Adiada', { exact: false })).toBeNull();
    });
});
