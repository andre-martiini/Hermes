import React, { useEffect, useMemo, useState } from 'react';
import { PlanoTrabalho } from '../../../types';
import {
  ASSISTENCIA_ENTREGA,
  CreatePgdPlanPayload,
  distributePgdPercentages,
  findLatestDescription,
  getPgdPeriodFromMonth,
  getPgdTargetPeriod,
  getSourcePlan,
  isOwnUnitItem,
  NAO_VINCULADA_DESCRICAO,
  normalizePgdDeliveryIdentity,
  suggestPgdDescription,
} from '../../utils/pgdPlanAutomation';

interface Props {
  plans: PlanoTrabalho[];
  onClose: () => void;
  onSubmit: (payload: CreatePgdPlanPayload) => Promise<void>;
}

const monthLabel = (value: string) => {
  const [year, month] = value.split('-').map(Number);
  return new Intl.DateTimeFormat('pt-BR', {
    month: 'long',
    year: 'numeric',
  }).format(new Date(year, month - 1, 1));
};

const AUTOMATION_API = 'http://127.0.0.1:8000/api/automations';

export const CreatePgdPlanModal: React.FC<Props> = ({
  plans,
  onClose,
  onSubmit,
}) => {
  const [targetMonth, setTargetMonth] = useState(
    () => getPgdTargetPeriod().mesAno,
  );
  const [liveCatalog, setLiveCatalog] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const period = useMemo(
    () => getPgdPeriodFromMonth(targetMonth),
    [targetMonth],
  );
  const sourcePlan = useMemo(
    () => getSourcePlan(plans, period.mesAno),
    [plans, period.mesAno],
  );
  const historicalPlans = useMemo(
    () => plans.filter(plan => plan.mes_ano < period.mesAno),
    [plans, period.mesAno],
  );
  const historicalSelection = useMemo(() => {
    const historical = (sourcePlan?.itens || [])
      .filter(isOwnUnitItem)
      .map(item => normalizePgdDeliveryIdentity(item.entrega));
    return new Set(
      liveCatalog.filter(
        item => historical.includes(normalizePgdDeliveryIdentity(item)),
      ),
    );
  }, [sourcePlan, liveCatalog]);
  const [selected, setSelected] = useState<Set<string>>(historicalSelection);
  const [descriptions, setDescriptions] = useState<Record<string, string>>(() => {
    const values: Record<string, string> = {};
    for (const entrega of liveCatalog) {
      values[entrega] = findLatestDescription(entrega, historicalPlans)
        || suggestPgdDescription(entrega);
    }
    values[ASSISTENCIA_ENTREGA] =
      findLatestDescription(ASSISTENCIA_ENTREGA, historicalPlans)
      || suggestPgdDescription(ASSISTENCIA_ENTREGA);
    values['Não vinculadas a entregas'] = NAO_VINCULADA_DESCRICAO;
    return values;
  });
  useEffect(() => {
    const nextDescriptions: Record<string, string> = {};
    for (const entrega of liveCatalog) {
      nextDescriptions[entrega] =
        findLatestDescription(entrega, historicalPlans)
        || suggestPgdDescription(entrega);
    }
    nextDescriptions[ASSISTENCIA_ENTREGA] =
      findLatestDescription(ASSISTENCIA_ENTREGA, historicalPlans)
      || suggestPgdDescription(ASSISTENCIA_ENTREGA);
    nextDescriptions['Não vinculadas a entregas'] = NAO_VINCULADA_DESCRICAO;
    setSelected(new Set(historicalSelection));
    setDescriptions(nextDescriptions);
  }, [targetMonth, historicalPlans, historicalSelection, liveCatalog]);

  const orderedSelected = liveCatalog.filter(item => selected.has(item));
  const totalDeliveries = orderedSelected.length + 2;
  const percentages = useMemo(
    () => distributePgdPercentages(totalDeliveries),
    [totalDeliveries],
  );

  const closeRemoteSession = async (id: string | null) => {
    if (!id) return;
    try {
      await fetch(`${AUTOMATION_API}/sessoes-plano-pgd/${id}`, {
        method: 'DELETE',
      });
    } catch {
      // A sessão também será descartada automaticamente após expirar.
    }
  };

  const resetCatalog = (closeSession = true) => {
    if (closeSession) void closeRemoteSession(sessionId);
    setSessionId(null);
    setLiveCatalog([]);
    setSelected(new Set());
    setError('');
  };

  const handleTargetMonthChange = (value: string) => {
    if (!/^\d{4}-\d{2}$/.test(value) || value === targetMonth) return;
    resetCatalog(true);
    setTargetMonth(value);
  };

  const handleClose = () => {
    void closeRemoteSession(sessionId);
    onClose();
  };

  const loadLiveCatalog = async () => {
    setError('');
    setIsLoadingCatalog(true);
    if (sessionId) {
      await closeRemoteSession(sessionId);
      setSessionId(null);
    }
    try {
      const response = await fetch(`${AUTOMATION_API}/preparar-plano-pgd`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mes_ano: period.mesAno,
          data_inicio: period.dataInicio,
          data_fim: period.dataFim,
          unidade: 'CLC-BSF',
          modalidade: 'Teletrabalho (Integral)',
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          data?.detail || 'Não foi possível consultar as entregas no Petrvs.',
        );
      }
      const deliveries = Array.isArray(data?.entregas)
        ? data.entregas.filter(
          (item: unknown): item is string =>
            typeof item === 'string' && item.trim().length > 0,
        )
        : [];
      if (!data?.sessao_id || deliveries.length === 0) {
        throw new Error('O Petrvs não retornou entregas disponíveis.');
      }
      setSessionId(String(data.sessao_id));
      setLiveCatalog(deliveries);
    } catch (catalogError) {
      setLiveCatalog([]);
      setSessionId(null);
      setError(
        catalogError instanceof Error
          ? catalogError.message
          : 'Não foi possível consultar as entregas no Petrvs.',
      );
    } finally {
      setIsLoadingCatalog(false);
    }
  };

  const toggleDelivery = (entrega: string) => {
    setSelected(current => {
      const next = new Set(current);
      if (next.has(entrega)) next.delete(entrega);
      else next.add(entrega);
      return next;
    });
  };

  const submit = async () => {
    setError('');
    if (!sessionId) {
      setError('Consulte as entregas disponíveis no Petrvs antes de gravar.');
      return;
    }
    const rows = [
      {
        origem: 'Outra Unidade' as const,
        unidade: 'BSF-CAB',
        entrega: ASSISTENCIA_ENTREGA,
        descricao: descriptions[ASSISTENCIA_ENTREGA].trim(),
        percentual: percentages[0],
        plano_entrega_codigo: '2568',
        fixed: true,
      },
      {
        origem: 'Não vinculadas a entregas' as const,
        unidade: 'Não vinculadas a entregas',
        entrega: 'Não vinculadas a entregas',
        descricao: descriptions['Não vinculadas a entregas'].trim(),
        percentual: percentages[1],
        fixed: true,
      },
      ...orderedSelected.map((entrega, index) => ({
        origem: 'Própria Unidade' as const,
        unidade: 'CLC-BSF',
        entrega,
        descricao: descriptions[entrega].trim(),
        percentual: percentages[index + 2],
      })),
    ];
    if (rows.some(row => !row.descricao)) {
      setError('Todas as entregas precisam ter uma descrição.');
      return;
    }
    setIsSubmitting(true);
    try {
      await onSubmit({
        sessao_id: sessionId,
        mes_ano: period.mesAno,
        data_inicio: period.dataInicio,
        data_fim: period.dataFim,
        unidade: 'CLC-BSF',
        modalidade: 'Teletrabalho (Integral)',
        entregas: rows,
      });
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : 'Não foi possível iniciar a automação.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderDescription = (entrega: string, fixed = false) => (
    <div className="border-2 border-border-grid bg-white p-4">
      <div className="flex items-start gap-3">
        {!fixed && (
          <input
            type="checkbox"
            checked={selected.has(entrega)}
            onChange={() => toggleDelivery(entrega)}
            className="mt-1 h-4 w-4 accent-slate-900"
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] font-black uppercase leading-snug text-slate-800 font-mono">
              {entrega}
            </p>
            {fixed && (
              <span className="shrink-0 border border-blue-200 bg-blue-50 px-2 py-1 text-[8px] font-black uppercase text-blue-600 font-mono">
                Fixa
              </span>
            )}
          </div>
          {(fixed || selected.has(entrega)) && (
            <textarea
              value={descriptions[entrega] || ''}
              onChange={event => setDescriptions(current => ({
                ...current,
                [entrega]: event.target.value,
              }))}
              className="mt-3 min-h-[72px] w-full resize-y border border-border-grid bg-slate-50 p-3 text-[10px] leading-relaxed text-slate-700 outline-none focus:border-blue-500 font-mono"
            />
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-slate-950/70 p-3 md:p-8">
      <div className="flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden border-2 border-slate-900 bg-slate-50 shadow-2xl">
        <header className="flex items-center justify-between border-b-2 border-border-grid bg-white p-5 md:p-6">
          <div>
            <p className="text-[9px] font-black uppercase tracking-[0.25em] text-blue-600 font-mono">
              Petrvs · Novo plano
            </p>
            <h2 className="mt-1 text-lg font-black uppercase text-slate-900 font-mono">
              Plano de {monthLabel(period.mesAno)}
            </h2>
            <p className="mt-1 text-[10px] text-slate-500 font-mono">
              {period.dataInicio.split('-').reverse().join('/')} até{' '}
              {period.dataFim.split('-').reverse().join('/')} · CLC-BSF · Teletrabalho Integral
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="border-2 border-border-grid bg-slate-50 px-3 py-2">
              <span className="block text-[8px] font-black uppercase tracking-widest text-slate-500 font-mono">
                Mês do plano
              </span>
              <input
                type="month"
                value={targetMonth}
                onChange={event => handleTargetMonthChange(event.target.value)}
                disabled={isSubmitting || isLoadingCatalog}
                className="mt-1 bg-transparent text-[11px] font-black text-slate-900 outline-none font-mono"
              />
            </label>
            <button
              onClick={handleClose}
              disabled={isSubmitting || isLoadingCatalog}
              className="h-10 w-10 border-2 border-border-grid bg-white text-xl font-black text-slate-500 hover:border-red-400 hover:text-red-600"
              aria-label="Fechar"
            >
              ×
            </button>
          </div>
        </header>

        <div className="grid flex-1 gap-5 overflow-y-auto p-4 md:grid-cols-[1.3fr_0.7fr] md:p-6">
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-[11px] font-black uppercase tracking-widest text-slate-800 font-mono">
                Entregas da própria unidade
              </h3>
              {sessionId && (
                <span className="text-[9px] font-black uppercase text-slate-400 font-mono">
                  {orderedSelected.length} de {liveCatalog.length} selecionada(s)
                </span>
              )}
            </div>
            {!sessionId ? (
              <div className="border-2 border-dashed border-border-grid bg-white p-8 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center border-2 border-blue-200 bg-blue-50 text-blue-600">
                  <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16l4-4 4 4m0-8l-4 4-4-4" />
                  </svg>
                </div>
                <h4 className="mt-4 text-[12px] font-black uppercase text-slate-800 font-mono">
                  Consultar entregas do Petrvs
                </h4>
                <p className="mx-auto mt-2 max-w-lg text-[10px] leading-relaxed text-slate-500 font-mono">
                  O Chrome será aberto para autenticação. O robô configurará o mês e
                  lerá as opções disponíveis diretamente no dropdown do Petrvs.
                </p>
                <button
                  onClick={loadLiveCatalog}
                  disabled={isLoadingCatalog || isSubmitting}
                  className="mt-5 bg-blue-600 px-6 py-3 text-[10px] font-black uppercase tracking-widest text-white hover:bg-blue-700 disabled:opacity-50 font-mono"
                >
                  {isLoadingCatalog ? 'Aguardando Petrvs...' : 'Acessar e consultar'}
                </button>
              </div>
            ) : (
              <>
                <div className="mb-3 flex items-center justify-between border border-emerald-200 bg-emerald-50 p-3">
                  <p className="text-[9px] font-black uppercase text-emerald-700 font-mono">
                    {liveCatalog.length} entregas consultadas em tempo real
                  </p>
                  <button
                    onClick={loadLiveCatalog}
                    disabled={isLoadingCatalog || isSubmitting}
                    className="text-[9px] font-black uppercase text-emerald-700 underline font-mono"
                  >
                    Atualizar
                  </button>
                </div>
                <div className="space-y-2">
                  {liveCatalog.map(entrega => (
                    <React.Fragment key={entrega}>
                      {renderDescription(entrega)}
                    </React.Fragment>
                  ))}
                </div>
              </>
            )}
          </section>

          <aside className="space-y-5">
            <div>
              <h3 className="mb-3 text-[11px] font-black uppercase tracking-widest text-slate-800 font-mono">
                Entregas obrigatórias
              </h3>
              <div className="space-y-2">
                {renderDescription(ASSISTENCIA_ENTREGA, true)}
                {renderDescription('Não vinculadas a entregas', true)}
              </div>
            </div>

            <div className="border-2 border-border-grid bg-white p-4">
              <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-800 font-mono">
                Distribuição automática
              </h3>
              <div className="mt-3 space-y-2">
                {[
                  ASSISTENCIA_ENTREGA,
                  'Não vinculadas a entregas',
                  ...orderedSelected,
                ].map((entrega, index) => (
                  <div key={entrega} className="flex items-start justify-between gap-3 border-b border-slate-100 pb-2">
                    <span className="text-[9px] leading-snug text-slate-500 font-mono">
                      {entrega}
                    </span>
                    <strong className="shrink-0 text-[10px] text-slate-900 font-mono">
                      {percentages[index]}%
                    </strong>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex justify-between border-t-2 border-slate-900 pt-3 text-[11px] font-black uppercase font-mono">
                <span>Total</span>
                <span>100%</span>
              </div>
            </div>
          </aside>
        </div>

        <footer className="border-t-2 border-border-grid bg-white p-4 md:flex md:items-center md:justify-between md:p-6">
          <div>
            {sourcePlan && (
              <p className="text-[9px] text-slate-500 font-mono">
                Descrições priorizadas a partir do plano {sourcePlan.mes_ano}.
              </p>
            )}
            {error && (
              <p className="mt-1 text-[10px] font-black text-red-600 font-mono">
                {error}
              </p>
            )}
          </div>
          <div className="mt-3 flex gap-2 md:mt-0">
            <button
              onClick={handleClose}
              disabled={isSubmitting || isLoadingCatalog}
              className="px-5 py-3 text-[10px] font-black uppercase tracking-widest text-slate-500 font-mono"
            >
              Cancelar
            </button>
            <button
              onClick={submit}
              disabled={isSubmitting || isLoadingCatalog || !sessionId}
              className="bg-slate-900 px-6 py-3 text-[10px] font-black uppercase tracking-[0.18em] text-white hover:bg-blue-600 disabled:opacity-50 font-mono"
            >
              {isSubmitting
                ? 'Iniciando...'
                : sessionId
                  ? 'Criar e gravar no Petrvs'
                  : 'Consulte o Petrvs primeiro'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
};
