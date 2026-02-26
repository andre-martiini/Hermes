import React, { useMemo } from 'react';
import { 
    Tarefa, FinanceTransaction, FinanceSettings, FixedBill, IncomeEntry, 
    HealthWeight, DailyHabits, HealthSettings, WorkItem, Sistema 
} from './types';

interface DashboardViewProps {
    tarefas: Tarefa[];
    financeTransactions: FinanceTransaction[];
    financeSettings: FinanceSettings;
    fixedBills: FixedBill[];
    incomeEntries: IncomeEntry[];
    healthWeights: HealthWeight[];
    healthDailyHabits: DailyHabits[];
    healthSettings: HealthSettings;
    unidades: { id: string, nome: string }[];
    sistemasDetalhes: Sistema[];
    workItems: WorkItem[];
    currentMonth: number;
    currentYear: number;
    onNavigate: (view: 'gallery' | 'finance' | 'saude' | 'sistemas-dev') => void;
    onOpenBacklog: () => void;
}

// --- SUBCOMPONENTES MOVIDOS PARA FORA ---

const DashboardCard = ({ title, iconColor, onRedirect, children }: { title: string, iconColor: string, onRedirect: () => void, children: React.ReactNode }) => (
    <div 
        onClick={onRedirect}
        className="group bg-white p-3 md:p-4 rounded-2xl md:rounded-[1.5rem] border border-slate-200 shadow-sm md:shadow-md hover:shadow-xl hover:border-slate-300 h-full transition-all flex flex-col cursor-pointer min-h-0"
        role="button"
        tabIndex={0}
    >
        <div className="flex items-center justify-between mb-2 shrink-0">
            <div className="flex items-center gap-2">
                <span className={`w-1.5 h-5 md:h-7 ${iconColor} rounded-full`}></span>
                <h3 className="text-xs md:text-base font-black text-slate-900 uppercase tracking-tight">{title}</h3>
            </div>
            <div className="p-2 rounded-xl text-slate-400 group-hover:bg-slate-50 group-hover:text-slate-900 transition-all">
                <svg className="w-5 h-5 transition-transform group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
            </div>
        </div>
        <div className="flex-1 flex flex-col justify-center min-h-0 overflow-hidden">
            {children}
        </div>
    </div>
);

const PieChart = ({ data }: { data: [string, number][] }) => {
    const total = data.reduce((acc, curr) => acc + curr[1], 0);
    if (total === 0) return <div className="h-24 md:h-40 flex items-center justify-center text-slate-300 text-[10px] font-black uppercase">Sem dados</div>;

    let currentAngle = 0;
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

    return (
        <div className="flex items-center gap-3 md:gap-6">
            <svg viewBox="0 0 100 100" className="w-16 h-16 md:w-28 md:h-28 transform -rotate-90 shrink-0 drop-shadow-lg">
                {data.map((item, i) => {
                    const percentage = item[1] / total;
                    const angle = percentage * 360;
                    
                    if (percentage === 1) {
                        return <circle key={i} cx="50" cy="50" r="40" fill={colors[i % colors.length]} />;
                    }

                    const x1 = 50 + 40 * Math.cos((currentAngle * Math.PI) / 180);
                    const y1 = 50 + 40 * Math.sin((currentAngle * Math.PI) / 180);
                    const x2 = 50 + 40 * Math.cos(((currentAngle + angle) * Math.PI) / 180);
                    const y2 = 50 + 40 * Math.sin(((currentAngle + angle) * Math.PI) / 180);

                    const largeArc = angle > 180 ? 1 : 0;
                    const d = `M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z`;

                    currentAngle += angle;
                    return <path key={i} d={d} className="transition-all duration-500 hover:opacity-80 cursor-pointer" fill={colors[i % colors.length]} />;
                })}
                <circle cx="50" cy="50" r="22" fill="white" />
            </svg>
            <div className="space-y-1 md:space-y-1.5 flex-1 min-w-0">
                {data.slice(0, 5).map((item, i) => (
                    <div key={i} className="flex items-center justify-between gap-3 group">
                        <div className="flex items-center gap-2 truncate">
                            <div className="w-2 h-2 md:w-2.5 md:h-2.5 rounded-full shrink-0 shadow-sm" style={{ backgroundColor: colors[i % colors.length] }}></div>
                            <span className="text-[9px] md:text-[11px] font-bold text-slate-600 uppercase truncate group-hover:text-slate-900 transition-colors">{item[0]}</span>
                        </div>
                        <span className="text-[10px] md:text-xs font-black text-slate-900">{item[1]}</span>
                    </div>
                ))}
            </div>
        </div>
    );
};

const BarChart = ({ data, color, maxHeight = 65 }: { data: number[], color: string, maxHeight?: number }) => {
    const max = Math.max(...data, 1);
    const chartHeightClass = "h-[40px] md:h-[65px]";
    return (
        <div className={`flex items-end gap-0.5 md:gap-1 ${chartHeightClass} w-full bg-slate-50/50 rounded-lg md:rounded-xl px-1 md:px-2 pb-1 md:pb-2`}>
            {data.map((v, i) => (
                <div key={i} className="flex-1 flex flex-col justify-end items-center gap-0.5 group">
                    <div
                        className="w-full rounded-t-sm md:rounded-t-md transition-all group-hover:opacity-80 cursor-pointer"
                        style={{
                            height: `${(v / max) * (typeof window !== 'undefined' && window.innerWidth >= 768 ? 50 : 35)}px`,
                            backgroundColor: color,
                            minWidth: '2px'
                        }}
                        title={`Dia ${i + 1}: R$ ${v.toFixed(2)}`}
                    />
                    <span className="text-[6px] md:text-[8px] text-slate-400 font-bold opacity-60 group-hover:opacity-100">{i + 1}</span>
                </div>
            ))}
        </div>
    );
};

const SystemsBarChart = ({ data }: { data: [string, number][] }) => {
    const max = Math.max(...data.map(d => d[1]), 1);
    return (
        <div className="space-y-1 md:space-y-2">
            {data.map((item, i) => (
                <div key={i} className="space-y-0.5 md:space-y-1">
                    <div className="flex justify-between text-[8px] md:text-[10px] font-black uppercase text-slate-500 tracking-tight">
                        <span className="truncate max-w-[150px] md:max-w-[200px]">{item[0]}</span>
                        <span className="text-slate-900">{item[1]} ajustes</span>
                    </div>
                    <div className="h-1 md:h-2 bg-slate-100 rounded-full overflow-hidden shadow-inner">
                        <div
                            className="h-full bg-violet-500 rounded-full transition-all duration-1000 shadow-[0_0_8px_rgba(139,92,246,0.3)]"
                            style={{ width: `${(item[1] / max) * 100}%` }}
                        />
                    </div>
                </div>
            ))}
            {data.length === 0 && (
                <div className="py-4 text-center text-slate-300 text-[10px] md:text-xs font-black uppercase tracking-widest italic opacity-50">Nenhum ajuste pendente</div>
            )}
        </div>
    );
};

// --- COMPONENTE PRINCIPAL ---

const DashboardView: React.FC<DashboardViewProps> = ({
    tarefas = [],
    financeTransactions = [],
    financeSettings = {} as FinanceSettings,
    fixedBills = [],
    incomeEntries = [],
    healthWeights = [],
    healthDailyHabits = [],
    healthSettings = {} as HealthSettings,
    unidades = [],
    sistemasDetalhes = [],
    workItems = [],
    currentMonth = new Date().getMonth(),
    currentYear = new Date().getFullYear(),
    onNavigate,
    onOpenBacklog
}) => {
    const { todayStr, tomorrowStr } = useMemo(() => {
        const now = new Date();
        const formatDate = (d: Date) => {
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return `${y}-${m}-${day}`;
        };
        const tom = new Date(now);
        tom.setDate(tom.getDate() + 1);
        return {
            todayStr: formatDate(now),
            tomorrowStr: formatDate(tom)
        };
    }, []);

    // --- ACTIONS LOGIC ---
    const inProgressActions = useMemo(() => tarefas.filter(t => t.status !== 'concluído' && t.status !== 'excluído' as any), [tarefas]);

    const nextTwoDaysActions = useMemo(() => inProgressActions.filter(t =>
        t.data_limite && t.data_limite !== '-' && t.data_limite >= todayStr && t.data_limite <= tomorrowStr
    ), [inProgressActions, todayStr, tomorrowStr]);

    const actionsByArea = useMemo(() => {
        const counts: Record<string, number> = {};
        inProgressActions.forEach(t => {
            const area = t.categoria || 'GERAL';
            counts[area] = (counts[area] || 0) + 1;
        });
        return Object.entries(counts).sort((a, b) => b[1] - a[1]);
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

    const dailySpending = useMemo(() => {
        const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
        const days = Array(daysInMonth).fill(0);
        currentMonthTransactions.forEach(t => {
            const day = new Date(t.date).getDate();
            if (day <= daysInMonth) days[day - 1] += t.amount;
        });
        return days;
    }, [currentMonthTransactions, currentMonth, currentYear]);

    const currentMonthIncome = useMemo(() => incomeEntries
        .filter(e => e.month === currentMonth && e.year === currentYear && e.isReceived && e.status !== 'deleted')
        .reduce((acc, curr) => acc + curr.amount, 0), [incomeEntries, currentMonth, currentYear]);

    const currentTotalBills = useMemo(() => fixedBills
        .filter(b => b.month === currentMonth && b.year === currentYear)
        .reduce((acc, curr) => acc + curr.amount, 0), [fixedBills, currentMonth, currentYear]);

    const prevMonth = currentMonth === 0 ? 11 : currentMonth - 1;
    const prevYear = currentMonth === 0 ? currentYear - 1 : currentYear;

    const prevMonthIncome = useMemo(() => incomeEntries
        .filter(e => e.month === prevMonth && e.year === prevYear && e.isReceived && e.status !== 'deleted')
        .reduce((acc, curr) => acc + curr.amount, 0), [incomeEntries, prevMonth, prevYear]);

    const prevTotalBills = useMemo(() => fixedBills
        .filter(b => b.month === prevMonth && b.year === prevYear)
        .reduce((acc, curr) => acc + curr.amount, 0), [fixedBills, prevMonth, prevYear]);

    const incomeVariation = prevMonthIncome > 0 ? ((currentMonthIncome - prevMonthIncome) / prevMonthIncome) * 100 : 0;
    const billsVariation = prevTotalBills > 0 ? ((currentTotalBills - prevTotalBills) / prevTotalBills) * 100 : 0;

    // --- HEALTH LOGIC ---
    const sortedWeights = useMemo(() => [...healthWeights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()), [healthWeights]);

    const currentWeight = sortedWeights[0]?.weight || 0;
    const initialWeight = sortedWeights[sortedWeights.length - 1]?.weight || 0;
    const totalWeightLost = initialWeight > 0 ? initialWeight - currentWeight : 0;

    const healthProjection = useMemo(() => {
        if (healthWeights.length < 2) return null;
        const oldest = healthWeights[healthWeights.length - 1];
        const newest = healthWeights[0];
        const diffWeight = oldest.weight - newest.weight;
        const diffDays = (new Date(newest.date).getTime() - new Date(oldest.date).getTime()) / (1000 * 60 * 60 * 24);
        
        if (diffDays <= 0 || diffWeight <= 0) return null;
        
        const lostPerDay = diffWeight / diffDays;
        const target = healthSettings?.targetWeight || 0;
        
        if (!target || newest.weight <= target) return 'Meta atingida!';
        
        const remainingToGoal = newest.weight - target;
        const daysUntilGoal = remainingToGoal / lostPerDay;
        const goalDate = new Date();
        goalDate.setDate(goalDate.getDate() + daysUntilGoal);
        return goalDate.toLocaleDateString('pt-BR');
    }, [healthWeights, healthSettings]);

    const habitStreak = useMemo(() => {
        let streak = 0;
        const sortedHabits = [...healthDailyHabits].sort((a, b) => b.id.localeCompare(a.id));
        let checkDate = new Date();

        for (const habit of sortedHabits) {
            const hDate = habit.id;
            const expectedDate = checkDate.toISOString().split('T')[0];

            if (hDate === expectedDate) {
                const completedCount = [habit.noSugar, habit.noAlcohol, habit.noSnacks, habit.workout, habit.eatUntil18, habit.eatSlowly].filter(Boolean).length;
                if (completedCount >= 4) { 
                    streak++;
                    checkDate.setDate(checkDate.getDate() - 1);
                } else break;
            } else if (hDate < expectedDate) break;
        }
        return streak;
    }, [healthDailyHabits]);

    // --- SYSTEMS LOGIC ---
    const systemsByPhase = useMemo(() => {
        const phases: Record<string, number> = { ideia: 0, prototipacao: 0, desenvolvimento: 0, testes: 0, producao: 0 };
        sistemasDetalhes.forEach(sys => {
            if (phases[sys.status] !== undefined) phases[sys.status]++;
        });
        return Object.entries(phases);
    }, [sistemasDetalhes]);

    const systemsByAdjustments = useMemo(() => {
        const counts: Record<string, number> = {};
        workItems.filter(w => !w.concluido).forEach(w => {
            const unit = unidades.find(u => u.id === w.sistema_id);
            const name = unit ? unit.nome.replace('SISTEMA:', '').trim() : 'Sistema Desconhecido';
            counts[name] = (counts[name] || 0) + 1;
        });
        return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5);
    }, [workItems, unidades]);

    return (
        <div className="animate-in fade-in duration-700 flex flex-col h-full lg:h-[calc(100vh-5rem)] p-1 md:p-2 lg:p-1 w-full max-w-[1600px] mx-auto overflow-hidden">
            <div className="grid grid-cols-1 lg:grid-cols-2 lg:grid-rows-2 gap-2 md:gap-3 lg:gap-2 flex-1 min-h-0">

                {/* CARD: AÇÕES */}
                <DashboardCard title="Ações" iconColor="bg-blue-500" onRedirect={() => onNavigate('gallery')}>
                    <div className="space-y-3 md:space-y-4">
                        <div className="grid grid-cols-2 gap-2 md:gap-3">
                            <div className="bg-blue-50/50 p-2 md:p-3 rounded-xl md:rounded-2xl border border-blue-100/50 flex flex-col justify-center transition-transform hover:scale-[1.01]">
                                <p className="text-[8px] md:text-[10px] font-black text-blue-600 uppercase tracking-widest mb-1">Em Andamento</p>
                                <div className="text-lg md:text-xl font-black text-slate-900">{inProgressActions.length}</div>
                            </div>
                            <div className="bg-indigo-50/50 p-2 md:p-3 rounded-xl md:rounded-2xl border border-indigo-100/50 flex flex-col justify-center transition-transform hover:scale-[1.01]">
                                <p className="text-[8px] md:text-[10px] font-black text-indigo-600 uppercase tracking-widest mb-1">Hoje/Amanhã</p>
                                <div className="text-lg md:text-xl font-black text-slate-900">{nextTwoDaysActions.length}</div>
                            </div>
                        </div>
                        <div className="flex-1">
                            <p className="text-[8px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 md:mb-3">Distribuição por Área</p>
                            <PieChart data={actionsByArea} />
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: FINANCEIRO */}
                <DashboardCard title="Financeiro" iconColor="bg-emerald-500" onRedirect={() => onNavigate('finance')}>
                    <div className="space-y-2 md:space-y-4">
                        <div>
                            <p className="text-[8px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest mb-0.5 md:mb-1">Saldo Disponível</p>
                            <div className={`text-lg md:text-2xl font-black tracking-tight ${availableBalance < 0 ? 'text-rose-600' : 'text-slate-900'}`}>
                                R$ {availableBalance.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                            </div>
                        </div>
                        <div className="flex-1">
                            <p className="text-[8px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Gastos Diários</p>
                            <BarChart data={dailySpending} color="#10b981" />
                        </div>
                        <div className="grid grid-cols-2 gap-2 md:gap-4 pt-2 md:pt-3 border-t border-slate-100">
                            <div className="group">
                                <p className="text-[7px] md:text-[9px] font-black text-slate-400 uppercase tracking-widest mb-0.5">Recebido</p>
                                <div className="text-[10px] md:text-sm font-black text-slate-900 group-hover:text-emerald-600 transition-colors">R$ {currentMonthIncome.toLocaleString('pt-BR')}</div>
                                <div className={`text-[7px] md:text-[9px] font-bold inline-flex items-center gap-1 ${incomeVariation >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                    {incomeVariation >= 0 ? '↑' : '↓'} {Math.abs(incomeVariation).toFixed(0)}%
                                </div>
                            </div>
                            <div className="group">
                                <p className="text-[7px] md:text-[9px] font-black text-slate-400 uppercase tracking-widest mb-0.5">Em Contas</p>
                                <div className="text-[10px] md:text-sm font-black text-slate-900 group-hover:text-rose-600 transition-colors">R$ {currentTotalBills.toLocaleString('pt-BR')}</div>
                                <div className={`text-[7px] md:text-[9px] font-bold inline-flex items-center gap-1 ${billsVariation <= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                    {billsVariation <= 0 ? '↓' : '↑'} {Math.abs(billsVariation).toFixed(0)}%
                                </div>
                            </div>
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: SAÚDE */}
                <DashboardCard title="Saúde" iconColor="bg-rose-500" onRedirect={() => onNavigate('saude')}>
                    <div className="space-y-3 md:space-y-4">
                        <div className="flex justify-between items-end">
                            <div>
                                <p className="text-[8px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest mb-0.5 md:mb-1">Peso vs Meta</p>
                                <div className="text-lg md:text-2xl font-black text-slate-900">
                                    {currentWeight.toFixed(1)} <span className="text-slate-300 text-xs md:text-base">/ {healthSettings?.targetWeight || '--'} kg</span>
                                </div>
                            </div>
                            <div className="text-right">
                                <p className="text-[8px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest mb-0.5 md:mb-1">Eliminado</p>
                                <div className="text-lg md:text-xl font-black text-emerald-500">-{totalWeightLost.toFixed(1)} kg</div>
                            </div>
                        </div>
                        <div className="bg-slate-900 p-3 md:p-4 rounded-xl md:rounded-2xl text-white shadow-lg relative overflow-hidden group">
                            <div className="absolute top-0 right-0 w-20 h-20 bg-blue-500/10 rounded-full blur-2xl -mr-10 -mt-10 group-hover:bg-blue-500/20 transition-all"></div>
                            <p className="text-[7px] md:text-[9px] font-black text-slate-400 uppercase tracking-widest mb-0.5 relative z-10">Previsão (ETA)</p>
                            <div className="text-lg md:text-xl font-black text-blue-400 relative z-10">{healthProjection || '--'}</div>
                        </div>
                        <div>
                            <div className="flex justify-between items-center mb-2">
                                <p className="text-[8px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest">Ofensiva de Hábitos</p>
                                <span className="bg-amber-100 text-amber-700 text-[9px] md:text-[10px] font-black px-2 py-0.5 rounded-full shadow-sm">{habitStreak} dias</span>
                            </div>
                            <div className="flex gap-1 md:gap-1.5">
                                {Array.from({ length: 7 }).map((_, i) => {
                                    const d = new Date();
                                    d.setDate(d.getDate() - (6 - i));
                                    const dStr = d.toISOString().split('T')[0];
                                    const habit = healthDailyHabits.find(h => h.id === dStr);
                                    const count = habit ? [habit.noSugar, habit.noAlcohol, habit.noSnacks, habit.workout, habit.eatUntil18, habit.eatSlowly].filter(Boolean).length : 0;
                                    return (
                                        <div
                                            key={i}
                                            className="flex-1 h-5 md:h-10 rounded-md md:rounded-lg shadow-inner transition-all hover:scale-105"
                                            style={{ backgroundColor: count === 0 ? '#f1f5f9' : `hsl(${(count / 6) * 120}, 70%, 50%)` }}
                                            title={`${dStr}: ${count}/6 hábitos`}
                                        />
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: SISTEMAS */}
                <DashboardCard title="Sistemas" iconColor="bg-violet-500" onRedirect={() => onNavigate('sistemas-dev')}>
                    <div className="space-y-3 md:space-y-4 flex flex-col h-full">
                        <div className="flex flex-wrap gap-2">
                            {systemsByPhase.map(([phase, count]) => (
                                <div key={phase} className="px-2 py-1 md:px-3 md:py-1.5 bg-slate-50 border border-slate-100 rounded-xl flex items-center gap-1.5 md:gap-2 transition-colors hover:bg-slate-100">
                                    <span className="text-[7px] md:text-[9px] font-black text-slate-400 uppercase tracking-tight">{phase === 'prototipacao' ? 'Protótipo' : phase === 'producao' ? 'Prod' : phase}</span>
                                    <span className="text-[9px] md:text-xs font-black text-slate-900">{count}</span>
                                </div>
                            ))}
                        </div>
                        <div className="flex-1">
                            <p className="text-[8px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 md:mb-3">Pendências por Sistema</p>
                            <SystemsBarChart data={systemsByAdjustments} />
                        </div>
                    </div>
                </DashboardCard>

            </div>
        </div>
    );
};

export default DashboardView;