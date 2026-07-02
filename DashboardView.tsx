import React, { useMemo, useState } from 'react';
import {
    Tarefa, FinanceTransaction, FinanceSettings, FixedBill, IncomeEntry,
    HealthWeight, DailyHabits, HealthSettings, ExerciseLog
} from './types';

interface DashboardViewProps {
    tarefas: Tarefa[];
    isDark?: boolean;
    financeTransactions: FinanceTransaction[];
    financeSettings: FinanceSettings;
    fixedBills: FixedBill[];
    incomeEntries: IncomeEntry[];
    healthWeights: HealthWeight[];
    healthDailyHabits: DailyHabits[];
    healthSettings: HealthSettings;
    exerciseLogs: ExerciseLog[];
    unidades: { id: string, nome: string }[];
    currentMonth: number;
    currentYear: number;
    onNavigate: (view: 'gallery' | 'finance' | 'saude') => void;
}

// --- CARD COMPONENT (Hermes Corporate Modern Design) ---
interface DashboardCardProps {
    title: string;
    onRedirect?: () => void;
    children: React.ReactNode;
    isDark?: boolean;
    headerAction?: React.ReactNode;
    className?: string;
    style?: React.CSSProperties;
}

const DashboardCard: React.FC<DashboardCardProps> = ({
    title,
    onRedirect,
    children,
    isDark = false,
    headerAction,
    className = "",
    style = {}
}) => {
    const isClickable = !!onRedirect;
    const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
        if (!onRedirect) return;
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onRedirect();
        }
    };

    return (
        <div
            onClick={onRedirect}
            onKeyDown={isClickable ? handleKeyDown : undefined}
            style={{
                boxShadow: isDark
                    ? '0 6px 12px rgba(0, 0, 0, 0.4), 0 4px 4px rgba(0, 0, 0, 0.2)'
                    : '0 6px 12px rgba(21, 28, 39, 0.05), 0 4px 4px rgba(21, 28, 39, 0.03)',
                fontFamily: 'Inter, sans-serif',
                ...style
            }}
            className={`group p-5 rounded-2xl border transition-all duration-300 flex flex-col min-h-0 shrink-0 ${
                isClickable ? 'cursor-pointer hover:border-[#861fdd]/40 hover:bg-slate-50/50 dark:hover:bg-slate-900/10' : ''
            } ${
                isDark
                    ? 'bg-[#151c27] border-[#2a313d] text-white'
                    : 'bg-[#ffffff] border-[#f3f4f6] text-[#151c27]'
            } ${className}`}
            role={isClickable ? "button" : undefined}
            tabIndex={isClickable ? 0 : undefined}
        >
            <div className="flex items-center justify-between mb-4 shrink-0">
                <h3 className={`text-xs font-bold uppercase tracking-[0.05em] font-sans ${
                    isDark ? 'text-[#ebf1ff]' : 'text-[#151c27]'
                }`}>
                    {title}
                </h3>
                <div className="flex items-center gap-1.5" onClick={(e) => isClickable && e.stopPropagation()}>
                    {headerAction}
                    {isClickable && (
                        <div className={`p-1.5 rounded-lg transition-all ${
                            isDark
                                ? 'text-slate-500 group-hover:bg-white/5 group-hover:text-[#ddb8ff]'
                                : 'text-slate-400 group-hover:bg-[#f5f3ff] group-hover:text-[#7800ce]'
                        }`}>
                            <svg className="w-4 h-4 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                            </svg>
                        </div>
                    )}
                </div>
            </div>
            <div className="flex-1 flex flex-col justify-start min-h-0">
                {children}
            </div>
        </div>
    );
};

// --- MASKED DATA PLACEHOLDER ---
const HiddenMoney = ({ className = "", compact = false }: { className?: string, compact?: boolean }) => (
    <span className={`inline-block font-bold tracking-normal select-none ${className}`} aria-label="valor oculto">
        <span className="opacity-70">R$</span> {compact ? '••••' : '••••••'}
    </span>
);

// --- MAIN COMPONENT ---
const DashboardView: React.FC<DashboardViewProps> = ({
    tarefas = [],
    isDark = false,
    financeTransactions = [],
    financeSettings = {} as FinanceSettings,
    fixedBills = [],
    incomeEntries = [],
    healthWeights = [],
    healthDailyHabits = [],
    healthSettings = {} as HealthSettings,
    exerciseLogs = [] as ExerciseLog[],
    currentMonth = new Date().getMonth(),
    currentYear = new Date().getFullYear(),
    onNavigate
}) => {
    const [isFinanceVisible, setIsFinanceVisible] = useState(false);

    // --- ACTIONS LOGIC ---
    const inProgressActions = useMemo(() => tarefas.filter(t => t.status !== 'concluído' && t.status !== 'excluído' as any), [tarefas]);

    const actionsByDay = useMemo(() => {
        const result = [];
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        for (let i = 0; i < 7; i++) {
            const d = new Date(today);
            d.setDate(today.getDate() + i);
            const dStr = d.toISOString().split('T')[0];
            const count = inProgressActions.filter(t => t.data_limite === dStr).length;

            result.push({
                dateStr: dStr,
                dayNum: d.getDate(),
                monthName: ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'][d.getMonth()],
                count,
                isToday: i === 0
            });
        }
        return result;
    }, [inProgressActions]);

    // --- FINANCE LOGIC ---
    const periodKey = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
    const currentBudget = financeSettings?.monthlyBudgets?.[periodKey] || financeSettings?.monthlyBudget || 0;

    const currentMonthTransactions = useMemo(() => financeTransactions.filter(t => {
        const d = new Date(t.date);
        return d.getMonth() === currentMonth && d.getFullYear() === currentYear && t.status !== 'deleted';
    }), [financeTransactions, currentMonth, currentYear]);

    const currentMonthTotalSpent = useMemo(() => currentMonthTransactions.reduce((acc, curr) => acc + curr.amount, 0), [currentMonthTransactions]);
    const availableBalance = currentBudget - currentMonthTotalSpent;

    const financeChartData = useMemo(() => {
        const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
        const monthName = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'][currentMonth];
        const result = [];

        for (let d = 1; d <= daysInMonth; d++) {
            const amount = currentMonthTransactions
                .filter(t => {
                    const transDate = new Date(t.date);
                    return transDate.getDate() === d;
                })
                .reduce((acc, curr) => acc + curr.amount, 0);

            if (amount > 0) {
                result.push({
                    day: d,
                    amount,
                    monthName
                });
            }
        }
        return result;
    }, [currentMonthTransactions, currentMonth, currentYear]);

    const currentMonthIncome = useMemo(() => incomeEntries
        .filter(e => e.month === currentMonth && e.year === currentYear && e.isReceived && e.status !== 'deleted')
        .reduce((acc, curr) => acc + curr.amount, 0), [incomeEntries, currentMonth, currentYear]);

    const currentTotalBills = useMemo(() => fixedBills
        .filter(b => b.month === currentMonth && b.year === currentYear)
        .reduce((acc, curr) => acc + curr.amount, 0), [fixedBills, currentMonth, currentYear]);

    // --- HEALTH LOGIC ---
    const sortedWeights = useMemo(() => [...healthWeights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()), [healthWeights]);
    const currentWeight = sortedWeights[0]?.weight || 0;
    const initialWeight = sortedWeights[sortedWeights.length - 1]?.weight || 0;
    const weightDelta = initialWeight > 0 ? initialWeight - currentWeight : 0;
    const weightDeltaAbs = Math.abs(weightDelta);
    const weightDeltaPrefix = weightDelta < -0.05 ? '+' : weightDelta > 0.05 ? '-' : '';

    const habitStreak = useMemo(() => {
        let streak = 0;
        const sortedHabits = [...healthDailyHabits].sort((a, b) => b.id.localeCompare(a.id));
        let checkDate = new Date();
        for (const habit of sortedHabits) {
            const hDate = habit.id;
            const expectedDate = checkDate.toISOString().split('T')[0];
            if (hDate === expectedDate) {
                const completedCount = [habit.noSugar, habit.noAlcohol, habit.noSnacks, habit.workout, habit.eatUntil18, habit.eatSlowly].filter(Boolean).length;
                if (completedCount >= 4) { streak++; checkDate.setDate(checkDate.getDate() - 1); } else break;
            } else if (hDate < expectedDate) break;
        }
        return streak;
    }, [healthDailyHabits]);

    const last7Habits = useMemo(() => {
        const today = new Date();
        return Array.from({ length: 7 }, (_, i) => {
            const d = new Date(today);
            d.setDate(today.getDate() - (6 - i));
            const key = d.toISOString().slice(0, 10);
            const record = healthDailyHabits.find(h => h.id === key);
            const done = record ? [record.noSugar, record.noAlcohol, record.noSnacks, record.workout, record.eatUntil18, record.eatSlowly].filter(Boolean).length : 0;
            return { label: String(d.getDate()).padStart(2, '0'), done, total: 6, isToday: i === 6 };
        });
    }, [healthDailyHabits]);

    const todayTelemetry = useMemo(() => {
        const key = new Date().toISOString().slice(0, 10);
        return exerciseLogs.find(l => l.id === key) || null;
    }, [exerciseLogs]);
    // --- PROGRESS BAR RENDER HELPER ---
    const renderProgressBar = (value: number, max: number) => {
        const percent = max > 0 ? Math.min((value / max) * 100, 100) : 0;
        return (
            <div className={`h-[6px] w-full rounded-full overflow-hidden ${isDark ? 'bg-[#2a313d]' : 'bg-[#f3f4f6]'}`}>
                <div style={{ width: `${percent}%` }} className="h-full bg-[#9333ea] rounded-full transition-all duration-500" />
            </div>
        );
    };

    return (
        <div
            style={{ fontFamily: 'Inter, sans-serif' }}
            className={`animate-in fade-in duration-700 flex flex-col gap-5 w-full max-w-[1600px] mx-auto p-4 md:p-6 overflow-hidden ${
                isDark ? 'text-white' : 'text-[#151c27]'
            }`}
        >

            <div className="flex flex-col xl:flex-row gap-6 w-full items-stretch min-h-0 xl:h-[calc(100vh-7rem)]">

                {/* 1. COLUNA ESQUERDA: Área de Trabalho (Flexível) */}
                <div className="flex-1 flex flex-col gap-6 xl:overflow-y-auto custom-scrollbar xl:max-h-[calc(100vh-7rem)] pr-1">

                    {/* CARD: Carga de Trabalho Semanal */}
                    <DashboardCard title="Carga Semanal de Trabalho" isDark={isDark} onRedirect={() => onNavigate('gallery')}>
                        <div className="flex flex-col gap-4">
                            <p className="text-[10px] font-bold uppercase tracking-[0.2em] font-mono text-slate-400">
                                // CARGA OPERACIONAL D+6
                            </p>

                            <div className="grid grid-cols-7 gap-2 md:gap-3 border-b border-[#f3f4f6] pb-2 dark:border-white/5">
                                {actionsByDay.map((day, i) => {
                                    const maxCount = Math.max(...actionsByDay.map(d => d.count), 1);
                                    const heightPercent = (day.count / maxCount) * 100;

                                    return (
                                        <div key={i} className="flex min-w-0 flex-col items-center group">
                                            <div className="flex h-40 w-full flex-col justify-end">
                                                <div className="flex h-32 w-full items-end">
                                                    <div
                                                        className="flex w-full flex-col items-center"
                                                        style={{ height: day.count > 0 ? `${Math.max(heightPercent, 8)}%` : '2px' }}
                                                    >
                                                        <span className={`mb-1 block text-center text-[11px] font-bold font-mono leading-none transition-colors ${
                                                            day.count > 0
                                                                ? (day.isToday ? 'text-[#7800ce] dark:text-[#ddb8ff]' : 'text-slate-600 dark:text-slate-300')
                                                                : 'text-slate-300 dark:text-slate-700'
                                                        }`}>
                                                            {String(day.count).padStart(2, '0')}
                                                        </span>
                                                        <div
                                                            className={`min-h-0 w-full flex-1 transition-all duration-300 rounded-lg ${
                                                                day.isToday
                                                                    ? 'bg-[#7800ce] shadow-[0_0_12px_rgba(120,0,206,0.3)]'
                                                                    : day.count > 0
                                                                        ? 'bg-[#9333ea]/20 hover:bg-[#9333ea]/40'
                                                                        : isDark ? 'bg-white/5' : 'bg-slate-100'
                                                            }`}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="mt-3 flex flex-col items-center gap-0.5">
                                                <span className={`text-[10px] font-bold font-mono ${
                                                    day.isToday ? 'text-[#7800ce] dark:text-[#ddb8ff]' : 'text-slate-400 dark:text-slate-500'
                                                }`}>
                                                    {String(day.dayNum).padStart(2, '0')}
                                                </span>
                                                <span className="text-[8px] font-semibold text-slate-400 uppercase tracking-widest font-mono">
                                                    {day.monthName}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </DashboardCard>
                    {/* CARD: Painel Financeiro */}
                    <DashboardCard
                        title="Resumo Financeiro"
                        isDark={isDark}
                        onRedirect={() => onNavigate('finance')}
                        headerAction={
                            <button
                                onClick={(e) => { e.stopPropagation(); setIsFinanceVisible(!isFinanceVisible); }}
                                className={`p-1.5 rounded-lg border transition-all ${
                                    isDark
                                        ? 'border-white/10 text-slate-400 hover:text-white hover:bg-white/5'
                                        : 'border-[#e5e7eb] text-slate-500 hover:text-[#9333ea] hover:bg-[#f5f3ff]'
                                }`}
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    {isFinanceVisible ? (
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                    ) : (
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                                    )}
                                </svg>
                            </button>
                        }
                    >
                        <div className="flex flex-col gap-5">
                            <div className="flex items-center justify-between">
                                <div className="flex flex-col gap-1">
                                    <span className="text-[10px] font-bold uppercase tracking-[0.2em] font-mono text-slate-400">
                                        Consumo Mensal
                                    </span>
                                    <div className="text-2xl font-bold font-mono text-[#10b981]">
                                        {isFinanceVisible ? (
                                            <>
                                                <span className="text-xs opacity-75 font-sans mr-0.5">R$</span>
                                                {currentMonthTotalSpent.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                            </>
                                        ) : (
                                            <HiddenMoney compact />
                                        )}
                                    </div>
                                </div>
                                <div className="text-right flex flex-col gap-1">
                                    <span className="text-[10px] font-bold uppercase tracking-[0.2em] font-mono text-slate-400">
                                        Saldo Disponível
                                    </span>
                                    <div className={`text-base font-bold font-mono ${
                                        availableBalance < 0 ? 'text-[#ba1a1a]' : 'text-slate-600 dark:text-slate-300'
                                    }`}>
                                        {isFinanceVisible ? (
                                            <>
                                                <span className="text-xs opacity-75 mr-0.5">R$</span>
                                                {availableBalance.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                            </>
                                        ) : (
                                            '••••'
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Progresso de Orçamento */}
                            <div className="flex flex-col gap-1.5">
                                <div className="flex justify-between text-[11px] text-slate-500">
                                    <span>Limite Planejado</span>
                                    <span className="font-mono">
                                        {isFinanceVisible ? `R$ ${currentBudget.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '••••'}
                                    </span>
                                </div>
                                {renderProgressBar(currentMonthTotalSpent, currentBudget)}
                            </div>

                            <hr className={isDark ? 'border-white/10' : 'border-[#e5e7eb]'} />

                            {/* Gráfico Financeiro */}
                            <div className="flex flex-col gap-2">
                                <span className="text-[10px] font-bold uppercase tracking-[0.2em] font-mono text-slate-400">
                                    // CONSUMO DIÁRIO DO PERÍODO
                                </span>
                                <div className="h-20 flex items-end gap-1 px-1 relative">
                                    {isFinanceVisible ? (
                                        financeChartData.length > 0 ? (
                                            financeChartData.map((item, i) => {
                                                const maxAmount = Math.max(...financeChartData.map(d => d.amount), 1);
                                                const heightPercent = (item.amount / maxAmount) * 100;
                                                return (
                                                    <div key={i} className="flex-1 min-w-[8px] flex flex-col justify-end h-full group">
                                                        <div
                                                            style={{ height: `${Math.max(heightPercent, 6)}%` }}
                                                            className="w-full bg-[#10b981]/30 group-hover:bg-[#10b981] transition-all duration-300 rounded-sm"
                                                            title={`Dia ${item.day}: R$ ${item.amount.toFixed(2)}`}
                                                        />
                                                    </div>
                                                );
                                            })
                                        ) : (
                                            <div className="flex-1 h-full flex items-center justify-center border border-dashed border-[#e5e7eb] dark:border-white/10 rounded-xl">
                                                <span className="text-[10px] uppercase font-mono italic text-slate-400">Sem registros neste mês</span>
                                            </div>
                                        )
                                    ) : (
                                        <div className="flex-1 h-full flex items-center justify-center border border-dashed border-[#e5e7eb] dark:border-white/10 rounded-xl bg-slate-500/5 backdrop-blur-[1px]">
                                            <span className="text-[10px] uppercase tracking-wider font-mono font-bold text-slate-400">DADOS OMITIDOS DE FORMA SEGURA</span>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Resumo Caixa de Entradas/Saídas */}
                            <div className="grid grid-cols-2 gap-4 text-xs font-medium">
                                <div className={`p-3 rounded-xl border ${isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'}`}>
                                    <span className="text-[9px] uppercase tracking-wider text-slate-400 font-mono">Receitas do Mês</span>
                                    <p className="text-sm font-bold text-[#10b981] mt-1 font-mono">
                                        {isFinanceVisible ? `R$ ${currentMonthIncome.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '••••'}
                                    </p>
                                </div>
                                <div className={`p-3 rounded-xl border ${isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'}`}>
                                    <span className="text-[9px] uppercase tracking-wider text-slate-400 font-mono">Contas Fixas</span>
                                    <p className="text-sm font-bold text-slate-600 dark:text-slate-300 mt-1 font-mono">
                                        {isFinanceVisible ? `R$ ${currentTotalBills.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '••••'}
                                    </p>
                                </div>
                            </div>
                        </div>
                    </DashboardCard>

                </div>

                {/* 2. COLUNA DIREITA: Saúde & Telemetria (320px Fixo) */}
                <div className="w-full xl:w-[320px] shrink-0 flex flex-col gap-6 xl:overflow-y-auto custom-scrollbar xl:max-h-[calc(100vh-7rem)] pr-1">
                    {/* CARD: Saúde & Telemetria */}
                    <DashboardCard title="Saúde & Telemetria" isDark={isDark} onRedirect={() => onNavigate('saude')}>
                        <div className="flex flex-col gap-4">
                            <div className="flex items-center justify-between shrink-0">
                                <span className="text-[9px] uppercase tracking-wider text-slate-400 font-mono">// MONITORAMENTO HÁBITOS</span>
                                <span className="rounded-full bg-[#10b981] text-white text-[9px] font-bold px-2 py-0.5 font-sans uppercase">
                                    {habitStreak} Dias Seguidos
                                </span>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div className={`p-3 rounded-xl border flex flex-col justify-center ${
                                    isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'
                                }`}>
                                    <span className="text-[8px] font-bold uppercase tracking-wider text-slate-400 font-mono">Massa</span>
                                    <div className="text-base font-bold font-mono mt-0.5">
                                        {currentWeight > 0 ? `${currentWeight.toFixed(1)}` : '-'}
                                        {currentWeight > 0 && <span className="text-[10px] text-slate-400 font-sans ml-0.5">KG</span>}
                                    </div>
                                    <div className="text-[9px] font-bold font-mono text-slate-400 mt-0.5">
                                        Delta {currentWeight > 0 ? `${weightDeltaPrefix}${weightDeltaAbs.toFixed(1)}` : '-'}
                                    </div>
                                </div>

                                <div className={`p-3 rounded-xl border flex flex-col justify-center ${
                                    isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'
                                }`}>
                                    <span className="text-[8px] font-bold uppercase tracking-wider text-slate-400 font-mono">Passos</span>
                                    <div className="text-base font-bold font-mono mt-0.5">
                                        {todayTelemetry?.walk?.steps ? todayTelemetry.walk.steps.toLocaleString('pt-BR') : '-'}
                                    </div>
                                    <div className="text-[9px] font-bold font-mono text-slate-400 mt-0.5">
                                        {todayTelemetry?.walk?.distance ? `${todayTelemetry.walk.distance.toFixed(1)} KM` : '-'}
                                    </div>
                                </div>

                                <div className={`p-3 rounded-xl border flex flex-col justify-center ${
                                    isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'
                                }`}>
                                    <span className="text-[8px] font-bold uppercase tracking-wider text-slate-400 font-mono">Calorias</span>
                                    <div className="text-base font-bold font-mono mt-0.5">
                                        {todayTelemetry?.calories ? Math.round(todayTelemetry.calories).toLocaleString('pt-BR') : '-'}
                                        {todayTelemetry?.calories && <span className="text-[9px] text-slate-400 font-sans ml-0.5">KCAL</span>}
                                    </div>
                                    <div className="text-[9px] font-bold font-mono text-slate-400 mt-0.5">
                                        {todayTelemetry?.activeMinutes ? `${todayTelemetry.activeMinutes} MIN ATIVOS` : '-'}
                                    </div>
                                </div>

                                <div className={`p-3 rounded-xl border flex flex-col justify-center ${
                                    isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'
                                }`}>
                                    <span className="text-[8px] font-bold uppercase tracking-wider text-slate-400 font-mono">Repouso</span>
                                    <div className="text-base font-bold font-mono mt-0.5">
                                        {todayTelemetry?.sleep?.totalMinutes ? `${Math.floor(todayTelemetry.sleep.totalMinutes / 60)}h ${todayTelemetry.sleep.totalMinutes % 60}m` : '-'}
                                    </div>
                                    <div className="text-[9px] font-bold font-mono text-slate-400 mt-0.5">
                                        STATUS NOMINAL
                                    </div>
                                </div>
                            </div>

                            {/* Habit Completion Last 7 Days */}
                            <div className="flex flex-col gap-2 mt-2">
                                <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 font-mono">// ÚLTIMOS 7 DIAS</span>
                                <div className="flex justify-between items-center gap-1.5 bg-[#f9fafb] dark:bg-white/[0.01] border border-[#f3f4f6] dark:border-white/5 p-3 rounded-xl">
                                    {last7Habits.map((h, i) => {
                                        const donePercent = h.total > 0 ? (h.done / h.total) * 100 : 0;
                                        return (
                                            <div key={i} className="flex-1 flex flex-col items-center gap-1.5">
                                                <div className="h-10 w-2.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden flex flex-col justify-end">
                                                    <div
                                                        style={{ height: `${donePercent}%` }}
                                                        className={`w-full rounded-full transition-all duration-300 ${
                                                            h.done >= 4 ? 'bg-[#10b981]' : h.done > 0 ? 'bg-[#9333ea]/60' : 'bg-transparent'
                                                        }`}
                                                    />
                                                </div>
                                                <span className={`text-[8px] font-bold font-mono ${
                                                    h.isToday ? 'text-[#7800ce] dark:text-[#ddb8ff]' : 'text-slate-400'
                                                }`}>
                                                    {h.label}
                                                </span>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                        </div>
                    </DashboardCard>

                </div>

            </div>
        </div>
    );
};

export default DashboardView;
