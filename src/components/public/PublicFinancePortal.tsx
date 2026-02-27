import React, { useState, useEffect } from 'react';
import { collection, addDoc, onSnapshot, doc, query, where, getDocs } from 'firebase/firestore';
import { db } from '../../../firebase';
import { FinanceSettings, FinanceTransaction } from '../../../types';

const PublicFinancePortal = () => {
    const [token, setToken] = useState<string | null>(null);
    const [isValid, setIsValid] = useState<boolean | null>(null);
    const [settings, setSettings] = useState<FinanceSettings | null>(null);
    const [spentAmount, setSpentAmount] = useState<number>(0);
    const [loading, setLoading] = useState<boolean>(true);

    // Form State
    const [description, setDescription] = useState('');
    const [amount, setAmount] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    useEffect(() => {
        const urlParams = new URLSearchParams(window.location.search);
        const tokenParam = urlParams.get('token');
        setToken(tokenParam);

        if (tokenParam) {
            // Validate against public config doc to prevent data leak
            const unsubSettings = onSnapshot(doc(db, 'public_configs', 'finance_portal'), (docSnap) => {
                if (docSnap.exists()) {
                    const data = docSnap.data();

                    if (data.token && data.token === tokenParam) {
                        setIsValid(true);
                        // Map public data to settings structure for UI compatibility
                        setSettings({
                            externalSpendingLimit: data.limit,
                            externalToken: data.token
                        } as any);
                    } else {
                        setIsValid(false);
                    }
                } else {
                    setIsValid(false);
                }
                setLoading(false);
            });

            return () => unsubSettings();
        } else {
            setIsValid(false);
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (isValid && settings) {
            const now = new Date();
            const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
            const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString();

            // Query with date filter to improve performance and prevent full history download
            // Note: This requires a composite index on 'origin' + 'date' in Firestore.
            // If it fails, it usually falls back or errors out, but for robustness we include the filter.
            const q = query(
                collection(db, 'finance_transactions'),
                where('origin', '==', 'external'),
                where('date', '>=', startOfMonth)
            );

            const unsubTransactions = onSnapshot(q, (snapshot) => {
                let total = 0;
                snapshot.docs.forEach(doc => {
                    const t = doc.data() as FinanceTransaction;
                    // Double check end date just in case
                    if (t.date <= endOfMonth && t.status !== 'deleted') {
                        total += t.amount;
                    }
                });
                setSpentAmount(total);
            });

            return () => unsubTransactions();
        }
    }, [isValid, settings]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!description || !amount) return;

        setSubmitting(true);
        try {
            const numAmount = parseFloat(amount.replace(',', '.'));
            if (isNaN(numAmount)) throw new Error("Valor inválido");

            const now = new Date();
            const day = now.getDate();
            const sprint = day < 8 ? 1 : day < 15 ? 2 : day < 22 ? 3 : 4;

            const newTransaction: Omit<FinanceTransaction, 'id'> = {
                description,
                amount: numAmount,
                date: now.toISOString(),
                sprint,
                category: 'Gasto Externo',
                status: 'active',
                origin: 'external'
            };

            await addDoc(collection(db, 'finance_transactions'), newTransaction);

            setDescription('');
            setAmount('');
            setSuccessMessage("Gasto registrado com sucesso!");
            setTimeout(() => setSuccessMessage(null), 3000);
        } catch (error) {
            console.error("Error adding transaction:", error);
            alert("Erro ao registrar gasto. Tente novamente.");
        } finally {
            setSubmitting(false);
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-slate-900 flex items-center justify-center">
                <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
        );
    }

    if (!isValid) {
        return (
            <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
                <div className="bg-white rounded-2xl p-8 max-w-md w-full text-center">
                    <div className="w-16 h-16 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center mx-auto mb-4">
                        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </div>
                    <h2 className="text-xl font-black text-slate-900 mb-2">Acesso Negado</h2>
                    <p className="text-slate-500">Token inválido ou expirado. Solicite um novo link de acesso.</p>
                </div>
            </div>
        );
    }

    const limit = settings?.externalSpendingLimit || 0;
    const remaining = limit - spentAmount;
    const percentUsed = limit > 0 ? (spentAmount / limit) * 100 : 0;
    const isOverLimit = remaining < 0;

    return (
        <div className="min-h-screen bg-slate-50 font-sans">
            <header className="bg-slate-900 text-white p-6 shadow-lg">
                <div className="max-w-md mx-auto">
                    <h1 className="text-lg font-black uppercase tracking-widest text-center">Controle de Gastos</h1>
                </div>
            </header>

            <main className="max-w-md mx-auto p-4 space-y-6 -mt-4">
                {/* Balance Card */}
                <div className="bg-white rounded-[2rem] p-6 shadow-xl border border-slate-100 relative overflow-hidden">
                    <div className="relative z-10 text-center">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-2">Saldo Restante</p>
                        <div className={`text-4xl font-black tracking-tighter ${isOverLimit ? 'text-rose-500' : 'text-emerald-500'}`}>
                            R$ {remaining.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                        </div>
                        <div className="mt-4 flex justify-between text-xs font-bold text-slate-400 uppercase tracking-widest px-4">
                            <span>Gasto: R$ {spentAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                            <span>Limite: R$ {limit.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                        </div>

                        <div className="mt-4 h-3 bg-slate-100 rounded-full overflow-hidden w-full">
                            <div
                                className={`h-full transition-all duration-1000 ${isOverLimit ? 'bg-rose-500' : percentUsed > 80 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                                style={{ width: `${Math.min(percentUsed, 100)}%` }}
                            ></div>
                        </div>
                    </div>
                </div>

                {/* Input Form */}
                <div className="bg-white rounded-[2rem] p-6 shadow-lg border border-slate-100">
                    <h2 className="text-sm font-black text-slate-900 uppercase tracking-widest mb-6 border-l-4 border-blue-500 pl-3">Novo Lançamento</h2>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="space-y-2">
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Descrição</label>
                            <input
                                type="text"
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                placeholder="O que você comprou?"
                                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                                required
                            />
                        </div>

                        <div className="space-y-2">
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Valor (R$)</label>
                            <input
                                type="number"
                                step="0.01"
                                inputMode="decimal"
                                value={amount}
                                onChange={(e) => setAmount(e.target.value)}
                                placeholder="0,00"
                                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-lg font-black text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                                required
                            />
                        </div>

                        <button
                            type="submit"
                            disabled={submitting}
                            className="w-full bg-slate-900 text-white py-4 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-4 active:scale-95"
                        >
                            {submitting ? 'Enviando...' : 'Registrar Gasto'}
                        </button>
                    </form>
                </div>

                {successMessage && (
                    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-emerald-500 text-white px-6 py-3 rounded-full shadow-2xl font-bold text-xs uppercase tracking-widest animate-in fade-in slide-in-from-bottom-4">
                        {successMessage}
                    </div>
                )}
            </main>
        </div>
    );
};

export default PublicFinancePortal;
