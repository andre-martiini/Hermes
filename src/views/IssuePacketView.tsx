/**
 * IssuePacketView.tsx
 *
 * Fase 5 — Propostas Técnicas Revisáveis (Issue Packets).
 * Lists, creates, and manages IssuePacket documents.
 *
 * Features:
 * - Filter by status, tipo, severidade
 * - Create packet manually (form)
 * - Detail slide-over: summary, affected files, proposed changes (markdown),
 *   rationale, routing assessment, approval controls
 * - Status workflow enforcement via canTransition()
 */

import React, { useState, useEffect, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { db } from '../../firebase';
import {
    IssuePacket,
    IssuePacketStatus,
    IssuePacketTipo,
    IssuePacketSeveridade,
    AffectedFile,
    POPLearningEvent,
    POPRun,
    POPStepRun,
    POP,
    Sistema,
} from '../../types';
import {
    createIssuePacket,
    updateIssuePacketStatus,
    updateIssuePacket,
    getRecentIssuePackets,
    canTransition,
    TIPO_LABELS,
    SEVERIDADE_LABELS,
    STATUS_LABELS,
    SEVERIDADE_COLORS,
    TIPO_COLORS,
    STATUS_COLORS,
} from '../utils/issuePacket';
import { getRecentPOPs } from '../utils/pop';
import { buildPOPRationale, rankPOPsForCase } from '../utils/popMatching';
import { applyPOPStepResolution, canTransitionPOPRunStatus, createPOPLearningEvent, createPOPRunFromPOP, getPOPRunById, getRecentPOPLearningEvents, updatePOPRunStatus } from '../utils/popRun';

// ── Props ─────────────────────────────────────────────────────────────────────

interface IssuePacketViewProps {
    sistemas: Sistema[];
    showToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const CHANGE_TYPE_ICON: Record<AffectedFile['change_type'], React.ReactNode> = {
    modified: <span className="text-amber-500 font-black text-[10px]">M</span>,
    added:    <span className="text-emerald-500 font-black text-[10px]">A</span>,
    deleted:  <span className="text-rose-500 font-black text-[10px]">D</span>,
};

const EMPTY_FILE: AffectedFile = { path: '', change_type: 'modified', summary: '' };

const formatSistemaName = (sistema?: Pick<Sistema, 'id' | 'nome'> | null): string => {
    const rawName = typeof sistema?.nome === 'string' && sistema.nome.trim()
        ? sistema.nome
        : sistema?.id || 'Sistema sem nome';
    return String(rawName ?? 'Sistema sem nome').replace('SISTEMA:', '').trim();
};

// ── Component ─────────────────────────────────────────────────────────────────

export const IssuePacketView: React.FC<IssuePacketViewProps> = ({ sistemas, showToast }) => {
    const [packets, setPackets] = useState<IssuePacket[]>([]);
    const [pops, setPops] = useState<POP[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [selectedPacket, setSelectedPacket] = useState<IssuePacket | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [reviewNote, setReviewNote] = useState('');
    const [isEditing, setIsEditing] = useState(false);
    const [currentPOPRun, setCurrentPOPRun] = useState<POPRun | null>(null);
    const [learningEvents, setLearningEvents] = useState<POPLearningEvent[]>([]);
    const [learningDraft, setLearningDraft] = useState('');
    const [isCreatingPOPRun, setIsCreatingPOPRun] = useState(false);
    const [isSavingLearning, setIsSavingLearning] = useState(false);
    const [popRunApprovalGranted, setPopRunApprovalGranted] = useState(false);

    // Filters
    const [filterStatus, setFilterStatus] = useState<IssuePacketStatus | 'all'>('all');
    const [filterTipo, setFilterTipo] = useState<IssuePacketTipo | 'all'>('all');
    const [filterSeveridade, setFilterSeveridade] = useState<IssuePacketSeveridade | 'all'>('all');
    const [filterSistema, setFilterSistema] = useState<string>('all');
    const [searchTerm, setSearchTerm] = useState('');

    // Create form
    const [form, setForm] = useState<Partial<IssuePacket>>({
        titulo: '',
        descricao: '',
        tipo: 'bug',
        severidade: 'media',
        proposed_changes: '',
        rationale: '',
        affected_files: [],
        status: 'draft',
        created_by: 'user',
    });
    const [newFile, setNewFile] = useState<AffectedFile>({ ...EMPTY_FILE });

    // Edit form (for selected packet)
    const [editForm, setEditForm] = useState<Partial<IssuePacket>>({});
    const [editNewFile, setEditNewFile] = useState<AffectedFile>({ ...EMPTY_FILE });

    useEffect(() => {
        let cancelled = false;
        setIsLoading(true);
        getRecentIssuePackets(db, 200)
            .then(data => { if (!cancelled) { setPackets(data); setIsLoading(false); } })
            .catch(() => { if (!cancelled) setIsLoading(false); });
        return () => { cancelled = true; };
    }, []);

    useEffect(() => {
        let cancelled = false;
        getRecentPOPs(db, 200)
            .then(data => {
                if (!cancelled) {
                    setPops(data.filter(pop => pop.status === 'active' || pop.status === 'draft'));
                }
            })
            .catch(() => undefined);
        return () => { cancelled = true; };
    }, []);

    // Sync selectedPacket with latest data after mutations
    useEffect(() => {
        if (selectedPacket) {
            const updated = packets.find(p => p.id === selectedPacket.id);
            if (updated) setSelectedPacket(updated);
        }
    }, [packets]);

    useEffect(() => {
        setPopRunApprovalGranted(false);
    }, [selectedPacket?.id]);

    useEffect(() => {
        let cancelled = false;

        const loadRunContext = async () => {
            if (!selectedPacket?.pop_run_id || !selectedPacket?.suggested_pop_id) {
                if (!cancelled) {
                    setCurrentPOPRun(null);
                    setLearningEvents([]);
                }
                return;
            }

            try {
                const [run, events] = await Promise.all([
                    getPOPRunById(db, selectedPacket.pop_run_id),
                    getRecentPOPLearningEvents(db, selectedPacket.suggested_pop_id, 12),
                ]);
                if (!cancelled) {
                    setCurrentPOPRun(run);
                    setLearningEvents(events);
                }
            } catch {
                if (!cancelled) {
                    setCurrentPOPRun(null);
                    setLearningEvents([]);
                }
            }
        };

        loadRunContext();
        return () => { cancelled = true; };
    }, [selectedPacket?.pop_run_id, selectedPacket?.suggested_pop_id]);

    const filtered = useMemo(() => packets.filter(p => {
        if (filterStatus !== 'all' && p.status !== filterStatus) return false;
        if (filterTipo !== 'all' && p.tipo !== filterTipo) return false;
        if (filterSeveridade !== 'all' && p.severidade !== filterSeveridade) return false;
        if (filterSistema !== 'all' && p.sistema_id !== filterSistema) return false;
        if (searchTerm) {
            const q = searchTerm.toLowerCase();
            return p.titulo.toLowerCase().includes(q) || p.descricao.toLowerCase().includes(q);
        }
        return true;
    }), [packets, filterStatus, filterTipo, filterSeveridade, filterSistema, searchTerm]);

    const getSistemaName = (sistemaId: string) =>
        formatSistemaName(sistemas.find(s => s.id === sistemaId) ?? { id: sistemaId, nome: sistemaId });

    const suggestedPOP = useMemo(() => {
        const ranked = rankPOPsForCase(pops, {
            dominio: 'sistemas_e_codigo',
            routing_assessment: form.routing_assessment,
            intake_record: form.intake_record,
            tags: [form.tipo, form.severidade].filter(Boolean) as string[],
            expectedArtifacts: ['issue packet'],
            text: `${form.titulo ?? ''} ${form.descricao ?? ''} ${form.rationale ?? ''}`,
        });
        return ranked[0] ?? null;
    }, [pops, form]);

    // ── Handlers ───────────────────────────────────────────────────────────────

    const handleCreate = async () => {
        if (!form.titulo?.trim() || !form.sistema_id) {
            showToast('Título e sistema são obrigatórios.', 'error');
            return;
        }
        try {
            const packetPayload = {
                ...form,
                suggested_pop_id: form.suggested_pop_id ?? suggestedPOP?.pop.id,
            } as Omit<IssuePacket, 'id' | 'created_at'>;
            const id = await createIssuePacket(db, packetPayload);
            const created: IssuePacket = {
                ...packetPayload,
                id,
                created_at: new Date().toISOString(),
                affected_files: packetPayload.affected_files ?? [],
            } as IssuePacket;
            setPackets(prev => [created, ...prev]);
            setIsCreating(false);
            setForm({ titulo: '', descricao: '', tipo: 'bug', severidade: 'media', proposed_changes: '', rationale: '', affected_files: [], status: 'draft', created_by: 'user' });
            showToast('Proposta técnica criada.', 'success');
        } catch (e) {
            showToast('Erro ao criar proposta.', 'error');
        }
    };

    const handleStatusChange = async (packet: IssuePacket, newStatus: IssuePacketStatus) => {
        if (!canTransition(packet.status, newStatus)) return;
        try {
            await updateIssuePacketStatus(db, packet.id, packet.status, newStatus, { reviewer: 'user', reviewNote });
            setPackets(prev => prev.map(p => p.id === packet.id
                ? { ...p, status: newStatus, reviewed_by: 'user', reviewed_at: new Date().toISOString(), review_note: reviewNote }
                : p));
            setReviewNote('');
            showToast(`Status atualizado: ${STATUS_LABELS[newStatus]}`, 'success');
        } catch (e: any) {
            showToast(e.message ?? 'Erro ao atualizar status.', 'error');
        }
    };

    const handleSaveEdit = async () => {
        if (!selectedPacket) return;
        try {
            await updateIssuePacket(db, selectedPacket.id, editForm);
            setPackets(prev => prev.map(p => p.id === selectedPacket.id ? { ...p, ...editForm } : p));
            setIsEditing(false);
            showToast('Proposta atualizada.', 'success');
        } catch {
            showToast('Erro ao salvar alterações.', 'error');
        }
    };

    const addFileToForm = () => {
        if (!newFile.path.trim()) return;
        setForm(f => ({ ...f, affected_files: [...(f.affected_files ?? []), { ...newFile }] }));
        setNewFile({ ...EMPTY_FILE });
    };

    const addFileToEdit = () => {
        if (!editNewFile.path.trim()) return;
        setEditForm(f => ({ ...f, affected_files: [...(f.affected_files ?? []), { ...editNewFile }] }));
        setEditNewFile({ ...EMPTY_FILE });
    };

    const handleCreatePOPRun = async (packet: IssuePacket) => {
        const linkedPOP = pops.find(pop => pop.id === packet.suggested_pop_id);
        if (!linkedPOP) {
            showToast('Nenhum POP sugerido disponível para esta proposta.', 'error');
            return;
        }
        if (packet.pop_run_id) {
            showToast('Esta proposta já possui execução de POP vinculada.', 'info');
            return;
        }
        setIsCreatingPOPRun(true);
        try {
            const popRunId = await createPOPRunFromPOP(db, {
                pop: linkedPOP,
                caso_origem_tipo: 'issue_packet',
                caso_origem_id: packet.id,
                assessment: packet.routing_assessment,
                input_refs: packet.intake_record?.source_refs,
            });
            await updateIssuePacket(db, packet.id, {
                suggested_pop_id: linkedPOP.id,
                pop_run_id: popRunId,
            } as Partial<IssuePacket>);
            setPackets(prev => prev.map(item => item.id === packet.id ? { ...item, suggested_pop_id: linkedPOP.id, pop_run_id: popRunId } : item));
            showToast('Execução do POP criada para a proposta.', 'success');
        } catch {
            showToast('Erro ao criar execução do POP.', 'error');
        } finally {
            setIsCreatingPOPRun(false);
        }
    };

    const handleTogglePOPRunStep = async (stepId: string) => {
        if (!currentPOPRun) return;
        const updatedSteps = currentPOPRun.steps_resolved.map((step: POPStepRun) =>
            step.step_id === stepId
                ? { ...step, status: step.status === 'completed' ? 'pending' : 'completed' }
                : step,
        );
        try {
            await applyPOPStepResolution(db, currentPOPRun.id, updatedSteps);
            setCurrentPOPRun({
                ...currentPOPRun,
                steps_resolved: updatedSteps,
                updated_at: new Date().toISOString(),
            });
            showToast('Passo do procedimento atualizado.', 'success');
        } catch {
            showToast('Erro ao atualizar o passo do procedimento.', 'error');
        }
    };

    const handleCreateLearningEvent = async () => {
        if (!selectedPacket?.suggested_pop_id || !learningDraft.trim()) return;
        setIsSavingLearning(true);
        try {
            const eventId = await createPOPLearningEvent(db, selectedPacket.suggested_pop_id, {
                pop_run_id: selectedPacket.pop_run_id,
                tipo: 'step_adjusted',
                descricao: learningDraft.trim(),
                impacto: selectedPacket.routing_assessment?.risk_level || 'medium',
                review_status: 'pending',
            });
            const created: POPLearningEvent = {
                id: eventId,
                pop_id: selectedPacket.suggested_pop_id,
                pop_run_id: selectedPacket.pop_run_id,
                tipo: 'step_adjusted',
                descricao: learningDraft.trim(),
                impacto: selectedPacket.routing_assessment?.risk_level || 'medium',
                review_status: 'pending',
                created_at: new Date().toISOString(),
            };
            setLearningEvents(prev => [created, ...prev]);
            setLearningDraft('');
            showToast('Aprendizado registrado para revisão.', 'success');
        } catch {
            showToast('Erro ao registrar aprendizado.', 'error');
        } finally {
            setIsSavingLearning(false);
        }
    };

    const guardPOPRunApproval = (targetStatus: POPRun['status']) => {
        if (!selectedPacket?.routing_assessment) return true;
        if (targetStatus !== 'approved' && targetStatus !== 'applied') return true;
        if (selectedPacket.routing_assessment.approval_mode === 'automatic') return true;
        if (popRunApprovalGranted) return true;
        showToast(
            selectedPacket.routing_assessment.approval_mode === 'required'
                ? 'Esta transição do procedimento exige liberação explícita.'
                : 'Confirme a execução do procedimento antes de aprovar ou aplicar.',
            'info',
        );
        return false;
    };

    const handlePOPRunStatusChange = async (newStatus: POPRun['status']) => {
        if (!currentPOPRun) return;
        if (!canTransitionPOPRunStatus(currentPOPRun.status, newStatus)) return;
        if (!guardPOPRunApproval(newStatus)) return;
        try {
            await updatePOPRunStatus(db, currentPOPRun.id, currentPOPRun.status, newStatus);
            setCurrentPOPRun({
                ...currentPOPRun,
                status: newStatus,
                updated_at: new Date().toISOString(),
            });
            showToast(`Execução do POP atualizada para ${newStatus}.`, 'success');
        } catch (error: any) {
            showToast(error.message ?? 'Erro ao atualizar status do procedimento.', 'error');
        }
    };

    // ── Summary stats ─────────────────────────────────────────────────────────

    const stats = useMemo(() => {
        const by: Record<IssuePacketStatus, number> = { draft: 0, review: 0, approved: 0, rejected: 0, applied: 0 };
        packets.forEach(p => by[p.status]++);
        return by;
    }, [packets]);

    // ── Render ────────────────────────────────────────────────────────────────

    return (
        <div className="flex flex-col h-full bg-white">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 shrink-0">
                <div>
                    <h2 className="text-lg font-black text-slate-900 tracking-tight">Propostas Técnicas</h2>
                    <p className="text-xs text-slate-400 font-semibold mt-0.5">{packets.length} packet{packets.length !== 1 ? 's' : ''} · {stats.review} em revisão · {stats.approved} aprovado{stats.approved !== 1 ? 's' : ''}</p>
                </div>
                <button
                    onClick={() => setIsCreating(true)}
                    className="flex items-center gap-2 px-4 py-2.5 bg-slate-900 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-700 transition-all shadow-sm"
                >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                    Nova Proposta
                </button>
            </div>

            {/* Summary strip */}
            <div className="flex gap-3 px-6 py-3 border-b border-slate-50 overflow-x-auto shrink-0">
                {(Object.keys(STATUS_LABELS) as IssuePacketStatus[]).map(s => (
                    <button
                        key={s}
                        onClick={() => setFilterStatus(filterStatus === s ? 'all' : s)}
                        className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border ${filterStatus === s ? STATUS_COLORS[s] + ' border-current' : 'bg-white text-slate-400 border-slate-100 hover:border-slate-200'}`}
                    >
                        <span>{stats[s]}</span>
                        <span>{STATUS_LABELS[s]}</span>
                    </button>
                ))}
            </div>

            {/* Filter bar */}
            <div className="flex flex-wrap gap-2 px-6 py-3 border-b border-slate-50 shrink-0">
                <input
                    type="text"
                    placeholder="Buscar…"
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                    className="flex-1 min-w-[160px] text-xs font-semibold text-slate-700 bg-slate-50 border border-slate-100 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-300"
                />
                <select value={filterSistema} onChange={e => setFilterSistema(e.target.value)} className="text-[10px] font-black uppercase tracking-widest text-slate-600 bg-slate-50 border border-slate-100 rounded-xl px-3 py-2 focus:outline-none">
                    <option value="all">Todos os sistemas</option>
                    {sistemas.map(s => <option key={s.id} value={s.id}>{formatSistemaName(s)}</option>)}
                </select>
                <select value={filterTipo} onChange={e => setFilterTipo(e.target.value as any)} className="text-[10px] font-black uppercase tracking-widest text-slate-600 bg-slate-50 border border-slate-100 rounded-xl px-3 py-2 focus:outline-none">
                    <option value="all">Todos os tipos</option>
                    {(Object.keys(TIPO_LABELS) as IssuePacketTipo[]).map(t => <option key={t} value={t}>{TIPO_LABELS[t]}</option>)}
                </select>
                <select value={filterSeveridade} onChange={e => setFilterSeveridade(e.target.value as any)} className="text-[10px] font-black uppercase tracking-widest text-slate-600 bg-slate-50 border border-slate-100 rounded-xl px-3 py-2 focus:outline-none">
                    <option value="all">Todas as severidades</option>
                    {(Object.keys(SEVERIDADE_LABELS) as IssuePacketSeveridade[]).map(s => <option key={s} value={s}>{SEVERIDADE_LABELS[s]}</option>)}
                </select>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3" style={{ scrollbarWidth: 'thin' }}>
                {isLoading ? (
                    <div className="flex items-center justify-center py-20 text-slate-400 text-sm font-semibold">Carregando…</div>
                ) : filtered.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 gap-3 opacity-40">
                        <svg className="w-10 h-10 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                        <p className="text-sm font-bold text-slate-400">Nenhuma proposta encontrada.</p>
                    </div>
                ) : filtered.map(packet => (
                    <button
                        key={packet.id}
                        onClick={() => { setSelectedPacket(packet); setIsEditing(false); setReviewNote(''); }}
                        className="w-full text-left bg-white border border-slate-100 rounded-2xl p-4 hover:border-slate-300 hover:shadow-sm transition-all group"
                    >
                        <div className="flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                                <div className="flex flex-wrap items-center gap-1.5 mb-2">
                                    <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${TIPO_COLORS[packet.tipo]}`}>{TIPO_LABELS[packet.tipo]}</span>
                                    <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${SEVERIDADE_COLORS[packet.severidade]}`}>{SEVERIDADE_LABELS[packet.severidade]}</span>
                                    <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${STATUS_COLORS[packet.status]}`}>{STATUS_LABELS[packet.status]}</span>
                                </div>
                                <p className="text-sm font-black text-slate-900 leading-snug">{packet.titulo}</p>
                                <p className="text-xs text-slate-500 font-medium mt-1 line-clamp-2">{packet.descricao}</p>
                            </div>
                            <svg className="w-4 h-4 text-slate-300 group-hover:text-slate-500 transition-colors shrink-0 mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
                        </div>
                        <div className="flex items-center gap-3 mt-3">
                            <p className="text-[10px] text-slate-400 font-semibold">{getSistemaName(packet.sistema_id)}</p>
                            {(packet.affected_files?.length ?? 0) > 0 && (
                                <p className="text-[10px] text-slate-400 font-semibold">{packet.affected_files.length} arquivo{packet.affected_files.length !== 1 ? 's' : ''}</p>
                            )}
                            <p className="text-[10px] text-slate-300 font-semibold ml-auto">{new Date(packet.created_at).toLocaleDateString('pt-BR')}</p>
                        </div>
                    </button>
                ))}
            </div>

            {/* ── Detail slide-over ───────────────────────────────────────── */}
            {selectedPacket && (
                <div className="fixed inset-0 z-[200] flex justify-end animate-in fade-in duration-300">
                    <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => { setSelectedPacket(null); setIsEditing(false); }} />
                    <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right-full duration-500">
                        {/* Detail header */}
                        <header className="p-6 border-b border-slate-100 flex items-start justify-between gap-4 shrink-0">
                            <div className="flex-1 min-w-0">
                                <div className="flex flex-wrap items-center gap-1.5 mb-2">
                                    <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${TIPO_COLORS[selectedPacket.tipo]}`}>{TIPO_LABELS[selectedPacket.tipo]}</span>
                                    <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${SEVERIDADE_COLORS[selectedPacket.severidade]}`}>{SEVERIDADE_LABELS[selectedPacket.severidade]}</span>
                                    <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${STATUS_COLORS[selectedPacket.status]}`}>{STATUS_LABELS[selectedPacket.status]}</span>
                                </div>
                                <h3 className="text-lg font-black text-slate-900 leading-snug">{selectedPacket.titulo}</h3>
                                <p className="text-[10px] text-slate-400 font-semibold mt-1">{getSistemaName(selectedPacket.sistema_id)} · criado em {new Date(selectedPacket.created_at).toLocaleDateString('pt-BR')}</p>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                                {(selectedPacket.status === 'draft' || selectedPacket.status === 'review') && (
                                    <button
                                        onClick={() => { setIsEditing(v => !v); setEditForm({ ...selectedPacket }); setEditNewFile({ ...EMPTY_FILE }); }}
                                        className="p-2 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-700 transition-all"
                                        title={isEditing ? 'Cancelar edição' : 'Editar'}
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                    </button>
                                )}
                                <button onClick={() => { setSelectedPacket(null); setIsEditing(false); }} className="p-2 hover:bg-slate-100 rounded-full transition-all">
                                    <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                </button>
                            </div>
                        </header>

                        <div className="flex-1 overflow-y-auto p-6 space-y-8" style={{ scrollbarWidth: 'thin' }}>
                            {/* Descrição */}
                            <section>
                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-3 border-l-4 border-slate-300 pl-3">Descrição</h4>
                                {isEditing ? (
                                    <textarea
                                        value={editForm.descricao ?? ''}
                                        onChange={e => setEditForm(f => ({ ...f, descricao: e.target.value }))}
                                        rows={3}
                                        className="w-full text-sm text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-300 resize-none"
                                    />
                                ) : (
                                    <p className="text-sm text-slate-700 font-medium leading-relaxed">{selectedPacket.descricao}</p>
                                )}
                            </section>

                            {/* Arquivos afetados */}
                            <section>
                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-3 border-l-4 border-amber-400 pl-3">
                                    Arquivos Afetados
                                    <span className="ml-2 bg-amber-50 text-amber-600 text-[9px] font-black rounded-full px-2 py-0.5">{(isEditing ? editForm.affected_files : selectedPacket.affected_files)?.length ?? 0}</span>
                                </h4>
                                {isEditing ? (
                                    <div className="space-y-2">
                                        {(editForm.affected_files ?? []).map((file, i) => (
                                            <div key={i} className="flex items-center gap-2 bg-slate-50 rounded-xl px-3 py-2">
                                                <span className="shrink-0">{CHANGE_TYPE_ICON[file.change_type]}</span>
                                                <code className="flex-1 text-[11px] text-slate-700 font-mono truncate">{file.path}</code>
                                                <button onClick={() => setEditForm(f => ({ ...f, affected_files: (f.affected_files ?? []).filter((_, idx) => idx !== i) }))} className="shrink-0 text-rose-400 hover:text-rose-600 transition-colors">
                                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                                                </button>
                                            </div>
                                        ))}
                                        <div className="flex gap-2 mt-2">
                                            <input value={editNewFile.path} onChange={e => setEditNewFile(f => ({ ...f, path: e.target.value }))} placeholder="caminho/do/arquivo.ts" className="flex-1 text-xs font-mono text-slate-700 bg-white border border-slate-200 rounded-xl px-3 py-2 focus:outline-none" />
                                            <select value={editNewFile.change_type} onChange={e => setEditNewFile(f => ({ ...f, change_type: e.target.value as any }))} className="text-[10px] font-black text-slate-600 bg-white border border-slate-200 rounded-xl px-2 py-2 focus:outline-none">
                                                <option value="modified">M</option>
                                                <option value="added">A</option>
                                                <option value="deleted">D</option>
                                            </select>
                                            <button onClick={addFileToEdit} className="px-3 py-2 bg-slate-900 text-white rounded-xl text-[10px] font-black hover:bg-slate-700 transition-all">+</button>
                                        </div>
                                    </div>
                                ) : selectedPacket.affected_files.length === 0 ? (
                                    <p className="text-xs text-slate-400 font-semibold">Nenhum arquivo listado.</p>
                                ) : (
                                    <div className="space-y-1.5">
                                        {selectedPacket.affected_files.map((file, i) => (
                                            <div key={i} className="flex items-start gap-2 bg-slate-50 rounded-xl px-3 py-2">
                                                <span className="shrink-0 mt-0.5">{CHANGE_TYPE_ICON[file.change_type]}</span>
                                                <div className="min-w-0">
                                                    <code className="text-[11px] text-slate-700 font-mono">{file.path}</code>
                                                    {file.summary && <p className="text-[10px] text-slate-400 mt-0.5">{file.summary}</p>}
                                                    {file.diff_preview && (
                                                        <pre className="mt-1.5 text-[10px] bg-slate-900 text-emerald-400 rounded-lg p-2 overflow-x-auto font-mono leading-relaxed">{file.diff_preview}</pre>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </section>

                            {/* Proposta de mudança */}
                            <section>
                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-3 border-l-4 border-blue-500 pl-3">Proposta de Mudança</h4>
                                {isEditing ? (
                                    <textarea
                                        value={editForm.proposed_changes ?? ''}
                                        onChange={e => setEditForm(f => ({ ...f, proposed_changes: e.target.value }))}
                                        rows={8}
                                        className="w-full text-xs font-mono text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none"
                                        placeholder="Markdown aceito"
                                    />
                                ) : (
                                    <div className="prose prose-sm prose-slate max-w-none bg-blue-50/40 border border-blue-100 rounded-2xl p-5 text-sm">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{selectedPacket.proposed_changes || '_Sem conteúdo._'}</ReactMarkdown>
                                    </div>
                                )}
                            </section>

                            {/* Rationale */}
                            {(selectedPacket.rationale || isEditing) && (
                                <section>
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-3 border-l-4 border-violet-400 pl-3">Justificativa</h4>
                                    {isEditing ? (
                                        <textarea
                                            value={editForm.rationale ?? ''}
                                            onChange={e => setEditForm(f => ({ ...f, rationale: e.target.value }))}
                                            rows={4}
                                            className="w-full text-sm text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-200 resize-none"
                                        />
                                    ) : (
                                        <p className="text-sm text-slate-700 font-medium leading-relaxed italic bg-violet-50/40 border border-violet-100 rounded-2xl p-4">{selectedPacket.rationale}</p>
                                    )}
                                </section>
                            )}

                            {selectedPacket.suggested_pop_id && (
                                <section>
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-3 border-l-4 border-emerald-400 pl-3">Procedimento Associado</h4>
                                    <div className="bg-emerald-50/40 border border-emerald-100 rounded-2xl p-4">
                                        <p className="text-xs font-bold text-emerald-800">POP sugerido: <span className="text-emerald-950">{pops.find(pop => pop.id === selectedPacket.suggested_pop_id)?.nome ?? selectedPacket.suggested_pop_id}</span></p>
                                        <div className="mt-3 flex flex-wrap gap-2">
                                            <button
                                                onClick={() => handleCreatePOPRun(selectedPacket)}
                                                disabled={isCreatingPOPRun || !!selectedPacket.pop_run_id}
                                                className="px-3 py-2 text-[10px] font-black uppercase tracking-widest bg-emerald-700 text-white rounded-xl hover:bg-emerald-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                {selectedPacket.pop_run_id ? 'Execução vinculada' : isCreatingPOPRun ? 'Criando...' : 'Instanciar execução'}
                                            </button>
                                        </div>
                                    </div>
                                </section>
                            )}

                            {selectedPacket.suggested_pop_id && currentPOPRun && (
                                <section>
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-3 border-l-4 border-emerald-500 pl-3">Execução do Procedimento</h4>
                                    {selectedPacket.routing_assessment && selectedPacket.routing_assessment.approval_mode !== 'automatic' && (
                                        <div className={`mb-3 rounded-2xl border px-4 py-3 ${selectedPacket.routing_assessment.approval_mode === 'required' ? 'bg-rose-50 border-rose-200' : 'bg-amber-50 border-amber-200'}`}>
                                            <div className="flex items-center justify-between gap-3">
                                                <div>
                                                    <p className={`text-[10px] font-black uppercase tracking-widest ${selectedPacket.routing_assessment.approval_mode === 'required' ? 'text-rose-700' : 'text-amber-700'}`}>Governança do Procedimento</p>
                                                    <p className="mt-1 text-xs font-medium text-slate-600">
                                                        {selectedPacket.routing_assessment.approval_mode === 'required'
                                                            ? 'Aprovar ou aplicar este POP exige liberação explícita.'
                                                            : 'Aprovar ou aplicar este POP pede confirmação curta.'}
                                                    </p>
                                                </div>
                                                <button
                                                    onClick={() => setPopRunApprovalGranted(true)}
                                                    disabled={popRunApprovalGranted}
                                                    className={`px-3 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${popRunApprovalGranted ? 'bg-emerald-500 text-white opacity-80' : selectedPacket.routing_assessment.approval_mode === 'required' ? 'bg-rose-600 text-white hover:bg-rose-700' : 'bg-amber-500 text-white hover:bg-amber-600'}`}
                                                >
                                                    {popRunApprovalGranted ? 'Liberado' : 'Liberar sessão'}
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    <div className="mb-3 flex flex-wrap gap-2">
                                        {(['proposed', 'in_review', 'approved', 'applied'] as POPRun['status'][])
                                            .filter(status => canTransitionPOPRunStatus(currentPOPRun.status, status))
                                            .map(status => (
                                                <button
                                                    key={status}
                                                    onClick={() => handlePOPRunStatusChange(status)}
                                                    className="px-3 py-2 text-[10px] font-black uppercase tracking-widest bg-slate-100 text-slate-700 rounded-xl hover:bg-slate-200 transition-all"
                                                >
                                                    {status}
                                                </button>
                                            ))}
                                    </div>

                                    <div className="space-y-2">
                                        {(pops.find(pop => pop.id === selectedPacket.suggested_pop_id)?.passos || [])
                                            .slice()
                                            .sort((a, b) => a.ordem - b.ordem)
                                            .map(step => {
                                                const resolved = currentPOPRun.steps_resolved.find((item: POPStepRun) => item.step_id === step.id);
                                                const completed = resolved?.status === 'completed';
                                                return (
                                                    <button
                                                        key={step.id}
                                                        onClick={() => handleTogglePOPRunStep(step.id)}
                                                        className="w-full rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-left transition-all hover:bg-slate-100"
                                                    >
                                                        <div className="flex items-start gap-3">
                                                            <div className={`mt-0.5 h-4 w-4 rounded border-2 flex items-center justify-center shrink-0 ${completed ? 'bg-emerald-500 border-emerald-500' : 'border-slate-300'}`}>
                                                                {completed && (
                                                                    <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M5 13l4 4L19 7" />
                                                                    </svg>
                                                                )}
                                                            </div>
                                                            <div className="min-w-0 flex-1">
                                                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Passo {step.ordem} · {step.tipo}</p>
                                                                <p className={`mt-1 text-sm font-black ${completed ? 'text-slate-400 line-through' : 'text-slate-900'}`}>{step.titulo}</p>
                                                                <p className={`mt-1 text-xs leading-relaxed ${completed ? 'text-slate-400' : 'text-slate-600'}`}>{step.descricao}</p>
                                                            </div>
                                                        </div>
                                                    </button>
                                                );
                                            })}
                                    </div>

                                    <div className="mt-4 bg-slate-50 border border-slate-100 rounded-2xl p-4">
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Aprendizado do POP</p>
                                        <textarea
                                            value={learningDraft}
                                            onChange={e => setLearningDraft(e.target.value)}
                                            rows={3}
                                            placeholder="Registre aqui exceções, ajustes ou correções humanas deste procedimento..."
                                            className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 resize-none focus:outline-none"
                                        />
                                        <div className="mt-2 flex justify-end">
                                            <button
                                                onClick={handleCreateLearningEvent}
                                                disabled={isSavingLearning || !learningDraft.trim()}
                                                className="px-3 py-2 text-[10px] font-black uppercase tracking-widest bg-slate-900 text-white rounded-xl hover:bg-slate-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                {isSavingLearning ? 'Salvando...' : 'Registrar aprendizado'}
                                            </button>
                                        </div>
                                    </div>

                                    {learningEvents.length > 0 && (
                                        <div className="mt-3 space-y-2">
                                            {learningEvents.slice(0, 4).map(event => (
                                                <div key={event.id} className="rounded-xl border border-slate-100 bg-white px-4 py-3">
                                                    <div className="flex items-center justify-between gap-2">
                                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{event.tipo}</p>
                                                        <span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase tracking-widest ${event.review_status === 'pending' ? 'bg-amber-100 text-amber-700' : event.review_status === 'accepted' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                                                            {event.review_status}
                                                        </span>
                                                    </div>
                                                    <p className="mt-2 text-xs leading-relaxed text-slate-700">{event.descricao}</p>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </section>
                            )}

                            {/* Routing assessment */}
                            {selectedPacket.routing_assessment && (
                                <section>
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-3 border-l-4 border-slate-400 pl-3">Avaliação de Governança</h4>
                                    <div className="bg-slate-50 border border-slate-100 rounded-2xl p-4 grid grid-cols-3 gap-3">
                                        <div>
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Clareza</p>
                                            <p className="text-sm font-black text-slate-900">{selectedPacket.routing_assessment.clarity_score}</p>
                                        </div>
                                        <div>
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Contexto</p>
                                            <p className="text-sm font-black text-slate-900">{selectedPacket.routing_assessment.context_score}</p>
                                        </div>
                                        <div>
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Risco</p>
                                            <p className="text-sm font-black text-slate-900">{selectedPacket.routing_assessment.risk_level}</p>
                                        </div>
                                        {selectedPacket.routing_assessment.rationale.length > 0 && (
                                            <div className="col-span-3 mt-1">
                                                <ul className="space-y-1">
                                                    {selectedPacket.routing_assessment.rationale.map((r, i) => (
                                                        <li key={i} className="text-[11px] text-slate-500 flex gap-2">
                                                            <span className="text-slate-300">—</span>{r}
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                    </div>
                                </section>
                            )}

                            {/* Review audit */}
                            {(selectedPacket.reviewed_by || selectedPacket.review_note) && (
                                <section>
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-3 border-l-4 border-emerald-400 pl-3">Revisão</h4>
                                    <div className="bg-emerald-50/40 border border-emerald-100 rounded-2xl p-4 space-y-1">
                                        {selectedPacket.reviewed_by && <p className="text-xs font-bold text-slate-600">Por: <span className="text-slate-900">{selectedPacket.reviewed_by}</span></p>}
                                        {selectedPacket.reviewed_at && <p className="text-xs text-slate-400">{new Date(selectedPacket.reviewed_at).toLocaleString('pt-BR')}</p>}
                                        {selectedPacket.review_note && <p className="text-sm text-slate-700 font-medium mt-2 leading-relaxed">{selectedPacket.review_note}</p>}
                                    </div>
                                </section>
                            )}
                        </div>

                        {/* Action footer */}
                        <footer className="p-5 border-t border-slate-100 shrink-0 space-y-3">
                            {isEditing ? (
                                <div className="flex justify-end gap-2">
                                    <button onClick={() => setIsEditing(false)} className="px-4 py-2.5 text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-100 rounded-xl transition-all">Cancelar</button>
                                    <button onClick={handleSaveEdit} className="px-5 py-2.5 text-[10px] font-black uppercase tracking-widest bg-slate-900 text-white rounded-xl hover:bg-slate-700 transition-all">Salvar Alterações</button>
                                </div>
                            ) : (
                                <>
                                    {(['draft', 'review', 'approved', 'rejected'].includes(selectedPacket.status)) && (
                                        <textarea
                                            value={reviewNote}
                                            onChange={e => setReviewNote(e.target.value)}
                                            rows={2}
                                            placeholder="Nota de revisão (opcional)…"
                                            className="w-full text-xs text-slate-700 bg-slate-50 border border-slate-100 rounded-xl px-3 py-2 focus:outline-none resize-none"
                                        />
                                    )}
                                    <div className="flex flex-wrap gap-2">
                                        {(Object.keys(STATUS_LABELS) as IssuePacketStatus[])
                                            .filter(s => canTransition(selectedPacket.status, s))
                                            .map(s => (
                                                <button
                                                    key={s}
                                                    onClick={() => handleStatusChange(selectedPacket, s)}
                                                    className={`px-4 py-2.5 text-[10px] font-black uppercase tracking-widest rounded-xl transition-all ${STATUS_COLORS[s]} hover:opacity-80`}
                                                >
                                                    → {STATUS_LABELS[s]}
                                                </button>
                                            ))}
                                    </div>
                                </>
                            )}
                        </footer>
                    </div>
                </div>
            )}

            {/* ── Create packet modal ──────────────────────────────────────── */}
            {isCreating && (
                <div className="fixed inset-0 z-[300] flex items-center justify-center animate-in fade-in duration-200">
                    <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setIsCreating(false)} />
                    <div className="relative w-full max-w-xl bg-white rounded-3xl shadow-2xl flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200">
                        <div className="flex items-center justify-between p-6 border-b border-slate-100">
                            <h3 className="text-base font-black text-slate-900">Nova Proposta Técnica</h3>
                            <button onClick={() => setIsCreating(false)} className="p-2 hover:bg-slate-100 rounded-full transition-all">
                                <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6 space-y-5" style={{ scrollbarWidth: 'thin' }}>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1.5">Título *</label>
                                <input value={form.titulo ?? ''} onChange={e => setForm(f => ({ ...f, titulo: e.target.value }))} className="w-full text-sm font-semibold text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-slate-300" placeholder="Título da proposta" />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1.5">Sistema *</label>
                                <select value={form.sistema_id ?? ''} onChange={e => setForm(f => ({ ...f, sistema_id: e.target.value }))} className="w-full text-sm font-semibold text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 focus:outline-none">
                                    <option value="">Selecionar sistema…</option>
                                    {sistemas.map(s => <option key={s.id} value={s.id}>{formatSistemaName(s)}</option>)}
                                </select>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1.5">Tipo</label>
                                    <select value={form.tipo} onChange={e => setForm(f => ({ ...f, tipo: e.target.value as IssuePacketTipo }))} className="w-full text-sm font-semibold text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 focus:outline-none">
                                        {(Object.keys(TIPO_LABELS) as IssuePacketTipo[]).map(t => <option key={t} value={t}>{TIPO_LABELS[t]}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1.5">Severidade</label>
                                    <select value={form.severidade} onChange={e => setForm(f => ({ ...f, severidade: e.target.value as IssuePacketSeveridade }))} className="w-full text-sm font-semibold text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 focus:outline-none">
                                        {(Object.keys(SEVERIDADE_LABELS) as IssuePacketSeveridade[]).map(s => <option key={s} value={s}>{SEVERIDADE_LABELS[s]}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1.5">Descrição</label>
                                <textarea value={form.descricao ?? ''} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} rows={3} className="w-full text-sm font-semibold text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus:outline-none resize-none" placeholder="Descrição do problema ou oportunidade" />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1.5">Proposta de Mudança (Markdown)</label>
                                <textarea value={form.proposed_changes ?? ''} onChange={e => setForm(f => ({ ...f, proposed_changes: e.target.value }))} rows={5} className="w-full text-xs font-mono text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus:outline-none resize-none" placeholder="O que precisa mudar e como…" />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1.5">Justificativa</label>
                                <textarea value={form.rationale ?? ''} onChange={e => setForm(f => ({ ...f, rationale: e.target.value }))} rows={2} className="w-full text-sm font-semibold text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus:outline-none resize-none" placeholder="Por que essa mudança é necessária?" />
                            </div>
                            {suggestedPOP && (
                                <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 px-4 py-4">
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600">POP sugerido</p>
                                            <h4 className="mt-1 text-sm font-black text-emerald-900">{suggestedPOP.pop.nome}</h4>
                                        </div>
                                        <span className="rounded-full bg-white px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-emerald-700 border border-emerald-100">
                                            {Math.round(suggestedPOP.score * 100)}%
                                        </span>
                                    </div>
                                    <p className="mt-2 text-xs font-semibold leading-relaxed text-emerald-800">
                                        {buildPOPRationale(suggestedPOP)}
                                    </p>
                                    {suggestedPOP.missing_requirements.length > 0 && (
                                        <p className="mt-2 text-[11px] font-semibold text-amber-700">
                                            Lacunas: {suggestedPOP.missing_requirements.join(' ')}
                                        </p>
                                    )}
                                </div>
                            )}
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Arquivos Afetados</label>
                                <div className="space-y-2">
                                    {(form.affected_files ?? []).map((file, i) => (
                                        <div key={i} className="flex items-center gap-2 bg-slate-50 rounded-xl px-3 py-2">
                                            <span className="shrink-0">{CHANGE_TYPE_ICON[file.change_type]}</span>
                                            <code className="flex-1 text-[11px] text-slate-700 font-mono truncate">{file.path}</code>
                                            <button onClick={() => setForm(f => ({ ...f, affected_files: (f.affected_files ?? []).filter((_, idx) => idx !== i) }))} className="shrink-0 text-rose-400 hover:text-rose-600 transition-colors">
                                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                                            </button>
                                        </div>
                                    ))}
                                    <div className="flex gap-2">
                                        <input value={newFile.path} onChange={e => setNewFile(f => ({ ...f, path: e.target.value }))} onKeyDown={e => e.key === 'Enter' && addFileToForm()} placeholder="caminho/do/arquivo.ts" className="flex-1 text-xs font-mono text-slate-700 bg-white border border-slate-200 rounded-xl px-3 py-2 focus:outline-none" />
                                        <select value={newFile.change_type} onChange={e => setNewFile(f => ({ ...f, change_type: e.target.value as any }))} className="text-[10px] font-black text-slate-600 bg-white border border-slate-200 rounded-xl px-2 py-2 focus:outline-none">
                                            <option value="modified">Mod</option>
                                            <option value="added">Add</option>
                                            <option value="deleted">Del</option>
                                        </select>
                                        <button onClick={addFileToForm} className="px-3 py-2 bg-slate-900 text-white rounded-xl text-[10px] font-black hover:bg-slate-700 transition-all">+</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2 p-5 border-t border-slate-100">
                            <button onClick={() => setIsCreating(false)} className="px-4 py-2.5 text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-100 rounded-xl transition-all">Cancelar</button>
                            <button onClick={handleCreate} disabled={!form.titulo?.trim() || !form.sistema_id} className="px-6 py-2.5 text-[10px] font-black uppercase tracking-widest bg-slate-900 text-white rounded-xl hover:bg-slate-700 transition-all disabled:opacity-40 disabled:cursor-not-allowed">Criar Proposta</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
