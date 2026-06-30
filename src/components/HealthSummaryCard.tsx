import React, { useEffect, useRef, useState } from 'react';
import { doc, getDoc, setDoc } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from '../../firebase';
import { HealthWeight, HealthSettings, ExerciseLog } from '../../types';

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
    exerciseLogs: ExerciseLog[];
    settings: HealthSettings;
}

const CACHE_DOC = doc(db, 'health_summary', 'config');
const CACHE_SCHEMA_VERSION = 'health-summary-v3-telemetry-only';

const STATUS_STYLES: Record<HealthStatus, {
    label: string;
    container: string;
    eyebrow: string;
    muted: string;
    badge: string;
    accent: string;
}> = {
    critical: {
        label: 'Critico',
        container: 'border-rose-200',
        eyebrow: 'text-rose-700',
        muted: 'text-rose-700',
        badge: 'bg-rose-600 text-white',
        accent: 'bg-rose-600',
    },
    attention: {
        label: 'Atencao',
        container: 'border-amber-200',
        eyebrow: 'text-amber-700',
        muted: 'text-amber-700',
        badge: 'bg-amber-100 text-amber-800',
        accent: 'bg-amber-500',
    },
    stable: {
        label: 'Estavel',
        container: 'border-sky-200',
        eyebrow: 'text-sky-700',
        muted: 'text-sky-700',
        badge: 'bg-sky-100 text-sky-800',
        accent: 'bg-sky-600',
    },
    strong: {
        label: 'Forte',
        container: 'border-emerald-200',
        eyebrow: 'text-emerald-700',
        muted: 'text-emerald-700',
        badge: 'bg-emerald-100 text-emerald-800',
        accent: 'bg-emerald-600',
    },
};

const FALLBACK_ANALYSIS: HealthAnalysis = {
    status: 'attention',
    title: 'Diagnostico de saude em preparacao',
    summary: 'Ainda nao ha uma analise consolidada para este recorte de saude.',
    mainRisk: 'Dados insuficientes para apontar o risco principal com seguranca.',
    positivePoint: 'Assim que houver dados suficientes, o Hermes destacara o ponto mais saudavel do periodo.',
    actionProposal: 'Sincronize peso, caminhada, sono, calorias e dor para permitir uma analise mais precisa.',
};

function getLocalDateKey(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}


function buildSnapshot(props: HealthSummaryCardProps) {
    const { weights, exerciseLogs, settings } = props;
    const today = new Date();
    const todayStr = getLocalDateKey(today);

    const sortedW = [...weights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    const currentWeight = sortedW[0]?.weight ?? null;
    const targetWeight = settings.targetWeight || null;
    const thirtyAgo = new Date(today);
    thirtyAgo.setDate(today.getDate() - 30);
    const recentW = sortedW.filter(w => new Date(w.date) >= thirtyAgo);
    const oldestRecent = recentW[recentW.length - 1]?.weight ?? null;
    const trend30d = currentWeight !== null && oldestRecent !== null ? +(currentWeight - oldestRecent).toFixed(1) : null;

    const sevenAgo = new Date(today);
    sevenAgo.setDate(today.getDate() - 6);
    const sevenStr = getLocalDateKey(sevenAgo);
    const recentLogs = exerciseLogs.filter(l => l.id >= sevenStr && l.id <= todayStr);

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

    const sleepLogs = recentLogs.filter(l => l.sleep?.totalMinutes);
    const avgSleepMin = sleepLogs.length > 0
        ? Math.round(sleepLogs.reduce((a, l) => a + l.sleep!.totalMinutes, 0) / sleepLogs.length)
        : null;
    const deepArr = sleepLogs.filter(l => l.sleep?.deepMinutes).map(l => l.sleep!.deepMinutes!);
    const avgDeepMin = deepArr.length > 0 ? Math.round(deepArr.reduce((a, b) => a + b, 0) / deepArr.length) : null;
    const daysBelow7h = sleepLogs.filter(l => l.sleep!.totalMinutes < 420).length;

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
        return { ...FALLBACK_ANALYSIS, title: 'Diagnostico de saude', summary: value.trim(), mainRisk: '', positivePoint: '', actionProposal: '', isStructured: false };
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

function buildLocalAnalysis(snapshot: ReturnType<typeof buildSnapshot>): HealthAnalysis {
    const weightDelta = snapshot.biometria.tendencia30d;
    const avgSteps = snapshot.atividade7d.mediaPassosDia;
    const avgSleep = snapshot.sono7d.mediaTotalMin;
    const painCrisis = snapshot.dor7d.crisesRecentes;
    const idealDays = snapshot.atividade7d.diasMetaIdealAtingida;

    let status: HealthStatus = 'stable';
    let score = 72;

    if ((painCrisis ?? 0) > 0 || (avgSleep !== null && avgSleep < 360) || (weightDelta !== null && weightDelta > 1.5)) {
        status = 'attention';
        score = 58;
    }
    if ((painCrisis ?? 0) >= 2 || ((avgSleep !== null && avgSleep < 330) && (avgSteps !== null && avgSteps < 3500))) {
        status = 'critical';
        score = 38;
    }
    if ((avgSleep !== null && avgSleep >= 420) && (avgSteps !== null && avgSteps >= 7000) && idealDays >= 3 && (painCrisis ?? 0) === 0) {
        status = 'strong';
        score = 84;
    }

    const sleepText = avgSleep !== null ? `${(avgSleep / 60).toFixed(1)}h de sono medio` : 'sono ainda sem media';
    const stepsText = avgSteps !== null ? `${avgSteps.toLocaleString('pt-BR')} passos/dia` : 'passos ainda sem media';
    const weightText = weightDelta !== null ? `tendencia de ${weightDelta > 0 ? '+' : ''}${weightDelta.toFixed(1)} kg em 30 dias` : 'peso sem tendencia recente';

    return {
        status,
        score,
        title: 'Analise local de saude',
        summary: `Resumo calculado localmente: ${stepsText}, ${sleepText} e ${weightText}.`,
        mainRisk: painCrisis ? `${painCrisis} crise(s) de dor registradas nos ultimos 7 dias.` : 'Sem risco dominante claro nos dados disponiveis.',
        positivePoint: idealDays > 0 ? `${idealDays} dia(s) atingiram a meta ideal de caminhada.` : avgSleep !== null && avgSleep >= 420 ? 'Sono medio acima de 7h no periodo com dados.' : 'O painel ja possui dados suficientes para acompanhar tendencia.',
        actionProposal: 'Nesta semana, priorize sincronizar telemetria diariamente e manter a caminhada minima antes de aumentar intensidade.',
        isStructured: true,
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
            const snapshot = buildSnapshot(props);
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
                const result = await fn({ snapshot });
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
                console.warn('Resumo remoto de saude indisponivel; usando analise local.', err);
                setAnalysis(buildLocalAnalysis(snapshot));
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
        <div className={`relative overflow-hidden rounded-2xl border bg-white p-5 shadow-card ${styles.container}`}>
            <div className={`absolute left-0 top-0 h-full w-1 ${styles.accent}`} />
            <div className="flex flex-col gap-4 pl-2">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <p className={`text-[10px] font-semibold uppercase tracking-[0.05em] font-sans ${styles.eyebrow}`}>
                            Saude geral
                        </p>
                        <h3 className="mt-1 text-base font-bold leading-tight text-on-surface">
                            {visibleAnalysis.title}
                        </h3>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                        {typeof visibleAnalysis.score === 'number' && (
                            <span className={`text-[10px] font-semibold uppercase tracking-[0.05em] font-sans ${styles.muted}`}>
                                {visibleAnalysis.score}/100
                            </span>
                        )}
                        <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.05em] font-sans ${styles.badge}`}>
                            {loading ? 'Analisando' : styles.label}
                        </span>
                    </div>
                </div>

                {analysis ? (
                    <>
                        <p className="text-sm font-medium leading-relaxed text-on-surface-variant">
                            {visibleAnalysis.summary}
                        </p>

                        {hasStructuredDetails && (
                            <div className="grid gap-3 border-t border-border-subtle pt-3 sm:grid-cols-2">
                                <div>
                                    <p className={`text-[10px] font-semibold uppercase tracking-[0.05em] font-sans ${styles.eyebrow}`}>
                                        Ponto de atencao
                                    </p>
                                    <p className="mt-1 text-xs font-semibold leading-relaxed text-on-surface-variant">
                                        {visibleAnalysis.mainRisk}
                                    </p>
                                </div>
                                <div>
                                    <p className={`text-[10px] font-semibold uppercase tracking-[0.05em] font-sans ${styles.eyebrow}`}>
                                        Ponto positivo
                                    </p>
                                    <p className="mt-1 text-xs font-semibold leading-relaxed text-on-surface-variant">
                                        {visibleAnalysis.positivePoint}
                                    </p>
                                </div>
                            </div>
                        )}

                        {hasStructuredDetails && (
                            <div className="border-t border-border-subtle pt-3">
                                <p className={`text-[10px] font-semibold uppercase tracking-[0.05em] font-sans ${styles.eyebrow}`}>
                                    Proposta para esta semana
                                </p>
                                <p className="mt-1 text-sm font-bold leading-relaxed text-on-surface">
                                    {visibleAnalysis.actionProposal}
                                </p>
                            </div>
                        )}
                    </>
                ) : loading ? (
                    <div className="space-y-3">
                        <div className="h-3 w-2/3 animate-pulse rounded-lg bg-slate-100" />
                        <div className="h-16 animate-pulse rounded-lg bg-slate-100" />
                    </div>
                ) : (
                    <p className={`text-sm font-semibold ${styles.muted}`}>Aguardando analise...</p>
                )}

            </div>
        </div>
    );
}
