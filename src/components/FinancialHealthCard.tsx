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
}

const CACHE_DOC = doc(db, 'finance_health_summary', 'config');

const STATUS_STYLES: Record<FinancialHealthStatus, {
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
    const spendingByCategory = transactionsThisMonth.reduce<Record<string, number>>((acc, t) => {
        const category = t.category || 'Sem categoria';
        acc[category] = (acc[category] || 0) + t.amount;
        return acc;
    }, {});

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
            topCategories: Object.entries(spendingByCategory)
                .map(([category, amount]) => ({ category, amount: +amount.toFixed(2) }))
                .sort((a, b) => b.amount - a.amount)
                .slice(0, 5),
            largestTransactions: transactionsThisMonth
                .map(t => ({
                    description: t.description,
                    category: t.category,
                    amount: +t.amount.toFixed(2),
                    date: t.date,
                }))
                .sort((a, b) => b.amount - a.amount)
                .slice(0, 5),
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
    return JSON.stringify(buildSnapshot(props));
}

function normalizeStatus(value: unknown): FinancialHealthStatus {
    if (value === 'critical' || value === 'attention' || value === 'stable' || value === 'strong') return value;
    return 'attention';
}

function normalizeAnalysis(value: unknown): FinancialHealthAnalysis {
    if (typeof value === 'string' && value.trim()) {
        return { ...FALLBACK_ANALYSIS, summary: value.trim(), title: 'Diagnóstico financeiro' };
    }

    if (!value || typeof value !== 'object') return FALLBACK_ANALYSIS;

    const raw = value as Partial<FinancialHealthAnalysis>;
    const score = typeof raw.score === 'number' && Number.isFinite(raw.score)
        ? Math.max(0, Math.min(100, Math.round(raw.score)))
        : undefined;

    return {
        status: normalizeStatus(raw.status),
        score,
        title: raw.title?.trim() || FALLBACK_ANALYSIS.title,
        summary: raw.summary?.trim() || FALLBACK_ANALYSIS.summary,
        mainRisk: raw.mainRisk?.trim() || FALLBACK_ANALYSIS.mainRisk,
        positivePoint: raw.positivePoint?.trim() || FALLBACK_ANALYSIS.positivePoint,
        actionProposal: raw.actionProposal?.trim() || FALLBACK_ANALYSIS.actionProposal,
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
                    const cached = snap.data() as { analysis?: FinancialHealthAnalysis; summary?: string; fingerprint: string };
                    if (cached.fingerprint === fingerprint) {
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

    return (
        <div className={`p-4 rounded-none border-4 flex flex-col gap-4 ${styles.container}`}>
            <div className="flex items-start justify-between gap-3 shrink-0">
                <div className="min-w-0">
                    <p className={`text-[10px] font-black uppercase tracking-[0.2em] font-mono ${styles.eyebrow}`}>
                        Saúde Financeira
                    </p>
                    <h3 className={`mt-1 text-base font-black leading-tight ${styles.title}`}>
                        {visibleAnalysis.title}
                    </h3>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    {typeof visibleAnalysis.score === 'number' && (
                        <span className={`text-[10px] font-black uppercase tracking-widest font-mono ${styles.muted}`}>
                            {visibleAnalysis.score}/100
                        </span>
                    )}
                    <span className={`px-2 py-1 text-[9px] font-black uppercase tracking-[0.16em] font-mono ${styles.badge}`}>
                        {loading ? 'Analisando' : styles.label}
                    </span>
                </div>
            </div>

            {analysis ? (
                <>
                    <p className={`text-sm font-medium leading-relaxed ${styles.text}`}>
                        {visibleAnalysis.summary}
                    </p>

                    <div className={`grid gap-3 sm:grid-cols-2 border-t pt-3 ${styles.divider}`}>
                        <div>
                            <p className={`text-[9px] font-black uppercase tracking-[0.18em] font-mono ${styles.eyebrow}`}>
                                Risco principal
                            </p>
                            <p className={`mt-1 text-xs font-bold leading-relaxed ${styles.text}`}>
                                {visibleAnalysis.mainRisk}
                            </p>
                        </div>
                        <div>
                            <p className={`text-[9px] font-black uppercase tracking-[0.18em] font-mono ${styles.eyebrow}`}>
                                Ponto positivo
                            </p>
                            <p className={`mt-1 text-xs font-bold leading-relaxed ${styles.text}`}>
                                {visibleAnalysis.positivePoint}
                            </p>
                        </div>
                    </div>

                    <div className={`border-t pt-3 ${styles.divider}`}>
                        <p className={`text-[9px] font-black uppercase tracking-[0.18em] font-mono ${styles.eyebrow}`}>
                            Proposta de ação
                        </p>
                        <p className={`mt-1 text-sm font-black leading-relaxed ${styles.title}`}>
                            {visibleAnalysis.actionProposal}
                        </p>
                    </div>
                </>
            ) : loading ? (
                <div className="space-y-3">
                    <div className="h-3 w-2/3 rounded-none animate-pulse bg-black/10" />
                    <div className="h-16 rounded-none animate-pulse bg-black/10" />
                </div>
            ) : (
                <p className={`text-sm font-bold italic ${styles.muted}`}>Aguardando análise...</p>
            )}
        </div>
    );
}
