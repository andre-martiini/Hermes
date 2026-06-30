import React, { useEffect, useState, useRef } from 'react';
import { doc, getDoc, setDoc } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from '../../firebase';
import { FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill, IncomeEntry } from '../../types';

type FinancialHealthStatus = 'critical' | 'attention' | 'stable' | 'strong';

interface FinancialHealthAnalysis {
    status: FinancialHealthStatus;
    score?: number;
    title: string;
    summary: string;
    mainRisk: string;
    positivePoint: string;
    actionProposal: string;
    isStructured?: boolean;
}

interface FinancialHealthCardProps {
    transactions: FinanceTransaction[];
    goals: FinanceGoal[];
    emergencyReserve: { target: number; current: number };
    settings: FinanceSettings;
    currentMonthTotal: number;
    currentMonthIncome: number;
    fixedBills: FixedBill[];
    incomeEntries: IncomeEntry[];
    currentMonth: number;
    currentYear: number;
    onOpenFinancialCopilot?: () => void;
}

const CACHE_DOC = doc(db, 'finance_health_summary', 'config');
const CACHE_SCHEMA_VERSION = 'financial-health-v2-structured-no-categories';

const STATUS_STYLES: Record<FinancialHealthStatus, {
    label: string;
    container: string;
    eyebrow: string;
    muted: string;
    badge: string;
    accent: string;
}> = {
    critical: {
        label: 'Crítico',
        container: 'border-rose-200 dark:border-rose-900/30',
        eyebrow: 'text-rose-700',
        muted: 'text-rose-700',
        badge: 'bg-rose-100 text-rose-800 dark:bg-rose-950/20 dark:text-rose-400',
        accent: 'bg-rose-600',
    },
    attention: {
        label: 'Atenção',
        container: 'border-amber-200 dark:border-amber-900/30',
        eyebrow: 'text-amber-700',
        muted: 'text-amber-700',
        badge: 'bg-amber-100 text-amber-800 dark:bg-amber-950/20 dark:text-amber-400',
        accent: 'bg-amber-500',
    },
    stable: {
        label: 'Estável',
        container: 'border-sky-200 dark:border-sky-900/30',
        eyebrow: 'text-sky-700',
        muted: 'text-sky-700',
        badge: 'bg-sky-100 text-sky-800 dark:bg-sky-950/20 dark:text-sky-400',
        accent: 'bg-sky-600',
    },
    strong: {
        label: 'Forte',
        container: 'border-emerald-200 dark:border-emerald-900/30',
        eyebrow: 'text-emerald-700',
        muted: 'text-emerald-700',
        badge: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/20 dark:text-emerald-400',
        accent: 'bg-emerald-600',
    },
};

const FALLBACK_ANALYSIS: FinancialHealthAnalysis = {
    status: 'attention',
    title: 'Diagnóstico financeiro em preparação',
    summary: 'Ainda não há uma análise consolidada para este recorte financeiro.',
    mainRisk: 'Dados insuficientes para apontar o risco principal com segurança.',
    positivePoint: 'Assim que houver dados suficientes, o Hermes destacará o ponto mais saudável do mês.',
    actionProposal: 'Revise as entradas, contas e gastos do mês para permitir uma proposta mais precisa.',
};

function buildSnapshot(props: FinancialHealthCardProps) {
    const { transactions, incomeEntries, fixedBills, goals, emergencyReserve, settings, currentMonthTotal, currentMonthIncome, currentMonth, currentYear } = props;

    const monthKey = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
    const budget = settings.monthlyBudgets?.[monthKey] ?? settings.monthlyBudget ?? 0;
    const reserveCoverageMonths = budget > 0 ? +(emergencyReserve.current / budget).toFixed(1) : 0;
    const transactionsThisMonth = transactions.filter(t => t.status !== 'deleted' && t.date.startsWith(monthKey));

    const billsThisMonth = fixedBills.filter(b => b.month === currentMonth && b.year === currentYear);
    const billsTotalAmount = billsThisMonth.reduce((s, b) => s + b.amount, 0);
    const billsPaidAmount = billsThisMonth.filter(b => b.isPaid).reduce((s, b) => s + b.amount, 0);

    const incomeThisMonth = incomeEntries.filter(
        e => e.status !== 'deleted' && e.month === currentMonth && e.year === currentYear
    );
    const incomeExpectedAmount = incomeThisMonth.reduce((s, e) => s + e.amount, 0);
    const incomeReceivedAmount = incomeThisMonth.filter(e => e.isReceived).reduce((s, e) => s + e.amount, 0);

    const tendencia3Meses: { month: string; incomeReceived: number; spent: number }[] = [];
    for (let i = 3; i >= 1; i--) {
        let m = currentMonth - i;
        let y = currentYear;
        if (m < 0) { m += 12; y -= 1; }
        const mKey = `${y}-${String(m + 1).padStart(2, '0')}`;
        const mIncome = incomeEntries
            .filter(e => e.status !== 'deleted' && e.month === m && e.year === y && e.isReceived)
            .reduce((s, e) => s + e.amount, 0);
        const mSpent = transactions
            .filter(t => t.status !== 'deleted' && t.date.startsWith(mKey))
            .reduce((s, t) => s + t.amount, 0);
        tendencia3Meses.push({ month: mKey, incomeReceived: +mIncome.toFixed(2), spent: +mSpent.toFixed(2) });
    }

    return {
        currentMonth: monthKey,
        gastos: {
            budget: +budget.toFixed(2),
            spent: +currentMonthTotal.toFixed(2),
            available: +(budget - currentMonthTotal).toFixed(2),
            lancamentos: transactionsThisMonth
                .filter(t => t.amount > 50)
                .map(t => ({
                    description: t.description,
                    amount: +t.amount.toFixed(2),
                    date: t.date,
                }))
                .sort((a, b) => b.amount - a.amount),
        },
        fluxoCaixa: {
            receivedIncome: +currentMonthIncome.toFixed(2),
            spent: +currentMonthTotal.toFixed(2),
            balance: +(currentMonthIncome - currentMonthTotal).toFixed(2),
        },
        reserve: {
            target: +emergencyReserve.target.toFixed(2),
            current: +emergencyReserve.current.toFixed(2),
            coverageMonths: reserveCoverageMonths,
        },
        metas: goals
            .filter(g => g.status === 'active')
            .map(g => ({
                name: g.name,
                target: +g.targetAmount.toFixed(2),
                current: +g.currentAmount.toFixed(2),
                progress: g.targetAmount > 0 ? +(g.currentAmount / g.targetAmount).toFixed(2) : 0,
            })),
        obrigacoesSaida: {
            total: billsThisMonth.length,
            paid: billsThisMonth.filter(b => b.isPaid).length,
            totalAmount: +billsTotalAmount.toFixed(2),
            paidAmount: +billsPaidAmount.toFixed(2),
            pendingAmount: +(billsTotalAmount - billsPaidAmount).toFixed(2),
            items: billsThisMonth.map(b => ({
                descricao: b.description,
                amount: +b.amount.toFixed(2),
                isPaid: b.isPaid,
            })),
        },
        obrigacoesEntrada: {
            total: incomeThisMonth.length,
            received: incomeThisMonth.filter(e => e.isReceived).length,
            expectedAmount: +incomeExpectedAmount.toFixed(2),
            receivedAmount: +incomeReceivedAmount.toFixed(2),
            pendingAmount: +(incomeExpectedAmount - incomeReceivedAmount).toFixed(2),
            items: incomeThisMonth.map(e => ({
                descricao: e.description,
                amount: +e.amount.toFixed(2),
                isReceived: e.isReceived,
            })),
        },
        tendencia3Meses,
    };
}

function computeFingerprint(props: FinancialHealthCardProps): string {
    return JSON.stringify({
        schemaVersion: CACHE_SCHEMA_VERSION,
        snapshot: buildSnapshot(props),
    });
}

function normalizeStatus(value: unknown): FinancialHealthStatus {
    if (value === 'critical' || value === 'attention' || value === 'stable' || value === 'strong') return value;
    return 'attention';
}

function normalizeAnalysis(value: unknown): FinancialHealthAnalysis {
    if (typeof value === 'string' && value.trim()) {
        return {
            ...FALLBACK_ANALYSIS,
            title: 'Diagnóstico financeiro',
            summary: value.trim(),
            mainRisk: '',
            positivePoint: '',
            actionProposal: '',
            isStructured: false,
        };
    }

    if (!value || typeof value !== 'object') return FALLBACK_ANALYSIS;

    const raw = value as Partial<FinancialHealthAnalysis>;
    const score = typeof raw.score === 'number' && Number.isFinite(raw.score)
        ? Math.max(0, Math.min(100, Math.round(raw.score)))
        : undefined;
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

export function FinancialHealthCard(props: FinancialHealthCardProps) {
    const [analysis, setAnalysis] = useState<FinancialHealthAnalysis | null>(null);
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
                    const cached = snap.data() as {
                        analysis?: FinancialHealthAnalysis;
                        summary?: string;
                        fingerprint: string;
                        schemaVersion?: string;
                    };
                    if (cached.fingerprint === fingerprint && cached.schemaVersion === CACHE_SCHEMA_VERSION) {
                        setAnalysis(normalizeAnalysis(cached.analysis ?? cached.summary));
                        return;
                    }
                }

                setLoading(true);
                const fn = httpsCallable<{ snapshot: object }, { analysis?: FinancialHealthAnalysis; summary?: string }>(functions, 'gerarResumoFinanceiro', { timeout: 60000 });
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
                console.error('Erro ao gerar resumo financeiro:', err);
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
        <div className={`relative overflow-hidden rounded-2xl border bg-white dark:bg-slate-900 p-5 shadow-card ${styles.container}`}>
            <div className={`absolute left-0 top-0 h-full w-1 ${styles.accent}`} />
            <div className="flex flex-col gap-4 pl-2">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <p className={`text-[10px] font-semibold uppercase tracking-[0.05em] font-sans ${styles.eyebrow}`}>
                            Saúde Financeira
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
                                        Risco principal
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
                                    Proposta de ação
                                </p>
                                <p className="mt-1 text-sm font-bold leading-relaxed text-on-surface">
                                    {visibleAnalysis.actionProposal}
                                </p>
                            </div>
                        )}
                    </>
                ) : loading ? (
                    <div className="space-y-3">
                        <div className="h-3 w-2/3 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
                        <div className="h-16 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
                    </div>
                ) : (
                    <p className={`text-sm font-semibold ${styles.muted}`}>Aguardando análise...</p>
                )}

            </div>
        </div>
    );
}
