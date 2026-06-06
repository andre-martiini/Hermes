import React, { useState, useRef, useCallback } from 'react';
import { BaseConhecimento, ConhecimentoItem } from '../../types';

interface RAGBasesViewProps {
    bases: BaseConhecimento[];
    items: ConhecimentoItem[];
    onCreateBase: (nome: string) => Promise<void>;
    onUpdateBase: (id: string, updates: Partial<BaseConhecimento>) => Promise<void>;
    onDeleteBase: (id: string) => Promise<void>;
    onUploadFile: (file: File, baseId: string) => Promise<void>;
    onAddLink: (url: string, title: string, baseId: string) => Promise<void>;
    onDeleteItem: (id: string) => void;
    onVectorizeItem?: (id: string) => Promise<void>;
    showConfirm?: (title: string, message: string, onConfirm: () => void) => void;
    isDark?: boolean;
    onNavigateToOrigin?: (modulo: string, id: string) => void;
}

const COLOR_OPTIONS = [
    { label: 'Âmbar',         value: '#f59e0b' },
    { label: 'Laranja',       value: '#f97316' },
    { label: 'Vermelho',      value: '#ef4444' },
    { label: 'Rosa',          value: '#ec4899' },
    { label: 'Magenta',       value: '#d946ef' },
    { label: 'Roxo',          value: '#8b5cf6' },
    { label: 'Violeta',       value: '#7c3aed' },
    { label: 'Azul Índigo',   value: '#6366f1' },
    { label: 'Azul',          value: '#3b82f6' },
    { label: 'Azul Céu',      value: '#0ea5e9' },
    { label: 'Ciano',         value: '#06b6d4' },
    { label: 'Turquesa',      value: '#14b8a6' },
    { label: 'Verde',         value: '#10b981' },
    { label: 'Verde Lima',    value: '#84cc16' },
    { label: 'Lima',          value: '#a3e635' },
    { label: 'Amarelo',       value: '#eab308' },
    { label: 'Marrom',        value: '#a16207' },
    { label: 'Cinza Escuro',  value: '#374151' },
    { label: 'Cinza',         value: '#6b7280' },
    { label: 'Ardósia',       value: '#475569' },
];

const FileIcon: React.FC<{ tipo: string; isDark?: boolean }> = ({ tipo, isDark }) => {
    const t = (tipo || '').toLowerCase();
    const colorsLight: Record<string, string> = {
        'pdf': 'bg-rose-50 text-rose-600 border-rose-200',
        'doc': 'bg-blue-50 text-blue-600 border-blue-200',
        'docx': 'bg-blue-50 text-blue-600 border-blue-200',
        'xls': 'bg-emerald-50 text-emerald-600 border-emerald-200',
        'xlsx': 'bg-emerald-50 text-emerald-600 border-emerald-200',
        'link': 'bg-violet-50 text-violet-600 border-violet-200',
        'txt': 'bg-slate-50 text-slate-600 border-slate-200',
        'md': 'bg-slate-50 text-slate-600 border-slate-200',
    };
    const colorsDark: Record<string, string> = {
        'pdf': 'bg-rose-950/40 text-rose-400 border-rose-800/60',
        'doc': 'bg-blue-950/40 text-blue-400 border-blue-800/60',
        'docx': 'bg-blue-950/40 text-blue-400 border-blue-800/60',
        'xls': 'bg-emerald-950/40 text-emerald-400 border-emerald-800/60',
        'xlsx': 'bg-emerald-950/40 text-emerald-400 border-emerald-800/60',
        'link': 'bg-violet-950/40 text-violet-400 border-violet-800/60',
        'txt': 'bg-slate-800 text-slate-400 border-slate-700',
        'md': 'bg-slate-800 text-slate-400 border-slate-700',
    };
    const cls = isDark
        ? (colorsDark[t] || 'bg-slate-800 text-slate-400 border-slate-700')
        : (colorsLight[t] || 'bg-slate-50 text-slate-600 border-slate-200');
    return (
        <div className={`w-10 h-10 border flex items-center justify-center flex-shrink-0 font-mono font-black text-[9px] uppercase tracking-tighter ${cls}`}>
            {t === 'link' ? (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
            ) : t.substring(0, 3)}
        </div>
    );
};

const VectorBadge: React.FC<{ hasEmbedding: boolean; isDark?: boolean }> = ({ hasEmbedding, isDark }) => {
    const cls = hasEmbedding
        ? (isDark ? 'bg-emerald-950/40 text-emerald-400 border-emerald-800/60' : 'bg-emerald-50 text-emerald-600 border-emerald-200')
        : (isDark ? 'bg-slate-800 text-slate-500 border-slate-700' : 'bg-slate-50 text-slate-400 border-slate-200');
    const dotCls = hasEmbedding ? 'bg-emerald-500' : (isDark ? 'bg-slate-600' : 'bg-slate-300');
    return (
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 border font-mono text-[9px] font-black uppercase tracking-widest ${cls}`}>
            <div className={`w-1.5 h-1.5 ${dotCls}`} />
            {hasEmbedding ? 'Vetorizado' : 'Offline'}
        </span>
    );
};

export const RAGBasesView: React.FC<RAGBasesViewProps> = ({
    bases,
    items,
    onCreateBase,
    onUpdateBase,
    onDeleteBase,
    onUploadFile,
    onAddLink,
    onDeleteItem,
    onVectorizeItem,
    showConfirm,
    isDark = false,
    onNavigateToOrigin,
}) => {
    const [mobileView, setMobileView] = useState<'bases' | 'content'>('bases');
    const [selectedBaseId, setSelectedBaseId] = useState<string | null>(bases[0]?.id ?? null);
    const [isCreatingBase, setIsCreatingBase] = useState(false);
    const [newBaseName, setNewBaseName] = useState('');
    const [isDragging, setIsDragging] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [editingBase, setEditingBase] = useState<BaseConhecimento | null>(null);
    const [isAddLinkOpen, setIsAddLinkOpen] = useState(false);
    const [linkUrl, setLinkUrl] = useState('');
    const [linkTitle, setLinkTitle] = useState('');
    const [vectorizingId, setVectorizingId] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const selectedBase = bases.find(b => b.id === selectedBaseId) ?? null;

    const baseItems = items.filter(item =>
        item.base_id === selectedBaseId &&
        (searchTerm === '' ||
            item.titulo.toLowerCase().includes(searchTerm.toLowerCase()) ||
            (item.tags ?? []).some(t => t.toLowerCase().includes(searchTerm.toLowerCase())))
    );

    const handleCreateBase = async () => {
        const name = newBaseName.trim();
        if (!name) return;
        await onCreateBase(name);
        setNewBaseName('');
        setIsCreatingBase(false);
    };

    const handleFileDrop = useCallback(async (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        if (!selectedBaseId) return;
        const files = Array.from(e.dataTransfer.files);
        if (files.length === 0) return;
        setIsUploading(true);
        for (const file of files) {
            await onUploadFile(file, selectedBaseId);
        }
        setIsUploading(false);
    }, [selectedBaseId, onUploadFile]);

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!selectedBaseId) return;
        const files = Array.from(e.target.files ?? []);
        if (files.length === 0) return;
        setIsUploading(true);
        for (const file of files) {
            await onUploadFile(file, selectedBaseId);
        }
        setIsUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleAddLink = async () => {
        if (!selectedBaseId || !linkUrl.trim()) return;
        await onAddLink(linkUrl.trim(), linkTitle.trim() || linkUrl.trim(), selectedBaseId);
        setLinkUrl('');
        setLinkTitle('');
        setIsAddLinkOpen(false);
    };

    const handleDeleteItem = (id: string) => {
        if (showConfirm) {
            showConfirm('Remover documento', 'Tem certeza que deseja remover este documento da base?', () => onDeleteItem(id));
        } else {
            onDeleteItem(id);
        }
    };

    const handleDeleteBase = (base: BaseConhecimento) => {
        if (showConfirm) {
            showConfirm('Excluir Área Temática', `Excluir a área "${base.nome}"? Os documentos vinculados não serão excluídos.`, async () => {
                await onDeleteBase(base.id);
                if (selectedBaseId === base.id) setSelectedBaseId(bases.find(b => b.id !== base.id)?.id ?? null);
            });
        } else {
            onDeleteBase(base.id);
            if (selectedBaseId === base.id) setSelectedBaseId(null);
        }
    };

    return (
        <div className={`flex flex-col md:flex-row h-[100dvh] overflow-hidden ${isDark ? 'bg-slate-950 text-slate-100' : 'bg-[#f9f9f9] text-slate-900'}`}>
            {/* Sidebar */}
            <aside className={`w-full md:w-72 flex-shrink-0 border-r flex flex-col h-full ${mobileView === 'content' ? 'hidden md:flex' : 'flex'} ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                <div className={`p-6 border-b ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                    <div className="flex items-center gap-4 mb-4 md:hidden">
                        <button
                            onClick={() => window.history.back()}
                            className={`w-10 h-10 flex items-center justify-center border transition-colors ${isDark ? 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700' : 'border-slate-200 bg-white text-slate-900 hover:bg-slate-50'}`}
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                            </svg>
                        </button>
                        <p className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest">SAIR DO MÓDULO</p>
                    </div>
                    <div className="flex items-center gap-2 mb-1">
                        <div className="w-2 h-2 bg-slate-400"></div>
                        <p className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest">SYSTEM: ÁREAS TEMÁTICAS</p>
                    </div>
                    <h2 className={`text-sm font-mono font-black uppercase tracking-tight ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Conhecimento das Áreas</h2>
                </div>

                <nav className="flex-1 overflow-y-auto">
                    {bases.map((base, idx) => (
                        <button
                            key={base.id}
                            onClick={() => {
                                setSelectedBaseId(base.id);
                                setMobileView('content');
                            }}
                            className={`w-full flex items-center gap-3 px-6 py-4 border-b text-left transition-all group relative ${selectedBaseId === base.id ? (isDark ? 'bg-slate-800 border-slate-800' : 'bg-slate-50 border-slate-100') : (isDark ? 'border-slate-800/60 hover:bg-slate-800/40' : 'border-slate-100 hover:bg-slate-50/50')}`}
                        >
                            {selectedBaseId === base.id && (
                                <div className="absolute left-0 top-0 bottom-0 w-1" style={{ backgroundColor: base.cor || '#6b7280' }}></div>
                            )}
                            <div className="flex flex-col flex-1 min-w-0">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">ÁREA-{String(idx + 1).padStart(3, '0')}</span>
                                    <span className={`text-[10px] font-mono font-black ${selectedBaseId === base.id ? 'text-slate-600' : 'text-slate-400'}`}>
                                        ITEMS: {items.filter(i => i.base_id === base.id).length}
                                    </span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className={`text-sm font-mono font-black truncate uppercase tracking-tight ${selectedBaseId === base.id ? (isDark ? 'text-slate-100' : 'text-slate-900') : (isDark ? 'text-slate-400' : 'text-slate-600')}`}>
                                        {base.nome}
                                    </span>
                                </div>
                            </div>
                        </button>
                    ))}
                </nav>

                <div className={`p-4 border-t ${isDark ? 'border-slate-800 bg-slate-900/80' : 'border-slate-200 bg-slate-50'}`}>
                    {isCreatingBase ? (
                        <div className="flex flex-col gap-2">
                            <input
                                autoFocus
                                value={newBaseName}
                                onChange={e => setNewBaseName(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter') handleCreateBase(); if (e.key === 'Escape') setIsCreatingBase(false); }}
                                placeholder="NOME DA ÁREA..."
                                className={`w-full px-3 py-2 text-xs font-mono font-bold border rounded-none outline-none transition-colors ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-violet-400 placeholder:text-slate-500' : 'bg-white border-slate-200 text-slate-900 focus:border-violet-500 placeholder:text-slate-400'}`}
                            />
                            <div className="flex gap-2">
                                <button onClick={handleCreateBase} className={`flex-1 py-2 text-white rounded-none text-[10px] font-mono font-black uppercase tracking-widest transition-colors ${isDark ? 'bg-slate-600 hover:bg-slate-700' : 'bg-slate-900 hover:bg-black'}`}>Criar</button>
                                <button onClick={() => setIsCreatingBase(false)} className={`flex-1 py-2 border rounded-none text-[10px] font-mono font-black uppercase tracking-widest transition-colors ${isDark ? 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}>Cancelar</button>
                            </div>
                        </div>
                    ) : (
                        <button
                            onClick={() => setIsCreatingBase(true)}
                            className={`w-full flex items-center justify-center gap-2 px-3 py-3 border border-dashed transition-all text-[10px] font-mono font-black uppercase tracking-widest ${isDark ? 'border-slate-700 text-slate-400 hover:border-slate-400 hover:text-slate-300 bg-slate-800/40 hover:bg-slate-800' : 'border-slate-300 text-slate-400 hover:border-slate-500 hover:text-slate-600'}`}
                        >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M12 4v16m8-8H4" />
                            </svg>
                            Nova Área Temática
                        </button>
                    )}
                </div>
            </aside>

            {/* Main Content */}
            <main className={`flex-1 flex flex-col h-full overflow-hidden ${mobileView === 'bases' ? 'hidden md:flex' : 'flex'}`}>
                {!selectedBase ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-center p-12">
                        <div className={`w-20 h-20 rounded-3xl flex items-center justify-center mb-4 ${isDark ? 'bg-slate-800 text-slate-500' : 'bg-slate-100 text-slate-400'}`}>
                            <svg className="w-10 h-10 text-inherit" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                            </svg>
                        </div>
                        <p className="text-slate-400 font-semibold">Selecione ou crie uma Área Temática na barra lateral</p>
                    </div>
                ) : (
                    <>
                        {/* Header */}
                        <div className={`border-b px-4 md:px-8 py-4 md:py-6 flex flex-col md:flex-row md:items-center gap-4 md:gap-6 ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                            <div className="flex items-center justify-between md:justify-start gap-4">
                                <button
                                    onClick={() => setMobileView('bases')}
                                    className={`md:hidden flex items-center justify-center w-10 h-10 border transition-colors z-10 ${isDark ? 'border-slate-700 bg-slate-800 text-slate-100 hover:bg-slate-700' : 'border-slate-200 text-slate-900 bg-white hover:bg-slate-50'}`}
                                    title="VOLTAR PARA LISTA"
                                >
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                                    </svg>
                                </button>
                                <div className="flex items-center gap-3">
                                    <span className="text-2xl">{selectedBase.emoji || '📁'}</span>
                                    <div className="min-w-0">
                                        <p className="text-[10px] font-mono font-black text-violet-500 uppercase tracking-[0.2em]">ÁREA TEMÁTICA</p>
                                        <h1 className={`text-xl font-mono font-black uppercase tracking-tight truncate ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{selectedBase.nome}</h1>
                                    </div>
                                </div>
                            </div>
                            {selectedBase.descricao && (
                                <p className="text-[11px] font-mono text-slate-400 font-bold ml-0 md:ml-10 truncate hidden md:block">{selectedBase.descricao}</p>
                            )}
                            <div className="flex items-center gap-2 md:gap-3 overflow-x-auto pb-2 md:pb-0 scrollbar-hide">
                                {/* Search */}
                                <div className={`flex items-center border rounded-none px-3 md:px-4 py-2 md:py-2.5 gap-2 md:gap-3 min-w-[140px] md:w-64 focus-within:border-violet-400 transition-all ${isDark ? 'bg-slate-800/80 border-slate-700' : 'bg-slate-50 border-slate-200'}`}>
                                    <svg className="w-4 h-4 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                    </svg>
                                    <input
                                        value={searchTerm}
                                        onChange={e => setSearchTerm(e.target.value)}
                                        placeholder="BUSCAR DOCUMENTOS..."
                                        className={`bg-transparent text-[11px] font-mono font-black outline-none w-full uppercase tracking-widest ${isDark ? 'text-slate-100 placeholder:text-slate-500' : 'text-slate-700 placeholder:text-slate-300'}`}
                                    />
                                </div>
                                <button
                                    onClick={() => setIsAddLinkOpen(true)}
                                    className={`flex items-center gap-2 px-4 py-2.5 border rounded-none text-[10px] font-mono font-black uppercase tracking-widest transition-all ${isDark ? 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-slate-100' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                                    </svg>
                                    Link
                                </button>
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    disabled={isUploading}
                                    className="flex items-center gap-2 px-5 py-2.5 bg-violet-600 text-white rounded-none text-[10px] font-mono font-black uppercase tracking-widest hover:bg-violet-700 transition-all disabled:opacity-60 shadow-lg shadow-violet-100"
                                >
                                    {isUploading ? (
                                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                        </svg>
                                    ) : (
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                                        </svg>
                                    )}
                                    {isUploading ? 'PROCESSANDO' : 'UPLOAD'}
                                </button>
                                <button
                                    onClick={() => setEditingBase(selectedBase)}
                                    className={`w-10 h-10 flex-shrink-0 flex items-center justify-center border rounded-none transition-all ${isDark ? 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-slate-200' : 'bg-white border-slate-200 text-slate-500 hover:bg-slate-50'}`}
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                    </svg>
                                </button>
                            </div>
                        </div>

                        {/* Drop zone + Document list */}
                        <div
                            className={`flex-1 overflow-y-auto p-4 md:p-6 transition-all ${isDragging ? (isDark ? 'bg-violet-950/20 ring-2 ring-violet-500 ring-inset' : 'bg-violet-50 ring-2 ring-violet-400 ring-inset') : ''}`}
                            onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                            onDragLeave={() => setIsDragging(false)}
                            onDrop={handleFileDrop}
                        >
                            {isDragging && (
                                <div className="fixed inset-0 z-40 flex items-center justify-center pointer-events-none">
                                    <div className="bg-violet-600 text-white px-8 py-4 rounded-2xl shadow-2xl font-black text-lg">
                                        Solte para adicionar à base
                                    </div>
                                </div>
                            )}

                            {baseItems.length === 0 ? (
                                <div className={`flex flex-col items-center justify-center h-full min-h-[400px] text-center border-2 border-dashed ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                                    <div className={`w-16 h-16 flex items-center justify-center mb-6 ${isDark ? 'bg-slate-800/80 text-slate-600' : 'bg-slate-50 text-slate-200'}`}>
                                        <svg className="w-8 h-8 text-inherit" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                                        </svg>
                                    </div>
                                    <p className="text-[10px] font-mono font-black text-slate-300 uppercase tracking-[0.3em] mb-2">SYSTEM: NO DATA DETECTED</p>
                                    <p className="text-slate-400 text-[11px] font-mono">Arraste arquivos aqui ou use o comando UPLOAD.</p>
                                </div>
                            ) : (
                                <div className={`flex flex-col border-l border-t ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                                    {baseItems.map(item => (
                                        <div
                                            key={item.id}
                                            className={`border-r border-b px-6 py-4 flex items-center gap-4 transition-all group relative -ml-px -mt-px ${isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-800/60' : 'bg-white border-slate-200 hover:bg-slate-50'}`}
                                        >
                                            <FileIcon tipo={item.tipo_arquivo} isDark={isDark} />
                                            <div className="flex-1 min-w-0 py-1">
                                                <p className={`text-[13px] font-mono font-black uppercase tracking-tight truncate ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{item.titulo}</p>
                                                <div className="flex flex-wrap items-center gap-2 md:gap-3 mt-1">
                                                    <span className="text-[9px] font-mono font-black text-slate-400 uppercase tracking-widest whitespace-nowrap">
                                                        {new Date(item.data_criacao).toLocaleDateString('pt-BR')}
                                                    </span>
                                                    <VectorBadge hasEmbedding={!!(item as any).embedding} isDark={isDark} />
                                                    {item.tags && item.tags.length > 0 && item.tags.slice(0, 2).map(tag => (
                                                        <span key={tag} className={`text-[9px] font-mono font-black px-2 py-0.5 uppercase tracking-widest ${isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-100 text-slate-500'}`}>{tag}</span>
                                                    ))}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-1 md:gap-2 opacity-0 group-hover:opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                                                {item.origem && onNavigateToOrigin && (
                                                    <button
                                                        onClick={() => onNavigateToOrigin(item.origem!.modulo, item.origem!.id_origem)}
                                                        className={`w-9 h-9 flex items-center justify-center border transition-all ${isDark ? 'border-slate-800 bg-slate-800 text-slate-400 hover:text-violet-400 hover:bg-slate-700' : 'border-slate-100 bg-white text-slate-400 hover:text-violet-600 hover:bg-violet-50'}`}
                                                        title="Ver Origem"
                                                    >
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                        </svg>
                                                    </button>
                                                )}
                                                {item.url_drive && item.url_drive !== '' && (
                                                    <a
                                                        href={item.url_drive}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className={`w-9 h-9 flex items-center justify-center border transition-all ${isDark ? 'border-slate-800 bg-slate-800 text-slate-400 hover:text-blue-400 hover:bg-slate-700' : 'border-slate-100 bg-white text-slate-400 hover:text-blue-600 hover:bg-blue-50'}`}
                                                        title="Abrir arquivo"
                                                    >
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                        </svg>
                                                    </a>
                                                )}
                                                {onVectorizeItem && !(item as any).embedding && (
                                                    <button
                                                        onClick={async () => {
                                                            setVectorizingId(item.id);
                                                            await onVectorizeItem(item.id);
                                                            setVectorizingId(null);
                                                        }}
                                                        disabled={vectorizingId === item.id}
                                                        className={`w-9 h-9 flex items-center justify-center border transition-all disabled:opacity-60 ${isDark ? 'border-slate-800 bg-slate-800 text-slate-400 hover:text-violet-400 hover:bg-slate-700' : 'border-slate-100 bg-white text-slate-400 hover:text-violet-600 hover:bg-violet-50'}`}
                                                    >
                                                        {vectorizingId === item.id ? (
                                                            <svg className="w-4 h-4 animate-spin text-violet-500" fill="none" viewBox="0 0 24 24">
                                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                                            </svg>
                                                        ) : (
                                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                                            </svg>
                                                        )}
                                                    </button>
                                                )}
                                                <button
                                                    onClick={() => handleDeleteItem(item.id)}
                                                    className={`w-9 h-9 flex items-center justify-center border transition-all ${isDark ? 'border-slate-800 bg-slate-800 text-slate-400 hover:text-rose-400 hover:bg-slate-700' : 'border-slate-100 bg-white text-slate-400 hover:text-rose-600 hover:bg-rose-50'}`}
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                    </svg>
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </main>

            {/* Hidden file input */}
            <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleFileSelect}
            />

            {/* Add Link Modal */}
            {isAddLinkOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <div className={`rounded-none shadow-2xl w-full max-w-md p-8 border ${isDark ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'}`}>
                        <h2 className={`text-sm font-mono font-black uppercase tracking-[0.2em] mb-6 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>ADICIONAR RECURSO EXTERNO</h2>
                        <div className="flex flex-col gap-5">
                            <div>
                                <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-1.5 block">URL DE ORIGEM</label>
                                <input
                                    autoFocus
                                    value={linkUrl}
                                    onChange={e => setLinkUrl(e.target.value)}
                                    placeholder="https://..."
                                    className={`w-full px-4 py-3 text-xs font-mono font-bold border rounded-none outline-none transition-colors ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-violet-400 placeholder:text-slate-500' : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-violet-500 placeholder:text-slate-400'}`}
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-1.5 block">TÍTULO IDENTIFICADOR (OPCIONAL)</label>
                                <input
                                    value={linkTitle}
                                    onChange={e => setLinkTitle(e.target.value)}
                                    onKeyDown={e => { if (e.key === 'Enter') handleAddLink(); }}
                                    placeholder="NOME DO LINK..."
                                    className={`w-full px-4 py-3 text-xs font-mono font-bold border rounded-none outline-none transition-colors ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-violet-400 placeholder:text-slate-500' : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-violet-500 placeholder:text-slate-400'}`}
                                />
                            </div>
                        </div>
                        <div className="flex gap-3 mt-8">
                            <button onClick={handleAddLink} className="flex-1 py-3 bg-violet-600 text-white rounded-none text-[10px] font-mono font-black uppercase tracking-widest hover:bg-violet-700 transition-all">Sincronizar</button>
                            <button onClick={() => { setIsAddLinkOpen(false); setLinkUrl(''); setLinkTitle(''); }} className={`flex-1 py-3 border rounded-none text-[10px] font-mono font-black uppercase tracking-widest transition-all ${isDark ? 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}>Cancelar</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Edit Base Modal */}
            {editingBase && (
                <EditBaseModal
                    base={editingBase}
                    onSave={async (updates) => { await onUpdateBase(editingBase.id, updates); setEditingBase(null); }}
                    onDelete={() => { handleDeleteBase(editingBase); setEditingBase(null); }}
                    onClose={() => setEditingBase(null)}
                    isDark={isDark}
                />
            )}
        </div>
    );
};

// --- Edit Base Modal ---

interface EditBaseModalProps {
    base: BaseConhecimento;
    onSave: (updates: Partial<BaseConhecimento>) => Promise<void>;
    onDelete: () => void;
    onClose: () => void;
    isDark?: boolean;
}

const EditBaseModal: React.FC<EditBaseModalProps> = ({ base, onSave, onDelete, onClose, isDark = false }) => {
    const [nome, setNome] = useState(base.nome);
    const [descricao, setDescricao] = useState(base.descricao || '');
    const [cor, setCor] = useState(base.cor || '#f59e0b');
    const [incluirDiarios, setIncluirDiarios] = useState(base.configuracao_rag?.incluir_diarios ?? false);
    const [incluirManual, setIncluirManual] = useState(base.configuracao_rag?.incluir_manual ?? false);
    const [tagsInput, setTagsInput] = useState((base.configuracao_rag?.tags_vinculadas ?? []).join(', '));

    const handleSave = async () => {
        await onSave({
            nome: nome.trim() || base.nome,
            descricao: descricao.trim(),
            cor,
            configuracao_rag: {
                incluir_diarios: incluirDiarios,
                incluir_manual: incluirManual,
                categorias_vinculadas: [],
                tags_vinculadas: tagsInput.split(',').map(s => s.trim()).filter(Boolean),
            }
        });
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
            <div className={`rounded-none shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto border ${isDark ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'}`}>
                <div className={`p-8 border-b flex items-center justify-between ${isDark ? 'border-slate-800 bg-slate-900/80' : 'border-slate-200 bg-slate-50'}`}>
                    <div>
                        <p className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-1">SYSTEM CONFIGURATION</p>
                        <h2 className={`text-sm font-mono font-black uppercase tracking-tight ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Configurar Área Temática</h2>
                    </div>
                    <button onClick={onClose} className={`w-10 h-10 flex items-center justify-center border transition-colors ${isDark ? 'border-slate-700 bg-slate-800 text-slate-300 hover:text-slate-100 hover:bg-slate-700' : 'border-slate-200 bg-white text-slate-400 hover:text-slate-600'}`}>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <div className="p-8 flex flex-col gap-6">
                    {/* Color Palette */}
                    <div>
                        <div className="flex items-center justify-between mb-3">
                            <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest">Cor da Área Temática</label>
                            <div className="flex items-center gap-2">
                                <div className="w-5 h-5 border-2 border-white shadow" style={{ backgroundColor: cor }} />
                                <span className="text-[10px] font-mono font-black uppercase tracking-widest" style={{ color: cor }}>
                                    {COLOR_OPTIONS.find(c => c.value === cor)?.label || cor}
                                </span>
                            </div>
                        </div>
                        <div className="grid grid-cols-10 gap-1.5">
                            {COLOR_OPTIONS.map(c => (
                                <button
                                    key={c.value}
                                    onClick={() => setCor(c.value)}
                                    title={c.label}
                                    className={`w-full aspect-square transition-all border-2 ${cor === c.value ? 'scale-110 border-slate-900 shadow-md' : 'border-transparent hover:scale-105 hover:border-slate-300'}`}
                                    style={{ backgroundColor: c.value }}
                                />
                            ))}
                        </div>
                    </div>

                    <div>
                        <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-2 block">Nome da Área Temática</label>
                        <input
                            value={nome}
                            onChange={e => setNome(e.target.value)}
                            className={`w-full px-4 py-3 text-xs font-mono font-bold border rounded-none outline-none transition-colors uppercase tracking-widest ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-violet-400 placeholder:text-slate-500' : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-violet-500 placeholder:text-slate-400'}`}
                        />
                    </div>

                    <div>
                        <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-2 block">Descrição</label>
                        <input
                            value={descricao}
                            onChange={e => setDescricao(e.target.value)}
                            placeholder="FINALIDADE DESTA ÁREA NO SISTEMA..."
                            className={`w-full px-4 py-3 text-xs font-mono font-bold border rounded-none outline-none transition-colors uppercase tracking-widest ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-violet-400 placeholder:text-slate-500' : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-violet-500 placeholder:text-slate-400'}`}
                        />
                    </div>

                    {/* RAG Config */}
                    <div className={`border-t ${isDark ? 'border-slate-800' : 'border-slate-200'} pt-6`}>
                        <p className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-[0.2em] mb-4">MÓDULOS DE INTEGRAÇÃO RAG</p>
                        <div className="flex flex-col gap-4">
                            <label className="flex items-center gap-4 cursor-pointer group">
                                <div
                                    onClick={() => setIncluirDiarios(!incluirDiarios)}
                                    className={`w-12 h-6 border transition-colors relative ${incluirDiarios ? 'bg-violet-600 border-violet-700' : (isDark ? 'bg-slate-800 border-slate-700' : 'bg-slate-200 border-slate-300')}`}
                                >
                                    <div className={`w-4 h-4 bg-white shadow-sm absolute top-0.5 transition-all ${incluirDiarios ? 'left-7' : 'left-0.5'}`} />
                                </div>
                                <span className={`text-[11px] font-mono font-black uppercase tracking-tight ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>Incluir Diários de Bordo</span>
                            </label>
                            <label className="flex items-center gap-4 cursor-pointer group">
                                <div
                                    onClick={() => setIncluirManual(!incluirManual)}
                                    className={`w-12 h-6 border transition-colors relative ${incluirManual ? 'bg-violet-600 border-violet-700' : (isDark ? 'bg-slate-800 border-slate-700' : 'bg-slate-200 border-slate-300')}`}
                                >
                                    <div className={`w-4 h-4 bg-white shadow-sm absolute top-0.5 transition-all ${incluirManual ? 'left-7' : 'left-0.5'}`} />
                                </div>
                                <span className={`text-[11px] font-mono font-black uppercase tracking-tight ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>Incluir Manual Operacional</span>
                            </label>
                            <div>
                                <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-1.5 block">Tags RAG</label>
                                <input
                                    value={tagsInput}
                                    onChange={e => setTagsInput(e.target.value)}
                                    placeholder="PROCEDIMENTO, PROTOCOLO, REUNIÃO..."
                                    className={`w-full px-4 py-2.5 text-[10px] font-mono font-bold border rounded-none outline-none transition-colors uppercase ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-slate-400 placeholder:text-slate-500' : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-slate-400 placeholder:text-slate-400'}`}
                                />
                                <p className={`text-[9px] font-mono mt-1.5 ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Separe as tags por vírgula</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div className={`p-8 border-t flex gap-3 ${isDark ? 'border-slate-800 bg-slate-900/80' : 'border-slate-200 bg-slate-50'}`}>
                    <button onClick={handleSave} className={`flex-1 py-4 text-white rounded-none text-[10px] font-mono font-black uppercase tracking-widest transition-all ${isDark ? 'bg-slate-600 hover:bg-slate-700' : 'bg-slate-900 hover:bg-black'}`}>Atualizar Sistema</button>
                    <button onClick={onClose} className={`flex-1 py-4 border rounded-none text-[10px] font-mono font-black uppercase tracking-widest transition-all ${isDark ? 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}>Cancelar</button>
                    <button onClick={onDelete} className={`w-14 flex items-center justify-center border rounded-none transition-all ${isDark ? 'bg-rose-950/40 text-rose-400 border-rose-800/60 hover:bg-rose-900/60' : 'bg-rose-50 text-rose-600 border-rose-100 hover:bg-rose-100'}`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    );
};

export default RAGBasesView;
