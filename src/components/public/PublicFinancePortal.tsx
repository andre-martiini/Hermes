import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../../firebase';
import { FinanceSettings, FinanceTransaction } from '../../../types';

const PublicFinancePortal = () => {
  const [isValid, setIsValid] = useState<boolean | null>(null);
  const [settings, setSettings] = useState<FinanceSettings | null>(null);
  const [externalTransactions, setExternalTransactions] = useState<FinanceTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [description, setDescription] = useState('');
  const [amount, setAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const tokenParam = new URLSearchParams(window.location.search).get('token') || '';

  const refreshPortal = useCallback(async () => {
    if (!tokenParam) {
      setIsValid(false);
      setLoading(false);
      return;
    }

    try {
      const fn = httpsCallable(functions, 'getPublicFinancePortal');
      const response = await fn({ token: tokenParam });
      const data = response.data as {
        valid: boolean;
        settings: { externalSpendingLimit: number };
        transactions: FinanceTransaction[];
      };

      setIsValid(Boolean(data.valid));
      setSettings({
        externalSpendingLimit: Number(data.settings?.externalSpendingLimit || 0),
        externalToken: tokenParam,
      } as FinanceSettings);
      setExternalTransactions(Array.isArray(data.transactions) ? data.transactions : []);
    } catch (error) {
      console.error('Erro ao carregar portal externo de gastos:', error);
      setIsValid(false);
      setExternalTransactions([]);
    } finally {
      setLoading(false);
    }
  }, [tokenParam]);

  useEffect(() => {
    void refreshPortal();
    if (!tokenParam) return;

    const interval = window.setInterval(() => {
      void refreshPortal();
    }, 15000);

    return () => window.clearInterval(interval);
  }, [refreshPortal, tokenParam]);

  const spentAmount = useMemo(
    () => externalTransactions.reduce((acc, transaction) => acc + Number(transaction.amount || 0), 0),
    [externalTransactions],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim() || !amount || !tokenParam) return;

    setSubmitting(true);
    try {
      const numAmount = parseFloat(amount.replace(',', '.'));
      if (Number.isNaN(numAmount)) throw new Error('Valor invalido');

      const fn = httpsCallable(functions, 'submitPublicFinanceTransaction');
      await fn({
        token: tokenParam,
        description: description.trim(),
        amount: numAmount,
      });

      setDescription('');
      setAmount('');
      setSuccessMessage('Gasto registrado com sucesso!');
      window.setTimeout(() => setSuccessMessage(null), 3000);
      await refreshPortal();
    } catch (error) {
      console.error('Erro ao registrar gasto externo:', error);
      alert('Erro ao registrar gasto. Tente novamente.');
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
          <p className="text-slate-500">Token invalido ou expirado. Solicite um novo link de acesso.</p>
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

        <div className="bg-white rounded-[2rem] p-6 shadow-lg border border-slate-100">
          <h2 className="text-sm font-black text-slate-900 uppercase tracking-widest mb-6 border-l-4 border-blue-500 pl-3">Novo Lancamento</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Descricao</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="O que voce comprou?"
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

          {successMessage && <p className="mt-4 text-center text-sm font-bold text-emerald-600">{successMessage}</p>}
        </div>

        <div className="bg-white rounded-[2rem] p-6 shadow-lg border border-slate-100">
          <h2 className="text-sm font-black text-slate-900 uppercase tracking-widest mb-4 border-l-4 border-emerald-500 pl-3">Lancamentos Externos</h2>
          <div className="space-y-3">
            {externalTransactions.length === 0 ? (
              <p className="text-sm text-slate-400 font-medium">Nenhum gasto externo registrado ainda.</p>
            ) : (
              externalTransactions.map((transaction) => (
                <div key={transaction.id} className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 border border-slate-100">
                  <div>
                    <p className="text-sm font-black text-slate-900">{transaction.description}</p>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                      {new Date(transaction.date).toLocaleString('pt-BR')}
                    </p>
                  </div>
                  <div className="text-sm font-black text-rose-500">
                    R$ {Number(transaction.amount || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default PublicFinancePortal;
