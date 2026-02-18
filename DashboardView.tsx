
import React, { useMemo, useState } from 'react';
import { Tarefa, FinanceTransaction, FinanceSettings, FixedBill, IncomeEntry, HealthWeight } from './types';

interface DashboardViewProps {
    tarefas: Tarefa[];
    financeTransactions: FinanceTransaction[];
    financeSettings: FinanceSettings;
    fixedBills: FixedBill[];
    incomeEntries: IncomeEntry[];
    healthWeights: HealthWeight[];
    unidades: { id: string, nome: string }[];
    sistemasDetalhes: any[]; // Adjust if you have a specific type for this
    currentMonth: number;
    currentYear: number;
}

const DashboardSection = ({ title, iconColor, children }: { title: string, iconColor: string, children: React.ReactNode }) => {
    const [isExpanded, setIsExpanded] = useState(true);

    return (
        <div className="bg-white p-6 md:p-8 rounded-none md:rounded-[2.5rem] border border-slate-200 shadow-lg h-full">
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full text-xl font-black text-slate-900 mb-6 flex items-center justify-between group"
            >
                <div className="flex items-center gap-3">
                    <span className={`w-2 h-8 ${iconColor} rounded-full`}></span>
                    {title}
                </div>
                <svg className={`w-5 h-5 text-slate-300 group-hover:text-slate-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {isExpanded && (
                <div className="animate-in slide-in-from-top-2 duration-300">
                    {children}
                </div>
            )}
        </div>
    );
};

const DashboardView: React.FC<DashboardViewProps> = ({
    tarefas,
    financeTransactions,
    financeSettings,
    fixedBills,
    incomeEntries,
    healthWeights,
    unidades,
    sistemasDetalhes,
    currentMonth,
    currentYear
}) => {
    const todayStr = new Date().toISOString().split('T')[0];

    // --- ACTIONS LOGIC ---
    const overdueActionsCount = useMemo(() => {
        return tarefas.filter(t =>
            t.status !== 'concluído' &&
            t.data_limite &&
            t.data_limite !== '-' &&
            t.data_limite < todayStr
        ).length;
    }, [tarefas, todayStr]);

    const todayActionsCount = useMemo(() => {
        return tarefas.filter(t =>
            t.status !== 'concluído' &&
            t.data_limite === todayStr
        ).length;
    }, [tarefas, todayStr]);

    // --- FINANCE LOGIC ---
    const periodKey = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
    const currentBudget = financeSettings.monthlyBudgets?.[periodKey] || financeSettings.monthlyBudget || 0;

    const currentMonthTransactions = useMemo(() => {
        return financeTransactions.filter(t => {
            const d = new Date(t.date);
            return d.getMonth() === currentMonth && d.getFullYear() === currentYear && t.status !== 'deleted';
        });
    }, [financeTransactions, currentMonth, currentYear]);

    const currentMonthTotalSpent = useMemo(() => {
        return currentMonthTransactions.reduce((acc, curr) => acc + curr.amount, 0);
    }, [currentMonthTransactions]);


    const emergencyReserveTarget = financeSettings.emergencyReserveTarget || 0;
    const emergencyReserveCurrent = financeSettings.emergencyReserveCurrent || 0;
    const emergencyReservePercent = emergencyReserveTarget > 0
        ? Math.min((emergencyReserveCurrent / emergencyReserveTarget) * 100, 100)
        : 0;

    // --- HEALTH LOGIC ---
    const sortedWeights = useMemo(() => {
        return [...healthWeights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    }, [healthWeights]);

    const currentWeight = sortedWeights[0]?.weight || 0;
    const initialWeight = sortedWeights[sortedWeights.length - 1]?.weight || 0;
    const totalWeightLost = initialWeight > 0 ? initialWeight - currentWeight : 0;

    // --- SYSTEMS LOGIC ---
    const concludedTasksThisMonth = useMemo(() => {
        return tarefas.filter(t => {
            if (t.status !== 'concluído' || !t.data_conclusao) return false;
            const d = new Date(t.data_conclusao);
            return d.getMonth() === currentMonth && d.getFullYear() === currentYear;
        });
    }, [tarefas, currentMonth, currentYear]);

    const productivityEfficacy = useMemo(() => {
        if (concludedTasksThisMonth.length === 0) return 0;
        const highImpact = concludedTasksThisMonth.filter(t => t.contabilizar_meta || t.prioridade === 'alta').length;
        return (highImpact / concludedTasksThisMonth.length) * 100;
    }, [concludedTasksThisMonth]);

    const systems = useMemo(() => {
        return unidades.filter(u => u.nome.startsWith('SISTEMA:'));
    }, [unidades]);

    const systemStats = useMemo(() => {
        return systems.map(sys => {
            const details = sistemasDetalhes.find(d => d.id === sys.id);
            return {
                name: sys.nome.replace('SISTEMA:', '').trim(),
                status: details?.status || 'ideia'
            };
        });
    }, [systems, sistemasDetalhes]);

    // --- RENDERING HELPERS ---
    const budgetPercent = currentBudget > 0 ? (currentMonthTotalSpent / currentBudget) * 100 : 0;
    const availableBalance = currentBudget - currentMonthTotalSpent;

    // Last 7 days spending for Sparkline
    const last7DaysSpending = useMemo(() => {
        const days = [];
        for (let i = 6; i >= 0; i--) {
            const d = new Date();
            d.setDate(d.getDate() - i);
            const dStr = d.toISOString().split('T')[0];
            const dayTotal = financeTransactions
                .filter(t => t.date === dStr && t.status !== 'deleted')
                .reduce((acc, curr) => acc + curr.amount, 0);
            days.push(dayTotal);
        }
        return days;
    }, [financeTransactions]);

    const last7DaysWeight = useMemo(() => {
        const days = [];
        for (let i = 6; i >= 0; i--) {
            const d = new Date();
            d.setDate(d.getDate() - i);
            const dStr = d.toISOString().split('T')[0];
            // Find weight for this day or the closest previous one
            const weightEntry = [...healthWeights]
                .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
                .find(w => w.date <= dStr);
            days.push(weightEntry ? weightEntry.weight : initialWeight);
        }
        return days;
    }, [healthWeights, initialWeight]);

    const weightDelta = useMemo(() => {
        if (last7DaysWeight.length < 2) return 0;
        const current = last7DaysWeight[6];
        const previous = last7DaysWeight[0];
        return previous > 0 ? ((current - previous) / previous) * 100 : 0;
    }, [last7DaysWeight]);

    const dailyAverageSpent = useMemo(() => {
        const total = last7DaysSpending.reduce((a, b) => a + b, 0);
        return total / 7;
    }, [last7DaysSpending]);

    const spendingVariance = useMemo(() => {
        if (last7DaysSpending.length === 0) return 0;
        const mean = dailyAverageSpent;
        const squareDiffs = last7DaysSpending.map(value => Math.pow(value - mean, 2));
        const avgSquareDiff = squareDiffs.reduce((a, b) => a + b, 0) / last7DaysSpending.length;
        return Math.sqrt(avgSquareDiff);
    }, [last7DaysSpending, dailyAverageSpent]);

    const spendingVolatility = dailyAverageSpent > 0 ? (spendingVariance / dailyAverageSpent) * 100 : 0;

    const spentToday = last7DaysSpending[6];
    const deltaVsAverage = dailyAverageSpent > 0 ? ((spentToday - dailyAverageSpent) / dailyAverageSpent) * 100 : 0;

    const offendingCategories = useMemo(() => {
        const cats: Record<string, number> = {};
        currentMonthTransactions.forEach(t => {
            cats[t.category] = (cats[t.category] || 0) + t.amount;
        });
        return Object.entries(cats)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([name, amount]) => ({ name, amount, percent: (amount / (currentMonthTotalSpent || 1)) * 100 }));
    }, [currentMonthTransactions, currentMonthTotalSpent]);

    const Sparkline = ({ data, color }: { data: number[], color: string }) => {
        if (!data || data.length === 0) return null;
        const max = Math.max(...data, 1);
        const min = Math.min(...data);
        const range = max - min || 1;
        const width = 100;
        const height = 30;
        const points = data.map((d, i) => {
            const x = (i / (data.length - 1)) * width;
            const y = height - ((d - min) / range) * height;
            return `${x},${y}`;
        }).join(' ');

        return (
            <svg viewBox={`0 0 ${width} ${height}`} className="w-24 h-8 overflow-visible">
                <polyline
                    fill="none"
                    stroke={color}
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points={points}
                />
            </svg>
        );
    };

    interface CompositeCardProps {
        title: string;
        value: string;
        delta: number;
        sparkData: number[];
        isAlert: boolean;
    }

    const CompositeCard = ({ title, value, delta, sparkData, isAlert }: CompositeCardProps) => (
        <div className={`bg-white p-6 rounded-[2rem] border ${isAlert ? 'border-rose-200 bg-rose-50/30' : 'border-slate-200 shadow-sm'} flex flex-col justify-between h-full transition-all hover:shadow-md`}>
            <div>
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">{title}</p>
                <div className={`text-2xl font-black ${isAlert ? 'text-rose-600' : 'text-slate-900'}`}>
                    {value}
                </div>
            </div>
            <div className="flex items-center justify-between mt-4">
                <div className={`text-[10px] font-bold ${delta > 0 ? (isAlert ? 'text-rose-500' : 'text-emerald-500') : 'text-slate-400'}`}>
                    {delta > 0 ? '▲' : delta < 0 ? '▼' : ''} {Math.abs(delta).toFixed(0)}% vs média
                </div>
                <Sparkline data={sparkData} color={isAlert ? '#e11d48' : '#64748b'} />
            </div>
        </div>
    );

    return (
        <div className="animate-in fade-in duration-700 space-y-8 pb-12">
            {/* Header: SITUAÇÃO SITUACIONAL */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
                <div className="lg:col-span-8 bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                    <div className="space-y-1">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Saldo Disponível do Mês</p>
                        <div className={`text-[3.5rem] leading-none font-black tracking-tighter ${availableBalance < 0 ? 'text-rose-600' : 'text-slate-900'}`}>
                            R$ {availableBalance.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                        </div>
                        <div className="flex items-center gap-2 mt-2">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase ${budgetPercent > 90 ? 'bg-rose-100 text-rose-600' : 'bg-emerald-100 text-emerald-600'}`}>
                                {budgetPercent.toFixed(1)}% do orçamento
                            </span>
                            <span className="text-[10px] font-bold text-slate-400 uppercase">
                                {new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}
                            </span>
                        </div>
                    </div>

                    <div className="flex gap-4">
                        <div className={`px-6 py-4 rounded-3xl border ${overdueActionsCount > 0 ? 'bg-rose-50 border-rose-100' : 'bg-slate-50 border-slate-100'} flex flex-col`}>
                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Ações Imediatas</span>
                            <div className="flex items-baseline gap-2">
                                <span className={`text-3xl font-black ${overdueActionsCount > 0 ? 'text-rose-600' : 'text-slate-900'}`}>
                                    {overdueActionsCount + todayActionsCount}
                                </span>
                                {overdueActionsCount > 0 && (
                                    <span className="text-[10px] font-black text-rose-500 uppercase">({overdueActionsCount} Atrasadas)</span>
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                <div className="lg:col-span-4 grid grid-cols-1 gap-4">
                    <div className="bg-slate-900 p-6 rounded-[2.5rem] shadow-xl text-white flex flex-col justify-center">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Eficácia: Orçamento</p>
                        <div className={`text-3xl font-black ${budgetPercent <= 100 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {Math.max(0, 100 - budgetPercent).toFixed(1)}%
                        </div>
                        <p className="text-[9px] font-medium text-slate-500 uppercase">Economia Potencial</p>
                    </div>
                    <div className="bg-white p-6 rounded-[2.5rem] border border-slate-200 shadow-xl flex flex-col justify-center">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Qualidade das Ações</p>
                        <div className={`text-3xl font-black ${productivityEfficacy > 70 ? 'text-emerald-600' : productivityEfficacy > 40 ? 'text-amber-500' : 'text-rose-500'}`}>
                            {productivityEfficacy.toFixed(0)}%
                        </div>
                        <p className="text-[9px] font-medium text-slate-400 uppercase">Impacto Real vs Volume</p>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                {/* LADO ESQUERDO: Ação Imediata */}
                <div className="lg:col-span-4 space-y-8">
                    <DashboardSection title="O que exige atenção agora" iconColor="bg-rose-500">
                        <div className="space-y-4">
                            {overdueActionsCount > 0 && (
                                <div className="p-4 bg-rose-50 rounded-2xl border border-rose-100 flex items-center justify-between">
                                    <span className="text-sm font-bold text-rose-700">Ações Vencidas</span>
                                    <span className="bg-rose-600 text-white px-3 py-1 rounded-full text-xs font-black">{overdueActionsCount}</span>
                                </div>
                            )}
                            {todayActionsCount > 0 && (
                                <div className="p-4 bg-amber-50 rounded-2xl border border-amber-100 flex items-center justify-between">
                                    <span className="text-sm font-bold text-amber-700">Ações para Hoje</span>
                                    <span className="bg-amber-500 text-white px-3 py-1 rounded-full text-xs font-black">{todayActionsCount}</span>
                                </div>
                            )}
                            {budgetPercent > 90 && (
                                <div className="p-4 bg-rose-50 rounded-2xl border border-rose-100 flex items-center justify-between">
                                    <span className="text-sm font-bold text-rose-700">Risco de Orçamento</span>
                                    <span className="text-[10px] font-black text-rose-600 uppercase">Crítico</span>
                                </div>
                            )}
                            {overdueActionsCount === 0 && todayActionsCount === 0 && budgetPercent <= 90 && (
                                <div className="py-12 flex flex-col items-center text-center">
                                    <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mb-4">
                                        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                    </div>
                                    <p className="text-sm font-bold text-slate-500">Tudo sob controle!</p>
                                </div>
                            )}
                        </div>

                        <div className="mt-8 pt-8 border-t border-slate-50">
                            <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Categorias Ofensoras (Gastos)</h4>
                            <div className="space-y-3 mb-6">
                                {offendingCategories.map(cat => (
                                    <div key={cat.name} className="flex flex-col gap-1">
                                        <div className="flex justify-between text-[11px] font-bold">
                                            <span className="text-slate-600 uppercase">{cat.name}</span>
                                            <span className="text-slate-900">{cat.percent.toFixed(1)}%</span>
                                        </div>
                                        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                            <div className="h-full bg-slate-400" style={{ width: `${cat.percent}%` }} />
                                        </div>
                                    </div>
                                ))}
                            </div>

                            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100">
                                <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Volatilidade de Gastos (7d)</p>
                                <div className="flex items-center justify-between">
                                    <span className={`text-lg font-black ${spendingVolatility > 50 ? 'text-rose-500' : 'text-slate-700'}`}>
                                        {spendingVolatility.toFixed(0)}%
                                    </span>
                                    <span className="text-[9px] font-bold text-slate-400 uppercase">
                                        {spendingVolatility > 50 ? 'Desvio Alto' : 'Estável'}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </DashboardSection>
                </div>

                {/* LADO DIREITO: Tendências e Eficácia */}
                <div className="lg:col-span-8 space-y-8">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <CompositeCard
                            title="Fluxo de Caixa (Hoje)"
                            value={`R$ ${spentToday.toLocaleString('pt-BR')}`}
                            delta={deltaVsAverage}
                            sparkData={last7DaysSpending}
                            isAlert={spentToday > dailyAverageSpent * 1.2}
                        />
                        <CompositeCard
                            title="Saúde & Peso"
                            value={`${currentWeight.toFixed(1)} kg`}
                            delta={weightDelta}
                            sparkData={last7DaysWeight}
                            isAlert={weightDelta > 0}
                        />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {/* Reserva de Emergência */}
                        <DashboardSection title="Reserva de Emergência" iconColor="bg-emerald-500">
                            <div className="flex items-center gap-6">
                                <div className="relative w-24 h-24">
                                    <svg viewBox="0 0 36 36" className="w-24 h-24 transform -rotate-90">
                                        <path className="text-slate-100" stroke="currentColor" strokeWidth="3" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                                        <path className="text-emerald-500" stroke="currentColor" strokeWidth="3" strokeDasharray={`${emergencyReservePercent}, 100`} fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                                    </svg>
                                    <div className="absolute inset-0 flex items-center justify-center text-xs font-black text-slate-900">
                                        {emergencyReservePercent.toFixed(0)}%
                                    </div>
                                </div>
                                <div className="flex-1">
                                    <div className="text-xl font-black text-slate-900">R$ {emergencyReserveCurrent.toLocaleString('pt-BR')}</div>
                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">de R$ {emergencyReserveTarget.toLocaleString('pt-BR')}</p>
                                </div>
                            </div>
                        </DashboardSection>

                        {/* Sistemas */}
                        <DashboardSection title="Status de Sistemas" iconColor="bg-blue-500">
                            <div className="flex flex-wrap gap-2">
                                {systemStats.map(sys => (
                                    <div key={sys.name} className="px-3 py-1 bg-slate-50 border border-slate-100 rounded-lg flex items-center gap-2">
                                        <span className="text-[10px] font-bold text-slate-600">{sys.name}</span>
                                        <div className={`w-1.5 h-1.5 rounded-full ${sys.status === 'producao' ? 'bg-emerald-500' : 'bg-blue-500'}`} />
                                    </div>
                                ))}
                            </div>
                            <div className="mt-4 text-[10px] font-bold text-slate-400">
                                {systemStats.filter(s => s.status === 'producao').length} de {systemStats.length} em produção
                            </div>
                        </DashboardSection>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default DashboardView;
