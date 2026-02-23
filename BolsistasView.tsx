import React, { useState, useEffect } from 'react';
import { collection, query, where, onSnapshot, addDoc, updateDoc, doc, getDoc } from 'firebase/firestore';
import { db } from './firebase';
import { VinculoProjeto, PerfilPessoa, TipoBolsa, Projeto } from './types';
import { generateScholarshipForm } from './src/utils/pdfGenerator';

interface BolsistasViewProps {
    projetoId: string;
}

export const BolsistasView: React.FC<BolsistasViewProps> = ({ projetoId }) => {
    const [links, setLinks] = useState<VinculoProjeto[]>([]);
    const [people, setPeople] = useState<Record<string, PerfilPessoa>>({});
    const [scholarshipTypes, setScholarshipTypes] = useState<TipoBolsa[]>([]);
    const [project, setProject] = useState<Projeto | null>(null);

    // Modal States
    const [isLinkModalOpen, setIsLinkModalOpen] = useState(false);
    const [editingLink, setEditingLink] = useState<VinculoProjeto | null>(null);
    const [selectedPersonId, setSelectedPersonId] = useState<string>('');

    // Form Data for New/Edit Link
    const [linkForm, setLinkForm] = useState<Partial<VinculoProjeto>>({
        percentual_recebimento: 100,
        status: 'Em regularização'
    });

    // Fetch Project
    useEffect(() => {
        if(!projetoId) return;
        getDoc(doc(db, 'projetos', projetoId)).then(snap => {
             if (snap.exists()) setProject({ id: snap.id, ...snap.data() } as Projeto);
        });
    }, [projetoId]);

    // Fetch Scholarship Types
    useEffect(() => {
        const unsub = onSnapshot(collection(db, 'tipos_bolsa'), (snap) => {
            setScholarshipTypes(snap.docs.map(d => ({ id: d.id, ...d.data() } as TipoBolsa)));
        });
        return () => unsub();
    }, []);

    // Fetch Links and People
    useEffect(() => {
        if (!projetoId) return;

        const q = query(collection(db, 'vinculos_projeto'), where('projeto_id', '==', projetoId));
        const unsubLinks = onSnapshot(q, async (snapshot) => {
            const fetchedLinks = snapshot.docs.map(d => ({ id: d.id, ...d.data() } as VinculoProjeto));

            // Sort by date desc
            fetchedLinks.sort((a, b) => new Date(b.data_inicio).getTime() - new Date(a.data_inicio).getTime());
            setLinks(fetchedLinks);

            // Fetch related People (Optimized)
            const personIds = Array.from(new Set(fetchedLinks.map(l => l.pessoa_id)));
            if (personIds.length > 0) {
                // Fetch profiles in parallel
                const promises = personIds.map(pid => getDoc(doc(db, 'perfil_pessoas', pid)));
                const peopleSnaps = await Promise.all(promises);

                const peopleMap: Record<string, PerfilPessoa> = {};
                peopleSnaps.forEach(snap => {
                    if (snap.exists()) {
                        peopleMap[snap.id] = { id: snap.id, ...snap.data() } as PerfilPessoa;
                    }
                });
                setPeople(peopleMap);
            }
        });

        return () => unsubLinks();
    }, [projetoId]);

    // Group links by Person
    const groupedLinks = links.reduce((acc, link) => {
        if (!acc[link.pessoa_id]) acc[link.pessoa_id] = [];
        acc[link.pessoa_id].push(link);
        return acc;
    }, {} as Record<string, VinculoProjeto[]>);

    const handleSaveLink = async () => {
        try {
            const linkData = {
                ...linkForm,
                projeto_id: projetoId,
                pessoa_id: selectedPersonId || editingLink?.pessoa_id,
            };

            // Calculate value based on Type and Percentage if not set manually
            let calculatedMonthlyValue = linkData.valor_bolsa_mensal_atual || 0;
            if (linkData.tipo_bolsa_id) {
                const type = scholarshipTypes.find(t => t.id === linkData.tipo_bolsa_id);
                if (type) {
                    const baseValue = type.valor_integral;
                    const percent = linkData.percentual_recebimento || 100;
                    calculatedMonthlyValue = (baseValue * percent) / 100;
                    linkData.valor_bolsa_mensal_atual = calculatedMonthlyValue;
                }
            }

            // --- Budget Check (Rule 5) ---
            if (linkData.status === 'Ativo(a)' && project?.orcamento?.bolsas) {
                // Calculate total committed so far (approximate using links)
                const totalBudget = project.orcamento.bolsas;

                // Calculate cost of existing links
                const existingCost = links.reduce((acc, link) => {
                    // If editing, skip the current version of this link to avoid double counting
                    if (editingLink && link.id === editingLink.id) return acc;

                    if (link.status === 'Desligado(a)') {
                       // If terminated, calculate cost until termination
                       // (This needs data_desligamento_real, assuming full duration for now if missing or simpler check)
                       return acc; // For safety/simplicity, ignoring past terminated for "Active" check, but ideally should sum all history.
                    }

                    // Future/Active commitment
                    const start = new Date(link.data_inicio);
                    const end = link.data_fim_prevista ? new Date(link.data_fim_prevista) : new Date(start.getFullYear() + 1, start.getMonth(), start.getDate());
                    const months = Math.max(0, (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth()));
                    return acc + (link.valor_bolsa_mensal_atual * months);
                }, 0);

                // Cost of new/updated link
                const newStart = new Date(linkData.data_inicio as string);
                const newEnd = linkData.data_fim_prevista ? new Date(linkData.data_fim_prevista as string) : new Date(newStart.getFullYear() + 1, newStart.getMonth(), newStart.getDate());
                const newMonths = Math.max(0, (newEnd.getFullYear() - newStart.getFullYear()) * 12 + (newEnd.getMonth() - newStart.getMonth()));
                const newCost = calculatedMonthlyValue * newMonths;

                if ((existingCost + newCost) > totalBudget) {
                    const confirmOver = confirm(`Atenção: O valor comprometido (R$ ${(existingCost + newCost).toLocaleString()}) ultrapassa o teto da rubrica de bolsas (R$ ${totalBudget.toLocaleString()}). Deseja continuar mesmo assim?`);
                    if (!confirmOver) return;
                }
            }

            if (editingLink) {
                await updateDoc(doc(db, 'vinculos_projeto', editingLink.id), linkData);
            } else {
                await addDoc(collection(db, 'vinculos_projeto'), linkData);
            }
            setIsLinkModalOpen(false);
            setEditingLink(null);
            setLinkForm({});
        } catch (e) {
            console.error(e);
            alert("Erro ao salvar vínculo.");
        }
    };

    const handleDeleteLink = async (id: string) => {
        if (confirm("Tem certeza que deseja remover este vínculo?")) {
            // Logic to delete or mark as deleted
            alert("Função de deletar não implementada para segurança (use 'Desligado' no status).");
        }
    };

    const isExpiringSoon = (dateStr: string) => {
        if (!dateStr) return false;
        const today = new Date();
        const end = new Date(dateStr);
        const diffTime = end.getTime() - today.getTime();
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return diffDays >= 0 && diffDays <= 30;
    };

    return (
        <div className="p-8 space-y-8">
            <div className="flex justify-between items-center">
                <div>
                    <h3 className="text-xl font-black text-slate-800">Equipe de Bolsistas</h3>
                    <p className="text-slate-400 text-xs font-medium mt-1">{Object.keys(groupedLinks).length} bolsistas ativos/históricos</p>
                </div>
                {/* For adding new people not via portal, we'd need a Person Search/Create modal. For now, let's assume we pick from existing people or just show the portal link */}
                <div className="flex gap-2">
                    <button
                        onClick={() => {
                            // Copy portal link
                            const url = `${window.location.origin}/join/${projetoId}/invite`;
                            navigator.clipboard.writeText(url);
                            alert("Link do Portal de Autocadastro copiado!");
                        }}
                        className="px-4 py-2 bg-slate-100 text-slate-600 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-200 transition-all"
                    >
                        Link do Portal
                    </button>
                    {/* Add manual link button could go here */}
                </div>
            </div>

            <div className="grid grid-cols-1 gap-6">
                {Object.entries(groupedLinks).map(([personId, personLinks]) => {
                    const person = people[personId];
                    if (!person) return null; // Loading or not found

                    const activeLink = personLinks.find(l => l.status === 'Ativo(a)' || l.status === 'Em regularização') || personLinks[0];
                    const isExpiring = activeLink.data_fim_prevista && isExpiringSoon(activeLink.data_fim_prevista);

                    return (
                        <div key={personId} className={`bg-white border ${isExpiring ? 'border-amber-300 ring-2 ring-amber-100' : 'border-slate-200'} rounded-[2rem] p-6 shadow-sm hover:shadow-md transition-all`}>
                            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                                <div className="flex items-center gap-4">
                                    <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 font-black text-sm">
                                        {person.nome.charAt(0)}
                                    </div>
                                    <div>
                                        <h4 className="text-lg font-bold text-slate-800">{person.nome}</h4>
                                        <div className="flex items-center gap-2 mt-1">
                                            <span className="text-xs text-slate-400">{person.cpf}</span>
                                            <span className="text-xs text-slate-300">•</span>
                                            <span className="text-xs text-slate-400">{person.email}</span>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => {
                                            const type = scholarshipTypes.find(t => t.id === activeLink.tipo_bolsa_id);
                                            generateScholarshipForm(person, activeLink, project || undefined, type);
                                        }}
                                        className="px-4 py-2 bg-indigo-50 text-indigo-600 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-indigo-100 transition-all flex items-center gap-2"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                        Ficha
                                    </button>
                                    <button
                                        onClick={() => {
                                            setEditingLink(null);
                                            setSelectedPersonId(personId);
                                            setLinkForm({
                                                status: 'Ativo(a)',
                                                percentual_recebimento: 100,
                                                projeto_id: projetoId,
                                                pessoa_id: personId
                                            });
                                            setIsLinkModalOpen(true);
                                        }}
                                        className="px-4 py-2 bg-slate-900 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-800 transition-all"
                                    >
                                        Novo Aditivo
                                    </button>
                                </div>
                            </div>

                            {/* Timeline of Links */}
                            <div className="space-y-3">
                                {personLinks.map(link => {
                                    const type = scholarshipTypes.find(t => t.id === link.tipo_bolsa_id);
                                    return (
                                        <div key={link.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-2xl border border-slate-100 group hover:border-indigo-200 transition-colors">
                                            <div className="flex items-center gap-4">
                                                <div className={`w-2 h-10 rounded-full ${
                                                    link.status === 'Ativo(a)' ? 'bg-emerald-500' :
                                                    link.status === 'Em regularização' ? 'bg-amber-500' : 'bg-slate-300'
                                                }`}></div>
                                                <div>
                                                    <p className="text-sm font-bold text-slate-700">
                                                        {type?.nome_modalidade || 'Bolsa'} <span className="text-slate-400 font-normal">({link.percentual_recebimento}%)</span>
                                                    </p>
                                                    <p className="text-xs text-slate-400 font-medium">
                                                        {new Date(link.data_inicio).toLocaleDateString('pt-BR')} até {link.data_fim_prevista ? new Date(link.data_fim_prevista).toLocaleDateString('pt-BR') : 'Indefinido'}
                                                    </p>
                                                </div>
                                            </div>
                                            <div className="text-right flex items-center gap-4">
                                                <div>
                                                    <p className="text-sm font-black text-slate-800">
                                                        {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(link.valor_bolsa_mensal_atual)}
                                                    </p>
                                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">{link.status}</p>
                                                </div>
                                                <button
                                                    onClick={() => {
                                                        setEditingLink(link);
                                                        setLinkForm(link);
                                                        setIsLinkModalOpen(true);
                                                    }}
                                                    className="p-2 text-slate-300 hover:text-indigo-600 opacity-0 group-hover:opacity-100 transition-all"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                                </button>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Modal for Link */}
            {isLinkModalOpen && (
                <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
                    <div className="bg-white w-full max-w-lg rounded-[2rem] shadow-2xl p-8 animate-in zoom-in-95">
                        <h3 className="text-xl font-black text-slate-900 mb-6">{editingLink ? 'Editar Vínculo' : 'Novo Vínculo/Aditivo'}</h3>
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Tipo de Bolsa</label>
                                    <select
                                        value={linkForm.tipo_bolsa_id}
                                        onChange={e => setLinkForm({...linkForm, tipo_bolsa_id: e.target.value})}
                                        className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700 bg-white"
                                    >
                                        <option value="">Selecione...</option>
                                        {scholarshipTypes.map(t => (
                                            <option key={t.id} value={t.id}>{t.nome_modalidade} ({new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(t.valor_integral)})</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">% Recebimento</label>
                                    <input
                                        type="number"
                                        value={linkForm.percentual_recebimento}
                                        onChange={e => setLinkForm({...linkForm, percentual_recebimento: Number(e.target.value)})}
                                        className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700"
                                    />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Data Início</label>
                                    <input
                                        type="date"
                                        value={linkForm.data_inicio}
                                        onChange={e => setLinkForm({...linkForm, data_inicio: e.target.value})}
                                        className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700"
                                    />
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Previsão Fim</label>
                                    <input
                                        type="date"
                                        value={linkForm.data_fim_prevista}
                                        onChange={e => setLinkForm({...linkForm, data_fim_prevista: e.target.value})}
                                        className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700"
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Status</label>
                                <select
                                    value={linkForm.status}
                                    onChange={e => setLinkForm({...linkForm, status: e.target.value as any})}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700 bg-white"
                                >
                                    <option value="Em regularização">Em regularização</option>
                                    <option value="Ativo(a)">Ativo(a)</option>
                                    <option value="Concluído(a)">Concluído(a)</option>
                                    <option value="Desligado(a)">Desligado(a)</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Função/Atividades</label>
                                <input
                                    value={linkForm.funcao || ''}
                                    onChange={e => setLinkForm({...linkForm, funcao: e.target.value})}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-medium text-slate-600"
                                    placeholder="Ex: Pesquisador Assistente"
                                />
                            </div>
                        </div>
                        <div className="flex gap-4 pt-6">
                            <button
                                onClick={() => setIsLinkModalOpen(false)}
                                className="flex-1 py-3 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-xl transition-all"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleSaveLink}
                                className="flex-1 bg-indigo-600 text-white py-3 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg hover:bg-indigo-700 transition-all"
                            >
                                Salvar
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
