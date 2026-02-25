import React, { useState, useEffect } from 'react';
import { collection, query, where, onSnapshot, addDoc, updateDoc, doc, getDoc, getDocs } from 'firebase/firestore';
import { db } from '../firebase';
import { VinculoProjeto, PerfilPessoa, TipoBolsa, Projeto } from '../types';
import { generateScholarshipForm } from '../utils/pdfGenerator';

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
    const [isScholarshipTypeModalOpen, setIsScholarshipTypeModalOpen] = useState(false);
    const [selectedPersonIdForView, setSelectedPersonIdForView] = useState<string | null>(null);
    const [newTypeForm, setNewTypeForm] = useState<Partial<TipoBolsa>>({});

    // Form Data for New/Edit Link
    const [linkForm, setLinkForm] = useState<Partial<VinculoProjeto>>({
        percentual_recebimento: 100,
        status: 'Em regularização'
    });
    const [searchTerm, setSearchTerm] = useState('');
    const fileInputRef = React.useRef<HTMLInputElement>(null);

    const parseCSV = (text: string) => {
        const lines = text.split(/\r?\n/);
        if (lines.length === 0) return [];
        
        const headerLine = lines[0];
        const delimiter = headerLine.includes(';') ? ';' : ',';
        const headers = headerLine.split(delimiter).map(h => h.replace(/^"|"$/g, '').trim());
        const result = [];

        for (let i = 1; i < lines.length; i++) {
            if (!lines[i].trim()) continue;
            
            const line = lines[i].trim();
            if (!line) continue;
            
            // Regex mais robusto para lidar com aspas e delimitadores
            let values: string[] = [];
            if (delimiter === ';') {
                values = line.split(';').map(v => v.replace(/^"|"$/g, '').trim());
            } else {
                // Para vírgula, usa regex que ignora vírgulas dentro de aspas
                const matches = line.match(/(".*?"|[^",\s]+|(?<=,|^)(?=,|$))/g);
                values = matches ? matches.map(v => v.replace(/^"|"$/g, '').trim()) : [];
            }

            if (values.length > 0) {
                const obj: any = {};
                headers.forEach((h, idx) => {
                    obj[h] = values[idx] || '';
                });
                result.push(obj);
            }
        }
        return result;
    };

    const parseBrDate = (dateStr: string) => {
        if (!dateStr || dateStr === 'Não se aplica') return '';
        const months: Record<string, string> = {
            'janeiro': '01', 'fevereiro': '02', 'março': '03', 'abril': '04',
            'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
            'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12'
        };
        const parts = dateStr.toLowerCase().replace(/ de /g, ' ').split(' ');
        if (parts.length < 3) return '';
        
        const day = parts[0].padStart(2, '0');
        const month = months[parts[1]] || '01';
        const year = parts[2];
        return `${year}-${month}-${day}`;
    };

    const handleImportCSV = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (event) => {
            const text = event.target?.result as string;
            const data = parseCSV(text);
            
            if (data.length === 0) {
                alert("Arquivo vazio ou formato inválido.");
                return;
            }

            let importedCount = 0;
            let errorCount = 0;

            for (const row of data) {
                try {
                    const cpf = row['CPF']?.replace(/\D/g, '');
                    if (!cpf) continue;

                    // 1. Check/Create Person
                    let personId = '';
                    const qPerson = query(collection(db, 'perfil_pessoas'), where('cpf', '==', cpf));
                    const personSnap = await getDocs(qPerson);

                    const personData: any = {
                        nome: row['Pergunta 1'],
                        cpf: cpf,
                        rg: row['RG'],
                        email: row['Email'],
                        telefone: row['Telefone de contato'],
                        endereco: row['Endereço'],
                        campus: row['Campus'],
                        curso: row['Curso no Ifes'],
                        lattes: row['Currículo Lattes'],
                        dados_bancarios: {
                            agencia: row['Agência Banestes'],
                            conta: row['Conta Corrente Banestes'],
                            banco: 'Banestes'
                        },
                        data_atualizacao: new Date().toISOString()
                    };

                    if (personSnap.empty) {
                        personData.data_criacao = new Date().toISOString();
                        const newPerson = await addDoc(collection(db, 'perfil_pessoas'), personData);
                        personId = newPerson.id;
                    } else {
                        personId = personSnap.docs[0].id;
                        await updateDoc(doc(db, 'perfil_pessoas', personId), personData);
                    }

                    // 2. Resolve Scholarship Type
                    const modalidadeRaw = (row['Modalidade de bolsa'] || row['Modalidade'] || row['Bolsa'] || '').trim();
                    
                    // Regex para pegar o nome da modalidade (ex: BPIG-I)
                    const nameMatch = modalidadeRaw.match(/(BPIG-[IVX]+|BPIG\s?[IVX]+)/i);
                    const namePart = nameMatch ? nameMatch[0].replace(/\s/g, '-').toUpperCase() : modalidadeRaw.split(' ')[0];
                    const percentPart = modalidadeRaw.includes('60') ? 60 : 100;

                    let type = scholarshipTypes.find(t => 
                        t.nome_modalidade.toUpperCase() === namePart.toUpperCase() ||
                        t.nome_modalidade.toUpperCase().includes(namePart.toUpperCase())
                    );
                    
                    // Se não encontrou mas é um BPIG conhecido, tenta buscar de forma mais agressiva
                    if (!type && namePart.startsWith('BPIG')) {
                        type = scholarshipTypes.find(t => t.nome_modalidade.replace(/[^a-zA-Z0-9]/g, '').includes(namePart.replace(/[^a-zA-Z0-9]/g, '')));
                    }
                    
                    const typeId = type?.id || '';

                    // 3. Create Link
                    const start = parseBrDate(row['Data de Início']);
                    const end = parseBrDate(row['Data de Conclusão']);

                    const linkData: Partial<VinculoProjeto> = {
                        pessoa_id: personId,
                        projeto_id: projetoId,
                        data_inicio: start,
                        data_fim_prevista: end,
                        status: row['Status da convocação'] as any || 'Ativo(a)',
                        funcao: row['Função'],
                        tipo_bolsa_id: typeId,
                        percentual_recebimento: percentPart,
                        valor_bolsa_mensal_atual: type ? (type.valor_integral * percentPart) / 100 : 0
                    };

                    const qLink = query(
                        collection(db, 'vinculos_projeto'), 
                        where('projeto_id', '==', projetoId),
                        where('pessoa_id', '==', personId),
                        where('data_inicio', '==', start)
                    );
                    const linkSnap = await getDocs(qLink);

                    if (linkSnap.empty) {
                        await addDoc(collection(db, 'vinculos_projeto'), linkData);
                        importedCount++;
                    }
                } catch (err) {
                    console.error("Erro ao importar linha:", row, err);
                    errorCount++;
                }
            }

            alert(`Importação concluída: ${importedCount} novos bolsistas, ${errorCount} erros.`);
            if (fileInputRef.current) fileInputRef.current.value = '';
        };
        reader.readAsText(file);
    };


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
            const types = snap.docs.map(d => ({ id: d.id, ...d.data() } as TipoBolsa));
            // Garante que a interface não mostre duplicados caso o banco já contenha nomes repetidos
            const uniqueTypes = types.filter((v, i, a) => a.findIndex(t => t.nome_modalidade === v.nome_modalidade) === i);
            setScholarshipTypes(uniqueTypes);
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

    // Filtered Grouped Links
    const filteredGroupedLinks = Object.entries(groupedLinks).filter(([personId, personLinks]) => {
        const person = people[personId];
        if (!person) return false;
        const search = searchTerm.toLowerCase();
        return (
            person.nome.toLowerCase().includes(search) ||
            person.cpf.includes(search) ||
            person.email?.toLowerCase().includes(search)
        );
    });

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
        <div className="p-8 space-y-6">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h3 className="text-xl font-black text-slate-800">Equipe de Bolsistas</h3>
                    <p className="text-slate-400 text-xs font-medium mt-1">{Object.keys(groupedLinks).length} bolsistas no total</p>
                </div>
                <div className="flex flex-wrap gap-2 w-full md:w-auto">
                    <div className="relative flex-1 md:flex-none">
                        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        <input 
                            type="text"
                            placeholder="Pesquisar por nome, CPF ou email..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="pl-10 pr-4 py-2 bg-slate-100 border-none rounded-xl text-xs font-bold text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500 w-full md:w-64 transition-all"
                        />
                    </div>
                    <input
                        type="file"
                        ref={fileInputRef}
                        onChange={handleImportCSV}
                        accept=".csv"
                        className="hidden"
                    />
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        className="px-4 py-2 bg-emerald-50 text-emerald-600 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-emerald-100 transition-all flex items-center gap-2"
                    >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                        Importar CSV
                    </button>
                    <button
                        onClick={() => {
                            const url = `${window.location.origin}/join/${projetoId}/invite`;
                            navigator.clipboard.writeText(url);
                            alert("Link do Portal de Autocadastro copiado!");
                        }}
                        className="px-4 py-2 bg-slate-100 text-slate-600 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-200 transition-all"
                    >
                        Link do Portal
                    </button>
                    <button
                        onClick={() => setIsScholarshipTypeModalOpen(true)}
                        className="px-4 py-2 bg-indigo-50 text-indigo-600 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-indigo-100 transition-all flex items-center gap-2"
                    >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                        Modalidades
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 gap-3">
                {filteredGroupedLinks.map(([personId, personLinks]) => {
                    const person = people[personId];
                    if (!person) return null;

                    const activeLink = personLinks.find(l => l.status === 'Ativo(a)' || l.status === 'Em regularização') || personLinks[0];
                    const isExpiring = activeLink.data_fim_prevista && isExpiringSoon(activeLink.data_fim_prevista);
                    const type = scholarshipTypes.find(t => t.id === activeLink.tipo_bolsa_id);

                    return (
                        <div key={personId} className={`bg-white border ${isExpiring ? 'border-amber-300 ring-1 ring-amber-100' : 'border-slate-100'} rounded-2xl p-4 hover:shadow-md transition-all group overflow-hidden relative`}>
                            <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
                                <div 
                                    className="flex items-center gap-4 flex-1 cursor-pointer group/card min-w-0"
                                    onClick={() => setSelectedPersonIdForView(personId)}
                                >
                                    <div className="w-10 h-10 rounded-full bg-slate-50 flex items-center justify-center text-slate-400 font-black text-xs border border-slate-100 group-hover/card:bg-indigo-600 group-hover/card:text-white transition-all">
                                        {person.nome.charAt(0)}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2">
                                            <h4 className="text-sm font-black text-slate-800 truncate group-hover/card:text-indigo-600 transition-colors">{person.nome}</h4>
                                            <span className={`px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-widest ${
                                                activeLink.status === 'Ativo(a)' ? 'bg-emerald-100 text-emerald-700' :
                                                activeLink.status === 'Em regularização' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'
                                            }`}>
                                                {activeLink.status}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-3 mt-0.5">
                                            <span className="text-[10px] text-slate-400 font-bold">{person.cpf}</span>
                                            <span className="text-[10px] text-slate-300">•</span>
                                            <span className="text-[10px] text-slate-400 font-bold">{type?.nome_modalidade || 'Bolsa'}</span>
                                            <span className="text-[10px] text-slate-300">•</span>
                                            <span className="text-[10px] text-indigo-600 font-black">{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(activeLink.valor_bolsa_mensal_atual)}</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2 w-full lg:w-auto justify-end border-t lg:border-t-0 pt-3 lg:pt-0 border-slate-50">
                                    <button
                                        onClick={() => generateScholarshipForm(person, activeLink, project || undefined, type)}
                                        className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-slate-50 rounded-lg transition-all"
                                        title="Gerar Ficha"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                    </button>
                                    <button
                                        onClick={() => {
                                            setEditingLink(null);
                                            setSelectedPersonId(personId);
                                            setLinkForm({ status: 'Ativo(a)', percentual_recebimento: 100, projeto_id: projetoId, pessoa_id: personId });
                                            setIsLinkModalOpen(true);
                                        }}
                                        className="px-3 py-1.5 text-slate-500 hover:text-slate-800 text-[9px] font-black uppercase tracking-widest border border-slate-100 rounded-lg hover:bg-slate-50 transition-all"
                                    >
                                        Aditivo
                                    </button>
                                    <button
                                        onClick={() => {
                                            setEditingLink(activeLink);
                                            setLinkForm(activeLink);
                                            setIsLinkModalOpen(true);
                                        }}
                                        className="px-3 py-1.5 bg-slate-900 text-white text-[9px] font-black uppercase tracking-widest rounded-lg hover:bg-slate-800 transition-all shadow-sm"
                                    >
                                        Editar
                                    </button>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Modal for Link */}
            {isLinkModalOpen && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setIsLinkModalOpen(false)}></div>
                    <div className="bg-white w-full max-w-lg rounded-[2rem] shadow-2xl p-8 relative z-10">
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

            {/* Modal for Scholarship Types */}
            {isScholarshipTypeModalOpen && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setIsScholarshipTypeModalOpen(false)}></div>
                    <div className="bg-white w-full max-w-2xl rounded-[2rem] shadow-2xl p-8 relative z-10">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-xl font-black text-slate-900">Configurar Modalidades de Bolsa</h3>
                            <button onClick={() => setIsScholarshipTypeModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                        
                        <div className="space-y-6">
                            {/* Add New Type Form */}
                            <div className="bg-slate-50 p-6 rounded-2xl border border-slate-100 flex flex-col md:flex-row gap-4 items-end">
                                <div className="flex-1 space-y-2">
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Nome da Modalidade</label>
                                    <input 
                                        type="text"
                                        placeholder="Ex: BPIG-II"
                                        value={newTypeForm.nome_modalidade || ''}
                                        onChange={e => setNewTypeForm({...newTypeForm, nome_modalidade: e.target.value})}
                                        className="w-full p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700 bg-white"
                                    />
                                </div>
                                <div className="w-full md:w-48 space-y-2">
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Valor Integral (100%)</label>
                                    <input 
                                        type="number"
                                        placeholder="Ex: 1500"
                                        value={newTypeForm.valor_integral || ''}
                                        onChange={e => setNewTypeForm({...newTypeForm, valor_integral: Number(e.target.value)})}
                                        className="w-full p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700 bg-white"
                                    />
                                </div>
                                <button 
                                    onClick={async () => {
                                        if(!newTypeForm.nome_modalidade || !newTypeForm.valor_integral) return;
                                        await addDoc(collection(db, 'tipos_bolsa'), newTypeForm);
                                        setNewTypeForm({});
                                    }}
                                    className="bg-indigo-600 text-white px-6 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200"
                                >
                                    Adicionar
                                </button>
                            </div>

                            {/* List of Types */}
                            <div className="max-h-[300px] overflow-y-auto space-y-2 pr-2">
                                {scholarshipTypes.map(t => (
                                    <div key={t.id} className="flex items-center justify-between p-4 bg-white border border-slate-100 rounded-xl hover:border-indigo-100 transition-all group">
                                        <div>
                                            <p className="font-black text-slate-800">{t.nome_modalidade}</p>
                                            <p className="text-xs text-slate-400 font-bold">{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(t.valor_integral)} <span className="text-slate-300 font-normal">/ mês integral</span></p>
                                        </div>
                                        <button 
                                            onClick={async () => {
                                                if(confirm("Deseja remover esta modalidade?")) {
                                                    // Logic to delete would go here
                                                    alert("Funcionalidade de exclusão desativada para evitar inconsistências em vínculos existentes.");
                                                }
                                            }}
                                            className="p-2 text-slate-300 hover:text-red-500 transition-colors"
                                        >
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Modal for Person Detail */}
            {selectedPersonIdForView && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={() => setSelectedPersonIdForView(null)}></div>
                    <div className="bg-slate-50 w-full max-w-4xl max-h-[90vh] rounded-[2.5rem] shadow-2xl flex flex-col md:flex-row overflow-hidden relative z-10">
                        {/* Sidebar: Profile Summary */}
                        <div className="w-full md:w-80 bg-white border-r border-slate-200 p-8 flex flex-col">
                            <div className="flex flex-col items-center text-center space-y-4 mb-8">
                                <div className="w-24 h-24 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 font-black text-3xl border-4 border-slate-50 shadow-inner">
                                    {people[selectedPersonIdForView]?.nome.charAt(0)}
                                </div>
                                <div>
                                    <h3 className="text-xl font-black text-slate-900 leading-tight">{people[selectedPersonIdForView]?.nome}</h3>
                                    <p className="text-xs font-bold text-indigo-600 uppercase tracking-widest mt-1">Bolsista</p>
                                </div>
                            </div>

                            <div className="space-y-4 flex-1">
                                <div className="bg-slate-50 p-4 rounded-2xl">
                                    <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Documentação</p>
                                    <p className="text-xs font-bold text-slate-700">CPF: <span className="font-medium">{people[selectedPersonIdForView]?.cpf}</span></p>
                                    <p className="text-xs font-bold text-slate-700">RG: <span className="font-medium">{people[selectedPersonIdForView]?.rg}</span></p>
                                </div>
                                <div className="bg-slate-50 p-4 rounded-2xl">
                                    <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Contato</p>
                                    <p className="text-xs font-bold text-slate-700 truncate">{people[selectedPersonIdForView]?.email}</p>
                                    <p className="text-xs font-bold text-slate-700 mt-1">{people[selectedPersonIdForView]?.telefone}</p>
                                </div>
                                <div className="bg-slate-50 p-4 rounded-2xl">
                                    <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Acadêmico</p>
                                    <p className="text-xs font-bold text-slate-700">{people[selectedPersonIdForView]?.campus || 'Campus não inf.'}</p>
                                    <p className="text-xs text-slate-500 font-medium line-clamp-1">{people[selectedPersonIdForView]?.curso || 'Curso não inf.'}</p>
                                </div>
                            </div>

                            <button
                                onClick={() => setSelectedPersonIdForView(null)}
                                className="w-full mt-6 py-3 bg-slate-900 text-white rounded-xl text-xs font-black uppercase tracking-widest hover:bg-slate-800 transition-all shadow-lg"
                            >
                                Fechar
                            </button>
                        </div>

                        {/* Main Content: Info & Timeline */}
                        <div className="flex-1 overflow-y-auto p-10 space-y-8">
                            <div>
                                <h4 className="text-lg font-black text-slate-800 mb-4 flex items-center gap-2">
                                   <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
                                   Dados Bancários e Endereço
                                </h4>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm">
                                        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Conta para Recebimento</p>
                                        <div className="space-y-1">
                                            <p className="text-xs font-bold text-slate-800">Banco: <span className="font-medium">{people[selectedPersonIdForView]?.dados_bancarios?.banco}</span></p>
                                            <p className="text-xs font-bold text-slate-800">Agência: <span className="font-medium">{people[selectedPersonIdForView]?.dados_bancarios?.agencia}</span></p>
                                            <p className="text-xs font-bold text-slate-800">Conta: <span className="font-medium">{people[selectedPersonIdForView]?.dados_bancarios?.conta}</span></p>
                                        </div>
                                    </div>
                                    <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm">
                                        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Endereço Residencial</p>
                                        <p className="text-xs font-medium text-slate-600 leading-relaxed">{people[selectedPersonIdForView]?.endereco || 'Endereço não cadastrado.'}</p>
                                    </div>
                                </div>
                            </div>

                            <div>
                                <h4 className="text-lg font-black text-slate-800 mb-4 flex items-center gap-2">
                                   <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                   Histórico de Vínculos no Projeto
                                </h4>
                                <div className="space-y-3">
                                    {groupedLinks[selectedPersonIdForView]?.map(link => {
                                        const type = scholarshipTypes.find(t => t.id === link.tipo_bolsa_id);
                                        return (
                                            <div key={link.id} className="bg-white border border-slate-200 p-5 rounded-3xl flex items-center justify-between shadow-sm hover:border-indigo-200 transition-colors">
                                                <div className="flex items-center gap-4">
                                                    <div className={`w-3 h-3 rounded-full ${
                                                        link.status === 'Ativo(a)' ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)]' :
                                                        link.status === 'Em regularização' ? 'bg-amber-500' : 'bg-slate-300'
                                                    }`}></div>
                                                    <div>
                                                        <p className="text-sm font-black text-slate-800">
                                                            {type?.nome_modalidade || 'Bolsa'} 
                                                            <span className="text-slate-400 font-bold ml-2">({link.percentual_recebimento}%)</span>
                                                        </p>
                                                        <p className="text-[10px] text-slate-500 font-bold mt-0.5">
                                                            📅 {new Date(link.data_inicio).toLocaleDateString('pt-BR')} — {link.data_fim_prevista ? new Date(link.data_fim_prevista).toLocaleDateString('pt-BR') : 'Indefinido'}
                                                        </p>
                                                    </div>
                                                </div>
                                                <div className="text-right">
                                                    <p className="text-sm font-black text-indigo-600">
                                                        {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(link.valor_bolsa_mensal_atual)}
                                                    </p>
                                                    <p className="text-[8px] font-black uppercase tracking-widest text-slate-400 mt-1">{link.status}</p>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            {people[selectedPersonIdForView]?.lattes && (
                                <div className="pt-4">
                                    <a 
                                        href={people[selectedPersonIdForView]?.lattes} 
                                        target="_blank" 
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-2 text-xs font-black text-indigo-600 hover:text-indigo-700 uppercase tracking-widest bg-indigo-50 px-4 py-2 rounded-xl transition-all"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                        Acessar Currículo Lattes
                                    </a>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
