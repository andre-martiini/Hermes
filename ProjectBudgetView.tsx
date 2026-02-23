import React, { useState, useEffect } from 'react';
import { collection, doc, onSnapshot, updateDoc, addDoc, query, orderBy, where } from 'firebase/firestore';
import { db } from './firebase';
import { Projeto, OrcamentoProjeto, ItemOrcamento, RemanejamentoRecursos, TransacaoProjeto, VinculoProjeto, TipoBolsa } from './types';
import { BurnRateSimulator } from './src/components/projects/BurnRateSimulator';

interface ProjectBudgetViewProps {
    projetoId: string;
}

export const ProjectBudgetView: React.FC<ProjectBudgetViewProps> = ({ projetoId }) => {
    const [project, setProject] = useState<Projeto | null>(null);
    const [items, setItems] = useState<ItemOrcamento[]>([]);
    const [reallocations, setReallocations] = useState<RemanejamentoRecursos[]>([]);
    const [transactions, setTransactions] = useState<TransacaoProjeto[]>([]);
    const [activeLinks, setActiveLinks] = useState<VinculoProjeto[]>([]);
    const [scholarshipTypes, setScholarshipTypes] = useState<TipoBolsa[]>([]);

    // Budget Config State
    const [budgetConfig, setBudgetConfig] = useState<OrcamentoProjeto>({ custeio: 0, capital: 0, bolsas: 0 });
    const [isEditingBudget, setIsEditingBudget] = useState(false);

    // Item Form State
    const [newItem, setNewItem] = useState<Partial<ItemOrcamento>>({
        rubrica: 'custeio',
        quantidade: 1,
        valor_unitario_estimado: 0,
        status: 'planejado'
    });
    const [isAddingItem, setIsAddingItem] = useState(false);

    // Sync local budget state when project loads
    useEffect(() => {
        if (project?.orcamento) {
            setBudgetConfig(project.orcamento);
        }
    }, [project]);

    // Subscriptions
    useEffect(() => {
        if (!projetoId) return;

        // Project Document (for Budget Config)
        const unsubProject = onSnapshot(doc(db, 'projetos', projetoId), (doc) => {
            if (doc.exists()) {
                setProject({ id: doc.id, ...doc.data() } as Projeto);
            }
        });

        // Planned Items
        const qItems = query(collection(db, 'projetos', projetoId, 'itens_orcamento'));
        const unsubItems = onSnapshot(qItems, (snapshot) => {
            setItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as ItemOrcamento)));
        });

        // Reallocations
        const qRealloc = query(collection(db, 'projetos', projetoId, 'remanejamentos'), orderBy('data', 'desc'));
        const unsubRealloc = onSnapshot(qRealloc, (snapshot) => {
            setReallocations(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as RemanejamentoRecursos)));
        });

        // Transactions
        const qTrans = query(collection(db, 'projetos', projetoId, 'transacoes'));
        const unsubTrans = onSnapshot(qTrans, (snapshot) => {
            setTransactions(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as TransacaoProjeto)));
        });

        // Active Links (for Simulator)
        const qLinks = query(collection(db, 'vinculos_projeto'), where('projeto_id', '==', projetoId));
        const unsubLinks = onSnapshot(qLinks, (snapshot) => {
            setActiveLinks(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as VinculoProjeto)));
        });

        // Scholarship Types
        const unsubTypes = onSnapshot(collection(db, 'tipos_bolsa'), (snapshot) => {
            setScholarshipTypes(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as TipoBolsa)));
        });

        return () => {
            unsubProject();
            unsubItems();
            unsubRealloc();
            unsubTrans();
            unsubLinks();
            unsubTypes();
        };
    }, [projetoId]);

    const handleSaveBudget = async () => {
        if (!project) return;
        try {
            await updateDoc(doc(db, 'projetos', project.id), {
                orcamento: budgetConfig
            });
            setIsEditingBudget(false);
        } catch (error) {
            console.error("Error saving budget:", error);
            alert("Erro ao salvar orçamento.");
        }
    };

    // Calculate Balances
    const calculateBalances = () => {
        const initial = project?.orcamento || { custeio: 0, capital: 0, bolsas: 0 };
        const balances = { custeio: 0, capital: 0, bolsas: 0 };
        const totalAllocated = { custeio: 0, capital: 0, bolsas: 0 }; // Initial + In - Out

        // Reallocations
        const reallocationsIn = { custeio: 0, capital: 0, bolsas: 0 };
        const reallocationsOut = { custeio: 0, capital: 0, bolsas: 0 };

        reallocations.forEach(r => {
            reallocationsOut[r.origem] += r.valor;
            reallocationsIn[r.destino] += r.valor;
        });

        // Spent
        const spent = { custeio: 0, capital: 0, bolsas: 0 };
        transactions.forEach(t => {
            if (t.status === 'cancelado') return;
            const item = items.find(i => i.id === t.item_orcamento_id);
            if (item) {
                spent[item.rubrica] += t.valor_real;
            }
        });

        // Final Calculation
        (['custeio', 'capital', 'bolsas'] as const).forEach(r => {
            const currentTotal = (initial[r] || 0) + reallocationsIn[r] - reallocationsOut[r];
            totalAllocated[r] = currentTotal;
            balances[r] = currentTotal - spent[r];
        });

        const totalProjectValue = (initial.custeio || 0) + (initial.capital || 0) + (initial.bolsas || 0);

        return { balances, spent, totalAllocated, totalProjectValue };
    };

    // Reallocation State
    const [reallocationForm, setReallocationForm] = useState({
        origem: 'custeio' as 'custeio' | 'capital' | 'bolsas',
        destino: 'capital' as 'custeio' | 'capital' | 'bolsas',
        valor: 0,
        justificativa: ''
    });

    const handleReallocate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (reallocationForm.origem === reallocationForm.destino) {
            alert("Origem e destino devem ser diferentes.");
            return;
        }
        if (reallocationForm.valor <= 0) {
            alert("O valor deve ser maior que zero.");
            return;
        }

        // Check balance (using the calculated balance from current render scope)
        const currentBalanceOrigem = balances[reallocationForm.origem];
        if (reallocationForm.valor > currentBalanceOrigem) {
            alert(`Saldo insuficiente em ${reallocationForm.origem}. Disponível: ${new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(currentBalanceOrigem)}`);
            return;
        }

        try {
            await addDoc(collection(db, 'projetos', projetoId, 'remanejamentos'), {
                projeto_id: projetoId,
                origem: reallocationForm.origem,
                destino: reallocationForm.destino,
                valor: Number(reallocationForm.valor),
                data: new Date().toISOString(),
                justificativa: reallocationForm.justificativa,
                usuario_responsavel: 'Gestor'
            });
            setReallocationForm({
                origem: 'custeio',
                destino: 'capital',
                valor: 0,
                justificativa: ''
            });
            alert("Remanejamento realizado com sucesso!");
        } catch (error) {
            console.error("Error reallocating:", error);
            alert("Erro ao realizar remanejamento.");
        }
    };

    const handleAddItem = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newItem.nome || !newItem.valor_unitario_estimado) return;

        try {
            await addDoc(collection(db, 'projetos', projetoId, 'itens_orcamento'), {
                ...newItem,
                quantidade: Number(newItem.quantidade),
                valor_unitario_estimado: Number(newItem.valor_unitario_estimado)
            });
            setNewItem({
                rubrica: 'custeio',
                quantidade: 1,
                valor_unitario_estimado: 0,
                status: 'planejado',
                nome: '',
                descricao: ''
            });
            setIsAddingItem(false);
        } catch (error) {
            console.error("Error adding item:", error);
            alert("Erro ao adicionar item.");
        }
    };

    const { balances, spent, totalAllocated, totalProjectValue } = calculateBalances();

    if (!project) return <div className="p-8 text-center text-slate-400 font-bold animate-pulse">Carregando dados financeiros...</div>;

    return (
        <div className="p-6 space-y-10">

           {/* 1. Configuração do Teto Orçamental */}
           <div className="bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h3 className="text-xl font-black text-slate-800">Teto Orçamental Inicial</h3>
                        <p className="text-slate-400 text-xs font-medium mt-1">Defina os valores aprovados para cada rubrica macro.</p>
                    </div>
                    {!isEditingBudget ? (
                        <button
                            onClick={() => setIsEditingBudget(true)}
                            className="text-indigo-600 hover:text-indigo-800 text-xs font-black uppercase tracking-widest flex items-center gap-2"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                            Editar Tetos
                        </button>
                    ) : (
                        <div className="flex gap-3">
                            <button
                                onClick={() => {
                                    setIsEditingBudget(false);
                                    if (project.orcamento) setBudgetConfig(project.orcamento);
                                }}
                                className="text-slate-400 hover:text-slate-600 text-xs font-black uppercase tracking-widest"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleSaveBudget}
                                className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-xs font-black uppercase tracking-widest shadow-lg shadow-indigo-200 hover:bg-indigo-700 transition-all"
                            >
                                Salvar Alterações
                            </button>
                        </div>
                    )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {(['custeio', 'capital', 'bolsas'] as const).map(rubrica => (
                        <div key={rubrica} className={`p-6 rounded-2xl border ${isEditingBudget ? 'border-indigo-200 bg-indigo-50/30' : 'border-slate-100 bg-slate-50'}`}>
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] block mb-2">
                                {rubrica}
                            </label>
                            {isEditingBudget ? (
                                <div className="relative">
                                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-bold text-sm">R$</span>
                                    <input
                                        type="number"
                                        value={budgetConfig[rubrica]}
                                        onChange={e => setBudgetConfig(prev => ({ ...prev, [rubrica]: Number(e.target.value) }))}
                                        className="w-full bg-white border border-slate-200 rounded-xl py-2 pl-10 pr-4 font-black text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500"
                                    />
                                </div>
                            ) : (
                                <p className="text-2xl font-black text-slate-700">
                                    {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(budgetConfig[rubrica])}
                                </p>
                            )}
                        </div>
                    ))}
                </div>
           </div>

           {/* 2. Dashboard Resumo */}
           <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                <div className="lg:col-span-1 bg-indigo-600 rounded-[2rem] p-8 text-white shadow-xl shadow-indigo-200 relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16"></div>
                    <div className="relative z-10">
                        <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-70">Valor Total do Projeto</p>
                        <p className="text-3xl font-black mt-2 tracking-tight">
                            {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(totalProjectValue)}
                        </p>
                        <div className="mt-8 pt-6 border-t border-white/20">
                            <p className="text-xs font-medium opacity-80">Saldo Global Disponível</p>
                            <p className="text-xl font-bold mt-1">
                                {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(
                                    balances.custeio + balances.capital + balances.bolsas
                                )}
                            </p>
                        </div>
                    </div>
                </div>

                <div className="lg:col-span-3 grid grid-cols-1 md:grid-cols-3 gap-4">
                    {(['custeio', 'capital', 'bolsas'] as const).map(rubrica => {
                        const balance = balances[rubrica];
                        const total = totalAllocated[rubrica];
                        const percent = total > 0 ? (balance / total) * 100 : 0;
                        const isLow = percent < 10;

                        return (
                            <div key={rubrica} className="bg-white rounded-[2rem] border border-slate-200 p-6 flex flex-col justify-between hover:shadow-lg transition-shadow">
                                <div>
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{rubrica}</span>
                                        {isLow && balance > 0 && (
                                            <span className="px-2 py-1 bg-red-100 text-red-600 rounded-full text-[9px] font-black uppercase tracking-widest animate-pulse">
                                                Atenção
                                            </span>
                                        )}
                                    </div>
                                    <p className={`text-2xl font-black ${isLow ? 'text-red-500' : 'text-slate-800'}`}>
                                        {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(balance)}
                                    </p>
                                    <p className="text-xs font-medium text-slate-400 mt-1">
                                        de {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(total)}
                                    </p>
                                </div>
                                <div className="mt-4">
                                    <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                                        <div
                                            className={`h-full rounded-full ${isLow ? 'bg-red-500' : 'bg-emerald-500'}`}
                                            style={{ width: `${Math.min(percent, 100)}%` }}
                                        ></div>
                                    </div>
                                    <div className="flex justify-between mt-2 text-[10px] font-bold text-slate-400">
                                        <span>Gasto: {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(spent[rubrica])}</span>
                                        <span>{percent.toFixed(1)}% Disp.</span>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
           </div>

           {/* 3. Gestão de Itens Planeados */}
           <div className="bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm">
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h3 className="text-xl font-black text-slate-800">Itens Planejados</h3>
                        <p className="text-slate-400 text-xs font-medium mt-1">Lista de aquisições e contratações previstas no plano de trabalho.</p>
                    </div>
                    <button
                        onClick={() => setIsAddingItem(!isAddingItem)}
                        className="bg-slate-900 text-white px-5 py-3 rounded-xl text-xs font-black uppercase tracking-widest hover:bg-slate-800 transition-all flex items-center gap-2"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>
                        Novo Item
                    </button>
                </div>

                {isAddingItem && (
                    <form onSubmit={handleAddItem} className="mb-8 bg-slate-50 p-6 rounded-2xl border border-slate-200 animate-in fade-in slide-in-from-top-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                            <div className="lg:col-span-2">
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Descrição do Item</label>
                                <input
                                    placeholder="Ex: Notebook Core i7"
                                    value={newItem.nome || ''}
                                    onChange={e => setNewItem({...newItem, nome: e.target.value})}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700"
                                    autoFocus
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Rubrica</label>
                                <select
                                    value={newItem.rubrica}
                                    onChange={e => setNewItem({...newItem, rubrica: e.target.value as any})}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-medium text-slate-700 bg-white"
                                >
                                    <option value="custeio">Custeio</option>
                                    <option value="capital">Capital</option>
                                    <option value="bolsas">Bolsas</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Qtd</label>
                                <input
                                    type="number"
                                    value={newItem.quantidade}
                                    onChange={e => setNewItem({...newItem, quantidade: Number(e.target.value)})}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Valor Unit. Est.</label>
                                <input
                                    type="number"
                                    value={newItem.valor_unitario_estimado}
                                    onChange={e => setNewItem({...newItem, valor_unitario_estimado: Number(e.target.value)})}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700"
                                />
                            </div>
                            <div className="lg:col-span-3">
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Observações</label>
                                <input
                                    placeholder="Detalhes adicionais..."
                                    value={newItem.descricao || ''}
                                    onChange={e => setNewItem({...newItem, descricao: e.target.value})}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-medium text-slate-600"
                                />
                            </div>
                        </div>
                        <div className="flex justify-end gap-3">
                            <button
                                type="button"
                                onClick={() => setIsAddingItem(false)}
                                className="px-4 py-2 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-slate-600"
                            >
                                Cancelar
                            </button>
                            <button
                                type="submit"
                                className="bg-indigo-600 text-white px-6 py-2 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg shadow-indigo-200 hover:bg-indigo-700"
                            >
                                Adicionar Item
                            </button>
                        </div>
                    </form>
                )}

                <div className="overflow-hidden rounded-2xl border border-slate-100">
                    <table className="w-full">
                        <thead className="bg-slate-50 border-b border-slate-100">
                            <tr>
                                <th className="p-4 text-left text-[10px] font-black text-slate-400 uppercase tracking-widest">Item</th>
                                <th className="p-4 text-left text-[10px] font-black text-slate-400 uppercase tracking-widest">Rubrica</th>
                                <th className="p-4 text-left text-[10px] font-black text-slate-400 uppercase tracking-widest">Est. Total</th>
                                <th className="p-4 text-left text-[10px] font-black text-slate-400 uppercase tracking-widest">Gasto Real</th>
                                <th className="p-4 text-left text-[10px] font-black text-slate-400 uppercase tracking-widest">Economia</th>
                                <th className="p-4 text-left text-[10px] font-black text-slate-400 uppercase tracking-widest">Status</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {items.map(item => {
                                const totalEstimated = item.quantidade * item.valor_unitario_estimado;
                                const totalReal = transactions
                                    .filter(t => t.item_orcamento_id === item.id && t.status !== 'cancelado')
                                    .reduce((acc, curr) => acc + curr.valor_real, 0);
                                const savings = totalEstimated - totalReal;
                                const isExecuted = item.status === 'executado' || totalReal > 0;

                                return (
                                    <tr key={item.id} className="hover:bg-slate-50 transition-colors group">
                                        <td className="p-4">
                                            <p className="font-bold text-slate-700 text-sm">{item.nome}</p>
                                            <p className="text-xs text-slate-400 font-medium">{item.quantidade} un. x {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(item.valor_unitario_estimado)}</p>
                                        </td>
                                        <td className="p-4">
                                            <span className="px-2 py-1 bg-slate-100 text-slate-500 rounded text-[10px] font-black uppercase tracking-widest">
                                                {item.rubrica}
                                            </span>
                                        </td>
                                        <td className="p-4 text-sm font-bold text-slate-600">
                                            {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(totalEstimated)}
                                        </td>
                                        <td className="p-4 text-sm font-bold text-indigo-600">
                                            {totalReal > 0 ? new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(totalReal) : '-'}
                                        </td>
                                        <td className="p-4">
                                            {totalReal > 0 ? (
                                                <span className={`text-xs font-bold ${savings >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                                                    {savings > 0 ? '+' : ''}{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(savings)}
                                                </span>
                                            ) : (
                                                <span className="text-slate-300 text-xs">-</span>
                                            )}
                                        </td>
                                        <td className="p-4">
                                            <span className={`px-2 py-1 rounded text-[10px] font-black uppercase tracking-widest ${
                                                isExecuted ? 'bg-green-100 text-green-700' : 'bg-yellow-50 text-yellow-600'
                                            }`}>
                                                {isExecuted ? 'Em Execução' : 'Planejado'}
                                            </span>
                                        </td>
                                    </tr>
                                );
                            })}
                            {items.length === 0 && (
                                <tr>
                                    <td colSpan={6} className="p-8 text-center text-slate-400 font-medium text-sm italic">Nenhum item planejado ainda.</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
           </div>

           {/* 4. Remanejamento de Recursos */}
           <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Formulário */}
                <div className="bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm">
                    <h3 className="text-xl font-black text-slate-800 mb-6">Remanejar Recursos</h3>
                    <form onSubmit={handleReallocate} className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">De (Origem)</label>
                                <select
                                    value={reallocationForm.origem}
                                    onChange={e => setReallocationForm({...reallocationForm, origem: e.target.value as any})}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-medium text-slate-700 bg-white"
                                >
                                    <option value="custeio">Custeio</option>
                                    <option value="capital">Capital</option>
                                    <option value="bolsas">Bolsas</option>
                                </select>
                                <p className="text-[10px] font-bold text-slate-400 mt-1 text-right">
                                    Disp: {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(balances[reallocationForm.origem])}
                                </p>
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Para (Destino)</label>
                                <select
                                    value={reallocationForm.destino}
                                    onChange={e => setReallocationForm({...reallocationForm, destino: e.target.value as any})}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-medium text-slate-700 bg-white"
                                >
                                    <option value="custeio">Custeio</option>
                                    <option value="capital">Capital</option>
                                    <option value="bolsas">Bolsas</option>
                                </select>
                            </div>
                        </div>
                        <div>
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Valor a Transferir</label>
                            <div className="relative">
                                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-bold text-sm">R$</span>
                                <input
                                    type="number"
                                    value={reallocationForm.valor}
                                    onChange={e => setReallocationForm({...reallocationForm, valor: Number(e.target.value)})}
                                    className="w-full pl-10 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Justificativa</label>
                            <textarea
                                value={reallocationForm.justificativa}
                                onChange={e => setReallocationForm({...reallocationForm, justificativa: e.target.value})}
                                className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-medium text-slate-600 h-24 resize-none"
                                placeholder="Motivo do remanejamento..."
                                required
                            />
                        </div>
                        <button
                            type="submit"
                            className="w-full bg-slate-900 text-white py-3 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
                        >
                            Confirmar Transferência
                        </button>
                    </form>
                </div>

                {/* Histórico */}
                <div className="bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm h-full max-h-[500px] overflow-y-auto">
                    <h3 className="text-xl font-black text-slate-800 mb-6">Histórico de Movimentações</h3>
                    <div className="space-y-4">
                        {reallocations.map(realloc => (
                            <div key={realloc.id} className="p-4 rounded-2xl bg-slate-50 border border-slate-100 flex items-start gap-4">
                                <div className="mt-1 w-8 h-8 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
                                </div>
                                <div className="flex-1">
                                    <div className="flex justify-between items-start">
                                        <p className="text-sm font-bold text-slate-700">
                                            {realloc.origem} <span className="text-slate-400">➔</span> {realloc.destino}
                                        </p>
                                        <span className="text-xs font-black text-slate-400">
                                            {new Date(realloc.data).toLocaleDateString('pt-BR')}
                                        </span>
                                    </div>
                                    <p className="text-lg font-black text-indigo-600 mt-1">
                                        {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(realloc.valor)}
                                    </p>
                                    <p className="text-xs text-slate-500 mt-2 font-medium italic">"{realloc.justificativa}"</p>
                                </div>
                            </div>
                        ))}
                        {reallocations.length === 0 && (
                            <p className="text-center text-slate-400 text-sm italic py-8">Nenhuma movimentação registrada.</p>
                        )}
                    </div>
                </div>
           </div>

           {/* 5. Simulador de Sustentabilidade (Bolsas) */}
           <div className="bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm">
                <h3 className="text-xl font-black text-slate-800 mb-6">Simulador de Sustentabilidade (Bolsas)</h3>
                <BurnRateSimulator
                    availableBalance={balances.bolsas}
                    totalBudget={totalAllocated.bolsas}
                    activeLinks={activeLinks}
                    scholarshipTypes={scholarshipTypes}
                />
           </div>

        </div>
    );
};
