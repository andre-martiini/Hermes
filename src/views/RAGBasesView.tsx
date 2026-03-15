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

const FileIcon: React.FC<{ tipo: string }> = ({ tipo }) => {
    const t = (tipo || '').toLowerCase();
    if (t === 'pdf') return (
        <div className="w-10 h-10 bg-red-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <span className="text-xs font-black text-red-600">PDF</span>
        </div>
    );
    if (['doc', 'docx'].includes(t)) return (
        <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <span className="text-xs font-black text-blue-600">DOC</span>
        </div>
    );
    if (['xls', 'xlsx'].includes(t)) return (
        <div className="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <span className="text-xs font-black text-green-600">XLS</span>
        </div>
    );
    if (t === 'link') return (
        <div className="w-10 h-10 bg-violet-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5 text-violet-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
        </div>
    );
    if (['txt', 'md'].includes(t)) return (
        <div className="w-10 h-10 bg-slate-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <span className="text-xs font-black text-slate-500">TXT</span>
        </div>
    );
    return (
        <div className="w-10 h-10 bg-slate-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
        </div>
    );
};

const VectorBadge: React.FC<{ hasEmbedding: boolean }> = ({ hasEmbedding }) => (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${hasEmbedding ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${hasEmbedding ? 'bg-emerald-500' : 'bg-slate-300'}`} />
        {hasEmbedding ? 'Vetorizado' : 'Sem vetor'}
    </span>
);

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
}) => {
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
            showConfirm('Excluir base RAG', `Excluir a base "${base.nome}"? Os documentos vinculados não serão excluídos.`, async () => {
                await onDeleteBase(base.id);
                if (selectedBaseId === base.id) setSelectedBaseId(bases.find(b => b.id !== base.id)?.id ?? null);
            });
        } else {
            onDeleteBase(base.id);
            if (selectedBaseId === base.id) setSelectedBaseId(null);
        }
    };

    return (
        <div className="flex h-full min-h-screen bg-slate-50">
            {/* Sidebar */}
            <aside className="w-64 flex-shrink-0 bg-white border-r border-slate-200 flex flex-col">
                <div className="p-4 border-b border-slate-100">
                    <div className="flex items-center gap-2 mb-1">
                        <svg className="w-4 h-4 text-violet-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                        <span className="text-[11px] font-black text-slate-400 uppercase tracking-widest">Bases RAG</span>
                    </div>
                </div>

                <nav className="flex-1 overflow-y-auto p-2">
                    {bases.map(base => (
                        <button
                            key={base.id}
                            onClick={() => setSelectedBaseId(base.id)}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left transition-all mb-0.5 group ${selectedBaseId === base.id ? 'bg-violet-50 text-violet-800' : 'text-slate-600 hover:bg-slate-50'}`}
                        >
                            <span
                                className="w-7 h-7 rounded-lg flex items-center justify-center text-sm flex-shrink-0"
                                style={{ backgroundColor: (base.cor || '#f59e0b') + '22' }}
                            >
                                {base.emoji || '📁'}
                            </span>
                            <span className="text-sm font-semibold truncate flex-1">{base.nome}</span>
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0 ${selectedBaseId === base.id ? 'bg-violet-100 text-violet-600' : 'bg-slate-100 text-slate-400'}`}>
                                {items.filter(i => i.base_id === base.id).length}
                            </span>
                        </button>
                    ))}
                </nav>

                <div className="p-3 border-t border-slate-100">
                    {isCreatingBase ? (
                        <div className="flex flex-col gap-2">
                            <input
                                autoFocus
                                value={newBaseName}
                                onChange={e => setNewBaseName(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter') handleCreateBase(); if (e.key === 'Escape') setIsCreatingBase(false); }}
                                placeholder="Nome da base..."
                                className="w-full px-3 py-2 text-sm border border-violet-300 rounded-lg outline-none focus:ring-2 focus:ring-violet-500"
                            />
                            <div className="flex gap-2">
                                <button onClick={handleCreateBase} className="flex-1 py-1.5 bg-violet-600 text-white rounded-lg text-xs font-bold hover:bg-violet-700">Criar</button>
                                <button onClick={() => setIsCreatingBase(false)} className="flex-1 py-1.5 bg-slate-100 text-slate-600 rounded-lg text-xs font-bold hover:bg-slate-200">Cancelar</button>
                            </div>
                        </div>
                    ) : (
                        <button
                            onClick={() => setIsCreatingBase(true)}
                            className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-slate-500 hover:bg-slate-50 hover:text-violet-600 transition-all text-sm font-semibold"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
                            </svg>
                            Nova Base RAG
                        </button>
                    )}
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col overflow-hidden">
                {!selectedBase ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-center p-12">
                        <div className="w-20 h-20 bg-violet-50 rounded-3xl flex items-center justify-center mb-4">
                            <svg className="w-10 h-10 text-violet-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                            </svg>
                        </div>
                        <p className="text-slate-400 font-semibold">Selecione ou crie uma Base RAG na barra lateral</p>
                    </div>
                ) : (
                    <>
                        {/* Header */}
                        <div className="bg-white border-b border-slate-200 px-6 py-4 flex items-center gap-4">
                            <span
                                className="w-10 h-10 rounded-xl flex items-center justify-center text-xl flex-shrink-0"
                                style={{ backgroundColor: (selectedBase.cor || '#f59e0b') + '22' }}
                            >
                                {selectedBase.emoji || '📁'}
                            </span>
                            <div className="flex-1 min-w-0">
                                <h1 className="text-lg font-black text-slate-900 truncate">{selectedBase.nome}</h1>
                                {selectedBase.descricao && (
                                    <p className="text-xs text-slate-400 truncate">{selectedBase.descricao}</p>
                                )}
                            </div>
                            <div className="flex items-center gap-2">
                                {/* Search */}
                                <div className="flex items-center bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 gap-2 w-48">
                                    <svg className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                    </svg>
                                    <input
                                        value={searchTerm}
                                        onChange={e => setSearchTerm(e.target.value)}
                                        placeholder="Buscar documentos..."
                                        className="bg-transparent text-xs text-slate-700 outline-none w-full placeholder:text-slate-300"
                                    />
                                </div>
                                {/* Add Link */}
                                <button
                                    onClick={() => setIsAddLinkOpen(true)}
                                    className="flex items-center gap-1.5 px-3 py-2 bg-slate-50 border border-slate-200 text-slate-600 rounded-xl text-xs font-bold hover:bg-slate-100 transition-all"
                                >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                                    </svg>
                                    Link
                                </button>
                                {/* Upload */}
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    disabled={isUploading}
                                    className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 text-white rounded-xl text-xs font-bold hover:bg-violet-700 transition-all disabled:opacity-60"
                                >
                                    {isUploading ? (
                                        <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                        </svg>
                                    ) : (
                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                                        </svg>
                                    )}
                                    {isUploading ? 'Enviando...' : 'Upload'}
                                </button>
                                {/* Settings */}
                                <button
                                    onClick={() => setEditingBase(selectedBase)}
                                    className="w-9 h-9 flex items-center justify-center bg-slate-50 border border-slate-200 text-slate-500 rounded-xl hover:bg-slate-100 transition-all"
                                    title="Configurar base"
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                </button>
                            </div>
                        </div>

                        {/* Drop zone + Document list */}
                        <div
                            className={`flex-1 overflow-y-auto p-6 transition-all ${isDragging ? 'bg-violet-50 ring-2 ring-violet-400 ring-inset' : ''}`}
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
                                <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-center">
                                    <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mb-4">
                                        <svg className="w-8 h-8 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                                        </svg>
                                    </div>
                                    <p className="text-slate-400 font-semibold text-sm mb-1">Nenhum documento nesta base</p>
                                    <p className="text-slate-300 text-xs">Arraste arquivos aqui ou use o botão Upload</p>
                                </div>
                            ) : (
                                <div className="flex flex-col gap-2">
                                    {baseItems.map(item => (
                                        <div
                                            key={item.id}
                                            className="bg-white border border-slate-100 rounded-2xl px-4 py-3 flex items-center gap-3 hover:border-slate-200 hover:shadow-sm transition-all group"
                                        >
                                            <FileIcon tipo={item.tipo_arquivo} />
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-semibold text-slate-800 truncate">{item.titulo}</p>
                                                <div className="flex items-center gap-2 mt-0.5">
                                                    <span className="text-[10px] text-slate-400">
                                                        {new Date(item.data_criacao).toLocaleDateString('pt-BR')}
                                                    </span>
                                                    <VectorBadge hasEmbedding={!!(item as any).embedding} />
                                                    {item.tags && item.tags.length > 0 && item.tags.slice(0, 2).map(tag => (
                                                        <span key={tag} className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded-full font-medium">{tag}</span>
                                                    ))}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                {item.url_drive && item.url_drive !== '' && (
                                                    <a
                                                        href={item.url_drive}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
                                                        title="Abrir arquivo"
                                                    >
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
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
                                                        className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                                                        title={vectorizingId === item.id ? 'Vetorizando...' : 'Vetorizar agora'}
                                                    >
                                                        {vectorizingId === item.id ? (
                                                            <svg className="w-4 h-4 animate-spin text-violet-500" fill="none" viewBox="0 0 24 24">
                                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                                            </svg>
                                                        ) : (
                                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                                            </svg>
                                                        )}
                                                    </button>
                                                )}
                                                <button
                                                    onClick={() => handleDeleteItem(item.id)}
                                                    className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                                                    title="Remover"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
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
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
                    <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md p-6">
                        <h2 className="text-base font-black text-slate-900 mb-4">Adicionar Link</h2>
                        <div className="flex flex-col gap-3">
                            <div>
                                <label className="text-xs font-bold text-slate-500 mb-1 block">URL</label>
                                <input
                                    autoFocus
                                    value={linkUrl}
                                    onChange={e => setLinkUrl(e.target.value)}
                                    placeholder="https://..."
                                    className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-violet-500"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-bold text-slate-500 mb-1 block">Título (opcional)</label>
                                <input
                                    value={linkTitle}
                                    onChange={e => setLinkTitle(e.target.value)}
                                    onKeyDown={e => { if (e.key === 'Enter') handleAddLink(); }}
                                    placeholder="Nome do link..."
                                    className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-violet-500"
                                />
                            </div>
                        </div>
                        <div className="flex gap-2 mt-5">
                            <button onClick={handleAddLink} className="flex-1 py-2.5 bg-violet-600 text-white rounded-xl text-sm font-bold hover:bg-violet-700">Adicionar</button>
                            <button onClick={() => { setIsAddLinkOpen(false); setLinkUrl(''); setLinkTitle(''); }} className="flex-1 py-2.5 bg-slate-100 text-slate-600 rounded-xl text-sm font-bold hover:bg-slate-200">Cancelar</button>
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
}

const EditBaseModal: React.FC<EditBaseModalProps> = ({ base, onSave, onDelete, onClose }) => {
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
            <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
                <div className="p-6 border-b border-slate-100 flex items-center justify-between">
                    <h2 className="text-base font-black text-slate-900">Configurar Base RAG</h2>
                    <button onClick={onClose} className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-600 rounded-lg">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <div className="p-6 flex flex-col gap-4">
                    {/* Identity */}
                    <div className="flex gap-3">
                        <div>
                            <label className="text-xs font-bold text-slate-500 mb-1 block">Ícone</label>
                            <div className="grid grid-cols-4 gap-1">
                                {EMOJI_OPTIONS.map(e => (
                                    <button
                                        key={e}
                                        onClick={() => setEmoji(e)}
                                        className={`w-9 h-9 text-lg rounded-lg flex items-center justify-center transition-all ${emoji === e ? 'bg-violet-100 ring-2 ring-violet-400' : 'bg-slate-50 hover:bg-slate-100'}`}
                                    >{e}</button>
                                ))}
                            </div>
                        </div>
                        <div className="flex-1">
                            <label className="text-xs font-bold text-slate-500 mb-1 block">Cor</label>
                            <div className="grid grid-cols-4 gap-1">
                                {COLOR_OPTIONS.map(c => (
                                    <button
                                        key={c.value}
                                        onClick={() => setCor(c.value)}
                                        title={c.label}
                                        className={`w-9 h-9 rounded-lg transition-all ${cor === c.value ? 'ring-2 ring-offset-1 ring-slate-400 scale-110' : 'hover:scale-105'}`}
                                        style={{ backgroundColor: c.value }}
                                    />
                                ))}
                            </div>
                        </div>
                    </div>

                    <div>
                        <label className="text-xs font-bold text-slate-500 mb-1 block">Nome</label>
                        <input
                            value={nome}
                            onChange={e => setNome(e.target.value)}
                            className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-violet-500"
                        />
                    </div>

                    <div>
                        <label className="text-xs font-bold text-slate-500 mb-1 block">Descrição</label>
                        <input
                            value={descricao}
                            onChange={e => setDescricao(e.target.value)}
                            placeholder="Para que serve esta base?"
                            className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-violet-500"
                        />
                    </div>

                    {/* RAG Config */}
                    <div className="border-t border-slate-100 pt-4">
                        <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-3">Configuração RAG</p>
                        <div className="flex flex-col gap-3">
                            <label className="flex items-center gap-3 cursor-pointer">
                                <div
                                    onClick={() => setIncluirDiarios(!incluirDiarios)}
                                    className={`w-10 h-6 rounded-full transition-colors flex-shrink-0 ${incluirDiarios ? 'bg-violet-600' : 'bg-slate-200'}`}
                                >
                                    <div className={`w-4 h-4 bg-white rounded-full shadow m-1 transition-transform ${incluirDiarios ? 'translate-x-4' : ''}`} />
                                </div>
                                <span className="text-sm font-semibold text-slate-700">Incluir diários de bordo das ações</span>
                            </label>
                            <label className="flex items-center gap-3 cursor-pointer">
                                <div
                                    onClick={() => setIncluirManual(!incluirManual)}
                                    className={`w-10 h-6 rounded-full transition-colors flex-shrink-0 ${incluirManual ? 'bg-violet-600' : 'bg-slate-200'}`}
                                >
                                    <div className={`w-4 h-4 bg-white rounded-full shadow m-1 transition-transform ${incluirManual ? 'translate-x-4' : ''}`} />
                                </div>
                                <span className="text-sm font-semibold text-slate-700">Incluir manual do HERMES</span>
                            </label>
                            <div>
                                <label className="text-xs font-bold text-slate-500 mb-1 block">Categorias vinculadas</label>
                                <input
                                    value={categoriasInput}
                                    onChange={e => setCategoriasInput(e.target.value)}
                                    placeholder="TI, GESTÃO, FINANCEIRO"
                                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-violet-500"
                                />
                                <p className="text-[10px] text-slate-400 mt-1">Separe por vírgula</p>
                            </div>
                            <div>
                                <label className="text-xs font-bold text-slate-500 mb-1 block">Tags vinculadas</label>
                                <input
                                    value={tagsInput}
                                    onChange={e => setTagsInput(e.target.value)}
                                    placeholder="manual, procedimento"
                                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-violet-500"
                                />
                                <p className="text-[10px] text-slate-400 mt-1">Separe por vírgula</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="p-6 border-t border-slate-100 flex gap-2">
                    <button onClick={handleSave} className="flex-1 py-3 bg-violet-600 text-white rounded-2xl text-sm font-black hover:bg-violet-700">Salvar</button>
                    <button onClick={onClose} className="flex-1 py-3 bg-slate-100 text-slate-600 rounded-2xl text-sm font-black hover:bg-slate-200">Cancelar</button>
                    <button onClick={onDelete} className="py-3 px-4 bg-red-50 text-red-500 rounded-2xl text-sm font-black hover:bg-red-100">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    );
};

export default RAGBasesView;
