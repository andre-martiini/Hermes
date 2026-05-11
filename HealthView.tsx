import React, { useState, useMemo, useEffect } from 'react';
import { 
    HealthWeight, DailyHabits, HealthSettings, ExerciseLog, 
    ExerciseSettings, PullupPhase, formatDate, formatDateLocalISO, 
    HealthExam, PoolItem, HealthTelegramReminder
} from './types';
import { GoogleHealthService } from './GoogleHealthService';
import { HealthSummaryCard } from './src/components/HealthSummaryCard';

interface HealthViewProps {
    weights: HealthWeight[];
    dailyHabits: DailyHabits[];
    settings: HealthSettings;
    onUpdateSettings: (settings: HealthSettings) => void;
    onAddWeight: (weight: number, date: string) => void;
    onDeleteWeight: (id: string) => void;
    onUpdateHabits: (date: string, habits: Partial<DailyHabits>) => void;
    exerciseLogs: ExerciseLog[];
    exerciseSettings: ExerciseSettings;
    onSaveExerciseLog: (date: string, data: Partial<ExerciseLog>) => Promise<void>;
    telegramReminders: HealthTelegramReminder[];
    onSaveTelegramReminder: (reminder: HealthTelegramReminder) => Promise<void>;
    onDeleteTelegramReminder: (id: string) => Promise<void>;
    exams: HealthExam[];
    onAddExam: (exam: Omit<HealthExam, 'id' | 'data_criacao' | 'pool_dados'>, files: File[]) => void;
    onDeleteExam: (id: string) => void;
    onUpdateExam: (id: string, updates: Partial<HealthExam>) => void;
    isDark?: boolean;
}

// --- UTILS & CONSTANTS ---

const PULLUP_PHASE_LABELS: Record<PullupPhase, { name: string; metric: string; gate: string; tip: string }> = {
    dead_hang: { name: 'Fase 1 — Barra Parada', metric: 'segundos pendurado', gate: 'Meta de avanço: 30s contínuos (2 sessões)', tip: 'Segure-se na barra com os braços estendidos. Foco no grip.' },
    negative: { name: 'Fase 2 — Negativas', metric: 'repetições', gate: 'Meta de avanço: 5 negativas (2 sessões)', tip: 'Suba com auxílio e desça bem devagar (~5s). Foco no controle.' },
    assisted: { name: 'Fase 3 — Barra Assistida', metric: 'repetições', gate: 'Meta de avanço: 8 repetições (2 sessões)', tip: 'Use faixa elástica na barra para reduzir o peso corporal.' },
    full: { name: 'Fase 4 — Barra Completa', metric: 'repetições', gate: '', tip: 'Puxada completa do zero até o queixo acima da barra.' },
};

const SPINE_ROUTINE = [
    { name: 'Joelho ao peito', timing: 'Manhã', detail: '30s por lado, ainda no leito ou logo após levantar.' },
    { name: 'Postura da criança', timing: 'Manhã/noite', detail: '1-2 min com respiração diafragmática, sem forçar amplitude.' },
    { name: 'Gato-vaca', timing: 'Manhã', detail: '10-15 ciclos lentos, sincronizados com a respiração.' },
    { name: 'Ativação abdominal', timing: 'Manhã/noite', detail: '8-10s por repetição, sem prender a respiração.' },
    { name: 'Ponte pélvica', timing: 'Treino leve', detail: 'Subida controlada, glúteos ativos e coluna neutra.' },
    { name: 'Bird-dog', timing: 'Treino leve', detail: 'Movimento lento; a meta é não deixar a pelve girar.' },
];

const DEFAULT_HEALTH_REMINDERS: HealthTelegramReminder[] = [
    {
        id: 'spine_morning',
        title: 'Rotina lombar',
        message: 'André, hora da sua rotina lombar. Comece leve: mobilidade, respiração e sem pressa.',
        time: '05:00',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
        category: 'spine',
        telegramOnly: true,
    },
    {
        id: 'lunch_slow',
        title: 'Almoço com calma',
        message: 'André, lembre de comer devagar no almoço. Ritmo baixo também é estratégia.',
        time: '11:45',
        enabled: true,
        daysOfWeek: [1, 2, 3, 4, 5],
        category: 'nutrition',
        telegramOnly: true,
    },
    {
        id: 'food_window',
        title: 'Janela alimentar',
        message: 'André, última janela alimentar chegando. Se for comer, mantenha leve.',
        time: '17:30',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
        category: 'nutrition',
        telegramOnly: true,
    },
    {
        id: 'pain_checkin',
        title: 'Check-in lombar',
        message: 'André, check-in rápido: como ficou sua lombar hoje?',
        time: '21:30',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
        category: 'pain',
        telegramOnly: true,
    },
];

// --- COMPONENTS ---

const IndustrialHUDCard = ({ label, value, unit, trend, colorClass, icon }: { label: string, value: string | number, unit?: string, trend?: string, colorClass: string, icon?: React.ReactNode }) => (
    <div className="bg-surface border-r border-border-grid p-6 flex flex-col justify-center relative overflow-hidden group">
        <div className={`absolute top-0 left-0 w-full h-0.5 ${colorClass} opacity-20 group-hover:opacity-100 transition-opacity`}></div>
        <div className="absolute -right-2 -top-2 opacity-[0.03] group-hover:opacity-[0.07] transition-opacity">
            {icon || <svg className="w-24 h-24" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2z"/></svg>}
        </div>
        
        <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.3em] mb-2">// {label}</span>
        <div className="flex items-baseline gap-2 relative z-10">
            <span className="text-4xl font-mono font-bold text-on-surface tracking-tighter animate-in slide-in-from-left-4">
                {value}
            </span>
            {unit && <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">{unit}</span>}
        </div>
        {trend && (
            <div className="mt-2 flex items-center gap-1.5">
                <div className={`w-1.5 h-1.5 rounded-full ${trend.startsWith('+') ? 'bg-rose-500' : 'bg-emerald-500'} animate-pulse`}></div>
                <span className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest">{trend}</span>
            </div>
        )}
    </div>
);

const HealthSection = ({ title, children, iconColor, defaultExpanded = true, techNode = "SECTION_NODE" }: { title: string, children: React.ReactNode, iconColor: string, defaultExpanded?: boolean, techNode?: string }) => {
    const [isExpanded, setIsExpanded] = useState(defaultExpanded);

    return (
        <div className="bg-surface p-6 md:p-10 rounded-none border border-border-grid shadow-none relative overflow-hidden">
            <div className={`absolute top-0 left-0 w-1 h-full ${iconColor} opacity-50`}></div>
            
            <button onClick={() => setIsExpanded(!isExpanded)} className="w-full flex items-center justify-between group/btn">
                <div className="flex flex-col items-start gap-1">
                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.3em]">// {techNode}</span>
                    <h3 className="text-2xl font-mono font-bold text-on-surface tracking-tight text-left">{title}</h3>
                </div>
                <div className={`w-8 h-8 rounded-soft-touch border border-border-grid flex items-center justify-center transition-all ${isExpanded ? 'bg-on-surface text-surface' : 'bg-surface text-slate-300 hover:text-on-surface'}`}>
                    <svg className={`w-4 h-4 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                    </svg>
                </div>
            </button>
            
            {isExpanded && (
                <div className="mt-10 animate-in fade-in slide-in-from-top-4 duration-500">
                    {children}
                </div>
            )}
        </div>
    );
};

const NumberEntryCard = ({
    label,
    value,
    unit,
    placeholder,
    colorClass,
    onCommit,
}: {
    label: string;
    value: string | number;
    unit: string;
    placeholder: string;
    colorClass: string;
    onCommit: (value: number) => void;
}) => (
    <div className="bg-slate-50 p-6 border border-border-grid flex flex-col gap-4">
        <div>
            <span className={`text-[9px] font-mono font-bold uppercase tracking-widest ${colorClass}`}>// {label}</span>
            <div className="text-3xl font-mono font-bold mt-1">{value}<span className="text-xs text-slate-400 ml-2">{unit}</span></div>
        </div>
        <input
            type="number"
            className="bg-white border border-border-grid px-4 py-2 text-xs font-mono font-bold w-full outline-none focus:ring-1 focus:ring-sky-500"
            placeholder={placeholder}
            onKeyDown={e => {
                if (e.key === 'Enter') {
                    const val = parseInt((e.target as HTMLInputElement).value);
                    if (Number.isFinite(val)) onCommit(val);
                    (e.target as HTMLInputElement).value = '';
                }
            }}
        />
    </div>
);

// --- MAIN COMPONENT ---

const HealthView: React.FC<HealthViewProps> = ({
    weights, dailyHabits, settings, onUpdateSettings, onAddWeight, onDeleteWeight, 
    onUpdateHabits, exerciseLogs, exerciseSettings, onSaveExerciseLog, exams, 
    telegramReminders, onSaveTelegramReminder, onDeleteTelegramReminder,
    onAddExam, onDeleteExam, onUpdateExam, isDark = false
}) => {
    const [selectedDate, setSelectedDate] = useState<string>(formatDateLocalISO(new Date()));
    const [activeTab, setActiveTab] = useState<'telemetry' | 'archive'>('telemetry');

    // Mappings & Memoized Data
    const todayStr = formatDateLocalISO(new Date());
    const sortedWeights = useMemo(() => [...weights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()), [weights]);
    const currentWeight = sortedWeights[0]?.weight || 0;
    const previousWeight = sortedWeights[1]?.weight || currentWeight;
    const weightDelta = currentWeight - previousWeight;
    
    const todayLog = useMemo(() => exerciseLogs.find(l => l.id === selectedDate) || { id: selectedDate }, [exerciseLogs, selectedDate]);
    const walkingMinimum = settings.walkingMinimumMinutes ?? 45;
    const walkingIdeal = settings.walkingIdealMinutes ?? 100;
    const walkingMinutes = todayLog.walk?.done ?? todayLog.activeMinutes ?? 0;
    const walkingProgress = Math.min(100, Math.round((walkingMinutes / walkingIdeal) * 100));
    const activeReminders = useMemo(() => {
        const byId = new Map(telegramReminders.map(reminder => [reminder.id, reminder]));
        DEFAULT_HEALTH_REMINDERS.forEach(reminder => {
            if (!byId.has(reminder.id)) byId.set(reminder.id, reminder);
        });
        return [...byId.values()].sort((a, b) => a.time.localeCompare(b.time));
    }, [telegramReminders]);
    const currentHabits = useMemo(() => (dailyHabits.find(h => h.id === selectedDate) || { 
        id: selectedDate,
        noSugar: false,
        noAlcohol: false,
        noSnacks: false,
        workout: false,
        eatUntil18: false,
        eatSlowly: false
    }) as DailyHabits, [dailyHabits, selectedDate]);


    return (
        <div className={`health-view min-h-screen bg-surface ${isDark ? 'health-view-dark' : ''} pb-20`}>
            
            {/* 1. HUD: REAL-TIME TELEMETRY READOUT */}
            <div className="grid grid-cols-1 md:grid-cols-4 border-b border-border-grid">
                <IndustrialHUDCard 
                    label="CURRENT_MASS" 
                    value={currentWeight ? currentWeight.toFixed(1) : '--.-'} 
                    unit="KG" 
                    trend={weightDelta !== 0 ? `${weightDelta > 0 ? '+' : ''}${weightDelta.toFixed(1)} KG` : 'STABLE'}
                    colorClass="bg-primary-tactile"
                    icon={<svg className="w-24 h-24 text-primary-tactile" fill="currentColor" viewBox="0 0 24 24"><path d="M20.57 14.86L22 13.43 20.57 12 17 15.57 8.43 7 12 3.43 10.57 2 9.14 3.43 7.72 2 5.58 4.14 4.14 2.71 2.71 4.14 4.14 5.58 2 7.72 3.43 9.14 2 10.57 3.43 12 7 8.43 15.57 17 12 20.57 13.43 22 14.86 20.57 16.29 22 18.43 19.86 19.86 22 22 19.86 20.57 18.43 22 16.29 20.57 14.86z"/></svg>}
                />
                <IndustrialHUDCard 
                    label="DAILY_STEPS" 
                    value={todayLog.walk?.steps?.toLocaleString() || '0'} 
                    unit="STEPS" 
                    trend={`${todayLog.walk?.distance?.toFixed(1) || '0.0'} KM`}
                    colorClass="bg-sky-500"
                    icon={<svg className="w-24 h-24 text-sky-500" fill="currentColor" viewBox="0 0 24 24"><path d="M13.5 5.5c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zM9.8 8.9L7 23h2.1l1.8-8 2.1 2v6h2V15.5L13 13.5l.5-2.5c1.1 1.2 2.4 2 4 2v-2c-1.2 0-2.3-.7-3-1.6l-1-1.6c-.4-.7-1.1-1.1-1.9-1.1-.3 0-.6.1-.9.2L6 10.5V15h2v-4.1l1.8-.7z"/></svg>}
                />
                <IndustrialHUDCard 
                    label="CALORIC_OUTPUT" 
                    value={todayLog.calories || '0'} 
                    unit="KCAL" 
                    trend="ACTIVE_BURN"
                    colorClass="bg-rose-500"
                    icon={<svg className="w-24 h-24 text-rose-500" fill="currentColor" viewBox="0 0 24 24"><path d="M13.5 .67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73l.03-.36C5.21 7.51 4 10.62 4 14c0 4.42 3.58 8 8 8s8-3.58 8-8c0-6.03-4.54-12.33-4.54-13.33z"/></svg>}
                />
                <IndustrialHUDCard 
                    label="SLEEP_INTEGRITY" 
                    value={todayLog.sleep ? (todayLog.sleep.totalMinutes / 60).toFixed(1) : '--.-'} 
                    unit="HOURS" 
                    trend={todayLog.sleep ? 'REST_COMPLETE' : 'NO_DATA'}
                    colorClass="bg-violet-500"
                    icon={<svg className="w-24 h-24 text-violet-500" fill="currentColor" viewBox="0 0 24 24"><path d="M10 7c-3.87 0-7 3.13-7 7s3.13 7 7 7 7-3.13 7-7h-2c0 2.76-2.24 5-5 5s-5-2.24-5-5 2.24-5 5-5V7zM21.78 4.01L19 6.79l-.79-.78 2.78-2.78c.2-.2.51-.2.71 0l.08.08c.2.2.2.51 0 .7zM3 3.5v2h2v-2H3zm4 0v2h2v-2H7zm8 0v2h2v-2h-2z"/></svg>}
                />
            </div>

            {/* 2. NAVIGATION STRIP */}
            <div className="bg-slate-50 border-b border-border-grid px-6 py-3 flex items-center justify-between">
                <div className="flex gap-4">
                    {['telemetry', 'archive'].map(tab => (
                        <button 
                            key={tab}
                            onClick={() => setActiveTab(tab as any)}
                            className={`text-[10px] font-mono font-bold uppercase tracking-[0.2em] px-4 py-2 transition-all ${activeTab === tab ? 'bg-on-surface text-surface' : 'text-slate-400 hover:text-on-surface'}`}
                        >
                            {tab}_NODE
                        </button>
                    ))}
                </div>
                <div className="flex items-center gap-4">
                    <input 
                        type="date" 
                        value={selectedDate} 
                        onChange={e => setSelectedDate(e.target.value)}
                        className="bg-transparent border border-border-grid px-3 py-1.5 text-[10px] font-mono font-bold text-on-surface outline-none"
                    />
                </div>
            </div>

            {/* 3. MAIN GRID CONTENT */}
            <div className="p-6 md:p-10">
                {/* HEALTH SUMMARY AI CARD */}
                <div className="mb-8">
                    <HealthSummaryCard
                        weights={weights}
                        dailyHabits={dailyHabits}
                        exerciseLogs={exerciseLogs}
                        settings={settings}
                    />
                </div>
                {activeTab === 'telemetry' ? (
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
                        
                        {/* LEFT COLUMN: CORE PROTOCOLS & HABITS */}
                        <div className="lg:col-span-1 space-y-10">
                            <HealthSection title="Habit_Integrity" techNode="BEHAVIORAL_LOG" iconColor="bg-accent-tactile">
                                <div className="grid grid-cols-1 gap-3">
                                    {[
                                        { key: 'noSugar', label: 'ZERO_SUGAR', icon: '🧁' },
                                        { key: 'noAlcohol', label: 'ZERO_ALCOHOL', icon: '🍷' },
                                        { key: 'noSnacks', label: 'ZERO_SNACKS', icon: '🍟' },
                                        { key: 'workout', label: 'WORKOUT_COMPLETED', icon: '🏋️' },
                                        { key: 'eatUntil18', label: 'FASTING_POST_18H', icon: '⏰' },
                                        { key: 'eatSlowly', label: 'MINDFUL_EATING', icon: '🧘' }
                                    ].map((habit) => (
                                        <button
                                            key={habit.key}
                                            onClick={() => onUpdateHabits(selectedDate, { [habit.key]: !currentHabits[habit.key as keyof DailyHabits] })}
                                            className={`p-4 border transition-all flex items-center justify-between group ${currentHabits[habit.key as keyof DailyHabits] ? 'bg-accent-tactile border-accent-tactile text-white' : 'bg-surface border-border-grid text-on-surface hover:border-accent-tactile'}`}
                                        >
                                            <div className="flex items-center gap-4">
                                                <span className="text-xl">{habit.icon}</span>
                                                <span className="text-[10px] font-mono font-bold uppercase tracking-[0.2em]">{habit.label}</span>
                                            </div>
                                            <div className={`w-4 h-4 border-2 flex items-center justify-center ${currentHabits[habit.key as keyof DailyHabits] ? 'bg-white border-white' : 'border-slate-200'}`}>
                                                {currentHabits[habit.key as keyof DailyHabits] && <svg className="w-3 h-3 text-accent-tactile" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" /></svg>}
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            </HealthSection>

                            <HealthSection title="Biometric_Consistency" techNode="MONTHLY_HEATMAP" iconColor="bg-primary-tactile">
                                <div className="grid grid-cols-7 gap-1">
                                    {/* Simplified Heatmap Logic */}
                                    {Array.from({ length: 31 }).map((_, i) => (
                                        <div key={i} className="aspect-square bg-slate-50 border border-border-grid flex items-center justify-center text-[8px] font-mono font-bold text-slate-300">
                                            {String(i + 1).padStart(2, '0')}
                                        </div>
                                    ))}
                                </div>
                            </HealthSection>

                            <HealthSection title="Spine_Routine" techNode="LOMBAR_GUIDE" iconColor="bg-violet-500" defaultExpanded={false}>
                                <div className="space-y-3">
                                    {SPINE_ROUTINE.map(item => (
                                        <div key={item.name} className="border border-border-grid bg-slate-50 p-4">
                                            <div className="flex items-center justify-between gap-3">
                                                <span className="text-xs font-mono font-bold text-on-surface uppercase">{item.name}</span>
                                                <span className="text-[9px] font-mono font-bold text-violet-600 uppercase tracking-widest">{item.timing}</span>
                                            </div>
                                            <p className="mt-2 text-xs leading-relaxed text-slate-500">{item.detail}</p>
                                        </div>
                                    ))}
                                    <p className="text-[10px] leading-relaxed text-slate-400 font-mono">
                                        Guia informativo: faça sem dor aguda, sem prender a respiração e interrompa se houver irradiação, choque ou piora clara.
                                    </p>
                                </div>
                            </HealthSection>

                            <HealthSection title="Telegram_Reminders" techNode="HEALTH_PROMPTS" iconColor="bg-emerald-500" defaultExpanded={false}>
                                <div className="space-y-3">
                                    {activeReminders.map(reminder => (
                                        <div key={reminder.id} className="border border-border-grid bg-slate-50 p-4 flex items-start gap-3">
                                            <input
                                                type="checkbox"
                                                checked={reminder.enabled}
                                                onChange={e => onSaveTelegramReminder({ ...reminder, enabled: e.target.checked })}
                                                className="mt-1"
                                            />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center justify-between gap-3">
                                                    <input
                                                        value={reminder.title}
                                                        onChange={e => onSaveTelegramReminder({ ...reminder, title: e.target.value })}
                                                        className="bg-transparent text-xs font-mono font-bold uppercase text-on-surface outline-none w-full"
                                                    />
                                                    <input
                                                        type="time"
                                                        value={reminder.time}
                                                        onChange={e => onSaveTelegramReminder({ ...reminder, time: e.target.value })}
                                                        className="bg-white border border-border-grid px-2 py-1 text-[10px] font-mono font-bold"
                                                    />
                                                </div>
                                                <textarea
                                                    value={reminder.message}
                                                    onChange={e => onSaveTelegramReminder({ ...reminder, message: e.target.value })}
                                                    className="mt-2 w-full bg-white border border-border-grid p-2 text-xs text-slate-600 outline-none min-h-[58px]"
                                                />
                                                <div className="mt-2 flex items-center justify-between">
                                                    <span className="text-[9px] font-mono font-bold uppercase text-slate-400">Telegram only</span>
                                                    {!DEFAULT_HEALTH_REMINDERS.some(item => item.id === reminder.id) && (
                                                        <button onClick={() => onDeleteTelegramReminder(reminder.id)} className="text-[9px] font-mono font-bold uppercase text-rose-500">remover</button>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                    <button
                                        onClick={() => onSaveTelegramReminder({
                                            id: `custom_${Date.now()}`,
                                            title: 'Novo lembrete',
                                            message: 'André, lembrete de saúde configurado no Hermes.',
                                            time: '08:00',
                                            enabled: true,
                                            daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
                                            category: 'custom',
                                            telegramOnly: true,
                                        })}
                                        className="w-full border border-dashed border-border-grid p-3 text-[10px] font-mono font-bold uppercase tracking-widest text-slate-500 hover:text-on-surface hover:border-on-surface transition-colors"
                                    >
                                        Adicionar lembrete Telegram
                                    </button>
                                </div>
                            </HealthSection>
                        </div>

                        {/* CENTER COLUMN: TRAINING & TELEMETRY CHARTS */}
                        <div className="lg:col-span-2 space-y-10">
                            <HealthSection title="Walking_Core" techNode="PRIMARY_METRIC" iconColor="bg-sky-500">
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                    <div className="md:col-span-2 bg-slate-50 border border-border-grid p-6">
                                        <div className="flex items-end justify-between gap-4 mb-4">
                                            <div>
                                                <span className="text-[9px] font-mono font-bold text-sky-600 uppercase tracking-widest">// WALKING_MINUTES</span>
                                                <div className="text-5xl font-mono font-bold mt-1">{walkingMinutes}<span className="text-xs text-slate-400 ml-2">/ {walkingIdeal} MIN</span></div>
                                            </div>
                                            <span className="text-[10px] font-mono font-bold uppercase text-slate-400">{todayLog.walk?.steps?.toLocaleString() || 0} passos</span>
                                        </div>
                                        <div className="h-3 bg-white border border-border-grid overflow-hidden">
                                            <div className="h-full bg-sky-500 transition-all" style={{ width: `${walkingProgress}%` }} />
                                        </div>
                                        <div className="mt-3 flex items-center justify-between text-[10px] font-mono font-bold uppercase text-slate-400">
                                            <span>Mínimo: {walkingMinimum} min</span>
                                            <span>Ideal: {walkingIdeal} min</span>
                                            <span>{todayLog.walk?.distance?.toFixed(1) || '0.0'} km</span>
                                        </div>
                                    </div>
                                    <div className="bg-slate-50 border border-border-grid p-6 space-y-3">
                                        <label className="block">
                                            <span className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest">mínimo</span>
                                            <input type="number" value={walkingMinimum} onChange={e => onUpdateSettings({ ...settings, walkingMinimumMinutes: parseInt(e.target.value) || 0 })} className="mt-1 w-full bg-white border border-border-grid px-3 py-2 text-xs font-mono font-bold" />
                                        </label>
                                        <label className="block">
                                            <span className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest">ideal</span>
                                            <input type="number" value={walkingIdeal} onChange={e => onUpdateSettings({ ...settings, walkingIdealMinutes: parseInt(e.target.value) || 0 })} className="mt-1 w-full bg-white border border-border-grid px-3 py-2 text-xs font-mono font-bold" />
                                        </label>
                                    </div>
                                </div>
                            </HealthSection>

                            <HealthSection title="Pain_Checkin" techNode="LOMBAR_SIGNAL" iconColor="bg-orange-500">
                                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                    <label className="bg-slate-50 border border-border-grid p-4">
                                        <span className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest">manhã</span>
                                        <input type="number" min="0" max="10" value={todayLog.pain?.morning ?? ''} onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, morning: parseInt(e.target.value) || 0 } })} className="mt-2 w-full bg-white border border-border-grid px-3 py-2 text-xs font-mono font-bold" />
                                    </label>
                                    <label className="bg-slate-50 border border-border-grid p-4">
                                        <span className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest">noite</span>
                                        <input type="number" min="0" max="10" value={todayLog.pain?.evening ?? ''} onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, evening: parseInt(e.target.value) || 0 } })} className="mt-2 w-full bg-white border border-border-grid px-3 py-2 text-xs font-mono font-bold" />
                                    </label>
                                    <button onClick={() => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, sciatica: !todayLog.pain?.sciatica } })} className={`border border-border-grid p-4 text-left ${todayLog.pain?.sciatica ? 'bg-orange-500 text-white' : 'bg-slate-50 text-on-surface'}`}>
                                        <span className="text-[9px] font-mono font-bold uppercase tracking-widest">ciática</span>
                                        <div className="text-xs font-mono font-bold mt-2">{todayLog.pain?.sciatica ? 'SIM' : 'NÃO'}</div>
                                    </button>
                                    <button onClick={() => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, crisis: !todayLog.pain?.crisis } })} className={`border border-border-grid p-4 text-left ${todayLog.pain?.crisis ? 'bg-rose-500 text-white' : 'bg-slate-50 text-on-surface'}`}>
                                        <span className="text-[9px] font-mono font-bold uppercase tracking-widest">crise</span>
                                        <div className="text-xs font-mono font-bold mt-2">{todayLog.pain?.crisis ? 'SIM' : 'NÃO'}</div>
                                    </button>
                                </div>
                                <textarea
                                    value={todayLog.pain?.notes || ''}
                                    onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, notes: e.target.value } })}
                                    placeholder="NOTA_CURTA_OPCIONAL"
                                    className="mt-4 w-full bg-slate-50 border border-border-grid p-3 text-xs text-slate-600 outline-none min-h-[72px]"
                                />
                            </HealthSection>
                            
                            {/* TRAINING GROUNDS */}
                            <HealthSection title="Training_Grounds" techNode="PHYSICAL_OUTPUT" iconColor="bg-rose-500">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    {/* Pushups Control */}
                                    <div className="bg-slate-50 p-6 border border-border-grid flex flex-col gap-4">
                                        <div className="flex justify-between items-start">
                                            <div>
                                                <span className="text-[9px] font-mono font-bold text-emerald-600 uppercase tracking-widest">// PUSHUPS</span>
                                                <div className="text-3xl font-mono font-bold mt-1">{todayLog.pushups?.done || 0}<span className="text-xs text-slate-400 ml-2">/ {exerciseSettings.pushups?.activeGoal || '--'}</span></div>
                                            </div>
                                        </div>
                                        <div className="flex gap-2">
                                            <input 
                                                type="number" 
                                                className="bg-white border border-border-grid px-4 py-2 text-xs font-mono font-bold w-full outline-none focus:ring-1 focus:ring-emerald-500" 
                                                placeholder="SET_COUNT"
                                                onKeyDown={e => {
                                                    if (e.key === 'Enter') {
                                                        const val = parseInt((e.target as HTMLInputElement).value);
                                                        onSaveExerciseLog(selectedDate, { pushups: { done: val, goal: exerciseSettings.pushups?.activeGoal || val } });
                                                        (e.target as HTMLInputElement).value = '';
                                                    }
                                                }}
                                            />
                                        </div>
                                    </div>

                                    {/* Pullups Control */}
                                    <div className="bg-slate-50 p-6 border border-border-grid flex flex-col gap-4">
                                        <div className="flex justify-between items-start">
                                            <div>
                                                <span className="text-[9px] font-mono font-bold text-violet-600 uppercase tracking-widest">// PULLUPS</span>
                                                <div className="text-3xl font-mono font-bold mt-1">{todayLog.pullups?.done || 0}<span className="text-xs text-slate-400 ml-2">/ {exerciseSettings.pullups?.activeGoal || '--'}</span></div>
                                            </div>
                                        </div>
                                        <div className="flex gap-2">
                                            <input 
                                                type="number" 
                                                className="bg-white border border-border-grid px-4 py-2 text-xs font-mono font-bold w-full outline-none focus:ring-1 focus:ring-violet-500" 
                                                placeholder="SET_COUNT"
                                                onKeyDown={e => {
                                                    if (e.key === 'Enter') {
                                                        const val = parseInt((e.target as HTMLInputElement).value);
                                                        onSaveExerciseLog(selectedDate, { pullups: { done: val, goal: exerciseSettings.pullups?.activeGoal || val, phase: exerciseSettings.pullups?.phase || 'dead_hang' } });
                                                        (e.target as HTMLInputElement).value = '';
                                                    }
                                                }}
                                            />
                                        </div>
                                    </div>

                                    <NumberEntryCard
                                        label="PLANK"
                                        value={todayLog.plank?.seconds || 0}
                                        unit="SEC"
                                        placeholder="SECONDS"
                                        colorClass="text-sky-600"
                                        onCommit={val => onSaveExerciseLog(selectedDate, { plank: { seconds: val } })}
                                    />
                                    <NumberEntryCard
                                        label="BRIDGE"
                                        value={todayLog.bridge?.reps || 0}
                                        unit="REPS"
                                        placeholder="REPS"
                                        colorClass="text-emerald-600"
                                        onCommit={val => onSaveExerciseLog(selectedDate, { bridge: { reps: val } })}
                                    />
                                    <NumberEntryCard
                                        label="BIRD_DOG"
                                        value={todayLog.birdDog?.reps || 0}
                                        unit="REPS"
                                        placeholder="REPS"
                                        colorClass="text-violet-600"
                                        onCommit={val => onSaveExerciseLog(selectedDate, { birdDog: { reps: val } })}
                                    />
                                    <NumberEntryCard
                                        label="SQUATS"
                                        value={todayLog.squats?.reps || 0}
                                        unit="REPS"
                                        placeholder="REPS"
                                        colorClass="text-orange-600"
                                        onCommit={val => onSaveExerciseLog(selectedDate, { squats: { reps: val } })}
                                    />
                                </div>
                            </HealthSection>

                            {/* MASS TELEMETRY CHART */}
                            <HealthSection title="Biometric_Telemetries" techNode="WEIGHT_TREND_ANALYSIS" iconColor="bg-sky-500">
                                <div className="h-[300px] w-full bg-slate-50 border border-border-grid border-dashed relative overflow-hidden flex items-center justify-center">
                                    <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: 'radial-gradient(#000 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>
                                    
                                    {weights.length > 1 ? (
                                        <div className="w-full h-full p-10 flex items-end gap-1">
                                            {/* Simplified Bar Chart for Trend */}
                                            {weights.slice(0, 20).reverse().map((w, i) => {
                                                const h = Math.min(100, Math.max(10, ((w.weight - 60) / 40) * 100));
                                                return (
                                                    <div key={i} className="flex-1 bg-primary-tactile opacity-60 hover:opacity-100 transition-opacity relative group" style={{ height: `${h}%` }}>
                                                        <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-on-surface text-surface text-[8px] font-mono font-bold px-1.5 py-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                                            {w.weight.toFixed(1)}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    ) : (
                                        <span className="text-[10px] font-mono font-bold text-slate-300 uppercase tracking-widest italic">INSUFFICIENT_TELEMETRY_DATA</span>
                                    )}
                                </div>
                            </HealthSection>
                        </div>

                    </div>
                ) : (
                    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <HealthSection title="Medical_Archive" techNode="RECORDS_VAULT" iconColor="bg-slate-400">
                             <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {exams.map(exam => (
                                    <div key={exam.id} className="bg-surface border border-border-grid p-6 hover:border-primary-tactile transition-all group">
                                        <div className="flex justify-between items-start mb-4">
                                            <span className="text-[8px] font-mono font-bold uppercase px-2 py-0.5 border border-border-grid">{exam.tipo}</span>
                                            <span className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest">{formatDate(exam.data)}</span>
                                        </div>
                                        <h4 className="text-lg font-mono font-bold text-on-surface mb-2">{exam.titulo}</h4>
                                        <p className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest mb-4">LOC: {exam.doutor_local || 'N/A'}</p>
                                        
                                        {exam.pool_dados && exam.pool_dados.length > 0 && (
                                            <div className="flex gap-2">
                                                {exam.pool_dados.map(file => (
                                                    <a key={file.id} href={file.valor} target="_blank" rel="noreferrer" className="p-2 border border-border-grid hover:bg-on-surface hover:text-white transition-all">
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
                                                    </a>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ))}
                             </div>
                        </HealthSection>
                    </div>
                )}
            </div>
        </div>
    );
};

export default HealthView;
