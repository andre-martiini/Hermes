import React, { useState, useEffect } from 'react';
import { collection, query, onSnapshot, addDoc, doc, updateDoc, where } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from '../firebase';
import { ItemOrcamento, TransacaoProjeto, Cotacao } from '../types';

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
            if (import.meta.env.DEV) {
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
        <div className="p-6 space-y-8 animate-in fade-in duration-500">
            {/* Tabs */}
            <div className="flex gap-4 border-b border-slate-200">
                <button
                    onClick={() => setActiveTab('needs')}
                    className={`pb-4 px-2 text-xs font-black uppercase tracking-widest border-b-2 transition-colors ${activeTab === 'needs' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                >
                    Inventário de Necessidades
                </button>
                <button
                    onClick={() => setActiveTab('process')}
                    className={`pb-4 px-2 text-xs font-black uppercase tracking-widest border-b-2 transition-colors ${activeTab === 'process' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
                >
                    Processar Nota Fiscal (IA)
                </button>
            </div>

            {activeTab === 'needs' && (
                <div className="bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm">
                    <h3 className="text-xl font-black text-slate-800 mb-2">Falta Comprar</h3>
                    <p className="text-slate-400 text-xs font-medium mb-6">Itens planejados pendentes de aquisição ou com saldo disponível.</p>

                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead className="bg-slate-50 border-b border-slate-100">
                                <tr>
                                    <th className="p-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Item</th>
                                    <th className="p-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Orçado</th>
                                    <th className="p-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Executado</th>
                                    <th className="p-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Saldo</th>
                                    <th className="p-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Ações</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {pendingItems.map(item => {
                                    const totalEst = item.quantidade * item.valor_unitario_estimado;
                                    const totalReal = transactions
                                        .filter(t => t.item_orcamento_id === item.id && t.status !== 'cancelado')
                                        .reduce((acc, curr) => acc + curr.valor_real, 0);
                                    const balance = totalEst - totalReal;

                                    return (
                                        <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                                            <td className="p-4">
                                                <p className="font-bold text-slate-700 text-sm">{item.nome}</p>
                                                <span className="text-[9px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded uppercase tracking-wider">{item.rubrica}</span>
                                            </td>
                                            <td className="p-4 text-sm font-bold text-slate-600">
                                                {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(totalEst)}
                                            </td>
                                            <td className="p-4 text-sm font-bold text-indigo-600">
                                                {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(totalReal)}
                                            </td>
                                            <td className="p-4 text-sm font-bold text-emerald-600">
                                                {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(balance)}
                                            </td>
                                            <td className="p-4">
                                                <button
                                                    onClick={() => handleGetQuotes(item)}
                                                    disabled={quotingItemId === item.id}
                                                    className="bg-indigo-50 text-indigo-600 px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-indigo-100 transition-all flex items-center gap-2"
                                                >
                                                    {quotingItemId === item.id ? (
                                                        <div className="w-3 h-3 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
                                                    ) : (
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                                                    )}
                                                    Cotação Auto
                                                </button>
                                            </td>
                                        </tr>
                                    );
                                })}
                                {pendingItems.length === 0 && (
                                    <tr>
                                        <td colSpan={5} className="p-8 text-center text-slate-400 italic text-sm">Tudo comprado! Parabéns.</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {activeTab === 'process' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                    <div className="space-y-6">
                        <div className="bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm">
                            <h3 className="text-xl font-black text-slate-800 mb-6">Upload Inteligente</h3>

                            <label className={`flex flex-col items-center justify-center w-full h-64 border-2 border-dashed rounded-3xl cursor-pointer transition-all ${isUploading ? 'bg-slate-50 border-indigo-300' : 'bg-slate-50 border-slate-300 hover:bg-slate-100 hover:border-indigo-400'}`}>
                                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                    {isUploading ? (
                                        <>
                                            <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-4"></div>
                                            <p className="text-sm text-indigo-600 font-bold">Processando IA...</p>
                                        </>
                                    ) : (
                                        <>
                                            <svg className="w-10 h-10 mb-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                                            <p className="mb-2 text-sm text-slate-500"><span className="font-bold">Clique para enviar</span> Nota Fiscal</p>
                                            <p className="text-xs text-slate-400">PDF, PNG, JPG (Gemini Vision)</p>
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
                                <div className="mt-4 p-4 bg-emerald-50 border border-emerald-100 rounded-xl flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center">
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                                    </div>
                                    <div className="flex-1">
                                        <p className="text-xs font-bold text-emerald-800">Arquivo Carregado</p>
                                        <a href={invoiceUrl} target="_blank" rel="noreferrer" className="text-[10px] text-emerald-600 underline">Visualizar Documento</a>
                                    </div>
                                </div>
                            )}
                        </div>

                        {ocrResult && (
                            <div className="bg-slate-900 text-white rounded-[2rem] p-8 shadow-xl">
                                <h4 className="text-sm font-black uppercase tracking-widest mb-4 text-indigo-400">Dados Extraídos</h4>
                                <div className="space-y-4 text-sm font-medium opacity-90">
                                    <p><span className="text-slate-500">Fornecedor:</span> {ocrResult.fornecedor || 'Não identificado'}</p>
                                    <p><span className="text-slate-500">CNPJ:</span> {ocrResult.cnpj || 'Não identificado'}</p>
                                    <p><span className="text-slate-500">Valor Total:</span> R$ {ocrResult.valor_total || '0.00'}</p>
                                    <p><span className="text-slate-500">Itens:</span> {ocrResult.itens?.length || 0} encontrados</p>
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm">
                        <h3 className="text-xl font-black text-slate-800 mb-6">Registrar Aquisição</h3>

                        <div className="space-y-4">
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Vincular ao Item Planejado</label>
                                <select
                                    value={selectedItemId}
                                    onChange={e => setSelectedItemId(e.target.value)}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700 bg-white"
                                >
                                    <option value="">Selecione um item...</option>
                                    {items.filter(i => i.status !== 'executado').map(i => (
                                        <option key={i.id} value={i.id}>{i.nome} (R$ {i.valor_unitario_estimado})</option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Descrição da Transação</label>
                                <input
                                    value={formDescription}
                                    onChange={e => setFormDescription(e.target.value)}
                                    className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-medium text-slate-700"
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Valor Total</label>
                                    <input
                                        type="number"
                                        value={formAmount}
                                        onChange={e => setFormAmount(Number(e.target.value))}
                                        className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-bold text-slate-700"
                                    />
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Data Emissão</label>
                                    <input
                                        type="date"
                                        value={formDate}
                                        onChange={e => setFormDate(e.target.value)}
                                        className="w-full mt-1 p-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-medium text-slate-700"
                                    />
                                </div>
                            </div>

                            {formAmount > 1000 && (
                                <div className={`p-4 rounded-xl border ${formQuotes.length >= 3 ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'}`}>
                                    <div className="flex items-start gap-3">
                                        <div className={`mt-0.5 w-5 h-5 rounded-full flex items-center justify-center text-white ${formQuotes.length >= 3 ? 'bg-emerald-500' : 'bg-amber-500'}`}>
                                            {formQuotes.length >= 3 ? (
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                            ) : (
                                                <span className="text-[10px] font-black">!</span>
                                            )}
                                        </div>
                                        <div>
                                            <p className={`text-xs font-bold ${formQuotes.length >= 3 ? 'text-emerald-700' : 'text-amber-700'}`}>
                                                Compliance: Cotações ({formQuotes.length}/3)
                                            </p>
                                            <p className="text-[10px] opacity-80 mt-1">Compras acima de R$ 1.000 exigem 3 orçamentos.</p>
                                        </div>
                                    </div>
                                </div>
                            )}

                            <button
                                onClick={handleSaveTransaction}
                                className="w-full py-4 bg-indigo-600 text-white rounded-xl text-xs font-black uppercase tracking-widest shadow-xl hover:bg-indigo-700 transition-all mt-4"
                            >
                                Finalizar e Salvar
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
