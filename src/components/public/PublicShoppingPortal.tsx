import React, { useEffect, useMemo, useState } from 'react';
import { collection, doc, onSnapshot, updateDoc, writeBatch } from 'firebase/firestore';
import { db } from '../../../firebase';
import { ShoppingItem } from '../../../types';

const PublicShoppingPortal = () => {
    const [isValid, setIsValid] = useState<boolean | null>(null);
    const [loading, setLoading] = useState(true);
    const [items, setItems] = useState<ShoppingItem[]>([]);
    const [view, setView] = useState<'planning' | 'shopping'>('planning');
    const [searchTerm, setSearchTerm] = useState('');

    useEffect(() => {
        const urlParams = new URLSearchParams(window.location.search);
        const tokenParam = urlParams.get('token');

        if (!tokenParam) {
            setIsValid(false);
            setLoading(false);
            return;
        }

        const unsub = onSnapshot(doc(db, 'public_configs', 'shopping_portal'), (docSnap) => {
            if (!docSnap.exists()) {
                setIsValid(false);
                setLoading(false);
                return;
            }

            const data = docSnap.data() as { token?: string };
            setIsValid(!!data.token && data.token === tokenParam);
            setLoading(false);
        });

        return () => unsub();
    }, []);

    useEffect(() => {
        if (!isValid) {
            setItems([]);
            return;
        }

        const unsub = onSnapshot(collection(db, 'shopping_items'), (snapshot) => {
            const data = snapshot.docs.map((itemDoc) => ({ id: itemDoc.id, ...itemDoc.data() } as ShoppingItem));
            setItems(data);
        });

        return () => unsub();
    }, [isValid]);

    const filteredCatalog = useMemo(
        () =>
            items
                .filter(
                    (i) =>
                        i.nome.toLowerCase().includes(searchTerm.toLowerCase()) ||
                        i.categoria.toLowerCase().includes(searchTerm.toLowerCase())
                )
                .sort((a, b) => a.categoria.localeCompare(b.categoria) || a.nome.localeCompare(b.nome)),
        [items, searchTerm]
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
        [items]
    );

    const purchasedCount = plannedItems.filter((item) => item.isPurchased).length;

    const togglePlanned = async (id: string) => {
        const item = items.find((i) => i.id === id);
        if (!item) return;
        await updateDoc(doc(db, 'shopping_items', id), { isPlanned: !item.isPlanned, isPurchased: false });
    };

    const togglePurchased = async (id: string) => {
        const item = items.find((i) => i.id === id);
        if (!item) return;
        await updateDoc(doc(db, 'shopping_items', id), { isPurchased: !item.isPurchased });
    };

    const updateQuantidade = async (id: string, value: string) => {
        await updateDoc(doc(db, 'shopping_items', id), { quantidade: value });
    };

    const clearPlanning = async () => {
        const planned = items.filter((item) => item.isPlanned || item.isPurchased);
        if (planned.length === 0) return;
        const batch = writeBatch(db);
        planned.forEach((item) => {
            batch.update(doc(db, 'shopping_items', item.id), { isPlanned: false, isPurchased: false });
        });
        await batch.commit();
    };

    const finalizeShopping = async () => {
        const planned = items.filter((item) => item.isPlanned || item.isPurchased);
        if (planned.length === 0) return;
        const batch = writeBatch(db);
        planned.forEach((item) => {
            batch.update(doc(db, 'shopping_items', item.id), { isPlanned: false, isPurchased: false });
        });
        await batch.commit();
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
                    <h2 className="text-xl font-black text-slate-900 mb-2">Acesso Negado</h2>
                    <p className="text-slate-500">Token inválido ou expirado. Solicite um novo link de acesso.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 font-sans">
            <header className="bg-slate-900 text-white p-6 shadow-lg">
                <div className="max-w-4xl mx-auto">
                    <h1 className="text-lg font-black uppercase tracking-widest text-center">Lista de Compras</h1>
                    <p className="text-center text-[10px] font-bold uppercase tracking-widest text-slate-300 mt-2">
                        Sincronização em tempo real com o Hermes
                    </p>
                </div>
            </header>

            <main className="max-w-4xl mx-auto p-4 space-y-6 -mt-4">
                <div className="bg-white rounded-[2rem] border border-slate-100 shadow-xl p-4 md:p-6">
                    <div className="flex flex-wrap gap-2">
                        {(['planning', 'shopping'] as const).map((tab) => {
                            const label = tab === 'planning' ? 'Planejar' : 'Comprar';
                            return (
                                <button
                                    key={tab}
                                    onClick={() => setView(tab)}
                                    className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all relative ${view === tab ? 'bg-slate-900 text-white shadow-sm' : 'bg-slate-100 text-slate-500 hover:text-slate-700'}`}
                                >
                                    {label}
                                    {tab === 'planning' && plannedItems.length > 0 && (
                                        <span className="absolute -top-1 -right-1 bg-blue-500 text-white text-[8px] font-black w-4 h-4 rounded-full flex items-center justify-center">{plannedItems.length}</span>
                                    )}
                                    {tab === 'shopping' && purchasedCount > 0 && (
                                        <span className="absolute -top-1 -right-1 bg-emerald-500 text-white text-[8px] font-black w-4 h-4 rounded-full flex items-center justify-center">{purchasedCount}</span>
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
                            <button onClick={clearPlanning} className="h-12 px-4 bg-white border border-slate-100 rounded-2xl shadow-sm flex items-center gap-2 text-slate-400 hover:text-rose-500 hover:border-rose-200 hover:bg-rose-50 transition-all">
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                                <span className="text-[9px] font-black uppercase tracking-widest">Limpar</span>
                            </button>
                        </div>

                        {items.length === 0 ? (
                            <div className="py-24 text-center text-slate-300">
                                <p className="font-black uppercase tracking-widest text-sm">Nenhum item disponível</p>
                                <p className="text-xs font-medium mt-2 opacity-60">Adicione itens no Hermes para começar</p>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {Object.entries(groupedCatalog).map(([category, categoryItems]) => (
                                    <div key={category}>
                                        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.3em] pl-2 mb-2">{category}</h4>
                                        <div className="bg-white rounded-[2rem] border border-slate-100 shadow-sm divide-y divide-slate-50 overflow-hidden">
                                            {categoryItems.map((item) => (
                                                <div key={item.id} className={`flex items-center gap-4 px-5 py-4 transition-all ${item.isPlanned ? 'bg-blue-50/40' : 'hover:bg-slate-50'}`}>
                                                    <button
                                                        onClick={() => togglePlanned(item.id)}
                                                        className={`w-8 h-8 rounded-xl flex items-center justify-center transition-all flex-shrink-0 ${item.isPlanned ? 'bg-blue-600 text-white shadow-md shadow-blue-200' : 'bg-slate-100 text-slate-400 hover:bg-slate-200'}`}
                                                    >
                                                        {item.isPlanned ? (
                                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                        ) : (
                                                            <div className="w-2 h-2 bg-slate-400 rounded-full" />
                                                        )}
                                                    </button>
                                                    <span className={`flex-1 font-bold text-sm ${item.isPlanned ? 'text-slate-900' : 'text-slate-400'}`}>{item.nome}</span>
                                                    {item.isPlanned && (
                                                        <div className="flex items-center gap-2 bg-white border border-blue-100 rounded-xl px-3 py-1.5 shadow-sm">
                                                            <button
                                                                onClick={() =>
                                                                    updateQuantidade(
                                                                        item.id,
                                                                        String(Math.max(0.5, parseFloat(item.quantidade || '1') - (parseFloat(item.quantidade || '1') % 1 === 0 ? 1 : 0.5)))
                                                                    )
                                                                }
                                                                className="w-6 h-6 rounded-lg bg-slate-100 text-slate-600 font-black flex items-center justify-center hover:bg-blue-100 transition-all text-sm leading-none"
                                                            >
                                                                -
                                                            </button>
                                                            <span className="w-12 text-center text-slate-800 font-black text-sm">
                                                                {item.quantidade} <span className="text-slate-400 font-medium text-[10px]">{item.unit}</span>
                                                            </span>
                                                            <button
                                                                onClick={() =>
                                                                    updateQuantidade(
                                                                        item.id,
                                                                        String(parseFloat(item.quantidade || '1') + (parseFloat(item.quantidade || '1') % 1 === 0 ? 1 : 0.5))
                                                                    )
                                                                }
                                                                className="w-6 h-6 rounded-lg bg-slate-100 text-slate-600 font-black flex items-center justify-center hover:bg-blue-100 transition-all text-sm leading-none"
                                                            >
                                                                +
                                                            </button>
                                                        </div>
                                                    )}
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
                        <div className="bg-white rounded-[2rem] border border-slate-100 shadow-xl p-6">
                            <div className="flex items-center justify-between mb-4 gap-3">
                                <div>
                                    <h3 className="text-xl font-black text-slate-900">Comprando</h3>
                                    <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-0.5">
                                        {purchasedCount} de {plannedItems.length} comprados
                                    </p>
                                </div>
                                <button onClick={finalizeShopping} className="bg-emerald-500 text-white px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-emerald-600 transition-all shadow-lg shadow-emerald-100">
                                    Finalizar
                                </button>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                                <div
                                    className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
                                    style={{ width: plannedItems.length > 0 ? `${(purchasedCount / plannedItems.length) * 100}%` : '0%' }}
                                />
                            </div>
                        </div>

                        {plannedItems.length === 0 ? (
                            <div className="py-24 text-center text-slate-300">
                                <p className="font-black uppercase tracking-widest text-sm">Lista de compra vazia</p>
                                <p className="text-xs font-medium mt-2 opacity-60">Planeje itens para começar</p>
                            </div>
                        ) : (
                            <div className="bg-white rounded-[2rem] border border-slate-100 shadow-xl overflow-hidden">
                                <div className="divide-y divide-slate-50">
                                    {plannedItems.map((item) => (
                                        <div
                                            key={item.id}
                                            onClick={() => togglePurchased(item.id)}
                                            className={`flex items-center gap-5 px-6 py-5 cursor-pointer transition-all select-none ${item.isPurchased ? 'bg-slate-50/60 opacity-50' : 'hover:bg-slate-50'}`}
                                        >
                                            <div className={`w-10 h-10 rounded-2xl flex items-center justify-center transition-all flex-shrink-0 ${item.isPurchased ? 'bg-emerald-500 text-white shadow-md shadow-emerald-200' : 'bg-slate-100 text-slate-400'}`}>
                                                {item.isPurchased ? (
                                                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                ) : (
                                                    <div className="w-3 h-3 border-2 border-current rounded-full" />
                                                )}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <p className={`text-lg font-black tracking-tight ${item.isPurchased ? 'line-through text-slate-400' : 'text-slate-900'}`}>{item.nome}</p>
                                                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{item.categoria}</p>
                                            </div>
                                            <div className="text-right flex-shrink-0">
                                                <span className={`text-xl font-black ${item.isPurchased ? 'text-slate-300' : 'text-blue-600'}`}>{item.quantidade}</span>
                                                <span className="text-slate-400 font-medium text-xs ml-1">{item.unit}</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </main>
        </div>
    );
};

export default PublicShoppingPortal;
