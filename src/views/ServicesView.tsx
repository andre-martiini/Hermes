import React, { useState, useMemo, useEffect } from 'react';
import { Servico, ParcelaServico } from '../../types';

interface ServicesViewProps {
  services: Servico[];
  onCreateService: (service: Omit<Servico, 'id' | 'data_criacao' | 'data_atualizacao'>) => Promise<void>;
  onUpdateService: (id: string, service: Partial<Servico>) => Promise<void>;
  onDeleteService: (id: string) => Promise<void>;
}

export const ServicesView: React.FC<ServicesViewProps> = ({
  services,
  onCreateService,
  onUpdateService,
  onDeleteService
}) => {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'list'>('dashboard');
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  const [localDoc, setLocalDoc] = useState<Servico | null>(null);
  const [showBatchForm, setShowBatchForm] = useState(false);
  const [batchForm, setBatchForm] = useState({
      start: '',
      end: '',
      day: 5,
      value: 0
  } as { start: string, end: string, day: number, value: number });

  const selectedService = useMemo(() => services.find(s => s.id === selectedServiceId), [services, selectedServiceId]);

  useEffect(() => {
    if (selectedService) {
        setLocalDoc(selectedService);
    } else {
        setLocalDoc(null);
    }
  }, [selectedServiceId, selectedService]);

  // --- Auto-Conclusion Logic ---
  useEffect(() => {
     const now = new Date();
     services.forEach(service => {
         if (service.status === 'Ativo' && service.data_termino) {
             const end = new Date(service.data_termino + 'T23:59:59');
             if (end < now) {
                 onUpdateService(service.id, { status: 'Concluído' });
             }
         }
     });
  }, [services, onUpdateService]);

  const handleApproveService = (id: string) => {
      onUpdateService(id, { status: 'Ativo' });
  };

  const handleCancelService = (id: string) => {
      if (!confirm("Tem certeza que deseja cancelar este serviço? Todas as parcelas futuras serão removidas.")) return;
      
      const now = new Date();
      const todayStr = now.toISOString().split('T')[0];
      
      // Filter parcelas: keep only those with date <= now
      const currentParcelas = selectedService?.parcelas || [];
      const updatedParcelas = currentParcelas.filter(p => new Date(p.data_prevista) <= now);
      
      onUpdateService(id, { 
          status: 'Cancelado', 
          data_termino: todayStr,
          parcelas: updatedParcelas
      });
      setSelectedServiceId(null);
  };

  const handleUpdateTotalFromParcelas = () => {
      if (!localDoc?.parcelas || !selectedService) return;
      const total = localDoc.parcelas.reduce((acc, curr) => acc + (curr.valor || 0), 0);
      setLocalDoc(prev => prev ? { ...prev, valor_total: total } : null);
      onUpdateService(selectedService.id, { valor_total: total });
  };

  // --- Dashboard Metrics Logic ---
  const activeServices = useMemo(() => services.filter(s => s.status === 'Ativo'), [services]);

  const mrr = useMemo(() => {
    return activeServices.reduce((acc, curr) => {
        if (curr.tipo_contrato === 'Mensalidade') {
            return acc + curr.valor_total;
        } else if (curr.tipo_contrato === 'Pacote Fechado') {
            // For closed packages, approximate MRR if duration spans multiple months
            // This is a simplified approach. A more robust one might sum active parcelas for the current month.
            const start = new Date(curr.data_inicio);
            const end = new Date(curr.data_termino);
            let months = (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth());
            months = months <= 0 ? 1 : months;
            return acc + (curr.valor_total / months);
        }
        return acc;
    }, 0);
  }, [activeServices]);

  const receivables = useMemo(() => {
    const today = new Date();
    return services
        .filter(s => s.status === 'Ativo' || s.status === 'Concluído')
        .reduce((acc, curr) => {
            const pendingAmount = curr.parcelas
                .filter(p => new Date(p.data_prevista) > today)
                .reduce((sum, p) => sum + p.valor, 0);
            return acc + pendingAmount;
        }, 0);
  }, [services]);

  const committedCapacity = useMemo(() => {
    return activeServices.reduce((acc, curr) => acc + (curr.carga_horaria_semanal || 0), 0);
  }, [activeServices]);

  const handleGenerateBatch = () => {
    if (!batchForm.start || !batchForm.end || !selectedService) return;
    
    const start = new Date(batchForm.start + 'T00:00:00');
    const end = new Date(batchForm.end + 'T23:59:59');
    const day = batchForm.day;
    const value = batchForm.value;
    
    const newParcelas: ParcelaServico[] = [];
    let current = new Date(start.getFullYear(), start.getMonth(), 1);
    
    while (current <= end) {
        const installmentDate = new Date(current.getFullYear(), current.getMonth(), day);
        
        // Se o dia transbordou o mês
        if (installmentDate.getMonth() !== current.getMonth()) {
            installmentDate.setDate(0);
        }
        
        if (installmentDate >= start && installmentDate <= end) {
            newParcelas.push({
                id: Math.random().toString(36).substr(2, 9),
                valor: value,
                data_prevista: installmentDate.toISOString(),
                status: installmentDate <= new Date() ? 'pago' : 'pendente',
                descricao: `Parcela ${ (selectedService.parcelas?.length || 0) + newParcelas.length + 1}`
            });
        }
        current.setMonth(current.getMonth() + 1);
    }
    
    if (newParcelas.length > 0) {
        const updatedParcelas = [...(selectedService.parcelas || []), ...newParcelas];
        onUpdateService(selectedService.id, { parcelas: updatedParcelas });
        setLocalDoc(prev => prev ? { ...prev, parcelas: updatedParcelas } : null);
        setShowBatchForm(false);
        setBatchForm({ start: '', end: '', day: 5, value: 0 });
    }
  };


  return (
    <div className="space-y-8 animate-in fade-in pb-20">
        {/* Header & Tabs */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-6 md:p-8 rounded-[2rem] border border-slate-200 shadow-sm">
            <div>
                <h3 className="text-3xl font-black text-slate-950 tracking-tighter">Portfólio de Serviços</h3>
                <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mt-1">Gestão de Portfólio e Faturamento</p>
            </div>
            <div className="flex bg-slate-100 p-1 rounded-xl">
                <button
                    onClick={() => setActiveTab('dashboard')}
                    className={`px-6 py-2 rounded-lg text-xs font-black uppercase tracking-widest transition-all ${activeTab === 'dashboard' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                >
                    Visão Geral
                </button>
                <button
                    onClick={() => setActiveTab('list')}
                    className={`px-6 py-2 rounded-lg text-xs font-black uppercase tracking-widest transition-all ${activeTab === 'list' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                >
                    Meus Serviços
                </button>
            </div>
        </div>

        {/* --- Dashboard Tab --- */}
        {activeTab === 'dashboard' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* MRR Card */}
                <div className="bg-white p-8 rounded-[2rem] border border-indigo-100 shadow-sm flex flex-col justify-between relative overflow-hidden group">
                    <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity">
                        <svg className="w-24 h-24 text-indigo-500" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" /></svg>
                    </div>
                    <div className="relative z-10">
                        <h4 className="text-[10px] font-black text-indigo-500 uppercase tracking-[0.2em] mb-2">MRR Projetado</h4>
                        <div className="text-4xl font-black text-slate-900 tracking-tighter">
                            R$ {mrr.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <p className="text-xs text-slate-400 font-medium mt-2">Receita recorrente mensal aproximada</p>
                    </div>
                </div>

                {/* Receivables Card */}
                <div className="bg-white p-8 rounded-[2rem] border border-emerald-100 shadow-sm flex flex-col justify-between relative overflow-hidden group">
                    <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity">
                        <svg className="w-24 h-24 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </div>
                    <div className="relative z-10">
                        <h4 className="text-[10px] font-black text-emerald-500 uppercase tracking-[0.2em] mb-2">A Receber</h4>
                        <div className="text-4xl font-black text-slate-900 tracking-tighter">
                            R$ {receivables.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <p className="text-xs text-slate-400 font-medium mt-2">Soma de parcelas pendentes (Ativos/Concluídos)</p>
                    </div>
                </div>

                {/* Capacity Card */}
                <div className="bg-white p-8 rounded-[2rem] border border-amber-100 shadow-sm flex flex-col justify-between relative overflow-hidden group">
                    <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity">
                        <svg className="w-24 h-24 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </div>
                    <div className="relative z-10">
                        <h4 className="text-[10px] font-black text-amber-500 uppercase tracking-[0.2em] mb-2">Capacidade Comprometida</h4>
                        <div className="text-4xl font-black text-slate-900 tracking-tighter">
                            {committedCapacity}h <span className="text-xl text-slate-400 font-bold tracking-normal">/semana</span>
                        </div>
                        <p className="text-xs text-slate-400 font-medium mt-2">Baseado em contratos ativos</p>
                    </div>
                </div>
            </div>
        )}

        {/* --- List Tab --- */}
        {activeTab === 'list' && (
            <div className="bg-white p-6 md:p-10 rounded-[2rem] border border-slate-200 shadow-xl overflow-hidden min-h-[500px]">
                <div className="flex items-center justify-between mb-8 pb-6 border-b border-slate-100">
                    <h3 className="text-xl font-black text-slate-950 tracking-tight">Portfólio de Serviços</h3>
                    <button
                        onClick={() => {
                            // Temporary placeholder for creating a new service
                            const dummyService: Omit<Servico, 'id' | 'data_criacao' | 'data_atualizacao'> = {
                                titulo: 'Novo Serviço ' + Math.floor(Math.random() * 100),
                                descricao: 'Descreva os detalhes do serviço aqui...',
                                cliente: 'Nome do Cliente',
                                papel: 'Seu papel / cargo',
                                status: 'Prospecção',
                                tags: [],
                                data_inicio: new Date().toISOString().split('T')[0],
                                data_termino: new Date().toISOString().split('T')[0],
                                carga_horaria_semanal: 0,
                                tipo_contrato: 'Mensalidade',
                                valor_total: 0,
                                parcelas: [],
                                categoria_financeira: 'Serviço Particular'
                            };
                            onCreateService(dummyService);
                        }}
                        className="bg-indigo-600 text-white px-6 py-3 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg hover:bg-indigo-700 transition-all flex items-center gap-2"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        Novo Serviço
                    </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {services.map(service => (
                        <div
                            key={service.id}
                            onClick={() => setSelectedServiceId(service.id)}
                            className="group bg-slate-50 border border-slate-200 rounded-2xl p-6 hover:shadow-lg hover:border-indigo-300 transition-all relative overflow-hidden cursor-pointer"
                        >
                            <div className="flex items-start justify-between mb-4">
                                <div>
                                    <span className={`text-[9px] font-black px-3 py-1 rounded-full uppercase tracking-widest ${
                                        service.status === 'Ativo' ? 'bg-emerald-100 text-emerald-700' :
                                        service.status === 'Concluído' ? 'bg-blue-100 text-blue-700' :
                                        service.status === 'Prospecção' ? 'bg-amber-100 text-amber-700' :
                                        'bg-slate-200 text-slate-600'
                                    }`}>
                                        {service.status}
                                    </span>
                                </div>
                                <div className="bg-white px-2 py-1 rounded border border-slate-200 text-[10px] font-bold text-slate-500 uppercase">
                                    {service.tipo_contrato}
                                </div>
                            </div>

                            <h4 className="text-lg font-black text-slate-950 leading-tight mb-2 group-hover:text-indigo-700 transition-colors">{service.titulo}</h4>
                            <p className="text-xs text-slate-500 font-medium line-clamp-2 mb-4">{service.descricao}</p>

                            <div className="space-y-2 mb-6">
                                <div className="flex items-center justify-between text-xs">
                                    <span className="font-bold text-slate-400">Cliente</span>
                                    <span className="font-bold text-slate-700">{service.cliente}</span>
                                </div>
                                <div className="flex items-center justify-between text-xs">
                                    <span className="font-bold text-slate-400">Papel</span>
                                    <span className="font-bold text-slate-700">{service.papel}</span>
                                </div>
                                {service.status !== 'Prospecção' && (
                                    <div className="flex items-center justify-between text-xs">
                                        <span className="font-bold text-slate-400">Carga</span>
                                        <span className="font-bold text-slate-700">{service.carga_horaria_semanal}h / sem</span>
                                    </div>
                                )}
                            </div>

                            <div className="pt-4 border-t border-slate-200 flex items-center justify-between">
                                <div className="text-lg font-black text-slate-900 tracking-tighter">
                                    R$ {service.valor_total.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                </div>
                                <div className="text-indigo-600 opacity-0 group-hover:opacity-100 transition-all font-black text-[10px] uppercase tracking-widest flex items-center gap-1">
                                    Ver Detalhes
                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                                </div>
                            </div>
                        </div>
                    ))}

                    {services.length === 0 && (
                        <div className="col-span-full py-12 text-center border-2 border-dashed border-slate-200 rounded-2xl">
                            <p className="text-slate-400 font-black uppercase tracking-widest text-xs">Nenhum serviço cadastrado.</p>
                        </div>
                    )}
                </div>
            </div>
        )}

        {/* --- Detail View Modal --- */}
        {selectedService && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
                <div className="bg-white w-full max-w-4xl rounded-[2.5rem] shadow-2xl flex flex-col max-h-[90vh] overflow-hidden animate-in zoom-in-95">

                    {/* Header */}
                    <div className="p-8 border-b border-slate-100 bg-slate-50 flex items-center justify-between flex-shrink-0">
                        <div>
                            <div className="flex items-center gap-3 mb-2">
                                <span className={`text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-widest ${
                                        selectedService.status === 'Ativo' ? 'bg-emerald-100 text-emerald-700' :
                                        selectedService.status === 'Concluído' ? 'bg-blue-100 text-blue-700' :
                                        selectedService.status === 'Prospecção' ? 'bg-amber-100 text-amber-700' :
                                        'bg-slate-200 text-slate-600'
                                    }`}>
                                        {selectedService.status}
                                </span>
                                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{selectedService.tipo_contrato}</span>
                            </div>
                            <input
                                className="text-3xl font-black text-slate-950 tracking-tighter bg-transparent border-none outline-none focus:ring-2 focus:ring-indigo-500 rounded p-1 w-full"
                                value={localDoc?.titulo || ''}
                                onChange={(e) => setLocalDoc(prev => prev ? { ...prev, titulo: e.target.value } : null)}
                                onBlur={(e) => onUpdateService(selectedService.id, { titulo: e.target.value })}
                            />
                            <div className="mt-4 flex gap-2">
                                {selectedService.status === 'Prospecção' && (
                                    <button 
                                        onClick={() => handleApproveService(selectedService.id)}
                                        className="bg-emerald-600 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-emerald-700 transition-all flex items-center gap-2"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                        Aprovar Serviço
                                    </button>
                                )}
                                {selectedService.status === 'Ativo' && (
                                    <button 
                                        onClick={() => handleCancelService(selectedService.id)}
                                        className="bg-rose-50 text-rose-600 border border-rose-100 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-rose-100 transition-all flex items-center gap-2"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                                        Cancelar Serviço
                                    </button>
                                )}
                            </div>
                        </div>
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => {
                                    if(confirm("Tem certeza que deseja excluir este serviço?")) {
                                        onDeleteService(selectedService.id);
                                        setSelectedServiceId(null);
                                    }
                                }}
                                className="p-3 text-rose-500 hover:bg-rose-50 rounded-xl transition-all" title="Excluir"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                            </button>
                            <button onClick={() => setSelectedServiceId(null)} className="p-3 text-slate-400 hover:bg-slate-200 rounded-xl transition-all">
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                    </div>

                    {/* Content */}
                    <div className="p-8 flex-1 overflow-y-auto space-y-8 bg-white">

                        {/* Info Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            <div className="space-y-4">
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Cliente / Instituição</label>
                                    <input
                                        type="text"
                                        value={localDoc?.cliente || ''}
                                        onChange={(e) => setLocalDoc(prev => prev ? { ...prev, cliente: e.target.value } : null)}
                                        onBlur={(e) => onUpdateService(selectedService.id, { cliente: e.target.value })}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500"
                                    />
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Papel / Função</label>
                                    <input
                                        type="text"
                                        value={localDoc?.papel || ''}
                                        onChange={(e) => setLocalDoc(prev => prev ? { ...prev, papel: e.target.value } : null)}
                                        onBlur={(e) => onUpdateService(selectedService.id, { papel: e.target.value })}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500"
                                    />
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Descrição do Escopo</label>
                                    <textarea
                                        value={localDoc?.descricao || ''}
                                        onChange={(e) => setLocalDoc(prev => prev ? { ...prev, descricao: e.target.value } : null)}
                                        onBlur={(e) => onUpdateService(selectedService.id, { descricao: e.target.value })}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500 min-h-[100px] resize-none"
                                    />
                                </div>
                            </div>

                            <div className="space-y-4">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Início</label>
                                        <input
                                            type="date"
                                            disabled={localDoc?.status === 'Prospecção'}
                                            value={localDoc?.data_inicio?.split('T')[0] || ''}
                                            onChange={(e) => {
                                                const val = new Date(e.target.value).toISOString();
                                                setLocalDoc(prev => prev ? { ...prev, data_inicio: val } : null);
                                                onUpdateService(selectedService.id, { data_inicio: val });
                                            }}
                                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Término Previsto</label>
                                        <input
                                            type="date"
                                            disabled={localDoc?.status === 'Prospecção'}
                                            value={localDoc?.data_termino?.split('T')[0] || ''}
                                            onChange={(e) => {
                                                const val = new Date(e.target.value).toISOString();
                                                setLocalDoc(prev => prev ? { ...prev, data_termino: val } : null);
                                                onUpdateService(selectedService.id, { data_termino: val });
                                            }}
                                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                                        />
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-1.5">Classificação Financeira</label>
                                        <select
                                            value={localDoc?.categoria_financeira || 'Serviço Particular'}
                                            onChange={(e) => {
                                                const val = e.target.value as any;
                                                setLocalDoc(prev => prev ? { ...prev, categoria_financeira: val } : null);
                                                onUpdateService(selectedService.id, { categoria_financeira: val });
                                            }}
                                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500"
                                        >
                                            <option value="Serviço Particular">Serviço Particular</option>
                                            <option value="Bolsa">Bolsa</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Carga Horária (h/sem)</label>
                                        <input
                                            type="number"
                                            disabled={localDoc?.status === 'Prospecção'}
                                            value={localDoc?.carga_horaria_semanal || 0}
                                            onChange={(e) => setLocalDoc(prev => prev ? { ...prev, carga_horaria_semanal: Number(e.target.value) } : null)}
                                            onBlur={(e) => onUpdateService(selectedService.id, { carga_horaria_semanal: Number(e.target.value) })}
                                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                                        />
                                    </div>
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Valor Total (R$)</label>
                                    <input
                                        type="number"
                                        value={localDoc?.valor_total || 0}
                                        onChange={(e) => setLocalDoc(prev => prev ? { ...prev, valor_total: Number(e.target.value) } : null)}
                                        onBlur={(e) => onUpdateService(selectedService.id, { valor_total: Number(e.target.value) })}
                                        className="w-full bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3 text-xl font-black text-indigo-900 outline-none focus:ring-2 focus:ring-indigo-500"
                                    />
                                    <button 
                                        onClick={handleUpdateTotalFromParcelas}
                                        disabled={!localDoc?.parcelas || localDoc.parcelas.length === 0}
                                        className="mt-3 text-[10px] font-black text-indigo-600 hover:text-indigo-800 disabled:text-slate-300 disabled:cursor-not-allowed uppercase tracking-widest flex items-center gap-1.5 transition-colors pl-1"
                                    >
                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                                        Sincronizar com Cronograma
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Parcelas Section */}
                        <div className="pt-8 border-t border-slate-100">
                            <div className="flex items-center justify-between mb-6">
                                <div>
                                    <h4 className="text-sm font-black text-slate-900 uppercase tracking-widest">Cronograma Financeiro</h4>
                                    <p className="text-xs text-slate-500 font-medium mt-1">Marcos e parcelas deste serviço</p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => setShowBatchForm(!showBatchForm)}
                                        className="bg-indigo-50 text-indigo-700 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-indigo-100 transition-all flex items-center gap-2"
                                    >
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                                        {showBatchForm ? 'Fechar Lote' : 'Gerar em Lote'}
                                    </button>
                                    <button
                                        onClick={() => {
                                            const newParcela: ParcelaServico = {
                                                id: Math.random().toString(36).substr(2, 9),
                                                valor: 0,
                                                data_prevista: new Date().toISOString(),
                                                status: 'pendente',
                                                descricao: 'Nova Parcela'
                                            };
                                            const newParcelas = [...(selectedService.parcelas || []), newParcela];
                                            onUpdateService(selectedService.id, { parcelas: newParcelas });
                                            setLocalDoc(prev => prev ? { ...prev, parcelas: newParcelas } : null);
                                        }}
                                        className="bg-slate-900 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-800 transition-all flex items-center gap-2"
                                    >
                                        + Adicionar Parcela
                                    </button>
                                </div>
                            </div>

                            {/* Batch Generation Form */}
                            {showBatchForm && (
                                <div className="bg-indigo-50/50 border border-indigo-100 p-6 rounded-2xl mb-8 animate-in slide-in-from-top-4 duration-300">
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
                                        <div>
                                            <label className="text-[9px] font-black text-indigo-400 uppercase tracking-widest mb-1.5 block">Data Inicial</label>
                                            <input 
                                                type="date" 
                                                value={batchForm.start}
                                                onChange={e => setBatchForm(prev => ({ ...prev, start: e.target.value }))}
                                                className="w-full bg-white border border-indigo-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-400" 
                                            />
                                        </div>
                                        <div>
                                            <label className="text-[9px] font-black text-indigo-400 uppercase tracking-widest mb-1.5 block">Data Final</label>
                                            <input 
                                                type="date" 
                                                value={batchForm.end}
                                                onChange={e => setBatchForm(prev => ({ ...prev, end: e.target.value }))}
                                                className="w-full bg-white border border-indigo-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-400" 
                                            />
                                        </div>
                                        <div className="grid grid-cols-2 gap-3">
                                            <div>
                                                <label className="text-[9px] font-black text-indigo-400 uppercase tracking-widest mb-1.5 block">Dia Venc.</label>
                                                <input 
                                                    type="number" 
                                                    min="1" max="31"
                                                    value={batchForm.day}
                                                    onChange={e => setBatchForm(prev => ({ ...prev, day: Number(e.target.value) }))}
                                                    className="w-full bg-white border border-indigo-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-400" 
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[9px] font-black text-indigo-400 uppercase tracking-widest mb-1.5 block">Valor (R$)</label>
                                                <input 
                                                    type="number" 
                                                    placeholder="0,00"
                                                    value={batchForm.value}
                                                    onChange={e => setBatchForm(prev => ({ ...prev, value: Number(e.target.value) }))}
                                                    className="w-full bg-white border border-indigo-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-400" 
                                                />
                                            </div>
                                        </div>
                                        <button 
                                            onClick={handleGenerateBatch}
                                            className="w-full bg-indigo-600 text-white px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-indigo-700 transition-all flex items-center justify-center gap-2"
                                        >
                                            Confirmar e Gerar
                                        </button>
                                    </div>
                                    <p className="text-[9px] text-indigo-400 mt-4 font-bold italic">* As parcelas serão anexadas ao cronograma atual.</p>
                                </div>
                            )}

                            <div className="space-y-3">
                                {(localDoc?.parcelas || []).map((parcela, index) => (
                                    <div key={parcela.id} className="flex items-center gap-4 bg-slate-50 p-4 rounded-xl border border-slate-200 group">
                                        <div className="w-8 h-8 rounded-full bg-white border border-slate-200 flex items-center justify-center text-[10px] font-black text-slate-400 shrink-0">
                                            {index + 1}
                                        </div>
                                        <div className="flex-1 grid grid-cols-1 md:grid-cols-4 gap-4">
                                            <input
                                                type="text"
                                                value={parcela.descricao}
                                                onChange={(e) => {
                                                    const updated = [...localDoc!.parcelas];
                                                    updated[index].descricao = e.target.value;
                                                    setLocalDoc({ ...localDoc!, parcelas: updated });
                                                }}
                                                onBlur={(e) => {
                                                    const updated = [...localDoc!.parcelas];
                                                    updated[index].descricao = e.target.value;
                                                    onUpdateService(selectedService.id, { parcelas: updated });
                                                }}
                                                className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-800 w-full"
                                                placeholder="Descrição da Parcela"
                                            />
                                            <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-lg px-3 py-2 w-full">
                                                <span className="text-xs font-black text-slate-400">R$</span>
                                                <input
                                                    type="number"
                                                    value={parcela.valor}
                                                    onChange={(e) => {
                                                        const updated = [...localDoc!.parcelas];
                                                        updated[index].valor = Number(e.target.value);
                                                        setLocalDoc({ ...localDoc!, parcelas: updated });
                                                    }}
                                                    onBlur={(e) => {
                                                        const updated = [...localDoc!.parcelas];
                                                        updated[index].valor = Number(e.target.value);
                                                        onUpdateService(selectedService.id, { parcelas: updated });
                                                    }}
                                                    className="border-none outline-none text-xs font-bold text-slate-800 w-full bg-transparent"
                                                />
                                            </div>
                                            <input
                                                type="date"
                                                value={parcela.data_prevista.split('T')[0]}
                                                onChange={(e) => {
                                                    const val = new Date(e.target.value).toISOString();
                                                    const updated = [...localDoc!.parcelas];
                                                    updated[index].data_prevista = val;
                                                    setLocalDoc({ ...localDoc!, parcelas: updated });
                                                    onUpdateService(selectedService.id, { parcelas: updated });
                                                }}
                                                className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-800 w-full"
                                            />
                                            <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold w-full flex items-center h-full">
                                                {new Date(parcela.data_prevista) <= new Date() ? (
                                                    <span className="text-emerald-600 flex items-center gap-1">
                                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                        Recebido
                                                    </span>
                                                ) : (
                                                    <span className="text-amber-600 flex items-center gap-1">
                                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                                        Pendente
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => {
                                                if (confirm("Deseja realmente excluir esta parcela?")) {
                                                    const updated = localDoc!.parcelas.filter((_, i) => i !== index);
                                                    setLocalDoc({ ...localDoc!, parcelas: updated });
                                                    onUpdateService(selectedService.id, { parcelas: updated });
                                                }
                                            }}
                                            className="p-2 text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors shrink-0"
                                        >
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                        </button>
                                    </div>
                                ))}
                                {(localDoc?.parcelas || []).length === 0 && (
                                    <div className="py-8 text-center border-2 border-dashed border-slate-200 rounded-xl">
                                        <p className="text-slate-400 font-black uppercase tracking-widest text-[10px]">Nenhuma parcela cadastrada</p>
                                    </div>
                                )}
                            </div>
                        </div>

                    </div>
                </div>
            </div>
        )}

    </div>
  );
};
