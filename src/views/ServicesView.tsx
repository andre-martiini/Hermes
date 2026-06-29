import React, { useState, useMemo, useEffect } from 'react';
import { Servico, ParcelaServico, BaseConhecimento } from '../../types';

interface ServicesViewProps {
  services: Servico[];
  knowledgeBases: BaseConhecimento[];
  onCreateService: (service: Omit<Servico, 'id' | 'data_criacao' | 'data_atualizacao'>) => Promise<void>;
  onUpdateService: (id: string, service: Partial<Servico>) => Promise<void>;
  onDeleteService: (id: string) => Promise<void>;
}

export const ServicesView: React.FC<ServicesViewProps> = ({
  services,
  knowledgeBases = [],
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
    <div className="space-y-12 animate-in fade-in pb-20 bg-surface min-h-screen p-6">
        {/* Header & Tabs Industriais */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 border-b-2 border-primary-tactile pb-6">
            <div>
                <h3 className="text-3xl font-sans font-semibold text-on-surface">Services_Portfolio</h3>
                <div className="flex items-center gap-2 mt-2">
                    <span className="text-[10px] font-sans font-semibold text-primary-tactile uppercase tracking-widest">// REVENUE_MANAGEMENT_V2</span>
                    <span className="w-1 h-1 rounded-full bg-primary-tactile"></span>
                    <span className="text-[10px] font-sans font-semibold text-slate-400 uppercase tracking-widest">STATUS: CONNECTED</span>
                </div>
            </div>
            <div className="flex gap-1 bg-slate-100 p-1 rounded-lg border border-[#e5e7eb] dark:border-white/10">
                <button
                    onClick={() => setActiveTab('dashboard')}
                    className={`px-6 py-3 text-[10px] font-sans font-semibold uppercase tracking-[0.2em] transition-all ${activeTab === 'dashboard' ? 'bg-white text-on-surface border border-[#e5e7eb] dark:border-white/10 shadow-sm' : 'text-slate-400 hover:text-on-surface hover:bg-white/50'}`}
                >
                    DASHBOARD_OVERVIEW
                </button>
                <button
                    onClick={() => setActiveTab('list')}
                    className={`px-6 py-3 text-[10px] font-sans font-semibold uppercase tracking-[0.2em] transition-all ${activeTab === 'list' ? 'bg-white text-on-surface border border-[#e5e7eb] dark:border-white/10 shadow-sm' : 'text-slate-400 hover:text-on-surface hover:bg-white/50'}`}
                >
                    SERVICE_INVENTORY
                </button>
            </div>
        </div>

        {/* --- Dashboard Tab --- */}
        {activeTab === 'dashboard' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-0 border border-[#e5e7eb] dark:border-white/10 bg-white">
                {/* MRR Card */}
                <div className="p-8 border-r border-[#e5e7eb] dark:border-white/10 flex flex-col justify-between relative overflow-hidden group">
                    <div className="relative z-10">
                        <h4 className="text-[10px] font-sans font-semibold text-primary-tactile uppercase tracking-[0.25em] mb-4 flex items-center gap-2">
                            <span className="w-2 h-2 bg-primary-tactile"></span>
                            PROJECTED_MRR
                        </h4>
                        <div className="text-4xl font-sans font-semibold text-on-surface tracking-tighter">
                            R$ {mrr.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <p className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest mt-4 opacity-70">ANNUAL_RECURRING_METRIC_ESTIMATE</p>
                    </div>
                </div>

                {/* Receivables Card */}
                <div className="p-8 border-r border-[#e5e7eb] dark:border-white/10 flex flex-col justify-between relative overflow-hidden group">
                    <div className="relative z-10">
                        <h4 className="text-[10px] font-sans font-semibold text-emerald-600 uppercase tracking-[0.25em] mb-4 flex items-center gap-2">
                            <span className="w-2 h-2 bg-emerald-500"></span>
                            ACCOUNT_RECEIVABLES
                        </h4>
                        <div className="text-4xl font-sans font-semibold text-on-surface tracking-tighter">
                            R$ {receivables.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <p className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest mt-4 opacity-70">PENDING_INSTALLMENTS_AGGREGATE</p>
                    </div>
                </div>

                {/* Capacity Card */}
                <div className="p-8 flex flex-col justify-between relative overflow-hidden group">
                    <div className="relative z-10">
                        <h4 className="text-[10px] font-sans font-semibold text-amber-600 uppercase tracking-[0.25em] mb-4 flex items-center gap-2">
                            <span className="w-2 h-2 bg-amber-500"></span>
                            COMMITTED_CAPACITY
                        </h4>
                        <div className="text-4xl font-sans font-semibold text-on-surface tracking-tighter">
                            {committedCapacity}H <span className="text-xl text-slate-400">/WEEK</span>
                        </div>
                        <p className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest mt-4 opacity-70">ACTIVE_CONTRACT_LOAD_SIGNAL</p>
                    </div>
                </div>
            </div>
        )}

        {/* --- List Tab --- */}
        {activeTab === 'list' && (
            <div className="bg-surface rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-none overflow-hidden min-h-[500px]">
                <div className="flex items-center justify-between p-8 border-b border-[#e5e7eb] dark:border-white/10 bg-slate-50/50">
                    <div>
                        <h3 className="text-xl font-sans font-semibold text-on-surface">Service_Inventory</h3>
                        <p className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest mt-1">ACTIVE_SERVICE_REGISTRY_NODE</p>
                    </div>
                    <button
                        onClick={() => {
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
                        className="bg-primary-tactile text-white px-6 py-3 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest shadow-sm hover:bg-on-surface transition-all flex items-center gap-3"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        INITIALIZE_NEW_SERVICE
                    </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-0 border-t border-[#e5e7eb] dark:border-white/10">
                    {services.map(service => (
                        <div
                            key={service.id}
                            onClick={() => setSelectedServiceId(service.id)}
                            className="group bg-white border border-[#e5e7eb] dark:border-white/10 p-8 hover:bg-slate-50 transition-all relative overflow-hidden cursor-pointer flex flex-col justify-between"
                        >
                            <div>
                                <div className="flex items-start justify-between mb-6">
                                    <span className={`text-[8px] font-sans font-semibold px-2 py-0.5 border border-[#e5e7eb] dark:border-white/10 uppercase tracking-widest ${
                                        service.status === 'Ativo' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                                        service.status === 'Concluído' ? 'bg-blue-50 text-blue-700 border-blue-200' :
                                        service.status === 'Prospecção' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                                        'bg-slate-100 text-slate-600 border-slate-300'
                                    }`}>
                                        {service.status}
                                    </span>
                                    <span className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-[0.2em]">
                                        TYPE: {service.tipo_contrato}
                                    </span>
                                </div>

                                <h4 className="text-lg font-sans font-semibold text-on-surface leading-tight mb-4 group-hover:text-primary-tactile transition-colors">{service.titulo}</h4>
                                
                                <div className="space-y-3 font-sans text-[10px] uppercase tracking-widest mb-8">
                                    <div className="flex justify-between border-b border-slate-100 pb-2">
                                        <span className="text-slate-400">CLIENT_ID:</span>
                                        <span className="text-on-surface font-bold">{service.cliente}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-slate-100 pb-2">
                                        <span className="text-slate-400">ROLE_SPEC:</span>
                                        <span className="text-on-surface font-bold">{service.papel}</span>
                                    </div>
                                    {service.status !== 'Prospecção' && (
                                        <div className="flex justify-between border-b border-slate-100 pb-2">
                                            <span className="text-slate-400">WORKLOAD:</span>
                                            <span className="text-on-surface font-bold">{service.carga_horaria_semanal}H/W</span>
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div className="pt-6 border-t border-[#e5e7eb] dark:border-white/10 border-dashed flex items-center justify-between">
                                <div className="text-xl font-sans font-semibold text-on-surface tracking-tighter">
                                    R$ {service.valor_total.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                </div>
                                <div className="text-primary-tactile opacity-0 group-hover:opacity-100 transition-all font-sans font-semibold text-[9px] uppercase tracking-widest flex items-center gap-2">
                                    ACCESS_DETAILS
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
                                </div>
                            </div>
                        </div>
                    ))}

                    {services.length === 0 && (
                        <div className="col-span-full py-24 text-center bg-slate-50/50">
                            <p className="text-slate-400 font-sans font-semibold uppercase tracking-[0.3em] text-[10px]">NULL_DATASET // ZERO_SERVICES_REGISTERED</p>
                        </div>
                    )}
                </div>
            </div>
        )}

        {/* --- Detail View Modal --- */}
        {selectedService && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-on-surface/80 backdrop-blur-sm animate-in fade-in duration-300">
                <div className="bg-surface w-full max-w-5xl rounded-lg border-2 border-primary-tactile shadow-none flex flex-col max-h-[95vh] overflow-hidden animate-in zoom-in-95">

                    {/* Header Industrial */}
                    <div className="p-8 border-b border-[#e5e7eb] dark:border-white/10 bg-slate-50 flex items-center justify-between flex-shrink-0">
                        <div className="flex-1 mr-8">
                            <div className="flex items-center gap-4 mb-4">
                                <span className={`text-[8px] font-sans font-semibold px-2 py-0.5 border border-[#e5e7eb] dark:border-white/10 uppercase tracking-widest ${
                                        selectedService.status === 'Ativo' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                                        selectedService.status === 'Concluído' ? 'bg-blue-50 text-blue-700 border-blue-200' :
                                        selectedService.status === 'Prospecção' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                                        'bg-slate-100 text-slate-600 border-slate-300'
                                    }`}>
                                        {selectedService.status}
                                </span>
                                <span className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest">// CONTRACT_TYPE: {selectedService.tipo_contrato}</span>
                            </div>
                            <input
                                className="text-3xl font-sans font-semibold text-on-surface bg-transparent border-none outline-none focus:ring-1 focus:ring-primary-tactile rounded-lg p-1 w-full"
                                value={localDoc?.titulo || ''}
                                onChange={(e) => setLocalDoc(prev => prev ? { ...prev, titulo: e.target.value } : null)}
                                onBlur={(e) => onUpdateService(selectedService.id, { titulo: e.target.value })}
                            />
                        </div>
                        <div className="flex items-center gap-3">
                            {selectedService.status === 'Prospecção' && (
                                <button 
                                    onClick={() => handleApproveService(selectedService.id)}
                                    className="bg-emerald-600 text-white px-5 py-3 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest shadow-sm hover:bg-emerald-700 transition-all flex items-center gap-2"
                                >
                                    ACTIVATE_CONTRACT
                                </button>
                            )}
                            {selectedService.status === 'Ativo' && (
                                <button 
                                    onClick={() => handleCancelService(selectedService.id)}
                                    className="bg-white border border-rose-200 text-rose-600 px-5 py-3 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest hover:bg-rose-50 transition-all flex items-center gap-2"
                                >
                                    TERMINATE_SERVICE
                                </button>
                            )}
                            <button
                                onClick={() => {
                                    if(confirm("Tem certeza que deseja excluir este serviço?")) {
                                        onDeleteService(selectedService.id);
                                        setSelectedServiceId(null);
                                    }
                                }}
                                className="p-3 text-rose-500 hover:bg-rose-50 rounded-soft-touch transition-all border border-transparent hover:border-rose-100" title="Excluir"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                            </button>
                            <button onClick={() => setSelectedServiceId(null)} className="p-3 text-slate-400 hover:bg-slate-100 rounded-soft-touch transition-all border border-[#e5e7eb] dark:border-white/10">
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                    </div>

                    {/* Content */}
                    <div className="p-10 flex-1 overflow-y-auto space-y-12 bg-white">

                        {/* Info Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
                            <div className="space-y-6">
                                <div>
                                    <label className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-2">RESOURCE_IDENTIFIER (CLIENT)</label>
                                    <input
                                        type="text"
                                        value={localDoc?.cliente || ''}
                                        onChange={(e) => setLocalDoc(prev => prev ? { ...prev, cliente: e.target.value } : null)}
                                        onBlur={(e) => onUpdateService(selectedService.id, { cliente: e.target.value })}
                                        className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                    />
                                </div>
                                <div>
                                    <label className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-2">OPERATIONAL_ROLE_SPEC</label>
                                    <input
                                        type="text"
                                        value={localDoc?.papel || ''}
                                        onChange={(e) => setLocalDoc(prev => prev ? { ...prev, papel: e.target.value } : null)}
                                        onBlur={(e) => onUpdateService(selectedService.id, { papel: e.target.value })}
                                        className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                    />
                                </div>
                                <div>
                                    <label className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-2">PROJECT_SCOPE_LOG</label>
                                    <textarea
                                        value={localDoc?.descricao || ''}
                                        onChange={(e) => setLocalDoc(prev => prev ? { ...prev, descricao: e.target.value } : null)}
                                        onBlur={(e) => onUpdateService(selectedService.id, { descricao: e.target.value })}
                                        className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile min-h-[120px] resize-none"
                                    />
                                </div>
                            </div>

                            <div className="space-y-6">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-2">INITIAL_DATE</label>
                                        <input
                                            type="date"
                                            disabled={localDoc?.status === 'Prospecção'}
                                            value={localDoc?.data_inicio?.split('T')[0] || ''}
                                            onChange={(e) => {
                                                const val = new Date(e.target.value).toISOString();
                                                setLocalDoc(prev => prev ? { ...prev, data_inicio: val } : null);
                                                onUpdateService(selectedService.id, { data_inicio: val });
                                            }}
                                            className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile disabled:opacity-30"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-2">TERMINATION_ETA</label>
                                        <input
                                            type="date"
                                            disabled={localDoc?.status === 'Prospecção'}
                                            value={localDoc?.data_termino?.split('T')[0] || ''}
                                            onChange={(e) => {
                                                const val = new Date(e.target.value).toISOString();
                                                setLocalDoc(prev => prev ? { ...prev, data_termino: val } : null);
                                                onUpdateService(selectedService.id, { data_termino: val });
                                            }}
                                            className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile disabled:opacity-30"
                                        />
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    <div>
                                        <label className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-2">FINANCIAL_CLASS</label>
                                        <select
                                            value={localDoc?.categoria_financeira || 'Serviço Particular'}
                                            onChange={(e) => {
                                                const val = e.target.value as any;
                                                setLocalDoc(prev => prev ? { ...prev, categoria_financeira: val } : null);
                                                onUpdateService(selectedService.id, { categoria_financeira: val });
                                            }}
                                            className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile appearance-none"
                                        >
                                            <option value="Serviço Particular">PRIVATE_SERVICE</option>
                                            <option value="Bolsa">GRANT_SCHOLARSHIP</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-2">HOURLY_LOAD (H/W)</label>
                                        <input
                                            type="number"
                                            disabled={localDoc?.status === 'Prospecção'}
                                            value={localDoc?.carga_horaria_semanal || 0}
                                            onChange={(e) => setLocalDoc(prev => prev ? { ...prev, carga_horaria_semanal: Number(e.target.value) } : null)}
                                            onBlur={(e) => onUpdateService(selectedService.id, { carga_horaria_semanal: Number(e.target.value) })}
                                            className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile disabled:opacity-30"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-2">Área Temática (RAG)</label>
                                        <select
                                            value={localDoc?.base_id || ''}
                                            onChange={(e) => {
                                                const val = e.target.value;
                                                setLocalDoc(prev => prev ? { ...prev, base_id: val } : null);
                                                onUpdateService(selectedService.id, { base_id: val });
                                            }}
                                            className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-soft-touch px-4 py-3 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile appearance-none"
                                        >
                                            <option value="">Nenhuma / Geral</option>
                                            {knowledgeBases.map(base => (
                                                <option key={base.id} value={base.id}>{base.nome}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                                <div>
                                    <label className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest block mb-2">TOTAL_VAL_AGREEMENT (BRL)</label>
                                    <div className="relative">
                                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-xs font-sans font-semibold text-primary-tactile">R$</span>
                                        <input
                                            type="number"
                                            value={localDoc?.valor_total || 0}
                                            onChange={(e) => setLocalDoc(prev => prev ? { ...prev, valor_total: Number(e.target.value) } : null)}
                                            onBlur={(e) => onUpdateService(selectedService.id, { valor_total: Number(e.target.value) })}
                                            className="w-full bg-slate-50 border border-primary-tactile rounded-soft-touch pl-10 pr-4 py-4 text-2xl font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile"
                                        />
                                    </div>
                                    <button 
                                        onClick={handleUpdateTotalFromParcelas}
                                        disabled={!localDoc?.parcelas || localDoc.parcelas.length === 0}
                                        className="mt-3 text-[9px] font-sans font-semibold text-primary-tactile hover:underline disabled:text-slate-300 disabled:no-underline uppercase tracking-widest flex items-center gap-2 transition-all"
                                    >
                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                                        SYNC_WITH_PAYMENT_TIMELINE
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Parcelas Section */}
                        <div className="pt-10 border-t border-[#e5e7eb] dark:border-white/10 border-dashed">
                            <div className="flex items-center justify-between mb-8">
                                <div>
                                    <h4 className="text-[10px] font-sans font-semibold text-on-surface uppercase tracking-[0.3em] flex items-center gap-2">
                                        <span className="w-2 h-2 bg-primary-tactile"></span>
                                        FINANCIAL_SCHEDULE_STREAM
                                    </h4>
                                    <p className="text-[9px] font-sans font-semibold text-slate-400 uppercase tracking-widest mt-1">PAYMENT_MILESTONES_AND_INSTALLMENTS</p>
                                </div>
                                <div className="flex items-center gap-3">
                                    <button
                                        onClick={() => setShowBatchForm(!showBatchForm)}
                                        className="bg-white border border-[#e5e7eb] dark:border-white/10 text-on-surface px-4 py-2 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest hover:bg-slate-50 transition-all flex items-center gap-2 shadow-sm"
                                    >
                                        {showBatchForm ? 'CLOSE_BATCH_MODULE' : 'INITIALIZE_BATCH_GEN'}
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
                                        className="bg-on-surface text-white px-4 py-2 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest hover:bg-primary-tactile transition-all flex items-center gap-2 shadow-md"
                                    >
                                        + APPEND_INSTALLMENT
                                    </button>
                                </div>
                            </div>

                            {/* Batch Generation Form Industrial */}
                            {showBatchForm && (
                                <div className="bg-slate-50 border border-[#e5e7eb] dark:border-white/10 p-8 rounded-lg mb-10 animate-in slide-in-from-top-4 duration-300">
                                    <h5 className="text-[9px] font-sans font-semibold text-primary-tactile uppercase tracking-widest mb-6 border-b border-[#e5e7eb] dark:border-white/10 pb-2">// BATCH_GENERATOR_CONFIG</h5>
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-end">
                                        <div>
                                            <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2 block">START_PERIOD</label>
                                            <input 
                                                type="date" 
                                                value={batchForm.start}
                                                onChange={e => setBatchForm(prev => ({ ...prev, start: e.target.value }))}
                                                className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-3 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile" 
                                            />
                                        </div>
                                        <div>
                                            <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2 block">END_PERIOD</label>
                                            <input 
                                                type="date" 
                                                value={batchForm.end}
                                                onChange={e => setBatchForm(prev => ({ ...prev, end: e.target.value }))}
                                                className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-3 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile" 
                                            />
                                        </div>
                                        <div className="grid grid-cols-2 gap-3">
                                            <div>
                                                <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2 block">DUE_DAY</label>
                                                <input 
                                                    type="number" 
                                                    min="1" max="31"
                                                    value={batchForm.day}
                                                    onChange={e => setBatchForm(prev => ({ ...prev, day: Number(e.target.value) }))}
                                                    className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-3 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile" 
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[8px] font-sans font-semibold text-slate-400 uppercase tracking-widest mb-2 block">VAL_BRL</label>
                                                <input 
                                                    type="number" 
                                                    placeholder="0,00"
                                                    value={batchForm.value}
                                                    onChange={e => setBatchForm(prev => ({ ...prev, value: Number(e.target.value) }))}
                                                    className="w-full bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg px-3 py-2 text-xs font-sans font-semibold text-on-surface outline-none focus:ring-1 focus:ring-primary-tactile" 
                                                />
                                            </div>
                                        </div>
                                        <button 
                                            onClick={handleGenerateBatch}
                                            className="w-full bg-primary-tactile text-white px-4 py-3 rounded-soft-touch text-[10px] font-sans font-semibold uppercase tracking-widest hover:bg-on-surface transition-all shadow-sm"
                                        >
                                            GENERATE_BATCH_STREAM
                                        </button>
                                    </div>
                                    <p className="text-[8px] font-sans font-semibold text-slate-400 mt-6 uppercase tracking-widest opacity-60">* INJECTING_PARCELAS_INTO_EXISTING_DATASET.</p>
                                </div>
                            )}

                            <div className="space-y-2">
                                {(localDoc?.parcelas || []).map((parcela, index) => (
                                    <div key={parcela.id} className="flex items-center gap-4 bg-white p-3 rounded-lg border border-[#e5e7eb] dark:border-white/10 group hover:bg-slate-50 transition-all">
                                        <div className="w-8 h-8 rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-slate-50 flex items-center justify-center text-[10px] font-sans font-semibold text-slate-400 shrink-0">
                                            {String(index + 1).padStart(2, '0')}
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
                                                className="bg-transparent border-none focus:ring-1 focus:ring-primary-tactile rounded-lg px-3 py-2 text-xs font-sans font-semibold text-on-surface w-full"
                                                placeholder="INSTALLMENT_LABEL"
                                            />
                                            <div className="flex items-center gap-2 bg-slate-50 border border-[#e5e7eb] dark:border-white/10 rounded-lg px-3 py-2 w-full">
                                                <span className="text-[10px] font-sans font-semibold text-primary-tactile">BRL</span>
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
                                                    className="border-none outline-none text-xs font-sans font-semibold text-on-surface w-full bg-transparent"
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
                                                className="bg-transparent border-none focus:ring-1 focus:ring-primary-tactile rounded-lg px-3 py-2 text-xs font-sans font-semibold text-on-surface w-full"
                                            />
                                            <div className="px-3 py-2 text-[10px] font-sans font-semibold w-full flex items-center h-full uppercase tracking-widest">
                                                {new Date(parcela.data_prevista) <= new Date() ? (
                                                    <span className="text-emerald-600 flex items-center gap-2">
                                                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                                                        RECEIVED
                                                    </span>
                                                ) : (
                                                    <span className="text-amber-600 flex items-center gap-2">
                                                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                                                        PENDING_FLOW
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
                                            className="p-2 text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-soft-touch transition-all shrink-0 border border-transparent hover:border-rose-100"
                                        >
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                        </button>
                                    </div>
                                ))}
                                {(localDoc?.parcelas || []).length === 0 && (
                                    <div className="py-12 text-center border border-[#e5e7eb] dark:border-white/10 border-dashed bg-slate-50/50">
                                        <p className="text-slate-400 font-sans font-semibold uppercase tracking-[0.2em] text-[10px]">NULL_TIMELINE // NO_INSTALLMENTS_DETECTED</p>
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
