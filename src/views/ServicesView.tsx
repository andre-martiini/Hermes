import React, { useState, useMemo, useEffect } from 'react';
import { Servico, ParcelaServico } from '../../types';

interface ServicesViewProps {
  services: Servico[];
  onCreateService: (service: Omit<Servico, 'id' | 'data_criacao' | 'data_atualizacao'>) => Promise<void>;
  onUpdateService: (id: string, service: Partial<Servico>) => Promise<void>;
  onDeleteService: (id: string) => Promise<void>;
}

const statusStyles: Record<string, string> = {
  Ativo: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  'Concluído': 'bg-blue-50 text-blue-700 border-blue-200',
  'Prospecção': 'bg-amber-50 text-amber-700 border-amber-200',
  Cancelado: 'bg-rose-50 text-rose-700 border-rose-200',
  'Em Pausa': 'bg-slate-100 text-slate-600 border-slate-200'
};

const statusLabels: Record<string, string> = {
  Ativo: 'Ativo',
  'Concluído': 'Concluído',
  'Prospecção': 'Prospecção',
  Cancelado: 'Cancelado',
  'Em Pausa': 'Em pausa'
};

const formatCurrency = (value: number) =>
  `R$ ${value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const chartColors = [
  '#c4b5fd',
  '#fde68a',
  '#93c5fd',
  '#fdba74',
  '#86efac',
  '#cbd5e1',
  '#fca5a5',
  '#99f6e4',
  '#fbcfe8',
  '#a5b4fc',
  '#f0abfc',
  '#bef264'
];

const normalizeParcelas = (parcelas: ParcelaServico[]) =>
  parcelas.map((parcela, index) => ({
    ...parcela,
    descricao: `Parcela ${index + 1}`
  }));

const getDateParts = (dateValue?: string) => {
  if (!dateValue) return null;

  const isoDate = String(dateValue).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (isoDate) {
    return {
      year: Number(isoDate[1]),
      month: Number(isoDate[2]) - 1
    };
  }

  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return null;

  return {
    year: date.getFullYear(),
    month: date.getMonth()
  };
};

const FieldLabel = ({ children }: { children: React.ReactNode }) => (
  <label className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.05em] text-slate-500">
    {children}
  </label>
);

const fieldClass =
  'w-full rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-4 py-3 text-sm font-medium text-on-surface outline-none transition-all focus:bg-white focus:ring-1 focus:ring-primary-tactile disabled:cursor-not-allowed disabled:opacity-50';

const StatusPill = ({ status }: { status: Servico['status'] }) => (
  <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.05em] ${statusStyles[status] || statusStyles['Em Pausa']}`}>
    {statusLabels[status] || status}
  </span>
);

const MetricCard = ({
  label,
  value,
  helper,
  accent = 'primary'
}: {
  label: string;
  value: string;
  helper: string;
  accent?: 'primary' | 'emerald' | 'blue';
}) => {
  const accentClasses = {
    primary: 'bg-primary-tactile',
    emerald: 'bg-emerald-500',
    blue: 'bg-blue-500'
  };

  return (
    <div className="rounded-2xl border border-[#f3f4f6] bg-white p-5 shadow-card">
      <div className="mb-4 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${accentClasses[accent]}`} />
        <span className="text-[10px] font-semibold uppercase tracking-[0.05em] text-slate-500">{label}</span>
      </div>
      <div className="text-2xl font-bold tracking-normal text-on-surface">{value}</div>
      <p className="mt-2 text-xs font-medium leading-relaxed text-on-surface-variant">{helper}</p>
    </div>
  );
};

const IconButton = ({
  title,
  onClick,
  children,
  className = ''
}: {
  title: string;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
}) => (
  <button
    type="button"
    title={title}
    aria-label={title}
    onClick={onClick}
    className={`inline-flex h-10 w-10 items-center justify-center rounded-lg border border-[#e5e7eb] bg-white text-slate-500 transition-all hover:bg-slate-50 hover:text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-tactile ${className}`}
  >
    {children}
  </button>
);

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
  } as { start: string; end: string; day: number; value: number });
  const [chartYear, setChartYear] = useState(new Date().getFullYear());

  const selectedService = useMemo(() => services.find(s => s.id === selectedServiceId), [services, selectedServiceId]);
  const isSinglePayment = localDoc?.tipo_contrato === 'Pacote Fechado';

  useEffect(() => {
    if (selectedService) {
      setLocalDoc(selectedService);
    } else {
      setLocalDoc(null);
      setShowBatchForm(false);
    }
  }, [selectedServiceId, selectedService]);

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
    if (!confirm('Tem certeza que deseja cancelar este serviço? Todas as parcelas futuras serão removidas.')) return;

    const now = new Date();
    const todayStr = now.toISOString().split('T')[0];
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

  const activeServices = useMemo(() => services.filter(s => s.status === 'Ativo'), [services]);

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
    return activeServices.length;
  }, [activeServices]);

  const availableChartYears = useMemo(() => {
    const years = new Set<number>([new Date().getFullYear()]);

    services.forEach(service => {
      (service.parcelas || []).forEach(parcela => {
        const dateParts = getDateParts(parcela.data_prevista);
        if (dateParts) years.add(dateParts.year);
      });
    });

    return Array.from(years).sort((a, b) => b - a);
  }, [services]);

  const monthlyRevenueChartData = useMemo(() => {
    const monthKeys = Array.from({ length: 12 }, (_, index) => {
      const date = new Date(chartYear, index, 1);
      return {
        key: `${chartYear}-${String(index + 1).padStart(2, '0')}`,
        label: date.toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '').toUpperCase(),
        year: chartYear
      };
    });

    const serviceColorById = new Map<string, string>();
    services.forEach((service, index) => {
      serviceColorById.set(service.id, chartColors[index % chartColors.length]);
    });

    const data = monthKeys.map(month => ({
      ...month,
      total: 0,
      segments: [] as Array<{ serviceId: string; title: string; amount: number; color: string }>
    }));

    const dataByMonth = new Map(data.map(month => [month.key, month]));

    services
      .forEach(service => {
        (service.parcelas || []).forEach(parcela => {
          const dateParts = getDateParts(parcela.data_prevista);
          if (!dateParts) return;

          const key = `${dateParts.year}-${String(dateParts.month + 1).padStart(2, '0')}`;
          const monthData = dataByMonth.get(key);
          if (!monthData) return;

          const existingSegment = monthData.segments.find(segment => segment.serviceId === service.id);
          if (existingSegment) {
            existingSegment.amount += parcela.valor || 0;
          } else {
            monthData.segments.push({
              serviceId: service.id,
              title: service.titulo,
              amount: parcela.valor || 0,
              color: serviceColorById.get(service.id) || chartColors[0]
            });
          }

          monthData.total += parcela.valor || 0;
        });
      });

    data.forEach(month => {
      month.segments.sort((a, b) => b.amount - a.amount);
    });

    return data;
  }, [services, chartYear]);

  const maxMonthlyRevenue = useMemo(
    () => Math.max(...monthlyRevenueChartData.map(month => month.total), 1),
    [monthlyRevenueChartData]
  );

  const revenueLegend = useMemo(() => {
    const servicesByAmount = new Map<string, { title: string; amount: number; color: string }>();

    monthlyRevenueChartData.forEach(month => {
      month.segments.forEach(segment => {
        const current = servicesByAmount.get(segment.serviceId);
        if (current) {
          current.amount += segment.amount;
        } else {
          servicesByAmount.set(segment.serviceId, {
            title: segment.title,
            amount: segment.amount,
            color: segment.color
          });
        }
      });
    });

    return Array.from(servicesByAmount.values())
      .sort((a, b) => b.amount - a.amount);
  }, [monthlyRevenueChartData]);

  const selectedYearRevenue = useMemo(
    () => monthlyRevenueChartData.reduce((acc, month) => acc + month.total, 0),
    [monthlyRevenueChartData]
  );

  const handleGenerateBatch = () => {
    if (!batchForm.start || !batchForm.end || !selectedService || selectedService.tipo_contrato === 'Pacote Fechado') return;

    const start = new Date(batchForm.start + 'T00:00:00');
    const end = new Date(batchForm.end + 'T23:59:59');
    const day = batchForm.day;
    const value = batchForm.value;
    const newParcelas: ParcelaServico[] = [];
    let current = new Date(start.getFullYear(), start.getMonth(), 1);

    while (current <= end) {
      const installmentDate = new Date(current.getFullYear(), current.getMonth(), day);

      if (installmentDate.getMonth() !== current.getMonth()) {
        installmentDate.setDate(0);
      }

      if (installmentDate >= start && installmentDate <= end) {
        newParcelas.push({
          id: Math.random().toString(36).substr(2, 9),
          valor: value,
          data_prevista: installmentDate.toISOString(),
          status: installmentDate <= new Date() ? 'pago' : 'pendente',
          descricao: `Parcela ${(selectedService.parcelas?.length || 0) + newParcelas.length + 1}`
        });
      }

      current.setMonth(current.getMonth() + 1);
    }

    if (newParcelas.length > 0) {
      const updatedParcelas = normalizeParcelas([...(selectedService.parcelas || []), ...newParcelas]);
      onUpdateService(selectedService.id, { parcelas: updatedParcelas });
      setLocalDoc(prev => prev ? { ...prev, parcelas: updatedParcelas } : null);
      setShowBatchForm(false);
      setBatchForm({ start: '', end: '', day: 5, value: 0 });
    }
  };

  const handleCreateService = () => {
    const newService: Omit<Servico, 'id' | 'data_criacao' | 'data_atualizacao'> = {
      titulo: 'Novo Serviço',
      descricao: 'Descreva o escopo do serviço.',
      cliente: 'Nome do cliente',
      papel: '',
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

    onCreateService(newService);
    setActiveTab('list');
  };

  return (
    <div className="min-h-screen bg-[#f9fafb] p-4 pb-20 font-sans text-on-surface md:p-6">
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6">
        <header className="flex flex-col gap-4 rounded-2xl border border-[#f3f4f6] bg-white p-5 shadow-card md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.05em] text-primary-tactile">Gestão comercial</p>
            <h1 className="mt-1 text-2xl font-bold leading-tight text-on-surface">Serviços</h1>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-on-surface-variant">
              Acompanhe contratos, capacidade comprometida e parcelas previstas em uma única área.
            </p>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="inline-flex rounded-lg border border-[#e5e7eb] bg-slate-100 p-1">
              <button
                type="button"
                onClick={() => setActiveTab('dashboard')}
                className={`rounded-md px-4 py-2 text-xs font-semibold transition-all ${activeTab === 'dashboard' ? 'bg-white text-on-surface shadow-sm' : 'text-slate-500 hover:text-on-surface'}`}
              >
                Visão geral
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('list')}
                className={`rounded-md px-4 py-2 text-xs font-semibold transition-all ${activeTab === 'list' ? 'bg-white text-on-surface shadow-sm' : 'text-slate-500 hover:text-on-surface'}`}
              >
                Inventário
              </button>
            </div>
            <button
              type="button"
              onClick={handleCreateService}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary-tactile px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition-all hover:bg-on-surface focus:outline-none focus:ring-1 focus:ring-primary-tactile"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
              </svg>
              Novo serviço
            </button>
          </div>
        </header>

        {activeTab === 'dashboard' && (
          <div className="flex flex-col gap-4">
            <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <MetricCard
                label={`Receita programada ${chartYear}`}
                value={formatCurrency(selectedYearRevenue)}
                helper="Total das parcelas cadastradas no ano selecionado."
              />
              <MetricCard
                label="A receber"
                value={formatCurrency(receivables)}
                helper="Parcelas futuras em serviços ativos ou concluídos."
                accent="emerald"
              />
              <MetricCard
                label="Serviços ativos"
                value={String(committedCapacity)}
                helper="Contratos atualmente em execução."
                accent="blue"
              />
            </section>

            <section className="rounded-2xl border border-[#f3f4f6] bg-white p-5 shadow-card">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.05em] text-primary-tactile">Receita programada</p>
                  <h2 className="mt-1 text-base font-bold text-on-surface">Ganho mensal por serviço</h2>
                  <p className="mt-1 text-sm leading-relaxed text-on-surface-variant">
                    Colunas empilhadas de janeiro a dezembro com base nas parcelas programadas.
                  </p>
                </div>

                <div className="flex flex-col gap-3 md:items-end">
                  <div>
                    <FieldLabel>Ano</FieldLabel>
                    <select
                      value={chartYear}
                      onChange={(e) => setChartYear(Number(e.target.value))}
                      className="rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-4 py-2 text-sm font-semibold text-on-surface outline-none transition-all focus:bg-white focus:ring-1 focus:ring-primary-tactile"
                    >
                      {availableChartYears.map(year => (
                        <option key={year} value={year}>{year}</option>
                      ))}
                    </select>
                  </div>

                  {revenueLegend.length > 0 && (
                    <div className="flex max-w-xl flex-wrap justify-start gap-2 md:justify-end">
                      {revenueLegend.map(item => (
                        <span key={item.title} className="inline-flex max-w-[220px] items-center gap-2 rounded-full border border-[#e5e7eb] bg-[#f9fafb] px-3 py-1 text-[10px] font-semibold text-slate-600">
                          <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                          <span className="truncate">{item.title}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {monthlyRevenueChartData.some(month => month.total > 0) ? (
                <div className="mt-6 overflow-x-auto pb-2">
                  <div className="flex min-w-[760px] items-end gap-3">
                    {monthlyRevenueChartData.map(month => {
                      const heightPercent = (month.total / maxMonthlyRevenue) * 100;

                      return (
                        <div key={month.key} className="flex min-w-0 flex-1 flex-col items-center gap-3">
                          <div className="flex h-56 w-full flex-col justify-end rounded-xl border border-[#f3f4f6] bg-[#f9fafb] p-2">
                            <div
                              className="flex min-h-[8px] w-full flex-col-reverse overflow-hidden rounded-lg"
                              style={{ height: `${Math.max(heightPercent, month.total > 0 ? 8 : 0)}%` }}
                              title={`${month.label}/${month.year}: ${formatCurrency(month.total)}`}
                            >
                              {month.segments.map(segment => (
                                <div
                                  key={segment.serviceId}
                                  className="w-full transition-opacity hover:opacity-80"
                                  style={{
                                    height: `${month.total > 0 ? (segment.amount / month.total) * 100 : 0}%`,
                                    backgroundColor: segment.color,
                                    borderTop: '1px solid rgba(255,255,255,0.85)'
                                  }}
                                  title={`${segment.title}: ${formatCurrency(segment.amount)}`}
                                />
                              ))}
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-slate-500">{month.label}</div>
                            <div className="mt-1 text-xs font-bold text-on-surface">{formatCurrency(month.total)}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="mt-6 rounded-2xl border border-dashed border-[#e5e7eb] bg-[#f9fafb] p-10 text-center">
                  <p className="text-sm font-semibold text-slate-500">Nenhuma parcela programada em {chartYear}.</p>
                  <p className="mt-1 text-sm text-on-surface-variant">Adicione parcelas aos serviços para visualizar a projeção mensal do ano.</p>
                </div>
              )}
            </section>
          </div>
        )}

        {activeTab === 'list' && (
          <section className="rounded-2xl border border-[#f3f4f6] bg-white shadow-card">
            <div className="flex flex-col gap-2 border-b border-[#f3f4f6] p-5 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-base font-bold text-on-surface">Inventário de serviços</h2>
                <p className="mt-1 text-sm text-on-surface-variant">{services.length} serviço(s) cadastrado(s)</p>
              </div>
            </div>

            {services.length === 0 ? (
              <div className="flex min-h-[280px] flex-col items-center justify-center p-8 text-center">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#f5f3ff] text-primary-tactile">
                  <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 7h-3V5a2 2 0 00-2-2H9a2 2 0 00-2 2v2H4m16 0v12a2 2 0 01-2 2H6a2 2 0 01-2-2V7m16 0H4m5 0V5h6v2" />
                  </svg>
                </div>
                <h3 className="text-sm font-bold text-on-surface">Nenhum serviço cadastrado</h3>
                <p className="mt-1 max-w-md text-sm text-on-surface-variant">Crie o primeiro registro para acompanhar escopo, valores e parcelas.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
                {services.map(service => (
                  <button
                    key={service.id}
                    type="button"
                    onClick={() => setSelectedServiceId(service.id)}
                    className="group flex min-h-[260px] flex-col rounded-2xl border border-[#f3f4f6] bg-white p-5 text-left shadow-sm transition-all hover:border-primary-tactile/30 hover:bg-slate-50/60 focus:outline-none focus:ring-1 focus:ring-primary-tactile"
                  >
                    <div className="mb-4 flex items-start justify-between gap-3">
                      <StatusPill status={service.status} />
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-500">
                        {service.tipo_contrato === 'Pacote Fechado' ? 'Parcela única' : 'Mensalidade'}
                      </span>
                    </div>

                    <h3 className="text-lg font-bold leading-tight text-on-surface transition-colors group-hover:text-primary-tactile">{service.titulo}</h3>
                    <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-on-surface-variant">{service.descricao || 'Sem descrição cadastrada.'}</p>

                    <div className="mt-5 space-y-3 text-sm">
                      <div className="flex items-center justify-between gap-4 border-t border-[#f3f4f6] pt-3">
                        <span className="text-slate-500">Cliente</span>
                        <span className="truncate font-semibold text-on-surface">{service.cliente}</span>
                      </div>
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-slate-500">Forma</span>
                        <span className="truncate font-semibold text-on-surface">
                          {service.tipo_contrato === 'Pacote Fechado' ? 'Parcela única' : 'Mensalidade'}
                        </span>
                      </div>
                    </div>

                    <div className="mt-auto flex items-end justify-between border-t border-[#f3f4f6] pt-5">
                      <div>
                        <span className="text-[10px] font-semibold uppercase tracking-[0.05em] text-slate-500">Valor total</span>
                        <p className="mt-1 text-lg font-bold text-on-surface">{formatCurrency(service.valor_total)}</p>
                      </div>
                      <span className="text-xs font-semibold text-primary-tactile opacity-0 transition-opacity group-hover:opacity-100">Abrir</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>
        )}

        {selectedService && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-on-surface/70 p-4 backdrop-blur-sm">
            <div className="flex max-h-[95vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-[#f3f4f6] bg-white shadow-card animate-in zoom-in-95 duration-200">
              <div className="flex flex-col gap-4 border-b border-[#f3f4f6] bg-white p-5 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    <StatusPill status={selectedService.status} />
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.05em] text-slate-500">
                      {selectedService.tipo_contrato === 'Pacote Fechado' ? 'Parcela única' : 'Mensalidade'}
                    </span>
                  </div>
                  <textarea
                    rows={2}
                    className="min-h-[72px] w-full resize-none rounded-lg border border-transparent bg-transparent px-0 py-1 text-2xl font-bold leading-tight text-on-surface outline-none transition-all focus:border-[#e5e7eb] focus:bg-[#f9fafb] focus:px-3 focus:ring-1 focus:ring-primary-tactile"
                    value={localDoc?.titulo || ''}
                    onChange={(e) => setLocalDoc(prev => prev ? { ...prev, titulo: e.target.value } : null)}
                    onBlur={(e) => onUpdateService(selectedService.id, { titulo: e.target.value })}
                  />
                  <p className="mt-1 text-sm text-on-surface-variant">Edite o cadastro, as datas e a agenda financeira deste serviço.</p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {selectedService.status === 'Prospecção' && (
                    <button
                      type="button"
                      onClick={() => handleApproveService(selectedService.id)}
                      className="rounded-lg bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white transition-all hover:bg-emerald-700"
                    >
                      Ativar
                    </button>
                  )}
                  {selectedService.status === 'Ativo' && (
                    <button
                      type="button"
                      onClick={() => handleCancelService(selectedService.id)}
                      className="rounded-lg border border-rose-200 bg-white px-4 py-2.5 text-xs font-semibold text-rose-600 transition-all hover:bg-rose-50"
                    >
                      Cancelar
                    </button>
                  )}
                  <IconButton
                    title="Excluir serviço"
                    onClick={() => {
                      if (confirm('Tem certeza que deseja excluir este serviço?')) {
                        onDeleteService(selectedService.id);
                        setSelectedServiceId(null);
                      }
                    }}
                    className="text-rose-500 hover:border-rose-100 hover:bg-rose-50 hover:text-rose-600"
                  >
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </IconButton>
                  <IconButton title="Fechar" onClick={() => setSelectedServiceId(null)}>
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </IconButton>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto bg-[#f9fafb] p-5">
                <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
                  <section className="rounded-2xl border border-[#f3f4f6] bg-white p-5 shadow-sm">
                    <h2 className="text-base font-bold text-on-surface">Dados do serviço</h2>
                    <div className="mt-5 grid grid-cols-1 gap-5">
                      <div>
                        <FieldLabel>Cliente</FieldLabel>
                        <input
                          type="text"
                          value={localDoc?.cliente || ''}
                          onChange={(e) => setLocalDoc(prev => prev ? { ...prev, cliente: e.target.value } : null)}
                          onBlur={(e) => onUpdateService(selectedService.id, { cliente: e.target.value })}
                          className={fieldClass}
                        />
                      </div>
                      <div>
                        <FieldLabel>Escopo</FieldLabel>
                        <textarea
                          value={localDoc?.descricao || ''}
                          onChange={(e) => setLocalDoc(prev => prev ? { ...prev, descricao: e.target.value } : null)}
                          onBlur={(e) => onUpdateService(selectedService.id, { descricao: e.target.value })}
                          className={`${fieldClass} min-h-[128px] resize-none leading-relaxed`}
                        />
                      </div>
                    </div>
                  </section>

                  <aside className="rounded-2xl border border-[#f3f4f6] bg-white p-5 shadow-sm">
                    <h2 className="text-base font-bold text-on-surface">Contrato</h2>
                    <div className="mt-5 space-y-5">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <FieldLabel>Inicio</FieldLabel>
                          <input
                            type="date"
                            disabled={localDoc?.status === 'Prospecção'}
                            value={localDoc?.data_inicio?.split('T')[0] || ''}
                            onChange={(e) => {
                              const val = new Date(e.target.value).toISOString();
                              setLocalDoc(prev => prev ? { ...prev, data_inicio: val } : null);
                              onUpdateService(selectedService.id, { data_inicio: val });
                            }}
                            className={fieldClass}
                          />
                        </div>
                        <div>
                          <FieldLabel>Termino</FieldLabel>
                          <input
                            type="date"
                            disabled={localDoc?.status === 'Prospecção'}
                            value={localDoc?.data_termino?.split('T')[0] || ''}
                            onChange={(e) => {
                              const val = new Date(e.target.value).toISOString();
                              setLocalDoc(prev => prev ? { ...prev, data_termino: val } : null);
                              onUpdateService(selectedService.id, { data_termino: val });
                            }}
                            className={fieldClass}
                          />
                        </div>
                      </div>

                      <div>
                        <FieldLabel>Forma de pagamento</FieldLabel>
                        <select
                          value={localDoc?.tipo_contrato || 'Mensalidade'}
                          onChange={(e) => {
                            const val = e.target.value as Servico['tipo_contrato'];
                            const currentParcelas = localDoc?.parcelas || [];
                            const nextParcelas = val === 'Pacote Fechado'
                              ? normalizeParcelas(currentParcelas.slice(0, 1))
                              : normalizeParcelas(currentParcelas);

                            setLocalDoc(prev => prev ? { ...prev, tipo_contrato: val, parcelas: nextParcelas } : null);
                            onUpdateService(selectedService.id, { tipo_contrato: val, parcelas: nextParcelas });
                            if (val === 'Pacote Fechado') setShowBatchForm(false);
                          }}
                          className={fieldClass}
                        >
                          <option value="Pacote Fechado">Parcela única</option>
                          <option value="Mensalidade">Mensalidade</option>
                        </select>
                      </div>

                      <div>
                        <FieldLabel>Valor total</FieldLabel>
                        <div className="relative">
                          <span className="absolute left-4 top-1/2 -translate-y-1/2 text-xs font-semibold text-primary-tactile">R$</span>
                          <input
                            type="number"
                            value={localDoc?.valor_total || 0}
                            onChange={(e) => setLocalDoc(prev => prev ? { ...prev, valor_total: Number(e.target.value) } : null)}
                            onBlur={(e) => onUpdateService(selectedService.id, { valor_total: Number(e.target.value) })}
                            className={`${fieldClass} pl-10 text-lg font-bold`}
                          />
                        </div>
                        <button
                          type="button"
                          onClick={handleUpdateTotalFromParcelas}
                          disabled={!localDoc?.parcelas || localDoc.parcelas.length === 0}
                          className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-primary-tactile transition-all hover:text-on-surface disabled:text-slate-300"
                        >
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 7h6m0 10v-3m-3 3h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                          </svg>
                          Atualizar pelo total das parcelas
                        </button>
                      </div>
                    </div>
                  </aside>
                </div>

                <section className="mt-5 rounded-2xl border border-[#f3f4f6] bg-white p-5 shadow-sm">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                      <h2 className="text-base font-bold text-on-surface">Parcelas</h2>
                      <p className="mt-1 text-sm text-on-surface-variant">
                        {isSinglePayment
                          ? 'Informe o valor e a data da parcela única.'
                          : 'Agenda financeira usada para sincronizar receitas mensais.'}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {!isSinglePayment && (
                        <button
                          type="button"
                          onClick={() => setShowBatchForm(!showBatchForm)}
                          className="rounded-lg border border-[#e5e7eb] bg-white px-4 py-2.5 text-xs font-semibold text-slate-600 transition-all hover:bg-slate-50"
                        >
                          {showBatchForm ? 'Fechar gerador' : 'Gerar em lote'}
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={isSinglePayment && (localDoc?.parcelas || []).length >= 1}
                        onClick={() => {
                          if (isSinglePayment && (localDoc?.parcelas || []).length >= 1) return;

                          const newParcela: ParcelaServico = {
                            id: Math.random().toString(36).substr(2, 9),
                            valor: 0,
                            data_prevista: new Date().toISOString(),
                            status: 'pendente',
                            descricao: `Parcela ${(localDoc?.parcelas || []).length + 1}`
                          };
                          const newParcelas = normalizeParcelas(
                            isSinglePayment ? [newParcela] : [...(selectedService.parcelas || []), newParcela]
                          );
                          onUpdateService(selectedService.id, { parcelas: newParcelas });
                          setLocalDoc(prev => prev ? { ...prev, parcelas: newParcelas } : null);
                        }}
                        className="rounded-lg bg-on-surface px-4 py-2.5 text-xs font-semibold text-white transition-all hover:bg-primary-tactile disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {isSinglePayment ? 'Adicionar valor' : 'Adicionar parcela'}
                      </button>
                    </div>
                  </div>

                  {showBatchForm && !isSinglePayment && (
                    <div className="mt-5 rounded-2xl border border-[#f3f4f6] bg-[#f9fafb] p-5">
                      <h3 className="text-sm font-bold text-on-surface">Gerar parcelas recorrentes</h3>
                      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-5 md:items-end">
                        <div>
                          <FieldLabel>Inicio</FieldLabel>
                          <input type="date" value={batchForm.start} onChange={e => setBatchForm(prev => ({ ...prev, start: e.target.value }))} className={fieldClass} />
                        </div>
                        <div>
                          <FieldLabel>Fim</FieldLabel>
                          <input type="date" value={batchForm.end} onChange={e => setBatchForm(prev => ({ ...prev, end: e.target.value }))} className={fieldClass} />
                        </div>
                        <div>
                          <FieldLabel>Dia</FieldLabel>
                          <input type="number" min="1" max="31" value={batchForm.day} onChange={e => setBatchForm(prev => ({ ...prev, day: Number(e.target.value) }))} className={fieldClass} />
                        </div>
                        <div>
                          <FieldLabel>Valor</FieldLabel>
                          <input type="number" value={batchForm.value} onChange={e => setBatchForm(prev => ({ ...prev, value: Number(e.target.value) }))} className={fieldClass} />
                        </div>
                        <button
                          type="button"
                          onClick={handleGenerateBatch}
                          className="rounded-lg bg-primary-tactile px-4 py-3 text-xs font-semibold text-white transition-all hover:bg-on-surface"
                        >
                          Gerar parcelas
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="mt-5 space-y-3">
                    {(localDoc?.parcelas || []).map((parcela, index) => {
                      const isReceived = new Date(parcela.data_prevista) <= new Date();

                      return (
                        <div key={parcela.id} className="grid grid-cols-1 gap-3 rounded-2xl border border-[#f3f4f6] bg-white p-4 shadow-sm md:grid-cols-[40px_minmax(0,1fr)_160px_160px_140px_40px] md:items-center">
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 text-xs font-bold text-slate-500">
                            {String(index + 1).padStart(2, '0')}
                          </div>
                          <div className="rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-4 py-3 text-sm font-semibold text-on-surface">
                            Parcela {index + 1}
                          </div>
                          <div className="relative">
                            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[10px] font-semibold text-primary-tactile">R$</span>
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
                                const normalized = normalizeParcelas(updated);
                                setLocalDoc({ ...localDoc!, parcelas: normalized });
                                onUpdateService(selectedService.id, { parcelas: normalized });
                              }}
                              className={`${fieldClass} pl-9`}
                            />
                          </div>
                          <input
                            type="date"
                            value={parcela.data_prevista.split('T')[0]}
                            onChange={(e) => {
                              const val = new Date(e.target.value).toISOString();
                              const updated = [...localDoc!.parcelas];
                              updated[index].data_prevista = val;
                              const normalized = normalizeParcelas(updated);
                              setLocalDoc({ ...localDoc!, parcelas: normalized });
                              onUpdateService(selectedService.id, { parcelas: normalized });
                            }}
                            className={fieldClass}
                          />
                          <span className={`inline-flex w-fit items-center gap-2 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.05em] ${isReceived ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${isReceived ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                            {isReceived ? 'Recebida' : 'Pendente'}
                          </span>
                          <IconButton
                            title="Excluir parcela"
                            onClick={() => {
                              if (confirm('Deseja realmente excluir esta parcela?')) {
                                const updated = normalizeParcelas(localDoc!.parcelas.filter((_, i) => i !== index));
                                setLocalDoc({ ...localDoc!, parcelas: updated });
                                onUpdateService(selectedService.id, { parcelas: updated });
                              }
                            }}
                            className="text-rose-500 hover:border-rose-100 hover:bg-rose-50 hover:text-rose-600"
                          >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </IconButton>
                        </div>
                      );
                    })}

                    {(localDoc?.parcelas || []).length === 0 && (
                      <div className="rounded-2xl border border-dashed border-[#e5e7eb] bg-[#f9fafb] p-10 text-center">
                        <p className="text-sm font-semibold text-slate-500">Nenhuma parcela cadastrada.</p>
                        <p className="mt-1 text-sm text-on-surface-variant">
                          {isSinglePayment
                            ? 'Adicione o valor único a receber.'
                            : 'Adicione uma parcela avulsa ou gere uma sequência recorrente.'}
                        </p>
                      </div>
                    )}
                  </div>
                </section>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
