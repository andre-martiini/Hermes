import React, { useState, useMemo } from 'react';
import { HealthWeight, DailyHabits, HealthSettings, formatDate } from './types';

interface HealthViewProps {
    weights: HealthWeight[];
    dailyHabits: DailyHabits[];
    settings: HealthSettings;
    onUpdateSettings: (settings: HealthSettings) => void;
    onAddWeight: (weight: number, date: string) => void;
    onDeleteWeight: (id: string) => void;
    onUpdateHabits: (date: string, habits: Partial<DailyHabits>) => void;
}

const HealthSection = ({ title, children, iconColor, defaultExpanded = true }: { title: string, children: React.ReactNode, iconColor: string, defaultExpanded?: boolean }) => {
    const [isExpanded, setIsExpanded] = useState(defaultExpanded);

    return (
        <div className="bg-white p-6 md:p-8 rounded-none md:rounded-lg border-b md:border border-slate-200 shadow-none md:shadow-lg">
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full flex items-center justify-between group"
            >
                <div className="flex items-center gap-3">
                    <span className={`w-2 h-8 ${iconColor} rounded-full`}></span>
                    <h3 className="text-xl font-black text-slate-900 tracking-tight capitalize text-left">{title}</h3>
                </div>
                <svg className={`w-5 h-5 text-slate-300 group-hover:text-slate-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {isExpanded && (
                <div className="mt-6 animate-in slide-in-from-top-2 duration-300">
                    {children}
                </div>
            )}
        </div>
    );
};

const HabitHeatmap = ({ habits, selectedDate, onSelectDate }: { habits: DailyHabits[], selectedDate: string, onSelectDate: (date: string) => void }) => {
    const today = new Date();
    const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    const monthName = new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(today);
    const todayStr = today.toISOString().split('T')[0];

    return (
        <HealthSection title={`Mapa de Consistência - ${monthName}`} iconColor="bg-blue-500">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                <div>
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">Volume de hábitos cumpridos por dia</p>
                </div>
                <div className="flex items-center gap-4 bg-slate-50 p-3 rounded-lg md:rounded-2xl border border-slate-100">
                    <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest">Legenda:</span>
                    <div className="flex gap-1.5">
                        {[0, 1, 2, 3, 4, 5, 6].map(c => (
                            <div key={c} className="w-4 h-4 rounded-md shadow-sm" title={`${c} hábitos`} style={{ backgroundColor: `hsl(${(c / 6) * 120}, 75%, 45%)` }}></div>
                        ))}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-7 sm:grid-cols-10 md:grid-cols-15 lg:grid-cols-[repeat(31,minmax(0,1fr))] gap-2 sm:gap-3 overflow-x-auto pb-4">
                {Array.from({ length: daysInMonth }).map((_, i) => {
                    const day = i + 1;
                    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                    const dayHabits = habits.find(h => h.id === dateStr);
                    const isFuture = dateStr > todayStr;
                    const isSelected = selectedDate === dateStr;

                    let completedCount = 0;
                    let hasRecord = false;
                    if (dayHabits) {
                        hasRecord = true;
                        if (dayHabits.noSugar) completedCount++;
                        if (dayHabits.noAlcohol) completedCount++;
                        if (dayHabits.noSnacks) completedCount++;
                        if (dayHabits.workout) completedCount++;
                        if (dayHabits.eatUntil18) completedCount++;
                        if (dayHabits.eatSlowly) completedCount++;
                    }

                    const ratio = completedCount / 6;
                    let style: React.CSSProperties = { backgroundColor: '#f8fafc', color: '#cbd5e1' };

                    if (hasRecord) {
                        const hue = ratio * 120;
                        style = {
                            backgroundColor: `hsl(${hue}, 75%, 45%)`,
                            color: 'white',
                            boxShadow: isSelected ? `0 0 0 3px white, 0 0 0 6px hsl(${hue}, 75%, 45%)` : `0 4px 12px -4px hsl(${hue}, 75%, 45%)`
                        };
                    } else if (isSelected) {
                        style = {
                            backgroundColor: '#e2e8f0',
                            color: '#475569',
                            boxShadow: `0 0 0 3px white, 0 0 0 6px #cbd5e1`
                        };
                    }

                    return (
                        <button
                            key={day}
                            disabled={isFuture}
                            onClick={() => onSelectDate(dateStr)}
                            title={isFuture ? `Data futura` : hasRecord ? `Dia ${day}: ${completedCount}/6 hábitos` : `Dia ${day}: Sem registro`}
                            className={`aspect-square rounded-xl flex items-center justify-center text-[10px] md:text-sm font-black transition-all duration-300 ${isFuture ? 'opacity-20 cursor-not-allowed' : 'hover:scale-125 hover:z-10 cursor-pointer'} ${hasRecord ? 'hover:shadow-lg' : 'hover:bg-slate-200'} ${isSelected ? 'scale-110 z-10' : ''}`}
                            style={style}
                        >
                            {day}
                        </button>
                    );
                })}
            </div>
        </HealthSection>
    );
};

const HealthView: React.FC<HealthViewProps> = ({
    weights,
    dailyHabits,
    settings,
    onUpdateSettings,
    onAddWeight,
    onDeleteWeight,
    onUpdateHabits
}) => {
    const todayStr = new Date().toISOString().split('T')[0];
    const [selectedDate, setSelectedDate] = useState<string>(todayStr);
    const [newWeight, setNewWeight] = useState<string>('');
    const [targetInput, setTargetInput] = useState<string>(settings.targetWeight?.toString() || '');
    const [isEditingTarget, setIsEditingTarget] = useState(false);

    const currentHabits = dailyHabits.find(h => h.id === selectedDate) || {
        id: selectedDate,
        noSugar: false,
        noAlcohol: false,
        noSnacks: false,
        workout: false,
        eatUntil18: false,
        eatSlowly: false
    };

    const sortedWeights = useMemo(() => {
        return [...weights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    }, [weights]);

    const currentWeight = sortedWeights[0]?.weight || 0;
    const initialWeight = sortedWeights[sortedWeights.length - 1]?.weight || 0;
    const totalLost = initialWeight > 0 ? initialWeight - currentWeight : 0;

    // Projection Logic
    const projection = useMemo(() => {
        if (weights.length < 2) return null;

        const oldest = weights[weights.length - 1];
        const newest = weights[0];

        const diffWeight = oldest.weight - newest.weight;
        const diffDays = (new Date(newest.date).getTime() - new Date(oldest.date).getTime()) / (1000 * 60 * 60 * 24);

        if (diffDays <= 0 || diffWeight <= 0) return null;

        const lostPerDay = diffWeight / diffDays;
        const lostPerWeek = lostPerDay * 7;

        if (!settings.targetWeight || newest.weight <= settings.targetWeight) return { lostPerWeek, goalDate: 'Meta atingida!' };

        const remainingToGoal = newest.weight - settings.targetWeight;
        const daysUntilGoal = remainingToGoal / lostPerDay;

        const goalDate = new Date();
        goalDate.setDate(goalDate.getDate() + daysUntilGoal);

        return {
            lostPerWeek,
            goalDate: goalDate.toLocaleDateString('pt-BR')
        };
    }, [weights, settings.targetWeight]);

    const handleHabitToggle = (habitKey: keyof DailyHabits) => {
        if (habitKey === 'id') return;
        onUpdateHabits(selectedDate, { [habitKey]: !currentHabits[habitKey] });
    };

    const generateChartPath = () => {
        if (weights.length < 2) return "";
        const w = 400;
        const h = 150;
        const padding = 20;

        const chartWeights = [...weights].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
        const minW = Math.min(...chartWeights.map(v => v.weight), settings.targetWeight || Infinity) - 2;
        const maxW = Math.max(...chartWeights.map(v => v.weight), settings.targetWeight || -Infinity) + 2;
        const rangeW = maxW - minW;

        const points = chartWeights.map((v, i) => {
            const x = padding + (i / (chartWeights.length - 1)) * (w - 2 * padding);
            const y = h - padding - ((v.weight - minW) / rangeW) * (h - 2 * padding);
            return `${x},${y}`;
        });

        return `M ${points.join(' L ')}`;
    };

    return (
        <div className="space-y-0 md:space-y-8 pb-20">
            {/* Header Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-0 md:gap-6 border-b md:border-none border-slate-100">
                <div className="bg-white p-6 rounded-none md:rounded-[2rem] border-b md:border border-slate-200 shadow-none md:shadow-xl flex flex-col justify-center">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Peso Atual</span>
                    <div className="flex items-baseline gap-2">
                        <span className="text-4xl font-black text-slate-900">{currentWeight.toFixed(1) || '--'}</span>
                        <span className="text-sm font-bold text-slate-400">kg</span>
                    </div>
                </div>

                <div className="bg-white p-6 rounded-none md:rounded-[2rem] border-b md:border border-slate-200 shadow-none md:shadow-xl flex flex-col justify-center relative group">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Meta</span>
                    <div className="flex items-baseline gap-2">
                        {isEditingTarget ? (
                            <input
                                autoFocus
                                type="number"
                                value={targetInput}
                                onChange={(e) => setTargetInput(e.target.value)}
                                onBlur={() => {
                                    onUpdateSettings({ targetWeight: parseFloat(targetInput) || 0 });
                                    setIsEditingTarget(false);
                                }}
                                className="text-2xl font-black text-rose-600 bg-rose-50 rounded-lg px-2 w-24 outline-none"
                            />
                        ) : (
                            <span className="text-4xl font-black text-rose-600" onClick={() => setIsEditingTarget(true)}>
                                {settings.targetWeight?.toFixed(1) || '--'}
                            </span>
                        )}
                        <span className="text-sm font-bold text-slate-400">kg</span>
                    </div>
                    <button onClick={() => setIsEditingTarget(true)} className="absolute top-4 right-4 text-slate-300 hover:text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                    </button>
                </div>

                <div className="bg-emerald-500 p-6 rounded-none md:rounded-[2rem] border-b md:border-none border-emerald-600 shadow-none md:shadow-xl flex flex-col justify-center text-white">
                    <span className="text-[10px] font-black text-emerald-100 uppercase tracking-widest mb-1">Eliminado</span>
                    <div className="flex items-baseline gap-2">
                        <span className="text-4xl font-black">{totalLost > 0 ? `-${totalLost.toFixed(1)}` : '--'}</span>
                        <span className="text-sm font-bold text-emerald-100">kg</span>
                    </div>
                </div>

                <div className="bg-slate-900 p-6 rounded-none md:rounded-[2rem] border-b md:border-none border-slate-800 shadow-none md:shadow-xl flex flex-col justify-center text-white">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Previsão Meta</span>
                    <div className="flex flex-col">
                        <span className="text-xl font-black text-blue-400">{projection?.goalDate || 'Aguardando dados...'}</span>
                        {projection?.lostPerWeek && (
                            <span className="text-[9px] font-bold text-slate-500 uppercase mt-1">Média: {projection.lostPerWeek.toFixed(2)}kg/sem</span>
                        )}
                    </div>
                </div>
            </div>

            {/* WEIGHT REGISTRY AND EVOLUTION CHART (Moved here for mobile positioning) */}
            <div className="flex flex-col gap-0 md:gap-8">
                <HealthSection title="Registro de Peso" iconColor="bg-rose-500">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8">
                        <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">Geralmente aos sábados</p>
                        </div>
                        <div className="flex flex-wrap gap-3">
                            <input
                                type="number"
                                step="0.1"
                                placeholder="Peso (Kg)"
                                value={newWeight}
                                onChange={(e) => setNewWeight(e.target.value)}
                                className="bg-slate-100 border-none rounded-lg md:rounded-2xl px-6 py-4 text-sm font-bold text-slate-900 w-32 focus:ring-2 focus:ring-rose-500 transition-all"
                            />
                            <button
                                onClick={() => {
                                    if (newWeight) {
                                        onAddWeight(parseFloat(newWeight), new Date().toISOString().split('T')[0]);
                                        setNewWeight('');
                                    }
                                }}
                                className="flex-1 bg-rose-500 text-white px-8 py-4 rounded-lg md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-rose-600 transition-all active:scale-95 flex items-center justify-center gap-3"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                                Registrar
                            </button>
                        </div>
                    </div>

                    {/* Evolution Chart (SVG) */}
                    <div className="bg-slate-50 rounded-none md:rounded-3xl p-6 border border-slate-100 mb-8 overflow-hidden">
                        <div className="flex justify-between items-center mb-4">
                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Evolução de Peso</span>
                            <div className="flex gap-4">
                                <div className="flex items-center gap-1.5">
                                    <div className="w-2 h-2 rounded-full bg-rose-500"></div>
                                    <span className="text-[8px] font-bold text-slate-500 uppercase">Peso</span>
                                </div>
                            </div>
                        </div>
                        <div className="relative h-[150px] w-full">
                            {weights.length > 1 ? (
                                <svg viewBox="0 0 400 150" className="w-full h-full overflow-visible">
                                    {/* Target Line */}
                                    {settings.targetWeight && weights.length > 0 && (() => {
                                        const min = Math.min(...weights.map(v => v.weight), settings.targetWeight) - 2;
                                        const max = Math.max(...weights.map(v => v.weight), settings.targetWeight) + 2;
                                        const targetY = 150 - 20 - ((settings.targetWeight - min) / (max - min)) * (150 - 40);
                                        return (
                                            <line
                                                x1="0" y1={targetY}
                                                x2="400" y2={targetY}
                                                stroke="#FDA4AF" strokeDasharray="4 4" strokeWidth="1"
                                            />
                                        );
                                    })()}
                                    <path
                                        d={generateChartPath()}
                                        fill="none"
                                        stroke="#F43F5E"
                                        strokeWidth="3"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        className="drop-shadow-sm"
                                    />
                                    {/* Points */}
                                    {[...weights].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()).map((v, i, arr) => {
                                        const w_chart = 400; const h_chart = 150; const p = 20;
                                        const min = Math.min(...arr.map(x => x.weight), settings.targetWeight || Infinity) - 2;
                                        const max = Math.max(...arr.map(x => x.weight), settings.targetWeight || -Infinity) + 2;
                                        const x = p + (i / (arr.length - 1)) * (w_chart - 2 * p);
                                        const y = h_chart - p - ((v.weight - min) / (max - min)) * (h_chart - 2 * p);
                                        return (
                                            <circle key={i} cx={x} cy={y} r="4" fill="white" stroke="#F43F5E" strokeWidth="2" />
                                        );
                                    })}
                                </svg>
                            ) : (
                                <div className="h-full flex items-center justify-center text-slate-300 text-[10px] font-black uppercase tracking-widest italic">
                                    Precisamos de pelo menos 2 registros para o gráfico
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Weights History */}
                    <div className="overflow-hidden border border-slate-100 rounded-none md:rounded-3xl">
                        {/* Desktop Table */}
                        <table className="w-full text-left hidden md:table">
                            <thead className="bg-slate-50 border-b border-slate-200">
                                <tr>
                                    <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Data</th>
                                    <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-right">Peso</th>
                                    <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest w-16"></th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-50">
                                {sortedWeights.map((w) => (
                                    <tr key={w.id} className="hover:bg-slate-50/50 transition-colors group/row">
                                        <td className="px-6 py-4 text-xs font-black text-slate-700">{formatDate(w.date)}</td>
                                        <td className="px-6 py-4 text-sm font-black text-slate-900 text-right">{w.weight.toFixed(1)} kg</td>
                                        <td className="px-6 py-4 text-right">
                                            <button
                                                onClick={() => onDeleteWeight(w.id)}
                                                className="p-2 text-rose-300 hover:text-rose-600 hover:bg-rose-50 rounded-lg md:rounded-xl transition-all opacity-0 group-hover/row:opacity-100"
                                                title="Excluir Registro"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        {/* Mobile Card View */}
                        <div className="md:hidden divide-y divide-slate-50">
                            {sortedWeights.map((w) => (
                                <div key={w.id} className="p-4 flex justify-between items-center bg-white">
                                    <div>
                                        <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{formatDate(w.date)}</div>
                                        <div className="text-lg font-black text-slate-900">{w.weight.toFixed(1)} kg</div>
                                    </div>
                                    <button
                                        onClick={() => onDeleteWeight(w.id)}
                                        className="p-3 text-rose-500 bg-rose-50 rounded-lg md:rounded-xl active:bg-rose-100 transition-all"
                                    >
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                    </button>
                                </div>
                            ))}
                        </div>

                        {sortedWeights.length === 0 && (
                            <div className="py-12 text-center text-slate-300 font-black uppercase tracking-widest italic text-[10px] border-t border-slate-50">
                                Tudo pronto para começar!
                            </div>
                        )}
                    </div>
                </HealthSection>
            </div>

            {/* Habit Consistency Heatmap */}
            <HabitHeatmap habits={dailyHabits} selectedDate={selectedDate} onSelectDate={setSelectedDate} />

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-0 md:gap-8">
                {/* Daily Habits */}
                <div className="lg:col-span-12 flex flex-col">
                    <HealthSection title={selectedDate === todayStr ? "Hábitos de Hoje" : `Hábitos do dia ${selectedDate.split('-').reverse().join('/')}`} iconColor="bg-amber-500">
                        <div className="space-y-4">
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1 mb-4">
                                {selectedDate === todayStr ? "Consistência é o segredo" : "Editando registros retroativos"}
                            </p>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                {[
                                    { id: 'noSugar', label: 'Sem Açúcar', color: 'rose' },
                                    { id: 'noAlcohol', label: 'Sem Álcool', color: 'purple' },
                                    { id: 'noSnacks', label: 'Sem Lanches/Delivery', color: 'orange' },
                                    { id: 'workout', label: 'Treino do Dia', color: 'emerald' },
                                    { id: 'eatUntil18', label: 'Comer até as 18h', color: 'blue' },
                                    { id: 'eatSlowly', label: 'Comer Devagar', color: 'indigo' }
                                ].map((habit) => {
                                    const colorMap: Record<string, { bg: string, border: string, text: string, dot: string }> = {
                                        rose: { bg: 'bg-rose-50', border: 'border-rose-200', text: 'text-rose-700', dot: 'bg-rose-500' },
                                        purple: { bg: 'bg-purple-50', border: 'border-purple-200', text: 'text-purple-700', dot: 'bg-purple-500' },
                                        orange: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', dot: 'bg-orange-500' },
                                        emerald: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', dot: 'bg-emerald-500' },
                                        blue: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', dot: 'bg-blue-500' },
                                        indigo: { bg: 'bg-indigo-50', border: 'border-indigo-200', text: 'text-indigo-700', dot: 'bg-indigo-500' }
                                    };
                                    const colors = colorMap[habit.color] || colorMap.rose;
                                    const isActive = !!currentHabits[habit.id as keyof DailyHabits];

                                    return (
                                        <button
                                            key={habit.id}
                                            onClick={() => handleHabitToggle(habit.id as keyof DailyHabits)}
                                            className={`w-full flex items-center justify-between p-4 rounded-lg md:rounded-2xl border-2 transition-all duration-300 ${isActive
                                                ? `${colors.bg} ${colors.border} shadow-sm`
                                                : 'bg-white border-slate-100 hover:border-slate-200'
                                                }`}
                                        >
                                            <span className={`text-sm font-bold ${isActive ? colors.text : 'text-slate-600'}`}>
                                                {habit.label}
                                            </span>
                                            <div className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${isActive
                                                ? `${colors.dot} text-white scale-110`
                                                : 'border-2 border-slate-200'
                                                }`}>
                                                {isActive && (
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" /></svg>
                                                )}
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    </HealthSection>
                </div>
            </div>
        </div>
    );
};

export default HealthView;
