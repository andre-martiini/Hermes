import React, { useEffect, useMemo, useState } from 'react';
import { arrayUnion, collection, doc, limit, onSnapshot, orderBy, query, runTransaction, updateDoc, where } from 'firebase/firestore';
import { db } from './firebase';
import {
    Tarefa, FinanceTransaction, FinanceSettings, FixedBill, IncomeEntry,
    HealthWeight, HealthSettings, ExerciseLog, WalkBlock,
    formatDateLocalISO, sumWalkBlocksKm
} from './types';
import { buildDiaryEmailNote, buildDiaryGenericNote } from './src/utils/diaryEntries';

interface DashboardViewProps {
    tarefas: Tarefa[];
    isDark?: boolean;
    financeTransactions: FinanceTransaction[];
    financeSettings: FinanceSettings;
    fixedBills: FixedBill[];
    incomeEntries: IncomeEntry[];
    healthWeights: HealthWeight[];
    healthSettings: HealthSettings;
    exerciseLogs: ExerciseLog[];
    onSaveExerciseLog?: (date: string, data: Partial<ExerciseLog>) => Promise<void>;
    onAddHealthWeight?: (weight: number, date: string) => Promise<void>;
    unidades: { id: string, nome: string }[];
    currentMonth: number;
    currentYear: number;
    onNavigate: (view: 'gallery' | 'finance' | 'saude') => void;
}

// --- CARD COMPONENT (Hermes Corporate Modern Design) ---
interface DashboardCardProps {
    title: string;
    onRedirect?: () => void;
    children: React.ReactNode;
    isDark?: boolean;
    headerAction?: React.ReactNode;
    className?: string;
    style?: React.CSSProperties;
}

const DashboardCard: React.FC<DashboardCardProps> = ({
    title,
    onRedirect,
    children,
    isDark = false,
    headerAction,
    className = "",
    style = {}
}) => {
    const isClickable = !!onRedirect;
    const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
        if (!onRedirect) return;
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onRedirect();
        }
    };

    return (
        <div
            onClick={onRedirect}
            onKeyDown={isClickable ? handleKeyDown : undefined}
            style={{
                boxShadow: isDark
                    ? '0 6px 12px rgba(0, 0, 0, 0.4), 0 4px 4px rgba(0, 0, 0, 0.2)'
                    : '0 6px 12px rgba(21, 28, 39, 0.05), 0 4px 4px rgba(21, 28, 39, 0.03)',
                fontFamily: 'Inter, sans-serif',
                ...style
            }}
            className={`group p-5 rounded-2xl border transition-all duration-300 flex flex-col min-h-0 shrink-0 ${
                isClickable ? 'cursor-pointer hover:border-[#861fdd]/40 hover:bg-slate-50/50 dark:hover:bg-slate-900/10' : ''
            } ${
                isDark
                    ? 'bg-[#151c27] border-[#2a313d] text-white'
                    : 'bg-[#ffffff] border-[#f3f4f6] text-[#151c27]'
            } ${className}`}
            role={isClickable ? "button" : undefined}
            tabIndex={isClickable ? 0 : undefined}
        >
            <div className="flex items-center justify-between mb-4 shrink-0">
                <h3 className={`text-xs font-bold uppercase tracking-[0.05em] font-sans ${
                    isDark ? 'text-[#ebf1ff]' : 'text-[#151c27]'
                }`}>
                    {title}
                </h3>
                <div className="flex items-center gap-1.5" onClick={(e) => isClickable && e.stopPropagation()}>
                    {headerAction}
                    {isClickable && (
                        <div className={`p-1.5 rounded-lg transition-all ${
                            isDark
                                ? 'text-slate-500 group-hover:bg-white/5 group-hover:text-[#ddb8ff]'
                                : 'text-slate-400 group-hover:bg-[#f5f3ff] group-hover:text-[#7800ce]'
                        }`}>
                            <svg className="w-4 h-4 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                            </svg>
                        </div>
                    )}
                </div>
            </div>
            <div className="flex-1 flex flex-col justify-start min-h-0">
                {children}
            </div>
        </div>
    );
};

// --- MASKED DATA PLACEHOLDER ---
const HiddenMoney = ({ className = "", compact = false }: { className?: string, compact?: boolean }) => (
    <span className={`inline-block font-bold tracking-normal select-none ${className}`} aria-label="valor oculto">
        <span className="opacity-70">R$</span> {compact ? '••••' : '••••••'}
    </span>
);

const getFinanceDateParts = (dateValue?: string) => {
    if (!dateValue) return null;

    const isoDate = dateValue.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoDate) {
        return {
            year: Number(isoDate[1]),
            month: Number(isoDate[2]) - 1,
            day: Number(isoDate[3])
        };
    }

    const fallbackDate = new Date(dateValue);
    if (Number.isNaN(fallbackDate.getTime())) return null;

    return {
        year: fallbackDate.getFullYear(),
        month: fallbackDate.getMonth(),
        day: fallbackDate.getDate()
    };
};

// --- FILA WEB DE SUGESTÕES DE VÍNCULO SINAL↔AÇÃO (functions/email_action_linker.py) ---
// Complementa a confirmação via Telegram: mostra sugestões pending/expired de
// qualquer canal (e-mail, SIPAC, Calendar, WhatsApp, ...) para decidir pelo
// navegador o que não foi respondido no Telegram a tempo.
const _CANAL_ICONS: Record<string, string> = { email: '📧', whatsapp: '📱', sipac: '📋', calendar: '📅', pagina: '🌐' };
const _CANAL_LABELS: Record<string, string> = {
    email: 'E-mail', whatsapp: 'Conversa de WhatsApp', sipac: 'Processo SIPAC', calendar: 'Reunião', pagina: 'Página monitorada'
};

interface ActionLinkSuggestion {
    id: string;
    canal?: string;
    titulo_sinal?: string;
    origem_sinal?: string;
    link_externo?: string;
    resumo?: string;
    task_id?: string;
    task_titulo?: string;
    task_status?: string;
    reativar_sugerido?: boolean;
    status: 'pending' | 'expired';
    google_message_id?: string;
    analyzed_at?: string;
}

const EmailLinkSuggestionsPanel: React.FC<{ isDark?: boolean }> = ({ isDark = false }) => {
    const [suggestions, setSuggestions] = useState<ActionLinkSuggestion[]>([]);
    const [busyId, setBusyId] = useState<string | null>(null);

    useEffect(() => {
        const unsubscribers = (['pending', 'expired'] as const).map(status => {
            const q = query(collection(db, 'email_action_suggestions'), where('status', '==', status));
            return onSnapshot(q, snap => {
                const items: ActionLinkSuggestion[] = snap.docs.map(d => ({ id: d.id, ...(d.data() as any), status }));
                setSuggestions(prev => [...prev.filter(s => s.status !== status), ...items]);
            });
        });
        return () => unsubscribers.forEach(unsub => unsub());
    }, []);

    const sorted = useMemo(
        () => [...suggestions].sort((a, b) => (b.analyzed_at || '').localeCompare(a.analyzed_at || '')),
        [suggestions]
    );

    if (sorted.length === 0) return null;

    const decide = async (suggestion: ActionLinkSuggestion, action: 'ok' | 'on' | 'no') => {
        setBusyId(suggestion.id);
        try {
            const nowIso = new Date().toISOString();
            const suggestionRef = doc(db, 'email_action_suggestions', suggestion.id);

            if (action === 'no') {
                await updateDoc(suggestionRef, { status: 'dismissed', decided_at: nowIso });
            } else if (suggestion.task_id) {
                const canal = suggestion.canal || 'email';
                const titulo = suggestion.titulo_sinal || '(sem título)';
                const origem = suggestion.origem_sinal || '';
                const nota = canal === 'email'
                    ? buildDiaryEmailNote(titulo, origem, `https://mail.google.com/mail/u/0/#all/${suggestion.google_message_id || suggestion.id}`, suggestion.resumo || '')
                    : buildDiaryGenericNote(_CANAL_ICONS[canal] || '🔔', _CANAL_LABELS[canal] || 'Sinal', titulo, origem, suggestion.resumo || '', suggestion.link_externo);
                const reactivate = action === 'on';
                const taskRef = doc(db, 'tarefas', suggestion.task_id);

                // Transação: só aplica se a sugestão ainda estiver "pending" (evita duplicar a
                // nota no diário se o Telegram e esta fila web decidirem a mesma sugestão quase
                // ao mesmo tempo) e grava a nota + o status da sugestão atomicamente — mesma
                // lógica de functions/email_action_linker.py:apply_suggestion.
                await runTransaction(db, async (transaction) => {
                    const suggestionSnap = await transaction.get(suggestionRef);
                    if (!suggestionSnap.exists() || suggestionSnap.data().status !== 'pending') {
                        throw new Error('Sugestão já foi decidida em outro lugar.');
                    }
                    const taskSnap = await transaction.get(taskRef);
                    if (!taskSnap.exists()) {
                        throw new Error('Ação vinculada não encontrada.');
                    }
                    const taskUpdates: Record<string, any> = {
                        acompanhamento: arrayUnion({ data: nowIso, nota }),
                        data_atualizacao: nowIso
                    };
                    if (reactivate) {
                        taskUpdates.status = 'em andamento';
                        taskUpdates.data_conclusao = null;
                    }
                    transaction.update(taskRef, taskUpdates);
                    transaction.update(suggestionRef, {
                        status: reactivate ? 'applied_reactivated' : 'applied',
                        applied_at: nowIso,
                        decided_at: nowIso
                    });
                });
            }
        } catch (err) {
            console.error('[EmailLinkSuggestions] Falha ao decidir sugestão:', err);
        } finally {
            setBusyId(null);
        }
    };

    return (
        <DashboardCard title={`Sinais para vincular a ações (${sorted.length})`} isDark={isDark}>
            <div className="flex flex-col gap-3">
                {sorted.slice(0, 6).map(suggestion => (
                    <div key={suggestion.id} className={`rounded-xl border p-3 ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-100 bg-slate-50'}`}>
                        <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                                <p className="text-xs font-bold truncate">
                                    {_CANAL_ICONS[suggestion.canal || 'email'] || '🔔'} {suggestion.titulo_sinal || '(sem título)'}
                                </p>
                                <p className={`text-[10px] truncate ${isDark ? 'text-white/50' : 'text-slate-500'}`}>{suggestion.origem_sinal}</p>
                            </div>
                            {suggestion.status === 'expired' && (
                                <span className="shrink-0 text-[8px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-600">
                                    Expirado no Telegram
                                </span>
                            )}
                        </div>
                        {suggestion.task_titulo && (
                            <p className={`mt-1 text-[10px] font-bold ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}>
                                → {suggestion.task_titulo}{suggestion.task_status ? ` (${suggestion.task_status})` : ''}
                            </p>
                        )}
                        {suggestion.resumo && (
                            <p className={`mt-1 text-[10px] leading-snug ${isDark ? 'text-white/60' : 'text-slate-600'}`}>{suggestion.resumo}</p>
                        )}
                        <div className="mt-2 flex flex-wrap gap-2">
                            <button
                                type="button"
                                disabled={busyId === suggestion.id}
                                onClick={() => decide(suggestion, 'ok')}
                                className="flex-1 rounded-lg bg-[#9333ea] py-1.5 text-[10px] font-bold uppercase tracking-wider text-white transition hover:bg-[#7800ce] disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                Registrar
                            </button>
                            {suggestion.reativar_sugerido && (
                                <button
                                    type="button"
                                    disabled={busyId === suggestion.id}
                                    onClick={() => decide(suggestion, 'on')}
                                    className="flex-1 rounded-lg border border-[#9333ea] py-1.5 text-[10px] font-bold uppercase tracking-wider text-[#9333ea] transition hover:bg-[#9333ea]/10 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    Registrar + Reativar
                                </button>
                            )}
                            <button
                                type="button"
                                disabled={busyId === suggestion.id}
                                onClick={() => decide(suggestion, 'no')}
                                className={`rounded-lg px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition disabled:cursor-not-allowed disabled:opacity-50 ${isDark ? 'text-white/40 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-200'}`}
                            >
                                Ignorar
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </DashboardCard>
    );
};

// --- PAINEL DE LEITURA DO DIÁRIO PESSOAL (functions/personal_diary.py) ---
// Só leitura — o ajuste ao texto acontece via Telegram (botão "✍️ Ajustar",
// ver hermes_core_logic.py) para reaproveitar o mesmo fluxo de revisão que
// alimenta o consolidador semanal de personalidade.
interface PersonalDiaryEntry {
    id: string;
    data?: string;
    texto?: string;
    editado?: boolean;
    sem_material?: boolean;
}

const PersonalDiaryPanel: React.FC<{ isDark?: boolean }> = ({ isDark = false }) => {
    const [entries, setEntries] = useState<PersonalDiaryEntry[]>([]);
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        const q = query(collection(db, 'diario_pessoal'), orderBy('data', 'desc'), limit(7));
        return onSnapshot(q, snap => {
            setEntries(snap.docs.map(d => ({ id: d.id, ...(d.data() as any) })));
        });
    }, []);

    const withText = entries.filter(e => !!e.texto);
    if (withText.length === 0) return null;

    const [latest, ...older] = withText;

    return (
        <DashboardCard title="Diário Pessoal" isDark={isDark}>
            <div className="flex flex-col gap-3">
                <div>
                    <div className="flex items-center justify-between mb-1">
                        <p className={`text-[10px] font-black uppercase tracking-wider ${isDark ? 'text-white/40' : 'text-slate-400'}`}>{latest.data}</p>
                        {latest.editado && (
                            <span className="text-[8px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-500">Ajustado</span>
                        )}
                    </div>
                    <p className={`text-xs leading-relaxed whitespace-pre-line ${isDark ? 'text-white/80' : 'text-slate-700'}`}>{latest.texto}</p>
                </div>
                {older.length > 0 && (
                    <button
                        type="button"
                        onClick={() => setExpanded(v => !v)}
                        className={`self-start text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}
                    >
                        {expanded ? 'Ocultar dias anteriores' : `Ver ${older.length} dia(s) anterior(es)`}
                    </button>
                )}
                {expanded && older.map(e => (
                    <div key={e.id} className={`pt-3 border-t ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                        <p className={`text-[10px] font-black uppercase tracking-wider mb-1 ${isDark ? 'text-white/40' : 'text-slate-400'}`}>{e.data}</p>
                        <p className={`text-xs leading-relaxed whitespace-pre-line ${isDark ? 'text-white/70' : 'text-slate-600'}`}>{e.texto}</p>
                    </div>
                ))}
                <p className={`text-[9px] ${isDark ? 'text-white/30' : 'text-slate-400'}`}>
                    Gerado automaticamente às 21h30. Peça um ajuste no Telegram tocando "✍️ Ajustar".
                </p>
            </div>
        </DashboardCard>
    );
};

// --- MAIN COMPONENT ---
const DashboardView: React.FC<DashboardViewProps> = ({
    tarefas = [],
    isDark = false,
    financeTransactions = [],
    financeSettings = {} as FinanceSettings,
    fixedBills = [],
    incomeEntries = [],
    healthWeights = [],
    healthSettings = {} as HealthSettings,
    exerciseLogs = [] as ExerciseLog[],
    onSaveExerciseLog,
    onAddHealthWeight,
    currentMonth = new Date().getMonth(),
    currentYear = new Date().getFullYear(),
    onNavigate
}) => {
    const [isFinanceVisible, setIsFinanceVisible] = useState(false);

    // --- ACTIONS LOGIC ---
    const inProgressActions = useMemo(() => tarefas.filter(t => t.status !== 'concluído' && t.status !== 'excluído' as any), [tarefas]);

    const actionsByDay = useMemo(() => {
        const result = [];
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        for (let i = 0; i < 7; i++) {
            const d = new Date(today);
            d.setDate(today.getDate() + i);
            const dStr = d.toISOString().split('T')[0];
            const count = inProgressActions.filter(t => t.data_limite === dStr).length;

            result.push({
                dateStr: dStr,
                dayNum: d.getDate(),
                monthName: ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'][d.getMonth()],
                count,
                isToday: i === 0
            });
        }
        return result;
    }, [inProgressActions]);

    // --- FINANCE LOGIC ---
    const periodKey = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
    const currentBudget = financeSettings?.monthlyBudgets?.[periodKey] || financeSettings?.monthlyBudget || 0;

    const currentMonthTransactions = useMemo(() => financeTransactions.filter(t => {
        const dateParts = getFinanceDateParts(t.date);
        return dateParts?.month === currentMonth && dateParts.year === currentYear && t.status !== 'deleted';
    }), [financeTransactions, currentMonth, currentYear]);

    const currentMonthTotalSpent = useMemo(() => currentMonthTransactions.reduce((acc, curr) => acc + curr.amount, 0), [currentMonthTransactions]);
    const availableBalance = currentBudget - currentMonthTotalSpent;

    const financeChartData = useMemo(() => {
        const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
        const monthName = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'][currentMonth];
        const amountByDay = new Map<number, number>();

        currentMonthTransactions.forEach(transaction => {
            const dateParts = getFinanceDateParts(transaction.date);
            if (!dateParts) return;

            amountByDay.set(dateParts.day, (amountByDay.get(dateParts.day) || 0) + transaction.amount);
        });

        return Array.from({ length: daysInMonth }, (_, index) => {
            const day = index + 1;
            return {
                day,
                amount: amountByDay.get(day) || 0,
                monthName
            };
        });
    }, [currentMonthTransactions, currentMonth, currentYear]);

    const maxFinanceChartAmount = useMemo(
        () => Math.max(...financeChartData.map(d => d.amount), 1),
        [financeChartData]
    );

    const currentMonthIncome = useMemo(() => incomeEntries
        .filter(e => e.month === currentMonth && e.year === currentYear && e.isReceived && e.status !== 'deleted')
        .reduce((acc, curr) => acc + curr.amount, 0), [incomeEntries, currentMonth, currentYear]);

    const currentTotalBills = useMemo(() => fixedBills
        .filter(b => b.month === currentMonth && b.year === currentYear)
        .reduce((acc, curr) => acc + curr.amount, 0), [fixedBills, currentMonth, currentYear]);

    // --- HEALTH LOGIC ---
    const sortedWeights = useMemo(() => [...healthWeights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()), [healthWeights]);
    const currentWeight = sortedWeights[0]?.weight || 0;
    const previousWeight = sortedWeights[1]?.weight || currentWeight;
    const weightDelta = previousWeight > 0 && currentWeight > 0 ? currentWeight - previousWeight : 0;

    const targetWeight = healthSettings?.targetWeight || 0;
    const targetDelta = (targetWeight > 0 && currentWeight > 0) ? currentWeight - targetWeight : null;

    const todayKey = useMemo(() => formatDateLocalISO(new Date()), []);

    const todayHealthLog = useMemo(() => {
        return exerciseLogs.find(l => l.id === todayKey) || null;
    }, [exerciseLogs, todayKey]);

    const painLogs = useMemo(() => {
        return [...exerciseLogs]
            .filter(log => log.pain?.evening !== undefined)
            .sort((a, b) => a.id.localeCompare(b.id))
            .slice(-7);
    }, [exerciseLogs]);

    // --- WALK GOAL LOGIC ---
    const todayWalkKm = useMemo(() => sumWalkBlocksKm(todayHealthLog), [todayHealthLog]);
    const walkingMinimumKm = healthSettings?.walkingMinimumKm ?? 3;
    const walkingIdealKm = healthSettings?.walkingIdealKm ?? 8;
    const walkMetMinimum = todayWalkKm >= walkingMinimumKm;
    const walkMetIdeal = todayWalkKm >= walkingIdealKm;

    const [isWalkModalOpen, setIsWalkModalOpen] = useState(false);
    const [walkKmInput, setWalkKmInput] = useState('');
    const [isSavingWalk, setIsSavingWalk] = useState(false);

    const handleQuickRegisterWalk = async () => {
        const distance = parseFloat(walkKmInput.replace(',', '.'));
        if (!onSaveExerciseLog || isNaN(distance) || distance <= 0 || distance > 50) return;
        setIsSavingWalk(true);
        try {
            const block: WalkBlock = {
                id: `walk_${Date.now()}`,
                time: new Date().toTimeString().slice(0, 5),
                distance,
                source: 'web',
            };
            await onSaveExerciseLog(todayKey, { walkBlocks: arrayUnion(block) } as unknown as Partial<ExerciseLog>);
            setWalkKmInput('');
            setIsWalkModalOpen(false);
        } finally {
            setIsSavingWalk(false);
        }
    };

    // --- REGISTRO RAPIDO DE PESO ---
    const [isWeightModalOpen, setIsWeightModalOpen] = useState(false);
    const [weightKgInput, setWeightKgInput] = useState('');
    const [isSavingWeight, setIsSavingWeight] = useState(false);

    const handleQuickRegisterWeight = async () => {
        const weight = parseFloat(weightKgInput.replace(',', '.'));
        if (!onAddHealthWeight || isNaN(weight) || weight <= 0 || weight > 400) return;
        setIsSavingWeight(true);
        try {
            await onAddHealthWeight(weight, todayKey);
            setWeightKgInput('');
            setIsWeightModalOpen(false);
        } finally {
            setIsSavingWeight(false);
        }
    };
    // --- PROGRESS BAR RENDER HELPER ---
    // Nivelamento suave de cor da caminhada: abaixo do minimo fica em cinza
    // (nao entrou na zona de pontuacao ainda); do minimo ao ideal, a cor
    // desliza continuamente de vermelho -> laranja -> amarelo -> verde (em
    // vez de saltar entre 3 cores fixas); do ideal em diante e "lucro" e
    // fica no verde cheio.
    const walkGradientColor = (km: number, minKm: number, idealKm: number) => {
        if (minKm <= 0 || km < minKm) return isDark ? '#475569' : '#94a3b8';
        if (km >= idealKm) return '#10b981';
        const t = idealKm > minKm ? (km - minKm) / (idealKm - minKm) : 1;
        const hue = t * 142; // 0 = vermelho, ~142 = verde-esmeralda
        return `hsl(${hue}, 82%, 46%)`;
    };

    const renderProgressBar = (value: number, max: number) => {
        const percent = max > 0 ? Math.min((value / max) * 100, 100) : 0;
        return (
            <div className={`h-[6px] w-full rounded-full overflow-hidden ${isDark ? 'bg-[#2a313d]' : 'bg-[#f3f4f6]'}`}>
                <div style={{ width: `${percent}%` }} className="h-full bg-[#9333ea] rounded-full transition-all duration-500" />
            </div>
        );
    };

    return (
        <div
            style={{ fontFamily: 'Inter, sans-serif' }}
            className={`animate-in fade-in duration-700 flex flex-col gap-5 w-full max-w-[1600px] mx-auto p-4 md:p-6 overflow-hidden ${
                isDark ? 'text-white' : 'text-[#151c27]'
            }`}
        >

            <EmailLinkSuggestionsPanel isDark={isDark} />
            <PersonalDiaryPanel isDark={isDark} />

            <div className="flex flex-col xl:flex-row gap-6 w-full items-stretch min-h-0 xl:h-[calc(100vh-7rem)]">

                {/* 1. COLUNA ESQUERDA: Área de Trabalho (Flexível) */}
                <div className="flex-1 flex flex-col gap-6 xl:overflow-y-auto custom-scrollbar xl:max-h-[calc(100vh-7rem)] pr-1">

                    {/* CARD: Carga de Trabalho Semanal */}
                    <DashboardCard title="Carga Semanal de Trabalho" isDark={isDark} onRedirect={() => onNavigate('gallery')}>
                        <div className="flex flex-col gap-4">
                            <p className="text-[10px] font-bold uppercase tracking-[0.2em] font-mono text-slate-400">
                                // CARGA OPERACIONAL D+6
                            </p>

                            <div className="grid grid-cols-7 gap-2 md:gap-3 border-b border-[#f3f4f6] pb-2 dark:border-white/5">
                                {actionsByDay.map((day, i) => {
                                    const maxCount = Math.max(...actionsByDay.map(d => d.count), 1);
                                    const heightPercent = (day.count / maxCount) * 100;

                                    return (
                                        <div key={i} className="flex min-w-0 flex-col items-center group">
                                            <div className="flex h-40 w-full flex-col justify-end">
                                                <div className="flex h-32 w-full items-end">
                                                    <div
                                                        className="flex w-full flex-col items-center"
                                                        style={{ height: day.count > 0 ? `${Math.max(heightPercent, 8)}%` : '2px' }}
                                                    >
                                                        <span className={`mb-1 block text-center text-[11px] font-bold font-mono leading-none transition-colors ${
                                                            day.count > 0
                                                                ? (day.isToday ? 'text-[#7800ce] dark:text-[#ddb8ff]' : 'text-slate-600 dark:text-slate-300')
                                                                : 'text-slate-300 dark:text-slate-700'
                                                        }`}>
                                                            {String(day.count).padStart(2, '0')}
                                                        </span>
                                                        <div
                                                            className={`min-h-0 w-full flex-1 transition-all duration-300 rounded-lg ${
                                                                day.isToday
                                                                    ? 'bg-[#7800ce] shadow-[0_0_12px_rgba(120,0,206,0.3)]'
                                                                    : day.count > 0
                                                                        ? 'bg-[#9333ea]/20 hover:bg-[#9333ea]/40'
                                                                        : isDark ? 'bg-white/5' : 'bg-slate-100'
                                                            }`}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="mt-3 flex flex-col items-center gap-0.5">
                                                <span className={`text-[10px] font-bold font-mono ${
                                                    day.isToday ? 'text-[#7800ce] dark:text-[#ddb8ff]' : 'text-slate-400 dark:text-slate-500'
                                                }`}>
                                                    {String(day.dayNum).padStart(2, '0')}
                                                </span>
                                                <span className="text-[8px] font-semibold text-slate-400 uppercase tracking-widest font-mono">
                                                    {day.monthName}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </DashboardCard>
                    {/* CARD: Painel Financeiro */}
                    <DashboardCard
                        title="Resumo Financeiro"
                        isDark={isDark}
                        onRedirect={() => onNavigate('finance')}
                        headerAction={
                            <button
                                onClick={(e) => { e.stopPropagation(); setIsFinanceVisible(!isFinanceVisible); }}
                                className={`p-1.5 rounded-lg border transition-all ${
                                    isDark
                                        ? 'border-white/10 text-slate-400 hover:text-white hover:bg-white/5'
                                        : 'border-[#e5e7eb] text-slate-500 hover:text-[#9333ea] hover:bg-[#f5f3ff]'
                                }`}
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    {isFinanceVisible ? (
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                    ) : (
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                                    )}
                                </svg>
                            </button>
                        }
                    >
                        <div className="flex flex-col gap-5">
                            <div className="flex items-center justify-between">
                                <div className="flex flex-col gap-1">
                                    <span className="text-[10px] font-bold uppercase tracking-[0.2em] font-mono text-slate-400">
                                        Consumo Mensal
                                    </span>
                                    <div className="text-2xl font-bold font-mono text-[#10b981]">
                                        {isFinanceVisible ? (
                                            <>
                                                <span className="text-xs opacity-75 font-sans mr-0.5">R$</span>
                                                {currentMonthTotalSpent.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                            </>
                                        ) : (
                                            <HiddenMoney compact />
                                        )}
                                    </div>
                                </div>
                                <div className="text-right flex flex-col gap-1">
                                    <span className="text-[10px] font-bold uppercase tracking-[0.2em] font-mono text-slate-400">
                                        Saldo Disponível
                                    </span>
                                    <div className={`text-base font-bold font-mono ${
                                        availableBalance < 0 ? 'text-[#ba1a1a]' : 'text-slate-600 dark:text-slate-300'
                                    }`}>
                                        {isFinanceVisible ? (
                                            <>
                                                <span className="text-xs opacity-75 mr-0.5">R$</span>
                                                {availableBalance.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                            </>
                                        ) : (
                                            '••••'
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Progresso de Orçamento */}
                            <div className="flex flex-col gap-1.5">
                                <div className="flex justify-between text-[11px] text-slate-500">
                                    <span>Limite Planejado</span>
                                    <span className="font-mono">
                                        {isFinanceVisible ? `R$ ${currentBudget.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '••••'}
                                    </span>
                                </div>
                                {renderProgressBar(currentMonthTotalSpent, currentBudget)}
                            </div>

                            <hr className={isDark ? 'border-white/10' : 'border-[#e5e7eb]'} />

                            {/* Gráfico Financeiro */}
                            <div className="flex flex-col gap-2">
                                <span className="text-[10px] font-bold uppercase tracking-[0.2em] font-mono text-slate-400">
                                    // CONSUMO DIÁRIO DO PERÍODO
                                </span>
                                <div className="h-20 flex items-end gap-1 px-1 relative">
                                    {isFinanceVisible ? (
                                        financeChartData.some(item => item.amount > 0) ? (
                                            financeChartData.map((item, i) => {
                                                const heightPercent = (item.amount / maxFinanceChartAmount) * 100;
                                                const hasAmount = item.amount > 0;
                                                return (
                                                    <div key={i} className="flex-1 min-w-[8px] flex flex-col justify-end h-full group">
                                                        <div
                                                            style={{ height: hasAmount ? `${Math.max(heightPercent, 6)}%` : '2px' }}
                                                            className={`w-full transition-all duration-300 rounded-sm ${
                                                                hasAmount
                                                                    ? 'bg-[#10b981]/30 group-hover:bg-[#10b981]'
                                                                    : isDark ? 'bg-white/10' : 'bg-slate-200'
                                                            }`}
                                                            title={`${String(item.day).padStart(2, '0')} ${item.monthName}: R$ ${item.amount.toFixed(2)}`}
                                                        />
                                                    </div>
                                                );
                                            })
                                        ) : (
                                            <div className="flex-1 h-full flex items-center justify-center border border-dashed border-[#e5e7eb] dark:border-white/10 rounded-xl">
                                                <span className="text-[10px] uppercase font-mono italic text-slate-400">Sem registros neste mês</span>
                                            </div>
                                        )
                                    ) : (
                                        <div className="flex-1 h-full flex items-center justify-center border border-dashed border-[#e5e7eb] dark:border-white/10 rounded-xl bg-slate-500/5 backdrop-blur-[1px]">
                                            <span className="text-[10px] uppercase tracking-wider font-mono font-bold text-slate-400">DADOS OMITIDOS DE FORMA SEGURA</span>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Resumo Caixa de Entradas/Saídas */}
                            <div className="grid grid-cols-2 gap-4 text-xs font-medium">
                                <div className={`p-3 rounded-xl border ${isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'}`}>
                                    <span className="text-[9px] uppercase tracking-wider text-slate-400 font-mono">Receitas do Mês</span>
                                    <p className="text-sm font-bold text-[#10b981] mt-1 font-mono">
                                        {isFinanceVisible ? `R$ ${currentMonthIncome.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '••••'}
                                    </p>
                                </div>
                                <div className={`p-3 rounded-xl border ${isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'}`}>
                                    <span className="text-[9px] uppercase tracking-wider text-slate-400 font-mono">Contas Fixas</span>
                                    <p className="text-sm font-bold text-slate-600 dark:text-slate-300 mt-1 font-mono">
                                        {isFinanceVisible ? `R$ ${currentTotalBills.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` : '••••'}
                                    </p>
                                </div>
                            </div>
                        </div>
                    </DashboardCard>

                </div>

                {/* 2. COLUNA DIREITA: Saúde & Telemetria (320px Fixo) */}
                <div className="w-full xl:w-[320px] shrink-0 flex flex-col gap-6 xl:overflow-y-auto custom-scrollbar xl:max-h-[calc(100vh-7rem)] pr-1">
                    {/* CARD: Saúde & Telemetria */}
                    <DashboardCard title="Saúde & Telemetria" isDark={isDark} onRedirect={() => onNavigate('saude')}>
                        <div className="flex flex-col gap-4">
                            <div className="flex items-center justify-between shrink-0">
                                <span className="text-[9px] uppercase tracking-wider text-slate-400 font-mono">// BIOMETRIA & SINAL CLÍNICO</span>
                                <span className="text-[9px] font-bold text-[#9333ea] dark:text-[#ddb8ff] uppercase tracking-wider font-mono">PAINEL INTEGRADO →</span>
                            </div>

                            {/* 1. SEÇÃO PESO E META */}
                            <div className={`p-3.5 rounded-xl border flex flex-col gap-2.5 ${
                                isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'
                            }`}>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <span className="text-[8px] font-bold uppercase tracking-wider text-slate-400 font-mono">Massa Corporal</span>
                                        <div className="text-lg font-bold font-mono mt-0.5 flex items-baseline gap-1">
                                            {currentWeight > 0 ? currentWeight.toFixed(1) : '--'}
                                            <span className="text-[10px] text-slate-400 font-sans">KG</span>
                                        </div>
                                    </div>

                                    <div className="text-right">
                                        <span className="text-[8px] font-bold uppercase tracking-wider text-slate-400 font-mono">Variação</span>
                                        <div className={`text-xs font-bold font-mono mt-0.5 ${
                                            weightDelta > 0 ? 'text-amber-500' : weightDelta < 0 ? 'text-emerald-500' : 'text-slate-400'
                                        }`}>
                                            {currentWeight > 0 && previousWeight > 0 && currentWeight !== previousWeight
                                                ? `${weightDelta > 0 ? '+' : ''}${weightDelta.toFixed(1)} kg`
                                                : 'Estável'}
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center justify-end">
                                    <button
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); setIsWeightModalOpen(true); }}
                                        className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-wider transition-all ${
                                            isDark
                                                ? 'bg-white/5 text-[#ddb8ff] hover:bg-white/10'
                                                : 'bg-[#f5f3ff] text-[#7800ce] hover:bg-[#ece5ff]'
                                        }`}
                                    >
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v14M5 12h14" /></svg>
                                        Registrar
                                    </button>
                                </div>

                                {targetWeight > 0 && (
                                    <div className="pt-2 border-t border-slate-200/40 dark:border-white/5 flex flex-col gap-1.5">
                                        <div className="flex items-center justify-between text-[9px] font-mono">
                                            <span className="text-slate-400 font-bold uppercase">Meta: {targetWeight.toFixed(1)} kg</span>
                                            <span className="font-bold text-[#9333ea] dark:text-[#ddb8ff]">
                                                {targetDelta !== null ? (
                                                    targetDelta > 0 ? `+${targetDelta.toFixed(1)} kg até a meta` : targetDelta < 0 ? `${Math.abs(targetDelta).toFixed(1)} kg abaixo` : 'Na meta!'
                                                ) : ''}
                                            </span>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* 2. SEÇÃO CAMINHADA NA ESTEIRA */}
                            <div className={`p-3.5 rounded-xl border flex flex-col gap-2.5 ${
                                isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'
                            }`}>
                                <div className="flex items-center justify-between">
                                    <span className="text-[8px] font-bold uppercase tracking-wider text-slate-400 font-mono">Caminhada (Hoje)</span>
                                    <span
                                        className="px-1.5 py-0.5 text-[8px] font-black uppercase rounded"
                                        style={{
                                            color: walkGradientColor(todayWalkKm, walkingMinimumKm, walkingIdealKm),
                                            backgroundColor: `${walkGradientColor(todayWalkKm, walkingMinimumKm, walkingIdealKm)}33`,
                                        }}
                                    >
                                        {walkMetIdeal ? 'Meta ideal' : walkMetMinimum ? 'Mínimo ok' : 'Abaixo do mínimo'}
                                    </span>
                                </div>

                                <div className="flex items-center justify-between">
                                    <div className="text-lg font-bold font-mono flex items-baseline gap-1">
                                        {todayWalkKm.toFixed(1)}
                                        <span className="text-[10px] text-slate-400 font-sans">KM</span>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); setIsWalkModalOpen(true); }}
                                        className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-wider transition-all ${
                                            isDark
                                                ? 'bg-white/5 text-[#ddb8ff] hover:bg-white/10'
                                                : 'bg-[#f5f3ff] text-[#7800ce] hover:bg-[#ece5ff]'
                                        }`}
                                    >
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v14M5 12h14" /></svg>
                                        Registrar
                                    </button>
                                </div>

                                <div className="relative h-[6px] w-full rounded-full overflow-hidden mt-0.5">
                                    <div className={`absolute inset-0 rounded-full ${isDark ? 'bg-[#2a313d]' : 'bg-[#f3f4f6]'}`} />
                                    <div
                                        style={{
                                            width: `${Math.min((todayWalkKm / Math.max(walkingIdealKm, walkingMinimumKm, todayWalkKm, 1)) * 100, 100)}%`,
                                            backgroundColor: walkGradientColor(todayWalkKm, walkingMinimumKm, walkingIdealKm),
                                        }}
                                        className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
                                    />
                                </div>
                                <div className="flex items-center justify-between text-[8px] font-mono text-slate-400 font-bold uppercase">
                                    <span>Mín. {walkingMinimumKm} km</span>
                                    <span>Ideal {walkingIdealKm} km</span>
                                </div>
                            </div>

                            {/* 3. SEÇÃO DOR LOMBAR / CHECK-IN TELEGRAM */}
                            <div className={`p-3.5 rounded-xl border flex flex-col gap-2.5 ${
                                isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'
                            }`}>
                                <div className="flex items-center justify-between">
                                    <span className="text-[8px] font-bold uppercase tracking-wider text-slate-400 font-mono">Dor Lombar (Hoje)</span>
                                    {todayHealthLog?.pain?.crisis ? (
                                        <span className="px-1.5 py-0.5 text-[8px] font-black uppercase rounded bg-rose-500/20 text-rose-500 animate-pulse">CRISE ATIVA</span>
                                    ) : todayHealthLog?.pain?.sciatica ? (
                                        <span className="px-1.5 py-0.5 text-[8px] font-black uppercase rounded bg-amber-500/20 text-amber-500">CIÁTICA</span>
                                    ) : (
                                        <span className="px-1.5 py-0.5 text-[8px] font-black uppercase rounded bg-emerald-500/20 text-emerald-500">ESTÁVEL</span>
                                    )}
                                </div>

                                <div className="flex items-center justify-between mt-0.5">
                                    <span className="text-[8px] text-slate-400 font-mono uppercase">Registro Noturno (Telegram)</span>
                                    <span className="text-xs font-bold font-mono text-slate-700 dark:text-slate-200">
                                        {todayHealthLog?.pain?.evening !== undefined ? `${todayHealthLog.pain.evening}/10` : '--'}
                                    </span>
                                </div>

                                {todayHealthLog?.pain?.notes && (
                                    <p className="text-[10px] italic text-slate-400 border-t border-slate-200/40 dark:border-white/5 pt-1.5 truncate">
                                        "{todayHealthLog.pain.notes}"
                                    </p>
                                )}
                            </div>

                            {/* 4. MINI GRÁFICO / TENDÊNCIA DE DOR NOTURNA (7 REGISTROS RECENTES) */}
                            <div className={`p-3.5 rounded-xl border flex flex-col gap-2 ${
                                isDark ? 'border-white/5 bg-white/[0.01]' : 'border-[#f3f4f6] bg-[#f9fafb]'
                            }`}>
                                <span className="text-[8px] font-bold uppercase tracking-wider text-slate-400 font-mono">Tendência Recente de Dor Noturna (0-10)</span>
                                
                                {painLogs.length >= 2 ? (
                                    <div className="h-20 w-full flex items-end justify-between gap-1.5 pt-2">
                                        {painLogs.map(log => {
                                            const val = log.pain?.evening ?? 0;
                                            const heightPct = Math.max(val * 10, 8);
                                            const isHigh = val >= 6;
                                            const isMid = val >= 3;
                                            const dayLabel = log.id.split('-')[2] || log.id;
                                            return (
                                                <div key={log.id} className="flex-1 h-full flex flex-col justify-end items-center group/bar relative">
                                                    <div className="w-full flex-1 flex items-end justify-center">
                                                        <div 
                                                            className={`w-full rounded-t transition-all duration-300 ${
                                                                log.pain?.crisis ? 'bg-rose-600' : isHigh ? 'bg-rose-500' : isMid ? 'bg-amber-500' : 'bg-emerald-500'
                                                            }`}
                                                            style={{ height: `${heightPct}%` }}
                                                        />
                                                    </div>
                                                    <span className="text-[8px] font-mono text-slate-400 font-semibold mt-1 shrink-0">{dayLabel}</span>
                                                    <div className="absolute -top-8 hidden group-hover/bar:flex flex-col items-center bg-slate-900 text-white text-[9px] px-2 py-1 rounded shadow-xl z-20 whitespace-nowrap font-mono border border-slate-700 pointer-events-none">
                                                        <span className="font-bold text-amber-400">{log.id}</span>
                                                        <span>Dor Noturna: {val}/10</span>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                ) : (
                                    <p className="text-[10px] text-slate-400 font-mono italic text-center py-2">
                                        Aguardando histórico de check-ins.
                                    </p>
                                )}
                            </div>

                        </div>
                    </DashboardCard>

                </div>

            </div>

            {isWalkModalOpen && (
                <div
                    className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200"
                    onClick={() => setIsWalkModalOpen(false)}
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        className={`w-full max-w-xs rounded-2xl p-6 shadow-2xl animate-in zoom-in-95 ${
                            isDark ? 'bg-[#151c27] border border-[#2a313d] text-white' : 'bg-white text-[#151c27]'
                        }`}
                    >
                        <h3 className="text-sm font-bold uppercase tracking-wider">Registrar caminhada</h3>
                        <p className={`mt-1 text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                            Distância do bloco em km. Soma automaticamente ao total de hoje ({todayWalkKm.toFixed(1)} km).
                        </p>
                        <input
                            type="text"
                            inputMode="decimal"
                            autoFocus
                            value={walkKmInput}
                            onChange={(e) => setWalkKmInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') handleQuickRegisterWalk(); }}
                            placeholder="Ex: 2.5"
                            className={`mt-4 w-full rounded-xl border px-4 py-3 text-center text-2xl font-bold font-mono outline-none transition focus:ring-2 focus:ring-[#9333ea] ${
                                isDark ? 'bg-white/5 border-[#2a313d] text-white' : 'bg-slate-50 border-slate-200 text-slate-800'
                            }`}
                        />
                        <div className="mt-2 flex flex-wrap gap-2">
                            {[1, 1.5, 2, 2.5, 3].map(preset => (
                                <button
                                    key={preset}
                                    type="button"
                                    onClick={() => setWalkKmInput(String(preset))}
                                    className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                                        isDark
                                            ? 'border-[#2a313d] text-slate-300 hover:border-[#861fdd]/40 hover:text-[#ddb8ff]'
                                            : 'border-slate-200 text-slate-500 hover:border-[#861fdd]/40 hover:text-[#7800ce]'
                                    }`}
                                >
                                    {preset.toString().replace('.', ',')} km
                                </button>
                            ))}
                        </div>
                        <div className="mt-5 flex gap-3">
                            <button
                                type="button"
                                onClick={() => { setIsWalkModalOpen(false); setWalkKmInput(''); }}
                                className={`flex-1 rounded-xl py-2.5 text-xs font-bold uppercase tracking-wider transition ${
                                    isDark ? 'text-slate-400 hover:bg-white/5' : 'text-slate-400 hover:bg-slate-50'
                                }`}
                            >
                                Cancelar
                            </button>
                            <button
                                type="button"
                                disabled={isSavingWalk || !walkKmInput.trim()}
                                onClick={handleQuickRegisterWalk}
                                className="flex-1 rounded-xl bg-[#9333ea] py-2.5 text-xs font-bold uppercase tracking-wider text-white shadow-lg transition hover:bg-[#7800ce] disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                {isSavingWalk ? 'Salvando…' : 'Registrar'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {isWeightModalOpen && (
                <div
                    className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200"
                    onClick={() => setIsWeightModalOpen(false)}
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        className={`w-full max-w-xs rounded-2xl p-6 shadow-2xl animate-in zoom-in-95 ${
                            isDark ? 'bg-[#151c27] border border-[#2a313d] text-white' : 'bg-white text-[#151c27]'
                        }`}
                    >
                        <h3 className="text-sm font-bold uppercase tracking-wider">Registrar peso</h3>
                        <p className={`mt-1 text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                            Peso atual em quilos{currentWeight > 0 ? ` (último registro: ${currentWeight.toFixed(1)} kg)` : ''}.
                        </p>
                        <input
                            type="text"
                            inputMode="decimal"
                            autoFocus
                            value={weightKgInput}
                            onChange={(e) => setWeightKgInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') handleQuickRegisterWeight(); }}
                            placeholder="Ex: 94.8"
                            className={`mt-4 w-full rounded-xl border px-4 py-3 text-center text-2xl font-bold font-mono outline-none transition focus:ring-2 focus:ring-[#9333ea] ${
                                isDark ? 'bg-white/5 border-[#2a313d] text-white' : 'bg-slate-50 border-slate-200 text-slate-800'
                            }`}
                        />
                        <div className="mt-5 flex gap-3">
                            <button
                                type="button"
                                onClick={() => { setIsWeightModalOpen(false); setWeightKgInput(''); }}
                                className={`flex-1 rounded-xl py-2.5 text-xs font-bold uppercase tracking-wider transition ${
                                    isDark ? 'text-slate-400 hover:bg-white/5' : 'text-slate-400 hover:bg-slate-50'
                                }`}
                            >
                                Cancelar
                            </button>
                            <button
                                type="button"
                                disabled={isSavingWeight || !weightKgInput.trim()}
                                onClick={handleQuickRegisterWeight}
                                className="flex-1 rounded-xl bg-[#9333ea] py-2.5 text-xs font-bold uppercase tracking-wider text-white shadow-lg transition hover:bg-[#7800ce] disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                {isSavingWeight ? 'Salvando…' : 'Registrar'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default DashboardView;
