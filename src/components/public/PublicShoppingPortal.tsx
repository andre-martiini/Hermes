import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../../firebase';
import { ShoppingItem } from '../../../types';

const PublicShoppingPortal = () => {
  const [isValid, setIsValid] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<ShoppingItem[]>([]);
  const [view, setView] = useState<'planning' | 'shopping'>('planning');
  const [searchTerm, setSearchTerm] = useState('');
  const [isClearPlanningPending, setIsClearPlanningPending] = useState(false);
  const [exitingPurchasedIds, setExitingPurchasedIds] = useState<string[]>([]);
  const [isPurchasedSectionOpen, setIsPurchasedSectionOpen] = useState(false);

  const tokenParam = new URLSearchParams(window.location.search).get('token') || '';

  const refreshPortal = useCallback(async () => {
    if (!tokenParam) {
      setIsValid(false);
      setLoading(false);
      return;
    }

    try {
      const fn = httpsCallable(functions, 'getPublicShoppingPortal');
      const response = await fn({ token: tokenParam });
      const data = response.data as { valid: boolean; items: ShoppingItem[] };
      setIsValid(Boolean(data.valid));
      setItems(Array.isArray(data.items) ? data.items : []);
    } catch (error) {
      console.error('Erro ao carregar portal externo de compras:', error);
      setIsValid(false);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [tokenParam]);

  useEffect(() => {
    void refreshPortal();
    if (!tokenParam) return;

    const interval = window.setInterval(() => {
      void refreshPortal();
    }, 12000);

    return () => window.clearInterval(interval);
  }, [refreshPortal, tokenParam]);

  const mutatePortal = useCallback(
    async (action: string, itemId?: string, value?: string) => {
      const fn = httpsCallable(functions, 'mutatePublicShoppingPortal');
      await fn({ token: tokenParam, action, itemId, value });
      await refreshPortal();
    },
    [refreshPortal, tokenParam],
  );

  const filteredCatalog = useMemo(
    () =>
      items
        .filter(
          (i) =>
            i.nome.toLowerCase().includes(searchTerm.toLowerCase()) ||
            i.categoria.toLowerCase().includes(searchTerm.toLowerCase()),
        )
        .sort((a, b) => a.categoria.localeCompare(b.categoria) || a.nome.localeCompare(b.nome)),
    [items, searchTerm],
  );

  const groupedCatalog = useMemo(() => {
    const grouped: Record<string, ShoppingItem[]> = {};
    filteredCatalog.forEach((item) => {
      if (!grouped[item.categoria]) grouped[item.categoria] = [];
      grouped[item.categoria].push(item);
    });
    return grouped;
  }, [filteredCatalog]);

  const plannedItems = useMemo(
    () =>
      items
        .filter((i) => i.isPlanned)
        .sort((a, b) => Number(a.isPurchased) - Number(b.isPurchased) || a.categoria.localeCompare(b.categoria)),
    [items],
  );

  const purchasedCount = plannedItems.filter((item) => item.isPurchased).length;
  const pendingShoppingItems = useMemo(() => plannedItems.filter((item) => !item.isPurchased), [plannedItems]);
  const purchasedShoppingItems = useMemo(() => plannedItems.filter((item) => item.isPurchased), [plannedItems]);

  const togglePlanned = async (id: string) => {
    await mutatePortal('toggle_planned', id);
  };

  const togglePurchased = async (id: string) => {
    const item = items.find((i) => i.id === id);
    if (!item) return;

    if (!item.isPurchased) {
      setExitingPurchasedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
      window.setTimeout(async () => {
        try {
          await mutatePortal('toggle_purchased', id);
        } finally {
          setExitingPurchasedIds((prev) => prev.filter((itemId) => itemId !== id));
        }
      }, 320);
      return;
    }

    await mutatePortal('toggle_purchased', id);
  };

  const updateQuantidade = async (id: string, value: string) => {
    await mutatePortal('update_quantity', id, value);
  };

  const handleClearPlanningClick = async () => {
    if (!isClearPlanningPending) {
      setIsClearPlanningPending(true);
      window.setTimeout(() => setIsClearPlanningPending(false), 3500);
      return;
    }
    setIsClearPlanningPending(false);
    await mutatePortal('clear_planning');
  };

  const finalizeShopping = async () => {
    await mutatePortal('finalize');
    setView('planning');
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
          <h2 className="text-xl font-bold text-slate-900 mb-2">Acesso Negado</h2>
          <p className="text-slate-500">Token invalido ou expirado. Solicite um novo link de acesso.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 font-sans">
      <header className="bg-slate-900 text-white p-6 shadow-lg">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-lg font-bold uppercase tracking-wider text-center">Lista de Compras</h1>
          <p className="text-center text-[10px] font-bold uppercase tracking-wider text-slate-300 mt-2">
            Sincronizacao em tempo real por atualizacao periodica
          </p>
        </div>
      </header>

      <main className="max-w-4xl mx-auto p-4 space-y-6 -mt-4">
        <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-4 md:p-6">
          <div className="flex flex-wrap gap-2">
            {(['planning', 'shopping'] as const).map((tab) => {
              const label = tab === 'planning' ? 'Planejar' : 'Comprar';
              return (
                <button
                  key={tab}
                  onClick={() => setView(tab)}
                  className={`px-4 py-2 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all relative ${view === tab ? 'bg-slate-900 text-white shadow-sm' : 'bg-slate-100 text-slate-500 hover:text-slate-700'}`}
                >
                  {label}
                  {tab === 'planning' && plannedItems.length > 0 && (
                    <span className="absolute -top-1 -right-1 bg-blue-500 text-white text-[8px] font-bold w-4 h-4 rounded-full flex items-center justify-center">{plannedItems.length}</span>
                  )}
                  {tab === 'shopping' && purchasedCount > 0 && (
                    <span className="absolute -top-1 -right-1 bg-emerald-500 text-white text-[8px] font-bold w-4 h-4 rounded-full flex items-center justify-center">{purchasedCount}</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {view === 'planning' && (
          <div className="space-y-6 animate-in fade-in duration-300">
            <div className="flex items-center gap-3">
              <div className="flex-1 bg-white border border-slate-100 rounded-2xl px-5 py-3 flex items-center gap-3 shadow-sm focus-within:ring-2 focus-within:ring-blue-100 transition-all">
                <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                <input
                  type="text"
                  placeholder="Filtrar itens..."
                  className="flex-1 bg-transparent outline-none text-sm font-bold text-slate-700 placeholder:text-slate-300"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              <button onClick={handleClearPlanningClick} className={`h-12 px-3 border rounded-2xl shadow-sm flex items-center gap-2 transition-all ${isClearPlanningPending ? 'bg-rose-500 border-rose-600 text-white' : 'bg-white border-slate-100 text-slate-400 hover:text-rose-500 hover:border-rose-200 hover:bg-rose-50'}`}>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                <span className="text-[8px] font-bold uppercase tracking-wider">{isClearPlanningPending ? 'Confirma limpeza' : 'Limpar Planejamento'}</span>
              </button>
            </div>

            {items.length === 0 ? (
              <div className="py-24 text-center text-slate-300">
                <p className="font-bold uppercase tracking-wider text-sm">Nenhum item disponivel</p>
                <p className="text-xs font-medium mt-2 opacity-60">Adicione itens no Hermes para comecar</p>
              </div>
            ) : (
              <div className="space-y-4">
                {Object.entries(groupedCatalog).map(([category, categoryItems]) => (
                  <div key={category}>
                    <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider pl-2 mb-2">{category}</h4>
                    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm divide-y divide-slate-50 overflow-hidden">
                      {categoryItems.map((item) => (
                        <div key={item.id} className={`flex items-center gap-4 px-5 py-4 transition-all ${item.isPlanned ? 'bg-blue-50/40' : 'hover:bg-slate-50'}`}>
                          <button
                            onClick={() => void togglePlanned(item.id)}
                            className={`w-8 h-8 rounded-xl flex items-center justify-center transition-all flex-shrink-0 ${item.isPlanned ? 'bg-blue-600 text-white shadow-md shadow-blue-200' : 'bg-slate-100 text-slate-400 hover:bg-slate-200'}`}
                          >
                            {item.isPlanned ? '✓' : '+'}
                          </button>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-bold text-slate-800">{item.nome}</p>
                            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{item.categoria}</p>
                          </div>
                          <input
                            value={item.quantidade || ''}
                            onChange={(e) => void updateQuantidade(item.id, e.target.value)}
                            className="w-16 text-center bg-slate-50 border border-slate-200 rounded-xl px-2 py-2 text-xs font-bold text-slate-700"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {view === 'shopping' && (
          <div className="space-y-6 animate-in fade-in duration-300">
            <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 flex items-center justify-between">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Em aberto</p>
                <p className="text-2xl font-bold text-slate-900">{pendingShoppingItems.length}</p>
              </div>
              <button
                onClick={() => void finalizeShopping()}
                className="bg-emerald-600 text-white px-4 py-3 rounded-xl text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-700 transition-all"
              >
                Finalizar Compra
              </button>
            </div>

            <div className="space-y-3 hermes-stagger">
              {pendingShoppingItems.map((item) => (
                <div key={item.id} className="bg-white rounded-2xl border border-slate-100 shadow-sm px-5 py-4 flex items-center gap-4">
                  <button
                    onClick={() => void togglePurchased(item.id)}
                    className="w-10 h-10 rounded-2xl bg-slate-100 text-slate-500 font-bold"
                  >
                    {exitingPurchasedIds.includes(item.id) ? '...' : 'OK'}
                  </button>
                  <div className="flex-1">
                    <p className="text-sm font-bold text-slate-900">{item.nome}</p>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {item.quantidade || '1'} {item.unit || 'un'} • {item.categoria}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4">
              <button
                onClick={() => setIsPurchasedSectionOpen((prev) => !prev)}
                className="w-full flex items-center justify-between text-left"
              >
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Comprados ({purchasedShoppingItems.length})
                </span>
                <span className="text-slate-400">{isPurchasedSectionOpen ? '-' : '+'}</span>
              </button>

              {isPurchasedSectionOpen && (
                <div className="mt-4 space-y-3">
                  {purchasedShoppingItems.map((item) => (
                    <div key={item.id} className="bg-slate-50 rounded-2xl border border-slate-100 px-5 py-4 flex items-center gap-4">
                      <button
                        onClick={() => void togglePurchased(item.id)}
                        className="w-10 h-10 rounded-2xl bg-emerald-500 text-white font-bold"
                      >
                        ✓
                      </button>
                      <div className="flex-1">
                        <p className="text-sm font-bold text-slate-900">{item.nome}</p>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          {item.quantidade || '1'} {item.unit || 'un'} • {item.categoria}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default PublicShoppingPortal;
