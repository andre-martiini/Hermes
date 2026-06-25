import React, { useEffect, useMemo, useState } from 'react';
import { addDoc, collection, deleteDoc, doc, onSnapshot, query, Timestamp, updateDoc, where } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from '../../firebase';
import { EstrategiaIndicadorSucesso, EstrategiaPessoal, EstrategiaPilar, EstrategiaStatus, EstrategiaTipoMeta } from '../../types';

type StrategyIndicatorDraft = EstrategiaIndicadorSucesso;

type StrategyDraft = Omit<EstrategiaPessoal, 'id' | 'userId' | 'timestamp' | 'metricaAlvo' | 'indicadoresSucesso'> & {
  metricaAlvo?: {
    valorInicial?: number | string;
    valorAtual: number | string;
    valorObjetivo: number | string;
    unidade: string;
  };
  indicadoresSucesso?: StrategyIndicatorDraft[];
};

interface StrategyDashboardViewProps {
  userId: string;
  isDark?: boolean;
  showToast?: (msg: string, type?: 'success' | 'error' | 'info' | 'warning') => void;
}

const PILLARS: Array<{ id: EstrategiaPilar; label: string; accent: string }> = [
  { id: 'carreira', label: 'Carreira', accent: 'bg-blue-600' },
  { id: 'financas', label: 'Finanças', accent: 'bg-emerald-600' },
  { id: 'saude', label: 'Saúde', accent: 'bg-rose-600' },
  { id: 'intelectual', label: 'Intelectual', accent: 'bg-amber-500' },
  { id: 'estilo_vida', label: 'Estilo de vida', accent: 'bg-cyan-600' },
];

const emptyDraft: StrategyDraft = {
  pilar: 'carreira',
  objetivoMacro: '',
  tipoMeta: 'relativa_qualitativa',
  indicadoresSucesso: [{ id: 'draft-indicador-1', descricao: '', concluido: false }],
  diretrizesDerivadas: [''],
  status: 'ativo',
};

const normalizeList = (items?: string[]) => (items || []).map(item => item.trim()).filter(Boolean);
const parseMetricNumber = (value: number | string | undefined) => Number(String(value ?? 0).replace(',', '.')) || 0;
const createIndicatorId = () => `indicador-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const createRecordId = () => `registro-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const getPersistedIndicatorId = (item: string | EstrategiaIndicadorSucesso, index: number) => {
  if (typeof item !== 'string' && item.id) return item.id;
  return `indicador-legado-${index}`;
};

const toIndicatorDrafts = (items?: Array<string | EstrategiaIndicadorSucesso>): StrategyIndicatorDraft[] => {
  const converted = (items || []).map((item, index) => {
    if (typeof item === 'string') {
      return { id: getPersistedIndicatorId(item, index), descricao: item, concluido: false };
    }
    return {
      id: getPersistedIndicatorId(item, index),
      descricao: item.descricao || '',
      concluido: Boolean(item.concluido),
      dataConclusao: item.dataConclusao,
      evidencia: item.evidencia || '',
      registros: item.registros || [],
    };
  }).filter(item => item.descricao.trim() || item.evidencia?.trim());
  return converted.length ? converted : [{ id: createIndicatorId(), descricao: '', concluido: false }];
};

const normalizeIndicators = (items?: StrategyIndicatorDraft[]): EstrategiaIndicadorSucesso[] =>
  (items || [])
    .map(item => {
      const normalized: EstrategiaIndicadorSucesso = {
        id: item.id || createIndicatorId(),
        descricao: item.descricao.trim(),
        concluido: Boolean(item.concluido),
        registros: item.registros || [],
      };
      if (normalized.concluido) {
        normalized.dataConclusao = item.dataConclusao || new Date().toISOString();
      }
      const evidencia = item.evidencia?.trim();
      if (evidencia) {
        normalized.evidencia = evidencia;
      }
      return normalized;
    })
    .filter(item => item.descricao);

const computeProgress = (item: EstrategiaPessoal) => {
  const metric = item.metricaAlvo;
  if (!metric || !Number.isFinite(metric.valorAtual) || !Number.isFinite(metric.valorObjetivo)) {
    return null;
  }
  const current = metric.valorAtual;
  const target = metric.valorObjetivo;
  const initial = Number.isFinite(metric.valorInicial) ? Number(metric.valorInicial) : target < current ? current : 0;
  if (initial === target) return current === target ? 100 : 0;
  const rawProgress = target < initial
    ? ((initial - current) / (initial - target)) * 100
    : ((current - initial) / (target - initial)) * 100;
  return Math.max(0, Math.min(100, Math.round(rawProgress)));
};

const strategyToDraft = (item: EstrategiaPessoal): StrategyDraft => ({
  pilar: item.pilar,
  objetivoMacro: item.objetivoMacro,
  tipoMeta: item.tipoMeta,
  metricaAlvo: item.metricaAlvo,
  indicadoresSucesso: toIndicatorDrafts(item.indicadoresSucesso),
  diretrizesDerivadas: item.diretrizesDerivadas?.length ? item.diretrizesDerivadas : [''],
  status: item.status,
});

const buildLocalStrategyFallback = (text: string): StrategyDraft[] => {
  const lowerText = text.toLowerCase();
  const pilar: EstrategiaPilar =
    /dinheiro|renda|receita|patrim|invest|finan|brl|real|gasto|reserva/.test(lowerText) ? 'financas' :
    /peso|saude|saúde|sono|treino|exerc|dieta|corpo|energia/.test(lowerText) ? 'saude' :
    /carreira|trabalho|profiss|cliente|servi|negocio|negócio|cargo/.test(lowerText) ? 'carreira' :
    /estudo|livro|aprend|pesquis|artigo|intelect|curso/.test(lowerText) ? 'intelectual' :
    /vida|casa|familia|família|rotina|viagem|lazer/.test(lowerText) ? 'estilo_vida' :
    'intelectual';

  const numericMatch = text.match(/(\d+(?:[.,]\d+)?)\s*(kg|brl|r\$|reais|%|por cento|horas?|h)\b/i);
  const tipoMeta: EstrategiaTipoMeta = numericMatch ? 'absoluta' : 'relativa_qualitativa';
  const unidade = numericMatch?.[2]?.replace(/^r\$$/i, 'BRL') || '';
  const targetValue = numericMatch ? Number(numericMatch[1].replace(',', '.')) : 0;

  return [{
    pilar,
    objetivoMacro: text.trim(),
    tipoMeta,
    metricaAlvo: tipoMeta === 'absoluta' ? {
      valorInicial: 0,
      valorAtual: 0,
      valorObjetivo: targetValue,
      unidade,
    } : undefined,
    indicadoresSucesso: toIndicatorDrafts([
      'Definir evidências observáveis de progresso',
      'Revisar o objetivo em ciclos mensais',
      'Registrar marcos concretos de avanço',
    ]),
    diretrizesDerivadas: [
      'Use esta intenção apenas quando o usuário pedir alinhamento estratégico.',
      'Evite transformar esta diretriz em pressão operacional diária.',
      'Priorize respostas que preservem foco e consistência de longo prazo.',
    ],
    status: 'ativo',
  }];
};

const getInputClass = (isDark: boolean) =>
  `w-full border px-3 py-2 text-sm font-bold outline-none transition-all focus:ring-1 ${
    isDark ? 'border-slate-700 bg-slate-950 text-slate-100 focus:ring-slate-500' : 'border-slate-200 bg-white text-slate-900 focus:ring-slate-900'
  }`;

export const StrategyDashboardView: React.FC<StrategyDashboardViewProps> = ({ userId, isDark = false, showToast }) => {
  const [items, setItems] = useState<EstrategiaPessoal[]>([]);
  const [intention, setIntention] = useState('');
  const [drafts, setDrafts] = useState<StrategyDraft[]>([]);
  const [manualDraft, setManualDraft] = useState<StrategyDraft>(emptyDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedPillar, setSelectedPillar] = useState<EstrategiaPilar | 'todos'>('todos');
  const [isRefining, setIsRefining] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editingDraft, setEditingDraft] = useState<StrategyDraft | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [metricInputs, setMetricInputs] = useState<Record<string, string>>({});
  const [indicatorNotes, setIndicatorNotes] = useState<Record<string, string>>({});
  const [expandedIndicators, setExpandedIndicators] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!userId) return;
    const q = query(collection(db, 'estrategia_pessoal'), where('userId', '==', userId));
    return onSnapshot(q, (snap) => {
      const next = snap.docs.map(d => ({ id: d.id, ...d.data() } as EstrategiaPessoal));
      next.sort((a, b) => {
        const aTime = a.timestamp?.toMillis?.() || 0;
        const bTime = b.timestamp?.toMillis?.() || 0;
        return bTime - aTime;
      });
      setItems(next);
    });
  }, [userId]);

  const stats = useMemo(() => {
    const active = items.filter(item => item.status === 'ativo');
    const byPillar = PILLARS.map(pillar => ({
      ...pillar,
      count: active.filter(item => item.pilar === pillar.id).length,
    }));
    const numeric = active.map(computeProgress).filter((value): value is number => value !== null);
    const avgProgress = numeric.length ? Math.round(numeric.reduce((sum, value) => sum + value, 0) / numeric.length) : 0;
    return { activeCount: active.length, qualitativeCount: active.filter(item => item.tipoMeta === 'relativa_qualitativa').length, byPillar, avgProgress };
  }, [items]);

  const filteredItems = selectedPillar === 'todos' ? items : items.filter(item => item.pilar === selectedPillar);
  const panelClass = isDark ? 'bg-slate-950 text-slate-100 border-slate-800' : 'bg-white text-slate-900 border-slate-200';
  const softPanelClass = isDark ? 'bg-slate-900/60 border-slate-800' : 'bg-slate-50 border-slate-200';
  const mutedClass = isDark ? 'text-slate-400' : 'text-slate-500';
  const inputClass = getInputClass(isDark);

  const updateDraftList = (index: number, field: 'diretrizesDerivadas', valueIndex: number, value: string) => {
    setDrafts(prev => prev.map((draft, idx) => {
      if (idx !== index) return draft;
      const nextList = [...(draft[field] || [])];
      nextList[valueIndex] = value;
      return { ...draft, [field]: nextList };
    }));
  };

  const updateDraftIndicator = (index: number, valueIndex: number, updates: Partial<StrategyIndicatorDraft>) => {
    setDrafts(prev => prev.map((draft, idx) => {
      if (idx !== index) return draft;
      const nextList = [...(draft.indicadoresSucesso || [])];
      nextList[valueIndex] = { ...(nextList[valueIndex] || { id: createIndicatorId(), descricao: '', concluido: false }), ...updates };
      return { ...draft, indicadoresSucesso: nextList };
    }));
  };

  const updateManualList = (field: 'diretrizesDerivadas', valueIndex: number, value: string) => {
    setManualDraft(prev => {
      const nextList = [...(prev[field] || [])];
      nextList[valueIndex] = value;
      return { ...prev, [field]: nextList };
    });
  };

  const updateManualIndicator = (valueIndex: number, updates: Partial<StrategyIndicatorDraft>) => {
    setManualDraft(prev => {
      const nextList = [...(prev.indicadoresSucesso || [])];
      nextList[valueIndex] = { ...(nextList[valueIndex] || { id: createIndicatorId(), descricao: '', concluido: false }), ...updates };
      return { ...prev, indicadoresSucesso: nextList };
    });
  };

  const refineIntention = async () => {
    if (!intention.trim()) return;
    setIsRefining(true);
    try {
      const callable = httpsCallable(functions, 'refinarDiretrizesEstrategicas', { timeout: 120000 });
      const result = await callable({ intencao: intention.trim(), userId });
      const data = result.data as any;
      const proposals = Array.isArray(data?.propostas) ? data.propostas : [];
      setDrafts(proposals.map((proposal: any) => ({
        pilar: PILLARS.some(p => p.id === proposal.pilar) ? proposal.pilar : 'carreira',
        objetivoMacro: String(proposal.objetivoMacro || ''),
        tipoMeta: proposal.tipoMeta === 'absoluta' ? 'absoluta' : 'relativa_qualitativa',
        metricaAlvo: proposal.tipoMeta === 'absoluta' && proposal.metricaAlvo ? {
          valorInicial: Number(proposal.metricaAlvo.valorInicial ?? proposal.metricaAlvo.valorAtual ?? 0),
          valorAtual: Number(proposal.metricaAlvo.valorAtual || 0),
          valorObjetivo: Number(proposal.metricaAlvo.valorObjetivo || 0),
          unidade: String(proposal.metricaAlvo.unidade || ''),
        } : undefined,
        indicadoresSucesso: toIndicatorDrafts(normalizeList(proposal.indicadoresSucesso)),
        diretrizesDerivadas: normalizeList(proposal.diretrizesDerivadas).length ? normalizeList(proposal.diretrizesDerivadas) : [''],
        status: 'ativo',
      })));
      showToast?.('Proposta estratégica refinada.', 'success');
    } catch (error: any) {
      const message = String(error?.message || error?.code || '');
      if (/cors|failed to fetch|network|internal/i.test(message)) {
        setDrafts(buildLocalStrategyFallback(intention.trim()));
        showToast?.('Refinamento local usado. Publique a Cloud Function para ativar o refinamento por IA.', 'warning');
      } else {
        showToast?.(error?.message || 'Erro ao refinar estratégia.', 'error');
      }
    } finally {
      setIsRefining(false);
    }
  };

  const persistDraft = async (draft: StrategyDraft, id?: string) => {
    const valorAtual = parseMetricNumber(draft.metricaAlvo?.valorAtual);
    const valorObjetivo = parseMetricNumber(draft.metricaAlvo?.valorObjetivo);
    const valorInicial = draft.metricaAlvo?.valorInicial !== undefined
      ? parseMetricNumber(draft.metricaAlvo.valorInicial)
      : valorObjetivo < valorAtual ? valorAtual : 0;
    const payloadBase: Omit<EstrategiaPessoal, 'id' | 'metricaAlvo'> = {
      userId,
      pilar: draft.pilar,
      objetivoMacro: draft.objetivoMacro.trim(),
      tipoMeta: draft.tipoMeta,
      indicadoresSucesso: normalizeIndicators(draft.indicadoresSucesso),
      diretrizesDerivadas: normalizeList(draft.diretrizesDerivadas),
      status: draft.status,
      timestamp: Timestamp.now(),
    };
    const payload: Omit<EstrategiaPessoal, 'id'> = draft.tipoMeta === 'absoluta'
      ? {
        ...payloadBase,
        metricaAlvo: {
          valorInicial,
          valorAtual,
          valorObjetivo,
          unidade: String(draft.metricaAlvo?.unidade || '').trim(),
        },
      }
      : payloadBase;
    if (!payload.objetivoMacro) throw new Error('Informe um objetivo macro.');
    if (!payload.diretrizesDerivadas.length) throw new Error('Informe ao menos uma diretriz derivada.');
    if (id) {
      await updateDoc(doc(db, 'estrategia_pessoal', id), payload as any);
    } else {
      await addDoc(collection(db, 'estrategia_pessoal'), payload);
    }
  };

  const saveDraft = async (draft: StrategyDraft, index?: number, id?: string) => {
    setIsSaving(true);
    try {
      await persistDraft(draft, id);
      if (typeof index === 'number') setDrafts(prev => prev.filter((_, idx) => idx !== index));
      if (!id) setIntention('');
      setEditingId(null);
      setEditingDraft(null);
      if (!id && (index === undefined || drafts.length <= 1)) setIsCreateModalOpen(false);
      showToast?.('Estratégia salva.', 'success');
    } catch (error: any) {
      showToast?.(error?.message || 'Erro ao salvar estratégia.', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  const registerMetricValue = async (item: EstrategiaPessoal) => {
    if (!item.id || !item.metricaAlvo) return;
    const rawValue = metricInputs[item.id];
    const value = parseMetricNumber(rawValue);
    if (!Number.isFinite(value) || rawValue === undefined || rawValue.trim() === '') {
      showToast?.('Informe um valor numérico para registrar a métrica.', 'error');
      return;
    }
    const currentMetric = item.metricaAlvo;
    const valorInicial = Number.isFinite(currentMetric.valorInicial)
      ? Number(currentMetric.valorInicial)
      : currentMetric.valorObjetivo < currentMetric.valorAtual ? currentMetric.valorAtual : 0;
    const record = {
      id: createRecordId(),
      data: new Date().toISOString(),
      valor: value,
      nota: `Registro manual da métrica principal: ${value} ${currentMetric.unidade || ''}`.trim(),
    };
    try {
      await updateDoc(doc(db, 'estrategia_pessoal', item.id), {
        metricaAlvo: {
          valorInicial,
          valorAtual: value,
          valorObjetivo: currentMetric.valorObjetivo,
          unidade: currentMetric.unidade || '',
        },
        historicoMetrica: [...(item.historicoMetrica || []), record],
      } as any);
      setMetricInputs(prev => ({ ...prev, [item.id!]: '' }));
      showToast?.('Métrica principal registrada.', 'success');
    } catch (error: any) {
      showToast?.(error?.message || 'Erro ao registrar métrica.', 'error');
    }
  };
  const registerIndicatorNote = async (item: EstrategiaPessoal, indicatorIndex: number) => {
    if (!item.id) return;
    const indicators = toIndicatorDrafts(item.indicadoresSucesso);
    const current = indicators[indicatorIndex];
    if (!current) return;
    const noteKey = `${item.id}:${current.id}`;
    const note = (indicatorNotes[noteKey] || '').trim();
    if (!note) {
      showToast?.('Escreva um registro antes de salvar o marco.', 'error');
      return;
    }
    const record = {
      id: createRecordId(),
      data: new Date().toISOString(),
      nota: note,
    };
    indicators[indicatorIndex] = {
      ...current,
      evidencia: note,
      registros: [...(current.registros || []), record],
    };
    try {
      await updateDoc(doc(db, 'estrategia_pessoal', item.id), {
        indicadoresSucesso: normalizeIndicators(indicators),
      });
      setIndicatorNotes(prev => ({ ...prev, [noteKey]: '' }));
      showToast?.('Registro do marco salvo.', 'success');
    } catch (error: any) {
      showToast?.(error?.message || 'Erro ao registrar marco.', 'error');
    }
  };
  const renderDraftEditor = ({
    draft,
    index,
    onChange,
    onListChange,
    onIndicatorChange,
    onSave,
    onCancel,
  }: {
    draft: StrategyDraft;
    index?: number;
    onChange: (updates: Partial<StrategyDraft>) => void;
    onListChange: (field: 'diretrizesDerivadas', valueIndex: number, value: string) => void;
    onIndicatorChange: (valueIndex: number, updates: Partial<StrategyIndicatorDraft>) => void;
    onSave: () => void;
    onCancel?: () => void;
  }) => (
    <div className={`border p-4 ${panelClass}`}>
      <div className="grid gap-3 md:grid-cols-3">
        <label className="text-[10px] font-black uppercase tracking-widest">
          Pilar
          <select className={`${inputClass} mt-1`} value={draft.pilar} onChange={e => onChange({ pilar: e.target.value as EstrategiaPilar })}>
            {PILLARS.map(pillar => <option key={pillar.id} value={pillar.id}>{pillar.label}</option>)}
          </select>
        </label>
        <label className="text-[10px] font-black uppercase tracking-widest">
          Tipo
          <select className={`${inputClass} mt-1`} value={draft.tipoMeta} onChange={e => onChange({ tipoMeta: e.target.value as EstrategiaTipoMeta })}>
            <option value="relativa_qualitativa">Qualitativa</option>
            <option value="absoluta">Absoluta</option>
          </select>
        </label>
        <label className="text-[10px] font-black uppercase tracking-widest">
          Status
          <select className={`${inputClass} mt-1`} value={draft.status} onChange={e => onChange({ status: e.target.value as EstrategiaStatus })}>
            <option value="ativo">Ativo</option>
            <option value="revisar">Revisar</option>
            <option value="concluido">Concluído</option>
          </select>
        </label>
      </div>
      <label className="mt-3 block text-[10px] font-black uppercase tracking-widest">
        Objetivo macro
        <textarea className={`${inputClass} mt-1 min-h-[76px] resize-y`} value={draft.objetivoMacro} onChange={e => onChange({ objetivoMacro: e.target.value })} />
      </label>
      {draft.tipoMeta === 'absoluta' && (
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <label className="text-[10px] font-black uppercase tracking-widest">Atual<input className={`${inputClass} mt-1`} type="text" inputMode="decimal" value={draft.metricaAlvo?.valorAtual ?? ''} onChange={e => onChange({ metricaAlvo: { valorInicial: draft.metricaAlvo?.valorInicial, valorAtual: e.target.value, valorObjetivo: draft.metricaAlvo?.valorObjetivo ?? '', unidade: draft.metricaAlvo?.unidade || '' } })} /></label>
          <label className="text-[10px] font-black uppercase tracking-widest">Objetivo<input className={`${inputClass} mt-1`} type="text" inputMode="decimal" value={draft.metricaAlvo?.valorObjetivo ?? ''} onChange={e => onChange({ metricaAlvo: { valorInicial: draft.metricaAlvo?.valorInicial, valorAtual: draft.metricaAlvo?.valorAtual ?? '', valorObjetivo: e.target.value, unidade: draft.metricaAlvo?.unidade || '' } })} /></label>
          <label className="text-[10px] font-black uppercase tracking-widest">Unidade<input className={`${inputClass} mt-1`} value={draft.metricaAlvo?.unidade || ''} onChange={e => onChange({ metricaAlvo: { valorInicial: draft.metricaAlvo?.valorInicial, valorAtual: draft.metricaAlvo?.valorAtual ?? '', valorObjetivo: draft.metricaAlvo?.valorObjetivo ?? '', unidade: e.target.value } })} /></label>
        </div>
      )}
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div>
          <p className="mb-2 text-[10px] font-black uppercase tracking-widest">Indicadores</p>
          {(draft.indicadoresSucesso || []).map((value, valueIndex) => (
            <input key={value.id || `${index ?? 'manual'}-indicador-${valueIndex}`} className={`${inputClass} mb-2`} value={value.descricao} onChange={e => onIndicatorChange(valueIndex, { descricao: e.target.value })} />
          ))}
          <button className={`text-[10px] font-black uppercase tracking-widest ${mutedClass}`} onClick={() => onChange({ indicadoresSucesso: [...(draft.indicadoresSucesso || []), { id: createIndicatorId(), descricao: '', concluido: false }] })}>Adicionar indicador</button>
        </div>
        <div>
          <p className="mb-2 text-[10px] font-black uppercase tracking-widest">Diretrizes para IA</p>
          {(draft.diretrizesDerivadas || ['']).map((value, valueIndex) => (
            <input key={`${index ?? 'manual'}-diretriz-${valueIndex}`} className={`${inputClass} mb-2`} value={value} onChange={e => onListChange('diretrizesDerivadas', valueIndex, e.target.value)} />
          ))}
          <button className={`text-[10px] font-black uppercase tracking-widest ${mutedClass}`} onClick={() => onChange({ diretrizesDerivadas: [...(draft.diretrizesDerivadas || []), ''] })}>Adicionar diretriz</button>
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        {onCancel && <button onClick={onCancel} className={`px-4 py-2 text-[10px] font-black uppercase tracking-widest ${softPanelClass}`}>Cancelar</button>}
        <button disabled={isSaving} onClick={onSave} className="bg-slate-900 px-5 py-2 text-[10px] font-black uppercase tracking-widest text-white disabled:opacity-50">
          {isSaving ? 'Salvando...' : 'Salvar'}
        </button>
      </div>
    </div>
  );

  return (
    <div className={`min-h-screen px-4 pb-24 md:px-8 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="flex flex-col gap-2">
        <p className={`text-[10px] font-black uppercase tracking-[0.22em] ${mutedClass}`}>Governança pessoal</p>
        <h2 className="text-2xl font-black tracking-tight md:text-3xl">Estratégia pessoal</h2>
        </div>
        <button
          onClick={() => {
            setIsCreateModalOpen(true);
            setDrafts([]);
            setIntention('');
            setManualDraft(emptyDraft);
          }}
          className="bg-blue-600 px-5 py-3 text-[10px] font-black uppercase tracking-widest text-white transition-all hover:bg-blue-700"
        >
          Novo objetivo
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <div className={`border p-4 ${panelClass}`}><p className={mutedClass}>Ativos</p><strong className="text-3xl">{stats.activeCount}</strong></div>
        <div className={`border p-4 ${panelClass}`}><p className={mutedClass}>Qualitativos</p><strong className="text-3xl">{stats.qualitativeCount}</strong></div>
        <div className={`border p-4 ${panelClass}`}><p className={mutedClass}>Progresso médio</p><strong className="text-3xl">{stats.avgProgress}%</strong></div>
        <div className={`border p-4 ${panelClass}`}><p className={mutedClass}>Pilares ativos</p><strong className="text-3xl">{stats.byPillar.filter(p => p.count > 0).length}</strong></div>
      </div>

      {isCreateModalOpen && (
        <div className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-slate-950/60 px-4 py-6 backdrop-blur-sm">
          <div className={`w-full max-w-5xl border shadow-2xl ${panelClass}`}>
            <div className={`flex items-center justify-between border-b p-4 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <div>
                <p className={`text-[10px] font-black uppercase tracking-[0.22em] ${mutedClass}`}>Estratégia pessoal</p>
                <h3 className="text-xl font-black tracking-tight">Novo objetivo</h3>
              </div>
              <button
                onClick={() => {
                  setIsCreateModalOpen(false);
                  setDrafts([]);
                  setIntention('');
                }}
                className={`px-3 py-2 text-[10px] font-black uppercase tracking-widest ${softPanelClass}`}
              >
                Fechar
              </button>
            </div>
            <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,420px)_1fr]">
              <section className={`border p-4 ${softPanelClass}`}>
                <h3 className="text-sm font-black uppercase tracking-widest">Entrada orgânica</h3>
                <textarea className={`${inputClass} mt-3 min-h-[140px] resize-y`} value={intention} onChange={e => setIntention(e.target.value)} placeholder="Descreva uma intenção estratégica em texto livre." />
                <button disabled={isRefining || !intention.trim()} onClick={refineIntention} className="mt-3 w-full bg-blue-600 px-5 py-3 text-[10px] font-black uppercase tracking-widest text-white disabled:opacity-50">
                  {isRefining ? 'Refinando...' : 'Refinar com Hermes'}
                </button>

                <div className={`mt-5 border-t pt-5 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                  <h3 className="mb-3 text-sm font-black uppercase tracking-widest">Cadastro manual</h3>
                  {renderDraftEditor({
                    draft: manualDraft,
                    onChange: updates => setManualDraft(prev => ({ ...prev, ...updates })),
                    onListChange: updateManualList,
                    onIndicatorChange: updateManualIndicator,
                    onSave: () => saveDraft(manualDraft).then(() => setManualDraft(emptyDraft)),
                  })}
                </div>
              </section>

              <section className="space-y-3">
                <h3 className="text-sm font-black uppercase tracking-widest">Propostas para validação</h3>
                {drafts.length === 0 ? (
                  <div className={`border p-8 text-center ${softPanelClass}`}>
                    <p className={`text-xs font-black uppercase tracking-widest ${mutedClass}`}>As propostas refinadas aparecerão aqui.</p>
                  </div>
                ) : drafts.map((draft, index) => (
                  <React.Fragment key={`modal-draft-${index}`}>
                    {renderDraftEditor({
                      draft,
                      index,
                      onChange: updates => setDrafts(prev => prev.map((item, idx) => idx === index ? { ...item, ...updates } : item)),
                      onListChange: (field, valueIndex, value) => updateDraftList(index, field, valueIndex, value),
                      onIndicatorChange: (valueIndex, updates) => updateDraftIndicator(index, valueIndex, updates),
                      onSave: () => saveDraft(draft, index),
                      onCancel: () => setDrafts(prev => prev.filter((_, idx) => idx !== index)),
                    })}
                  </React.Fragment>
                ))}
              </section>
            </div>
          </div>
        </div>
      )}

      <div className="mt-6">
        <section className={`hidden border p-4 ${panelClass}`}>
          <h3 className="text-sm font-black uppercase tracking-widest">Entrada orgânica</h3>
          <textarea className={`${inputClass} mt-3 min-h-[140px] resize-y`} value={intention} onChange={e => setIntention(e.target.value)} placeholder="Descreva uma intenção estratégica em texto livre." />
          <button disabled={isRefining || !intention.trim()} onClick={refineIntention} className="mt-3 w-full bg-blue-600 px-5 py-3 text-[10px] font-black uppercase tracking-widest text-white disabled:opacity-50">
            {isRefining ? 'Refinando...' : 'Refinar com Hermes'}
          </button>

          <div className={`mt-5 border-t pt-5 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
            <h3 className="mb-3 text-sm font-black uppercase tracking-widest">Cadastro manual</h3>
            {renderDraftEditor({
              draft: manualDraft,
              onChange: updates => setManualDraft(prev => ({ ...prev, ...updates })),
              onListChange: updateManualList,
              onIndicatorChange: updateManualIndicator,
              onSave: () => saveDraft(manualDraft).then(() => setManualDraft(emptyDraft)),
            })}
          </div>
        </section>

        <section className="space-y-4">
          {false && drafts.length > 0 && (
            <div className={`border p-4 ${softPanelClass}`}>
              <h3 className="mb-3 text-sm font-black uppercase tracking-widest">Propostas para validação</h3>
              <div className="space-y-3">
                {drafts.map((draft, index) => (
                  <React.Fragment key={`draft-${index}`}>
                    {renderDraftEditor({
                      draft,
                      index,
                      onChange: updates => setDrafts(prev => prev.map((item, idx) => idx === index ? { ...item, ...updates } : item)),
                      onListChange: (field, valueIndex, value) => updateDraftList(index, field, valueIndex, value),
                      onIndicatorChange: (valueIndex, updates) => updateDraftIndicator(index, valueIndex, updates),
                      onSave: () => saveDraft(draft, index),
                      onCancel: () => setDrafts(prev => prev.filter((_, idx) => idx !== index)),
                    })}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <button onClick={() => setSelectedPillar('todos')} className={`px-3 py-2 text-[10px] font-black uppercase tracking-widest ${selectedPillar === 'todos' ? 'bg-slate-900 text-white' : softPanelClass}`}>Todos</button>
            {PILLARS.map(pillar => (
              <button key={pillar.id} onClick={() => setSelectedPillar(pillar.id)} className={`px-3 py-2 text-[10px] font-black uppercase tracking-widest ${selectedPillar === pillar.id ? 'bg-slate-900 text-white' : softPanelClass}`}>
                {pillar.label} ({stats.byPillar.find(p => p.id === pillar.id)?.count || 0})
              </button>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {filteredItems.map(item => {
              const pillar = PILLARS.find(p => p.id === item.pilar) || PILLARS[0];
              const progress = computeProgress(item);
              const indicators = toIndicatorDrafts(item.indicadoresSucesso).filter(indicator => indicator.descricao.trim());
              const indicatorPanelId = `strategy-indicators-${item.id || item.objetivoMacro}`;
              const areIndicatorsExpanded = Boolean(item.id && expandedIndicators[item.id]);
              const indicatorRecordCount = indicators.reduce((sum, indicator) => sum + (indicator.registros || []).length, 0);
              if (editingId === item.id && editingDraft) {
                return (
                  <React.Fragment key={item.id}>
                    {renderDraftEditor({
                      draft: editingDraft,
                      onChange: updates => setEditingDraft(prev => prev ? { ...prev, ...updates } : prev),
                      onListChange: (field, valueIndex, value) => {
                        setEditingDraft(prev => {
                          if (!prev) return prev;
                          const list = [...(prev[field] || [])];
                          list[valueIndex] = value;
                          return { ...prev, [field]: list };
                        });
                      },
                      onIndicatorChange: (valueIndex, updates) => {
                        setEditingDraft(prev => {
                          if (!prev) return prev;
                          const list = [...(prev.indicadoresSucesso || [])];
                          list[valueIndex] = { ...(list[valueIndex] || { id: createIndicatorId(), descricao: '', concluido: false }), ...updates };
                          return { ...prev, indicadoresSucesso: list };
                        });
                      },
                      onSave: () => saveDraft(editingDraft, undefined, item.id),
                      onCancel: () => {
                        setEditingId(null);
                        setEditingDraft(null);
                      },
                    })}
                  </React.Fragment>
                );
              }
              return (
                <article key={item.id} className={`border p-4 ${panelClass}`}>
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div>
                      <span className={`inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest ${mutedClass}`}>
                        <span className={`h-2 w-2 ${pillar.accent}`} />{pillar.label}
                      </span>
                      <h3 className="mt-2 text-base font-black leading-snug">{item.objetivoMacro}</h3>
                    </div>
                    <span className={`border px-2 py-1 text-[9px] font-black uppercase tracking-widest ${softPanelClass}`}>{item.status}</span>
                  </div>
                  {progress !== null && (
                    <div className={`mb-4 border p-3 ${softPanelClass}`}>
                      <p className={`mb-2 text-[10px] font-black uppercase tracking-widest ${mutedClass}`}>Métrica principal</p>
                      <div className="mb-1 flex justify-between text-[10px] font-black uppercase tracking-widest">
                        <span>{item.metricaAlvo?.valorAtual} / {item.metricaAlvo?.valorObjetivo} {item.metricaAlvo?.unidade}</span>
                        <span>{progress}%</span>
                      </div>
                      <div className={`h-2 ${isDark ? 'bg-slate-800' : 'bg-slate-100'}`}><div className="h-full bg-blue-600" style={{ width: `${progress}%` }} /></div>
                      <div className="mt-3 flex gap-2">
                        <input
                          className={`${inputClass} text-xs`}
                          type="text"
                          inputMode="decimal"
                          value={metricInputs[item.id || ''] ?? ''}
                          onChange={(event) => item.id && setMetricInputs(prev => ({ ...prev, [item.id!]: event.target.value }))}
                          placeholder={`Novo valor${item.metricaAlvo?.unidade ? ` em ${item.metricaAlvo.unidade}` : ''}`}
                        />
                        <button
                          onClick={() => registerMetricValue(item)}
                          className="shrink-0 bg-blue-600 px-3 py-2 text-[10px] font-black uppercase tracking-widest text-white"
                          title="Registrar métrica principal"
                        >
                          Registrar
                        </button>
                      </div>
                      {(item.historicoMetrica || []).length > 0 && (
                        <p className={`mt-2 text-[10px] font-bold ${mutedClass}`}>
                          Último registro: {(item.historicoMetrica || []).slice(-1)[0].valor} {item.metricaAlvo?.unidade} em {new Date((item.historicoMetrica || []).slice(-1)[0].data).toLocaleDateString('pt-BR')}
                        </p>
                      )}
                    </div>
                  )}
                  <div className="space-y-3">
                    <div>
                      <button
                        type="button"
                        onClick={() => item.id && setExpandedIndicators(prev => ({ ...prev, [item.id!]: !prev[item.id!] }))}
                        className={`flex w-full items-center justify-between border px-3 py-2 text-left transition-all ${softPanelClass}`}
                        aria-expanded={areIndicatorsExpanded}
                        aria-controls={indicatorPanelId}
                      >
                        <span>
                          <span className={`block text-[10px] font-black uppercase tracking-widest ${mutedClass}`}>Detalhes</span>
                          <span className="mt-0.5 block text-xs font-bold">
                            {indicators.length} indicador{indicators.length === 1 ? '' : 'es'} · {indicatorRecordCount} registro{indicatorRecordCount === 1 ? '' : 's'}
                          </span>
                        </span>
                        <svg className={`h-4 w-4 transition-transform ${areIndicatorsExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="m6 9 6 6 6-6" />
                        </svg>
                      </button>
                      {areIndicatorsExpanded && (
                        <div id={indicatorPanelId} className="mt-2 space-y-4">
                          <div className="space-y-2">
                            <p className={`text-[10px] font-black uppercase tracking-widest ${mutedClass}`}>Indicadores</p>
                            {indicators.length === 0 ? (
                              <p className={`text-xs font-bold ${mutedClass}`}>Nenhum marco registrado.</p>
                            ) : indicators.map((indicator, indicatorIndex) => (
                              <div key={indicator.id} className={`border p-2 ${softPanelClass}`}>
                                <div className="flex items-start justify-between gap-2">
                                  <span className="text-sm font-semibold">{indicator.descricao}</span>
                                  {(indicator.registros || []).length > 0 && (
                                    <span className="bg-emerald-600 px-2 py-1 text-[8px] font-black uppercase tracking-widest text-white">
                                      {(indicator.registros || []).length} registro{(indicator.registros || []).length === 1 ? '' : 's'}
                                    </span>
                                  )}
                                </div>
                                {(indicator.registros || []).slice(-2).map(record => (
                                  <p key={record.id} className={`mt-1 text-xs font-semibold ${mutedClass}`}>
                                    {new Date(record.data).toLocaleDateString('pt-BR')}: {record.nota}
                                  </p>
                                ))}
                                <div className="mt-2 flex gap-2">
                                  <input
                                    value={indicatorNotes[`${item.id}:${indicator.id}`] ?? ''}
                                    onChange={(event) => setIndicatorNotes(prev => ({ ...prev, [`${item.id}:${indicator.id}`]: event.target.value }))}
                                    className={`${inputClass} text-xs`}
                                    placeholder="Escreva o registro do marco"
                                  />
                                  <button
                                    onClick={() => registerIndicatorNote(item, indicatorIndex)}
                                    className="flex h-9 w-9 shrink-0 items-center justify-center bg-slate-900 text-white transition-all hover:bg-slate-700"
                                    title="Registrar marco"
                                    aria-label="Registrar marco"
                                  >
                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v14m7-7H5" />
                                    </svg>
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                          <div>
                            <p className={`text-[10px] font-black uppercase tracking-widest ${mutedClass}`}>Diretrizes passivas</p>
                            <ul className="mt-1 space-y-1 text-sm font-semibold">{item.diretrizesDerivadas.map(directive => <li key={directive}>- {directive}</li>)}</ul>
                          </div>
                        </div>
                      )}

                    </div>
                  </div>
                  <div className="mt-4 flex justify-end gap-2">
                    <button onClick={() => { setEditingId(item.id || null); setEditingDraft(strategyToDraft(item)); }} className={`px-3 py-2 text-[10px] font-black uppercase tracking-widest ${softPanelClass}`}>Editar</button>
                    <button onClick={() => item.id && deleteDoc(doc(db, 'estrategia_pessoal', item.id))} className="bg-rose-600 px-3 py-2 text-[10px] font-black uppercase tracking-widest text-white">Excluir</button>
                  </div>
                </article>
              );
            })}
            {filteredItems.length === 0 && (
              <div className={`border p-10 text-center ${softPanelClass}`}>
                <p className={`text-sm font-black uppercase tracking-widest ${mutedClass}`}>Nenhuma estratégia cadastrada neste filtro.</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default StrategyDashboardView;
