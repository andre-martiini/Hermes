import React, { useState, useRef } from 'react';
import { FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill } from './types';
import { storage } from './firebase';
import { ref, uploadBytes, getDownloadURL } from 'firebase/storage';

interface FinanceViewProps {
    transactions: FinanceTransaction[];
    goals: FinanceGoal[];
    settings: FinanceSettings;
    currentMonthTotal: number;
    fixedBills: FixedBill[];
    onUpdateSettings: (settings: FinanceSettings) => void;
    onAddGoal: (goal: Omit<FinanceGoal, 'id'>) => void;
    onUpdateGoal: (goal: FinanceGoal) => void;
    onAddBill: (bill: Omit<FixedBill, 'id'>) => Promise<void>;
    onUpdateBill: (bill: FixedBill) => Promise<void>;
    onDeleteBill: (id: string) => Promise<void>;
}

const FinanceView = ({
    transactions,
    goals,
    settings,
    currentMonthTotal,
    fixedBills = [],
    onUpdateSettings,
    onAddGoal,
    onUpdateGoal,
    onAddBill,
    onUpdateBill,
    onDeleteBill
}: FinanceViewProps) => {
    const [activeTab, setActiveTab] = useState<'dashboard' | 'fixed'>('dashboard');
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);

    // Goals State
    const [newGoalName, setNewGoalName] = useState('');
    const [newGoalTarget, setNewGoalTarget] = useState('');

    // Fixed Bills State
    const [isAddingBill, setIsAddingBill] = useState(false);
    const [newBill, setNewBill] = useState<Partial<FixedBill>>({ category: 'Conta Fixa' });
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const today = new Date();
    const currentDay = today.getDate();
    const currentSprint = currentDay < 8 ? 1 : currentDay < 15 ? 2 : currentDay < 22 ? 3 : 4;
    const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    const monthProgress = (currentDay / daysInMonth) * 100;

    const getSprintStatus = () => {
        const budgetPerSprint = settings.monthlyBudget / 4;
        const expectedSpend = budgetPerSprint * currentSprint;

        if (currentMonthTotal < expectedSpend * 0.9) return 'bg-emerald-500';
        if (currentMonthTotal <= expectedSpend) return 'bg-yellow-500';
        return 'bg-rose-500';
    };

    const getBudgetColor = (percentage: number) => {
        if (percentage < monthProgress) return 'bg-emerald-500';
        if (percentage < monthProgress + 5) return 'bg-yellow-500';
        return 'bg-rose-500';
    };

    const budgetPercentage = Math.min((currentMonthTotal / settings.monthlyBudget) * 100, 100);

    const activeGoal = goals.find(g => g.status === 'active') || goals[0];
    const queuedGoals = goals.filter(g => g.id !== activeGoal?.id).sort((a, b) => a.priority - b.priority);

    const handleFileUpload = async (file: File) => {
        if (!file) return null;
        setUploading(true);
        try {
            const storageRef = ref(storage, `bills/${Date.now()}_${file.name}`);
            const snapshot = await uploadBytes(storageRef, file);
            const url = await getDownloadURL(snapshot.ref);
            return url;
        } catch (error) {
            console.error("Upload failed", error);
            return null;
        } finally {
            setUploading(false);
        }
    };

    const handleSaveBill = async () => {
        if (!newBill.description || !newBill.amount || !newBill.dueDay) return;

        const billData: Omit<FixedBill, 'id'> = {
            description: newBill.description,
            amount: Number(newBill.amount),
            dueDay: Number(newBill.dueDay),
            barcode: newBill.barcode || '',
            pixCode: newBill.pixCode || '',
            category: newBill.category || 'Conta Fixa',
            isPaid: false,
            attachmentUrl: newBill.attachmentUrl
        };

        await onAddBill(billData);
        setIsAddingBill(false);
        setNewBill({ category: 'Conta Fixa' });
    };

    const swapGoals = (indexA: number, indexB: number) => {
        if (indexA < 0 || indexB < 0 || indexA >= queuedGoals.length || indexB >= queuedGoals.length) return;

        const goalA = queuedGoals[indexA];
        const goalB = queuedGoals[indexB];

        // Swap priority
        const tempPriority = goalA.priority;
        onUpdateGoal({ ...goalA, priority: goalB.priority });
        onUpdateGoal({ ...goalB, priority: tempPriority });
    };

    return (
        <div className="animate-in space-y-8 pb-32">
            {/* Header & Tabs */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div>
                    <h3 className="text-3xl font-black text-slate-900 tracking-tighter">Financeiro</h3>
                    <div className="flex gap-4 mt-2">
                        <button
                            onClick={() => setActiveTab('dashboard')}
                            className={`text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full transition-all ${activeTab === 'dashboard' ? 'bg-slate-900 text-white' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            Visão Geral
                        </button>
                        <button
                            onClick={() => setActiveTab('fixed')}
                            className={`text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full transition-all ${activeTab === 'fixed' ? 'bg-slate-900 text-white' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            Contas Fixas & Poupança
                        </button>
                    </div>
                </div>
                <button
                    onClick={() => setIsSettingsOpen(!isSettingsOpen)}
                    className="bg-white border border-slate-200 text-slate-500 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-50 transition-all flex items-center gap-2"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                    Configurações
                </button>
            </div>

            {isSettingsOpen && (
                <div className="bg-slate-900 text-white p-6 rounded-[2rem] shadow-xl animate-in slide-in-from-top-4">
                    <h4 className="text-sm font-black uppercase tracking-widest mb-4">Definir Orçamento Mensal</h4>
                    <div className="flex gap-4">
                        <input
                            type="number"
                            defaultValue={settings.monthlyBudget}
                            onBlur={(e) => onUpdateSettings({ ...settings, monthlyBudget: Number(e.target.value) })}
                            className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-white font-bold outline-none focus:ring-2 focus:ring-blue-500 w-full md:w-64"
                        />
                    </div>
                </div>
            )}

            {/* DASHBOARD VIEW */}
            {activeTab === 'dashboard' && (
                <>
                    {/* Budget Bar Section */}
                    <div className="bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-xl relative overflow-hidden">
                        <div className="flex justify-between items-end mb-6">
                            <div>
                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-1">Gasto Acumulado</h4>
                                <div className="text-4xl md:text-5xl font-black text-slate-900 tracking-tighter">
                                    R$ {currentMonthTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                    <span className="text-slate-300 text-xl md:text-2xl ml-2">/ {settings.monthlyBudget.toLocaleString('pt-BR')}</span>
                                </div>
                            </div>
                            <div className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest text-white ${getSprintStatus()}`}>
                                Sprint {currentSprint}
                            </div>
                        </div>

                        <div className="relative h-6 bg-slate-100 rounded-full overflow-hidden shadow-inner">
                            <div className="absolute top-0 bottom-0 left-[25%] w-0.5 bg-white/50 z-10 flex flex-col justify-end"><span className="text-[8px] font-bold text-slate-400 -ml-1">25%</span></div>
                            <div className="absolute top-0 bottom-0 left-[50%] w-0.5 bg-white/50 z-10 flex flex-col justify-end"><span className="text-[8px] font-bold text-slate-400 -ml-1">50%</span></div>
                            <div className="absolute top-0 bottom-0 left-[75%] w-0.5 bg-white/50 z-10 flex flex-col justify-end"><span className="text-[8px] font-bold text-slate-400 -ml-1">75%</span></div>

                            <div
                                className={`h-full transition-all duration-1000 ${getBudgetColor(budgetPercentage)}`}
                                style={{ width: `${budgetPercentage}%` }}
                            >
                                <div className="absolute right-2 top-1/2 -translate-y-1/2 text-[9px] font-black text-white/90">{budgetPercentage.toFixed(1)}%</div>
                            </div>
                        </div>

                        <div className="mt-4 flex justify-between text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                            <span>01/Mês</span>
                            <span>Fim do Mês</span>
                        </div>
                    </div>

                    {/* Waterfall Goals */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                        <div className="space-y-6">
                            <div className="flex items-center justify-between">
                                <h4 className="text-xl font-black text-slate-800 tracking-tight flex items-center gap-2">
                                    <svg className="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                    Metas em Cascata
                                </h4>
                                <button onClick={() => {/* Toggle form logic handled below */ }} className="text-[10px] font-black text-blue-600 uppercase tracking-widest hover:underline">+ Nova Meta</button>
                            </div>

                            {activeGoal ? (
                                <div className="bg-white p-6 rounded-[2rem] border-2 border-slate-900 shadow-lg relative overflow-hidden group">
                                    <div className="absolute top-0 right-0 bg-slate-900 text-white text-[9px] font-black px-3 py-1 rounded-bl-xl uppercase tracking-widest">Ativa / Prioridade {activeGoal.priority}</div>
                                    <div className="mt-2">
                                        <h5 className="text-lg font-black text-slate-900">{activeGoal.name}</h5>
                                        <div className="flex items-end gap-2 mt-1">
                                            <span className="text-2xl font-bold text-emerald-600">R$ {activeGoal.currentAmount.toLocaleString('pt-BR')}</span>
                                            <span className="text-sm font-bold text-slate-400 mb-1">/ {activeGoal.targetAmount.toLocaleString('pt-BR')}</span>
                                        </div>
                                    </div>
                                    <div className="mt-4 h-3 bg-slate-100 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-slate-900 rounded-full transition-all duration-1000"
                                            style={{ width: `${Math.min((activeGoal.currentAmount / activeGoal.targetAmount) * 100, 100)}%` }}
                                        ></div>
                                    </div>
                                </div>
                            ) : (
                                <div className="p-8 border-2 border-dashed border-slate-200 rounded-[2rem] text-center">
                                    <p className="text-slate-400 font-bold">Nenhuma meta ativa definida.</p>
                                </div>
                            )}

                            {queuedGoals.length > 0 && (
                                <div className="space-y-3">
                                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-2">Na Fila (Reordenar)</p>
                                    {queuedGoals.map((goal, idx) => (
                                        <div key={goal.id} className="bg-white p-4 rounded-2xl border border-slate-200 flex justify-between items-center opacity-70 hover:opacity-100 transition-opacity">
                                            <div>
                                                <div className="font-bold text-slate-700">{goal.name}</div>
                                                <div className="text-xs font-black text-slate-400">R$ {goal.targetAmount.toLocaleString('pt-BR')}</div>
                                            </div>
                                            <div className="flex flex-col gap-1">
                                                <button
                                                    onClick={() => swapGoals(idx, idx - 1)}
                                                    disabled={idx === 0}
                                                    className="p-1 rounded bg-slate-100 hover:bg-slate-200 disabled:opacity-30"
                                                >
                                                    <svg className="w-3 h-3 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 15l7-7 7 7" /></svg>
                                                </button>
                                                <button
                                                    onClick={() => swapGoals(idx, idx + 1)}
                                                    disabled={idx === queuedGoals.length - 1}
                                                    className="p-1 rounded bg-slate-100 hover:bg-slate-200 disabled:opacity-30"
                                                >
                                                    <svg className="w-3 h-3 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Add Goal Form */}
                            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200">
                                <div className="flex gap-2 mb-2">
                                    <input
                                        type="text"
                                        placeholder="Nome da Meta"
                                        value={newGoalName}
                                        onChange={(e) => setNewGoalName(e.target.value)}
                                        className="flex-1 text-sm bg-white border border-slate-200 rounded-xl px-3 py-2"
                                    />
                                    <input
                                        type="number"
                                        placeholder="Alvo (R$)"
                                        value={newGoalTarget}
                                        onChange={(e) => setNewGoalTarget(e.target.value)}
                                        className="w-24 text-sm bg-white border border-slate-200 rounded-xl px-3 py-2"
                                    />
                                </div>
                                <button
                                    onClick={() => {
                                        if (newGoalName && newGoalTarget) {
                                            onAddGoal({
                                                name: newGoalName,
                                                targetAmount: Number(newGoalTarget),
                                                currentAmount: 0,
                                                priority: goals.length + 1,
                                                status: goals.length === 0 ? 'active' : 'queued'
                                            });
                                            setNewGoalName('');
                                            setNewGoalTarget('');
                                        }
                                    }}
                                    className="w-full bg-slate-900 text-white text-[10px] font-black uppercase py-2 rounded-xl hover:bg-slate-800"
                                >
                                    Adicionar Fila
                                </button>
                            </div>
                        </div>

                        {/* Transactions/Activity Feed */}
                        <div className="bg-white p-6 rounded-[2rem] border border-slate-200 shadow-lg h-fit">
                            <h4 className="text-sm font-black text-slate-900 uppercase tracking-widest mb-4">Últimas Transações</h4>
                            <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 scrollbar-thin">
                                {transactions.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()).map(t => (
                                    <div key={t.id} className="flex justify-between items-center p-3 hover:bg-slate-50 rounded-xl transition-colors border-b border-slate-50 last:border-0">
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center text-blue-600 font-bold text-xs">
                                                {new Date(t.date).getDate()}
                                            </div>
                                            <div>
                                                <div className="text-xs font-black text-slate-800 uppercase">{t.description || 'Gasto Semanal'}</div>
                                                <div className="text-[9px] text-slate-400 font-bold uppercase tracking-wider">{new Date(t.date).toLocaleDateString('pt-BR')} • Sprint {t.sprint}</div>
                                            </div>
                                        </div>
                                        <div className="font-mono font-bold text-slate-900">
                                            - R$ {t.amount.toLocaleString('pt-BR')}
                                        </div>
                                    </div>
                                ))}
                                {transactions.length === 0 && (
                                    <div className="text-center py-10">
                                        <p className="text-slate-300 font-black text-xs uppercase tracking-widest">Nenhum gasto registrado este mês</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </>
            )}

            {/* FIXED BILLS & SAVINGS VIEW */}
            {activeTab === 'fixed' && (
                <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4">
                    <div className="flex justify-between items-center">
                        <div>
                            <h4 className="text-xl font-black text-slate-800 tracking-tight">Obrigações Mensais e Poupança</h4>
                            <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">Gerenciamento de contas fixas e aportes</p>
                        </div>
                        <button onClick={() => setIsAddingBill(true)} className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg hover:shadow-blue-500/20">
                            + Novo Item
                        </button>
                    </div>

                    {/* Form de Adição */}
                    {isAddingBill && (
                        <div className="bg-white p-6 rounded-[2rem] border border-slate-200 shadow-xl space-y-4">
                            <h5 className="text-sm font-black text-slate-900 uppercase tracking-widest">Adicionar Nova Conta/Aporte</h5>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <input type="text" placeholder="Descrição (ex: Aluguel, Poupança)" className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.description || ''} onChange={(e) => setNewBill({ ...newBill, description: e.target.value })} />
                                <div className="flex gap-2">
                                    <span className="px-4 py-3 bg-slate-100 rounded-xl font-bold text-slate-500">R$</span>
                                    <input type="number" placeholder="Valor" className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.amount || ''} onChange={(e) => setNewBill({ ...newBill, amount: Number(e.target.value) })} />
                                </div>
                                <select className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.category} onChange={(e) => setNewBill({ ...newBill, category: e.target.value })}>
                                    <option value="Conta Fixa">Conta Fixa</option>
                                    <option value="Poupança">Poupança</option>
                                    <option value="Investimento">Investimento</option>
                                </select>
                                <input type="number" placeholder="Dia de Vencimento" max={31} min={1} className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.dueDay || ''} onChange={(e) => setNewBill({ ...newBill, dueDay: Number(e.target.value) })} />
                                <input type="text" placeholder="Linha Digitável (Código de Barras)" className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.barcode || ''} onChange={(e) => setNewBill({ ...newBill, barcode: e.target.value })} />
                                <input type="text" placeholder="Código Pix (Copia e Cola)" className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.pixCode || ''} onChange={(e) => setNewBill({ ...newBill, pixCode: e.target.value })} />
                            </div>

                            {/* File Upload */}
                            <div className="border-2 border-dashed border-slate-200 rounded-xl p-4 flex flex-col items-center justify-center bg-slate-50 cursor-pointer hover:bg-slate-100 transition-colors" onClick={() => fileInputRef.current?.click()}>
                                <input type="file" ref={fileInputRef} className="hidden" accept="image/*,.pdf" onChange={async (e) => {
                                    if (e.target.files?.[0]) {
                                        const url = await handleFileUpload(e.target.files[0]);
                                        if (url) setNewBill({ ...newBill, attachmentUrl: url });
                                    }
                                }} />
                                {uploading ? (
                                    <p className="text-sm font-bold text-blue-500 animate-pulse">Enviando arquivo...</p>
                                ) : newBill.attachmentUrl ? (
                                    <div className="flex items-center gap-2 text-emerald-600 font-bold text-sm">
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                                        Arquivo Anexado
                                    </div>
                                ) : (
                                    <div className="text-center text-slate-400">
                                        <svg className="w-6 h-6 mx-auto mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                                        <p className="text-xs font-bold uppercase">Clique para anexar Boleto/QR Code</p>
                                    </div>
                                )}
                            </div>

                            <div className="flex justify-end gap-3 pt-4">
                                <button onClick={() => setIsAddingBill(false)} className="px-6 py-2 rounded-xl text-xs font-black uppercase tracking-widest text-slate-500 hover:bg-slate-100">Cancelar</button>
                                <button onClick={handleSaveBill} disabled={uploading} className="bg-slate-900 text-white px-8 py-2 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 disabled:opacity-50">
                                    Salvar Item
                                </button>
                            </div>
                        </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {fixedBills.map(bill => (
                            <div key={bill.id} className={`bg-white p-6 rounded-[2rem] border-2 shadow-sm relative group hover:shadow-xl transition-all ${bill.isPaid ? 'border-emerald-100 opacity-60' : 'border-slate-100'}`}>
                                <div className="absolute top-4 right-4 checkbox-wrapper">
                                    <input type="checkbox" checked={bill.isPaid} onChange={() => onUpdateBill({ ...bill, isPaid: !bill.isPaid })} className="w-5 h-5 rounded-lg border-slate-300 text-emerald-500 focus:ring-emerald-500 cursor-pointer" />
                                </div>
                                <div className={`text-[10px] font-black uppercase tracking-widest mb-2 px-3 py-1 rounded-full w-fit ${bill.category === 'Poupança' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>{bill.category || 'Conta Fixa'}</div>
                                <h5 className="text-lg font-black text-slate-900 leading-tight">{bill.description}</h5>
                                <div className="text-3xl font-black text-slate-800 mt-2 tracking-tighter">R$ {bill.amount.toLocaleString('pt-BR')}</div>
                                <div className="flex items-center gap-2 mt-4 text-xs font-bold text-slate-500">
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                                    Vence dia {bill.dueDay}
                                </div>

                                {/* Actions */}
                                <div className="mt-6 flex gap-2">
                                    {bill.barcode && (
                                        <button onClick={() => navigator.clipboard.writeText(bill.barcode || '')} className="flex-1 bg-slate-50 hover:bg-slate-100 text-slate-600 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center justify-center gap-2">
                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                                            Copiar Cód.
                                        </button>
                                    )}
                                    {bill.attachmentUrl && (
                                        <a href={bill.attachmentUrl} target="_blank" rel="noopener noreferrer" className="flex-1 bg-blue-50 hover:bg-blue-100 text-blue-600 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center justify-center gap-2">
                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                                            Ver Anexo
                                        </a>
                                    )}
                                </div>
                                <button onClick={() => onDeleteBill(bill.id)} className="absolute top-4 right-0 mt-8 mr-4 opacity-0 group-hover:opacity-100 transition-opacity text-rose-400 hover:text-rose-600">
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                </button>
                            </div>
                        ))}
                        {fixedBills.length === 0 && (
                            <div className="col-span-full py-12 text-center border-2 border-dashed border-slate-200 rounded-[2rem]">
                                <p className="text-slate-400 font-bold uppercase tracking-widest">Nenhuma conta cadastrada</p>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default FinanceView;
