import React, { useEffect, useMemo, useState } from 'react';
import { addDoc, collection, deleteDoc, doc, onSnapshot, query, Timestamp, updateDoc, where } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from '../../firebase';
import { EstrategiaIndicadorSucesso, EstrategiaMarco, EstrategiaPessoal, EstrategiaPilar, EstrategiaStatus, EstrategiaTipoMeta, Tarefa } from '../../types';
import { normalizeSearchText } from '../utils/helpers';


type StrategyIndicatorDraft = EstrategiaIndicadorSucesso;
type StrategyMilestoneDraft = EstrategiaMarco;


type StrategyDraft = Omit<EstrategiaPessoal, 'id' | 'userId' | 'timestamp' | 'metricaAlvo' | 'indicadoresSucesso' | 'marcos'> & {
  metricaAlvo?: {
    valorInicial?: number | string;
    valorAtual: number | string;
    valorObjetivo: number | string;
    unidade: string;
  };
  indicadoresSucesso?: StrategyIndicatorDraft[];
  marcos?: StrategyMilestoneDraft[];
};


interface StrategyDashboardViewProps {
  userId: string;
  isDark?: boolean;
  showToast?: (msg: string, type?: 'success' | 'error' | 'info' | 'warning') => void;
  tarefas?: Tarefa[];
  onCreateIndicadorAction?: (item: EstrategiaPessoal, indicator: EstrategiaIndicadorSucesso) => void;
}


const PILLARS: Array<{ id: EstrategiaPilar; label: string; accent: string }> = [
  { id: 'carreira', label: 'Carreira', accent: 'bg-[#7800ce]' },
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
  marcos: [{ id: 'draft-marco-1', descricao: '', concluido: false }],
  diretrizesDerivadas: [''],
  status: 'ativo',
};


const normalizeList = (items?: string[]) => (items || []).map(item => item.trim()).filter(Boolean);
const parseMetricNumber = (value: number | string | undefined) => Number(String(value ?? 0).replace(',', '.')) || 0;
const createIndicatorId = () => `indicador-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const createMilestoneId = () => `marco-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const createRecordId = () => `registro-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const getPersistedIndicatorId = (item: string | EstrategiaIndicadorSucesso, index: number) => {
  if (typeof item !== 'string' && item.id) return item.id;
  return `indicador-legado-${index}`;
};
const getPersistedMilestoneId = (item: string | EstrategiaMarco, index: number) => {
  if (typeof item !== 'string' && item.id) return item.id;
  return `marco-legado-${index}`;
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


const toMilestoneDrafts = (items?: Array<string | EstrategiaMarco>): StrategyMilestoneDraft[] => {
  const converted = (items || []).map((item, index) => {
    if (typeof item === 'string') {
      return { id: getPersistedMilestoneId(item, index), descricao: item, concluido: false };
    }
    return {
      id: getPersistedMilestoneId(item, index),
      descricao: item.descricao || '',
      concluido: Boolean(item.concluido),
      dataConclusao: item.dataConclusao,
      evidencia: item.evidencia || '',
      registros: item.registros || [],
    };
  }).filter(item => item.descricao.trim() || item.evidencia?.trim());
  return converted.length ? converted : [{ id: createMilestoneId(), descricao: '', concluido: false }];
};


const normalizeMilestones = (items?: StrategyMilestoneDraft[]): EstrategiaMarco[] =>
  (items || [])
    .map(item => {
      const normalized: EstrategiaMarco = {
        id: item.id || createMilestoneId(),
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
  marcos: toMilestoneDrafts(item.marcos),
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
  `w-full rounded-lg border px-3 py-2 text-sm font-medium outline-none transition-all focus:ring-2 ${
    isDark ? 'border-slate-700 bg-slate-950 text-slate-100 focus:ring-[#7800ce]/35' : 'border-slate-200 bg-white text-slate-900 focus:border-[#9333ea] focus:ring-[#9333ea]/20'
  }`;

export const StrategyDashboardView: React.FC<StrategyDashboardViewProps> = ({ userId, isDark = false, showToast, tarefas = [], onCreateIndicadorAction }) => {
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
  const [deleteTarget, setDeleteTarget] = useState<EstrategiaPessoal | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [metricInputs, setMetricInputs] = useState<Record<string, string>>({});
  const [indicatorNotes, setIndicatorNotes] = useState<Record<string, string>>({});
  const [milestoneNotes, setMilestoneNotes] = useState<Record<string, string>>({});
  const [recordingIndicatorId, setRecordingIndicatorId] = useState<string | null>(null);
  const [selectedObjectiveId, setSelectedObjectiveId] = useState<string | null>(null);
  const [linkingIndicatorId, setLinkingIndicatorId] = useState<string | null>(null);
  const [selectedTaskToLink, setSelectedTaskToLink] = useState<string>('');
  const [taskSearch, setTaskSearch] = useState('');

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
  const selectedObjective = useMemo(
    () => selectedObjectiveId ? items.find(item => item.id === selectedObjectiveId) || null : null,
    [items, selectedObjectiveId],
  );
  const getIndicatorActions = (objectiveId?: string, indicatorId?: string) => {
    if (!objectiveId || !indicatorId) return [];
    return tarefas.filter(task => task.estrategia_objetivo_id === objectiveId && task.estrategia_indicador_id === indicatorId && task.status !== 'excluído');
  };
  const handleLinkTask = async (objectiveId?: string, indicatorId?: string) => {
    if (!objectiveId || !indicatorId || !selectedTaskToLink) return;
    try {
      await updateDoc(doc(db, 'tarefas', selectedTaskToLink), {
        estrategia_objetivo_id: objectiveId,
        estrategia_indicador_id: indicatorId
      });
      showToast?.('Ação vinculada com sucesso', 'success');
      setLinkingIndicatorId(null);
      setSelectedTaskToLink('');
    } catch (error) {
      console.error('Error linking task:', error);
      showToast?.('Erro ao vincular ação', 'error');
    }
  };

  const isTaskCompleted = (task: Tarefa) => {
    const normalized = String(task.status || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    return normalized === 'concluido';
  };
  const panelClass = isDark ? 'rounded-2xl bg-slate-950 text-slate-100 border-slate-800 shadow-sm' : 'rounded-2xl bg-white text-slate-900 border-slate-200 shadow-sm';
  const softPanelClass = isDark ? 'rounded-xl bg-slate-950/60 border-slate-800' : 'rounded-xl bg-slate-50 border-slate-200';
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


  const updateDraftMilestone = (index: number, valueIndex: number, updates: Partial<StrategyMilestoneDraft>) => {
    setDrafts(prev => prev.map((draft, idx) => {
      if (idx !== index) return draft;
      const nextList = [...(draft.marcos || [])];
      nextList[valueIndex] = { ...(nextList[valueIndex] || { id: createMilestoneId(), descricao: '', concluido: false }), ...updates };
      return { ...draft, marcos: nextList };
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


  const updateManualMilestone = (valueIndex: number, updates: Partial<StrategyMilestoneDraft>) => {
    setManualDraft(prev => {
      const nextList = [...(prev.marcos || [])];
      nextList[valueIndex] = { ...(nextList[valueIndex] || { id: createMilestoneId(), descricao: '', concluido: false }), ...updates };
      return { ...prev, marcos: nextList };
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
        marcos: toMilestoneDrafts(normalizeList(proposal.marcos)),
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
      marcos: normalizeMilestones(draft.marcos),
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


  const completeMilestone = async (item: EstrategiaPessoal, milestoneIndex: number) => {
    if (!item.id) return;
    const milestones = toMilestoneDrafts(item.marcos);
    const current = milestones[milestoneIndex];
    if (!current) return;
    const noteKey = `${item.id}:${current.id}`;
    const note = (milestoneNotes[noteKey] || '').trim();
    const record = {
      id: createRecordId(),
      data: new Date().toISOString(),
      nota: note || 'Marco concluído',
    };
    milestones[milestoneIndex] = {
      ...current,
      concluido: true,
      dataConclusao: record.data,
      evidencia: note || current.evidencia,
      registros: [...(current.registros || []), record],
    };
    try {
      await updateDoc(doc(db, 'estrategia_pessoal', item.id), {
        marcos: normalizeMilestones(milestones),
      });
      setMilestoneNotes(prev => ({ ...prev, [noteKey]: '' }));
      showToast?.('Marco concluído.', 'success');
    } catch (error: any) {
      showToast?.(error?.message || 'Erro ao concluir marco.', 'error');
    }
  };


  const confirmDeleteStrategy = async () => {
    if (!deleteTarget?.id) return;
    setIsDeleting(true);
    try {
      await deleteDoc(doc(db, 'estrategia_pessoal', deleteTarget.id));
      if (selectedObjectiveId === deleteTarget.id) setSelectedObjectiveId(null);
      setDeleteTarget(null);
      showToast?.('Objetivo excluído.', 'success');
    } catch (error: any) {
      showToast?.(error?.message || 'Erro ao excluir objetivo.', 'error');
    } finally {
      setIsDeleting(false);
    }
  };


  const renderDraftEditor = ({
    draft,
    index,
    onChange,
    onListChange,
    onIndicatorChange,
    onMilestoneChange,
    onSave,
    onCancel,
  }: {
    draft: StrategyDraft;
    index?: number;
    onChange: (updates: Partial<StrategyDraft>) => void;
    onListChange: (field: 'diretrizesDerivadas', valueIndex: number, value: string) => void;
    onIndicatorChange: (valueIndex: number, updates: Partial<StrategyIndicatorDraft>) => void;
    onMilestoneChange: (valueIndex: number, updates: Partial<StrategyMilestoneDraft>) => void;
    onSave: () => void;
    onCancel?: () => void;
  }) => {
    const handleIndicatorRemove = (idx: number) => {
      const newList = [...(draft.indicadoresSucesso || [])];
      newList.splice(idx, 1);
      onChange({ indicadoresSucesso: newList });
    };
    const handleMilestoneRemove = (idx: number) => {
      const newList = [...(draft.marcos || [])];
      newList.splice(idx, 1);
      onChange({ marcos: newList });
    };
    const handleGuidelineRemove = (idx: number) => {
      const newList = [...(draft.diretrizesDerivadas || [])];
      newList.splice(idx, 1);
      onChange({ diretrizesDerivadas: newList });
    };

    return (
    <div className={`border p-4 ${panelClass}`}>
      <div className="grid gap-3 md:grid-cols-3">
        <label className="text-[10px] font-bold uppercase tracking-wider">
          Pilar
          <select className={`${inputClass} mt-1`} value={draft.pilar} onChange={e => onChange({ pilar: e.target.value as EstrategiaPilar })}>
            {PILLARS.map(pillar => <option key={pillar.id} value={pillar.id}>{pillar.label}</option>)}
          </select>
        </label>
        <label className="text-[10px] font-bold uppercase tracking-wider">
          Tipo
          <select className={`${inputClass} mt-1`} value={draft.tipoMeta} onChange={e => onChange({ tipoMeta: e.target.value as EstrategiaTipoMeta })}>
            <option value="relativa_qualitativa">Qualitativa</option>
            <option value="absoluta">Absoluta</option>
          </select>
        </label>
        <label className="text-[10px] font-bold uppercase tracking-wider">
          Status
          <select className={`${inputClass} mt-1`} value={draft.status} onChange={e => onChange({ status: e.target.value as EstrategiaStatus })}>
            <option value="ativo">Ativo</option>
            <option value="revisar">Revisar</option>
            <option value="concluido">Concluído</option>
          </select>
        </label>
      </div>
      <label className="mt-3 block text-[10px] font-bold uppercase tracking-wider">
        Objetivo macro
        <textarea className={`${inputClass} mt-1 min-h-[76px] resize-y`} value={draft.objetivoMacro} onChange={e => onChange({ objetivoMacro: e.target.value })} />
      </label>
      {draft.tipoMeta === 'absoluta' && (
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <label className="text-[10px] font-bold uppercase tracking-wider">Atual<input className={`${inputClass} mt-1`} type="text" inputMode="decimal" value={draft.metricaAlvo?.valorAtual ?? ''} onChange={e => onChange({ metricaAlvo: { valorInicial: draft.metricaAlvo?.valorInicial, valorAtual: e.target.value, valorObjetivo: draft.metricaAlvo?.valorObjetivo ?? '', unidade: draft.metricaAlvo?.unidade || '' } })} /></label>
          <label className="text-[10px] font-bold uppercase tracking-wider">Objetivo<input className={`${inputClass} mt-1`} type="text" inputMode="decimal" value={draft.metricaAlvo?.valorObjetivo ?? ''} onChange={e => onChange({ metricaAlvo: { valorInicial: draft.metricaAlvo?.valorInicial, valorAtual: draft.metricaAlvo?.valorAtual ?? '', valorObjetivo: e.target.value, unidade: draft.metricaAlvo?.unidade || '' } })} /></label>
          <label className="text-[10px] font-bold uppercase tracking-wider">Unidade<input className={`${inputClass} mt-1`} value={draft.metricaAlvo?.unidade || ''} onChange={e => onChange({ metricaAlvo: { valorInicial: draft.metricaAlvo?.valorInicial, valorAtual: draft.metricaAlvo?.valorAtual ?? '', valorObjetivo: draft.metricaAlvo?.valorObjetivo ?? '', unidade: e.target.value } })} /></label>
        </div>
      )}
      <div className="mt-6 flex flex-col gap-6">
        <div>
          <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">Indicadores contínuos</p>
          <div className="flex flex-col gap-2">
            {(draft.indicadoresSucesso || []).length === 0 && (
              <p className={`text-xs italic ${mutedClass}`}>Nenhum indicador cadastrado.</p>
            )}
            {(draft.indicadoresSucesso || []).map((value, valueIndex) => (
              <div key={value.id || `${index ?? 'manual'}-indicador-${valueIndex}`} className="flex items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400" title="Indicador contínuo">🎯</span>
                <input className={`${inputClass} flex-1`} placeholder="Escreva o indicador..." value={value.descricao} onChange={e => onIndicatorChange(valueIndex, { descricao: e.target.value })} />
                <button type="button" onClick={() => handleIndicatorRemove(valueIndex)} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-all hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400" title="Remover indicador">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
              </div>
            ))}
            <button type="button" className="mt-1 flex w-fit items-center gap-1.5 rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 transition-all hover:border-emerald-500 hover:text-emerald-600 dark:border-slate-700 dark:hover:border-emerald-500 dark:hover:text-emerald-400" onClick={() => onChange({ indicadoresSucesso: [...(draft.indicadoresSucesso || []), { id: createIndicatorId(), descricao: '', concluido: false }] })}>
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/></svg>
              Adicionar indicador
            </button>
          </div>
        </div>

        <div>
          <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">Marcos pontuais</p>
          <div className="flex flex-col gap-2">
            {(draft.marcos || []).length === 0 && (
              <p className={`text-xs italic ${mutedClass}`}>Nenhum marco cadastrado.</p>
            )}
            {(draft.marcos || []).map((value, valueIndex) => (
              <div key={value.id || `${index ?? 'manual'}-marco-${valueIndex}`} className="flex items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-orange-100 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400" title="Marco pontual">🚩</span>
                <input className={`${inputClass} flex-1`} placeholder="Escreva o marco..." value={value.descricao} onChange={e => onMilestoneChange(valueIndex, { descricao: e.target.value })} />
                <button type="button" onClick={() => handleMilestoneRemove(valueIndex)} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-all hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400" title="Remover marco">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
              </div>
            ))}
            <button type="button" className="mt-1 flex w-fit items-center gap-1.5 rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 transition-all hover:border-orange-500 hover:text-orange-600 dark:border-slate-700 dark:hover:border-orange-500 dark:hover:text-orange-400" onClick={() => onChange({ marcos: [...(draft.marcos || []), { id: createMilestoneId(), descricao: '', concluido: false }] })}>
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/></svg>
              Adicionar marco
            </button>
          </div>
        </div>

        <div>
          <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">Diretrizes para IA</p>
          <div className="flex flex-col gap-2">
            {(draft.diretrizesDerivadas || []).length === 0 && (
              <p className={`text-xs italic ${mutedClass}`}>Nenhuma diretriz cadastrada.</p>
            )}
            {(draft.diretrizesDerivadas || []).map((value, valueIndex) => (
              <div key={`${index ?? 'manual'}-diretriz-${valueIndex}`} className="flex items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400" title="Diretriz para IA">✨</span>
                <input className={`${inputClass} flex-1`} placeholder="Escreva a diretriz..." value={value} onChange={e => onListChange('diretrizesDerivadas', valueIndex, e.target.value)} />
                <button type="button" onClick={() => handleGuidelineRemove(valueIndex)} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-all hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400" title="Remover diretriz">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
              </div>
            ))}
            <button type="button" className="mt-1 flex w-fit items-center gap-1.5 rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 transition-all hover:border-blue-500 hover:text-blue-600 dark:border-slate-700 dark:hover:border-blue-500 dark:hover:text-blue-400" onClick={() => onChange({ diretrizesDerivadas: [...(draft.diretrizesDerivadas || []), ''] })}>
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/></svg>
              Adicionar diretriz
            </button>
          </div>
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        {onCancel && <button onClick={onCancel} className={`px-4 py-2 text-[10px] font-bold uppercase tracking-wider ${softPanelClass}`}>Cancelar</button>}
        <button disabled={isSaving} onClick={onSave} className="rounded-lg bg-[#7800ce] px-5 py-2 text-[10px] font-bold uppercase tracking-wider text-white disabled:opacity-50">
          {isSaving ? 'Salvando...' : 'Salvar'}
        </button>
      </div>
    </div>
  );
  };

  return (
    <div className={`min-h-screen px-4 pb-24 md:px-8 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
      {!selectedObjective && (
        <>
          <div className="mb-6 flex justify-end animate-in fade-in duration-300">
        <button
          onClick={() => {
            setIsCreateModalOpen(true);
            setDrafts([]);
            setIntention('');
            setManualDraft(emptyDraft);
          }}
          className="rounded-lg bg-[#7800ce] px-5 py-3 text-[10px] font-bold uppercase tracking-wider text-white shadow-sm transition-all hover:bg-[#9333ea]"
        >
          Novo objetivo
        </button>
      </div>
          <div className="grid gap-3 md:grid-cols-4 mb-6">
        <div className={`border p-4 ${panelClass}`}><p className={mutedClass}>Ativos</p><strong className="text-3xl">{stats.activeCount}</strong></div>
        <div className={`border p-4 ${panelClass}`}><p className={mutedClass}>Qualitativos</p><strong className="text-3xl">{stats.qualitativeCount}</strong></div>
        <div className={`border p-4 ${panelClass}`}><p className={mutedClass}>Progresso médio</p><strong className="text-3xl">{stats.avgProgress}%</strong></div>
        <div className={`border p-4 ${panelClass}`}><p className={mutedClass}>Pilares ativos</p><strong className="text-3xl">{stats.byPillar.filter(p => p.count > 0).length}</strong></div>
      </div>
      </>
      )}


      {isCreateModalOpen && (
        <div className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-slate-950/60 px-4 py-6 backdrop-blur-sm">
          <div className={`w-full max-w-5xl border shadow-lg ${panelClass}`}>
            <div className={`flex items-center justify-between border-b p-4 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <div>
                <h3 className="text-xl font-bold tracking-tight">Novo objetivo</h3>
              </div>
              <button
                onClick={() => {
                  setIsCreateModalOpen(false);
                  setDrafts([]);
                  setIntention('');
                }}
                className={`px-3 py-2 text-[10px] font-bold uppercase tracking-wider ${softPanelClass}`}
              >
                Fechar
              </button>
            </div>
            <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,420px)_1fr]">
              <section className={`border p-4 ${softPanelClass}`}>
                <h3 className="text-sm font-bold uppercase tracking-wider">Entrada orgânica</h3>
                <textarea className={`${inputClass} mt-3 min-h-[140px] resize-y`} value={intention} onChange={e => setIntention(e.target.value)} placeholder="Descreva uma intenção estratégica em texto livre." />
                <button disabled={isRefining || !intention.trim()} onClick={refineIntention} className="mt-3 w-full rounded-lg bg-[#7800ce] px-5 py-3 text-[10px] font-bold uppercase tracking-wider text-white transition-all hover:bg-[#9333ea] disabled:opacity-50">
                  {isRefining ? 'Refinando...' : 'Refinar com Hermes'}
                </button>


                <div className={`mt-5 border-t pt-5 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                  <h3 className="mb-3 text-sm font-bold uppercase tracking-wider">Cadastro manual</h3>
                  {renderDraftEditor({
                    draft: manualDraft,
                    onChange: updates => setManualDraft(prev => ({ ...prev, ...updates })),
                    onListChange: updateManualList,
                    onIndicatorChange: updateManualIndicator,
                    onMilestoneChange: updateManualMilestone,
                    onSave: () => saveDraft(manualDraft).then(() => setManualDraft(emptyDraft)),
                  })}
                </div>
              </section>


              <section className="space-y-3">
                <h3 className="text-sm font-bold uppercase tracking-wider">Propostas para validação</h3>
                {drafts.length === 0 ? (
                  <div className={`border p-8 text-center ${softPanelClass}`}>
                    <p className={`text-xs font-bold uppercase tracking-wider ${mutedClass}`}>As propostas refinadas aparecerão aqui.</p>
                  </div>
                ) : drafts.map((draft, index) => (
                  <React.Fragment key={`modal-draft-${index}`}>
                    {renderDraftEditor({
                      draft,
                      index,
                      onChange: updates => setDrafts(prev => prev.map((item, idx) => idx === index ? { ...item, ...updates } : item)),
                      onListChange: (field, valueIndex, value) => updateDraftList(index, field, valueIndex, value),
                      onIndicatorChange: (valueIndex, updates) => updateDraftIndicator(index, valueIndex, updates),
                      onMilestoneChange: (valueIndex, updates) => updateDraftMilestone(index, valueIndex, updates),
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


      {deleteTarget && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/60 px-4 py-6 backdrop-blur-sm">
          <div className={`w-full max-w-md border shadow-lg ${panelClass}`}>
            <div className={`border-b p-4 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Confirmar exclusão</p>
              <h3 className="mt-1 text-xl font-bold tracking-tight">Excluir objetivo?</h3>
            </div>
            <div className="p-4">
              <p className={`text-sm font-semibold leading-relaxed ${mutedClass}`}>
                Esta ação removerá o objetivo estratégico e seus registros associados. A exclusão não pode ser desfeita.
              </p>
              <div className={`mt-4 border p-3 ${softPanelClass}`}>
                <p className="text-sm font-bold leading-snug">{deleteTarget.objetivoMacro}</p>
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  disabled={isDeleting}
                  onClick={() => setDeleteTarget(null)}
                  className={`px-4 py-2 text-[10px] font-bold uppercase tracking-wider disabled:opacity-50 ${softPanelClass}`}
                >
                  Cancelar
                </button>
                <button
                  disabled={isDeleting}
                  onClick={confirmDeleteStrategy}
                  className="rounded-lg bg-rose-600 px-4 py-2 text-[10px] font-bold uppercase tracking-wider text-white disabled:opacity-50"
                >
                  {isDeleting ? 'Excluindo...' : 'Excluir definitivamente'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {selectedObjective && (() => {
        const item = selectedObjective;
        const pillar = PILLARS.find(p => p.id === item.pilar) || PILLARS[0];
        const progress = computeProgress(item);
        const indicators = toIndicatorDrafts(item.indicadoresSucesso).filter(indicator => indicator.descricao.trim());
        const milestones = toMilestoneDrafts(item.marcos).filter(milestone => milestone.descricao.trim());
        const isEditingSelected = Boolean(editingDraft);
        return (
          <div className="animate-in slide-in-from-right-8 duration-300">
            <div className={`w-full border ${panelClass}`}>
              <div className={`flex items-start justify-between gap-4 border-b p-5 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                <div className="min-w-0">
                  <span className={`inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>
                    <span className={`h-2.5 w-2.5 rounded-full ${pillar.accent}`} />{pillar.label}
                  </span>
                  <h3 className="mt-2 text-2xl font-bold tracking-tight">{isEditingSelected ? 'Editar objetivo' : item.objetivoMacro}</h3>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedObjectiveId(null);
                    setEditingDraft(null);
                    setEditingId(null);
                  }}
                  className={`shrink-0 px-3 py-2 text-[10px] font-bold uppercase tracking-wider ${softPanelClass}`}
                >
                  Fechar
                </button>
              </div>
              {isEditingSelected && editingDraft ? (
                <div className="p-5">
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
                    onMilestoneChange: (valueIndex, updates) => {
                      setEditingDraft(prev => {
                        if (!prev) return prev;
                        const list = [...(prev.marcos || [])];
                        list[valueIndex] = { ...(list[valueIndex] || { id: createMilestoneId(), descricao: '', concluido: false }), ...updates };
                        return { ...prev, marcos: list };
                      });
                    },
                    onSave: () => saveDraft(editingDraft, undefined, item.id),
                    onCancel: () => {
                      setEditingId(null);
                      setEditingDraft(null);
                    },
                  })}
                </div>
              ) : (
                <div className="grid gap-5 p-5 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="space-y-5">
                    <section className={`border p-4 ${softPanelClass}`}>
                      <div className="grid gap-3 md:grid-cols-3">
                        <div>
                          <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Status</p>
                          <p className="mt-1 text-sm font-bold">{item.status}</p>
                        </div>
                        <div>
                          <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Tipo</p>
                          <p className="mt-1 text-sm font-bold">{item.tipoMeta === 'absoluta' ? 'Meta absoluta' : 'Qualitativa'}</p>
                        </div>
                        <div>
                          <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Diretrizes</p>
                          <p className="mt-1 text-sm font-bold">{item.diretrizesDerivadas.length}</p>
                        </div>
                      </div>
                    </section>
                    {progress !== null && (
                      <section className={`border p-4 ${softPanelClass}`}>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Metrica principal</p>
                            <p className="mt-1 text-sm font-bold">{item.metricaAlvo?.valorAtual} / {item.metricaAlvo?.valorObjetivo} {item.metricaAlvo?.unidade}</p>
                          </div>
                          <strong className="text-2xl">{progress}%</strong>
                        </div>
                        <div className={`mt-3 h-2 overflow-hidden rounded-full ${isDark ? 'bg-slate-800' : 'bg-slate-100'}`}>
                          <div className="h-full rounded-full bg-[#7800ce]" style={{ width: `${progress}%` }} />
                        </div>
                        <div className="mt-4 flex gap-2">
                          <input
                            className={`${inputClass} text-xs`}
                            type="text"
                            inputMode="decimal"
                            value={metricInputs[item.id || ''] ?? ''}
                            onChange={(event) => item.id && setMetricInputs(prev => ({ ...prev, [item.id!]: event.target.value }))}
                            placeholder={`Novo valor${item.metricaAlvo?.unidade ? ` em ${item.metricaAlvo.unidade}` : ''}`}
                          />
                          <button onClick={() => registerMetricValue(item)} className="shrink-0 rounded-lg bg-[#7800ce] px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white transition-all hover:bg-[#9333ea]">
                            Registrar
                          </button>
                        </div>
                      </section>
                    )}
                    <section className="space-y-3">
                      <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Indicadores continuos</p>
                      {indicators.length === 0 ? (
                        <div className={`border p-4 text-sm font-semibold ${softPanelClass}`}>Nenhum indicador continuo cadastrado.</div>
                      ) : indicators.map((indicator, indicatorIndex) => {
                        const linkedActions = getIndicatorActions(item.id, indicator.id);
                        const completedLinkedActions = linkedActions.filter(isTaskCompleted);
                        return (
                          <div key={indicator.id} className={`border p-4 ${softPanelClass}`}>
                            <div className="flex items-start justify-between gap-3">
                              <p className="text-base font-bold leading-relaxed">{indicator.descricao}</p>
                              <span className={`shrink-0 rounded-lg px-2 py-1 text-[9px] font-bold uppercase tracking-wider ${isDark ? 'bg-slate-800 text-slate-300' : 'bg-slate-200 text-slate-700'}`}>
                                {completedLinkedActions.length}/{linkedActions.length} ações
                              </span>
                            </div>
                            {linkedActions.length > 0 && (
                              <div className="mt-3 space-y-1">
                                {linkedActions.slice(0, 5).map(action => (
                                  <div key={action.id} className={`flex items-center justify-between gap-2 border px-3 py-2 text-xs font-semibold ${panelClass}`}>
                                    <span className={isTaskCompleted(action) ? 'line-through opacity-70' : ''}>{action.titulo}</span>
                                    <span className={`shrink-0 text-[8px] font-bold uppercase tracking-wider ${mutedClass}`}>{action.status}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                            {(indicator.registros || []).slice(-3).map(record => (
                              <p key={record.id} className={`mt-2 text-xs font-semibold ${mutedClass}`}>
                                {new Date(record.data).toLocaleDateString('pt-BR')}: {record.nota}
                              </p>
                            ))}
                            {linkingIndicatorId === indicator.id ? (
                              <div className="mt-3 flex flex-col gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/50">
                                <label className="text-[10px] font-bold uppercase tracking-wider">Vincular ação existente</label>
                                <div className="relative">
                                  <input
                                    type="text"
                                    placeholder="Buscar ou selecionar tarefa..."
                                    value={taskSearch}
                                    onChange={e => {
                                      setTaskSearch(e.target.value);
                                      setSelectedTaskToLink('');
                                    }}
                                    className={`${inputClass} text-xs w-full`}
                                  />
                                  {!selectedTaskToLink && (
                                    <div className="mt-1 max-h-40 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800">
                                      {tarefas
                                        .filter(t => !t.estrategia_indicador_id && t.status !== 'excluído')
                                        .filter(t => normalizeSearchText(t.titulo).includes(normalizeSearchText(taskSearch)))
                                        .map(t => (
                                          <button
                                            key={t.id}
                                            type="button"
                                            onClick={() => {
                                              setSelectedTaskToLink(t.id);
                                              setTaskSearch(t.titulo);
                                            }}
                                            className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-xs transition-all hover:bg-slate-100 dark:hover:bg-slate-700"
                                          >
                                            <span className="truncate">{t.titulo}</span>
                                            <span className={`shrink-0 text-[8px] font-bold uppercase tracking-wider ${
                                              isTaskCompleted(t) ? 'text-emerald-600 dark:text-emerald-400' :
                                              t.status === 'em andamento' ? 'text-blue-600 dark:text-blue-400' :
                                              'text-slate-500'
                                            }`}>
                                              {t.status}
                                            </span>
                                          </button>
                                      ))}
                                      {tarefas.filter(t => !t.estrategia_indicador_id && t.status !== 'excluído' && normalizeSearchText(t.titulo).includes(normalizeSearchText(taskSearch))).length === 0 && (
                                        <div className="px-3 py-2 text-xs text-slate-500">Nenhuma tarefa encontrada</div>
                                      )}
                                    </div>
                                  )}
                                </div>
                                <div className="flex gap-2">
                                  <button
                                    type="button"
                                    disabled={!selectedTaskToLink}
                                    onClick={() => handleLinkTask(item.id, indicator.id)}
                                    className="rounded-lg bg-emerald-600 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white transition-all hover:bg-emerald-700 disabled:opacity-50"
                                  >
                                    Vincular
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => { setLinkingIndicatorId(null); setSelectedTaskToLink(''); setTaskSearch(''); }}
                                    className={`rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all ${softPanelClass}`}
                                  >
                                    Cancelar
                                  </button>
                                </div>
                              </div>
                            ) : recordingIndicatorId === indicator.id ? (
                              <div className="mt-3 flex flex-col gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/50">
                                <input
                                  value={indicatorNotes[`${item.id}:${indicator.id}`] ?? ''}
                                  onChange={(event) => setIndicatorNotes(prev => ({ ...prev, [`${item.id}:${indicator.id}`]: event.target.value }))}
                                  className={`${inputClass} text-xs`}
                                  placeholder="Escreva o registro do indicador"
                                />
                                <div className="flex gap-2">
                                  <button onClick={() => { registerIndicatorNote(item, indicatorIndex); setRecordingIndicatorId(null); }} className="rounded-lg bg-[#7800ce] px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white transition-all hover:bg-[#9333ea]">
                                    Registrar
                                  </button>
                                  <button onClick={() => setRecordingIndicatorId(null)} className={`rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all ${softPanelClass}`}>
                                    Cancelar
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div className="mt-3 flex items-center justify-start gap-2 border-t border-slate-200 pt-3 dark:border-slate-800">
                                <button
                                  type="button"
                                  onClick={() => setRecordingIndicatorId(indicator.id!)}
                                  className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-300"
                                >
                                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/></svg>
                                  Registro
                                </button>
                                <button
                                  type="button"
                                  onClick={() => { setLinkingIndicatorId(indicator.id!); setSelectedTaskToLink(''); setTaskSearch(''); }}
                                  className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-300"
                                >
                                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                                  Vincular
                                </button>
                                <button
                                  type="button"
                                  onClick={() => onCreateIndicadorAction?.(item, indicator)}
                                  disabled={!item.id || !onCreateIndicadorAction}
                                  className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-800 disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-slate-300"
                                >
                                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
                                  Nova ação
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </section>
                  </div>
                  <aside className="space-y-5">
                    <section className="space-y-3">
                      <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Marcos pontuais</p>
                      {milestones.length === 0 ? (
                        <div className={`border p-4 text-sm font-semibold ${softPanelClass}`}>Nenhum marco pontual cadastrado.</div>
                      ) : milestones.map((milestone, milestoneIndex) => (
                        <div key={milestone.id} className={`border p-4 ${softPanelClass}`}>
                          <div className="flex items-start justify-between gap-2">
                            <span className={`text-sm font-bold leading-relaxed ${milestone.concluido ? 'line-through opacity-70' : ''}`}>{milestone.descricao}</span>
                            {milestone.concluido && <span className="rounded-lg bg-emerald-600 px-2 py-1 text-[8px] font-bold uppercase tracking-wider text-white">Concluido</span>}
                          </div>
                          {!milestone.concluido && (
                            <div className="mt-3 flex gap-2">
                              <input
                                value={milestoneNotes[`${item.id}:${milestone.id}`] ?? ''}
                                onChange={(event) => setMilestoneNotes(prev => ({ ...prev, [`${item.id}:${milestone.id}`]: event.target.value }))}
                                className={`${inputClass} text-xs`}
                                placeholder="Evidencia ou nota"
                              />
                              <button onClick={() => completeMilestone(item, milestoneIndex)} className="shrink-0 rounded-lg bg-emerald-600 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white">
                                Concluir
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </section>
                    <section className={`border p-4 ${softPanelClass}`}>
                      <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Diretrizes passivas</p>
                      <ul className="mt-3 space-y-2 text-sm font-semibold">
                        {item.diretrizesDerivadas.map(directive => <li key={directive}>- {directive}</li>)}
                      </ul>
                    </section>
                  </aside>
                </div>
              )}
              {!isEditingSelected && (
                <div className={`flex justify-end gap-2 border-t p-5 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                  <button onClick={() => setEditingDraft(strategyToDraft(item))} className={`px-4 py-2 text-[10px] font-bold uppercase tracking-wider ${softPanelClass}`}>Editar</button>
                  <button onClick={() => setDeleteTarget(item)} className="rounded-lg bg-rose-600 px-4 py-2 text-[10px] font-bold uppercase tracking-wider text-white">Excluir</button>
                </div>
              )}
            </div>
          </div>
        );
      })()}
      {!selectedObjective && (
      <div className="mt-6 animate-in fade-in duration-300">
        <section className={`hidden border p-4 ${panelClass}`}>
          <h3 className="text-sm font-bold uppercase tracking-wider">Entrada orgânica</h3>
          <textarea className={`${inputClass} mt-3 min-h-[140px] resize-y`} value={intention} onChange={e => setIntention(e.target.value)} placeholder="Descreva uma intenção estratégica em texto livre." />
          <button disabled={isRefining || !intention.trim()} onClick={refineIntention} className="mt-3 w-full rounded-lg bg-[#7800ce] px-5 py-3 text-[10px] font-bold uppercase tracking-wider text-white transition-all hover:bg-[#9333ea] disabled:opacity-50">
            {isRefining ? 'Refinando...' : 'Refinar com Hermes'}
          </button>


          <div className={`mt-5 border-t pt-5 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
            <h3 className="mb-3 text-sm font-bold uppercase tracking-wider">Cadastro manual</h3>
            {renderDraftEditor({
              draft: manualDraft,
              onChange: updates => setManualDraft(prev => ({ ...prev, ...updates })),
              onListChange: updateManualList,
              onIndicatorChange: updateManualIndicator,
              onMilestoneChange: updateManualMilestone,
              onSave: () => saveDraft(manualDraft).then(() => setManualDraft(emptyDraft)),
            })}
          </div>
        </section>


        <section className="space-y-4">
          {false && drafts.length > 0 && (
            <div className={`border p-4 ${softPanelClass}`}>
              <h3 className="mb-3 text-sm font-bold uppercase tracking-wider">Propostas para validação</h3>
              <div className="space-y-3">
                {drafts.map((draft, index) => (
                  <React.Fragment key={`draft-${index}`}>
                    {renderDraftEditor({
                      draft,
                      index,
                      onChange: updates => setDrafts(prev => prev.map((item, idx) => idx === index ? { ...item, ...updates } : item)),
                      onListChange: (field, valueIndex, value) => updateDraftList(index, field, valueIndex, value),
                      onIndicatorChange: (valueIndex, updates) => updateDraftIndicator(index, valueIndex, updates),
                      onMilestoneChange: (valueIndex, updates) => updateDraftMilestone(index, valueIndex, updates),
                      onSave: () => saveDraft(draft, index),
                      onCancel: () => setDrafts(prev => prev.filter((_, idx) => idx !== index)),
                    })}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}


          <div className="flex flex-wrap gap-2">
            <button onClick={() => setSelectedPillar('todos')} className={`rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all ${selectedPillar === 'todos' ? 'bg-[#7800ce] text-white shadow-sm' : softPanelClass}`}>Todos</button>
            {PILLARS.map(pillar => (
              <button key={pillar.id} onClick={() => setSelectedPillar(pillar.id)} className={`rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all ${selectedPillar === pillar.id ? 'bg-[#7800ce] text-white shadow-sm' : softPanelClass}`}>
                {pillar.label} ({stats.byPillar.find(p => p.id === pillar.id)?.count || 0})
              </button>
            ))}
          </div>


          <div className="grid gap-4 lg:grid-cols-2">
            {filteredItems.map(item => {
              const pillar = PILLARS.find(p => p.id === item.pilar) || PILLARS[0];
              const progress = computeProgress(item);
              const indicators = toIndicatorDrafts(item.indicadoresSucesso).filter(indicator => indicator.descricao.trim());
              const milestones = toMilestoneDrafts(item.marcos).filter(milestone => milestone.descricao.trim());
              const indicatorPanelId = `strategy-objective-${item.id || item.objetivoMacro}`;
              const areIndicatorsExpanded = false;
              const indicatorActionCount = indicators.reduce((sum, indicator) => sum + getIndicatorActions(item.id, indicator.id).length, 0);
              const completedIndicatorActionCount = indicators.reduce((sum, indicator) => sum + getIndicatorActions(item.id, indicator.id).filter(isTaskCompleted).length, 0);
              const completedMilestoneCount = milestones.filter(milestone => milestone.concluido).length;
              return (
                <article
                  key={item.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => item.id && setSelectedObjectiveId(item.id)}
                  onKeyDown={(event) => {
                    if ((event.key === 'Enter' || event.key === ' ') && item.id) {
                      event.preventDefault();
                      setSelectedObjectiveId(item.id);
                    }
                  }}
                  className={`cursor-pointer border p-4 transition-all hover:-translate-y-0.5 hover:border-[#7800ce]/50 hover:shadow-md ${panelClass}`}
                >
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div>
                      <span className={`inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>
                        <span className={`h-2 w-2 rounded-full ${pillar.accent}`} />{pillar.label}
                      </span>
                      <h3 className="mt-2 text-base font-bold leading-snug">{item.objetivoMacro}</h3>
                    </div>
                    <span className={`border px-2 py-1 text-[9px] font-bold uppercase tracking-wider ${softPanelClass}`}>{item.status}</span>
                  </div>
                  {progress !== null && (
                    <div className={`mb-4 border p-3 ${softPanelClass}`}>
                      <p className={`mb-2 text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Métrica principal</p>
                      <div className="mb-1 flex justify-between text-[10px] font-bold uppercase tracking-wider">
                        <span>{item.metricaAlvo?.valorAtual} / {item.metricaAlvo?.valorObjetivo} {item.metricaAlvo?.unidade}</span>
                        <span>{progress}%</span>
                      </div>
                      <div className={`h-2 overflow-hidden rounded-full ${isDark ? 'bg-slate-800' : 'bg-slate-100'}`}><div className="h-full rounded-full bg-[#7800ce]" style={{ width: `${progress}%` }} /></div>
                      <div className="hidden">
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
                          className="shrink-0 rounded-lg bg-[#7800ce] px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white transition-all hover:bg-[#9333ea]"
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
                        onClick={(event) => {
                          event.stopPropagation();
                          item.id && setSelectedObjectiveId(item.id);
                        }}
                        className={`flex w-full items-center justify-between border px-3 py-2 text-left transition-all ${softPanelClass}`}
                        aria-expanded={areIndicatorsExpanded}
                        aria-controls={indicatorPanelId}
                      >
                        <span>
                          <span className={`block text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Abrir detalhes</span>
                          <span className="mt-2 flex flex-wrap gap-2">
                            {indicators.length > 0 && (
                              <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${isDark ? 'bg-slate-800 text-slate-300' : 'bg-slate-200 text-slate-700'}`}>
                                {indicators.length} indicador{indicators.length === 1 ? '' : 'es'}
                              </span>
                            )}
                            {indicatorActionCount > 0 && (
                              <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${isDark ? 'bg-slate-800 text-slate-300' : 'bg-slate-200 text-slate-700'}`}>
                                {completedIndicatorActionCount}/{indicatorActionCount} {indicatorActionCount === 1 ? 'ação' : 'ações'}
                              </span>
                            )}
                            {milestones.length > 0 && (
                              <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${isDark ? 'bg-slate-800 text-slate-300' : 'bg-slate-200 text-slate-700'}`}>
                                {completedMilestoneCount}/{milestones.length} marco{milestones.length === 1 ? '' : 's'}
                              </span>
                            )}
                          </span>
                        </span>
                        <svg className="h-4 w-4 text-[#7800ce]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                        </svg>
                      </button>
                      {areIndicatorsExpanded && (
                        <div id={indicatorPanelId} className="mt-2 space-y-4">
                          <div className="space-y-2">
                            <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Indicadores contínuos</p>
                            {indicators.length === 0 ? (
                              <p className={`text-xs font-bold ${mutedClass}`}>Nenhum indicador contínuo cadastrado.</p>
                            ) : indicators.map((indicator, indicatorIndex) => {
                              const linkedActions = getIndicatorActions(item.id, indicator.id);
                              const completedLinkedActions = linkedActions.filter(isTaskCompleted);
                              return (
                              <div key={indicator.id} className={`border p-2 ${softPanelClass}`}>
                                <div className="flex items-start justify-between gap-2">
                                  <span className="text-base font-bold leading-relaxed">{indicator.descricao}</span>
                                  <span className={`shrink-0 rounded-lg px-2 py-1 text-[9px] font-bold uppercase tracking-wider ${isDark ? 'bg-slate-800 text-slate-300' : 'bg-slate-200 text-slate-700'}`}>
                                    {completedLinkedActions.length}/{linkedActions.length} ações
                                  </span>
                                </div>
                                {linkedActions.length > 0 && (
                                  <div className="mt-2 space-y-1">
                                    {linkedActions.slice(0, 4).map(action => (
                                      <div key={action.id} className={`flex items-center justify-between gap-2 border px-2 py-1 text-xs font-semibold ${panelClass}`}>
                                        <span className={isTaskCompleted(action) ? 'line-through opacity-70' : ''}>{action.titulo}</span>
                                        <span className={`shrink-0 text-[8px] font-bold uppercase tracking-wider ${mutedClass}`}>{action.status}</span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                                {(indicator.registros || []).slice(-2).map(record => (
                                  <p key={record.id} className={`mt-1 text-xs font-semibold ${mutedClass}`}>
                                    {new Date(record.data).toLocaleDateString('pt-BR')}: {record.nota}
                                  </p>
                                ))}
                                {linkingIndicatorId === indicator.id ? (
                                  <div className="mt-2 flex flex-col gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/50">
                                    <label className="text-[10px] font-bold uppercase tracking-wider">Vincular ação existente</label>
                                    <div className="relative">
                                      <input
                                        type="text"
                                        placeholder="Buscar ou selecionar tarefa..."
                                        value={taskSearch}
                                        onChange={e => {
                                          setTaskSearch(e.target.value);
                                          setSelectedTaskToLink('');
                                        }}
                                        className={`${inputClass} text-xs w-full`}
                                      />
                                      {!selectedTaskToLink && (
                                        <div className="mt-1 max-h-40 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800">
                                          {tarefas
                                            .filter(t => !t.estrategia_indicador_id && t.status !== 'excluído')
                                            .filter(t => normalizeSearchText(t.titulo).includes(normalizeSearchText(taskSearch)))
                                            .map(t => (
                                              <button
                                                key={t.id}
                                                type="button"
                                                onClick={() => {
                                                  setSelectedTaskToLink(t.id);
                                                  setTaskSearch(t.titulo);
                                                }}
                                                className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-xs transition-all hover:bg-slate-100 dark:hover:bg-slate-700"
                                              >
                                                <span className="truncate">{t.titulo}</span>
                                                <span className={`shrink-0 text-[8px] font-bold uppercase tracking-wider ${
                                                  isTaskCompleted(t) ? 'text-emerald-600 dark:text-emerald-400' :
                                                  t.status === 'em andamento' ? 'text-blue-600 dark:text-blue-400' :
                                                  'text-slate-500'
                                                }`}>
                                                  {t.status}
                                                </span>
                                              </button>
                                          ))}
                                          {tarefas.filter(t => !t.estrategia_indicador_id && t.status !== 'excluído' && normalizeSearchText(t.titulo).includes(normalizeSearchText(taskSearch))).length === 0 && (
                                            <div className="px-3 py-2 text-xs text-slate-500">Nenhuma tarefa encontrada</div>
                                          )}
                                        </div>
                                      )}
                                    </div>
                                    <div className="flex gap-2">
                                      <button
                                        type="button"
                                        disabled={!selectedTaskToLink}
                                        onClick={() => handleLinkTask(item.id, indicator.id)}
                                        className="rounded-lg bg-emerald-600 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white transition-all hover:bg-emerald-700 disabled:opacity-50"
                                      >
                                        Vincular
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => { setLinkingIndicatorId(null); setSelectedTaskToLink(''); setTaskSearch(''); }}
                                        className={`rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all ${softPanelClass}`}
                                      >
                                        Cancelar
                                      </button>
                                    </div>
                                  </div>
                                ) : recordingIndicatorId === indicator.id ? (
                                  <div className="mt-2 flex flex-col gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/50">
                                    <input
                                      value={indicatorNotes[`${item.id}:${indicator.id}`] ?? ''}
                                      onChange={(event) => setIndicatorNotes(prev => ({ ...prev, [`${item.id}:${indicator.id}`]: event.target.value }))}
                                      className={`${inputClass} text-xs`}
                                      placeholder="Escreva o registro do indicador"
                                    />
                                    <div className="flex gap-2">
                                      <button onClick={() => { registerIndicatorNote(item, indicatorIndex); setRecordingIndicatorId(null); }} className="rounded-lg bg-[#7800ce] px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white transition-all hover:bg-[#9333ea]">
                                        Registrar
                                      </button>
                                      <button onClick={() => setRecordingIndicatorId(null)} className={`rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-wider transition-all ${softPanelClass}`}>
                                        Cancelar
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="mt-2 flex items-center justify-start gap-1 border-t border-slate-200 pt-2 dark:border-slate-800">
                                    <button
                                      type="button"
                                      onClick={() => setRecordingIndicatorId(indicator.id!)}
                                      className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-300"
                                      title="Adicionar registro"
                                    >
                                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/></svg>
                                      Registro
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => { setLinkingIndicatorId(indicator.id!); setSelectedTaskToLink(''); setTaskSearch(''); }}
                                      className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-300"
                                      title="Vincular ação"
                                    >
                                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                                      Vincular
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => onCreateIndicadorAction?.(item, indicator)}
                                      disabled={!item.id || !onCreateIndicadorAction}
                                      className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-800 disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-slate-300"
                                      title="Nova ação"
                                    >
                                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
                                      Ação
                                    </button>
                                  </div>
                                )}
                              </div>
                              );
                            })}
                          </div>
                          <div className="space-y-2">
                            <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Marcos pontuais</p>
                            {milestones.length === 0 ? (
                              <p className={`text-xs font-bold ${mutedClass}`}>Nenhum marco pontual cadastrado.</p>
                            ) : milestones.map((milestone, milestoneIndex) => (
                              <div key={milestone.id} className={`border p-2 ${softPanelClass}`}>
                                <div className="flex items-start justify-between gap-2">
                                  <span className={`text-sm font-semibold ${milestone.concluido ? 'line-through opacity-70' : ''}`}>{milestone.descricao}</span>
                                  {milestone.concluido && (
                                    <span className="rounded-lg bg-emerald-600 px-2 py-1 text-[8px] font-bold uppercase tracking-wider text-white">Concluído</span>
                                  )}
                                </div>
                                {milestone.concluido && (
                                  <p className={`mt-1 text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>
                                    Concluído em {milestone.dataConclusao ? new Date(milestone.dataConclusao).toLocaleDateString('pt-BR') : 'data não registrada'}
                                  </p>
                                )}
                                {(milestone.registros || []).slice(-2).map(record => (
                                  <p key={record.id} className={`mt-1 text-xs font-semibold ${mutedClass}`}>
                                    {new Date(record.data).toLocaleDateString('pt-BR')}: {record.nota}
                                  </p>
                                ))}
                                {!milestone.concluido && (
                                  <div className="mt-2 flex gap-2">
                                    <input
                                      value={milestoneNotes[`${item.id}:${milestone.id}`] ?? ''}
                                      onChange={(event) => setMilestoneNotes(prev => ({ ...prev, [`${item.id}:${milestone.id}`]: event.target.value }))}
                                      className={`${inputClass} text-xs`}
                                      placeholder="Evidência ou nota de conclusão"
                                    />
                                    <button
                                      onClick={() => completeMilestone(item, milestoneIndex)}
                                      className="shrink-0 rounded-lg bg-emerald-600 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white"
                                    >
                                      Concluir
                                    </button>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                          <div>
                            <p className={`text-[10px] font-bold uppercase tracking-wider ${mutedClass}`}>Diretrizes passivas</p>
                            <ul className="mt-1 space-y-1 text-sm font-semibold">{item.diretrizesDerivadas.map(directive => <li key={directive}>- {directive}</li>)}</ul>
                          </div>
                        </div>
                      )}


                    </div>
                  </div>
                  <div className="hidden">
                    <button onClick={() => { setSelectedObjectiveId(item.id || null); setEditingDraft(strategyToDraft(item)); }} className={`px-3 py-2 text-[10px] font-bold uppercase tracking-wider ${softPanelClass}`}>Editar</button>
                    <button onClick={() => setDeleteTarget(item)} className="rounded-lg bg-rose-600 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white">Excluir</button>
                  </div>
                </article>
              );
            })}
            {filteredItems.length === 0 && (
              <div className={`border p-10 text-center ${softPanelClass}`}>
                <p className={`text-sm font-bold uppercase tracking-wider ${mutedClass}`}>Nenhuma estratégia cadastrada neste filtro.</p>
              </div>
            )}
          </div>
        </section>
      </div>
      )}
    </div>
  );
};


export default StrategyDashboardView;

