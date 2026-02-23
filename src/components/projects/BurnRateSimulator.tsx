import React, { useState, useMemo } from 'react';
import { VinculoProjeto, TipoBolsa } from '../../../types';

interface BurnRateSimulatorProps {
    availableBalance: number; // Current cash on hand (Total - Spent)
    totalBudget: number;      // Original Total Budget for Scholarships
    activeLinks: VinculoProjeto[];
    scholarshipTypes: TipoBolsa[];
}

export const BurnRateSimulator: React.FC<BurnRateSimulatorProps> = ({
    availableBalance,
    totalBudget,
    activeLinks,
    scholarshipTypes
}) => {
    const [scenarioMode, setScenarioMode] = useState<'A' | 'B'>('A');
    const [selectedTypeId, setSelectedTypeId] = useState('');
    const [targetMonths, setTargetMonths] = useState(12);

    // Calculate Monthly Burn Rate (Committed)
    const monthlyBurnRate = useMemo(() => {
        const now = new Date();
        return activeLinks.reduce((acc, link) => {
            if (link.status === 'Desligado(a)' || link.status === 'Concluído(a)') return acc;
            const end = new Date(link.data_fim_prevista);
            if (end < now) return acc;
            return acc + link.valor_bolsa_mensal_atual;
        }, 0);
    }, [activeLinks]);

    // Calculate Future Commitment (Total remaining to be paid)
    const futureCommitment = useMemo(() => {
        const now = new Date();
        return activeLinks.reduce((acc, link) => {
            if (link.status === 'Desligado(a)' || link.status === 'Concluído(a)') return acc;
            const end = new Date(link.data_fim_prevista);
            if (end < now) return acc;

            // Months remaining
            const months = (end.getFullYear() - now.getFullYear()) * 12 + (end.getMonth() - now.getMonth());
            return acc + (link.valor_bolsa_mensal_atual * Math.max(0, months));
        }, 0);
    }, [activeLinks]);

    const realFreeBalance = availableBalance - futureCommitment;

    // Simulation Results
    const simulationResult = useMemo(() => {
        if (scenarioMode === 'A') {
            if (!selectedTypeId) return null;
            const type = scholarshipTypes.find(t => t.id === selectedTypeId);
            if (!type) return null;

            // How many months can we sustain this new scholarship?
            // Formula: RealFreeBalance / MonthlyValue
            const months = Math.floor(realFreeBalance / type.valor_integral);
            return {
                label: 'Sustentabilidade',
                value: `${months} meses`,
                isPositive: months >= 12,
                detail: `Custo mensal: ${new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(type.valor_integral)}`
            };
        } else {
            // Scenario B: Max Value for N months
            if (targetMonths <= 0) return null;
            const maxVal = realFreeBalance / targetMonths;
            return {
                label: 'Valor Máximo Mensal',
                value: new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(maxVal),
                isPositive: maxVal > 0,
                detail: `Para ${targetMonths} meses de duração`
            };
        }
    }, [scenarioMode, selectedTypeId, targetMonths, realFreeBalance, scholarshipTypes]);

    // Simple SVG Chart Data
    const chartData = useMemo(() => {
        const months = 12;
        const data = [];
        let currentBalance = availableBalance; // Start with current cash

        for (let i = 0; i <= months; i++) {
            // Assuming simplified constant burn rate for chart visualization
            // In reality, it drops as scholarships end, but let's keep it simple or calculate properly

            // Calculate actual burn for month i
            const date = new Date();
            date.setMonth(date.getMonth() + i);

            const burnForMonth = activeLinks.reduce((acc, link) => {
                if (link.status === 'Desligado(a)' || link.status === 'Concluído(a)') return acc;
                const end = new Date(link.data_fim_prevista);
                return date <= end ? acc + link.valor_bolsa_mensal_atual : acc;
            }, 0);

            data.push({
                month: i,
                balance: currentBalance,
                burn: burnForMonth
            });

            currentBalance -= burnForMonth;
        }
        return data;
    }, [availableBalance, activeLinks]);

    return (
        <div className="space-y-8">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="p-6 bg-slate-50 rounded-[2rem] border border-slate-200">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Saldo em Caixa</p>
                    <p className="text-2xl font-black text-slate-800">{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(availableBalance)}</p>
                </div>
                <div className="p-6 bg-slate-50 rounded-[2rem] border border-slate-200">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Comprometido (Futuro)</p>
                    <p className="text-2xl font-black text-amber-600">{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(futureCommitment)}</p>
                </div>
                <div className={`p-6 rounded-[2rem] border ${realFreeBalance >= 0 ? 'bg-emerald-50 border-emerald-100' : 'bg-rose-50 border-rose-100'}`}>
                    <p className={`text-[10px] font-black uppercase tracking-widest ${realFreeBalance >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>Saldo Real Livre</p>
                    <p className={`text-2xl font-black ${realFreeBalance >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(realFreeBalance)}</p>
                </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-[2rem] p-8 shadow-xl">
                <h4 className="text-lg font-black text-slate-900 mb-6">Simulador de Contratação</h4>

                <div className="flex gap-6 mb-6 border-b border-slate-100 pb-6">
                    <button
                        onClick={() => setScenarioMode('A')}
                        className={`flex-1 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${scenarioMode === 'A' ? 'bg-indigo-600 text-white shadow-lg' : 'bg-slate-50 text-slate-400 hover:bg-slate-100'}`}
                    >
                        Cenário A: Por Modalidade
                    </button>
                    <button
                        onClick={() => setScenarioMode('B')}
                        className={`flex-1 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${scenarioMode === 'B' ? 'bg-indigo-600 text-white shadow-lg' : 'bg-slate-50 text-slate-400 hover:bg-slate-100'}`}
                    >
                        Cenário B: Por Orçamento
                    </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
                    <div>
                        {scenarioMode === 'A' ? (
                            <div className="space-y-4">
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Selecionar Modalidade</label>
                                <select
                                    value={selectedTypeId}
                                    onChange={(e) => setSelectedTypeId(e.target.value)}
                                    className="w-full p-4 rounded-2xl border border-slate-200 bg-slate-50 font-bold text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500"
                                >
                                    <option value="">Selecione...</option>
                                    {scholarshipTypes.map(t => (
                                        <option key={t.id} value={t.id}>{t.nome_modalidade} ({new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(t.valor_integral)})</option>
                                    ))}
                                </select>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Duração Desejada (Meses)</label>
                                <input
                                    type="number"
                                    value={targetMonths}
                                    onChange={(e) => setTargetMonths(Number(e.target.value))}
                                    className="w-full p-4 rounded-2xl border border-slate-200 bg-slate-50 font-bold text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500"
                                />
                            </div>
                        )}
                    </div>

                    <div className="text-center p-6 bg-slate-50 rounded-[2rem] border border-slate-100">
                        {simulationResult ? (
                            <>
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{simulationResult.label}</p>
                                <p className={`text-4xl font-black my-2 ${simulationResult.isPositive ? 'text-indigo-600' : 'text-rose-500'}`}>{simulationResult.value}</p>
                                <p className="text-xs font-bold text-slate-500">{simulationResult.detail}</p>
                            </>
                        ) : (
                            <p className="text-slate-400 font-bold text-sm">Configure os parâmetros para simular.</p>
                        )}
                    </div>
                </div>
            </div>

            {/* Burn Down Chart Visualization */}
            <div className="bg-white border border-slate-200 rounded-[2rem] p-8 shadow-sm">
                <h4 className="text-lg font-black text-slate-900 mb-6">Projeção de Saldo (Burn-down)</h4>
                <div className="h-64 flex items-end gap-2">
                    {chartData.map((data, i) => {
                        const heightPercent = Math.max(0, Math.min(100, (data.balance / availableBalance) * 100));
                        return (
                            <div key={i} className="flex-1 flex flex-col items-center gap-2 group relative">
                                <div className="absolute bottom-full mb-2 bg-slate-900 text-white text-[9px] font-bold px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
                                    Mês {i}: {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(data.balance)}
                                </div>
                                <div
                                    className={`w-full rounded-t-lg transition-all duration-500 ${data.balance >= 0 ? 'bg-indigo-200 group-hover:bg-indigo-400' : 'bg-rose-300'}`}
                                    style={{ height: `${heightPercent}%` }}
                                ></div>
                                <span className="text-[8px] font-black text-slate-400">{i}</span>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};
