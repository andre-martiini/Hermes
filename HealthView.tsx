import React, { useEffect, useMemo, useRef, useState } from 'react';
import { arrayUnion, arrayRemove } from 'firebase/firestore';
import {
    HealthWeight, HealthSettings, ExerciseLog,
    ExerciseSettings, formatDate, formatDateLocalISO,
    HealthExam, HealthExamTipo, HEALTH_EXAM_TYPES, HealthTelegramReminder, WalkBlock, sumWalkBlocksKm,
    HealthWaist, RadicularLocation, RadicularSide, TherapyModality, TriggerType,
    RADICULAR_LOCATIONS, THERAPY_MODALITIES, TRIGGER_TYPES,
    HealthEvent, HealthEventType, HEALTH_EVENT_TYPES, HealthWeeklySummary, HealthWeeklyReport
} from './types';
import {
    computeWeightHeadline, movingAverage, weeklyAggregate, parseLocalDate, formatLocalISO, addDays,
    linearRegression, daysSinceEpoch, daysToReachTarget, compareGroups, GroupComparison, WeeklyBucket
} from './src/utils/healthAnalytics';

interface HealthViewProps {
    weights: HealthWeight[];
    settings: HealthSettings;
    onUpdateSettings: (settings: HealthSettings) => void;
    onAddWeight: (weight: number, date: string) => void;
    onUpdateWeight: (id: string, weight: number, date: string) => void;
    onDeleteWeight: (id: string) => void;
    waist: HealthWaist[];
    onAddWaist: (cm: number, date: string) => void;
    onDeleteWaist: (id: string) => void;
    events: HealthEvent[];
    onAddEvent: (event: Omit<HealthEvent, 'id'>) => Promise<void>;
    onDeleteEvent: (id: string) => void;
    latestWeeklySummary?: HealthWeeklySummary;
    weeklyReports?: HealthWeeklyReport[];
    exerciseLogs: ExerciseLog[];
    exerciseSettings: ExerciseSettings;
    onSaveExerciseLog: (date: string, data: Partial<ExerciseLog>) => Promise<void>;
    telegramReminders: HealthTelegramReminder[];
    onSaveTelegramReminder: (reminder: HealthTelegramReminder) => Promise<void>;
    onDeleteTelegramReminder: (id: string) => Promise<void>;
    exams: HealthExam[];
    onAddExam: (exam: Omit<HealthExam, 'id' | 'data_criacao' | 'pool_dados'>, files: File[]) => Promise<void>;
    onDeleteExam: (id: string) => void;
    onUpdateExam: (id: string, updates: Partial<HealthExam>, newFiles?: File[]) => Promise<void>;
    isDark?: boolean;
}

type IconName = 'scale' | 'chevron' | 'heart' | 'calendar' | 'file' | 'plus' | 'trash' | 'walk' | 'edit';
type PainTrendPoint = { id: string; label: string; morning?: number; evening?: number; crisis?: boolean };

// Mantenha esta lista em sincronia com default_health_reminders em functions/main.py
// (mesmos id/title/message/time/daysOfWeek/category) — nao ha fonte unica entre
// TypeScript e Python, entao qualquer mudanca aqui precisa ser replicada la.
const DEFAULT_HEALTH_REMINDERS: HealthTelegramReminder[] = [
    {
        id: 'lunch_slow',
        title: 'Almoço com calma',
        message: 'André, lembre de comer devagar no almoço. Ritmo baixo também é estratégia.',
        time: '11:45',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
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
        id: 'morning_checkin',
        title: 'Check-in da manhã',
        message: 'André, hora do check-in da manhã — 3 perguntas rápidas sobre dor e sono.',
        time: '12:00',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
        category: 'checkin_morning',
        telegramOnly: true,
    },
    {
        id: 'night_checkin',
        title: 'Check-in da noite',
        message: 'André, hora do check-in da noite — uma pergunta por vez, leva menos de 1 minuto.',
        time: '19:00',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
        category: 'checkin_night',
        telegramOnly: true,
    },
    {
        id: 'strength_training',
        title: 'Treino de força — Seg e Sex',
        message: 'André, hoje é dia de treino de força (bloco A ou B).',
        time: '17:20',
        enabled: true,
        daysOfWeek: [1, 5],
        category: 'spine',
        telegramOnly: true,
    },
    {
        id: 'strength_training_wed',
        title: 'Treino de força — Quarta (antes da acupuntura)',
        message: 'André, hoje é dia de treino de força (bloco A ou B) — mais cedo por causa da acupuntura às 17h.',
        time: '15:05',
        enabled: true,
        daysOfWeek: [3],
        category: 'spine',
        telegramOnly: true,
    },
    {
        id: 'daily_weighin',
        title: 'Pesagem diária',
        message: 'André, pese-se ao acordar, antes do café — antes da caminhada.',
        time: '04:20',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
        category: 'custom',
        telegramOnly: true,
    },
    {
        id: 'waist_saturday',
        title: 'Cintura da semana',
        message: 'André, meça a circunferência de cintura na altura do umbigo.',
        time: '08:00',
        enabled: true,
        daysOfWeek: [6],
        category: 'custom',
        telegramOnly: true,
    },
    {
        id: 'batch_cooking_sunday',
        title: 'Batch cooking',
        message: 'André, hora de preparar as refeições da semana.',
        time: '09:45',
        enabled: true,
        daysOfWeek: [0],
        category: 'nutrition',
        telegramOnly: true,
    },
    {
        id: 'fexofenadina_reminder',
        title: 'Fexofenadina',
        message: 'André, tome a fexofenadina com água — longe de suco e de antiácido, que reduzem a absorção em 30–40%.',
        time: '08:00',
        enabled: true,
        daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
        category: 'custom',
        telegramOnly: true,
    },
];

function ChipGroup<T extends string>({
    options,
    value,
    onChange,
    multi = false,
    layout = 'wrap',
    deselectable = true,
}: {
    options: { value: T; label: string }[];
    value: T | T[] | undefined;
    onChange: (next: any) => void;
    multi?: boolean;
    layout?: 'wrap' | 'stack';
    deselectable?: boolean;
}) {
    const selectedValues: T[] = multi ? (Array.isArray(value) ? value : []) : value !== undefined ? [value as T] : [];
    const handleClick = (opt: T) => {
        if (multi) {
            const next = selectedValues.includes(opt) ? selectedValues.filter(v => v !== opt) : [...selectedValues, opt];
            onChange(next);
        } else {
            if (!deselectable && value === opt) return;
            onChange(value === opt ? undefined : opt);
        }
    };
    return (
        <div className={layout === 'stack' ? 'flex flex-col items-stretch gap-1 sm:items-start' : 'flex flex-wrap gap-1.5'}>
            {options.map(opt => {
                const isSelected = selectedValues.includes(opt.value);
                return (
                    <button
                        key={opt.value}
                        type="button"
                        onClick={() => handleClick(opt.value)}
                        className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                            isSelected
                                ? 'border-primary-container bg-primary-container text-white'
                                : 'border-border-standard bg-white text-on-surface-variant hover:border-primary-container hover:text-primary-container'
                        } ${layout === 'stack' ? 'text-left' : ''}`}
                    >
                        {opt.label}
                    </button>
                );
            })}
        </div>
    );
}

// Toggle com trilha de switch visível (bolinha desliza) — em vez de rótulo + a palavra
// "Não" em texto puro, que não sinaliza que é clicável.
const ToggleTile = ({
    label,
    active,
    onClick,
    activeTone = 'primary',
}: {
    label: string;
    active: boolean;
    onClick: () => void;
    activeTone?: 'primary' | 'error' | 'tertiary';
}) => {
    const toneClasses = {
        primary: 'border-primary-container bg-primary-container text-white',
        error: 'border-error bg-error-container text-on-error-container',
        tertiary: 'border-tertiary-container bg-tertiary-container text-on-tertiary-container',
    }[activeTone];
    return (
        <button
            type="button"
            onClick={onClick}
            className={`rounded-xl border p-3 text-left transition ${active ? toneClasses : 'border-border-subtle bg-background text-on-surface'}`}
        >
            <span className={`text-[10px] font-semibold uppercase tracking-[0.05em] ${active ? 'text-current opacity-80' : 'text-on-surface-variant'}`}>{label}</span>
            <div className="mt-2 flex items-center gap-2">
                <span className={`flex h-5 w-9 shrink-0 items-center rounded-full border p-0.5 transition ${active ? 'justify-end border-white/40 bg-white/20' : 'justify-start border-border-standard bg-white'}`}>
                    <span className={`h-3.5 w-3.5 rounded-full transition ${active ? 'bg-white' : 'bg-on-surface-variant/50'}`} />
                </span>
                <span className="text-sm font-bold">{active ? 'Sim' : 'Não'}</span>
            </div>
        </button>
    );
};

const ReminderCard = ({
    reminder,
    isDefault,
    onSave,
    onDelete,
}: {
    reminder: HealthTelegramReminder;
    isDefault: boolean;
    onSave: (reminder: HealthTelegramReminder) => void;
    onDelete: (id: string) => void;
}) => {
    // Estado local do horário: grava no Firestore só no onBlur, não a cada tecla. Digitar
    // direto no <input type="time"> e persistir em cada onChange fazia o valor voltar do
    // estado no meio da digitação (perdia dígito) e reordenava a lista embaixo do cursor —
    // os dois eram o mesmo bug (achados N10/N11 da revisão).
    const [timeValue, setTimeValue] = useState(reminder.time);
    useEffect(() => setTimeValue(reminder.time), [reminder.time]);
    const commitTime = () => {
        if (timeValue && timeValue !== reminder.time) onSave({ ...reminder, time: timeValue });
    };
    return (
        <div className="rounded-xl border border-border-subtle bg-background p-4">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-sm font-bold text-on-surface">{reminder.title}</p>
                    <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">{reminder.message}</p>
                    <p className="mt-1 text-xs font-semibold text-primary-container">{formatCadence(reminder.daysOfWeek, reminder.time)}</p>
                </div>
                <button
                    type="button"
                    onClick={() => onSave({ ...reminder, enabled: !reminder.enabled })}
                    className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase ${reminder.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}
                >
                    {reminder.enabled ? 'Ativo' : 'Pausado'}
                </button>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
                {WEEKDAY_LABELS.map((label, day) => {
                    const days = reminder.daysOfWeek && reminder.daysOfWeek.length ? reminder.daysOfWeek : [0, 1, 2, 3, 4, 5, 6];
                    const active = days.includes(day);
                    return (
                        <button
                            key={day}
                            type="button"
                            title={WEEKDAY_NAMES[day]}
                            aria-label={`${WEEKDAY_NAMES[day]} — ${active ? 'ativo' : 'inativo'}`}
                            aria-pressed={active}
                            onClick={() => {
                                const next = active ? days.filter(d => d !== day) : [...days, day];
                                if (next.length === 0) return;
                                onSave({ ...reminder, daysOfWeek: next.sort() });
                            }}
                            className={`flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold transition ${active ? 'bg-primary-container text-white' : 'bg-white text-on-surface-variant border border-border-standard'}`}
                        >
                            {label}
                        </button>
                    );
                })}
            </div>
            <div className="mt-3 flex items-center justify-between gap-3">
                <input
                    type="time"
                    value={timeValue}
                    onChange={e => setTimeValue(e.target.value)}
                    onBlur={commitTime}
                    className="rounded-lg border border-border-standard bg-white px-3 py-2 text-sm font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-container"
                />
                {!isDefault && (
                    <button
                        type="button"
                        onClick={() => onDelete(reminder.id)}
                        className="text-xs font-semibold text-error hover:underline"
                    >
                        Remover
                    </button>
                )}
            </div>
        </div>
    );
};

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
        case 'edit':
            return <svg {...common}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 4H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2v-5" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>;
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

// Sessão recorrente de terapia sincronizada da agenda (pilates/fisio/acupuntura toda
// semana) é linha de base, não evento — não responde "o que mudou aqui na curva?" como
// uma consulta ou um exame pontual respondem. Vira faixa de densidade, não pino numerado.
const isRecurringTherapySession = (event: { source?: 'manual' | 'calendar' | 'exam'; type: HealthEventType }) =>
    event.source === 'calendar' && (event.type === 'fisioterapia' || event.type === 'modalidade_terapeutica');

const formatKm = (value: number) => value.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 2 });

const MONTH_ABBR_PT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

// Projeção de data com faixa de incerteza — nunca um dia exato, que sugeriria uma
// precisão que a regressão nao tem.
const formatApproxMonth = (dateStr: string): string => {
    const [year, month, day] = dateStr.split('-').map(Number);
    const dayNum = day || 1;
    const part = dayNum <= 10 ? 'início' : dayNum <= 20 ? 'meados' : 'fim';
    return `${part} de ${MONTH_ABBR_PT[(month || 1) - 1]}/${year}`;
};

const WEEKDAY_LABELS = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'];
const WEEKDAY_NAMES = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'];

const formatCadence = (daysOfWeek: number[] | undefined, time: string): string => {
    const days = daysOfWeek && daysOfWeek.length ? [...daysOfWeek].sort() : [0, 1, 2, 3, 4, 5, 6];
    if (days.length === 7) return `Todos os dias às ${time}`;
    if (days.length === 1) return `${WEEKDAY_NAMES[days[0]].replace(/^./, c => c.toUpperCase())} às ${time}`;
    const names = days.map(d => WEEKDAY_NAMES[d].slice(0, 3).replace(/^./, c => c.toUpperCase()));
    const last = names.pop();
    return `${names.join(', ')} e ${last} às ${time}`;
};

const URL_REGEX = /(https?:\/\/[^\s]+)/g;

const renderTextWithLinks = (text: string): React.ReactNode[] =>
    text.split(URL_REGEX).map((part, index) =>
        /^https?:\/\//.test(part) ? (
            <a
                key={index}
                href={part}
                target="_blank"
                rel="noreferrer"
                className="break-all text-primary-container underline hover:opacity-80"
            >
                {part}
            </a>
        ) : (
            part
        )
    );

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
    helper?: React.ReactNode;
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

function useChartHover(count: number) {
    const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
    const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
    const updateFromClientX = (clientX: number, clientY: number, svg: SVGSVGElement, padLeft: number, plotWidth: number) => {
        if (count < 2) return;
        const rect = svg.getBoundingClientRect();
        if (rect.width === 0) return;
        const viewBoxWidth = svg.viewBox.baseVal.width || rect.width;
        const scaleX = viewBoxWidth / rect.width;
        const xInSvg = (clientX - rect.left) * scaleX;
        const ratio = (xInSvg - padLeft) / plotWidth;
        const index = Math.round(ratio * (count - 1));
        setHoveredIndex(Math.max(0, Math.min(count - 1, index)));
        setHoverPos({ x: clientX, y: clientY });
    };
    const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>, padLeft: number, plotWidth: number) =>
        updateFromClientX(e.clientX, e.clientY, e.currentTarget, padLeft, plotWidth);
    const handleTouchMove = (e: React.TouchEvent<SVGSVGElement>, padLeft: number, plotWidth: number) => {
        const touch = e.touches[0];
        if (touch) updateFromClientX(touch.clientX, touch.clientY, e.currentTarget, padLeft, plotWidth);
    };
    const handleLeave = () => { setHoveredIndex(null); setHoverPos(null); };
    return { hoveredIndex, hoverPos, handleMouseMove, handleTouchMove, handleLeave };
}

const ChartTooltip = ({ x, y, children }: { x: number; y: number; children: React.ReactNode }) => {
    const vw = typeof window !== 'undefined' ? window.innerWidth : x + 118;
    const vh = typeof window !== 'undefined' ? window.innerHeight : y + 40;
    const clampedX = Math.min(Math.max(x, 118), Math.max(118, vw - 118));
    const clampedY = Math.min(Math.max(y, 12), vh - 12);
    return (
        <div
            className="pointer-events-none fixed z-30 max-w-[220px] -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg bg-on-surface px-2.5 py-1.5 text-[11px] font-semibold text-background shadow-lg"
            style={{ left: clampedX, top: clampedY }}
        >
            {children}
        </div>
    );
};

const ChartTableToggle = ({ showTable, onToggle }: { showTable: boolean; onToggle: () => void }) => (
    <button
        type="button"
        onClick={onToggle}
        className="absolute right-4 top-4 z-10 rounded-full border border-border-standard bg-white px-2.5 py-1 text-[10px] font-semibold text-on-surface-variant transition hover:border-primary-container hover:text-primary-container"
    >
        {showTable ? 'Ver gráfico' : 'Ver tabela'}
    </button>
);

const ChartDataTable = ({ columns, rows }: { columns: string[]; rows: (string | number)[][] }) => (
    <div className="max-h-[280px] overflow-auto rounded-xl border border-border-subtle">
        <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-background">
                <tr>{columns.map(c => <th key={c} className="whitespace-nowrap px-3 py-2 font-semibold text-on-surface-variant">{c}</th>)}</tr>
            </thead>
            <tbody>
                {rows.map((row, i) => (
                    <tr key={i} className="border-t border-border-subtle">
                        {row.map((cell, j) => <td key={j} className="whitespace-nowrap px-3 py-2 text-on-surface">{cell}</td>)}
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

const chartPalette = (isDark: boolean) => ({
    bg: isDark ? '#171e2b' : '#f8fafc',
    grid: isDark ? '#2c3547' : '#d8dee8',
    text: isDark ? '#c3cadb' : '#4d4354',
    line: isDark ? '#60a5fa' : '#2563eb',
    point: isDark ? '#171e2b' : '#ffffff',
    target: isDark ? '#34d399' : '#10b981',
    targetText: isDark ? '#6ee7b7' : '#047857',
    amber: isDark ? '#fbbf24' : '#f59e0b',
    amberText: isDark ? '#fcd34d' : '#b45309',
    rose: isDark ? '#fb7185' : '#e11d48',
    emerald: isDark ? '#34d399' : '#10b981',
    trajectory: isDark ? '#a78bfa' : '#7c3aed',
    trendLine: isDark ? '#fb923c' : '#c2410c',
    // Vermelho fica reservado para o estado de alerta (sinal vermelho) — nenhuma
    // série de gráfico usa vermelho/rose, para não diluir esse único canal de alarme.
    eveningPain: isDark ? '#818cf8' : '#4f46e5',
});

function nearestByTime<T>(items: T[], getTime: (item: T) => number, targetTime: number): T | null {
    if (!items.length) return null;
    let best = items[0];
    let bestDiff = Math.abs(getTime(items[0]) - targetTime);
    for (const item of items) {
        const diff = Math.abs(getTime(item) - targetTime);
        if (diff < bestDiff) { best = item; bestDiff = diff; }
    }
    return best;
}

const WeightTrendChart = ({
    points,
    targetWeight,
    projectionLines = [],
    isDark = false,
}: {
    points: { date: string; value: number }[];
    targetWeight?: number;
    projectionLines?: { key: string; label: string; color: 'trajectory' | 'trendLine'; points: { date: string; value: number }[] }[];
    isDark?: boolean;
}) => {
    const [showTable, setShowTable] = useState(false);
    const [hoverTime, setHoverTime] = useState<number | null>(null);
    const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
    const palette = chartPalette(isDark);

    if (points.length < 2) {
        return (
            <div className="flex h-[280px] items-center justify-center rounded-2xl border border-dashed border-border-standard bg-background p-4 text-center text-sm font-semibold text-on-surface-variant">
                {points.length === 0
                    ? 'Ainda não há registros de peso — adicione o primeiro em "Registro de peso".'
                    : `Falta pelo menos mais 1 registro de peso para montar o gráfico de tendência (há ${points.length} até agora).`}
            </div>
        );
    }

    const width = 720;
    const height = 260;
    const pad = { top: 26, right: 18, bottom: 42, left: 46 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;

    const allDates = [...points.map(p => p.date), ...projectionLines.flatMap(l => l.points.map(p => p.date))];
    const minDate = allDates.reduce((a, b) => (a < b ? a : b));
    const maxDate = allDates.reduce((a, b) => (a > b ? a : b));
    const minTime = parseLocalDate(minDate).getTime();
    const maxTime = Math.max(parseLocalDate(maxDate).getTime(), minTime + 1);
    const totalSpan = Math.max(1, maxTime - minTime);
    const xForDate = (d: string) => pad.left + ((parseLocalDate(d).getTime() - minTime) / totalSpan) * plotWidth;

    const allValues = [...points.map(p => p.value), ...(targetWeight ? [targetWeight] : []), ...projectionLines.flatMap(l => l.points.map(p => p.value))];
    const rawMin = Math.min(...allValues);
    const rawMax = Math.max(...allValues);
    const min = Math.floor(rawMin - 1);
    const max = Math.ceil(rawMax + 1);
    const range = Math.max(1, max - min);
    const yFor = (value: number) => pad.top + ((max - value) / range) * plotHeight;
    const path = points.map(p => `${xForDate(p.date)},${yFor(p.value)}`).join(' ');
    const targetY = targetWeight ? yFor(targetWeight) : null;
    const yTicks = [max, Math.round((max + min) / 2), min];

    const handleMove = (e: React.MouseEvent<SVGSVGElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        if (rect.width === 0) return;
        const ratio = (e.clientX - rect.left) / rect.width;
        const xInSvg = ratio * width;
        const timeRatio = (xInSvg - pad.left) / plotWidth;
        setHoverTime(minTime + Math.max(0, Math.min(1, timeRatio)) * totalSpan);
        setHoverPos({ x: e.clientX, y: e.clientY });
    };
    const handleTouch = (e: React.TouchEvent<SVGSVGElement>) => {
        const touch = e.touches[0];
        if (!touch) return;
        const rect = e.currentTarget.getBoundingClientRect();
        if (rect.width === 0) return;
        const ratio = (touch.clientX - rect.left) / rect.width;
        const xInSvg = ratio * width;
        const timeRatio = (xInSvg - pad.left) / plotWidth;
        setHoverTime(minTime + Math.max(0, Math.min(1, timeRatio)) * totalSpan);
        setHoverPos({ x: touch.clientX, y: touch.clientY });
    };
    const handleLeave = () => { setHoverTime(null); setHoverPos(null); };
    const hovered = hoverTime !== null ? nearestByTime(points, p => parseLocalDate(p.date).getTime(), hoverTime) : null;
    const hoverX = hoverTime !== null ? xForDate(formatLocalISO(new Date(hoverTime))) : null;

    if (showTable) {
        return (
            <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
                <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(false)} />
                <p className={`${labelClasses} mb-2`}>Tendência de peso</p>
                <ChartDataTable columns={['Data', 'Peso — média 7d (kg)']} rows={points.map(p => [formatShortDate(p.date), p.value.toFixed(1).replace('.', ',')])} />
            </div>
        );
    }

    return (
        <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
            <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(true)} />
            {hovered && hoverPos && (
                <ChartTooltip x={hoverPos.x} y={hoverPos.y - 12}>
                    {formatShortDate(hovered.date)}: {hovered.value.toFixed(1).replace('.', ',')} kg
                </ChartTooltip>
            )}
            <svg
                viewBox={`0 0 ${width} ${height}`}
                className="h-[280px] w-full touch-none overflow-visible"
                role="img"
                aria-label="Gráfico de tendência de peso"
                onMouseMove={handleMove}
                onTouchMove={handleTouch}
                onMouseLeave={handleLeave}
                onTouchEnd={handleLeave}
            >
                <rect x="0" y="0" width={width} height={height} rx="16" fill={palette.bg} />
                {yTicks.map(tick => (
                    <g key={tick}>
                        <line x1={pad.left} x2={width - pad.right} y1={yFor(tick)} y2={yFor(tick)} stroke={palette.grid} strokeWidth="1" />
                        <text x={pad.left - 10} y={yFor(tick) + 4} textAnchor="end" fontSize="12" fontWeight="600" fill={palette.text}>{tick} kg</text>
                    </g>
                ))}
                {targetY !== null && (
                    <g>
                        <line x1={pad.left} x2={width - pad.right} y1={targetY} y2={targetY} stroke={palette.target} strokeWidth="2" strokeDasharray="6 6" />
                        <text x={width - pad.right} y={targetY - 8} textAnchor="end" fontSize="12" fontWeight="700" fill={palette.targetText}>meta</text>
                    </g>
                )}
                {hoverX !== null && (
                    <line x1={hoverX} x2={hoverX} y1={pad.top} y2={height - pad.bottom} stroke={palette.text} strokeOpacity="0.3" strokeWidth="1.5" />
                )}
                {projectionLines.map(line => (
                    <g key={line.key}>
                        <polyline
                            points={line.points.map(p => `${xForDate(p.date)},${yFor(p.value)}`).join(' ')}
                            fill="none"
                            stroke={palette[line.color]}
                            strokeWidth="2"
                            strokeDasharray="5 5"
                            strokeLinecap="round"
                        />
                        <text x={xForDate(line.points[line.points.length - 1].date)} y={yFor(line.points[line.points.length - 1].value) - 6} textAnchor="end" fontSize="10" fontWeight="700" fill={palette[line.color]}>{line.label}</text>
                    </g>
                ))}
                <polyline points={path} fill="none" stroke={palette.line} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
                {points.map(point => (
                    <g key={point.date}>
                        <circle cx={xForDate(point.date)} cy={yFor(point.value)} r={hovered?.date === point.date ? 6 : 4} fill={palette.point} stroke={palette.line} strokeWidth="2.5" />
                    </g>
                ))}
                <text x={xForDate(points[0].date)} y={height - 16} textAnchor="start" fontSize="11" fontWeight="700" fill={palette.text}>{formatShortDate(points[0].date)}</text>
                <text x={xForDate(points[points.length - 1].date)} y={height - 16} textAnchor="end" fontSize="11" fontWeight="700" fill={palette.text}>{formatShortDate(points[points.length - 1].date)}</text>
            </svg>
        </div>
    );
};

const PainTrendChart = ({ points, isDark = false }: { points: PainTrendPoint[]; isDark?: boolean }) => {
    const visiblePoints = points.filter(point => point.morning !== undefined || point.evening !== undefined);
    const [showTable, setShowTable] = useState(false);
    const { hoveredIndex, hoverPos, handleMouseMove, handleTouchMove, handleLeave } = useChartHover(visiblePoints.length);
    const palette = chartPalette(isDark);

    if (visiblePoints.length < 2) {
        return (
            <div className="flex h-[240px] items-center justify-center rounded-2xl border border-dashed border-border-standard bg-background p-4 text-center text-sm font-semibold text-on-surface-variant">
                {visiblePoints.length === 0
                    ? 'Ainda não há registros de dor — preencha "Dor lombar" no registro diário ou responda o check-in do Telegram.'
                    : `Falta pelo menos mais 1 registro de dor para montar o gráfico (há ${visiblePoints.length} até agora).`}
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
    const hovered = hoveredIndex !== null ? visiblePoints[hoveredIndex] : null;

    if (showTable) {
        return (
            <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
                <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(false)} />
                <p className={`${labelClasses} mb-2`}>Tendência de dor lombar</p>
                <ChartDataTable
                    columns={['Data', 'Manhã', 'Noite', 'Crise']}
                    rows={visiblePoints.map(p => [p.label, p.morning ?? '-', p.evening ?? '-', p.crisis ? 'Sim' : 'Não'])}
                />
            </div>
        );
    }

    return (
        <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
            <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(true)} />
            {hovered && hoverPos && (
                <ChartTooltip x={hoverPos.x} y={hoverPos.y - 12}>
                    {hovered.label}: manhã {hovered.morning ?? '-'}, noite {hovered.evening ?? '-'}{hovered.crisis ? ', crise' : ''}
                </ChartTooltip>
            )}
            <div className="mb-3 flex flex-wrap items-center gap-4 text-xs font-semibold text-on-surface-variant">
                <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-amber-500" />Manhã</span>
                <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-indigo-600" />Noite / Telegram</span>
                <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-on-surface" />Crise</span>
            </div>
            <svg
                viewBox={`0 0 ${width} ${height}`}
                className="h-[240px] w-full touch-none overflow-visible"
                role="img"
                aria-label="Gráfico de dor lombar"
                onMouseMove={e => handleMouseMove(e, pad.left, plotWidth)}
                onTouchMove={e => handleTouchMove(e, pad.left, plotWidth)}
                onMouseLeave={handleLeave}
                onTouchEnd={handleLeave}
            >
                <rect x="0" y="0" width={width} height={height} rx="16" fill={palette.bg} />
                {[10, 7, 5, 3, 0].map(tick => (
                    <g key={tick}>
                        <line x1={pad.left} x2={width - pad.right} y1={yFor(tick)} y2={yFor(tick)} stroke={palette.grid} strokeWidth="1" />
                        <text x={pad.left - 10} y={yFor(tick) + 4} textAnchor="end" fontSize="12" fontWeight="700" fill={palette.text}>{tick}</text>
                    </g>
                ))}
                {hoveredIndex !== null && (
                    <line x1={xFor(hoveredIndex)} x2={xFor(hoveredIndex)} y1={pad.top} y2={height - pad.bottom} stroke={palette.text} strokeOpacity="0.3" strokeWidth="1.5" />
                )}
                {lineFor('morning') && <polyline points={lineFor('morning')} fill="none" stroke={palette.amber} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />}
                {lineFor('evening') && <polyline points={lineFor('evening')} fill="none" stroke={palette.eveningPain} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />}
                {visiblePoints.map((point, index) => (
                    <g key={point.id}>
                        {point.morning !== undefined && <circle cx={xFor(index)} cy={yFor(point.morning)} r={hoveredIndex === index ? 7 : 5} fill={palette.point} stroke={palette.amber} strokeWidth="3" />}
                        {point.evening !== undefined && <circle cx={xFor(index)} cy={yFor(point.evening)} r={hoveredIndex === index ? 8 : 6} fill={palette.point} stroke={palette.eveningPain} strokeWidth="3" />}
                        {point.crisis && <circle cx={xFor(index)} cy={yFor(Math.max(point.morning ?? 0, point.evening ?? 0, 1))} r="9" fill="none" stroke={palette.text} strokeWidth="2" strokeDasharray="3 3" />}
                    </g>
                ))}
                {visiblePoints.map((point, index) => (
                    index === 0 || index === visiblePoints.length - 1 || index % Math.ceil(visiblePoints.length / 5) === 0 ? (
                        <text key={`label-${point.id}`} x={xFor(index)} y={height - 16} textAnchor="middle" fontSize="11" fontWeight="700" fill={palette.text}>{point.label}</text>
                    ) : null
                ))}
            </svg>
        </div>
    );
};

const WalkGoalBar = ({
    doneKm,
    minimumKm,
    normalTopKm,
    isCrisis,
}: {
    doneKm: number;
    minimumKm: number;
    normalTopKm: number;
    isCrisis: boolean;
}) => {
    const scaleKm = Math.max(normalTopKm, minimumKm, doneKm, 1);
    const percent = Math.min((doneKm / scaleKm) * 100, 100);
    const minPercent = Math.min((minimumKm / scaleKm) * 100, 100);
    const metMinimum = doneKm >= minimumKm;
    const inBonus = doneKm > normalTopKm;

    if (isCrisis) {
        return (
            <div>
                <div className="flex items-baseline justify-between gap-3">
                    <p className="text-2xl font-bold leading-none text-on-surface">
                        {formatKm(doneKm)} <span className="text-xs font-semibold uppercase text-on-surface-variant">km hoje</span>
                    </p>
                    <span className="rounded-full bg-tertiary-container px-2.5 py-1 text-[10px] font-semibold uppercase text-on-tertiary-container">
                        Dia de crise
                    </span>
                </div>
                <p className="mt-3 text-xs font-semibold leading-relaxed text-on-surface-variant">
                    Caminhadas curtas e frequentes, sem meta de distância — o piso mínimo não se aplica hoje.
                </p>
            </div>
        );
    }

    return (
        <div>
            <div className="flex items-baseline justify-between gap-3">
                <p className="text-2xl font-bold leading-none text-on-surface">
                    {formatKm(doneKm)} <span className="text-xs font-semibold uppercase text-on-surface-variant">km hoje</span>
                </p>
                <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase ${
                    inBonus ? 'bg-emerald-100 text-emerald-700'
                        : metMinimum ? 'bg-amber-100 text-amber-700'
                            : 'bg-slate-100 text-slate-500'
                }`}>
                    {inBonus ? 'Bônus — acima da faixa normal' : metMinimum ? 'Dentro da faixa normal' : `Faltam ${formatKm(minimumKm - doneKm)} km p/ mínimo`}
                </span>
            </div>
            <div className="relative mt-3 h-3 w-full overflow-hidden rounded-full bg-surface-container-low">
                <div
                    style={{ width: `${percent}%` }}
                    className={`h-full rounded-full transition-all duration-500 ${inBonus ? 'bg-emerald-500' : metMinimum ? 'bg-amber-500' : 'bg-primary-container'}`}
                />
                <div style={{ left: `${minPercent}%` }} className="absolute top-0 h-full w-0.5 bg-on-surface/40" title={`Mínimo: ${formatKm(minimumKm)} km`} />
            </div>
            <div className="mt-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.05em] text-on-surface-variant">
                <span>0 km</span>
                <span>Mínimo {formatKm(minimumKm)} km</span>
                <span>Faixa normal até {formatKm(normalTopKm)} km</span>
            </div>
        </div>
    );
};

const WalkDailyChart = ({
    days,
    minimumKm,
    idealKm,
    isDark = false,
}: {
    days: { id: string; label: string; km: number }[];
    minimumKm: number;
    idealKm: number;
    isDark?: boolean;
}) => {
    const [showTable, setShowTable] = useState(false);
    const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
    const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
    const palette = chartPalette(isDark);

    if (!days.some(day => day.km > 0)) {
        return (
            <div className="flex h-[220px] items-center justify-center rounded-2xl border border-dashed border-border-standard bg-background text-sm font-semibold text-on-surface-variant">
                Ainda não há caminhadas registradas nos últimos dias.
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
    const hovered = hoveredIndex !== null ? days[hoveredIndex] : null;

    const updateHoverFromClientX = (clientX: number, clientY: number, svg: SVGSVGElement) => {
        const rect = svg.getBoundingClientRect();
        if (rect.width === 0) return;
        const viewBoxWidth = svg.viewBox.baseVal.width || rect.width;
        const scaleX = viewBoxWidth / rect.width;
        const xInSvg = (clientX - rect.left) * scaleX;
        const index = Math.floor((xInSvg - pad.left) / slot);
        setHoveredIndex(Math.max(0, Math.min(days.length - 1, index)));
        setHoverPos({ x: clientX, y: clientY });
    };

    if (showTable) {
        return (
            <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
                <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(false)} />
                <p className={`${labelClasses} mb-2`}>Caminhadas diárias</p>
                <ChartDataTable columns={['Data', 'Km']} rows={days.map(d => [d.label, formatKm(d.km)])} />
            </div>
        );
    }

    return (
        <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
            <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(true)} />
            {hovered && hoverPos && (
                <ChartTooltip x={hoverPos.x} y={hoverPos.y - 12}>
                    {hovered.label}: {formatKm(hovered.km)} km
                </ChartTooltip>
            )}
            <svg
                viewBox={`0 0 ${width} ${height}`}
                className="h-[220px] w-full touch-none overflow-visible"
                role="img"
                aria-label="Gráfico de caminhadas diárias"
                onMouseMove={e => updateHoverFromClientX(e.clientX, e.clientY, e.currentTarget)}
                onTouchMove={e => { const t = e.touches[0]; if (t) updateHoverFromClientX(t.clientX, t.clientY, e.currentTarget); }}
                onMouseLeave={() => { setHoveredIndex(null); setHoverPos(null); }}
                onTouchEnd={() => { setHoveredIndex(null); setHoverPos(null); }}
            >
                <rect x="0" y="0" width={width} height={height} rx="16" fill={palette.bg} />
                {[maxKm, maxKm / 2, 0].map(tick => (
                    <g key={tick}>
                        <line x1={pad.left} x2={width - pad.right} y1={yFor(tick)} y2={yFor(tick)} stroke={palette.grid} strokeWidth="1" />
                        <text x={pad.left - 8} y={yFor(tick) + 4} textAnchor="end" fontSize="11" fontWeight="600" fill={palette.text}>{formatKm(tick)}</text>
                    </g>
                ))}
                <line x1={pad.left} x2={width - pad.right} y1={yFor(minimumKm)} y2={yFor(minimumKm)} stroke={palette.amber} strokeWidth="2" strokeDasharray="6 6" />
                <text x={width - pad.right} y={yFor(minimumKm) - 6} textAnchor="end" fontSize="11" fontWeight="700" fill={palette.amberText}>mínimo</text>
                <line x1={pad.left} x2={width - pad.right} y1={yFor(idealKm)} y2={yFor(idealKm)} stroke={palette.target} strokeWidth="2" strokeDasharray="6 6" />
                <text x={width - pad.right} y={yFor(idealKm) - 6} textAnchor="end" fontSize="11" fontWeight="700" fill={palette.targetText}>normal</text>
                {hoveredIndex !== null && (
                    <rect x={pad.left + hoveredIndex * slot} y={pad.top} width={slot} height={plotHeight} fill={palette.text} opacity="0.06" />
                )}
                {days.map((day, index) => {
                    const x = pad.left + index * slot + (slot - barWidth) / 2;
                    const y = yFor(day.km);
                    const barHeight = Math.max(0, pad.top + plotHeight - y);
                    // Uma única cor para km em todo o app (mesma de "km" no gráfico integrado) — as
                    // linhas tracejadas de mínimo/ideal já comunicam o status; abaixo do mínimo só
                    // fica um tom mais claro da mesma cor, não uma cor categórica diferente.
                    const opacity = hoveredIndex === index ? 1 : day.km >= minimumKm ? 0.9 : 0.45;
                    return (
                        <g key={day.id}>
                            {day.km > 0 && <rect x={x} y={y} width={barWidth} height={barHeight} rx="5" fill={palette.emerald} opacity={opacity} />}
                            <text x={x + barWidth / 2} y={height - 14} textAnchor="middle" fontSize="10" fontWeight="700" fill={palette.text}>{day.label}</text>
                        </g>
                    );
                })}
            </svg>
        </div>
    );
};

const IntegratedTrendChart = ({
    weightPoints,
    painWeekly,
    kmWeekly,
    events,
    targetWeight,
    isDark = false,
}: {
    weightPoints: { date: string; value: number; count?: number }[];
    painWeekly: WeeklyBucket[];
    kmWeekly: WeeklyBucket[];
    events: HealthEvent[];
    targetWeight?: number;
    isDark?: boolean;
}) => {
    const [showTable, setShowTable] = useState(false);
    const [hoverTime, setHoverTime] = useState<number | null>(null);
    const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
    const palette = chartPalette(isDark);

    const allDates = [
        ...weightPoints.map(p => p.date),
        ...painWeekly.map(b => b.weekStart),
        ...kmWeekly.map(b => b.weekStart),
        ...events.map(e => e.date),
    ];

    if (allDates.length < 2) {
        return (
            <div className="flex h-[260px] items-center justify-center rounded-2xl border border-dashed border-border-standard bg-background p-4 text-center text-sm font-semibold text-on-surface-variant">
                Faltam registros de peso, dor ou caminhada neste período para montar o gráfico integrado.
            </div>
        );
    }

    const todayStr = formatLocalISO(new Date());
    const minDate = allDates.reduce((a, b) => (a < b ? a : b));
    const maxDate = [...allDates, todayStr].reduce((a, b) => (a > b ? a : b));
    const minTime = parseLocalDate(minDate).getTime();
    const maxTime = parseLocalDate(maxDate).getTime();
    const totalSpan = Math.max(1, maxTime - minTime);

    // Layout: cada painel tem cabeçalho próprio (fora da área de plotagem), superfície
    // própria e gap real entre painéis. Trilha de eventos reservada no topo, com
    // clearance para o botão "Ver tabela"/"Gerar relatório" do cabeçalho do card.
    const width = 720;
    const padLeft = 50;
    const padRight = 18;
    const plotWidth = width - padLeft - padRight;

    const eventTrackTop = 30;
    const eventTrackH = 24;
    const headerH = 16;
    const panelGap = 22;
    const weightH = 150;
    const painH = 130;
    const kmH = 130;

    const weightHeaderY = eventTrackTop + eventTrackH + 8;
    const weightPlotY = weightHeaderY + headerH;
    const painHeaderY = weightPlotY + weightH + panelGap;
    const painPlotY = painHeaderY + headerH;
    const kmHeaderY = painPlotY + painH + panelGap;
    const kmPlotY = kmHeaderY + headerH;
    const gridBottomY = kmPlotY + kmH;
    const xAxisY = gridBottomY + 24;
    const totalHeight = xAxisY + 8;

    const xForTime = (t: number) => padLeft + ((t - minTime) / totalSpan) * plotWidth;
    const xForDate = (d: string) => xForTime(parseLocalDate(d).getTime());

    // Painel 1: peso (media movel de 7 dias)
    const weightValues = weightPoints.map(p => p.value);
    const weightMin = weightValues.length ? Math.floor(Math.min(...weightValues) - 0.5) : 0;
    const weightMax = weightValues.length ? Math.ceil(Math.max(...weightValues) + 0.5) : 1;
    const weightRange = Math.max(0.5, weightMax - weightMin);
    const weightScaleExpanded = targetWeight !== undefined && (targetWeight < weightMin || targetWeight > weightMax);
    const yForWeight = (v: number) => weightPlotY + ((weightMax - v) / weightRange) * weightH;
    const weightPath = weightPoints.map(p => `${xForDate(p.date)},${yForWeight(p.value)}`).join(' ');
    const weightTicks = [weightMax, weightMax - weightRange / 3, weightMax - (2 * weightRange) / 3, weightMin];

    // Painel 2: dor media semanal (escala fixa 0-10)
    const yForPain = (v: number) => painPlotY + ((10 - v) / 10) * painH;
    const painPath = painWeekly.map(b => `${xForDate(b.weekStart)},${yForPain(b.average)}`).join(' ');
    const painTicks = [10, 5, 0];

    // Painel 3: km caminhados por semana (barras)
    const maxKmWeek = Math.max(1, ...kmWeekly.map(b => b.sum));
    const yForKm = (v: number) => kmPlotY + kmH - (v / maxKmWeek) * kmH;
    const kmBarWidth = Math.min(24, (plotWidth / Math.max(1, kmWeekly.length)) * 0.6);
    const kmTicks = [maxKmWeek, maxKmWeek / 2, 0];

    // Datas do eixo X compartilhado (5-6 marcas, com grade vertical atravessando os 3 painéis)
    const AXIS_TICK_COUNT = 6;
    const axisTimes = Array.from({ length: AXIS_TICK_COUNT }, (_, i) => minTime + (totalSpan * i) / (AXIS_TICK_COUNT - 1));

    const sortedEvents = [...events].sort((a, b) => a.date.localeCompare(b.date));

    // Sessão recorrente sincronizada da agenda (pilates/fisio/acupuntura semanais) é
    // linha de base, não evento pontual — separada em faixa de densidade discreta, sem
    // número. Pino numerado fica só para o que de fato explica uma inflexão na curva:
    // consulta, exame, viagem, medicação, troca de modalidade.
    const recurringSessions = sortedEvents.filter(isRecurringTherapySession);
    const punctualEvents = sortedEvents.filter(e => !isRecurringTherapySession(e));

    // Pinos numerados em vez de rótulo de texto no SVG: com eventos próximos no tempo,
    // qualquer rótulo textual — mesmo truncado e empacotado por linha — fica ilegível.
    // O número mapeia 1:1 com os chips de legenda abaixo do gráfico (mesma ordem
    // cronológica), que já trazem data e nome completo. Título completo também no hover.
    const eventLayout = punctualEvents.map((event, i) => ({ event, x: xForDate(event.date), number: i + 1 }));
    const recurringLayout = recurringSessions.map(event => ({ event, x: xForDate(event.date) }));

    const updateHoverFromClientX = (clientX: number, clientY: number, containerRect: DOMRect) => {
        if (containerRect.width === 0) return;
        const ratioX = (clientX - containerRect.left) / containerRect.width;
        const xInSvg = ratioX * width;
        const ratio = (xInSvg - padLeft) / plotWidth;
        const time = minTime + Math.max(0, Math.min(1, ratio)) * totalSpan;
        setHoverTime(time);
        setHoverPos({ x: clientX, y: clientY });
    };
    const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => updateHoverFromClientX(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect());
    const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
        const touch = e.touches[0];
        if (touch) updateHoverFromClientX(touch.clientX, touch.clientY, e.currentTarget.getBoundingClientRect());
    };
    const handleLeave = () => { setHoverTime(null); setHoverPos(null); };

    const hoverWeight = hoverTime !== null ? nearestByTime(weightPoints, p => parseLocalDate(p.date).getTime(), hoverTime) : null;
    const hoverPain = hoverTime !== null ? nearestByTime(painWeekly, b => parseLocalDate(b.weekStart).getTime(), hoverTime) : null;
    const hoverKm = hoverTime !== null ? nearestByTime(kmWeekly, b => parseLocalDate(b.weekStart).getTime(), hoverTime) : null;
    const hoverDateLabel = hoverTime !== null ? formatShortDate(formatLocalISO(new Date(hoverTime))) : null;
    const hoverX = hoverTime !== null ? xForTime(hoverTime) : null;

    if (showTable) {
        const weekStarts = [...new Set([...painWeekly.map(b => b.weekStart), ...kmWeekly.map(b => b.weekStart)])].sort();
        return (
            <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
                <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(false)} />
                <p className={`${labelClasses} mb-2`}>Gráfico integrado — por semana</p>
                <ChartDataTable
                    columns={['Semana', 'Peso méd. 7d (kg)', 'Dor média', 'Km na semana']}
                    rows={weekStarts.map(ws => [
                        formatShortDate(ws),
                        nearestByTime(weightPoints, p => parseLocalDate(p.date).getTime(), parseLocalDate(ws).getTime())?.value.toFixed(1).replace('.', ',') ?? '-',
                        painWeekly.find(b => b.weekStart === ws)?.average.toFixed(1).replace('.', ',') ?? '-',
                        kmWeekly.find(b => b.weekStart === ws)?.sum.toFixed(1).replace('.', ',') ?? '-',
                    ])}
                />
            </div>
        );
    }

    return (
        <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
            <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(true)} />
            {hoverTime !== null && hoverPos && (
                <ChartTooltip x={hoverPos.x} y={hoverPos.y - 12}>
                    <div>{hoverDateLabel}</div>
                    {hoverWeight && <div>Peso (méd. 7d): {hoverWeight.value.toFixed(1).replace('.', ',')} kg</div>}
                    {hoverPain && <div>Dor média sem.: {hoverPain.average.toFixed(1).replace('.', ',')}</div>}
                    {hoverKm && <div>Km na semana: {hoverKm.sum.toFixed(1).replace('.', ',')} km</div>}
                </ChartTooltip>
            )}
            <div
                className="touch-none"
                onMouseMove={handleMouseMove}
                onMouseLeave={handleLeave}
                onTouchMove={handleTouchMove}
                onTouchEnd={handleLeave}
            >
                <svg viewBox={`0 0 ${width} ${totalHeight}`} className="w-full overflow-visible" role="img" aria-label="Gráfico integrado de peso, dor e caminhada">
                    {/* Grade vertical do eixo X compartilhado, atravessando os 3 painéis */}
                    {axisTimes.map(t => (
                        <line key={t} x1={xForTime(t)} x2={xForTime(t)} y1={weightPlotY} y2={gridBottomY} stroke={palette.grid} strokeWidth="1" opacity="0.6" />
                    ))}

                    {/* Painel 1 — Peso */}
                    <text x={padLeft} y={weightHeaderY + 11} fontSize="10" fontWeight="700" fill={palette.text} textAnchor="start">
                        {weightPoints.length && (weightPoints[weightPoints.length - 1].count ?? 4) >= 4 ? 'PESO — MÉDIA 7D' : 'PESO — ÚLTIMO REGISTRO'}
                    </text>
                    <text x={padLeft + plotWidth} y={weightHeaderY + 11} fontSize="11" fontWeight="700" fill={palette.line} textAnchor="end">
                        {weightPoints.length ? `${weightPoints[weightPoints.length - 1].value.toFixed(1).replace('.', ',')} kg` : '—'}
                    </text>
                    <rect x={padLeft} y={weightPlotY} width={plotWidth} height={weightH} fill={palette.bg} stroke={palette.grid} strokeWidth="1" rx="10" />
                    {weightTicks.map((tick, i) => (
                        <g key={i}>
                            <line x1={padLeft} x2={padLeft + plotWidth} y1={yForWeight(tick)} y2={yForWeight(tick)} stroke={palette.grid} strokeWidth="1" />
                            <text x={padLeft - 6} y={yForWeight(tick) + 3} fontSize="9" fill={palette.text} textAnchor="end">{tick.toFixed(1).replace('.', ',')}</text>
                        </g>
                    ))}
                    {weightPoints.length >= 2 && <polyline points={weightPath} fill="none" stroke={palette.line} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />}
                    {weightScaleExpanded && (
                        <text x={padLeft + plotWidth} y={weightPlotY + weightH - 6} fontSize="8" fontStyle="italic" fill={palette.text} opacity="0.6" textAnchor="end">
                            escala ampliada — meta {targetWeight} kg fora do intervalo visível
                        </text>
                    )}

                    {/* Painel 2 — Dor */}
                    <text x={padLeft} y={painHeaderY + 11} fontSize="10" fontWeight="700" fill={palette.text} textAnchor="start">DOR MÉDIA SEMANAL (0–10)</text>
                    <text x={padLeft + plotWidth} y={painHeaderY + 11} fontSize="11" fontWeight="700" fill={palette.amber} textAnchor="end">
                        {painWeekly.length ? painWeekly[painWeekly.length - 1].average.toFixed(1).replace('.', ',') : '—'}
                    </text>
                    <rect x={padLeft} y={painPlotY} width={plotWidth} height={painH} fill={palette.bg} stroke={palette.grid} strokeWidth="1" rx="10" />
                    {painTicks.map(tick => (
                        <g key={tick}>
                            <line x1={padLeft} x2={padLeft + plotWidth} y1={yForPain(tick)} y2={yForPain(tick)} stroke={palette.grid} strokeWidth="1" />
                            <text x={padLeft - 6} y={yForPain(tick) + 3} fontSize="9" fill={palette.text} textAnchor="end">{tick}</text>
                        </g>
                    ))}
                    {painWeekly.length >= 2 && <polyline points={painPath} fill="none" stroke={palette.amber} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />}
                    {painWeekly.map((b, i) => (
                        (i === 0 || i === painWeekly.length - 1 || (hoverPain && hoverPain.weekStart === b.weekStart)) && (
                            <circle key={b.weekStart} cx={xForDate(b.weekStart)} cy={yForPain(b.average)} r="3.5" fill={palette.point} stroke={palette.amber} strokeWidth="2" />
                        )
                    ))}

                    {/* Painel 3 — Km */}
                    <text x={padLeft} y={kmHeaderY + 11} fontSize="10" fontWeight="700" fill={palette.text} textAnchor="start">KM CAMINHADOS POR SEMANA</text>
                    <text x={padLeft + plotWidth} y={kmHeaderY + 11} fontSize="11" fontWeight="700" fill={palette.emerald} textAnchor="end">
                        {kmWeekly.length ? `${kmWeekly[kmWeekly.length - 1].sum.toFixed(1).replace('.', ',')} km` : '—'}
                    </text>
                    <rect x={padLeft} y={kmPlotY} width={plotWidth} height={kmH} fill={palette.bg} stroke={palette.grid} strokeWidth="1" rx="10" />
                    {kmTicks.map((tick, i) => (
                        <g key={i}>
                            <line x1={padLeft} x2={padLeft + plotWidth} y1={yForKm(tick)} y2={yForKm(tick)} stroke={palette.grid} strokeWidth="1" />
                            <text x={padLeft - 6} y={yForKm(tick) + 3} fontSize="9" fill={palette.text} textAnchor="end">{tick.toFixed(0).replace('.', ',')}</text>
                        </g>
                    ))}
                    {kmWeekly.length > 0 ? kmWeekly.map(b => {
                        const x = xForDate(b.weekStart) - kmBarWidth / 2;
                        const y = yForKm(b.sum);
                        const h = Math.max(0, kmPlotY + kmH - y);
                        return <rect key={b.weekStart} x={x} y={y} width={kmBarWidth} height={h} rx="3" fill={palette.emerald} />;
                    }) : (
                        <text x={padLeft + plotWidth / 2} y={kmPlotY + kmH / 2} fontSize="10" fill={palette.text} opacity="0.5" textAnchor="middle">sem registro no período</text>
                    )}

                    {/* Eixo X compartilhado */}
                    {axisTimes.map((t, i) => (
                        <text
                            key={t}
                            x={xForTime(t)}
                            y={xAxisY}
                            fontSize="10"
                            fontWeight="700"
                            fill={palette.text}
                            textAnchor={i === 0 ? 'start' : i === axisTimes.length - 1 ? 'end' : 'middle'}
                        >
                            {formatShortDate(formatLocalISO(new Date(t)))}
                        </text>
                    ))}

                    {/* Faixa de densidade das sessões recorrentes — presença sem numeração,
                        sem linha vertical cruzando os painéis (com dezenas de sessões, as
                        linhas por si só voltariam a poluir o eixo) */}
                    {recurringLayout.map(({ event, x }) => (
                        <circle key={event.id} cx={x} cy={eventTrackTop + eventTrackH - 3} r="1.75" fill={palette.text} opacity="0.3">
                            <title>{`${event.label} — ${formatShortDate(event.date)}`}</title>
                        </circle>
                    ))}

                    {/* Trilha de eventos pontuais — desenhada por cima dos painéis, nunca embaixo */}
                    {eventLayout.map(({ event, x, number }) => {
                        const pinY = eventTrackTop + 12;
                        return (
                            <g key={event.id}>
                                <line x1={x} x2={x} y1={weightPlotY} y2={gridBottomY} stroke={palette.text} strokeOpacity="0.2" strokeWidth="1.25" strokeDasharray="3 3" />
                                <circle cx={x} cy={pinY} r="7" fill={palette.bg} stroke={palette.text} strokeWidth="1.25" opacity="0.9" />
                                <text x={x} y={pinY + 3} fontSize="8" fontWeight="700" fill={palette.text} textAnchor="middle">{number}</text>
                                <title>{`${number}. ${event.label} — ${formatShortDate(event.date)}`}</title>
                            </g>
                        );
                    })}

                    {/* Crosshair — camada de overlay, sempre por cima de tudo */}
                    {hoverX !== null && (
                        <line x1={hoverX} x2={hoverX} y1={weightPlotY} y2={gridBottomY} stroke={palette.line} strokeOpacity="0.5" strokeWidth="1.5" />
                    )}
                </svg>
            </div>
        </div>
    );
};

const RADICULAR_CATEGORIES: RadicularLocation[] = ['gluteo', 'quadril', 'coxa', 'joelho', 'panturrilha', 'tornozelo', 'pe'];

const RadicularTimelineChart = ({
    points,
    isDark = false,
}: {
    points: { date: string; location: RadicularLocation; side?: RadicularSide; intensity?: number }[];
    isDark?: boolean;
}) => {
    const [showTable, setShowTable] = useState(false);
    const palette = chartPalette(isDark);

    if (points.length < 1) {
        return (
            <div className="flex h-[200px] items-center justify-center rounded-2xl border border-dashed border-border-standard bg-background text-sm font-semibold text-on-surface-variant">
                Ainda não há registros de sintoma radicular neste período.
            </div>
        );
    }

    const width = 720;
    const height = 220;
    const pad = { top: 16, right: 18, bottom: 30, left: 90 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;

    const minDate = points[0].date;
    const maxDate = points[points.length - 1].date;
    const minTime = parseLocalDate(minDate).getTime();
    const maxTime = Math.max(parseLocalDate(maxDate).getTime(), minTime + 1);
    const totalSpan = Math.max(1, maxTime - minTime);
    const xForDate = (d: string) => pad.left + ((parseLocalDate(d).getTime() - minTime) / totalSpan) * plotWidth;
    const yForLocation = (loc: RadicularLocation) => {
        const idx = Math.max(0, RADICULAR_CATEGORIES.indexOf(loc));
        return pad.top + plotHeight - (idx / (RADICULAR_CATEGORIES.length - 1)) * plotHeight;
    };
    const sideColor = (side?: RadicularSide) =>
        side === 'direito' ? palette.line : side === 'esquerdo' ? palette.amber : side === 'ambos' ? palette.trajectory : palette.text;
    const linePath = points.map(p => `${xForDate(p.date)},${yForLocation(p.location)}`).join(' ');

    if (showTable) {
        return (
            <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
                <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(false)} />
                <p className={`${labelClasses} mb-2`}>Evolução do sintoma radicular</p>
                <ChartDataTable
                    columns={['Data', 'Local', 'Lado', 'Intensidade']}
                    rows={points.map(p => [
                        formatShortDate(p.date),
                        RADICULAR_LOCATIONS.find(l => l.value === p.location)?.label || p.location,
                        p.side || '-',
                        p.intensity ?? '-',
                    ])}
                />
            </div>
        );
    }

    return (
        <div className="relative rounded-2xl border border-border-subtle bg-background p-4">
            <ChartTableToggle showTable={showTable} onToggle={() => setShowTable(true)} />
            <svg viewBox={`0 0 ${width} ${height}`} className="h-[220px] w-full overflow-visible" role="img" aria-label="Evolução do sintoma radicular ao longo do tempo">
                <rect x="0" y="0" width={width} height={height} rx="16" fill={palette.bg} />
                {RADICULAR_CATEGORIES.map(cat => (
                    <g key={cat}>
                        <line x1={pad.left} x2={width - pad.right} y1={yForLocation(cat)} y2={yForLocation(cat)} stroke={palette.grid} strokeWidth="1" />
                        <text x={pad.left - 8} y={yForLocation(cat) + 3} textAnchor="end" fontSize="10" fontWeight="600" fill={palette.text}>
                            {RADICULAR_LOCATIONS.find(l => l.value === cat)?.label}
                        </text>
                    </g>
                ))}
                <polyline points={linePath} fill="none" stroke={palette.text} strokeOpacity="0.25" strokeWidth="1.5" />
                {points.map((p, i) => (
                    <circle
                        key={`${p.date}-${i}`}
                        cx={xForDate(p.date)}
                        cy={yForLocation(p.location)}
                        r={3 + (p.intensity ?? 0) * 0.5}
                        fill={sideColor(p.side)}
                        stroke={palette.point}
                        strokeWidth="1.5"
                    >
                        <title>{`${formatShortDate(p.date)}: ${RADICULAR_LOCATIONS.find(l => l.value === p.location)?.label}${p.side ? ` (${p.side})` : ''}${p.intensity !== undefined ? ` — intensidade ${p.intensity}/10` : ''}`}</title>
                    </circle>
                ))}
                {minDate === maxDate ? (
                    <text x={xForDate(minDate)} y={height - 10} textAnchor="middle" fontSize="10" fontWeight="700" fill={palette.text}>{formatShortDate(minDate)}</text>
                ) : (
                    <>
                        <text x={xForDate(minDate)} y={height - 10} textAnchor="start" fontSize="10" fontWeight="700" fill={palette.text}>{formatShortDate(minDate)}</text>
                        <text x={xForDate(maxDate)} y={height - 10} textAnchor="end" fontSize="10" fontWeight="700" fill={palette.text}>{formatShortDate(maxDate)}</text>
                    </>
                )}
            </svg>
            <div className="mt-2 flex flex-wrap gap-3 text-[10px] font-semibold text-on-surface-variant">
                <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: palette.line }} />Direito</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: palette.amber }} />Esquerdo</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: palette.trajectory }} />Ambos</span>
            </div>
        </div>
    );
};

const HealthView: React.FC<HealthViewProps> = ({
    weights, settings, onUpdateSettings, onAddWeight, onUpdateWeight, onDeleteWeight,
    waist, onAddWaist, onDeleteWaist,
    events, onAddEvent, onDeleteEvent, latestWeeklySummary, weeklyReports = [],
    exerciseLogs, onSaveExerciseLog, exams, onAddExam, onDeleteExam, onUpdateExam,
    telegramReminders, onSaveTelegramReminder, onDeleteTelegramReminder,
    isDark = false
}) => {
    const [selectedDate, setSelectedDate] = useState<string>(formatDateLocalISO(new Date()));
    const [activeTab, setActiveTab] = useState<'overview' | 'records' | 'charts' | 'reminders' | 'report' | 'archive'>('overview');
    const [weightInput, setWeightInput] = useState<string>('');
    const [waistInput, setWaistInput] = useState<string>('');
    const [editingWeightId, setEditingWeightId] = useState<string | null>(null);
    const [editWeightValue, setEditWeightValue] = useState<string>('');
    const [editWeightDate, setEditWeightDate] = useState<string>('');
    const [editingBlockId, setEditingBlockId] = useState<string | null>(null);
    const [editBlockDistance, setEditBlockDistance] = useState<string>('');
    const [editBlockMinutes, setEditBlockMinutes] = useState<string>('');
    const [editBlockSteps, setEditBlockSteps] = useState<string>('');
    const [editBlockCalories, setEditBlockCalories] = useState<string>('');
    const [integratedRangeDays, setIntegratedRangeDays] = useState<number | null>(90);
    const [isReportOpen, setIsReportOpen] = useState<boolean>(false);
    const [isAddExamOpen, setIsAddExamOpen] = useState<boolean>(false);
    const addExamTituloRef = useRef<HTMLInputElement>(null);
    const addExamTriggerRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        if (!isAddExamOpen) return;
        addExamTituloRef.current?.focus();
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setIsAddExamOpen(false);
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
            addExamTriggerRef.current?.focus();
        };
    }, [isAddExamOpen]);

    const [isAddReminderOpen, setIsAddReminderOpen] = useState<boolean>(false);
    const [newReminderTitle, setNewReminderTitle] = useState('');
    const [newReminderMessage, setNewReminderMessage] = useState('');
    const [newReminderTime, setNewReminderTime] = useState('08:00');
    const [newReminderDays, setNewReminderDays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6]);
    const addReminderTituloRef = useRef<HTMLInputElement>(null);
    const addReminderTriggerRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        if (!isAddReminderOpen) return;
        addReminderTituloRef.current?.focus();
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setIsAddReminderOpen(false);
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
            addReminderTriggerRef.current?.focus();
        };
    }, [isAddReminderOpen]);

    // Grava só ao confirmar no modal — o botão antigo criava o lembrete na hora do
    // clique ("Novo lembrete", 08:00, todo dia), sem dar chance de escolher nada antes
    // de já existir no Firestore. Foi assim que 7 lembretes duplicados nasceram.
    const handleCreateReminder = () => {
        const title = newReminderTitle.trim();
        if (!title) return;
        onSaveTelegramReminder({
            id: `custom_${Date.now()}`,
            title,
            message: newReminderMessage.trim() || 'André, lembrete de saúde configurado no Hermes.',
            time: newReminderTime,
            enabled: true,
            daysOfWeek: newReminderDays.length ? newReminderDays : [0, 1, 2, 3, 4, 5, 6],
            category: 'custom',
            telegramOnly: true,
        });
        setNewReminderTitle('');
        setNewReminderMessage('');
        setNewReminderTime('08:00');
        setNewReminderDays([0, 1, 2, 3, 4, 5, 6]);
        setIsAddReminderOpen(false);
    };
    const [guidedMode, setGuidedMode] = useState<'morning' | 'night' | null>(null);
    const [guidedStep, setGuidedStep] = useState<number>(0);
    const guidedTriggerRef = useRef<HTMLButtonElement | null>(null);
    const guidedStepContentRef = useRef<HTMLDivElement>(null);
    const [eventDate, setEventDate] = useState<string>(formatDateLocalISO(new Date()));
    const [eventType, setEventType] = useState<HealthEventType>('fisioterapia');
    const [eventLabel, setEventLabel] = useState<string>('');
    const [walkDistanceInput, setWalkDistanceInput] = useState<string>('');
    const [walkMinutesInput, setWalkMinutesInput] = useState<string>('');
    const [walkStepsInput, setWalkStepsInput] = useState<string>('');
    const [walkCaloriesInput, setWalkCaloriesInput] = useState<string>('');
    const [examTitulo, setExamTitulo] = useState<string>('');
    const [examTipo, setExamTipo] = useState<HealthExamTipo>('exame');
    const [examData, setExamData] = useState<string>(formatDateLocalISO(new Date()));
    const [examDoutorLocal, setExamDoutorLocal] = useState<string>('');
    const [examResultados, setExamResultados] = useState<string>('');
    const [examAchadosChave, setExamAchadosChave] = useState<string>('');
    const [examProfissional, setExamProfissional] = useState<string>('');
    const [examEspecialidade, setExamEspecialidade] = useState<string>('');
    const [examProximaReavaliacao, setExamProximaReavaliacao] = useState<string>('');
    const [examTags, setExamTags] = useState<string>('');
    const [examFiles, setExamFiles] = useState<File[]>([]);
    const [isSavingExam, setIsSavingExam] = useState<boolean>(false);
    const [editingExamId, setEditingExamId] = useState<string | null>(null);
    const [editTitulo, setEditTitulo] = useState<string>('');
    const [editTipo, setEditTipo] = useState<HealthExamTipo>('exame');
    const [editData, setEditData] = useState<string>('');
    const [editDoutorLocal, setEditDoutorLocal] = useState<string>('');
    const [editResultados, setEditResultados] = useState<string>('');
    const [editAchadosChave, setEditAchadosChave] = useState<string>('');
    const [editProfissional, setEditProfissional] = useState<string>('');
    const [editEspecialidade, setEditEspecialidade] = useState<string>('');
    const [editProximaReavaliacao, setEditProximaReavaliacao] = useState<string>('');
    const [editTags, setEditTags] = useState<string>('');
    const [editFiles, setEditFiles] = useState<File[]>([]);
    const [isSavingEditExam, setIsSavingEditExam] = useState<boolean>(false);

    const sortedWeights = useMemo(() => [...weights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()), [weights]);
    const currentWeight = sortedWeights[0]?.weight || 0;
    const targetDelta = settings.targetWeight && currentWeight ? currentWeight - settings.targetWeight : null;
    const weightHeadline = useMemo(
        () => computeWeightHeadline(weights.map(w => ({ date: w.date, value: w.weight }))),
        [weights]
    );

    const sortedWaist = useMemo(() => [...waist].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()), [waist]);

    const sortedExams = useMemo(
        () => [...exams].sort((a, b) => new Date(b.data).getTime() - new Date(a.data).getTime()),
        [exams]
    );

    const radicularSeries = useMemo(() => {
        return exerciseLogs
            .filter(l => l.radicular && l.radicular.location !== 'nenhum')
            .map(l => ({ date: l.id, location: l.radicular!.location, side: l.radicular!.side, intensity: l.radicular!.intensity }))
            .sort((a, b) => a.date.localeCompare(b.date));
    }, [exerciseLogs]);

    const integratedRangeStart = useMemo(
        () => (integratedRangeDays === null ? null : addDays(formatDateLocalISO(new Date()), -integratedRangeDays)),
        [integratedRangeDays]
    );
    const weightForIntegrated = useMemo(() => {
        const filtered = weights.filter(w => !integratedRangeStart || w.date >= integratedRangeStart);
        return movingAverage(filtered.map(w => ({ date: w.date, value: w.weight })), 7).map(p => ({ date: p.date, value: p.average as number, count: p.count }));
    }, [weights, integratedRangeStart]);
    const painWeeklyForIntegrated = useMemo(() => {
        const dailyPain = exerciseLogs
            .filter(l => (!integratedRangeStart || l.id >= integratedRangeStart) && (l.pain?.morning !== undefined || l.pain?.evening !== undefined))
            .map(l => {
                const vals = [l.pain?.morning, l.pain?.evening].filter((v): v is number => v !== undefined);
                return { date: l.id, value: vals.reduce((s, v) => s + v, 0) / vals.length };
            });
        return weeklyAggregate(dailyPain);
    }, [exerciseLogs, integratedRangeStart]);
    const kmWeeklyForIntegrated = useMemo(() => {
        const dailyKm = exerciseLogs
            .filter(l => !integratedRangeStart || l.id >= integratedRangeStart)
            .map(l => ({ date: l.id, value: sumWalkBlocksKm(l) }));
        const aggregated = weeklyAggregate(dailyKm);
        if (dailyKm.length === 0) return aggregated;
        // Preenche semanas sem nenhum registro com 0 km, em vez de omiti-las — evita que o
        // painel de km fique com grandes lacunas quando há poucas caminhadas na janela.
        const rangeStartDate = integratedRangeStart ?? dailyKm.reduce((min, p) => (p.date < min ? p.date : min), dailyKm[0].date);
        const byWeek = new Map(aggregated.map(b => [b.weekStart, b]));
        const cursor = parseLocalDate(rangeStartDate);
        const cursorDay = cursor.getDay();
        cursor.setDate(cursor.getDate() + (cursorDay === 0 ? -6 : 1 - cursorDay));
        const end = new Date();
        const filled: WeeklyBucket[] = [];
        while (cursor <= end) {
            const weekStart = formatLocalISO(cursor);
            filled.push(byWeek.get(weekStart) ?? { weekStart, values: [], sum: 0, average: 0, count: 0 });
            cursor.setDate(cursor.getDate() + 7);
        }
        return filled;
    }, [exerciseLogs, integratedRangeStart]);
    const eventsForIntegrated = useMemo(() => {
        const manual = events
            .filter(e => !integratedRangeStart || e.date >= integratedRangeStart)
            .map(e => ({ ...e, source: e.source ?? 'manual' as const }));
        // Todo registro do arquivo médico com data vira automaticamente um marcador —
        // derivado aqui na leitura, não duplicado no Firestore, para nunca ficar
        // dessincronizado se o exame for editado ou removido.
        const fromExams = exams
            .filter(e => e.data && (!integratedRangeStart || e.data >= integratedRangeStart))
            .map(e => ({ id: `exam_${e.id}`, date: e.data, type: 'consulta_medica' as HealthEventType, label: e.titulo, source: 'exam' as const }));
        return [...manual, ...fromExams].sort((a, b) => a.date.localeCompare(b.date));
    }, [events, exams, integratedRangeStart]);

    const logsInReportPeriod = useMemo(
        () => exerciseLogs.filter(l => !integratedRangeStart || l.id >= integratedRangeStart),
        [exerciseLogs, integratedRangeStart]
    );
    const radicularSeriesInPeriod = useMemo(
        () => radicularSeries.filter(p => !integratedRangeStart || p.date >= integratedRangeStart),
        [radicularSeries, integratedRangeStart]
    );
    const examsInReportPeriod = useMemo(
        () => sortedExams.filter(e => !integratedRangeStart || e.data >= integratedRangeStart),
        [sortedExams, integratedRangeStart]
    );
    const medUsageInPeriod = useMemo(() => {
        let pregabalinaDays = 0, fexofenadinaDays = 0, dipironaTotal = 0, adorlanTotal = 0;
        const outrosSet = new Set<string>();
        logsInReportPeriod.forEach(l => {
            const meds = l.meds;
            if (!meds) return;
            if (meds.pregabalina) pregabalinaDays++;
            if (meds.fexofenadina) fexofenadinaDays++;
            dipironaTotal += meds.dipirona || 0;
            adorlanTotal += meds.adorlan || 0;
            if (meds.outros) outrosSet.add(meds.outros);
        });
        return { pregabalinaDays, fexofenadinaDays, dipironaTotal, adorlanTotal, outros: [...outrosSet], totalDays: logsInReportPeriod.length };
    }, [logsInReportPeriod]);
    const adherenceInPeriod = useMemo(() => {
        const dietDays = logsInReportPeriod.filter(l => l.nutrition?.plan === 'sim').length;
        const strengthSessions = logsInReportPeriod.filter(l => l.strength?.done).length;
        const kmTotal = logsInReportPeriod.reduce((s, l) => s + sumWalkBlocksKm(l), 0);
        const painValues = logsInReportPeriod.flatMap(l => [l.pain?.morning, l.pain?.evening].filter((v): v is number => v !== undefined));
        const avgPain = painValues.length ? painValues.reduce((s, v) => s + v, 0) / painValues.length : null;
        return { dietDays, strengthSessions, kmTotal, avgPain, totalDays: logsInReportPeriod.length };
    }, [logsInReportPeriod]);

    const handleAddEvent = async () => {
        const label = eventLabel.trim();
        if (!label || !eventDate) return;
        await onAddEvent({ date: eventDate, type: eventType, label });
        setEventLabel('');
    };

    const todayLog = useMemo(() => exerciseLogs.find(l => l.id === selectedDate) || { id: selectedDate }, [exerciseLogs, selectedDate]);
    const selectedDateLabel = formatDate(selectedDate);
    const isRedFlagActive = Boolean(
        todayLog.radicular?.location === 'pe' ||
        todayLog.radicular?.motorWeakness === true ||
        (todayLog.pain?.morning ?? 0) >= 9 ||
        (todayLog.pain?.evening ?? 0) >= 9
    );
    const previousMedsLog = useMemo(
        () => [...exerciseLogs].filter(log => log.id < selectedDate && log.meds).sort((a, b) => b.id.localeCompare(a.id))[0],
        [exerciseLogs, selectedDate]
    );

    useEffect(() => {
        if (!todayLog.meds && previousMedsLog?.meds) {
            onSaveExerciseLog(selectedDate, { meds: previousMedsLog.meds });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedDate, todayLog.meds, previousMedsLog]);
    const weightMASeries = useMemo(() => {
        const sorted = [...weights].sort((a, b) => a.date.localeCompare(b.date));
        return movingAverage(sorted.map(w => ({ date: w.date, value: w.weight })), 7)
            .map(p => ({ date: p.date, value: p.average as number }));
    }, [weights]);
    const weightTrendPoints = useMemo(() => weightMASeries.slice(-60), [weightMASeries]);

    const ritmoAlvoKgSemana = settings.ritmoAlvoKgSemana ?? 0.6;
    const marcos = useMemo(() => (settings.marcos && settings.marcos.length ? settings.marcos : [92, 85.5, 80]), [settings.marcos]);
    const lastMAPoint = weightMASeries[weightMASeries.length - 1] || null;

    const trajectoryPoints = useMemo(() => {
        if (!lastMAPoint) return [];
        const slopePerDay = -ritmoAlvoKgSemana / 7;
        const weeks = 16;
        return Array.from({ length: weeks + 1 }, (_, w) => ({
            date: addDays(lastMAPoint.date, w * 7),
            value: lastMAPoint.value + slopePerDay * w * 7,
        }));
    }, [lastMAPoint, ritmoAlvoKgSemana]);

    const MIN_TREND_POINTS = 14;
    const recentWeightPoints = useMemo(() => {
        if (!lastMAPoint) return [];
        const cutoff = addDays(lastMAPoint.date, -28);
        return weightMASeries.filter(p => p.date >= cutoff);
    }, [weightMASeries, lastMAPoint]);

    const recentTrendRegression = useMemo(() => {
        if (recentWeightPoints.length < MIN_TREND_POINTS) return null;
        return linearRegression(recentWeightPoints.map(p => ({ x: daysSinceEpoch(p.date), y: p.value })));
    }, [recentWeightPoints]);

    const trendSlopePerDay = recentTrendRegression?.slope ?? 0;
    const trendIsDecreasing = trendSlopePerDay < -0.001;

    const trendPoints = useMemo(() => {
        if (!lastMAPoint || !recentTrendRegression) return [];
        const weeks = 16;
        const startDay = daysSinceEpoch(lastMAPoint.date);
        return Array.from({ length: weeks + 1 }, (_, w) => {
            const day = startDay + w * 7;
            return {
                date: addDays(lastMAPoint.date, w * 7),
                value: recentTrendRegression.intercept + recentTrendRegression.slope * day,
            };
        });
    }, [lastMAPoint, recentTrendRegression]);

    const weightProjectionLines = useMemo(() => {
        const lines: { key: string; label: string; color: 'trajectory' | 'trendLine'; points: { date: string; value: number }[] }[] = [];
        if (trajectoryPoints.length > 1) lines.push({ key: 'trajectory', label: 'trajetória alvo', color: 'trajectory', points: trajectoryPoints });
        if (trendIsDecreasing && trendPoints.length > 1) lines.push({ key: 'trend', label: 'tendência real', color: 'trendLine', points: trendPoints });
        return lines;
    }, [trajectoryPoints, trendPoints, trendIsDecreasing]);

    const dailyPainSeries = useMemo(() => {
        return exerciseLogs
            .filter(l => l.pain?.morning !== undefined || l.pain?.evening !== undefined)
            .map(l => {
                const vals = [l.pain?.morning, l.pain?.evening].filter((v): v is number => v !== undefined);
                return { log: l, pain: vals.reduce((s, v) => s + v, 0) / vals.length };
            });
    }, [exerciseLogs]);

    const correlationRows = useMemo(() => {
        const withWithoutSplit = (predicate: (log: ExerciseLog) => boolean): GroupComparison => {
            const withValues: number[] = [];
            const withoutValues: number[] = [];
            dailyPainSeries.forEach(({ log, pain }) => (predicate(log) ? withValues : withoutValues).push(pain));
            return compareGroups(withValues, withoutValues, 8);
        };

        const rows: { key: string; label: string; comparison: GroupComparison }[] = [
            { key: 'strength', label: 'treino de força', comparison: withWithoutSplit(l => !!l.strength?.done) },
            { key: 'pilates', label: 'pilates', comparison: withWithoutSplit(l => !!l.therapy?.includes('pilates')) },
            { key: 'fisioterapia', label: 'fisioterapia', comparison: withWithoutSplit(l => !!l.therapy?.includes('fisioterapia')) },
            { key: 'walk6km', label: 'caminhada acima de 6 km', comparison: withWithoutSplit(l => sumWalkBlocksKm(l) > 6) },
            { key: 'pregabalina', label: 'uso de pregabalina', comparison: withWithoutSplit(l => !!l.meds?.pregabalina) },
            { key: 'wokeInPain', label: 'despertar com dor', comparison: withWithoutSplit(l => !!l.sleepQuality?.wokeInPain) },
        ];

        TRIGGER_TYPES.forEach(trigger => {
            if (exerciseLogs.some(l => l.triggers?.types?.includes(trigger.value))) {
                rows.push({
                    key: `trigger_${trigger.value}`,
                    label: `gatilho "${trigger.label.toLowerCase()}"`,
                    comparison: withWithoutSplit(l => !!l.triggers?.types?.includes(trigger.value)),
                });
            }
        });

        return rows;
    }, [dailyPainSeries, exerciseLogs]);

    const MAX_PROJECTION_DAYS = 548; // ~18 meses — além disso a extrapolação linear deixa de ser confiável
    const milestoneDates = useMemo(() => {
        if (!lastMAPoint) return [];
        return marcos.map(target => {
            if (!trendIsDecreasing) return { target, dateStr: null as string | null };
            const days = daysToReachTarget(lastMAPoint.value, trendSlopePerDay, target);
            if (days === null || days > MAX_PROJECTION_DAYS) return { target, dateStr: null as string | null };
            return { target, dateStr: addDays(lastMAPoint.date, days) };
        });
    }, [marcos, lastMAPoint, trendSlopePerDay, trendIsDecreasing]);
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
    // "walkingIdealKm" guarda o topo da faixa normal (4-6 km é dia normal; acima é
    // bônus, não meta a perseguir) — não é mais um teto a ser alcançado.
    const walkingIdealKm = settings.walkingIdealKm ?? 6;
    const isCrisisToday = !!todayLog.pain?.crisis;
    const selectedWalkBlocks = todayLog.walkBlocks || [];
    const selectedWalkKm = sumWalkBlocksKm(todayLog);
    const walkGapMinutes = (a?: string, b?: string): number | null => {
        if (!a || !b) return null;
        const [ah, am] = a.split(':').map(Number);
        const [bh, bm] = b.split(':').map(Number);
        if ([ah, am, bh, bm].some(Number.isNaN)) return null;
        return (bh * 60 + bm) - (ah * 60 + am);
    };
    const maiorIntervaloSemCaminharMin = useMemo(() => {
        const times = selectedWalkBlocks.map(b => b.time).filter((t): t is string => !!t).sort();
        if (times.length < 2) return null;
        let maxGap = -Infinity;
        for (let i = 1; i < times.length; i++) {
            const gap = walkGapMinutes(times[i - 1], times[i]);
            if (gap !== null) maxGap = Math.max(maxGap, gap);
        }
        return maxGap === -Infinity ? null : maxGap;
    }, [selectedWalkBlocks]);
    const todayWalkKm = useMemo(() => {
        const todayKey = formatDateLocalISO(new Date());
        return sumWalkBlocksKm(exerciseLogs.find(log => log.id === todayKey));
    }, [exerciseLogs]);
    const isCrisisTodayReal = useMemo(() => {
        const todayKey = formatDateLocalISO(new Date());
        return !!exerciseLogs.find(log => log.id === todayKey)?.pain?.crisis;
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

    const startEditWeight = (weight: HealthWeight) => {
        setEditingWeightId(weight.id);
        setEditWeightValue(String(weight.weight));
        setEditWeightDate(weight.date);
    };
    const cancelEditWeight = () => setEditingWeightId(null);
    const saveEditWeight = () => {
        if (!editingWeightId) return;
        const value = parseFloat(editWeightValue.replace(',', '.'));
        if (!isNaN(value) && value >= 30 && value <= 250 && editWeightDate) {
            onUpdateWeight(editingWeightId, value, editWeightDate);
            setEditingWeightId(null);
        }
    };

    const startEditBlock = (block: WalkBlock) => {
        setEditingBlockId(block.id);
        setEditBlockDistance(String(block.distance));
        setEditBlockMinutes(block.minutes ? String(block.minutes) : '');
        setEditBlockSteps(block.steps ? String(block.steps) : '');
        setEditBlockCalories(block.calories ? String(block.calories) : '');
    };
    const cancelEditBlock = () => setEditingBlockId(null);
    const saveEditBlock = async () => {
        if (!editingBlockId) return;
        const distance = parsePositiveNumber(editBlockDistance);
        if (!distance || distance > 50) return;
        const minutes = parsePositiveNumber(editBlockMinutes);
        const steps = parsePositiveNumber(editBlockSteps);
        const calories = parsePositiveNumber(editBlockCalories);
        const updatedBlocks = selectedWalkBlocks.map(b => b.id === editingBlockId
            ? {
                ...b,
                distance,
                minutes: minutes ? Math.round(minutes) : undefined,
                steps: steps ? Math.round(steps) : undefined,
                calories: calories ? Math.round(calories) : undefined,
            }
            : b
        );
        await onSaveExerciseLog(selectedDate, { walkBlocks: updatedBlocks });
        setEditingBlockId(null);
    };

    const handleAddWeight = () => {
        const value = parseFloat(weightInput.replace(',', '.'));
        if (!isNaN(value) && value >= 30 && value <= 250) {
            onAddWeight(value, selectedDate);
            setWeightInput('');
        }
    };

    const handleAddWaist = () => {
        const value = parseFloat(waistInput.replace(',', '.'));
        if (!isNaN(value) && value >= 50 && value <= 200) {
            onAddWaist(value, selectedDate);
            setWaistInput('');
        }
    };

    const updateRadicular = (patch: Partial<NonNullable<ExerciseLog['radicular']>>) => {
        const current: NonNullable<ExerciseLog['radicular']> = todayLog.radicular || { location: 'nenhum' };
        onSaveExerciseLog(selectedDate, { radicular: { ...current, ...patch } });
    };

    const updateStrength = (patch: Partial<NonNullable<ExerciseLog['strength']>>) => {
        const current: NonNullable<ExerciseLog['strength']> = todayLog.strength || { done: false };
        onSaveExerciseLog(selectedDate, { strength: { ...current, ...patch } });
    };

    const updateNutrition = (patch: Partial<NonNullable<ExerciseLog['nutrition']>>) => {
        const current: NonNullable<ExerciseLog['nutrition']> = todayLog.nutrition || { plan: 'nao', proteinTarget: false };
        onSaveExerciseLog(selectedDate, { nutrition: { ...current, ...patch } });
    };

    const updateSleepQuality = (patch: Partial<NonNullable<ExerciseLog['sleepQuality']>>) => {
        const current: NonNullable<ExerciseLog['sleepQuality']> = todayLog.sleepQuality || { wokeInPain: false };
        onSaveExerciseLog(selectedDate, { sleepQuality: { ...current, ...patch } });
    };

    const updateMeds = (patch: Partial<NonNullable<ExerciseLog['meds']>>) => {
        const current: NonNullable<ExerciseLog['meds']> = todayLog.meds || { pregabalina: false, dipirona: 0, adorlan: 0, fexofenadina: false };
        onSaveExerciseLog(selectedDate, { meds: { ...current, ...patch } });
    };

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
                    // '' e não undefined — o Firestore rejeita addDoc/updateDoc com campo undefined
                    doutor_local: examDoutorLocal.trim(),
                    resultados: examResultados.trim(),
                    achadosChave: examAchadosChave.trim(),
                    profissional: examProfissional.trim(),
                    especialidade: examEspecialidade.trim(),
                    proximaReavaliacao: examProximaReavaliacao,
                    tags: examTags.split(',').map(t => t.trim()).filter(Boolean),
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
            setExamAchadosChave('');
            setExamProfissional('');
            setExamEspecialidade('');
            setExamProximaReavaliacao('');
            setExamTags('');
            setExamFiles([]);
            setIsAddExamOpen(false);
        } catch (err) {
            console.error('Falha ao adicionar registro de saúde:', err);
        } finally {
            setIsSavingExam(false);
        }
    };

    const startEditExam = (exam: HealthExam) => {
        setEditingExamId(exam.id);
        setEditTitulo(exam.titulo);
        setEditTipo(exam.tipo);
        setEditData(exam.data);
        setEditDoutorLocal(exam.doutor_local || '');
        setEditResultados(exam.resultados || '');
        setEditAchadosChave(exam.achadosChave || '');
        setEditProfissional(exam.profissional || '');
        setEditEspecialidade(exam.especialidade || '');
        setEditProximaReavaliacao(exam.proximaReavaliacao || '');
        setEditTags((exam.tags || []).join(', '));
        setEditFiles([]);
    };

    const cancelEditExam = () => {
        setEditingExamId(null);
        setEditFiles([]);
    };

    const handleSaveEditExam = async () => {
        const titulo = editTitulo.trim();
        if (!editingExamId || !titulo || !editData || isSavingEditExam) return;
        setIsSavingEditExam(true);
        try {
            await onUpdateExam(
                editingExamId,
                {
                    titulo,
                    tipo: editTipo,
                    data: editData,
                    // '' e não undefined — permite limpar o campo na edição e evita o erro de
                    // "Unsupported field value: undefined" do Firestore
                    doutor_local: editDoutorLocal.trim(),
                    resultados: editResultados.trim(),
                    achadosChave: editAchadosChave.trim(),
                    profissional: editProfissional.trim(),
                    especialidade: editEspecialidade.trim(),
                    proximaReavaliacao: editProximaReavaliacao,
                    tags: editTags.split(',').map(t => t.trim()).filter(Boolean),
                },
                editFiles
            );
            setEditingExamId(null);
            setEditFiles([]);
        } catch (err) {
            console.error('Falha ao atualizar registro de saúde:', err);
        } finally {
            setIsSavingEditExam(false);
        }
    };

    const activeReminders = useMemo(() => {
        const byId = new Map(telegramReminders.map(reminder => [reminder.id, reminder]));
        DEFAULT_HEALTH_REMINDERS.forEach(reminder => {
            if (!byId.has(reminder.id)) byId.set(reminder.id, reminder);
        });
        return [...byId.values()].sort((a, b) => a.time.localeCompare(b.time));
    }, [telegramReminders]);

    const isStrengthTrainingDay = useMemo(() => {
        // O treino de força virou dois lembretes (dias/horários diferentes: seg+sex vs.
        // quarta, por causa da acupuntura) — precisa checar os dois ids, não só um.
        const todayJsDay = parseLocalDate(selectedDate).getDay();
        const strengthReminders = activeReminders.filter(r => r.id.startsWith('strength_training'));
        if (strengthReminders.length === 0) return [1, 3, 5].includes(todayJsDay);
        return strengthReminders.some(r => (r.daysOfWeek && r.daysOfWeek.length ? r.daysOfWeek : [1, 3, 5]).includes(todayJsDay));
    }, [selectedDate, activeReminders]);

    type GuidedStep = { id: string; skip?: () => boolean; answered: () => boolean; render: () => React.ReactNode };

    const morningSteps: GuidedStep[] = [
        {
            id: 'morning_pain',
            answered: () => todayLog.pain?.morning !== undefined,
            render: () => (
                <div>
                    <p className="text-4xl font-bold text-center text-on-surface">{todayLog.pain?.morning ?? '—'}<span className="text-base font-semibold text-on-surface-variant">/10</span></p>
                    <input type="range" min="0" max="10" value={todayLog.pain?.morning ?? 0} onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, morning: parseInt(e.target.value) } })} className={`mt-4 w-full accent-primary-container ${todayLog.pain?.morning === undefined ? 'opacity-40' : ''}`} />
                    {todayLog.pain?.morning === undefined && <p className="mt-2 text-center text-xs font-semibold text-on-surface-variant">Arraste o slider para responder</p>}
                </div>
            ),
        },
        {
            id: 'morning_afterwalk',
            answered: () => todayLog.pain?.afterWalk !== undefined,
            render: () => (
                <div>
                    <p className="text-4xl font-bold text-center text-on-surface">{todayLog.pain?.afterWalk ?? '—'}<span className="text-base font-semibold text-on-surface-variant">/10</span></p>
                    <input type="range" min="0" max="10" value={todayLog.pain?.afterWalk ?? 0} onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, afterWalk: parseInt(e.target.value) } })} className={`mt-4 w-full accent-primary-container ${todayLog.pain?.afterWalk === undefined ? 'opacity-40' : ''}`} />
                    {todayLog.pain?.afterWalk === undefined && <p className="mt-2 text-center text-xs font-semibold text-on-surface-variant">Arraste o slider para responder</p>}
                </div>
            ),
        },
        {
            id: 'morning_woke',
            answered: () => todayLog.sleepQuality?.wokeInPain !== undefined,
            render: () => (
                <ChipGroup
                    options={[{ value: 'sim', label: 'Sim' }, { value: 'nao', label: 'Não' }]}
                    value={todayLog.sleepQuality?.wokeInPain === undefined ? undefined : (todayLog.sleepQuality.wokeInPain ? 'sim' : 'nao')}
                    onChange={(v: 'sim' | 'nao') => updateSleepQuality({ wokeInPain: v === 'sim' })}
                    deselectable={false}
                />
            ),
        },
        {
            id: 'morning_quality',
            answered: () => todayLog.sleepQuality?.quality !== undefined,
            render: () => (
                <ChipGroup
                    options={[1, 2, 3, 4, 5].map(q => ({ value: String(q), label: String(q) }))}
                    value={todayLog.sleepQuality?.quality ? String(todayLog.sleepQuality.quality) : undefined}
                    onChange={(v: string) => updateSleepQuality({ quality: parseInt(v) })}
                    deselectable={false}
                />
            ),
        },
    ];

    const nightSteps: GuidedStep[] = [
        {
            id: 'night_pain',
            answered: () => todayLog.pain?.evening !== undefined,
            render: () => (
                <div>
                    <p className="text-4xl font-bold text-center text-on-surface">{todayLog.pain?.evening ?? '—'}<span className="text-base font-semibold text-on-surface-variant">/10</span></p>
                    <input type="range" min="0" max="10" value={todayLog.pain?.evening ?? 0} onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, evening: parseInt(e.target.value) } })} className={`mt-4 w-full accent-primary-container ${todayLog.pain?.evening === undefined ? 'opacity-40' : ''}`} />
                    {todayLog.pain?.evening === undefined && <p className="mt-2 text-center text-xs font-semibold text-on-surface-variant">Arraste o slider para responder</p>}
                </div>
            ),
        },
        {
            id: 'night_radicular',
            answered: () => !!todayLog.radicular?.location,
            render: () => (
                <div className="space-y-4">
                    <ChipGroup options={RADICULAR_LOCATIONS} value={todayLog.radicular?.location} onChange={(l: RadicularLocation) => updateRadicular({ location: l })} layout="stack" deselectable={false} />
                    {todayLog.radicular && todayLog.radicular.location !== 'nenhum' && (
                        <>
                            <div>
                                <span className={labelClasses}>Lado</span>
                                <div className="mt-1.5"><ChipGroup options={[{ value: 'direito', label: 'Direito' }, { value: 'esquerdo', label: 'Esquerdo' }, { value: 'ambos', label: 'Ambos' }]} value={todayLog.radicular.side} onChange={(s: RadicularSide) => updateRadicular({ side: s })} /></div>
                            </div>
                            <div>
                                <div className="flex items-baseline justify-between"><span className={labelClasses}>Intensidade</span><span className="text-sm font-bold text-on-surface">{todayLog.radicular.intensity ?? 0}/10</span></div>
                                <input type="range" min="0" max="10" value={todayLog.radicular.intensity ?? 0} onChange={e => updateRadicular({ intensity: parseInt(e.target.value) })} className="mt-1 w-full accent-primary-container" />
                            </div>
                        </>
                    )}
                </div>
            ),
        },
        {
            id: 'night_weakness',
            skip: () => !todayLog.radicular?.location || todayLog.radicular.location === 'nenhum',
            answered: () => todayLog.radicular?.motorWeakness !== undefined,
            render: () => (
                <ChipGroup
                    options={[{ value: 'sim', label: 'Sim' }, { value: 'nao', label: 'Não' }]}
                    value={todayLog.radicular?.motorWeakness === undefined ? undefined : (todayLog.radicular.motorWeakness ? 'sim' : 'nao')}
                    onChange={(v: 'sim' | 'nao') => updateRadicular({ motorWeakness: v === 'sim' })}
                    deselectable={false}
                />
            ),
        },
        {
            id: 'night_sciatica_crisis',
            answered: () => todayLog.pain?.sciatica !== undefined && todayLog.pain?.crisis !== undefined,
            render: () => (
                <div className="grid grid-cols-2 gap-3">
                    <button type="button" onClick={() => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, sciatica: !todayLog.pain?.sciatica } })} className={`rounded-xl border p-4 text-center transition ${todayLog.pain?.sciatica ? 'border-tertiary-container bg-tertiary-container text-on-tertiary-container' : 'border-border-subtle bg-background text-on-surface'}`}>
                        <span className={labelClasses}>Ciática</span>
                        <div className="mt-1 text-sm font-bold">{todayLog.pain?.sciatica ? 'Sim' : 'Não'}</div>
                    </button>
                    <button type="button" onClick={() => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, crisis: !todayLog.pain?.crisis } })} className={`rounded-xl border p-4 text-center transition ${todayLog.pain?.crisis ? 'border-error bg-error-container text-on-error-container' : 'border-border-subtle bg-background text-on-surface'}`}>
                        <span className={labelClasses}>Crise</span>
                        <div className="mt-1 text-sm font-bold">{todayLog.pain?.crisis ? 'Sim' : 'Não'}</div>
                    </button>
                </div>
            ),
        },
        {
            id: 'night_strength',
            skip: () => !isStrengthTrainingDay,
            answered: () => todayLog.strength?.done !== undefined,
            render: () => (
                <div className="space-y-3">
                    <ChipGroup
                        options={[{ value: 'sim', label: 'Feito' }, { value: 'nao', label: 'Não feito' }]}
                        value={todayLog.strength?.done === undefined ? undefined : (todayLog.strength.done ? 'sim' : 'nao')}
                        onChange={(v: 'sim' | 'nao') => updateStrength({ done: v === 'sim' })}
                        deselectable={false}
                    />
                    {todayLog.strength?.done && (
                        <ChipGroup options={[{ value: 'A', label: 'Bloco A' }, { value: 'B', label: 'Bloco B' }]} value={todayLog.strength?.block || undefined} onChange={(b: 'A' | 'B') => updateStrength({ block: b })} deselectable={false} />
                    )}
                </div>
            ),
        },
        {
            id: 'night_therapy',
            answered: () => todayLog.therapy !== undefined,
            render: () => (
                <ChipGroup options={THERAPY_MODALITIES} value={todayLog.therapy || []} onChange={(next: TherapyModality[]) => onSaveExerciseLog(selectedDate, { therapy: next })} multi />
            ),
        },
        {
            id: 'night_diet',
            answered: () => !!todayLog.nutrition?.plan,
            render: () => (
                <div className="space-y-3">
                    <ChipGroup options={[{ value: 'sim', label: 'Sim' }, { value: 'parcial', label: 'Parcial' }, { value: 'nao', label: 'Não' }]} value={todayLog.nutrition?.plan} onChange={(p: 'sim' | 'parcial' | 'nao') => updateNutrition({ plan: p })} deselectable={false} />
                    <button type="button" onClick={() => updateNutrition({ proteinTarget: !todayLog.nutrition?.proteinTarget })} className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${todayLog.nutrition?.proteinTarget ? 'border-primary-container bg-primary-container text-white' : 'border-border-standard bg-white text-on-surface-variant'}`}>
                        Proteína batida {todayLog.nutrition?.proteinTarget ? '✓' : ''}
                    </button>
                </div>
            ),
        },
        {
            id: 'night_meds',
            answered: () => todayLog.meds !== undefined,
            render: () => (
                <div className="grid grid-cols-2 gap-2">
                    <button type="button" onClick={() => updateMeds({ pregabalina: !todayLog.meds?.pregabalina })} className={`rounded-xl border p-3 text-left transition ${todayLog.meds?.pregabalina ? 'border-primary-container bg-primary-container text-white' : 'border-border-subtle bg-background text-on-surface'}`}>
                        <span className={labelClasses}>Pregabalina</span>
                        <div className="mt-1 text-sm font-bold">{todayLog.meds?.pregabalina ? 'Tomou' : 'Não tomou'}</div>
                    </button>
                    <button type="button" onClick={() => updateMeds({ fexofenadina: !todayLog.meds?.fexofenadina })} className={`rounded-xl border p-3 text-left transition ${todayLog.meds?.fexofenadina ? 'border-primary-container bg-primary-container text-white' : 'border-border-subtle bg-background text-on-surface'}`}>
                        <span className={labelClasses}>Fexofenadina</span>
                        <div className="mt-1 text-sm font-bold">{todayLog.meds?.fexofenadina ? 'Tomou' : 'Não tomou'}</div>
                    </button>
                    <div className="rounded-xl border border-border-subtle bg-background p-3">
                        <span className={labelClasses}>Dipirona</span>
                        <div className="mt-1 flex items-center justify-between gap-2">
                            <button type="button" onClick={() => updateMeds({ dipirona: Math.max(0, (todayLog.meds?.dipirona || 0) - 1) })} className="h-7 w-7 rounded-lg border border-border-standard text-sm font-bold text-on-surface-variant">−</button>
                            <span className="text-sm font-bold text-on-surface">{todayLog.meds?.dipirona || 0}</span>
                            <button type="button" onClick={() => updateMeds({ dipirona: (todayLog.meds?.dipirona || 0) + 1 })} className="h-7 w-7 rounded-lg border border-border-standard text-sm font-bold text-on-surface-variant">+</button>
                        </div>
                    </div>
                    <div className="rounded-xl border border-border-subtle bg-background p-3">
                        <span className={labelClasses}>Adorlan</span>
                        <div className="mt-1 flex items-center justify-between gap-2">
                            <button type="button" onClick={() => updateMeds({ adorlan: Math.max(0, (todayLog.meds?.adorlan || 0) - 1) })} className="h-7 w-7 rounded-lg border border-border-standard text-sm font-bold text-on-surface-variant">−</button>
                            <span className="text-sm font-bold text-on-surface">{todayLog.meds?.adorlan || 0}</span>
                            <button type="button" onClick={() => updateMeds({ adorlan: (todayLog.meds?.adorlan || 0) + 1 })} className="h-7 w-7 rounded-lg border border-border-standard text-sm font-bold text-on-surface-variant">+</button>
                        </div>
                    </div>
                </div>
            ),
        },
        {
            id: 'night_trigger',
            answered: () => todayLog.triggers !== undefined,
            render: () => (
                <ChipGroup options={TRIGGER_TYPES} value={todayLog.triggers?.types || []} onChange={(next: TriggerType[]) => onSaveExerciseLog(selectedDate, { triggers: { types: next, note: todayLog.triggers?.note } })} multi />
            ),
        },
        {
            id: 'night_note',
            answered: () => !!todayLog.note,
            render: () => (
                <textarea
                    value={todayLog.note || ''}
                    onChange={e => onSaveExerciseLog(selectedDate, { note: e.target.value })}
                    placeholder="Nota curta opcional"
                    className="min-h-[88px] w-full rounded-xl border border-border-standard bg-background p-3 text-sm text-on-surface outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container"
                />
            ),
        },
    ];

    // Pergunta ancorada no evento em vez de "dor da manhã" solto — o check-in da
    // manhã só dispara ao meio-dia (de propósito, ver N16), e sem a âncora a
    // resposta varia dia a dia entre "como acordei", "média da manhã" e "agora",
    // sem nenhum sinal disso na série.
    const guidedStepQuestions: Record<string, string> = {
        morning_pain: 'Nota para a dor nos primeiros minutos depois de levantar da cama, antes da caminhada.',
        morning_afterwalk: 'E depois da caminhada, como ficou? A diferença entre as duas notas mede o quanto caminhar alivia a dor.',
    };

    const guidedStepLabels: Record<string, string> = {
        morning_pain: 'Dor ao acordar',
        morning_afterwalk: 'Dor após a caminhada',
        morning_woke: 'Acordou com dor?',
        morning_quality: 'Qualidade do sono',
        night_pain: 'Dor lombar à noite',
        night_radicular: 'Sintoma na perna',
        night_weakness: 'Fraqueza para levantar a ponta do pé',
        night_sciatica_crisis: 'Ciática e crise',
        night_strength: 'Treino de força',
        night_therapy: 'Modalidade terapêutica',
        night_diet: 'Aderência alimentar',
        night_meds: 'Medicação do dia',
        night_trigger: 'Evento / gatilho (opcional)',
        night_note: 'Observação do dia (opcional)',
    };

    const openGuided = (mode: 'morning' | 'night') => {
        guidedTriggerRef.current = document.activeElement as HTMLButtonElement | null;
        const steps = (mode === 'morning' ? morningSteps : nightSteps).filter(s => !s.skip || !s.skip());
        const firstUnanswered = steps.findIndex(s => !s.answered());
        setGuidedStep(firstUnanswered === -1 ? Math.max(0, steps.length - 1) : firstUnanswered);
        setGuidedMode(mode);
    };

    // Semântica de diálogo do check-in guiado (achado N19, mesmo padrão do A17):
    // role="dialog" no container, foco movido para dentro do passo atual a cada
    // troca (o usuário de teclado não fica preso fora do fluxo), Escape fecha
    // igual ao botão "Fechar" já fazia (sem confirmação — as respostas já estão
    // salvas incrementalmente a cada passo, fechar cedo só deixa incompleto, não
    // perde dado), e o foco volta para quem abriu.
    useEffect(() => {
        if (!guidedMode) return;
        guidedStepContentRef.current?.focus();
    }, [guidedMode, guidedStep]);

    useEffect(() => {
        if (!guidedMode) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                setGuidedMode(null);
                setGuidedStep(0);
                guidedTriggerRef.current?.focus();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [guidedMode]);

    if (guidedMode) {
        const allSteps = guidedMode === 'morning' ? morningSteps : nightSteps;
        const visibleSteps = allSteps.filter(s => !s.skip || !s.skip());
        const clampedStep = Math.min(guidedStep, visibleSteps.length - 1);
        const step = visibleSteps[clampedStep];
        const isLast = clampedStep === visibleSteps.length - 1;
        const isAnswered = step ? step.answered() : true;

        // .focus() chamado direto aqui, não só na cleanup do useEffect de baixo: a
        // cleanup roda depois que o React já desmontou o dialog (o botão "Fechar"
        // focado é removido do DOM primeiro, o navegador já jogou o foco pro body
        // nesse instante) — às vezes perdia a corrida. Chamar aqui garante que o
        // foco vai pro gatilho antes de qualquer desmonte.
        const closeGuided = () => {
            setGuidedMode(null);
            setGuidedStep(0);
            guidedTriggerRef.current?.focus();
        };
        const goNext = () => {
            if (isLast) { closeGuided(); return; }
            setGuidedStep(clampedStep + 1);
        };
        const skipStep = () => {
            if (isLast) { closeGuided(); return; }
            setGuidedStep(clampedStep + 1);
        };
        const goBack = () => setGuidedStep(Math.max(0, clampedStep - 1));

        return (
            <div role="dialog" aria-modal="true" aria-labelledby="guided-checkin-title" className="fixed inset-0 z-50 flex flex-col bg-background">
                <div className="border-b border-border-subtle bg-white px-6 py-4">
                    <div className="mx-auto flex max-w-[600px] items-center justify-between">
                        <button type="button" onClick={closeGuided} className="text-xs font-semibold text-on-surface-variant hover:text-primary-container">Fechar</button>
                        <span className="text-xs font-semibold text-on-surface-variant">{clampedStep + 1} de {visibleSteps.length}</span>
                    </div>
                    <div className="mx-auto mt-3 h-1.5 max-w-[600px] overflow-hidden rounded-full bg-surface-container-low">
                        <div className="h-full rounded-full bg-primary-container transition-all duration-300" style={{ width: `${((clampedStep + 1) / visibleSteps.length) * 100}%` }} />
                    </div>
                </div>
                <div className="flex flex-1 justify-center overflow-y-auto px-6 py-10">
                    <div className="h-fit w-full max-w-[600px] pt-[8vh]">
                        <p className={labelClasses}>{guidedMode === 'morning' ? 'Check-in da manhã' : 'Check-in da noite'}</p>
                        <h2 id="guided-checkin-title" className="mt-1 text-xl font-bold text-on-surface">{step ? guidedStepLabels[step.id] : ''}</h2>
                        {step && guidedStepQuestions[step.id] && (
                            <p className="mt-1 text-sm text-on-surface-variant">{guidedStepQuestions[step.id]}</p>
                        )}
                        <div ref={guidedStepContentRef} tabIndex={-1} className="mt-6 outline-none">{step?.render()}</div>
                    </div>
                </div>
                <div className="border-t border-border-subtle bg-white px-6 py-4">
                    <div className="mx-auto flex max-w-[600px] items-center justify-between gap-3">
                        <button type="button" onClick={goBack} disabled={clampedStep === 0} className="rounded-xl border border-border-standard px-4 py-2.5 text-sm font-semibold text-on-surface-variant transition disabled:cursor-not-allowed disabled:opacity-30">Voltar</button>
                        <div className="flex items-center gap-2">
                            {!isLast && (
                                <button type="button" onClick={skipStep} className="rounded-xl px-4 py-2.5 text-sm font-semibold text-on-surface-variant">Pular</button>
                            )}
                            <button
                                type="button"
                                onClick={goNext}
                                disabled={!isAnswered}
                                className="rounded-xl bg-primary-container px-6 py-2.5 text-sm font-bold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                {isLast ? 'Concluir' : 'Continuar'}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    if (isReportOpen) {
        const periodStartLabel = formatDate(integratedRangeStart || (exerciseLogs[0]?.id ?? selectedDate));
        const periodEndLabel = formatDate(formatDateLocalISO(new Date()));
        return (
            <div id="health-consult-report" className="min-h-screen bg-white p-8 text-black">
                <style>{`
                    @media print {
                        body * { visibility: hidden; }
                        #health-consult-report, #health-consult-report * { visibility: visible; }
                        #health-consult-report { position: absolute; left: 0; top: 0; width: 100%; padding: 12px; }
                        .no-print { display: none !important; }
                    }
                `}</style>
                <div className="no-print mb-6 flex items-center justify-between">
                    <button
                        type="button"
                        onClick={() => setIsReportOpen(false)}
                        className="rounded-lg border border-border-standard px-4 py-2 text-sm font-semibold text-on-surface-variant"
                    >
                        ← Voltar ao painel
                    </button>
                    <button
                        type="button"
                        onClick={() => window.print()}
                        className="rounded-lg bg-primary-container px-4 py-2 text-sm font-bold text-white"
                    >
                        Imprimir / salvar PDF
                    </button>
                </div>

                <h1 className="text-xl font-bold text-black">Relatório de acompanhamento — coluna lombar</h1>
                <p className="mt-1 text-sm text-slate-600">
                    Período: {periodStartLabel} a {periodEndLabel} · Gerado em {periodEndLabel}
                </p>

                <section className="mt-6">
                    <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">Peso, dor e caminhada</h2>
                    <div className="mt-2">
                        <IntegratedTrendChart
                            weightPoints={weightForIntegrated}
                            painWeekly={painWeeklyForIntegrated}
                            kmWeekly={kmWeeklyForIntegrated}
                            events={eventsForIntegrated}
                            targetWeight={settings.targetWeight}
                            isDark={false}
                        />
                    </div>
                </section>

                <section className="mt-6">
                    <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">Evolução do sintoma radicular</h2>
                    <div className="mt-2">
                        <RadicularTimelineChart points={radicularSeriesInPeriod} isDark={false} />
                    </div>
                </section>

                <section className="mt-6 grid grid-cols-2 gap-6">
                    <div>
                        <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">Medicação no período</h2>
                        <table className="mt-2 w-full text-left text-xs text-black">
                            <tbody>
                                <tr><td className="py-1 pr-4 font-semibold">Pregabalina</td><td>{medUsageInPeriod.pregabalinaDays} de {medUsageInPeriod.totalDays} dias</td></tr>
                                <tr><td className="py-1 pr-4 font-semibold">Dipirona</td><td>{medUsageInPeriod.dipironaTotal} comprimido(s) no total</td></tr>
                                <tr><td className="py-1 pr-4 font-semibold">Adorlan</td><td>{medUsageInPeriod.adorlanTotal} comprimido(s) no total</td></tr>
                                <tr><td className="py-1 pr-4 font-semibold">Fexofenadina</td><td>{medUsageInPeriod.fexofenadinaDays} de {medUsageInPeriod.totalDays} dias</td></tr>
                                {medUsageInPeriod.outros.length > 0 && (
                                    <tr><td className="py-1 pr-4 font-semibold">Outros</td><td>{medUsageInPeriod.outros.join('; ')}</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                    <div>
                        <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">Aderência ao tratamento</h2>
                        <table className="mt-2 w-full text-left text-xs text-black">
                            <tbody>
                                <tr><td className="py-1 pr-4 font-semibold">Dor média (manhã+noite)</td><td>{adherenceInPeriod.avgPain !== null ? adherenceInPeriod.avgPain.toFixed(1).replace('.', ',') : '-'}</td></tr>
                                <tr><td className="py-1 pr-4 font-semibold">Cardápio seguido</td><td>{adherenceInPeriod.dietDays} de {adherenceInPeriod.totalDays} dias</td></tr>
                                <tr><td className="py-1 pr-4 font-semibold">Treino de força</td><td>{adherenceInPeriod.strengthSessions} sessões</td></tr>
                                <tr><td className="py-1 pr-4 font-semibold">Caminhada total</td><td>{adherenceInPeriod.kmTotal.toFixed(1).replace('.', ',')} km</td></tr>
                            </tbody>
                        </table>
                    </div>
                </section>

                <section className="mt-6">
                    <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">Documentos do arquivo médico no período</h2>
                    {examsInReportPeriod.length > 0 ? (
                        <ul className="mt-2 space-y-1 text-xs text-black">
                            {examsInReportPeriod.map(exam => (
                                <li key={exam.id}>
                                    <strong>{formatDate(exam.data)}</strong> — {exam.titulo} ({HEALTH_EXAM_TYPES.find(t => t.value === exam.tipo)?.label || exam.tipo}){exam.doutor_local ? ` · ${exam.doutor_local}` : ''}
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="mt-2 text-xs text-slate-500">Nenhum documento no período selecionado.</p>
                    )}
                </section>
            </div>
        );
    }

    return (
        <div className={`health-view min-h-screen bg-background pb-20 ${isDark ? 'health-view-dark' : ''}`}>
            <div>
                <div className="mx-auto flex max-w-[1440px] flex-col gap-5 px-6 py-6 lg:px-8">
                    <div>
                        <p className={labelClasses}>Saúde integrada</p>
                        <h2 className="mt-1 text-2xl font-bold tracking-tight text-on-surface">Painel de saúde</h2>
                        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-on-surface-variant">
                            Registro manual de peso, acompanhamento de dor lombar e arquivo médico em um painel de acompanhamento contínuo.
                        </p>
                    </div>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex flex-wrap rounded-xl border border-border-standard bg-background p-1">
                            {[
                                { id: 'overview', label: 'Visão geral' },
                                { id: 'records', label: 'Registros' },
                                { id: 'charts', label: 'Gráficos' },
                                { id: 'reminders', label: 'Lembretes' },
                                { id: 'report', label: 'Relatório' },
                                { id: 'archive', label: 'Arquivo médico' },
                            ].map(tab => (
                                <button
                                    key={tab.id}
                                    type="button"
                                    onClick={() => setActiveTab(tab.id as typeof activeTab)}
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

                    {activeTab === 'overview' && (
                    <div className="grid grid-cols-1 gap-4 sm:max-w-2xl sm:grid-cols-2">
                        <MetricCard
                            label={weightHeadline?.isAverage ? 'Média de 7 dias' : 'Peso de hoje'}
                            value={weightHeadline ? weightHeadline.displayValue.toFixed(1).replace('.', ',') : '—'}
                            unit="kg"
                            helper={weightHeadline ? (
                                <>
                                    {weightHeadline.isAverage
                                        ? (weightHeadline.deltaVsWeekAgo !== null
                                            ? `${weightHeadline.deltaVsWeekAgo > 0 ? '+' : ''}${weightHeadline.deltaVsWeekAgo.toFixed(1).replace('.', ',')} kg vs. média de 7 dias atrás`
                                            : 'Ainda sem média de 7 dias atrás para comparar')
                                        : `Faltam ${4 - weightHeadline.windowCount} registro(s) na semana para calcular a média de 7 dias`}
                                    <br />
                                    <span className="opacity-70">Último registro: {weightHeadline.latestRaw.toFixed(1).replace('.', ',')} kg em {formatShortDate(weightHeadline.latestRawDate)}</span>
                                </>
                            ) : 'Nenhum registro de peso ainda.'}
                            icon="scale"
                        />
                        <MetricCard
                            label="Caminhada hoje"
                            value={formatKm(todayWalkKm)}
                            unit="km"
                            helper={isCrisisTodayReal
                                ? 'Dia de crise: caminhadas curtas e frequentes, sem meta de distância.'
                                : todayWalkKm > walkingIdealKm
                                    ? `Bônus — acima da faixa normal (${formatKm(walkingMinimumKm)}–${formatKm(walkingIdealKm)} km)`
                                    : todayWalkKm >= walkingMinimumKm
                                        ? 'Dentro da faixa normal'
                                        : `Faltam ${formatKm(walkingMinimumKm - todayWalkKm)} km para o mínimo de ${formatKm(walkingMinimumKm)} km`}
                            icon="walk"
                            tone="text-emerald-600"
                        />
                    </div>
                    )}
                </div>
            </div>

            <main className="mx-auto max-w-[1440px] px-6 py-6 lg:px-8">
                {activeTab !== 'archive' && (
                    <div className="mb-6 flex flex-col gap-3 rounded-2xl border border-primary-container/30 bg-white p-5 shadow-card sm:flex-row sm:items-center sm:justify-between">
                        <div>
                            <p className={labelClasses}>Check-in guiado</p>
                            <h3 className="mt-1 text-base font-bold text-on-surface">Uma pergunta por vez — leva menos de 1 minuto</h3>
                        </div>
                        <div className="flex gap-2">
                            <button type="button" onClick={() => openGuided('morning')} className="rounded-xl border border-border-standard bg-white px-4 py-2.5 text-sm font-bold text-on-surface transition hover:border-primary-container hover:text-primary-container">
                                Check-in da manhã
                            </button>
                            <button type="button" onClick={() => openGuided('night')} className="rounded-xl bg-primary-container px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90">
                                Check-in da noite
                            </button>
                        </div>
                    </div>
                )}
                {activeTab === 'overview' && (
                    <>
                    {latestWeeklySummary && (
                        <div className="mb-6 rounded-2xl border border-border-subtle bg-white p-5 shadow-card">
                            <p className={labelClasses}>Resumo semanal · {formatShortDate(latestWeeklySummary.weekStart)} a {formatShortDate(latestWeeklySummary.weekEnd)}</p>
                            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
                                <div>
                                    <p className="text-[10px] font-semibold uppercase text-on-surface-variant">Peso médio</p>
                                    <p className="text-sm font-bold text-on-surface">
                                        {latestWeeklySummary.avgWeight !== null ? `${latestWeeklySummary.avgWeight.toFixed(1).replace('.', ',')} kg` : '—'}
                                        {latestWeeklySummary.weightDelta !== null && (
                                            <span className="ml-1 text-xs font-semibold text-on-surface-variant">
                                                ({latestWeeklySummary.weightDelta > 0 ? '+' : ''}{latestWeeklySummary.weightDelta.toFixed(1).replace('.', ',')})
                                            </span>
                                        )}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-[10px] font-semibold uppercase text-on-surface-variant">Cintura</p>
                                    <p className="text-sm font-bold text-on-surface">{latestWeeklySummary.waistCm !== null ? `${latestWeeklySummary.waistCm.toFixed(1).replace('.', ',')} cm` : '—'}</p>
                                </div>
                                <div>
                                    <p className="text-[10px] font-semibold uppercase text-on-surface-variant">Dor manhã/noite</p>
                                    <p className="text-sm font-bold text-on-surface">
                                        {latestWeeklySummary.avgPainMorning?.toFixed(1).replace('.', ',') ?? '-'} / {latestWeeklySummary.avgPainEvening?.toFixed(1).replace('.', ',') ?? '-'}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-[10px] font-semibold uppercase text-on-surface-variant">Km caminhados</p>
                                    <p className="text-sm font-bold text-on-surface">{latestWeeklySummary.kmTotal.toFixed(1).replace('.', ',')} km</p>
                                </div>
                                <div>
                                    <p className="text-[10px] font-semibold uppercase text-on-surface-variant">Força</p>
                                    <p className="text-sm font-bold text-on-surface">{latestWeeklySummary.strengthSessions}/{latestWeeklySummary.strengthGoal}</p>
                                </div>
                                <div>
                                    <p className="text-[10px] font-semibold uppercase text-on-surface-variant">Cardápio seguido</p>
                                    <p className="text-sm font-bold text-on-surface">{latestWeeklySummary.dietDays} dias</p>
                                </div>
                                <div>
                                    <p className="text-[10px] font-semibold uppercase text-on-surface-variant">Eventos</p>
                                    <p className="text-sm font-bold text-on-surface">{latestWeeklySummary.events.length}</p>
                                </div>
                            </div>
                        </div>
                    )}
                    <HealthSection title="Gráfico integrado" eyebrow="Peso, dor e caminhada juntos">
                        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                            <p className="max-w-xl text-xs font-medium leading-relaxed text-on-surface-variant">
                                Três painéis empilhados com o mesmo eixo de tempo — nunca em um único gráfico de eixo duplo, para não sugerir correlações falsas.
                            </p>
                            <div className="flex rounded-xl border border-border-standard bg-white p-1">
                                {[{ v: 30, l: '30d' }, { v: 90, l: '90d' }, { v: 180, l: '180d' }, { v: null as number | null, l: 'Tudo' }].map(opt => (
                                    <button
                                        key={opt.l}
                                        type="button"
                                        onClick={() => setIntegratedRangeDays(opt.v)}
                                        className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${integratedRangeDays === opt.v ? 'bg-primary-container text-white' : 'text-on-surface-variant hover:text-primary-container'}`}
                                    >
                                        {opt.l}
                                    </button>
                                ))}
                            </div>
                            <button
                                type="button"
                                onClick={() => setIsReportOpen(true)}
                                className="flex items-center gap-2 rounded-xl border border-border-standard bg-white px-3 py-2 text-xs font-semibold text-on-surface-variant transition hover:border-primary-container hover:text-primary-container"
                            >
                                <Icon name="file" className="h-4 w-4" />
                                Gerar relatório para consulta
                            </button>
                        </div>
                        <IntegratedTrendChart
                            weightPoints={weightForIntegrated}
                            painWeekly={painWeeklyForIntegrated}
                            kmWeekly={kmWeeklyForIntegrated}
                            events={eventsForIntegrated}
                            targetWeight={settings.targetWeight}
                            isDark={isDark}
                        />
                        <div className="mt-5 rounded-2xl border border-border-subtle bg-background p-4">
                            <p className={`${labelClasses} mb-3`}>Marcador de evento</p>
                            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[140px_180px_1fr_auto]">
                                <label className="block">
                                    <span className={labelClasses}>Data</span>
                                    <input type="date" value={eventDate} onChange={e => setEventDate(e.target.value)} className={inputClasses} />
                                </label>
                                <label className="block">
                                    <span className={labelClasses}>Tipo</span>
                                    <select value={eventType} onChange={e => setEventType(e.target.value as HealthEventType)} className={inputClasses}>
                                        {HEALTH_EVENT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                                    </select>
                                </label>
                                <label className="block">
                                    <span className={labelClasses}>Rótulo</span>
                                    <input type="text" value={eventLabel} onChange={e => setEventLabel(e.target.value)} placeholder="Ex: Início da fisioterapia" className={inputClasses} />
                                </label>
                                <button
                                    type="button"
                                    onClick={handleAddEvent}
                                    disabled={!eventLabel.trim()}
                                    className="mt-5 flex items-center justify-center gap-2 rounded-xl bg-primary-container px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                                >
                                    <Icon name="plus" className="h-4 w-4" />
                                    Adicionar
                                </button>
                            </div>
                            {eventsForIntegrated.length > 0 && (() => {
                                const punctualLegend = eventsForIntegrated.filter(e => !isRecurringTherapySession(e));
                                const recurringLegend = eventsForIntegrated.filter(isRecurringTherapySession);
                                const recurringCounts = new Map<string, number>();
                                recurringLegend.forEach(e => recurringCounts.set(e.label, (recurringCounts.get(e.label) ?? 0) + 1));
                                return (
                                    <div className="mt-4 space-y-3">
                                        {punctualLegend.length > 0 && (
                                            <div className="flex flex-wrap gap-2">
                                                <p className="w-full text-[10px] font-medium text-on-surface-variant">Legenda dos pinos numerados do gráfico acima:</p>
                                                {punctualLegend.map((event, i) => (
                                                    <span key={event.id} className="inline-flex items-center gap-1.5 rounded-full border border-border-standard bg-white px-2.5 py-1 text-[10px] font-semibold text-on-surface-variant">
                                                        <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-surface-container-low text-[9px] font-bold text-on-surface">{i + 1}</span>
                                                        {formatShortDate(event.date)} · {event.label}
                                                        {event.source === 'exam' ? (
                                                            <span className="text-on-surface-variant/50" title="Vem do arquivo médico">📎</span>
                                                        ) : event.source === 'calendar' ? (
                                                            <span className="text-on-surface-variant/50" title="Vem da Google Agenda">📅</span>
                                                        ) : (
                                                            <button type="button" onClick={() => onDeleteEvent(event.id)} className="text-on-surface-variant/60 hover:text-error" aria-label="Remover evento">×</button>
                                                        )}
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                        {recurringCounts.size > 0 && (
                                            <p className="text-[10px] font-medium text-on-surface-variant">
                                                Pontinhos discretos na trilha: {[...recurringCounts.entries()].map(([label, count]) => `${label.toLowerCase()} ${count}×`).join(' · ')} nesta janela — sessões recorrentes, sem pino próprio
                                            </p>
                                        )}
                                    </div>
                                );
                            })()}
                        </div>
                    </HealthSection>
                    </>
                )}
                {activeTab === 'records' && (
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
                                                Distância até a meta: {targetDelta > 0 ? '+' : ''}{targetDelta.toFixed(1).replace('.', ',')} kg
                                            </p>
                                        )}
                                    </div>
                                </div>

                                <div className="mt-5">
                                    <p className={`${labelClasses} mb-2`}>Registros recentes</p>
                                    {sortedWeights.length > 0 ? (
                                        <div className="max-h-[240px] space-y-2 overflow-y-auto">
                                            {sortedWeights.slice(0, 20).map(weight => (
                                                editingWeightId === weight.id ? (
                                                    <div key={weight.id} className="flex items-center gap-2 rounded-xl border border-primary-container bg-white px-3 py-2">
                                                        <input
                                                            type="text"
                                                            inputMode="decimal"
                                                            value={editWeightValue}
                                                            onChange={e => setEditWeightValue(e.target.value)}
                                                            className="w-16 rounded-lg border border-border-standard px-2 py-1 text-sm font-bold"
                                                        />
                                                        <input
                                                            type="date"
                                                            value={editWeightDate}
                                                            onChange={e => setEditWeightDate(e.target.value)}
                                                            className="rounded-lg border border-border-standard px-2 py-1 text-xs"
                                                        />
                                                        <button type="button" onClick={saveEditWeight} className="ml-auto rounded-lg bg-primary-container px-2.5 py-1 text-xs font-bold text-white">Salvar</button>
                                                        <button type="button" onClick={cancelEditWeight} className="text-xs font-semibold text-on-surface-variant">Cancelar</button>
                                                    </div>
                                                ) : (
                                                    <div key={weight.id} className="flex items-center justify-between gap-3 rounded-xl border border-border-subtle bg-white px-4 py-2.5">
                                                        <div className="flex items-baseline gap-2">
                                                            <span className="text-sm font-bold text-on-surface">{weight.weight.toFixed(1).replace('.', ',')} kg</span>
                                                            <span className="text-xs font-medium text-on-surface-variant">{formatDate(weight.date)}</span>
                                                        </div>
                                                        <div className="flex items-center gap-1">
                                                            <button
                                                                type="button"
                                                                onClick={() => startEditWeight(weight)}
                                                                className="rounded-lg p-1.5 text-on-surface-variant transition hover:bg-surface-container-low hover:text-primary-container"
                                                                aria-label="Editar registro"
                                                            >
                                                                <Icon name="edit" className="h-4 w-4" />
                                                            </button>
                                                            <button
                                                                type="button"
                                                                onClick={() => onDeleteWeight(weight.id)}
                                                                className="rounded-lg p-1.5 text-on-surface-variant transition hover:bg-error-container hover:text-on-error-container"
                                                                aria-label="Remover registro"
                                                            >
                                                                <Icon name="trash" className="h-4 w-4" />
                                                            </button>
                                                        </div>
                                                    </div>
                                                )
                                            ))}
                                        </div>
                                    ) : (
                                        <p className="text-xs font-semibold text-on-surface-variant">Nenhum registro de peso ainda.</p>
                                    )}
                                </div>
                            </HealthSection>

                            <HealthSection title="Circunferência de cintura" eyebrow="Registro semanal">
                                <p className="text-xs font-medium text-on-surface-variant">Meça na altura do umbigo, sempre no mesmo dia da semana.</p>
                                <div className="mt-3 flex items-end gap-2">
                                    <label className="block flex-1">
                                        <span className={labelClasses}>Cintura (cm)</span>
                                        <input
                                            type="text"
                                            inputMode="decimal"
                                            value={waistInput}
                                            onChange={e => setWaistInput(e.target.value)}
                                            onKeyDown={e => { if (e.key === 'Enter') handleAddWaist(); }}
                                            placeholder="Ex: 98"
                                            className={inputClasses}
                                        />
                                    </label>
                                    <button
                                        type="button"
                                        onClick={handleAddWaist}
                                        className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-primary-container px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90"
                                    >
                                        <Icon name="plus" className="h-4 w-4" />
                                        Registrar
                                    </button>
                                </div>
                                {sortedWaist.length > 0 ? (
                                    <div className="mt-4 max-h-[160px] space-y-2 overflow-y-auto">
                                        {sortedWaist.slice(0, 8).map(entry => (
                                            <div key={entry.id} className="flex items-center justify-between gap-3 rounded-xl border border-border-subtle bg-white px-4 py-2.5">
                                                <div className="flex items-baseline gap-2">
                                                    <span className="text-sm font-bold text-on-surface">{entry.cm.toFixed(1).replace('.', ',')} cm</span>
                                                    <span className="text-xs font-medium text-on-surface-variant">{formatDate(entry.date)}</span>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => onDeleteWaist(entry.id)}
                                                    className="rounded-lg p-1.5 text-on-surface-variant transition hover:bg-error-container hover:text-on-error-container"
                                                    aria-label="Remover registro"
                                                >
                                                    <Icon name="trash" className="h-4 w-4" />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="mt-4 text-xs font-semibold text-on-surface-variant">Nenhum registro de cintura ainda.</p>
                                )}
                            </HealthSection>
                        </div>

                        <div className="space-y-6">
                            <HealthSection title="Caminhada na esteira" eyebrow="Meta diária de distância">
                                <WalkGoalBar doneKm={selectedWalkKm} minimumKm={walkingMinimumKm} normalTopKm={walkingIdealKm} isCrisis={isCrisisToday} />

                                <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
                                    <div className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <label className="block">
                                            <span className={labelClasses}>Distância do bloco (km)</span>
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
                                            Só a distância é obrigatória. Data do registro: {selectedDateLabel}
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
                                        {selectedWalkBlocks.length > 0 && (
                                            <div className="mt-2 flex flex-wrap gap-4 text-xs font-semibold text-on-surface-variant">
                                                <span>
                                                    <span className="text-sm font-bold text-on-surface">{selectedWalkBlocks.length}</span> bloco{selectedWalkBlocks.length === 1 ? '' : 's'} hoje
                                                    {selectedWalkBlocks.length >= 4 && <span className="ml-1 text-emerald-600">· meta de 4+ ok</span>}
                                                </span>
                                                {maiorIntervaloSemCaminharMin !== null && (
                                                    <span>
                                                        Maior intervalo sem caminhar: <span className="text-sm font-bold text-on-surface">{Math.floor(maiorIntervaloSemCaminharMin / 60)}h{String(maiorIntervaloSemCaminharMin % 60).padStart(2, '0')}
                                                        </span>
                                                    </span>
                                                )}
                                            </div>
                                        )}
                                        {selectedWalkBlocks.length > 0 ? (
                                            <div className="mt-3 max-h-[220px] space-y-2 overflow-y-auto">
                                                {selectedWalkBlocks.map(block => (
                                                    editingBlockId === block.id ? (
                                                        <div key={block.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-primary-container bg-white px-3 py-2">
                                                            <input type="text" inputMode="decimal" value={editBlockDistance} onChange={e => setEditBlockDistance(e.target.value)} placeholder="km" className="w-16 rounded-lg border border-border-standard px-2 py-1 text-xs" />
                                                            <input type="text" inputMode="decimal" value={editBlockMinutes} onChange={e => setEditBlockMinutes(e.target.value)} placeholder="min" className="w-14 rounded-lg border border-border-standard px-2 py-1 text-xs" />
                                                            <input type="text" inputMode="decimal" value={editBlockSteps} onChange={e => setEditBlockSteps(e.target.value)} placeholder="passos" className="w-16 rounded-lg border border-border-standard px-2 py-1 text-xs" />
                                                            <input type="text" inputMode="decimal" value={editBlockCalories} onChange={e => setEditBlockCalories(e.target.value)} placeholder="kcal" className="w-16 rounded-lg border border-border-standard px-2 py-1 text-xs" />
                                                            <button type="button" onClick={saveEditBlock} className="ml-auto rounded-lg bg-primary-container px-2.5 py-1 text-xs font-bold text-white">Salvar</button>
                                                            <button type="button" onClick={cancelEditBlock} className="text-xs font-semibold text-on-surface-variant">Cancelar</button>
                                                        </div>
                                                    ) : (
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
                                                            <div className="flex items-center gap-1">
                                                                <button
                                                                    type="button"
                                                                    onClick={() => startEditBlock(block)}
                                                                    className="rounded-lg p-1.5 text-on-surface-variant transition hover:bg-surface-container-low hover:text-primary-container"
                                                                    aria-label="Editar bloco"
                                                                >
                                                                    <Icon name="edit" className="h-4 w-4" />
                                                                </button>
                                                                <button
                                                                    type="button"
                                                                    onClick={() => handleDeleteWalkBlock(block.id)}
                                                                    className="rounded-lg p-1.5 text-on-surface-variant transition hover:bg-error-container hover:text-on-error-container"
                                                                    aria-label="Remover bloco"
                                                                >
                                                                    <Icon name="trash" className="h-4 w-4" />
                                                                </button>
                                                            </div>
                                                        </div>
                                                    )
                                                ))}
                                            </div>
                                        ) : (
                                            <p className="mt-3 text-xs font-semibold text-on-surface-variant">Nenhum bloco registrado neste dia.</p>
                                        )}
                                        <div className="mt-4 grid grid-cols-2 gap-2">
                                            <label className="block">
                                                <span className={labelClasses}>Mínimo (km) — não se aplica em dia de crise</span>
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
                                                <span className={labelClasses}>Topo da faixa normal (km) — acima é bônus</span>
                                                <input
                                                    type="number"
                                                    step="0.5"
                                                    min="0"
                                                    value={settings.walkingIdealKm ?? 6}
                                                    onChange={e => onUpdateSettings({ ...settings, walkingIdealKm: parseFloat(e.target.value) || 0 })}
                                                    className={inputClasses}
                                                />
                                            </label>
                                        </div>
                                    </div>
                                </div>

                                <div className="mt-5">
                                    <p className={`${labelClasses} mb-2`}>Últimos 14 dias</p>
                                    <WalkDailyChart days={walkChartDays} minimumKm={walkingMinimumKm} idealKm={walkingIdealKm} isDark={isDark} />
                                </div>
                            </HealthSection>

                            <HealthSection title="Registro diário (edição manual)" eyebrow="Sinal clínico e hábitos" defaultExpanded={false}>
                                <div className="space-y-5">
                                    {isRedFlagActive && (
                                        <div className="rounded-xl border border-error bg-error-container p-4 text-on-error-container">
                                            <p className="text-sm font-bold">⚠️ Sinais de alerta no registro deste dia</p>
                                            <p className="mt-1 text-xs leading-relaxed">
                                                Isto não é um diagnóstico — é uma lista de sinais que, se presentes, indicam buscar atendimento
                                                médico o quanto antes: dormência na região da sela (períneo), alteração no controle de urina ou
                                                fezes, fraqueza progressiva para levantar a ponta do pé, ou sintomas nas duas pernas ao mesmo
                                                tempo. Se notar qualquer um desses, procure atendimento.
                                            </p>
                                        </div>
                                    )}
                                    <div>
                                        <p className={`${labelClasses} mb-2`}>Dor lombar</p>
                                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                            <div className="rounded-xl border border-border-subtle bg-background p-4">
                                                <div className="flex items-baseline justify-between">
                                                    <span className={labelClasses} title="Nos primeiros minutos depois de levantar da cama, antes da caminhada">Manhã (ao levantar)</span>
                                                    <span className="text-sm font-bold text-on-surface">{todayLog.pain?.morning ?? '—'}/10</span>
                                                </div>
                                                <input type="range" min="0" max="10" value={todayLog.pain?.morning ?? 0} onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, morning: parseInt(e.target.value) } })} className="mt-2 w-full accent-primary-container" />
                                            </div>
                                            <div className="rounded-xl border border-border-subtle bg-background p-4">
                                                <div className="flex items-baseline justify-between">
                                                    <span className={labelClasses}>Noite</span>
                                                    <span className="text-sm font-bold text-on-surface">{todayLog.pain?.evening ?? '—'}/10</span>
                                                </div>
                                                <input type="range" min="0" max="10" value={todayLog.pain?.evening ?? 0} onChange={e => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, evening: parseInt(e.target.value) } })} className="mt-2 w-full accent-primary-container" />
                                            </div>
                                        </div>
                                        <div className="mt-3 grid grid-cols-2 gap-3">
                                            <ToggleTile
                                                label="Ciática"
                                                active={!!todayLog.pain?.sciatica}
                                                activeTone="tertiary"
                                                onClick={() => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, sciatica: !todayLog.pain?.sciatica } })}
                                            />
                                            <ToggleTile
                                                label="Crise"
                                                active={!!todayLog.pain?.crisis}
                                                activeTone="error"
                                                onClick={() => onSaveExerciseLog(selectedDate, { pain: { ...todayLog.pain, crisis: !todayLog.pain?.crisis } })}
                                            />
                                        </div>
                                    </div>

                                    <div>
                                        <p className={`${labelClasses} mb-2`}>Sintoma radicular (perna) — do quadril ao pé</p>
                                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[220px_1fr]">
                                            <ChipGroup
                                                options={RADICULAR_LOCATIONS}
                                                value={todayLog.radicular?.location}
                                                onChange={(location: RadicularLocation) => updateRadicular({ location })}
                                                layout="stack"
                                                deselectable={false}
                                            />
                                            {todayLog.radicular && todayLog.radicular.location !== 'nenhum' && (
                                                <div className="space-y-3 rounded-xl border border-border-subtle bg-background p-4">
                                                    <div>
                                                        <span className={labelClasses}>Lado</span>
                                                        <div className="mt-1.5">
                                                            <ChipGroup
                                                                options={[{ value: 'direito', label: 'Direito' }, { value: 'esquerdo', label: 'Esquerdo' }, { value: 'ambos', label: 'Ambos' }]}
                                                                value={todayLog.radicular.side}
                                                                onChange={(side: RadicularSide) => updateRadicular({ side })}
                                                            />
                                                        </div>
                                                    </div>
                                                    <div>
                                                        <div className="flex items-baseline justify-between">
                                                            <span className={labelClasses}>Intensidade</span>
                                                            <span className="text-sm font-bold text-on-surface">{todayLog.radicular.intensity ?? 0}/10</span>
                                                        </div>
                                                        <input
                                                            type="range"
                                                            min="0"
                                                            max="10"
                                                            value={todayLog.radicular.intensity ?? 0}
                                                            onChange={e => updateRadicular({ intensity: parseInt(e.target.value) })}
                                                            className="mt-1 w-full accent-primary-container"
                                                        />
                                                    </div>
                                                    <ToggleTile
                                                        label="Fraqueza para levantar a ponta do pé"
                                                        active={!!todayLog.radicular?.motorWeakness}
                                                        activeTone="error"
                                                        onClick={() => updateRadicular({ motorWeakness: !todayLog.radicular?.motorWeakness })}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                                        <div>
                                            <p className={`${labelClasses} mb-2`}>Treino de força</p>
                                            <div className="flex flex-wrap items-center gap-2">
                                                <button
                                                    type="button"
                                                    onClick={() => updateStrength({ done: !todayLog.strength?.done })}
                                                    className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${todayLog.strength?.done ? 'border-primary-container bg-primary-container text-white' : 'border-border-standard bg-white text-on-surface-variant'}`}
                                                >
                                                    {todayLog.strength?.done ? 'Feito' : 'Não feito'}
                                                </button>
                                                {todayLog.strength?.done && (
                                                    <>
                                                        <ChipGroup
                                                            options={[{ value: 'A', label: 'Bloco A' }, { value: 'B', label: 'Bloco B' }]}
                                                            value={todayLog.strength?.block || undefined}
                                                            onChange={(block: 'A' | 'B') => updateStrength({ block })}
                                                            deselectable={false}
                                                        />
                                                        <ChipGroup
                                                            options={[15, 30, 45, 60].map(m => ({ value: String(m), label: `${m} min` }))}
                                                            value={todayLog.strength?.minutes ? String(todayLog.strength.minutes) : undefined}
                                                            onChange={(value: string) => updateStrength({ minutes: parseInt(value) })}
                                                        />
                                                    </>
                                                )}
                                            </div>
                                        </div>

                                        <div>
                                            <p className={`${labelClasses} mb-2`}>Modalidade terapêutica</p>
                                            <ChipGroup
                                                options={THERAPY_MODALITIES}
                                                value={todayLog.therapy || []}
                                                onChange={(next: TherapyModality[]) => onSaveExerciseLog(selectedDate, { therapy: next })}
                                                multi
                                            />
                                        </div>

                                        <div>
                                            <p className={`${labelClasses} mb-2`}>Aderência alimentar</p>
                                            <ChipGroup
                                                options={[{ value: 'sim', label: 'Sim' }, { value: 'parcial', label: 'Parcial' }, { value: 'nao', label: 'Não' }]}
                                                value={todayLog.nutrition?.plan}
                                                onChange={(plan: 'sim' | 'parcial' | 'nao') => updateNutrition({ plan })}
                                                deselectable={false}
                                            />
                                            <button
                                                type="button"
                                                onClick={() => updateNutrition({ proteinTarget: !todayLog.nutrition?.proteinTarget })}
                                                className={`mt-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${todayLog.nutrition?.proteinTarget ? 'border-primary-container bg-primary-container text-white' : 'border-border-standard bg-white text-on-surface-variant'}`}
                                            >
                                                Proteína batida {todayLog.nutrition?.proteinTarget ? '✓' : ''}
                                            </button>
                                        </div>

                                        <div>
                                            <p className={`${labelClasses} mb-2`}>Sono</p>
                                            <div className="flex flex-wrap items-center gap-2">
                                                <button
                                                    type="button"
                                                    onClick={() => updateSleepQuality({ wokeInPain: !todayLog.sleepQuality?.wokeInPain })}
                                                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${todayLog.sleepQuality?.wokeInPain ? 'border-error bg-error-container text-on-error-container' : 'border-border-standard bg-white text-on-surface-variant'}`}
                                                >
                                                    <span className={`h-2 w-2 rounded-full ${todayLog.sleepQuality?.wokeInPain ? 'bg-error' : 'border border-on-surface-variant/50'}`} />
                                                    Acordou com dor {todayLog.sleepQuality?.wokeInPain ? 'Sim' : 'Não'}
                                                </button>
                                                <ChipGroup
                                                    options={[1, 2, 3, 4, 5].map(q => ({ value: String(q), label: String(q) }))}
                                                    value={todayLog.sleepQuality?.quality ? String(todayLog.sleepQuality.quality) : undefined}
                                                    onChange={(value: string) => updateSleepQuality({ quality: parseInt(value) })}
                                                />
                                            </div>
                                        </div>
                                    </div>

                                    <div>
                                        <p className={`${labelClasses} mb-2`}>Medicação do dia</p>
                                        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                                            <button
                                                type="button"
                                                onClick={() => updateMeds({ pregabalina: !todayLog.meds?.pregabalina })}
                                                className={`rounded-xl border p-3 text-left transition ${todayLog.meds?.pregabalina ? 'border-primary-container bg-primary-container text-white' : 'border-border-subtle bg-background text-on-surface'}`}
                                            >
                                                <span className={`${labelClasses} ${todayLog.meds?.pregabalina ? 'text-white/80' : ''}`}>Pregabalina</span>
                                                <div className="mt-2 flex items-center gap-2">
                                                    <span className={`flex h-5 w-9 shrink-0 items-center rounded-full border p-0.5 transition ${todayLog.meds?.pregabalina ? 'justify-end border-white/40 bg-white/20' : 'justify-start border-border-standard bg-white'}`}>
                                                        <span className={`h-3.5 w-3.5 rounded-full transition ${todayLog.meds?.pregabalina ? 'bg-white' : 'bg-on-surface-variant/50'}`} />
                                                    </span>
                                                    <span className="text-sm font-bold">{todayLog.meds?.pregabalina ? 'Tomou' : 'Não tomou'}</span>
                                                </div>
                                            </button>
                                            <div className="rounded-xl border border-border-subtle bg-background p-3">
                                                <span className={labelClasses}>Dipirona</span>
                                                <div className="mt-1 flex items-center justify-between gap-2">
                                                    <button type="button" onClick={() => updateMeds({ dipirona: Math.max(0, (todayLog.meds?.dipirona || 0) - 1) })} className="h-7 w-7 rounded-lg border border-border-standard text-sm font-bold text-on-surface-variant">−</button>
                                                    <span className="text-sm font-bold text-on-surface">{todayLog.meds?.dipirona || 0}</span>
                                                    <button type="button" onClick={() => updateMeds({ dipirona: (todayLog.meds?.dipirona || 0) + 1 })} className="h-7 w-7 rounded-lg border border-border-standard text-sm font-bold text-on-surface-variant">+</button>
                                                </div>
                                            </div>
                                            <div className="rounded-xl border border-border-subtle bg-background p-3">
                                                <span className={labelClasses}>Adorlan</span>
                                                <div className="mt-1 flex items-center justify-between gap-2">
                                                    <button type="button" onClick={() => updateMeds({ adorlan: Math.max(0, (todayLog.meds?.adorlan || 0) - 1) })} className="h-7 w-7 rounded-lg border border-border-standard text-sm font-bold text-on-surface-variant">−</button>
                                                    <span className="text-sm font-bold text-on-surface">{todayLog.meds?.adorlan || 0}</span>
                                                    <button type="button" onClick={() => updateMeds({ adorlan: (todayLog.meds?.adorlan || 0) + 1 })} className="h-7 w-7 rounded-lg border border-border-standard text-sm font-bold text-on-surface-variant">+</button>
                                                </div>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => updateMeds({ fexofenadina: !todayLog.meds?.fexofenadina })}
                                                className={`rounded-xl border p-3 text-left transition ${todayLog.meds?.fexofenadina ? 'border-primary-container bg-primary-container text-white' : 'border-border-subtle bg-background text-on-surface'}`}
                                            >
                                                <span className={`${labelClasses} ${todayLog.meds?.fexofenadina ? 'text-white/80' : ''}`}>Fexofenadina</span>
                                                <div className="mt-2 flex items-center gap-2">
                                                    <span className={`flex h-5 w-9 shrink-0 items-center rounded-full border p-0.5 transition ${todayLog.meds?.fexofenadina ? 'justify-end border-white/40 bg-white/20' : 'justify-start border-border-standard bg-white'}`}>
                                                        <span className={`h-3.5 w-3.5 rounded-full transition ${todayLog.meds?.fexofenadina ? 'bg-white' : 'bg-on-surface-variant/50'}`} />
                                                    </span>
                                                    <span className="text-sm font-bold">{todayLog.meds?.fexofenadina ? 'Tomou' : 'Não tomou'}</span>
                                                </div>
                                            </button>
                                        </div>
                                        <input
                                            type="text"
                                            value={todayLog.meds?.outros || ''}
                                            onChange={e => updateMeds({ outros: e.target.value })}
                                            placeholder="Outros medicamentos (opcional)"
                                            className={`${inputClasses} mt-2`}
                                        />
                                    </div>

                                    <div>
                                        <p className={`${labelClasses} mb-2`}>Evento / gatilho</p>
                                        <ChipGroup
                                            options={TRIGGER_TYPES}
                                            value={todayLog.triggers?.types || []}
                                            onChange={(next: TriggerType[]) => onSaveExerciseLog(selectedDate, { triggers: { types: next, note: todayLog.triggers?.note } })}
                                            multi
                                        />
                                        <input
                                            type="text"
                                            value={todayLog.triggers?.note || ''}
                                            onChange={e => onSaveExerciseLog(selectedDate, { triggers: { types: todayLog.triggers?.types || [], note: e.target.value } })}
                                            placeholder="Descreva o gatilho (opcional)"
                                            className={`${inputClasses} mt-2`}
                                        />
                                    </div>

                                    <div>
                                        <span className={labelClasses}>Observação do dia</span>
                                        <textarea
                                            value={todayLog.note || ''}
                                            onChange={e => onSaveExerciseLog(selectedDate, { note: e.target.value })}
                                            placeholder="Nota curta opcional"
                                            className="mt-1 min-h-[72px] w-full rounded-xl border border-border-standard bg-background p-3 text-sm text-on-surface outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container"
                                        />
                                    </div>
                                </div>
                            </HealthSection>
                        </div>
                    </div>
                )}
                {activeTab === 'charts' && (
                        <div className="space-y-6">
                            <HealthSection title="Evolução do sintoma radicular" eyebrow="Centralização vs. periferalização">
                                <RadicularTimelineChart points={radicularSeries} isDark={isDark} />
                                <p className="mt-3 text-xs font-semibold leading-relaxed text-on-surface-variant">
                                    Sintoma subindo em direção à lombar (do pé para o quadril) tende a indicar melhora; descendo em
                                    direção ao pé tende a indicar piora.
                                </p>
                            </HealthSection>

                            <HealthSection title="Tendência de dor lombar" eyebrow="Histórico do Telegram e painel">
                                <PainTrendChart points={painTrendPoints} isDark={isDark} />
                                <p className="mt-3 text-xs font-semibold leading-relaxed text-on-surface-variant">
                                    Os pontos de noite incluem respostas do check-in no Telegram. Registros manuais feitos no painel aparecem junto no mesmo histórico.
                                </p>
                            </HealthSection>

                            <HealthSection title="O que anda junto" eyebrow="Painel de correlação">
                                {correlationRows.length > 0 ? (
                                    <div className="space-y-2">
                                        {correlationRows.map(row => (
                                            <div key={row.key} className="rounded-xl border border-border-subtle bg-background p-3 text-sm">
                                                {row.comparison.suppressed ? (
                                                    <p className="text-on-surface-variant">
                                                        Dor nos dias em que houve <strong className="text-on-surface">{row.label}</strong>: dados insuficientes
                                                        <span className="text-xs"> ({row.comparison.withN} vs. {row.comparison.withoutN} dias — mínimo 8 em cada grupo)</span>
                                                    </p>
                                                ) : (
                                                    <p className="text-on-surface-variant">
                                                        Dor média nos dias em que houve <strong className="text-on-surface">{row.label}</strong>: <strong className="text-on-surface">{row.comparison.withAvg?.toFixed(1).replace('.', ',')}</strong>
                                                        {' · '}nos demais dias: <strong className="text-on-surface">{row.comparison.withoutAvg?.toFixed(1).replace('.', ',')}</strong>
                                                        <span className="text-xs"> ({row.comparison.withN} vs. {row.comparison.withoutN} dias)</span>
                                                    </p>
                                                )}
                                            </div>
                                        ))}
                                        <p className="pt-1 text-xs font-semibold italic text-on-surface-variant">Associação não é causa.</p>
                                    </div>
                                ) : (
                                    <p className="text-xs font-semibold text-on-surface-variant">
                                        Ainda não há registros de dor suficientes para calcular comparações.
                                    </p>
                                )}
                            </HealthSection>

                            <HealthSection title="Tendência de peso" eyebrow="Biometria histórica">
                                <WeightTrendChart points={weightTrendPoints} targetWeight={settings.targetWeight} projectionLines={weightProjectionLines} isDark={isDark} />
                                {targetDelta !== null && (
                                    <p className="mt-3 text-xs font-semibold text-on-surface-variant">
                                        Distância até a meta: {targetDelta > 0 ? '+' : ''}{targetDelta.toFixed(1).replace('.', ',')} kg.
                                    </p>
                                )}
                                {recentWeightPoints.length < MIN_TREND_POINTS ? (
                                    <p className="mt-2 text-xs font-semibold text-on-surface-variant">
                                        Faltam registros recentes para projetar uma tendência — {recentWeightPoints.length} de {MIN_TREND_POINTS} pesagens necessárias nas últimas 4 semanas.
                                    </p>
                                ) : !trendIsDecreasing && (
                                    <p className="mt-2 text-xs font-semibold text-on-surface-variant">
                                        Sem tendência de queda nas últimas 4 semanas — os marcos abaixo não têm data estimada.
                                    </p>
                                )}
                                {milestoneDates.length > 0 && (
                                    <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                                        {milestoneDates.map(({ target, dateStr }) => (
                                            <div key={target} className="rounded-xl border border-border-subtle bg-background p-3">
                                                <span className={labelClasses}>{target} kg</span>
                                                <div className="mt-1 text-sm font-bold text-on-surface">
                                                    {dateStr ? formatApproxMonth(dateStr) : 'Sem tendência de queda'}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </HealthSection>
                        </div>
                )}
                {activeTab === 'reminders' && (
                            <HealthSection title="Lembretes Telegram" eyebrow="Intervenções leves">
                                <div className="mb-4 flex justify-end">
                                    <button
                                        type="button"
                                        ref={addReminderTriggerRef}
                                        onClick={() => setIsAddReminderOpen(true)}
                                        className="flex items-center gap-2 rounded-xl bg-primary-container px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90"
                                    >
                                        <Icon name="plus" className="h-4 w-4" />
                                        Adicionar lembrete
                                    </button>
                                </div>
                                {isAddReminderOpen && (
                                    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 py-10" onClick={() => setIsAddReminderOpen(false)}>
                                        <div role="dialog" aria-modal="true" aria-labelledby="add-reminder-modal-title" className="w-full max-w-lg rounded-2xl border border-border-subtle bg-white p-5 shadow-card" onClick={e => e.stopPropagation()}>
                                            <div className="mb-3 flex items-center justify-between">
                                                <p id="add-reminder-modal-title" className={labelClasses}>Novo lembrete</p>
                                                <button type="button" onClick={() => setIsAddReminderOpen(false)} aria-label="Fechar" className="rounded-lg px-2 py-1 text-sm font-bold text-on-surface-variant transition hover:bg-surface-container-low">✕</button>
                                            </div>
                                            <div className="space-y-3">
                                                <label className="block">
                                                    <span className={labelClasses}>Título</span>
                                                    <input
                                                        ref={addReminderTituloRef}
                                                        type="text"
                                                        value={newReminderTitle}
                                                        onChange={e => setNewReminderTitle(e.target.value)}
                                                        placeholder="Ex: Alongamento pós-almoço"
                                                        className={inputClasses}
                                                    />
                                                </label>
                                                <label className="block">
                                                    <span className={labelClasses}>Mensagem</span>
                                                    <input
                                                        type="text"
                                                        value={newReminderMessage}
                                                        onChange={e => setNewReminderMessage(e.target.value)}
                                                        placeholder="André, lembrete de saúde configurado no Hermes."
                                                        className={inputClasses}
                                                    />
                                                </label>
                                                <label className="block w-fit">
                                                    <span className={labelClasses}>Horário</span>
                                                    <input
                                                        type="time"
                                                        value={newReminderTime}
                                                        onChange={e => setNewReminderTime(e.target.value)}
                                                        className={inputClasses}
                                                    />
                                                </label>
                                                <div>
                                                    <span className={labelClasses}>Dias</span>
                                                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                                        {WEEKDAY_LABELS.map((label, day) => {
                                                            const active = newReminderDays.includes(day);
                                                            return (
                                                                <button
                                                                    key={day}
                                                                    type="button"
                                                                    title={WEEKDAY_NAMES[day]}
                                                                    aria-label={`${WEEKDAY_NAMES[day]} — ${active ? 'ativo' : 'inativo'}`}
                                                                    aria-pressed={active}
                                                                    onClick={() => {
                                                                        const next = active ? newReminderDays.filter(d => d !== day) : [...newReminderDays, day];
                                                                        if (next.length === 0) return;
                                                                        setNewReminderDays(next.sort());
                                                                    }}
                                                                    className={`flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold transition ${active ? 'bg-primary-container text-white' : 'bg-white text-on-surface-variant border border-border-standard'}`}
                                                                >
                                                                    {label}
                                                                </button>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={handleCreateReminder}
                                                    disabled={!newReminderTitle.trim()}
                                                    className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-primary-container px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                                                >
                                                    <Icon name="plus" className="h-4 w-4" />
                                                    Adicionar lembrete
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )}
                                <div className="space-y-3">
                                    {activeReminders.map(reminder => (
                                        <ReminderCard
                                            key={reminder.id}
                                            reminder={reminder}
                                            isDefault={DEFAULT_HEALTH_REMINDERS.some(defaultReminder => defaultReminder.id === reminder.id)}
                                            onSave={onSaveTelegramReminder}
                                            onDelete={onDeleteTelegramReminder}
                                        />
                                    ))}
                                </div>
                            </HealthSection>
                )}
                {activeTab === 'report' && (
                    <HealthSection title="Relatório semanal" eyebrow="Placar de resultado — domingo 19h">
                        {weeklyReports.length === 0 ? (() => {
                            // Data real da próxima geração, não "próximo domingo" solto — ambíguo
                            // justamente quando hoje já é domingo antes das 19h (achado N18).
                            const now = new Date();
                            const nextRun = new Date(now);
                            const daysUntilSunday = (7 - nextRun.getDay()) % 7;
                            nextRun.setDate(nextRun.getDate() + daysUntilSunday);
                            if (daysUntilSunday === 0 && now.getHours() >= 19) nextRun.setDate(nextRun.getDate() + 7);
                            const isToday = daysUntilSunday === 0 && now.getHours() < 19;
                            const nextRunLabel = `${isToday ? 'hoje, ' : ''}domingo ${nextRun.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}`;
                            return (
                                <p className="text-sm font-semibold text-on-surface-variant">
                                    Ainda não há relatório gerado. O primeiro sai automaticamente {nextRunLabel} às 19h.
                                </p>
                            );
                        })() : (() => {
                            const [latest, ...history] = weeklyReports;
                            const card = latest.card;
                            const fmt1 = (v: number | null, suffix = '') => v !== null ? `${v.toFixed(1).replace('.', ',')}${suffix}` : 'ainda não dá para dizer';
                            const radicularLabel: Record<string, string> = {
                                subindo: 'Subindo (centralizando — bom sinal)',
                                descendo: 'Descendo (periferalizando — atenção)',
                                estável: 'Estável',
                                sem_dado: 'Sem dado suficiente',
                            };
                            const stat = (label: string, value: React.ReactNode) => (
                                <div>
                                    <p className="text-[10px] font-semibold uppercase text-on-surface-variant">{label}</p>
                                    <p className="text-sm font-bold text-on-surface">{value}</p>
                                </div>
                            );
                            return (
                                <div className="space-y-6">
                                    <div className="rounded-2xl border border-border-subtle bg-background p-5">
                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                            <p className={labelClasses}>Semana {formatShortDate(card.week_start)} a {formatShortDate(card.week_end)}</p>
                                            <span className="rounded-full bg-primary-container px-2.5 py-1 text-[10px] font-semibold uppercase text-white">Mais recente</span>
                                        </div>
                                        <p className="mt-2 text-xs font-medium text-on-surface-variant">
                                            Fase 1 do relatório — só o placar calculado, sem narrativa nem ajuste sugerido ainda.
                                        </p>
                                        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
                                            {stat('Peso méd. 7d', <>{fmt1(card.weight_avg7, ' kg')}{card.weight_delta !== null && <span className="ml-1 text-xs font-semibold text-on-surface-variant">({card.weight_delta > 0 ? '+' : ''}{card.weight_delta.toFixed(1).replace('.', ',')})</span>}</>)}
                                            {stat('Cintura', card.waist.value !== null ? <>{fmt1(card.waist.value, ' cm')}{card.waist.delta !== null && <span className="ml-1 text-xs font-semibold text-on-surface-variant">({card.waist.delta > 0 ? '+' : ''}{card.waist.delta.toFixed(1).replace('.', ',')})</span>}</> : 'ainda não dá para dizer')}
                                            {stat('Km na semana', `${formatKm(card.km_total)} km em ${card.km_days} dia(s)`)}
                                            {stat('Dor manhã / noite', `${card.pain_morning_avg ?? '—'} / ${card.pain_evening_avg ?? '—'}`)}
                                            {stat('Sintoma radicular', radicularLabel[card.radicular_trend] || card.radicular_trend)}
                                            {stat('Treino de força', `${card.strength_done}/${card.strength_planned}`)}
                                            {stat('Terapia', `${card.therapy_done}/${card.therapy_planned}`)}
                                            {stat('Aderência ao check-in', `${Math.round(card.checkin_adherence * 100)}%`)}
                                            {stat('Sono médio', fmt1(card.sleep_avg, '/5'))}
                                        </div>
                                    </div>
                                    {history.length > 0 && (
                                        <div>
                                            <p className={`${labelClasses} mb-2`}>Histórico</p>
                                            <div className="space-y-2">
                                                {history.map(report => (
                                                    <div key={report.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border-subtle bg-background px-4 py-2.5 text-xs font-semibold text-on-surface-variant">
                                                        <span>{formatShortDate(report.card.week_start)} a {formatShortDate(report.card.week_end)}</span>
                                                        <span>{fmt1(report.card.weight_avg7, ' kg')}</span>
                                                        <span>{formatKm(report.card.km_total)} km</span>
                                                        <span>check-in {Math.round(report.card.checkin_adherence * 100)}%</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        })()}
                    </HealthSection>
                )}
                {activeTab === 'archive' && (
                    <HealthSection title="Arquivo médico" eyebrow="Exames e consultas">
                        <div className="flex justify-end">
                            <button
                                type="button"
                                ref={addExamTriggerRef}
                                onClick={() => setIsAddExamOpen(true)}
                                className="flex items-center gap-2 rounded-xl bg-primary-container px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90"
                            >
                                <Icon name="plus" className="h-4 w-4" />
                                Adicionar registro
                            </button>
                        </div>
                        {isAddExamOpen && (
                        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 py-10" onClick={() => setIsAddExamOpen(false)}>
                        <div role="dialog" aria-modal="true" aria-labelledby="add-exam-modal-title" className="w-full max-w-3xl rounded-2xl border border-border-subtle bg-white p-5 shadow-card" onClick={e => e.stopPropagation()}>
                            <div className="mb-3 flex items-center justify-between">
                                <p id="add-exam-modal-title" className={labelClasses}>Novo registro</p>
                                <button type="button" onClick={() => setIsAddExamOpen(false)} aria-label="Fechar" className="rounded-lg px-2 py-1 text-sm font-bold text-on-surface-variant transition hover:bg-surface-container-low">✕</button>
                            </div>
                            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                <label className="block">
                                    <span className={labelClasses}>Título</span>
                                    <input
                                        ref={addExamTituloRef}
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
                                        onChange={e => setExamTipo(e.target.value as HealthExamTipo)}
                                        className={inputClasses}
                                    >
                                        {HEALTH_EXAM_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
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
                                    <span className={labelClasses}>Achados-chave</span>
                                    <input
                                        type="text"
                                        value={examAchadosChave}
                                        onChange={e => setExamAchadosChave(e.target.value)}
                                        placeholder="Resumo em uma linha (opcional)"
                                        className={inputClasses}
                                    />
                                </label>
                                <label className="block">
                                    <span className={labelClasses}>Profissional</span>
                                    <input
                                        type="text"
                                        value={examProfissional}
                                        onChange={e => setExamProfissional(e.target.value)}
                                        placeholder="Opcional"
                                        className={inputClasses}
                                    />
                                </label>
                                <label className="block">
                                    <span className={labelClasses}>Especialidade</span>
                                    <input
                                        type="text"
                                        value={examEspecialidade}
                                        onChange={e => setExamEspecialidade(e.target.value)}
                                        placeholder="Opcional"
                                        className={inputClasses}
                                    />
                                </label>
                                <label className="block">
                                    <span className={labelClasses}>Próxima reavaliação</span>
                                    <input
                                        type="date"
                                        value={examProximaReavaliacao}
                                        onChange={e => setExamProximaReavaliacao(e.target.value)}
                                        className={inputClasses}
                                    />
                                </label>
                                <label className="block">
                                    <span className={labelClasses}>Tags</span>
                                    <input
                                        type="text"
                                        value={examTags}
                                        onChange={e => setExamTags(e.target.value)}
                                        placeholder="Separadas por vírgula"
                                        className={inputClasses}
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
                        </div>
                        )}

                        {sortedExams.length > 0 ? (
                            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                                {sortedExams.map(exam => (
                                    <article key={exam.id} className="rounded-2xl border border-border-subtle bg-background p-5">
                                        {editingExamId === exam.id ? (
                                            <div className="flex flex-col gap-3">
                                                <span className="w-fit rounded-full bg-surface-container-low px-2.5 py-1 text-[10px] font-semibold uppercase text-on-surface-variant">Editando</span>
                                                <label className="block">
                                                    <span className={labelClasses}>Título</span>
                                                    <input type="text" value={editTitulo} onChange={e => setEditTitulo(e.target.value)} className={inputClasses} />
                                                </label>
                                                <div className="grid grid-cols-2 gap-3">
                                                    <label className="block">
                                                        <span className={labelClasses}>Tipo</span>
                                                        <select value={editTipo} onChange={e => setEditTipo(e.target.value as HealthExamTipo)} className={inputClasses}>
                                                            {HEALTH_EXAM_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                                                        </select>
                                                    </label>
                                                    <label className="block">
                                                        <span className={labelClasses}>Data</span>
                                                        <input type="date" value={editData} onChange={e => setEditData(e.target.value)} className={inputClasses} />
                                                    </label>
                                                </div>
                                                <label className="block">
                                                    <span className={labelClasses}>Doutor(a) / Local</span>
                                                    <input type="text" value={editDoutorLocal} onChange={e => setEditDoutorLocal(e.target.value)} placeholder="Opcional" className={inputClasses} />
                                                </label>
                                                <label className="block">
                                                    <span className={labelClasses}>Resultados / notas</span>
                                                    <textarea value={editResultados} onChange={e => setEditResultados(e.target.value)} placeholder="Opcional" className={`${inputClasses} min-h-[64px]`} />
                                                </label>
                                                <label className="block">
                                                    <span className={labelClasses}>Achados-chave</span>
                                                    <input type="text" value={editAchadosChave} onChange={e => setEditAchadosChave(e.target.value)} placeholder="Opcional" className={inputClasses} />
                                                </label>
                                                <div className="grid grid-cols-2 gap-3">
                                                    <label className="block">
                                                        <span className={labelClasses}>Profissional</span>
                                                        <input type="text" value={editProfissional} onChange={e => setEditProfissional(e.target.value)} placeholder="Opcional" className={inputClasses} />
                                                    </label>
                                                    <label className="block">
                                                        <span className={labelClasses}>Especialidade</span>
                                                        <input type="text" value={editEspecialidade} onChange={e => setEditEspecialidade(e.target.value)} placeholder="Opcional" className={inputClasses} />
                                                    </label>
                                                </div>
                                                <div className="grid grid-cols-2 gap-3">
                                                    <label className="block">
                                                        <span className={labelClasses}>Próxima reavaliação</span>
                                                        <input type="date" value={editProximaReavaliacao} onChange={e => setEditProximaReavaliacao(e.target.value)} className={inputClasses} />
                                                    </label>
                                                    <label className="block">
                                                        <span className={labelClasses}>Tags</span>
                                                        <input type="text" value={editTags} onChange={e => setEditTags(e.target.value)} placeholder="Separadas por vírgula" className={inputClasses} />
                                                    </label>
                                                </div>
                                                {exam.pool_dados && exam.pool_dados.length > 0 && (
                                                    <div className="flex flex-wrap gap-2">
                                                        {exam.pool_dados.map(file => (
                                                            <span key={file.id} title={file.nome || 'Arquivo'} className="inline-flex max-w-[160px] items-center gap-1.5 rounded-lg border border-border-standard bg-white px-2 py-1 text-[10px] font-semibold text-on-surface-variant">
                                                                <Icon name="file" className="h-3 w-3 shrink-0" />
                                                                <span className="min-w-0 truncate">{file.nome || 'Arquivo'}</span>
                                                            </span>
                                                        ))}
                                                    </div>
                                                )}
                                                <label className="block">
                                                    <span className={labelClasses}>Anexar mais arquivos</span>
                                                    <input
                                                        type="file"
                                                        multiple
                                                        onChange={e => setEditFiles(e.target.files ? Array.from(e.target.files) : [])}
                                                        className={`${inputClasses} file:mr-3 file:rounded-lg file:border-0 file:bg-primary-container file:px-3 file:py-1.5 file:text-xs file:font-bold file:text-white`}
                                                    />
                                                    {editFiles.length > 0 && (
                                                        <p className="mt-1 text-xs font-medium text-on-surface-variant">{editFiles.length} arquivo(s) selecionado(s)</p>
                                                    )}
                                                </label>
                                                <div className="mt-1 flex items-center gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={handleSaveEditExam}
                                                        disabled={!editTitulo.trim() || !editData || isSavingEditExam}
                                                        className="flex-1 rounded-xl bg-primary-container px-4 py-2 text-sm font-bold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                                                    >
                                                        {isSavingEditExam ? 'Salvando...' : 'Salvar'}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={cancelEditExam}
                                                        className="rounded-xl border border-border-standard px-4 py-2 text-sm font-semibold text-on-surface-variant transition hover:bg-surface-container-low"
                                                    >
                                                        Cancelar
                                                    </button>
                                                </div>
                                            </div>
                                        ) : (
                                            <>
                                                <div className="flex items-start justify-between gap-3">
                                                    <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[10px] font-semibold uppercase text-on-surface-variant">{HEALTH_EXAM_TYPES.find(t => t.value === exam.tipo)?.label || exam.tipo}</span>
                                                    <div className="flex items-center gap-1">
                                                        <span className="text-xs font-semibold text-on-surface-variant">{formatDate(exam.data)}</span>
                                                        <button
                                                            type="button"
                                                            onClick={() => startEditExam(exam)}
                                                            className="rounded-lg p-1.5 text-on-surface-variant transition hover:bg-surface-container-low hover:text-primary-container"
                                                            aria-label="Editar registro"
                                                        >
                                                            <Icon name="edit" className="h-4 w-4" />
                                                        </button>
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
                                                <p className="mt-1 text-sm text-on-surface-variant">{exam.doutor_local || 'Local não informado'}</p>
                                                {exam.achadosChave && (
                                                    <p className="mt-2 text-sm font-semibold text-on-surface">{exam.achadosChave}</p>
                                                )}
                                                {(exam.profissional || exam.especialidade) && (
                                                    <p className="mt-1 text-xs text-on-surface-variant">
                                                        {[exam.profissional, exam.especialidade].filter(Boolean).join(' · ')}
                                                    </p>
                                                )}
                                                {exam.resultados && (
                                                    <p className="mt-2 whitespace-pre-wrap text-sm text-on-surface-variant">{renderTextWithLinks(exam.resultados)}</p>
                                                )}
                                                {exam.proximaReavaliacao && (() => {
                                                    const daysUntil = daysSinceEpoch(exam.proximaReavaliacao) - daysSinceEpoch(formatDateLocalISO(new Date()));
                                                    const tone = daysUntil < 0 ? 'error' : daysUntil <= 30 ? 'amber' : 'neutral';
                                                    const daysLabel = daysUntil < 0
                                                        ? `atrasada há ${Math.abs(daysUntil)} dia${Math.abs(daysUntil) === 1 ? '' : 's'}`
                                                        : daysUntil === 0
                                                            ? 'hoje'
                                                            : `em ${daysUntil} dia${daysUntil === 1 ? '' : 's'}`;
                                                    const toneClasses = tone === 'error' ? 'bg-error-container text-on-error-container' : tone === 'amber' ? 'bg-amber-100 text-amber-700' : 'bg-surface-container-low text-on-surface-variant';
                                                    return (
                                                        <p className={`mt-2 inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${toneClasses}`}>
                                                            Próxima reavaliação {daysLabel} ({formatDate(exam.proximaReavaliacao)})
                                                        </p>
                                                    );
                                                })()}
                                                {exam.tags && exam.tags.length > 0 && (
                                                    <div className="mt-2 flex flex-wrap gap-1.5">
                                                        {exam.tags.map(tag => (
                                                            <span key={tag} className="rounded-full bg-surface-container-low px-2 py-0.5 text-[10px] font-semibold text-on-surface-variant">{tag}</span>
                                                        ))}
                                                    </div>
                                                )}
                                                {exam.pool_dados && exam.pool_dados.length > 0 && (
                                                    <div className="mt-4 flex flex-wrap gap-2">
                                                        {exam.pool_dados.map(file => (
                                                            <a key={file.id} href={file.valor} target="_blank" rel="noreferrer" title={file.nome || 'Arquivo'} className="inline-flex max-w-[160px] items-center gap-2 rounded-lg border border-border-standard bg-white px-3 py-2 text-xs font-semibold text-on-surface-variant transition hover:border-primary-container hover:text-primary-container">
                                                                <Icon name="file" className="h-4 w-4 shrink-0" />
                                                                <span className="min-w-0 truncate">{file.nome || 'Arquivo'}</span>
                                                            </a>
                                                        ))}
                                                    </div>
                                                )}
                                            </>
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
