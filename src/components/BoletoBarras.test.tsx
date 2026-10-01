// @vitest-environment jsdom
import React from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { BoletoBarras } from './BoletoBarras';
import { analisarBoleto, larguraItf } from '../utils/boleto';

afterEach(() => cleanup());

// Sintético (ver src/utils/boleto.test.ts).
const LINHA = '34191.09008 00012.345674 89012.345677 1 15950000012345';
const CODIGO = '34191159500000123451090000012345678901234567';
const HOJE = new Date('2026-10-01T12:00:00Z');

describe('BoletoBarras', () => {
    it('número válido mostra o resumo e as barras só no desktop', () => {
        render(<BoletoBarras analise={analisarBoleto(LINHA, HOJE)} />);
        expect(screen.getByTestId('boleto-resumo').textContent).toContain('vence 10/10/2026');
        const svg = screen.getByTestId('boleto-codigo-de-barras');
        expect(svg.closest('div')!.className).toContain('hidden md:block');
        // Uma barra por elemento par das larguras (barra, espaço, barra...).
        const barras = larguraItf(CODIGO).filter((_, i) => i % 2 === 0).length;
        expect(svg.querySelectorAll('rect')).toHaveLength(barras);
        expect(screen.queryByTestId('boleto-aviso')).toBeNull();
    });

    it('dígito trocado mostra o aviso e nenhuma barra', () => {
        render(<BoletoBarras analise={analisarBoleto(LINHA.replace('15950', '15951'), HOJE)} />);
        expect(screen.getByTestId('boleto-aviso').textContent).toMatch(/não conferem/);
        expect(screen.queryByTestId('boleto-codigo-de-barras')).toBeNull();
    });

    it('campo vazio não mostra nada', () => {
        const { container } = render(<BoletoBarras analise={analisarBoleto('', HOJE)} />);
        expect(container.innerHTML).toBe('');
    });
});
