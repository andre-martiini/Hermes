import React, { useState, useRef, useEffect, useMemo } from 'react';
import { FinanceTransaction, FinanceGoal, FinanceSettings, FixedBill, BillRubric, IncomeEntry, IncomeRubric } from './types';
import { storage, db } from './firebase';
import { ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { doc, setDoc } from 'firebase/firestore';

const parseDateDay = (dateStr?: string) => {
    if (!dateStr) return null;
    const isoMatch = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
        return {
            year: Number(isoMatch[1]),
            month: Number(isoMatch[2]) - 1,
            day: Number(isoMatch[3])
        };
    }
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return null;
    return {
        year: d.getFullYear(),
        month: d.getMonth(),
        day: d.getDate()
    };
};
import { resolveTwoStepAction } from './src/utils/destructiveActions';
import { getFinancePeriodSummary } from './src/utils/financeBudget';
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
    activeTab: 'dashboard' | 'income' | 'expense';
    setActiveTab: (tab: 'dashboard' | 'income' | 'expense') => void;
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

const FormattedCurrencyInput: React.FC<{
    value: number;
    onChange: (val: number) => void;
    onSave?: (val: number) => void;
    className?: string;
    prefixColorClass?: string;
}> = ({ value, onChange, onSave, className = '', prefixColorClass = 'text-emerald-600' }) => {
    const formatValue = (num: number): string => {
        if (num === undefined || num === null || isNaN(num)) return '0,00';
        return num.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };

    const [displayStr, setDisplayStr] = useState<string>(formatValue(value));
    const [isFocused, setIsFocused] = useState(false);

    useEffect(() => {
        if (!isFocused) {
            setDisplayStr(formatValue(value));
        }
    }, [value, isFocused]);

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const raw = e.target.value;
        setDisplayStr(raw);

        const clean = raw.replace(/\./g, '').replace(',', '.').replace(/[^\d.-]/g, '');
        const num = parseFloat(clean);
        if (!isNaN(num)) {
            onChange(num);
        }
    };

    const handleBlur = () => {
        setIsFocused(false);
        const clean = displayStr.replace(/\./g, '').replace(',', '.').replace(/[^\d.-]/g, '');
        const num = parseFloat(clean);
        const validNum = isNaN(num) ? 0 : num;
        setDisplayStr(formatValue(validNum));
        onChange(validNum);
        if (onSave) onSave(validNum);
    };

    return (
        <div className="group/edit relative flex items-baseline">
            <span className={`text-2xl font-sans font-semibold ${prefixColorClass} mr-2 select-none`}>R$</span>
            <input
                type="text"
                inputMode="decimal"
                className={`text-2xl font-sans font-semibold ${prefixColorClass} bg-transparent border-none outline-none focus:ring-0 p-0 ${className}`}
                value={displayStr}
                onChange={handleInputChange}
                onFocus={() => setIsFocused(true)}
                onBlur={handleBlur}
            />
        </div>
    );
};

const GoalTargetInput: React.FC<{
    targetAmount: number;
    onSave: (newTarget: number) => void;
}> = ({ targetAmount, onSave }) => {
    const formatValue = (num: number): string => {
        if (num === undefined || num === null || isNaN(num)) return '0,00';
        return num.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };

    const [str, setStr] = useState<string>(formatValue(targetAmount));
    const [isFocused, setIsFocused] = useState(false);

    useEffect(() => {
        if (!isFocused) {
            setStr(formatValue(targetAmount));
        }
    }, [targetAmount, isFocused]);

    const handleBlur = () => {
        setIsFocused(false);
        const clean = str.replace(/\./g, '').replace(',', '.').replace(/[^\d.-]/g, '');
        const num = parseFloat(clean);
        const validNum = isNaN(num) ? 0 : num;
        setStr(formatValue(validNum));
        if (validNum !== targetAmount) {
            onSave(validNum);
        }
    };

    return (
        <div className="flex items-center gap-1">
            <span className="text-slate-400 font-normal">Meta: R$</span>
            <input
                type="text"
                inputMode="decimal"
                className="bg-transparent border-b border-slate-200 dark:border-white/10 p-0 text-xs font-sans font-semibold text-on-surface w-28 outline-none focus:border-indigo-500"
                value={str}
                onChange={(e) => setStr(e.target.value)}
                onFocus={() => setIsFocused(true)}
                onBlur={handleBlur}
            />
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

    // Budget Chart Selector Tab ('accumulated' | 'daily')
    const [budgetChartTab, setBudgetChartTab] = useState<'accumulated' | 'daily'>('accumulated');

    // Selected Day Modal State
    const [selectedDayModal, setSelectedDayModal] = useState<number | null>(null);

    // Emergency Reserve Local State for Sync
    const [localEmergencyCurrent, setLocalEmergencyCurrent] = useState(emergencyReserve.current);
    const [localEmergencyTarget, setLocalEmergencyTarget] = useState(emergencyReserve.target);

    // Investment Reserve Local State for Sync
    const [localInvestmentCurrent, setLocalInvestmentCurrent] = useState(settings.investmentReserveCurrent ?? 0);
    const [localInvestmentTarget, setLocalInvestmentTarget] = useState(settings.investmentReserveTarget ?? 50000);
    const [localDefaultPrincipalIncome, setLocalDefaultPrincipalIncome] = useState(settings.defaultPrincipalIncome ?? 0);
    const [revenueYear, setRevenueYear] = useState<number>(currentYear);

    // Sync local state when props change (from parent/firebase)
    useEffect(() => {
        setLocalEmergencyCurrent(emergencyReserve.current);
    }, [emergencyReserve.current]);

    useEffect(() => {
        setLocalEmergencyTarget(emergencyReserve.target);
    }, [emergencyReserve.target]);

    useEffect(() => {
        setLocalInvestmentCurrent(settings.investmentReserveCurrent ?? 0);
    }, [settings.investmentReserveCurrent]);

    useEffect(() => {
        setLocalInvestmentTarget(settings.investmentReserveTarget ?? 50000);
    }, [settings.investmentReserveTarget]);

    useEffect(() => {
        setLocalDefaultPrincipalIncome(settings.defaultPrincipalIncome ?? 0);
    }, [settings.defaultPrincipalIncome]);

    // Monthly Revenue Consolidation for Selected Year
    const monthlyRevenueData = useMemo(() => {
        const months = [
            'JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN',
            'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'
        ];
        const defaultSalary = settings.defaultPrincipalIncome || 0;

        return months.map((mName, mIdx) => {
            const monthEntries = incomeEntries.filter(e => e.month === mIdx && e.year === revenueYear);

            // 1. Remuneração / Renda Principal
            const explicitPrincipalEntries = monthEntries.filter(e =>
                e.category === 'Renda Principal' ||
                (e.category && e.category.toLowerCase().includes('remuneraç')) ||
                (e.category && e.category.toLowerCase().includes('salário')) ||
                (e.description && e.description.toLowerCase().includes('remuneraç')) ||
                (e.description && e.description.toLowerCase().includes('salário')) ||
                (e.description && e.description.toLowerCase().includes('pro-labore'))
            );

            const principalAmount = explicitPrincipalEntries.length > 0
                ? explicitPrincipalEntries.reduce((a, c) => a + c.amount, 0)
                : defaultSalary;

            // 2. Receita Programada de Serviços / Contratos (inclui parcelas vinculadas via rubricId e categorias de serviços)
            const serviceEntries = monthEntries.filter(e =>
                !explicitPrincipalEntries.includes(e) && (
                    Boolean(e.rubricId) ||
                    (e.category && e.category.toLowerCase().includes('serviç')) ||
                    (e.category && e.category.toLowerCase().includes('consultoria')) ||
                    (e.category && e.category.toLowerCase().includes('projeto')) ||
                    (e.category && e.category.toLowerCase().includes('contrato')) ||
                    (e.description && e.description.toLowerCase().includes('serviç')) ||
                    (e.description && e.description.toLowerCase().includes('contrato')) ||
                    (e.description && e.description.toLowerCase().includes('nota fiscal')) ||
                    (e.description && e.description.toLowerCase().includes('nfse'))
                )
            );
            const serviceAmount = serviceEntries.reduce((a, c) => a + c.amount, 0);

            // 3. Outras Entradas & Rendimentos (apenas o que não for Renda Principal nem Serviços)
            const otherEntries = monthEntries.filter(e =>
                !explicitPrincipalEntries.includes(e) &&
                !serviceEntries.includes(e)
            );
            const otherAmount = otherEntries.reduce((a, c) => a + c.amount, 0);

            const receivedAmount = monthEntries.filter(e => e.isReceived).reduce((a, c) => a + c.amount, 0);
            const totalForecast = principalAmount + serviceAmount + otherAmount;

            return {
                monthIndex: mIdx,
                monthName: mName,
                principalAmount,
                serviceAmount,
                otherAmount,
                totalForecast,
                receivedAmount,
                isCurrentMonth: mIdx === currentMonth && revenueYear === currentYear,
                hasExplicitEntries: monthEntries.length > 0
            };
        });
    }, [incomeEntries, revenueYear, settings.defaultPrincipalIncome, currentMonth, currentYear]);

    const totalAnnualForecast = useMemo(() => {
        return monthlyRevenueData.reduce((acc, curr) => acc + curr.totalForecast, 0);
    }, [monthlyRevenueData]);

    const totalAnnualReceived = useMemo(() => {
        return monthlyRevenueData.reduce((acc, curr) => acc + curr.receivedAmount, 0);
    }, [monthlyRevenueData]);

    const maxMonthlyForecast = useMemo(() => {
        const max = Math.max(...monthlyRevenueData.map(d => d.totalForecast), 1);
        return max;
    }, [monthlyRevenueData]);

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
    const budgetSummary = getFinancePeriodSummary(transactions, settings, currentYear, currentMonth);
    const currentBudget = budgetSummary.budget;
    const budgetPercentage = Math.min(budgetSummary.budgetRatio * 100, 100);

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
                const parts = parseDateDay(t.date);
                return parts && parts.month === currentMonth && parts.year === currentYear;
            })
            .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

        if (filteredTransactions.length === 0) {
            return;
        }

        const headers = ['Data', 'Descrição', 'Valor'];
        const rows = filteredTransactions.map(t => {
            const parts = parseDateDay(t.date);
            const formattedDate = parts 
                ? `${String(parts.day).padStart(2, '0')}/${String(parts.month + 1).padStart(2, '0')}/${parts.year}`
                : new Date(t.date).toLocaleDateString('pt-BR');
            return [
                formattedDate,
                t.description || 'LOG_ITEM_STREAM',
                t.amount.toFixed(2).replace('.', ',')
            ];
        });

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
    const pendingIncomeRubrics = incomeRubrics.filter(rubric => !rubric.eventual && !currentMonthIncomeEntries.some(entry => entry.rubricId === rubric.id));
    const eventualIncomeRubrics = incomeRubrics.filter(rubric => rubric.eventual);
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

    // Previsão de Receita Calculations
    const principalIncomeTotal = currentMonthIncomeEntries
        .filter(e => e.category === 'Renda Principal' || e.description.toLowerCase().includes('remuneração') || e.description.toLowerCase().includes('salário') || e.description.toLowerCase().includes('pro-labore'))
        .reduce((acc, curr) => acc + curr.amount, 0);

    const serviceIncomeTotal = currentMonthIncomeEntries
        .filter(e => e.category === 'Serviços' || e.category === 'Consultoria' || e.category === 'Projetos' || e.description.toLowerCase().includes('serviço') || e.description.toLowerCase().includes('contrato') || e.description.toLowerCase().includes('nota fiscal') || e.description.toLowerCase().includes('nfse'))
        .reduce((acc, curr) => acc + curr.amount, 0);

    const otherIncomeTotal = Math.max(0, incomeOverallTotal - (principalIncomeTotal + serviceIncomeTotal));
    const pendingRubricsTotal = pendingIncomeRubrics.reduce((acc, curr) => acc + (curr.defaultAmount || 0), 0);
    const totalRevenueForecast = Math.max(incomeOverallTotal, incomeOverallTotal + pendingRubricsTotal);
    const totalRevenueReceived = incomeReceivedTotal;
    const revenuePercentage = totalRevenueForecast > 0 ? Math.min((totalRevenueReceived / totalRevenueForecast) * 100, 100) : 0;
    const pendingRevenue = Math.max(0, totalRevenueForecast - totalRevenueReceived);

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

    // --- DAILY CONSUMPTION CHART CALCULATIONS ---
    const currentMonthTransactionsList = useMemo(() => {
        return transactions.filter(t => {
            const parts = parseDateDay(t.date);
            return parts && parts.month === currentMonth && parts.year === currentYear;
        });
    }, [transactions, currentMonth, currentYear]);

    const dailyChartData = useMemo(() => {
        const amountByDay = new Map<number, { amount: number; count: number }>();
        currentMonthTransactionsList.forEach(t => {
            const parts = parseDateDay(t.date);
            if (!parts) return;
            const prev = amountByDay.get(parts.day) || { amount: 0, count: 0 };
            amountByDay.set(parts.day, {
                amount: prev.amount + t.amount,
                count: prev.count + 1
            });
        });

        const now = new Date();
        const isCurrentMonth = now.getMonth() === currentMonth && now.getFullYear() === currentYear;
        const currentDay = isCurrentMonth ? now.getDate() : 0;

        return Array.from({ length: daysInMonth }, (_, idx) => {
            const day = idx + 1;
            const data = amountByDay.get(day) || { amount: 0, count: 0 };
            return {
                day,
                amount: data.amount,
                count: data.count,
                isToday: day === currentDay,
                isPast: isCurrentMonth ? day <= currentDay : true
            };
        });
    }, [currentMonthTransactionsList, daysInMonth, currentMonth, currentYear]);

    const maxDailyAmount = useMemo(() => {
        return Math.max(...dailyChartData.map(d => d.amount), 1);
    }, [dailyChartData]);

    const peakDay = useMemo(() => {
        let max = { day: 0, amount: 0 };
        dailyChartData.forEach(d => {
            if (d.amount > max.amount) max = { day: d.day, amount: d.amount };
        });
        return max;
    }, [dailyChartData]);

    const averageDailySpend = useMemo(() => {
        const now = new Date();
        const isCurrentMonth = now.getMonth() === currentMonth && now.getFullYear() === currentYear;
        const elapsedDays = isCurrentMonth ? Math.max(now.getDate(), 1) : daysInMonth;
        return currentMonthTotal / elapsedDays;
    }, [currentMonthTotal, currentMonth, currentYear, daysInMonth]);

    const selectedDayTransactions = useMemo(() => {
        if (selectedDayModal === null) return [];
        return currentMonthTransactionsList.filter(t => {
            const parts = parseDateDay(t.date);
            return parts && parts.day === selectedDayModal;
        }).sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    }, [selectedDayModal, currentMonthTransactionsList]);

    const selectedDayTotal = useMemo(() => {
        return selectedDayTransactions.reduce((acc, t) => acc + t.amount, 0);
    }, [selectedDayTransactions]);

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
                <div className="bg-surface dark:bg-slate-900 text-on-surface p-6 md:p-8 rounded-2xl border border-slate-200 dark:border-white/10 shadow-card animate-in slide-in-from-top-4 space-y-8">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        <div>
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider mb-2 text-primary-tactile flex items-center gap-2">
                                <span className="w-1.5 h-1.5 bg-primary-tactile rounded-full"></span>
                                Orçamento do Período — {new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}
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
                                    className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-3 text-on-surface font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full text-base"
                                />
                            </div>
                            <p className="text-[9px] text-slate-400 dark:text-slate-500 uppercase mt-2 font-sans font-semibold tracking-wider">Limite personalizado para o mês ativo</p>
                        </div>
                        <div>
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider mb-2 text-slate-500 flex items-center gap-2">
                                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full"></span>
                                Orçamento Padrão
                            </h4>
                            <div className="flex gap-4">
                                <input
                                    type="number"
                                    defaultValue={settings.monthlyBudget}
                                    onBlur={(e) => onUpdateSettings({ ...settings, monthlyBudget: Number(e.target.value) })}
                                    className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-3 text-on-surface font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full text-base"
                                />
                            </div>
                            <p className="text-[9px] text-slate-400 dark:text-slate-500 uppercase mt-2 font-sans font-semibold tracking-wider">Base geral de referência do sistema</p>
                        </div>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4">
                        <div>
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider mb-2 text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
                                Meta da Reserva de Emergência
                            </h4>
                            <input
                                type="number"
                                value={localEmergencyTarget}
                                onChange={(e) => setLocalEmergencyTarget(Number(e.target.value))}
                                onBlur={(e) => onUpdateSettings({ ...settings, emergencyReserveTarget: Number(e.target.value) })}
                                className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-3 text-on-surface font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full"
                            />
                        </div>
                        <div>
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider mb-2 text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
                                Saldo Atual da Reserva (Com Rendimentos)
                            </h4>
                            <input
                                type="number"
                                value={localEmergencyCurrent}
                                onChange={(e) => setLocalEmergencyCurrent(Number(e.target.value))}
                                onBlur={(e) => onUpdateSettings({ ...settings, emergencyReserveCurrent: Number(e.target.value) })}
                                className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-3 text-on-surface font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full"
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4">
                        <div>
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider mb-2 text-indigo-600 dark:text-indigo-400 flex items-center gap-2">
                                <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full"></span>
                                Meta de Investimentos & Objetivos
                            </h4>
                            <input
                                type="number"
                                value={localInvestmentTarget}
                                onChange={(e) => setLocalInvestmentTarget(Number(e.target.value))}
                                onBlur={(e) => onUpdateSettings({ ...settings, investmentReserveTarget: Number(e.target.value) })}
                                className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-3 text-on-surface font-sans font-semibold outline-none focus:ring-1 focus:ring-indigo-500 w-full"
                            />
                        </div>
                        <div>
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider mb-2 text-indigo-600 dark:text-indigo-400 flex items-center gap-2">
                                <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full"></span>
                                Saldo Atual de Investimentos
                            </h4>
                            <input
                                type="number"
                                value={localInvestmentCurrent}
                                onChange={(e) => setLocalInvestmentCurrent(Number(e.target.value))}
                                onBlur={(e) => onUpdateSettings({ ...settings, investmentReserveCurrent: Number(e.target.value) })}
                                className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-3 text-on-surface font-sans font-semibold outline-none focus:ring-1 focus:ring-indigo-500 w-full"
                            />
                        </div>
                    </div>

                    <div className="pt-4">
                        <div>
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider mb-2 text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
                                Remuneração Mensal Padrão (Renda Principal)
                            </h4>
                            <input
                                type="number"
                                value={localDefaultPrincipalIncome}
                                onChange={(e) => setLocalDefaultPrincipalIncome(Number(e.target.value))}
                                onBlur={(e) => onUpdateSettings({ ...settings, defaultPrincipalIncome: Number(e.target.value) })}
                                className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-3 text-on-surface font-sans font-semibold outline-none focus:ring-1 focus:ring-emerald-500 w-full"
                            />
                            <p className="text-[9px] text-slate-400 uppercase mt-1 font-sans font-semibold tracking-wider">
                                Valor base de salário/remuneração aplicável nos meses sem lançamento específico
                            </p>
                        </div>
                    </div>

                    {/* Configuração de Gastos Externos */}
                    <div className="pt-6 border-t border-slate-200 dark:border-white/10">
                        <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider mb-4 text-purple-650 dark:text-purple-400">// Portal de Acesso Externo</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            <div>
                                <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block mb-2">Limite de Gastos para Visualização Externa (R$)</label>
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
                                    className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-3 text-on-surface font-sans font-semibold outline-none focus:ring-1 focus:ring-primary-tactile w-full"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block mb-2">Token de Autenticação Externa</label>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={settings.externalToken || ''}
                                        readOnly
                                        placeholder="Nenhum token gerado"
                                        className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-3 text-on-surface font-sans text-xs outline-none w-full"
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
                                        className="bg-slate-100 dark:bg-slate-800 text-on-surface hover:bg-primary-tactile hover:text-white px-5 py-2.5 rounded-lg text-[10px] font-sans font-bold uppercase tracking-wider transition-all border border-slate-200 dark:border-white/10 shrink-0"
                                    >
                                        Gerar Token
                                    </button>
                                </div>
                            </div>
                        </div>
                        {settings.externalToken && (
                            <div className="mt-4 bg-slate-50 dark:bg-slate-950 border border-slate-250 dark:border-white/10 p-4 rounded-xl flex flex-col md:flex-row items-center justify-between gap-4">
                                <div className="text-[10px] font-sans text-purple-700 dark:text-purple-400 break-all opacity-90 italic">
                                    {window.location.origin}/gastos-externos?token={settings.externalToken}
                                </div>
                                <button
                                    onClick={() => navigator.clipboard.writeText(`${window.location.origin}/gastos-externos?token=${settings.externalToken}`)}
                                    className="bg-primary-tactile/10 text-primary-tactile border border-primary-tactile/20 hover:bg-primary-tactile/20 px-4 py-2 rounded-lg text-[9px] font-sans font-bold uppercase tracking-wider transition-all flex items-center gap-2"
                                >
                                    Copiar Link do Portal
                                </button>
                            </div>
                        )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-6 border-t border-slate-200 dark:border-white/10">
                        {/* Gestão de Categorias de Obrigações */}
                        <div className="space-y-4">
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">// Categorias de Saídas (Obrigações)</h4>
                            <div className="flex flex-wrap gap-2">
                                {(settings.billCategories || ['Conta Fixa', 'Poupança', 'Investimento']).map(cat => (
                                    <div key={cat} className="flex items-center gap-2 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 px-3 py-1.5 rounded-lg group">
                                        <span className="text-[10px] font-sans font-bold uppercase tracking-wider text-on-surface">{cat}</span>
                                        <button
                                            onClick={() => onUpdateSettings({
                                                ...settings,
                                                billCategories: (settings.billCategories || []).filter(c => c !== cat)
                                            })}
                                            className="text-slate-400 dark:text-slate-600 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-all font-sans font-semibold text-[10px]"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                ))}
                            </div>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    placeholder="Nova Categoria..."
                                    className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-[10px] font-sans font-semibold uppercase tracking-wider outline-none focus:ring-1 focus:ring-blue-500 w-full"
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
                                    className="bg-blue-600 text-white px-4 py-2.5 rounded-lg text-xs font-bold hover:bg-blue-700 transition-colors"
                                >
                                    +
                                </button>
                            </div>
                        </div>

                        {/* Gestão de Categorias de Renda */}
                        <div className="space-y-4">
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">// Categorias de Entrada (Fontes de Renda)</h4>
                            <div className="flex flex-wrap gap-2">
                                {(settings.incomeCategories || ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']).map(cat => (
                                    <div key={cat} className="flex items-center gap-2 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 px-3 py-1.5 rounded-lg group">
                                        <span className="text-[10px] font-sans font-bold uppercase tracking-wider text-on-surface">{cat}</span>
                                        <button
                                            onClick={() => onUpdateSettings({
                                                ...settings,
                                                incomeCategories: (settings.incomeCategories || []).filter(c => c !== cat)
                                            })}
                                            className="text-slate-400 dark:text-slate-600 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-all font-sans font-semibold text-[10px]"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                ))}
                            </div>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    placeholder="Nova Fonte..."
                                    className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-[10px] font-sans font-semibold uppercase tracking-wider outline-none focus:ring-1 focus:ring-emerald-500 w-full"
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
                                    className="bg-emerald-600 text-white px-4 py-2.5 rounded-lg text-xs font-bold hover:bg-emerald-700 transition-colors"
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
                    {/* COMPARATIVE HUB */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="lg:col-span-2 bg-surface p-6 md:p-8 rounded-2xl border border-slate-200 dark:border-white/10 shadow-card flex flex-col justify-between relative overflow-hidden group">
                            <div className="relative z-10">
                                <div className="mb-6">
                                    <h4 className="text-[10px] font-sans font-bold text-slate-400 uppercase tracking-wider">Comparativo de Fluxo Mensal</h4>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                    <div>
                                        <div className="text-[10px] font-sans font-bold text-emerald-600 dark:text-emerald-400 uppercase mb-2 tracking-wider flex items-center gap-2">
                                            Previsão de Entrada
                                            {prevIncome > 0 && (
                                                <span className={`text-[9px] px-1.5 py-0.5 rounded-full border border-slate-200 dark:border-white/10 ${incomeOverallTotal >= prevIncome ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/20 dark:text-emerald-400' : 'bg-rose-50 text-rose-600 dark:bg-rose-950/20 dark:text-rose-400'}`}>
                                                    {incomeOverallTotal >= prevIncome ? 'Alta' : 'Queda'} {Math.round(Math.abs((incomeOverallTotal - prevIncome) / prevIncome) * 100)}%
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-3xl font-sans font-bold text-on-surface tracking-tight">
                                            R$ {incomeOverallTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-[10px] font-sans font-bold text-blue-600 dark:text-blue-400 uppercase mb-2 tracking-wider flex items-center gap-2">
                                            Previsão de Saída (Fixas)
                                            {prevBills > 0 && (
                                                <span className={`text-[9px] px-1.5 py-0.5 rounded-full border border-slate-200 dark:border-white/10 ${currentTotalBills <= prevBills ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/20 dark:text-emerald-400' : 'bg-rose-50 text-rose-600 dark:bg-rose-950/20 dark:text-rose-400'}`}>
                                                    {currentTotalBills <= prevBills ? 'Queda' : 'Alta'} {Math.round(Math.abs((currentTotalBills - prevBills) / prevBills) * 100)}%
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-3xl font-sans font-bold text-on-surface tracking-tight">
                                            R$ {currentTotalBills.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-8">
                                    <div className="flex justify-between text-[10px] font-sans font-bold uppercase tracking-wider mb-2">
                                        <span className="text-slate-400">Comprometimento de Renda ({Math.round((currentTotalBills / (incomeOverallTotal || 1)) * 100)}%)</span>
                                        <span className="text-slate-400 italic">Limite Ideal: 70%</span>
                                    </div>
                                    <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden border border-slate-200 dark:border-white/10">
                                        <div
                                            className={`h-full transition-all duration-1000 ${incomeOverallTotal > 0 && (currentTotalBills / incomeOverallTotal) > 0.7 ? 'bg-rose-500' : 'bg-emerald-500'}`}
                                            style={{ width: `${Math.min(incomeOverallTotal > 0 ? (currentTotalBills / incomeOverallTotal) * 100 : 0, 100)}%` }}
                                        ></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className={`p-6 md:p-8 rounded-2xl border border-slate-200 dark:border-white/10 shadow-card flex flex-col justify-center items-center text-center transition-all ${incomeOverallTotal - currentTotalBills >= 0 ? 'bg-slate-50 dark:bg-slate-900 text-on-surface' : 'bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-400'}`}>
                            <h4 className="text-[10px] font-sans font-bold uppercase tracking-wider mb-2 text-slate-400">Saldo Projetado</h4>
                            <div className={`text-4xl font-sans font-bold tracking-tight mb-2 ${incomeOverallTotal - currentTotalBills >= 0 ? 'text-on-surface' : 'text-rose-600 dark:text-rose-400'}`}>
                                R$ {(incomeOverallTotal - currentTotalBills).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                            </div>
                            <p className="text-[9px] font-sans font-semibold uppercase text-slate-400 tracking-wider">Saldo Líquido Estimado</p>
                        </div>
                    </div>

                    {/* SALDOS FINANCEIROS DO PERÍODO */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {/* O Hermes ainda não recebe o saldo bancário atual do PicPay. */}
                        <div className="bg-gradient-to-br from-emerald-500/10 via-teal-500/5 to-transparent p-5 rounded-2xl border border-emerald-500/30 flex flex-col gap-1 shadow-sm relative overflow-hidden">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] font-sans font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                                    🏦 Saldo Real da Conta (PicPay)
                                </span>
                                <span className="text-[8px] font-sans font-extrabold bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 px-2 py-0.5 rounded-full uppercase">
                                    Sem integração
                                </span>
                            </div>
                            <div className="text-2xl md:text-3xl font-sans font-extrabold text-emerald-600 dark:text-emerald-400 tracking-tight mt-1">
                                Não sincronizado
                            </div>
                            <p className="text-[9px] font-sans font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mt-0.5">
                                Consulte o aplicativo bancário para o saldo atual
                            </p>
                        </div>

                        {/* Card 2: Orçamento Somente para Pix */}
                        <div className="bg-gradient-to-br from-indigo-500/10 via-purple-500/5 to-transparent p-5 rounded-2xl border border-indigo-500/30 flex flex-col gap-1 shadow-sm relative overflow-hidden">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] font-sans font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 flex items-center gap-1.5">
                                    📱 Orçamento Somente Pix
                                </span>
                                <span className="text-[8px] font-sans font-extrabold bg-indigo-500/20 text-indigo-600 dark:text-indigo-300 px-2 py-0.5 rounded-full uppercase">
                                    Pix
                                </span>
                            </div>
                            <div className="text-2xl md:text-3xl font-sans font-extrabold text-indigo-600 dark:text-indigo-400 tracking-tight mt-1">
                                {formatCurrency(budgetSummary.pixAvailable)}
                            </div>
                            <p className="text-[9px] font-sans font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mt-0.5">
                                Orçamento menos os gastos Pix do período
                            </p>
                        </div>

                        {/* Card 3: Orçamento Geral de Gastos */}
                        <div className="bg-gradient-to-br from-purple-500/10 via-pink-500/5 to-transparent p-5 rounded-2xl border border-purple-500/30 flex flex-col gap-1 shadow-sm relative overflow-hidden">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] font-sans font-bold uppercase tracking-wider text-purple-600 dark:text-purple-400 flex items-center gap-1.5">
                                    📊 Orçamento Geral (Todos os Gastos)
                                </span>
                                <span className="text-[8px] font-sans font-extrabold bg-purple-500/20 text-purple-600 dark:text-purple-300 px-2 py-0.5 rounded-full uppercase">
                                    Geral
                                </span>
                            </div>
                            <div className="text-2xl md:text-3xl font-sans font-extrabold text-purple-600 dark:text-purple-400 tracking-tight mt-1">
                                {formatCurrency(budgetSummary.available)}
                            </div>
                            <p className="text-[9px] font-sans font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mt-0.5">
                                Saldo disponível para todos os gastos
                            </p>
                        </div>
                    </div>
                    {/* Budget Bar & Daily Consumption Section */}
                    <div className="bg-surface p-6 md:p-8 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none relative overflow-hidden flex flex-col gap-6">
                        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                            <div>
                                <h4 className="text-xl md:text-2xl font-sans font-semibold text-on-surface tracking-tight mb-1">
                                    {budgetChartTab === 'accumulated'
                                        ? `// GASTO ACUMULADO • ${new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}`
                                        : budgetChartTab === 'daily'
                                        ? `// CONSUMO DIÁRIO DO PERÍODO • ${new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}`
                                        : `// PREVISÃO DE RECEITA • ${new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth))}`
                                    }
                                </h4>
                                <p className="text-[10px] font-sans text-slate-500 uppercase tracking-wider">
                                    {budgetChartTab === 'accumulated'
                                        ? 'Progresso orçamentário mensal e tempo decorrido'
                                        : budgetChartTab === 'daily'
                                        ? 'Detalhamento diário dos lançamentos e picos de consumo do mês'
                                        : 'Projeção de receitas programadas, remuneração principal e entradas adicionais'
                                    }
                                </p>
                            </div>

                            <div className="flex items-center gap-3 self-end sm:self-auto">
                                {/* TAB SELECTOR */}
                                <div className="flex p-1 bg-slate-100 dark:bg-white/5 rounded-xl border border-slate-200 dark:border-white/10 flex-wrap">
                                    <button
                                        type="button"
                                        onClick={() => setBudgetChartTab('accumulated')}
                                        className={`px-3 py-1.5 rounded-lg text-[9px] md:text-[10px] font-sans font-bold uppercase tracking-wider transition-all ${
                                            budgetChartTab === 'accumulated'
                                                ? 'bg-white dark:bg-slate-800 text-primary-tactile shadow-sm'
                                                : 'text-slate-500 hover:text-on-surface'
                                        }`}
                                    >
                                        Acumulado
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setBudgetChartTab('daily')}
                                        className={`px-3 py-1.5 rounded-lg text-[9px] md:text-[10px] font-sans font-bold uppercase tracking-wider transition-all ${
                                            budgetChartTab === 'daily'
                                                ? 'bg-white dark:bg-slate-800 text-primary-tactile shadow-sm'
                                                : 'text-slate-500 hover:text-on-surface'
                                        }`}
                                    >
                                        Consumo Diário
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setBudgetChartTab('revenue_forecast')}
                                        className={`px-3 py-1.5 rounded-lg text-[9px] md:text-[10px] font-sans font-bold uppercase tracking-wider transition-all ${
                                            budgetChartTab === 'revenue_forecast'
                                                ? 'bg-white dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 shadow-sm'
                                                : 'text-slate-500 hover:text-on-surface'
                                        }`}
                                    >
                                        Previsão de Receita
                                    </button>
                                </div>

                                <div className={`px-3 py-1.5 rounded-soft-touch text-[9px] md:text-[10px] font-sans font-semibold uppercase tracking-widest text-white shadow-sm shrink-0 ${getSprintStatus()}`}>
                                    SPRINT {currentSprint}
                                </div>
                            </div>
                        </div>

                        {budgetChartTab === 'accumulated' ? (
                            <div className="flex flex-col gap-6">
                                <div>
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

                                <div className="flex justify-between text-[9px] font-sans font-semibold text-slate-500 uppercase tracking-widest">
                                    <span>01 / MONTH_START</span>
                                    <span>MONTH_END / {daysInMonth}</span>
                                </div>
                            </div>
                        ) : budgetChartTab === 'daily' ? (
                            <div className="flex flex-col gap-6">
                                {/* Resumo de Métricas Diárias */}
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                    <div className="p-3.5 rounded-xl border border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-white/[0.02] flex flex-col gap-1">
                                        <span className="text-[9px] font-sans font-bold uppercase tracking-wider text-slate-400">Total Gasto (Mês)</span>
                                        <span className="text-base font-sans font-bold text-on-surface">
                                            R$ {currentMonthTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </span>
                                    </div>
                                    <div className="p-3.5 rounded-xl border border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-white/[0.02] flex flex-col gap-1">
                                        <span className="text-[9px] font-sans font-bold uppercase tracking-wider text-slate-400">Média Diária (Decorridos)</span>
                                        <span className="text-base font-sans font-bold text-primary-tactile">
                                            R$ {averageDailySpend.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </span>
                                    </div>
                                    <div className="p-3.5 rounded-xl border border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-white/[0.02] flex flex-col gap-1">
                                        <span className="text-[9px] font-sans font-bold uppercase tracking-wider text-slate-400">Pico de Gasto Diário</span>
                                        <span className="text-base font-sans font-bold text-rose-500">
                                            {peakDay.amount > 0 ? `R$ ${peakDay.amount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })} (Dia ${String(peakDay.day).padStart(2, '0')})` : 'Sem lançamentos'}
                                        </span>
                                    </div>
                                </div>

                                 {/* Gráfico de Barras Diário Detalhado */}
                                <div className="flex flex-col gap-2">
                                    <div className="h-44 w-full flex items-end gap-1 sm:gap-1.5 pt-6 pb-2 px-1 relative">
                                        {dailyChartData.map((item) => {
                                            const heightPercent = item.amount > 0 ? Math.max((item.amount / maxDailyAmount) * 100, 6) : 0;
                                            const isPeak = item.day === peakDay.day && peakDay.amount > 0;

                                            return (
                                                <div
                                                    key={item.day}
                                                    onClick={() => setSelectedDayModal(item.day)}
                                                    className="flex-1 min-w-[6px] h-full flex flex-col justify-end items-center group relative cursor-pointer"
                                                    title={`Clique para ver lançamentos do Dia ${String(item.day).padStart(2, '0')}`}
                                                >
                                                    <div
                                                        style={{ height: item.amount > 0 ? `${heightPercent}%` : '3px' }}
                                                        className={`w-full rounded-t transition-all duration-300 ${
                                                            item.isToday
                                                                ? 'bg-[#9333ea] shadow-[0_0_8px_rgba(147,51,234,0.5)] ring-1 ring-white'
                                                                : isPeak
                                                                ? 'bg-rose-500 group-hover:bg-rose-400'
                                                                : item.amount > 0
                                                                ? 'bg-emerald-500/70 dark:bg-emerald-400/60 group-hover:bg-emerald-500'
                                                                : 'bg-slate-200 dark:bg-white/10'
                                                        } group-hover:brightness-110`}
                                                    />

                                                    {/* Tooltip no Hover */}
                                                    <div className="absolute -top-14 hidden group-hover:flex flex-col items-center bg-slate-900 text-white text-[9px] px-2.5 py-1.5 rounded-lg shadow-xl z-30 whitespace-nowrap font-mono border border-slate-700 pointer-events-none">
                                                        <span className="font-bold text-emerald-400">Dia {String(item.day).padStart(2, '0')}: R$ {item.amount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                                        <span className="text-[8px] text-slate-300">{item.count} lançamento(s) • Clique para ver</span>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>

                                    {/* Eixo X - Rótulos dos Dias */}
                                    <div className="flex justify-between text-[9px] font-mono text-slate-400 px-1 border-t border-slate-200/50 dark:border-white/5 pt-2">
                                        {Array.from({ length: Math.ceil(daysInMonth / 5) + 1 })
                                            .map((_, idx) => Math.min(idx * 5 + 1, daysInMonth))
                                            .filter((dayNum, i, arr) => arr.indexOf(dayNum) === i)
                                            .map((dayNum) => (
                                                <span key={`tick-${dayNum}`}>DIA {String(dayNum).padStart(2, '0')}</span>
                                            ))
                                        }
                                    </div>
                                </div>

                                {/* Legenda */}
                                <div className="flex flex-wrap items-center justify-between text-[9px] font-mono text-slate-500 gap-3">
                                    <div className="flex items-center gap-4">
                                        <span className="flex items-center gap-1.5">
                                            <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Gastos Diários
                                        </span>
                                        <span className="flex items-center gap-1.5">
                                            <span className="w-2 h-2 rounded-full bg-rose-500"></span> Pico do Mês
                                        </span>
                                        <span className="flex items-center gap-1.5">
                                            <span className="w-2 h-2 rounded-full bg-[#9333ea]"></span> Hoje
                                        </span>
                                    </div>
                                    <span className="italic">* Passe o cursor ou clique nas barras para ver os lançamentos do dia.</span>
                                </div>
                            </div>
                        ) : (
                            /* Previsão de Receita View - Consolidado Mês a Mês (12 meses) */
                            <div className="flex flex-col gap-6">
                                {/* Top Controls & Summary Banner */}
                                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-50 dark:bg-white/[0.02] p-4 rounded-xl border border-slate-200 dark:border-white/5">
                                    <div>
                                        <span className="text-[10px] font-sans font-bold uppercase tracking-wider text-slate-400">Total Projeção Anual ({revenueYear})</span>
                                        <div className="text-2xl md:text-3xl font-sans font-extrabold text-emerald-600 dark:text-emerald-400 tracking-tight mt-0.5">
                                            R$ {totalAnnualForecast.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </div>
                                        <div className="flex flex-wrap gap-3 mt-1.5 text-[9px] font-sans font-semibold uppercase tracking-wider">
                                            <span className="text-emerald-500 flex items-center gap-1">
                                                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
                                                Confirmado: R$ {totalAnnualReceived.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                            </span>
                                            <span className="text-slate-400 flex items-center gap-1">
                                                <span className="w-1.5 h-1.5 bg-amber-500 rounded-full"></span>
                                                Pendente: R$ {Math.max(0, totalAnnualForecast - totalAnnualReceived).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                            </span>
                                        </div>
                                    </div>

                                    {/* Year Selector Dropdown */}
                                    <div className="flex items-center gap-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 px-3 py-2 rounded-lg shadow-sm">
                                        <span className="text-[9px] font-sans font-bold uppercase tracking-wider text-slate-400">EXIBIR ANO:</span>
                                        <select
                                            value={revenueYear}
                                            onChange={(e) => setRevenueYear(Number(e.target.value))}
                                            className="bg-transparent text-xs font-sans font-extrabold text-on-surface outline-none cursor-pointer pr-1"
                                        >
                                            {[2024, 2025, 2026, 2027, 2028].map(yr => (
                                                <option key={yr} value={yr} className="bg-surface text-on-surface">
                                                    {yr} {yr === currentYear ? '• (Atual)' : ''}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                {/* Gráfico de 12 Meses (Consolidado Mês a Mês Empilhado) */}
                                <div className="flex flex-col gap-2">
                                    <div className="h-48 w-full flex items-end gap-1.5 sm:gap-2 pt-6 pb-2 px-1 relative">
                                        {monthlyRevenueData.map((item) => {
                                            const heightPercent = item.totalForecast > 0
                                                ? Math.max((item.totalForecast / maxMonthlyForecast) * 100, 8)
                                                : 0;

                                            return (
                                                <div
                                                    key={item.monthIndex}
                                                    className="flex-1 min-w-[12px] h-full flex flex-col justify-end items-center group relative cursor-pointer"
                                                >
                                                    {/* Bar Box Empilhado com 3 Segmentos de Cores */}
                                                    <div
                                                        style={{ height: item.totalForecast > 0 ? `${heightPercent}%` : '4px' }}
                                                        className={`w-full rounded-t overflow-hidden flex flex-col justify-end transition-all duration-300 ${
                                                            item.isCurrentMonth
                                                                ? 'ring-2 ring-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.35)] z-10'
                                                                : ''
                                                        }`}
                                                    >
                                                        {/* Segmento 3: Outras Entradas (Âmbar / Amarelo) - Topo */}
                                                        {item.otherAmount > 0 && item.totalForecast > 0 && (
                                                            <div
                                                                style={{ height: `${(item.otherAmount / item.totalForecast) * 100}%` }}
                                                                className="w-full bg-amber-500 hover:bg-amber-400 transition-all duration-200"
                                                            />
                                                        )}

                                                        {/* Segmento 2: Serviços / Contratos (Índigo / Roxo) - Meio */}
                                                        {item.serviceAmount > 0 && item.totalForecast > 0 && (
                                                            <div
                                                                style={{ height: `${(item.serviceAmount / item.totalForecast) * 100}%` }}
                                                                className="w-full bg-indigo-500 hover:bg-indigo-400 transition-all duration-200"
                                                            />
                                                        )}

                                                        {/* Segmento 1: Remuneração Principal (Esmeralda / Verde) - Base */}
                                                        {item.principalAmount > 0 && item.totalForecast > 0 && (
                                                            <div
                                                                style={{ height: `${(item.principalAmount / item.totalForecast) * 100}%` }}
                                                                className="w-full bg-emerald-500 hover:bg-emerald-400 transition-all duration-200"
                                                            />
                                                        )}

                                                        {/* Fallback para mês sem receita */}
                                                        {item.totalForecast === 0 && (
                                                            <div className="w-full h-full bg-slate-200 dark:bg-white/10" />
                                                        )}
                                                    </div>

                                                    {/* Tooltip no Hover com Detalhamento do Mês */}
                                                    <div className="absolute -top-36 hidden group-hover:flex flex-col bg-slate-900 text-white text-[9px] px-3 py-2 rounded-xl shadow-2xl z-50 whitespace-nowrap font-mono border border-slate-700 pointer-events-none min-w-[195px]">
                                                        <div className="font-bold text-emerald-400 border-b border-slate-800 pb-1 mb-1.5 flex justify-between items-center">
                                                            <span>{item.monthName} / {revenueYear}</span>
                                                            <span className="text-[8px] text-slate-400">{item.isCurrentMonth ? '(Mês Atual)' : ''}</span>
                                                        </div>
                                                        <div className="flex justify-between gap-4 text-slate-300">
                                                            <span className="flex items-center gap-1">
                                                                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
                                                                💼 Remuneração:
                                                            </span>
                                                            <span className="font-semibold text-white">R$ {item.principalAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                                        </div>
                                                        <div className="flex justify-between gap-4 text-slate-300">
                                                            <span className="flex items-center gap-1">
                                                                <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full"></span>
                                                                📄 Serviços/Contratos:
                                                            </span>
                                                            <span className="font-semibold text-white">R$ {item.serviceAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                                        </div>
                                                        <div className="flex justify-between gap-4 text-slate-300">
                                                            <span className="flex items-center gap-1">
                                                                <span className="w-1.5 h-1.5 bg-amber-500 rounded-full"></span>
                                                                💰 Outras Entradas:
                                                            </span>
                                                            <span className="font-semibold text-white">R$ {item.otherAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                                        </div>
                                                        <div className="border-t border-slate-800 pt-1 mt-1 flex justify-between text-emerald-400 font-bold">
                                                            <span>Total Projeção:</span>
                                                            <span>R$ {item.totalForecast.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                                        </div>
                                                        <div className="flex justify-between text-[8px] text-slate-400 mt-0.5">
                                                            <span>Confirmado / Recebido:</span>
                                                            <span>R$ {item.receivedAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>

                                    {/* Eixo X - Nomes dos Meses */}
                                    <div className="flex justify-between text-[9px] font-mono text-slate-400 px-1 border-t border-slate-200/50 dark:border-white/5 pt-2">
                                        {monthlyRevenueData.map((item) => (
                                            <span
                                                key={item.monthIndex}
                                                className={`text-center flex-1 ${item.isCurrentMonth ? 'text-emerald-500 font-bold' : ''}`}
                                            >
                                                {item.monthName}
                                            </span>
                                        ))}
                                    </div>

                                    {/* Legenda de Cores dos Segmentos */}
                                    <div className="flex flex-wrap items-center justify-center sm:justify-start gap-4 text-[9px] font-mono text-slate-500 pt-1">
                                        <span className="flex items-center gap-1.5">
                                            <span className="w-2.5 h-2.5 rounded bg-emerald-500"></span> Remuneração Principal
                                        </span>
                                        <span className="flex items-center gap-1.5">
                                            <span className="w-2.5 h-2.5 rounded bg-indigo-500"></span> Serviços / Contratos
                                        </span>
                                        <span className="flex items-center gap-1.5">
                                            <span className="w-2.5 h-2.5 rounded bg-amber-500"></span> Outras Entradas & Rendimentos
                                        </span>
                                    </div>
                                </div>

                                {/* Legenda e Cards de Composição Anual */}
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
                                    <div className="p-3 rounded-xl border border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-white/[0.02] flex flex-col gap-1">
                                        <span className="text-[9px] font-sans font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                            💼 Remuneração Padrão
                                        </span>
                                        <span className="text-sm font-sans font-bold text-on-surface">
                                            R$ {(settings.defaultPrincipalIncome || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })} / mês
                                        </span>
                                        <span className="text-[8px] text-slate-400 italic">
                                            {settings.defaultPrincipalIncome ? 'Definido nas configurações' : 'Nenhum valor padrão definido'}
                                        </span>
                                    </div>

                                    <div className="p-3 rounded-xl border border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-white/[0.02] flex flex-col gap-1">
                                        <span className="text-[9px] font-sans font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                            📄 Total Serviços no Ano ({revenueYear})
                                        </span>
                                        <span className="text-sm font-sans font-bold text-indigo-600 dark:text-indigo-400">
                                            R$ {monthlyRevenueData.reduce((a, c) => a + c.serviceAmount, 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </span>
                                        <span className="text-[8px] text-slate-400 italic">
                                            Contratos e serviços programados no ano
                                        </span>
                                    </div>

                                    <div className="p-3 rounded-xl border border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-white/[0.02] flex flex-col gap-1">
                                        <span className="text-[9px] font-sans font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                            📊 Concretização da Anual
                                        </span>
                                        <span className="text-sm font-sans font-bold text-emerald-600 dark:text-emerald-400">
                                            {totalAnnualForecast > 0 ? ((totalAnnualReceived / totalAnnualForecast) * 100).toFixed(1) : '0.0'}% Recebido
                                        </span>
                                        <span className="text-[8px] text-slate-400 italic">
                                            R$ {totalAnnualReceived.toLocaleString('pt-BR', { minimumFractionDigits: 2 })} de R$ {totalAnnualForecast.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Modal Detalhado de Lançamentos do Dia */}
                    {selectedDayModal !== null && (
                        <div
                            className="fixed inset-0 z-[99999] flex items-center justify-center bg-slate-950/70 backdrop-blur-sm p-4 animate-in fade-in duration-200"
                            onClick={() => setSelectedDayModal(null)}
                        >
                            <div
                                className="w-full max-w-xl bg-surface border border-[#e5e7eb] dark:border-white/10 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] animate-in zoom-in-95 duration-200"
                                onClick={(e) => e.stopPropagation()}
                            >
                                {/* Modal Header */}
                                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/[0.02] shrink-0">
                                    <div>
                                        <h3 className="text-sm md:text-base font-sans font-bold uppercase tracking-tight text-on-surface flex items-center gap-2">
                                            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                                            LANÇAMENTOS DO DIA {String(selectedDayModal).padStart(2, '0')} DE {new Intl.DateTimeFormat('pt-BR', { month: 'long' }).format(new Date(currentYear, currentMonth)).toUpperCase()}
                                        </h3>
                                        <p className="text-xs text-slate-500 font-sans mt-0.5">
                                            {selectedDayTransactions.length} lançamento(s) registrado(s) • Total: <strong className="text-on-surface">R$ {selectedDayTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</strong>
                                        </p>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => setSelectedDayModal(null)}
                                        className="px-3 py-1.5 rounded-xl text-slate-400 hover:text-on-surface hover:bg-slate-200/50 dark:hover:bg-white/10 transition-all font-mono text-xs font-bold"
                                    >
                                        ✕ FECHAR
                                    </button>
                                </div>

                                {/* Modal Content */}
                                <div className="p-5 overflow-y-auto custom-scrollbar flex-1 space-y-3">
                                    {selectedDayTransactions.length > 0 ? (
                                        selectedDayTransactions.map((t) => (
                                            <div
                                                key={t.id}
                                                className="group relative flex flex-col sm:flex-row sm:justify-between sm:items-center p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 rounded-xl hover:border-primary-tactile/50 transition-all shadow-sm gap-3"
                                            >
                                                <div className="flex items-center gap-3.5 min-w-0">
                                                    <div className="w-10 h-10 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-800/50 flex items-center justify-center text-on-surface font-sans font-bold text-xs shrink-0">
                                                        {String(selectedDayModal).padStart(2, '0')}
                                                    </div>
                                                    <div className="min-w-0 flex-1">
                                                        <div
                                                            className="text-xs font-sans font-bold text-on-surface uppercase tracking-tight truncate pr-2"
                                                            title={t.description}
                                                        >
                                                            {t.description || 'LOG_ITEM_STREAM'}
                                                        </div>
                                                        <div className="flex items-center gap-2 text-[9px] text-slate-400 font-sans font-semibold uppercase tracking-widest mt-0.5">
                                                            <span>{new Date(t.date).toLocaleDateString('pt-BR')}</span>
                                                            {t.sprint && <span>// SPRINT_{t.sprint}</span>}
                                                        </div>
                                                    </div>
                                                </div>

                                                <div className="flex items-center justify-between sm:justify-end gap-4 shrink-0">
                                                    <div className="font-sans font-bold text-on-surface text-sm">
                                                        - R$ {t.amount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                                    </div>
                                                    <div className="flex items-center gap-1.5">
                                                        <button
                                                            onClick={() => {
                                                                setSelectedDayModal(null);
                                                                setEditingTransaction(t);
                                                            }}
                                                            className="p-2 text-slate-400 hover:text-primary-tactile transition-all border border-slate-200 dark:border-white/10 rounded-lg"
                                                            title="Editar Lançamento"
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                                                            </svg>
                                                        </button>
                                                        <button
                                                            onClick={() => handleTwoStepDelete(`transaction_${t.id}`, () => onDeleteTransaction(t.id))}
                                                            className={`p-2 rounded-lg transition-all border ${
                                                                pendingDeleteKey === `transaction_${t.id}`
                                                                    ? 'bg-rose-500 text-white border-rose-600'
                                                                    : 'text-slate-400 border-slate-200 dark:border-white/10 hover:text-rose-500 hover:border-rose-200'
                                                            }`}
                                                            title="Excluir Lançamento"
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                            </svg>
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        ))
                                    ) : (
                                        <div className="py-12 text-center flex flex-col items-center justify-center gap-2">
                                            <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-white/5 flex items-center justify-center text-slate-400">
                                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                                </svg>
                                            </div>
                                            <p className="text-xs font-bold uppercase tracking-wider text-slate-400">
                                                Nenhum gasto registrado nesta data
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

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
                                            const parts = parseDateDay(t.date);
                                            return parts && parts.month === currentMonth && parts.year === currentYear;
                                        })
                                        .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
                                        .map(t => {
                                            const parts = parseDateDay(t.date);
                                            const dayStr = parts ? String(parts.day).padStart(2, '0') : '01';
                                            const formattedDate = parts 
                                                ? `${dayStr}/${String(parts.month + 1).padStart(2, '0')}/${parts.year}`
                                                : new Date(t.date).toLocaleDateString('pt-BR');
                                            return (
                                                <div key={t.id} className="group relative flex flex-col sm:flex-row sm:justify-between sm:items-center p-4 hover:bg-slate-50 rounded-lg transition-all border-b border-[#e5e7eb] dark:border-white/10 last:border-0 gap-3 sm:gap-4">
                                                    <div className="flex items-center gap-4 min-w-0">
                                                        <div className="w-10 h-10 rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white flex items-center justify-center text-on-surface font-sans font-semibold text-xs shrink-0">
                                                            {dayStr}
                                                        </div>
                                                        <div className="min-w-0 flex-1">
                                                            <div className="text-xs font-sans font-semibold text-on-surface uppercase tracking-tight truncate pr-8" title={t.description}>{t.description || 'LOG_ITEM_STREAM'}</div>
                                                            <div className="text-[9px] text-slate-400 font-sans font-semibold uppercase tracking-widest mt-0.5">
                                                                {`${formattedDate} // SPRINT_${t.sprint}`}
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
                                        );
                                    })}
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
                                <div className="flex items-center justify-between">
                                    <h5 className="text-xl font-sans font-semibold text-on-surface flex items-center gap-2">
                                        RESERVA_EMERGÊNCIA
                                    </h5>
                                    {emergencyReserve.current >= (emergencyReserve.target || 1) && (
                                        <span className="text-[9px] font-extrabold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1">
                                            🏆 100% ALCANÇADO
                                        </span>
                                    )}
                                </div>

                                <div className="flex items-end gap-2 mt-2">
                                    <FormattedCurrencyInput
                                        value={localEmergencyCurrent}
                                        prefixColorClass="text-emerald-600 dark:text-emerald-400"
                                        className="w-44"
                                        onChange={(num) => setLocalEmergencyCurrent(num)}
                                        onSave={(num) => onUpdateSettings({ ...settings, emergencyReserveCurrent: num })}
                                    />
                                    <span className="text-sm font-sans font-semibold text-slate-400 mb-0.5">/ {emergencyReserve.target.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                </div>

                                {/* Progress bar with Rendimentos Overflow Support */}
                                {(() => {
                                    const target = emergencyReserve.target || 1;
                                    const current = emergencyReserve.current;
                                    const isOverflow = current > target;
                                    const surplus = isOverflow ? current - target : 0;
                                    const basePct = Math.min((current / target) * 100, 100);
                                    const yieldPct = target > 0 ? (surplus / target) * 100 : 0;

                                    return (
                                        <div className="mt-4">
                                            <div className="h-2.5 bg-slate-200 dark:bg-white/10 rounded-lg overflow-hidden border border-[#e5e7eb] dark:border-white/10 flex">
                                                <div
                                                    className="h-full bg-emerald-500 transition-all duration-1000"
                                                    style={{ width: `${basePct}%` }}
                                                ></div>
                                                {isOverflow && (
                                                    <div
                                                        className="h-full bg-emerald-300 dark:bg-emerald-400 transition-all duration-1000 animate-pulse"
                                                        style={{ width: `${Math.min(yieldPct, 100)}%` }}
                                                        title={`Rendimentos: +R$ ${surplus.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`}
                                                    ></div>
                                                )}
                                            </div>

                                            <div className="mt-2 flex items-center justify-between text-[9px] font-sans font-semibold uppercase tracking-widest">
                                                {isOverflow ? (
                                                    <>
                                                        <span className="text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-1">
                                                            ✨ RENDIMENTOS: +R$ {surplus.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ({yieldPct.toFixed(1)}%)
                                                        </span>
                                                        <span className="text-slate-400">BASE PROTEGIDA</span>
                                                    </>
                                                ) : current >= target ? (
                                                    <span className="text-emerald-600 dark:text-emerald-400 font-bold">STATUS: RESERVA_CONCLUÍDA</span>
                                                ) : (
                                                    <span className="text-slate-400 italic">STATUS: RESERVA_PENDENTE</span>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })()}
                            </div>

                            {/* Twin Card: INVESTIMENTOS & OBJETIVOS (SEM META/BARRINHA, ALIMENTA AS METAS EM CASCATA) */}
                            <div className="bg-surface p-6 rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none relative overflow-hidden group">
                                <div className="flex items-center justify-between">
                                    <h5 className="text-xl font-sans font-semibold text-on-surface flex items-center gap-2">
                                        INVESTIMENTOS_&_OBJETIVOS
                                    </h5>
                                </div>

                                <div className="flex items-end gap-2 mt-2">
                                    <FormattedCurrencyInput
                                        value={localInvestmentCurrent}
                                        prefixColorClass="text-indigo-600 dark:text-indigo-400"
                                        className="w-44"
                                        onChange={(num) => setLocalInvestmentCurrent(num)}
                                        onSave={(num) => onUpdateSettings({ ...settings, investmentReserveCurrent: num })}
                                    />
                                </div>

                                <div className="mt-4 pt-3 border-t border-slate-100 dark:border-white/5 flex items-center justify-between text-[9px] font-sans font-semibold uppercase tracking-widest">
                                    <span className="text-indigo-600 dark:text-indigo-400 font-bold flex items-center gap-1">
                                        ✨ APLICADO INTEGRALMENTE EM CADA UMA DAS AQUISIÇÕES ABAIXO
                                    </span>
                                    <span className="text-slate-400">FONTE DE RECURSOS</span>
                                </div>
                            </div>

                                <div className="">
                                <FinanceSection title="Aquisições & Desejos de Compra" disableCollapse>
                                    <div className="flex justify-end mb-4">
                                        <button
                                            onClick={() => {
                                                onAddGoal({
                                                    name: 'Novo Desejo de Compra',
                                                    targetAmount: 0,
                                                    currentAmount: 0,
                                                    priority: -1,
                                                    status: 'active'
                                                });
                                            }}
                                            className="bg-primary-tactile/10 text-primary-tactile border border-primary-tactile/20 px-4 py-2 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest hover:bg-primary-tactile hover:text-white transition-all"
                                        >
                                               + NOVO DESEJO DE COMPRA
                                        </button>
                                    </div>

                                    {sortedGoals.length > 0 ? (
                                        <div className="space-y-4">
                                            {sortedGoals.map((goal) => {
                                                const isReady = goal.targetAmount > 0 && goal.currentAmount >= goal.targetAmount;
                                                const pct = goal.targetAmount > 0 ? Math.min(100, (goal.currentAmount / goal.targetAmount) * 100) : 0;

                                                return (
                                                    <div
                                                        key={goal.id}
                                                        className={`p-5 rounded-xl border transition-all relative group ${
                                                            isReady
                                                                ? 'bg-emerald-500/5 dark:bg-emerald-500/10 border-emerald-500/40 shadow-sm'
                                                                : 'bg-surface border-[#e5e7eb] dark:border-white/10 hover:border-slate-300 dark:hover:border-white/20'
                                                        }`}
                                                    >
                                                        <div className="flex flex-col gap-3">
                                                            {/* Header: Item Title + Ready Badge / Delete button */}
                                                            <div className="flex items-start justify-between gap-3">
                                                                <div className="flex-1">
                                                                    <textarea
                                                                        defaultValue={goal.name}
                                                                        rows={1}
                                                                        placeholder="Nome do desejo/aquisição..."
                                                                        className="w-full bg-transparent border-none p-0 font-sans font-bold text-on-surface text-base outline-none focus:ring-0 resize-none overflow-hidden leading-snug"
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
                                                                    />
                                                                </div>

                                                                <div className="flex items-center gap-2">
                                                                    {isReady && (
                                                                        <span className="text-[9px] font-extrabold bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1">
                                                                            🛒 RECURSOS DISPONÍVEIS
                                                                        </span>
                                                                    )}
                                                                    <button
                                                                        onClick={() => handleTwoStepDelete(`goal_${goal.id}`, () => onDeleteGoal(goal.id))}
                                                                        className={`p-1.5 rounded-soft-touch transition-all ${
                                                                            pendingDeleteKey === `goal_${goal.id}`
                                                                                ? 'bg-accent-tactile text-white scale-110'
                                                                                : 'text-slate-300 hover:text-accent-tactile'
                                                                        }`}
                                                                        title={pendingDeleteKey === `goal_${goal.id}` ? 'Confirmar exclusão' : 'Excluir item'}
                                                                    >
                                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                                        </svg>
                                                                    </button>
                                                                </div>
                                                            </div>

                                                            {/* Amount details */}
                                                            <div className="flex items-center justify-between text-xs font-sans font-semibold">
                                                                <div className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                                                                    <span>R$ {goal.currentAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                                                                    <span>/</span>
                                                                    <GoalTargetInput
                                                                        targetAmount={goal.targetAmount}
                                                                        onSave={(newVal) => onUpdateGoal({ ...goal, targetAmount: newVal })}
                                                                    />
                                                                </div>

                                                                <span className={`text-[10px] font-sans font-bold uppercase tracking-wider ${isReady ? 'text-emerald-600 dark:text-emerald-400' : 'text-indigo-600 dark:text-indigo-400'}`}>
                                                                    {pct.toFixed(1)}% COBERTO
                                                                </span>
                                                            </div>

                                                            {/* Progress bar */}
                                                            <div className="h-2 bg-slate-100 dark:bg-white/5 rounded-lg overflow-hidden w-full border border-[#e5e7eb] dark:border-white/10">
                                                                <div
                                                                    className={`h-full transition-all duration-1000 ${
                                                                        isReady
                                                                            ? 'bg-gradient-to-r from-emerald-500 to-teal-400'
                                                                            : 'bg-gradient-to-r from-indigo-500 to-purple-500'
                                                                    }`}
                                                                    style={{ width: `${pct}%` }}
                                                                ></div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    ) : (
                                        <div className="p-8 border border-dashed border-[#e5e7eb] dark:border-white/10 rounded-lg text-center">
                                            <p className="text-slate-400 font-sans font-semibold uppercase text-[10px]">NENHUM DESEJO OU AQUISIÇÃO CADASTRADO</p>
                                        </div>
                                    )}
                                </FinanceSection>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* RENDAS VIEW (ENTRADA) */}
            {activeTab === 'income' && (
                <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4">

                    {isNFSeGeneratorOpen && (
                        <NFSeGenerator onClose={() => setIsNFSeGeneratorOpen(false)} />
                    )}

                    {/* SEÇÃO DE RENDAS / GANHOS */}
                    <FinanceSection title="Rendas e Rendimentos">
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                            <p className="text-slate-400 font-sans text-[10px] font-bold uppercase tracking-wider">Fontes de Renda Ativas</p>
                            <div className="flex gap-3 w-full md:w-auto">
                                <button
                                    onClick={() => setIsNFSeGeneratorOpen(true)}
                                    className="flex-1 md:flex-none border border-slate-200 dark:border-white/10 bg-surface hover:bg-slate-50 text-on-surface px-4 py-2 flex items-center justify-center gap-2 rounded-lg text-[10px] font-sans font-bold uppercase tracking-wider transition-all shadow-sm"
                                >
                                    <svg className="w-4 h-4 text-primary-tactile" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                    Gerar NFS-e
                                </button>
                                <button
                                    onClick={() => setIsManagingIncomeRubrics(!isManagingIncomeRubrics)}
                                    className={`flex-1 md:flex-none px-4 py-2 flex items-center justify-center rounded-lg text-[10px] font-sans font-bold uppercase tracking-wider transition-all border ${isManagingIncomeRubrics ? 'bg-slate-900 dark:bg-slate-800 text-white border-slate-900 dark:border-slate-850' : 'bg-surface text-slate-700 border-slate-200 dark:border-white/10 hover:bg-slate-50 shadow-sm'}`}
                                >
                                    {isManagingIncomeRubrics ? 'Fechar Fontes' : 'Gerenciar Fontes'}
                                </button>
                                <button onClick={() => {
                                    setNewIncome({ category: settings.incomeCategories?.[0] || 'Renda Principal' });
                                    setIsAddingIncome(true);
                                }} className="flex-1 md:flex-none bg-primary-tactile text-white px-4 py-2 flex items-center justify-center rounded-lg text-[10px] font-sans font-bold uppercase tracking-wider transition-all shadow-md hover:bg-primary">
                                    + Nova Entrada
                                </button>
                            </div>
                        </div>
                                     {/* Gestão de Rubricas de Renda Industrial */}
                        {isManagingIncomeRubrics && (
                            <div className="bg-slate-50 dark:bg-slate-900 text-on-surface p-6 md:p-8 rounded-2xl border border-slate-200 dark:border-white/10 shadow-card animate-in fade-in slide-in-from-top-4 space-y-6">
                                <div className="flex justify-between items-center">
                                    <div>
                                        <h5 className="text-[10px] font-sans font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">// Cadastro de Fontes de Receita</h5>
                                        <p className="text-slate-400 text-[9px] font-semibold uppercase tracking-wider mt-1">Canais de Receita Recorrente</p>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {incomeRubrics.map(rubric => (
                                        <div key={rubric.id} className="bg-surface border border-slate-200 dark:border-white/10 p-4 rounded-xl flex justify-between items-center group hover:bg-slate-50 transition-all shadow-sm">
                                            <div>
                                                <div className="text-[8px] font-sans font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-1 flex items-center gap-2">
                                                    {rubric.category}
                                                    {rubric.eventual && <span className="text-slate-400 dark:text-slate-500">// Eventual</span>}
                                                </div>
                                                <div className="text-xs font-sans font-bold text-on-surface uppercase tracking-tight">{rubric.description}</div>
                                                <div className="text-[9px] text-slate-400 font-sans font-semibold uppercase tracking-wider mt-2 flex items-center gap-2">
                                                    Previsto: Dia {rubric.expectedDay}
                                                    {rubric.defaultAmount ? ` // R$ ${rubric.defaultAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : ' // Valor Variável'}
                                                </div>
                                            </div>
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => {
                                                        setEditingIncomeRubric(rubric);
                                                        setNewIncomeRubric(rubric);
                                                    }}
                                                    className="p-1.5 text-slate-300 hover:text-emerald-500 hover:border-slate-100 transition-all opacity-0 group-hover:opacity-100 border border-transparent rounded-lg"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                </button>
                                                <button onClick={() => handleTwoStepDelete(`income_rubric_${rubric.id}`, () => onDeleteIncomeRubric(rubric.id))} className={`p-1.5 rounded-lg transition-all opacity-0 group-hover:opacity-100 border ${pendingDeleteKey === `income_rubric_${rubric.id}` ? 'bg-rose-500 text-white opacity-100 border-rose-600' : 'text-slate-300 border-transparent hover:text-rose-500 hover:border-rose-100'}`}>
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="bg-surface p-6 rounded-xl border border-slate-200 dark:border-white/10 shadow-sm space-y-4">
                                    <h6 className="text-[10px] font-sans font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-2">
                                        <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
                                        {editingIncomeRubric ? 'Atualizar Fonte' : 'Cadastrar Nova Fonte'}
                                    </h6>
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                                        <input
                                            type="text"
                                            placeholder="Descrição da Renda"
                                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-xs font-sans font-semibold focus:ring-1 focus:ring-emerald-500 outline-none text-on-surface"
                                            value={newIncomeRubric.description || ''}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, description: e.target.value })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Dia Previsto (1-31)"
                                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-xs font-sans font-semibold focus:ring-1 focus:ring-emerald-500 outline-none text-on-surface"
                                            value={newIncomeRubric.expectedDay || ''}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, expectedDay: Number(e.target.value) })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Valor Base (Opcional)"
                                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-xs font-sans font-semibold focus:ring-1 focus:ring-emerald-500 outline-none text-on-surface"
                                            value={newIncomeRubric.defaultAmount || ''}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, defaultAmount: e.target.value ? Number(e.target.value) : undefined })}
                                        />
                                        <select
                                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-xs font-sans font-semibold focus:ring-1 focus:ring-emerald-500 outline-none text-on-surface"
                                            value={newIncomeRubric.category}
                                            onChange={e => setNewIncomeRubric({ ...newIncomeRubric, category: e.target.value })}
                                        >
                                            {(settings.incomeCategories || ['Renda Principal', 'Renda Extra', 'Dividendos', 'Outros']).map(cat => (
                                                <option key={cat} value={cat} className="text-on-surface">{cat}</option>
                                            ))}
                                        </select>
                                        <label className="flex items-center gap-2 px-1 text-[10px] font-sans font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 cursor-pointer select-none">
                                            <input
                                                type="checkbox"
                                                checked={!!newIncomeRubric.eventual}
                                                onChange={e => setNewIncomeRubric({ ...newIncomeRubric, eventual: e.target.checked })}
                                                className="rounded border-slate-300 dark:border-white/20 text-emerald-500 focus:ring-emerald-500"
                                            />
                                            Fonte eventual (não cobrar lançamento todo mês)
                                        </label>
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
                                                className="flex-1 bg-primary-tactile hover:bg-primary text-white rounded-lg px-4 py-2.5 text-[10px] font-sans font-bold uppercase tracking-wider transition-all shadow-sm"
                                            >
                                                {editingIncomeRubric ? 'Salvar' : 'Adicionar'}
                                            </button>
                                            {editingIncomeRubric && (
                                                <button
                                                    onClick={() => {
                                                        setEditingIncomeRubric(null);
                                                        setNewIncomeRubric({ category: 'Renda Principal' });
                                                    }}
                                                    className="bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg px-4 py-2.5 text-xs font-sans font-bold uppercase tracking-wider transition-all"
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

                        {eventualIncomeRubrics.length > 0 && (
                            <div className="mb-6 rounded-lg md:rounded-[2rem] border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/40 p-5 shadow-none md:shadow-card">
                                <div className="mb-3">
                                    <h5 className="text-sm font-bold uppercase tracking-wider text-on-surface">Fontes eventuais</h5>
                                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Renda esporádica — não cobrada todo mês, lance quando ocorrer</p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {eventualIncomeRubrics.map(rubric => (
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
                                            className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-800 px-4 py-2 text-xs font-bold uppercase tracking-wider text-on-surface transition-colors hover:bg-slate-100 dark:hover:bg-slate-700"
                                        >
                                            {rubric.description}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-3">
                            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-emerald-50/20 dark:bg-emerald-950/10 p-6 shadow-card">
                                <div className="text-[9px] font-sans font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-450 mb-2">// Ganhos Confirmados</div>
                                <div className="text-3xl font-sans font-bold tracking-tight text-emerald-700 dark:text-emerald-400">{formatCurrency(incomeReceivedTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-wider text-slate-400">{currentMonthIncomeEntries.filter(entry => entry.isReceived).length} entrada(s) confirmada(s)</div>
                            </div>
                            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-amber-50/20 dark:bg-amber-950/10 p-6 shadow-card">
                                <div className="text-[9px] font-sans font-bold uppercase tracking-wider text-amber-600 dark:text-amber-450 mb-2">// Ganhos Pendentes</div>
                                <div className="text-3xl font-sans font-bold tracking-tight text-amber-750 dark:text-amber-400">{formatCurrency(incomePendingTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-wider text-slate-400">{currentMonthIncomeEntries.filter(entry => !entry.isReceived).length} entrada(s) pendente(s)</div>
                            </div>
                            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900 p-6 shadow-card">
                                <div className="text-[9px] font-sans font-bold uppercase tracking-wider text-slate-550 dark:text-slate-400 mb-2">// Receita Total Projetada</div>
                                <div className="text-3xl font-sans font-bold tracking-tight text-on-surface">{formatCurrency(incomeOverallTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-wider text-slate-400">{currentMonthIncomeEntries.length} lançamento(s) no mês</div>
                            </div>
                        </div>

                        <div className="mb-6 overflow-hidden rounded-2xl border border-slate-200 dark:border-white/10 bg-surface shadow-card">
                            <div className="border-b border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900 p-6">
                                <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider">Filtrar por Descrição</label>
                                        <input
                                            type="text"
                                            placeholder="Buscar descrição..."
                                            value={incomeSearch}
                                            onChange={(e) => setIncomeSearch(e.target.value)}
                                            className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider">Status</label>
                                        <select value={incomeStatusFilter} onChange={(e) => setIncomeStatusFilter(e.target.value as 'all' | 'received' | 'pending')} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile">
                                            <option value="all">Todos os Status</option>
                                            <option value="received">Confirmados</option>
                                            <option value="pending">Pendentes</option>
                                        </select>
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider">Categoria</label>
                                        <select value={incomeCategoryFilter} onChange={(e) => setIncomeCategoryFilter(e.target.value)} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile">
                                            <option value="all">Todas as Fontes</option>
                                            {(settings.incomeCategories || []).map(cat => (
                                                <option key={cat} value={cat}>{cat}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="flex items-end">
                                        <div className="w-full flex items-center justify-center rounded-lg bg-slate-900 text-white px-4 py-2 text-[10px] font-sans font-bold uppercase tracking-wider">
                                            Filtrados: {visibleIncomeEntries.length}
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="min-w-full text-sm">
                                    <thead className="bg-slate-100 dark:bg-slate-900 text-[10px] font-sans uppercase tracking-wider text-slate-500 border-b border-slate-200 dark:border-white/10">
                                        <tr>
                                            <th className="px-4 py-3 text-left font-bold">Conf.</th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('description')} className="flex items-center gap-2">Descrição <span>{incomeSort.key === 'description' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('category')} className="flex items-center gap-2">Categoria <span>{incomeSort.key === 'category' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('day')} className="flex items-center gap-2">Dia Previsto <span>{incomeSort.key === 'day' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('amount')} className="flex items-center gap-2">Valor <span>{incomeSort.key === 'amount' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleIncomeSort('status')} className="flex items-center gap-2">Status <span>{incomeSort.key === 'status' ? (incomeSort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button></th>
                                            <th className="px-4 py-3 text-right font-bold">Ações</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-150 dark:divide-white/10 bg-white dark:bg-slate-900">
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
                                                    <tr className={`cursor-pointer transition-colors font-sans ${isExpanded ? 'bg-slate-50 dark:bg-slate-800 text-on-surface' : 'hover:bg-slate-50 dark:hover:bg-slate-800 text-on-surface'}`} onClick={() => setExpandedIncomeId(isExpanded ? null : entry.id)}>
                                                        <td className="px-4 py-4">
                                                            <input type="checkbox" checked={entry.isReceived} onClick={(e) => e.stopPropagation()} onChange={() => onUpdateIncomeEntry({ ...entry, isReceived: !entry.isReceived })} className="h-4 w-4 rounded-lg border-slate-200 dark:border-white/10 text-primary-tactile focus:ring-0 bg-transparent" />
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <div className="font-bold text-xs">{entry.description}</div>
                                                            {entry.rubricId && <div className="text-[8px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">// Origem Vinculada</div>}
                                                        </td>
                                                        <td className="px-4 py-4 font-bold text-[10px] text-slate-550 dark:text-slate-400 uppercase">{entry.category || 'Entrada'}</td>
                                                        <td className="px-4 py-4 font-bold text-[10px] text-slate-550 dark:text-slate-400 uppercase">Dia {entry.day}</td>
                                                        <td className="px-4 py-4">
                                                            <div className="font-bold text-xs text-emerald-600 dark:text-emerald-400">{formatCurrency(entry.amount)}</div>
                                                            {diff !== 0 && <div className={`text-[9px] font-bold ${diff > 0 ? 'text-emerald-600' : 'text-accent-tactile'}`}>{diff > 0 ? '+' : '-'} {formatCurrency(Math.abs(diff))}</div>}
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <span className={`inline-flex border border-slate-200 dark:border-white/10 px-2 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-wider ${entry.isReceived ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/20 dark:text-emerald-405' : 'bg-amber-50 text-amber-600 dark:bg-amber-950/20 dark:text-amber-405'}`}>
                                                                {entry.isReceived ? 'Confirmado' : 'Pendente'}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <div className="flex items-center justify-end gap-2">
                                                                <button onClick={(e) => { e.stopPropagation(); setExpandedIncomeId(isExpanded ? null : entry.id); }} className="rounded-lg p-1 text-slate-300 hover:text-on-surface">
                                                                    <svg className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
                                                                </button>
                                                                <button onClick={(e) => { e.stopPropagation(); handleTwoStepDelete(`income_entry_${entry.id}`, () => onDeleteIncomeEntry(entry.id)); }} className={`rounded-lg p-1 transition-colors ${pendingDeleteKey === `income_entry_${entry.id}` ? 'bg-accent-tactile text-white' : 'text-slate-350 hover:text-accent-tactile'}`}>
                                                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                    {isExpanded && (
                                                        <tr className="bg-slate-50 dark:bg-slate-800">
                                                            <td colSpan={7} className="px-4 py-6 border-b border-slate-200 dark:border-white/10">
                                                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
                                                                    <div className="space-y-1">
                                                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Descrição</label>
                                                                        <input type="text" defaultValue={entry.description} onBlur={(e) => onUpdateIncomeEntry({ ...entry, description: e.target.value })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500" />
                                                                    </div>
                                                                    <div className="space-y-1">
                                                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Valor (R$)</label>
                                                                        <input type="number" defaultValue={entry.amount} onBlur={(e) => onUpdateIncomeEntry({ ...entry, amount: Number(e.target.value) })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500" />
                                                                    </div>
                                                                    <div className="space-y-1">
                                                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Dia Previsto</label>
                                                                        <input type="number" min={1} max={31} defaultValue={entry.day} onBlur={(e) => onUpdateIncomeEntry({ ...entry, day: Number(e.target.value) })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500" />
                                                                    </div>
                                                                    <div className="space-y-1">
                                                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Categoria</label>
                                                                        <select defaultValue={entry.category} onBlur={(e) => onUpdateIncomeEntry({ ...entry, category: e.target.value })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-emerald-500">
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
                                                <td colSpan={7} className="px-4 py-12 text-center text-[10px] font-sans font-semibold uppercase tracking-wider text-slate-400">Nenhum lançamento de entrada encontrado</td>
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
                </div>
            )}

            {/* OBRIGAÇÕES VIEW (SAÍDA) */}
            {activeTab === 'expense' && (
                <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4">
                    {/* SEÇÃO DE CONTAS / OBRIGAÇÕES */}
                    <FinanceSection title="Obrigações e Despesas">
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                            <div>
                                <h5 className="text-[10px] font-sans font-bold text-slate-550 dark:text-slate-400 uppercase tracking-wider">// Gestão de Obrigações Fixas</h5>
                                <p className="text-slate-400 text-[9px] font-semibold uppercase tracking-wider mt-1">Central de Pagamento de Contas</p>
                            </div>
                            <div className="flex gap-3 w-full md:w-auto">
                                <button
                                    onClick={() => setIsManagingRubrics(!isManagingRubrics)}
                                    className={`flex-1 md:flex-none px-4 py-2.5 rounded-lg text-[10px] font-sans font-bold uppercase tracking-wider transition-all border ${isManagingRubrics ? 'bg-slate-900 dark:bg-slate-800 text-white border-slate-900 dark:border-slate-850' : 'bg-surface text-slate-700 border-slate-200 dark:border-white/10 hover:bg-slate-50 shadow-sm'}`}
                                >
                                    {isManagingRubrics ? 'Fechar Categorias' : 'Gerenciar Categorias'}
                                </button>
                                <button onClick={() => {
                                    setNewBill({ category: settings.billCategories?.[0] || 'Conta Fixa' });
                                    setIsAddingBill(true);
                                }} className="flex-1 md:flex-none bg-primary-tactile hover:bg-primary text-white px-4 py-2.5 rounded-lg text-[10px] font-sans font-bold uppercase tracking-wider transition-all shadow-md">
                                    + Nova Obrigação
                                </button>
                            </div>
                        </div>

                        {/* Gestão de Rubricas Industrial */}
                        {isManagingRubrics && (
                            <div className="bg-slate-50 dark:bg-slate-900 text-on-surface p-6 md:p-8 rounded-2xl border border-slate-200 dark:border-white/10 shadow-card animate-in fade-in slide-in-from-top-4 mb-10 space-y-6">
                                <div className="flex justify-between items-center">
                                    <div>
                                        <h5 className="text-[10px] font-sans font-bold uppercase tracking-wider text-primary-tactile">// Cadastro de Obrigações Recorrentes</h5>
                                        <p className="text-slate-400 text-[9px] font-semibold uppercase tracking-wider mt-1">Base Mensal de Compromissos</p>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {billRubrics.map(rubric => (
                                        <div key={rubric.id} className="bg-surface border border-slate-200 dark:border-white/10 p-4 rounded-xl flex justify-between items-center group hover:bg-slate-50 transition-all shadow-sm">
                                            <div>
                                                <div className="text-[8px] font-sans font-bold text-primary-tactile uppercase tracking-wider mb-1">{rubric.category}</div>
                                                <div className="text-xs font-sans font-bold text-on-surface uppercase tracking-tight">{rubric.description}</div>
                                                <div className="text-[9px] text-slate-400 font-sans font-semibold uppercase tracking-wider mt-2 flex items-center gap-2">
                                                    Vencimento: Dia {rubric.dueDay}
                                                    {rubric.defaultAmount ? ` // R$ ${rubric.defaultAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : ' // Valor Variável'}
                                                    {rubric.pixCode && ' // Pix Salvo'}
                                                </div>
                                            </div>
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => {
                                                        setEditingRubric(rubric);
                                                        setNewRubric(rubric);
                                                    }}
                                                    className="p-1.5 text-slate-350 hover:text-primary-tactile transition-all opacity-0 group-hover:opacity-100 border border-transparent rounded-lg"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                </button>
                                                <button onClick={() => handleTwoStepDelete(`rubric_${rubric.id}`, () => onDeleteRubric(rubric.id))} className={`p-1.5 rounded-lg transition-all opacity-0 group-hover:opacity-100 border ${pendingDeleteKey === `rubric_${rubric.id}` ? 'bg-rose-500 text-white opacity-100 border-rose-600' : 'text-slate-300 border-transparent hover:text-rose-500 hover:border-rose-100'}`}>
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="bg-surface p-6 rounded-xl border border-slate-200 dark:border-white/10 shadow-sm space-y-4">
                                    <h6 className="text-[10px] font-sans font-bold text-slate-550 uppercase tracking-wider mb-2 flex items-center gap-2">
                                        <span className="w-1.5 h-1.5 bg-primary-tactile rounded-full"></span>
                                        {editingRubric ? 'Atualizar Categoria' : 'Cadastrar Nova Categoria'}
                                    </h6>
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
                                        <input
                                            type="text"
                                            placeholder="Nome da Obrigação"
                                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-on-surface"
                                            value={newRubric.description || ''}
                                            onChange={e => setNewRubric({ ...newRubric, description: e.target.value })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Dia do Vencimento"
                                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-on-surface"
                                            value={newRubric.dueDay || ''}
                                            onChange={e => setNewRubric({ ...newRubric, dueDay: Number(e.target.value) })}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Valor Fixo (Opcional)"
                                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-on-surface"
                                            value={newRubric.defaultAmount || ''}
                                            onChange={e => setNewRubric({ ...newRubric, defaultAmount: e.target.value ? Number(e.target.value) : undefined })}
                                        />
                                        <select
                                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-on-surface"
                                            value={newRubric.category}
                                            onChange={e => setNewRubric({ ...newRubric, category: e.target.value })}
                                        >
                                            {(settings.billCategories || ['Conta Fixa', 'Poupança', 'Investimento']).map(cat => (
                                                <option key={cat} value={cat} className="text-on-surface">{cat}</option>
                                            ))}
                                        </select>
                                        <input
                                            type="text"
                                            placeholder="Chave Pix (Opcional)"
                                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-4 py-2.5 text-xs font-sans font-semibold focus:ring-1 focus:ring-primary-tactile outline-none text-on-surface lg:col-span-1"
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
                                                className="flex-1 bg-primary-tactile hover:bg-primary text-white rounded-lg px-4 py-2.5 text-[10px] font-sans font-bold uppercase tracking-wider transition-all shadow-sm"
                                            >
                                                {editingRubric ? 'Salvar' : 'Adicionar'}
                                            </button>
                                            {editingRubric && (
                                                <button
                                                    onClick={() => {
                                                        setEditingRubric(null);
                                                        setNewRubric({ category: 'Conta Fixa' });
                                                    }}
                                                    className="bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg px-4 py-2.5 text-xs font-sans font-bold uppercase tracking-wider transition-all"
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
                            <div className="mb-6 bg-surface p-6 md:p-8 rounded-2xl border border-slate-200 dark:border-white/10 shadow-card animate-in fade-in slide-in-from-top-2 space-y-6">
                                <div>
                                    <h4 className="text-[10px] font-sans font-bold text-primary-tactile uppercase tracking-wider flex items-center gap-2">
                                        <span className="w-1.5 h-1.5 bg-primary-tactile rounded-full"></span>
                                        Registrar Nova Obrigação Fixa
                                    </h4>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Descrição</label>
                                        <input type="text" placeholder="ex: Aluguel, Internet..." className="w-full px-4 py-2.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.description || ''} onChange={(e) => setNewBill({ ...newBill, description: e.target.value })} />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Valor (R$)</label>
                                        <input type="number" placeholder="0.00" className="w-full px-4 py-2.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.amount || ''} onChange={(e) => setNewBill({ ...newBill, amount: Number(e.target.value) })} />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Categoria</label>
                                        <select className="w-full px-4 py-2.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.category || ''} onChange={(e) => setNewBill({ ...newBill, category: e.target.value })}>
                                            <option value="">Selecionar Categoria</option>
                                            {(settings.billCategories || ['Conta Fixa', 'Poupança', 'Investimento']).map(cat => (
                                                <option key={cat} value={cat}>{cat}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Dia do Vencimento</label>
                                        <input type="number" placeholder="1-31" max={31} min={1} className="w-full px-4 py-2.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.dueDay || ''} onChange={(e) => setNewBill({ ...newBill, dueDay: Number(e.target.value) })} />
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Código de Barras (Linha Digitável)</label>
                                        <input type="text" placeholder="Cole a linha digitável do boleto..." className="w-full px-4 py-2.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.barcode || ''} onChange={(e) => setNewBill({ ...newBill, barcode: e.target.value })} />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block">Código Pix Copia e Cola</label>
                                        <input type="text" placeholder="Cole o código Pix Copia e Cola..." className="w-full px-4 py-2.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-on-surface font-sans font-semibold text-xs outline-none focus:ring-1 focus:ring-primary-tactile" value={newBill.pixCode || ''} onChange={(e) => setNewBill({ ...newBill, pixCode: e.target.value })} />
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className={`border border-dashed rounded-lg p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${newBill.attachmentUrl ? 'border-primary-tactile bg-blue-50/50' : 'border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 hover:bg-slate-100'}`} onClick={() => {
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
                                            <div className="flex items-center gap-2 text-primary-tactile font-sans font-bold text-[10px] uppercase tracking-wider">
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                                Boleto Anexado
                                            </div>
                                        ) : (
                                            <div className="text-center text-slate-400">
                                                <p className="text-[10px] font-sans font-bold uppercase tracking-wider">Anexar PDF ou Imagem do Boleto</p>
                                            </div>
                                        )}
                                    </div>

                                    <div className={`border border-dashed rounded-lg p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${newBill.pixQrCodeUrl ? 'border-emerald-250 bg-emerald-50/50' : 'border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 hover:bg-slate-100'}`} onClick={() => {
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
                                            <div className="flex items-center gap-2 text-emerald-600 font-sans font-bold text-[10px] uppercase tracking-wider">
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                                QR Code Pix Carregado
                                            </div>
                                        ) : (
                                            <div className="text-center text-slate-400">
                                                <p className="text-[10px] font-sans font-bold uppercase tracking-wider">Carregar Imagem do QR Code Pix</p>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-white/10">
                                    <button onClick={() => setIsAddingBill(false)} className="px-5 py-2.5 border border-slate-200 dark:border-white/10 rounded-lg text-xs font-bold text-slate-500 hover:text-on-surface hover:bg-slate-50 dark:hover:bg-slate-850 transition-all">Cancelar</button>
                                    <button onClick={handleSaveBill} disabled={uploading === true || !newBill.description || newBill.amount === undefined} className={`px-8 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${uploading || !newBill.description || newBill.amount === undefined ? 'bg-slate-150 text-slate-400 dark:bg-slate-800 cursor-not-allowed' : 'bg-primary-tactile hover:bg-primary text-white shadow-sm'}`}>
                                        {uploading ? 'Processando...' : 'Salvar Obrigação'}
                                    </button>
                                </div>
                            </div>
                        )}

                        {pendingBillRubrics.length > 0 && (
                            <div className="mb-6 rounded-2xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900 p-6 shadow-card">
                                <div className="mb-4">
                                    <h5 className="text-[10px] font-sans font-bold uppercase tracking-wider text-slate-650 dark:text-slate-450">// Obrigações pendentes de lançamento no período</h5>
                                    <p className="text-[9px] font-sans font-semibold uppercase tracking-wider text-slate-400 mt-1 italic">Clique em uma obrigação para pré-preencher um novo lançamento</p>
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
                                            className="rounded-lg border border-slate-200 dark:border-white/10 bg-surface text-slate-700 dark:text-slate-350 hover:bg-slate-50 dark:hover:bg-slate-800 hover:border-slate-300 dark:hover:border-white/20 px-4 py-2 text-xs font-bold uppercase tracking-wider transition-all shadow-sm"
                                        >
                                            {rubric.description}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-3">
                            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-emerald-50/20 dark:bg-emerald-950/10 p-6 shadow-card">
                                <div className="text-[9px] font-sans font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-450 mb-2">// Total Pago</div>
                                <div className="text-3xl font-sans font-bold tracking-tight text-emerald-700 dark:text-emerald-400">{formatCurrency(billsPaidTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-wider text-slate-400">{currentMonthBills.filter(bill => bill.isPaid).length} conta(s) paga(s)</div>
                            </div>
                            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-rose-50/20 dark:bg-rose-950/10 p-6 shadow-card">
                                <div className="text-[9px] font-sans font-bold uppercase tracking-wider text-rose-600 dark:text-rose-450 mb-2">// Total Pendente</div>
                                <div className="text-3xl font-sans font-bold tracking-tight text-rose-700 dark:text-rose-400">{formatCurrency(billsPendingTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-wider text-slate-400">{currentMonthBills.filter(bill => !bill.isPaid).length} conta(s) pendente(s)</div>
                            </div>
                            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900 p-6 shadow-card">
                                <div className="text-[9px] font-sans font-bold uppercase tracking-wider text-slate-550 dark:text-slate-400 mb-2">// Valor Total das Contas</div>
                                <div className="text-3xl font-sans font-bold tracking-tight text-on-surface">{formatCurrency(billsOverallTotal)}</div>
                                <div className="mt-3 text-[9px] font-sans font-semibold uppercase tracking-wider text-slate-400">{currentMonthBills.length} obrigação(ões) no período</div>
                            </div>
                        </div>
                        <div className="mb-6 overflow-hidden rounded-2xl border border-slate-200 dark:border-white/10 bg-surface shadow-card">
                            <div className="border-b border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900 p-6">
                                <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider">Filtrar por Descrição / Chave</label>
                                        <input
                                            type="text"
                                            placeholder="Buscar por descrição, Pix..."
                                            value={billSearch}
                                            onChange={(e) => setBillSearch(e.target.value)}
                                            className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider">Status</label>
                                        <select value={billStatusFilter} onChange={(e) => setBillStatusFilter(e.target.value as 'all' | 'paid' | 'unpaid')} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile">
                                            <option value="all">Todos os Status</option>
                                            <option value="paid">Pagas</option>
                                            <option value="unpaid">Pendentes</option>
                                        </select>
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider">Categoria</label>
                                        <select value={billCategoryFilter} onChange={(e) => setBillCategoryFilter(e.target.value)} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile">
                                            <option value="all">Todas as Categorias</option>
                                            {(settings.billCategories || []).map(cat => (
                                                <option key={cat} value={cat}>{cat}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="flex items-end">
                                        <div className="w-full rounded-lg border border-slate-250 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500 flex items-center justify-center">
                                            Pagas: {visibleBills.filter(bill => bill.isPaid).length} | Pendentes: {visibleBills.filter(bill => !bill.isPaid).length}
                                        </div>
                                    </div>
                                    <div className="flex items-end">
                                        <div className="w-full flex items-center justify-center rounded-lg bg-slate-900 text-white px-4 py-2 text-[10px] font-bold uppercase tracking-wider">
                                            Filtrados: {visibleBills.length}
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="min-w-full text-sm">
                                    <thead className="bg-slate-100 dark:bg-slate-900 text-[10px] font-sans uppercase tracking-wider text-slate-500 border-b border-slate-200 dark:border-white/10">
                                        <tr>
                                            <th className="px-4 py-3 text-left font-bold">Pago</th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleBillSort('description')} className="flex items-center gap-2">Descrição <span>{getSortIndicator(billSort.key === 'description', billSort.direction)}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleBillSort('category')} className="flex items-center gap-2">Categoria <span>{getSortIndicator(billSort.key === 'category', billSort.direction)}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleBillSort('dueDay')} className="flex items-center gap-2">Vencimento <span>{getSortIndicator(billSort.key === 'dueDay', billSort.direction)}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold"><button onClick={() => toggleBillSort('amount')} className="flex items-center gap-2">Valor <span>{getSortIndicator(billSort.key === 'amount', billSort.direction)}</span></button></th>
                                            <th className="px-4 py-3 text-left font-bold">Anexo</th>
                                            <th className="px-4 py-3 text-left font-bold">Pix</th>
                                            <th className="px-4 py-3 text-left font-bold">Status</th>
                                            <th className="px-4 py-3 text-right font-bold">Ações</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-150 dark:divide-white/10 bg-white dark:bg-slate-900">
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
                                                    <tr className={`cursor-pointer transition-colors font-sans ${isExpanded ? 'bg-slate-50 dark:bg-slate-800' : 'hover:bg-slate-50 dark:hover:bg-slate-800'}`} onClick={() => setExpandedBillId(isExpanded ? null : bill.id)}>
                                                        <td className="px-4 py-4">
                                                            <input
                                                                type="checkbox"
                                                                checked={bill.isPaid}
                                                                onClick={(e) => e.stopPropagation()}
                                                                onChange={() => onUpdateBill({ ...bill, isPaid: !bill.isPaid })}
                                                                className="h-4 w-4 rounded-lg border-slate-200 dark:border-white/10 text-emerald-600 focus:ring-0 bg-transparent"
                                                            />
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <div className={`font-bold text-xs ${bill.isPaid ? 'text-slate-350 dark:text-slate-500 line-through font-normal' : 'text-on-surface font-semibold'}`}>{bill.description}</div>
                                                            {bill.rubricId && <div className="text-[8px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">// Origem Vinculada</div>}
                                                        </td>
                                                        <td className="px-4 py-4 font-bold text-[10px] text-slate-550 dark:text-slate-400 uppercase">{bill.category || 'Compromisso'}</td>
                                                        <td className="px-4 py-4 font-bold text-[10px] text-slate-550 dark:text-slate-400 uppercase">Dia {bill.dueDay}</td>
                                                        <td className="px-4 py-4">
                                                            <div className={`font-bold text-xs ${bill.isPaid ? 'text-slate-350 dark:text-slate-500 line-through font-normal' : 'text-on-surface font-semibold'}`}>{formatCurrency(bill.amount)}</div>
                                                            {diff !== 0 && <div className={`text-[9px] font-bold ${diff < 0 ? 'text-emerald-600' : 'text-accent-tactile'}`}>{diff < 0 ? '-' : '+'} {formatCurrency(Math.abs(diff))}</div>}
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <span className={`inline-flex border border-slate-200 dark:border-white/10 px-2 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-wider ${bill.barcode ? 'bg-slate-900 text-white dark:bg-slate-800' : 'bg-slate-50 text-slate-300 dark:bg-slate-950 dark:text-slate-600'}`}>
                                                                {bill.barcode ? 'Disponível' : 'Nenhum'}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <span className={`inline-flex border border-slate-200 dark:border-white/10 px-2 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-wider ${bill.pixCode ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/20 dark:text-emerald-405' : 'bg-slate-50 text-slate-300 dark:bg-slate-950 dark:text-slate-600'}`}>
                                                                {bill.pixCode ? 'Disponível' : 'Nenhum'}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <span className={`inline-flex border border-slate-200 dark:border-white/10 px-2 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-wider ${bill.isPaid ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/20 dark:text-emerald-405' : 'bg-amber-50 text-amber-600 dark:bg-amber-950/20 dark:text-amber-405'}`}>
                                                                {bill.isPaid ? 'Pago' : 'Pendente'}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <div className="flex items-center justify-end gap-2">
                                                                <button onClick={(e) => { e.stopPropagation(); setExpandedBillId(isExpanded ? null : bill.id); }} className="rounded-lg p-1 text-slate-300 hover:text-on-surface">
                                                                    <svg className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
                                                                </button>
                                                                <button onClick={(e) => { e.stopPropagation(); handleTwoStepDelete(`bill_${bill.id}`, () => onDeleteBill(bill.id)); }} className={`rounded-lg p-1 transition-colors ${pendingDeleteKey === `bill_${bill.id}` ? 'bg-accent-tactile text-white' : 'text-slate-350 hover:text-accent-tactile'}`}>
                                                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                    {isExpanded && (
                                                        <tr className="bg-slate-50 dark:bg-slate-800">
                                                            <td colSpan={9} className="px-4 py-6 border-b border-slate-200 dark:border-white/10">
                                                                <div className="space-y-6">
                                                                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
                                                                        <div>
                                                                            <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block mb-1">Descrição</label>
                                                                            <input type="text" defaultValue={bill.description} onBlur={(e) => onUpdateBill({ ...bill, description: e.target.value })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface" />
                                                                        </div>
                                                                        <div>
                                                                            <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block mb-1">Valor (R$)</label>
                                                                            <input type="number" defaultValue={bill.amount} onBlur={(e) => onUpdateBill({ ...bill, amount: Number(e.target.value) })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface" />
                                                                        </div>
                                                                        <div>
                                                                            <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block mb-1">Dia do Vencimento</label>
                                                                            <input type="number" min={1} max={31} defaultValue={bill.dueDay} onBlur={(e) => onUpdateBill({ ...bill, dueDay: Number(e.target.value) })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface" />
                                                                        </div>
                                                                        <div>
                                                                            <label className="text-[10px] font-sans font-semibold text-slate-500 uppercase tracking-wider block mb-1">Categoria</label>
                                                                            <select defaultValue={bill.category} onBlur={(e) => onUpdateBill({ ...bill, category: e.target.value })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-2 text-xs font-sans font-semibold text-on-surface">
                                                                                {(settings.billCategories || ['Conta Fixa', 'Poupança', 'Investimento']).map(cat => (
                                                                                    <option key={cat} value={cat}>{cat}</option>
                                                                                ))}
                                                                            </select>
                                                                        </div>
                                                                    </div>

                                                                    <div className="flex border-b border-slate-200 dark:border-white/10">
                                                                        <button
                                                                            onClick={(e) => { e.stopPropagation(); setActiveBillTabs(prev => ({ ...prev, [bill.id]: 'codigo' })); }}
                                                                            className={`px-4 py-2 text-[10px] font-sans font-bold uppercase tracking-wider transition-colors border-b-2 ${activeBillTab === 'codigo' ? 'border-primary-tactile text-on-surface font-bold' : 'border-transparent text-slate-400 hover:text-on-surface'}`}
                                                                        >
                                                                            Códigos de Pagamento
                                                                        </button>
                                                                        <button
                                                                            onClick={(e) => { e.stopPropagation(); setActiveBillTabs(prev => ({ ...prev, [bill.id]: 'arquivo' })); }}
                                                                            className={`px-4 py-2 text-[10px] font-sans font-bold uppercase tracking-wider transition-colors border-b-2 ${activeBillTab === 'arquivo' ? 'border-primary-tactile text-on-surface' : 'border-transparent text-slate-400 hover:text-on-surface'}`}
                                                                        >
                                                                            Anexos e Arquivos
                                                                        </button>
                                                                    </div>

                                                                    {activeBillTab === 'codigo' ? (
                                                                        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                                                                            <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 p-4 shadow-sm">
                                                                                <label className="mb-2 block text-[9px] font-sans font-bold uppercase tracking-wider text-slate-500">Código de Barras</label>
                                                                                <div className="flex gap-2">
                                                                                    <input type="text" defaultValue={bill.barcode || ''} onBlur={(e) => onUpdateBill({ ...bill, barcode: e.target.value })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900 px-4 py-2 font-sans text-xs font-semibold text-on-surface" />
                                                                                    {bill.barcode && (
                                                                                        <button onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(bill.barcode || ''); }} className="rounded-lg bg-slate-900 text-white px-4 py-2 text-[9px] font-sans font-bold uppercase tracking-wider hover:bg-slate-800 transition-all">
                                                                                            Copiar
                                                                                        </button>
                                                                                    )}
                                                                                </div>
                                                                            </div>
                                                                            <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 p-4 shadow-sm">
                                                                                <label className="mb-2 block text-[9px] font-sans font-bold uppercase tracking-wider text-slate-500">Código Pix Copia e Cola</label>
                                                                                <div className="flex gap-2">
                                                                                    <input type="text" defaultValue={bill.pixCode || ''} onBlur={(e) => onUpdateBill({ ...bill, pixCode: e.target.value })} className="w-full rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900 px-4 py-2 font-sans text-xs font-semibold text-on-surface" />
                                                                                    {bill.pixCode && (
                                                                                        <button onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(bill.pixCode || ''); }} className="rounded-lg bg-slate-900 text-white px-4 py-2 text-[9px] font-sans font-bold uppercase tracking-wider hover:bg-slate-800 transition-all">
                                                                                            Copiar
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
                                                                                className={`cursor-pointer rounded-xl border border-dashed p-4 transition-colors ${bill.attachmentUrl ? 'border-primary-tactile bg-blue-50/50 dark:bg-blue-950/10' : 'border-slate-250 dark:border-white/10 bg-white dark:bg-slate-950 hover:bg-slate-50 dark:hover:bg-slate-900'}`}
                                                                            >
                                                                                <div className="mb-2 text-[9px] font-sans font-bold uppercase tracking-wider text-slate-500">Arquivo do Boleto (PDF/Imagem)</div>
                                                                                <div className="text-[10px] font-sans font-semibold text-on-surface uppercase">{bill.attachmentUrl ? 'Arquivo Carregado' : 'Clique para anexar arquivo'}</div>
                                                                                {bill.attachmentUrl && (
                                                                                    <a href={bill.attachmentUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="mt-3 inline-flex border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-1 rounded-lg text-[9px] font-sans font-bold uppercase tracking-wider text-on-surface shadow-sm hover:bg-slate-50">
                                                                                        Visualizar Documento
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
                                                                                className={`cursor-pointer rounded-xl border border-dashed p-4 transition-colors ${bill.pixQrCodeUrl ? 'border-emerald-250 bg-emerald-50/50 dark:bg-emerald-950/10' : 'border-slate-250 dark:border-white/10 bg-white dark:bg-slate-950 hover:bg-slate-50 dark:hover:bg-slate-900'}`}
                                                                            >
                                                                                <div className="mb-2 text-[9px] font-sans font-bold uppercase tracking-wider text-slate-550 dark:text-slate-400">QR Code Pix (Imagem)</div>
                                                                                <div className="text-[10px] font-sans font-semibold text-on-surface uppercase">{bill.pixQrCodeUrl ? 'Arquivo Carregado' : 'Clique para anexar arquivo'}</div>
                                                                                {bill.pixQrCodeUrl && (
                                                                                    <a href={bill.pixQrCodeUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="mt-3 inline-flex border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 px-4 py-1 rounded-lg text-[9px] font-sans font-bold uppercase tracking-wider text-on-surface shadow-sm hover:bg-slate-50">
                                                                                        Visualizar Documento
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
                                                <td colSpan={9} className="px-4 py-12 text-center text-xs font-sans font-semibold text-slate-400">Nenhuma obrigação encontrada</td>
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
