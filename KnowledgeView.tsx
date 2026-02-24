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

const KnowledgeView: React.FC<KnowledgeViewProps> = ({ items, onUploadFile, onAddLink, onSaveItem, onDeleteItem, onProcessWithAI, onGenerateSlides, onNavigateToOrigin, allTasks = [], allWorkItems = [], showConfirm }) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
    const [selectedItem, setSelectedItem] = useState<ConhecimentoItem | null>(null);
    const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
    const [isProcessingAI, setIsProcessingAI] = useState(false);
    const [isOcrExpanded, setIsOcrExpanded] = useState(false);

    // Modals State
    const [isLinkModalOpen, setIsLinkModalOpen] = useState(false);
    const [linkUrl, setLinkUrl] = useState('');
    const [linkTitle, setLinkTitle] = useState('');

    const [isPresentationModalOpen, setIsPresentationModalOpen] = useState(false);
    const [presentationTitle, setPresentationTitle] = useState('');
    const [presentationDraft, setPresentationDraft] = useState('');
    const [generatedSlides, setGeneratedSlides] = useState<any>(null);
    const [isGeneratingSlides, setIsGeneratingSlides] = useState(false);

    const currentItem = useMemo(() => {
        if (!selectedItem) return null;
        return items.find(i => i.id === selectedItem.id) || selectedItem;
    }, [items, selectedItem]);

    const handleCopyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
        alert("Texto copiado para a área de transferência!");
    };

    const getOriginInfo = (origem: ConhecimentoItem['origem']) => {
        if (!origem) return { label: 'Upload Direto', title: 'Manual' };
        
        switch (origem.modulo) {
            case 'tarefas':
                const task = allTasks.find(t => t.id === origem.id_origem);
                return { label: 'Ação / Tarefa', title: task?.titulo || `Tarefa #${origem.id_origem}` };
            case 'sistemas':
                const workItem = allWorkItems.find(w => w.id === origem.id_origem);
                return { label: 'Log de Sistema', title: workItem?.descricao || `Log #${origem.id_origem}` };
            default:
                return { label: origem.modulo, title: origem.id_origem };
        }
    };

    const categories = useMemo(() => {
        const cats = new Set<string>();
        items.forEach(item => {
            if (item.categoria) cats.add(item.categoria);
        });
        return Array.from(cats).sort();
    }, [items]);

    const filteredItems = useMemo(() => {
        return items.filter(item => {
            const matchesSearch =
                item.titulo.toLowerCase().includes(searchTerm.toLowerCase()) ||
                (item.tags && item.tags.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()))) ||
                (item.texto_bruto && item.texto_bruto.toLowerCase().includes(searchTerm.toLowerCase()));

            const matchesCategory = !selectedCategory || item.categoria === selectedCategory;

            return matchesSearch && matchesCategory;
        }).sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime());
    }, [items, searchTerm, selectedCategory]);

    const handleAIProcess = async (id: string) => {
        setIsProcessingAI(true);
        try {
            if (onProcessWithAI) {
                const result = await onProcessWithAI(id);
                if (result && !result.success && result.error) {
                    alert(`Erro na IA: ${result.error}`);
                }
            } else {
                alert("Processamento com IA não configurado nesta tela.");
            }
        } catch (error: any) {
            alert(`Erro ao processar: ${error.message}`);
        } finally {
            setIsProcessingAI(false);
        }
    };

    const handleExportPPTX = async () => {
        if (!currentItem || !currentItem.slides_data) return;

        try {
            const pptxgen = (await import('pptxgenjs')).default;
            const pres = new pptxgen();
            const slidesData = currentItem.slides_data.slides || [];

            slidesData.forEach((slideInfo: any) => {
                const slide = pres.addSlide();

                // Background color default
                slide.background = { color: "FFFFFF" };

                if (slideInfo.layout === 'capa') {
                    slide.background = { color: "1e293b" }; // slate-800
                    slide.addText(slideInfo.titulo, { x: 1, y: 2, w: '80%', h: 1, fontSize: 44, color: "FFFFFF", bold: true, align: 'center' });
                    if (slideInfo.topicos && slideInfo.topicos.length > 0) {
                        slide.addText(slideInfo.topicos[0], { x: 1, y: 3.5, w: '80%', fontSize: 24, color: "cbd5e1", align: 'center' });
                    }
                } else {
                    // Header
                    slide.addText(slideInfo.titulo, { x: 0.5, y: 0.5, w: '90%', h: 0.8, fontSize: 32, color: "1e293b", bold: true });
                    slide.addShape(pres.ShapeType.line, { x: 0.5, y: 1.3, w: '90%', h: 0, line: { color: "3b82f6", width: 2 } });

                    // Content
                    if (slideInfo.topicos && Array.isArray(slideInfo.topicos)) {
                        slideInfo.topicos.forEach((topic: string, idx: number) => {
                            slide.addText(topic, {
                                x: 0.8,
                                y: 1.8 + (idx * 0.8),
                                w: '85%',
                                h: 0.6,
                                fontSize: 18,
                                color: "475569",
                                bullet: true
                            });
                        });
                    }
                }

                // Footer
                slide.addText("Gerado por Hermes AI", { x: 0.5, y: 5.2, fontSize: 10, color: "94a3b8" });
            });

            pres.writeFile({ fileName: `${currentItem.titulo}.pptx` });
        } catch (e) {
            console.error(e);
            alert("Erro ao gerar PPTX.");
        }
    };

    const handleExportTXT = () => {
        if (!currentItem) return;
        const element = document.createElement("a");
        const file = new Blob([currentItem.texto_bruto || ''], {type: 'text/plain'});
        element.href = URL.createObjectURL(file);
        element.download = `${currentItem.titulo}.txt`;
        document.body.appendChild(element);
        element.click();
    };

    const getFileIcon = (type: string) => {
        const t = type.toLowerCase();
        if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(t)) return (
            <svg className="w-10 h-10 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
        );
        if (t === 'pdf') return (
            <svg className="w-10 h-10 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 9h1m0 4h1m0 4h1" /></svg>
        );
        if (t === 'link') return (
            <svg className="w-10 h-10 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
        );
        if (t === 'apresentacao') return (
            <svg className="w-10 h-10 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" /></svg>
        );
        return (
            <svg className="w-10 h-10 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.707.293V19a2 2 0 01-2 2z" /></svg>
        );
    };

    return (
        <div className="flex h-[calc(100vh-120px)] bg-slate-50 overflow-hidden rounded-none md:rounded-[2.5rem] border border-slate-200 shadow-2xl animate-in fade-in duration-500">
            {/* Sidebar - Categorias */}
            <aside className="hidden md:flex w-72 bg-white border-r border-slate-100 flex-col">
                <div className="p-8 border-b border-slate-50">
                    <h3 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] mb-1">Repositório</h3>
                    <p className="text-[9px] text-slate-400 font-bold uppercase">Base de Conhecimento</p>
                </div>

                <nav className="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
                    <button
                        onClick={() => setSelectedCategory(null)}
                        className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${!selectedCategory ? 'bg-slate-900 text-white shadow-lg' : 'text-slate-500 hover:bg-slate-50'}`}
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
                        <span className="text-[11px] font-black uppercase tracking-wider">Todos os Arquivos</span>
                    </button>

                    <div className="pt-4">
                        <h4 className="px-4 text-[9px] font-black text-slate-300 uppercase tracking-widest mb-4">Categorias</h4>
                        {categories.map(cat => (
                            <button
                                key={cat}
                                onClick={() => setSelectedCategory(cat)}
                                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all mb-1 ${selectedCategory === cat ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-500 hover:bg-slate-50'}`}
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
                                <span className="text-[11px] font-black uppercase tracking-wider truncate">{cat}</span>
                            </button>
                        ))}
                    </div>
                </nav>

                <div className="p-6 border-t border-slate-50 space-y-3">
                    <label className="w-full bg-slate-100 hover:bg-slate-200 text-slate-600 px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all cursor-pointer flex items-center justify-center gap-3 border-2 border-dashed border-slate-200">
                        <input
                            type="file"
                            className="hidden"
                            onChange={(e) => {
                                const file = e.target.files?.[0];
                                if (file) onUploadFile(file);
                            }}
                        />
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        Novo Upload
                    </label>
                    <button
                        onClick={() => setIsLinkModalOpen(true)}
                        className="w-full bg-white hover:bg-slate-50 text-blue-600 border border-blue-100 px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-3"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
                        Novo Link
                    </button>
                    <button
                        onClick={() => {
                            setPresentationTitle('');
                            setPresentationDraft('');
                            setGeneratedSlides(null);
                            setIsPresentationModalOpen(true);
                        }}
                        className="w-full bg-white hover:bg-slate-50 text-orange-600 border border-orange-100 px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-3"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" /></svg>
                        Apresentação
                    </button>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col min-w-0 bg-slate-50">
                {/* Search Header */}
                <header className="p-8 bg-white border-b border-slate-100 flex items-center justify-between gap-8">
                    <div className="flex-1 relative">
                        <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        <input
                            type="text"
                            placeholder="Buscar por título, conteúdo ou tags..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full bg-slate-50 border-none rounded-2xl pl-12 pr-6 py-4 text-sm font-bold text-slate-700 focus:ring-2 focus:ring-blue-500 transition-all outline-none"
                        />
                    </div>
                    <div className="flex bg-slate-100 p-1 rounded-xl">
                        <button
                            onClick={() => setViewMode('grid')}
                            className={`p-2 rounded-lg transition-all ${viewMode === 'grid' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>
                        </button>
                        <button
                            onClick={() => setViewMode('list')}
                            className={`p-2 rounded-lg transition-all ${viewMode === 'list' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" /></svg>
                        </button>
                    </div>
                </header>

                {/* Items Grid/List */}
                <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
                    {viewMode === 'grid' ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                            {filteredItems.map(item => (
                                <div
                                    key={item.id}
                                    onClick={() => setSelectedItem(item)}
                                    className="bg-white p-6 rounded-[2rem] border border-slate-100 shadow-sm hover:shadow-xl hover:border-blue-200 transition-all cursor-pointer group flex flex-col h-full"
                                >
                                    <div className="flex justify-between items-start mb-6">
                                        <div className="p-3 bg-slate-50 rounded-2xl group-hover:bg-blue-50 transition-colors">
                                            {getFileIcon(item.tipo_arquivo)}
                                        </div>
                                        {item.categoria && (
                                            <span className="text-[8px] font-black uppercase px-2 py-1 bg-blue-50 text-blue-600 rounded-lg tracking-widest">
                                                {item.categoria}
                                            </span>
                                        )}
                                    </div>
                                    <h4 className="text-sm font-black text-slate-900 leading-tight mb-3 line-clamp-2 group-hover:text-blue-600 transition-colors">{item.titulo}</h4>

                                    {item.tipo_arquivo === 'link' ? (
                                        <div className="flex-1 text-[10px] text-blue-500 font-bold mb-4 break-all">
                                            {item.url_drive}
                                        </div>
                                    ) : item.resumo_tldr ? (
                                        <p className="text-[11px] text-slate-500 font-medium line-clamp-3 mb-4 leading-relaxed">
                                            {item.resumo_tldr}
                                        </p>
                                    ) : (
                                        <div className="flex-1 flex items-center gap-2 text-slate-300 italic text-[10px] mb-4">
                                            {item.tipo_arquivo !== 'link' && (
                                                <>
                                                    <div className="w-2 h-2 bg-slate-200 rounded-full animate-pulse"></div>
                                                    Processando IA...
                                                </>
                                            )}
                                        </div>
                                    )}

                                    <div className="mt-auto pt-4 border-t border-slate-50 flex flex-wrap gap-1.5">
                                        {(item.tags || []).slice(0, 3).map(tag => (
                                            <span key={tag} className="text-[8px] font-bold text-slate-400 border border-slate-100 px-2 py-0.5 rounded-md">#{tag}</span>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="bg-white rounded-[2rem] border border-slate-100 overflow-hidden shadow-sm">
                            <table className="w-full text-left">
                                <thead className="bg-slate-50 border-b border-slate-100">
                                    <tr>
                                        <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Nome do Arquivo</th>
                                        <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Categoria</th>
                                        <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Data</th>
                                        <th className="px-8 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-right">Ações</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-50">
                                    {filteredItems.map(item => (
                                        <tr
                                            key={item.id}
                                            onClick={() => setSelectedItem(item)}
                                            className="hover:bg-slate-50 transition-colors cursor-pointer group"
                                        >
                                            <td className="px-8 py-4">
                                                <div className="flex items-center gap-4">
                                                    <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center shrink-0">
                                                        {getFileIcon(item.tipo_arquivo)}
                                                    </div>
                                                    <span className="text-sm font-bold text-slate-700 group-hover:text-blue-600 transition-colors">{item.titulo}</span>
                                                </div>
                                            </td>
                                            <td className="px-8 py-4">
                                                <span className="text-[10px] font-black uppercase text-slate-400 tracking-widest">{item.categoria || 'Geral'}</span>
                                            </td>
                                            <td className="px-8 py-4 text-[10px] font-bold text-slate-400 uppercase">
                                                {formatDate(item.data_criacao?.split('T')[0])}
                                            </td>
                                            <td className="px-8 py-4 text-right">
                                                <div className="flex items-center justify-end gap-2">
                                                    {item.tipo_arquivo !== 'link' && item.tipo_arquivo !== 'apresentacao' && (
                                                        <a
                                                            href={`https://drive.google.com/uc?export=download&id=${item.id}`}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                            onClick={(e) => e.stopPropagation()}
                                                            className="p-2 text-slate-300 hover:text-emerald-500 transition-colors"
                                                            title="Download"
                                                        >
                                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                                                        </a>
                                                    )}
                                                    <button
                                                        onClick={(e) => { e.stopPropagation(); if(window.confirm("Excluir item?")) onDeleteItem(item.id); }}
                                                        className="p-2 text-slate-300 hover:text-rose-500 transition-colors"
                                                        title="Excluir"
                                                    >
                                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {filteredItems.length === 0 && (
                        <div className="py-20 text-center">
                            <div className="w-20 h-20 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-6">
                                <svg className="w-10 h-10 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                            </div>
                            <h3 className="text-lg font-black text-slate-900 tracking-tight">Nenhum arquivo encontrado</h3>
                            <p className="text-slate-400 text-sm mt-1">Tente ajustar seus termos de busca ou categoria.</p>
                        </div>
                    )}
                </div>
            </main>

            {/* Slide-over Preview */}
            {currentItem && (
                <div className="fixed inset-0 z-[200] flex justify-end animate-in fade-in duration-300">
                    <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setSelectedItem(null)}></div>
                    <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right-full duration-500">
                        <header className="p-8 border-b border-slate-100 flex items-center justify-between flex-shrink-0">
                            <div className="flex items-center gap-4">
                                <div className="p-3 bg-slate-100 rounded-2xl">
                                    {getFileIcon(currentItem.tipo_arquivo)}
                                </div>
                                <div>
                                    <h3 className="text-xl font-black text-slate-900 tracking-tight leading-tight">{currentItem.titulo}</h3>
                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mt-1">{currentItem.categoria || 'Geral'}</p>
                                </div>
                            </div>
                            <button onClick={() => setSelectedItem(null)} className="p-3 hover:bg-slate-100 rounded-full transition-all">
                                <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </header>

                        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar space-y-10">

                            {/* Conteúdo Link */}
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

                            {/* Conteúdo Apresentação */}
                            {currentItem.tipo_arquivo === 'apresentacao' && (
                                <section>
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between">
                                            <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Conteúdo da Apresentação</h4>
                                            <div className="flex gap-2">
                                                <button onClick={handleExportPPTX} className="bg-orange-500 hover:bg-orange-600 text-white px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all">
                                                    PPTX
                                                </button>
                                                <button onClick={handleExportTXT} className="bg-slate-200 hover:bg-slate-300 text-slate-600 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all">
                                                    TXT
                                                </button>
                                            </div>
                                        </div>
                                        <div className="bg-slate-50 p-6 rounded-[2rem] border border-slate-200 text-sm font-medium text-slate-700 leading-relaxed whitespace-pre-wrap font-mono max-h-60 overflow-y-auto">
                                            {currentItem.texto_bruto || "Sem conteúdo."}
                                        </div>
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

                            {/* Conteúdo Extraído (para docs/imagens) */}
                            {currentItem.texto_bruto && currentItem.tipo_arquivo !== 'apresentacao' && (
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

                            {/* Tags */}
                            {(currentItem.tags || []).length > 0 && (
                                <section>
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4">Tags Identificadas</h4>
                                    <div className="flex flex-wrap gap-2">
                                        {currentItem.tags?.map(tag => (
                                            <span key={tag} className="bg-slate-100 text-slate-600 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest border border-slate-200">
                                                #{tag}
                                            </span>
                                        ))}
                                    </div>
                                </section>
                            )}

                            {/* Metadados */}
                            <section className="pt-10 border-t border-slate-100 grid grid-cols-2 gap-8">
                                <div>
                                    <h5 className="text-[9px] font-black text-slate-400 uppercase mb-1">Data de Criação</h5>
                                    <p className="text-xs font-bold text-slate-900">{formatDate(currentItem.data_criacao?.split('T')[0])}</p>
                                </div>
                                <div>
                                    <h5 className="text-[9px] font-black text-slate-400 uppercase mb-1">Origem</h5>
                                    <button 
                                        disabled={!currentItem.origem || !onNavigateToOrigin}
                                        onClick={() => currentItem.origem && onNavigateToOrigin && onNavigateToOrigin(currentItem.origem.modulo, currentItem.origem.id_origem)}
                                        className={`text-xs font-bold text-left transition-all ${currentItem.origem ? 'text-blue-600 hover:text-blue-800 hover:underline' : 'text-slate-900'}`}
                                    >
                                        <div className="text-[8px] opacity-60 uppercase mb-0.5">{getOriginInfo(currentItem.origem).label}</div>
                                        {getOriginInfo(currentItem.origem).title}
                                    </button>
                                </div>
                            </section>

                            {/* Diário de Bordo / Contexto de Origem */}
                            {currentItem.origem && (
                                <section className="pt-10 border-t border-slate-100">
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-6 flex items-center gap-3">
                                        <span className="w-1.5 h-1.5 rounded-full bg-violet-500"></span>
                                        Diário de Bordo / Histórico
                                    </h4>

                                    <div className="space-y-4">
                                        {currentItem.origem.modulo === 'tarefas' && (() => {
                                            const task = allTasks.find(t => t.id === currentItem.origem?.id_origem);
                                            if (!task || !task.acompanhamento || task.acompanhamento.length === 0) {
                                                return <p className="text-xs text-slate-400 italic">Nenhum registro encontrado na tarefa de origem.</p>;
                                            }
                                            return task.acompanhamento.map((log, idx) => (
                                                <div key={idx} className="bg-slate-50 border border-slate-100 p-4 rounded-2xl relative">
                                                    <div className="flex items-center justify-between mb-2">
                                                        <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">
                                                            {new Date(log.data).toLocaleDateString('pt-BR')} {new Date(log.data).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                                                        </span>
                                                    </div>
                                                    <p className="text-xs font-medium text-slate-600 leading-relaxed whitespace-pre-wrap">
                                                        {log.nota.startsWith('LINK::') ? log.nota.split('::')[1] || log.nota.split('::')[2] : 
                                                         log.nota.startsWith('FILE::') ? log.nota.split('::')[1] : 
                                                         log.nota.startsWith('CONTACT::') ? log.nota.split('::')[1] : 
                                                         log.nota}
                                                    </p>
                                                    {log.nota.includes('::') && (
                                                        <div className="mt-2 text-[8px] font-black text-blue-500 uppercase tracking-widest">Anexo Registrado</div>
                                                    )}
                                                </div>
                                            ));
                                        })()}

                                        {currentItem.origem.modulo === 'sistemas' && (() => {
                                            const workItem = allWorkItems.find(w => w.id === currentItem.origem?.id_origem);
                                            if (!workItem) return <p className="text-xs text-slate-400 italic">Nenhum registro encontrado no log de sistema.</p>;
                                            return (
                                                <div className="bg-slate-50 border border-slate-100 p-4 rounded-2xl">
                                                    <div className="flex items-center justify-between mb-2">
                                                        <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">
                                                            {new Date(workItem.data_criacao).toLocaleDateString('pt-BR')}
                                                        </span>
                                                        <span className="text-[8px] font-black px-2 py-0.5 rounded uppercase bg-violet-100 text-violet-700">
                                                            {workItem.tipo}
                                                        </span>
                                                    </div>
                                                    <p className="text-xs font-medium text-slate-600 leading-relaxed whitespace-pre-wrap">{workItem.descricao}</p>
                                                </div>
                                            );
                                        })()}

                                        {currentItem.origem.modulo === 'saude' && (
                                            <p className="text-xs text-slate-400 italic">Este item faz parte de um registro de saúde (exame/consulta).</p>
                                        )}
                                    </div>
                                </section>
                            )}
                        </div>

                        <footer className="p-8 border-t border-slate-100 bg-slate-50 flex gap-4">
                            {/* Botão de Processamento IA */}
                            {(!currentItem.resumo_tldr || !currentItem.tags) && currentItem.tipo_arquivo !== 'link' && currentItem.tipo_arquivo !== 'apresentacao' && (
                                <button
                                    onClick={() => handleAIProcess(currentItem.id)}
                                    disabled={isProcessingAI}
                                    className={`flex-1 bg-blue-600 text-white py-5 rounded-3xl text-[10px] font-black uppercase tracking-[0.2em] text-center shadow-lg hover:bg-blue-700 transition-all flex items-center justify-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed`}
                                >
                                    {isProcessingAI ? (
                                        <>
                                            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                                            Processando...
                                        </>
                                    ) : (
                                        <>
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                            Processar com IA
                                        </>
                                    )}
                                </button>
                            )}

                            {currentItem.tipo_arquivo !== 'link' && currentItem.tipo_arquivo !== 'apresentacao' && (
                                <>
                                    <a
                                        href={`https://drive.google.com/uc?export=download&id=${currentItem.id}`}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="flex-1 bg-emerald-600 text-white py-5 rounded-3xl text-[10px] font-black uppercase tracking-[0.2em] text-center shadow-lg hover:bg-emerald-700 transition-all flex items-center justify-center gap-3"
                                    >
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                                        Download
                                    </a>

                                    <a
                                        href={currentItem.url_drive}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="flex-1 bg-slate-900 text-white py-5 rounded-3xl text-[10px] font-black uppercase tracking-[0.2em] text-center shadow-lg hover:bg-slate-800 transition-all flex items-center justify-center gap-3"
                                    >
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                        Abrir no Drive
                                    </a>
                                </>
                            )}
                            {currentItem.tipo_arquivo === 'apresentacao' && (
                                <button
                                    onClick={() => {
                                        setPresentationTitle(currentItem.titulo);
                                        setPresentationDraft(currentItem.texto_bruto || '');
                                        setGeneratedSlides(currentItem.slides_data);
                                        setIsPresentationModalOpen(true);
                                    }}
                                    className="flex-1 bg-orange-500 text-white py-5 rounded-3xl text-[10px] font-black uppercase tracking-[0.2em] text-center shadow-lg hover:bg-orange-600 transition-all flex items-center justify-center gap-3"
                                >
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                    Editar Apresentação
                                </button>
                            )}
                            <button
                                title="Excluir"
                                onClick={() => { if(window.confirm("Excluir item?")) { onDeleteItem(currentItem.id); setSelectedItem(null); } }}
                                className="px-6 bg-white border border-rose-100 text-rose-500 rounded-3xl hover:bg-rose-50 transition-all"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                            </button>
                        </footer>
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

            {/* Presentation Modal */}
            {isPresentationModalOpen && (
                <div className="fixed inset-0 z-[300] bg-white md:bg-black/60 md:backdrop-blur-sm flex items-center justify-center p-0 md:p-8 animate-in fade-in duration-300">
                    <div className="bg-white w-full h-full md:h-auto md:max-w-5xl md:rounded-[2.5rem] flex flex-col overflow-hidden shadow-2xl">
                        <div className="p-6 md:p-10 border-b border-slate-100 flex items-center justify-between bg-white sticky top-0 z-10">
                            <div>
                                <h3 className="text-2xl font-black text-slate-900 tracking-tight">Editor de Apresentações</h3>
                                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">IA Powered Slides Generator</p>
                            </div>
                            <button onClick={() => setIsPresentationModalOpen(false)} className="p-3 bg-slate-100 text-slate-500 rounded-full hover:bg-slate-200 transition-all">
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>

                        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
                            {/* Left: Input */}
                            <div className="w-full md:w-1/2 p-6 md:p-10 border-r border-slate-100 flex flex-col gap-6 overflow-y-auto">
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Título da Apresentação</label>
                                    <input
                                        type="text"
                                        value={presentationTitle}
                                        onChange={e => setPresentationTitle(e.target.value)}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-lg font-bold text-slate-900 outline-none focus:ring-2 focus:ring-orange-500 mt-2"
                                        placeholder="Título Principal..."
                                    />
                                </div>
                                <div className="flex-1 flex flex-col">
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Rascunho / Conteúdo Bruto</label>
                                    <AutoExpandingTextarea
                                        value={presentationDraft}
                                        onChange={e => setPresentationDraft(e.target.value)}
                                        className="flex-1 w-full bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-orange-500 mt-2 leading-relaxed"
                                        placeholder="Cole aqui o texto, anotações ou tópicos que deseja transformar em slides..."
                                    />
                                </div>
                                <button
                                    onClick={async () => {
                                        setIsGeneratingSlides(true);
                                        try {
                                            if (onGenerateSlides) {
                                                const result = await onGenerateSlides(presentationDraft);
                                                setGeneratedSlides(result);
                                            } else {
                                                alert("Função de geração não configurada.");
                                            }
                                        } catch (e) {
                                            console.error(e);
                                            alert("Erro ao gerar slides.");
                                        } finally {
                                            setIsGeneratingSlides(false);
                                        }
                                    }}
                                    disabled={isGeneratingSlides || !presentationDraft}
                                    className="w-full bg-slate-900 text-white py-4 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50 flex items-center justify-center gap-3"
                                >
                                    {isGeneratingSlides ? (
                                        <>
                                            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                                            Gerando Estrutura...
                                        </>
                                    ) : (
                                        <>
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>
                                            Gerar Slides com IA
                                        </>
                                    )}
                                </button>
                            </div>

                            {/* Right: Preview */}
                            <div className="w-full md:w-1/2 p-6 md:p-10 bg-slate-50 flex flex-col gap-6 overflow-y-auto border-t md:border-t-0 md:border-l border-slate-100">
                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Preview da Estrutura</h4>
                                {generatedSlides ? (
                                    <div className="space-y-6">
                                        {(generatedSlides.slides || []).map((slide: any, idx: number) => (
                                            <div key={idx} className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                                                <div className="flex justify-between items-start mb-4">
                                                    <span className="text-[9px] font-black text-slate-300 uppercase tracking-widest">Slide {slide.numero} • {slide.layout}</span>
                                                </div>
                                                <h5 className="text-lg font-black text-slate-900 mb-2">{slide.titulo}</h5>
                                                <ul className="list-disc pl-5 space-y-1">
                                                    {(slide.topicos || []).map((t: string, i: number) => (
                                                        <li key={i} className="text-sm text-slate-600">{t}</li>
                                                    ))}
                                                </ul>
                                                {slide.prompt_imagem && (
                                                    <div className="mt-4 p-3 bg-slate-50 rounded-xl text-[10px] text-slate-500 italic border border-slate-100">
                                                        Prompt: {slide.prompt_imagem}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="flex-1 flex flex-col items-center justify-center text-slate-300 gap-4 opacity-50">
                                        <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                                        <p className="text-xs font-black uppercase tracking-widest">Nenhum slide gerado</p>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="p-6 md:p-8 bg-white border-t border-slate-100 flex gap-4">
                            <button onClick={() => setIsPresentationModalOpen(false)} className="flex-1 py-4 text-[10px] font-black uppercase text-slate-400 hover:bg-slate-50 rounded-2xl">Fechar</button>
                            <button
                                onClick={async () => {
                                    if (onSaveItem && presentationTitle) {
                                        await onSaveItem({
                                            id: selectedItem?.id,
                                            titulo: presentationTitle,
                                            texto_bruto: presentationDraft,
                                            slides_data: generatedSlides,
                                            tipo_arquivo: 'apresentacao',
                                            categoria: 'Apresentações'
                                        });
                                        setIsPresentationModalOpen(false);
                                    }
                                }}
                                disabled={!presentationTitle}
                                className="flex-1 bg-orange-500 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-orange-600 transition-all disabled:opacity-50"
                            >
                                Salvar Apresentação
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default KnowledgeView;
