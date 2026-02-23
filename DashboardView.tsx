
import React, { useMemo } from 'react';
import { Tarefa, FinanceTransaction, FinanceSettings, FixedBill, IncomeEntry, HealthWeight, DailyHabits, HealthSettings, WorkItem, Sistema } from './types';

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

const DashboardCard = ({ title, iconColor, onRedirect, children }: { title: string, iconColor: string, onRedirect: () => void, children: React.ReactNode }) => {
    return (
        <div className="bg-white p-6 md:p-8 !rounded-none md:rounded-[2.5rem] border-b border-slate-100 md:border md:border-slate-200 shadow-none md:shadow-lg h-full transition-all flex flex-col">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <span className={`w-2 h-8 ${iconColor} rounded-full`}></span>
                    <h3 className="text-sm md:text-xl font-black text-slate-900 uppercase tracking-tight">{title}</h3>
                </div>
                <button
                    onClick={onRedirect}
                    className="p-2 hover:bg-slate-50 rounded-xl text-slate-400 hover:text-slate-900 transition-all group"
                    title="Ir para o módulo"
                >
                    <svg className="w-5 h-5 transition-transform group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                </button>
            </div>
            <div className="flex-1">
                {children}
            </div>
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
    healthDailyHabits,
    healthSettings,
    unidades,
    sistemasDetalhes,
    workItems,
    currentMonth,
    currentYear,
    onNavigate,
    onOpenBacklog
}) => {
    const todayStr = new Date().toISOString().split('T')[0];
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];
    const afterTomorrow = new Date();
    afterTomorrow.setDate(afterTomorrow.getDate() + 2);
    const afterTomorrowStr = afterTomorrow.toISOString().split('T')[0];

    // --- ACTIONS LOGIC ---
    const inProgressActions = useMemo(() => {
        return tarefas.filter(t => t.status !== 'concluído' && t.status !== 'excluído' as any);
    }, [tarefas]);

    const nextTwoDaysActions = useMemo(() => {
        return inProgressActions.filter(t =>
            t.data_limite &&
            t.data_limite !== '-' &&
            t.data_limite >= todayStr &&
            t.data_limite <= afterTomorrowStr
        );
    }, [inProgressActions, todayStr, afterTomorrowStr]);

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

    const availableBalance = currentBudget - currentMonthTotalSpent;

    const dailySpending = useMemo(() => {
        const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
        const days = Array(daysInMonth).fill(0);
        currentMonthTransactions.forEach(t => {
            const day = new Date(t.date).getDate();
            if (day <= daysInMonth) {
                days[day - 1] += t.amount;
            }
        });
        return days;
    }, [currentMonthTransactions, currentMonth, currentYear]);

    const currentMonthIncome = useMemo(() => {
        return incomeEntries
            .filter(e => e.month === currentMonth && e.year === currentYear && e.isReceived && e.status !== 'deleted')
            .reduce((acc, curr) => acc + curr.amount, 0);
    }, [incomeEntries, currentMonth, currentYear]);

    const currentTotalBills = useMemo(() => {
        return fixedBills
            .filter(b => b.month === currentMonth && b.year === currentYear)
            .reduce((acc, curr) => acc + curr.amount, 0);
    }, [fixedBills, currentMonth, currentYear]);

    // Previous month data for comparison
    const prevMonth = currentMonth === 0 ? 11 : currentMonth - 1;
    const prevYear = currentMonth === 0 ? currentYear - 1 : currentYear;

    const prevMonthIncome = useMemo(() => {
        return incomeEntries
            .filter(e => e.month === prevMonth && e.year === prevYear && e.isReceived && e.status !== 'deleted')
            .reduce((acc, curr) => acc + curr.amount, 0);
    }, [incomeEntries, prevMonth, prevYear]);

    const prevTotalBills = useMemo(() => {
        return fixedBills
            .filter(b => b.month === prevMonth && b.year === prevYear)
            .reduce((acc, curr) => acc + curr.amount, 0);
    }, [fixedBills, prevMonth, prevYear]);

    const incomeVariation = prevMonthIncome > 0 ? ((currentMonthIncome - prevMonthIncome) / prevMonthIncome) * 100 : 0;
    const billsVariation = prevTotalBills > 0 ? ((currentTotalBills - prevTotalBills) / prevTotalBills) * 100 : 0;

    // --- HEALTH LOGIC ---
    const sortedWeights = useMemo(() => {
        return [...healthWeights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    }, [healthWeights]);

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
        if (!healthSettings.targetWeight || newest.weight <= healthSettings.targetWeight) return 'Meta atingida!';
        const remainingToGoal = newest.weight - healthSettings.targetWeight;
        const daysUntilGoal = remainingToGoal / lostPerDay;
        const goalDate = new Date();
        goalDate.setDate(goalDate.getDate() + daysUntilGoal);
        return goalDate.toLocaleDateString('pt-BR');
    }, [healthWeights, healthSettings.targetWeight]);

    const habitStreak = useMemo(() => {
        let streak = 0;
        const sortedHabits = [...healthDailyHabits].sort((a, b) => b.id.localeCompare(a.id));
        let checkDate = new Date();

        for (const habit of sortedHabits) {
            const hDate = habit.id;
            const expectedDate = checkDate.toISOString().split('T')[0];

            if (hDate === expectedDate) {
                const completedCount = [habit.noSugar, habit.noAlcohol, habit.noSnacks, habit.workout, habit.eatUntil18, habit.eatSlowly].filter(Boolean).length;
                if (completedCount >= 4) { // Consider streak if at least 4 habits done
                    streak++;
                    checkDate.setDate(checkDate.getDate() - 1);
                } else {
                    break;
                }
            } else if (hDate < expectedDate) {
                break;
            }
        }
        return streak;
    }, [healthDailyHabits]);

    // --- SYSTEMS LOGIC ---
    const systemsByPhase = useMemo(() => {
        const phases: Record<string, number> = { ideia: 0, prototipacao: 0, desenvolvimento: 0, testes: 0, producao: 0 };
        sistemasDetalhes.forEach(sys => {
            if (phases[sys.status] !== undefined) {
                phases[sys.status]++;
            }
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

    // --- CHART COMPONENTS ---
    const PieChart = ({ data }: { data: [string, number][] }) => {
        const total = data.reduce((acc, curr) => acc + curr[1], 0);
        if (total === 0) return <div className="h-32 flex items-center justify-center text-slate-300 text-[10px] font-black uppercase">Sem dados</div>;

        let currentAngle = 0;
        const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

        return (
            <div className="flex items-center gap-6">
                <svg viewBox="0 0 100 100" className="w-32 h-32 transform -rotate-90">
                    {data.map((item, i) => {
                        const angle = (item[1] / total) * 360;
                        const x1 = 50 + 40 * Math.cos((currentAngle * Math.PI) / 180);
                        const y1 = 50 + 40 * Math.sin((currentAngle * Math.PI) / 180);
                        const x2 = 50 + 40 * Math.cos(((currentAngle + angle) * Math.PI) / 180);
                        const y2 = 50 + 40 * Math.sin(((currentAngle + angle) * Math.PI) / 180);

                        const largeArc = angle > 180 ? 1 : 0;
                        const d = `M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z`;

                        const path = <path key={i} d={d} fill={colors[i % colors.length]} />;
                        currentAngle += angle;
                        return path;
                    })}
                    <circle cx="50" cy="50" r="25" fill="white" />
                </svg>
                <div className="space-y-1">
                    {data.slice(0, 4).map((item, i) => (
                        <div key={i} className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: colors[i % colors.length] }}></div>
                            <span className="text-[10px] font-bold text-slate-600 uppercase truncate max-w-[80px]">{item[0]}</span>
                            <span className="text-[10px] font-black text-slate-900">{item[1]}</span>
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    const BarChart = ({ data, color, maxHeight = 80 }: { data: number[], color: string, maxHeight?: number }) => {
        const max = Math.max(...data, 1);
        return (
            <div className="flex items-end gap-0.5 h-[100px] w-full bg-slate-50/50 rounded-lg px-2 pb-1">
                {data.map((v, i) => (
                    <div key={i} className="flex-1 flex flex-col justify-end items-center gap-1 group">
                        <div
                            className="w-full rounded-t-sm transition-all group-hover:opacity-80"
                            style={{
                                height: `${(v / max) * maxHeight}px`,
                                backgroundColor: color,
                                minWidth: '2px'
                            }}
                            title={`Dia ${i + 1}: R$ ${v.toFixed(2)}`}
                        />
                        <span className="text-[8px] text-slate-400 font-bold">{i + 1}</span>
                    </div>
                ))}
            </div>
        );
    };

    const SystemsBarChart = ({ data }: { data: [string, number][] }) => {
        const max = Math.max(...data.map(d => d[1]), 1);
        return (
            <div className="space-y-2">
                {data.map((item, i) => (
                    <div key={i} className="space-y-1">
                        <div className="flex justify-between text-[9px] font-black uppercase text-slate-500">
                            <span className="truncate max-w-[150px]">{item[0]}</span>
                            <span>{item[1]} ajustes</span>
                        </div>
                        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-violet-500 rounded-full transition-all duration-1000"
                                style={{ width: `${(item[1] / max) * 100}%` }}
                            />
                        </div>
                    </div>
                ))}
                {data.length === 0 && (
                    <div className="py-8 text-center text-slate-300 text-[10px] font-black uppercase tracking-widest italic">Nenhum ajuste pendente</div>
                )}
            </div>
        );
    };

    return (
        <div className="animate-in fade-in duration-700 space-y-8 md:space-y-12 pb-20 pt-8">
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 max-w-6xl mx-auto">

                {/* CARD: AÇÕES */}
                <DashboardCard
                    title="Ações"
                    iconColor="bg-blue-500"
                    onRedirect={() => onNavigate('gallery')}
                >
                    <div className="space-y-6">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="bg-blue-50 p-4 rounded-2xl border border-blue-100">
                                <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-1">Em Andamento</p>
                                <div className="text-2xl font-black text-slate-900">{inProgressActions.length}</div>
                            </div>
                            <div className="bg-indigo-50 p-4 rounded-2xl border border-indigo-100">
                                <p className="text-[10px] font-black text-indigo-600 uppercase tracking-widest mb-1">Próx. 48h</p>
                                <div className="text-2xl font-black text-slate-900">{nextTwoDaysActions.length}</div>
                            </div>
                        </div>
                        <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Distribuição por Área</p>
                            <PieChart data={actionsByArea} />
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: FINANCEIRO */}
                <DashboardCard
                    title="Financeiro"
                    iconColor="bg-emerald-500"
                    onRedirect={() => onNavigate('finance')}
                >
                    <div className="space-y-6">
                        <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Saldo Disponível</p>
                            <div className={`text-2xl font-black tracking-tight ${availableBalance < 0 ? 'text-rose-600' : 'text-slate-900'}`}>
                                R$ {availableBalance.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                            </div>
                        </div>
                        <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Gastos Diários ({new Intl.DateTimeFormat('pt-BR', { month: 'short' }).format(new Date(currentYear, currentMonth))})</p>
                            <BarChart data={dailySpending} color="#10b981" />
                        </div>
                        <div className="grid grid-cols-2 gap-4 pt-2 border-t border-slate-50">
                            <div>
                                <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Recebido</p>
                                <div className="text-xs font-black text-slate-900">R$ {currentMonthIncome.toLocaleString('pt-BR')}</div>
                                <div className={`text-[8px] font-bold ${incomeVariation >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                    {incomeVariation >= 0 ? '↑' : '↓'} {Math.abs(incomeVariation).toFixed(0)}%
                                </div>
                            </div>
                            <div>
                                <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Em Contas</p>
                                <div className="text-xs font-black text-slate-900">R$ {currentTotalBills.toLocaleString('pt-BR')}</div>
                                <div className={`text-[8px] font-bold ${billsVariation <= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                    {billsVariation <= 0 ? '↓' : '↑'} {Math.abs(billsVariation).toFixed(0)}%
                                </div>
                            </div>
                        </div>
                    </div>
                </DashboardCard>

                {/* CARD: SAÚDE */}
                <DashboardCard
                    title="Saúde"
                    iconColor="bg-rose-500"
                    onRedirect={() => onNavigate('saude')}
                >
                    <div className="space-y-6">
                        <div className="flex justify-between items-end">
                            <div>
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Peso vs Meta</p>
                                <div className="text-2xl font-black text-slate-900">
                                    {currentWeight.toFixed(1)} <span className="text-slate-300 text-sm">/ {healthSettings.targetWeight || '--'} kg</span>
                                </div>
                            </div>
                            <div className="text-right">
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Eliminado</p>
                                <div className="text-xl font-black text-emerald-500">-{totalWeightLost.toFixed(1)} kg</div>
                            </div>
                        </div>
                        <div className="bg-slate-900 p-4 rounded-2xl text-white">
                            <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Previsão (ETA)</p>
                            <div className="text-lg font-black text-blue-400">{healthProjection || '--'}</div>
                        </div>
                        <div>
                            <div className="flex justify-between items-center mb-2">
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Ofensiva de Hábitos</p>
                                <span className="bg-amber-100 text-amber-700 text-[10px] font-black px-2 py-0.5 rounded-full">{habitStreak} dias</span>
                            </div>
                            <div className="flex gap-1">
                                {Array.from({ length: 7 }).map((_, i) => {
                                    const d = new Date();
                                    d.setDate(d.getDate() - (6 - i));
                                    const dStr = d.toISOString().split('T')[0];
                                    const habit = healthDailyHabits.find(h => h.id === dStr);
                                    const count = habit ? [habit.noSugar, habit.noAlcohol, habit.noSnacks, habit.workout, habit.eatUntil18, habit.eatSlowly].filter(Boolean).length : 0;
                                    return (
                                        <div
                                            key={i}
                                            className="flex-1 h-8 rounded-md shadow-inner transition-all"
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
                <DashboardCard
                    title="Sistemas"
                    iconColor="bg-violet-500"
                    onRedirect={() => onNavigate('sistemas-dev')}
                >
                    <div className="space-y-6">
                        <div className="flex flex-wrap gap-1.5">
                            {systemsByPhase.map(([phase, count]) => (
                                <div key={phase} className="px-2 py-1 bg-slate-50 border border-slate-100 rounded-lg flex items-center gap-1.5">
                                    <span className="text-[8px] font-black text-slate-400 uppercase">{phase === 'prototipacao' ? 'Protótipo' : phase === 'producao' ? 'Prod' : phase}</span>
                                    <span className="text-[10px] font-black text-slate-900">{count}</span>
                                </div>
                            ))}
                        </div>
                        <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Pendências por Sistema</p>
                            <SystemsBarChart data={systemsByAdjustments} />
                        </div>
                    </div>
                </DashboardCard>

            </div>
        </div>
    );
};

export default DashboardView;
