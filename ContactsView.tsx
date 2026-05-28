import React, { useState, useEffect } from 'react';
import { collection, query, onSnapshot, addDoc, updateDoc, doc, deleteDoc, orderBy, where } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from './firebase';
import { PerfilPessoa, InteracaoPessoa } from './types';
import { navigateWithinApp } from './src/utils/internalNavigation';

interface ContactsViewProps {
    isDark?: boolean;
}

const ContactsView: React.FC<ContactsViewProps> = ({ isDark = false }) => {
    const [contacts, setContacts] = useState<PerfilPessoa[]>([]);
    const [selectedContact, setSelectedContact] = useState<PerfilPessoa | null>(null);
    const [timeline, setTimeline] = useState<InteracaoPessoa[]>([]);
    
    // Auto-select contact from URL
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const contactId = params.get('contactId');
        if (contactId && contacts.length > 0) {
            const found = contacts.find(c => c.id === contactId);
            if (found) setSelectedContact(found);
        }
    }, [contacts]);

    // UI States
    const [filterTag, setFilterTag] = useState<string>('todos');
    const [searchTerm, setSearchTerm] = useState<string>('');
    const [isSyncing, setIsSyncing] = useState<boolean>(false);
    const [syncStats, setSyncStats] = useState<any>(null);
    const [showSyncModal, setShowSyncModal] = useState<boolean>(false);
    
    // Merge & Summary States
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [isMerging, setIsMerging] = useState<boolean>(false);
    const [showMergeModal, setShowMergeModal] = useState<boolean>(false);
    const [primaryMergeId, setPrimaryMergeId] = useState<string>('');
    const [isGeneratingSummary, setIsGeneratingSummary] = useState<boolean>(false);
    
    // Add/Edit Modal
    const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
    const [editingContact, setEditingContact] = useState<PerfilPessoa | null>(null);
    const [formState, setFormState] = useState<Partial<PerfilPessoa>>({
        nome: '',
        email: '',
        telefone: '',
        observacoes: '',
        tags: []
    });

    // Theme Class helper
    const themeClass = {
        bg: isDark ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-800',
        card: isDark ? 'bg-slate-900 border-slate-800 text-white hover:bg-slate-850' : 'bg-white border-slate-100 text-slate-800 hover:shadow-md',
        input: isDark ? 'bg-slate-800 border-slate-700 text-white focus:ring-indigo-500' : 'bg-slate-100 border-transparent text-slate-700 focus:ring-indigo-500',
        label: isDark ? 'text-slate-400' : 'text-slate-400',
        border: isDark ? 'border-slate-800' : 'border-slate-100',
        timelineLine: isDark ? 'bg-slate-800' : 'bg-slate-200',
        timelineDot: isDark ? 'bg-indigo-500 border-slate-900' : 'bg-indigo-600 border-white',
        textMuted: isDark ? 'text-slate-400' : 'text-slate-500',
        headerBg: isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100',
        modalBg: isDark ? 'bg-slate-900 border-slate-850' : 'bg-white border-slate-200'
    };

    // Real-time listener for perfil_pessoas
    useEffect(() => {
        const q = query(collection(db, 'perfil_pessoas'), orderBy('nome', 'asc'));
        const unsubscribe = onSnapshot(q, (snapshot) => {
            const list = snapshot.docs.map(d => ({ id: d.id, ...d.data() } as PerfilPessoa));
            setContacts(list);
            
            // Sync selected contact details if it changes in real-time
            if (selectedContact) {
                const updated = list.find(c => c.id === selectedContact.id);
                if (updated) setSelectedContact(updated);
            }
        });
        return () => unsubscribe();
    }, [selectedContact?.id]);

    // Real-time listener for interacoes_pessoas
    useEffect(() => {
        if (!selectedContact) {
            setTimeline([]);
            return;
        }

        const q = query(
            collection(db, 'interacoes_pessoas'),
            where('pessoa_id', '==', selectedContact.id)
        );
        
        const unsubscribe = onSnapshot(q, (snapshot) => {
            const list = snapshot.docs.map(d => ({ id: d.id, ...d.data() } as InteracaoPessoa));
            // Ordenar por data desc
            list.sort((a, b) => new Date(b.data).getTime() - new Date(a.data).getTime());
            setTimeline(list);
        });

        return () => unsubscribe();
    }, [selectedContact]);

    // Trigger Google sync
    const handleGoogleSync = async () => {
        setIsSyncing(true);
        setSyncStats(null);
        setShowSyncModal(true);
        try {
            const syncFn = httpsCallable(functions, 'sync_google_contacts');
            const result = await syncFn();
            const resData = result.data as any;
            if (resData.success) {
                setSyncStats(resData.stats);
            } else {
                alert("Erro na sincronização de contatos do Google.");
                setShowSyncModal(false);
            }
        } catch (err: any) {
            console.error(err);
            alert(`Erro na sincronização de contatos: ${err.message || err}`);
            setShowSyncModal(false);
        } finally {
            setIsSyncing(false);
        }
    };
    
    // Generate AI Summary based on interactions
    const handleGenerateSummary = async (contactId: string) => {
        setIsGeneratingSummary(true);
        try {
            const summaryFn = httpsCallable(functions, 'generate_contact_summary');
            const result = await summaryFn({ pessoa_id: contactId });
            const resData = result.data as any;
            if (resData.success) {
                // Update selected contact locally immediately
                setSelectedContact(prev => prev && prev.id === contactId ? { ...prev, resumo_ia: resData.resumo_ia } : prev);
            } else {
                alert("Erro ao gerar resumo por IA.");
            }
        } catch (err: any) {
            console.error(err);
            alert(`Erro ao chamar gerador de resumo: ${err.message || err}`);
        } finally {
            setIsGeneratingSummary(false);
        }
    };

    // Confirm Merging Contacts
    const handleConfirmMerge = async () => {
        if (!primaryMergeId) {
            alert("Selecione o contato principal.");
            return;
        }
        setIsMerging(true);
        try {
            const mergeFn = httpsCallable(functions, 'merge_contacts');
            const result = await mergeFn({
                primary_id: primaryMergeId,
                secondary_ids: selectedIds.filter(id => id !== primaryMergeId)
            });
            const resData = result.data as any;
            if (resData.success) {
                alert(resData.message);
                setSelectedIds([]);
                setShowMergeModal(false);
                
                // Clear selection and select the merged contact
                const mergedContact = contacts.find(c => c.id === primaryMergeId);
                if (mergedContact) {
                    setSelectedContact(mergedContact);
                } else {
                    setSelectedContact(null);
                }
            } else {
                alert("Erro ao realizar a mesclagem.");
            }
        } catch (err: any) {
            console.error(err);
            alert(`Erro ao mesclar: ${err.message || err}`);
        } finally {
            setIsMerging(false);
        }
    };

    // Save Contact (Create/Update)
    const handleSaveContact = async () => {
        if (!formState.nome) {
            alert('Por favor, informe ao menos o nome.');
            return;
        }

        const now = new Date().toISOString();
        const initials = (formState.nome || '')
            .split(/\s+/)
            .filter(Boolean)
            .map(part => part[0].toUpperCase())
            .join('')
            .slice(0, 2);
        const colors = ["bg-indigo-500", "bg-purple-500", "bg-pink-500", "bg-rose-500", "bg-amber-500", "bg-emerald-500", "bg-teal-500", "bg-cyan-500", "bg-sky-500", "bg-blue-500"];
        let avatarColor = formState.avatar_color;
        if (!avatarColor) {
            let hashVal = 0;
            for (let i = 0; i < (formState.nome || '').length; i++) hashVal += (formState.nome || '').charCodeAt(i);
            avatarColor = colors[hashVal % colors.length];
        }

        const payload = {
            nome: formState.nome,
            email: formState.email || '',
            telefone: formState.telefone || '',
            observacoes: formState.observacoes || '',
            tags: formState.tags || ['Contato'],
            origem: formState.origem || 'manual',
            avatar_color: avatarColor,
            avatar_initials: initials,
            data_atualizacao: now
        };

        try {
            if (editingContact) {
                await updateDoc(doc(db, 'perfil_pessoas', editingContact.id), payload);
            } else {
                const newPayload = {
                    ...payload,
                    data_criacao: now
                };
                await addDoc(collection(db, 'perfil_pessoas'), newPayload);
            }
            setIsModalOpen(false);
            setEditingContact(null);
            setFormState({ nome: '', email: '', telefone: '', observacoes: '', tags: [] });
        } catch (err) {
            console.error(err);
            alert('Erro ao salvar contato.');
        }
    };

    // Delete Contact
    const handleDeleteContact = async (contact: PerfilPessoa) => {
        if (confirm(`Deseja realmente remover o contato de "${contact.nome}"? Isso removerá o cadastro, mas o histórico de interações permanecerá guardado.`)) {
            try {
                await deleteDoc(doc(db, 'perfil_pessoas', contact.id));
                if (selectedContact?.id === contact.id) {
                    setSelectedContact(null);
                }
            } catch (err) {
                console.error(err);
                alert('Erro ao excluir contato.');
            }
        }
    };

    // Open Modal for Add
    const openAddModal = () => {
        setEditingContact(null);
        setFormState({
            nome: '',
            email: '',
            telefone: '',
            observacoes: '',
            tags: ['Contato'],
            origem: 'manual'
        });
        setIsModalOpen(true);
    };

    // Open Modal for Edit
    const openEditModal = (contact: PerfilPessoa) => {
        setEditingContact(contact);
        setFormState({
            nome: contact.nome,
            email: contact.email || '',
            telefone: contact.telefone || '',
            observacoes: contact.observacoes || '',
            tags: contact.tags || [],
            origem: contact.origem || 'manual',
            avatar_color: contact.avatar_color
        });
        setIsModalOpen(true);
    };

    // Filters & Search
    const filteredContacts = contacts.filter(c => {
        // Tag filters
        if (filterTag === 'google' && !(c.tags || []).includes('Contatos do Google')) return false;
        if (filterTag === 'ia' && !(c.tags || []).includes('Extraído por IA')) return false;
        if (filterTag === 'copiloto' && !(c.tags || []).includes('Copiloto')) return false;

        // Search term
        const search = searchTerm.toLowerCase();
        return (
            c.nome.toLowerCase().includes(search) ||
            (c.email || '').toLowerCase().includes(search) ||
            (c.telefone || '').includes(search) ||
            (c.tags || []).some(t => t.toLowerCase().includes(search))
        );
    });
    return (
        <div className={`p-8 space-y-6 ${isDark ? 'bg-[#0f1724]' : ''}`}>
            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h3 className={`text-xl font-black ${isDark ? 'text-white' : 'text-slate-800'}`}>Contatos e Histórico Inteligente</h3>
                    <p className={`text-xs font-medium mt-1 font-mono ${isDark ? 'text-slate-400' : 'text-slate-550'}`}>
                        Catalogador inteligente de nomes mencionadas em ações de trabalho integrado ao Google Contacts.
                    </p>
                </div>
                <div className="flex flex-wrap gap-2 w-full md:w-auto">
                    <button
                        onClick={handleGoogleSync}
                        className={`px-4 py-2 border rounded-none text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2 font-mono ${
                            isDark ? 'bg-slate-850 border-border-grid text-indigo-400 hover:bg-slate-800' : 'bg-indigo-50 border-indigo-100 text-indigo-600 hover:bg-indigo-100'
                        }`}
                    >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H18" /></svg>
                        Sincronizar Google
                    </button>
                    <button
                        onClick={openAddModal}
                        className={`px-4 py-2 border rounded-none text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2 font-mono ${
                            isDark ? 'bg-white text-slate-900 border-white hover:bg-slate-100' : 'bg-slate-900 text-white border-slate-900 hover:bg-slate-800'
                        }`}
                    >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                        Adicionar Pessoa
                    </button>
                </div>
            </div>

            {/* Filter and Search Bar */}
            <div className="flex flex-col md:flex-row gap-4 items-stretch md:items-center justify-between">
                <div className="flex flex-wrap gap-1.5">
                    {[
                        { id: 'todos', label: 'Todos' },
                        { id: 'google', label: 'Contatos Google' },
                        { id: 'ia', label: 'Extraídos por IA' },
                        { id: 'copiloto', label: 'Mencionados no Copiloto' }
                    ].map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setFilterTag(tab.id)}
                            className={`px-4 py-1.5 border rounded-none text-[10px] font-black uppercase tracking-widest transition-all font-mono ${
                                filterTag === tab.id
                                    ? isDark ? 'bg-white text-slate-900 border-white' : 'bg-slate-900 text-white border-slate-900'
                                    : isDark ? 'bg-slate-800/80 border-border-grid text-slate-400 hover:bg-slate-700/80 hover:text-white' : 'bg-slate-100 border-transparent text-slate-500 hover:bg-slate-200/60'
                            }`}
                        >
                            {tab.label}
                        </button>
                    ))}
                </div>
                <div className="relative">
                    <svg className={`absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-slate-500' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                    <input
                        type="text"
                        placeholder="Pesquisar por nome ou e-mail..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className={`pl-10 pr-4 py-2 border rounded-none text-xs font-bold font-mono outline-none focus:ring-1 focus:ring-primary-tactile w-full md:w-64 transition-all ${
                            isDark ? 'bg-slate-800/80 border-border-grid text-white placeholder:text-slate-500' : 'bg-slate-100 border-transparent text-slate-750 placeholder:text-slate-400'
                        }`}
                    />
                </div>
            </div>

            {/* Main Content Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                {/* Left: Contact List */}
                <div className="lg:col-span-3 space-y-3 max-h-[65vh] overflow-y-auto pr-1">
                    {filteredContacts.length === 0 ? (
                        <div className={`p-12 text-center border border-dashed rounded-none font-mono ${isDark ? 'border-border-grid bg-slate-900/40 text-slate-550' : 'border-slate-200 bg-slate-50 text-slate-400'}`}>
                            <p className="text-sm font-bold">Nenhum contato encontrado.</p>
                        </div>
                    ) : (
                        filteredContacts.map(contact => {
                            const isSelected = selectedContact?.id === contact.id;
                            const isChecked = selectedIds.includes(contact.id);
                            return (
                                <div
                                    key={contact.id}
                                    onClick={() => setSelectedContact(contact)}
                                    className={`border rounded-none p-4 transition-all duration-200 cursor-pointer flex items-center justify-between font-mono ${
                                        isSelected 
                                            ? isDark ? 'bg-slate-800 border-white text-white shadow-lg' : 'bg-slate-900 border-slate-900 text-white shadow-lg' 
                                            : isDark ? 'bg-slate-900/40 border-border-grid text-slate-200 hover:bg-slate-800/60 hover:border-slate-700' : 'bg-white border-slate-100 text-slate-800 hover:shadow-md'
                                    }`}
                                >
                                    <div className="flex items-center gap-3.5 min-w-0">
                                        <input
                                            type="checkbox"
                                            checked={isChecked}
                                            onChange={(e) => {
                                                e.stopPropagation();
                                                if (isChecked) {
                                                    setSelectedIds(prev => prev.filter(id => id !== contact.id));
                                                } else {
                                                    setSelectedIds(prev => [...prev, contact.id]);
                                                }
                                            }}
                                            className={`h-4.5 w-4.5 cursor-pointer accent-indigo-600 rounded-none border transition-all ${
                                                isDark ? 'border-slate-750 bg-slate-850' : 'border-slate-300 bg-white'
                                            }`}
                                        />
                                        <div className={`w-10 h-10 rounded-none flex items-center justify-center font-black text-xs text-white ${contact.avatar_color || 'bg-indigo-500'}`}>
                                            {contact.avatar_initials || contact.nome.charAt(0).toUpperCase()}
                                        </div>
                                        <div className="min-w-0">
                                            <h4 className="text-sm font-black truncate">{contact.nome}</h4>
                                            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-1">
                                                {contact.email && (
                                                    <span className={`text-[10px] truncate ${isSelected ? 'text-slate-300' : isDark ? 'text-slate-400' : 'text-slate-500'} font-bold`}>
                                                        {contact.email}
                                                    </span>
                                                )}
                                                {contact.email && contact.telefone && <span className="text-[10px] text-slate-350">•</span>}
                                                {contact.telefone && (
                                                    <span className={`text-[10px] truncate ${isSelected ? 'text-slate-300' : isDark ? 'text-slate-400' : 'text-slate-500'} font-bold`}>
                                                        {contact.telefone}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {/* Tags */}
                                        <div className="hidden sm:flex flex-wrap gap-1">
                                            {(contact.tags || []).slice(0, 2).map((t, idx) => (
                                                <span 
                                                    key={idx} 
                                                    className={`px-2 py-0.5 rounded-none text-[8px] font-black uppercase tracking-widest ${
                                                        isSelected
                                                            ? 'bg-white/20 text-white'
                                                            : t === 'Contatos do Google' ? isDark ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-900/50' : 'bg-emerald-50 text-emerald-700' :
                                                              t === 'Extraído por IA' ? isDark ? 'bg-amber-950/80 text-amber-400 border border-amber-900/50' : 'bg-amber-50 text-amber-700' : 
                                                              isDark ? 'bg-slate-800 text-slate-400 border border-slate-700' : 'bg-slate-100 text-slate-500'
                                                    }`}
                                                >
                                                    {t}
                                                </span>
                                            ))}
                                            {(contact.tags || []).length > 2 && (
                                                <span className={`px-2 py-0.5 rounded-none text-[8px] font-black ${isSelected ? 'bg-white/20 text-white' : isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-100 text-slate-400'}`}>
                                                    +{(contact.tags || []).length - 2}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>

                {/* Right: Timeline & Contact Details Panel */}
                <div className="lg:col-span-2">
                    {!selectedContact ? (
                        <div className={`border rounded-none p-12 text-center h-full flex flex-col justify-center items-center font-mono ${
                            isDark ? 'bg-slate-900/40 border-border-grid' : 'bg-slate-50 border-slate-100'
                        }`}>
                            <svg className={`w-10 h-10 mb-4 ${isDark ? 'text-slate-750' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                            <h4 className={`text-sm font-black ${isDark ? 'text-slate-300' : 'text-slate-800'}`}>Nenhum contato selecionado</h4>
                            <p className={`text-xs mt-1 max-w-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                Selecione um contato da lista para ver informações cadastrais completas e linha do tempo de interações.
                            </p>
                        </div>
                    ) : (
                        <div className={`border rounded-none p-6 font-mono space-y-6 ${
                            isDark ? 'bg-slate-900/40 border-border-grid' : 'bg-white border-slate-100 shadow-sm'
                        }`}>
                            {/* Panel Header */}
                            <div className="flex items-start justify-between">
                                <div className="flex items-center gap-4">
                                    <div className={`w-12 h-12 rounded-none flex items-center justify-center font-black text-sm text-white ${selectedContact.avatar_color || 'bg-indigo-500'}`}>
                                        {selectedContact.avatar_initials || selectedContact.nome.charAt(0).toUpperCase()}
                                    </div>
                                    <div>
                                        <h4 className={`text-base font-black leading-snug ${isDark ? 'text-white' : 'text-slate-900'}`}>{selectedContact.nome}</h4>
                                        <p className={`text-[10px] font-bold uppercase tracking-widest mt-0.5 ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                            Origem: {selectedContact.origem === 'google_contacts' ? 'Google Contacts' : selectedContact.origem === 'extracao_ia' ? 'IA Extraído' : 'Manual'}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex gap-1">
                                    <button 
                                        onClick={() => openEditModal(selectedContact)}
                                        className={`p-1.5 rounded-none border transition-all ${isDark ? 'text-slate-400 hover:text-indigo-405 border-transparent hover:border-slate-800 hover:bg-slate-850' : 'text-slate-400 hover:text-indigo-600 border-transparent hover:border-slate-200 hover:bg-slate-50'}`}
                                        title="Editar Contato"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                    </button>
                                    <button 
                                        onClick={() => handleDeleteContact(selectedContact)}
                                        className={`p-1.5 rounded-none border transition-all ${isDark ? 'text-slate-400 hover:text-rose-450 border-transparent hover:border-slate-800 hover:bg-slate-850' : 'text-slate-400 hover:text-rose-600 border-transparent hover:border-slate-200 hover:bg-slate-50'}`}
                                        title="Excluir Contato"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                    </button>
                                </div>
                            </div>

                            {/* Contact Details Fields */}
                            <div className={`grid grid-cols-1 gap-3 p-4 rounded-none text-xs border ${isDark ? 'bg-slate-900/60 border-slate-800' : 'bg-slate-50 border-slate-100'}`}>
                                {selectedContact.email && (
                                    <div className="flex justify-between">
                                        <span className={`font-bold uppercase tracking-widest text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>E-mail</span>
                                        <span className={`font-black ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>{selectedContact.email}</span>
                                    </div>
                                )}
                                {selectedContact.telefone && (
                                    <div className="flex justify-between">
                                        <span className={`font-bold uppercase tracking-widest text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Telefone</span>
                                        <span className={`font-black ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>{selectedContact.telefone}</span>
                                    </div>
                                )}
                                {selectedContact.cpf && (
                                    <div className="flex justify-between">
                                        <span className={`font-bold uppercase tracking-widest text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>CPF</span>
                                        <span className={`font-black ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>{selectedContact.cpf}</span>
                                    </div>
                                )}
                                {selectedContact.observacoes && (
                                    <div className={`pt-2 border-t flex flex-col gap-1 ${isDark ? 'border-slate-800' : 'border-slate-100'}`}>
                                        <span className={`font-bold uppercase tracking-widest text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Observações / Notas</span>
                                        <p className={`text-[11px] font-bold leading-relaxed p-2.5 rounded-none border ${
                                            isDark ? 'bg-slate-900 border-slate-800 text-slate-350' : 'bg-white border-slate-100 text-slate-600'
                                        }`}>{selectedContact.observacoes}</p>
                                    </div>
                                )}
                                
                                {/* Resumo de IA */}
                                <div className={`pt-2 border-t flex flex-col gap-1 ${isDark ? 'border-slate-800' : 'border-slate-100'}`}>
                                    <div className="flex items-center justify-between">
                                        <span className={`font-bold uppercase tracking-widest text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'} flex items-center gap-1`}>
                                            <svg className="w-3.5 h-3.5 text-amber-500 animate-pulse" fill="currentColor" viewBox="0 0 20 20">
                                                <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
                                            </svg>
                                            Resumo da IA (Histórico)
                                        </span>
                                        {selectedContact.resumo_ia && (
                                            <button
                                                onClick={() => handleGenerateSummary(selectedContact.id)}
                                                className={`text-[9px] font-black uppercase tracking-wider underline hover:no-underline ${
                                                    isDark ? 'text-indigo-400 hover:text-indigo-300' : 'text-indigo-650 hover:text-indigo-850'
                                                }`}
                                                disabled={isGeneratingSummary}
                                            >
                                                {isGeneratingSummary ? 'Gerando...' : 'Regerar'}
                                            </button>
                                        )}
                                    </div>
                                    {selectedContact.resumo_ia ? (
                                        <p className={`text-[11px] font-bold italic leading-relaxed p-2.5 rounded-none border border-dashed ${
                                            isDark ? 'bg-slate-900 border-slate-800 text-slate-350' : 'bg-white border-slate-150 text-slate-650'
                                        }`}>
                                            "{selectedContact.resumo_ia}"
                                        </p>
                                    ) : (
                                        <div className="pt-1">
                                            <button
                                                onClick={() => handleGenerateSummary(selectedContact.id)}
                                                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-750 disabled:bg-indigo-850 text-white font-black text-[9px] uppercase tracking-wider rounded-none border border-indigo-500 flex items-center gap-1 transition-all"
                                                disabled={isGeneratingSummary}
                                            >
                                                {isGeneratingSummary ? (
                                                    <>
                                                        <svg className="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                                        </svg>
                                                        Gerando...
                                                    </>
                                                ) : (
                                                    <>
                                                        <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                                        </svg>
                                                        Gerar Resumo por IA
                                                    </>
                                                )}
                                            </button>
                                        </div>
                                    )}
                                </div>

                                <div className={`pt-2 border-t flex flex-wrap gap-1 ${isDark ? 'border-slate-800' : 'border-slate-100'}`}>
                                    {(selectedContact.tags || []).map((t, idx) => (
                                        <span key={idx} className={`px-2.5 py-0.5 rounded-none text-[9px] font-black uppercase tracking-widest border ${
                                            isDark ? 'bg-slate-800 border-slate-700 text-slate-400' : 'bg-slate-200 text-slate-650 border-slate-300/45'
                                        }`}>
                                            {t}
                                        </span>
                                    ))}
                                </div>
                            </div>

                            {/* Interactions Timeline */}
                            <div className="space-y-4">
                                <h4 className={`text-xs font-black uppercase tracking-[0.2em] border-b-2 pb-2 ${isDark ? 'text-white border-white' : 'text-slate-900 border-slate-900'}`}>
                                    Linha do Tempo de Interações
                                </h4>
                                
                                {timeline.length === 0 ? (
                                    <div className={`p-8 text-center text-xs font-bold rounded-none border ${isDark ? 'bg-slate-900/20 border-slate-800 text-slate-500' : 'bg-slate-50 border-slate-100 text-slate-400'}`}>
                                        Nenhuma interação registrada ainda.
                                    </div>
                                ) : (
                                    <div className={`relative pl-6 space-y-6 before:content-[''] before:absolute before:left-2 before:top-2 before:bottom-2 before:w-[2px] ${isDark ? 'before:bg-slate-800' : 'before:bg-slate-150'}`}>
                                        {timeline.map((item, idx) => {
                                            const formattedDate = new Date(item.data).toLocaleDateString('pt-BR', {
                                                day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
                                            });
                                            return (
                                                <div key={item.id || idx} className="relative">
                                                    <div className={`absolute -left-[23px] top-[3px] w-3 h-3 rounded-none border-[3px] ${item.tipo === 'mencao_copiloto' ? 'bg-blue-400 border-slate-900' : isDark ? 'bg-indigo-400 border-slate-900' : 'bg-indigo-600 border-white'}`} />
                                                    <div>
                                                        <div className="flex items-center justify-between gap-2">
                                                            <div className="flex items-center gap-2">
                                                                <span className={`text-[9px] font-mono font-black uppercase tracking-wider ${isDark ? 'text-indigo-450' : 'text-indigo-600'}`}>{formattedDate}</span>
                                                                {item.tipo === 'mencao_copiloto' && (
                                                                    <span className="text-[8px] bg-blue-500/10 text-blue-500 px-1.5 py-0.5 rounded-none font-black uppercase tracking-widest">IA</span>
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-2">
                                                                {item.sessao_copiloto_id && (
                                                                     <button
                                                                        onClick={() => {
                                                                            navigateWithinApp(`/copiloto?sessionId=${item.sessao_copiloto_id}`);
                                                                        }}
                                                                        className={`text-[9px] font-black uppercase tracking-widest flex items-center gap-1 ${
                                                                            isDark ? 'text-blue-400 hover:text-blue-300' : 'text-blue-600 hover:text-blue-800 hover:underline'
                                                                        }`}
                                                                    >
                                                                        Sessão ↗
                                                                    </button>
                                                                )}
                                                                {item.tarefa_id && (
                                                                    <a
                                                                        href={item.link_origem || `/tarefas?id=${item.tarefa_id}`}
                                                                        onClick={(e) => {
                                                                            e.preventDefault();
                                                                            navigateWithinApp(`/tarefas?task=${item.tarefa_id}`);
                                                                        }}
                                                                        className={`text-[9px] font-black uppercase tracking-widest flex items-center gap-1 ${
                                                                            isDark ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-800 hover:underline'
                                                                        }`}
                                                                    >
                                                                        Ação ↗
                                                                    </a>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <p className={`text-[11px] font-bold mt-1 leading-relaxed ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                                                            {item.descricao}
                                                        </p>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Syncing Loading & Stats Modal */}
            {showSyncModal && (
                <div className="fixed inset-0 z-[300] flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={() => !isSyncing && setShowSyncModal(false)}></div>
                    <div className={`w-full max-w-sm rounded-none border shadow-2xl p-8 relative z-10 text-center space-y-4 font-mono ${
                        isDark ? 'bg-slate-900 border-border-grid text-white' : 'bg-white border-slate-200 text-slate-800'
                    }`}>
                        {isSyncing ? (
                            <>
                                <div className="flex justify-center py-6">
                                    <div className="w-12 h-12 border-4 border-indigo-650 border-t-transparent rounded-none animate-spin"></div>
                                </div>
                                <h4 className="text-sm font-black">Sincronizando com Google Contacts...</h4>
                                <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                    Buscando e cruzando cadastros de contatos. Aguarde um instante.
                                </p>
                            </>
                        ) : (
                            <>
                                <div className="flex justify-center text-emerald-500 py-3">
                                    <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                </div>
                                <h4 className="text-base font-black">Sincronização Concluída!</h4>
                                {syncStats && (
                                    <div className={`grid grid-cols-2 gap-3 p-4 rounded-none text-xs font-bold mt-3 text-left border ${
                                        isDark ? 'bg-slate-950 border-slate-850 text-slate-450' : 'bg-slate-50 border-slate-100 text-slate-600'
                                    }`}>
                                        <div className="flex flex-col">
                                            <span className="text-[9px] uppercase tracking-widest opacity-60">Contatos Importados</span>
                                            <span className="text-lg font-black text-indigo-500">{syncStats.added || 0}</span>
                                        </div>
                                        <div className="flex flex-col">
                                            <span className="text-[9px] uppercase tracking-widest opacity-60">Contatos Vinculados</span>
                                            <span className="text-lg font-black text-emerald-500">{syncStats.merged || 0}</span>
                                        </div>
                                    </div>
                                )}
                                <button
                                    onClick={() => setShowSyncModal(false)}
                                    className={`w-full mt-6 py-3 rounded-none text-[10px] font-black uppercase tracking-widest transition-all border ${
                                        isDark ? 'bg-white text-slate-900 border-white hover:bg-slate-100' : 'bg-slate-900 text-white border-slate-900 hover:bg-slate-800'
                                    }`}
                                >
                                    Fechar
                                </button>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* Manual Add/Edit Modal */}
            {isModalOpen && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={() => setIsModalOpen(false)}></div>
                    <div className={`w-full max-w-md rounded-none border shadow-2xl p-8 relative z-10 font-mono ${
                        isDark ? 'bg-slate-900 border-border-grid text-white' : 'bg-white border-slate-200 text-slate-800'
                    }`}>
                        <h3 className="text-lg font-black mb-6 border-b pb-2 border-border-grid">
                            {editingContact ? 'Editar Contato' : 'Adicionar Contato'}
                        </h3>
                        <div className="space-y-4">
                            <div>
                                <label className={`text-[10px] font-black uppercase tracking-widest ml-1 ${isDark ? 'text-slate-550' : 'text-slate-400'}`}>Nome Completo</label>
                                <input
                                    type="text"
                                    value={formState.nome}
                                    onChange={e => setFormState({...formState, nome: e.target.value})}
                                    className={`w-full mt-1 p-3 rounded-none border outline-none font-bold text-xs ${
                                        isDark ? 'bg-slate-950 border-slate-800 text-white focus:border-white' : 'bg-white border-slate-200 text-slate-700 focus:border-slate-900'
                                    }`}
                                    placeholder="Ex: João da Silva"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className={`text-[10px] font-black uppercase tracking-widest ml-1 ${isDark ? 'text-slate-555' : 'text-slate-400'}`}>E-mail</label>
                                    <input
                                        type="email"
                                        value={formState.email}
                                        onChange={e => setFormState({...formState, email: e.target.value})}
                                        className={`w-full mt-1 p-3 rounded-none border outline-none font-bold text-xs ${
                                            isDark ? 'bg-slate-950 border-slate-800 text-white focus:border-white' : 'bg-white border-slate-200 text-slate-700 focus:border-slate-900'
                                        }`}
                                        placeholder="email@example.com"
                                    />
                                </div>
                                <div>
                                    <label className={`text-[10px] font-black uppercase tracking-widest ml-1 ${isDark ? 'text-slate-555' : 'text-slate-400'}`}>Telefone</label>
                                    <input
                                        type="text"
                                        value={formState.telefone}
                                        onChange={e => setFormState({...formState, telefone: e.target.value})}
                                        className={`w-full mt-1 p-3 rounded-none border outline-none font-bold text-xs ${
                                            isDark ? 'bg-slate-950 border-slate-800 text-white focus:border-white' : 'bg-white border-slate-200 text-slate-700 focus:border-slate-900'
                                        }`}
                                        placeholder="(27) 99999-9999"
                                    />
                                </div>
                            </div>
                            <div>
                                <label className={`text-[10px] font-black uppercase tracking-widest ml-1 ${isDark ? 'text-slate-555' : 'text-slate-400'}`}>Observações</label>
                                <textarea
                                    value={formState.observacoes}
                                    onChange={e => setFormState({...formState, observacoes: e.target.value})}
                                    rows={3}
                                    className={`w-full mt-1 p-3 rounded-none border outline-none font-bold text-xs resize-none ${
                                        isDark ? 'bg-slate-950 border-slate-800 text-white focus:border-white' : 'bg-white border-slate-200 text-slate-700 focus:border-slate-900'
                                    }`}
                                    placeholder="Notas adicionais sobre a pessoa..."
                                />
                            </div>
                            <div className="flex gap-2 justify-end pt-4">
                                <button
                                    onClick={() => setIsModalOpen(false)}
                                    className={`px-5 py-2.5 rounded-none text-[10px] font-black uppercase tracking-widest transition-all border ${
                                        isDark ? 'bg-slate-800 text-slate-350 border-border-grid hover:bg-slate-750' : 'bg-slate-100 text-slate-600 border-transparent hover:bg-slate-200'
                                    }`}
                                >
                                    Cancelar
                                </button>
                                <button
                                    onClick={handleSaveContact}
                                    className={`px-5 py-2.5 rounded-none text-[10px] font-black uppercase tracking-widest transition-all border ${
                                        isDark ? 'bg-white text-slate-900 border-white hover:bg-slate-100' : 'bg-slate-900 text-white border-slate-900 hover:bg-slate-800'
                                    }`}
                                >
                                    Salvar
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Merge Floating Action Bar */}
            {selectedIds.length >= 2 && (
                <div className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-6 px-6 py-4 border rounded-none shadow-2xl font-mono ${
                    isDark ? 'bg-slate-900 border-white text-white' : 'bg-slate-900 border-slate-950 text-white'
                }`}>
                    <div className="flex flex-col">
                        <span className="text-xs font-black uppercase tracking-wider">{selectedIds.length} Contatos Selecionados</span>
                        <span className="text-[10px] text-slate-400 font-bold">Unifique registros duplicados mesclando-os</span>
                    </div>
                    <div className="flex gap-2">
                        <button
                            onClick={() => setSelectedIds([])}
                            className="px-3 py-1.5 transition-all font-black text-xs uppercase tracking-wider rounded-none text-slate-400 hover:text-white"
                        >
                            Limpar
                        </button>
                        <button
                            onClick={() => {
                                // Default primary contact to the first selected one
                                setPrimaryMergeId(selectedIds[0]);
                                setShowMergeModal(true);
                            }}
                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-750 transition-all font-black text-xs uppercase tracking-wider rounded-none text-white border border-indigo-500"
                        >
                            Mesclar
                        </button>
                    </div>
                </div>
            )}

            {/* Merge Contacts Modal */}
            {showMergeModal && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className={`w-full max-w-md p-6 border rounded-none font-mono ${themeClass.modalBg}`}>
                        <div className="flex justify-between items-start mb-4">
                            <h3 className={`text-sm font-black uppercase tracking-[0.2em] ${isDark ? 'text-white' : 'text-slate-950'}`}>
                                Mesclar Contatos
                            </h3>
                            <button 
                                onClick={() => setShowMergeModal(false)}
                                className={`text-slate-400 hover:${isDark ? 'text-white' : 'text-slate-950'}`}
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                        
                        <p className={`text-xs mb-4 leading-relaxed ${themeClass.textMuted}`}>
                            Você selecionou <span className="font-black text-indigo-500">{selectedIds.length}</span> contatos para unificar. Escolha abaixo qual perfil será o **principal** (todas as interações e dados dos outros perfis serão migrados para ele):
                        </p>
                        
                        <div className="space-y-2 max-h-[40vh] overflow-y-auto mb-6 pr-1">
                            {contacts.filter(c => selectedIds.includes(c.id)).map(contact => (
                                <label 
                                    key={contact.id}
                                    className={`flex items-center gap-3 p-3 border cursor-pointer transition-all ${
                                        primaryMergeId === contact.id 
                                            ? isDark ? 'bg-slate-800 border-white text-white' : 'bg-slate-100 border-slate-900 text-slate-950'
                                            : isDark ? 'bg-slate-950 border-slate-850 text-slate-400 hover:bg-slate-900/60' : 'bg-slate-50 border-slate-150 text-slate-650 hover:bg-slate-100/60'
                                    }`}
                                >
                                    <input 
                                        type="radio" 
                                        name="primaryContact"
                                        checked={primaryMergeId === contact.id}
                                        onChange={() => setPrimaryMergeId(contact.id)}
                                        className="h-4 w-4 accent-indigo-650 cursor-pointer"
                                    />
                                    <div className="min-w-0">
                                        <h4 className="text-xs font-black truncate">{contact.nome}</h4>
                                        <p className="text-[10px] text-slate-400 truncate mt-0.5">
                                            {contact.email || 'Sem e-mail'} {contact.telefone ? `• ${contact.telefone}` : ''}
                                        </p>
                                    </div>
                                </label>
                            ))}
                        </div>
                        
                        <div className="flex justify-end gap-3 pt-3 border-t border-border-grid">
                            <button
                                onClick={() => setShowMergeModal(false)}
                                className={`px-4 py-2 border rounded-none font-black text-xs uppercase tracking-wider transition-all ${
                                    isDark ? 'border-slate-800 text-slate-400 hover:bg-slate-850 hover:text-white' : 'border-slate-200 text-slate-650 hover:bg-slate-50'
                                }`}
                                disabled={isMerging}
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleConfirmMerge}
                                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-750 disabled:bg-indigo-800 text-white font-black text-xs uppercase tracking-wider rounded-none border border-indigo-500 flex items-center gap-2"
                                disabled={isMerging || !primaryMergeId}
                            >
                                {isMerging ? 'Mesclando...' : 'Confirmar Mesclagem'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ContactsView;
