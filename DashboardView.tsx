
import React, { useMemo } from 'react';
import { Tarefa, FinanceTransaction, FinanceSettings, FixedBill, IncomeEntry, HealthWeight, Sistema, SistemaStatus, formatDate, Categoria } from './types';

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
  const actionsByArea = useMemo(() => {
    const counts: Record<string, number> = {};
    tarefas.forEach(t => {
      if (t.status === 'concluído') return;
      const area = t.categoria || 'NÃO CLASSIFICADA';
      counts[area] = (counts[area] || 0) + 1;
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [tarefas]);

  const overdueActionsCount = useMemo(() => {
    return tarefas.filter(t =>
      t.status !== 'concluído' &&
      t.data_limite &&
      t.data_limite !== '-' &&
      t.data_limite < todayStr
    ).length;
  }, [tarefas, todayStr]);

  // --- FINANCE LOGIC ---
  const periodKey = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
  const currentBudget = financeSettings.monthlyBudgets?.[periodKey] || financeSettings.monthlyBudget || 0;

  const currentMonthTotalSpent = useMemo(() => {
    return financeTransactions
      .filter(t => {
        const d = new Date(t.date);
        return d.getMonth() === currentMonth && d.getFullYear() === currentYear && t.status !== 'deleted';
      })
      .reduce((acc, curr) => acc + curr.amount, 0);
  }, [financeTransactions, currentMonth, currentYear]);

  const currentMonthIncome = useMemo(() => {
    return incomeEntries
      .filter(e => e.month === currentMonth && e.year === currentYear && e.status !== 'deleted')
      .reduce((acc, curr) => acc + curr.amount, 0);
  }, [incomeEntries, currentMonth, currentYear]);

  const currentMonthObligations = useMemo(() => {
    return fixedBills
      .filter(b => b.month === currentMonth && b.year === currentYear)
      .reduce((acc, curr) => acc + curr.amount, 0);
  }, [fixedBills, currentMonth, currentYear]);

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
  const budgetPercent = currentBudget > 0 ? Math.min((currentMonthTotalSpent / currentBudget) * 100, 100) : 0;

  return (
    <div className="animate-in fade-in duration-700 space-y-8 pb-12">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-xl">
        <div>
          <h2 className="text-3xl font-black text-slate-900 tracking-tighter">Dashboard Geral</h2>
          <p className="text-slate-500 font-bold mt-1 uppercase tracking-widest text-[10px]">
            {new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(new Date(currentYear, currentMonth))}
          </p>
        </div>
        <div className="flex gap-4">
            <div className="bg-slate-50 px-6 py-3 rounded-2xl border border-slate-100 flex flex-col items-center">
                <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Ações Vencidas</span>
                <span className={`text-xl font-black ${overdueActionsCount > 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                    {overdueActionsCount}
                </span>
            </div>
            <div className="bg-slate-50 px-6 py-3 rounded-2xl border border-slate-100 flex flex-col items-center">
                <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Saldo Atual</span>
                <span className={`text-xl font-black ${currentMonthIncome - currentMonthObligations >= 0 ? 'text-emerald-600' : 'text-rose-500'}`}>
                    R$ {(currentMonthIncome - currentMonthObligations).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                </span>
            </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

        {/* Coluna 1: Ações */}
        <div className="lg:col-span-4 space-y-8">
            <div className="bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-lg h-full">
                <h3 className="text-xl font-black text-slate-900 mb-6 flex items-center gap-3">
                    <span className="w-2 h-8 bg-blue-600 rounded-full"></span>
                    Ações por Área
                </h3>

                <div className="space-y-6">
                    {/* Donut Chart (Simples com SVG) */}
                    <div className="relative flex justify-center py-4">
                        <svg viewBox="0 0 36 36" className="w-48 h-48">
                            <path
                                className="text-slate-100"
                                stroke="currentColor"
                                strokeWidth="3"
                                fill="none"
                                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                            />
                            {(() => {
                                let accumulatedPercent = 0;
                                const total = actionsByArea.reduce((acc, curr) => acc + curr[1], 0);
                                const colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

                                return actionsByArea.map((area, idx) => {
                                    const percent = (area[1] / (total || 1)) * 100;
                                    const dashArray = `${percent} ${100 - percent}`;
                                    const dashOffset = -accumulatedPercent;
                                    accumulatedPercent += percent;

                                    return (
                                        <path
                                            key={area[0]}
                                            stroke={colors[idx % colors.length]}
                                            strokeWidth="3.5"
                                            strokeDasharray={dashArray}
                                            strokeDashoffset={dashOffset}
                                            strokeLinecap="round"
                                            fill="none"
                                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                        />
                                    );
                                });
                            })()}
                        </svg>
                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                            <span className="text-4xl font-black text-slate-900">
                                {actionsByArea.reduce((acc, curr) => acc + curr[1], 0)}
                            </span>
                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Total Ativas</span>
                        </div>
                    </div>

                    <div className="space-y-3">
                        {actionsByArea.map((area, idx) => {
                            const colors = ['bg-blue-600', 'bg-emerald-500', 'bg-amber-500', 'bg-rose-500', 'bg-violet-500', 'bg-pink-500'];
                            return (
                                <div key={area[0]} className="flex items-center justify-between p-3 bg-slate-50 rounded-2xl border border-slate-100">
                                    <div className="flex items-center gap-3">
                                        <div className={`w-3 h-3 rounded-full ${colors[idx % colors.length]}`}></div>
                                        <span className="text-xs font-black text-slate-700 uppercase tracking-wider">{area[0]}</span>
                                    </div>
                                    <span className="text-sm font-black text-slate-900">{area[1]}</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        </div>

        {/* Coluna 2: Financeiro */}
        <div className="lg:col-span-5 space-y-8">
            <div className="bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-lg space-y-8">
                <h3 className="text-xl font-black text-slate-900 flex items-center gap-3">
                    <span className="w-2 h-8 bg-emerald-500 rounded-full"></span>
                    Saúde Financeira
                </h3>

                {/* Gasto Acumulado vs Disponível */}
                <div className="space-y-4">
                    <div className="flex justify-between items-end">
                        <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Gasto Acumulado vs Disponível</p>
                            <div className="text-3xl font-black text-slate-900">
                                R$ {currentMonthTotalSpent.toLocaleString('pt-BR')}
                                <span className="text-slate-300 text-lg ml-2">/ R$ {currentBudget.toLocaleString('pt-BR')}</span>
                            </div>
                        </div>
                        <span className={`text-xs font-black uppercase px-3 py-1 rounded-lg ${budgetPercent > 90 ? 'bg-rose-100 text-rose-600' : 'bg-emerald-100 text-emerald-600'}`}>
                            {budgetPercent.toFixed(1)}%
                        </span>
                    </div>
                    <div className="h-4 bg-slate-100 rounded-full overflow-hidden shadow-inner">
                        <div
                            className={`h-full transition-all duration-1000 ${budgetPercent > 90 ? 'bg-rose-500' : 'bg-emerald-500'}`}
                            style={{ width: `${budgetPercent}%` }}
                        />
                    </div>
                </div>

                {/* Reserva de Emergência */}
                <div className="space-y-4 pt-6 border-t border-slate-50">
                    <div className="flex justify-between items-end">
                        <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Reserva de Emergência</p>
                            <div className="text-3xl font-black text-emerald-600">
                                {emergencyReservePercent.toFixed(1)}%
                            </div>
                            <p className="text-[10px] font-bold text-slate-400 mt-1">
                                R$ {emergencyReserveCurrent.toLocaleString('pt-BR')} de R$ {emergencyReserveTarget.toLocaleString('pt-BR')}
                            </p>
                        </div>
                        <div className="w-12 h-12 bg-emerald-50 rounded-2xl flex items-center justify-center text-emerald-600">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
                        </div>
                    </div>
                    <div className="h-4 bg-slate-100 rounded-full overflow-hidden shadow-inner">
                        <div
                            className="h-full bg-emerald-500 rounded-full transition-all duration-1000"
                            style={{ width: `${emergencyReservePercent}%` }}
                        />
                    </div>
                </div>

                {/* Comparativo Renda vs Obrigações */}
                <div className="pt-6 border-t border-slate-50">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-8">Projeção: Renda vs Obrigações</p>
                    <div className="flex items-end gap-8 h-32 px-4">
                        {(() => {
                            const max = Math.max(currentMonthIncome, currentMonthObligations, 1);
                            const incomeHeight = (currentMonthIncome / max) * 100;
                            const obligationsHeight = (currentMonthObligations / max) * 100;

                            return (
                                <>
                                    <div className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                                        <div className="w-full bg-emerald-500 rounded-t-xl relative group transition-all hover:bg-emerald-600" style={{ height: `${incomeHeight}%` }}>
                                            <div className="absolute -top-7 left-1/2 -translate-x-1/2 text-[10px] font-black text-emerald-600 whitespace-nowrap">
                                                R$ {currentMonthIncome.toLocaleString('pt-BR')}
                                            </div>
                                        </div>
                                        <span className="text-[9px] font-black text-slate-400 uppercase">Rendas</span>
                                    </div>
                                    <div className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                                        <div
                                            className="w-full bg-rose-500 rounded-t-xl relative group transition-all hover:bg-rose-600"
                                            style={{ height: `${obligationsHeight}%` }}
                                        >
                                            <div className="absolute -top-7 left-1/2 -translate-x-1/2 text-[10px] font-black text-rose-600 whitespace-nowrap">
                                                R$ {currentMonthObligations.toLocaleString('pt-BR')}
                                            </div>
                                        </div>
                                        <span className="text-[9px] font-black text-slate-400 uppercase">Obrigações</span>
                                    </div>
                                </>
                            );
                        })()}
                    </div>
                </div>
            </div>
        </div>

        {/* Coluna 3: Saúde e Sistemas */}
        <div className="lg:col-span-3 space-y-8">
            {/* Saúde */}
            <div className="bg-gradient-to-br from-rose-500 to-rose-600 p-8 rounded-[2.5rem] shadow-lg text-white relative overflow-hidden">
                <div className="absolute top-0 right-0 p-4 opacity-20">
                    <svg className="w-20 h-20" fill="currentColor" viewBox="0 0 24 24"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" /></svg>
                </div>
                <div className="relative z-10">
                    <h3 className="text-xl font-black mb-6 uppercase tracking-widest text-[12px]">Saúde & Peso</h3>
                    <div className="space-y-6">
                        <div>
                            <p className="text-rose-100 text-[10px] font-black uppercase tracking-widest mb-1">Peso Atual</p>
                            <div className="flex items-baseline gap-2">
                                <span className="text-5xl font-black tracking-tighter">{currentWeight.toFixed(1)}</span>
                                <span className="text-lg font-bold text-rose-200">kg</span>
                            </div>
                        </div>
                        <div className="bg-white/10 backdrop-blur-md rounded-2xl p-4 border border-white/10">
                            <p className="text-rose-100 text-[9px] font-black uppercase tracking-widest mb-1">Total Eliminado</p>
                            <div className="flex items-baseline gap-2">
                                <span className="text-2xl font-black text-emerald-300">-{totalWeightLost.toFixed(1)}</span>
                                <span className="text-sm font-bold text-emerald-200">kg</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Sistemas */}
            <div className="bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-lg">
                <h3 className="text-xl font-black text-slate-900 mb-6 flex items-center gap-3">
                    <span className="w-2 h-8 bg-violet-600 rounded-full"></span>
                    Sistemas
                </h3>
                <div className="space-y-4">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Status dos Projetos</span>
                        <span className="bg-violet-100 text-violet-700 px-3 py-1 rounded-full text-[10px] font-black">{systemStats.length}</span>
                    </div>
                    <div className="space-y-2">
                        {systemStats.map(sys => (
                            <div key={sys.name} className="p-4 bg-slate-50 rounded-2xl border border-slate-100 flex items-center justify-between group hover:border-violet-300 transition-all">
                                <span className="text-xs font-bold text-slate-700">{sys.name}</span>
                                <span className={`text-[8px] font-black uppercase px-2 py-1 rounded-lg ${
                                    sys.status === 'producao' ? 'bg-emerald-100 text-emerald-700' :
                                    sys.status === 'desenvolvimento' ? 'bg-blue-100 text-blue-700' :
                                    sys.status === 'testes' ? 'bg-amber-100 text-amber-700' :
                                    'bg-slate-200 text-slate-500'
                                }`}>
                                    {sys.status}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>

      </div>
    </div>
  );
};

export default DashboardView;
