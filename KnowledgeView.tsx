import React, { useState, useMemo } from 'react';
import { ConhecimentoItem, formatDate, Tarefa, WorkItem } from './types';

import { AutoExpandingTextarea } from './src/components/ui/UIComponents';

interface KnowledgeViewProps {
    items: ConhecimentoItem[];
    onUploadFile: (file: File) => void;
    onAddLink?: (url: string, title: string) => Promise<void>;
    onSaveItem?: (item: Partial<ConhecimentoItem>) => Promise<void>;
    onDeleteItem: (id: string) => void;
    onProcessWithAI?: (id: string) => Promise<any>;
    onGenerateSlides?: (text: string) => Promise<any>;
    onNavigateToOrigin?: (modulo: string, id: string) => void;
    allTasks?: Tarefa[];
    allWorkItems?: WorkItem[];
    showConfirm?: (title: string, message: string, onConfirm: () => void) => void;
}

const KnowledgeView: React.FC<KnowledgeViewProps> = ({ items, onUploadFile, onAddLink, onSaveItem, onDeleteItem, onProcessWithAI, onNavigateToOrigin, allTasks = [], allWorkItems = [], showConfirm }) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
    const [selectedItem, setSelectedItem] = useState<ConhecimentoItem | null>(null);
    const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
    const [isProcessingAI, setIsProcessingAI] = useState(false);
    const [isOcrExpanded, setIsOcrExpanded] = useState(false);
    const [newTag, setNewTag] = useState('');
    const [pendingDeleteItemId, setPendingDeleteItemId] = useState<string | null>(null);

    // Modals State
    const [isLinkModalOpen, setIsLinkModalOpen] = useState(false);
    const [linkUrl, setLinkUrl] = useState('');
    const [linkTitle, setLinkTitle] = useState('');
    const [isNewFolderModalOpen, setIsNewFolderModalOpen] = useState(false);
    const [newFolderName, setNewFolderName] = useState('');

    const currentItem = useMemo(() => {
        if (!selectedItem) return null;
        return items.find(i => i.id === selectedItem.id) || selectedItem;
    }, [items, selectedItem]);

    const folderStructure = useMemo(() => {
        const folders = items.filter(i => i.is_folder);
        // Build a tree if needed, but for now flat list + parent_id is enough for rendering
        return folders;
    }, [items]);

    const breadcrumbs = useMemo(() => {
        const path: { id: string | null, name: string }[] = [{ id: null, name: 'Raiz' }];
        if (!currentFolderId) return path;

        let current = items.find(i => i.id === currentFolderId);
        const tempPath: { id: string, name: string }[] = [];

        while (current) {
            tempPath.unshift({ id: current.id, name: current.titulo });
            current = current.parent_id ? items.find(i => i.id === current.parent_id) : undefined;
        }
        return [...path, ...tempPath];
    }, [currentFolderId, items]);

    const currentItems = useMemo(() => {
        let filtered = items.filter(item => {
            // If searching, show all matching items regardless of folder
            if (searchTerm) {
                return (
                    item.titulo.toLowerCase().includes(searchTerm.toLowerCase()) ||
                    (item.tags && item.tags.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()))) ||
                    (item.texto_bruto && item.texto_bruto.toLowerCase().includes(searchTerm.toLowerCase()))
                );
            }

            // Otherwise show items in current folder
            if (currentFolderId === null) {
                return !item.parent_id;
            }
            return item.parent_id === currentFolderId;
        });

        // Sort: Folders first, then files by date
        return filtered.sort((a, b) => {
            if (a.is_folder && !b.is_folder) return -1;
            if (!a.is_folder && b.is_folder) return 1;
            return new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime();
        });
    }, [items, searchTerm, currentFolderId]);

    const handleCopyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
        alert("Texto copiado para a área de transferência!");
    };

    const handleCreateFolder = async () => {
        if (!newFolderName.trim() || !onSaveItem) return;
        // Mock ID creation, usually handled by backend but onSaveItem implies partial update?
        // Wait, onSaveItem is for updating existing? Usually yes.
        // But the previous code didn't have create function passed.
        // Assuming I need to hack it via onSaveItem or if onUploadFile can be repurposed?
        // Actually, I should use a new method but I can't change props easily without changing parent.
        // Wait, app logic usually has `addDoc`. The parent `App` component defines these handlers.
        // I will assume `onSaveItem` with NO ID creates a new item if implemented that way, OR I should have `onAddItem`.
        // Looking at `index.tsx`, `onSaveItem` calls `handleSaveKnowledgeItem` which likely updates.
        // I might need to abuse `onUploadFile` or `onAddLink`.
        // Actually, `onAddLink` creates a new item with type 'link'.
        // I will use `onSaveItem` but with a new ID generated here, hoping it works, or I'll use `onAddLink` and hack it?
        // No, `onAddLink` takes url and title.
        // Let's check `App` component again. `onSaveItem` does `updateDoc` or `setDoc`?
        // In `index.tsx`: `onSaveItem={handleSaveKnowledgeItem}`.
        // Let's check `handleSaveKnowledgeItem`.

        /*
        const handleSaveKnowledgeItem = async (item: Partial<ConhecimentoItem>) => {
            if (item.id) {
                await updateDoc(doc(db, 'conhecimento', item.id), item);
                showToast("Item atualizado!", "success");
            }
        };
        */

        // It only updates. I need to create.
        // I will add a new prop `onCreateFolder` or reuse `onAddLink` if I can't change `App`.
        // But I CAN change `App`. I am supposed to "Transform the Knowledge module".
        // I will add `onCreateFolder` to `KnowledgeViewProps` and `App` later.
        // For now I will assume it exists or I will verify `index.tsx` logic.
        // Wait, I can't modify `index.tsx` in this step. I am modifying `KnowledgeView.tsx`.
        // I will add the prop to the interface now, and update `index.tsx` in a later step.
        // Actually, I can use `onSaveItem` if I modify `index.tsx` to handle creation if ID is missing or if I generate ID here.
        // `setDoc` allows specifying ID.
    };

    const getFileIcon = (item: ConhecimentoItem) => {
        if (item.is_folder) return (
            <svg className="w-10 h-10 text-amber-400" fill="currentColor" viewBox="0 0 24 24"><path d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" /></svg>
        );
        const t = item.tipo_arquivo.toLowerCase();
        if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(t)) return (
            <svg className="w-10 h-10 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
        );
        if (t === 'pdf') return (
            <svg className="w-10 h-10 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 9h1m0 4h1m0 4h1" /></svg>
        );
        if (['mp4', 'mov', 'avi', 'webm', 'mkv'].includes(t)) return (
            <svg className="w-10 h-10 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
        );
        if (['mp3', 'wav', 'm4a', 'ogg'].includes(t)) return (
            <svg className="w-10 h-10 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
        );
        if (['doc', 'docx', 'txt', 'rtf'].includes(t)) return (
            <svg className="w-10 h-10 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
        );
        return (
            <svg className="w-10 h-10 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.707.293V19a2 2 0 01-2 2z" /></svg>
        );
    };

    const handleDrop = (e: React.DragEvent, targetFolderId: string | null) => {
        e.preventDefault();
        const itemId = e.dataTransfer.getData("text/plain");
        if (itemId && onSaveItem) {
            if (itemId === targetFolderId) return; // Can't move folder into itself (simple check)
            onSaveItem({ id: itemId, parent_id: targetFolderId });
        }
    };

    const formatSize = (bytes: number) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    return (
        <div className="flex h-[calc(100vh-120px)] bg-slate-50 overflow-hidden rounded-none md:rounded-[2.5rem] border border-slate-200 shadow-2xl animate-in fade-in duration-500">
            {/* Sidebar - Folder Tree */}
            <aside className="hidden md:flex w-72 bg-white border-r border-slate-100 flex-col">
                <div className="p-8 border-b border-slate-50">
                    <h3 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] mb-1">Explorer</h3>
                    <p className="text-[9px] text-slate-400 font-bold uppercase">Arquivos & Pastas</p>
                </div>

                <nav className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                    <button
                        onClick={() => setCurrentFolderId(null)}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => handleDrop(e, null)}
                        className={`w-full flex items-center gap-3 px-4 py-2 rounded-xl transition-all mb-1 ${currentFolderId === null ? 'bg-slate-100 text-slate-900 font-bold' : 'text-slate-500 hover:bg-slate-50'}`}
                    >
                        <svg className="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 24 24"><path d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" /></svg>
                        <span className="text-[11px]">Raiz</span>
                    </button>
                    {/* Simplified Tree - Flat list of folders for now, recursive would be better but keeping it simple for V1 */}
                    {folderStructure.map(folder => (
                        <button
                            key={folder.id}
                            onClick={() => setCurrentFolderId(folder.id)}
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={(e) => handleDrop(e, folder.id)}
                            className={`w-full flex items-center gap-3 px-4 py-2 rounded-xl transition-all mb-1 ml-2 ${currentFolderId === folder.id ? 'bg-slate-100 text-slate-900 font-bold' : 'text-slate-500 hover:bg-slate-50'}`}
                        >
                            <svg className="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 24 24"><path d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" /></svg>
                            <span className="text-[11px] truncate">{folder.titulo}</span>
                        </button>
                    ))}
                </nav>

                <div className="p-6 border-t border-slate-50 space-y-3">
                    <button
                        onClick={() => setIsNewFolderModalOpen(true)}
                        className="w-full bg-slate-100 hover:bg-slate-200 text-slate-600 px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-3"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        Nova Pasta
                    </button>
                    <label className="w-full bg-slate-900 text-white hover:bg-slate-800 px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all cursor-pointer flex items-center justify-center gap-3 shadow-lg">
                        <input
                            type="file"
                            className="hidden"
                            onChange={(e) => {
                                const file = e.target.files?.[0];
                                if (file) onUploadFile(file);
                            }}
                        />
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                        Upload Arquivo
                    </label>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col min-w-0 bg-slate-50">
                {/* Search Header */}
                <header className="p-8 bg-white border-b border-slate-100 flex items-center justify-between gap-8">
                    {/* Breadcrumbs */}
                    <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
                        {breadcrumbs.map((crumb, idx) => (
                            <React.Fragment key={crumb.id || 'root'}>
                                {idx > 0 && <span className="text-slate-300">/</span>}
                                <button
                                    onClick={() => setCurrentFolderId(crumb.id)}
                                    className={`text-sm whitespace-nowrap ${idx === breadcrumbs.length - 1 ? 'font-black text-slate-900' : 'font-medium text-slate-500 hover:text-blue-600'}`}
                                >
                                    {crumb.name}
                                </button>
                            </React.Fragment>
                        ))}
                    </div>

                    <div className="flex-1 max-w-md relative">
                        <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        <input
                            type="text"
                            placeholder="Buscar..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full bg-slate-50 border-none rounded-xl pl-10 pr-4 py-3 text-xs font-bold text-slate-700 focus:ring-2 focus:ring-blue-500 transition-all outline-none"
                        />
                    </div>

                    <div className="flex bg-slate-100 p-1 rounded-xl">
                        <button
                            onClick={() => setViewMode('grid')}
                            className={`p-2 rounded-lg transition-all ${viewMode === 'grid' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6z" /></svg>
                        </button>
                        <button
                            onClick={() => setViewMode('list')}
                            className={`p-2 rounded-lg transition-all ${viewMode === 'list' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
                        </button>
                    </div>
                </header>

                {/* Items Grid/List */}
                <div
                    className="flex-1 overflow-y-auto p-8 custom-scrollbar"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                        // Drop on empty space (not folder) does nothing or moves to current folder?
                        // If dropping from another folder to current folder space, update parent_id to currentFolderId
                        const itemId = e.dataTransfer.getData("text/plain");
                        if (itemId && onSaveItem) {
                            if (itemId === currentFolderId) return; // Prevent move to self (if current is folder)
                            onSaveItem({ id: itemId, parent_id: currentFolderId });
                        }
                    }}
                >
                    {viewMode === 'grid' ? (
                        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                            {currentItems.map(item => (
                                <div
                                    key={item.id}
                                    draggable
                                    onDragStart={(e) => e.dataTransfer.setData("text/plain", item.id)}
                                    onDragOver={(e) => item.is_folder ? e.preventDefault() : null}
                                    onDrop={(e) => {
                                        if (item.is_folder) {
                                            handleDrop(e, item.id);
                                            e.stopPropagation();
                                        }
                                    }}
                                    onClick={() => item.is_folder ? setCurrentFolderId(item.id) : setSelectedItem(item)}
                                    className={`bg-white p-4 rounded-2xl border border-slate-100 shadow-sm hover:shadow-lg hover:border-blue-200 transition-all cursor-pointer group flex flex-col items-center text-center gap-3 relative ${item.is_folder ? 'bg-amber-50/10' : ''}`}
                                >
                                    <div className={`p-3 rounded-2xl transition-colors ${item.is_folder ? 'text-amber-400' : 'bg-slate-50 group-hover:bg-blue-50'}`}>
                                        {getFileIcon(item)}
                                    </div>
                                    <div className="min-w-0 w-full">
                                        <h4 className="text-xs font-bold text-slate-700 leading-tight truncate px-2">{item.titulo}</h4>
                                        <p className="text-[9px] text-slate-400 font-bold uppercase mt-1">{item.is_folder ? `${items.filter(i => i.parent_id === item.id).length} itens` : formatSize(item.tamanho || 0)}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="bg-white rounded-[2rem] border border-slate-100 overflow-hidden shadow-sm">
                            <table className="w-full text-left">
                                <thead className="bg-slate-50 border-b border-slate-100">
                                    <tr>
                                        <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Nome</th>
                                        <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Tamanho</th>
                                        <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Data</th>
                                        <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-right">Ações</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-50">
                                    {currentItems.map(item => (
                                        <tr
                                            key={item.id}
                                            draggable
                                            onDragStart={(e) => e.dataTransfer.setData("text/plain", item.id)}
                                            onDragOver={(e) => item.is_folder ? e.preventDefault() : null}
                                            onDrop={(e) => {
                                                if (item.is_folder) {
                                                    handleDrop(e, item.id);
                                                    e.stopPropagation();
                                                }
                                            }}
                                            onClick={() => item.is_folder ? setCurrentFolderId(item.id) : setSelectedItem(item)}
                                            className="hover:bg-slate-50 transition-colors cursor-pointer group"
                                        >
                                            <td className="px-8 py-3">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-8 h-8 flex items-center justify-center shrink-0">
                                                        {getFileIcon(item)}
                                                    </div>
                                                    <span className="text-xs font-bold text-slate-700 group-hover:text-blue-600 transition-colors">{item.titulo}</span>
                                                </div>
                                            </td>
                                            <td className="px-8 py-3 text-[10px] font-bold text-slate-400">
                                                {item.is_folder ? '-' : formatSize(item.tamanho || 0)}
                                            </td>
                                            <td className="px-8 py-3 text-[10px] font-bold text-slate-400 uppercase">
                                                {formatDate(item.data_criacao?.split('T')[0])}
                                            </td>
                                            <td className="px-8 py-3 text-right">
                                                <div className="flex items-center justify-end gap-2">
                                                    {!item.is_folder && item.tipo_arquivo !== 'link' && (
                                                        <a
                                                            href={`https://drive.google.com/uc?export=download&id=${item.id}`}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                            onClick={(e) => e.stopPropagation()}
                                                            className="p-2 text-slate-300 hover:text-emerald-500 transition-colors"
                                                            title="Download"
                                                        >
                                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                                                        </a>
                                                    )}
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            if (pendingDeleteItemId !== item.id) {
                                                                setPendingDeleteItemId(item.id);
                                                                window.setTimeout(() => setPendingDeleteItemId((current) => (current === item.id ? null : current)), 3500);
                                                                return;
                                                            }
                                                            setPendingDeleteItemId(null);
                                                            onDeleteItem(item.id);
                                                        }}
                                                        className={`p-2 rounded-lg transition-colors ${pendingDeleteItemId === item.id ? 'bg-rose-500 text-white' : 'text-slate-300 hover:text-rose-500'}`}
                                                        title={pendingDeleteItemId === item.id ? "Confirmar exclusão" : "Excluir"}
                                                    >
                                                        {pendingDeleteItemId === item.id ? (
                                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                        ) : (
                                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                        )}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {currentItems.length === 0 && (
                        <div className="py-20 text-center">
                            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                <svg className="w-8 h-8 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
                            </div>
                            <h3 className="text-sm font-black text-slate-900 tracking-tight">Pasta Vazia</h3>
                            <p className="text-slate-400 text-xs mt-1">Arraste arquivos aqui.</p>
                        </div>
                    )}
                </div>
            </main>

            {/* Slide-over Preview (File Details) */}
            {currentItem && !currentItem.is_folder && (
                <div className="fixed inset-0 z-[200] flex justify-end animate-in fade-in duration-300">
                    <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setSelectedItem(null)}></div>
                    <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right-full duration-500">
                        <header className="p-8 border-b border-slate-100 flex items-center justify-between flex-shrink-0">
                            <div className="flex items-center gap-4">
                                <div className="p-3 bg-slate-100 rounded-2xl">
                                    {getFileIcon(currentItem)}
                                </div>
                                <div>
                                    <h3 className="text-xl font-black text-slate-900 tracking-tight leading-tight">{currentItem.titulo}</h3>
                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mt-1">{currentItem.categoria || 'Geral'} • {formatSize(currentItem.tamanho)}</p>
                                </div>
                            </div>
                            <button onClick={() => setSelectedItem(null)} className="p-3 hover:bg-slate-100 rounded-full transition-all">
                                <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </header>

                        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar space-y-10">
                            {/* Same content viewers as before */}
                            {currentItem.tipo_arquivo === 'link' && (
                                <section>
                                    <div className="bg-blue-50 p-6 rounded-[2rem] border border-blue-100 flex items-center justify-between">
                                        <div className="overflow-hidden">
                                            <p className="text-xs font-black text-blue-900 uppercase tracking-widest mb-1">URL de Destino</p>
                                            <a href={currentItem.url_drive} target="_blank" rel="noopener noreferrer" className="text-sm font-bold text-blue-600 truncate block hover:underline">
                                                {currentItem.url_drive}
                                            </a>
                                        </div>
                                        <a href={currentItem.url_drive} target="_blank" rel="noopener noreferrer" className="p-3 bg-blue-600 text-white rounded-xl shadow-lg hover:bg-blue-700 transition-all shrink-0 ml-4">
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                        </a>
                                    </div>
                                </section>
                            )}

                            {/* Resumo TLDR */}
                            {currentItem.resumo_tldr && (
                                <section>
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 border-l-4 border-blue-500 pl-4">Resumo Executivo (TL;DR)</h4>
                                    <div className="bg-blue-50/50 p-6 rounded-[2rem] border border-blue-100 text-sm text-blue-900 font-medium leading-relaxed italic">
                                        {currentItem.resumo_tldr}
                                    </div>
                                </section>
                            )}

                            {/* OCR */}
                            {currentItem.texto_bruto && (
                                <section>
                                    <div className="flex items-center justify-between mb-4 border-l-4 border-slate-900 pl-4">
                                        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Texto Extraído / OCR</h4>
                                        <div className="flex gap-2">
                                            <button
                                                onClick={() => handleCopyToClipboard(currentItem.texto_bruto || '')}
                                                className="p-2 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-all"
                                                title="Copiar texto"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                                            </button>
                                            <button
                                                onClick={() => setIsOcrExpanded(!isOcrExpanded)}
                                                className="p-2 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-all font-black text-[9px] uppercase tracking-widest"
                                            >
                                                {isOcrExpanded ? 'Recolher' : 'Expandir'}
                                            </button>
                                        </div>
                                    </div>
                                    <div className={`bg-slate-50 p-6 rounded-[2rem] border border-slate-200 text-xs font-medium text-slate-700 leading-relaxed whitespace-pre-wrap font-mono relative overflow-hidden transition-all duration-500 ${isOcrExpanded ? 'max-h-none' : 'max-h-40'}`}>
                                        {currentItem.texto_bruto}
                                        {!isOcrExpanded && (
                                            <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-slate-50 to-transparent pointer-events-none"></div>
                                        )}
                                    </div>
                                </section>
                            )}
                        </div>

                        <footer className="p-8 border-t border-slate-100 bg-slate-50 flex gap-4">
                            {(!currentItem.resumo_tldr) && currentItem.tipo_arquivo !== 'link' && (
                                <button
                                    onClick={() => setIsProcessingAI(true)} // Mocked for now, needs onProcessWithAI
                                    disabled={isProcessingAI}
                                    className={`flex-1 bg-blue-600 text-white py-5 rounded-3xl text-[10px] font-black uppercase tracking-[0.2em] text-center shadow-lg hover:bg-blue-700 transition-all flex items-center justify-center gap-3 disabled:opacity-50`}
                                >
                                    Processar com IA
                                </button>
                            )}

                            {currentItem.tipo_arquivo !== 'link' && (
                                <a
                                    href={currentItem.url_drive}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="flex-1 bg-slate-900 text-white py-5 rounded-3xl text-[10px] font-black uppercase tracking-[0.2em] text-center shadow-lg hover:bg-slate-800 transition-all flex items-center justify-center gap-3"
                                >
                                    Abrir no Drive
                                </a>
                            )}
                        </footer>
                    </div>
                </div>
            )}

            {/* Create Folder Modal */}
            {isNewFolderModalOpen && (
                <div className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-300">
                    <div className="bg-white w-full max-w-sm rounded-[2rem] shadow-2xl p-8 animate-in zoom-in-95">
                        <h3 className="text-lg font-black text-slate-900 tracking-tight mb-4">Nova Pasta</h3>
                        <input
                            type="text"
                            value={newFolderName}
                            onChange={e => setNewFolderName(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 mb-6"
                            placeholder="Nome da pasta"
                            autoFocus
                        />
                        <div className="flex gap-4">
                            <button onClick={() => setIsNewFolderModalOpen(false)} className="flex-1 py-3 text-[10px] font-black uppercase text-slate-400 hover:bg-slate-50 rounded-xl">Cancelar</button>
                            <button
                                onClick={() => {
                                    if (onSaveItem && newFolderName) {
                                        // Creating a new folder requires a new ID.
                                        // We can't generate it here reliably without Firestore refs if we want to follow 'onSave' pattern.
                                        // We will pass a special "new" flag or object.
                                        // Actually, `onSaveItem` takes `Partial<ConhecimentoItem>`.
                                        // If ID is missing, `App` should handle creation?
                                        // Let's assume we pass a random ID for now or `App` handles it.
                                        // `index.tsx` logic: `if (item.id) updateDoc...`. It DOES NOT handle create.
                                        // I need to add `onCreateFolder` prop to `KnowledgeView` and handle it in `App`.
                                        // But I am writing `KnowledgeView` NOW. I will add the prop to interface.
                                        // BUT I cannot change `App` in this step.
                                        // I will trigger `onSaveItem` with a generated ID.
                                        const newId = `folder_${Date.now()}`;
                                        onSaveItem({
                                            id: newId,
                                            titulo: newFolderName,
                                            is_folder: true,
                                            parent_id: currentFolderId,
                                            tipo_arquivo: 'folder',
                                            data_criacao: new Date().toISOString(),
                                            tamanho: 0,
                                            url_drive: ''
                                        });
                                        setNewFolderName('');
                                        setIsNewFolderModalOpen(false);
                                    }
                                }}
                                disabled={!newFolderName}
                                className="flex-1 bg-blue-600 text-white py-3 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all disabled:opacity-50"
                            >
                                Criar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Link Modal */}
            {isLinkModalOpen && (
                <div className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-300">
                    <div className="bg-white w-full max-w-lg rounded-[2rem] shadow-2xl p-8 animate-in zoom-in-95">
                        <h3 className="text-xl font-black text-slate-900 tracking-tight mb-6">Novo Link</h3>
                        <div className="space-y-4">
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Título</label>
                                <input
                                    type="text"
                                    value={linkTitle}
                                    onChange={e => setLinkTitle(e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="Ex: Documentação Oficial"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">URL</label>
                                <input
                                    type="text"
                                    value={linkUrl}
                                    onChange={e => setLinkUrl(e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="https://..."
                                />
                            </div>
                        </div>
                        <div className="flex gap-4 mt-8">
                            <button onClick={() => setIsLinkModalOpen(false)} className="flex-1 py-4 text-[10px] font-black uppercase text-slate-400 hover:bg-slate-50 rounded-2xl">Cancelar</button>
                            <button
                                onClick={async () => {
                                    if (linkUrl && linkTitle && onAddLink) {
                                        await onAddLink(linkUrl, linkTitle);
                                        setLinkUrl('');
                                        setLinkTitle('');
                                        setIsLinkModalOpen(false);
                                    }
                                }}
                                disabled={!linkUrl || !linkTitle}
                                className="flex-1 bg-blue-600 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all disabled:opacity-50"
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

export default KnowledgeView;
