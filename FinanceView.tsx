import React, { useState, useRef, useEffect } from 'react';
import { FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill, BillRubric, IncomeEntry, IncomeRubric } from './types';
import { storage, db } from './firebase';
import { ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { doc, setDoc } from 'firebase/firestore';
import { resolveTwoStepAction } from './src/utils/destructiveActions';
import { NFSeGenerator } from './src/components/NFSeGenerator';
import { FinancialHealthCard } from './src/components/FinancialHealthCard';
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
    onOpenFinancialCopilot?: () => void;
}

const FinanceSection = ({ title, children, defaultExpanded = true, disableCollapse = false }: { title: string, children: React.ReactNode, defaultExpanded?: boolean, disableCollapse?: boolean }) => {
    const [isExpanded, setIsExpanded] = useState(defaultExpanded);
    const showChildren = disableCollapse || isExpanded;

    return (
        <div className="bg-surface p-6 md:p-8 rounded-lg border-b md:border border-[#e5e7eb] dark:border-white/10 shadow-none">
            {!disableCollapse ? (
                <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="w-full flex items-center justify-between group"
                >
                    <h4 className="text-xl font-sans font-semibold text-on-surface uppercase tracking-tight">{title}</h4>
                    <svg className={`w-5 h-5 text-slate-300 group-hover:text-primary-tactile transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                    </svg>
                </button>
            ) : (
                <h4 className="text-xl font-sans font-semibold text-on-surface uppercase tracking-tight mb-6">{title}</h4>
            )}
            {showChildren && (
                <div className={`${!disableCollapse ? 'mt-6' : ''} animate-in slide-in-from-top-2 duration-300`}>
                    {children}
                </div>
            )}
        </div>
    );
};

type SortDirection = 'asc' | 'desc';

const formatCurrency = (value: number) => `R$ ${value.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;

const getSortIndicator = (isActive: boolean, direction: SortDirection) => {
    if (!isActive) return '<->';
    return direction === 'asc' ? '^' : 'v';
};

const sortByDirection = <T,>(items: T[], getValue: (item: T) => string | number | boolean, direction: SortDirection) => {
    return [...items].sort((a, b) => {
        const valueA = getValue(a);
        const valueB = getValue(b);

        if (typeof valueA === 'string' && typeof valueB === 'string') {
            const comparison = valueA.localeCompare(valueB, 'pt-BR', { sensitivity: 'base' });
            return direction === 'asc' ? comparison : -comparison;
        }

        const normalizedA = Number(valueA);
        const normalizedB = Number(valueB);
        return direction === 'asc' ? normalizedA - normalizedB : normalizedB - normalizedA;
    });
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
    setIsSettingsOpen,
    onOpenFinancialCopilot
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
    const [newIncome, setNewIncome] = useState<Partial<IncomeEntry>>({ category: 'Renda Principal', isReceived: false });
    const [incomeSearch, setIncomeSearch] = useState('');
    const [incomeStatusFilter, setIncomeStatusFilter] = useState<'all' | 'received' | 'pending'>('all');
    const [incomeCategoryFilter, setIncomeCategoryFilter] = useState('all');
    const [incomeSort, setIncomeSort] = useState<{ key: 'description' | 'category' | 'amount' | 'day' | 'status'; direction: SortDirection }>({ key: 'day', direction: 'asc' });
    const [expandedIncomeId, setExpandedIncomeId] = useState<string | null>(null);

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
    const [billSearch, setBillSearch] = useState('');
    const [billStatusFilter, setBillStatusFilter] = useState<'all' | 'paid' | 'unpaid'>('all');
    const [billCategoryFilter, setBillCategoryFilter] = useState('all');
    const [billSort, setBillSort] = useState<{ key: 'description' | 'category' | 'amount' | 'dueDay' | 'status' | 'barcode' | 'pix'; direction: SortDirection }>({ key: 'dueDay', direction: 'asc' });

    // NFSe Generator State
    const [isNFSeGeneratorOpen, setIsNFSeGeneratorOpen] = useState(false);

    // Emergency Reserve Local State for Sync
    const [localEmergencyCurrent, setLocalEmergencyCurrent] = useState(emergencyReserve.current);
    const [localEmergencyTarget, setLocalEmergencyTarget] = useState(emergencyReserve.target);

    // Sync local state when props change (from parent/firebase)
    useEffect(() => {
        setLocalEmergencyCurrent(emergencyReserve.current);
    }, [emergencyReserve.current]);

    useEffect(() => {
        setLocalEmergencyTarget(emergencyReserve.target);
    }, [emergencyReserve.target]);

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
    const monthProgress = isCurrentMonth ? (today.getDate() / daysInMonth) * 100 : null;

    const getSprintStatus = () => {
        const budgetPerSprint = currentBudget / 4;
        const expectedSpend = budgetPerSprint * currentSprint;

        if (currentMonthTotal < expectedSpend * 0.9) return 'bg-emerald-500';
        if (currentMonthTotal <= expectedSpend) return 'bg-yellow-500';
        return 'bg-rose-500';
    };

    const getBudgetColor = (percentage: number) => {
        if (!isCurrentMonth) return percentage >= 100 ? 'bg-rose-500' : 'bg-emerald-500';
        if (percentage < monthProgress!) return 'bg-emerald-500';
        if (percentage < monthProgress! + 5) return 'bg-yellow-500';
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

    const handleExportCSV = () => {
        const filteredTransactions = transactions
            .filter(t => {
                const d = new Date(t.date);
                return d.getMonth() === currentMonth && d.getFullYear() === currentYear;
            })
            .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

        if (filteredTransactions.length === 0) {
            return;
        }

        const headers = ['Data', 'Descrição', 'Valor'];
        const rows = filteredTransactions.map(t => [
            new Date(t.date).toLocaleDateString('pt-BR'),
            t.description || 'LOG_ITEM_STREAM',
            t.amount.toFixed(2).replace('.', ',')
        ]);

        const csvContent = [
            headers.join(';'),
            ...rows.map(row => row.join(';'))
        ].join('\n');

        const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const monthName = new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth));
        link.setAttribute('href', url);
        link.setAttribute('download', `lancamentos_${monthName}_${currentYear}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

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
    const currentMonthIncomeEntries = incomeEntries.filter(e => e.month === currentMonth && e.year === currentYear);
    const currentMonthBills = fixedBills.filter(b => b.month === currentMonth && b.year === currentYear);
    const pendingIncomeRubrics = incomeRubrics.filter(rubric => !currentMonthIncomeEntries.some(entry => entry.rubricId === rubric.id));
    const pendingBillRubrics = billRubrics.filter(rubric => !currentMonthBills.some(bill => bill.rubricId === rubric.id));

    const toggleIncomeSort = (key: 'description' | 'category' | 'amount' | 'day' | 'status') => {
        setIncomeSort(current => current.key === key
            ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
            : { key, direction: 'asc' });
    };

    const toggleBillSort = (key: 'description' | 'category' | 'amount' | 'dueDay' | 'status' | 'barcode' | 'pix') => {
        setBillSort(current => current.key === key
            ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
            : { key, direction: 'asc' });
    };

    let visibleIncomeEntries = currentMonthIncomeEntries.filter(entry => {
        const matchesStatus = incomeStatusFilter === 'all'
            || (incomeStatusFilter === 'received' && entry.isReceived)
            || (incomeStatusFilter === 'pending' && !entry.isReceived);
        const matchesCategory = incomeCategoryFilter === 'all' || entry.category === incomeCategoryFilter;
        const matchesSearch = incomeSearch.trim() === '' || entry.description.toLowerCase().includes(incomeSearch.trim().toLowerCase());
        return matchesStatus && matchesCategory && matchesSearch;
    });

    visibleIncomeEntries = sortByDirection(visibleIncomeEntries, entry => {
        switch (incomeSort.key) {
            case 'description': return entry.description;
            case 'category': return entry.category || '';
            case 'amount': return entry.amount;
            case 'day': return entry.day;
            case 'status': return entry.isReceived ? 1 : 0;
        }
    }, incomeSort.direction);

    let visibleBills = currentMonthBills.filter(bill => {
        const matchesStatus = billStatusFilter === 'all'
            || (billStatusFilter === 'paid' && bill.isPaid)
            || (billStatusFilter === 'unpaid' && !bill.isPaid);
        const matchesCategory = billCategoryFilter === 'all' || bill.category === billCategoryFilter;
        const term = billSearch.trim().toLowerCase();
        const matchesSearch = term === ''
            || bill.description.toLowerCase().includes(term)
            || (bill.barcode || '').toLowerCase().includes(term)
            || (bill.pixCode || '').toLowerCase().includes(term);
        return matchesStatus && matchesCategory && matchesSearch;
    });

    visibleBills = sortByDirection(visibleBills, bill => {
        switch (billSort.key) {
            case 'description': return bill.description;
            case 'category': return bill.category || '';
            case 'amount': return bill.amount;
            case 'dueDay': return bill.dueDay;
            case 'status': return bill.isPaid ? 1 : 0;
            case 'barcode': return bill.barcode ? 1 : 0;
            case 'pix': return bill.pixCode ? 1 : 0;
        }
    }, billSort.direction);

    const incomeReceivedTotal = currentMonthIncomeEntries
        .filter(entry => entry.isReceived)
        .reduce((acc, curr) => acc + curr.amount, 0);
    const incomePendingTotal = currentMonthIncomeEntries
        .filter(entry => !entry.isReceived)
        .reduce((acc, curr) => acc + curr.amount, 0);
    const incomeOverallTotal = currentMonthIncomeEntries.reduce((acc, curr) => acc + curr.amount, 0);

    const billsPaidTotal = currentMonthBills
        .filter(bill => bill.isPaid)
        .reduce((acc, curr) => acc + curr.amount, 0);
    const billsPendingTotal = currentMonthBills
        .filter(bill => !bill.isPaid)
        .reduce((acc, curr) => acc + curr.amount, 0);
    const billsOverallTotal = currentMonthBills.reduce((acc, curr) => acc + curr.amount, 0);

    const getHealthStatus = () => {
        if (incomeOverallTotal === 0) return { label: 'Aguardando Renda', color: 'text-slate-400', icon: '⏳' };
        const ratio = currentTotalBills / incomeOverallTotal;
        if (ratio < 0.4) return { label: 'Saúde Excelente', color: 'text-emerald-500', icon: '✨' };
        if (ratio < 0.7) return { label: 'Saúde Estável', color: 'text-blue-500', icon: '✅' };
        if (ratio < 0.9) return { label: 'Atenção Necessária', color: 'text-amber-500', icon: '⚠️' };
        return { label: 'Risco Financeiro', color: 'text-rose-500', icon: '🚨' };
    };

    const health = getHealthStatus();

    const handleSaveBill = async () => {
        if (!newBill.description || newBill.amount === undefined || newBill.amount === null) return;

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
                <div className="bg-on-surface text-surface p-8 rounded-lg shadow-none animate-in slide-in-from-top-4 space-y-10 border-b-4 border-primary-tactile">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                        <div>
                            <h4 className="text-[10px] font-sans font-semibold uppercase tracking-[0.3em] mb-4 text-primary-tactile flex items-center gap-2">
                                <span className="w-2 h-2 bg-primary-tactile"></span>
                                BUDGET_PERIOD // {new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}
                            </h4>
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
                                    className="bg-white/5 border border-white/20 rounded-lg px-4 py-3 text-white font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full text-lg"
                                />
                            </div>
                            <p className="text-[8px] text-white/30 uppercase mt-2 font-sans font-semibold italic tracking-widest">LOCAL_OVERRIDE_ACTIVE</p>
                        </div>
                        <div>
                            <h4 className="text-[10px] font-sans font-semibold uppercase tracking-[0.3em] mb-4 text-slate-400 flex items-center gap-2">
                                <span className="w-2 h-2 bg-slate-600"></span>
                                DEFAULT_BUDGET_FALLBACK
                            </h4>
                            <div className="flex gap-4">
                                <input
                                    type="number"
                                    defaultValue={settings.monthlyBudget}
                                    onBlur={(e) => onUpdateSettings({ ...settings, monthlyBudget: Number(e.target.value) })}
                                    className="bg-white/5 border border-white/20 rounded-lg px-4 py-3 text-white font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full text-lg"
                                />
                            </div>
                            <p className="text-[8px] text-white/30 uppercase mt-2 font-sans font-semibold italic tracking-widest">GLOBAL_SYSTEM_BASELINE</p>
                        </div>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                        <div>
                            <h4 className="text-[10px] font-sans font-semibold uppercase tracking-[0.3em] mb-4 text-emerald-500 flex items-center gap-2">
                                <span className="w-2 h-2 bg-emerald-500"></span>
                                EMERGENCY_RESERVE_TARGET
                            </h4>
                            <input
                                type="number"
                                value={localEmergencyTarget}
                                onChange={(e) => setLocalEmergencyTarget(Number(e.target.value))}
                                onBlur={(e) => onUpdateSettings({ ...settings, emergencyReserveTarget: Number(e.target.value) })}
                                className="bg-white/5 border border-white/20 rounded-lg px-4 py-3 text-white font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full"
                            />
                        </div>
                        <div>
                            <h4 className="text-[10px] font-sans font-semibold uppercase tracking-[0.3em] mb-4 text-emerald-500 flex items-center gap-2">
                                <span className="w-2 h-2 bg-emerald-500"></span>
                                CURRENT_RESERVE_SYNC
                            </h4>
                            <input
                                type="number"
                                value={localEmergencyCurrent}
                                onChange={(e) => setLocalEmergencyCurrent(Number(e.target.value))}
                                onBlur={(e) => onUpdateSettings({ ...settings, emergencyReserveCurrent: Number(e.target.value) })}
                                className="bg-white/5 border border-white/20 rounded-lg px-4 py-3 text-white font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full"
                            />
                        </div>
                    </div>

                    {/* Configuração de Gastos Externos Industrial */}
                    <div className="pt-8 border-t border-white/10">
                        <h4 className="text-[10px] font-sans font-semibold uppercase tracking-[0.4em] mb-6 text-purple-400">// EXTERNAL_SPENDING_PORTAL</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                            <div>
                                <label className="text-[9px] font-sans font-semibold text-white/40 uppercase tracking-widest block mb-2">EXTERNAL_LIMIT_ALLOCATION</label>
                                <input
                                    type="number"
                                    defaultValue={settings.externalSpendingLimit || 0}
                                    onBlur={async (e) => {
                                        const newVal = Number(e.target.value);
                                        const newSettings = { ...settings, externalSpendingLimit: newVal };
                                        onUpdateSettings(newSettings);
                                        await setDoc(doc(db, 'public_configs', 'finance_portal'), {
                                            limit: newVal,
                                            token: settings.externalToken
                                        }, { merge: true });
                                    }}
                                    className="bg-white/5 border border-white/20 rounded-lg px-4 py-3 text-white font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full"
                                />
                            </div>
                            <div>
                                <label className="text-[9px] font-sans font-semibold text-white/40 uppercase tracking-widest block mb-2">AUTH_TOKEN_GENERATOR</label>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={settings.externalToken || ''}
                                        readOnly
                                        placeholder="NULL_TOKEN"
                                        className="bg-white/5 border border-white/20 rounded-lg px-4 py-3 text-white font-sans text-xs outline-none w-full"
                                    />
                                    <button
                                        onClick={async () => {
                                            const newToken = Math.random().toString(36).substring(2, 10) + Math.random().toString(36).substring(2, 10);
                                            const newSettings = { ...settings, externalToken: newToken };
                                            onUpdateSettings(newSettings);
                                            await setDoc(doc(db, 'public_configs', 'finance_portal'), {
                                                limit: settings.externalSpendingLimit,
                                                token: newToken
                                            }, { merge: true });
                                        }}
                                        className="bg-white text-on-surface hover:bg-primary-tactile hover:text-white px-6 py-3 rounded-lg text-[10px] font-sans font-semibold uppercase tracking-widest transition-all"
                                    >
                                        GENERATE
                                    </button>
                                </div>
                            </div>
                        </div>
                        {settings.externalToken && (
                            <div className="mt-6 bg-white/5 border border-white/10 p-4 rounded-lg flex flex-col md:flex-row items-center justify-between gap-4">
                                <div className="text-[10px] font-sans text-purple-300 break-all opacity-80 italic">
                                    {window.location.origin}/gastos-externos?token={settings.externalToken}
                                </div>
                                <button
                                    onClick={() => navigator.clipboard.writeText(`${window.location.origin}/gastos-externos?token=${settings.externalToken}`)}
                                    className="bg-purple-600/20 text-purple-300 border border-purple-500/30 px-5 py-2 rounded-soft-touch text-[9px] font-sans font-semibold uppercase tracking-widest hover:bg-purple-600/40 transition-all flex items-center gap-2"
                                >
                                    COPY_LINK_STREAM
                                </button>
                            </div>
                        )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-10 pt-8 border-t border-white/10">
                        {/* Gestão de Categorias de Obrigações Industrial */}
                        <div className="space-y-6">
                            <h4 className="text-[10px] font-sans font-semibold uppercase tracking-[0.3em] text-blue-400">// BILL_TAXONOMY</h4>
                            <div className="flex flex-wrap gap-2">
                                {(settings.billCategories || ['Conta Fixa', 'Poupança', 'Investimento']).map(cat => (
                                    <div key={cat} className="flex items-center gap-3 bg-white/5 border border-white/10 px-3 py-1 rounded-lg group">
                                        <span className="text-[10px] font-sans font-semibold uppercase tracking-widest">{cat}</span>
                                        <button
                                            onClick={() => onUpdateSettings({
                                                ...settings,
                                                billCategories: (settings.billCategories || []).filter(c => c !== cat)
                                            })}
                                            className="text-white/20 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-all font-sans font-semibold text-[10px]"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                ))}
                            </div>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    placeholder="APPEND_NEW_TAG"
                                    className="bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-[10px] font-sans font-semibold uppercase tracking-widest outline-none focus:ring-1 focus:ring-blue-500 w-full"
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
                                    className="bg-blue-600 text-white px-4 py-2 rounded-soft-touch text-[10px] font-sans font-semibold"
                                >
                                    +
                                </button>
                            </div>
                        </div>

                        {/* Gestão de Categorias de Renda Industrial */}
                        <div className="space-y-6">
                            <h4 className="text-[10px] font-sans font-semibold uppercase tracking-[0.3em] text-emerald-400">// INCOME_SOURCES</h4>
                            <div className="flex flex-wrap gap-2">
                                {(settings.incomeCategories || ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']).map(cat => (
                                    <div key={cat} className="flex items-center gap-3 bg-white/5 border border-white/10 px-3 py-1 rounded-lg group">
                                        <span className="text-[10px] font-sans font-semibold uppercase tracking-widest">{cat}</span>
                                        <button
                                            onClick={() => onUpdateSettings({
                                                ...settings,
                                                incomeCategories: (settings.incomeCategories || []).filter(c => c !== cat)
                                            })}
                                            className="text-white/20 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-all font-sans font-semibold text-[10px]"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                ))}
                            </div>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    placeholder="APPEND_NEW_SOURCE"
                                    className="bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-[10px] font-sans font-semibold uppercase tracking-widest outline-none focus:ring-1 focus:ring-emerald-500 w-full"
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
                                    className="bg-emerald-600 text-white px-4 py-2 rounded-soft-touch text-[10px] font-sans font-semibold"
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
                    <FinancialHealthCard
                        transactions={transactions}
                        goals={goals}
                        emergencyReserve={emergencyReserve}
                        settings={settings}
                        currentMonthTotal={currentMonthTotal}
                        currentMonthIncome={currentMonthIncome}
                        fixedBills={fixedBills}
                        incomeEntries={incomeEntries}
                        currentMonth={currentMonth}
                        currentYear={currentYear}
                        onOpenFinancialCopilot={onOpenFinancialCopilot}
                    />
                    {/* Budget Bar Section */}
                    <div className="bg-surface p-6 md:p-8 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none relative overflow-hidden">
                        <div className="flex justify-between items-end mb-6">
                            <div>
                                <h4 className="text-2xl font-sans font-semibold text-on-surface tracking-tight mb-1">
                                    // GASTO ACUMULADO • {new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}
                                </h4>
                                <div className="text-2xl md:text-5xl font-sans font-semibold text-on-surface tracking-tighter leading-none">
                                    R$ {currentMonthTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                    <span className="text-slate-400 text-sm md:text-2xl ml-1">/ {currentBudget.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                </div>
                                <div className="flex flex-wrap gap-4 mt-2">
                                    <p className="text-slate-500 text-[9px] md:text-[10px] font-sans font-semibold uppercase tracking-widest flex items-center gap-1">
                                        <span className="w-1 h-1 bg-primary-tactile rounded-full"></span>
                                        DISPONÍVEL: R$ {(currentBudget - currentMonthTotal).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                    </p>
                                </div>
                            </div>
                            <div className={`px-3 py-1.5 rounded-soft-touch text-[9px] md:text-[10px] font-sans font-semibold uppercase tracking-widest text-white shadow-sm ${getSprintStatus()}`}>
                                SPRINT {currentSprint}
                            </div>
                        </div>

                        <div className="relative h-4 overflow-visible">
                            <div className="absolute inset-0 bg-slate-200 rounded-lg overflow-hidden border border-[#e5e7eb] dark:border-white/10">
                                <div
                                    className={`h-full transition-all duration-1000 ${getBudgetColor(budgetPercentage)}`}
                                    style={{ width: `${budgetPercentage}%` }}
                                />
                            </div>
                            <div className="absolute top-0 bottom-0 left-[25%] w-px bg-on-surface/10 z-10"></div>
                            <div className="absolute top-0 bottom-0 left-[50%] w-px bg-on-surface/10 z-10"></div>
                            <div className="absolute top-0 bottom-0 left-[75%] w-px bg-on-surface/10 z-10"></div>

                            {monthProgress !== null && (
                                <div
                                    className="absolute top-1/2 -translate-y-1/2 z-20"
                                    style={{ left: `${Math.min(monthProgress, 100)}%` }}
                                >
                                    <div className="relative -translate-x-1/2">
                                        <div className="absolute left-1/2 -top-6 h-6 w-px bg-on-surface/30" />
                                        <div className="absolute left-1/2 top-2 h-2 w-2 -translate-x-1/2 bg-on-surface border border-surface" />
                                        <div className="absolute left-1/2 -top-10 -translate-x-1/2 whitespace-nowrap bg-on-surface px-2 py-0.5 text-[8px] font-sans font-semibold uppercase tracking-widest text-white">
                                            ATUAL
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-sans font-semibold text-on-surface/40">
                                {budgetPercentage.toFixed(1)}%
                            </div>
                        </div>

                        <div className="mt-4 flex justify-between text-[9px] font-sans font-semibold text-slate-500 uppercase tracking-widest">
                            <span>01 / MONTH_START</span>
                            <span>MONTH_END / {daysInMonth}</span>
                        </div>
                    </div>

                    {/* Content Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8">

                        {/* TRANSACTIONS (LEFT COLUMN) */}
                        <div className="order-2 md:order-1 h-full">
                            <FinanceSection title={`Lançamentos de ${new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}`} disableCollapse>
                                <div className="flex justify-end mb-4 gap-6">
                                    <button
                                        onClick={handleExportCSV}
                                        className="text-[10px] font-black text-slate-400 uppercase tracking-widest hover:text-primary-tactile transition-colors"
                                    >
                                        Exportar CSV
                                    </button>
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

                                {/* Form para Adicionar/Editar Transação Industrial */}
                                {(isAddingTransaction || editingTransaction) && (
                                    <div className="mb-8 p-6 bg-slate-50 rounded-lg border border-[#e5e7eb] dark:border-white/10 space-y-4 animate-in slide-in-from-top-4">
                                        <h5 className="text-[9px] font-sans font-semibold uppercase text-primary-tactile tracking-widest flex items-center gap-2">
                                            <span className="w-1.5 h-1.5 bg-primary-tactile"></span>
                                            {editingTransaction ? 'EDIT_TRANSACTION_NODE' : 'INITIALIZE_NEW_TRANSACTION'}
                                        </h5>
                                        <input
                                            type="text"
                                            placeholder="DESCRIPTION_LOG"
                                            className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                            value={(editingTransaction || newTransaction).description || ''}
                                            onChange={e => editingTransaction ? setEditingTransaction({ ...editingTransaction, description: e.target.value }) : setNewTransaction({ ...newTransaction, description: e.target.value })}
                                        />
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="relative">
                                                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[10px] font-sans font-semibold text-slate-400">BRL</span>
                                                <input
                                                    type="number"
                                                    placeholder="0.00"
                                                    className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg pl-12 pr-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                                    value={(editingTransaction || newTransaction).amount || ''}
                                                    onChange={e => editingTransaction ? setEditingTransaction({ ...editingTransaction, amount: Number(e.target.value) }) : setNewTransaction({ ...newTransaction, amount: Number(e.target.value) })}
                                                />
                                            </div>
                                            <input
                                                type="date"
                                                className="bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                                value={(editingTransaction || newTransaction).date?.split('T')[0] || ''}
                                                onChange={e => {
                                                    const date = new Date(e.target.value).toISOString();
                                                    const day = new Date(e.target.value).getDate();
                                                    const sprint = day < 8 ? 1 : day < 15 ? 2 : day < 22 ? 3 : 4;
                                                    editingTransaction ? setEditingTransaction({ ...editingTransaction, date, sprint }) : setNewTransaction({ ...newTransaction, date, sprint });
                                                }}
                                            />
                                        </div>
                                        <div className="flex gap-2 pt-2">
                                            <button
                                                onClick={() => { setIsAddingTransaction(false); setEditingTransaction(null); }}
                                                className="flex-1 px-4 py-3 border border-[#e5e7eb] dark:border-white/10 text-slate-400 hover:text-on-surface hover:bg-slate-100 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest transition-all"
                                            >
                                                ABORT
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
                                                className="flex-1 px-4 py-3 bg-on-surface text-white rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest hover:bg-primary-tactile transition-all"
                                            >
                                                COMMIT_DATA
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
                                            <div key={t.id} className="group relative flex flex-col sm:flex-row sm:justify-between sm:items-center p-4 hover:bg-slate-50 rounded-lg transition-all border-b border-[#e5e7eb] dark:border-white/10 last:border-0 gap-3 sm:gap-4">
                                                <div className="flex items-center gap-4 min-w-0">
                                                    <div className="w-10 h-10 rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white flex items-center justify-center text-on-surface font-sans font-semibold text-xs shrink-0">
                                                        {String(new Date(t.date).getUTCDate()).padStart(2, '0')}
                                                    </div>
                                                    <div className="min-w-0 flex-1">
                                                        <div className="text-xs font-sans font-semibold text-on-surface uppercase tracking-tight truncate pr-8" title={t.description}>{t.description || 'LOG_ITEM_STREAM'}</div>
                                                        <div className="text-[9px] text-slate-400 font-sans font-semibold uppercase tracking-widest mt-0.5">
                                                            {new Date(t.date).toLocaleDateString('pt-BR')} // SPRINT_{t.sprint}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="flex items-center justify-between sm:justify-end gap-6 w-full sm:w-auto">
                                                    <div className="font-sans font-semibold text-on-surface whitespace-nowrap text-sm">
                                                        - BRL {t.amount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                                    </div>
                                                    <div className="flex sm:hidden group-hover:flex items-center gap-2">
                                                        <button onClick={() => setEditingTransaction(t)} className="p-2 text-slate-300 hover:text-primary-tactile transition-all border border-transparent hover:border-[#e5e7eb] dark:border-white/10 rounded-soft-touch">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                        </button>
                                                        <button onClick={() => handleTwoStepDelete(`transaction_${t.id}`, () => onDeleteTransaction(t.id))} className={`p-2 rounded-soft-touch transition-all border ${pendingDeleteKey === `transaction_${t.id}` ? 'bg-rose-500 text-white border-rose-600' : 'text-slate-300 border-transparent hover:text-rose-500 hover:border-rose-100'}`}>
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    {transactions.length === 0 && (
                                        <div className="text-center py-10">
                                            <p className="text-slate-300 font-bold text-xs uppercase tracking-wider">Nenhum gasto registrado este mês</p>
                                        </div>
                                    )}
                                </div>
                            </FinanceSection>
                        </div>

                        {/* EMERGENCY & GOALS (RIGHT COLUMN) */}
                        <div className="order-3 md:order-2 space-y-6">
                            {/* Emergency Reserve Section */}
                            <div className="bg-surface p-6 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none relative overflow-hidden group">
                                <div className="mt-2">
                                    <h5 className="text-xl font-sans font-semibold text-on-surface flex items-center gap-2">
                                        RESERVA_EMERGÊNCIA
                                    </h5>
                                    <div className="flex items-end gap-2 mt-2">
                                        <div className="group/edit relative flex items-center">
                                            <span className="text-2xl font-sans font-semibold text-emerald-600">R$ </span>
                                            <input
                                                type="number"
                                                className="text-2xl font-sans font-semibold text-emerald-600 bg-transparent border-none outline-none focus:ring-0 w-32 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                                value={localEmergencyCurrent}
                                                onChange={(e) => setLocalEmergencyCurrent(Number(e.target.value))}
                                                onBlur={(e) => onUpdateSettings({ ...settings, emergencyReserveCurrent: Number(e.target.value) })}
                                            />
                                        </div>
                                        <span className="text-sm font-sans font-semibold text-slate-400 mb-1">/ {emergencyReserve.target.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                    </div>
                                </div>
                                <div className="mt-4 h-2 bg-slate-200 rounded-lg overflow-hidden border border-[#e5e7eb] dark:border-white/10">
                                    <div
                                        className="h-full bg-emerald-500 transition-all duration-1000"
                                        style={{ width: `${Math.min((emergencyReserve.current / (emergencyReserve.target || 1)) * 100, 100)}%` }}
                                    ></div>
                                </div>
                                {emergencyReserve.current < emergencyReserve.target && (
                                    <p className="mt-2 text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest italic">STATUS: RESERVA_PENDENTE</p>
                                )}
                            </div>

                            <div className="">
                                <FinanceSection title="Metas em Cascata" disableCollapse>
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
                                            className="bg-primary-tactile/10 text-primary-tactile border border-primary-tactile/20 px-4 py-2 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest hover:bg-primary-tactile hover:text-white transition-all"
                                        >
                                               + ADD_NEW_GOAL
                                        </button>
                                    </div>

                                    {sortedGoals.length > 0 ? (
                                        <div className="space-y-4">
                                            {sortedGoals.map((goal, idx) => (
                                                <div key={goal.id} className={`p-4 rounded-lg border transition-all relative group ${idx === 0 ? 'bg-surface border-primary-tactile border-2' : 'bg-surface border-[#e5e7eb] dark:border-white/10 opacity-80 hover:opacity-100'}`}>
                                                    <div className="flex flex-col gap-2">
                                                        {/* Setas de reordenação */}
                                                        <div className="absolute left-2 top-1/2 -translate-y-1/2 flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                                                            <button
                                                                onClick={() => swapGoals(idx, idx - 1)}
                                                                disabled={idx === 0}
                                                                className="p-1 rounded-soft-touch hover:bg-slate-100 disabled:opacity-20 transition-all"
                                                                title="Mover para cima"
                                                            >
                                                                <svg className="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 15l7-7 7 7" /></svg>
                                                            </button>
                                                            <button
                                                                onClick={() => swapGoals(idx, idx + 1)}
                                                                disabled={idx === sortedGoals.length - 1}
                                                                className="p-1 rounded-soft-touch hover:bg-slate-100 disabled:opacity-20 transition-all"
                                                                title="Mover para baixo"
                                                            >
                                                                <svg className="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                                                            </button>
                                                        </div>

                                                        {/* Badge P1 + Lixeira */}
                                                        <div className="absolute right-3 top-3 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                                                            <div className="bg-slate-100 text-slate-500 text-[8px] font-sans font-semibold px-1.5 py-0.5 rounded-lg border border-[#e5e7eb] dark:border-white/10 uppercase tracking-widest">{`PRIORITY_${idx + 1}`}</div>
                                                            <button
                                                                onClick={() => handleTwoStepDelete(`goal_${goal.id}`, () => onDeleteGoal(goal.id))}
                                                                className={`p-1.5 rounded-soft-touch transition-all ${pendingDeleteKey === `goal_${goal.id}` ? 'bg-accent-tactile text-white scale-110' : 'text-slate-300 hover:text-accent-tactile'}`}
                                                                title={pendingDeleteKey === `goal_${goal.id}` ? 'Confirmar exclusão' : 'Excluir meta'}
                                                            >
                                                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                            </button>
                                                        </div>

                                                        {/* Conteúdo principal */}
                                                        <div className="w-full pl-6">
                                                            <textarea
                                                                defaultValue={goal.name}
                                                                rows={1}
                                                                className="w-full bg-transparent border-none p-0 font-sans font-semibold text-on-surface text-lg outline-none focus:ring-0 rounded-lg transition-all resize-none overflow-hidden leading-snug pr-16"
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
                                                                <span className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest">R$ {goal.currentAmount.toLocaleString('pt-BR', { minimumFractionDigits: 0 })} DE</span>
                                                                <input
                                                                    type="number"
                                                                    className="bg-transparent border-none p-0 text-[10px] font-sans font-semibold text-on-surface w-24 outline-none focus:ring-0 rounded-lg"
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
                                                        <div className="h-1 bg-slate-100 rounded-lg overflow-hidden w-full border border-[#e5e7eb] dark:border-white/10">
                                                            <div
                                                                className={`h-full transition-all duration-1000 ${idx === 0 ? 'bg-primary-tactile' : 'bg-slate-400'}`}
                                                                style={{ width: `${Math.min((goal.currentAmount / goal.targetAmount) * 100, 100)}%` }}
                                                            ></div>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="p-8 border border-dashed border-[#e5e7eb] dark:border-white/10 rounded-lg text-center">
                                            <p className="text-slate-400 font-sans font-semibold uppercase text-[10px]">NO_GOALS_DEFINED</p>
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
                        <div className="lg:col-span-2 bg-surface p-8 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none flex flex-col justify-between relative overflow-hidden group">
                            <div className="relative z-10">
                                <div className="mb-6">
                                    <h4 className="text-[10px] font-sans font-semibold text-slate-400 uppercase tracking-[0.2em]">COMPARATIVO_MENSAL / REPORT</h4>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                    <div>
                                        <div className="text-[10px] font-sans font-semibold text-emerald-600 uppercase mb-2 tracking-widest flex items-center gap-2">
                                            // TOTAL_PREVISTO
                                            {prevIncome > 0 && (
                                                <span className={`text-[9px] px-1.5 py-0.5 border border-[#e5e7eb] dark:border-white/10 ${incomeOverallTotal >= prevIncome ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                                                    {incomeOverallTotal >= prevIncome ? 'UP' : 'DOWN'} {Math.round(Math.abs((incomeOverallTotal - prevIncome) / prevIncome) * 100)}%
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-4xl font-sans font-semibold text-on-surface tracking-tighter">
                                            R$ {incomeOverallTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-[10px] font-sans font-semibold text-accent-tactile uppercase mb-2 tracking-widest flex items-center gap-2">
                                            // TOTAL_CONTAS
                                            {prevBills > 0 && (
                                                <span className={`text-[9px] px-1.5 py-0.5 border border-[#e5e7eb] dark:border-white/10 ${currentTotalBills <= prevBills ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                                                    {currentTotalBills <= prevBills ? 'DOWN' : 'UP'} {Math.round(Math.abs((currentTotalBills - prevBills) / prevBills) * 100)}%
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-4xl font-sans font-semibold text-on-surface tracking-tighter">
                                            R$ {currentTotalBills.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-8">
                                    <div className="flex justify-between text-[10px] font-sans font-semibold uppercase tracking-widest mb-2">
                                        <span className="text-slate-400">COMPROMETIMENTO_RENDA ({Math.round((currentTotalBills / (incomeOverallTotal || 1)) * 100)}%)</span>
                                        <span className="text-slate-300 italic">THRESHOLD: 70%</span>
                                    </div>
                                    <div className="h-2 bg-slate-100 rounded-lg overflow-hidden border border-[#e5e7eb] dark:border-white/10">
                                        <div
                                            className={`h-full transition-all duration-1000 ${incomeOverallTotal > 0 && (currentTotalBills / incomeOverallTotal) > 0.7 ? 'bg-accent-tactile' : 'bg-emerald-500'}`}
                                            style={{ width: `${Math.min(incomeOverallTotal > 0 ? (currentTotalBills / incomeOverallTotal) * 100 : 0, 100)}%` }}
                                        ></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className={`p-8 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none flex flex-col justify-center items-center text-center transition-all ${incomeOverallTotal - currentTotalBills >= 0 ? 'bg-on-surface text-surface' : 'bg-accent-tactile text-white'}`}>
                            <h4 className="text-[10px] font-sans font-semibold uppercase tracking-[0.2em] mb-2 opacity-60">SALDO_PROJETADO</h4>
                            <div className="text-4xl md:text-5xl font-sans font-semibold tracking-tighter mb-2">
                                R$ {(incomeOverallTotal - currentTotalBills).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                            </div>
                            <p className="text-[10px] font-sans font-semibold uppercase opacity-40 tracking-widest">NET_REMAINING_BALANCE</p>
                        </div>
                    </div>

                    <div className="h-px bg-slate-100 w-full opacity-50" />

                    {/* SEÇÃO DE RENDAS / GANHOS */}
                    <FinanceSection title="Rendas e Rendimentos">
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                            <p className="text-slate-400 font-sans text-[10px] font-bold uppercase tracking-widest">REVENUE_STREAMS / ACTIVE_INCOME</p>
                            <div className="flex gap-3 w-full md:w-auto">
                                <button
                                    onClick={() => setIsNFSeGeneratorOpen(true)}
                                    className="flex-1 md:flex-none border border-[#e5e7eb] dark:border-white/10 bg-surface hover:bg-slate-100 text-on-surface px-5 py-2 flex items-center justify-center gap-2 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest transition-all"
                                >
                                    <svg className="w-4 h-4 text-primary-tactile" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                    NFS-e_GEN
                                </button>
                                <button
                                    onClick={() => setIsManagingIncomeRubrics(!isManagingIncomeRubrics)}
                                    className={`flex-1 md:flex-none px-5 py-2 flex items-center justify-center rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest transition-all border ${isManagingIncomeRubrics ? 'bg-on-surface text-surface border-on-surface' : 'bg-surface text-on-surface border-[#e5e7eb] dark:border-white/10 hover:bg-slate-100'}`}
                                >
                                    {isManagingIncomeRubrics ? 'CLOSE_RESOURCES' : 'MANAGE_RESOURCES'}
                                </button>
                                <button onClick={() => {
                                    setNewIncome({ category: settings.incomeCategories?.[0] || 'Renda Principal' });
                                    setIsAddingIncome(true);
                                }} className="flex-1 md:flex-none bg-primary-tactile text-white px-5 py-2 flex items-center justify-center rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest transition-all">
                                    + ADD_ENTRY
                                </button>
                            </div>
                        </div>
                                     {/* Gestão de Rubricas de Renda Industrial */}
                        {isManagingIncomeRubrics && (
                            <div className="bg-on-surface text-surface p-8 rounded-lg shadow-none animate-in fade-in slide-in-from-top-4 border-b-4 border-emerald-500">
                                <div className="flex justify-between items-center mb-10">
                                    <div>
                                        <h5 className="text-[10px] font-sans font-semibold uppercase tracking-[0.4em] text-emerald-400">// INCOME_STREAMS_REGISTRY</h5>
                                        <p className="text-emerald-300/30 text-[8px] font-sans font-semibold uppercase tracking-widest mt-1">RECURRING_REVENUE_CHANNELS</p>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
                                    {incomeRubrics.map(rubric => (
                                        <div key={rubric.id} className="bg-white/5 border border-white/10 p-5 rounded-lg flex justify-between items-center group hover:bg-white/10 transition-all">
                                            <div>
                                                <div className="text-[8px] font-sans font-semibold text-emerald-400 uppercase tracking-widest mb-1">{rubric.category} // TAG</div>
                                                <div className="text-sm font-sans font-semibold uppercase tracking-tight">{rubric.description}</div>
                                                <div className="text-[9px] text-white/30 font-sans font-semibold uppercase tracking-widest mt-2 flex items-center gap-2">
                                                    ETA: DAY_{rubric.expectedDay}
                                                    {rubric.defaultAmount ? ` // BRL ${rubric.defaultAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : ' // VARIABLE_VAL'}
                                                </div>
                                            </div>
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => {
                                                        setEditingIncomeRubric(rubric);
                                                        setNewIncomeRubric(rubric);
                                                    }}
                                                    className="p-2 text-white/20 hover:text-emerald-400 transition-all opacity-0 group-hover:opacity-100 border border-transparent hover:border-white/10"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                </button>
                                                <button onClick={() => handleTwoStepDelete(`income_rubric_${rubric.id}`, () => onDeleteIncomeRubric(rubric.id))} className={`p-2 rounded-soft-touch transition-all opacity-0 group-hover:opacity-100 border ${pendingDeleteKey === `income_rubric_${rubric.id}` ? 'bg-rose-500 text-white opacity-100 border-rose-600' : 'text-white/20 border-transparent hover:text-rose-400 hover:border-rose-900/30'}`}>
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="bg-white/5 p-8 rounded-lg border border-white/10">
                                    <h6 className="text-[10px] font-sans font-semibold text-white/30 uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
                                        <span className="w-2 h-2 bg-emerald-500"></span>
                                        {editingIncomeRubric ? 'UPDATE_RESOURCE_NODE' : 'REGISTER_NEW_STREAM'}
                                    </h6>
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
                                        <input
                                            type="text"
                                            placeholder="STREAM_IDENTIFIER"
                                            className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold focus:ring-1 focus:ring-emerald-500 outline-none text-white placeholder:text-white/10"
                                            value={newIncomeRubric.description || ''}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, description: e.target.value })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="EXPECTED_DAY"
                                            className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold focus:ring-1 focus:ring-emerald-500 outline-none text-white placeholder:text-white/10"
                                            value={newIncomeRubric.expectedDay || ''}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, expectedDay: Number(e.target.value) })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="BASELINE_VALUE"
                                            className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold focus:ring-1 focus:ring-emerald-500 outline-none text-white placeholder:text-white/10"
                                            value={newIncomeRubric.defaultAmount || ''}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, defaultAmount: e.target.value ? Number(e.target.value) : undefined })}
                                        />
                                        <select
                                            className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold focus:ring-1 focus:ring-emerald-500 outline-none text-white [color-scheme:dark]"
                                            value={newIncomeRubric.category}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, category: e.target.value })}
                                        >
                                            {(settings.incomeCategories || ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']).map(cat => (
                                                <option key={cat} value={cat} className="bg-on-surface text-white uppercase">{cat}</option>
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
                                                className="flex-1 bg-white text-on-surface hover:bg-emerald-500 hover:text-white rounded-soft-touch px-4 py-3 text-[10px] font-sans font-semibold uppercase tracking-widest transition-all"
                                            >
                                                {editingIncomeRubric ? 'COMMIT_UP' : 'INITIALIZE'}
                                            </button>
                                            {editingIncomeRubric && (
                                                <button
                                                    onClick={() => {
                                                        setEditingIncomeRubric(null);
                                                        setNewIncomeRubric({ category: 'Renda Principal' });
                                                    }}
                                                    className="bg-white/10 hover:bg-white/20 text-white rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold uppercase tracking-widest transition-all"
                                                >
                                                    ✕
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Formulário de Registro de Recebimento Industrial */}
                        {isAddingIncome && (
                            <div className="bg-surface p-8 rounded-lg border border-emerald-500 shadow-none space-y-6 animate-in slide-in-from-top-4 border-l-4">
                                <h5 className="text-[10px] font-sans font-semibold text-emerald-600 uppercase tracking-[0.3em] flex items-center gap-2">
                                    <span className="w-1.5 h-1.5 bg-emerald-600"></span>
                                    LOG_NEW_REVENUE_EVENT
                                </h5>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                                    <div className="space-y-1">
                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">DESCRIPTION</label>
                                        <input type="text" placeholder="REVENUE_SOURCE_LOG" className="w-full px-4 py-3 rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-emerald-500" value={newIncome.description || ''} onChange={(e) => setNewIncome({ ...newIncome, description: e.target.value })} />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">VALUE_BRL</label>
                                        <div className="flex gap-0">
                                            <span className="px-3 py-3 bg-emerald-50 border border-r-0 border-[#e5e7eb] dark:border-white/10 font-sans font-semibold text-emerald-600 text-xs">R$</span>
                                            <input type="number" placeholder="0.00" className="w-full px-4 py-3 rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-emerald-500" value={newIncome.amount || ''} onChange={(e) => setNewIncome({ ...newIncome, amount: Number(e.target.value) })} />
                                        </div>
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">EXPECTED_DAY</label>
                                        <input type="number" placeholder="1-31" max={31} min={1} className="w-full px-4 py-3 rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-emerald-500" value={newIncome.day || ''} onChange={(e) => setNewIncome({ ...newIncome, day: Number(e.target.value) })} />
                                    </div>
                                    <div className="flex items-end">
                                        <label className="w-full px-4 py-3 rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-slate-50 font-sans font-semibold flex items-center gap-3 text-slate-600 cursor-pointer hover:bg-slate-100 transition-all">
                                            <input type="checkbox" checked={Boolean(newIncome.isReceived)} onChange={(e) => setNewIncome({ ...newIncome, isReceived: e.target.checked })} className="w-4 h-4 rounded-lg border-[#e5e7eb] dark:border-white/10 text-emerald-600 focus:ring-0 bg-transparent" />
                                            <span className="text-[10px] uppercase tracking-widest">STATUS_RECEIVED</span>
                                        </label>
                                    </div>
                                </div>
                                <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
                                    <button onClick={() => setIsAddingIncome(false)} className="px-6 py-3 border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest text-slate-400 hover:text-on-surface hover:bg-slate-50 transition-all">ABORT_STREAM</button>
                                    <button
                                        onClick={async () => {
                                            if (newIncome.description && newIncome.amount && newIncome.day) {
                                                await onAddIncomeEntry({
                                                    ...newIncome as Omit<IncomeEntry, 'id'>,
                                                    month: currentMonth,
                                                    year: currentYear,
                                                    category: newIncome.category || (settings.incomeCategories?.[0] || 'Renda Principal'),
                                                    isReceived: Boolean(newIncome.isReceived)
                                                });
                                                setIsAddingIncome(false);
                                                setNewIncome({ category: 'Renda Principal', isReceived: false });
                                            }
                                        }}
                                        className="bg-on-surface text-white px-10 py-3 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest hover:bg-emerald-600 transition-all"
                                    >
                                        COMMIT_REVENUE
                                    </button>
                                </div>
                            </div>
                        )}

                        {pendingIncomeRubrics.length > 0 && (
                            <div className="mb-6 rounded-lg md:rounded-[2rem] border border-emerald-900/20 bg-emerald-950 p-5 text-white shadow-none md:shadow-xl">
                                <div className="mb-3">
                                    <h5 className="text-sm font-bold uppercase tracking-wider text-emerald-100">Fontes sem lancamento no periodo</h5>
                                    <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-300/50">Clique em uma fonte para pre-preencher um novo ganho</p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {pendingIncomeRubrics.map(rubric => (
                                        <button
                                            key={rubric.id}
                                            onClick={() => {
                                                setNewIncome({
                                                    description: rubric.description,
                                                    category: rubric.category,
                                                    day: rubric.expectedDay,
                                                    amount: rubric.defaultAmount,
                                                    rubricId: rubric.id,
                                                    isReceived: false
                                                });
                                                setIsAddingIncome(true);
                                            }}
                                            className="rounded-xl border border-white/10 bg-white/10 px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors hover:bg-white/20"
                                        >
                                            {rubric.description}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="mb-10 grid grid-cols-1 gap-6 md:grid-cols-3">
                            <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-emerald-50/50 p-6 shadow-none">
                                <div className="text-[9px] font-sans font-semibold uppercase tracking-[0.2em] text-emerald-600 mb-2">// TOTAL_RECEIVED</div>
                                <div className="text-3xl font-sans font-semibold tracking-tighter text-emerald-700">{formatCurrency(incomeReceivedTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-widest text-emerald-600/60">{currentMonthIncomeEntries.filter(entry => entry.isReceived).length} NODES_ACKNOWLEDGED</div>
                            </div>
                            <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-amber-50/50 p-6 shadow-none">
                                <div className="text-[9px] font-sans font-semibold uppercase tracking-[0.2em] text-amber-600 mb-2">// TOTAL_PENDING</div>
                                <div className="text-3xl font-sans font-semibold tracking-tighter text-amber-700">{formatCurrency(incomePendingTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-widest text-amber-600/60">{currentMonthIncomeEntries.filter(entry => !entry.isReceived).length} NODES_IN_TRANSIT</div>
                            </div>
                            <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-slate-50 p-6 shadow-none">
                                <div className="text-[9px] font-sans font-semibold uppercase tracking-[0.2em] text-slate-500 mb-2">// OVERALL_TOTAL</div>
                                <div className="text-3xl font-sans font-semibold tracking-tighter text-on-surface">{formatCurrency(incomeOverallTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-widest text-slate-400">{currentMonthIncomeEntries.length} TOTAL_ENTRIES_PERIOD</div>
                            </div>
                        </div>

                        <div className="mb-6 overflow-hidden rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-surface shadow-none">
                            <div className="border-b border-[#e5e7eb] dark:border-white/10 bg-slate-50 p-6">
                                <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
                                    <div className="space-y-1">
                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">QUERY_FILTER</label>
                                        <input
                                            type="text"
                                            placeholder="SEARCH_BY_DESCRIPTION"
                                            value={incomeSearch}
                                            onChange={(e) => setIncomeSearch(e.target.value)}
                                            className="w-full rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2.5 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">STATUS_FILTER</label>
                                        <select value={incomeStatusFilter} onChange={(e) => setIncomeStatusFilter(e.target.value as 'all' | 'received' | 'pending')} className="w-full rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2.5 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500">
                                            <option value="all">ALL_STATUS</option>
                                            <option value="received">RECEIVED</option>
                                            <option value="pending">PENDING</option>
                                        </select>
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">TAG_FILTER</label>
                                        <select value={incomeCategoryFilter} onChange={(e) => setIncomeCategoryFilter(e.target.value)} className="w-full rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2.5 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500">
                                            <option value="all">ALL_CATEGORIES</option>
                                            {(settings.incomeCategories || []).map(cat => (
                                                <option key={cat} value={cat}>{cat}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="flex items-end">
                                        <div className="w-full flex items-center justify-center rounded-soft-touch bg-on-surface text-white px-4 py-2.5 text-[10px] font-sans font-semibold uppercase tracking-[0.2em]">
                                            COUNT: {visibleIncomeEntries.length}
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="min-w-full text-sm">
                                    <thead className="bg-slate-100 text-[10px] font-sans uppercase tracking-widest text-slate-500 border-b border-[#e5e7eb] dark:border-white/10">
                                        <tr>
                                            <th className="px-4 py-3 text-left font-bold">ACK</th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('description')} className="flex items-center gap-2">DESCRIPTION <span>{incomeSort.key === 'description' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('category')} className="flex items-center gap-2">CATEGORY <span>{incomeSort.key === 'category' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('day')} className="flex items-center gap-2">ETA <span>{incomeSort.key === 'day' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('amount')} className="flex items-center gap-2">AMOUNT <span>{incomeSort.key === 'amount' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('status')} className="flex items-center gap-2">STATUS <span>{incomeSort.key === 'status' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-right font-bold">ACTIONS</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-[#e5e7eb] dark:divide-white/10 bg-white">
                                        {visibleIncomeEntries.map(entry => {
                                            const prevEntry = incomeEntries.find(e =>
                                                e.description === entry.description &&
                                                e.month === (currentMonth === 0 ? 11 : currentMonth - 1) &&
                                                e.year === (currentMonth === 0 ? currentYear - 1 : currentYear)
                                            );
                                            const diff = prevEntry ? entry.amount - prevEntry.amount : 0;
                                            const isExpanded = expandedIncomeId === entry.id;

                                            return (
                                                <React.Fragment key={entry.id}>
                                                    <tr className={`cursor-pointer transition-colors font-sans ${isExpanded ? 'bg-slate-50 text-on-surface' : 'hover:bg-slate-50 text-on-surface'}`} onClick={() => setExpandedIncomeId(isExpanded ? null : entry.id)}>
                                                        <td className="px-4 py-4">
                                                            <input type="checkbox" checked={entry.isReceived} onClick={(e) => e.stopPropagation()} onChange={() => onUpdateIncomeEntry({ ...entry, isReceived: !entry.isReceived })} className="h-4 w-4 rounded-lg border-[#e5e7eb] dark:border-white/10 text-primary-tactile focus:ring-0 bg-transparent" />
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <div className="font-bold text-xs">{entry.description}</div>
                                                            {entry.rubricId && <div className="text-[8px] font-bold uppercase tracking-widest text-slate-400">// LINKED_RESOURCE</div>}
                                                        </td>
                                                        <td className="px-4 py-4 font-bold text-[10px] text-slate-500 uppercase">{entry.category || 'INCOME'}</td>
                                                        <td className="px-4 py-4 font-bold text-[10px] text-slate-500 uppercase">DAY_{entry.day}</td>
                                                        <td className="px-4 py-4">
                                                            <div className="font-bold text-xs text-emerald-600">{formatCurrency(entry.amount)}</div>
                                                            {diff !== 0 && <div className={`text-[9px] font-bold ${diff > 0 ? 'text-emerald-600' : 'text-accent-tactile'}`}>{diff > 0 ? '+' : '-'} {formatCurrency(Math.abs(diff))}</div>}
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <span className={`inline-flex border border-[#e5e7eb] dark:border-white/10 px-2 py-0.5 text-[8px] font-bold uppercase tracking-widest ${entry.isReceived ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                                                                {entry.isReceived ? 'OK' : 'PENDING'}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <div className="flex items-center justify-end gap-2">
                                                                <button onClick={(e) => { e.stopPropagation(); setExpandedIncomeId(isExpanded ? null : entry.id); }} className="rounded-soft-touch p-1 text-slate-300 hover:text-on-surface">
                                                                    <svg className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
                                                                </button>
                                                                <button onClick={(e) => { e.stopPropagation(); handleTwoStepDelete(`income_entry_${entry.id}`, () => onDeleteIncomeEntry(entry.id)); }} className={`rounded-soft-touch p-1 transition-colors ${pendingDeleteKey === `income_entry_${entry.id}` ? 'bg-accent-tactile text-white' : 'text-slate-200 hover:text-accent-tactile'}`}>
                                                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                    {isExpanded && (
                                                        <tr className="bg-slate-50">
                                                            <td colSpan={7} className="px-4 py-6 border-b border-[#e5e7eb] dark:border-white/10">
                                                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
                                                                    <div className="space-y-1">
                                                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest block">DESCRIPTION_ID</label>
                                                                        <input type="text" defaultValue={entry.description} onBlur={(e) => onUpdateIncomeEntry({ ...entry, description: e.target.value })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500" />
                                                                    </div>
                                                                    <div className="space-y-1">
                                                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest block">AMOUNT_VAL</label>
                                                                        <input type="number" defaultValue={entry.amount} onBlur={(e) => onUpdateIncomeEntry({ ...entry, amount: Number(e.target.value) })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500" />
                                                                    </div>
                                                                    <div className="space-y-1">
                                                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest block">ETA_DAY</label>
                                                                        <input type="number" min={1} max={31} defaultValue={entry.day} onBlur={(e) => onUpdateIncomeEntry({ ...entry, day: Number(e.target.value) })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500" />
                                                                    </div>
                                                                    <div className="space-y-1">
                                                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest block">CATEGORY_TAG</label>
                                                                        <select defaultValue={entry.category} onBlur={(e) => onUpdateIncomeEntry({ ...entry, category: e.target.value })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500">
                                                                            {(settings.incomeCategories || ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']).map(cat => (
                                                                                <option key={cat} value={cat}>{cat}</option>
                                                                            ))}
                                                                        </select>
                                                                    </div>
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    )}
                                                </React.Fragment>
                                            );
                                        })}
                                        {visibleIncomeEntries.length === 0 && (
                                            <tr>
                                                <td colSpan={7} className="px-4 py-12 text-center text-[10px] font-sans font-semibold uppercase tracking-widest text-slate-400">NO_RECORDS_FOUND / FILTER_MISMATCH</td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 gap-6 mb-10">
                            {/* Rubricas de Renda Pendentes Industrial */}
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                {incomeRubrics
                                    .filter(rubric => !incomeEntries.some(entry =>
                                        entry.rubricId === rubric.id &&
                                        entry.month === currentMonth &&
                                        entry.year === currentYear
                                    ))
                                    .map(rubric => (
                                        <div key={rubric.id} className="bg-white border border-[#e5e7eb] dark:border-white/10 p-6 rounded-lg shadow-none transition-all group hover:bg-slate-50 border-l-4 border-l-emerald-500">
                                            <div className="text-[10px] font-sans font-semibold uppercase tracking-widest mb-3 px-2 py-0.5 rounded-lg w-fit bg-emerald-50 text-emerald-600 border border-emerald-100">{rubric.category} // TAG</div>
                                            <h5 className="text-sm font-sans font-semibold text-on-surface leading-tight uppercase tracking-tight">{rubric.description}</h5>
                                            <div className="mt-4 text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-6 flex items-center gap-2">
                                                <span className="w-1.5 h-1.5 rounded-lg bg-emerald-500 animate-pulse" />
                                                WAITING_REVENUE_LOG
                                            </div>
                                            <button
                                                onClick={() => {
                                                    setNewIncome({
                                                        description: rubric.description,
                                                        category: rubric.category,
                                                        day: rubric.expectedDay,
                                                        amount: rubric.defaultAmount,
                                                        rubricId: rubric.id,
                                                        isReceived: false
                                                    });
                                                    setIsAddingIncome(true);
                                                }}
                                                className="w-full bg-on-surface text-surface py-3 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest hover:bg-emerald-600 transition-all flex items-center justify-center gap-2"
                                            >
                                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                                                INITIALIZE_LOG
                                            </button>
                                        </div>
                                    ))
                                }
                            </div>

                            {/* Rendas Efetivadas (Compactas) Industrial */}
                            <div className="space-y-4">
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
                                            <div key={entry.id} className="bg-white p-5 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none flex items-center justify-between group hover:bg-slate-50 transition-all">
                                                <div className="flex items-center gap-6">
                                                    <div className="w-10 h-10 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600 font-sans font-semibold text-xs">
                                                        ACK
                                                    </div>
                                                    <div>
                                                        <div className="text-[8px] font-sans font-semibold text-emerald-600/50 uppercase tracking-widest mb-1">{entry.category || 'INCOME'} // NODE</div>
                                                        <div className="text-sm font-sans font-semibold text-on-surface leading-none uppercase tracking-tight">{entry.description}</div>
                                                        <div className="text-[9px] text-slate-400 font-sans font-semibold mt-2 flex items-center gap-3">
                                                            ETA: DAY_{entry.day}
                                                            <span className={`px-2 py-0.5 rounded-lg text-[8px] font-sans font-semibold uppercase tracking-widest border ${entry.isReceived ? 'bg-emerald-50 text-emerald-600 border-emerald-100' : 'bg-amber-50 text-amber-600 border-amber-100'}`}>
                                                                {entry.isReceived ? 'CONFIRMED' : 'IN_TRANSIT'}
                                                            </span>
                                                            {diff !== 0 && (
                                                                <span className={`text-[8px] font-sans font-semibold ${diff > 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                                                    {diff > 0 ? '▲' : '▼'} BRL {Math.abs(diff).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                                                </span>
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-6">
                                                    <input
                                                        type="checkbox"
                                                        checked={entry.isReceived}
                                                        onChange={() => onUpdateIncomeEntry({ ...entry, isReceived: !entry.isReceived })}
                                                        className="w-4 h-4 rounded-lg border-[#e5e7eb] dark:border-white/10 text-emerald-600 focus:ring-0 bg-transparent"
                                                        title={entry.isReceived ? 'Marcar como nao recebido' : 'Marcar como recebido'}
                                                    />
                                                    <div className="text-xl font-sans font-semibold text-emerald-600 tracking-tighter">BRL {entry.amount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</div>
                                                    <button onClick={() => handleTwoStepDelete(`income_entry_${entry.id}`, () => onDeleteIncomeEntry(entry.id))} className={`p-2 rounded-soft-touch transition-all opacity-0 group-hover:opacity-100 border ${pendingDeleteKey === `income_entry_${entry.id}` ? 'bg-rose-500 text-white opacity-100 border-rose-600' : 'text-slate-200 border-transparent hover:text-rose-400 hover:border-rose-900/30'}`}>
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                    </button>
                                                </div>
                                            </div>
                                        );
                                    })
                                }
                            </div>
                        </div>
                    </FinanceSection>

                    <div className="h-px bg-slate-100 w-full opacity-50" />

                    {/* SEÇÃO DE CONTAS / OBRIGAÇÕES */}
                    <FinanceSection title="Obrigações e Despesas">
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-10">
                            <div>
                                <h5 className="text-[10px] font-sans font-semibold text-slate-400 uppercase tracking-[0.3em]">// OBLIGATION_MANAGEMENT_STREAM</h5>
                                <p className="text-slate-300 text-[8px] font-sans font-semibold uppercase tracking-widest mt-1">LIABILITY_SETTLEMENT_HUB</p>
                            </div>
                            <div className="flex gap-3 w-full md:w-auto">
                                <button
                                    onClick={() => setIsManagingRubrics(!isManagingRubrics)}
                                    className={`flex-1 md:flex-none px-6 py-3 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest transition-all border ${isManagingRubrics ? 'bg-on-surface text-white border-on-surface shadow-none' : 'bg-white text-slate-600 border-[#e5e7eb] dark:border-white/10 hover:bg-slate-50 shadow-none'}`}
                                >
                                    {isManagingRubrics ? 'CLOSE_TAXONOMY' : 'MANAGE_RUBRICS'}
                                </button>
                                <button onClick={() => {
                                    setNewBill({ category: settings.billCategories?.[0] || 'Conta Fixa' });
                                    setIsAddingBill(true);
                                }} className="flex-1 md:flex-none bg-primary-tactile text-white px-6 py-3 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest transition-all hover:bg-blue-700 shadow-none">
                                    + ADD_OBLIGATION
                                </button>
                            </div>
                        </div>

                        {/* Gestão de Rubricas Industrial */}
                        {isManagingRubrics && (
                            <div className="bg-on-surface text-surface p-8 rounded-lg shadow-none animate-in fade-in slide-in-from-top-4 border-b-4 border-primary-tactile mb-10">
                                <div className="flex justify-between items-center mb-10">
                                    <div>
                                        <h5 className="text-[10px] font-sans font-semibold uppercase tracking-[0.4em] text-primary-tactile">// RECURRING_OBLIGATION_TAXONOMY</h5>
                                        <p className="text-white/30 text-[8px] font-sans font-semibold uppercase tracking-widest mt-1">MONTHLY_LIABILITY_BASELINE</p>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
                                    {billRubrics.map(rubric => (
                                        <div key={rubric.id} className="bg-white/5 border border-white/10 p-5 rounded-lg flex justify-between items-center group hover:bg-white/10 transition-all">
                                            <div>
                                                <div className="text-[8px] font-sans font-semibold text-primary-tactile uppercase tracking-widest mb-1">{rubric.category} // TAG</div>
                                                <div className="text-sm font-sans font-semibold uppercase tracking-tight">{rubric.description}</div>
                                                <div className="text-[9px] text-white/30 font-sans font-semibold uppercase tracking-widest mt-2 flex items-center gap-2">
                                                    DUE: DAY_{rubric.dueDay}
                                                    {rubric.defaultAmount ? ` // BRL ${rubric.defaultAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : ' // VARIABLE_VAL'}
                                                    {rubric.pixCode && ' // PIX_LINKED'}
                                                </div>
                                            </div>
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => {
                                                        setEditingRubric(rubric);
                                                        setNewRubric(rubric);
                                                    }}
                                                    className="p-2 text-white/20 hover:text-primary-tactile transition-all opacity-0 group-hover:opacity-100 border border-transparent hover:border-white/10"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                </button>
                                                <button onClick={() => handleTwoStepDelete(`rubric_${rubric.id}`, () => onDeleteRubric(rubric.id))} className={`p-2 rounded-soft-touch transition-all opacity-0 group-hover:opacity-100 border ${pendingDeleteKey === `rubric_${rubric.id}` ? 'bg-rose-500 text-white opacity-100 border-rose-600' : 'text-white/20 border-transparent hover:text-rose-400 hover:border-rose-900/30'}`}>
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="bg-white/5 p-8 rounded-lg border border-white/10">
                                    <h6 className="text-[10px] font-sans font-semibold text-white/30 uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
                                        <span className="w-2 h-2 bg-primary-tactile"></span>
                                        {editingRubric ? 'UPDATE_RUBRIC_NODE' : 'REGISTER_NEW_OBLIGATION'}
                                    </h6>
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-6">
                                        <input
                                            type="text"
                                            placeholder="OBLIGATION_NAME"
                                            className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-white placeholder:text-white/10"
                                            value={newRubric.description || ''}
                                            onChange={e => setNewRubric({ ...newRubric, description: e.target.value })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="DUE_DAY"
                                            className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-white placeholder:text-white/10"
                                            value={newRubric.dueDay || ''}
                                            onChange={e => setNewRubric({ ...newRubric, dueDay: Number(e.target.value) })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="FIXED_VAL_OPT"
                                            className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-white placeholder:text-white/10"
                                            value={newRubric.defaultAmount || ''}
                                            onChange={e => setNewRubric({ ...newRubric, defaultAmount: e.target.value ? Number(e.target.value) : undefined })}
                                        />
                                        <select
                                            className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-white [color-scheme:dark]"
                                            value={newRubric.category}
                                            onChange={e => setNewRubric({ ...newRubric, category: e.target.value })}
                                        >
                                            {(settings.billCategories || ['Conta Fixa', 'Poupança', 'Investimento']).map(cat => (
                                                <option key={cat} value={cat} className="bg-on-surface text-white uppercase">{cat}</option>
                                            ))}
                                        </select>
                                        <input
                                            type="text"
                                            placeholder="PIX_KEY_OPT"
                                            className="bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-white placeholder:text-white/10 lg:col-span-1"
                                            value={newRubric.pixCode || ''}
                                            onChange={e => setNewRubric({ ...newRubric, pixCode: e.target.value })}
                                        />
                                        <div className="flex gap-2">
                                            <button
                                                onClick={async () => {
                                                    if (newRubric.description && newRubric.dueDay) {
                                                        if (editingRubric) {
                                                            (onUpdateRubric as any)({ ...newRubric, id: editingRubric.id });
                                                        } else {
                                                            await onAddRubric(newRubric as BillRubric);
                                                        }
                                                        setNewRubric({ category: 'Conta Fixa' });
                                                        setEditingRubric(null);
                                                    }
                                                }}
                                                className="flex-1 bg-white text-on-surface hover:bg-primary-tactile hover:text-white rounded-soft-touch px-4 py-3 text-[10px] font-sans font-semibold uppercase tracking-widest transition-all"
                                            >
                                                {editingRubric ? 'COMMIT_UP' : 'INITIALIZE'}
                                            </button>
                                            {editingRubric && (
                                                <button
                                                    onClick={() => {
                                                        setEditingRubric(null);
                                                        setNewRubric({ category: 'Conta Fixa' });
                                                    }}
                                                    className="bg-white/10 hover:bg-white/20 text-white rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold uppercase tracking-widest transition-all"
                                                >
                                                    ✕
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}

                        {isAddingBill && (
                            <div className="mb-6 bg-surface p-6 rounded-lg border-2 border-primary-tactile shadow-none animate-in fade-in slide-in-from-top-2">
                                <div className="mb-4">
                                    <h4 className="text-[10px] font-sans font-semibold text-primary-tactile uppercase tracking-widest">// NEW_ENTRY_OBLIGATION</h4>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                                    <input type="text" placeholder="DESCRIPTION" className="px-4 py-2 rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.description || ''} onChange={(e) => setNewBill({ ...newBill, description: e.target.value })} />
                                    <input type="number" placeholder="AMOUNT_BRL" className="px-4 py-2 rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.amount || ''} onChange={(e) => setNewBill({ ...newBill, amount: Number(e.target.value) })} />
                                    <select className="px-4 py-2 rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.category || ''} onChange={(e) => setNewBill({ ...newBill, category: e.target.value })}>
                                        <option value="">SELECT_CATEGORY</option>
                                        {(settings.billCategories || ['Conta Fixa', 'Poupanca', 'Investimento']).map(cat => (
                                            <option key={cat} value={cat}>{cat}</option>
                                        ))}
                                    </select>
                                    <input type="number" placeholder="DUE_DAY" max={31} min={1} className="px-4 py-2 rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.dueDay || ''} onChange={(e) => setNewBill({ ...newBill, dueDay: Number(e.target.value) })} />
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                                    <input type="text" placeholder="BARCODE_LINE" className="px-4 py-2 rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.barcode || ''} onChange={(e) => setNewBill({ ...newBill, barcode: e.target.value })} />
                                    <input type="text" placeholder="PIX_COPY_PASTE" className="px-4 py-2 rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.pixCode || ''} onChange={(e) => setNewBill({ ...newBill, pixCode: e.target.value })} />
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className={`border border-dashed rounded-lg p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${newBill.attachmentUrl ? 'border-primary-tactile bg-blue-50' : 'border-[#e5e7eb] dark:border-white/10 bg-slate-50 hover:bg-slate-100'}`} onClick={() => {
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
                                            <div className="flex items-center gap-2 text-primary-tactile font-sans font-semibold text-[10px] uppercase tracking-tighter">
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                                ATTACHMENT_LOADED
                                            </div>
                                        ) : (
                                            <div className="text-center text-slate-400">
                                                <p className="text-[10px] font-sans font-semibold uppercase tracking-widest">UPLOAD_BOLETO_PDF</p>
                                            </div>
                                        )}
                                    </div>

                                    <div className={`border border-dashed rounded-lg p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${newBill.pixQrCodeUrl ? 'border-emerald-200 bg-emerald-50' : 'border-[#e5e7eb] dark:border-white/10 bg-slate-50 hover:bg-slate-100'}`} onClick={() => {
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
                                            <div className="flex items-center gap-2 text-emerald-600 font-sans font-semibold text-[10px] uppercase tracking-tighter">
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                                PIX_QR_LOADED
                                            </div>
                                        ) : (
                                            <div className="text-center text-slate-400">
                                                <p className="text-[10px] font-sans font-semibold uppercase tracking-widest">UPLOAD_PIX_QR_IMG</p>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="flex justify-end gap-3 pt-6 border-t border-[#e5e7eb] dark:border-white/10 mt-6">
                                    <button onClick={() => setIsAddingBill(false)} className="px-6 py-2 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest text-slate-400 hover:text-on-surface transition-colors">CANCEL</button>
                                    <button onClick={handleSaveBill} disabled={uploading === true || !newBill.description || newBill.amount === undefined} className={`px-8 py-2 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest transition-all ${uploading || !newBill.description || newBill.amount === undefined ? 'bg-slate-200 text-slate-400 cursor-not-allowed' : 'bg-primary-tactile text-white'}`}>
                                        {uploading ? 'PROCESSING...' : 'SAVE_RECORD'}
                                    </button>
                                </div>
                            </div>
                        )}

                        {pendingBillRubrics.length > 0 && (
                            <div className="mb-6 rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-on-surface p-6 text-surface shadow-none">
                                <div className="mb-4">
                                    <h5 className="text-[10px] font-sans font-semibold uppercase tracking-[0.2em] opacity-60">// PENDING_RUBRICS / NO_ENTRY_DETECTED</h5>
                                    <p className="text-[8px] font-sans font-semibold uppercase tracking-widest text-white/40 mt-1 italic">ACTION_REQUIRED: INITIALIZE_PERIOD_ENTRIES</p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {pendingBillRubrics.map(rubric => (
                                        <button
                                            key={rubric.id}
                                            onClick={() => {
                                                setNewBill({
                                                    description: rubric.description,
                                                    category: rubric.category,
                                                    dueDay: rubric.dueDay,
                                                    amount: rubric.defaultAmount,
                                                    pixCode: rubric.pixCode,
                                                    rubricId: rubric.id
                                                });
                                                setIsAddingBill(true);
                                            }}
                                            className="rounded-soft-touch border border-white/20 bg-white/5 px-4 py-2 text-[10px] font-sans font-semibold uppercase tracking-widest transition-all hover:bg-white/10 hover:border-white/40"
                                        >
                                            {rubric.description}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="mb-10 grid grid-cols-1 gap-6 md:grid-cols-3">
                            <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-emerald-50/50 p-6 shadow-none">
                                <div className="text-[9px] font-sans font-semibold uppercase tracking-[0.2em] text-emerald-600 mb-2">// TOTAL_SETTLED</div>
                                <div className="text-3xl font-sans font-semibold tracking-tighter text-emerald-700">{formatCurrency(billsPaidTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-widest text-emerald-600/60">{currentMonthBills.filter(bill => bill.isPaid).length} OBLIGATIONS_CLEARED</div>
                            </div>
                            <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-rose-50/50 p-6 shadow-none">
                                <div className="text-[9px] font-sans font-semibold uppercase tracking-[0.2em] text-rose-600 mb-2">// TOTAL_OUTSTANDING</div>
                                <div className="text-3xl font-sans font-semibold tracking-tighter text-rose-700">{formatCurrency(billsPendingTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-widest text-rose-600/60">{currentMonthBills.filter(bill => !bill.isPaid).length} OBLIGATIONS_PENDING</div>
                            </div>
                            <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-slate-50 p-6 shadow-none">
                                <div className="text-[9px] font-sans font-semibold uppercase tracking-[0.2em] text-slate-500 mb-2">// LIABILITY_TOTAL</div>
                                <div className="text-3xl font-sans font-semibold tracking-tighter text-on-surface">{formatCurrency(billsOverallTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-widest text-slate-400">{currentMonthBills.length} TOTAL_OBLIGATIONS_PERIOD</div>
                            </div>
                        </div>
                        <div className="mb-6 overflow-hidden rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-surface shadow-none">
                            <div className="border-b border-[#e5e7eb] dark:border-white/10 bg-slate-50 p-6">
                                <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
                                    <div className="space-y-1">
                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">QUERY_FILTER</label>
                                        <input
                                            type="text"
                                            placeholder="ID_BARCODE_PIX"
                                            value={billSearch}
                                            onChange={(e) => setBillSearch(e.target.value)}
                                            className="w-full rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2.5 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">STATUS_FILTER</label>
                                        <select value={billStatusFilter} onChange={(e) => setBillStatusFilter(e.target.value as 'all' | 'paid' | 'unpaid')} className="w-full rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2.5 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile">
                                            <option value="all">ALL_STATUS</option>
                                            <option value="paid">PAID</option>
                                            <option value="unpaid">UNPAID</option>
                                        </select>
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">TAG_FILTER</label>
                                        <select value={billCategoryFilter} onChange={(e) => setBillCategoryFilter(e.target.value)} className="w-full rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2.5 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile">
                                            <option value="all">ALL_CATEGORIES</option>
                                            {(settings.billCategories || []).map(cat => (
                                                <option key={cat} value={cat}>{cat}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="flex items-end">
                                        <div className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2.5 text-[10px] font-sans font-semibold uppercase tracking-widest text-slate-500 flex items-center justify-center">
                                            P: {visibleBills.filter(bill => bill.isPaid).length} / U: {visibleBills.filter(bill => !bill.isPaid).length}
                                        </div>
                                    </div>
                                    <div className="flex items-end">
                                        <div className="w-full flex items-center justify-center rounded-soft-touch bg-on-surface text-white px-4 py-2.5 text-[10px] font-sans font-semibold uppercase tracking-[0.2em]">
                                            COUNT: {visibleBills.length}
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="min-w-full text-sm">
                                    <thead className="bg-slate-100 text-[10px] font-sans uppercase tracking-widest text-slate-500 border-b border-[#e5e7eb] dark:border-white/10">
                                        <tr>
                                            <th className="px-4 py-3 text-left font-bold">ACK</th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleBillSort('description')} className="flex items-center gap-2">DESCRIPTION <span>{getSortIndicator(billSort.key === 'description', billSort.direction)}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleBillSort('category')} className="flex items-center gap-2">TAG <span>{getSortIndicator(billSort.key === 'category', billSort.direction)}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleBillSort('dueDay')} className="flex items-center gap-2">DUE <span>{getSortIndicator(billSort.key === 'dueDay', billSort.direction)}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleBillSort('amount')} className="flex items-center gap-2">VAL <span>{getSortIndicator(billSort.key === 'amount', billSort.direction)}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold">DOCS</th>
                                            <th className="px-4 py-3 text-left font-bold">PIX</th>
                                            <th className="px-4 py-3 text-left font-bold">STATUS</th>
                                            <th className="px-4 py-3 text-right font-bold">ACT</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-[#e5e7eb] dark:divide-white/10 bg-white">
                                        {visibleBills.map(bill => {
                                            const prevBill = fixedBills.find(b =>
                                                b.description === bill.description &&
                                                b.month === (currentMonth === 0 ? 11 : currentMonth - 1) &&
                                                b.year === (currentMonth === 0 ? currentYear - 1 : currentYear)
                                            );
                                            const diff = prevBill ? bill.amount - prevBill.amount : 0;
                                            const isExpanded = expandedBillId === bill.id;
                                            const activeBillTab = activeBillTabs[bill.id] || 'codigo';

                                            return (
                                                <React.Fragment key={bill.id}>
                                                    <tr className={`cursor-pointer transition-colors font-sans ${isExpanded ? 'bg-slate-50' : 'hover:bg-slate-50'}`} onClick={() => setExpandedBillId(isExpanded ? null : bill.id)}>
                                                        <td className="px-4 py-4">
                                                            <input
                                                                type="checkbox"
                                                                checked={bill.isPaid}
                                                                onClick={(e) => e.stopPropagation()}
                                                                onChange={() => onUpdateBill({ ...bill, isPaid: !bill.isPaid })}
                                                                className="h-4 w-4 rounded-lg border-[#e5e7eb] dark:border-white/10 text-emerald-600 focus:ring-0 bg-transparent"
                                                            />
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <div className={`font-bold text-xs ${bill.isPaid ? 'text-slate-300 line-through' : 'text-on-surface'}`}>{bill.description}</div>
                                                            {bill.rubricId && <div className="text-[8px] font-bold uppercase tracking-widest text-slate-400">// LINKED_RESOURCE</div>}
                                                        </td>
                                                        <td className="px-4 py-4 font-bold text-[10px] text-slate-500 uppercase">{bill.category || 'FIXED'}</td>
                                                        <td className="px-4 py-4 font-bold text-[10px] text-slate-500 uppercase">DAY_{bill.dueDay}</td>
                                                        <td className="px-4 py-4">
                                                            <div className={`font-bold text-xs ${bill.isPaid ? 'text-slate-300' : 'text-on-surface'}`}>{formatCurrency(bill.amount)}</div>
                                                            {diff !== 0 && <div className={`text-[9px] font-bold ${diff < 0 ? 'text-emerald-600' : 'text-accent-tactile'}`}>{diff < 0 ? '-' : '+'} {formatCurrency(Math.abs(diff))}</div>}
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <span className={`inline-flex border border-[#e5e7eb] dark:border-white/10 px-2 py-0.5 text-[8px] font-bold uppercase tracking-widest ${bill.barcode ? 'bg-on-surface text-surface' : 'bg-slate-50 text-slate-300'}`}>
                                                                {bill.barcode ? 'AVAIL' : 'NONE'}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <span className={`inline-flex border border-[#e5e7eb] dark:border-white/10 px-2 py-0.5 text-[8px] font-bold uppercase tracking-widest ${bill.pixCode ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-50 text-slate-300'}`}>
                                                                {bill.pixCode ? 'AVAIL' : 'NONE'}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <span className={`inline-flex border border-[#e5e7eb] dark:border-white/10 px-2 py-0.5 text-[8px] font-bold uppercase tracking-widest ${bill.isPaid ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                                                                {bill.isPaid ? 'PAID' : 'PENDING'}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <div className="flex items-center justify-end gap-2">
                                                                <button onClick={(e) => { e.stopPropagation(); setExpandedBillId(isExpanded ? null : bill.id); }} className="rounded-soft-touch p-1 text-slate-300 hover:text-on-surface">
                                                                    <svg className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
                                                                </button>
                                                                <button onClick={(e) => { e.stopPropagation(); handleTwoStepDelete(`bill_${bill.id}`, () => onDeleteBill(bill.id)); }} className={`rounded-soft-touch p-1 transition-colors ${pendingDeleteKey === `bill_${bill.id}` ? 'bg-accent-tactile text-white' : 'text-slate-200 hover:text-accent-tactile'}`}>
                                                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                    {isExpanded && (
                                                        <tr className="bg-slate-50">
                                                            <td colSpan={9} className="px-4 py-6 border-b border-[#e5e7eb] dark:border-white/10">
                                                                <div className="space-y-6">
                                                                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
                                                                        <div>
                                                                            <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-1">DESCRIPTION_ID</label>
                                                                            <input type="text" defaultValue={bill.description} onBlur={(e) => onUpdateBill({ ...bill, description: e.target.value })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2 text-xs font-sans font-semibold text-on-surface" />
                                                                        </div>
                                                                        <div>
                                                                            <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-1">AMOUNT_VAL</label>
                                                                            <input type="number" defaultValue={bill.amount} onBlur={(e) => onUpdateBill({ ...bill, amount: Number(e.target.value) })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2 text-xs font-sans font-semibold text-on-surface" />
                                                                        </div>
                                                                        <div>
                                                                            <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-1">DUE_CYCLE</label>
                                                                            <input type="number" min={1} max={31} defaultValue={bill.dueDay} onBlur={(e) => onUpdateBill({ ...bill, dueDay: Number(e.target.value) })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2 text-xs font-sans font-semibold text-on-surface" />
                                                                        </div>
                                                                        <div>
                                                                            <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-1">CATEGORY_TAG</label>
                                                                            <select defaultValue={bill.category} onBlur={(e) => onUpdateBill({ ...bill, category: e.target.value })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-2 text-xs font-sans font-semibold text-on-surface">
                                                                                {(settings.billCategories || ['Conta Fixa', 'Poupanca', 'Investimento']).map(cat => (
                                                                                    <option key={cat} value={cat}>{cat}</option>
                                                                                ))}
                                                                            </select>
                                                                        </div>
                                                                    </div>

                                                                    <div className="flex border-b border-[#e5e7eb] dark:border-white/10">
                                                                        <button
                                                                            onClick={(e) => { e.stopPropagation(); setActiveBillTabs(prev => ({ ...prev, [bill.id]: 'codigo' })); }}
                                                                            className={`px-6 py-2 text-[10px] font-sans font-semibold uppercase tracking-widest transition-colors border-b-2 ${activeBillTab === 'codigo' ? 'border-primary-tactile text-on-surface' : 'border-transparent text-slate-400 hover:text-on-surface'}`}
                                                                        >
                                                                            CODES_DATA
                                                                        </button>
                                                                        <button
                                                                            onClick={(e) => { e.stopPropagation(); setActiveBillTabs(prev => ({ ...prev, [bill.id]: 'arquivo' })); }}
                                                                            className={`px-6 py-2 text-[10px] font-sans font-semibold uppercase tracking-widest transition-colors border-b-2 ${activeBillTab === 'arquivo' ? 'border-primary-tactile text-on-surface' : 'border-transparent text-slate-400 hover:text-on-surface'}`}
                                                                        >
                                                                            FILE_ATTACHMENTS
                                                                        </button>
                                                                    </div>

                                                                    {activeBillTab === 'codigo' ? (
                                                                        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                                                                            <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white p-4">
                                                                                <label className="mb-2 block text-[8px] font-sans font-semibold uppercase tracking-widest text-slate-400">BARCODE_RAW</label>
                                                                                <div className="flex gap-2">
                                                                                    <input type="text" defaultValue={bill.barcode || ''} onBlur={(e) => onUpdateBill({ ...bill, barcode: e.target.value })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-slate-50 px-4 py-2 font-sans text-[10px] font-bold text-on-surface" />
                                                                                    {bill.barcode && (
                                                                                        <button onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(bill.barcode || ''); }} className="rounded-soft-touch bg-on-surface text-surface px-4 py-2 text-[8px] font-sans font-semibold uppercase tracking-widest">
                                                                                            COPY
                                                                                        </button>
                                                                                    )}
                                                                                </div>
                                                                            </div>
                                                                            <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white p-4">
                                                                                <label className="mb-2 block text-[8px] font-sans font-semibold uppercase tracking-widest text-slate-400">PIX_TOKEN</label>
                                                                                <div className="flex gap-2">
                                                                                    <input type="text" defaultValue={bill.pixCode || ''} onBlur={(e) => onUpdateBill({ ...bill, pixCode: e.target.value })} className="w-full rounded-soft-touch border border-[#e5e7eb] dark:border-white/10 bg-slate-50 px-4 py-2 font-sans text-[10px] font-bold text-on-surface" />
                                                                                    {bill.pixCode && (
                                                                                        <button onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(bill.pixCode || ''); }} className="rounded-soft-touch bg-on-surface text-surface px-4 py-2 text-[8px] font-sans font-semibold uppercase tracking-widest">
                                                                                            COPY
                                                                                        </button>
                                                                                    )}
                                                                                </div>
                                                                            </div>
                                                                        </div>
                                                                    ) : (
                                                                        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
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
                                                                                className={`cursor-pointer rounded-lg border border-dashed p-4 transition-colors ${bill.attachmentUrl ? 'border-primary-tactile bg-blue-50' : 'border-[#e5e7eb] dark:border-white/10 bg-white hover:bg-slate-50'}`}
                                                                            >
                                                                                <div className="mb-2 text-[8px] font-sans font-semibold uppercase tracking-widest text-slate-400">DOC_BOLETO_PDF</div>
                                                                                <div className="text-[10px] font-sans font-semibold text-on-surface uppercase">{bill.attachmentUrl ? 'FILE_STATUS: LOADED' : 'ACTION: CLICK_TO_ATTACH'}</div>
                                                                                {bill.attachmentUrl && (
                                                                                    <a href={bill.attachmentUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="mt-3 inline-flex border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-1 text-[8px] font-sans font-semibold uppercase tracking-widest text-on-surface shadow-none hover:bg-slate-50">
                                                                                        VIEW_DOCUMENT
                                                                                    </a>
                                                                                )}
                                                                            </div>
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
                                                                                className={`cursor-pointer rounded-lg border border-dashed p-4 transition-colors ${bill.pixQrCodeUrl ? 'border-emerald-200 bg-emerald-50' : 'border-[#e5e7eb] dark:border-white/10 bg-white hover:bg-slate-50'}`}
                                                                            >
                                                                                <div className="mb-2 text-[8px] font-sans font-semibold uppercase tracking-widest text-slate-400">IMG_PIX_QR</div>
                                                                                <div className="text-[10px] font-sans font-semibold text-on-surface uppercase">{bill.pixQrCodeUrl ? 'FILE_STATUS: LOADED' : 'ACTION: CLICK_TO_ATTACH'}</div>
                                                                                {bill.pixQrCodeUrl && (
                                                                                    <a href={bill.pixQrCodeUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="mt-3 inline-flex border border-[#e5e7eb] dark:border-white/10 bg-white px-4 py-1 text-[8px] font-sans font-semibold uppercase tracking-widest text-on-surface shadow-none hover:bg-slate-50">
                                                                                        VIEW_DOCUMENT
                                                                                    </a>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    )}
                                                </React.Fragment>
                                            );
                                        })}
                                        {visibleBills.length === 0 && (
                                            <tr>
                                                <td colSpan={9} className="px-4 py-12 text-center text-[10px] font-sans font-semibold uppercase tracking-widest text-slate-400">NO_RECORDS_FOUND / FILTER_MISMATCH</td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </FinanceSection>
                </div>
            )}
        </div>
    );
};

export default FinanceView;
