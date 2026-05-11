import React, { useMemo, useState } from 'react';
import {
    Tarefa, FinanceTransaction, FinanceSettings, FixedBill, IncomeEntry,
    HealthWeight, DailyHabits, HealthSettings, WorkItem, Sistema, ExerciseLog
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

const SystemsHeatmap = ({ data, isDark = false }: { data: {id: string, name: string, count: number, lastSync?: string}[], isDark?: boolean }) => {
    const max = Math.max(...data.map(d => d.count), 1);
    
    const getInitials = (name: string) => {
        if (!name) return '?';
        const cleanName = name.replace(/^SISTEMA:?\s*/i, '').replace(/[–—\-]/g, ' ');
        const words = cleanName.split(/\s+/).filter(w => w.length > 0 && !['DE', 'DO', 'DA', 'DOS', 'DAS', 'COM', 'EM', 'PARA'].includes(w.toUpperCase()));
        
        const acronym = words.find(w => w.length >= 2 && w === w.toUpperCase() && !/^\d+$/.test(w));
        if (acronym) return acronym.slice(0, 3);

        if (words.length === 0) return '?';
        if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
        return words.map(w => w[0]).join('').toUpperCase().slice(0, 3);
    };

    return (
        <div className="flex flex-wrap gap-2 md:gap-3">
            {data.map((item, i) => {
                const intensity = item.count === 0 ? 0 : Math.min(Math.max(Math.ceil((item.count / max) * 5), 1), 5);
                const bgClasses = [
                    isDark ? 'bg-violet-950/40 text-violet-300/40' : 'bg-violet-200/40 text-violet-900/30', // 0
                    isDark ? 'bg-violet-800 text-violet-100' : 'bg-violet-300 text-violet-900', // 1
                    isDark ? 'bg-violet-700 text-white' : 'bg-violet-500 text-white', // 2
                    isDark ? 'bg-violet-600 text-white' : 'bg-violet-700 text-white', // 3
                    isDark ? 'bg-violet-500 text-white' : 'bg-violet-800 text-white', // 4
                    isDark ? 'bg-violet-400 text-white' : 'bg-violet-950 text-white', // 5
                ];

                return (
                    <div 
                        key={item.id}
                        title={`${item.name || 'Sistema'}${item.lastSync ? ` (Sinc: ${new Date(item.lastSync).toLocaleDateString('pt-BR')})` : ''}: ${item.count} ações`}
                        className={`w-14 h-14 md:w-20 md:h-20 flex flex-col items-center justify-center transition-all hover:scale-105 cursor-help shadow-lg ${bgClasses[intensity]}`}
                    >
                        <span className="text-xs md:text-lg font-black font-mono leading-none">
                            {getInitials(item.name)}
                        </span>
                        <span className={`text-[8px] md:text-[10px] font-black font-lcd mt-1 ${intensity > 2 ? 'opacity-70' : 'opacity-40'}`}>
                            {item.count}
                        </span>
                    </div>
                );
            })}
        </div>
    );
};

const HiddenMoney = ({ className = "", compact = false }: { className?: string, compact?: boolean }) => (
    <span className={`inline-block font-black tracking-normal select-none font-lcd ${className}`} aria-label="valor oculto">
        <span className="font-mono">R$</span> {compact ? '••••' : '••••••'}
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
    exerciseLogs = [] as ExerciseLog[],
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
                monthName: ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'][d.getMonth()],
                count,
                isToday: i === 0
            });
        }
        return result;
    }, [inProgressActions, todayStr]);

    const distantFutureCount = useMemo(() => {
        if (actionsByDay.length === 0) return 0;
        const lastDate = actionsByDay[actionsByDay.length - 1].dateStr;
        return inProgressActions.filter(t => t.data_limite && t.data_limite > lastDate).length;
    }, [inProgressActions, actionsByDay]);

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

    const financeChartData = useMemo(() => {
        const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
        const monthName = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'][currentMonth];
        const result = [];
        
        for (let d = 1; d <= daysInMonth; d++) {
            const amount = currentMonthTransactions
                .filter(t => {
                    const transDate = new Date(t.date);
                    // Use UTC or local comparison carefully. Here we assume t.date is ISO or local.
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

    // --- SYSTEMS LOGIC ---
    const systemsByPhase = useMemo(() => {
        const phases: Record<string, number> = { ideia: 0, prototipacao: 0, desenvolvimento: 0, testes: 0, producao: 0 };
        sistemasDetalhes.forEach(sys => { if (phases[sys.status] !== undefined) phases[sys.status]++; });
        return Object.entries(phases);
    }, [sistemasDetalhes]);

    const systemsByAdjustments = useMemo(() => {
        return sistemasDetalhes.map(sys => {
            const activeWorkItems = workItems.filter(w => w.sistema_id === sys.id && !w.concluido);
            return {
                id: sys.id,
                name: sys.nome || 'Sistema',
                count: activeWorkItems.length,
                lastSync: sys.github_rag_synced_at
            };
        }).sort((a, b) => b.count - a.count);
    }, [sistemasDetalhes, workItems]);

    return (
        <div className="animate-in fade-in duration-700 flex flex-col h-full lg:h-[calc(100vh-5rem)] p-1 md:p-2 lg:p-1 w-full max-w-[1600px] mx-auto overflow-hidden">
            <div className="grid grid-cols-1 lg:grid-cols-2 lg:grid-rows-2 gap-2 md:gap-3 lg:gap-2 flex-1 min-h-0">

                {/* CARD: AÇÕES */}
                <DashboardCard title="Ações" iconColor="bg-primary-tactile" onRedirect={() => onNavigate('gallery')} isDark={isDark}>
                    <div className={`h-full flex flex-col gap-4 p-4 rounded-none border-4 ${isDark ? 'bg-[#FFB95F] border-black/20 shadow-[inset_0_4px_10px_rgba(0,0,0,0.2)]' : 'bg-[#FFB95F] border-black/10 shadow-[inset_0_4px_12px_rgba(0,0,0,0.15)]'}`}>
                        <div className="flex items-center justify-between shrink-0">
                            <p className="text-[10px] font-black uppercase tracking-[0.2em] font-mono text-amber-950/60">Carga Semanal (Hoje + 6D)</p>
                            <div className="flex items-center gap-2 md:gap-3">
                                <div className="flex items-center gap-1.5">
                                    <span className="text-[10px] font-black uppercase font-mono text-amber-950">{inProgressActions.length} Total</span>
                                </div>
                                {distantFutureCount > 0 && (
                                    <div className="px-2 py-0.5 bg-black/5 border border-black/10 flex items-center gap-1.5">
                                        <span className="w-1.5 h-1.5 bg-amber-950/40"></span>
                                        <span className="text-[10px] font-black uppercase font-mono text-amber-950/60">{distantFutureCount} Futuras</span>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="flex-1 flex items-end gap-1 md:gap-2 min-h-0 px-2 pb-2 relative">
                            {actionsByDay.map((day, i) => {
                                const maxCount = Math.max(...actionsByDay.map(d => d.count), 5);
                                const heightPercent = (day.count / maxCount) * 100;
                                
                                return (
                                    <div key={i} className="flex-1 flex flex-col items-center justify-end h-full">
                                        <span className={`text-[13px] md:text-base font-black font-lcd mb-1 ${day.count > 0 ? 'text-amber-950' : 'text-amber-950/10'}`}>
                                            {day.count}
                                        </span>
                                        <div 
                                            style={{ height: `${Math.max(heightPercent, day.count > 0 ? 8 : 0)}%` }}
                                            className={`w-full transition-all duration-500 rounded-none ${day.isToday 
                                                ? 'bg-amber-950 shadow-lg' 
                                                : day.count > 0 
                                                    ? 'bg-amber-950/30 hover:bg-amber-950/50'
                                                    : 'bg-black/5'}`}
                                        ></div>
                                        <div className={`mt-3 flex flex-col items-center gap-0.5 ${day.isToday ? 'opacity-100' : 'opacity-50'}`}>
                                            <span className="text-[10px] md:text-[11px] font-black font-mono leading-none whitespace-nowrap text-amber-950">
                                                {String(day.dayNum).padStart(2, '0')}/{day.monthName}
                                            </span>
                                        </div>
                                    </div>
                                );
                            })}
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
                            className={`p-2 rounded-none transition-all shadow-sm ${isDark ? 'text-slate-500 hover:bg-slate-800' : 'text-slate-400 hover:bg-emerald-50'}`}
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                {isFinanceVisible ? <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /> : <path d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />}
                            </svg>
                        </button>
                    }
                >
                    <div className={`h-full flex flex-col gap-4 p-4 rounded-none border-4 ${isDark ? 'bg-[#4ADE80] border-black/20 shadow-[inset_0_4px_10px_rgba(0,0,0,0.2)]' : 'bg-[#4ADE80] border-black/10 shadow-[inset_0_4px_12px_rgba(0,0,0,0.15)]'}`}>
                        <div className="flex items-center justify-between shrink-0">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-[0.2em] font-mono text-emerald-950/60">Consumo Mensal (Dias Ativos)</p>
                                <div className="text-xl md:text-2xl font-black font-lcd text-emerald-950 mt-1">
                                    {isFinanceVisible ? <><span className="font-mono">R$</span> {currentMonthTotalSpent.toLocaleString('pt-BR', { minimumFractionDigits: 0 })}</> : <HiddenMoney compact />}
                                </div>
                            </div>
                            <div className="text-right">
                                <p className="text-[8px] font-black uppercase tracking-[0.2em] font-mono text-emerald-950/60">Disponível</p>
                                <div className={`text-sm md:text-base font-black font-lcd ${availableBalance < 0 ? 'text-red-900' : 'text-emerald-950/80'}`}>
                                    {isFinanceVisible ? <><span className="font-mono">R$</span> {availableBalance.toLocaleString('pt-BR', { minimumFractionDigits: 0 })}</> : '••••'}
                                </div>
                            </div>
                        </div>

                        <div className="flex-1 flex items-end gap-1 md:gap-1.5 min-h-0 px-2 pb-2 relative overflow-x-auto scrollbar-hide">
                            {isFinanceVisible ? (
                                financeChartData.length > 0 ? (
                                    financeChartData.map((item, i) => {
                                        const maxAmount = Math.max(...financeChartData.map(d => d.amount), 1);
                                        const heightPercent = (item.amount / maxAmount) * 100;
                                        
                                        return (
                                            <div key={i} className="flex-1 min-w-[20px] flex flex-col items-center justify-end h-full group">
                                                <div 
                                                    style={{ height: `${Math.max(heightPercent, 5)}%` }}
                                                    className="w-full bg-emerald-950/40 group-hover:bg-emerald-950 transition-all duration-300 rounded-none border-t border-emerald-950/20"
                                                    title={`Dia ${item.day}: R$ ${item.amount.toFixed(2)}`}
                                                ></div>
                                                <div className="mt-2 flex flex-col items-center">
                                                    <span className="text-[9px] font-black font-lcd text-emerald-950">
                                                        {String(item.day).padStart(2, '0')}
                                                    </span>
                                                </div>
                                            </div>
                                        );
                                    })
                                ) : (
                                    <div className="flex-1 h-full flex items-center justify-center border-2 border-dashed border-emerald-950/10">
                                        <span className="text-[10px] font-black uppercase font-mono text-emerald-950/30 italic">Sem registros</span>
                                    </div>
                                )
                            ) : (
                                <div className="flex-1 h-full flex items-center justify-center border-2 border-dashed border-emerald-950/10">
                                    <span className="text-[10px] font-black uppercase font-mono text-emerald-950/30 italic">Dados Ocultos</span>
                                </div>
                            )}
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: SAÚDE */}
                <DashboardCard title="Saúde" iconColor="bg-red-500" onRedirect={() => onNavigate('saude')} isDark={isDark}>
                    <div className={`h-full flex flex-col gap-3 p-4 rounded-none border-4 bg-[#FF6B6B] ${isDark ? 'border-black/20 shadow-[inset_0_4px_10px_rgba(0,0,0,0.2)]' : 'border-black/10 shadow-[inset_0_4px_12px_rgba(0,0,0,0.15)]'}`}>
                        <div className="flex items-center justify-between shrink-0">
                            <p className="text-[10px] font-black uppercase tracking-[0.2em] font-mono text-red-950/60">Telemetria Hoje</p>
                            <span className="text-[10px] font-black uppercase font-mono text-red-950">{habitStreak} DIAS</span>
                        </div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-3 flex-1">
                            <div className="flex flex-col justify-center">
                                <p className="text-[8px] font-black uppercase tracking-[0.2em] font-mono text-red-950/60 mb-0.5">Peso Atual</p>
                                <div className="text-xl md:text-2xl font-black font-lcd text-red-950 leading-none">{currentWeight > 0 ? currentWeight.toFixed(1) : '—'}<span className="text-xs text-red-950/50 ml-1">kg</span></div>
                                <div className="text-[10px] font-black font-lcd text-red-950/70 mt-0.5">{currentWeight > 0 ? `${weightDeltaPrefix}${weightDeltaAbs.toFixed(1)} kg` : '—'}</div>
                            </div>
                            <div className="flex flex-col justify-center">
                                <p className="text-[8px] font-black uppercase tracking-[0.2em] font-mono text-red-950/60 mb-0.5">Passos</p>
                                <div className="text-xl md:text-2xl font-black font-lcd text-red-950 leading-none">{todayTelemetry?.walk?.steps ? todayTelemetry.walk.steps.toLocaleString('pt-BR') : '—'}</div>
                                <div className="text-[10px] font-black font-lcd text-red-950/70 mt-0.5">{todayTelemetry?.walk?.distance ? `${todayTelemetry.walk.distance.toFixed(1)} km` : '—'}</div>
                            </div>
                            <div className="flex flex-col justify-center">
                                <p className="text-[8px] font-black uppercase tracking-[0.2em] font-mono text-red-950/60 mb-0.5">Gasto Calórico</p>
                                <div className="text-xl md:text-2xl font-black font-lcd text-red-950 leading-none">{todayTelemetry?.calories ? Math.round(todayTelemetry.calories).toLocaleString('pt-BR') : '—'}<span className="text-xs text-red-950/50 ml-1">kcal</span></div>
                                <div className="text-[10px] font-black font-lcd text-red-950/70 mt-0.5">{todayTelemetry?.activeMinutes ? `${todayTelemetry.activeMinutes} min ativos` : '—'}</div>
                            </div>
                            <div className="flex flex-col justify-center">
                                <p className="text-[8px] font-black uppercase tracking-[0.2em] font-mono text-red-950/60 mb-0.5">Sono</p>
                                <div className="text-xl md:text-2xl font-black font-lcd text-red-950 leading-none">{todayTelemetry?.sleep?.totalMinutes ? `${Math.floor(todayTelemetry.sleep.totalMinutes / 60)}h ${todayTelemetry.sleep.totalMinutes % 60}m` : '—'}</div>
                                <div className="text-[10px] font-black font-lcd text-red-950/70 mt-0.5">{todayTelemetry?.sleep?.deepMinutes ? `${todayTelemetry.sleep.deepMinutes}m prof.` : '—'}</div>
                            </div>
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: SISTEMAS */}
                <DashboardCard title="Sistemas" iconColor="bg-violet-500" onRedirect={() => onNavigate('sistemas-dev')} isDark={isDark}>
                    <div className={`h-full flex flex-col gap-4 p-4 rounded-none border-4 bg-[#A78BFA] ${isDark ? 'border-black/20 shadow-[inset_0_4px_10px_rgba(0,0,0,0.2)]' : 'border-black/10 shadow-[inset_0_4px_12px_rgba(0,0,0,0.15)]'}`}>
                        <div className="flex-1 overflow-y-auto pr-1">
                            <p className={`text-[8px] md:text-[10px] font-black uppercase tracking-widest mb-4 font-mono ${isDark ? 'text-violet-200/60' : 'text-violet-950/60'}`}>Mapa de Calor Operacional</p>
                            <SystemsHeatmap data={systemsByAdjustments} isDark={isDark} />
                        </div>
                    </div>
                </DashboardCard>

            </div>
        </div>
    );
};

export default DashboardView;
