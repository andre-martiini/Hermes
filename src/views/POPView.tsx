import React, { useEffect, useMemo, useState } from 'react';
import { db } from '../../firebase';
import type {
    POP,
    POPLearningEvent,
    POPRun,
    POPStatus,
    POPStep,
    POPStepType,
    ApprovalMode,
    RiskLevel,
} from '../../types';
import {
    canTransitionPOPStatus,
    createPOP,
    getRecentPOPs,
    POP_APPROVAL_LABELS,
    POP_RISK_COLORS,
    POP_STATUS_COLORS,
    POP_STATUS_LABELS,
    POP_STEP_TYPE_LABELS,
    updatePOP,
    updatePOPStatus,
} from '../utils/pop';
import { getRecentPOPLearningEvents, getRecentPOPRunsForPOP } from '../utils/popRun';

interface POPViewProps {
    showToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

const EMPTY_STEP: POPStep = {
    id: '',
    ordem: 1,
    titulo: '',
    descricao: '',
    tipo: 'collect',
    obrigatorio: true,
};

const buildSlug = (value: string) =>
    value
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/(^-|-$)/g, '');

export const POPView: React.FC<POPViewProps> = ({ showToast }) => {
    const [pops, setPops] = useState<POP[]>([]);
    const [selectedPOP, setSelectedPOP] = useState<POP | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isCreating, setIsCreating] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [recentRuns, setRecentRuns] = useState<POPRun[]>([]);
    const [learningEvents, setLearningEvents] = useState<POPLearningEvent[]>([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [filterStatus, setFilterStatus] = useState<POPStatus | 'all'>('all');
    const [filterDomain, setFilterDomain] = useState('all');
    const [newStep, setNewStep] = useState<POPStep>({ ...EMPTY_STEP });
    const [editNewStep, setEditNewStep] = useState<POPStep>({ ...EMPTY_STEP });
    const [form, setForm] = useState<Partial<POP>>({
        nome: '',
        slug: '',
        descricao: '',
        dominio: '',
        status: 'draft',
        versao: 1,
        gatilhos: [],
        pre_condicoes: [],
        passos: [],
        excecoes: [],
        artefatos_gerados: [],
        criterios_validacao: [],
        risk_level: 'medium',
        approval_mode_default: 'confirm',
        tags: [],
        last_updated_by: 'user',
    });
    const [editForm, setEditForm] = useState<Partial<POP>>({});

    useEffect(() => {
        let cancelled = false;
        setIsLoading(true);
        getRecentPOPs(db, 200)
            .then(data => {
                if (!cancelled) {
                    setPops(data);
                    setIsLoading(false);
                }
            })
            .catch(() => {
                if (!cancelled) setIsLoading(false);
            });
        return () => { cancelled = true; };
    }, []);

    useEffect(() => {
        if (selectedPOP) {
            const updated = pops.find(pop => pop.id === selectedPOP.id);
            if (updated) setSelectedPOP(updated);
        }
    }, [pops, selectedPOP]);

    useEffect(() => {
        let cancelled = false;

        const loadOperationalContext = async () => {
            if (!selectedPOP) {
                if (!cancelled) {
                    setRecentRuns([]);
                    setLearningEvents([]);
                }
                return;
            }

            try {
                const [runs, events] = await Promise.all([
                    getRecentPOPRunsForPOP(db, selectedPOP.id, 8),
                    getRecentPOPLearningEvents(db, selectedPOP.id, 8),
                ]);
                if (!cancelled) {
                    setRecentRuns(runs);
                    setLearningEvents(events);
                }
            } catch {
                if (!cancelled) {
                    setRecentRuns([]);
                    setLearningEvents([]);
                }
            }
        };

        loadOperationalContext();
        return () => { cancelled = true; };
    }, [selectedPOP?.id]);

    const domains = useMemo(
        () => Array.from(new Set(pops.map(pop => pop.dominio).filter(Boolean))).sort(),
        [pops],
    );

    const filtered = useMemo(() => pops.filter(pop => {
        if (filterStatus !== 'all' && pop.status !== filterStatus) return false;
        if (filterDomain !== 'all' && pop.dominio !== filterDomain) return false;
        if (!searchTerm.trim()) return true;
        const q = searchTerm.trim().toLowerCase();
        return (
            pop.nome.toLowerCase().includes(q) ||
            pop.descricao.toLowerCase().includes(q) ||
            pop.dominio.toLowerCase().includes(q) ||
            (pop.tags ?? []).some(tag => tag.toLowerCase().includes(q))
        );
    }), [pops, filterStatus, filterDomain, searchTerm]);

    const stats = useMemo(() => {
        const by: Record<POPStatus, number> = { draft: 0, active: 0, archived: 0 };
        pops.forEach(pop => by[pop.status]++);
        return by;
    }, [pops]);

    const parseMultiline = (value: string) =>
        value
            .split('\n')
            .map(item => item.trim())
            .filter(Boolean);

    const handleCreate = async () => {
        if (!form.nome?.trim() || !form.dominio?.trim() || !(form.passos?.length)) {
            showToast('Nome, domínio e ao menos um passo são obrigatórios.', 'error');
            return;
        }
        try {
            const slug = form.slug?.trim() || buildSlug(form.nome);
            const id = await createPOP(db, {
                ...(form as Omit<POP, 'id' | 'created_at'>),
                slug,
            });
            const created: POP = {
                ...(form as POP),
                id,
                slug,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
            };
            setPops(prev => [created, ...prev]);
            setIsCreating(false);
            setForm({
                nome: '',
                slug: '',
                descricao: '',
                dominio: '',
                status: 'draft',
                versao: 1,
                gatilhos: [],
                pre_condicoes: [],
                passos: [],
                excecoes: [],
                artefatos_gerados: [],
                criterios_validacao: [],
                risk_level: 'medium',
                approval_mode_default: 'confirm',
                tags: [],
                last_updated_by: 'user',
            });
            setNewStep({ ...EMPTY_STEP });
            showToast('POP criado com sucesso.', 'success');
        } catch {
            showToast('Erro ao criar POP.', 'error');
        }
    };

    const handleSaveEdit = async () => {
        if (!selectedPOP) return;
        try {
            await updatePOP(db, selectedPOP.id, {
                ...editForm,
                versao: Math.max(selectedPOP.versao, editForm.versao ?? selectedPOP.versao),
            });
            setPops(prev => prev.map(pop => pop.id === selectedPOP.id ? {
                ...pop,
                ...editForm,
                updated_at: new Date().toISOString(),
            } : pop));
            setIsEditing(false);
            showToast('POP atualizado.', 'success');
        } catch {
            showToast('Erro ao atualizar POP.', 'error');
        }
    };

    const handleStatusChange = async (pop: POP, newStatus: POPStatus) => {
        if (!canTransitionPOPStatus(pop.status, newStatus)) return;
        try {
            await updatePOPStatus(db, pop.id, pop.status, newStatus);
            setPops(prev => prev.map(item => item.id === pop.id ? {
                ...item,
                status: newStatus,
                updated_at: new Date().toISOString(),
            } : item));
            showToast(`Status atualizado: ${POP_STATUS_LABELS[newStatus]}`, 'success');
        } catch (error: any) {
            showToast(error.message ?? 'Erro ao atualizar status.', 'error');
        }
    };

    const addStepToForm = () => {
        if (!newStep.titulo.trim() || !newStep.descricao.trim()) return;
        setForm(current => ({
            ...current,
            passos: [
                ...(current.passos ?? []),
                {
                    ...newStep,
                    id: crypto.randomUUID(),
                    ordem: (current.passos?.length ?? 0) + 1,
                },
            ],
        }));
        setNewStep({ ...EMPTY_STEP });
    };

    const addStepToEdit = () => {
        if (!editNewStep.titulo.trim() || !editNewStep.descricao.trim()) return;
        setEditForm(current => ({
            ...current,
            passos: [
                ...(current.passos ?? []),
                {
                    ...editNewStep,
                    id: crypto.randomUUID(),
                    ordem: (current.passos?.length ?? 0) + 1,
                },
            ],
        }));
        setEditNewStep({ ...EMPTY_STEP });
    };

    const applyMultilineField = (field: 'gatilhos' | 'pre_condicoes' | 'excecoes' | 'artefatos_gerados' | 'criterios_validacao' | 'tags', value: string, mode: 'create' | 'edit') => {
        const parsed = parseMultiline(value);
        if (mode === 'create') {
            setForm(current => ({ ...current, [field]: parsed }));
            return;
        }
        setEditForm(current => ({ ...current, [field]: parsed }));
    };

    const renderStepList = (steps: POPStep[] = []) => (
        <div className="space-y-2">
            {steps.length === 0 ? (
                <p className="text-xs font-semibold text-slate-400">Nenhum passo cadastrado.</p>
            ) : steps
                .sort((a, b) => a.ordem - b.ordem)
                .map(step => (
                    <div key={step.id} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Passo {step.ordem}</p>
                                <h4 className="text-sm font-black text-slate-900">{step.titulo}</h4>
                            </div>
                            <span className="rounded-full bg-white px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500 border border-slate-100">
                                {POP_STEP_TYPE_LABELS[step.tipo]}
                            </span>
                        </div>
                        <p className="mt-2 text-sm leading-relaxed text-slate-600">{step.descricao}</p>
                    </div>
                ))}
        </div>
    );

    return (
        <div className="flex h-full flex-col bg-white">
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4 shrink-0">
                <div>
                    <h2 className="text-lg font-black tracking-tight text-slate-900">POPs Adaptativos</h2>
                    <p className="mt-0.5 text-xs font-semibold text-slate-400">{pops.length} POPs · {stats.active} ativos · {stats.draft} rascunhos</p>
                </div>
                <button
                    onClick={() => setIsCreating(true)}
                    className="rounded-xl bg-slate-900 px-4 py-2.5 text-[10px] font-black uppercase tracking-widest text-white shadow-sm transition-all hover:bg-slate-700"
                >
                    Novo POP
                </button>
            </div>

            <div className="flex gap-3 overflow-x-auto border-b border-slate-50 px-6 py-3 shrink-0">
                {(Object.keys(POP_STATUS_LABELS) as POPStatus[]).map(status => (
                    <button
                        key={status}
                        onClick={() => setFilterStatus(filterStatus === status ? 'all' : status)}
                        className={`shrink-0 rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-widest transition-all ${filterStatus === status ? `${POP_STATUS_COLORS[status]} border-current` : 'border-slate-100 bg-white text-slate-400 hover:border-slate-200'}`}
                    >
                        {stats[status]} · {POP_STATUS_LABELS[status]}
                    </button>
                ))}
            </div>

            <div className="flex flex-wrap gap-2 border-b border-slate-50 px-6 py-3 shrink-0">
                <input
                    type="text"
                    placeholder="Buscar POP..."
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                    className="min-w-[180px] flex-1 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300"
                />
                <select
                    value={filterDomain}
                    onChange={e => setFilterDomain(e.target.value)}
                    className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-[10px] font-black uppercase tracking-widest text-slate-600 focus:outline-none"
                >
                    <option value="all">Todos os domínios</option>
                    {domains.map(domain => <option key={domain} value={domain}>{domain}</option>)}
                </select>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4" style={{ scrollbarWidth: 'thin' }}>
                {isLoading ? (
                    <div className="py-20 text-center text-sm font-semibold text-slate-400">Carregando...</div>
                ) : filtered.length === 0 ? (
                    <div className="py-20 text-center text-sm font-semibold text-slate-400">Nenhum POP encontrado.</div>
                ) : filtered.map(pop => (
                    <button
                        key={pop.id}
                        onClick={() => {
                            setSelectedPOP(pop);
                            setEditForm(pop);
                            setEditNewStep({ ...EMPTY_STEP });
                            setIsEditing(false);
                        }}
                        className="w-full rounded-[1.75rem] border border-slate-100 bg-white p-5 text-left shadow-sm transition-all hover:border-slate-200 hover:shadow-md"
                    >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                    <h3 className="text-base font-black tracking-tight text-slate-900">{pop.nome}</h3>
                                    <span className={`rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-widest ${POP_STATUS_COLORS[pop.status]}`}>
                                        {POP_STATUS_LABELS[pop.status]}
                                    </span>
                                    <span className={`rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-widest ${POP_RISK_COLORS[pop.risk_level]}`}>
                                        {pop.risk_level}
                                    </span>
                                </div>
                                <p className="mt-2 text-sm leading-relaxed text-slate-600">{pop.descricao}</p>
                            </div>
                            <div className="text-right">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{pop.dominio}</p>
                                <p className="mt-1 text-xs font-semibold text-slate-500">v{pop.versao} · {POP_APPROVAL_LABELS[pop.approval_mode_default]}</p>
                            </div>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2">
                            {(pop.tags ?? []).slice(0, 4).map(tag => (
                                <span key={tag} className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500">
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </button>
                ))}
            </div>

            {selectedPOP && (
                <div className="fixed inset-0 z-[210] flex justify-end bg-slate-900/40 backdrop-blur-sm">
                    <div className="h-full w-full max-w-3xl overflow-y-auto bg-white shadow-2xl">
                        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Procedimento Operacional</p>
                                <h3 className="text-xl font-black tracking-tight text-slate-900">{selectedPOP.nome}</h3>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => {
                                        setIsEditing(!isEditing);
                                        setEditForm(selectedPOP);
                                    }}
                                    className="rounded-xl border border-slate-200 px-3 py-2 text-[10px] font-black uppercase tracking-widest text-slate-600"
                                >
                                    {isEditing ? 'Cancelar edição' : 'Editar'}
                                </button>
                                <button
                                    onClick={() => setSelectedPOP(null)}
                                    className="rounded-full p-2 text-slate-500 transition-colors hover:bg-slate-100"
                                >
                                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                                </button>
                            </div>
                        </div>

                        <div className="space-y-6 px-6 py-6">
                            <div className="flex flex-wrap gap-2">
                                <span className={`rounded-full px-3 py-1.5 text-[10px] font-black uppercase tracking-widest ${POP_STATUS_COLORS[selectedPOP.status]}`}>
                                    {POP_STATUS_LABELS[selectedPOP.status]}
                                </span>
                                <span className={`rounded-full px-3 py-1.5 text-[10px] font-black uppercase tracking-widest ${POP_RISK_COLORS[selectedPOP.risk_level]}`}>
                                    Risco {selectedPOP.risk_level}
                                </span>
                                <span className="rounded-full bg-slate-100 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-slate-500">
                                    {POP_APPROVAL_LABELS[selectedPOP.approval_mode_default]}
                                </span>
                            </div>

                            {!isEditing ? (
                                <>
                                    <div className="grid gap-4 md:grid-cols-2">
                                        <div className="rounded-[1.5rem] border border-slate-100 bg-slate-50 p-5">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Domínio</p>
                                            <p className="mt-2 text-sm font-bold text-slate-800">{selectedPOP.dominio}</p>
                                            {selectedPOP.subdominio && <p className="mt-1 text-xs font-semibold text-slate-500">{selectedPOP.subdominio}</p>}
                                        </div>
                                        <div className="rounded-[1.5rem] border border-slate-100 bg-slate-50 p-5">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Versão</p>
                                            <p className="mt-2 text-sm font-bold text-slate-800">v{selectedPOP.versao}</p>
                                            <p className="mt-1 text-xs font-semibold text-slate-500">Atualizado em {selectedPOP.updated_at || selectedPOP.created_at}</p>
                                        </div>
                                    </div>

                                    <div className="rounded-[1.5rem] border border-slate-100 bg-white p-5">
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Descrição</p>
                                        <p className="mt-2 text-sm leading-relaxed text-slate-700">{selectedPOP.descricao}</p>
                                    </div>

                                    <div className="grid gap-4 md:grid-cols-2">
                                        <div className="rounded-[1.5rem] border border-slate-100 bg-white p-5">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Gatilhos</p>
                                            <div className="mt-3 space-y-2">
                                                {selectedPOP.gatilhos.length === 0 ? <p className="text-xs font-semibold text-slate-400">Sem gatilhos definidos.</p> : selectedPOP.gatilhos.map(item => <p key={item} className="text-sm text-slate-700">• {item}</p>)}
                                            </div>
                                        </div>
                                        <div className="rounded-[1.5rem] border border-slate-100 bg-white p-5">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Pré-condições</p>
                                            <div className="mt-3 space-y-2">
                                                {selectedPOP.pre_condicoes.length === 0 ? <p className="text-xs font-semibold text-slate-400">Sem pré-condições definidas.</p> : selectedPOP.pre_condicoes.map(item => <p key={item} className="text-sm text-slate-700">• {item}</p>)}
                                            </div>
                                        </div>
                                    </div>

                                    <div className="rounded-[1.5rem] border border-slate-100 bg-white p-5">
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Passos</p>
                                        <div className="mt-3">{renderStepList(selectedPOP.passos)}</div>
                                    </div>

                                    <div className="grid gap-4 md:grid-cols-3">
                                        {([
                                            ['Exceções', selectedPOP.excecoes],
                                            ['Artefatos gerados', selectedPOP.artefatos_gerados],
                                            ['Critérios de validação', selectedPOP.criterios_validacao],
                                        ] as const).map(([title, items]) => (
                                            <div key={title} className="rounded-[1.5rem] border border-slate-100 bg-white p-5">
                                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{title}</p>
                                                <div className="mt-3 space-y-2">
                                                    {items.length === 0 ? <p className="text-xs font-semibold text-slate-400">Nenhum item.</p> : items.map(item => <p key={item} className="text-sm text-slate-700">• {item}</p>)}
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    <div className="grid gap-4 md:grid-cols-2">
                                        <div className="rounded-[1.5rem] border border-slate-100 bg-white p-5">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Execuções Recentes</p>
                                            <div className="mt-3 space-y-2">
                                                {recentRuns.length === 0 ? (
                                                    <p className="text-xs font-semibold text-slate-400">Nenhuma execução recente.</p>
                                                ) : recentRuns.map(run => (
                                                    <div key={run.id} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
                                                        <div className="flex items-center justify-between gap-3">
                                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{run.caso_origem_tipo}</p>
                                                            <span className="rounded-full bg-white px-2 py-1 text-[9px] font-black uppercase tracking-widest text-slate-600 border border-slate-100">{run.status}</span>
                                                        </div>
                                                        <p className="mt-2 text-xs font-semibold text-slate-700">{run.caso_origem_id}</p>
                                                        <p className="mt-1 text-[11px] text-slate-400">{run.created_at}</p>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>

                                        <div className="rounded-[1.5rem] border border-slate-100 bg-white p-5">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Correções Recentes</p>
                                            <div className="mt-3 space-y-2">
                                                {learningEvents.length === 0 ? (
                                                    <p className="text-xs font-semibold text-slate-400">Nenhum aprendizado registrado.</p>
                                                ) : learningEvents.map(event => (
                                                    <div key={event.id} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
                                                        <div className="flex items-center justify-between gap-3">
                                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{event.tipo}</p>
                                                            <span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase tracking-widest ${event.review_status === 'pending' ? 'bg-amber-100 text-amber-700' : event.review_status === 'accepted' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                                                                {event.review_status}
                                                            </span>
                                                        </div>
                                                        <p className="mt-2 text-xs leading-relaxed text-slate-700">{event.descricao}</p>
                                                        <p className="mt-1 text-[11px] text-slate-400">{event.created_at}</p>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </div>

                                    <div className="flex flex-wrap gap-2 pt-2">
                                        {(Object.keys(POP_STATUS_LABELS) as POPStatus[])
                                            .filter(status => status !== selectedPOP.status && canTransitionPOPStatus(selectedPOP.status, status))
                                            .map(status => (
                                                <button
                                                    key={status}
                                                    onClick={() => handleStatusChange(selectedPOP, status)}
                                                    className="rounded-xl border border-slate-200 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-600 transition-all hover:border-slate-300"
                                                >
                                                    Marcar como {POP_STATUS_LABELS[status]}
                                                </button>
                                            ))}
                                    </div>
                                </>
                            ) : (
                                <div className="space-y-5">
                                    <div className="grid gap-4 md:grid-cols-2">
                                        <label className="space-y-2">
                                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Nome</span>
                                            <input value={editForm.nome ?? ''} onChange={e => setEditForm(current => ({ ...current, nome: e.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                        </label>
                                        <label className="space-y-2">
                                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Slug</span>
                                            <input value={editForm.slug ?? ''} onChange={e => setEditForm(current => ({ ...current, slug: e.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                        </label>
                                        <label className="space-y-2">
                                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Domínio</span>
                                            <input value={editForm.dominio ?? ''} onChange={e => setEditForm(current => ({ ...current, dominio: e.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                        </label>
                                        <label className="space-y-2">
                                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Versão</span>
                                            <input type="number" min={1} value={editForm.versao ?? 1} onChange={e => setEditForm(current => ({ ...current, versao: Number(e.target.value) }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                        </label>
                                    </div>

                                    <label className="block space-y-2">
                                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Descrição</span>
                                        <textarea value={editForm.descricao ?? ''} onChange={e => setEditForm(current => ({ ...current, descricao: e.target.value }))} rows={4} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 focus:outline-none" />
                                    </label>

                                    <div className="grid gap-4 md:grid-cols-2">
                                        <label className="space-y-2">
                                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Risco padrão</span>
                                            <select value={editForm.risk_level ?? 'medium'} onChange={e => setEditForm(current => ({ ...current, risk_level: e.target.value as RiskLevel }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none">
                                                <option value="low">low</option>
                                                <option value="medium">medium</option>
                                                <option value="high">high</option>
                                            </select>
                                        </label>
                                        <label className="space-y-2">
                                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Aprovação padrão</span>
                                            <select value={editForm.approval_mode_default ?? 'confirm'} onChange={e => setEditForm(current => ({ ...current, approval_mode_default: e.target.value as ApprovalMode }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none">
                                                <option value="automatic">automatic</option>
                                                <option value="confirm">confirm</option>
                                                <option value="required">required</option>
                                            </select>
                                        </label>
                                    </div>

                                    <div className="grid gap-4 md:grid-cols-2">
                                        {([
                                            ['gatilhos', 'Gatilhos'],
                                            ['pre_condicoes', 'Pré-condições'],
                                            ['excecoes', 'Exceções'],
                                            ['artefatos_gerados', 'Artefatos gerados'],
                                            ['criterios_validacao', 'Critérios de validação'],
                                            ['tags', 'Tags'],
                                        ] as const).map(([field, label]) => (
                                            <label key={field} className="space-y-2">
                                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</span>
                                                <textarea
                                                    defaultValue={(editForm[field] as string[] | undefined)?.join('\n') ?? ''}
                                                    onBlur={e => applyMultilineField(field, e.target.value, 'edit')}
                                                    rows={4}
                                                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 focus:outline-none"
                                                />
                                            </label>
                                        ))}
                                    </div>

                                    <div className="rounded-[1.5rem] border border-slate-100 bg-white p-5">
                                        <div className="flex items-center justify-between">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Passos</p>
                                            <button onClick={addStepToEdit} className="rounded-lg border border-slate-200 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-slate-600">Adicionar passo</button>
                                        </div>
                                        <div className="mt-4 grid gap-3 md:grid-cols-2">
                                            <input placeholder="Título do passo" value={editNewStep.titulo} onChange={e => setEditNewStep(current => ({ ...current, titulo: e.target.value }))} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                            <select value={editNewStep.tipo} onChange={e => setEditNewStep(current => ({ ...current, tipo: e.target.value as POPStepType }))} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none">
                                                {(Object.keys(POP_STEP_TYPE_LABELS) as POPStepType[]).map(type => <option key={type} value={type}>{POP_STEP_TYPE_LABELS[type]}</option>)}
                                            </select>
                                        </div>
                                        <textarea placeholder="Descrição do passo" value={editNewStep.descricao} onChange={e => setEditNewStep(current => ({ ...current, descricao: e.target.value }))} rows={3} className="mt-3 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 focus:outline-none" />
                                        <div className="mt-4">{renderStepList((editForm.passos as POPStep[]) ?? [])}</div>
                                    </div>

                                    <div className="flex justify-end gap-2">
                                        <button onClick={() => setIsEditing(false)} className="rounded-xl border border-slate-200 px-4 py-2.5 text-[10px] font-black uppercase tracking-widest text-slate-600">Cancelar</button>
                                        <button onClick={handleSaveEdit} className="rounded-xl bg-slate-900 px-4 py-2.5 text-[10px] font-black uppercase tracking-widest text-white">Salvar</button>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {isCreating && (
                <div className="fixed inset-0 z-[220] flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
                    <div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-[2rem] bg-white shadow-2xl">
                        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Novo Procedimento</p>
                                <h3 className="text-xl font-black tracking-tight text-slate-900">Criar POP</h3>
                            </div>
                            <button onClick={() => setIsCreating(false)} className="rounded-full p-2 text-slate-500 transition-colors hover:bg-slate-100">
                                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                        <div className="space-y-5 px-6 py-6">
                            <div className="grid gap-4 md:grid-cols-2">
                                <label className="space-y-2">
                                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Nome</span>
                                    <input value={form.nome ?? ''} onChange={e => setForm(current => ({ ...current, nome: e.target.value, slug: buildSlug(e.target.value) }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                </label>
                                <label className="space-y-2">
                                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Slug</span>
                                    <input value={form.slug ?? ''} onChange={e => setForm(current => ({ ...current, slug: e.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                </label>
                                <label className="space-y-2">
                                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Domínio</span>
                                    <input value={form.dominio ?? ''} onChange={e => setForm(current => ({ ...current, dominio: e.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                </label>
                                <label className="space-y-2">
                                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Subdomínio</span>
                                    <input value={form.subdominio ?? ''} onChange={e => setForm(current => ({ ...current, subdominio: e.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                </label>
                            </div>

                            <label className="block space-y-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Descrição</span>
                                <textarea value={form.descricao ?? ''} onChange={e => setForm(current => ({ ...current, descricao: e.target.value }))} rows={4} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 focus:outline-none" />
                            </label>

                            <div className="grid gap-4 md:grid-cols-2">
                                <label className="space-y-2">
                                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Risco padrão</span>
                                    <select value={form.risk_level ?? 'medium'} onChange={e => setForm(current => ({ ...current, risk_level: e.target.value as RiskLevel }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none">
                                        <option value="low">low</option>
                                        <option value="medium">medium</option>
                                        <option value="high">high</option>
                                    </select>
                                </label>
                                <label className="space-y-2">
                                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Aprovação padrão</span>
                                    <select value={form.approval_mode_default ?? 'confirm'} onChange={e => setForm(current => ({ ...current, approval_mode_default: e.target.value as ApprovalMode }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none">
                                        <option value="automatic">automatic</option>
                                        <option value="confirm">confirm</option>
                                        <option value="required">required</option>
                                    </select>
                                </label>
                            </div>

                            <div className="grid gap-4 md:grid-cols-2">
                                {([
                                    ['gatilhos', 'Gatilhos'],
                                    ['pre_condicoes', 'Pré-condições'],
                                    ['excecoes', 'Exceções'],
                                    ['artefatos_gerados', 'Artefatos gerados'],
                                    ['criterios_validacao', 'Critérios de validação'],
                                    ['tags', 'Tags'],
                                ] as const).map(([field, label]) => (
                                    <label key={field} className="space-y-2">
                                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</span>
                                        <textarea
                                            onBlur={e => applyMultilineField(field, e.target.value, 'create')}
                                            rows={4}
                                            className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 focus:outline-none"
                                        />
                                    </label>
                                ))}
                            </div>

                            <div className="rounded-[1.5rem] border border-slate-100 bg-white p-5">
                                <div className="flex items-center justify-between">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Passos</p>
                                    <button onClick={addStepToForm} className="rounded-lg border border-slate-200 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-slate-600">Adicionar passo</button>
                                </div>
                                <div className="mt-4 grid gap-3 md:grid-cols-2">
                                    <input placeholder="Título do passo" value={newStep.titulo} onChange={e => setNewStep(current => ({ ...current, titulo: e.target.value }))} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none" />
                                    <select value={newStep.tipo} onChange={e => setNewStep(current => ({ ...current, tipo: e.target.value as POPStepType }))} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none">
                                        {(Object.keys(POP_STEP_TYPE_LABELS) as POPStepType[]).map(type => <option key={type} value={type}>{POP_STEP_TYPE_LABELS[type]}</option>)}
                                    </select>
                                </div>
                                <textarea placeholder="Descrição do passo" value={newStep.descricao} onChange={e => setNewStep(current => ({ ...current, descricao: e.target.value }))} rows={3} className="mt-3 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 focus:outline-none" />
                                <div className="mt-4">{renderStepList((form.passos as POPStep[]) ?? [])}</div>
                            </div>

                            <div className="flex justify-end gap-2">
                                <button onClick={() => setIsCreating(false)} className="rounded-xl border border-slate-200 px-4 py-2.5 text-[10px] font-black uppercase tracking-widest text-slate-600">Cancelar</button>
                                <button onClick={handleCreate} className="rounded-xl bg-slate-900 px-4 py-2.5 text-[10px] font-black uppercase tracking-widest text-white">Criar POP</button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
