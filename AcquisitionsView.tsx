import React, { useState, useEffect } from 'react';
import { collection, query, onSnapshot, addDoc, doc, updateDoc, where } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from './firebase';
import { ItemOrcamento, TransacaoProjeto, Cotacao } from './types';

// Utility formatters
const formatCurrency = (val: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(val);

interface AcquisitionsViewProps {
    projetoId: string;
}

export const AcquisitionsView: React.FC<AcquisitionsViewProps> = ({ projetoId }) => {
    const [activeTab, setActiveTab] = useState<'needs' | 'process'>('needs');
    const [items, setItems] = useState<ItemOrcamento[]>([]);
    const [transactions, setTransactions] = useState<TransacaoProjeto[]>([]);

    // OCR & Upload State
    const [isUploading, setIsUploading] = useState(false);
    const [ocrResult, setOcrResult] = useState<any>(null);
    const [invoiceFileId, setInvoiceFileId] = useState<string | null>(null);
    const [invoiceUrl, setInvoiceUrl] = useState<string | null>(null);

    // Form State for New Transaction
    const [formDescription, setFormDescription] = useState('');
    const [formAmount, setFormAmount] = useState<number>(0);
    const [formDate, setFormDate] = useState('');
    const [selectedItemId, setSelectedItemId] = useState('');
    const [formQuotes, setFormQuotes] = useState<Cotacao[]>([]);

    // Auto Quote State
    const [quotingItemId, setQuotingItemId] = useState<string | null>(null);

    useEffect(() => {
        if (!projetoId) return;

        const qItems = query(collection(db, 'projetos', projetoId, 'itens_orcamento'));
        const unsubItems = onSnapshot(qItems, (snapshot) => {
            setItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as ItemOrcamento)));
        });

        const qTrans = query(collection(db, 'projetos', projetoId, 'transacoes'));
        const unsubTrans = onSnapshot(qTrans, (snapshot) => {
            setTransactions(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as TransacaoProjeto)));
        });

        return () => {
            unsubItems();
            unsubTrans();
        };
    }, [projetoId]);

    const handleFileUpload = async (file: File) => {
        setIsUploading(true);
        try {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = async () => {
                const base64 = (reader.result as string).split(',')[1];
                const uploadFunc = httpsCallable(functions, 'upload_to_drive');

                // 1. Upload to Drive
                const uploadRes = await uploadFunc({
                    fileName: `NFE_${Date.now()}_${file.name}`,
                    fileContent: base64,
                    mimeType: file.type,
                    folderId: null // Use default/root
                });

                const { fileId, webViewLink } = uploadRes.data as any;
                setInvoiceFileId(fileId);
                setInvoiceUrl(webViewLink);

                // 2. Trigger OCR
                const ocrFunc = httpsCallable(functions, 'processInvoiceOCR');
                const ocrRes = await ocrFunc({ fileId });
                const data = ocrRes.data as any;

                setOcrResult(data);

                // Auto-fill form
                if (data) {
                    setFormDescription(data.fornecedor ? `Compra ${data.fornecedor}` : 'Nova Aquisição');
                    setFormAmount(data.valor_total || 0);
                    setFormDate(data.data_emissao || new Date().toISOString().split('T')[0]);

                    // Try to match item by similarity (simple substring check for now)
                    if (data.itens && data.itens.length > 0) {
                        const desc = data.itens[0].descricao.toLowerCase();
                        const match = items.find(i => desc.includes(i.nome.toLowerCase()) || i.nome.toLowerCase().includes(desc));
                        if (match) setSelectedItemId(match.id);
                    }
                }

                setIsUploading(false);
            };
        } catch (error) {
            console.error(error);
            alert("Erro ao processar arquivo.");
            setIsUploading(false);
        }
    };

    const handleGetQuotes = async (item: ItemOrcamento) => {
        setQuotingItemId(item.id);
        try {
            if ((import.meta as any).env?.DEV) {
               // In local dev, we might need to proxy if using specific setup,
               // but typically standard callable works if emulators are set up or pointing to prod.
               // Assuming standard firebase config points to where functions are hosted.
            }

            // Note: The function 'getQuotes' is in the Node.js codebase (functions_node).
            // Ensure your firebase config allows calling it.
            // If they are deployed to the same project, simple name reference works.
            const quoteFunc = httpsCallable(functions, 'getQuotes');
            const res = await quoteFunc({ searchTerm: item.nome });
            const data = res.data as any;

            // Save quote to temporary state or directly to item?
            // Let's create a transaction draft or just alert for now,
            // OR update the item with "suggested quote".
            // For this view, let's just show it.
            alert(`Cotação Encontrada!\nVendor: ${data.vendor}\nValor: R$ ${data.price}\n\n(Screenshot salva)`);

            // In a real app, we'd save this to a "Cotacoes" subcollection or field.

        } catch (error: any) {
            console.error(error);
            alert("Erro ao buscar cotação: " + error.message);
        } finally {
            setQuotingItemId(null);
        }
    };

    const handleSaveTransaction = async () => {
        if (!selectedItemId || !formAmount) {
            alert("Preencha os campos obrigatórios.");
            return;
        }

        // Compliance Check
        if (formAmount > 1000 && formQuotes.length < 3) {
            if (!confirm(`ATENÇÃO: Valor superior a R$ 1.000,00 exige 3 cotações (você tem ${formQuotes.length}).\nDeseja salvar mesmo assim com pendência?`)) {
                return;
            }
        }

        try {
            await addDoc(collection(db, 'projetos', projetoId, 'transacoes'), {
                projeto_id: projetoId,
                item_orcamento_id: selectedItemId,
                descricao: formDescription,
                valor_real: formAmount,
                data_pagamento: formDate,
                nota_fiscal_url: invoiceUrl,
                status: 'pendente', // Requires approval/payment check
                tipo: 'compra',
                cotacoes: formQuotes
            });

            // Reset form
            setOcrResult(null);
            setInvoiceFileId(null);
            setFormDescription('');
            setFormAmount(0);
            setFormDate('');
            setSelectedItemId('');
            setFormQuotes([]);
            alert("Aquisição registrada com sucesso!");
            setActiveTab('needs');
        } catch (error) {
            console.error(error);
            alert("Erro ao salvar.");
        }
    };

    const pendingItems = items.filter(i => {
        const totalReal = transactions
            .filter(t => t.item_orcamento_id === i.id && t.status !== 'cancelado')
            .reduce((acc, curr) => acc + curr.valor_real, 0);
        return i.status !== 'executado' && (totalReal < (i.quantidade * i.valor_unitario_estimado));
    });

    return (
        <div className="p-6 space-y-12 animate-in fade-in duration-500 bg-surface min-h-screen">
            {/* Título de Seção Industrial */}
            <div className="border-b-2 border-primary-tactile pb-4">
                <h2 className="text-3xl font-mono font-bold text-on-surface">Acquisitions_Inventory</h2>
                <div className="flex items-center gap-2 mt-2">
                    <span className="text-[10px] font-mono font-bold text-primary-tactile uppercase tracking-widest">// PROJECT_ID: {projetoId}</span>
                    <span className="w-1 h-1 rounded-full bg-primary-tactile"></span>
                    <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">STATUS: SYSTEM_READY</span>
                </div>
            </div>

            {/* Tabs Industriais */}
            <div className="flex gap-1 bg-slate-100 p-1 rounded-none border border-border-grid">
                    <button
                        onClick={() => setActiveTab('needs')}
                        className={`flex-1 py-3 px-4 text-[10px] font-mono font-bold uppercase tracking-[0.2em] transition-all ${activeTab === 'needs' ? 'bg-white text-on-surface border border-border-grid' : 'text-slate-400 hover:text-on-surface hover:bg-white/50'}`}
                    >
                    NEEDS_INVENTORY
                </button>
                    <button
                        onClick={() => setActiveTab('process')}
                        className={`flex-1 py-3 px-4 text-[10px] font-mono font-bold uppercase tracking-[0.2em] transition-all ${activeTab === 'process' ? 'bg-white text-on-surface border border-border-grid' : 'text-slate-400 hover:text-on-surface hover:bg-white/50'}`}
                    >
                    OCR_AI_PROCESSOR
                </button>
            </div>

            {activeTab === 'needs' && (
                <div className="bg-surface rounded-none border border-border-grid p-0 shadow-none">
                    <div className="p-6 border-b border-border-grid bg-slate-50/50">
                        <h3 className="text-lg font-mono font-bold text-on-surface">Pending_Procurement</h3>
                        <p className="text-slate-500 font-mono text-[10px] uppercase tracking-widest mt-1">LOG: PENDING_ACQUISITIONS_DETECTED_IN_ORCAMENTO</p>
                    </div>

                    <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                            <thead className="bg-slate-100 text-[10px] font-mono uppercase tracking-widest text-slate-500 border-b border-border-grid">
                                <tr>
                                    <th className="p-4 font-bold border-r border-border-grid">RESOURCE_ID</th>
                                    <th className="p-4 font-bold border-r border-border-grid">BUDGET_EST</th>
                                    <th className="p-4 font-bold border-r border-border-grid">EXECUTED_VAL</th>
                                    <th className="p-4 font-bold border-r border-border-grid">BALANCE_REM</th>
                                    <th className="p-4 font-bold">ACTION_ACK</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border-grid bg-white">
                                {pendingItems.map(item => {
                                    const totalEst = item.quantidade * item.valor_unitario_estimado;
                                    const totalReal = transactions
                                        .filter(t => t.item_orcamento_id === item.id && t.status !== 'cancelado')
                                        .reduce((acc, curr) => acc + curr.valor_real, 0);
                                    const balance = totalEst - totalReal;

                                    return (
                                        <tr key={item.id} className="hover:bg-slate-50 transition-colors font-mono">
                                            <td className="p-4 border-r border-border-grid">
                                                <p className="font-bold text-on-surface text-xs">{item.nome}</p>
                                                <span className="text-[8px] font-bold border border-border-grid bg-slate-100 text-slate-500 px-2 py-0.5 mt-1 inline-block uppercase tracking-widest">{item.rubrica}</span>
                                            </td>
                                            <td className="p-4 text-xs font-bold text-slate-500 border-r border-border-grid">
                                                {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(totalEst)}
                                            </td>
                                            <td className="p-4 text-xs font-bold text-primary-tactile border-r border-border-grid">
                                                {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(totalReal)}
                                            </td>
                                            <td className="p-4 text-xs font-bold text-emerald-600 border-r border-border-grid">
                                                {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(balance)}
                                            </td>
                                            <td className="p-4">
                                                <button
                                                    onClick={() => handleGetQuotes(item)}
                                                    disabled={quotingItemId === item.id}
                                                    className="w-full bg-white border border-border-grid text-on-surface px-4 py-2 rounded-soft-touch text-[9px] font-bold uppercase tracking-widest hover:bg-slate-50 transition-all flex items-center justify-center gap-2"
                                                >
                                                    {quotingItemId === item.id ? (
                                                        <div className="w-3 h-3 border-2 border-primary-tactile border-t-transparent rounded-full animate-spin"></div>
                                                    ) : (
                                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                                                    )}
                                                    RUN_AUTO_QUOTE
                                                </button>
                                            </td>
                                        </tr>
                                    );
                                })}
                                {pendingItems.length === 0 && (
                                    <tr>
                                        <td colSpan={5} className="p-12 text-center text-slate-400 font-mono font-bold text-[10px] uppercase tracking-widest italic border-b border-border-grid">ZERO_PENDENCIES_DETECTED // SYSTEM_COMPLETE</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {activeTab === 'process' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 border border-border-grid bg-white">
                    <div className="border-r border-border-grid">
                        <div className="bg-white p-8">
                            <h3 className="text-xl font-mono font-bold text-on-surface mb-6">Source_Capture</h3>

                            <label className={`flex flex-col items-center justify-center w-full h-80 border-2 border-dashed rounded-none cursor-pointer transition-all ${isUploading ? 'bg-slate-50 border-primary-tactile' : 'bg-slate-50 border-border-grid hover:bg-white hover:border-primary-tactile'}`}>
                                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                    {isUploading ? (
                                        <>
                                            <div className="w-8 h-8 border-4 border-primary-tactile border-t-transparent rounded-full animate-spin mb-4"></div>
                                            <p className="text-[10px] font-mono font-bold text-primary-tactile uppercase tracking-widest animate-pulse">PROCESSING_IA_NEURAL_CAPTURE...</p>
                                        </>
                                    ) : (
                                        <>
                                            <svg className="w-10 h-10 mb-3 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                                            <p className="mb-2 text-[10px] font-mono font-bold text-slate-500 uppercase tracking-widest"><span className="text-primary-tactile underline">UPLOAD_INITIALIZE</span> NF-E_CAPTURE</p>
                                            <p className="text-[8px] font-mono font-bold text-slate-400 uppercase tracking-[0.2em]">FILE_TYPES: PDF_PNG_JPG (AI_VISION_V1)</p>
                                        </>
                                    )}
                                </div>
                                <input
                                    type="file"
                                    className="hidden"
                                    accept="application/pdf,image/*"
                                    disabled={isUploading}
                                    onChange={(e) => {
                                        if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
                                    }}
                                />
                            </label>

                            {invoiceUrl && (
                                <div className="mt-6 p-4 bg-emerald-50 border border-emerald-100 rounded-none flex items-center gap-4">
                                    <div className="w-8 h-8 rounded-none border border-emerald-200 bg-white text-emerald-600 flex items-center justify-center">
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                    </div>
                                    <div className="flex-1">
                                        <p className="text-[10px] font-mono font-bold text-emerald-800 uppercase tracking-widest">SIGNAL_CAPTURED: FILE_LOADED</p>
                                        <a href={invoiceUrl} target="_blank" rel="noreferrer" className="text-[9px] font-mono font-bold text-emerald-600 uppercase tracking-widest hover:underline mt-1 inline-block">OPEN_SOURCE_FILE_IN_NEW_TAB</a>
                                    </div>
                                </div>
                            )}
                        </div>

                        {ocrResult && (
                            <div className="bg-on-surface text-surface p-8">
                                <h4 className="text-[10px] font-mono font-bold uppercase tracking-[0.3em] mb-6 text-white/50">// EXTRACTED_METADATA_STREAM</h4>
                                <div className="space-y-4 font-mono text-[10px] font-bold uppercase tracking-widest">
                                    <div className="flex justify-between border-b border-white/10 pb-2">
                                        <span className="text-white/40">VENDOR_ID:</span>
                                        <span className="text-white">{ocrResult.fornecedor || 'NULL'}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-white/10 pb-2">
                                        <span className="text-white/40">TAX_ID_CNPJ:</span>
                                        <span className="text-white">{ocrResult.cnpj || 'NULL'}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-white/10 pb-2">
                                        <span className="text-white/40">GROSS_AMOUNT:</span>
                                        <span className="text-white">{formatCurrency(ocrResult.valor_total || 0)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-white/40">ITEMS_DETECTED:</span>
                                        <span className="text-white">{ocrResult.itens?.length || 0}_ENTRIES</span>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="bg-surface p-8">
                        <h3 className="text-xl font-mono font-bold text-on-surface mb-6">Finalize_Record</h3>

                        <div className="space-y-6">
                            <div>
                                <label className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">LINK_PLAN_RESOURCE</label>
                                <select
                                    value={selectedItemId}
                                    onChange={e => setSelectedItemId(e.target.value)}
                                    className="w-full p-3 rounded-soft-touch border border-border-grid focus:ring-1 focus:ring-primary-tactile outline-none font-mono font-bold text-xs text-on-surface bg-white appearance-none"
                                >
                                    <option value="">SELECT_BUDGET_ITEM...</option>
                                    {items.filter(i => i.status !== 'executado').map(i => (
                                        <option key={i.id} value={i.id}>{i.nome.toUpperCase()} ({formatCurrency(i.valor_unitario_estimado)})</option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">ENTRY_DESCRIPTION</label>
                                <input
                                    value={formDescription}
                                    onChange={e => setFormDescription(e.target.value)}
                                    className="w-full p-3 rounded-soft-touch border border-border-grid focus:ring-1 focus:ring-primary-tactile outline-none font-mono font-bold text-xs text-on-surface"
                                    placeholder="TRANSACTION_LOG_NAME"
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">TOTAL_VAL_BRL</label>
                                    <input
                                        type="number"
                                        value={formAmount}
                                        onChange={e => setFormAmount(Number(e.target.value))}
                                        className="w-full p-3 rounded-soft-touch border border-border-grid focus:ring-1 focus:ring-primary-tactile outline-none font-mono font-bold text-xs text-on-surface"
                                    />
                                </div>
                                <div>
                                    <label className="text-[9px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">EMISSION_DATE</label>
                                    <input
                                        type="date"
                                        value={formDate}
                                        onChange={e => setFormDate(e.target.value)}
                                        className="w-full p-3 rounded-soft-touch border border-border-grid focus:ring-1 focus:ring-primary-tactile outline-none font-mono font-bold text-xs text-on-surface"
                                    />
                                </div>
                            </div>

                            {formAmount > 1000 && (
                                <div className={`p-4 rounded-none border-2 border-dashed ${formQuotes.length >= 3 ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'}`}>
                                    <div className="flex items-start gap-4">
                                        <div className={`mt-0.5 w-6 h-6 rounded-none flex items-center justify-center text-white font-mono font-bold ${formQuotes.length >= 3 ? 'bg-emerald-500 shadow-sm' : 'bg-amber-500 animate-pulse shadow-sm'}`}>
                                            {formQuotes.length >= 3 ? '✓' : '!'}
                                        </div>
                                        <div>
                                            <p className={`text-[10px] font-mono font-bold uppercase tracking-widest ${formQuotes.length >= 3 ? 'text-emerald-700' : 'text-amber-700'}`}>
                                                COMPLIANCE_CHECK: QUOTES_LOG ({formQuotes.length}/3)
                                            </p>
                                            <p className="text-[8px] font-mono font-bold text-slate-500 uppercase tracking-widest mt-1 opacity-70">VAL &gt; 1.000_BRL REQUIRE_MIN_3_QUOTES_IN_DATASET.</p>
                                        </div>
                                    </div>
                                </div>
                            )}
                            <button
                                onClick={handleSaveTransaction}
                                className="w-full py-4 bg-primary-tactile text-white rounded-soft-touch text-[10px] font-mono font-bold uppercase tracking-[0.25em] border border-primary-tactile hover:bg-blue-700 transition-all mt-4"
                            >
                                FINALIZE_SAVE_RECORD
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
