import React, { useMemo, useState } from 'react';
import {
    HealthWeight, DailyHabits, HealthSettings, ExerciseLog,
    ExerciseSettings, formatDate, formatDateLocalISO,
    HealthExam, HealthTelegramReminder
} from './types';
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

type IconName = 'scale' | 'steps' | 'flame' | 'moon' | 'chevron' | 'heart' | 'calendar' | 'file' | 'plus';
type NumericTrendPoint = { id: string; label: string; value: number; marker?: boolean };
type PainTrendPoint = { id: string; label: string; morning?: number; evening?: number; crisis?: boolean };

const DEFAULT_HEALTH_REMINDERS: HealthTelegramReminder[] = [
    {
        id: 'lunch_slow',
        title: 'Almoco com calma',
        message: 'Andre, lembre de comer devagar no almoco. Ritmo baixo tambem e estrategia.',
        time: '11:45',
        enabled: true,
        daysOfWeek: [1, 2, 3, 4, 5],
        category: 'nutrition',
        telegramOnly: true,
    },
    {
        id: 'food_window',
        title: 'Janela alimentar',
        message: 'Andre, ultima janela alimentar chegando. Se for comer, mantenha leve.',
        time: '17:30',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
        category: 'nutrition',
        telegramOnly: true,
    },
    {
        id: 'pain_checkin',
        title: 'Check-in lombar',
        message: 'Andre, check-in rapido: como ficou sua lombar hoje?',
        time: '21:30',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
        category: 'pain',
        telegramOnly: true,
    },
];

const Icon = ({ name, className = 'h-4 w-4' }: { name: IconName; className?: string }) => {
    const common = { className, fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' };
    switch (name) {
        case 'scale':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 19h12M7 19l1.5-9h7L17 19M9 10a3 3 0 116 0M12 10v3" /></svg>;
        case 'steps':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 20c1.8 0 3-1.2 3-3v-1.5H8.5A2.5 2.5 0 006 18c0 1.2.8 2 2 2zM16 4c-1.8 0-3 1.2-3 3v1.5h2.5A2.5 2.5 0 0018 6c0-1.2-.8-2-2-2zM11 15.5V12m2-3.5V12" /></svg>;
        case 'flame':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 22a7 7 0 007-7c0-4.5-3.5-8-5.1-12-.9 2.8-2.8 4.3-5 6.2A7.3 7.3 0 005 15a7 7 0 007 7z" /></svg>;
        case 'moon':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 13.2A8 8 0 1110.8 3a6.5 6.5 0 0010.2 10.2z" /></svg>;
        case 'chevron':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 9l6 6 6-6" /></svg>;
        case 'heart':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20.8 4.6a5.3 5.3 0 00-7.5 0L12 5.9l-1.3-1.3a5.3 5.3 0 00-7.5 7.5L12 21l8.8-8.9a5.3 5.3 0 000-7.5z" /></svg>;
        case 'calendar':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 3v4m8-4v4M4 9h16M6 5h12a2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V7a2 2 0 012-2z" /></svg>;
        case 'file':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 3v5h5" /></svg>;
        case 'plus':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 5v14M5 12h14" /></svg>;
        default:
            return null;
    }
};

const metricCardClasses = 'rounded-2xl border border-border-subtle bg-white p-5 shadow-card';
const subtlePanelClasses = 'rounded-2xl border border-border-subtle bg-white p-5 shadow-card';
const inputClasses = 'mt-1 w-full rounded-lg border border-border-standard bg-background px-3 py-2 text-sm font-medium text-on-surface outline-none transition focus:border-primary-container focus:ring-1 focus:ring-primary-container';
const labelClasses = 'text-[10px] font-semibold uppercase tracking-[0.05em] text-on-surface-variant';

const formatShortDate = (value: string) => {
    const [, month, day] = value.split('-');
    return day && month ? `${day}/${month}` : value;
};

const MetricCard = ({
    label,
    value,
    unit,
    helper,
    icon,
    tone = 'text-primary-container',
}: {
    label: string;
    value: string | number;
    unit?: string;
    helper?: string;
    icon: IconName;
    tone?: string;
}) => (
    <div className={metricCardClasses}>
        <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
                <p className={labelClasses}>{label}</p>
                <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-3xl font-bold leading-none text-on-surface">{value}</span>
                    {unit && <span className="text-xs font-semibold uppercase text-on-surface-variant">{unit}</span>}
                </div>
            </div>
            <div className={`flex h-10 w-10 items-center justify-center rounded-xl bg-surface-container-low ${tone}`}>
                <Icon name={icon} className="h-5 w-5" />
            </div>
        </div>
        {helper && <p className="mt-3 text-xs font-medium leading-relaxed text-on-surface-variant">{helper}</p>}
    </div>
);

const HealthSection = ({
    title,
    eyebrow,
    children,
    defaultExpanded = true,
}: {
    title: string;
    eyebrow: string;
    children: React.ReactNode;
    defaultExpanded?: boolean;
}) => {
    const [isExpanded, setIsExpanded] = useState(defaultExpanded);

    return (
        <section className={subtlePanelClasses}>
            <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="flex w-full items-center justify-between gap-4 text-left"
            >
                <div>
                    <p className={labelClasses}>{eyebrow}</p>
                    <h3 className="mt-1 text-lg font-bold tracking-tight text-on-surface">{title}</h3>
                </div>
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border-standard bg-background text-on-surface-variant transition ${isExpanded ? 'rotate-180' : ''}`}>
                    <Icon name="chevron" className="h-4 w-4" />
                </span>
            </button>
            {isExpanded && (
                <div className="mt-5">
                    {children}
                </div>
            )}
        </section>
    );
};

const WeightTrendChart = ({
    points,
    targetWeight,
}: {
    points: NumericTrendPoint[];
    targetWeight?: number;
}) => {
    if (points.length < 2) {
        return (
            <div className="flex h-[280px] items-center justify-center rounded-2xl border border-dashed border-border-standard bg-background text-sm font-semibold text-on-surface-variant">
                Ainda nao ha registros suficientes para tendencia.
            </div>
        );
    }

    const width = 720;
    const height = 260;
    const pad = { top: 26, right: 18, bottom: 42, left: 46 };
    const values = [...points.map(point => point.value), ...(targetWeight ? [targetWeight] : [])];
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const min = Math.floor(rawMin - 1);
    const max = Math.ceil(rawMax + 1);
    const range = Math.max(1, max - min);
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const xFor = (index: number) => pad.left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
    const yFor = (value: number) => pad.top + ((max - value) / range) * plotHeight;
    const path = points.map((point, index) => `${xFor(index)},${yFor(point.value)}`).join(' ');
    const targetY = targetWeight ? yFor(targetWeight) : null;
    const yTicks = [max, Math.round((max + min) / 2), min];

    return (
        <div className="rounded-2xl border border-border-subtle bg-background p-4">
            <svg viewBox={`0 0 ${width} ${height}`} className="h-[280px] w-full overflow-visible" role="img" aria-label="Grafico de tendencia de peso">
                <rect x="0" y="0" width={width} height={height} rx="16" fill="#f8fafc" />
                {yTicks.map(tick => (
                    <g key={tick}>
                        <line x1={pad.left} x2={width - pad.right} y1={yFor(tick)} y2={yFor(tick)} stroke="#d8dee8" strokeWidth="1" />
                        <text x={pad.left - 10} y={yFor(tick) + 4} textAnchor="end" fontSize="12" fontWeight="600" fill="#4d4354">{tick} kg</text>
                    </g>
                ))}
                {targetY !== null && (
                    <g>
                        <line x1={pad.left} x2={width - pad.right} y1={targetY} y2={targetY} stroke="#10b981" strokeWidth="2" strokeDasharray="6 6" />
                        <text x={width - pad.right} y={targetY - 8} textAnchor="end" fontSize="12" fontWeight="700" fill="#047857">meta</text>
                    </g>
                )}
                <polyline points={path} fill="none" stroke="#2563eb" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
                {points.map((point, index) => (
                    <g key={point.id}>
                        <circle cx={xFor(index)} cy={yFor(point.value)} r="6" fill="#ffffff" stroke="#2563eb" strokeWidth="3" />
                        <title>{`${point.label}: ${point.value.toFixed(1)} kg`}</title>
                    </g>
                ))}
                {points.map((point, index) => (
                    index === 0 || index === points.length - 1 || index % Math.ceil(points.length / 5) === 0 ? (
                        <text key={`label-${point.id}`} x={xFor(index)} y={height - 16} textAnchor="middle" fontSize="11" fontWeight="700" fill="#4d4354">{point.label}</text>
                    ) : null
                ))}
            </svg>
        </div>
    );
};

const PainTrendChart = ({ points }: { points: PainTrendPoint[] }) => {
    const visiblePoints = points.filter(point => point.morning !== undefined || point.evening !== undefined);
    if (visiblePoints.length < 2) {
        return (
            <div className="flex h-[240px] items-center justify-center rounded-2xl border border-dashed border-border-standard bg-background text-sm font-semibold text-on-surface-variant">
                Ainda nao ha historico suficiente de dor para montar o grafico.
            </div>
        );
    }

    const width = 720;
    const height = 240;
    const pad = { top: 24, right: 18, bottom: 42, left: 38 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const xFor = (index: number) => pad.left + (index / (visiblePoints.length - 1)) * plotWidth;
    const yFor = (value: number) => pad.top + ((10 - value) / 10) * plotHeight;
    const lineFor = (key: 'morning' | 'evening') =>
        visiblePoints
            .map((point, index) => point[key] !== undefined ? `${xFor(index)},${yFor(point[key]!)}` : '')
            .filter(Boolean)
            .join(' ');

    return (
        <div className="rounded-2xl border border-border-subtle bg-background p-4">
            <div className="mb-3 flex flex-wrap items-center gap-4 text-xs font-semibold text-on-surface-variant">
                <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-amber-500" />Manha</span>
                <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-rose-600" />Noite / Telegram</span>
                <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-on-surface" />Crise</span>
            </div>
            <svg viewBox={`0 0 ${width} ${height}`} className="h-[240px] w-full overflow-visible" role="img" aria-label="Grafico de dor lombar">
                <rect x="0" y="0" width={width} height={height} rx="16" fill="#f8fafc" />
                {[10, 7, 5, 3, 0].map(tick => (
                    <g key={tick}>
                        <line x1={pad.left} x2={width - pad.right} y1={yFor(tick)} y2={yFor(tick)} stroke="#d8dee8" strokeWidth="1" />
                        <text x={pad.left - 10} y={yFor(tick) + 4} textAnchor="end" fontSize="12" fontWeight="700" fill="#4d4354">{tick}</text>
                    </g>
                ))}
                {lineFor('morning') && <polyline points={lineFor('morning')} fill="none" stroke="#f59e0b" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />}
                {lineFor('evening') && <polyline points={lineFor('evening')} fill="none" stroke="#e11d48" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />}
                {visiblePoints.map((point, index) => (
                    <g key={point.id}>
                        {point.morning !== undefined && <circle cx={xFor(index)} cy={yFor(point.morning)} r="5" fill="#ffffff" stroke="#f59e0b" strokeWidth="3" />}
                        {point.evening !== undefined && <circle cx={xFor(index)} cy={yFor(point.evening)} r="6" fill="#ffffff" stroke="#e11d48" strokeWidth="3" />}
                        {point.crisis && <circle cx={xFor(index)} cy={yFor(Math.max(point.morning ?? 0, point.evening ?? 0, 1))} r="9" fill="none" stroke="#151c27" strokeWidth="2" strokeDasharray="3 3" />}
                        <title>{`${point.label}: manha ${point.morning ?? '-'}, noite ${point.evening ?? '-'}${point.crisis ? ', crise' : ''}`}</title>
                    </g>
                ))}
                {visiblePoints.map((point, index) => (
                    index === 0 || index === visiblePoints.length - 1 || index % Math.ceil(visiblePoints.length / 5) === 0 ? (
                        <text key={`label-${point.id}`} x={xFor(index)} y={height - 16} textAnchor="middle" fontSize="11" fontWeight="700" fill="#4d4354">{point.label}</text>
                    ) : null
                ))}
            </svg>
        </div>
    );
};

const HealthView: React.FC<HealthViewProps> = ({
    weights, settings, onUpdateSettings,
    exerciseLogs, onSaveExerciseLog, exams,
    telegramReminders, onSaveTelegramReminder, onDeleteTelegramReminder,
    isDark = false
}) => {
    const [selectedDate, setSelectedDate] = useState<string>(formatDateLocalISO(new Date()));
    const [activeTab, setActiveTab] = useState<'telemetry' | 'archive'>('telemetry');

    const sortedWeights = useMemo(() => [...weights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()), [weights]);
    const currentWeight = sortedWeights[0]?.weight || 0;
    const previousWeight = sortedWeights[1]?.weight || currentWeight;
    const weightDelta = currentWeight - previousWeight;
    const targetDelta = settings.targetWeight && currentWeight ? currentWeight - settings.targetWeight : null;

    const todayLog = useMemo(() => exerciseLogs.find(l => l.id === selectedDate) || { id: selectedDate }, [exerciseLogs, selectedDate]);
    const walkingMinimum = settings.walkingMinimumMinutes ?? 45;
    const walkingIdeal = settings.walkingIdealMinutes ?? 100;
    const walkingMinutes = todayLog.walk?.done ?? todayLog.activeMinutes ?? 0;
    const walkingProgress = Math.min(100, Math.round((walkingMinutes / Math.max(walkingIdeal, 1)) * 100));
    const sleepHours = todayLog.sleep ? (todayLog.sleep.totalMinutes / 60).toFixed(1) : null;
    const selectedDateLabel = formatDate(selectedDate);
    const weightTrendPoints = useMemo<NumericTrendPoint[]>(() =>
        [...weights]
            .sort((a, b) => a.date.localeCompare(b.date))
            .slice(-20)
            .map(weight => ({
                id: weight.id,
                label: formatShortDate(weight.date),
                value: weight.weight,
            })),
        [weights]
    );
    const painTrendPoints = useMemo<PainTrendPoint[]>(() =>
        [...exerciseLogs]
            .filter(log => log.pain?.morning !== undefined || log.pain?.evening !== undefined)
            .sort((a, b) => a.id.localeCompare(b.id))
            .slice(-30)
            .map(log => ({
                id: log.id,
                label: formatShortDate(log.id),
                morning: log.pain?.morning,
                evening: log.pain?.evening,
                crisis: log.pain?.crisis,
            })),
        [exerciseLogs]
    );

    const activeReminders = useMemo(() => {
        const byId = new Map(telegramReminders.map(reminder => [reminder.id, reminder]));
        DEFAULT_HEALTH_REMINDERS.forEach(reminder => {
            if (!byId.has(reminder.id)) byId.set(reminder.id, reminder);
        });
        return [...byId.values()].sort((a, b) => a.time.localeCompare(b.time));
    }, [telegramReminders]);

    return (
        <div className={`health-view min-h-screen bg-background pb-20 ${isDark ? 'health-view-dark' : ''}`}>
            <div className="border-b border-border-subtle bg-white">
                <div className="mx-auto flex max-w-[1440px] flex-col gap-5 px-6 py-6 lg:px-8">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                        <div>
                            <p className={labelClasses}>Saude integrada</p>
                            <h2 className="mt-1 text-2xl font-bold tracking-tight text-on-surface">Painel de saude</h2>
                            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-on-surface-variant">
                                Biometria, caminhada, sono, calorias, dor e registros medicos em um painel de acompanhamento continuo.
                            </p>
                        </div>
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                            <div className="flex rounded-xl border border-border-standard bg-background p-1">
                                {[
                                    { id: 'telemetry', label: 'Telemetria' },
                                    { id: 'archive', label: 'Arquivo medico' },
                                ].map(tab => (
                                    <button
                                        key={tab.id}
                                        type="button"
                                        onClick={() => setActiveTab(tab.id as 'telemetry' | 'archive')}
                                        className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${
                                            activeTab === tab.id
                                                ? 'bg-primary-container text-white shadow-card'
                                                : 'text-on-surface-variant hover:bg-white hover:text-on-surface'
                                        }`}
                                    >
                                        {tab.label}
                                    </button>
                                ))}
                            </div>
                            <label className="flex items-center gap-2 rounded-xl border border-border-standard bg-background px-3 py-2">
                                <Icon name="calendar" className="h-4 w-4 text-on-surface-variant" />
                                <input
                                    type="date"
                                    value={selectedDate}
                                    onChange={e => setSelectedDate(e.target.value)}
                                    className="bg-transparent text-sm font-semibold text-on-surface outline-none"
                                />
                            </label>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                        <MetricCard
                            label="Peso atual"
                            value={currentWeight ? currentWeight.toFixed(1) : '--'}
                            unit="kg"
                            helper={weightDelta !== 0 ? `${weightDelta > 0 ? '+' : ''}${weightDelta.toFixed(1)} kg desde o registro anterior` : 'Sem variacao no ultimo registro'}
                            icon="scale"
                        />
                        <MetricCard
                            label="Passos do dia"
                            value={todayLog.walk?.steps?.toLocaleString('pt-BR') || '0'}
                            helper={`${todayLog.walk?.distance?.toFixed(1) || '0,0'} km registrados em ${selectedDateLabel}`}
                            icon="steps"
                            tone="text-secondary-container"
                        />
                        <MetricCard
                            label="Calorias"
                            value={todayLog.calories ? Math.round(todayLog.calories).toLocaleString('pt-BR') : '0'}
                            unit="kcal"
                            helper="Total informado pelo Google Fit para o periodo sincronizado"
                            icon="flame"
                            tone="text-error"
                        />
                        <MetricCard
                            label="Sono"
                            value={sleepHours || '--'}
                            unit="h"
                            helper={todayLog.sleep ? `${todayLog.sleep.totalMinutes} minutos totais${todayLog.sleep.deepMinutes ? `, ${todayLog.sleep.deepMinutes} min profundos` : ''}` : 'Sem dados de sono para esta data'}
                            icon="moon"
                            tone="text-primary"
                        />
                    </div>
                </div>
            </div>

            <main className="mx-auto max-w-[1440px] px-6 py-6 lg:px-8">
                <div className="mb-6">
                    <HealthSummaryCard
                        weights={weights}
                        exerciseLogs={exerciseLogs}
                        settings={settings}
                    />
                </div>

                {activeTab === 'telemetry' ? (
                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
                        <div className="space-y-6">
                            <HealthSection title="Lembretes Telegram" eyebrow="Intervencoes leves">
                                <div className="space-y-3">
                                    {activeReminders.map(reminder => (
                                        <div key={reminder.id} className="rounded-xl border border-border-subtle bg-background p-4">
                                            <div className="flex items-start justify-between gap-3">
                                                <div className="min-w-0">
                                                    <p className="text-sm font-bold text-on-surface">{reminder.title}</p>
                                                    <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">{reminder.message}</p>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => onSaveTelegramReminder({ ...reminder, enabled: !reminder.enabled })}
                                                    className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase ${reminder.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}
                                                >
                                                    {reminder.enabled ? 'Ativo' : 'Pausado'}
                                                </button>
                                            </div>
                                            <div className="mt-3 flex items-center justify-between gap-3">
                                                <input
                                                    type="time"
                                                    value={reminder.time}
                                                    onChange={e => onSaveTelegramReminder({ ...reminder, time: e.target.value })}
                                                    className="rounded-lg border border-border-standard bg-white px-3 py-2 text-sm font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-container"
                                                />
                                                {!DEFAULT_HEALTH_REMINDERS.some(defaultReminder => defaultReminder.id === reminder.id) && (
                                                    <button
                                                        type="button"
                                                        onClick={() => onDeleteTelegramReminder(reminder.id)}
                                                        className="text-xs font-semibold text-error hover:underline"
                                                    >
                                                        Remover
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                    <button
                                        type="button"
                                        onClick={() => onSaveTelegramReminder({
                                            id: `custom_${Date.now()}`,
                                            title: 'Novo lembrete',
                                            message: 'Andre, lembrete de saude configurado no Hermes.',
                                            time: '08:00',
                                            enabled: true,
                                            daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
                                            category: 'custom',
                                            telegramOnly: true,
                                        })}
                                        className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-border-standard bg-white px-4 py-3 text-sm font-semibold text-on-surface-variant transition hover:border-primary-container hover:text-primary-container"
                                    >
                                        <Icon name="plus" className="h-4 w-4" />
                                        Adicionar lembrete
                                    </button>
                                </div>
                            </HealthSection>
                        </div>

                        <div className="space-y-6">
                            <HealthSection title="Caminhada" eyebrow="Meta primaria do dia">
                                <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_240px]">
                                    <div className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                                            <div>
                                                <p className={labelClasses}>Minutos ativos</p>
                                                <div className="mt-2 flex items-baseline gap-2">
                                                    <span className="text-4xl font-bold text-on-surface">{walkingMinutes}</span>
                                                    <span className="text-sm font-semibold text-on-surface-variant">/ {walkingIdeal} min</span>
                                                </div>
                                            </div>
                                            <p className="text-sm font-semibold text-on-surface-variant">{todayLog.walk?.steps?.toLocaleString('pt-BR') || 0} passos</p>
                                        </div>
                                        <div className="mt-5 h-2 rounded-full bg-surface-container-high">
                                            <div className="h-full rounded-full bg-primary-container transition-all" style={{ width: `${walkingProgress}%` }} />
                                        </div>
                                        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-on-surface-variant">
                                            <span>Minimo: {walkingMinimum} min</span>
                                            <span>Ideal: {walkingIdeal} min</span>
                                            <span>{todayLog.walk?.distance?.toFixed(1) || '0.0'} km</span>
                                        </div>
                                    </div>
                                    <div className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <label className="block">
                                            <span className={labelClasses}>Minimo diario</span>
                                            <input type="number" value={walkingMinimum} onChange={e => onUpdateSettings({ ...settings, walkingMinimumMinutes: parseInt(e.target.value) || 0 })} className={inputClasses} />
                                        </label>
                                        <label className="mt-4 block">
                                            <span className={labelClasses}>Ideal diario</span>
                                            <input type="number" value={walkingIdeal} onChange={e => onUpdateSettings({ ...settings, walkingIdealMinutes: parseInt(e.target.value) || 0 })} className={inputClasses} />
                                        </label>
                                    </div>
                                </div>
                            </HealthSection>

                            <HealthSection title="Dor lombar" eyebrow="Sinal clinico diario">
                                <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                                    <label className="rounded-xl border border-border-subtle bg-background p-4">
                                        <span className={labelClasses}>Manha</span>
                                        <input type="number" min="0" max="10" value={todayLog.pain?.morning ?? ''} onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, morning: parseInt(e.target.value) || 0 } })} className={inputClasses} />
                                    </label>
                                    <label className="rounded-xl border border-border-subtle bg-background p-4">
                                        <span className={labelClasses}>Noite</span>
                                        <input type="number" min="0" max="10" value={todayLog.pain?.evening ?? ''} onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, evening: parseInt(e.target.value) || 0 } })} className={inputClasses} />
                                    </label>
                                    <button type="button" onClick={() => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, sciatica: !todayLog.pain?.sciatica } })} className={`rounded-xl border p-4 text-left transition ${todayLog.pain?.sciatica ? 'border-tertiary-container bg-tertiary-fixed text-on-tertiary-fixed' : 'border-border-subtle bg-background text-on-surface'}`}>
                                        <span className={labelClasses}>Ciatica</span>
                                        <div className="mt-2 text-sm font-bold">{todayLog.pain?.sciatica ? 'Sim' : 'Nao'}</div>
                                    </button>
                                    <button type="button" onClick={() => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, crisis: !todayLog.pain?.crisis } })} className={`rounded-xl border p-4 text-left transition ${todayLog.pain?.crisis ? 'border-error bg-error-container text-on-error-container' : 'border-border-subtle bg-background text-on-surface'}`}>
                                        <span className={labelClasses}>Crise</span>
                                        <div className="mt-2 text-sm font-bold">{todayLog.pain?.crisis ? 'Sim' : 'Nao'}</div>
                                    </button>
                                </div>
                                <textarea
                                    value={todayLog.pain?.notes || ''}
                                    onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, notes: e.target.value } })}
                                    placeholder="Nota curta opcional"
                                    className="mt-4 min-h-[88px] w-full rounded-xl border border-border-standard bg-background p-3 text-sm text-on-surface outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container"
                                />
                            </HealthSection>

                            <HealthSection title="Tendencia de dor lombar" eyebrow="Historico do Telegram e painel">
                                <PainTrendChart points={painTrendPoints} />
                                <p className="mt-3 text-xs font-semibold leading-relaxed text-on-surface-variant">
                                    Os pontos de noite incluem respostas do check-in no Telegram. Registros manuais feitos no painel aparecem junto no mesmo historico.
                                </p>
                            </HealthSection>

                            <HealthSection title="Tendencia de peso" eyebrow="Biometria historica">
                                <WeightTrendChart points={weightTrendPoints} targetWeight={settings.targetWeight} />
                                {targetDelta !== null && (
                                    <p className="mt-3 text-xs font-semibold text-on-surface-variant">
                                        Distancia ate a meta: {targetDelta > 0 ? '+' : ''}{targetDelta.toFixed(1)} kg.
                                    </p>
                                )}
                            </HealthSection>
                        </div>
                    </div>
                ) : (
                    <HealthSection title="Arquivo medico" eyebrow="Exames e consultas">
                        {exams.length > 0 ? (
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                                {exams.map(exam => (
                                    <article key={exam.id} className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <div className="flex items-start justify-between gap-3">
                                            <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[10px] font-semibold uppercase text-on-surface-variant">{exam.tipo}</span>
                                            <span className="text-xs font-semibold text-on-surface-variant">{formatDate(exam.data)}</span>
                                        </div>
                                        <h4 className="mt-4 text-base font-bold text-on-surface">{exam.titulo}</h4>
                                        <p className="mt-1 text-sm text-on-surface-variant">{exam.doutor_local || 'Local nao informado'}</p>
                                        {exam.pool_dados && exam.pool_dados.length > 0 && (
                                            <div className="mt-4 flex flex-wrap gap-2">
                                                {exam.pool_dados.map(file => (
                                                    <a key={file.id} href={file.valor} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-lg border border-border-standard bg-white px-3 py-2 text-xs font-semibold text-on-surface-variant transition hover:border-primary-container hover:text-primary-container">
                                                        <Icon name="file" className="h-4 w-4" />
                                                        {file.nome || 'Arquivo'}
                                                    </a>
                                                ))}
                                            </div>
                                        )}
                                    </article>
                                ))}
                            </div>
                        ) : (
                            <div className="rounded-2xl border border-dashed border-border-standard bg-background p-8 text-center">
                                <Icon name="heart" className="mx-auto h-8 w-8 text-on-surface-variant" />
                                <p className="mt-3 text-sm font-semibold text-on-surface">Nenhum exame registrado</p>
                                <p className="mt-1 text-sm text-on-surface-variant">Quando houver consultas ou anexos, eles aparecem aqui.</p>
                            </div>
                        )}
                    </HealthSection>
                )}
            </main>
        </div>
    );
};

export default HealthView;
