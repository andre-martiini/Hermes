import React, { useEffect, useMemo, useState } from 'react';
import { arrayUnion, collection, doc, getDoc, onSnapshot, query, runTransaction, updateDoc, where } from 'firebase/firestore';
import { db } from './firebase';
import {
    Tarefa, ActionPlanItem, FinanceTransaction, FinanceSettings, FixedBill, IncomeEntry,
    HealthWeight, HealthSettings, ExerciseLog, WalkBlock,
    formatDateLocalISO, sumWalkBlocksKm,
    ResumoMatinal, ResumoAcao, EtapaExecutor, SubtarefaEstado, BriefingDia
} from './types';
import { buildDiaryEmailNote, buildDiaryGenericNote, buildDiaryWhatsappNote, DiaryWhatsappActionItem } from './src/utils/diaryEntries';
import { addDays } from './src/utils/healthAnalytics';
import {
    comExecutorNoPlano, contarParaAgente, contarSubtarefas, eDoAgente, estaFeita, estadoDaSubtarefa,
    subtarefaCorrente, textoDaSubtarefa,
} from './src/utils/subtarefas';
import { classificarAcoesDoDia } from './src/utils/acoesDoDia';
import {
    agentePreparaHoje, alternarItemDecidir, diasEntre, focoPorAcao, preparoDosProximosDias, prepararDecidir,
    type LinhaAgentePrepara, type LinhaDecidir, type OrigemViva,
} from './src/utils/briefingDia';
import {
    AgentePreparaHoje, AvisosDoAgente, CabecalhoDoDia, LinkDiscreto, PrazosFinais, type PrazoFinal,
} from './src/components/painel/FaixasDoPainel';
import AgendaBloco from './src/components/painel/AgendaBloco';
import DecidirBloco from './src/components/painel/DecidirBloco';
import ElevacoesRodape, { type SugestaoDeElevacao } from './src/components/painel/ElevacoesRodape';
import CaminhadaCard, { type DiaDeCaminhada } from './src/components/painel/CaminhadaCard';
import { useMinutosAgora } from './src/components/painel/useRelogio';
import { eventosDoDia, type EventoDaAgenda } from './src/utils/agendaProximidade';
import { subtituloFinanceiro, subtituloSaude } from './src/utils/linksDoPainel';
import EtiquetaExecutor from './src/components/painel/EtiquetaExecutor';
import MenuExecutor from './src/components/painel/MenuExecutor';
import { isStandbyStatus } from './src/utils/helpers';

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
    onNavigate: (view: 'gallery' | 'finance' | 'saude' | 'diario') => void;
    onOpenTask?: (taskId: string) => void;
    onAskCopiloto?: (prompt: string) => void;
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

// --- FILA WEB DE SUGESTÕES DE VÍNCULO SINAL↔AÇÃO (functions/email_action_linker.py) ---
// Complementa a confirmação via Telegram: mostra sugestões pending/expired de
// qualquer canal (e-mail, SIPAC, Calendar, WhatsApp, ...) para decidir pelo
// navegador o que não foi respondido no Telegram a tempo.
const _CANAL_ICONS: Record<string, string> = { email: '📧', whatsapp: '📱', sipac: '📋', calendar: '📅', pagina: '🌐' };
const _CANAL_LABELS: Record<string, string> = {
    email: 'E-mail', whatsapp: 'Conversa de WhatsApp', sipac: 'Processo SIPAC', calendar: 'Reunião', pagina: 'Página monitorada'
};

interface ActionLinkMutations {
    novas_etapas?: string[];
    nova_data_limite?: string | null;
    lembrete_sugerido?: { data: string; texto: string } | null;
}

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
    // Elementos executivos extraídos pela triagem de WhatsApp (functions/whatsapp_ingest.py) —
    // itens de ação, decisões/pontos de auditoria e a mutação de ação proposta (plano/prazo/lembrete).
    itens_de_acao?: DiaryWhatsappActionItem[];
    decisoes?: string[];
    periodo_inicio?: string;
    periodo_fim?: string;
    mutacoes_propostas?: ActionLinkMutations;
    // Texto bruto por trás do resumo — corpo do e-mail limpo (email_action_linker.py)
    // ou transcript da janela de WhatsApp (whatsapp_ingest.py) — usado para dar ao
    // pedido de ação personalizada acesso a detalhes que o resumo pode ter condensado.
    texto_original?: string;
    numero_processo?: string;
}

// Mesma tradução usada no backend (functions/email_action_linker.py:_describe_mutations) —
// mantém o texto do que será/foi aplicado consistente entre o cartão do Telegram e a fila web.
const describeMutations = (mutacoes?: ActionLinkMutations): string[] => {
    if (!mutacoes) return [];
    const out: string[] = [];
    if (mutacoes.novas_etapas && mutacoes.novas_etapas.length > 0) out.push(`+${mutacoes.novas_etapas.length} etapa(s) no plano de ação`);
    if (mutacoes.nova_data_limite) out.push(`Prazo ajustado para ${mutacoes.nova_data_limite}`);
    if (mutacoes.lembrete_sugerido?.data) out.push(`Lembrete criado para ${mutacoes.lembrete_sugerido.data}`);
    return out;
};

// Mesma normalização usada no backend (functions/main.py:_normalize_task_reminders) — precisa
// ser reproduzida aqui porque a aplicação da mutação roda numa transação client-side.
const normalizeTaskReminders = (task: any): Array<{ id: string; reminder_at: string; reminder_sent: boolean; created_at: string; message: string }> => {
    const raw = Array.isArray(task?.reminders) ? task.reminders : [];
    const normalized = raw
        .filter((r: any) => r && r.reminder_at)
        .map((r: any, idx: number) => ({
            id: String(r.id || `legacy-${idx}`),
            reminder_at: String(r.reminder_at),
            reminder_sent: Boolean(r.reminder_sent),
            created_at: String(r.created_at || r.reminder_at),
            message: String(r.message || '')
        }));
    if (normalized.length === 0 && task?.reminder_at) {
        normalized.push({
            id: 'legacy-reminder',
            reminder_at: String(task.reminder_at),
            reminder_sent: Boolean(task.reminder_sent),
            created_at: String(task.data_atualizacao || task.data_criacao || task.reminder_at),
            message: ''
        });
    }
    return normalized;
};

// Formata o instante em que o sinal foi analisado (analyzed_at) de forma relativa
// ao dia atual — "Hoje/Ontem, HH:MM" para os casos mais comuns, senão "dd/mm, HH:MM".
const formatSuggestionTimestamp = (iso?: string): string => {
    if (!iso) return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';

    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    const time = date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

    if (date.toDateString() === now.toDateString()) return `Hoje, ${time}`;
    if (date.toDateString() === yesterday.toDateString()) return `Ontem, ${time}`;
    return `${date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}, ${time}`;
};

const EmailLinkSuggestionsPanel: React.FC<{
    isDark?: boolean;
    onOpenTask?: (taskId: string) => void;
    onAskCopiloto?: (prompt: string) => void;
}> = ({ isDark = false, onOpenTask, onAskCopiloto }) => {
    const [suggestions, setSuggestions] = useState<ActionLinkSuggestion[]>([]);
    const [busyId, setBusyId] = useState<string | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
    const [customInputs, setCustomInputs] = useState<Record<string, string>>({});
    const [searchQuery, setSearchQuery] = useState('');
    const [dismissingAll, setDismissingAll] = useState(false);

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

    const filtered = useMemo(() => {
        if (!searchQuery.trim()) return sorted;
        const q = searchQuery.toLowerCase().trim();
        return sorted.filter(s =>
            (s.titulo_sinal || '').toLowerCase().includes(q) ||
            (s.origem_sinal || '').toLowerCase().includes(q) ||
            (s.task_titulo || '').toLowerCase().includes(q) ||
            (s.resumo || '').toLowerCase().includes(q)
        );
    }, [sorted, searchQuery]);

    const dismissAllVisible = async () => {
        if (!filtered.length) return;
        setDismissingAll(true);
        try {
            const nowIso = new Date().toISOString();
            await Promise.all(
                filtered.map(s => updateDoc(doc(db, 'email_action_suggestions', s.id), {
                    status: 'dismissed',
                    decided_at: nowIso,
                }))
            );
        } catch (e) {
            console.error('Falha ao dispensar sinais:', e);
        } finally {
            setDismissingAll(false);
        }
    };

    if (sorted.length === 0) return null;

    const decide = async (suggestion: ActionLinkSuggestion, action: 'ok' | 'on' | 'no' | 'mut') => {
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
                // "mut" registra a nota E aplica as mutações propostas (novas etapas no plano,
                // ajuste de prazo, lembrete) — e também reativa se `reativar_sugerido` já indicava
                // isso, mesma regra do botão equivalente no Telegram (hermes_core_logic.py).
                const applyMutations = action === 'mut';
                const reactivate = action === 'on' || (applyMutations && !!suggestion.reativar_sugerido);
                const mutacoesAplicadas = applyMutations ? describeMutations(suggestion.mutacoes_propostas) : [];
                const nota = canal === 'email'
                    ? buildDiaryEmailNote(titulo, origem, `https://mail.google.com/mail/u/0/#all/${suggestion.google_message_id || suggestion.id}`, suggestion.resumo || '')
                    : canal === 'whatsapp'
                        ? buildDiaryWhatsappNote(titulo, origem, suggestion.resumo || '', suggestion.itens_de_acao || [], suggestion.decisoes || [], suggestion.periodo_inicio, suggestion.periodo_fim, mutacoesAplicadas)
                        : buildDiaryGenericNote(_CANAL_ICONS[canal] || '🔔', _CANAL_LABELS[canal] || 'Sinal', titulo, origem, suggestion.resumo || '', suggestion.link_externo);
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

                    if (applyMutations && suggestion.mutacoes_propostas) {
                        const taskData = taskSnap.data() as any;
                        const mutacoes = suggestion.mutacoes_propostas;
                        if (mutacoes.novas_etapas && mutacoes.novas_etapas.length > 0) {
                            const planoAtual = Array.isArray(taskData.plano_acao) ? taskData.plano_acao : [];
                            const novosItens = mutacoes.novas_etapas.map(texto => ({
                                id: Math.random().toString(36).substring(2, 9),
                                text: texto,
                                completed: false
                            }));
                            taskUpdates.plano_acao = [...planoAtual, ...novosItens];
                        }
                        if (mutacoes.nova_data_limite) {
                            taskUpdates.data_limite = mutacoes.nova_data_limite;
                        }
                        if (mutacoes.lembrete_sugerido?.data) {
                            const reminders = normalizeTaskReminders(taskData);
                            reminders.push({
                                id: Math.random().toString(36).substring(2, 12),
                                reminder_at: `${mutacoes.lembrete_sugerido.data}T09:00:00`,
                                reminder_sent: false,
                                created_at: nowIso,
                                message: mutacoes.lembrete_sugerido.texto || ''
                            });
                            const ordered = [...reminders].sort((a, b) => (a.reminder_at || '').localeCompare(b.reminder_at || ''));
                            const nextPending = ordered.find(r => !r.reminder_sent);
                            taskUpdates.reminders = ordered;
                            taskUpdates.reminder_at = nextPending ? nextPending.reminder_at : null;
                            taskUpdates.reminder_sent = nextPending ? Boolean(nextPending.reminder_sent) : true;
                        }
                    }

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

    const toggleExpanded = (id: string) => {
        setExpandedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    // Monta o contexto completo do sinal (canal, resumo, itens de ação, decisões, ação
    // vinculada) + o pedido livre do usuário, para o Copiloto Hermes executar via chat —
    // reaproveita as mesmas ferramentas (registrar_no_diario, editar_plano_acao, ...)
    // já disponíveis para o copiloto tradicional (functions/main.py:askCopilotoHermes).
    const buildCustomActionPrompt = (suggestion: ActionLinkSuggestion, instrucao: string): string => {
        const linhas: string[] = [];
        linhas.push(`[SINAL RECEBIDO — ${_CANAL_LABELS[suggestion.canal || 'email'] || 'Sinal'}]`);
        linhas.push(`Título: ${suggestion.titulo_sinal || '(sem título)'}`);
        if (suggestion.origem_sinal) linhas.push(`Origem: ${suggestion.origem_sinal}`);
        linhas.push(`Recebido: ${formatSuggestionTimestamp(suggestion.analyzed_at)}`);
        if (suggestion.numero_processo) linhas.push(`Número do processo SIPAC: ${suggestion.numero_processo}`);
        if (suggestion.resumo) linhas.push(`Resumo: ${suggestion.resumo}`);
        if (suggestion.itens_de_acao && suggestion.itens_de_acao.length > 0) {
            linhas.push('Itens de ação identificados:');
            suggestion.itens_de_acao.forEach(item => {
                linhas.push(`- ${item.descricao}${item.responsavel ? ` (${item.responsavel})` : ''}${item.prazo ? ` — prazo ${item.prazo}` : ''}`);
            });
        }
        if (suggestion.decisoes && suggestion.decisoes.length > 0) {
            linhas.push('Decisões registradas na conversa:');
            suggestion.decisoes.forEach(d => linhas.push(`- ${d}`));
        }
        linhas.push(
            suggestion.task_id
                ? `Ação vinculada: "${suggestion.task_titulo}" (ID: ${suggestion.task_id})`
                : 'Nenhuma ação vinculada a este sinal ainda.'
        );
        if (suggestion.texto_original) {
            linhas.push('');
            linhas.push('Mensagem original completa:');
            linhas.push(suggestion.texto_original);
        }
        linhas.push('');
        linhas.push(`Pedido do usuário: ${instrucao.trim()}`);
        return linhas.join('\n');
    };

    const handleCustomAction = (suggestion: ActionLinkSuggestion) => {
        const instrucao = (customInputs[suggestion.id] || '').trim();
        if (!instrucao || !onAskCopiloto) return;
        onAskCopiloto(buildCustomActionPrompt(suggestion, instrucao));
        setCustomInputs(prev => ({ ...prev, [suggestion.id]: '' }));
        setIsModalOpen(false);
    };

    const expiredCount = sorted.filter(s => s.status === 'expired').length;

    return (
        <>
            <DashboardCard
                title={`Sinais para vincular a ações (${sorted.length})`}
                isDark={isDark}
                onRedirect={() => setIsModalOpen(true)}
            >
                <div className="flex flex-col gap-2">
                    {sorted.slice(0, 3).map(suggestion => (
                        <div key={suggestion.id} className="flex items-center gap-2 min-w-0">
                            <span className="shrink-0 text-sm">{_CANAL_ICONS[suggestion.canal || 'email'] || '🔔'}</span>
                            <span className={`text-xs font-semibold truncate flex-1 ${isDark ? 'text-white/80' : 'text-slate-700'}`}>
                                {suggestion.titulo_sinal || '(sem título)'}
                            </span>
                            <span className={`shrink-0 text-[10px] font-mono ${isDark ? 'text-white/40' : 'text-slate-400'}`}>
                                {formatSuggestionTimestamp(suggestion.analyzed_at)}
                            </span>
                        </div>
                    ))}
                    {sorted.length > 3 && (
                        <p className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}>
                            + {sorted.length - 3} outro(s) sinal(is) pendente(s)
                        </p>
                    )}
                    <p className={`text-[9px] mt-1 ${isDark ? 'text-white/30' : 'text-slate-400'}`}>
                        {expiredCount > 0 ? `${expiredCount} expirado(s) no Telegram — ` : ''}Toque para revisar e decidir.
                    </p>
                </div>
            </DashboardCard>

            {isModalOpen && (
                <div
                    className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200"
                    onClick={() => setIsModalOpen(false)}
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        className={`w-full max-w-3xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl animate-in zoom-in-95 ${
                            isDark ? 'bg-[#151c27] border border-[#2a313d] text-white' : 'bg-white text-[#151c27]'
                        }`}
                    >
                        <div className={`flex items-center justify-between px-7 py-5 border-b shrink-0 ${isDark ? 'border-[#2a313d]' : 'border-slate-100'}`}>
                            <h3 className="text-base font-bold uppercase tracking-wider">
                                Sinais para vincular a ações ({filtered.length !== sorted.length ? `${filtered.length} de ${sorted.length}` : sorted.length})
                            </h3>
                            <button
                                type="button"
                                onClick={() => setIsModalOpen(false)}
                                aria-label="Fechar"
                                className={`p-2 rounded-lg transition ${isDark ? 'text-slate-400 hover:bg-white/5' : 'text-slate-400 hover:bg-slate-100'}`}
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>
                        <div className={`px-7 py-3 border-b flex flex-wrap items-center gap-3 shrink-0 ${isDark ? 'border-[#2a313d] bg-white/[0.02]' : 'border-slate-100 bg-slate-50/50'}`}>
                            <div className="relative flex-1 min-w-[200px]">
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="Filtrar por remetente, título, ação..."
                                    className={`w-full text-xs rounded-lg px-3 py-2 pl-8 outline-none border transition focus:ring-2 focus:ring-[#9333ea] ${
                                        isDark ? 'bg-white/5 border-white/10 text-white placeholder:text-white/30' : 'bg-white border-slate-200 text-slate-900 placeholder:text-slate-400'
                                    }`}
                                />
                                <svg className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                </svg>
                            </div>
                            {filtered.length > 0 && (
                                <button
                                    type="button"
                                    onClick={dismissAllVisible}
                                    disabled={dismissingAll}
                                    title="Descarta todos os sinais atualmente visíveis no filtro"
                                    className="text-[10px] font-black uppercase tracking-wider px-3 py-2 rounded-lg border transition disabled:opacity-50 text-rose-500 hover:bg-rose-500/10 border-rose-500/20"
                                >
                                    {dismissingAll ? 'Dispensando...' : `Dispensar visíveis (${filtered.length})`}
                                </button>
                            )}
                        </div>
                        <div className="flex-1 min-h-0 overflow-y-auto px-7 py-5 flex flex-col gap-3">
                            {filtered.length === 0 ? (
                                <div className="py-12 text-center text-xs font-mono text-slate-400">
                                    Nenhum sinal encontrado{searchQuery ? ' para o filtro atual.' : '.'}
                                </div>
                            ) : filtered.map(suggestion => {
                                const isExpanded = expandedIds.has(suggestion.id);
                                const mutacoesDescritas = describeMutations(suggestion.mutacoes_propostas);
                                return (
                                    <div key={suggestion.id} className={`shrink-0 rounded-2xl border overflow-hidden ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-200 bg-slate-50'}`}>
                                        <button
                                            type="button"
                                            onClick={() => toggleExpanded(suggestion.id)}
                                            aria-expanded={isExpanded}
                                            className={`w-full flex items-start gap-3 p-4 text-left transition ${isDark ? 'hover:bg-white/5' : 'hover:bg-slate-100'}`}
                                        >
                                            <span className="shrink-0 text-2xl leading-none mt-0.5">{_CANAL_ICONS[suggestion.canal || 'email'] || '🔔'}</span>
                                            <div className="min-w-0 flex-1">
                                                <p className="text-sm font-bold truncate">{suggestion.titulo_sinal || '(sem título)'}</p>
                                                <p className={`mt-0.5 text-xs truncate ${isDark ? 'text-white/50' : 'text-slate-500'}`}>
                                                    {_CANAL_LABELS[suggestion.canal || 'email'] || 'Sinal'} · {suggestion.origem_sinal}
                                                </p>
                                                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                                    <span className={`text-[11px] font-mono font-semibold ${isDark ? 'text-white/40' : 'text-slate-400'}`}>
                                                        {formatSuggestionTimestamp(suggestion.analyzed_at)}
                                                    </span>
                                                    {suggestion.status === 'expired' && (
                                                        <span className="text-[10px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-600">
                                                            Expirado no Telegram
                                                        </span>
                                                    )}
                                                    {suggestion.task_titulo && (
                                                        <span className={`text-[10px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded ${isDark ? 'bg-indigo-500/15 text-indigo-300' : 'bg-indigo-50 text-indigo-600'}`}>
                                                            → ação vinculada
                                                        </span>
                                                    )}
                                                    {mutacoesDescritas.length > 0 && (
                                                        <span className="text-[10px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-600">
                                                            Ajuste sugerido
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                            <svg
                                                className={`w-5 h-5 shrink-0 mt-1 transition-transform ${isDark ? 'text-white/40' : 'text-slate-400'} ${isExpanded ? 'rotate-180' : ''}`}
                                                fill="none" stroke="currentColor" viewBox="0 0 24 24"
                                            >
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                                            </svg>
                                        </button>

                                        {isExpanded && (
                                            <div className={`px-4 pb-4 border-t ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
                                                {suggestion.task_titulo && (
                                                    <div className={`mt-3 rounded-xl px-3 py-2.5 ${isDark ? 'bg-indigo-500/10' : 'bg-indigo-50'}`}>
                                                        <p className={`text-[11px] font-black uppercase tracking-wider ${isDark ? 'text-indigo-300/70' : 'text-indigo-400'}`}>
                                                            Ação vinculada
                                                        </p>
                                                        {suggestion.task_id ? (
                                                            <button
                                                                type="button"
                                                                onClick={() => onOpenTask?.(suggestion.task_id as string)}
                                                                className={`mt-0.5 text-sm font-bold underline underline-offset-2 decoration-dotted text-left ${isDark ? 'text-indigo-300 hover:text-indigo-200' : 'text-indigo-600 hover:text-indigo-700'}`}
                                                            >
                                                                {suggestion.task_titulo}{suggestion.task_status ? ` · ${suggestion.task_status}` : ''}
                                                            </button>
                                                        ) : (
                                                            <p className={`mt-0.5 text-sm font-bold ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}>
                                                                {suggestion.task_titulo}{suggestion.task_status ? ` · ${suggestion.task_status}` : ''}
                                                            </p>
                                                        )}
                                                    </div>
                                                )}
                                                {suggestion.resumo && (
                                                    <div className="mt-3">
                                                        <p className={`text-[11px] font-black uppercase tracking-wider ${isDark ? 'text-white/30' : 'text-slate-400'}`}>
                                                            Resumo do sinal
                                                        </p>
                                                        <p className={`mt-1 text-sm leading-relaxed ${isDark ? 'text-white/70' : 'text-slate-600'}`}>{suggestion.resumo}</p>
                                                    </div>
                                                )}
                                                {suggestion.numero_processo && (
                                                    <p className={`mt-2 text-xs font-mono ${isDark ? 'text-white/50' : 'text-slate-500'}`}>
                                                        Processo SIPAC: <span className="font-bold">{suggestion.numero_processo}</span>
                                                    </p>
                                                )}
                                                {suggestion.texto_original && (
                                                    <div className="mt-3">
                                                        <p className={`text-[11px] font-black uppercase tracking-wider ${isDark ? 'text-white/30' : 'text-slate-400'}`}>
                                                            Mensagem original
                                                        </p>
                                                        <div className={`mt-1 max-h-48 overflow-y-auto rounded-lg border px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap ${isDark ? 'border-white/10 bg-black/20 text-white/60' : 'border-slate-200 bg-white text-slate-600'}`}>
                                                            {suggestion.texto_original}
                                                        </div>
                                                    </div>
                                                )}
                                                {suggestion.itens_de_acao && suggestion.itens_de_acao.length > 0 && (
                                                    <div className="mt-3">
                                                        <p className={`text-[11px] font-black uppercase tracking-wider ${isDark ? 'text-white/30' : 'text-slate-400'}`}>Itens de ação</p>
                                                        <ul className="mt-1 space-y-1">
                                                            {suggestion.itens_de_acao.map((item, idx) => (
                                                                <li key={idx} className={`text-sm leading-relaxed ${isDark ? 'text-white/70' : 'text-slate-700'}`}>
                                                                    • {item.descricao}{item.responsavel ? ` — ${item.responsavel}` : ''}{item.prazo ? ` (prazo ${item.prazo})` : ''}
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    </div>
                                                )}
                                                {suggestion.decisoes && suggestion.decisoes.length > 0 && (
                                                    <div className="mt-3">
                                                        <p className={`text-[11px] font-black uppercase tracking-wider ${isDark ? 'text-white/30' : 'text-slate-400'}`}>Decisões</p>
                                                        <ul className="mt-1 space-y-1">
                                                            {suggestion.decisoes.map((d, idx) => (
                                                                <li key={idx} className={`text-sm leading-relaxed ${isDark ? 'text-white/70' : 'text-slate-700'}`}>• {d}</li>
                                                            ))}
                                                        </ul>
                                                    </div>
                                                )}
                                                {mutacoesDescritas.length > 0 && (
                                                    <div className={`mt-3 rounded-xl px-3 py-2.5 ${isDark ? 'bg-indigo-500/10' : 'bg-indigo-50'}`}>
                                                        <p className={`text-[11px] font-black uppercase tracking-wider ${isDark ? 'text-indigo-300/70' : 'text-indigo-400'}`}>
                                                            Ajuste proposto na ação
                                                        </p>
                                                        <ul className="mt-1 space-y-1">
                                                            {mutacoesDescritas.map((m, idx) => (
                                                                <li key={idx} className={`text-sm leading-relaxed ${isDark ? 'text-indigo-200' : 'text-indigo-700'}`}>• {m}</li>
                                                            ))}
                                                        </ul>
                                                    </div>
                                                )}

                                                {onAskCopiloto && (
                                                    <div className="mt-3">
                                                        <p className={`text-[11px] font-black uppercase tracking-wider ${isDark ? 'text-white/30' : 'text-slate-400'}`}>
                                                            Ação personalizada com IA
                                                        </p>
                                                        <textarea
                                                            value={customInputs[suggestion.id] || ''}
                                                            onChange={(e) => setCustomInputs(prev => ({ ...prev, [suggestion.id]: e.target.value }))}
                                                            placeholder='Ex: "Registre esse número de SIPAC no diário e acompanhe esse processo."'
                                                            rows={2}
                                                            className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-[#9333ea] resize-none ${
                                                                isDark ? 'bg-white/5 border-white/10 text-white placeholder:text-white/30' : 'bg-white border-slate-200 text-slate-800 placeholder:text-slate-400'
                                                            }`}
                                                        />
                                                        <button
                                                            type="button"
                                                            disabled={!(customInputs[suggestion.id] || '').trim()}
                                                            onClick={() => handleCustomAction(suggestion)}
                                                            className="mt-1.5 rounded-lg border border-[#9333ea] px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-[#9333ea] transition hover:bg-[#9333ea]/10 disabled:cursor-not-allowed disabled:opacity-40"
                                                        >
                                                            Pedir ao Gaspar
                                                        </button>
                                                    </div>
                                                )}

                                                <div className="mt-4 flex flex-wrap gap-2">
                                                    <button
                                                        type="button"
                                                        disabled={busyId === suggestion.id}
                                                        onClick={() => decide(suggestion, 'ok')}
                                                        className="flex-1 rounded-lg bg-[#9333ea] py-2 text-xs font-bold uppercase tracking-wider text-white transition hover:bg-[#7800ce] disabled:cursor-not-allowed disabled:opacity-50"
                                                    >
                                                        Registrar
                                                    </button>
                                                    {mutacoesDescritas.length > 0 && (
                                                        <button
                                                            type="button"
                                                            disabled={busyId === suggestion.id}
                                                            onClick={() => decide(suggestion, 'mut')}
                                                            className="flex-1 rounded-lg border border-indigo-500 py-2 text-xs font-bold uppercase tracking-wider text-indigo-500 transition hover:bg-indigo-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                                                        >
                                                            Registrar + aplicar mudanças
                                                        </button>
                                                    )}
                                                    {suggestion.reativar_sugerido && (
                                                        <button
                                                            type="button"
                                                            disabled={busyId === suggestion.id}
                                                            onClick={() => decide(suggestion, 'on')}
                                                            className="flex-1 rounded-lg border border-[#9333ea] py-2 text-xs font-bold uppercase tracking-wider text-[#9333ea] transition hover:bg-[#9333ea]/10 disabled:cursor-not-allowed disabled:opacity-50"
                                                        >
                                                            Registrar + Reativar
                                                        </button>
                                                    )}
                                                    <button
                                                        type="button"
                                                        disabled={busyId === suggestion.id}
                                                        onClick={() => decide(suggestion, 'no')}
                                                        className={`rounded-lg px-4 py-2 text-xs font-bold uppercase tracking-wider transition disabled:cursor-not-allowed disabled:opacity-50 ${isDark ? 'text-white/40 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-200'}`}
                                                    >
                                                        Ignorar
                                                    </button>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

// --- CARD: AÇÕES DE HOJE (colapsável + barra do dia) ---
// N29: um card por ação de hoje, com progresso real (etapas_feitas/etapas_totais,
// já calculado em morning_summary.py) e uma barra do dia que soma esse progresso.
// Ação cuja `subtarefa_do_dia` está aguardando terceiro sai da lista principal e
// vira "em espera" automaticamente -- não conta na barra, porque hoje não depende
// de André. Lê resumo_matinal/{data} ao vivo, mesmo padrão de listener que o
// EmailLinkSuggestionsPanel já usa acima.
// Exportado -- também usado fora do Dashboard desktop, na visão mobile
// (index.tsx renderiza este card acima da MobileShortcutsView), já que
// abaixo do breakpoint `sm` o DashboardView inteiro não é montado.
// Quadro compacto das ações em stand-by, abaixo de "Ações de hoje". Vem
// fechado; o cabeçalho mostra só a contagem.
const AcoesStandbyCard: React.FC<{
    tarefas: Tarefa[];
    isDark?: boolean;
    onOpenTask?: (taskId: string) => void;
}> = ({ tarefas, isDark = false, onOpenTask }) => {
    const [aberto, setAberto] = useState(false);
    const standby = useMemo(() => tarefas
        .filter(t => isStandbyStatus(t.status))
        .sort((a, b) => String(a.titulo || '').localeCompare(String(b.titulo || ''), 'pt-BR')),
    [tarefas]);

    if (standby.length === 0) return null;

    return (
        <div
            style={{
                boxShadow: isDark
                    ? '0 6px 12px rgba(0, 0, 0, 0.4), 0 4px 4px rgba(0, 0, 0, 0.2)'
                    : '0 6px 12px rgba(21, 28, 39, 0.05), 0 4px 4px rgba(21, 28, 39, 0.03)',
            }}
            className={`rounded-2xl border ${isDark ? 'bg-[#151c27] border-[#2a313d]' : 'bg-white border-[#f3f4f6]'}`}
        >
            <button
                type="button"
                onClick={() => setAberto(v => !v)}
                aria-expanded={aberto}
                className="w-full flex items-center justify-between gap-3 px-5 py-3.5 text-left"
            >
                <span className={`text-xs font-bold uppercase tracking-[0.05em] ${isDark ? 'text-[#ebf1ff]' : 'text-[#151c27]'}`}>
                    Ações em stand-by
                    <span className={`ml-2 text-[11px] font-bold normal-case tracking-normal ${isDark ? 'text-slate-500' : 'text-[#7e7386]'}`}>
                        {standby.length}
                    </span>
                </span>
                <svg
                    width="16" height="16" viewBox="0 0 24 24" fill="none"
                    stroke={isDark ? '#7e8aa3' : '#7e7386'} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
                    className="flex-shrink-0 transition-transform"
                    style={{ transform: aberto ? 'rotate(180deg)' : 'rotate(0deg)' }}
                >
                    <path d="m6 9 6 6 6-6" />
                </svg>
            </button>
            {aberto && (
                <div className="flex flex-col gap-2 px-5 pb-4">
                    {standby.map(t => {
                        const plano = Array.isArray(t.plano_acao) ? t.plano_acao : [];
                        const [feitas, totais] = contarSubtarefas(plano);
                        const data = String(t.data_limite || '').slice(0, 10);
                        return (
                            <button
                                key={t.id}
                                type="button"
                                title={t.titulo}
                                onClick={() => onOpenTask?.(t.id)}
                                disabled={!onOpenTask}
                                className={`flex items-center gap-3 px-4 py-2.5 rounded-xl border text-left transition-colors ${
                                    isDark ? 'bg-[#1e293b] border-[#2a313d] hover:border-[#9333ea]/40' : 'bg-[#f8f9fc] border-[#eef0f4] hover:border-[#9333ea]/40'
                                }`}
                            >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={isDark ? '#7e8aa3' : '#7e7386'} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0">
                                    <rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" />
                                </svg>
                                <span className={`flex-1 min-w-0 text-[13px] font-semibold truncate ${isDark ? 'text-slate-300' : 'text-[#4d4354]'}`}>{t.titulo}</span>
                                <span className={`text-[11px] font-bold tabular-nums whitespace-nowrap ${isDark ? 'text-slate-500' : 'text-[#7e7386]'}`}>
                                    {totais > 0 ? `${feitas}/${totais}` : ''}{totais > 0 && data ? ' · ' : ''}{data}
                                </span>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

/**
 * O resumo das 05:00 define quais ações pertencem ao dia. Quem assina o
 * documento é o pai (`resumo` por prop) quando ele também precisa dele; sem a
 * prop, o card assina sozinho.
 */
const useResumoMatinal = (ativo: boolean): ResumoMatinal | null => {
    const [resumo, setResumo] = useState<ResumoMatinal | null>(null);
    useEffect(() => {
        if (!ativo) return;
        const ref = doc(db, 'resumo_matinal', formatDateLocalISO(new Date()));
        const unsub = onSnapshot(ref, (snap) => {
            setResumo(snap.exists() ? (snap.data() as ResumoMatinal) : null);
        });
        return () => unsub();
    }, [ativo]);
    return resumo;
};

interface AcoesDoDiaCardProps {
    isDark?: boolean;
    /** Resumo já assinado pelo pai. `undefined`: o card assina sozinho. */
    resumo?: ResumoMatinal | null;
    /** `acao_id` -> motivo, de `briefing_dia.hoje`. */
    foco?: Map<string, string>;
    /** "O agente prepara hoje", de `briefing_dia.eu_faco`. */
    agentePrepara?: LinhaAgentePrepara[];
    /** Quantas ações o dia tem agora (ativas e em espera), para o cabeçalho da tela. */
    onContagem?: (contagem: { ativas: number; emEspera: number }) => void;
}

const IconeFoco: React.FC<{ tamanho?: number }> = ({ tamanho = 13 }) => (
    <svg width={tamanho} height={tamanho} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M5 21V4" /><path d="M5 4h12l-2.5 4L17 12H5" />
    </svg>
);

export const AcoesDoDiaCard: React.FC<AcoesDoDiaCardProps> = ({
    isDark = false, resumo: resumoDoPai, foco, agentePrepara = [], onContagem,
}) => {
    const resumoProprio = useResumoMatinal(resumoDoPai === undefined);
    const resumo = resumoDoPai === undefined ? resumoProprio : resumoDoPai;
    const [expanded, setExpanded] = useState<Record<string, boolean>>({});
    const [planos, setPlanos] = useState<Record<string, ActionPlanItem[]>>({});
    const [carregandoPlanos, setCarregandoPlanos] = useState<Record<string, boolean>>({});
    const [errosPlanos, setErrosPlanos] = useState<Record<string, boolean>>({});
    const [acoesAoVivo, setAcoesAoVivo] = useState<Record<string, Tarefa>>({});
    const [soAgente, setSoAgente] = useState(false);
    const [esperaAberta, setEsperaAberta] = useState(true);

    useEffect(() => {
        if (!resumo) return;

        // O resumo define quais ações pertencem ao dia. Para elas, a própria
        // tarefa é a fonte viva: qualquer escrita externa atualiza o card sem
        // depender de recarregar a página.
        const ids = [...new Set([
            ...(resumo.hoje?.avanco ?? []),
            ...(resumo.hoje?.continuo ?? []),
            ...(resumo.hoje?.atrasadas ?? []),
            ...(resumo.hoje?.aguardando_terceiro ?? []),
        ].map(acao => acao.id))];
        const unsubs = ids.map(id => onSnapshot(doc(db, 'tarefas', id), snap => {
            setAcoesAoVivo(prev => {
                if (!snap.exists()) {
                    const { [id]: _, ...resto } = prev;
                    return resto;
                }
                return { ...prev, [id]: { id: snap.id, ...(snap.data() as Omit<Tarefa, 'id'>) } };
            });
        }));
        return () => unsubs.forEach(unsub => unsub());
    }, [resumo]);

    const hojeId = formatDateLocalISO(new Date());
    const { ativas, emEspera } = classificarAcoesDoDia(resumo, acoesAoVivo, hojeId);

    useEffect(() => {
        onContagem?.({ ativas: ativas.length, emEspera: emEspera.length });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [ativas.length, emEspera.length]);

    if (!resumo) return null;
    if (ativas.length === 0 && emEspera.length === 0) return null;

    const totalFeitas = ativas.reduce((sum, a) => sum + (a.etapas_feitas || 0), 0);
    const totalPassos = ativas.reduce((sum, a) => sum + (a.etapas_totais || 0), 0);
    const diaPct = totalPassos > 0 ? Math.round((totalFeitas / totalPassos) * 100) : 0;
    const concluida = (a: ResumoAcao) => a.etapas_totais > 0 && a.etapas_feitas >= a.etapas_totais;
    const concluidasHoje = ativas.filter(concluida).length;
    const diaConcluido = ativas.length > 0 && diaPct >= 100;

    const toggle = async (id: string) => {
        const vaiAbrir = !expanded[id];
        setExpanded(prev => ({ ...prev, [id]: !prev[id] }));

        // O resumo diário só tem o próximo passo. O plano completo é lido sob
        // demanda para mostrar as etapas reais sem listeners permanentes extras.
        if (!vaiAbrir || id in planos || id in acoesAoVivo || carregandoPlanos[id]) return;
        setCarregandoPlanos(prev => ({ ...prev, [id]: true }));
        try {
            const snap = await getDoc(doc(db, 'tarefas', id));
            const plano = snap.exists() && Array.isArray(snap.data().plano_acao)
                ? snap.data().plano_acao as ActionPlanItem[]
                : [];
            setPlanos(prev => ({ ...prev, [id]: plano }));
            setErrosPlanos(prev => ({ ...prev, [id]: false }));
        } catch (error) {
            console.error('Não foi possível carregar as etapas da ação:', error);
            setErrosPlanos(prev => ({ ...prev, [id]: true }));
        } finally {
            setCarregandoPlanos(prev => ({ ...prev, [id]: false }));
        }
    };

    // O plano vivo da ação: o snapshot da tarefa quando já chegou, senão o lido sob demanda.
    const planoDe = (a: ResumoAcao): ActionPlanItem[] => acoesAoVivo[a.id]?.plano_acao || planos[a.id] || [];
    // Calculado a cada render com o plano vivo — nunca gravado: um número gravado
    // diverge na primeira etapa que o agente marca como feita.
    const paraAgente = (a: ResumoAcao) => contarParaAgente(planoDe(a));
    const rotuloParaAgente = (n: number) => `${n} ${n === 1 ? 'etapa' : 'etapas'} para o agente`;
    // O filtro só muda o que aparece; a barra do dia continua contando todas as ativas.
    const ativasVisiveis = soAgente ? ativas.filter(a => paraAgente(a) > 0) : ativas;
    const emEsperaVisiveis = soAgente ? emEspera.filter(a => paraAgente(a) > 0) : emEspera;

    // O André corrige quem executa a etapa. Lê o plano dentro da transação e troca
    // só essa etapa, para não apagar o que o agente gravou no meio do caminho;
    // `comExecutorNoPlano` grava `executor_definido_por: 'usuario'`.
    const corrigirExecutor = async (a: ResumoAcao, etapaId: string, executor: EtapaExecutor) => {
        try {
            const ref = doc(db, 'tarefas', a.id);
            await runTransaction(db, async (transaction) => {
                const snap = await transaction.get(ref);
                if (!snap.exists()) return;
                const plano = snap.data().plano_acao;
                if (!Array.isArray(plano)) return;
                transaction.update(ref, {
                    plano_acao: comExecutorNoPlano(plano as ActionPlanItem[], etapaId, executor),
                    data_atualizacao: new Date().toISOString(),
                });
            });
        } catch (error) {
            console.error('Não foi possível gravar quem executa a etapa:', error);
        }
    };

    const suave = isDark ? 'text-slate-400' : 'text-[#5f586a]';
    const borda = isDark ? 'border-[#2a313d]' : 'border-[#ece9f3]';

    const marcaDaEtapa = (estado: SubtarefaEstado) => {
        if (estado === 'aguardando_terceiro') {
            return (
                <span className="flex-none w-[18px] h-[18px] mt-px rounded-full box-border inline-flex items-center justify-center bg-[#e8f0fc] border-2 border-[#1d4a8a]" title="Aguardando terceiro">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#1d4a8a" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 6v6l4 2" /></svg>
                </span>
            );
        }
        return (
            <span className={`flex-none w-[18px] h-[18px] mt-px rounded-full box-border inline-flex items-center justify-center border-2 ${
                estado === 'em_andamento' ? 'border-[#7e22ce]' : 'border-[#a9a3b8]'
            } ${isDark ? 'bg-transparent' : 'bg-white'}`}>
                {estado === 'em_andamento' && <span className="w-1.5 h-1.5 rounded-full bg-[#7e22ce]" />}
            </span>
        );
    };

    // Painel de etapas restantes, usado pelas ações ativas e pelas em espera.
    const painelEtapas = (a: ResumoAcao) => {
        // Etapa sem data herda a data da ação; a lista segue a data efetiva, e o
        // empate mantém a ordem do plano (sort estável).
        const dataDaAcao = String(a.data_limite || '').slice(0, 10);
        const dataEfetiva = (etapa: ActionPlanItem) => String(etapa.data_prevista || '').slice(0, 10) || dataDaAcao;
        const etapasAbertas = planoDe(a)
            .filter(etapa => textoDaSubtarefa(etapa) && !estaFeita(etapa) && (!soAgente || eDoAgente(etapa)))
            .sort((x, y) => (dataEfetiva(x) || '9999').localeCompare(dataEfetiva(y) || '9999'));
        return (
            <div className={`border-t mt-0.5 pt-1.5 max-h-[420px] overflow-y-auto flex flex-col ${borda}`}>
                {carregandoPlanos[a.id] ? (
                    <p className={`m-0 py-1 text-xs ${suave}`}>Carregando etapas…</p>
                ) : errosPlanos[a.id] ? (
                    <p className="m-0 py-1 text-xs text-rose-500">Não foi possível carregar as etapas agora.</p>
                ) : etapasAbertas.length > 0 ? (
                    etapasAbertas.map(etapa => {
                        const estado = estadoDaSubtarefa(etapa);
                        const dataPrevista = dataEfetiva(etapa);
                        return (
                            <div key={etapa.id} className="flex items-start gap-2.5 py-[7px] px-0.5">
                                {marcaDaEtapa(estado)}
                                <div className="flex-1 min-w-0 flex flex-col gap-[3px]">
                                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                                        <p className={`m-0 text-[12.5px] leading-snug ${isDark ? 'text-slate-200' : 'text-[#151c27]'}`}>{textoDaSubtarefa(etapa)}</p>
                                        <EtiquetaExecutor etapa={etapa} isDark={isDark} />
                                    </div>
                                    {estado === 'aguardando_terceiro' && (
                                        <p className={`m-0 text-[11.5px] font-semibold ${isDark ? 'text-sky-300' : 'text-[#1d4a8a]'}`}>
                                            Aguardando{etapa.aguardando_de ? ` ${etapa.aguardando_de}` : ' terceiro'}
                                        </p>
                                    )}
                                    {eDoAgente(etapa) && etapa.executor_como && (
                                        <p className={`m-0 text-[11.5px] leading-snug ${isDark ? 'text-slate-400' : 'text-[#4a4455]'}`}>{etapa.executor_como}</p>
                                    )}
                                </div>
                                {dataPrevista && (
                                    <span className={`flex-none text-[11.5px] font-semibold whitespace-nowrap ${suave}`}>
                                        {dataPrevista.slice(8, 10)}/{dataPrevista.slice(5, 7)}
                                    </span>
                                )}
                                <MenuExecutor
                                    etapa={etapa}
                                    textoEtapa={textoDaSubtarefa(etapa)}
                                    isDark={isDark}
                                    onEscolher={executor => corrigirExecutor(a, etapa.id, executor)}
                                />
                            </div>
                        );
                    })
                ) : a.etapas_totais > 0 ? (
                    <p className={`m-0 py-1 text-xs ${suave}`}>Todas as etapas deste plano foram concluídas.</p>
                ) : a.proximo_passo && (
                    <p className={`m-0 py-1 text-xs leading-relaxed ${isDark ? 'text-slate-400' : 'text-[#4d4354]'}`}>{a.proximo_passo}</p>
                )}
            </div>
        );
    };

    const botaoEtapas = (a: ResumoAcao, aberta: boolean, apenasSeta = false) => (
        <button
            type="button"
            onClick={() => toggle(a.id)}
            aria-expanded={aberta}
            aria-label={`${aberta ? 'Ocultar' : 'Ver'} etapas: ${a.titulo}`}
            title={`${aberta ? 'Ocultar' : 'Ver'} etapas`}
            className={`flex-none min-h-[44px] rounded-xl border inline-flex items-center justify-center gap-1.5 text-[12.5px] font-bold whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7e22ce] ${
                apenasSeta ? 'w-11' : 'px-3'
            } ${isDark ? 'border-[#3b3552] text-violet-300 bg-transparent' : 'border-[#d9d4e6] text-[#4c1d95] bg-white'}`}
        >
            {!apenasSeta && (aberta ? 'Ocultar etapas' : 'Ver etapas')}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ transform: aberta ? 'rotate(180deg)' : 'none' }}>
                <path d="M6 9l6 6 6-6" />
            </svg>
        </button>
    );

    return (
        <section
            aria-label="Ações de hoje"
            className={`rounded-[20px] border p-[20px_22px] flex flex-col gap-3.5 ${isDark ? 'bg-[#151c27] border-[#2a313d]' : 'bg-white border-[#ececf1]'}`}
        >
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
                <h2 className="m-0 text-base font-extrabold">Ações de hoje</h2>
                <div className="flex items-center gap-2.5">
                    <span className={`text-[12.5px] font-semibold ${suave}`}>
                        {concluidasHoje} de {ativas.length} concluídas
                    </span>
                    <div className={`w-24 h-1.5 rounded-full overflow-hidden ${isDark ? 'bg-[#2a313d]' : 'bg-[#eeeef3]'}`} role="progressbar" aria-valuenow={diaPct} aria-valuemin={0} aria-valuemax={100} aria-label="Etapas concluídas hoje">
                        <div style={{ width: `${Math.min(diaPct, 100)}%`, background: diaConcluido ? '#10b981' : '#7e22ce' }} className="h-full transition-all duration-500" />
                    </div>
                    <span className={`text-xs font-bold whitespace-nowrap ${suave}`}>{emEspera.length} em espera</span>
                </div>
            </div>

            {diaConcluido && (
                <p className="m-0 text-[13px] font-bold">Dia concluído — as ações de hoje estão fechadas.</p>
            )}

            <AgentePreparaHoje linhas={agentePrepara} isDark={isDark} />

            {/* Filtro por executor + legenda das etiquetas */}
            <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2">
                <button
                    type="button"
                    aria-pressed={soAgente}
                    onClick={() => setSoAgente(v => !v)}
                    className={`min-h-[44px] px-3.5 rounded-full border text-[11.5px] font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7e22ce] ${
                        soAgente
                            ? 'bg-[#4c1d95] border-[#4c1d95] text-white'
                            : isDark ? 'bg-transparent border-[#4c3a7a] text-violet-300' : 'bg-white border-[#c9bfe6] text-[#4c1d95]'
                    }`}
                >
                    Só o que o agente faz
                </button>
                <span className={`inline-flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[11.5px] ${isDark ? 'text-slate-400' : 'text-[#4a4455]'}`}>
                    <EtiquetaExecutor etapa={{ executor: 'agente' }} isDark={isDark} />
                    <EtiquetaExecutor etapa={{ executor: 'agente_aprovado' }} isDark={isDark} />
                    <span>sem selo: só você</span>
                </span>
            </div>

            {soAgente && ativasVisiveis.length === 0 && emEsperaVisiveis.length === 0 && (
                <p className={`m-0 text-xs ${suave}`}>Nenhuma etapa em aberto está com o agente.</p>
            )}

            {/* Ações ativas */}
            {ativasVisiveis.length > 0 && (
                <div className="flex flex-col gap-2.5">
                    {ativasVisiveis.map((a) => {
                        const done = concluida(a);
                        const isOpen = soAgente || !!expanded[a.id];
                        const nAgente = paraAgente(a);
                        const pct = a.etapas_totais > 0 ? Math.round((a.etapas_feitas / a.etapas_totais) * 100) : 0;
                        const temFoco = !!foco?.has(a.id);
                        const motivoFoco = foco?.get(a.id) || '';
                        return (
                            <article
                                key={a.id}
                                data-testid="acao-ativa"
                                className={`rounded-2xl border px-4 py-3.5 flex flex-col gap-2 ${isDark ? 'bg-[#1a2230] border-[#2a313d]' : 'bg-[#fcfbfe] border-[#e6e3ee]'}`}
                            >
                                {temFoco && (
                                    <span
                                        data-testid="chip-foco"
                                        className={`self-start text-[11px] font-extrabold tracking-[.06em] uppercase px-2.5 py-0.5 rounded-full border ${
                                            isDark ? 'text-amber-200 bg-amber-900/40 border-amber-700/60' : 'text-[#7a4b00] bg-[#fff1d6] border-[#e3b865]'
                                        }`}
                                    >
                                        Foco{motivoFoco ? ` · ${motivoFoco}` : ''}
                                    </span>
                                )}
                                <h3 className="m-0 text-sm font-bold leading-snug">{a.titulo}</h3>
                                {a.proximo_passo && (
                                    <p className={`m-0 text-[13px] leading-snug ${isDark ? 'text-slate-300' : 'text-[#3d3747]'}`}>
                                        <span className="font-bold">Próximo passo:</span> {a.proximo_passo}
                                    </p>
                                )}
                                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
                                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 flex-1 basis-[240px] min-w-0">
                                        {a.etapas_totais > 0 ? (
                                            <>
                                                <div className={`flex-[0_1_200px] min-w-24 h-1.5 rounded-full overflow-hidden ${isDark ? 'bg-[#2a313d]' : 'bg-[#eeeef3]'}`}>
                                                    <div style={{ width: `${pct}%`, background: done ? '#10b981' : '#7e22ce' }} className="h-full transition-all duration-500" />
                                                </div>
                                                <span className={`text-xs font-bold whitespace-nowrap ${isDark ? 'text-slate-300' : 'text-[#4a4455]'}`}>
                                                    {a.etapas_feitas}/{a.etapas_totais} etapas
                                                </span>
                                            </>
                                        ) : (
                                            <span className={`text-xs font-semibold ${suave}`}>sem plano de etapas</span>
                                        )}
                                        {nAgente > 0 && (
                                            <span
                                                data-testid="contador-agente"
                                                className={`text-[11.5px] font-bold px-2.5 py-0.5 rounded-full whitespace-nowrap ${isDark ? 'text-violet-300 bg-violet-900/40' : 'text-[#4c1d95] bg-[#ece6fa]'}`}
                                            >
                                                {rotuloParaAgente(nAgente)}
                                            </span>
                                        )}
                                    </div>
                                    {botaoEtapas(a, isOpen)}
                                </div>
                                {isOpen && painelEtapas(a)}
                            </article>
                        );
                    })}
                </div>
            )}

            {/* Em espera — compacto, não conta na barra do dia */}
            {emEspera.length > 0 && (
                <div className={`flex flex-col gap-1.5 border-t pt-1 ${isDark ? 'border-[#2a313d]' : 'border-[#f0eff5]'}`}>
                    <button
                        type="button"
                        aria-expanded={esperaAberta}
                        onClick={() => setEsperaAberta(v => !v)}
                        className="min-h-[44px] flex items-center justify-between gap-3 px-1 text-left bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#7e22ce]"
                    >
                        <span className="text-xs font-bold tracking-[.05em] uppercase">
                            Em espera <span className={`ml-1.5 text-[11.5px] tracking-normal normal-case ${suave}`}>{emEsperaVisiveis.length}</span>
                        </span>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={suave} style={{ transform: esperaAberta ? 'rotate(180deg)' : 'none' }}>
                            <path d="M6 9l6 6 6-6" />
                        </svg>
                    </button>
                    {esperaAberta && (
                        <div className="flex flex-col gap-2">
                            {emEsperaVisiveis.map((a) => {
                                const aguardandoDe = a.subtarefa_do_dia?.aguardando_de ?? null;
                                const isOpen = soAgente || !!expanded[a.id];
                                const nAgente = paraAgente(a);
                                const temFoco = !!foco?.has(a.id);
                                const motivoFoco = foco?.get(a.id) || '';
                                return (
                                    <div
                                        key={a.id}
                                        data-testid="acao-em-espera"
                                        className={`flex flex-col gap-0.5 px-3.5 pt-1.5 pb-2 rounded-xl border ${isDark ? 'bg-[#1e293b] border-[#2a313d]' : 'bg-[#f8f9fc] border-[#eef0f4]'}`}
                                    >
                                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`flex-none ${suave}`}>
                                                <rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" />
                                            </svg>
                                            <span className="flex-1 basis-[220px] min-w-0 text-[13px] font-semibold leading-snug" title={a.titulo}>{a.titulo}</span>
                                            {temFoco && (
                                                <span
                                                    data-testid="icone-foco"
                                                    title={`Foco de hoje${motivoFoco ? ` · ${motivoFoco}` : ''}`}
                                                    aria-label={`Foco de hoje${motivoFoco ? ` · ${motivoFoco}` : ''}`}
                                                    role="img"
                                                    className={`flex-none w-[26px] h-[26px] rounded-full border inline-flex items-center justify-center ${
                                                        isDark ? 'text-amber-200 bg-amber-900/40 border-amber-700/60' : 'text-[#7a4b00] bg-[#fff1d6] border-[#e3b865]'
                                                    }`}
                                                >
                                                    <IconeFoco />
                                                </span>
                                            )}
                                            <span
                                                data-testid="espera-de"
                                                title={`Aguardando ${aguardandoDe || 'terceiro'}`}
                                                className={`flex-[0_1_auto] max-w-[200px] inline-flex items-center gap-[5px] text-xs font-semibold whitespace-nowrap ${isDark ? 'text-sky-300' : 'text-[#1d4a8a]'}`}
                                            >
                                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="flex-none">
                                                    <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
                                                </svg>
                                                <span className="overflow-hidden text-ellipsis">{aguardandoDe || 'terceiro'}</span>
                                            </span>
                                            {nAgente > 0 && (
                                                <span
                                                    data-testid="contador-agente"
                                                    title={rotuloParaAgente(nAgente)}
                                                    aria-label={rotuloParaAgente(nAgente)}
                                                    role="img"
                                                    className={`flex-none inline-flex items-center gap-[3px] text-xs font-bold px-2 py-0.5 rounded-full ${isDark ? 'text-violet-300 bg-violet-900/40' : 'text-[#4c1d95] bg-[#ece6fa]'}`}
                                                >
                                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2.5l2 6.2 6.2 2-6.2 2-2 6.3-2-6.3-6.2-2 6.2-2z" /></svg>
                                                    {nAgente}
                                                </span>
                                            )}
                                            <span className={`flex-none min-w-9 text-right text-[11.5px] font-bold ${suave}`}>{a.etapas_feitas}/{a.etapas_totais}</span>
                                            {botaoEtapas(a, isOpen, true)}
                                        </div>
                                        {isOpen && painelEtapas(a)}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}
        </section>
    );
};

// --- MAIN COMPONENT ---

/** Hora local "HH:MM" de um ISO com horário; `null` para data pura (dia inteiro). Mesma leitura do backend. */
const horaDoIso = (valor: unknown): string | null => {
    const texto = String(valor || '');
    return texto.includes('T') ? (texto.split('T')[1].slice(0, 5) || null) : null;
};

/** Painel largo: a partir daqui o corpo vira duas colunas (horizontal, 1440 px). */
const LARGURA_DUAS_COLUNAS = 1280;

const useLarguraMinima = (px: number): boolean => {
    const consulta = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function'
        ? window.matchMedia(`(min-width: ${px}px)`) : null;
    const [larga, setLarga] = useState(() => !!consulta()?.matches);
    useEffect(() => {
        const mq = consulta();
        if (!mq) return;
        setLarga(mq.matches);
        const aoMudar = (e: MediaQueryListEvent) => setLarga(e.matches);
        mq.addEventListener?.('change', aoMudar);
        return () => mq.removeEventListener?.('change', aoMudar);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [px]);
    return larga;
};

const DashboardView: React.FC<DashboardViewProps> = ({
    tarefas = [],
    isDark = false,
    healthWeights = [],
    healthSettings = {} as HealthSettings,
    exerciseLogs = [] as ExerciseLog[],
    onSaveExerciseLog,
    onNavigate,
    onOpenTask,
    onAskCopiloto
}) => {
    const [showNextActions, setShowNextActions] = useState(false);
    const hojeId = useMemo(() => formatDateLocalISO(new Date()), []);
    const todayKey = hojeId;

    // --- FONTES VIVAS E O BRIEFING ---
    // O resumo das 05:00 define o conjunto de ações do dia; o `briefing_dia` traz só o que a
    // IA escreve (Decidir, Foco, o que o agente prepara, Preparo, fora da agenda, avisos).
    // Ações, agenda e filas vêm sempre ao vivo.
    const resumo = useResumoMatinal(true);
    const [briefing, setBriefing] = useState<BriefingDia | null>(null);
    useEffect(() => {
        const unsub = onSnapshot(
            doc(db, 'briefing_dia', hojeId),
            snap => setBriefing(snap.exists() ? (snap.data() as BriefingDia) : null),
            // Sem briefing (ou sem permissão de leitura) a tela abre normal, sem os blocos novos.
            () => setBriefing(null),
        );
        return () => unsub();
    }, [hojeId]);

    const [agendaViva, setAgendaViva] = useState<EventoDaAgenda[] | null>(null);
    useEffect(() => {
        const q = query(
            collection(db, 'google_calendar_events'),
            where('data_inicio', '>=', hojeId),
            where('data_inicio', '<', addDays(hojeId, 1)),
        );
        const unsub = onSnapshot(q, snap => {
            setAgendaViva(snap.docs.map(d => {
                const data = d.data() as any;
                const inicio = horaDoIso(data.data_inicio);
                return { titulo: data.titulo || '(sem título)', inicio, fim: horaDoIso(data.data_fim), dia_inteiro: inicio === null };
            }));
        }, () => setAgendaViva(null));
        return () => unsub();
    }, [hojeId]);

    const refsAtencao = useMemo(
        () => [...new Set((briefing?.decidir ?? []).filter(i => i.origem === 'fila_atencao').map(i => i.ref))].sort(),
        [briefing],
    );
    const [atencao, setAtencao] = useState<OrigemViva['atencao']>({});
    useEffect(() => {
        const unsubs = refsAtencao.map(id => onSnapshot(
            doc(db, 'atencao', id),
            snap => setAtencao(prev => ({ ...prev, [id]: snap.exists() ? { estado: (snap.data() as any).estado } : null })),
            () => undefined,
        ));
        return () => unsubs.forEach(u => u());
    }, [refsAtencao]);

    const vivo: OrigemViva = useMemo(() => ({
        tarefas: Object.fromEntries(tarefas.map(t => [t.id, { status: t.status, titulo: t.titulo, plano_acao: t.plano_acao }])),
        tarefasCarregadas: tarefas.length > 0,
        atencao,
    }), [tarefas, atencao]);

    const decidir = useMemo(() => prepararDecidir(briefing, vivo), [briefing, vivo]);
    const foco = useMemo(() => focoPorAcao(briefing), [briefing]);
    const agentePrepara = useMemo(() => agentePreparaHoje(briefing, vivo), [briefing, vivo]);
    const preparo = useMemo(() => preparoDosProximosDias(briefing, hojeId), [briefing, hojeId]);
    const avisosDoAgente = briefing?.avisos ?? [];

    // O Feito do André: grava só `decidir` (é tudo o que as regras do Firestore deixam a tela
    // mexer), lendo o documento dentro da transação para não desfazer o que o agente atualizou.
    const alternarDecidir = async (linha: LinhaDecidir) => {
        try {
            const ref = doc(db, 'briefing_dia', hojeId);
            await runTransaction(db, async (transaction) => {
                const snap = await transaction.get(ref);
                const atual = snap.exists() ? (snap.data() as BriefingDia).decidir : null;
                if (!Array.isArray(atual)) return;
                transaction.update(ref, { decidir: alternarItemDecidir(atual, linha.item.id, new Date().toISOString()) });
            });
        } catch (error) {
            console.error('Não foi possível gravar o Feito do item de Decidir:', error);
        }
    };

    const [verSugestoes, setVerSugestoes] = useState(false);
    const [sugestoes, setSugestoes] = useState<SugestaoDeElevacao[]>([]);
    useEffect(() => {
        if (!verSugestoes) return;
        const q = query(collection(db, 'elevacoes_sugeridas'), where('status', '==', 'pendente'));
        const unsub = onSnapshot(q, snap => setSugestoes(snap.docs.map(d => ({ id: d.id, ...(d.data() as any) }))), () => undefined);
        return () => unsub();
    }, [verSugestoes]);

    const [contagem, setContagem] = useState({ ativas: 0, emEspera: 0 });

    // --- AGENDA ---
    const agendaDoDia = agendaViva ?? resumo?.agenda ?? [];
    const eventos = useMemo(
        () => eventosDoDia(agendaDoDia, briefing?.fora_da_agenda ?? []),
        [agendaDoDia, briefing],
    );
    const diaInteiro = useMemo(() => agendaDoDia.filter(e => e.dia_inteiro).map(e => e.titulo), [agendaDoDia]);
    const agoraMin = useMinutosAgora();
    const duasColunas = useLarguraMinima(LARGURA_DUAS_COLUNAS);

    // --- PRAZOS FINAIS (ao vivo, a partir das ações) ---
    const prazos: PrazoFinal[] = useMemo(() => {
        const limite = addDays(hojeId, 7);
        return tarefas
            .filter(t => ['em andamento', 'stand-by'].includes(String(t.status || '').toLowerCase()))
            .map(t => ({ t, prazo: String(t.prazo_final || '').slice(0, 10) }))
            .filter(({ prazo }) => /^\d{4}-\d{2}-\d{2}$/.test(prazo) && prazo >= hojeId && prazo <= limite)
            .sort((a, b) => a.prazo.localeCompare(b.prazo))
            .map(({ t, prazo }) => ({ id: t.id, titulo: t.titulo, prazo, dias: diasEntre(hojeId, prazo) }));
    }, [tarefas, hojeId]);

    // --- CARGA SEMANAL ---
    // A carga semanal usa o mesmo critério do card "Ações de hoje": a ação com
    // todos os passos feitos não conta, e a que tem a etapa corrente esperando
    // terceiro vai num segmento próprio da barra. A etapa corrente é a mesma que o
    // backend escolhe (`subtarefaCorrente`): a regra de espera é uma só.
    const inProgressActions = useMemo(() => tarefas.filter(t => t.status !== 'concluído' && t.status !== 'excluído' as any), [tarefas]);

    const workloadActions = useMemo(() => inProgressActions.flatMap(t => {
        const plano = Array.isArray(t.plano_acao) ? t.plano_acao : [];
        const [feitas, totais] = contarSubtarefas(plano);
        if (totais > 0 && feitas >= totais) return [];
        const dataLimite = String(t.data_limite || '').slice(0, 10);
        const corrente = subtarefaCorrente(plano, dataLimite);
        const emEspera = !!corrente && estadoDaSubtarefa(corrente) === 'aguardando_terceiro';
        return [{ id: t.id, titulo: t.titulo, dataLimite, emEspera }];
    }), [inProgressActions]);

    const actionsByDay = useMemo(() => {
        const result = [];
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        for (let i = 0; i < 7; i++) {
            const d = new Date(today);
            d.setDate(today.getDate() + i);
            // Data local: toISOString() vira o dia às 21h (UTC-3) e desloca o gráfico.
            const dStr = formatDateLocalISO(d);
            const doDia = workloadActions.filter(t => t.dataLimite === dStr);
            const waiting = doDia.filter(t => t.emEspera).length;

            result.push({
                dateStr: dStr,
                dayNum: d.getDate(),
                monthName: ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'][d.getMonth()],
                count: doDia.length,
                // Em andamento primeiro, em espera depois -- mesma ordem visual da barra.
                acoes: [...doDia].sort((a, b) => Number(a.emEspera) - Number(b.emEspera)),
                active: doDia.length - waiting,
                waiting,
                isToday: i === 0
            });
        }
        return result;
    }, [workloadActions]);

    // --- SAÚDE: caminhada (o resto fica no módulo Saúde) ---
    const sortedWeights = useMemo(() => [...healthWeights].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()), [healthWeights]);
    const currentWeight = sortedWeights[0]?.weight || 0;
    const targetWeight = healthSettings?.targetWeight || 0;

    const logByDate = useMemo(() => {
        const map = new Map<string, ExerciseLog>();
        exerciseLogs.forEach(l => map.set(l.id, l));
        return map;
    }, [exerciseLogs]);
    const todayHealthLog = logByDate.get(todayKey) || null;

    const last7Days = useMemo(() => {
        const days: string[] = [];
        for (let i = 6; i >= 0; i--) {
            const d = new Date();
            d.setDate(d.getDate() - i);
            days.push(formatDateLocalISO(d));
        }
        return days;
    }, []);

    // N24: mesmos limiares e a mesma lógica de faixa normal / dia de crise do
    // módulo Saúde (walkingIdealKm é o TOPO da faixa normal, não uma meta a perseguir; o
    // piso mínimo não se aplica em dia de crise).
    const todayWalkKm = useMemo(() => sumWalkBlocksKm(todayHealthLog), [todayHealthLog]);
    const walkingMinimumKm = healthSettings?.walkingMinimumKm ?? 3;
    const walkingIdealKm = healthSettings?.walkingIdealKm ?? 6;
    const isCrisisToday = !!todayHealthLog?.pain?.crisis;

    const diasDeCaminhada: DiaDeCaminhada[] = useMemo(() => last7Days.map((day, i) => {
        const log = logByDate.get(day);
        const [a, m, d] = day.split('-').map(Number);
        return {
            rotulo: i === last7Days.length - 1 ? 'hoje' : ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'][new Date(a, m - 1, d).getDay()],
            km: log ? sumWalkBlocksKm(log) : null,
            hoje: i === last7Days.length - 1,
        };
    }), [last7Days, logByDate]);
    const ontemLog = logByDate.get(addDays(todayKey, -1));

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

    // --- LINKS DISCRETOS (calculados ao vivo) ---
    const subtituloSaudeHoje = subtituloSaude({
        pesagemRegistrada: healthWeights.some(w => w.date === todayKey),
        checkinManha: todayHealthLog?.pain?.morning !== undefined && todayHealthLog?.pain?.morning !== null,
        checkinNoite: todayHealthLog?.pain?.evening !== undefined && todayHealthLog?.pain?.evening !== null,
        dorOntem: (() => {
            const dor = ontemLog?.pain;
            const valores = [dor?.morning, dor?.evening].filter((v): v is number => typeof v === 'number');
            return valores.length ? Math.max(...valores) : null;
        })(),
    });
    const subtituloFinanceiroHoje = subtituloFinanceiro(resumo ? (resumo.filas?.contas?.total ?? 0) : null);

    const cargaCard = (
        <DashboardCard title="Carga Semanal de Trabalho" isDark={isDark} onRedirect={() => onNavigate('gallery')} className="flex-1">
                        <div className="flex h-full flex-col gap-4">
                            <p className="text-[10px] font-bold uppercase tracking-[0.2em] font-mono text-slate-400 shrink-0">
                                // CARGA OPERACIONAL D+6
                            </p>

                            {/* N26: o grafico cresce junto com o cartao (flex-1) em vez de ficar em
                                altura fixa -- senao sobra vao vazio quando o cartao estica pra bater
                                com a altura do Resumo Financeiro. */}
                            <div className="grid flex-1 min-h-[200px] grid-cols-7 gap-2 md:gap-3 border-b border-[#f3f4f6] pb-2 dark:border-white/5">
                                {actionsByDay.map((day, i) => {
                                    const maxCount = Math.max(...actionsByDay.map(d => d.count), 1);
                                    const heightPercent = (day.count / maxCount) * 100;

                                    return (
                                        <div key={i} className="flex min-w-0 flex-col items-center group">
                                            <div className="flex flex-1 w-full flex-col justify-end">
                                                <div className="flex flex-1 w-full items-end">
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
                                                        {/* Segmentos empilhados: em espera (âmbar) em cima,
                                                            em andamento (roxo) embaixo, proporcionais à contagem. */}
                                                        <div
                                                            title={day.count > 0 ? `${day.active} em andamento · ${day.waiting} em espera` : undefined}
                                                            className={`flex min-h-0 w-full flex-1 flex-col gap-[2px] overflow-hidden rounded-lg transition-all duration-300 ${
                                                                day.count === 0 ? (isDark ? 'bg-white/5' : 'bg-slate-100') : ''
                                                            } ${day.isToday && day.active > 0 ? 'shadow-[0_0_12px_rgba(120,0,206,0.3)]' : ''}`}
                                                        >
                                                            {day.waiting > 0 && (
                                                                <div
                                                                    className={day.isToday ? 'bg-[#f59e0b]' : 'bg-[#f59e0b]/30 hover:bg-[#f59e0b]/50'}
                                                                    style={{ flexGrow: day.waiting, flexBasis: 0 }}
                                                                />
                                                            )}
                                                            {day.active > 0 && (
                                                                <div
                                                                    className={day.isToday ? 'bg-[#7800ce]' : 'bg-[#9333ea]/20 hover:bg-[#9333ea]/40'}
                                                                    style={{ flexGrow: day.active, flexBasis: 0 }}
                                                                />
                                                            )}
                                                        </div>
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
                            <div className="flex shrink-0 items-center gap-4 text-[9px] font-semibold uppercase tracking-widest font-mono text-slate-400">
                                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-[#9333ea]" />Em andamento</span>
                                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-[#f59e0b]" />Em espera</span>
                            </div>

                            {/* Próximas ações (D+1 a D+6): hoje já está no card "Ações de hoje".
                                stopPropagation porque o cartão inteiro navega para a galeria. */}
                            {actionsByDay.slice(1).some(day => day.count > 0) && (
                                <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
                                    <button
                                        type="button"
                                        onClick={() => setShowNextActions(v => !v)}
                                        aria-expanded={showNextActions}
                                        className={`flex items-center gap-1.5 text-[11px] font-bold ${isDark ? 'text-[#ddb8ff]' : 'text-[#7800ce]'}`}
                                    >
                                        {showNextActions ? 'Ocultar próximas ações' : 'Ver próximas ações'}
                                        <svg
                                            width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                            strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round"
                                            className="transition-transform"
                                            style={{ transform: showNextActions ? 'rotate(180deg)' : 'rotate(0deg)' }}
                                        >
                                            <path d="m6 9 6 6 6-6" />
                                        </svg>
                                    </button>
                                    {showNextActions && (
                                        <div className="mt-3 flex flex-col gap-3">
                                            {actionsByDay.slice(1).filter(day => day.count > 0).map(day => (
                                                <div key={day.dateStr}>
                                                    <p className="m-0 mb-1 text-[10px] font-bold uppercase tracking-widest font-mono text-slate-400">
                                                        {String(day.dayNum).padStart(2, '0')} {day.monthName} · {day.count}
                                                    </p>
                                                    <div className="flex flex-col">
                                                        {day.acoes.map(acao => (
                                                            <button
                                                                key={acao.id}
                                                                type="button"
                                                                title={acao.titulo}
                                                                onClick={() => onOpenTask?.(acao.id)}
                                                                disabled={!onOpenTask}
                                                                className={`flex items-center gap-2 rounded-md px-1.5 py-1 text-left text-[12.5px] ${
                                                                    isDark ? 'text-slate-300 hover:bg-white/5' : 'text-[#4d4354] hover:bg-[#f5f3ff]'
                                                                }`}
                                                            >
                                                                <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${acao.emEspera ? 'bg-[#f59e0b]' : 'bg-[#9333ea]'}`} />
                                                                <span className="min-w-0 flex-1 truncate">{acao.titulo}</span>
                                                            </button>
                                                        ))}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </DashboardCard>
    );

    const total = contagem.ativas + contagem.emEspera;
    const temRodapeDeDecidir = (resumo?.filas?.elevacoes?.total ?? 0) > 0 || (resumo?.avisos_do_sistema ?? []).length > 0;
    const rodapeDeDecidir = (
        <ElevacoesRodape
            total={resumo?.filas?.elevacoes?.total ?? 0}
            avisos={resumo?.avisos_do_sistema ?? []}
            sugestoes={sugestoes}
            onAbrir={setVerSugestoes}
            isDark={isDark}
        />
    );

    return (
        <div
            style={{ fontFamily: 'Inter, sans-serif' }}
            className={`animate-in fade-in duration-700 flex flex-col gap-5 w-full max-w-[1376px] mx-auto p-4 md:p-6 ${
                isDark ? 'text-white' : 'text-[#151c27]'
            }`}
        >
            <CabecalhoDoDia agora={new Date()} acoesHoje={total} emEspera={contagem.emEspera} isDark={isDark} />

            {/* Decidir: só existe com o briefing do dia. Sem briefing, a tela abre normal. */}
            {briefing ? (
                <DecidirBloco
                    linhas={decidir.linhas}
                    pendentes={decidir.pendentes}
                    onAlternar={alternarDecidir}
                    rodape={temRodapeDeDecidir ? rodapeDeDecidir : undefined}
                    isDark={isDark}
                />
            ) : temRodapeDeDecidir && (
                <section aria-label="Avisos do sistema" className={`rounded-2xl border px-[18px] py-3 ${isDark ? 'bg-[#151c27] border-[#2a313d]' : 'bg-white border-[#ececf1]'}`}>
                    {rodapeDeDecidir}
                </section>
            )}

            <EmailLinkSuggestionsPanel isDark={isDark} onOpenTask={onOpenTask} onAskCopiloto={onAskCopiloto} />

            {/* No retrato (coluna única) a ordem é a de `order-*`; a partir de 1280 px as duas
                colunas voltam à ordem do DOM: principal à esquerda, lateral à direita. */}
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start">
                <div className="contents xl:flex xl:flex-col xl:gap-5 xl:flex-[999_1_560px] xl:min-w-0">
                    <div className="order-3 xl:order-none">
                        <AcoesDoDiaCard
                            isDark={isDark}
                            resumo={resumo}
                            foco={foco}
                            agentePrepara={agentePrepara}
                            onContagem={setContagem}
                        />
                    </div>
                    <div className="order-4 xl:order-none">
                        <AcoesStandbyCard tarefas={tarefas} isDark={isDark} onOpenTask={onOpenTask} />
                    </div>
                    <div className="order-5 xl:order-none">{cargaCard}</div>
                </div>

                <aside className="contents xl:flex xl:flex-col xl:gap-5 xl:flex-[1_1_400px] xl:min-w-0">
                    <div className="order-6 xl:order-none">
                        <CaminhadaCard
                            km={todayWalkKm}
                            minimoKm={walkingMinimumKm}
                            idealKm={walkingIdealKm}
                            crise={isCrisisToday}
                            ontemKm={ontemLog ? sumWalkBlocksKm(ontemLog) : null}
                            ontemBlocos={(ontemLog?.walkBlocks || []).filter(b => (b.distance || 0) > 0).length}
                            pesoKg={currentWeight > 0 ? currentWeight : null}
                            alvoKg={targetWeight}
                            dias={diasDeCaminhada}
                            onRegistrar={() => setIsWalkModalOpen(true)}
                            isDark={isDark}
                        />
                    </div>
                    <div className="order-2 xl:order-none">
                        <AgendaBloco eventos={eventos} diaInteiro={diaInteiro} agoraMin={agoraMin} preparo={preparo} isDark={isDark} />
                    </div>
                    <div className="order-1 xl:order-none">
                        <PrazosFinais prazos={prazos} isDark={isDark} variante={duasColunas ? 'lista' : 'faixa'} />
                    </div>
                </aside>
            </div>

            <AvisosDoAgente avisos={avisosDoAgente} isDark={isDark} />

            {/* Menos usados: viraram links. O conteúdo completo mora nos módulos. */}
            <div className="grid gap-5 grid-cols-[repeat(auto-fit,minmax(min(380px,100%),1fr))]">
                <LinkDiscreto titulo="Resumo financeiro" subtitulo={subtituloFinanceiroHoje} onClick={() => onNavigate('finance')} isDark={isDark} />
                <LinkDiscreto titulo="Saúde e telemetria" subtitulo={subtituloSaudeHoje} onClick={() => onNavigate('saude')} isDark={isDark} />
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
                            Distância do bloco em km. Soma automaticamente ao total de hoje ({todayWalkKm.toFixed(1).replace('.', ',')} km).
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
        </div>
    );
};

export default DashboardView;
