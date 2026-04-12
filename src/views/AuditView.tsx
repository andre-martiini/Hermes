import React, { useEffect, useState } from 'react';
import { collection, getDocs, limit, orderBy, query } from 'firebase/firestore';
import { db, functions } from '../../firebase';
import { formatDate } from '../../types';
import type { ApprovalMode, RiskLevel, RoutingMode } from '../../types';
import { httpsCallable } from 'firebase/functions';

interface RoutingEventRecord {
  id: string;
  context_kind: 'task' | 'system' | 'tool';
  context_id?: string;
  context_label?: string;
  route: RoutingMode;
  approval_mode: ApprovalMode;
  risk_level: RiskLevel;
  clarity_score: number;
  context_score: number;
  impact_score: number;
  session_released: boolean;
  ts: string;
}

interface POPRunEventRecord {
  id: string;
  event_type: 'run_created' | 'run_status_changed' | 'step_resolved' | 'learning_recorded';
  pop_id: string;
  pop_run_id?: string;
  context_kind?: 'task' | 'issue_packet' | 'knowledge_item' | 'processo';
  context_id?: string;
  from_status?: string;
  to_status?: string;
  step_id?: string;
  step_status?: string;
  learning_event_id?: string;
  learning_type?: string;
  ts: string;
}

interface ContextUsageEventRecord {
  id: string;
  context_kind: 'task' | 'system';
  context_id?: string;
  context_label?: string;
  usage_kind: 'task_copilot' | 'system_copilot';
  layers: {
    L0: number;
    L1: number;
    L2: number;
    L3: number;
  };
  total_entries: number;
  suggested_pop_id?: string | null;
  pop_run_id?: string | null;
  ts: string;
}

interface AuditViewProps {
  onClose?: () => void;
}

const APPROVAL_LABELS: Record<ApprovalMode, string> = {
  automatic: 'Automático',
  confirm: 'Confirmação',
  required: 'Obrigatório',
};

const RISK_LABELS: Record<RiskLevel, string> = {
  low: 'Baixo',
  medium: 'Médio',
  high: 'Alto',
};

const CONTEXT_KIND_LABELS: Record<string, string> = {
  task: 'Ação',
  system: 'Sistema',
  tool: 'Ferramenta',
};

const APPROVAL_COLORS: Record<ApprovalMode, string> = {
  automatic: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  confirm: 'bg-amber-100 text-amber-700 border-amber-200',
  required: 'bg-rose-100 text-rose-700 border-rose-200',
};

const RISK_COLORS: Record<RiskLevel, string> = {
  low: 'text-emerald-600',
  medium: 'text-amber-600',
  high: 'text-rose-600',
};

export const AuditView: React.FC<AuditViewProps> = ({ onClose }) => {
  const [events, setEvents] = useState<RoutingEventRecord[]>([]);
  const [popEvents, setPopEvents] = useState<POPRunEventRecord[]>([]);
  const [contextUsageEvents, setContextUsageEvents] = useState<ContextUsageEventRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRawBusy, setIsRawBusy] = useState(false);
  const [rawSummary, setRawSummary] = useState<any>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const snap = await getDocs(
          query(
            collection(db, 'routing_events'),
            orderBy('ts', 'desc'),
            limit(200),
          ),
        );
        setEvents(snap.docs.map(d => ({ id: d.id, ...d.data() } as RoutingEventRecord)));

        const popSnap = await getDocs(
          query(
            collection(db, 'pop_run_events'),
            orderBy('ts', 'desc'),
            limit(200),
          ),
        );
        setPopEvents(popSnap.docs.map(d => ({ id: d.id, ...d.data() } as POPRunEventRecord)));

        const contextSnap = await getDocs(
          query(
            collection(db, 'context_usage_events'),
            orderBy('ts', 'desc'),
            limit(200),
          ),
        );
        setContextUsageEvents(contextSnap.docs.map(d => ({ id: d.id, ...d.data() } as ContextUsageEventRecord)));
      } catch (err) {
        console.error('Erro ao carregar eventos de auditoria:', err);
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  // ── Aggregates ────────────────────────────────────────────────
  const byApproval = events.reduce<Record<string, number>>((acc, e) => {
    acc[e.approval_mode] = (acc[e.approval_mode] ?? 0) + 1;
    return acc;
  }, {});

  const byRisk = events.reduce<Record<string, number>>((acc, e) => {
    acc[e.risk_level] = (acc[e.risk_level] ?? 0) + 1;
    return acc;
  }, {});

  const byRoute = events.reduce<Record<string, number>>((acc, e) => {
    acc[e.route] = (acc[e.route] ?? 0) + 1;
    return acc;
  }, {});

  const released = events.filter(e => e.session_released).length;
  const blocked = events.filter(
    e => e.approval_mode !== 'automatic' && !e.session_released,
  ).length;

  const total = events.length;
  const totalPopEvents = popEvents.length;
  const totalContextUsageEvents = contextUsageEvents.length;
  const popRunsCreated = popEvents.filter(e => e.event_type === 'run_created').length;
  const popLearned = popEvents.filter(e => e.event_type === 'learning_recorded').length;
  const popStatusChanged = popEvents.filter(e => e.event_type === 'run_status_changed').length;

  const handleEnsureRawStructure = async () => {
    setIsRawBusy(true);
    try {
      const fn = httpsCallable(functions, 'ensureRawDriveStructure');
      const response = await fn({});
      setRawSummary(response.data);
    } finally {
      setIsRawBusy(false);
    }
  };

  const handleProcessRawCycle = async () => {
    setIsRawBusy(true);
    try {
      const fn = httpsCallable(functions, 'processRawDriveCycle');
      const response = await fn({ maxFiles: 20 });
      setRawSummary(response.data);
    } finally {
      setIsRawBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-4xl mx-auto space-y-8">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-black text-slate-900 tracking-tight">Auditoria de Decisões</h1>
            <p className="text-sm text-slate-500 mt-1 font-medium">
              Histórico de avaliações de roteamento e liberações de sessão
            </p>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-200 rounded-xl text-slate-400 hover:text-slate-600 transition-all"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-40">
            <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* ── Summary cards ───────────────────────────────────── */}
            <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white border border-slate-200 rounded-2xl p-5">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Total</p>
                <p className="text-3xl font-black text-slate-900">{total}</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">eventos registrados</p>
              </div>
              <div className="bg-white border border-amber-200 rounded-2xl p-5">
                <p className="text-[10px] font-black text-amber-500 uppercase tracking-widest mb-1">Liberadas</p>
                <p className="text-3xl font-black text-slate-900">{released}</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">sessões liberadas pelo usuário</p>
              </div>
              <div className="bg-white border border-rose-200 rounded-2xl p-5">
                <p className="text-[10px] font-black text-rose-500 uppercase tracking-widest mb-1">Pendentes</p>
                <p className="text-3xl font-black text-slate-900">{blocked}</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">sessões não liberadas</p>
              </div>
              <div className="bg-white border border-slate-200 rounded-2xl p-5">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Automáticas</p>
                <p className="text-3xl font-black text-slate-900">{byApproval['automatic'] ?? 0}</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">sem intervenção necessária</p>
              </div>
            </section>

            <section className="bg-white border border-slate-200 rounded-2xl p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Ingestão RAW do Drive</h3>
                  <p className="text-sm text-slate-500 mt-2 font-medium">
                    Inicializa a estrutura `raw / raw_processed / raw_rejected` e executa um ciclo manual de ingestão.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={handleEnsureRawStructure}
                    disabled={isRawBusy}
                    className="px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest bg-slate-100 text-slate-700 hover:bg-slate-200 transition-all disabled:opacity-50"
                  >
                    Garantir estrutura RAW
                  </button>
                  <button
                    onClick={handleProcessRawCycle}
                    disabled={isRawBusy}
                    className="px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest bg-slate-900 text-white hover:bg-slate-700 transition-all disabled:opacity-50"
                  >
                    {isRawBusy ? 'Processando...' : 'Processar ciclo RAW'}
                  </button>
                </div>
              </div>
              {rawSummary && (
                <div className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-3">
                  <div className="rounded-xl bg-slate-50 border border-slate-100 px-4 py-3">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Lidos</p>
                    <p className="text-xl font-black text-slate-900 mt-1">{rawSummary.total_seen ?? '—'}</p>
                  </div>
                  <div className="rounded-xl bg-emerald-50 border border-emerald-100 px-4 py-3">
                    <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600">Processados</p>
                    <p className="text-xl font-black text-slate-900 mt-1">{rawSummary.processed ?? '—'}</p>
                  </div>
                  <div className="rounded-xl bg-amber-50 border border-amber-100 px-4 py-3">
                    <p className="text-[10px] font-black uppercase tracking-widest text-amber-600">Ignorados</p>
                    <p className="text-xl font-black text-slate-900 mt-1">{rawSummary.skipped ?? '—'}</p>
                  </div>
                  <div className="rounded-xl bg-rose-50 border border-rose-100 px-4 py-3">
                    <p className="text-[10px] font-black uppercase tracking-widest text-rose-600">Rejeitados</p>
                    <p className="text-xl font-black text-slate-900 mt-1">{rawSummary.rejected ?? '—'}</p>
                  </div>
                  <div className="rounded-xl bg-orange-50 border border-orange-100 px-4 py-3">
                    <p className="text-[10px] font-black uppercase tracking-widest text-orange-600">Bloqueados</p>
                    <p className="text-xl font-black text-slate-900 mt-1">{rawSummary.blocked_by_policy ?? '—'}</p>
                  </div>
                </div>
              )}
              {rawSummary?.sipoc && (
                <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Política SIPOC da esteira RAW</p>
                  <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-600">
                    <div>
                      <p className="font-black uppercase tracking-widest text-[10px] text-slate-400">Fontes homologadas</p>
                      <p className="mt-1 font-semibold text-slate-700">
                        {(rawSummary.sipoc.allowed_source_kinds || []).join(', ') || '—'}
                      </p>
                    </div>
                    <div>
                      <p className="font-black uppercase tracking-widest text-[10px] text-slate-400">Domínios aceitos</p>
                      <p className="mt-1 font-semibold text-slate-700">
                        {(rawSummary.sipoc.allowed_domains || []).join(', ') || '—'}
                      </p>
                    </div>
                  </div>
                </div>
              )}
              {rawSummary?.errors?.length > 0 && (
                <div className="mt-4 rounded-2xl border border-rose-100 bg-rose-50 px-4 py-4">
                  <p className="text-[10px] font-black uppercase tracking-widest text-rose-700">Últimos erros do ciclo RAW</p>
                  <ul className="mt-2 space-y-1">
                    {rawSummary.errors.map((err: string, index: number) => (
                      <li key={`${index}-${err}`} className="text-xs text-rose-800">{err}</li>
                    ))}
                  </ul>
                </div>
              )}
              {rawSummary?.matched_samples?.length > 0 && (
                <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-4">
                  <p className="text-[10px] font-black uppercase tracking-widest text-blue-700">Amostra de classificação e vínculos</p>
                  <div className="mt-3 space-y-3">
                    {rawSummary.matched_samples.map((sample: any) => (
                      <div key={sample.file_id} className="rounded-xl border border-blue-100 bg-white/80 px-4 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-black text-slate-900">{sample.filename}</p>
                          <span className="rounded-full bg-blue-100 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-blue-700">
                            {sample.domain_hint || 'sem domínio'}
                          </span>
                        </div>
                        <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 text-xs text-slate-600">
                          <div>
                            <p className="font-black uppercase tracking-widest text-[10px] text-slate-400">Sistema</p>
                            <p className="mt-1 font-semibold text-slate-700">
                              {sample.system ? `${sample.system.label} (${sample.system.score})` : 'Nenhum'}
                            </p>
                          </div>
                          <div>
                            <p className="font-black uppercase tracking-widest text-[10px] text-slate-400">Ação</p>
                            <p className="mt-1 font-semibold text-slate-700">
                              {sample.task ? `${sample.task.label} (${sample.task.score})` : 'Nenhuma'}
                            </p>
                          </div>
                          <div>
                            <p className="font-black uppercase tracking-widest text-[10px] text-slate-400">POP</p>
                            <p className="mt-1 font-semibold text-slate-700">
                              {sample.pop ? `${sample.pop.label} (${sample.pop.score})` : 'Nenhum'}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white border border-slate-200 rounded-2xl p-5">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Eventos POP</p>
                <p className="text-3xl font-black text-slate-900">{totalPopEvents}</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">eventos operacionais</p>
              </div>
              <div className="bg-white border border-emerald-200 rounded-2xl p-5">
                <p className="text-[10px] font-black text-emerald-500 uppercase tracking-widest mb-1">Runs criados</p>
                <p className="text-3xl font-black text-slate-900">{popRunsCreated}</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">instâncias de POP</p>
              </div>
              <div className="bg-white border border-blue-200 rounded-2xl p-5">
                <p className="text-[10px] font-black text-blue-500 uppercase tracking-widest mb-1">Mudanças de status</p>
                <p className="text-3xl font-black text-slate-900">{popStatusChanged}</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">transições de execução</p>
              </div>
              <div className="bg-white border border-amber-200 rounded-2xl p-5">
                <p className="text-[10px] font-black text-amber-500 uppercase tracking-widest mb-1">Aprendizados</p>
                <p className="text-3xl font-black text-slate-900">{popLearned}</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">correções registradas</p>
              </div>
            </section>

            {/* ── Breakdown ────────────────────────────────────────── */}
            <section className="bg-white border border-slate-200 rounded-2xl p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Uso de Contexto Dinâmico</h3>
                  <p className="text-sm text-slate-500 mt-2 font-medium">
                    Registra quando o copiloto usou contexto em camadas e POPs no fluxo assistido.
                  </p>
                </div>
                <div className="rounded-xl bg-blue-50 border border-blue-100 px-4 py-3 text-right">
                  <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Eventos</p>
                  <p className="text-xl font-black text-slate-900 mt-1">{totalContextUsageEvents}</p>
                </div>
              </div>
              {contextUsageEvents.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {contextUsageEvents.slice(0, 8).map(event => (
                    <div key={event.id} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-black text-slate-900">{event.context_label || event.context_id || 'Contexto sem rótulo'}</p>
                        <span className="text-[10px] font-black uppercase tracking-widest text-blue-700 bg-blue-100 rounded-full px-2.5 py-1">
                          {event.usage_kind === 'task_copilot' ? 'Copiloto de ação' : 'Copiloto de sistema'}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                        <span>L0 {event.layers?.L0 ?? 0}</span>
                        <span>L1 {event.layers?.L1 ?? 0}</span>
                        <span>L2 {event.layers?.L2 ?? 0}</span>
                        <span>L3 {event.layers?.L3 ?? 0}</span>
                        <span>Total {event.total_entries ?? 0}</span>
                      </div>
                      {(event.suggested_pop_id || event.pop_run_id) && (
                        <div className="mt-2 text-[11px] font-semibold text-slate-600">
                          {event.suggested_pop_id && <span>POP {event.suggested_pop_id}</span>}
                          {event.suggested_pop_id && event.pop_run_id && <span> · </span>}
                          {event.pop_run_id && <span>Run {event.pop_run_id}</span>}
                        </div>
                      )}
                      <p className="mt-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">
                        {event.ts ? formatDate(event.ts) : 'sem data'}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border-2 border-dashed border-slate-200 px-4 py-8 text-center">
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Sem eventos ainda</p>
                </div>
              )}
            </section>

            <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Approval mode */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5">
                <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Por modo de aprovação</h3>
                <div className="space-y-3">
                  {(['automatic', 'confirm', 'required'] as ApprovalMode[]).map(mode => (
                    <div key={mode} className="flex items-center justify-between">
                      <span className={`text-[10px] font-black uppercase tracking-widest border rounded-full px-2 py-0.5 ${APPROVAL_COLORS[mode]}`}>
                        {APPROVAL_LABELS[mode]}
                      </span>
                      <span className="text-sm font-black text-slate-900">{byApproval[mode] ?? 0}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Risk level */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5">
                <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Por nível de risco</h3>
                <div className="space-y-3">
                  {(['low', 'medium', 'high'] as RiskLevel[]).map(risk => (
                    <div key={risk} className="flex items-center justify-between">
                      <span className={`text-[10px] font-black uppercase tracking-widest ${RISK_COLORS[risk]}`}>
                        {RISK_LABELS[risk]}
                      </span>
                      <span className="text-sm font-black text-slate-900">{byRisk[risk] ?? 0}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Route */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5">
                <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Por rota</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-black uppercase tracking-widest text-blue-600">Direta</span>
                    <span className="text-sm font-black text-slate-900">{byRoute['deterministic'] ?? 0}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-black uppercase tracking-widest text-violet-600">Orquestrada</span>
                    <span className="text-sm font-black text-slate-900">{byRoute['orchestrated'] ?? 0}</span>
                  </div>
                </div>
              </div>
            </section>

            {/* ── Recent events list ───────────────────────────────── */}
            {events.length > 0 && (
              <section>
                <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 border-l-4 border-slate-900 pl-4">
                  Eventos Recentes
                </h3>
                <div className="space-y-2">
                  {events.slice(0, 50).map(event => (
                    <div
                      key={event.id}
                      className="bg-white border border-slate-100 rounded-2xl px-5 py-4 flex items-center gap-4"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 border border-slate-200 rounded-full px-2 py-0.5">
                            {CONTEXT_KIND_LABELS[event.context_kind] ?? event.context_kind}
                          </span>
                          <span className="text-sm font-bold text-slate-900 truncate">
                            {event.context_label ?? event.context_id ?? '—'}
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-400 font-medium mt-1">
                          clareza {event.clarity_score?.toFixed(2)} · contexto {event.context_score?.toFixed(2)} · impacto {event.impact_score?.toFixed(2)}
                        </p>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        {event.session_released && (
                          <span className="text-[9px] font-black uppercase tracking-widest text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
                            Liberado
                          </span>
                        )}
                        <span className={`text-[9px] font-black uppercase tracking-widest border rounded-full px-2 py-0.5 ${APPROVAL_COLORS[event.approval_mode]}`}>
                          {APPROVAL_LABELS[event.approval_mode]}
                        </span>
                        <span className={`text-[9px] font-black uppercase tracking-widest ${RISK_COLORS[event.risk_level]}`}>
                          {RISK_LABELS[event.risk_level]}
                        </span>
                        <span className="text-[9px] text-slate-400 font-medium">
                          {event.ts ? formatDate(event.ts) : '—'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {popEvents.length > 0 && (
              <section>
                <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 border-l-4 border-emerald-600 pl-4">
                  Eventos Recentes de POP
                </h3>
                <div className="space-y-2">
                  {popEvents.slice(0, 50).map(event => (
                    <div
                      key={event.id}
                      className="bg-white border border-slate-100 rounded-2xl px-5 py-4 flex items-center gap-4"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[9px] font-black uppercase tracking-widest text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
                            {event.event_type}
                          </span>
                          <span className="text-sm font-bold text-slate-900 truncate">
                            {event.context_kind ?? 'pop'} · {event.context_id ?? event.pop_id}
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-400 font-medium mt-1">
                          {event.from_status && event.to_status
                            ? `${event.from_status} → ${event.to_status}`
                            : event.step_id
                              ? `step ${event.step_id} · ${event.step_status}`
                              : event.learning_type
                                ? `learning ${event.learning_type}`
                                : `pop ${event.pop_id}`}
                        </p>
                      </div>
                      <div className="shrink-0 text-[9px] text-slate-400 font-medium">
                        {event.ts ? formatDate(event.ts) : '—'}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {events.length === 0 && (
              <div className="bg-white border border-slate-200 rounded-2xl p-10 text-center">
                <p className="text-sm font-bold text-slate-400">Nenhum evento registrado ainda.</p>
                <p className="text-xs text-slate-300 mt-1">Os eventos aparecem aqui quando ações assistidas são avaliadas.</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
