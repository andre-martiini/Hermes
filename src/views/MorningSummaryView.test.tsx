/**
 * Testa a renderização do Resumo Matinal contra um documento de fixture.
 *
 * O foco aqui é o que a tela AFIRMA: os números vêm prontos do backend, então o
 * risco não é cálculo errado — é a view mostrar a coisa errada (esconder a
 * herança da madrugada, engolir uma fila com itens, inventar um estado vazio
 * que não existe). Firebase é mockado: nenhuma rede, nenhum auth.
 */
// @vitest-environment jsdom
import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import { ResumoMatinal } from '../../types';

let snapshotData: any = null;

vi.mock('../../firebase', () => ({ db: {}, functions: {} }));

vi.mock('firebase/firestore', () => ({
    doc: vi.fn(() => ({})),
    setDoc: vi.fn(() => Promise.resolve()),
    onSnapshot: vi.fn((_ref: any, onNext: any) => {
        onNext({
            exists: () => snapshotData !== null,
            id: snapshotData?.data ?? 'x',
            data: () => snapshotData,
        });
        return () => {};
    }),
}));

const callable = vi.fn(() => Promise.resolve({ data: snapshotData }));
vi.mock('firebase/functions', () => ({ httpsCallable: () => callable }));

import MorningSummaryView from './MorningSummaryView';

const hoje = (() => {
    const n = new Date();
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`;
})();

const fixture = (over: Partial<ResumoMatinal> = {}): ResumoMatinal => ({
    data: hoje,
    dia_semana: 'quinta-feira',
    versao: 'v1',
    gerado_em: '2026-08-20T07:30:00+00:00',
    foco: [
        {
            task_id: 't1',
            titulo: 'Fechar o relatório do convênio',
            regra: 'prazo_final_iminente',
            motivo: 'Prazo final vence hoje (2026-08-20).',
            proximo_passo: 'Consolidar os anexos do capítulo 3',
            horario_inicio: '09:00',
        },
        {
            task_id: 't2',
            titulo: 'Retomar o plano de compras',
            regra: 'degracao_critica' as any,
            motivo: 'Adiada automaticamente 4x — não sobrevive a mais um dia.',
            proximo_passo: null,
            horario_inicio: null,
        },
    ],
    hoje: {
        avanco: [{
            id: 't1', titulo: 'Fechar o relatório do convênio', horario_inicio: '09:00', horario_fim: null,
            execution_lane: 'avanco', degradation_count: 0, herdada: false, cobrar: false, atrasada: false,
            data_limite: hoje, prazo_final: hoje, proximo_passo: 'Consolidar os anexos do capítulo 3',
            etapas_feitas: 2, etapas_totais: 5, estrategia_objetivo_id: null,
        }],
        continuo: [],
        aguardando_terceiro: [{
            id: 't3', titulo: '[COBRAR] Parecer da procuradoria', horario_inicio: null, horario_fim: null,
            execution_lane: 'aguardando_terceiro', degradation_count: 5, herdada: true, cobrar: true, atrasada: false,
            data_limite: hoje, prazo_final: null, proximo_passo: null,
            etapas_feitas: 0, etapas_totais: 0, estrategia_objetivo_id: null,
        }],
        atrasadas: [],
    },
    agenda: [{ titulo: 'Reunião de equipe', inicio: '10:00', fim: '11:00', dia_inteiro: false }],
    janelas_livres: [{ inicio: '11:00', fim: '19:00', minutos: 480 }],
    prazos_duros: [{ id: 't1', titulo: 'Fechar o relatório do convênio', prazo_final: hoje, dias: 0 }],
    carga_semana: Array.from({ length: 7 }, (_, i) => ({ data: `2026-08-${20 + i}`, total: i })),
    filas: {
        sugestoes_vinculo: { total: 4, amostra: [{ titulo: 'Ofício 231/2026', canal: 'email' }], rota: 'dashboard' },
        contas: { total: 0, amostra: [], rota: 'finance' },
    },
    saude: {
        rotinas_hoje: [
            { titulo: 'Pesagem diária', hora: '04:20', categoria: 'custom', verificavel: 'pesagem', feito: true },
            { titulo: 'Almoço com calma', hora: '11:45', categoria: 'nutrition', verificavel: null, feito: null },
            { titulo: 'Check-in da noite', hora: '19:00', categoria: 'checkin_night', verificavel: 'checkin_noite', feito: false },
        ],
        pesagem_registrada: true,
        cintura_registrada: false,
        checkin_manha: true,
        checkin_noite: false,
        peso: { ultimo: 92.4, data: hoje, media7: 92.8, alvo: 85, falta: 7.4 },
        dor_ontem: { manha: 3, noite: 5, ciatica: true, crise: false },
        ultimo_registro: hoje,
    },
    estrategia: {
        metas: [{
            id: 'm1', pilar: 'carreira', pilar_label: 'Carreira', objetivo: 'Consolidar o núcleo de convênios',
            gerida_por_acoes: true,
            acoes_hoje: 1, titulos_hoje: ['Fechar o relatório do convênio'], ultimo_movimento: hoje,
            dias_parada: 0, progresso_pct: 40, unidade: null, marcos_abertos: 2, marcos_total: 5,
        }],
        paradas: [{
            id: 'm2', pilar: 'intelectual', pilar_label: 'Intelectual', objetivo: 'Terminar o mestrado',
            gerida_por_acoes: true,
            acoes_hoje: 0, titulos_hoje: [], ultimo_movimento: '2026-07-14',
            dias_parada: 37, progresso_pct: null, unidade: null, marcos_abertos: 4, marcos_total: 4,
        }],
        servidas_hoje: 1,
        total_geridas_por_acoes: 2,
    },
    ontem: {
        concluidas: ['Revisar o edital', 'Responder a DAP'],
        diario: { data: '2026-08-19', texto: 'Dia puxado, mas fechei o que precisava.', editado: false },
    },
    perfil: null,
    contadores: { ativas: 31, hoje: 2, herdadas: 1, criticas: 1, cobrar: 1, sem_plano: 1, pendencias: 4, focos: 2 },
    ...over,
});

beforeEach(() => {
    snapshotData = fixture();
    callable.mockClear();
});

afterEach(cleanup);

describe('MorningSummaryView', () => {

    const secao = async (titulo: string): Promise<HTMLElement> =>
        (await screen.findByRole('heading', { name: titulo })).closest('section') as HTMLElement;

    it('mostra os focos do dia com o motivo da regra que os escolheu', async () => {
        render(<MorningSummaryView />);
        const foco = within(await secao('Foco de hoje'));
        expect(foco.getByText('Fechar o relatório do convênio')).toBeDefined();
        expect(foco.getByText('Prazo final vence hoje (2026-08-20).')).toBeDefined();
        expect(foco.getByText('↳ Consolidar os anexos do capítulo 3')).toBeDefined();
        expect(foco.getByText('Prazo final')).toBeDefined();
    });

    it('explicita quantas ações foram empurradas para hoje pelo reset da meia-noite', async () => {
        render(<MorningSummaryView />);
        expect(
            await screen.findByText(/1 de 2 ação\(ões\) de hoje não foram escolhidas para hoje/),
        ).toBeDefined();
    });

    it('não exibe o aviso de herança quando nada foi arrastado', async () => {
        snapshotData = fixture({
            contadores: { ativas: 31, hoje: 2, herdadas: 0, criticas: 0, cobrar: 0, sem_plano: 0, pendencias: 0, focos: 2 },
        });
        render(<MorningSummaryView />);
        await screen.findByText('Foco de hoje');
        expect(screen.queryByText(/não foram escolhidas para hoje/)).toBeNull();
    });

    it('lista só as filas com itens e esconde as zeradas', async () => {
        render(<MorningSummaryView />);
        expect(await screen.findByText('Sugestões de vínculo')).toBeDefined();
        expect(screen.queryByText('Contas vencendo')).toBeNull();
    });

    it('mostra a meta parada com o tempo sem movimento', async () => {
        render(<MorningSummaryView />);
        expect(await screen.findByText('Terminar o mestrado')).toBeDefined();
        expect(screen.getByText(/Parada há 37 dia\(s\)/)).toBeDefined();
    });

    it('marca so as rotinas verificaveis: feita, pendente, e aviso sem marcador', async () => {
        render(<MorningSummaryView />);
        const corpo = within(await secao('Corpo'));

        // Pesagem foi feita -> marcador de concluido e texto riscado.
        const pesagem = corpo.getByText('Pesagem diária');
        expect(pesagem.className).toContain('line-through');
        expect(pesagem.parentElement?.textContent).toContain('✓');

        // Check-in da noite ainda nao aconteceu -> marcador de pendente.
        const checkin = corpo.getByText('Check-in da noite');
        expect(checkin.className).not.toContain('line-through');
        expect(checkin.parentElement?.textContent).toContain('○');

        // Aviso ilustrativo -> nenhum marcador dos dois.
        const aviso = corpo.getByText('Almoço com calma').parentElement?.textContent || '';
        expect(aviso).not.toContain('✓');
        expect(aviso).not.toContain('○');
    });

    it('meta do pilar saude nao e cobrada por vinculo de acao', async () => {
        // No backend `paradas` e sempre um subconjunto de `metas` — a fixture
        // precisa refletir isso, senao testa um estado que nao existe.
        const metaSaude = {
            id: 'ms', pilar: 'saude' as const, pilar_label: 'Saúde', objetivo: 'Sair de 95kg para 80kg',
            gerida_por_acoes: false, acoes_hoje: 0, titulos_hoje: [], ultimo_movimento: hoje,
            dias_parada: 0, progresso_pct: 30, unidade: 'kg', marcos_abertos: 3, marcos_total: 5,
        };
        snapshotData = fixture({
            estrategia: { metas: [metaSaude], paradas: [metaSaude], servidas_hoje: 0, total_geridas_por_acoes: 0 },
        });
        render(<MorningSummaryView />);
        const est = within(await secao('O que isso constrói'));
        expect(est.getByText('Registro de hoje já lançado')).toBeDefined();
        expect(est.queryByText(/Parada há/)).toBeNull();
        // Sem meta executada por acoes, a frase nao pode culpar o dia por isso.
        expect(est.getByText('Nenhuma meta é executada por ações.')).toBeDefined();
    });

    it('abre a ação ao clicar num foco', async () => {
        const onOpenTask = vi.fn();
        render(<MorningSummaryView onOpenTask={onOpenTask} />);
        const foco = within(await secao('Foco de hoje'));
        fireEvent.click(foco.getByText('Fechar o relatório do convênio'));
        expect(onOpenTask).toHaveBeenCalledWith('t1');
    });

    it('navega para a tela onde a fila se resolve', async () => {
        const onNavigate = vi.fn();
        render(<MorningSummaryView onNavigate={onNavigate} />);
        fireEvent.click(await screen.findByText('Sugestões de vínculo'));
        expect(onNavigate).toHaveBeenCalledWith('dashboard');
    });

    it('o quadro de volume diz o que mede e abre a coluna da direita', async () => {
        render(<MorningSummaryView />);
        const titulo = await screen.findByRole('heading', { name: 'Volume de ações nos próximos 7 dias' });
        const coluna = titulo.closest('section')?.parentElement as HTMLElement;
        const titulos = Array.from(coluna.querySelectorAll('h3')).map(h => h.textContent);
        expect(titulos[0]).toBe('Volume de ações nos próximos 7 dias');
    });

    it('consolidações de WhatsApp não aparecem nem como fila nem em lugar nenhum', async () => {
        // Regressão: `merge=True` no backend deixava a chave antiga viva no doc,
        // então a tela seguia listando a fila mesmo depois de removida do código.
        snapshotData = fixture({
            filas: {
                sugestoes_vinculo: { total: 0, amostra: [], rota: 'dashboard' },
                consolidacoes_whatsapp: { total: 7, amostra: [{ titulo: 'Conversa consolidada' }], rota: 'whatsapp' },
            },
        });
        render(<MorningSummaryView />);
        await screen.findByText('Foco de hoje');
        // Nem o nome cru da chave, nem o conteúdo da amostra.
        expect(screen.queryByText(/consolidacoes_whatsapp/)).toBeNull();
        expect(screen.queryByText(/Consolidações/)).toBeNull();
        expect(screen.queryByText('Conversa consolidada')).toBeNull();
        // E a seção fica no estado vazio, não meio-preenchida.
        expect(screen.getByText('Nenhuma fila parada. Tudo decidido.')).toBeDefined();
    });

    it('dia sem ação nenhuma não inventa foco', async () => {
        snapshotData = fixture({
            foco: [],
            hoje: { avanco: [], continuo: [], aguardando_terceiro: [], atrasadas: [] },
            contadores: { ativas: 5, hoje: 0, herdadas: 0, criticas: 0, cobrar: 0, sem_plano: 0, pendencias: 0, focos: 0 },
        });
        render(<MorningSummaryView />);
        expect(await screen.findByText('Nenhuma ação programada para hoje. Dia livre.')).toBeDefined();
    });

    it('gera o resumo sob demanda quando o dia ainda não tem documento', async () => {
        snapshotData = null;
        render(<MorningSummaryView />);
        // Uma única chamada automática — sem loop de regeneração a cada snapshot.
        await waitFor(() => expect(callable).toHaveBeenCalledTimes(1));
        expect(callable).toHaveBeenCalledWith({ date: hoje });
    });
});
