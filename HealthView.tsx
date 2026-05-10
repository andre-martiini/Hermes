import React, { useState, useMemo } from 'react';
import { HealthWeight, DailyHabits, HealthSettings, ExerciseLog, ExerciseSettings, PullupPhase, formatDate, formatDateLocalISO, HealthExam, PoolItem } from './types';

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
    onSaveExerciseLog: (date: string, data: Partial<Pick<ExerciseLog, 'pushups' | 'pullups' | 'walk'>>) => Promise<void>;
    exams: HealthExam[];
    onAddExam: (exam: Omit<HealthExam, 'id' | 'data_criacao' | 'pool_dados'>, files: File[]) => void;
    onDeleteExam: (id: string) => void;
    onUpdateExam: (id: string, updates: Partial<HealthExam>) => void;
    isDark?: boolean;
}

const HealthSection = ({ title, children, iconColor, defaultExpanded = true }: { title: string, children: React.ReactNode, iconColor: string, defaultExpanded?: boolean }) => {
    const [isExpanded, setIsExpanded] = useState(defaultExpanded);

    return (
        <div className="bg-surface p-6 md:p-10 rounded-none border border-border-grid shadow-none relative overflow-hidden group">
            {/* Elemento Decorativo Industrial */}
            <div className={`absolute top-0 left-0 w-1 h-full ${iconColor} opacity-50`}></div>
            
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full flex items-center justify-between group/btn"
            >
                <div className="flex flex-col items-start gap-1">
                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.3em]">// SECTION_NODE</span>
                    <h3 className="text-2xl font-serif italic text-on-surface tracking-tight text-left">{title}</h3>
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

const HabitHeatmap = ({ habits, selectedDate, onSelectDate }: { habits: DailyHabits[], selectedDate: string, onSelectDate: (date: string) => void }) => {
    const today = new Date();
    const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    const monthName = new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(today);
    const todayStr = formatDateLocalISO(today);

    return (
        <HealthSection title={`Consistência_Mensal • ${monthName}`} iconColor="bg-primary-tactile">
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-10 border-b border-border-grid border-dashed pb-8">
                <div>
                    <h4 className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.2em] mb-2">// HABIT_PERFORMANCE_METRICS</h4>
                    <p className="text-xs font-serif italic text-slate-500">Volume de hábitos cumpridos processado por ciclo diário.</p>
                </div>
                <div className="flex items-center gap-4 bg-slate-50 p-4 rounded-none border border-border-grid">
                    <span className="text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest">LEGEND:</span>
                    <div className="flex gap-2">
                        {[0, 1, 2, 3, 4, 5, 6].map(c => (
                            <div key={c} className="w-5 h-5 rounded-soft-touch border border-white/20 shadow-sm" title={`${c} hábitos`} style={{ backgroundColor: `hsl(${(c / 6) * 120}, 60%, 50%)` }}></div>
                        ))}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-7 sm:grid-cols-10 md:grid-cols-15 lg:grid-cols-[repeat(31,minmax(0,1fr))] gap-2 sm:gap-2.5 overflow-x-auto pb-4">
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
                    let style: React.CSSProperties = { backgroundColor: 'transparent', color: '#cbd5e1', border: '1px solid #e2e8f0' };

                    if (hasRecord) {
                        const hue = ratio * 120;
                        style = {
                            backgroundColor: `hsl(${hue}, 60%, 50%)`,
                            color: 'white',
                            border: isSelected ? '2px solid black' : '1px solid rgba(255,255,255,0.2)',
                            boxShadow: isSelected ? `0 0 0 2px white, 0 0 0 4px hsl(${hue}, 60%, 50%)` : 'none'
                        };
                    } else if (isSelected) {
                        style = {
                            backgroundColor: '#e2e8f0',
                            color: '#475569',
                            border: '2px solid #64748b',
                            boxShadow: `0 0 0 2px white, 0 0 0 4px #cbd5e1`
                        };
                    }

                    return (
                        <button
                            key={day}
                            disabled={isFuture}
                            onClick={() => onSelectDate(dateStr)}
                            title={isFuture ? `Data futura` : hasRecord ? `Dia ${day}: ${completedCount}/6 hábitos` : `Dia ${day}: Sem registro`}
                            className={`aspect-square rounded-soft-touch flex items-center justify-center text-[9px] md:text-[10px] font-mono font-bold transition-all duration-300 ${isFuture ? 'opacity-10 cursor-not-allowed' : 'hover:scale-110 hover:z-10 cursor-pointer'} ${isSelected ? 'scale-110 z-10' : ''}`}
                            style={style}
                        >
                            {String(day).padStart(2, '0')}
                        </button>
                    );
                })}
            </div>
        </HealthSection>
    );
};

const PULLUP_PHASE_LABELS: Record<PullupPhase, { name: string; metric: string; gate: string; tip: string }> = {
    dead_hang: { name: 'Fase 1 — Barra Parada', metric: 'segundos pendurado', gate: 'Meta de avanço: 30s contínuos (2 sessões)', tip: 'Segure-se na barra com os braços estendidos. Foco no grip.' },
    negative: { name: 'Fase 2 — Negativas', metric: 'repetições', gate: 'Meta de avanço: 5 negativas (2 sessões)', tip: 'Suba com auxílio e desça bem devagar (~5s). Foco no controle.' },
    assisted: { name: 'Fase 3 — Barra Assistida', metric: 'repetições', gate: 'Meta de avanço: 8 repetições (2 sessões)', tip: 'Use faixa elástica na barra para reduzir o peso corporal.' },
    full: { name: 'Fase 4 — Barra Completa', metric: 'repetições', gate: '', tip: 'Puxada completa do zero até o queixo acima da barra.' },
};

interface ProtocolStep {
    label: string;
    detail?: string;
}

function getProtocol(
    exercise: 'pushups' | 'pullups' | 'walk',
    goal: number,
    phase?: PullupPhase
): ProtocolStep[] {
    if (exercise === 'walk') {
        return [
            { label: '5 min aquecimento', detail: 'Caminhada leve para preparar as articulações' },
            { label: 'Ritmo constante', detail: 'Mantenha um passo que permita conversar' },
            { label: 'Hidrate a cada 30 min', detail: 'Tome pelo menos um gole de água' },
            { label: '5 min desaquecimento', detail: 'Reduza o ritmo gradualmente nos últimos 5 min' },
        ];
    }

    if (exercise === 'pullups') {
        const ph = phase ?? 'dead_hang';
        if (ph === 'dead_hang') {
            const targetSec = Math.max(5, Math.round(goal * 0.7));
            const sets = 3;
            return [
                { label: `${sets} séries de ${targetSec}s pendurado`, detail: 'Braços estendidos, grip firme, ombros ativos' },
                { label: '90s de descanso entre séries', detail: 'Solte, respire fundo, aguarde' },
                { label: 'Se aguentar mais, ótimo!', detail: 'Registre o total do melhor set' },
            ];
        }
        if (ph === 'negative') {
            return [
                { label: `${goal} negativas no total`, detail: 'Suba com auxílio (banco ou impulso), desça em ~5s' },
                { label: 'Desça controlado — 5 a 8 segundos', detail: 'Sinta a tensão nos dorsais durante a descida' },
                { label: '2 min de descanso entre repetições', detail: 'Recupere bem antes da próxima' },
            ];
        }
        if (ph === 'assisted') {
            const sets = 3;
            const repsPerSet = Math.ceil(goal / sets);
            return [
                { label: `${sets} séries de ${repsPerSet} repetições`, detail: 'Use faixa elástica para reduzir o peso' },
                { label: '2 min de descanso entre séries', detail: 'Aguarde antes de iniciar a próxima série' },
                { label: 'Movimento completo', detail: 'Braços estendidos embaixo, queixo acima da barra em cima' },
            ];
        }
        // full
        const sets = 3;
        const repsPerSet = Math.ceil(goal * 0.6);
        return [
            { label: `${sets} séries de ${repsPerSet} repetições`, detail: 'Puxada completa, sem embalo' },
            { label: '2 min de descanso entre séries', detail: 'Respire fundo e relaxe a musculatura' },
            { label: 'Controlado na descida', detail: '2–3 segundos para descer após o topo' },
        ];
    }

    // pushups
    if (goal <= 10) {
        const sets = 3;
        const reps = Math.ceil(goal * 0.6);
        return [
            { label: `${sets} séries de ${reps} repetições`, detail: 'Corpo reto, desça até o peito quase tocar o chão' },
            { label: '60s de descanso entre séries', detail: 'Descanse e respire antes de continuar' },
            { label: 'Última série: força máxima', detail: 'Faça o máximo que conseguir com boa forma' },
        ];
    }
    if (goal <= 20) {
        const sets = 3;
        const reps = Math.ceil(goal * 0.6);
        return [
            { label: `${sets} séries de ${reps} repetições`, detail: 'Ritmo constante, sem prender a respiração' },
            { label: '90s de descanso entre séries', detail: 'Levante-se e caminhe levemente' },
            { label: 'Última série: força máxima', detail: 'Tente ir além das repetições planejadas' },
        ];
    }
    // goal > 20
    const sets = 4;
    const reps = Math.ceil(goal * 0.5);
    return [
        { label: `${sets} séries de ${reps} repetições`, detail: 'Mantenha tensão no core durante todo o movimento' },
        { label: '90s de descanso entre séries', detail: 'Respire e movimente os braços levemente' },
        { label: 'Série final: máximo esforço', detail: 'Vá até a falha com boa técnica' },
    ];
}

const ProtocolPanel = ({ steps, accentClass }: { steps: ProtocolStep[]; accentClass: string }) => {
    const [open, setOpen] = useState(false);
    return (
        <div className="mt-4">
            <button
                onClick={() => setOpen(o => !o)}
                className={`flex items-center gap-2 text-[9px] font-mono font-bold uppercase tracking-[0.2em] ${accentClass} bg-surface border border-border-grid px-3 py-1.5 rounded-soft-touch transition-all hover:bg-slate-100`}
            >
                <svg className={`w-3 h-3 transition-transform ${open ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                </svg>
                TRAINING_PROTOCOL
            </button>
            {open && (
                <div className="mt-4 p-4 bg-slate-50 border border-border-grid border-dashed rounded-none animate-in slide-in-from-top-2">
                    <ol className="space-y-3">
                        {steps.map((step, i) => (
                            <li key={i} className="flex gap-4">
                                <span className={`text-[10px] font-mono font-bold ${accentClass} opacity-60 mt-0.5 shrink-0`}>[{String(i + 1).padStart(2, '0')}]</span>
                                <div>
                                    <span className="text-[10px] font-mono font-bold text-on-surface uppercase block">{step.label}</span>
                                    {step.detail && (
                                        <span className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest mt-0.5 block">— {step.detail}</span>
                                    )}
                                </div>
                            </li>
                        ))}
                    </ol>
                </div>
            )}
        </div>
    );
};

const ExerciseGoalsSection = ({
    exerciseLogs,
    exerciseSettings,
    onSaveExerciseLog,
    selectedDate,
}: {
    exerciseLogs: ExerciseLog[];
    exerciseSettings: ExerciseSettings;
    onSaveExerciseLog: (date: string, data: Partial<Pick<ExerciseLog, 'pushups' | 'pullups' | 'walk'>>) => Promise<void>;
    selectedDate: string;
}) => {
    const todayLog = exerciseLogs.find(l => l.id === selectedDate);

    const [pushupsInput, setPushupsInput] = useState('');
    const [pullupsInput, setPullupsInput] = useState('');
    const [walkInput, setWalkInput] = useState('');
    const [saving, setSaving] = useState(false);

    const sortedLogs = useMemo(() =>
        [...exerciseLogs].sort((a, b) => b.id.localeCompare(a.id)),
        [exerciseLogs]
    );
    const recentPushups = sortedLogs.filter(l => l.pushups !== undefined).slice(0, 7);
    const recentPullups = sortedLogs.filter(l => l.pullups !== undefined).slice(0, 7);
    const recentWalks = sortedLogs.filter(l => l.walk !== undefined).slice(0, 7);

    const pushupsGoal = exerciseSettings.pushups?.activeGoal;
    const pullupPhase: PullupPhase = exerciseSettings.pullups?.phase ?? 'dead_hang';
    const pullupsGoal = exerciseSettings.pullups?.activeGoal;
    const pullupPhaseInfo = PULLUP_PHASE_LABELS[pullupPhase];

    const formatWalkDisplay = (minutes: number) => {
        const h = Math.floor(minutes / 60);
        const m = minutes % 60;
        return h > 0 ? `${h}h${m > 0 ? String(m).padStart(2, '0') : ''}` : `${m}min`;
    };

    const handleSave = async () => {
        const data: Partial<Pick<ExerciseLog, 'pushups' | 'pullups' | 'walk'>> = {};
        if (pushupsInput) {
            const done = parseInt(pushupsInput);
            data.pushups = { done, goal: pushupsGoal ?? done };
        }
        if (pullupsInput) {
            const done = parseInt(pullupsInput);
            data.pullups = { done, goal: pullupsGoal ?? done, phase: pullupPhase };
        }
        if (walkInput) {
            data.walk = { done: parseInt(walkInput) };
        }
        if (Object.keys(data).length === 0) return;
        setSaving(true);
        try {
            await onSaveExerciseLog(selectedDate, data);
            setPushupsInput('');
            setPullupsInput('');
            setWalkInput('');
        } finally {
            setSaving(false);
        }
    };

    const MiniHistory = ({ sessions, renderDot }: { sessions: ExerciseLog[]; renderDot: (log: ExerciseLog) => React.ReactNode }) => (
        <div className="flex gap-1.5 mt-3">
            {sessions.length === 0 ? (
                <span className="text-[9px] font-black text-slate-300 uppercase tracking-widest italic">sem histórico</span>
            ) : sessions.map(log => (
                <div key={log.id} title={log.id}>{renderDot(log)}</div>
            ))}
        </div>
    );

    return (
        <div className="space-y-10">
            <div>
                <h4 className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.3em] mb-2">// EXERCISE_LOG_STREAM</h4>
                <p className="text-xs font-serif italic text-slate-500">
                    Registre após os exercícios — metas se ajustam automaticamente baseado na performance histórica.
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

                {/* Flexões no chão */}
                <div className="bg-emerald-50/50 border border-emerald-100 rounded-none p-6 flex flex-col gap-4 relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-2 opacity-10">
                        <svg className="w-12 h-12 text-emerald-600" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2z"/></svg>
                    </div>
                    <div>
                        <span className="text-[9px] font-mono font-bold text-emerald-600 uppercase tracking-[0.2em]">// PUSHUPS_UNIT</span>
                        <div className="flex items-baseline gap-2 mt-2">
                            {pushupsGoal ? (
                                <>
                                    <span className="text-4xl font-mono font-bold text-on-surface tracking-tighter">{pushupsGoal}</span>
                                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">REPS_GOAL</span>
                                </>
                            ) : (
                                <span className="text-[10px] font-mono font-bold text-slate-400 uppercase italic">INITIALIZING_BASELINE...</span>
                            )}
                        </div>
                        {todayLog?.pushups && (
                            <div className={`mt-3 text-[10px] font-mono font-bold uppercase tracking-widest ${todayLog.pushups.done >= todayLog.pushups.goal ? 'text-emerald-600' : 'text-amber-600'}`}>
                                CURRENT_SESSION: {todayLog.pushups.done} REPS {todayLog.pushups.done >= todayLog.pushups.goal ? '[DONE]' : '[PENDING]'}
                            </div>
                        )}
                        <ProtocolPanel steps={getProtocol('pushups', pushupsGoal ?? 10)} accentClass="text-emerald-600" />
                    </div>
                    <div className="mt-auto space-y-4">
                        <div className="flex gap-2">
                            <input
                                type="number"
                                min="1"
                                placeholder="ENTER_VALUE"
                                value={pushupsInput}
                                onChange={e => setPushupsInput(e.target.value)}
                                className="w-full bg-white border border-border-grid rounded-soft-touch px-4 py-3 text-xs font-mono font-bold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500"
                            />
                        </div>
                        <div>
                            <span className="text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">RECENT_HISTORY (L7D)</span>
                            <MiniHistory sessions={recentPushups} renderDot={log => {
                                const hit = log.pushups!.done >= log.pushups!.goal;
                                return <div className={`w-5 h-5 rounded-soft-touch border border-white/20 shadow-sm ${hit ? 'bg-emerald-500' : 'bg-rose-400'}`} title={`${log.id}: ${log.pushups!.done}/${log.pushups!.goal}`} />;
                            }} />
                        </div>
                    </div>
                </div>

                {/* Barra */}
                <div className="bg-violet-50/50 border border-violet-100 rounded-none p-6 flex flex-col gap-4 relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-2 opacity-10">
                        <svg className="w-12 h-12 text-violet-600" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2z"/></svg>
                    </div>
                    <div>
                        <span className="text-[9px] font-mono font-bold text-violet-600 uppercase tracking-[0.2em]">// PULLUPS_UNIT</span>
                        <div className="flex items-baseline gap-2 mt-2">
                            {pullupsGoal ? (
                                <>
                                    <span className="text-4xl font-mono font-bold text-on-surface tracking-tighter">{pullupsGoal}</span>
                                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">{pullupPhaseInfo.metric.toUpperCase()}</span>
                                </>
                            ) : (
                                <span className="text-[10px] font-mono font-bold text-slate-400 uppercase italic">INITIALIZING_BASELINE...</span>
                            )}
                        </div>
                        <div className="mt-1 text-[9px] font-mono font-bold text-violet-500 uppercase tracking-widest">{pullupPhaseInfo.name}</div>
                        {todayLog?.pullups && (
                            <div className={`mt-3 text-[10px] font-mono font-bold uppercase tracking-widest ${todayLog.pullups.done >= todayLog.pullups.goal ? 'text-emerald-600' : 'text-amber-600'}`}>
                                CURRENT_SESSION: {todayLog.pullups.done} {todayLog.pullups.done >= todayLog.pullups.goal ? '[DONE]' : '[PENDING]'}
                            </div>
                        )}
                        <ProtocolPanel steps={getProtocol('pullups', pullupsGoal ?? 10, pullupPhase)} accentClass="text-violet-600" />
                    </div>
                    <div className="mt-auto space-y-4">
                        <div className="flex gap-2">
                            <input
                                type="number"
                                min="1"
                                placeholder="ENTER_VALUE"
                                value={pullupsInput}
                                onChange={e => setPullupsInput(e.target.value)}
                                className="w-full bg-white border border-border-grid rounded-soft-touch px-4 py-3 text-xs font-mono font-bold text-on-surface outline-none focus:ring-1 focus:ring-violet-500"
                            />
                        </div>
                        <div>
                            <span className="text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">RECENT_HISTORY (L7D)</span>
                            <MiniHistory sessions={recentPullups} renderDot={log => {
                                const hit = log.pullups!.done >= log.pullups!.goal;
                                return <div className={`w-5 h-5 rounded-soft-touch border border-white/20 shadow-sm ${hit ? 'bg-violet-500' : 'bg-rose-400'}`} title={`${log.id}: ${log.pullups!.done}/${log.pullups!.goal}`} />;
                            }} />
                        </div>
                    </div>
                </div>

                {/* Caminhada */}
                <div className="bg-sky-50/50 border border-sky-100 rounded-none p-6 flex flex-col gap-4 relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-2 opacity-10">
                        <svg className="w-12 h-12 text-sky-600" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2z"/></svg>
                    </div>
                    <div>
                        <span className="text-[9px] font-mono font-bold text-sky-600 uppercase tracking-[0.2em]">// WALK_UNIT</span>
                        <div className="flex items-baseline gap-2 mt-2">
                            <span className="text-4xl font-mono font-bold text-on-surface tracking-tighter">01h–02h</span>
                            <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">RANGE_TARGET</span>
                        </div>
                        <ProtocolPanel steps={getProtocol('walk', 60)} accentClass="text-sky-600" />
                        {todayLog?.walk && (() => {
                            const done = todayLog.walk!.done;
                            const pct = Math.min(100, Math.round(((done - 60) / 60) * 100));
                            const metMin = done >= 60;
                            const metIdeal = done >= 120;
                            return (
                                <div className="mt-4">
                                    <div className={`text-[10px] font-mono font-bold uppercase tracking-widest mb-2 ${metIdeal ? 'text-emerald-600' : metMin ? 'text-sky-600' : 'text-amber-600'}`}>
                                        LOGGED: {formatWalkDisplay(done)} {metIdeal ? '[IDEAL_REACHED]' : metMin ? '[MIN_MET]' : '[LOW_INTENSITY]'}
                                    </div>
                                    {metMin && !metIdeal && (
                                        <div className="w-full bg-sky-200/30 rounded-none h-1 border border-sky-200">
                                            <div className="bg-sky-500 h-full transition-all" style={{ width: `${pct}%` }} />
                                        </div>
                                    )}
                                </div>
                            );
                        })()}
                    </div>
                    <div className="mt-auto space-y-4">
                        <div className="flex gap-2">
                            <input
                                type="number"
                                min="1"
                                placeholder="ENTER_MINUTES"
                                value={walkInput}
                                onChange={e => setWalkInput(e.target.value)}
                                className="w-full bg-white border border-border-grid rounded-soft-touch px-4 py-3 text-xs font-mono font-bold text-on-surface outline-none focus:ring-1 focus:ring-sky-500"
                            />
                        </div>
                        <div>
                            <span className="text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">RECENT_HISTORY (L7D)</span>
                            <MiniHistory sessions={recentWalks} renderDot={log => {
                                const done = log.walk!.done;
                                const color = done >= 120 ? 'bg-emerald-500' : done >= 60 ? 'bg-sky-500' : 'bg-rose-400';
                                return <div className={`w-5 h-5 rounded-soft-touch border border-white/20 shadow-sm ${color}`} title={`${log.id}: ${formatWalkDisplay(done)}`} />;
                            }} />
                        </div>
                    </div>
                </div>
            </div>

            <div className="flex justify-end mt-8">
                <button
                    onClick={handleSave}
                    disabled={saving || (!pushupsInput && !pullupsInput && !walkInput)}
                    className="w-full md:w-auto bg-on-surface text-surface px-10 py-4 rounded-soft-touch text-[11px] font-mono font-bold uppercase tracking-[0.2em] hover:bg-primary-tactile transition-all shadow-none disabled:opacity-20 disabled:cursor-not-allowed"
                >
                    {saving ? 'PROCESSING_LOG...' : 'COMMIT_EXERCISE_DATA'}
                </button>
            </div>
        </div>
    );
};

const ExamsAndConsultationsManager = ({ 
    exams, 
    onAddExam, 
    onDeleteExam, 
    onUpdateExam 
}: { 
    exams: HealthExam[], 
    onAddExam: (exam: Omit<HealthExam, 'id' | 'data_criacao' | 'pool_dados'>, files: File[]) => void,
    onDeleteExam: (id: string) => void,
    onUpdateExam: (id: string, updates: Partial<HealthExam>) => void
}) => {
    const [isAdding, setIsAdding] = useState(false);
    const [newExam, setNewExam] = useState<Partial<HealthExam>>({
        tipo: 'consulta',
        data: formatDateLocalISO(new Date())
    });
    const [files, setFiles] = useState<File[]>([]);
    const [pendingDeleteExamId, setPendingDeleteExamId] = useState<string | null>(null);
    
    // Convert FileList to array correctly when handling input
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            setFiles(Array.from(e.target.files));
        }
    };

    const handleSubmit = () => {
        if (!newExam.titulo || !newExam.data || !newExam.tipo) return;
        
        onAddExam({
            titulo: newExam.titulo,
            data: newExam.data,
            tipo: newExam.tipo,
            ...(newExam.doutor_local && { doutor_local: newExam.doutor_local }),
            ...(newExam.resultados && { resultados: newExam.resultados })
        }, files);

        setIsAdding(false);
        setNewExam({ tipo: 'consulta', data: formatDateLocalISO(new Date()) });
        setFiles([]);
    };

    return (
        <div className="space-y-8">
            {!isAdding ? (
                <button 
                    onClick={() => setIsAdding(true)}
                    className="w-full py-6 border border-border-grid border-dashed bg-surface rounded-none text-slate-400 font-mono font-bold text-[10px] uppercase tracking-[0.3em] hover:border-primary-tactile hover:text-primary-tactile transition-all flex items-center justify-center gap-4 group"
                >
                    <div className="w-8 h-8 rounded-soft-touch border border-border-grid flex items-center justify-center group-hover:bg-primary-tactile group-hover:text-white transition-all">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                    </div>
                    REGISTER_NEW_MEDICAL_EVENT
                </button>
            ) : (
                <div className="bg-surface p-8 rounded-none border border-primary-tactile space-y-8 animate-in fade-in slide-in-from-top-4 duration-500 relative">
                    <div className="absolute top-0 right-0 p-4">
                         <div className="text-[8px] font-mono font-bold text-primary-tactile opacity-30 uppercase tracking-[0.2em]">FORM_ID: MED_RECORD_V1</div>
                    </div>
                    <div className="flex justify-between items-start">
                        <div>
                            <span className="text-[10px] font-mono font-bold text-primary-tactile uppercase tracking-[0.3em] mb-1 flex items-center gap-2">
                                <span className="w-2 h-2 bg-primary-tactile"></span>
                                NEW_RECORD_ENTRY
                            </span>
                            <p className="text-xs font-serif italic text-slate-500">Preencha os detalhes técnicos do evento médico para indexação.</p>
                        </div>
                        <button onClick={() => setIsAdding(false)} className="w-8 h-8 rounded-soft-touch border border-border-grid flex items-center justify-center text-slate-300 hover:text-accent-tactile transition-all">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        <div>
                            <label className="block text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest mb-3">EVENT_TYPE</label>
                            <div className="flex bg-slate-50 p-1 rounded-soft-touch border border-border-grid">
                                <button 
                                    onClick={() => setNewExam({ ...newExam, tipo: 'consulta' })}
                                    className={`flex-1 py-2 text-[10px] font-mono font-bold uppercase tracking-widest rounded-soft-touch transition-all ${newExam.tipo === 'consulta' ? 'bg-on-surface text-surface' : 'text-slate-400 hover:bg-white'}`}
                                >
                                    CONSULTATION
                                </button>
                                <button 
                                    onClick={() => setNewExam({ ...newExam, tipo: 'exame' })}
                                    className={`flex-1 py-2 text-[10px] font-mono font-bold uppercase tracking-widest rounded-soft-touch transition-all ${newExam.tipo === 'exame' ? 'bg-primary-tactile text-white' : 'text-slate-400 hover:bg-white'}`}
                                >
                                    EXAM_PROCEDURE
                                </button>
                            </div>
                        </div>

                        <div>
                            <label className="block text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest mb-3">EVENT_DATE</label>
                            <input 
                                type="date"
                                className="w-full bg-white border border-border-grid rounded-soft-touch px-4 py-3 text-xs font-mono font-bold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                value={newExam.data}
                                onChange={e => setNewExam({ ...newExam, data: e.target.value })}
                            />
                        </div>

                        <div className="md:col-span-2">
                            <label className="block text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest mb-3">TITLE / SPECIALIZATION</label>
                            <input 
                                type="text"
                                placeholder="E.G. CARDIOLOGY, COMPLETE_BLOOD_COUNT..."
                                className="w-full bg-white border border-border-grid rounded-soft-touch px-4 py-3 text-xs font-mono font-bold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                value={newExam.titulo || ''}
                                onChange={e => setNewExam({ ...newExam, titulo: e.target.value })}
                            />
                        </div>

                        <div className="md:col-span-2">
                            <label className="block text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest mb-3">FACILITY / PROFESSIONAL_ID</label>
                            <input 
                                type="text"
                                placeholder="E.G. DR. SMITH, DIAGNOSTIC_CENTER..."
                                className="w-full bg-white border border-border-grid rounded-soft-touch px-4 py-3 text-xs font-mono font-bold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                value={newExam.doutor_local || ''}
                                onChange={e => setNewExam({ ...newExam, doutor_local: e.target.value })}
                            />
                        </div>

                        <div className="md:col-span-2">
                            <label className="block text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest mb-3">TECHNICAL_ATTACHMENTS (PDF/IMG)</label>
                            <div className="border border-border-grid border-dashed rounded-none p-6 bg-slate-50 hover:bg-white transition-colors text-center cursor-pointer relative group">
                                <input 
                                    type="file" 
                                    multiple
                                    className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                    onChange={handleFileChange}
                                />
                                <div className="flex flex-col items-center gap-2">
                                    <svg className="w-6 h-6 text-slate-300 group-hover:text-primary-tactile transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                                    <div className="text-[10px] font-mono font-bold uppercase tracking-widest text-slate-400">
                                        {files.length > 0 ? (
                                            <span className="text-primary-tactile">{files.length} FILE(S) SELECTED_FOR_UPLOAD</span>
                                        ) : (
                                            <span>DRAG_DROP_OR_CLICK_TO_ATTACH</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="flex justify-start md:justify-end pt-4 border-t border-border-grid">
                        <button 
                            disabled={!newExam.titulo || !newExam.data}
                            onClick={handleSubmit}
                            className="w-full md:w-auto bg-primary-tactile text-white px-10 py-4 rounded-soft-touch text-[11px] font-mono font-bold uppercase tracking-[0.2em] hover:bg-on-surface transition-all disabled:opacity-20 disabled:cursor-not-allowed"
                        >
                            COMMIT_MEDICAL_RECORD
                        </button>
                    </div>
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {exams.sort((a, b) => new Date(b.data).getTime() - new Date(a.data).getTime()).map(exam => (
                    <div key={exam.id} className="bg-surface border border-border-grid rounded-none p-6 hover:border-primary-tactile transition-all group relative overflow-hidden">
                        <div className="absolute top-0 right-0 p-3 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button 
                                onClick={() => {
                                    if (pendingDeleteExamId !== exam.id) {
                                        setPendingDeleteExamId(exam.id);
                                        window.setTimeout(() => setPendingDeleteExamId((current) => (current === exam.id ? null : current)), 3500);
                                        return;
                                    }
                                    setPendingDeleteExamId(null);
                                    onDeleteExam(exam.id);
                                }}
                                className={`w-8 h-8 rounded-soft-touch flex items-center justify-center transition-all ${pendingDeleteExamId === exam.id ? 'bg-accent-tactile text-white scale-110' : 'bg-slate-100 text-slate-400 hover:bg-accent-tactile hover:text-white'}`}
                                title={pendingDeleteExamId === exam.id ? "CONFIRM_DELETE" : "DELETE_RECORD"}
                            >
                                {pendingDeleteExamId === exam.id ? (
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                ) : (
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                )}
                            </button>
                        </div>

                        <div className="flex flex-col gap-4">
                            <div className="flex items-center gap-3">
                                <span className={`text-[8px] font-mono font-bold uppercase px-2 py-0.5 rounded-none border ${exam.tipo === 'consulta' ? 'bg-slate-50 text-slate-600 border-slate-200' : 'bg-primary-tactile/10 text-primary-tactile border-primary-tactile/20'}`}>
                                    {exam.tipo === 'consulta' ? 'CONSULTATION' : 'EXAM_PROCEDURE'}
                                </span>
                                <span className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest">{formatDate(exam.data)}</span>
                            </div>
                            
                            <div>
                                <h4 className="text-lg font-serif italic text-on-surface leading-tight mb-1">{exam.titulo}</h4>
                                {exam.doutor_local && (
                                    <p className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /></svg>
                                        LOC: {exam.doutor_local}
                                    </p>
                                )}
                            </div>

                            {exam.pool_dados && exam.pool_dados.length > 0 && (
                                <div className="flex flex-wrap gap-2 pt-4 border-t border-border-grid border-dashed">
                                    {exam.pool_dados.map(file => (
                                        <a 
                                            key={file.id}
                                            href={file.valor}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 rounded-soft-touch border border-border-grid text-[9px] font-mono font-bold text-slate-600 uppercase tracking-widest hover:bg-on-surface hover:text-white transition-all"
                                        >
                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
                                            ATTACHMENT_ID_{file.id.slice(-4).toUpperCase()}
                                        </a>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                ))}
                
                {exams.length === 0 && !isAdding && (
                    <div className="md:col-span-2 text-center py-16 border border-border-grid border-dashed rounded-none">
                        <span className="text-[10px] font-mono font-bold text-slate-300 uppercase tracking-[0.3em]">NO_MEDICAL_RECORDS_DETECTED</span>
                    </div>
                )}
            </div>
        </div>
    );
};

const HealthView: React.FC<HealthViewProps> = ({
    weights,
    dailyHabits,
    settings,
    onUpdateSettings,
    onAddWeight,
    onDeleteWeight,
    onUpdateHabits,
    exerciseLogs,
    exerciseSettings,
    onSaveExerciseLog,
    exams,
    onAddExam,
    onDeleteExam,
    onUpdateExam,
    isDark = false
}) => {
    const todayStr = formatDateLocalISO(new Date());
    const [selectedDate, setSelectedDate] = useState<string>(todayStr);
    const [newWeight, setNewWeight] = useState<string>('');
    const [isWeightModalOpen, setIsWeightModalOpen] = useState(false);
    const [targetInput, setTargetInput] = useState<string>(settings.targetWeight?.toString() || '');
    const [isEditingTarget, setIsEditingTarget] = useState(false);
    const [pendingDeleteWeightId, setPendingDeleteWeightId] = useState<string | null>(null);

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

    const hasWeightData = sortedWeights.length > 0;
    const hasWeightTrendData = sortedWeights.length > 1;
    const currentWeight = sortedWeights[0]?.weight || 0;
    const initialWeight = sortedWeights[sortedWeights.length - 1]?.weight || 0;
    const weightDelta = initialWeight > 0 ? initialWeight - currentWeight : 0; // + perda | - ganho
    const weightDeltaAbs = Math.abs(weightDelta);
    const isWeightLoss = weightDelta > 0.05;
    const isWeightGain = weightDelta < -0.05;
    const weightDeltaLabel = isWeightLoss ? 'Eliminado' : isWeightGain ? 'Ganho' : 'Variação';
    const weightDeltaPrefix = isWeightGain ? '+' : isWeightLoss ? '-' : '';

    // Projection Logic
    const projection = useMemo(() => {
        if (sortedWeights.length < 2) return null;

        const newest = sortedWeights[0];
        const oldest = sortedWeights[sortedWeights.length - 1];

        const diffWeight = oldest.weight - newest.weight;
        const diffDays = (new Date(newest.date).getTime() - new Date(oldest.date).getTime()) / (1000 * 60 * 60 * 24);

        if (diffDays <= 0) return null;

        const trendPerDay = diffWeight / diffDays;
        const trendPerWeek = trendPerDay * 7;

        if (!settings.targetWeight) {
            return {
                trendPerWeek,
                goalDate: trendPerDay < 0 ? 'Peso em alta' : 'Defina uma meta'
            };
        }

        if (newest.weight <= settings.targetWeight) return { trendPerWeek, goalDate: 'Meta atingida!' };

        if (trendPerDay <= 0) return { trendPerWeek, goalDate: 'Sem previsão (peso em alta)' };

        const remainingToGoal = newest.weight - settings.targetWeight;
        const daysUntilGoal = remainingToGoal / trendPerDay;

        const goalDate = new Date();
        goalDate.setDate(goalDate.getDate() + daysUntilGoal);

        return {
            trendPerWeek,
            goalDate: goalDate.toLocaleDateString('pt-BR')
        };
    }, [sortedWeights, settings.targetWeight]);

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
        <div className={`health-view space-y-12 pb-32 bg-surface min-h-screen ${isDark ? 'health-view-dark' : ''}`}>
            
            {/* Header Metrics Industrial Grid */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-0 border-b border-border-grid">
                
                {/* Peso Atual */}
                <div className="bg-surface p-8 border-r border-border-grid flex flex-col justify-center relative group overflow-hidden">
                    <div className="absolute top-0 right-0 p-2 opacity-5">
                         <svg className="w-16 h-16 text-primary-tactile" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2z"/></svg>
                    </div>
                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.3em] mb-2">// CURRENT_BODY_MASS</span>
                    <div className="flex items-center justify-between relative z-10">
                        <div className="flex items-baseline gap-2">
                            <span className="text-4xl font-mono font-bold text-on-surface tracking-tighter">
                                {hasWeightData ? currentWeight.toFixed(1) : '--.-'}
                            </span>
                            <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">KG</span>
                        </div>
                        <button 
                            onClick={() => setIsWeightModalOpen(true)}
                            className="w-10 h-10 rounded-soft-touch border border-border-grid flex items-center justify-center bg-slate-50 text-slate-400 hover:bg-primary-tactile hover:text-white transition-all"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                        </button>
                    </div>
                </div>

                {/* Variação */}
                <div className="bg-surface p-8 border-r border-border-grid flex flex-col justify-center relative overflow-hidden">
                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.3em] mb-2">// MASS_DELTA</span>
                    <div className="flex items-baseline gap-2">
                        <span className={`text-4xl font-mono font-bold tracking-tighter ${isWeightLoss ? 'text-emerald-600' : isWeightGain ? 'text-rose-600' : 'text-on-surface'}`}>
                            {hasWeightTrendData ? `${weightDeltaPrefix}${weightDeltaAbs.toFixed(1)}` : '0.0'}
                        </span>
                        <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">{weightDeltaLabel.toUpperCase()}</span>
                    </div>
                </div>

                {/* Meta */}
                <div className="bg-surface p-8 border-r border-border-grid flex flex-col justify-center relative group overflow-hidden">
                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.3em] mb-2">// TARGET_MASS</span>
                    <div className="flex items-center justify-between">
                        <div className="flex items-baseline gap-2">
                            {isEditingTarget ? (
                                <input
                                    type="number"
                                    autoFocus
                                    className="w-24 bg-slate-50 border border-primary-tactile rounded-none px-2 py-1 text-2xl font-mono font-bold text-on-surface outline-none"
                                    value={targetInput}
                                    onChange={e => setTargetInput(e.target.value)}
                                    onBlur={() => {
                                        setIsEditingTarget(false);
                                        onUpdateSettings({ ...settings, targetWeight: parseFloat(targetInput) });
                                    }}
                                    onKeyDown={e => {
                                        if (e.key === 'Enter') {
                                            setIsEditingTarget(false);
                                            onUpdateSettings({ ...settings, targetWeight: parseFloat(targetInput) });
                                        }
                                    }}
                                />
                            ) : (
                                <>
                                    <span className="text-4xl font-mono font-bold text-on-surface tracking-tighter">
                                        {settings.targetWeight ? settings.targetWeight.toFixed(1) : '---'}
                                    </span>
                                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">KG</span>
                                </>
                            )}
                        </div>
                        <button 
                            onClick={() => setIsEditingTarget(true)}
                            className="w-8 h-8 rounded-soft-touch border border-border-grid flex items-center justify-center text-slate-300 hover:text-on-surface transition-all"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                        </button>
                    </div>
                </div>

                {/* Previsão */}
                <div className="bg-surface p-8 flex flex-col justify-center relative overflow-hidden bg-[url('https://www.transparenttextures.com/patterns/graphy.png')]">
                    <span className="text-[10px] font-mono font-bold text-primary-tactile uppercase tracking-[0.3em] mb-2">// ETA_ESTIMATION</span>
                    <div className="flex flex-col">
                        <span className="text-xl font-serif italic text-on-surface tracking-tight">
                            {projection?.goalDate || '---'}
                        </span>
                        {projection?.trendPerWeek !== undefined && (
                            <span className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest mt-1">
                                TREND: {projection.trendPerWeek.toFixed(2)} KG/WEEK
                            </span>
                        )}
                    </div>
                </div>
            </div>

            <div className="px-6 md:px-10 space-y-12">
                
                {/* Consistency Heatmap Area */}
                <HabitHeatmap habits={dailyHabits} selectedDate={selectedDate} onSelectDate={setSelectedDate} />

                {/* Main Content Stacked Layout */}
                <div className="flex flex-col gap-12">
                    
                    {/* Section: Protocols & Training */}
                    <div className="space-y-10">
                        <HealthSection title={`Daily_Protocols • ${selectedDate === todayStr ? 'TODAY' : selectedDate}`} iconColor="bg-accent-tactile">
                             <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-6">
                                {[
                                    { key: 'noSugar', label: 'ZERO_SUGAR', icon: '🧁' },
                                    { key: 'noAlcohol', label: 'ZERO_ALCOHOL', icon: '🍷' },
                                    { key: 'noSnacks', label: 'ZERO_SNACKS', icon: '🍟' },
                                    { key: 'eatUntil18', label: 'FASTING_POST_18H', icon: '⏰' },
                                    { key: 'eatSlowly', label: 'MINDFUL_EATING', icon: '🧘' }
                                ].map((habit) => (
                                    <button
                                        key={habit.key}
                                        onClick={() => handleHabitToggle(habit.key as keyof DailyHabits)}
                                        className={`p-6 rounded-none border-2 transition-all flex flex-col items-center gap-3 group relative overflow-hidden ${currentHabits[habit.key as keyof DailyHabits] ? 'bg-accent-tactile border-accent-tactile text-white' : 'bg-surface border-border-grid text-on-surface hover:border-accent-tactile'}`}
                                    >
                                        <div className="absolute top-0 left-0 w-full h-0.5 bg-white/20"></div>
                                        <span className="text-2xl group-hover:scale-125 transition-transform">{habit.icon}</span>
                                        <span className="text-[10px] font-mono font-bold uppercase tracking-[0.2em]">{habit.label}</span>
                                        <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center mt-2 ${currentHabits[habit.key as keyof DailyHabits] ? 'bg-white border-white' : 'border-slate-200'}`}>
                                            {currentHabits[habit.key as keyof DailyHabits] && <svg className="w-3 h-3 text-accent-tactile" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" /></svg>}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </HealthSection>

                        <HealthSection title="Training_Grounds" iconColor="bg-primary-tactile">
                            <ExerciseGoalsSection 
                                exerciseLogs={exerciseLogs} 
                                exerciseSettings={exerciseSettings} 
                                onSaveExerciseLog={onSaveExerciseLog}
                                selectedDate={selectedDate}
                            />
                        </HealthSection>
                    </div>

                    {/* Section: Telemetry & Records */}
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-10">
                        
                        {/* Gráfico de Peso Technical */}
                        <div className="bg-surface p-8 border border-border-grid rounded-none relative overflow-hidden h-full flex flex-col">
                            <div className="flex justify-between items-center mb-8">
                                <div>
                                    <h4 className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.3em]">// MASS_VARIATION_CHART</h4>
                                    <p className="text-xs font-serif italic text-slate-500">Telemetry_Data_L30D</p>
                                </div>
                            </div>
                            
                            <div className="h-[240px] w-full bg-slate-50 border border-border-grid border-dashed relative overflow-hidden mb-8">
                                <div className="absolute inset-0 opacity-10 pointer-events-none" style={{ backgroundImage: 'radial-gradient(#000 1px, transparent 1px)', backgroundSize: '15px 15px' }}></div>
                                
                                {weights.length > 1 ? (
                                    <svg viewBox="0 0 400 150" className="w-full h-full drop-shadow-sm overflow-visible">
                                        <path
                                            d={generateChartPath()}
                                            fill="none"
                                            stroke="var(--primary-tactile)"
                                            strokeWidth="3"
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            className="animate-chart-trace"
                                        />
                                        {[...weights].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()).map((v, i, arr) => {
                                            const w = 400; const h = 150; const padding = 20;
                                            const chartWeights = arr;
                                            const minW = Math.min(...chartWeights.map(v => v.weight), settings.targetWeight || Infinity) - 2;
                                            const maxW = Math.max(...chartWeights.map(v => v.weight), settings.targetWeight || -Infinity) + 2;
                                            const rangeW = maxW - minW;
                                            const x = padding + (i / (chartWeights.length - 1)) * (w - 2 * padding);
                                            const y = h - padding - ((v.weight - minW) / rangeW) * (h - 2 * padding);
                                            return (
                                                <circle key={i} cx={x} cy={y} r="4" fill="white" stroke="var(--primary-tactile)" strokeWidth="2" />
                                            );
                                        })}
                                    </svg>
                                ) : (
                                    <div className="flex items-center justify-center h-full text-[10px] font-mono font-bold text-slate-300 uppercase tracking-widest">
                                        INSUFFICIENT_TELEMETRY_DATA
                                    </div>
                                )}
                            </div>

                            {/* Weight History List (Simplified) */}
                            <div className="mt-auto space-y-2 max-h-[300px] overflow-y-auto pr-2">
                                {sortedWeights.slice(0, 10).map((w) => (
                                    <div key={w.id} className="flex items-center justify-between p-3 bg-slate-50 border border-border-grid group">
                                        <div className="flex flex-col">
                                            <span className="text-[10px] font-mono font-bold text-slate-400 uppercase">{formatDate(w.date)}</span>
                                            <span className="text-sm font-mono font-bold text-on-surface">{w.weight.toFixed(1)} KG</span>
                                        </div>
                                        <button
                                            onClick={() => {
                                                if (pendingDeleteWeightId !== w.id) {
                                                    setPendingDeleteWeightId(w.id);
                                                    window.setTimeout(() => setPendingDeleteWeightId((current) => (current === w.id ? null : current)), 3500);
                                                    return;
                                                }
                                                onDeleteWeight(w.id);
                                            }}
                                            className={`p-2 rounded-soft-touch transition-all ${pendingDeleteWeightId === w.id ? 'bg-accent-tactile text-white' : 'opacity-0 group-hover:opacity-100 text-slate-300 hover:text-accent-tactile'}`}
                                        >
                                            {pendingDeleteWeightId === w.id ? 'CONFIRM' : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <HealthSection title="Medical_Archive" iconColor="bg-slate-400">
                            <ExamsAndConsultationsManager 
                                exams={exams} 
                                onAddExam={onAddExam} 
                                onDeleteExam={onDeleteExam}
                                onUpdateExam={onUpdateExam}
                            />
                        </HealthSection>
                    </div>
                </div>
            </div>

            {/* Weight Update Modal */}
            {isWeightModalOpen && (
                <div className="fixed inset-0 bg-on-surface/80 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
                    <div className="bg-surface rounded-none border-2 border-primary-tactile shadow-none w-full max-w-md p-8 animate-in zoom-in-95 duration-200">
                        <div className="flex justify-between items-start mb-8">
                            <div>
                                <span className="text-[10px] font-mono font-bold text-primary-tactile uppercase tracking-[0.3em] mb-1 block">// TELEMETRY_INPUT</span>
                                <h3 className="text-2xl font-serif italic text-on-surface">Log_Body_Mass</h3>
                            </div>
                            <button onClick={() => setIsWeightModalOpen(false)} className="w-8 h-8 rounded-soft-touch border border-border-grid flex items-center justify-center text-slate-300 hover:text-on-surface transition-all">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                        
                        <div className="space-y-6">
                            <div>
                                <label className="block text-[8px] font-mono font-bold text-slate-400 uppercase tracking-widest mb-3">CURRENT_READING (KG)</label>
                                <input
                                    type="number"
                                    step="0.1"
                                    autoFocus
                                    placeholder="00.0"
                                    className="w-full bg-slate-50 border border-border-grid rounded-soft-touch px-6 py-4 text-2xl font-mono font-bold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                    value={newWeight}
                                    onChange={e => setNewWeight(e.target.value)}
                                />
                            </div>
                            
                            <div className="grid grid-cols-2 gap-4">
                                <button
                                    onClick={() => setIsWeightModalOpen(false)}
                                    className="py-4 border border-border-grid text-[10px] font-mono font-bold uppercase tracking-widest hover:bg-slate-50 transition-all rounded-soft-touch"
                                >
                                    ABORT_ACTION
                                </button>
                                <button
                                    onClick={() => {
                                        if (newWeight) {
                                            onAddWeight(parseFloat(newWeight), formatDateLocalISO(new Date()));
                                            setNewWeight('');
                                            setIsWeightModalOpen(false);
                                        }
                                    }}
                                    className="py-4 bg-primary-tactile text-white text-[10px] font-mono font-bold uppercase tracking-widest hover:bg-on-surface transition-all rounded-soft-touch"
                                >
                                    COMMIT_DATA
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default HealthView;
