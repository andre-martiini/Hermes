// @vitest-environment jsdom
import React from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import F from '../../utils/perfilEstrategia.fixture.json';
import type { MetaPerfil } from '../../utils/perfilEstrategia';
import PerfilDaMeta from './PerfilDaMeta';

const saude = F.metas.saude as unknown as MetaPerfil;
const financeira = F.metas.financeira as unknown as MetaPerfil;

afterEach(cleanup);

describe('PerfilDaMeta', () => {
    it('mostra atual, esperado de hoje, próximo marco, selo e origem de cada indicador', () => {
        render(<PerfilDaMeta meta={saude} atuais={{ peso: 90.5, cintura: 106.5 }}
            origens={{ peso: 'automatica', cintura: 'automatica' }} hoje="2026-12-15" isDark={false} />);
        const [peso] = screen.getAllByTestId('perfil-indicador');
        expect(within(peso).getByText('90,5 kg')).toBeInTheDocument();
        expect(within(peso).getByText('90,8 kg')).toBeInTheDocument();
        expect(within(peso).getByText('89,9 kg em 30/12/26')).toBeInTheDocument();
        expect(within(peso).getByText('No perfil')).toBeInTheDocument();
        expect(within(peso).getByText('Automático (peso)')).toBeInTheDocument();
        expect(screen.getAllByTestId('perfil-marco')).toHaveLength(3);
    });

    it('sem medida mostra "—" e Sem dado, nunca zero; dinheiro em reais', () => {
        render(<PerfilDaMeta meta={financeira} atuais={{ guardado: 0 }}
            origens={{ guardado: 'automatica', renda_produto: 'manual' }} hoje="2026-12-15" isDark />);
        const [guardado, renda] = screen.getAllByTestId('perfil-indicador');
        expect(within(guardado).getByText('R$ 4.500')).toBeInTheDocument();
        expect(within(guardado).getByText('Atrasado')).toBeInTheDocument();
        expect(within(renda).getAllByText('—').length).toBeGreaterThan(0);
        expect(within(renda).getByText('Sem dado')).toBeInTheDocument();
        expect(within(renda).getByText('Manual (último registro do histórico)')).toBeInTheDocument();
    });

    it('compacto não mostra a linha do tempo; meta sem perfil não desenha nada', () => {
        render(<PerfilDaMeta meta={saude} atuais={{}} origens={{}} hoje="2026-12-15" isDark={false} compacto />);
        expect(screen.queryAllByTestId('perfil-marco')).toHaveLength(0);
        cleanup();
        const { container } = render(<PerfilDaMeta meta={{ marcos: ['texto'] }} atuais={{}} origens={{}} hoje="2026-12-15" isDark={false} />);
        expect(container).toBeEmptyDOMElement();
    });
});
