import React, { useMemo, useState } from 'react';
import {
    Tarefa, FinanceTransaction, FinanceSettings, FixedBill, IncomeEntry,
    HealthWeight, DailyHabits, HealthSettings, WorkItem, Sistema
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
    unidades: { id: string, nome: string }[];
    sistemasDetalhes: Sistema[];
    workItems: WorkItem[];
    currentMonth: number;
    currentYear: number;
    onNavigate: (view: 'gallery' | 'finance' | 'saude' | 'sistemas-dev') => void;
    onOpenBacklog: () => void;
}

// --- SUBCOMPONENTES MOVIDOS PARA FORA ---

const DashboardCard = ({ title, iconColor, onRedirect, children, isDark = false, headerAction }: { title: string, iconColor: string, onRedirect: () => void, children: React.ReactNode, isDark?: boolean, headerAction?: React.ReactNode }) => (
    <div
        onClick={onRedirect}
        className={`group p-3 md:p-4 rounded-none border h-full transition-all flex flex-col cursor-pointer min-h-0 ${isDark ? 'bg-[#1b1c1c] border-white/10' : 'bg-white border-border-grid shadow-soft-touch hover:shadow-xl'}`}
        role="button"
        tabIndex={0}
    >
        <div className="flex items-center justify-between mb-4 shrink-0">
            <div className="flex items-center gap-2">
                <span className={`w-1.5 h-5 md:h-7 ${iconColor} rounded-none`}></span>
                <h3 className={`text-xs md:text-base font-black uppercase tracking-widest font-mono ${isDark ? 'text-[#f0f1f0]' : 'text-on-surface'}`}>{title}</h3>
            </div>
            <div className="flex items-center gap-1">
                {headerAction}
                <div className={`p-2 rounded-soft-touch transition-all shadow-soft-touch ${isDark ? 'text-slate-500 group-hover:bg-slate-800 group-hover:text-slate-100' : 'text-slate-400 group-hover:bg-slate-50 group-hover:text-slate-900'}`}>
                    <svg className="w-5 h-5 transition-transform group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                </div>
            </div>
        </div>
        <div className="flex-1 flex flex-col justify-center min-h-0 overflow-hidden">
            {children}
        </div>
    </div>
);

const PieChart = ({ data, isDark = false }: { data: [string, number][], isDark?: boolean }) => {
    const total = data.reduce((acc, curr) => acc + curr[1], 0);
    if (total === 0) return <div className={`h-24 md:h-40 flex items-center justify-center text-[10px] font-black uppercase font-mono ${isDark ? 'text-slate-600' : 'text-slate-300'}`}>Sem dados</div>;

    const colors = isDark
        ? ['#64b5f6', '#34d399', '#ffb74d', '#fb7185', '#a78bfa', '#f472b6']
        : ['#23619a', '#835500', '#0060ac', '#ef4444', '#8b5cf6', '#ec4899'];

    return (
        <div className="space-y-2 md:space-y-2.5">
            <div className={`h-2 rounded-none overflow-hidden flex ${isDark ? 'bg-slate-800' : 'bg-slate-100 border border-border-grid'}`}>
                {data.slice(0, 5).map((item, i) => (
                    <div
                        key={i}
                        className="h-full transition-all"
                        style={{ width: `${(item[1] / total) * 100}%`, backgroundColor: colors[i % colors.length] }}
                        title={`${item[0]}: ${item[1]}`}
                    />
                ))}
            </div>
            <div className="space-y-1.5 flex-1 min-w-0">
                {data.slice(0, 5).map((item, i) => (
                    <div key={i} className="flex items-center justify-between gap-3 group">
                        <div className="flex items-center gap-2 truncate flex-1">
                            <div className="w-2 h-2 md:w-2.5 md:h-2.5 rounded-none shrink-0" style={{ backgroundColor: colors[i % colors.length] }}></div>
                            <span className={`text-[9px] md:text-[11px] font-black uppercase truncate transition-colors font-mono ${isDark ? 'text-slate-300 group-hover:text-slate-100' : 'text-slate-600 group-hover:text-on-surface'}`}>{item[0]}</span>
                        </div>
                        <span className={`text-[10px] md:text-xs font-black font-lcd ${isDark ? 'text-white' : 'text-on-surface'}`}>{item[1]}</span>
                    </div>
                ))}
            </div>
        </div>
    );
};

const BarChart = ({ data, color, isDark = false, maxHeight = 65 }: { data: number[], color: string, isDark?: boolean, maxHeight?: number }) => {
    const max = Math.max(...data, 1);
    const chartHeightClass = "h-[40px] md:h-[65px]";
    return (
        <div className={`flex items-end gap-0.5 md:gap-1 ${chartHeightClass} w-full rounded-none px-1 md:px-2 pb-1 md:pb-2 border border-border-grid ${isDark ? 'bg-[#1b1c1c]/80' : 'bg-lcd-bg shadow-lcd-panel'}`}>
            {data.map((v, i) => (
                <div key={i} className="flex-1 flex flex-col justify-end items-center gap-0.5 group">
                    <div
                        className="w-full rounded-none transition-all group-hover:opacity-80 cursor-pointer"
                        style={{
                            height: `${(v / max) * (typeof window !== 'undefined' && window.innerWidth >= 768 ? 50 : 35)}px`,
                            backgroundColor: color,
                            minWidth: '2px'
                        }}
                        title={`Dia ${i + 1}: R$ ${v.toFixed(2)}`}
                    />
                    <span className={`text-[6px] md:text-[8px] font-black font-lcd opacity-60 group-hover:opacity-100 ${isDark ? 'text-slate-500' : 'text-slate-600'}`}>{i + 1}</span>
                </div>
            ))}
        </div>
    );
};

const SystemsBarChart = ({ data, isDark = false }: { data: [string, number][], isDark?: boolean }) => {
    const max = Math.max(...data.map(d => d[1]), 1);
    return (
        <div className="space-y-1 md:space-y-2">
            {data.map((item, i) => (
                <div key={i} className="space-y-0.5 md:space-y-1">
                    <div className={`flex justify-between text-[8px] md:text-[10px] font-black uppercase tracking-widest font-mono ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                        <span className="truncate max-w-[150px] md:max-w-[200px]">{item[0]}</span>
                        <span className={`${isDark ? 'text-white' : 'text-on-surface'}`}>{item[1]} ajustes</span>
                    </div>
                    <div className={`h-1.5 md:h-2.5 rounded-none overflow-hidden ${isDark ? 'bg-slate-800' : 'bg-lcd-bg border border-border-grid'}`}>
                        <div
                            className="h-full bg-accent-tactile transition-all duration-1000"
                            style={{ width: `${(item[1] / max) * 100}%` }}
                        />
                    </div>
                </div>
            ))}
        </div>
    );
};

const HiddenMoney = ({ className = "", compact = false }: { className?: string, compact?: boolean }) => (
    <span className={`inline-block font-black tracking-normal select-none font-lcd ${className}`} aria-label="valor oculto">
        R$ {compact ? '••••' : '••••••'}
    </span>
);

const HiddenPercent = ({ className = "" }: { className?: string }) => (
    <span className={`inline-flex items-center gap-1 font-black font-lcd select-none ${className}`} aria-label="percentual oculto">
        ••%
    </span>
);

const HiddenBarChart = ({ isDark = false }: { isDark?: boolean }) => (
    <div className={`relative flex items-end gap-0.5 md:gap-1 h-[40px] md:h-[65px] w-full rounded-none px-1 md:px-2 pb-1 md:pb-2 overflow-hidden border border-border-grid ${isDark ? 'bg-slate-900/80' : 'bg-lcd-bg shadow-lcd-panel'}`}>
        {Array.from({ length: 12 }).map((_, i) => (
            <div
                key={i}
                className={`flex-1 rounded-none ${isDark ? 'bg-slate-800' : 'bg-slate-300'}`}
                style={{ height: `${18 + ((i * 7) % 32)}px`, opacity: 0.55 }}
            />
        ))}
        <div className={`absolute inset-0 flex items-center justify-center text-[9px] md:text-[10px] font-black uppercase tracking-widest font-mono ${isDark ? 'text-slate-500 bg-slate-950/40' : 'text-slate-600 bg-white/35'}`}>
            Dados ocultos
        </div>
    </div>
);

// --- COMPONENTE PRINCIPAL ---

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
    unidades = [],
    sistemasDetalhes = [],
    workItems = [],
    currentMonth = new Date().getMonth(),
    currentYear = new Date().getFullYear(),
    onNavigate,
    onOpenBacklog
}) => {
    const [isFinanceVisible, setIsFinanceVisible] = useState(false);

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
            let area = t.area_tematica || 'GERAL';
            area = area.replace('SISTEMA:', '').trim();
            counts[area] = (counts[area] || 0) + 1;
        });
        return Object.entries(counts).sort((a, b) => b[1] - a[1]);
    }, [inProgressActions]);

    const overdueCount = useMemo(() => inProgressActions.filter(t =>
        t.data_limite && t.data_limite !== '-' && t.data_limite < todayStr
    ).length, [inProgressActions, todayStr]);

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
                dayName: ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB'][d.getDay()],
                monthName: ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'][d.getMonth()],
                count,
                isToday: i === 0
            });
        }
        return result;
    }, [inProgressActions, todayStr]);

    const nextMilestones = useMemo(() => {
        return inProgressActions
            .filter(t => t.data_limite && t.data_limite !== '-' && t.data_limite >= todayStr)
            .sort((a, b) => a.data_limite.localeCompare(b.data_limite))
            .slice(0, 3);
    }, [inProgressActions, todayStr]);

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

    // --- SYSTEMS LOGIC ---
    const systemsByPhase = useMemo(() => {
        const phases: Record<string, number> = { ideia: 0, prototipacao: 0, desenvolvimento: 0, testes: 0, producao: 0 };
        sistemasDetalhes.forEach(sys => { if (phases[sys.status] !== undefined) phases[sys.status]++; });
        return Object.entries(phases);
    }, [sistemasDetalhes]);

    const systemsByAdjustments = useMemo(() => {
        const counts: Record<string, number> = {};
        workItems.filter(w => !w.concluido).forEach(w => {
            const unit = unidades.find(u => u.id === w.sistema_id);
            const name = unit ? unit.nome.replace('SISTEMA:', '').trim() : 'Geral';
            counts[name] = (counts[name] || 0) + 1;
        });
        return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5);
    }, [workItems, unidades]);

    return (
        <div className="animate-in fade-in duration-700 flex flex-col h-full lg:h-[calc(100vh-5rem)] p-1 md:p-2 lg:p-1 w-full max-w-[1600px] mx-auto overflow-hidden">
            <div className="grid grid-cols-1 lg:grid-cols-2 lg:grid-rows-2 gap-2 md:gap-3 lg:gap-2 flex-1 min-h-0">

                {/* CARD: AÇÕES */}
                <DashboardCard title="Ações" iconColor="bg-primary-tactile" onRedirect={() => onNavigate('gallery')} isDark={isDark}>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-2 md:gap-3">
                            <div className={`p-3 rounded-lcd border-t border-black/20 border-b border-white/50 flex flex-col justify-center ${isDark ? 'bg-slate-900' : 'bg-lcd-bg shadow-lcd-panel'}`}>
                                <p className={`text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-1 font-mono text-slate-600`}>Em Andamento</p>
                                <div className="flex items-baseline gap-2">
                                    <div className="text-2xl md:text-3xl font-black font-lcd text-on-surface">{inProgressActions.length}</div>
                                    {overdueCount > 0 && (
                                        <div className="text-[10px] md:text-xs font-black font-lcd text-rose-600">+{overdueCount} ATR</div>
                                    )}
                                </div>
                            </div>
                            <div className={`p-3 rounded-lcd border-t border-black/20 border-b border-white/50 flex flex-col justify-center ${isDark ? 'bg-slate-900' : 'bg-lcd-bg shadow-lcd-panel'}`}>
                                <p className={`text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-1 font-mono text-slate-600`}>Hoje/Amanhã</p>
                                <div className="text-2xl md:text-3xl font-black font-lcd text-on-surface">{nextTwoDaysActions.length}</div>
                            </div>
                        </div>
                        <div className="flex-1 min-h-0">
                            <p className={`text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-2 font-mono ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Carga Semanal (Hoje + 6D)</p>
                            <div className="flex gap-1 h-14 md:h-16">
                                {overdueCount > 0 && (
                                    <div className={`flex-1 flex flex-col items-center justify-center border ${isDark ? 'bg-rose-950/20 border-rose-900/50 text-rose-500' : 'bg-rose-50 border-rose-200 text-rose-600'}`}>
                                        <span className="text-[7px] font-black font-mono">ATR</span>
                                        <div className="w-5 h-4 flex items-center justify-center font-lcd font-black text-sm md:text-lg">
                                            {overdueCount}
                                        </div>
                                    </div>
                                )}
                                {actionsByDay.map((day, i) => (
                                    <div 
                                        key={i} 
                                        className={`flex-1 flex flex-col items-center justify-center border transition-all ${day.isToday 
                                            ? (isDark ? 'bg-blue-900/30 border-blue-500 text-blue-400' : 'bg-blue-50 border-blue-600 text-blue-700 shadow-[inset_0_0_8px_rgba(37,99,235,0.1)]') 
                                            : (isDark ? 'bg-slate-900/50 border-white/5 text-slate-500' : 'bg-lcd-bg border-border-grid text-slate-400')}`}
                                    >
                                        <span className="text-[7px] font-black font-mono leading-none mb-1">{day.dayName}</span>
                                        <span className={`text-[9px] md:text-xs font-black font-lcd ${day.count > 0 ? (isDark ? 'text-white' : 'text-on-surface') : 'opacity-30'}`}>
                                            {String(day.dayNum).padStart(2, '0')}/{day.monthName}
                                        </span>
                                        <div className={`mt-1 w-5 h-4 flex items-center justify-center rounded-none border text-[9px] font-black font-lcd ${day.count > 0 
                                            ? (day.isToday 
                                                ? (isDark ? 'bg-blue-500 text-white border-blue-400' : 'bg-blue-700 text-white border-blue-800 shadow-sm') 
                                                : (isDark ? 'bg-slate-800 text-slate-300 border-white/10' : 'bg-slate-900 text-white border-slate-900')) 
                                            : 'border-transparent text-transparent'}`}>
                                            {day.count > 0 ? day.count : ''}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="pt-2 border-t border-border-grid/50">
                            <p className={`text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-2 font-mono ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Próximos Marcos</p>
                            <div className="space-y-1.5">
                                {nextMilestones.map(t => (
                                    <div key={t.id} className="flex items-center gap-2 group/ms">
                                        <div className={`w-1 h-3 shrink-0 ${isDark ? 'bg-slate-700' : 'bg-slate-200'}`}></div>
                                        <div className="flex-1 min-w-0">
                                            <p className={`text-[9px] font-bold truncate ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{t.titulo}</p>
                                        </div>
                                        <span className={`text-[8px] font-black uppercase font-mono px-1 border border-transparent ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                            {t.data_limite === todayStr ? 'HOJE' : t.data_limite === tomorrowStr ? 'AMANHÃ' : t.data_limite?.split('-').slice(1).reverse().join('/')}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: FINANCEIRO */}
                <DashboardCard
                    title="Financeiro"
                    iconColor="bg-emerald-500"
                    onRedirect={() => onNavigate('finance')}
                    isDark={isDark}
                    headerAction={
                        <button
                            onClick={(e) => { e.stopPropagation(); setIsFinanceVisible(!isFinanceVisible); }}
                            className={`p-2 rounded-soft-touch transition-all shadow-soft-touch ${isDark ? 'text-slate-500 hover:bg-slate-800' : 'text-slate-400 hover:bg-emerald-50'}`}
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                {isFinanceVisible ? <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /> : <path d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />}
                            </svg>
                        </button>
                    }
                >
                    <div className="space-y-4">
                        <div className={`p-4 rounded-lcd border-t border-black/20 border-b border-white/50 ${isDark ? 'bg-slate-900' : 'bg-lcd-bg shadow-lcd-panel'}`}>
                            <p className="text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-1 font-mono text-slate-600">Saldo Disponível</p>
                            <div className="text-2xl md:text-3xl font-black font-lcd text-on-surface">
                                {isFinanceVisible ? `R$ ${availableBalance.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : <HiddenMoney />}
                            </div>
                        </div>
                        <div className="flex-1">
                            <p className={`text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-2 font-mono ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Gastos Diários</p>
                            {isFinanceVisible ? <BarChart data={dailySpending} color={isDark ? "#34d399" : "#10b981"} isDark={isDark} /> : <HiddenBarChart isDark={isDark} />}
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: SAÚDE */}
                <DashboardCard title="Saúde" iconColor="bg-rose-500" onRedirect={() => onNavigate('saude')} isDark={isDark}>
                    <div className="space-y-4">
                        <div className="flex justify-between items-end">
                            <div className={`p-3 rounded-lcd flex-1 mr-2 border-t border-black/20 border-b border-white/50 ${isDark ? 'bg-slate-900' : 'bg-lcd-bg shadow-lcd-panel'}`}>
                                <p className="text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-1 font-mono text-slate-600">Peso Atual</p>
                                <div className="text-2xl font-black font-lcd text-on-surface">{currentWeight.toFixed(1)} <span className="text-xs opacity-50">kg</span></div>
                            </div>
                            <div className={`p-3 rounded-lcd flex-1 border-t border-black/20 border-b border-white/50 ${isDark ? 'bg-slate-900' : 'bg-lcd-bg shadow-lcd-panel'}`}>
                                <p className="text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-1 font-mono text-slate-600">Variação</p>
                                <div className={`text-2xl font-black font-lcd ${weightDelta > 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                    {weightDeltaPrefix}{weightDeltaAbs.toFixed(1)} <span className="text-xs opacity-50">kg</span>
                                </div>
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between items-center mb-2">
                                <p className={`text-[8px] md:text-[10px] font-black uppercase tracking-widest font-mono ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Ofensiva de Hábitos</p>
                                <span className="bg-operational-orange text-white text-[9px] font-black px-2 py-0.5 rounded-none shadow-soft-touch font-mono">{habitStreak} DIAS</span>
                            </div>
                            <div className="flex gap-1">
                                {Array.from({ length: 7 }).map((_, i) => (
                                    <div key={i} className={`flex-1 h-8 rounded-none border border-black/5 ${isDark ? 'bg-slate-800' : 'bg-slate-200'}`} />
                                ))}
                            </div>
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: SISTEMAS */}
                <DashboardCard title="Sistemas" iconColor="bg-violet-500" onRedirect={() => onNavigate('sistemas-dev')} isDark={isDark}>
                    <div className="space-y-4 flex flex-col h-full">
                        <div className="flex flex-wrap gap-2">
                            {systemsByPhase.map(([phase, count]) => (
                                <div key={phase} className={`px-3 py-1.5 rounded-soft-touch border shadow-soft-touch flex items-center gap-2 transition-all ${isDark ? 'bg-slate-900 border-white/10' : 'bg-white border-border-grid'}`}>
                                    <span className="text-[8px] font-black uppercase tracking-widest font-mono text-slate-400">{phase}</span>
                                    <span className="text-xs font-black font-lcd">{count}</span>
                                </div>
                            ))}
                        </div>
                        <div className="flex-1 overflow-y-auto pr-1">
                            <p className={`text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-2 font-mono ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Pendências por Sistema</p>
                            <SystemsBarChart data={systemsByAdjustments} isDark={isDark} />
                        </div>
                    </div>
                </DashboardCard>

            </div>
        </div>
    );
};

export default DashboardView;
