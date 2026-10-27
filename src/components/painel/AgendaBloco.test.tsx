/**
 * Agenda do painel: o efeito de proximidade, o conflito e o `prefers-reduced-motion`.
 * O relógio entra pronto (`agoraMin`): nada aqui depende da hora do computador.
 */
// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import { eventosDoDia, hhmmParaMin } from '../../utils/agendaProximidade';
import AgendaBloco from './AgendaBloco';

const min = (hhmm: string) => hhmmParaMin(hhmm) as number;

const AGENDA = [
    { titulo: 'Sessão de pilates', inicio: '09:00', fim: '09:50' },
    { titulo: 'Acupuntura', inicio: '13:30', fim: '14:30' },
];

const mostrar = (hhmm: string, extra: { fora?: any[]; agenda?: any[]; preparo?: any[] } = {}) =>
    render(
        <AgendaBloco
            eventos={eventosDoDia(extra.agenda ?? AGENDA, extra.fora ?? [])}
            agoraMin={min(hhmm)}
            preparo={extra.preparo ?? []}
        />,
    );

const caixa = () => screen.getByTestId('caixa-proximo');

const matchMediaReduzido = (reduzido: boolean) => {
    window.matchMedia = vi.fn().mockImplementation((consulta: string) => ({
        matches: reduzido && consulta.includes('prefers-reduced-motion'),
        media: consulta,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
    })) as any;
};

beforeEach(() => matchMediaReduzido(false));
afterEach(cleanup);

describe('AgendaBloco — proximidade (relógio injetado)', () => {
    it.each([
        ['08:29', 'normal', 'Próximo', 'em 31 min'],
        ['08:30', 'atencao', 'Em breve', 'em 30 min'],
        ['08:31', 'atencao', 'Em breve', 'em 29 min'],
        ['08:45', 'urgente', 'Já vai começar', 'em 15 min'],
        ['08:46', 'urgente', 'Já vai começar', 'em 14 min'],
    ])('às %s: %s', (hora, nivel, rotulo, tempo) => {
        mostrar(hora);
        expect(caixa()).toHaveAttribute('data-nivel', nivel);
        expect(within(caixa()).getByText(rotulo)).toBeInTheDocument();
        expect(within(caixa()).getByText(tempo)).toBeInTheDocument();
        expect(within(caixa()).getByText('09:00 · Sessão de pilates')).toBeInTheDocument();
    });

    it('dentro do compromisso: agora, verde, com "até HH:MM"', () => {
        mostrar('09:10');
        expect(caixa()).toHaveAttribute('data-nivel', 'agora');
        expect(within(caixa()).getByText('Agora')).toBeInTheDocument();
        expect(within(caixa()).getByText('Sessão de pilates')).toBeInTheDocument();
        expect(within(caixa()).getByText('até 09:50')).toBeInTheDocument();
    });

    it('sem mais compromissos', () => {
        mostrar('20:00');
        expect(within(caixa()).getByText('Sem mais compromissos hoje')).toBeInTheDocument();
    });

    it('o bloco da linha do tempo recebe o mesmo destaque, e só o do alvo', () => {
        mostrar('08:31');
        const blocos = screen.getAllByTestId('bloco-agenda');
        expect(blocos.map(b => b.getAttribute('data-marcado'))).toEqual(['sim', 'nao']);
    });

    it('nível normal não destaca bloco nenhum', () => {
        mostrar('08:00');
        expect(screen.getAllByTestId('bloco-agenda').every(b => b.getAttribute('data-marcado') === 'nao')).toBe(true);
    });

    it('o marcador "agora" anda com o relógio', () => {
        const { unmount } = mostrar('08:00');
        const antes = screen.getByTestId('marcador-agora').style.left;
        unmount();
        mostrar('13:00');
        expect(screen.getByTestId('marcador-agora').style.left).not.toBe(antes);
    });
});

describe('AgendaBloco — animação e prefers-reduced-motion', () => {
    it('atenção brilha devagar e urgente pulsa; agora e normal não animam', () => {
        mostrar('08:31');
        expect(caixa().className).toContain('painel-brilho-suave');
        expect(caixa()).toHaveAttribute('data-animado', 'sim');
        cleanup();
        mostrar('08:50');
        expect(caixa().className).toContain('painel-pulso');
        cleanup();
        mostrar('09:10');
        expect(caixa().className).not.toMatch(/painel-(pulso|brilho)/);
        cleanup();
        mostrar('08:00');
        expect(caixa().className).not.toMatch(/painel-(pulso|brilho)/);
    });

    it('com prefers-reduced-motion só a cor muda: nenhuma classe de animação', () => {
        matchMediaReduzido(true);
        mostrar('08:50');
        expect(caixa()).toHaveAttribute('data-nivel', 'urgente');
        expect(caixa()).toHaveAttribute('data-animado', 'nao');
        expect(caixa().className).not.toMatch(/painel-(pulso|brilho)/);
        const marcado = screen.getAllByTestId('bloco-agenda').find(b => b.getAttribute('data-marcado') === 'sim')!;
        expect(marcado.className).not.toMatch(/painel-(pulso|brilho)/);
    });

    it('o CSS também desliga as animações (media query), caso a classe esteja lá', () => {
        const { container } = mostrar('08:50');
        const css = container.querySelector('style')!.textContent!;
        expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)\{\.painel-brilho-suave,\.painel-pulso\{animation:none\}\}/);
    });
});

describe('AgendaBloco — conflito', () => {
    const fora = [{ titulo: 'Conselho de Escola — EMEF', inicio: '13:50', fim: null }];

    it('avisa no topo e marca na lista completa; o fora da agenda entra no cálculo e tracejado', () => {
        mostrar('08:00', { fora });
        expect(screen.getByTestId('aviso-conflito')).toHaveTextContent(
            'Conselho de Escola — EMEF 13h50 bate com Acupuntura 13h30.');
        const tracejado = screen.getAllByTestId('bloco-agenda').filter(b => b.getAttribute('data-fora-da-agenda') === 'sim');
        expect(tracejado).toHaveLength(1);
        expect(tracejado[0].style.border).toContain('dashed');

        fireEvent.click(screen.getByRole('button', { name: 'Mostrar ou recolher a agenda completa' }));
        expect(screen.getAllByText('Horário sobrepõe outro compromisso')).toHaveLength(2);
        expect(screen.getByText(/Conselho de Escola — EMEF \(não está na agenda\)/)).toBeInTheDocument();
    });

    it('sem sobreposição não há aviso', () => {
        mostrar('08:00');
        expect(screen.queryByTestId('aviso-conflito')).toBeNull();
    });

    it('o conflito é recalculado: tirando o compromisso, o aviso some', () => {
        const { rerender } = mostrar('08:00', { fora });
        expect(screen.getByTestId('aviso-conflito')).toBeInTheDocument();
        rerender(<AgendaBloco eventos={eventosDoDia(AGENDA, [])} agoraMin={min('08:00')} preparo={[]} />);
        expect(screen.queryByTestId('aviso-conflito')).toBeNull();
    });
});

describe('AgendaBloco — Preparo e lista', () => {
    it('mostra a faixa Preparo com o dia da semana', () => {
        mostrar('08:00', { preparo: [{ dia: '2026-10-28', rotulo: 'Qua', data: '28/10', texto: 'retirar o carro na Localiza, 9h' }] });
        const faixa = screen.getByTestId('faixa-preparo');
        expect(within(faixa).getByText('Qua')).toBeInTheDocument();
        expect(faixa).toHaveTextContent('retirar o carro na Localiza, 9h');
    });

    it('sem Preparo, a faixa não existe', () => {
        mostrar('08:00');
        expect(screen.queryByTestId('faixa-preparo')).toBeNull();
    });

    it('a lista completa é recolhível e usa aria-expanded', () => {
        mostrar('08:00');
        const botao = screen.getByRole('button', { name: 'Mostrar ou recolher a agenda completa' });
        expect(botao).toHaveAttribute('aria-expanded', 'false');
        fireEvent.click(botao);
        expect(botao).toHaveAttribute('aria-expanded', 'true');
        expect(screen.getByText('09:00–09:50')).toBeInTheDocument();
    });
});
