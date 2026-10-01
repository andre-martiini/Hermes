// @vitest-environment jsdom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

vi.mock('./firebase', () => ({ storage: {}, db: {}, functions: {} }));
vi.mock('firebase/functions', () => ({ httpsCallable: () => async () => ({ data: {} }) }));
vi.mock('firebase/storage', () => ({ ref: vi.fn(), uploadBytes: vi.fn(), getDownloadURL: vi.fn() }));
vi.mock('firebase/firestore', () => ({ doc: vi.fn(), setDoc: vi.fn() }));

import FinanceView from './FinanceView';
import type { FinanceSettings } from './types';

afterEach(() => cleanup());

// Sintético (ver src/utils/boleto.test.ts): R$ 123,45, vence em 10/10/2026.
const LINHA = '34191.09008 00012.345674 89012.345677 1 15950000012345';

const props = () => {
    const nada = vi.fn();
    const assincrono = vi.fn(async () => undefined);
    return {
        transactions: [], goals: [], emergencyReserve: { target: 0, current: 0 },
        bolsoAquisicoes: 0, itensQueCabemNoBolso: 0,
        settings: { billCategories: ['Conta Fixa'] } as unknown as FinanceSettings,
        currentMonthTotal: 0, currentMonthIncome: 0, fixedBills: [],
        onUpdateSettings: nada, onAddGoal: nada, onUpdateGoal: nada, onDeleteGoal: nada, onReorderGoals: nada,
        currentMonth: 9, currentYear: 2026, onMonthChange: nada,
        billRubrics: [], onAddRubric: assincrono, onUpdateRubric: nada, onDeleteRubric: nada,
        incomeEntries: [], incomeRubrics: [], onAddIncomeRubric: assincrono, onUpdateIncomeRubric: nada,
        onDeleteIncomeRubric: nada, onAddIncomeEntry: assincrono, onUpdateIncomeEntry: nada, onDeleteIncomeEntry: nada,
        onAddBill: assincrono, onUpdateBill: assincrono, onDeleteBill: assincrono,
        onAddTransaction: assincrono, onUpdateTransaction: assincrono, onDeleteTransaction: assincrono,
        activeTab: 'expense' as const, setActiveTab: nada, isSettingsOpen: false, setIsSettingsOpen: nada,
    };
};

const abrirFormulario = () => {
    render(<FinanceView {...(props() as any)} />);
    fireEvent.click(screen.getByText('+ Nova Obrigação'));
    return {
        codigo: screen.getByPlaceholderText('Cole a linha digitável do boleto...') as HTMLInputElement,
        valor: screen.getByPlaceholderText('0.00') as HTMLInputElement,
        dia: screen.getByPlaceholderText('1-31') as HTMLInputElement,
    };
};

describe('FinanceView — código de barras da nova obrigação', () => {
    it('colar a linha digitável preenche valor e dia e mostra resumo e barras', () => {
        const { codigo, valor, dia } = abrirFormulario();
        fireEvent.change(codigo, { target: { value: LINHA } });
        expect(valor.value).toBe('123.45');
        expect(dia.value).toBe('10');
        expect(screen.getByTestId('boleto-resumo').textContent).toContain('vence 10/10/2026');
        expect(screen.getByTestId('boleto-codigo-de-barras')).toBeTruthy();
    });

    it('não sobrescreve valor e dia já digitados', () => {
        const { codigo, valor, dia } = abrirFormulario();
        fireEvent.change(valor, { target: { value: '99' } });
        fireEvent.change(dia, { target: { value: '5' } });
        fireEvent.change(codigo, { target: { value: LINHA } });
        expect(valor.value).toBe('99');
        expect(dia.value).toBe('5');
    });

    it('número com dígito trocado avisa e não preenche nada', () => {
        const { codigo, valor, dia } = abrirFormulario();
        fireEvent.change(codigo, { target: { value: LINHA.replace('15950', '15951') } });
        expect(screen.getByTestId('boleto-aviso').textContent).toMatch(/não conferem/);
        expect(valor.value).toBe('');
        expect(dia.value).toBe('');
        expect(screen.queryByTestId('boleto-codigo-de-barras')).toBeNull();
    });
});
