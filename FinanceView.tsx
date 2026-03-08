import React, { useState, useRef } from 'react';
import { FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill, BillRubric, IncomeEntry, IncomeRubric } from './types';
import { storage, db } from './firebase';
import { ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { doc, setDoc } from 'firebase/firestore';
import { resolveTwoStepAction } from './src/utils/destructiveActions';
import { NFSeGenerator } from './src/components/NFSeGenerator';
interface FinanceViewProps {
    transactions: FinanceTransaction[];
    goals: FinanceGoal[];
    emergencyReserve: { target: number; current: number };
    settings: FinanceSettings;
    currentMonthTotal: number;
    currentMonthIncome: number;
    fixedBills: FixedBill[];
    onUpdateSettings: (settings: FinanceSettings) => void;
    onAddGoal: (goal: Omit<FinanceGoal, 'id'>) => void;
    onUpdateGoal: (goal: FinanceGoal) => void;
    onDeleteGoal: (id: string) => void;
    onReorderGoals: (goals: FinanceGoal[]) => void;
    currentMonth: number;
    currentYear: number;
    onMonthChange: (month: number, year: number) => void;
    billRubrics: BillRubric[];
    onAddRubric: (rubric: Omit<BillRubric, 'id'>) => Promise<void>;
    onUpdateRubric: (rubric: BillRubric) => void;
    onDeleteRubric: (id: string) => void;
    incomeEntries: IncomeEntry[];
    incomeRubrics: IncomeRubric[];
    onAddIncomeRubric: (rubric: Omit<IncomeRubric, 'id'>) => Promise<void>;
    onUpdateIncomeRubric: (rubric: IncomeRubric) => void;
    onDeleteIncomeRubric: (id: string) => void;
    onAddIncomeEntry: (entry: Omit<IncomeEntry, 'id'>) => Promise<void>;
    onUpdateIncomeEntry: (entry: IncomeEntry) => void;
    onDeleteIncomeEntry: (id: string) => void;
    onAddBill: (bill: Omit<FixedBill, 'id'>) => Promise<void>;
    onUpdateBill: (bill: FixedBill) => Promise<void>;
    onDeleteBill: (id: string) => Promise<void>;
    onAddTransaction: (transaction: Omit<FinanceTransaction, 'id'>) => Promise<void>;
    onUpdateTransaction: (transaction: FinanceTransaction) => Promise<void>;
    onDeleteTransaction: (id: string) => Promise<void>;
    activeTab: 'dashboard' | 'fixed';
    setActiveTab: (tab: 'dashboard' | 'fixed') => void;
    isSettingsOpen: boolean;
    setIsSettingsOpen: (isOpen: boolean) => void;
}

const FinanceSection = ({ title, children, defaultExpanded = true }: { title: string, children: React.ReactNode, defaultExpanded?: boolean }) => {
    const [isExpanded, setIsExpanded] = useState(defaultExpanded);

    return (
        <div className="bg-white p-6 md:p-8 rounded-none md:rounded-[2rem] border-b md:border border-slate-200 shadow-none md:shadow-lg">
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full flex items-center justify-between group"
            >
                <h4 className="text-lg font-black text-slate-900">{title}</h4>
                <svg className={`w-5 h-5 text-slate-300 group-hover:text-slate-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {isExpanded && (
                <div className="mt-6 animate-in slide-in-from-top-2 duration-300">
                    {children}
                </div>
            )}
        </div>
    );
};

const FinanceView = ({
    transactions,
    goals,
    emergencyReserve,
    settings,
    currentMonthTotal,
    currentMonthIncome = 0,
    fixedBills = [],
    onUpdateSettings,
    onAddGoal,
    onUpdateGoal,
    onDeleteGoal,
    onReorderGoals,
    currentMonth,
    currentYear,
    onMonthChange,
    billRubrics = [],
    onAddRubric,
    onUpdateRubric,
    onDeleteRubric,
    incomeEntries = [],
    incomeRubrics = [],
    onAddIncomeRubric,
    onUpdateIncomeRubric,
    onDeleteIncomeRubric,
    onAddIncomeEntry,
    onUpdateIncomeEntry,
    onDeleteIncomeEntry,
    onAddBill,
    onUpdateBill,
    onDeleteBill,
    onAddTransaction,
    onUpdateTransaction,
    onDeleteTransaction,
    activeTab,
    setActiveTab,
    isSettingsOpen,
    setIsSettingsOpen
}: FinanceViewProps) => {

    // Transaction States
    const [isAddingTransaction, setIsAddingTransaction] = useState(false);
    const [editingTransaction, setEditingTransaction] = useState<FinanceTransaction | null>(null);
    const [newTransaction, setNewTransaction] = useState<Partial<FinanceTransaction>>({});

    // Goals State
    // Goals State
    const [newGoalName, setNewGoalName] = useState('');
    const [newGoalTarget, setNewGoalTarget] = useState('');
    const [editingGoal, setEditingGoal] = useState<FinanceGoal | null>(null);
    const [isEmergencyReserveOpen, setIsEmergencyReserveOpen] = useState(false);
    const [isManagingRubrics, setIsManagingRubrics] = useState(false);
    const [editingRubric, setEditingRubric] = useState<BillRubric | null>(null);
    const [newRubric, setNewRubric] = useState<Partial<BillRubric>>({ category: 'Conta Fixa' });

    // Income States
    const [isManagingIncomeRubrics, setIsManagingIncomeRubrics] = useState(false);
    const [editingIncomeRubric, setEditingIncomeRubric] = useState<IncomeRubric | null>(null);
    const [newIncomeRubric, setNewIncomeRubric] = useState<Partial<IncomeRubric>>({ category: 'Renda Principal' });
    const [isAddingIncome, setIsAddingIncome] = useState(false);
    const [newIncome, setNewIncome] = useState<Partial<IncomeEntry>>({ category: 'Renda Principal' });

    // Category States for Settings
    const [newBillCategoryInput, setNewBillCategoryInput] = useState('');
    const [newIncomeCategoryInput, setNewIncomeCategoryInput] = useState('');

    // Fixed Bills State
    const [isAddingBill, setIsAddingBill] = useState(false);
    const [newBill, setNewBill] = useState<Partial<FixedBill>>({ category: 'Conta Fixa' });
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [editingAmountId, setEditingAmountId] = useState<string | null>(null);
    const [tempAmount, setTempAmount] = useState<string>('');
    const [pendingDeleteKey, setPendingDeleteKey] = useState<string | null>(null);
    const [expandedBillId, setExpandedBillId] = useState<string | null>(null);
    const [activeBillTabs, setActiveBillTabs] = useState<Record<string, 'codigo' | 'arquivo'>>({});
    
    // NFSe Generator State
    const [isNFSeGeneratorOpen, setIsNFSeGeneratorOpen] = useState(false);

    const handleTwoStepDelete = (key: string, action: () => void | Promise<void>) => {
        const decision = resolveTwoStepAction(pendingDeleteKey, key);
        if (!decision.confirmed) {
            setPendingDeleteKey(decision.pendingKey);
            window.setTimeout(() => setPendingDeleteKey((current) => (current === key ? null : current)), 3500);
            return;
        }
        setPendingDeleteKey(decision.pendingKey);
        void action();
    };

    const today = new Date();
    const isCurrentMonth = today.getMonth() === currentMonth && today.getFullYear() === currentYear;
    const currentDay = isCurrentMonth ? today.getDate() : 31;
    const currentSprint = currentDay < 8 ? 1 : currentDay < 15 ? 2 : currentDay < 22 ? 3 : 4;
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    const monthProgress = isCurrentMonth ? (currentDay / daysInMonth) * 100 : 100;

    const getSprintStatus = () => {
        const budgetPerSprint = currentBudget / 4;
        const expectedSpend = budgetPerSprint * currentSprint;

        if (currentMonthTotal < expectedSpend * 0.9) return 'bg-emerald-500';
        if (currentMonthTotal <= expectedSpend) return 'bg-yellow-500';
        return 'bg-rose-500';
    };

    const getBudgetColor = (percentage: number) => {
        if (!isCurrentMonth) return percentage >= 100 ? 'bg-rose-500' : 'bg-emerald-500';
        if (percentage < monthProgress) return 'bg-emerald-500';
        if (percentage < monthProgress + 5) return 'bg-yellow-500';
        return 'bg-rose-500';
    };

    const periodKey = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
    const currentBudget = settings.monthlyBudgets?.[periodKey] || settings.monthlyBudget;
    const budgetPercentage = Math.min((currentMonthTotal / currentBudget) * 100, 100);

    const sortedGoals = [...goals].sort((a, b) => a.priority - b.priority);

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

    const isAddingGoalVisible = activeTab === 'dashboard';

    // Helper to get previous month data
    const getPrevMonthData = () => {
        const prevMonth = currentMonth === 0 ? 11 : currentMonth - 1;
        const prevYear = currentMonth === 0 ? currentYear - 1 : currentYear;

        const prevIncome = incomeEntries
            .filter(e => e.month === prevMonth && e.year === prevYear)
            .reduce((acc, curr) => acc + curr.amount, 0);

        const prevBills = fixedBills
            .filter(b => b.month === prevMonth && b.year === prevYear)
            .reduce((acc, curr) => acc + curr.amount, 0);

        return { prevIncome, prevBills };
    };

    const { prevIncome, prevBills } = getPrevMonthData();
    const currentTotalBills = fixedBills
        .filter(b => b.month === currentMonth && b.year === currentYear)
        .reduce((acc, curr) => acc + curr.amount, 0);

    const getHealthStatus = () => {
        if (currentMonthIncome === 0) return { label: 'Aguardando Renda', color: 'text-slate-400', icon: '⏳' };
        const ratio = currentTotalBills / currentMonthIncome;
        if (ratio < 0.4) return { label: 'Saúde Excelente', color: 'text-emerald-500', icon: '✨' };
        if (ratio < 0.7) return { label: 'Saúde Estável', color: 'text-blue-500', icon: '✅' };
        if (ratio < 0.9) return { label: 'Atenção Necessária', color: 'text-amber-500', icon: '⚠️' };
        return { label: 'Risco Financeiro', color: 'text-rose-500', icon: '🚨' };
    };

    const health = getHealthStatus();

    const handleSaveBill = async () => {
        if (!newBill.description || !newBill.amount) return;

        const billData: Omit<FixedBill, 'id'> = {
            description: newBill.description,
            amount: Number(newBill.amount),
            dueDay: newBill.dueDay ? Number(newBill.dueDay) : new Date().getDate(),
            month: currentMonth,
            year: currentYear,
            barcode: newBill.barcode || '',
            pixCode: newBill.pixCode || '',
            category: newBill.category || (settings.billCategories?.[0] || 'Conta Fixa'),
            isPaid: false,
            attachmentUrl: newBill.attachmentUrl || '',
            pixQrCodeUrl: newBill.pixQrCodeUrl || '',
            rubricId: newBill.rubricId || ''
        };

        await onAddBill(billData);
        setIsAddingBill(false);
        setNewBill({ category: 'Conta Fixa' });
    };

    const swapGoals = (indexA: number, indexB: number) => {
        if (indexA < 0 || indexB < 0 || indexA >= sortedGoals.length || indexB >= sortedGoals.length) return;

        const newGoals = [...sortedGoals];
        const temp = newGoals[indexA];
        newGoals[indexA] = newGoals[indexB];
        newGoals[indexB] = temp;

        onReorderGoals(newGoals);
    };

    return (
        <div className="animate-in space-y-0 md:space-y-8 pb-32 pt-10">
            {/* Header & Tabs removidos - agora no Header global */}

            {isSettingsOpen && (
                <div className="bg-slate-900 text-white p-6 rounded-none md:rounded-[2rem] shadow-none md:shadow-xl animate-in slide-in-from-top-4 space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                            <h4 className="text-sm font-black uppercase tracking-widest mb-4 text-white/60">Orçamento de {new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}</h4>
                            <div className="flex gap-4">
                                <input
                                    type="number"
                                    defaultValue={settings.monthlyBudgets?.[periodKey] || settings.monthlyBudget}
                                    onBlur={(e) => onUpdateSettings({
                                        ...settings,
                                        monthlyBudgets: {
                                            ...(settings.monthlyBudgets || {}),
                                            [periodKey]: Number(e.target.value)
                                        }
                                    })}
                                    className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-4 py-2 text-white font-bold outline-none focus:ring-2 focus:ring-emerald-500 w-full"
                                />
                            </div>
                            <p className="text-[9px] text-white/40 uppercase mt-2 font-bold italic tracking-widest">Este valor se aplica apenas ao período selecionado.</p>
                        </div>
                        <div>
                            <h4 className="text-sm font-black uppercase tracking-widest mb-4 text-white/60">Orçamento Geral (Padrão)</h4>
                            <div className="flex gap-4">
                                <input
                                    type="number"
                                    defaultValue={settings.monthlyBudget}
                                    onBlur={(e) => onUpdateSettings({ ...settings, monthlyBudget: Number(e.target.value) })}
                                    className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-white font-bold outline-none focus:ring-2 focus:ring-blue-500 w-full"
                                />
                            </div>
                            <p className="text-[9px] text-white/40 uppercase mt-2 font-bold italic tracking-widest">Valor base para novos meses.</p>
                        </div>
                    </div>
                    <div>
                        <h4 className="text-sm font-black uppercase tracking-widest mb-4 text-white/60">Reserva de Emergência Alvo</h4>
                        <div className="flex gap-4">
                            <input
                                type="number"
                                defaultValue={settings.emergencyReserveTarget}
                                onBlur={(e) => onUpdateSettings({ ...settings, emergencyReserveTarget: Number(e.target.value) })}
                                className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-white font-bold outline-none focus:ring-2 focus:ring-emerald-500 w-full md:w-64"
                            />
                        </div>
                    </div>
                    <div>
                        <h4 className="text-sm font-black uppercase tracking-widest mb-4 text-white/60">Reserva de Emergência Atual (Manual)</h4>
                        <div className="flex gap-4">
                            <input
                                type="number"
                                defaultValue={settings.emergencyReserveCurrent}
                                onBlur={(e) => onUpdateSettings({ ...settings, emergencyReserveCurrent: Number(e.target.value) })}
                                className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-white font-bold outline-none focus:ring-2 focus:ring-emerald-500 w-full md:w-64"
                            />
                        </div>
                    </div>

                    {/* Configuração de Gastos Externos */}
                    <div className="pt-4 border-t border-white/5">
                        <h4 className="text-sm font-black uppercase tracking-widest mb-4 text-white/60 text-purple-400">Portal de Gastos Externos</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <label className="text-[10px] font-black text-white/40 uppercase tracking-widest block mb-2">Limite de Gastos Externo</label>
                                <input
                                    type="number"
                                    defaultValue={settings.externalSpendingLimit || 0}
                                    onBlur={async (e) => {
                                        const newVal = Number(e.target.value);
                                        const newSettings = { ...settings, externalSpendingLimit: newVal };
                                        onUpdateSettings(newSettings);
                                        // Sync public doc
                                        await setDoc(doc(db, 'public_configs', 'finance_portal'), {
                                            limit: newVal,
                                            token: settings.externalToken
                                        }, { merge: true });
                                    }}
                                    className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-white font-bold outline-none focus:ring-2 focus:ring-purple-500 w-full"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-white/40 uppercase tracking-widest block mb-2">Token de Acesso</label>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={settings.externalToken || ''}
                                        readOnly
                                        placeholder="Gere um token"
                                        className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-white font-mono text-xs outline-none w-full"
                                    />
                                    <button
                                        onClick={async () => {
                                            const newToken = Math.random().toString(36).substring(2, 10) + Math.random().toString(36).substring(2, 10);
                                            const newSettings = { ...settings, externalToken: newToken };
                                            onUpdateSettings(newSettings);
                                            // Sync public doc
                                            await setDoc(doc(db, 'public_configs', 'finance_portal'), {
                                                limit: settings.externalSpendingLimit,
                                                token: newToken
                                            }, { merge: true });
                                        }}
                                        className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase whitespace-nowrap"
                                    >
                                        Gerar
                                    </button>
                                </div>
                            </div>
                        </div>
                        {settings.externalToken && (
                            <div className="mt-4 bg-purple-500/10 border border-purple-500/20 p-4 rounded-xl flex flex-col md:flex-row items-center justify-between gap-4">
                                <div className="text-xs font-mono text-purple-200 break-all">
                                    {window.location.origin}/gastos-externos?token={settings.externalToken}
                                </div>
                                <button
                                    onClick={() => navigator.clipboard.writeText(`${window.location.origin}/gastos-externos?token=${settings.externalToken}`)}
                                    className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase flex items-center gap-2"
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                    Copiar Link
                                </button>
                            </div>
                        )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4 border-t border-white/5">
                        {/* Gestão de Categorias de Obrigações */}
                        <div className="space-y-4">
                            <h4 className="text-sm font-black uppercase tracking-widest text-white/60 text-blue-400">Categorias de Obrigações</h4>
                            <div className="flex flex-wrap gap-2">
                                {(settings.billCategories || ['Conta Fixa', 'Poupança', 'Investimento']).map(cat => (
                                    <div key={cat} className="flex items-center gap-2 bg-white/5 border border-white/10 px-3 py-1.5 rounded-xl group">
                                        <span className="text-xs font-bold">{cat}</span>
                                        <button
                                            onClick={() => onUpdateSettings({
                                                ...settings,
                                                billCategories: (settings.billCategories || []).filter(c => c !== cat)
                                            })}
                                            className="text-white/20 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-all font-black text-xs"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                ))}
                            </div>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    placeholder="Nova Categoria"
                                    className="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-xs font-bold outline-none focus:ring-2 focus:ring-blue-500 w-full"
                                    value={newBillCategoryInput}
                                    onChange={e => setNewBillCategoryInput(e.target.value)}
                                />
                                <button
                                    onClick={() => {
                                        if (newBillCategoryInput.trim()) {
                                            onUpdateSettings({
                                                ...settings,
                                                billCategories: [...(settings.billCategories || []), newBillCategoryInput.trim()]
                                            });
                                            setNewBillCategoryInput('');
                                        }
                                    }}
                                    className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase"
                                >
                                    +
                                </button>
                            </div>
                        </div>

                        {/* Gestão de Categorias de Renda */}
                        <div className="space-y-4">
                            <h4 className="text-sm font-black uppercase tracking-widest text-white/60 text-emerald-400">Categorias de Renda</h4>
                            <div className="flex flex-wrap gap-2">
                                {(settings.incomeCategories || ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']).map(cat => (
                                    <div key={cat} className="flex items-center gap-2 bg-white/5 border border-white/10 px-3 py-1.5 rounded-xl group">
                                        <span className="text-xs font-bold">{cat}</span>
                                        <button
                                            onClick={() => onUpdateSettings({
                                                ...settings,
                                                incomeCategories: (settings.incomeCategories || []).filter(c => c !== cat)
                                            })}
                                            className="text-white/20 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-all font-black text-xs"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                ))}
                            </div>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    placeholder="Nova Fonte"
                                    className="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-xs font-bold outline-none focus:ring-2 focus:ring-emerald-500 w-full"
                                    value={newIncomeCategoryInput}
                                    onChange={e => setNewIncomeCategoryInput(e.target.value)}
                                />
                                <button
                                    onClick={() => {
                                        if (newIncomeCategoryInput.trim()) {
                                            onUpdateSettings({
                                                ...settings,
                                                incomeCategories: [...(settings.incomeCategories || []), newIncomeCategoryInput.trim()]
                                            });
                                            setNewIncomeCategoryInput('');
                                        }
                                    }}
                                    className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase"
                                >
                                    +
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* DASHBOARD VIEW */}
            {activeTab === 'dashboard' && (
                <div className="flex flex-col gap-6 md:gap-8">
                    {/* Budget Bar Section */}
                    <div className="bg-white p-6 md:p-8 rounded-none md:rounded-[2rem] border-b md:border border-slate-200 shadow-none md:shadow-xl relative overflow-hidden">
                        <div className="flex justify-between items-end mb-6">
                            <div>
                                <h4 className="text-lg font-black text-slate-900 tracking-tight mb-1">
                                    Gasto Acumulado • {new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}
                                </h4>
                                <div className="text-2xl md:text-5xl font-black text-slate-900 tracking-tighter leading-none">
                                    R$ {currentMonthTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                    <span className="text-slate-300 text-sm md:text-2xl ml-1">/ {currentBudget.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                </div>
                                <div className="flex flex-wrap gap-4 mt-2">
                                    <p className="text-slate-400 text-[9px] md:text-[10px] font-bold uppercase tracking-widest flex items-center gap-1">
                                        <span className="w-1 h-1 bg-slate-300 rounded-full"></span>
                                        Disponível: R$ {(currentBudget - currentMonthTotal).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                    </p>
                                </div>
                            </div>
                            <div className={`px-3 py-1.5 rounded-lg text-[9px] md:text-[10px] font-black uppercase tracking-widest text-white shadow-sm ${getSprintStatus()}`}>
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
                            />
                            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-black text-slate-900/40">
                                {budgetPercentage.toFixed(1)}%
                            </div>
                        </div>

                        <div className="mt-4 flex justify-between text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                            <span>01/Mês</span>
                            <span>Fim do Mês</span>
                        </div>
                    </div>

                    {/* Content Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8">
                        
                        {/* TRANSACTIONS (LEFT COLUMN) */}
                        <div className="order-2 md:order-1 h-full">
                            <FinanceSection title={`Lançamentos de ${new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}`}>
                                <div className="flex justify-end mb-4">
                                    <button
                                        onClick={() => {
                                            setNewTransaction({ date: new Date().toISOString(), sprint: 1, category: 'Alimentação' });
                                            setIsAddingTransaction(true);
                                        }}
                                        className="text-[10px] font-black text-blue-600 uppercase tracking-widest hover:underline"
                                    >
                                        + Novo
                                    </button>
                                </div>

                                {/* Form para Adicionar/Editar Transação */}
                                {(isAddingTransaction || editingTransaction) && (
                                    <div className="mb-6 p-4 bg-slate-50 rounded-lg md:rounded-2xl border border-slate-100 space-y-3">
                                        <h5 className="text-[10px] font-black uppercase text-slate-400">{editingTransaction ? 'Editar Lançamento' : 'Novo Lançamento'}</h5>
                                        <input
                                            type="text"
                                            placeholder="Descrição"
                                            className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2 text-sm font-bold"
                                            value={(editingTransaction || newTransaction).description || ''}
                                            onChange={e => editingTransaction ? setEditingTransaction({ ...editingTransaction, description: e.target.value }) : setNewTransaction({ ...newTransaction, description: e.target.value })}
                                        />
                                        <div className="grid grid-cols-2 gap-2">
                                            <input
                                                type="number"
                                                placeholder="Valor"
                                                className="bg-white border border-slate-200 rounded-xl px-4 py-2 text-sm font-bold"
                                                value={(editingTransaction || newTransaction).amount || ''}
                                                onChange={e => editingTransaction ? setEditingTransaction({ ...editingTransaction, amount: Number(e.target.value) }) : setNewTransaction({ ...newTransaction, amount: Number(e.target.value) })}
                                            />
                                            <input
                                                type="date"
                                                className="bg-white border border-slate-200 rounded-xl px-4 py-2 text-sm font-bold"
                                                value={(editingTransaction || newTransaction).date?.split('T')[0] || ''}
                                                onChange={e => {
                                                    const date = new Date(e.target.value).toISOString();
                                                    const day = new Date(e.target.value).getDate();
                                                    const sprint = day < 8 ? 1 : day < 15 ? 2 : day < 22 ? 3 : 4;
                                                    editingTransaction ? setEditingTransaction({ ...editingTransaction, date, sprint }) : setNewTransaction({ ...newTransaction, date, sprint });
                                                }}
                                            />
                                        </div>
                                        <div className="flex gap-2">
                                            <button
                                                onClick={() => { setIsAddingTransaction(false); setEditingTransaction(null); }}
                                                className="flex-1 px-4 py-2 bg-slate-200 text-slate-600 rounded-xl text-[10px] font-black uppercase"
                                            >
                                                Cancelar
                                            </button>
                                            <button
                                                onClick={async () => {
                                                    const data = (editingTransaction || newTransaction);
                                                    if (data.description && data.amount && data.date) {
                                                        if (editingTransaction) {
                                                            await onUpdateTransaction(editingTransaction);
                                                        } else {
                                                            await onAddTransaction(newTransaction as Omit<FinanceTransaction, 'id'>);
                                                        }
                                                        setIsAddingTransaction(false);
                                                        setEditingTransaction(null);
                                                        setNewTransaction({});
                                                    }
                                                }}
                                                className="flex-1 px-4 py-2 bg-slate-900 text-white rounded-xl text-[10px] font-black uppercase"
                                            >
                                                Salvar
                                            </button>
                                        </div>
                                    </div>
                                )}

                                <div className="space-y-4 max-h-[500px] overflow-y-auto pr-2 scrollbar-thin">
                                    {transactions
                                        .filter(t => {
                                            const d = new Date(t.date);
                                            return d.getMonth() === currentMonth && d.getFullYear() === currentYear;
                                        })
                                        .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
                                        .map(t => (
                                            <div key={t.id} className="group relative flex flex-col sm:flex-row sm:justify-between sm:items-center p-3 hover:bg-slate-50 rounded-xl transition-colors border-b border-slate-50 last:border-0 gap-2 sm:gap-4">
                                                <div className="flex items-center gap-3 min-w-0">
                                                    <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center text-blue-600 font-bold text-xs shrink-0">
                                                        {new Date(t.date).getUTCDate()}
                                                    </div>
                                                    <div className="min-w-0 flex-1">
                                                        <div className="text-xs font-black text-slate-800 uppercase truncate pr-8" title={t.description}>{t.description || 'Gasto Semanal'}</div>
                                                        <div className="text-[9px] text-slate-400 font-bold uppercase tracking-wider">
                                                            {new Date(t.date).toLocaleDateString('pt-BR')} • Sprint {t.sprint}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="flex items-center justify-between sm:justify-end gap-4 w-full sm:w-auto">
                                                    <div className="font-mono font-bold text-slate-900 whitespace-nowrap">
                                                        - R$ {t.amount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                                    </div>
                                                    <div className="flex sm:hidden group-hover:flex items-center gap-1">
                                                        <button onClick={() => setEditingTransaction(t)} className="p-1 text-slate-300 hover:text-blue-500 transition-colors">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                        </button>
                                                        <button onClick={() => handleTwoStepDelete(`transaction_${t.id}`, () => onDeleteTransaction(t.id))} className={`p-1 rounded-md transition-colors ${pendingDeleteKey === `transaction_${t.id}` ? 'bg-rose-500 text-white' : 'text-slate-300 hover:text-rose-500'}`}>
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    {transactions.length === 0 && (
                                        <div className="text-center py-10">
                                            <p className="text-slate-300 font-black text-xs uppercase tracking-widest">Nenhum gasto registrado este mês</p>
                                        </div>
                                    )}
                                </div>
                            </FinanceSection>
                        </div>

                        {/* EMERGENCY & GOALS (RIGHT COLUMN) */}
                        <div className="order-3 md:order-2 space-y-6">
                            {/* Emergency Reserve Section */}
                            <div className="bg-white p-6 rounded-none md:rounded-[2rem] border-b md:border border-emerald-100 shadow-none md:shadow-lg relative overflow-hidden group">
                                <div className="mt-2">
                                    <h5 className="text-lg font-black text-slate-900 flex items-center gap-2">
                                        Reserva de Emergência
                                    </h5>
                                    <div className="flex items-end gap-2 mt-1">
                                        <div className="group/edit relative flex items-center">
                                            <span className="text-2xl font-black text-emerald-600">R$ </span>
                                            <input
                                                type="number"
                                                className="text-2xl font-black text-emerald-600 bg-transparent border-none outline-none focus:ring-0 w-32 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                                defaultValue={emergencyReserve.current}
                                                onBlur={(e) => onUpdateSettings({ ...settings, emergencyReserveCurrent: Number(e.target.value) })}
                                            />
                                            <div className="opacity-0 group-hover/edit:opacity-100 transition-opacity ml-1 text-emerald-600/30">
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                            </div>
                                        </div>
                                        <span className="text-sm font-bold text-slate-400 mb-1">/ {emergencyReserve.target.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                    </div>
                                </div>
                                <div className="mt-4 h-3 bg-slate-100 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-emerald-500 rounded-full transition-all duration-1000"
                                        style={{ width: `${Math.min((emergencyReserve.current / (emergencyReserve.target || 1)) * 100, 100)}%` }}
                                    ></div>
                                </div>
                                {emergencyReserve.current < emergencyReserve.target && (
                                    <p className="mt-2 text-[9px] font-bold text-slate-400 uppercase tracking-widest italic">As metas só serão preenchidas após completar a reserva.</p>
                                )}
                            </div>

                            <div className="">
                                <FinanceSection title="Metas em Cascata">
                                    <div className="flex justify-end mb-4">
                                        <button
                                            onClick={() => {
                                                onAddGoal({
                                                    name: 'Nova Meta',
                                                    targetAmount: 0,
                                                    currentAmount: 0,
                                                    priority: -1,
                                                    status: 'active'
                                                });
                                            }}
                                            className="text-[10px] font-black text-blue-600 uppercase tracking-widest hover:underline"
                                        >
                                            + Nova Meta
                                        </button>
                                    </div>

                                    {sortedGoals.length > 0 ? (
                                        <div className="space-y-4">
                                            {sortedGoals.map((goal, idx) => (
                                                <div key={goal.id} className={`p-3 md:p-4 rounded-none md:rounded-[1.5rem] border transition-all relative group ${idx === 0 ? 'bg-gradient-to-br from-blue-50/50 to-white border-blue-600 shadow-xl ring-1 ring-blue-100' : 'bg-white border-slate-100 opacity-80 hover:opacity-100 shadow-none'}`}>
                                                    <div className="flex flex-col gap-2">
                                                        {/* Setas de reordenação: absolutas à esquerda, só no hover */}
                                                        <div className="absolute left-2 top-1/2 -translate-y-1/2 flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                                                            <button
                                                                onClick={() => swapGoals(idx, idx - 1)}
                                                                disabled={idx === 0}
                                                                className="p-0.5 rounded hover:bg-slate-100 disabled:opacity-20 transition-all"
                                                                title="Mover para cima"
                                                            >
                                                                <svg className="w-2.5 h-2.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 15l7-7 7 7" /></svg>
                                                            </button>
                                                            <button
                                                                onClick={() => swapGoals(idx, idx + 1)}
                                                                disabled={idx === sortedGoals.length - 1}
                                                                className="p-0.5 rounded hover:bg-slate-100 disabled:opacity-20 transition-all"
                                                                title="Mover para baixo"
                                                            >
                                                                <svg className="w-2.5 h-2.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                                                            </button>
                                                        </div>

                                                        {/* Badge P1 + Lixeira: absolutos à direita, só no hover */}
                                                        <div className="absolute right-3 top-3 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                                                            <div className="bg-slate-100 text-slate-500 text-[8px] font-black px-1.5 py-0.5 rounded-lg uppercase tracking-widest">{`P${idx + 1}`}</div>
                                                            <button
                                                                onClick={() => handleTwoStepDelete(`goal_${goal.id}`, () => onDeleteGoal(goal.id))}
                                                                className={`p-1.5 rounded-md transition-all ${pendingDeleteKey === `goal_${goal.id}` ? 'bg-rose-500 text-white scale-110' : 'text-slate-300 hover:text-rose-500'}`}
                                                                title={pendingDeleteKey === `goal_${goal.id}` ? 'Confirmar exclusão' : 'Excluir meta'}
                                                            >
                                                                {pendingDeleteKey === `goal_${goal.id}` ? (
                                                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                                ) : (
                                                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                                )}
                                                            </button>
                                                        </div>

                                                        {/* Conteúdo principal: textarea + valor alvo */}
                                                        <div className="w-full">
                                                            <textarea
                                                                defaultValue={goal.name}
                                                                rows={1}
                                                                className="w-full bg-transparent border-none p-0 font-black text-slate-800 text-sm outline-none focus:ring-1 focus:ring-blue-100 rounded px-1 transition-all resize-none overflow-hidden leading-snug pr-16"
                                                                onInput={(e) => {
                                                                    const el = e.currentTarget;
                                                                    el.style.height = 'auto';
                                                                    el.style.height = el.scrollHeight + 'px';
                                                                }}
                                                                onBlur={(e) => {
                                                                    if (e.target.value !== goal.name) {
                                                                        onUpdateGoal({ ...goal, name: e.target.value });
                                                                    }
                                                                }}
                                                                onClick={(e) => e.stopPropagation()}
                                                            />
                                                            <div className="flex items-baseline gap-1 mt-1">
                                                                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">R$ {goal.currentAmount.toLocaleString('pt-BR', { minimumFractionDigits: 0 })} de</span>
                                                                <input
                                                                    type="number"
                                                                    className="bg-transparent border-none p-0 text-[10px] font-black text-slate-700 w-20 outline-none focus:ring-1 focus:ring-blue-200 rounded px-1 transition-all"
                                                                    defaultValue={goal.targetAmount}
                                                                    onBlur={(e) => {
                                                                        const newVal = Number(e.target.value);
                                                                        if (newVal !== goal.targetAmount) {
                                                                            onUpdateGoal({ ...goal, targetAmount: newVal });
                                                                        }
                                                                    }}
                                                                />
                                                            </div>
                                                        </div>

                                                        {/* Barra de progresso */}
                                                        <div className="h-1.5 bg-slate-50 rounded-full overflow-hidden w-full">
                                                            <div
                                                                className={`h-full transition-all duration-1000 ${idx === 0 ? 'bg-amber-500' : 'bg-blue-400'}`}
                                                                style={{ width: `${Math.min((goal.currentAmount / goal.targetAmount) * 100, 100)}%` }}
                                                            ></div>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="p-8 border-2 border-dashed border-slate-200 rounded-none md:rounded-[2rem] text-center">
                                            <p className="text-slate-400 font-bold">Nenhuma meta definida.</p>
                                        </div>
                                    )}

                                </FinanceSection>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* RENDAS E OBRIGAÇÕES VIEW */}
            {activeTab === 'fixed' && (
                <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4">

                    {isNFSeGeneratorOpen && (
                        <NFSeGenerator onClose={() => setIsNFSeGeneratorOpen(false)} />
                    )}

                    {/* HUB DE SAÚDE FINANCEIRA (COMPARATIVOS) */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="lg:col-span-2 bg-white p-8 rounded-none md:rounded-[2rem] border border-slate-200 shadow-none md:shadow-xl flex flex-col justify-between relative overflow-hidden group">
                            <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity">
                                <svg className="w-32 h-32" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" /></svg>
                            </div>
                            <div className="relative z-10">
                                <div className="mb-6">
                                    <h4 className="text-xs font-black text-slate-400 uppercase tracking-[0.2em]">Comparativo Mensal</h4>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                    <div>
                                        <div className="text-[10px] font-black text-emerald-500 uppercase mb-2 tracking-widest flex items-center gap-2">
                                            Total Recebido
                                            {prevIncome > 0 && (
                                                <span className={`text-[9px] px-1.5 py-0.5 rounded-md ${currentMonthIncome >= prevIncome ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                                                    {currentMonthIncome >= prevIncome ? '↑' : '↓'} {Math.round(Math.abs((currentMonthIncome - prevIncome) / prevIncome) * 100)}%
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-4xl font-black text-slate-900 tracking-tighter">
                                            R$ {currentMonthIncome.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-[10px] font-black text-rose-500 uppercase mb-2 tracking-widest flex items-center gap-2">
                                            Total em Contas
                                            {prevBills > 0 && (
                                                <span className={`text-[9px] px-1.5 py-0.5 rounded-md ${currentTotalBills <= prevBills ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                                                    {currentTotalBills <= prevBills ? '↓' : '↑'} {Math.round(Math.abs((currentTotalBills - prevBills) / prevBills) * 100)}%
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-4xl font-black text-slate-900 tracking-tighter">
                                            R$ {currentTotalBills.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-8">
                                    <div className="flex justify-between text-[10px] font-black uppercase tracking-widest mb-2">
                                        <span className="text-slate-400">Comprometimento da Renda ({Math.round((currentTotalBills / (currentMonthIncome || 1)) * 100)}%)</span>
                                        <span className="text-slate-300 italic">Limite sugerido: 70%</span>
                                    </div>
                                    <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
                                        <div
                                            className={`h-full rounded-full transition-all duration-1000 ${currentMonthIncome > 0 && (currentTotalBills / currentMonthIncome) > 0.7 ? 'bg-rose-500' : 'bg-emerald-500'}`}
                                            style={{ width: `${Math.min(currentMonthIncome > 0 ? (currentTotalBills / currentMonthIncome) * 100 : 0, 100)}%` }}
                                        ></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className={`p-8 rounded-none md:rounded-[2rem] border shadow-none md:shadow-xl flex flex-col justify-center items-center text-center transition-all ${currentMonthIncome - currentTotalBills >= 0 ? 'bg-emerald-950 border-emerald-900 text-white' : 'bg-rose-950 border-rose-900 text-white'}`}>
                            <h4 className="text-[10px] font-black uppercase tracking-[0.2em] mb-2 opacity-60">Saldo Projetado</h4>
                            <div className="text-4xl md:text-5xl font-black tracking-tighter mb-2">
                                R$ {(currentMonthIncome - currentTotalBills).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                            </div>
                            <p className="text-[10px] font-bold uppercase opacity-40 tracking-widest">Disponível após obrigações</p>
                        </div>
                    </div>

                    <div className="h-px bg-slate-100 w-full opacity-50" />

                    {/* SEÇÃO DE RENDAS / GANHOS */}
                    <FinanceSection title="Rendas e Rendimentos">
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                            <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">Fontes de entrada recorrentes e avulsas</p>
                            <div className="flex gap-3 w-full md:w-auto">
                                <button
                                    onClick={() => setIsNFSeGeneratorOpen(true)}
                                    className="flex-1 md:flex-none border border-emerald-500/50 hover:bg-emerald-50 text-emerald-700 px-5 py-2 flex items-center justify-center gap-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest transition-all shadow-sm"
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                    Gerador NFS-e
                                </button>
                                <button
                                    onClick={() => setIsManagingIncomeRubrics(!isManagingIncomeRubrics)}
                                    className={`flex-1 md:flex-none px-5 py-2 flex items-center justify-center rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border ${isManagingIncomeRubrics ? 'bg-emerald-900 text-white border-emerald-900' : 'bg-white text-emerald-700 border-emerald-100 hover:bg-emerald-50'}`}
                                >
                                    {isManagingIncomeRubrics ? 'Fechar Rubricas' : 'Minhas Fontes'}
                                </button>
                                <button onClick={() => {
                                    setNewIncome({ category: settings.incomeCategories?.[0] || 'Renda Principal' });
                                    setIsAddingIncome(true);
                                }} className="flex-1 md:flex-none bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2 flex items-center justify-center rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest transition-all shadow-lg hover:shadow-emerald-500/20">
                                    + Registrar Ganho
                                </button>
                            </div>
                        </div>

                        {/* Gestão de Rubricas de Renda */}
                        {isManagingIncomeRubrics && (
                            <div className="bg-emerald-900 text-white p-8 rounded-none md:rounded-[2.5rem] shadow-none md:shadow-xl animate-in fade-in zoom-in-95 duration-300">
                                <div className="flex justify-between items-center mb-8">
                                    <div>
                                        <h5 className="text-lg font-black uppercase tracking-tighter text-emerald-100">Canais de Renda</h5>
                                        <p className="text-emerald-300/40 text-[10px] font-bold uppercase tracking-widest">Fontes de rendimento recorrentes</p>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
                                    {incomeRubrics.map(rubric => (
                                        <div key={rubric.id} className="bg-white/5 border border-white/10 p-4 rounded-lg md:rounded-2xl flex justify-between items-center group">
                                            <div>
                                                <div className="text-[9px] font-black text-emerald-200/50 uppercase tracking-widest mb-1">{rubric.category}</div>
                                                <div className="text-sm font-bold">{rubric.description}</div>
                                                <div className="text-[10px] text-emerald-200/40 font-bold italic mt-1">
                                                    Previsto dia {rubric.expectedDay}
                                                    {rubric.defaultAmount ? ` • R$ ${rubric.defaultAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : ' • Valor Variável'}
                                                </div>
                                            </div>
                                            <div className="flex gap-1">
                                                <button
                                                    onClick={() => {
                                                        setEditingIncomeRubric(rubric);
                                                        setNewIncomeRubric(rubric);
                                                    }}
                                                    className="p-2 text-emerald-200/20 hover:text-blue-400 transition-colors opacity-0 group-hover:opacity-100"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                </button>
                                                <button onClick={() => handleTwoStepDelete(`income_rubric_${rubric.id}`, () => onDeleteIncomeRubric(rubric.id))} className={`p-2 rounded-lg transition-colors opacity-0 group-hover:opacity-100 ${pendingDeleteKey === `income_rubric_${rubric.id}` ? 'bg-rose-500 text-white opacity-100' : 'text-emerald-200/20 hover:text-rose-400'}`}>
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="bg-white/5 p-6 rounded-none md:rounded-[2rem] border border-white/10">
                                    <h6 className="text-[10px] font-black text-emerald-300/40 uppercase tracking-widest mb-4">
                                        {editingIncomeRubric ? 'Editar Fonte de Renda' : 'Configurar Nova Fonte'}
                                    </h6>
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                                        <input
                                            type="text"
                                            placeholder="Nome da Fonte"
                                            className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-sm font-bold focus:ring-2 focus:ring-emerald-500 outline-none text-white placeholder:text-emerald-100/30"
                                            value={newIncomeRubric.description || ''}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, description: e.target.value })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Dia Previsto"
                                            className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-sm font-bold focus:ring-2 focus:ring-emerald-500 outline-none text-white placeholder:text-emerald-100/30"
                                            value={newIncomeRubric.expectedDay || ''}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, expectedDay: Number(e.target.value) })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Valor Base"
                                            className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-sm font-bold focus:ring-2 focus:ring-emerald-500 outline-none text-white placeholder:text-emerald-100/30"
                                            value={newIncomeRubric.defaultAmount || ''}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, defaultAmount: e.target.value ? Number(e.target.value) : undefined })}
                                        />
                                        <select
                                            className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-sm font-bold focus:ring-2 focus:ring-emerald-500 outline-none text-white [color-scheme:dark]"
                                            value={newIncomeRubric.category}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, category: e.target.value })}
                                        >
                                            {(settings.incomeCategories || ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']).map(cat => (
                                                <option key={cat} value={cat} className="bg-slate-900 text-white">{cat}</option>
                                            ))}
                                        </select>
                                        <div className="flex gap-2">
                                            <button
                                                onClick={async () => {
                                                    if (newIncomeRubric.description && newIncomeRubric.expectedDay) {
                                                        if (editingIncomeRubric) {
                                                            onUpdateIncomeRubric({ ...newIncomeRubric, id: editingIncomeRubric.id } as IncomeRubric);
                                                        } else {
                                                            await onAddIncomeRubric(newIncomeRubric as Omit<IncomeRubric, 'id'>);
                                                        }
                                                        setNewIncomeRubric({ category: 'Renda Principal' });
                                                        setEditingIncomeRubric(null);
                                                    }
                                                }}
                                                className="flex-1 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl px-4 py-2 text-xs font-black uppercase tracking-widest transition-all"
                                            >
                                                {editingIncomeRubric ? 'Salvar' : 'Adicionar'}
                                            </button>
                                            {editingIncomeRubric && (
                                                <button
                                                    onClick={() => {
                                                        setEditingIncomeRubric(null);
                                                        setNewIncomeRubric({ category: 'Renda Principal' });
                                                    }}
                                                    className="bg-white/10 hover:bg-white/20 text-white rounded-xl px-4 py-2 text-xs font-black uppercase tracking-widest transition-all"
                                                >
                                                    X
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Formulário de Registro de Recebimento */}
                        {isAddingIncome && (
                            <div className="bg-white p-6 rounded-none md:rounded-[2rem] border border-emerald-200 shadow-none md:shadow-xl space-y-4 animate-in slide-in-from-top-4">
                                <h5 className="text-sm font-black text-emerald-900 uppercase tracking-widest">Efetivar Recebimento</h5>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    <input type="text" placeholder="Origem" className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newIncome.description || ''} onChange={(e) => setNewIncome({ ...newIncome, description: e.target.value })} />
                                    <div className="flex gap-2">
                                        <span className="px-4 py-3 bg-emerald-50 rounded-xl font-bold text-emerald-600">R$</span>
                                        <input type="number" placeholder="Valor Recebido" className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newIncome.amount || ''} onChange={(e) => setNewIncome({ ...newIncome, amount: Number(e.target.value) })} />
                                    </div>
                                    <input type="number" placeholder="Dia Recebimento" max={31} min={1} className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newIncome.day || ''} onChange={(e) => setNewIncome({ ...newIncome, day: Number(e.target.value) })} />
                                </div>
                                <div className="flex justify-end gap-3 pt-4">
                                    <button onClick={() => setIsAddingIncome(false)} className="px-6 py-2 rounded-xl text-xs font-black uppercase tracking-widest text-slate-500 hover:bg-slate-100">Cancelar</button>
                                    <button
                                        onClick={async () => {
                                            if (newIncome.description && newIncome.amount && newIncome.day) {
                                                await onAddIncomeEntry({
                                                    ...newIncome as Omit<IncomeEntry, 'id'>,
                                                    month: currentMonth,
                                                    year: currentYear,
                                                    isReceived: true
                                                });
                                                setIsAddingIncome(false);
                                                setNewIncome({ category: 'Renda Principal' });
                                            }
                                        }}
                                        className="bg-emerald-900 text-white px-8 py-2 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg hover:bg-emerald-800"
                                    >
                                        Efetivar Recebimento
                                    </button>
                                </div>
                            </div>
                        )}

                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {/* Rubricas de Renda Pendentes */}
                            {incomeRubrics
                                .filter(rubric => !incomeEntries.some(entry =>
                                    entry.rubricId === rubric.id &&
                                    entry.month === currentMonth &&
                                    entry.year === currentYear
                                ))
                                .map(rubric => (
                                    <div key={rubric.id} className="bg-emerald-50/30 p-6 rounded-none md:rounded-[2rem] border-2 border-dashed border-emerald-100 opacity-60 hover:opacity-100 transition-all group">
                                        <div className="text-[10px] font-black uppercase tracking-widest mb-2 px-3 py-1 rounded-full w-fit bg-emerald-100 text-emerald-700">{rubric.category}</div>
                                        <h5 className="text-lg font-black text-emerald-900/40 leading-tight">{rubric.description}</h5>
                                        <div className="mt-4 text-[10px] font-black text-emerald-700/40 uppercase tracking-widest italic mb-4">Aguardando recebimento</div>
                                        <button
                                            onClick={() => {
                                                setNewIncome({
                                                    description: rubric.description,
                                                    category: rubric.category,
                                                    day: rubric.expectedDay,
                                                    amount: rubric.defaultAmount,
                                                    rubricId: rubric.id
                                                });
                                                setIsAddingIncome(true);
                                            }}
                                            className="w-full bg-white border border-emerald-100 text-emerald-700 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-emerald-50 transition-all flex items-center justify-center gap-2 shadow-sm"
                                        >
                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                            Lançar Recebimento
                                        </button>
                                    </div>
                                ))
                            }

                            {/* Rendas Efetivadas (Compactas) */}
                            {incomeEntries
                                .filter(e => e.month === currentMonth && e.year === currentYear)
                                .map(entry => {
                                    const prevEntry = incomeEntries.find(e =>
                                        e.description === entry.description &&
                                        e.month === (currentMonth === 0 ? 11 : currentMonth - 1) &&
                                        e.year === (currentMonth === 0 ? currentYear - 1 : currentYear)
                                    );
                                    const diff = prevEntry ? entry.amount - prevEntry.amount : 0;

                                    return (
                                        <div key={entry.id} className="bg-white p-4 rounded-lg md:rounded-2xl border border-emerald-50 shadow-sm flex items-center justify-between group">
                                            <div className="flex items-center gap-4">
                                                <div className="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center text-emerald-600">
                                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                                </div>
                                                <div>
                                                    <div className="text-[10px] font-black text-emerald-600/50 uppercase tracking-widest mb-0.5">{entry.category || 'Renda'}</div>
                                                    <div className="text-sm font-black text-slate-800 leading-none">{entry.description}</div>
                                                    <div className="text-[10px] text-slate-400 font-bold mt-1 flex items-center gap-2">
                                                        Recebido dia {entry.day}
                                                        {diff !== 0 && (
                                                            <span className={`text-[8px] font-black ${diff > 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                                                {diff > 0 ? '↑' : '↓'} R$ {Math.abs(diff).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-4">
                                                <div className="text-lg font-black text-emerald-600 tracking-tighter">R$ {entry.amount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</div>
                                                <button onClick={() => handleTwoStepDelete(`income_entry_${entry.id}`, () => onDeleteIncomeEntry(entry.id))} className={`p-2 rounded-lg transition-colors opacity-0 group-hover:opacity-100 ${pendingDeleteKey === `income_entry_${entry.id}` ? 'bg-rose-500 text-white opacity-100' : 'text-slate-200 hover:text-rose-400'}`}>
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                </button>
                                            </div>
                                        </div>
                                    );
                                })
                            }
                        </div>
                    </FinanceSection>

                    <div className="h-px bg-slate-100 w-full opacity-50" />

                    {/* SEÇÃO DE CONTAS / OBRIGAÇÕES */}
                    <FinanceSection title="Obrigações e Despesas">
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                            <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">Gerenciamento de pagamentos e compromissos</p>
                             <div className="flex gap-3 w-full md:w-auto">
                                 <button
                                     onClick={() => setIsManagingRubrics(!isManagingRubrics)}
                                     className={`flex-1 md:flex-none px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border ${isManagingRubrics ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}
                                 >
                                     {isManagingRubrics ? 'Fechar Rubricas' : 'Gerenciar Rubricas'}
                                 </button>
                                 <button onClick={() => {
                                     setNewBill({ category: settings.billCategories?.[0] || 'Conta Fixa' });
                                     setIsAddingBill(true);
                                 }} className="flex-1 md:flex-none bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest transition-all shadow-lg hover:shadow-blue-500/20">
                                     + Registrar Conta
                                 </button>
                             </div>
                        </div>

                        {/* Gestão de Rubricas */}
                        {isManagingRubrics && (
                            <div className="bg-slate-900 text-white p-8 rounded-none md:rounded-[2.5rem] shadow-none md:shadow-xl animate-in fade-in zoom-in-95 duration-300">
                                <div className="flex justify-between items-center mb-8">
                                    <div>
                                        <h5 className="text-lg font-black uppercase tracking-tighter">Rubricas Recorrentes</h5>
                                        <p className="text-white/40 text-[10px] font-bold uppercase tracking-widest">Contas que se repetem todos os meses</p>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
                                    {billRubrics.map(rubric => (
                                        <div key={rubric.id} className="bg-white/5 border border-white/10 p-4 rounded-lg md:rounded-2xl flex justify-between items-center group">
                                            <div>
                                                <div className="text-[9px] font-black text-white/30 uppercase tracking-widest mb-1">{rubric.category}</div>
                                                <div className="text-sm font-bold">{rubric.description}</div>
                                                <div className="text-[10px] text-white/50 font-bold italic mt-1">
                                                    Dia {rubric.dueDay}
                                                    {rubric.defaultAmount ? ` • R$ ${rubric.defaultAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : ' • Valor Variável'}
                                                </div>
                                            </div>
                                            <div className="flex gap-1">
                                                <button
                                                    onClick={() => {
                                                        setEditingRubric(rubric);
                                                        setNewRubric(rubric);
                                                    }}
                                                    className="p-2 text-white/20 hover:text-blue-400 transition-colors opacity-0 group-hover:opacity-100"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                </button>
                                                <button onClick={() => handleTwoStepDelete(`rubric_${rubric.id}`, () => onDeleteRubric(rubric.id))} className={`p-2 rounded-lg transition-colors opacity-0 group-hover:opacity-100 ${pendingDeleteKey === `rubric_${rubric.id}` ? 'bg-rose-500 text-white opacity-100' : 'text-white/20 hover:text-rose-400'}`}>
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="bg-white/5 p-6 rounded-none md:rounded-[2rem] border border-white/10">
                                    <h6 className="text-[10px] font-black text-white/40 uppercase tracking-widest mb-4">
                                        {editingRubric ? 'Editar Rubrica' : 'Cadastrar Nova Rubrica'}
                                    </h6>
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                                        <input
                                            type="text"
                                            placeholder="Nome da Conta"
                                            className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-sm font-bold focus:ring-2 focus:ring-blue-500 outline-none"
                                            value={newRubric.description || ''}
                                            onChange={e => setNewRubric({ ...newRubric, description: e.target.value })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Dia Vencimento"
                                            className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-sm font-bold focus:ring-2 focus:ring-blue-500 outline-none"
                                            value={newRubric.dueDay || ''}
                                            onChange={e => setNewRubric({ ...newRubric, dueDay: Number(e.target.value) })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Valor Fixo (Opcional)"
                                            className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-sm font-bold focus:ring-2 focus:ring-blue-500 outline-none"
                                            value={newRubric.defaultAmount || ''}
                                            onChange={e => setNewRubric({ ...newRubric, defaultAmount: e.target.value ? Number(e.target.value) : undefined })}
                                        />
                                        <select
                                            className="bg-white/10 border border-white/20 rounded-xl px-4 py-2 text-sm font-bold focus:ring-2 focus:ring-blue-500 outline-none text-white [color-scheme:dark]"
                                            value={newRubric.category}
                                            onChange={e => setNewRubric({ ...newRubric, category: e.target.value })}
                                        >
                                            {(settings.billCategories || ['Conta Fixa', 'Poupança', 'Investimento']).map(cat => (
                                                <option key={cat} value={cat} className="bg-slate-900 text-white">{cat}</option>
                                            ))}
                                        </select>
                                        <div className="flex gap-2">
                                            <button
                                                onClick={async () => {
                                                    if (newRubric.description && newRubric.dueDay) {
                                                        if (editingRubric) {
                                                            // Precisamos de um onUpdateRubric no index.tsx
                                                            // Mas por agora podemos usar o onAddRubric se mudarmos o index para handle update
                                                            // Vou adicionar o onUpdateRubric na interface
                                                            (onUpdateRubric as any)({ ...newRubric, id: editingRubric.id });
                                                        } else {
                                                            await onAddRubric(newRubric as BillRubric);
                                                        }
                                                        setNewRubric({ category: 'Conta Fixa' });
                                                        setEditingRubric(null);
                                                    }
                                                }}
                                                className="flex-1 bg-blue-500 hover:bg-blue-600 text-white rounded-xl px-4 py-2 text-xs font-black uppercase tracking-widest transition-all"
                                            >
                                                {editingRubric ? 'Salvar' : 'Adicionar'}
                                            </button>
                                            {editingRubric && (
                                                <button
                                                    onClick={() => {
                                                        setEditingRubric(null);
                                                        setNewRubric({ category: 'Conta Fixa' });
                                                    }}
                                                    className="bg-white/10 hover:bg-white/20 text-white rounded-xl px-4 py-2 text-xs font-black uppercase tracking-widest transition-all"
                                                >
                                                    X
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Form de Adição */}
                        {isAddingBill && (
                            <div className="bg-white p-6 rounded-none md:rounded-[2rem] border border-slate-200 shadow-none md:shadow-xl space-y-4">
                                <h5 className="text-sm font-black text-slate-900 uppercase tracking-widest">Adicionar Nova Conta/Aporte</h5>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <input type="text" placeholder="Descrição (ex: Aluguel, Poupança)" className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.description || ''} onChange={(e) => setNewBill({ ...newBill, description: e.target.value })} />
                                    <div className="flex gap-2">
                                        <span className="px-4 py-3 bg-slate-100 rounded-xl font-bold text-slate-500">R$</span>
                                        <input type="number" placeholder="Valor" className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.amount || ''} onChange={(e) => setNewBill({ ...newBill, amount: Number(e.target.value) })} />
                                    </div>
                                    <select className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium text-slate-900" value={newBill.category} onChange={(e) => setNewBill({ ...newBill, category: e.target.value })}>
                                        {(settings.billCategories || ['Conta Fixa', 'Poupança', 'Investimento']).map(cat => (
                                            <option key={cat} value={cat} className="bg-white text-slate-900">{cat}</option>
                                        ))}
                                    </select>
                                    <input type="number" placeholder="Dia de Vencimento" max={31} min={1} className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.dueDay || ''} onChange={(e) => setNewBill({ ...newBill, dueDay: Number(e.target.value) })} />
                                    <input type="text" placeholder="Linha Digitável (Código de Barras)" className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.barcode || ''} onChange={(e) => setNewBill({ ...newBill, barcode: e.target.value })} />
                                    <input type="text" placeholder="Código Pix (Copia e Cola)" className="px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-medium" value={newBill.pixCode || ''} onChange={(e) => setNewBill({ ...newBill, pixCode: e.target.value })} />
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                     {/* File Upload 1: Boleto */}
                                    <div className={`border-2 border-dashed rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${newBill.attachmentUrl ? 'border-blue-200 bg-blue-50' : 'border-slate-200 bg-slate-50 hover:bg-slate-100'}`} onClick={() => {
                                        const input = document.createElement('input');
                                        input.type = 'file';
                                        input.accept = 'image/*,.pdf';
                                        input.onchange = async (e) => {
                                            const file = (e.target as HTMLInputElement).files?.[0];
                                            if (file) {
                                                const url = await handleFileUpload(file);
                                                if (url) setNewBill({ ...newBill, attachmentUrl: url });
                                            }
                                        };
                                        input.click();
                                    }}>
                                        {newBill.attachmentUrl ? (
                                            <div className="flex items-center gap-2 text-blue-600 font-bold text-xs uppercase tracking-tighter">
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                                Boleto Anexado
                                            </div>
                                        ) : (
                                            <div className="text-center text-slate-400">
                                                <svg className="w-5 h-5 mx-auto mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                                                <p className="text-[10px] font-black uppercase">Anexar Boleto/PDF</p>
                                            </div>
                                        )}
                                    </div>

                                    {/* File Upload 2: PIX QR */}
                                    <div className={`border-2 border-dashed rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${newBill.pixQrCodeUrl ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-slate-50 hover:bg-slate-100'}`} onClick={() => {
                                        const input = document.createElement('input');
                                        input.type = 'file';
                                        input.accept = 'image/*';
                                        input.onchange = async (e) => {
                                            const file = (e.target as HTMLInputElement).files?.[0];
                                            if (file) {
                                                const url = await handleFileUpload(file);
                                                if (url) setNewBill({ ...newBill, pixQrCodeUrl: url });
                                            }
                                        };
                                        input.click();
                                    }}>
                                        {newBill.pixQrCodeUrl ? (
                                            <div className="flex items-center gap-2 text-emerald-600 font-bold text-xs uppercase tracking-tighter">
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                                QR PIX Anexado
                                            </div>
                                        ) : (
                                            <div className="text-center text-slate-400">
                                                <svg className="w-5 h-5 mx-auto mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" /></svg>
                                                <p className="text-[10px] font-black uppercase">Anexar QR PIX</p>
                                            </div>
                                        )}
                                    </div>
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
                            {/* Rubricas que ainda não têm lançamento no mês atual */}
                            {billRubrics
                                .filter(rubric => !fixedBills.some(bill =>
                                    bill.rubricId === rubric.id &&
                                    bill.month === currentMonth &&
                                    bill.year === currentYear
                                ))
                                .map(rubric => (
                                    <div key={rubric.id} className="bg-slate-50 p-6 rounded-none md:rounded-[2rem] border-2 border-dashed border-slate-200 opacity-60 hover:opacity-100 transition-all group">
                                        <div className="text-[10px] font-black uppercase tracking-widest mb-2 px-3 py-1 rounded-full w-fit bg-slate-200 text-slate-500">{rubric.category}</div>
                                        <h5 className="text-lg font-black text-slate-400 leading-tight">{rubric.description}</h5>
                                        <div className="mt-4 text-[10px] font-black text-slate-400 uppercase tracking-widest italic mb-4">Aguardando lançamento de {new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}</div>
                                        <button
                                            onClick={() => {
                                                setNewBill({
                                                    description: rubric.description,
                                                    category: rubric.category,
                                                    dueDay: rubric.dueDay,
                                                    amount: rubric.defaultAmount,
                                                    rubricId: rubric.id
                                                });
                                                setIsAddingBill(true);
                                            }}
                                            className="w-full bg-white border border-slate-200 text-blue-600 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-50 transition-all flex items-center justify-center gap-2"
                                        >
                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                            Lançar Valor
                                        </button>
                                    </div>
                                ))
                            }

                            {/* Contas já lançadas (Compactas) */}
                            {fixedBills
                                .filter(b => b.month === currentMonth && b.year === currentYear)
                                .map(bill => {
                                    const prevBill = fixedBills.find(b =>
                                        b.description === bill.description &&
                                        b.month === (currentMonth === 0 ? 11 : currentMonth - 1) &&
                                        b.year === (currentMonth === 0 ? currentYear - 1 : currentYear)
                                    );
                                    const diff = prevBill ? bill.amount - prevBill.amount : 0;
                                    const isVariable = bill.amount === 0;

                                    return (
                                        <div key={bill.id}
                                            className={`transition-all flex flex-col group rounded-xl md:rounded-2xl border ${
                                                bill.isPaid
                                                    ? 'border-emerald-100 bg-emerald-50/30'
                                                    : isVariable
                                                        ? 'border-dashed border-slate-200 bg-slate-50/50'
                                                        : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
                                            }`}
                                        >
                                            {/* Header do Card - Design Imagem */}
                                            <div className="flex flex-col p-4 md:p-5">
                                                {/* Tags Topo */}
                                                <div className="flex items-center gap-2 mb-3">
                                                    <span className="text-[10px] font-bold text-slate-500 bg-slate-50 px-3 py-1 rounded-full uppercase tracking-wider">
                                                        {bill.category || 'Conta Fixa'}
                                                    </span>
                                                    {isVariable && (
                                                        <span className="text-[10px] font-bold text-slate-500 bg-slate-50 px-3 py-1 rounded-full uppercase tracking-wider">
                                                            Variável
                                                        </span>
                                                    )}
                                                </div>

                                                <div className="flex items-start gap-4">
                                                    {/* Checkbox */}
                                                    <div className="flex-shrink-0 pt-0.5">
                                                        <input
                                                            type="checkbox"
                                                            checked={bill.isPaid}
                                                            disabled={isVariable}
                                                            onChange={() => onUpdateBill({ ...bill, isPaid: !bill.isPaid })}
                                                            className={`w-5 h-5 rounded-[4px] border-slate-300 text-emerald-500 focus:ring-emerald-500 transition-all ${isVariable ? 'opacity-30 cursor-not-allowed' : 'cursor-pointer hover:border-emerald-400'}`}
                                                        />
                                                    </div>

                                                    {/* Corpo e Informações */}
                                                    <div className="flex-1 flex flex-col justify-start">
                                                        <div className={`text-lg md:text-xl font-bold leading-tight ${bill.isPaid ? 'text-slate-400 line-through' : 'text-slate-900'}`}>
                                                            {bill.description}
                                                        </div>
                                                        <div className="text-sm font-semibold text-slate-500 flex items-center gap-2 mt-1">
                                                            Vencimento dia {bill.dueDay}
                                                            {diff !== 0 && !isVariable && (
                                                                <span className={`font-bold ${diff < 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                                                    ({diff < 0 ? '↓' : '↑'} R$ {Math.abs(diff).toLocaleString('pt-BR')})
                                                                </span>
                                                            )}
                                                        </div>

                                                        {/* Valor e Ações de Valor */}
                                                        <div className="mt-4">
                                                            {editingAmountId === bill.id ? (
                                                                <div className="flex items-center gap-1.5 w-fit">
                                                                    <span className="text-xs font-semibold text-slate-400">R$</span>
                                                                    <input
                                                                        autoFocus
                                                                        type="number"
                                                                        className="w-24 bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 shadow-sm"
                                                                        value={tempAmount}
                                                                        onChange={e => setTempAmount(e.target.value)}
                                                                        onBlur={() => {
                                                                            if (tempAmount !== '') {
                                                                                onUpdateBill({ ...bill, amount: Number(tempAmount) });
                                                                            }
                                                                            setEditingAmountId(null);
                                                                        }}
                                                                        onKeyDown={e => {
                                                                            if (e.key === 'Enter') {
                                                                                if (tempAmount !== '') {
                                                                                    onUpdateBill({ ...bill, amount: Number(tempAmount) });
                                                                                }
                                                                                setEditingAmountId(null);
                                                                            }
                                                                            if (e.key === 'Escape') setEditingAmountId(null);
                                                                        }}
                                                                    />
                                                                </div>
                                                            ) : (
                                                                <div
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        setEditingAmountId(bill.id);
                                                                        setTempAmount(isVariable ? '' : String(bill.amount));
                                                                    }}
                                                                    className={`w-fit cursor-pointer transition-colors ${bill.isPaid ? 'text-slate-400' : 'text-slate-800'}`}
                                                                >
                                                                    {isVariable ? (
                                                                        <span className="text-xs font-bold text-slate-500 hover:text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 px-4 py-2 flex rounded-lg transition-colors shadow-sm">
                                                                            Informar Valor
                                                                        </span>
                                                                    ) : (
                                                                        <span className="text-base font-bold bg-slate-50 border border-slate-200 px-4 py-1.5 rounded-lg shadow-sm">
                                                                            R$ {bill.amount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>

                                                    {/* Ações Laterais */}
                                                    <div className="flex items-center gap-2 border-l border-slate-100 pl-4 py-1 self-start">
                                                        <button
                                                            onClick={() => setExpandedBillId(expandedBillId === bill.id ? null : bill.id)}
                                                            className={`p-1.5 rounded-lg transition-all ${expandedBillId === bill.id ? 'bg-slate-100 text-slate-800' : 'text-slate-400 hover:text-slate-700 hover:bg-slate-50'}`}
                                                            title="Expandir detalhes"
                                                        >
                                                            <svg className={`w-5 h-5 transition-transform duration-300 ${expandedBillId === bill.id ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                                                            </svg>
                                                        </button>
                                                        <button 
                                                            onClick={() => handleTwoStepDelete(`bill_${bill.id}`, () => onDeleteBill(bill.id))} 
                                                            className={`p-1.5 rounded-lg transition-colors ${pendingDeleteKey === `bill_${bill.id}` ? 'bg-rose-500 text-white' : 'text-slate-300 hover:text-rose-500 hover:bg-rose-50'}`}
                                                            title="Excluir"
                                                        >
                                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Área Expandida - Tabs Clean */}
                                            {expandedBillId === bill.id && (
                                                <div className="px-5 pb-6 pt-3 border-t border-slate-100 animate-in slide-in-from-top-2 duration-200">
                                                    
                                                    {/* Tabs Header */}
                                                    <div className="flex gap-2 mb-5">
                                                        <button
                                                            onClick={e => { e.stopPropagation(); setActiveBillTabs(prev => ({ ...prev, [bill.id]: 'codigo' })); }}
                                                            className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-colors ${activeBillTabs[bill.id] !== 'arquivo' ? 'bg-slate-800 text-white shadow-sm' : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-800'}`}
                                                        >
                                                            Digitar Código
                                                        </button>
                                                        <button
                                                            onClick={e => { e.stopPropagation(); setActiveBillTabs(prev => ({ ...prev, [bill.id]: 'arquivo' })); }}
                                                            className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-colors ${activeBillTabs[bill.id] === 'arquivo' ? 'bg-slate-800 text-white shadow-sm' : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-800'}`}
                                                        >
                                                            Anexar Arquivo
                                                        </button>
                                                    </div>

                                                    <div className="flex flex-col gap-5 max-w-2xl">
                                                        {activeBillTabs[bill.id] !== 'arquivo' ? (
                                                            <>
                                                                {/* Inputs de Texto */}
                                                                <div>
                                                                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-1.5">Linha Digitável / Código de Barras</label>
                                                                    <div className="flex gap-2">
                                                                        <div className="relative flex-1">
                                                                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                                                                <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" /></svg>
                                                                            </div>
                                                                            <input
                                                                                type="text"
                                                                                placeholder="00000.00000.00000.000000..."
                                                                                className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-3 py-2.5 text-sm text-slate-700 outline-none focus:ring-2 focus:ring-blue-500 transition-all font-mono"
                                                                                defaultValue={bill.barcode || ''}
                                                                                onBlur={(e) => onUpdateBill({ ...bill, barcode: e.target.value })}
                                                                            />
                                                                        </div>
                                                                        {bill.barcode && (
                                                                            <button onClick={() => navigator.clipboard.writeText(bill.barcode || '')} className="px-4 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 hover:text-slate-800 transition-colors flex items-center justify-center font-bold text-xs">
                                                                                Copiar
                                                                            </button>
                                                                        )}
                                                                    </div>
                                                                </div>

                                                                <div>
                                                                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-1.5">Código PIX</label>
                                                                    <div className="flex gap-2">
                                                                        <div className="relative flex-1">
                                                                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                                                                <svg className="w-4 h-4 text-emerald-500" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L2.5 7.5v9L12 22l9.5-5.5v-9L12 2zm0 2.24l7.5 4.33-7.5 4.33-7.5-4.33L12 4.24zm-8.5 6.1v7.62l7.5 4.33v-8.66l-7.5-4.33zm17 0l-7.5 4.33v8.66l7.5-4.33V10.34z"/></svg>
                                                                            </div>
                                                                            <input
                                                                                type="text"
                                                                                placeholder="00020126360014BR.GOV.BCB.PIX..."
                                                                                className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-3 py-2.5 text-sm text-slate-700 outline-none focus:ring-2 focus:ring-emerald-500 transition-all font-mono"
                                                                                defaultValue={bill.pixCode || ''}
                                                                                onBlur={(e) => onUpdateBill({ ...bill, pixCode: e.target.value })}
                                                                            />
                                                                        </div>
                                                                        {bill.pixCode && (
                                                                            <button onClick={() => navigator.clipboard.writeText(bill.pixCode || '')} className="px-4 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 hover:text-slate-800 transition-colors flex items-center justify-center font-bold text-xs">
                                                                                Copiar
                                                                            </button>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            </>
                                                        ) : (
                                                            <>
                                                                {/* Arquivos Relacionados - Empilhados Verticalmente */}
                                                                <div className="flex flex-col gap-3 mt-2">
                                                            {/* Dropzone PDF */}
                                                            <div>
                                                                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-1.5">Boleto / PDF</label>
                                                                <div
                                                                    onClick={() => {
                                                                        const input = document.createElement('input');
                                                                        input.type = 'file';
                                                                        input.accept = 'image/*,.pdf';
                                                                        input.onchange = async (e) => {
                                                                            const file = (e.target as HTMLInputElement).files?.[0];
                                                                            if (file) {
                                                                                const url = await handleFileUpload(file);
                                                                                if (url) onUpdateBill({ ...bill, attachmentUrl: url });
                                                                            }
                                                                        };
                                                                        input.click();
                                                                    }}
                                                                    className={`flex items-center gap-4 border border-dashed rounded-lg p-4 cursor-pointer transition-colors group ${bill.attachmentUrl ? 'bg-blue-50/50 border-blue-200 hover:border-blue-400' : 'bg-slate-50 border-slate-300 hover:bg-slate-100 hover:border-slate-400'}`}
                                                                >
                                                                    <div className={`p-3 rounded-full ${bill.attachmentUrl ? 'bg-blue-100 text-blue-500' : 'bg-slate-200 text-slate-400 group-hover:bg-blue-100 group-hover:text-blue-500'} transition-colors`}>
                                                                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                                                    </div>
                                                                    <div className="flex-1">
                                                                        {bill.attachmentUrl ? (
                                                                            <>
                                                                                <div className="text-sm font-bold text-blue-700">Arquivo Anexado com Sucesso</div>
                                                                                <div className="text-[11px] text-blue-500 mt-0.5">Clique para alterar o arquivo</div>
                                                                            </>
                                                                        ) : (
                                                                            <>
                                                                                <div className="text-sm font-semibold text-slate-600 group-hover:text-slate-800">Anexar Arquivo de Boleto</div>
                                                                                <div className="text-[11px] text-slate-400 mt-0.5">Faça o upload do PDF ou Imagem</div>
                                                                            </>
                                                                        )}
                                                                    </div>
                                                                    {bill.attachmentUrl && (
                                                                        <a href={bill.attachmentUrl} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} className="px-4 py-2 bg-white border border-blue-200 text-blue-600 rounded-lg text-xs font-bold hover:bg-blue-50 transition-colors shadow-sm">
                                                                            Visualizar
                                                                        </a>
                                                                    )}
                                                                </div>
                                                            </div>

                                                            {/* Dropzone QR PIX */}
                                                            <div>
                                                                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-1.5">Imagem do QR Code</label>
                                                                <div
                                                                    onClick={() => {
                                                                        const input = document.createElement('input');
                                                                        input.type = 'file';
                                                                        input.accept = 'image/*';
                                                                        input.onchange = async (e) => {
                                                                            const file = (e.target as HTMLInputElement).files?.[0];
                                                                            if (file) {
                                                                                const url = await handleFileUpload(file);
                                                                                if (url) onUpdateBill({ ...bill, pixQrCodeUrl: url });
                                                                            }
                                                                        };
                                                                        input.click();
                                                                    }}
                                                                    className={`flex items-center gap-4 border border-dashed rounded-lg p-4 cursor-pointer transition-colors group ${bill.pixQrCodeUrl ? 'bg-emerald-50/50 border-emerald-200 hover:border-emerald-400' : 'bg-slate-50 border-slate-300 hover:bg-slate-100 hover:border-slate-400'}`}
                                                                >
                                                                    <div className={`p-3 rounded-full ${bill.pixQrCodeUrl ? 'bg-emerald-100 text-emerald-500' : 'bg-slate-200 text-slate-400 group-hover:bg-emerald-100 group-hover:text-emerald-500'} transition-colors`}>
                                                                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" /></svg>
                                                                    </div>
                                                                    <div className="flex-1">
                                                                        {bill.pixQrCodeUrl ? (
                                                                            <>
                                                                                <div className="text-sm font-bold text-emerald-700">QR Code Anexado com Sucesso</div>
                                                                                <div className="text-[11px] text-emerald-500 mt-0.5">Clique para alterar a imagem</div>
                                                                            </>
                                                                        ) : (
                                                                            <>
                                                                                <div className="text-sm font-semibold text-slate-600 group-hover:text-slate-800">Anexar QR Code do PIX</div>
                                                                                <div className="text-[11px] text-slate-400 mt-0.5">Faça o upload de uma imagem do código</div>
                                                                            </>
                                                                        )}
                                                                    </div>
                                                                    {bill.pixQrCodeUrl && (
                                                                        <a href={bill.pixQrCodeUrl} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} className="px-4 py-2 bg-white border border-emerald-200 text-emerald-600 rounded-lg text-xs font-bold hover:bg-emerald-50 transition-colors shadow-sm">
                                                                            Visualizar
                                                                        </a>
                                                                    )}
                                                                </div>
                                                            </div>
                                                                </div>
                                                            </>
                                                        )}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            {fixedBills.filter(b => b.month === currentMonth && b.year === currentYear).length === 0 && billRubrics.length === 0 && (
                                <div className="col-span-full py-12 text-center border border-dashed border-slate-200 rounded-none md:rounded-[2rem]">
                                    <p className="text-slate-400 font-bold uppercase tracking-widest text-[10px]">Nenhuma obrigação registrada</p>
                                </div>
                            )}
                        </div>
                    </FinanceSection>
                </div>
            )}
        </div>
    );
};

export default FinanceView;
