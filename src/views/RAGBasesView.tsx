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
}

const EMOJI_OPTIONS = ['📁', '📚', '🧠', '⚡', '🔬', '🏛️', '🎯', '🗂️', '📋', '🌐', '🔧', '💡'];
const COLOR_OPTIONS = [
    { label: 'Amarelo', value: '#f59e0b' },
    { label: 'Azul', value: '#3b82f6' },
    { label: 'Verde', value: '#10b981' },
    { label: 'Roxo', value: '#8b5cf6' },
    { label: 'Rosa', value: '#ec4899' },
    { label: 'Vermelho', value: '#ef4444' },
    { label: 'Cinza', value: '#6b7280' },
    { label: 'Laranja', value: '#f97316' },
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
}) => {
    const [selectedBaseId, setSelectedBaseId] = useState<string | null>(null);
    const [isCreatingBase, setIsCreatingBase] = useState(false);
    const [newBaseName, setNewBaseName] = useState('');
    const [isCreatingInline, setIsCreatingInline] = useState(false);
    const [inlineName, setInlineName] = useState('');
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
                setSelectedBaseId(null);
            });
        } else {
            onDeleteBase(base.id);
            setSelectedBaseId(null);
        }
    };

    if (selectedBaseId === null || !selectedBase) {
        return (
            <div className={`flex flex-col h-[100dvh] overflow-hidden ${isDark ? 'bg-slate-950 text-slate-100' : 'bg-[#f9f9f9] text-slate-900'}`}>
                {/* Header */}
                <header className={`border-b px-6 py-5 flex items-center justify-between flex-shrink-0 ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => window.history.back()}
                            className={`w-10 h-10 flex items-center justify-center border transition-colors ${isDark ? 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700' : 'border-slate-200 bg-white text-slate-900 hover:bg-slate-50'}`}
                            title="VOLTAR"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                            </svg>
                        </button>
                        <div>
                            <div className="flex items-center gap-2 mb-0.5">
                                <div className="w-2 h-2 bg-violet-500"></div>
                                <p className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest">SYSTEM: CONFIGURAÇÕES</p>
                            </div>
                            <h1 className={`text-lg font-mono font-black uppercase tracking-tight ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Áreas Temáticas</h1>
                        </div>
                    </div>
                </header>

                {/* Grid Content */}
                <div className="flex-1 overflow-y-auto p-6 md:p-10">
                    <div className="max-w-7xl mx-auto">
                        <div className="mb-8">
                            <p className={`text-xs font-mono font-bold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                Selecione uma área temática para gerenciar seus documentos ou crie uma nova abaixo. Estas áreas categorizam as ações automáticas via Copiloto e Telegram.
                            </p>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                            {bases.map((base, idx) => {
                                const baseColor = base.cor || '#3b82f6';
                                const itemCount = items.filter(i => i.base_id === base.id).length;
                                return (
                                    <div
                                        key={base.id}
                                        onClick={() => setSelectedBaseId(base.id)}
                                        className={`group relative flex flex-col justify-between p-8 border-4 cursor-pointer transition-all duration-200 hover:-translate-x-1.5 hover:-translate-y-1.5 ${
                                            isDark 
                                                ? 'bg-slate-900 border-slate-800 hover:border-slate-100 text-slate-100' 
                                                : 'bg-white border-slate-950 hover:border-slate-950 text-slate-900'
                                        }`}
                                        style={{ 
                                            boxShadow: '0px 0px 0px 0px transparent',
                                            borderTopWidth: '8px', 
                                            borderTopColor: baseColor 
                                        } as React.CSSProperties}
                                        onMouseEnter={(e) => {
                                            e.currentTarget.style.boxShadow = `6px 6px 0px 0px ${baseColor}`;
                                        }}
                                        onMouseLeave={(e) => {
                                            e.currentTarget.style.boxShadow = '0px 0px 0px 0px transparent';
                                        }}
                                    >
                                        <div>
                                            <div className="flex justify-between items-start mb-4">
                                                <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">ÁREA-{String(idx + 1).padStart(3, '0')}</span>
                                                <span className={`px-2.5 py-1 text-[10px] font-mono font-black border-2 uppercase ${isDark ? 'bg-slate-800 border-slate-700 text-slate-300' : 'bg-slate-50 border-slate-950 text-slate-900'}`}>
                                                    {itemCount} {itemCount === 1 ? 'item' : 'itens'}
                                                </span>
                                            </div>

                                            <div className="flex items-start gap-4 mb-4">
                                                <span className={`text-3xl p-2 border-2 ${isDark ? 'border-slate-700 bg-slate-800' : 'border-slate-950 bg-slate-50'} rounded-none flex-shrink-0`}>{base.emoji || '📁'}</span>
                                                <h3 className="text-sm font-mono font-black uppercase tracking-tight whitespace-normal break-words leading-tight flex-1 mt-1">{base.nome}</h3>
                                            </div>

                                            {base.descricao && (
                                                <p className="text-[11px] font-mono text-slate-400 uppercase tracking-tight line-clamp-3 mb-4 leading-relaxed">
                                                    {base.descricao}
                                                </p>
                                            )}
                                        </div>

                                        {/* Actions */}
                                        <div className={`flex justify-end gap-2 pt-4 border-t-2 ${isDark ? 'border-slate-800' : 'border-slate-950'} mt-auto`}>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setEditingBase(base);
                                                }}
                                                className={`w-9 h-9 rounded-none flex items-center justify-center border-2 transition-all ${
                                                    isDark 
                                                        ? 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-slate-200' 
                                                        : 'bg-white border-slate-950 text-slate-900 hover:bg-slate-950 hover:text-white'
                                                }`}
                                                title="Configurações"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                                </svg>
                                            </button>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleDeleteBase(base);
                                                }}
                                                className={`w-9 h-9 rounded-none flex items-center justify-center border-2 transition-all ${
                                                    isDark 
                                                        ? 'bg-rose-950/40 border-rose-900/60 text-rose-400 hover:bg-rose-900/60' 
                                                        : 'bg-rose-50 border-slate-950 text-rose-600 hover:bg-slate-950 hover:text-white'
                                                }`}
                                                title="Excluir"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                </svg>
                                            </button>
                                        </div>
                                    </div>
                                );
                            })}

                            {/* Card de Criação Rápida */}
                            {isCreatingInline ? (
                                <div
                                    className={`flex flex-col justify-between p-8 border-4 border-violet-500 rounded-none transition-all duration-300 bg-violet-50/20 dark:bg-violet-950/10`}
                                    style={{ minHeight: '230px' }}
                                >
                                    <div>
                                        <span className="text-[10px] font-mono font-black text-violet-500 uppercase tracking-widest mb-2 block">NOVA ÁREA TEMÁTICA</span>
                                        <input
                                            autoFocus
                                            value={inlineName}
                                            onChange={e => setInlineName(e.target.value)}
                                            onKeyDown={e => {
                                                if (e.key === 'Enter') {
                                                    const name = inlineName.trim();
                                                    if (name) {
                                                        onCreateBase(name);
                                                        setInlineName('');
                                                        setIsCreatingInline(false);
                                                    }
                                                }
                                                if (e.key === 'Escape') {
                                                    setIsCreatingInline(false);
                                                    setInlineName('');
                                                }
                                            }}
                                            placeholder="NOME DA ÁREA TEMÁTICA..."
                                            className={`w-full px-3 py-2.5 text-xs font-mono font-bold border-2 rounded-none outline-none transition-colors mb-4 ${
                                                isDark 
                                                    ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-violet-400 placeholder:text-slate-500' 
                                                    : 'bg-white border-slate-950 text-slate-900 focus:border-violet-500 placeholder:text-slate-400'
                                            }`}
                                        />
                                    </div>
                                    <div className="flex gap-3">
                                        <button
                                            onClick={() => {
                                                const name = inlineName.trim();
                                                if (name) {
                                                    onCreateBase(name);
                                                    setInlineName('');
                                                    setIsCreatingInline(false);
                                                }
                                            }}
                                            className="flex-1 py-2.5 bg-violet-600 hover:bg-violet-700 text-white rounded-none text-[10px] font-mono font-black uppercase tracking-widest transition-colors"
                                        >
                                            Confirmar
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsCreatingInline(false);
                                                setInlineName('');
                                            }}
                                            className={`flex-1 py-2.5 border-2 rounded-none text-[10px] font-mono font-black uppercase tracking-widest transition-colors ${
                                                isDark 
                                                    ? 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700' 
                                                    : 'bg-white border-slate-950 text-slate-600 hover:bg-slate-50'
                                            }`}
                                        >
                                            Cancelar
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                <div
                                    onClick={() => setIsCreatingInline(true)}
                                    className={`flex flex-col items-center justify-center p-8 border-4 border-dashed rounded-none cursor-pointer transition-all duration-200 hover:-translate-x-1.5 hover:-translate-y-1.5 ${
                                        isDark 
                                            ? 'border-slate-800 text-slate-400 hover:border-violet-500 hover:text-violet-400 bg-slate-900/40 hover:bg-slate-900' 
                                            : 'border-slate-300 text-slate-400 hover:border-violet-500 hover:text-violet-600 bg-slate-50/50 hover:bg-white shadow-none'
                                    }`}
                                    style={{ 
                                        minHeight: '230px',
                                        boxShadow: '0px 0px 0px 0px transparent',
                                    }}
                                    onMouseEnter={(e) => {
                                        e.currentTarget.style.boxShadow = `6px 6px 0px 0px #8b5cf6`;
                                    }}
                                    onMouseLeave={(e) => {
                                        e.currentTarget.style.boxShadow = '0px 0px 0px 0px transparent';
                                    }}
                                >
                                    <svg className="w-8 h-8 mb-2 text-inherit" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M12 4v16m8-8H4" />
                                    </svg>
                                    <span className="text-[10px] font-mono font-black uppercase tracking-widest">Nova Área Temática</span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

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
    }

    return (
        <div className={`flex flex-col h-[100dvh] overflow-hidden ${isDark ? 'bg-slate-950 text-slate-100' : 'bg-[#f9f9f9] text-slate-900'}`}>
            {/* Header */}
            <div className={`border-b px-4 md:px-8 py-4 md:py-6 flex flex-col md:flex-row md:items-center gap-4 md:gap-6 ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => setSelectedBaseId(null)}
                        className={`flex items-center justify-center w-10 h-10 border transition-colors z-10 ${isDark ? 'border-slate-700 bg-slate-800 text-slate-100 hover:bg-slate-700' : 'border-slate-200 text-slate-900 bg-white hover:bg-slate-50'}`}
                        title="VOLTAR PARA ÁREAS TEMÁTICAS"
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
                <div className="flex items-center gap-2 md:gap-3 overflow-x-auto pb-2 md:pb-0 scrollbar-hide ml-auto">
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
    const [emoji, setEmoji] = useState(base.emoji || '📁');
    const [cor, setCor] = useState(base.cor || '#f59e0b');
    const [incluirDiarios, setIncluirDiarios] = useState(base.configuracao_rag?.incluir_diarios ?? false);
    const [incluirManual, setIncluirManual] = useState(base.configuracao_rag?.incluir_manual ?? false);
    const [categoriasInput, setCategoriasInput] = useState((base.configuracao_rag?.categorias_vinculadas ?? []).join(', '));
    const [tagsInput, setTagsInput] = useState((base.configuracao_rag?.tags_vinculadas ?? []).join(', '));

    const handleSave = async () => {
        await onSave({
            nome: nome.trim() || base.nome,
            descricao: descricao.trim(),
            emoji,
            cor,
            configuracao_rag: {
                incluir_diarios: incluirDiarios,
                incluir_manual: incluirManual,
                categorias_vinculadas: categoriasInput.split(',').map(s => s.trim()).filter(Boolean),
                tags_vinculadas: tagsInput.split(',').map(s => s.trim()).filter(Boolean),
            }
        });
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
            <div className={`rounded-none shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto border ${isDark ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'}`}>
                <div className={`p-8 border-b flex items-center justify-between ${isDark ? 'border-slate-800 bg-slate-900/80' : 'border-slate-200 bg-slate-50'}`}>
                    <div>
                        <p className="text-[10px] font-mono font-black text-violet-500 uppercase tracking-widest mb-1">SYSTEM CONFIGURATION</p>
                        <h2 className={`text-sm font-mono font-black uppercase tracking-tight ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Configurar Área Temática</h2>
                    </div>
                    <button onClick={onClose} className={`w-10 h-10 flex items-center justify-center border transition-colors ${isDark ? 'border-slate-700 bg-slate-800 text-slate-300 hover:text-slate-100 hover:bg-slate-700' : 'border-slate-200 bg-white text-slate-400 hover:text-slate-600'}`}>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <div className="p-8 flex flex-col gap-6">
                    {/* Identity */}
                    <div className="flex gap-6">
                        <div className="flex-1">
                            <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-2 block">Ícone do Sistema</label>
                            <div className="grid grid-cols-4 gap-2">
                                {EMOJI_OPTIONS.map(e => (
                                    <button
                                        key={e}
                                        onClick={() => setEmoji(e)}
                                        className={`w-10 h-10 text-xl flex items-center justify-center transition-all border ${emoji === e ? (isDark ? 'bg-violet-950/50 border-violet-500 ring-1 ring-violet-500 text-violet-400' : 'bg-violet-50 border-violet-400 ring-1 ring-violet-400 text-violet-600') : (isDark ? 'bg-slate-800 border-slate-700 hover:bg-slate-700 text-slate-300' : 'bg-slate-50 border-slate-200 hover:bg-slate-100 text-slate-700')}`}
                                    >{e}</button>
                                ))}
                            </div>
                        </div>
                        <div className="w-32">
                            <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-2 block">Cor ID</label>
                            <div className="grid grid-cols-3 gap-2">
                                {COLOR_OPTIONS.slice(0, 6).map(c => (
                                    <button
                                        key={c.value}
                                        onClick={() => setCor(c.value)}
                                        title={c.label}
                                        className={`w-8 h-8 transition-all border-2 ${cor === c.value ? (isDark ? 'border-white scale-110' : 'border-slate-900 scale-110') : 'border-transparent hover:scale-105'}`}
                                        style={{ backgroundColor: c.value }}
                                    />
                                ))}
                            </div>
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
                        <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-2 block">Descrição Técnica</label>
                        <input
                            value={descricao}
                            onChange={e => setDescricao(e.target.value)}
                            placeholder="FINALIDADE DESTA BASE NO SISTEMA..."
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
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-1.5 block">Categorias</label>
                                    <input
                                        value={categoriasInput}
                                        onChange={e => setCategoriasInput(e.target.value)}
                                        placeholder="TI, FINANCEIRO..."
                                        className={`w-full px-4 py-2 text-[10px] font-mono font-bold border rounded-none outline-none transition-colors uppercase ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-violet-400 placeholder:text-slate-500' : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-violet-500 placeholder:text-slate-400'}`}
                                    />
                                </div>
                                <div>
                                    <label className="text-[10px] font-mono font-black text-slate-400 uppercase tracking-widest mb-1.5 block">Tags RAG</label>
                                    <input
                                        value={tagsInput}
                                        onChange={e => setTagsInput(e.target.value)}
                                        placeholder="PROCEDIMENTO..."
                                        className={`w-full px-4 py-2 text-[10px] font-mono font-bold border rounded-none outline-none transition-colors uppercase ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-violet-400 placeholder:text-slate-500' : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-violet-500 placeholder:text-slate-400'}`}
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className={`p-8 border-t flex gap-3 ${isDark ? 'border-slate-800 bg-slate-900/80' : 'border-slate-200 bg-slate-50'}`}>
                    <button onClick={handleSave} className={`flex-1 py-4 text-white rounded-none text-[10px] font-mono font-black uppercase tracking-widest transition-all ${isDark ? 'bg-violet-600 hover:bg-violet-700' : 'bg-slate-900 hover:bg-black'}`}>Atualizar Sistema</button>
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
