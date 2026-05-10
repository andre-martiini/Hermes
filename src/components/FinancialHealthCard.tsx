import React, { useEffect, useState, useRef } from 'react';
import { doc, getDoc, setDoc } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from '../../firebase';
import { FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill, IncomeEntry } from '../../types';

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

function computeFingerprint(props: FinancialHealthCardProps): string {
    const { transactions, incomeEntries, fixedBills, goals, emergencyReserve, currentMonth, currentYear } = props;
    const activeTx = transactions.filter(t => t.status !== 'deleted');
    const receivedIncome = incomeEntries.filter(e => e.status !== 'deleted' && e.isReceived && e.month === currentMonth && e.year === currentYear);
    const paidBills = fixedBills.filter(b => b.isPaid && b.month === currentMonth && b.year === currentYear);
    const goalsSum = Math.round(goals.reduce((s, g) => s + (g.currentAmount || 0), 0));
    return [
        activeTx.length,
        receivedIncome.length,
        paidBills.length,
        goalsSum,
        emergencyReserve.current,
        currentMonth,
        currentYear,
    ].join('|');
}

function buildSnapshot(props: FinancialHealthCardProps) {
    const { transactions, incomeEntries, fixedBills, goals, emergencyReserve, settings, currentMonthTotal, currentMonthIncome, currentMonth, currentYear } = props;

    const monthKey = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
    const budget = settings.monthlyBudgets?.[monthKey] ?? settings.monthlyBudget ?? 0;

    const activeIncomeThisMonth = incomeEntries.filter(
        e => e.status !== 'deleted' && e.month === currentMonth && e.year === currentYear
    );
    const expectedIncome = activeIncomeThisMonth.reduce((s, e) => s + e.amount, 0);
    const receivedIncome = activeIncomeThisMonth.filter(e => e.isReceived).reduce((s, e) => s + e.amount, 0);

    const billsThisMonth = fixedBills.filter(b => b.month === currentMonth && b.year === currentYear);
    const billsTotal = billsThisMonth.reduce((s, b) => s + b.amount, 0);
    const billsPaid = billsThisMonth.filter(b => b.isPaid).reduce((s, b) => s + b.amount, 0);
    const billsPending = billsTotal - billsPaid;

    const reserveCoverageMonths = budget > 0 ? +(emergencyReserve.current / budget).toFixed(1) : 0;

    const activeTx = transactions.filter(t => t.status !== 'deleted');
    const spendingByCategory: Record<string, number> = {};
    for (const tx of activeTx) {
        spendingByCategory[tx.category] = (spendingByCategory[tx.category] || 0) + tx.amount;
    }
    const topCategories = Object.entries(spendingByCategory)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([name, amount]) => ({ name, amount: +amount.toFixed(2) }));

    const last3Months: { month: string; income: number; spent: number }[] = [];
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
        last3Months.push({ month: mKey, income: +mIncome.toFixed(2), spent: +mSpent.toFixed(2) });
    }

    return {
        currentMonth: monthKey,
        budget: +budget.toFixed(2),
        spent: +currentMonthTotal.toFixed(2),
        income: { expected: +expectedIncome.toFixed(2), received: +receivedIncome.toFixed(2) },
        bills: {
            total: billsThisMonth.length,
            paid: billsThisMonth.filter(b => b.isPaid).length,
            pendingAmount: +billsPending.toFixed(2),
        },
        reserve: {
            target: +emergencyReserve.target.toFixed(2),
            current: +emergencyReserve.current.toFixed(2),
            coverageMonths: reserveCoverageMonths,
        },
        goals: goals.filter(g => g.status === 'active').map(g => ({
            name: g.name,
            target: +g.targetAmount.toFixed(2),
            current: +g.currentAmount.toFixed(2),
            progress: g.targetAmount > 0 ? +(g.currentAmount / g.targetAmount).toFixed(2) : 0,
        })),
        topCategories,
        last3MonthsTrend: last3Months,
    };
}

export function FinancialHealthCard(props: FinancialHealthCardProps) {
    const [summary, setSummary] = useState<string | null>(null);
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
                    const cached = snap.data() as { summary: string; fingerprint: string };
                    if (cached.fingerprint === fingerprint) {
                        setSummary(cached.summary);
                        return;
                    }
                }

                setLoading(true);
                const fn = httpsCallable<{ snapshot: object }, { summary: string }>(functions, 'gerarResumoFinanceiro', { timeout: 60000 });
                const result = await fn({ snapshot: buildSnapshot(props) });
                const newSummary = result.data.summary;

                await setDoc(CACHE_DOC, {
                    summary: newSummary,
                    fingerprint,
                    generatedAt: new Date().toISOString(),
                });
                setSummary(newSummary);
            } catch (err) {
                console.error('Erro ao gerar resumo financeiro:', err);
            } finally {
                setLoading(false);
            }
        }

        refresh();
    }, [computeFingerprint(props)]);

    return (
        <div className="bg-surface p-6 md:p-8 rounded-none border-b md:border border-border-grid shadow-none">
            <div className="flex items-center justify-between mb-3">
                <h4 className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-primary-tactile rounded-full inline-block" />
                    SAÚDE FINANCEIRA
                </h4>
                {loading && (
                    <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest animate-pulse">
                        Analisando...
                    </span>
                )}
            </div>
            {summary ? (
                <p className="text-sm text-slate-300 leading-relaxed">
                    {summary}
                </p>
            ) : loading ? (
                <div className="h-12 bg-slate-800/40 rounded animate-pulse" />
            ) : (
                <p className="text-sm text-slate-500 italic">Aguardando análise...</p>
            )}
        </div>
    );
}
