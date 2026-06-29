import React, { useEffect, useState, useRef } from 'react';
import { doc, getDoc, setDoc } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from '../../firebase';
import { HealthWeight, DailyHabits, HealthSettings, ExerciseLog } from '../../types';

type HealthStatus = 'critical' | 'attention' | 'stable' | 'strong';

interface HealthAnalysis {
    status: HealthStatus;
    score?: number;
    title: string;
    summary: string;
    mainRisk: string;
    positivePoint: string;
    actionProposal: string;
    isStructured?: boolean;
}

interface HealthSummaryCardProps {
    weights: HealthWeight[];
    dailyHabits: DailyHabits[];
    exerciseLogs: ExerciseLog[];
    settings: HealthSettings;
    onOpenHealthCopilot?: () => void;
}

const CACHE_DOC = doc(db, 'health_summary', 'config');
const CACHE_SCHEMA_VERSION = 'health-summary-v1';

const STATUS_STYLES: Record<HealthStatus, {
    label: string;
    container: string;
    eyebrow: string;
    title: string;
    text: string;
    muted: string;
    badge: string;
    divider: string;
}> = {
    critical: {
        label: 'Crítico',
        container: 'bg-rose-50 border-rose-300 shadow-[inset_0_4px_12px_rgba(190,18,60,0.10)]',
        eyebrow: 'text-rose-700/70',
        title: 'text-rose-950',
        text: 'text-rose-950/85',
        muted: 'text-rose-800/65',
        badge: 'bg-rose-600 text-white',
        divider: 'border-rose-200',
    },
    attention: {
        label: 'Atenção',
        container: 'bg-amber-50 border-amber-300 shadow-[inset_0_4px_12px_rgba(180,83,9,0.10)]',
        eyebrow: 'text-amber-700/75',
        title: 'text-amber-950',
        text: 'text-amber-950/85',
        muted: 'text-amber-800/65',
        badge: 'bg-amber-500 text-amber-950',
        divider: 'border-amber-200',
    },
    stable: {
        label: 'Estável',
        container: 'bg-sky-50 border-sky-300 shadow-[inset_0_4px_12px_rgba(2,132,199,0.10)]',
        eyebrow: 'text-sky-700/70',
        title: 'text-sky-950',
        text: 'text-sky-950/85',
        muted: 'text-sky-800/65',
        badge: 'bg-sky-600 text-white',
        divider: 'border-sky-200',
    },
    strong: {
        label: 'Forte',
        container: 'bg-emerald-50 border-emerald-300 shadow-[inset_0_4px_12px_rgba(5,150,105,0.10)]',
        eyebrow: 'text-emerald-700/70',
        title: 'text-emerald-950',
        text: 'text-emerald-950/85',
        muted: 'text-emerald-800/65',
        badge: 'bg-emerald-600 text-white',
        divider: 'border-emerald-200',
    },
};

const FALLBACK_ANALYSIS: HealthAnalysis = {
    status: 'attention',
    title: 'Diagnóstico de saúde em preparação',
    summary: 'Ainda não há uma análise consolidada para este recorte de saúde.',
    mainRisk: 'Dados insuficientes para apontar o risco principal com segurança.',
    positivePoint: 'Assim que houver dados suficientes, o Hermes destacará o ponto mais saudável do período.',
    actionProposal: 'Registre hábitos, peso e atividades diárias para permitir uma análise mais precisa.',
};

const HABIT_KEYS = ['noSugar', 'noAlcohol', 'noSnacks', 'workout', 'eatUntil18', 'eatSlowly'] as const;

function computeHabitStreak(dailyHabits: DailyHabits[]): number {
    let streak = 0;
    const sorted = [...dailyHabits].sort((a, b) => b.id.localeCompare(a.id));
    const checkDate = new Date();
    for (const h of sorted) {
        const expected = checkDate.toISOString().slice(0, 10);
        if (h.id === expected) {
            const done = HABIT_KEYS.filter(k => h[k]).length;
            if (done >= 4) { streak++; checkDate.setDate(checkDate.getDate() - 1); }
            else break;
        } else if (h.id < expected) break;
    }
    return streak;
}

function getHabitAdherence(dailyHabits: DailyHabits[], days: number): Record<string, number> {
    const today = new Date();
    const cutoff = new Date(today);
    cutoff.setDate(today.getDate() - days + 1);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    const todayStr = today.toISOString().slice(0, 10);
    const window = dailyHabits.filter(h => h.id >= cutoffStr && h.id <= todayStr);
    if (window.length === 0) return {};
    const result: Record<string, number> = {};
    for (const key of HABIT_KEYS) {
        result[key] = Math.round(window.filter(h => h[key]).length / window.length * 100);
    }
    return result;
}

function buildSnapshot(props: HealthSummaryCardProps) {
    const { weights, dailyHabits, exerciseLogs, settings } = props;
    const today = new Date();
    const todayStr = today.toISOString().slice(0, 10);

    // --- Biometria ---
    const sortedW = [...weights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    const currentWeight = sortedW[0]?.weight ?? null;
    const targetWeight = settings.targetWeight || null;
    const thirtyAgo = new Date(today);
    thirtyAgo.setDate(today.getDate() - 30);
    const recentW = sortedW.filter(w => new Date(w.date) >= thirtyAgo);
    const oldestRecent = recentW[recentW.length - 1]?.weight ?? null;
    const trend30d = currentWeight !== null && oldestRecent !== null ? +(currentWeight - oldestRecent).toFixed(1) : null;

    // --- Hábitos ---
    const sevenAgo = new Date(today);
    sevenAgo.setDate(today.getDate() - 6);
    const sevenStr = sevenAgo.toISOString().slice(0, 10);
    const recentLogs = exerciseLogs.filter(l => l.id >= sevenStr && l.id <= todayStr);

    // --- Atividade 7d ---
    const stepsArr = recentLogs.filter(l => l.walk?.steps).map(l => l.walk!.steps!);
    const avgSteps = stepsArr.length > 0 ? Math.round(stepsArr.reduce((a, b) => a + b, 0) / stepsArr.length) : null;
    const distArr = recentLogs.filter(l => l.walk?.distance).map(l => l.walk!.distance!);
    const avgDistKm = distArr.length > 0 ? +(distArr.reduce((a, b) => a + b, 0) / distArr.length).toFixed(1) : null;
    const calArr = recentLogs.filter(l => l.calories).map(l => l.calories!);
    const avgCal = calArr.length > 0 ? Math.round(calArr.reduce((a, b) => a + b, 0) / calArr.length) : null;
    const minGoal = settings.walkingMinimumMinutes ?? 45;
    const idealGoal = settings.walkingIdealMinutes ?? 100;
    const daysMetMin = recentLogs.filter(l => (l.walk?.done ?? 0) >= minGoal).length;
    const daysMetIdeal = recentLogs.filter(l => (l.walk?.done ?? 0) >= idealGoal).length;

    // --- Sono 7d ---
    const sleepLogs = recentLogs.filter(l => l.sleep?.totalMinutes);
    const avgSleepMin = sleepLogs.length > 0
        ? Math.round(sleepLogs.reduce((a, l) => a + l.sleep!.totalMinutes, 0) / sleepLogs.length) : null;
    const deepArr = sleepLogs.filter(l => l.sleep?.deepMinutes).map(l => l.sleep!.deepMinutes!);
    const avgDeepMin = deepArr.length > 0 ? Math.round(deepArr.reduce((a, b) => a + b, 0) / deepArr.length) : null;
    const daysBelow7h = sleepLogs.filter(l => l.sleep!.totalMinutes < 420).length;

    // --- Dor 7d ---
    const painLogs = recentLogs.filter(l => l.pain?.morning !== undefined || l.pain?.evening !== undefined);
    const mornings = painLogs.filter(l => l.pain?.morning !== undefined).map(l => l.pain!.morning!);
    const evenings = painLogs.filter(l => l.pain?.evening !== undefined).map(l => l.pain!.evening!);
    const avgMorning = mornings.length > 0 ? +(mornings.reduce((a, b) => a + b, 0) / mornings.length).toFixed(1) : null;
    const avgEvening = evenings.length > 0 ? +(evenings.reduce((a, b) => a + b, 0) / evenings.length).toFixed(1) : null;
    const crisisCount = recentLogs.filter(l => l.pain?.crisis).length;

    return {
        dataReferencia: todayStr,
        biometria: {
            pesoAtual: currentWeight,
            metaPeso: targetWeight,
            deltaMetaPeso: currentWeight !== null && targetWeight ? +(currentWeight - targetWeight).toFixed(1) : null,
            tendencia30d: trend30d,
            registros30d: recentW.length,
        },
        habitos: {
            streak: computeHabitStreak(dailyHabits),
            adesao7d: getHabitAdherence(dailyHabits, 7),
            adesao30d: getHabitAdherence(dailyHabits, 30),
            diasRegistrados7d: dailyHabits.filter(h => h.id >= sevenStr && h.id <= todayStr).length,
        },
        atividade7d: {
            mediaPassosDia: avgSteps,
            mediaDistanciaKm: avgDistKm,
            mediaCalorias: avgCal,
            diasMetaMinimaAtingida: daysMetMin,
            diasMetaIdealAtingida: daysMetIdeal,
            metaMinimaMin: minGoal,
            metaIdealMin: idealGoal,
        },
        sono7d: {
            mediaTotalMin: avgSleepMin,
            mediaProfundoMin: avgDeepMin,
            diasAbaixo7h: daysBelow7h,
            diasComDados: sleepLogs.length,
        },
        dor7d: {
            mediaManha: avgMorning,
            mediaNoite: avgEvening,
            crisesRecentes: crisisCount,
            diasComDados: painLogs.length,
        },
    };
}

function computeFingerprint(props: HealthSummaryCardProps): string {
    return JSON.stringify({ schemaVersion: CACHE_SCHEMA_VERSION, snapshot: buildSnapshot(props) });
}

function normalizeStatus(value: unknown): HealthStatus {
    if (value === 'critical' || value === 'attention' || value === 'stable' || value === 'strong') return value;
    return 'attention';
}

function normalizeAnalysis(value: unknown): HealthAnalysis {
    if (typeof value === 'string' && value.trim()) {
        return { ...FALLBACK_ANALYSIS, title: 'Diagnóstico de saúde', summary: value.trim(), mainRisk: '', positivePoint: '', actionProposal: '', isStructured: false };
    }
    if (!value || typeof value !== 'object') return FALLBACK_ANALYSIS;
    const raw = value as Partial<HealthAnalysis>;
    const score = typeof raw.score === 'number' && Number.isFinite(raw.score) ? Math.max(0, Math.min(100, Math.round(raw.score))) : undefined;
    const mainRisk = raw.mainRisk?.trim() || '';
    const positivePoint = raw.positivePoint?.trim() || '';
    const actionProposal = raw.actionProposal?.trim() || '';
    return {
        status: normalizeStatus(raw.status),
        score,
        title: raw.title?.trim() || FALLBACK_ANALYSIS.title,
        summary: raw.summary?.trim() || FALLBACK_ANALYSIS.summary,
        mainRisk,
        positivePoint,
        actionProposal,
        isStructured: Boolean(mainRisk && positivePoint && actionProposal),
    };
}

export function HealthSummaryCard(props: HealthSummaryCardProps) {
    const [analysis, setAnalysis] = useState<HealthAnalysis | null>(null);
    const [loading, setLoading] = useState(false);
    const lastFingerprintRef = useRef<string | null>(null);

    useEffect(() => {
        const fingerprint = computeFingerprint(props);
        if (lastFingerprintRef.current === fingerprint) return;
        lastFingerprintRef.current = fingerprint;

        async function refresh() {
            try {
                const snap = await getDoc(CACHE_DOC);
                if (snap.exists()) {
                    const cached = snap.data() as { analysis?: HealthAnalysis; summary?: string; fingerprint: string; schemaVersion?: string };
                    if (cached.fingerprint === fingerprint && cached.schemaVersion === CACHE_SCHEMA_VERSION) {
                        setAnalysis(normalizeAnalysis(cached.analysis ?? cached.summary));
                        return;
                    }
                }
                setLoading(true);
                const fn = httpsCallable<{ snapshot: object }, { analysis?: HealthAnalysis; summary?: string }>(functions, 'gerarResumoSaude', { timeout: 60000 });
                const result = await fn({ snapshot: buildSnapshot(props) });
                const newAnalysis = normalizeAnalysis(result.data.analysis ?? result.data.summary);
                await setDoc(CACHE_DOC, {
                    analysis: newAnalysis,
                    summary: newAnalysis.summary,
                    fingerprint,
                    schemaVersion: CACHE_SCHEMA_VERSION,
                    generatedAt: new Date().toISOString(),
                });
                setAnalysis(newAnalysis);
            } catch (err) {
                console.error('Erro ao gerar resumo de saúde:', err);
            } finally {
                setLoading(false);
            }
        }

        refresh();
    }, [computeFingerprint(props)]);

    const visibleAnalysis = analysis ?? FALLBACK_ANALYSIS;
    const styles = STATUS_STYLES[visibleAnalysis.status];
    const hasStructuredDetails = Boolean(
        visibleAnalysis.isStructured
        && visibleAnalysis.mainRisk
        && visibleAnalysis.positivePoint
        && visibleAnalysis.actionProposal
    );

    return (
        <div className={`p-4 rounded-lg border-4 flex flex-col gap-4 ${styles.container}`}>
            <div className="flex items-start justify-between gap-3 shrink-0">
                <div className="min-w-0">
                    <p className={`text-[10px] font-black uppercase tracking-[0.2em] font-sans ${styles.eyebrow}`}>
                        Saúde Geral
                    </p>
                    <h3 className={`mt-1 text-base font-black leading-tight ${styles.title}`}>
                        {visibleAnalysis.title}
                    </h3>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    {props.onOpenHealthCopilot && (
                        <button
                            type="button"
                            onClick={props.onOpenHealthCopilot}
                            className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 border text-[9px] font-black uppercase tracking-[0.14em] font-sans transition-all ${
                                visibleAnalysis.status === 'critical' ? 'border-rose-300 bg-white/60 text-rose-800 hover:bg-white'
                                : visibleAnalysis.status === 'attention' ? 'border-amber-300 bg-white/60 text-amber-800 hover:bg-white'
                                : visibleAnalysis.status === 'stable' ? 'border-sky-300 bg-white/60 text-sky-800 hover:bg-white'
                                : 'border-emerald-300 bg-white/60 text-emerald-800 hover:bg-white'
                            }`}
                            title="Conversar com o copiloto de saude"
                        >
                            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                            </svg>
                            Copiloto
                        </button>
                    )}
                    {typeof visibleAnalysis.score === 'number' && (
                        <span className={`text-[10px] font-bold uppercase tracking-wider font-sans ${styles.muted}`}>
                            {visibleAnalysis.score}/100
                        </span>
                    )}
                    <span className={`px-2 py-1 text-[9px] font-black uppercase tracking-[0.16em] font-sans ${styles.badge}`}>
                        {loading ? 'Analisando' : styles.label}
                    </span>
                </div>
            </div>

            {analysis ? (
                <>
                    <p className={`text-sm font-medium leading-relaxed ${styles.text}`}>
                        {visibleAnalysis.summary}
                    </p>

                    {hasStructuredDetails && (
                        <div className={`grid gap-3 sm:grid-cols-2 border-t pt-3 ${styles.divider}`}>
                            <div>
                                <p className={`text-[9px] font-black uppercase tracking-[0.18em] font-sans ${styles.eyebrow}`}>
                                    Ponto de atenção
                                </p>
                                <p className={`mt-1 text-xs font-bold leading-relaxed ${styles.text}`}>
                                    {visibleAnalysis.mainRisk}
                                </p>
                            </div>
                            <div>
                                <p className={`text-[9px] font-black uppercase tracking-[0.18em] font-sans ${styles.eyebrow}`}>
                                    Ponto positivo
                                </p>
                                <p className={`mt-1 text-xs font-bold leading-relaxed ${styles.text}`}>
                                    {visibleAnalysis.positivePoint}
                                </p>
                            </div>
                        </div>
                    )}

                    {hasStructuredDetails && (
                        <div className={`border-t pt-3 ${styles.divider}`}>
                            <p className={`text-[9px] font-black uppercase tracking-[0.18em] font-sans ${styles.eyebrow}`}>
                                Proposta para esta semana
                            </p>
                            <p className={`mt-1 text-sm font-black leading-relaxed ${styles.title}`}>
                                {visibleAnalysis.actionProposal}
                            </p>
                        </div>
                    )}
                </>
            ) : loading ? (
                <div className="space-y-3">
                    <div className="h-3 w-2/3 rounded-lg animate-pulse bg-black/10" />
                    <div className="h-16 rounded-lg animate-pulse bg-black/10" />
                </div>
            ) : (
                <p className={`text-sm font-bold italic ${styles.muted}`}>Aguardando análise...</p>
            )}
            {props.onOpenHealthCopilot && (
                <button
                    type="button"
                    onClick={props.onOpenHealthCopilot}
                    className={`sm:hidden flex items-center justify-center gap-2 border px-3 py-2 text-[10px] font-black uppercase tracking-[0.14em] font-sans transition-all ${
                        visibleAnalysis.status === 'critical' ? 'border-rose-300 bg-white/60 text-rose-800'
                        : visibleAnalysis.status === 'attention' ? 'border-amber-300 bg-white/60 text-amber-800'
                        : visibleAnalysis.status === 'stable' ? 'border-sky-300 bg-white/60 text-sky-800'
                        : 'border-emerald-300 bg-white/60 text-emerald-800'
                    }`}
                >
                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                    Conversar com copiloto de saude
                </button>
            )}
        </div>
    );
}
