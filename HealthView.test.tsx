// @vitest-environment jsdom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import HealthView from './HealthView';
import { HealthWeight, HealthExam, ExerciseLog, HealthTelegramReminder, HealthEvent } from './types';

afterEach(() => {
    cleanup();
});

describe('HealthView', () => {
    const mockWeights: HealthWeight[] = [
        { id: 'w1', date: '2026-08-01', weight: 80.5 },
        { id: 'w2', date: '2026-08-02', weight: 80.2 },
        { id: 'w3', date: '2026-08-03', weight: 79.9 },
    ];

    const mockExams: HealthExam[] = [
        {
            id: 'e1',
            titulo: 'Ressonância Magnética Coluna Lombar',
            tipo: 'exame',
            data: '2026-08-01',
            doutor_local: 'Hospital Albert Einstein',
            achadosChave: 'Hérnia discal L5-S1 contida',
            resultados: 'Disco intervertebral com sinal reduzido',
            profissional: 'Dr. Silva',
            especialidade: 'Ortopedia',
            tags: ['lombar', 'ressonancia'],
        },
    ];

    const mockLogs: ExerciseLog[] = [
        {
            id: '2026-08-01',
            pain: { morning: 3, evening: 2, sciatica: false, crisis: false },
            radicular: { location: 'panturrilha', side: 'direito', intensity: 3, motorWeakness: false },
            strength: { done: true, block: 'A', minutes: 30 },
            walkBlocks: [{ id: 'wb1', distance: 2.5, minutes: 30, time: '08:00', source: 'web' }],
            meds: { pregabalina: true, dipirona: 1, adorlan: 0, fexofenadina: true },
            nutrition: { plan: 'sim', proteinTarget: true },
        },
    ];

    const mockReminders: HealthTelegramReminder[] = [
        {
            id: 'lunch_slow',
            title: 'Almoço com calma',
            message: 'Comer devagar',
            time: '11:45',
            enabled: true,
            daysOfWeek: [1, 2, 3, 4, 5],
            category: 'nutrition',
            telegramOnly: true,
        },
    ];

    const mockEvents: HealthEvent[] = [
        { id: 'ev1', date: '2026-08-01', type: 'fisioterapia', label: 'Sessão 1 fisioterapia' },
    ];

    const baseProps = {
        weights: mockWeights,
        settings: { targetWeight: 75, ritmoAlvoKgSemana: 0.5, marcos: [80, 78, 75], walkingMinimumKm: 3, walkingIdealKm: 8 },
        onUpdateSettings: vi.fn(),
        onAddWeight: vi.fn(),
        onUpdateWeight: vi.fn(),
        onDeleteWeight: vi.fn(),
        waist: [{ id: 'waist1', date: '2026-08-01', cm: 92 }],
        onAddWaist: vi.fn(),
        onDeleteWaist: vi.fn(),
        events: mockEvents,
        onAddEvent: vi.fn().mockResolvedValue(undefined),
        onDeleteEvent: vi.fn(),
        exerciseLogs: mockLogs,
        exerciseSettings: {},
        onSaveExerciseLog: vi.fn().mockResolvedValue(undefined),
        telegramReminders: mockReminders,
        onSaveTelegramReminder: vi.fn().mockResolvedValue(undefined),
        onDeleteTelegramReminder: vi.fn().mockResolvedValue(undefined),
        exams: mockExams,
        onAddExam: vi.fn().mockResolvedValue(undefined),
        onDeleteExam: vi.fn(),
        onUpdateExam: vi.fn().mockResolvedValue(undefined),
    };

    it('renders with full data without throwing ReferenceError', () => {
        expect(() => {
            render(<HealthView {...baseProps} />);
        }).not.toThrow();

        expect(screen.getByText('Painel de saúde')).toBeDefined();
        expect(screen.getByText('Telemetria')).toBeDefined();
        expect(screen.getByText('Arquivo médico')).toBeDefined();
    });

    it('renders with empty data without throwing', () => {
        const emptyProps = {
            ...baseProps,
            weights: [],
            waist: [],
            events: [],
            exerciseLogs: [],
            telegramReminders: [],
            exams: [],
        };

        expect(() => {
            render(<HealthView {...emptyProps} />);
        }).not.toThrow();
    });

    it('allows tab switching to Arquivo médico and opening consultation report', () => {
        render(<HealthView {...baseProps} />);

        // Switch to archive tab
        const archiveTabButtons = screen.getAllByRole('button', { name: 'Arquivo médico' });
        fireEvent.click(archiveTabButtons[0]);
        expect(screen.getByText('Ressonância Magnética Coluna Lombar')).toBeDefined();

        // Switch back to telemetry
        const telemetryTabButtons = screen.getAllByRole('button', { name: 'Telemetria' });
        fireEvent.click(telemetryTabButtons[0]);

        // Open report
        const reportButton = screen.getByRole('button', { name: /Gerar relatório para consulta/i });
        fireEvent.click(reportButton);
        expect(screen.getByText('Relatório de acompanhamento — coluna lombar')).toBeDefined();

        // Back to panel
        const backButton = screen.getByRole('button', { name: /Voltar ao painel/i });
        fireEvent.click(backButton);
        expect(screen.getByText('Painel de saúde')).toBeDefined();
    });
});
