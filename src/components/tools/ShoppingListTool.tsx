import React, { useState, useEffect, useMemo } from 'react';
import { ShoppingLocation, ShoppingItem } from '../../types';
const ShoppingListTool = ({ onBack, showToast }: { onBack: () => void, showToast: (msg: string, type: 'success' | 'error' | 'info') => void }) => {
  const [locations, setLocations] = useState<ShoppingLocation[]>(() => {
    try { return JSON.parse(localStorage.getItem(SHOPPING_LOCATIONS_KEY) || '[]'); } catch { return []; }
  });
  const [items, setItems] = useState<ShoppingItem[]>(() => {
    try { return JSON.parse(localStorage.getItem(SHOPPING_ITEMS_KEY) || '[]'); } catch { return []; }
  });
  const [activeLocationId, setActiveLocationId] = useState<string | null>(null);
  const [view, setView] = useState<'locations' | 'planning' | 'shopping' | 'setup'>('locations');
  const [searchTerm, setSearchTerm] = useState('');
  const [newItemName, setNewItemName] = useState('');
  const [isDeletingLocation, setIsDeletingLocation] = useState<string | null>(null);
  const [isEditingItem, setIsEditingItem] = useState<string | null>(null);
  const [editItemValue, setEditItemValue] = useState('');
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    localStorage.setItem(SHOPPING_LOCATIONS_KEY, JSON.stringify(locations));
  }, [locations]);

  useEffect(() => {
    localStorage.setItem(SHOPPING_ITEMS_KEY, JSON.stringify(items));
  }, [items]);

  const activeLocation = locations.find(l => l.id === activeLocationId);

  const handleAddLocation = () => {
    const nome = prompt("Nome do Estabelecimento (ex: Atacadão, Farmácia):");
    if (!nome) return;
    const newLoc: ShoppingLocation = { id: `loc_${Date.now()}`, nome, icon: 'store' };
    setLocations(prev => [...prev, newLoc]);
    setActiveLocationId(newLoc.id);
    setView('planning');
  };

  const handleAddItem = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!newItemName.trim() || !activeLocationId) return;

    const existing = items.find(i => i.locationId === activeLocationId && i.nome.toLowerCase() === newItemName.trim().toLowerCase());
    if (existing) {
      setItems(prev => prev.map(i => i.id === existing.id ? { ...i, isPlanned: true } : i));
    } else {
      const newItem: ShoppingItem = {
        id: `item_${Date.now()}`,
        nome: newItemName.trim(),
        categoria: 'Geral',
        quantidade: '1',
        unit: 'un',
        isPlanned: true,
        isPurchased: false,
        locationId: activeLocationId
      };
      setItems(prev => [...prev, newItem]);
    }
    setNewItemName('');
  };

  const handleBatchImport = () => {
    if (!importText.trim() || !activeLocationId) return;
    const lines = importText.split('\n').map(l => l.trim()).filter(l => l !== '');
    if (lines.length === 0) return;

    setItems(prev => {
      let currentItems = [...prev];
      lines.forEach(line => {
        const existing = currentItems.find(i => i.locationId === activeLocationId && i.nome.toLowerCase() === line.toLowerCase());
        if (existing) {
          currentItems = currentItems.map(i => i.id === existing.id ? { ...i, isPlanned: true } : i);
        } else {
          currentItems.push({
            id: `item_${Date.now()}_${Math.random()}`,
            nome: line,
            categoria: 'Geral',
            quantidade: '1',
            unit: 'un',
            isPlanned: true,
            isPurchased: false,
            locationId: activeLocationId
          });
        }
      });
      return currentItems;
    });

    setImportText('');
    setIsImportModalOpen(false);
    showToast(`${lines.length} itens importados!`, "success");
  };

  const toggleItemPlanned = (id: string) => {
    setItems(prev => prev.map(i => i.id === id ? { ...i, isPlanned: !i.isPlanned } : i));
  };

  const handleUnplanAll = () => {
    if (plannedItems.length === 0) return;
    if (!window.confirm(`Deseja desmarcar todos os ${plannedItems.length} itens planejados?`)) return;
    setItems(prev => prev.map(i => i.locationId === activeLocationId ? { ...i, isPlanned: false } : i));
    showToast("Planejamento limpo!", "info");
  };

  const toggleItemSelection = (id: string) => {
    setSelectedItemIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBulkCategorize = () => {
    if (selectedItemIds.size === 0) return;
    const firstItem = items.find(i => selectedItemIds.has(i.id));
    const newCat = prompt(`Definir categoria para ${selectedItemIds.size} itens:`, firstItem?.categoria);
    if (!newCat) return;
    setItems(prev => prev.map(i => selectedItemIds.has(i.id) ? { ...i, categoria: newCat } : i));
    setSelectedItemIds(new Set());
    showToast(`${selectedItemIds.size} itens categorizados!`, "success");
  };

  const toggleItemPurchased = (id: string) => {
    setItems(prev => prev.map(i => i.id === id ? { ...i, isPurchased: !i.isPurchased } : i));
  };

  const deleteItem = (id: string) => {
    setItems(prev => prev.filter(i => i.id !== id));
  };

  const finalizeShopping = () => {
    if (!window.confirm("Finalizar compra? Isso removerá os itens da lista de hoje, mantendo-os no histórico.")) return;
    setItems(prev => prev.map(i => i.locationId === activeLocationId ? { ...i, isPlanned: false, isPurchased: false } : i));
    setView('locations');
    setActiveLocationId(null);
    showToast("Compra finalizada!", "success");
  };

  const filteredItems = useMemo(() => {
    return items
      .filter(i => i.locationId === activeLocationId)
      .filter(i => i.nome.toLowerCase().includes(searchTerm.toLowerCase()));
  }, [items, activeLocationId, searchTerm]);

  const groupedItems = useMemo(() => {
    const groups: { [key: string]: ShoppingItem[] } = {};
    filteredItems.forEach(item => {
      const cat = item.categoria || 'Geral';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(item);
    });
    return groups;
  }, [filteredItems]);

  const plannedItems = items.filter(i => i.locationId === activeLocationId && i.isPlanned);

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-8 pb-32">
      <div className="flex items-center gap-6 mb-4">
        <button onClick={view === 'locations' ? onBack : () => setView('locations')} className="w-12 h-12 bg-white rounded-2xl flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-900 transition-all shadow-sm">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div className="flex-1">
          <h2 className="text-3xl font-black text-slate-900 tracking-tighter">Lista de Compras</h2>
          <p className="text-slate-500 font-medium">{activeLocation ? activeLocation.nome : 'Selecione ou crie um local de compra'}</p>
        </div>
        {activeLocation && (
          <div className="flex bg-slate-100 p-1 rounded-2xl">
            <button onClick={() => setView('planning')} className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${view === 'planning' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}>Planejar</button>
            <button onClick={() => setView('shopping')} className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2 ${view === 'shopping' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}>
              Comprar
              {plannedItems.length > 0 && <span className="bg-orange-500 text-white text-[8px] font-black px-1.5 py-0.5 rounded-full">{plannedItems.length}</span>}
            </button>
            <button onClick={() => setView('setup')} className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${view === 'setup' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}>Configurar</button>
          </div>
        )}
      </div>

      {view === 'locations' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {locations.map(loc => (
            <button key={loc.id} onClick={() => { setActiveLocationId(loc.id); setView('planning'); }} className="bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-xl hover:shadow-2xl transition-all group text-left relative overflow-hidden">
              <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={(e) => { e.stopPropagation(); if (window.confirm("Excluir este local?")) setLocations(prev => prev.filter(l => l.id !== loc.id)); }} className="p-2 text-rose-500 hover:bg-rose-50 rounded-xl transition-colors">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
              </div>
              <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-all mb-6">
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>
              </div>
              <h3 className="text-2xl font-black text-slate-900 tracking-tighter mb-2">{loc.nome}</h3>
              <p className="text-slate-400 font-bold text-xs uppercase tracking-widest">{items.filter(i => i.locationId === loc.id).length} itens no histórico</p>
            </button>
          ))}
          <button onClick={handleAddLocation} className="border-4 border-dashed border-slate-100 p-8 rounded-[2.5rem] flex flex-col items-center justify-center text-slate-300 hover:text-blue-500 hover:border-blue-200 transition-all group">
            <svg className="w-12 h-12 mb-4 group-hover:scale-110 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
            <span className="font-black uppercase tracking-widest text-xs">Novo Local</span>
          </button>
        </div>
      )}

      {view === 'planning' && activeLocation && (
        <div className="space-y-8 animate-in fade-in duration-300">
          <div className="max-w-2xl mx-auto space-y-6">
            <div className="flex items-center justify-between gap-4">
              <div className="flex-1 bg-white border border-slate-200 rounded-[1.5rem] px-6 py-3 flex items-center gap-3 shadow-sm focus-within:ring-2 focus-within:ring-blue-100 transition-all">
                <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                <input
                  type="text"
                  placeholder="Pesquisar nos itens..."
                  className="flex-1 bg-transparent outline-none text-sm font-bold text-slate-700 placeholder:text-slate-300"
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                />
              </div>
              <button
                onClick={handleUnplanAll}
                className="group flex flex-col items-center gap-1.5 px-4"
                title="Desmarcar todos os itens"
              >
                <div className="w-10 h-10 bg-white border border-slate-200 rounded-xl flex items-center justify-center text-slate-400 group-hover:text-rose-500 group-hover:border-rose-200 group-hover:bg-rose-50 transition-all shadow-sm">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                </div>
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 group-hover:text-rose-500">Limpar</span>
              </button>
            </div>

            <form onSubmit={handleAddItem} className="bg-white p-2 rounded-[2rem] border-2 border-slate-100 shadow-xl flex items-center gap-4 focus-within:border-blue-500 transition-all">
              <input
                autoFocus
                type="text"
                placeholder="O que você precisa comprar?"
                className="flex-1 bg-transparent border-none outline-none px-6 py-4 text-lg font-bold text-slate-800 placeholder:text-slate-300"
                value={newItemName}
                onChange={e => setNewItemName(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setIsImportModalOpen(true)}
                className="p-3 text-slate-300 hover:text-blue-500 hover:bg-blue-50 rounded-xl transition-all"
                title="Importar em Lote"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0l-4-4m4 4v12" /></svg>
              </button>
              <button type="submit" className="bg-blue-600 text-white h-12 w-12 flex items-center justify-center rounded-2xl hover:bg-blue-700 transition-all shadow-lg active:scale-95">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
              </button>
            </form>

            <div className="space-y-4">
              {Object.entries(groupedItems).map(([cat, catItems]) => (
                <div key={cat} className="space-y-3">
                  <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.3em] pl-4">{cat}</h4>
                  <div className="bg-white rounded-[2rem] border border-slate-100 shadow-sm divide-y divide-slate-50">
                    {catItems.map(item => (
                      <div key={item.id} className="flex items-center gap-4 p-4 hover:bg-slate-50 transition-all group">
                        <button onClick={() => toggleItemPlanned(item.id)} className={`w-8 h-8 rounded-xl flex items-center justify-center transition-all ${item.isPlanned ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-300 hover:bg-slate-200'}`}>
                          {item.isPlanned ? <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <div className="w-2 h-2 bg-current rounded-full"></div>}
                        </button>
                        <span className={`flex-1 font-bold ${item.isPlanned ? 'text-slate-900' : 'text-slate-300'}`}>{item.nome}</span>
                        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => {
                            const newCat = prompt("Mudar categoria:", item.categoria);
                            if (newCat) setItems(prev => prev.map(i => i.id === item.id ? { ...i, categoria: newCat } : i));
                          }} className="p-2 text-slate-300 hover:text-blue-500 hover:bg-blue-50 rounded-lg transition-colors">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>
                          </button>
                          <button onClick={() => deleteItem(item.id)} className="p-2 text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {filteredItems.length === 0 && (
                <div className="py-20 text-center text-slate-300">
                  <p className="font-black uppercase tracking-widest text-sm italic">Nenhum item cadastrado ainda</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {view === 'shopping' && activeLocation && (
        <div className="max-w-2xl mx-auto space-y-8 animate-in fade-in duration-300">
          <div className="bg-white rounded-[2.5rem] border border-slate-100 shadow-xl overflow-hidden">
            <div className="p-8 border-b border-slate-50 flex items-center justify-between">
              <div>
                <h3 className="text-xl font-black text-slate-900">Carrinho de Compras</h3>
                <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">{plannedItems.filter(i => i.isPurchased).length} de {plannedItems.length} comprados</p>
              </div>
              <button onClick={finalizeShopping} className="bg-emerald-500 text-white px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-emerald-600 transition-all shadow-lg shadow-emerald-100">Finalizar</button>
            </div>

            <div className="divide-y divide-slate-50">
              {plannedItems.length === 0 ? (
                <div className="py-20 text-center text-slate-300">
                  <p className="font-black uppercase tracking-widest text-sm">Lista vazia</p>
                  <button onClick={() => setView('planning')} className="text-blue-500 text-[10px] uppercase font-black tracking-widest mt-4">Vá para o Planejamento →</button>
                </div>
              ) : (
                plannedItems.sort((a,b) => Number(a.isPurchased) - Number(b.isPurchased)).map(item => (
                  <div key={item.id} onClick={() => toggleItemPurchased(item.id)} className={`flex items-center gap-6 p-6 cursor-pointer transition-all ${item.isPurchased ? 'bg-slate-50 opacity-50' : 'hover:bg-slate-50'}`}>
                    <div className={`w-10 h-10 rounded-2xl flex items-center justify-center transition-all ${item.isPurchased ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-400'}`}>
                      {item.isPurchased ? <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <div className="w-3 h-3 border-2 border-current rounded-full"></div>}
                    </div>
                    <div className="flex-1">
                      <p className={`text-xl font-black ${item.isPurchased ? 'line-through text-slate-400' : 'text-slate-900'} tracking-tight`}>{item.nome}</p>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{item.categoria}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {view === 'setup' && activeLocation && (
        <div className="max-w-2xl mx-auto space-y-8 animate-in fade-in duration-300 pb-20">
          <div className="bg-white rounded-[2.5rem] border border-slate-100 shadow-xl overflow-hidden">
            <div className="p-8 border-b border-slate-50 flex items-center justify-between bg-slate-50/50">
              <div>
                <h3 className="text-xl font-black text-slate-900">Configurar Itens</h3>
                <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">{selectedItemIds.size} selecionados para ação em lote</p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => setSelectedItemIds(new Set())}
                  className="px-6 py-3 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-slate-600 transition-all"
                >
                  Limpar
                </button>
                <button
                  onClick={handleBulkCategorize}
                  disabled={selectedItemIds.size === 0}
                  className="bg-blue-600 text-white px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-lg shadow-blue-100 flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>
                  Categorizar
                </button>
              </div>
            </div>

            <div className="divide-y divide-slate-50">
              {filteredItems.map(item => (
                <div
                  key={item.id}
                  onClick={() => toggleItemSelection(item.id)}
                  className={`flex items-center gap-4 p-5 cursor-pointer transition-all ${selectedItemIds.has(item.id) ? 'bg-blue-50/50' : 'hover:bg-slate-50'}`}
                >
                  <div className={`w-6 h-6 rounded-lg border-2 flex items-center justify-center transition-all ${selectedItemIds.has(item.id) ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-200 text-transparent'}`}>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" /></svg>
                  </div>
                  <div className="flex-1">
                    <p className="font-bold text-slate-800">{item.nome}</p>
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{item.categoria}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {isImportModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
          <div className="bg-white w-full max-w-lg rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
            <div className="p-8 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="text-2xl font-black text-slate-900 tracking-tight">Importação em Lote</h3>
                <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mt-1">Um item por linha</p>
              </div>
              <button onClick={() => setIsImportModalOpen(false)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="p-8 space-y-4">
              <textarea
                autoFocus
                className="w-full bg-slate-50 border border-slate-100 rounded-[1.5rem] p-6 text-slate-800 font-bold leading-relaxed outline-none focus:ring-4 focus:ring-blue-100 transition-all min-h-[300px] resize-none"
                placeholder="Exemplo:&#10;Arroz&#10;Feijão&#10;Macarrão&#10;Leite"
                value={importText}
                onChange={e => setImportText(e.target.value)}
              />
              <div className="flex gap-4">
                <button onClick={() => setIsImportModalOpen(false)} className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-2xl transition-all">Cancelar</button>
                <button
                  onClick={handleBatchImport}
                  className="flex-[2] py-4 bg-blue-600 text-white rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg shadow-blue-100 hover:bg-blue-700 transition-all"
                >
                  Importar {importText.split('\n').filter(l => l.trim()).length} Itens
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export { ShoppingListTool };
