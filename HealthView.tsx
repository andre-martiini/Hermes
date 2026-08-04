import React, { useMemo, useState } from 'react';
import { arrayUnion, arrayRemove } from 'firebase/firestore';
import {
    HealthWeight, HealthSettings, ExerciseLog,
    ExerciseSettings, formatDate, formatDateLocalISO,
    HealthExam, HealthTelegramReminder, WalkBlock, sumWalkBlocksKm
} from './types';

interface HealthViewProps {
    weights: HealthWeight[];
    settings: HealthSettings;
    onUpdateSettings: (settings: HealthSettings) => void;
    onAddWeight: (weight: number, date: string) => void;
    onDeleteWeight: (id: string) => void;
    exerciseLogs: ExerciseLog[];
    exerciseSettings: ExerciseSettings;
    onSaveExerciseLog: (date: string, data: Partial<ExerciseLog>) => Promise<void>;
    telegramReminders: HealthTelegramReminder[];
    onSaveTelegramReminder: (reminder: HealthTelegramReminder) => Promise<void>;
    onDeleteTelegramReminder: (id: string) => Promise<void>;
    exams: HealthExam[];
    onAddExam: (exam: Omit<HealthExam, 'id' | 'data_criacao' | 'pool_dados'>, files: File[]) => Promise<void>;
    onDeleteExam: (id: string) => void;
    onUpdateExam: (id: string, updates: Partial<HealthExam>) => void;
    isDark?: boolean;
}

type IconName = 'scale' | 'chevron' | 'heart' | 'calendar' | 'file' | 'plus' | 'trash' | 'walk';
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
        case 'trash':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>;
        case 'walk':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 19h9.5a3.5 3.5 0 000-7h-5a3.5 3.5 0 010-7H19" /><circle cx="5" cy="19" r="1.4" fill="currentColor" stroke="none" /><circle cx="19" cy="5" r="1.4" fill="currentColor" stroke="none" /></svg>;
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

const formatKm = (value: number) => value.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 2 });

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

const WalkGoalBar = ({
    doneKm,
    minimumKm,
    idealKm,
}: {
    doneKm: number;
    minimumKm: number;
    idealKm: number;
}) => {
    const scaleKm = Math.max(idealKm, minimumKm, doneKm, 1);
    const percent = Math.min((doneKm / scaleKm) * 100, 100);
    const minPercent = Math.min((minimumKm / scaleKm) * 100, 100);
    const metMinimum = doneKm >= minimumKm;
    const metIdeal = doneKm >= idealKm;

    return (
        <div>
            <div className="flex items-baseline justify-between gap-3">
                <p className="text-2xl font-bold leading-none text-on-surface">
                    {formatKm(doneKm)} <span className="text-xs font-semibold uppercase text-on-surface-variant">km hoje</span>
                </p>
                <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase ${
                    metIdeal ? 'bg-emerald-100 text-emerald-700'
                        : metMinimum ? 'bg-amber-100 text-amber-700'
                            : 'bg-slate-100 text-slate-500'
                }`}>
                    {metIdeal ? 'Meta ideal atingida' : metMinimum ? 'Minimo atingido' : `Faltam ${formatKm(minimumKm - doneKm)} km p/ minimo`}
                </span>
            </div>
            <div className="relative mt-3 h-3 w-full overflow-hidden rounded-full bg-surface-container-low">
                <div
                    style={{ width: `${percent}%` }}
                    className={`h-full rounded-full transition-all duration-500 ${metIdeal ? 'bg-emerald-500' : metMinimum ? 'bg-amber-500' : 'bg-primary-container'}`}
                />
                <div style={{ left: `${minPercent}%` }} className="absolute top-0 h-full w-0.5 bg-on-surface/40" title={`Minimo: ${formatKm(minimumKm)} km`} />
            </div>
            <div className="mt-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.05em] text-on-surface-variant">
                <span>0 km</span>
                <span>Minimo {formatKm(minimumKm)} km</span>
                <span>Ideal {formatKm(idealKm)} km</span>
            </div>
        </div>
    );
};

const WalkDailyChart = ({
    days,
    minimumKm,
    idealKm,
}: {
    days: { id: string; label: string; km: number }[];
    minimumKm: number;
    idealKm: number;
}) => {
    if (!days.some(day => day.km > 0)) {
        return (
            <div className="flex h-[220px] items-center justify-center rounded-2xl border border-dashed border-border-standard bg-background text-sm font-semibold text-on-surface-variant">
                Ainda nao ha caminhadas registradas nos ultimos dias.
            </div>
        );
    }

    const width = 720;
    const height = 220;
    const pad = { top: 24, right: 18, bottom: 36, left: 44 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const maxKm = Math.max(idealKm, ...days.map(day => day.km)) * 1.1;
    const yFor = (value: number) => pad.top + ((maxKm - value) / maxKm) * plotHeight;
    const slot = plotWidth / days.length;
    const barWidth = Math.min(34, slot * 0.6);

    return (
        <div className="rounded-2xl border border-border-subtle bg-background p-4">
            <svg viewBox={`0 0 ${width} ${height}`} className="h-[220px] w-full overflow-visible" role="img" aria-label="Grafico de caminhadas diarias">
                <rect x="0" y="0" width={width} height={height} rx="16" fill="#f8fafc" />
                {[maxKm, maxKm / 2, 0].map(tick => (
                    <g key={tick}>
                        <line x1={pad.left} x2={width - pad.right} y1={yFor(tick)} y2={yFor(tick)} stroke="#d8dee8" strokeWidth="1" />
                        <text x={pad.left - 8} y={yFor(tick) + 4} textAnchor="end" fontSize="11" fontWeight="600" fill="#4d4354">{formatKm(tick)}</text>
                    </g>
                ))}
                <line x1={pad.left} x2={width - pad.right} y1={yFor(minimumKm)} y2={yFor(minimumKm)} stroke="#f59e0b" strokeWidth="2" strokeDasharray="6 6" />
                <text x={width - pad.right} y={yFor(minimumKm) - 6} textAnchor="end" fontSize="11" fontWeight="700" fill="#b45309">minimo</text>
                <line x1={pad.left} x2={width - pad.right} y1={yFor(idealKm)} y2={yFor(idealKm)} stroke="#10b981" strokeWidth="2" strokeDasharray="6 6" />
                <text x={width - pad.right} y={yFor(idealKm) - 6} textAnchor="end" fontSize="11" fontWeight="700" fill="#047857">ideal</text>
                {days.map((day, index) => {
                    const x = pad.left + index * slot + (slot - barWidth) / 2;
                    const y = yFor(day.km);
                    const barHeight = Math.max(0, pad.top + plotHeight - y);
                    const color = day.km >= idealKm ? '#10b981' : day.km >= minimumKm ? '#f59e0b' : '#2563eb';
                    return (
                        <g key={day.id}>
                            {day.km > 0 && <rect x={x} y={y} width={barWidth} height={barHeight} rx="5" fill={color} />}
                            <title>{`${day.label}: ${formatKm(day.km)} km`}</title>
                            <text x={x + barWidth / 2} y={height - 14} textAnchor="middle" fontSize="10" fontWeight="700" fill="#4d4354">{day.label}</text>
                        </g>
                    );
                })}
            </svg>
        </div>
    );
};

const HealthView: React.FC<HealthViewProps> = ({
    weights, settings, onUpdateSettings, onAddWeight, onDeleteWeight,
    exerciseLogs, onSaveExerciseLog, exams, onAddExam, onDeleteExam,
    telegramReminders, onSaveTelegramReminder, onDeleteTelegramReminder,
    isDark = false
}) => {
    const [selectedDate, setSelectedDate] = useState<string>(formatDateLocalISO(new Date()));
    const [activeTab, setActiveTab] = useState<'telemetry' | 'archive'>('telemetry');
    const [weightInput, setWeightInput] = useState<string>('');
    const [walkDistanceInput, setWalkDistanceInput] = useState<string>('');
    const [walkMinutesInput, setWalkMinutesInput] = useState<string>('');
    const [walkStepsInput, setWalkStepsInput] = useState<string>('');
    const [walkCaloriesInput, setWalkCaloriesInput] = useState<string>('');
    const [examTitulo, setExamTitulo] = useState<string>('');
    const [examTipo, setExamTipo] = useState<'exame' | 'consulta'>('exame');
    const [examData, setExamData] = useState<string>(formatDateLocalISO(new Date()));
    const [examDoutorLocal, setExamDoutorLocal] = useState<string>('');
    const [examResultados, setExamResultados] = useState<string>('');
    const [examFiles, setExamFiles] = useState<File[]>([]);
    const [isSavingExam, setIsSavingExam] = useState<boolean>(false);

    const sortedWeights = useMemo(() => [...weights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()), [weights]);
    const currentWeight = sortedWeights[0]?.weight || 0;
    const previousWeight = sortedWeights[1]?.weight || currentWeight;
    const weightDelta = currentWeight - previousWeight;
    const targetDelta = settings.targetWeight && currentWeight ? currentWeight - settings.targetWeight : null;

    const todayLog = useMemo(() => exerciseLogs.find(l => l.id === selectedDate) || { id: selectedDate }, [exerciseLogs, selectedDate]);
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

    const walkingMinimumKm = settings.walkingMinimumKm ?? 3;
    const walkingIdealKm = settings.walkingIdealKm ?? 8;
    const selectedWalkBlocks = todayLog.walkBlocks || [];
    const selectedWalkKm = sumWalkBlocksKm(todayLog);
    const todayWalkKm = useMemo(() => {
        const todayKey = formatDateLocalISO(new Date());
        return sumWalkBlocksKm(exerciseLogs.find(log => log.id === todayKey));
    }, [exerciseLogs]);
    const walkChartDays = useMemo(() => {
        const days: { id: string; label: string; km: number }[] = [];
        const base = new Date();
        for (let offset = 13; offset >= 0; offset--) {
            const day = new Date(base);
            day.setDate(base.getDate() - offset);
            const id = formatDateLocalISO(day);
            days.push({ id, label: formatShortDate(id), km: sumWalkBlocksKm(exerciseLogs.find(log => log.id === id)) });
        }
        return days;
    }, [exerciseLogs]);

    const parsePositiveNumber = (value: string) => {
        const parsed = parseFloat(value.replace(',', '.'));
        return isNaN(parsed) || parsed <= 0 ? undefined : parsed;
    };

    const handleAddWalkBlock = async () => {
        const distance = parsePositiveNumber(walkDistanceInput);
        if (!distance || distance > 50) return;
        const block: WalkBlock = {
            id: `walk_${Date.now()}`,
            time: new Date().toTimeString().slice(0, 5),
            distance,
            source: 'web',
        };
        const minutes = parsePositiveNumber(walkMinutesInput);
        const steps = parsePositiveNumber(walkStepsInput);
        const calories = parsePositiveNumber(walkCaloriesInput);
        if (minutes) block.minutes = Math.round(minutes);
        if (steps) block.steps = Math.round(steps);
        if (calories) block.calories = Math.round(calories);
        await onSaveExerciseLog(selectedDate, { walkBlocks: arrayUnion(block) } as unknown as Partial<ExerciseLog>);
        setWalkDistanceInput('');
        setWalkMinutesInput('');
        setWalkStepsInput('');
        setWalkCaloriesInput('');
    };

    const handleDeleteWalkBlock = async (id: string) => {
        const block = selectedWalkBlocks.find(b => b.id === id);
        if (!block) return;
        await onSaveExerciseLog(selectedDate, { walkBlocks: arrayRemove(block) } as unknown as Partial<ExerciseLog>);
    };

    const handleAddWeight = () => {
        const value = parseFloat(weightInput.replace(',', '.'));
        if (!isNaN(value) && value > 0) {
            onAddWeight(value, selectedDate);
            setWeightInput('');
        }
    };

    const sortedExams = useMemo(
        () => [...exams].sort((a, b) => new Date(b.data).getTime() - new Date(a.data).getTime()),
        [exams]
    );

    const handleAddExam = async () => {
        const titulo = examTitulo.trim();
        if (!titulo || !examData || isSavingExam) return;
        setIsSavingExam(true);
        try {
            await onAddExam(
                {
                    titulo,
                    tipo: examTipo,
                    data: examData,
                    doutor_local: examDoutorLocal.trim() || undefined,
                    resultados: examResultados.trim() || undefined,
                },
                examFiles
            );
            // Só limpa o formulário depois que o registro foi persistido — em caso de falha
            // no upload/gravação, o usuário mantém o que digitou e pode tentar de novo.
            setExamTitulo('');
            setExamTipo('exame');
            setExamData(formatDateLocalISO(new Date()));
            setExamDoutorLocal('');
            setExamResultados('');
            setExamFiles([]);
        } catch (err) {
            console.error('Falha ao adicionar registro de saude:', err);
        } finally {
            setIsSavingExam(false);
        }
    };

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
                                Registro manual de peso, acompanhamento de dor lombar e arquivo medico em um painel de acompanhamento continuo.
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

                    <div className="grid grid-cols-1 gap-4 sm:max-w-2xl sm:grid-cols-2">
                        <MetricCard
                            label="Peso atual"
                            value={currentWeight ? currentWeight.toFixed(1) : '--'}
                            unit="kg"
                            helper={weightDelta !== 0 ? `${weightDelta > 0 ? '+' : ''}${weightDelta.toFixed(1)} kg desde o registro anterior` : 'Sem variacao no ultimo registro'}
                            icon="scale"
                        />
                        <MetricCard
                            label="Caminhada hoje"
                            value={formatKm(todayWalkKm)}
                            unit="km"
                            helper={todayWalkKm >= walkingIdealKm
                                ? 'Meta ideal atingida!'
                                : todayWalkKm >= walkingMinimumKm
                                    ? `Minimo ok — faltam ${formatKm(walkingIdealKm - todayWalkKm)} km para o ideal`
                                    : `Faltam ${formatKm(walkingMinimumKm - todayWalkKm)} km para o minimo de ${formatKm(walkingMinimumKm)} km`}
                            icon="walk"
                            tone="text-emerald-600"
                        />
                    </div>
                </div>
            </div>

            <main className="mx-auto max-w-[1440px] px-6 py-6 lg:px-8">
                {activeTab === 'telemetry' ? (
                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
                        <div className="space-y-6">
                            <HealthSection title="Registro de peso" eyebrow="Entrada manual">
                                <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
                                    <div className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <label className="block">
                                            <span className={labelClasses}>Peso (kg)</span>
                                            <input
                                                type="text"
                                                inputMode="decimal"
                                                value={weightInput}
                                                onChange={e => setWeightInput(e.target.value)}
                                                onKeyDown={e => { if (e.key === 'Enter') handleAddWeight(); }}
                                                placeholder="Ex: 78.5"
                                                className={inputClasses}
                                            />
                                        </label>
                                        <p className="mt-2 text-xs font-medium text-on-surface-variant">
                                            Data do registro: {selectedDateLabel}
                                        </p>
                                        <button
                                            type="button"
                                            onClick={handleAddWeight}
                                            className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-primary-container px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90"
                                        >
                                            <Icon name="plus" className="h-4 w-4" />
                                            Adicionar registro
                                        </button>
                                    </div>
                                    <div className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <label className="block">
                                            <span className={labelClasses}>Meta de peso (kg)</span>
                                            <input
                                                type="number"
                                                step="0.1"
                                                value={settings.targetWeight || ''}
                                                onChange={e => onUpdateSettings({ ...settings, targetWeight: parseFloat(e.target.value) || 0 })}
                                                placeholder="Ex: 75.0"
                                                className={inputClasses}
                                            />
                                        </label>
                                        {targetDelta !== null && (
                                            <p className="mt-3 text-xs font-semibold text-on-surface-variant">
                                                Distancia ate a meta: {targetDelta > 0 ? '+' : ''}{targetDelta.toFixed(1)} kg
                                            </p>
                                        )}
                                    </div>
                                </div>

                                <div className="mt-5">
                                    <p className={`${labelClasses} mb-2`}>Registros recentes</p>
                                    {sortedWeights.length > 0 ? (
                                        <div className="max-h-[240px] space-y-2 overflow-y-auto">
                                            {sortedWeights.slice(0, 20).map(weight => (
                                                <div key={weight.id} className="flex items-center justify-between gap-3 rounded-xl border border-border-subtle bg-white px-4 py-2.5">
                                                    <div className="flex items-baseline gap-2">
                                                        <span className="text-sm font-bold text-on-surface">{weight.weight.toFixed(1)} kg</span>
                                                        <span className="text-xs font-medium text-on-surface-variant">{formatDate(weight.date)}</span>
                                                    </div>
                                                    <button
                                                        type="button"
                                                        onClick={() => onDeleteWeight(weight.id)}
                                                        className="rounded-lg p-1.5 text-on-surface-variant transition hover:bg-error-container hover:text-on-error-container"
                                                        aria-label="Remover registro"
                                                    >
                                                        <Icon name="trash" className="h-4 w-4" />
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <p className="text-xs font-semibold text-on-surface-variant">Nenhum registro de peso ainda.</p>
                                    )}
                                </div>
                            </HealthSection>
                        </div>

                        <div className="space-y-6">
                            <HealthSection title="Caminhada na esteira" eyebrow="Meta diaria de distancia">
                                <WalkGoalBar doneKm={selectedWalkKm} minimumKm={walkingMinimumKm} idealKm={walkingIdealKm} />

                                <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
                                    <div className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <label className="block">
                                            <span className={labelClasses}>Distancia do bloco (km)</span>
                                            <input
                                                type="text"
                                                inputMode="decimal"
                                                value={walkDistanceInput}
                                                onChange={e => setWalkDistanceInput(e.target.value)}
                                                onKeyDown={e => { if (e.key === 'Enter') handleAddWalkBlock(); }}
                                                placeholder="Ex: 1.8"
                                                className={inputClasses}
                                            />
                                        </label>
                                        <div className="mt-2 flex flex-wrap gap-2">
                                            {[1, 1.5, 2, 2.5, 3].map(preset => (
                                                <button
                                                    key={preset}
                                                    type="button"
                                                    onClick={() => setWalkDistanceInput(String(preset))}
                                                    className="rounded-full border border-border-standard bg-white px-3 py-1 text-xs font-semibold text-on-surface-variant transition hover:border-primary-container hover:text-primary-container"
                                                >
                                                    {formatKm(preset)} km
                                                </button>
                                            ))}
                                        </div>
                                        <div className="mt-3 grid grid-cols-3 gap-2">
                                            <label className="block">
                                                <span className={labelClasses}>Minutos</span>
                                                <input type="number" min="0" value={walkMinutesInput} onChange={e => setWalkMinutesInput(e.target.value)} placeholder="40" className={inputClasses} />
                                            </label>
                                            <label className="block">
                                                <span className={labelClasses}>Passos</span>
                                                <input type="number" min="0" value={walkStepsInput} onChange={e => setWalkStepsInput(e.target.value)} placeholder="--" className={inputClasses} />
                                            </label>
                                            <label className="block">
                                                <span className={labelClasses}>Kcal</span>
                                                <input type="number" min="0" value={walkCaloriesInput} onChange={e => setWalkCaloriesInput(e.target.value)} placeholder="--" className={inputClasses} />
                                            </label>
                                        </div>
                                        <p className="mt-2 text-xs font-medium text-on-surface-variant">
                                            So a distancia e obrigatoria. Data do registro: {selectedDateLabel}
                                        </p>
                                        <button
                                            type="button"
                                            onClick={handleAddWalkBlock}
                                            className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-primary-container px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90"
                                        >
                                            <Icon name="plus" className="h-4 w-4" />
                                            Registrar bloco
                                        </button>
                                    </div>
                                    <div className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <p className={labelClasses}>Blocos de {selectedDateLabel}</p>
                                        {selectedWalkBlocks.length > 0 ? (
                                            <div className="mt-3 max-h-[220px] space-y-2 overflow-y-auto">
                                                {selectedWalkBlocks.map(block => (
                                                    <div key={block.id} className="flex items-center justify-between gap-3 rounded-xl border border-border-subtle bg-white px-4 py-2.5">
                                                        <div className="flex min-w-0 items-baseline gap-2">
                                                            <span className="text-sm font-bold text-on-surface">{formatKm(block.distance)} km</span>
                                                            <span className="truncate text-xs font-medium text-on-surface-variant">
                                                                {[
                                                                    block.time,
                                                                    block.minutes ? `${block.minutes} min` : null,
                                                                    block.steps ? `${block.steps} passos` : null,
                                                                    block.calories ? `${block.calories} kcal` : null,
                                                                ].filter(Boolean).join(' · ')}
                                                            </span>
                                                        </div>
                                                        <button
                                                            type="button"
                                                            onClick={() => handleDeleteWalkBlock(block.id)}
                                                            className="rounded-lg p-1.5 text-on-surface-variant transition hover:bg-error-container hover:text-on-error-container"
                                                            aria-label="Remover bloco"
                                                        >
                                                            <Icon name="trash" className="h-4 w-4" />
                                                        </button>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : (
                                            <p className="mt-3 text-xs font-semibold text-on-surface-variant">Nenhum bloco registrado neste dia.</p>
                                        )}
                                        <div className="mt-4 grid grid-cols-2 gap-2">
                                            <label className="block">
                                                <span className={labelClasses}>Meta minima (km)</span>
                                                <input
                                                    type="number"
                                                    step="0.5"
                                                    min="0"
                                                    value={settings.walkingMinimumKm ?? 3}
                                                    onChange={e => onUpdateSettings({ ...settings, walkingMinimumKm: parseFloat(e.target.value) || 0 })}
                                                    className={inputClasses}
                                                />
                                            </label>
                                            <label className="block">
                                                <span className={labelClasses}>Meta ideal (km)</span>
                                                <input
                                                    type="number"
                                                    step="0.5"
                                                    min="0"
                                                    value={settings.walkingIdealKm ?? 8}
                                                    onChange={e => onUpdateSettings({ ...settings, walkingIdealKm: parseFloat(e.target.value) || 0 })}
                                                    className={inputClasses}
                                                />
                                            </label>
                                        </div>
                                    </div>
                                </div>

                                <div className="mt-5">
                                    <p className={`${labelClasses} mb-2`}>Ultimos 14 dias</p>
                                    <WalkDailyChart days={walkChartDays} minimumKm={walkingMinimumKm} idealKm={walkingIdealKm} />
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
                    </div>
                ) : (
                    <HealthSection title="Arquivo medico" eyebrow="Exames e consultas">
                        <div className="rounded-2xl border border-border-subtle bg-background p-5">
                            <p className={`${labelClasses} mb-3`}>Novo registro</p>
                            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                <label className="block">
                                    <span className={labelClasses}>Titulo</span>
                                    <input
                                        type="text"
                                        value={examTitulo}
                                        onChange={e => setExamTitulo(e.target.value)}
                                        placeholder="Ex: Hemograma completo"
                                        className={inputClasses}
                                    />
                                </label>
                                <label className="block">
                                    <span className={labelClasses}>Tipo</span>
                                    <select
                                        value={examTipo}
                                        onChange={e => setExamTipo(e.target.value as 'exame' | 'consulta')}
                                        className={inputClasses}
                                    >
                                        <option value="exame">Exame</option>
                                        <option value="consulta">Consulta</option>
                                    </select>
                                </label>
                                <label className="block">
                                    <span className={labelClasses}>Data</span>
                                    <input
                                        type="date"
                                        value={examData}
                                        onChange={e => setExamData(e.target.value)}
                                        className={inputClasses}
                                    />
                                </label>
                                <label className="block">
                                    <span className={labelClasses}>Doutor(a) / Local</span>
                                    <input
                                        type="text"
                                        value={examDoutorLocal}
                                        onChange={e => setExamDoutorLocal(e.target.value)}
                                        placeholder="Opcional"
                                        className={inputClasses}
                                    />
                                </label>
                                <label className="block sm:col-span-2">
                                    <span className={labelClasses}>Resultados / notas</span>
                                    <textarea
                                        value={examResultados}
                                        onChange={e => setExamResultados(e.target.value)}
                                        placeholder="Opcional"
                                        className={`${inputClasses} min-h-[72px]`}
                                    />
                                </label>
                                <label className="block sm:col-span-2">
                                    <span className={labelClasses}>Anexar arquivos</span>
                                    <input
                                        type="file"
                                        multiple
                                        onChange={e => setExamFiles(e.target.files ? Array.from(e.target.files) : [])}
                                        className={`${inputClasses} file:mr-3 file:rounded-lg file:border-0 file:bg-primary-container file:px-3 file:py-1.5 file:text-xs file:font-bold file:text-white`}
                                    />
                                    {examFiles.length > 0 && (
                                        <p className="mt-1 text-xs font-medium text-on-surface-variant">{examFiles.length} arquivo(s) selecionado(s)</p>
                                    )}
                                </label>
                            </div>
                            <button
                                type="button"
                                onClick={handleAddExam}
                                disabled={!examTitulo.trim() || !examData || isSavingExam}
                                className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-primary-container px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 sm:w-auto"
                            >
                                <Icon name="plus" className="h-4 w-4" />
                                {isSavingExam ? 'Salvando...' : 'Adicionar registro'}
                            </button>
                        </div>

                        {sortedExams.length > 0 ? (
                            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                                {sortedExams.map(exam => (
                                    <article key={exam.id} className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <div className="flex items-start justify-between gap-3">
                                            <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[10px] font-semibold uppercase text-on-surface-variant">{exam.tipo}</span>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-semibold text-on-surface-variant">{formatDate(exam.data)}</span>
                                                <button
                                                    type="button"
                                                    onClick={() => onDeleteExam(exam.id)}
                                                    className="rounded-lg p-1.5 text-on-surface-variant transition hover:bg-error-container hover:text-on-error-container"
                                                    aria-label="Remover registro"
                                                >
                                                    <Icon name="trash" className="h-4 w-4" />
                                                </button>
                                            </div>
                                        </div>
                                        <h4 className="mt-4 text-base font-bold text-on-surface">{exam.titulo}</h4>
                                        <p className="mt-1 text-sm text-on-surface-variant">{exam.doutor_local || 'Local nao informado'}</p>
                                        {exam.resultados && (
                                            <p className="mt-2 text-sm text-on-surface-variant">{exam.resultados}</p>
                                        )}
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
                            <div className="mt-5 rounded-2xl border border-dashed border-border-standard bg-background p-8 text-center">
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
