import { useState, useMemo, useCallback } from 'react';
import { doc, updateDoc, arrayUnion } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { PlanoTrabalho, PlanoTrabalhoItem, Tarefa, EntregaInstitucional } from '@/types';
import { buildHeuristicPgdSuggestions, PgdMatchResult } from './pgdLinkHeuristics';

interface UsePgdSmartLinkingProps {
  currentPlan: PlanoTrabalho | undefined;
  pgcTasksAguardando: Tarefa[];
  pgcEntregas: EntregaInstitucional[];
  handleCreateEntregaFromPlan: (item: PlanoTrabalhoItem) => Promise<string | null>;
  handleLinkTarefa: (tarefaId: string, entregaId: string) => Promise<void>;
  showToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
  functions: any;
  db: any;
}

export function usePgdSmartLinking({
  currentPlan,
  pgcTasksAguardando,
  pgcEntregas,
  handleCreateEntregaFromPlan,
  handleLinkTarefa,
  showToast,
  functions,
  db,
}: UsePgdSmartLinkingProps) {
  const [pgdAiSuggestions, setPgdAiSuggestions] = useState<
    Record<string, { itemIndex: number; confidence: number; motivo: string }>
  >({});
  const [pgdDismissedTaskIds, setPgdDismissedTaskIds] = useState<Set<string>>(new Set());
  const [isSuggestingPgdAI, setIsSuggestingPgdAI] = useState(false);
  const [confirmingTaskIds, setConfirmingTaskIds] = useState<Set<string>>(new Set());

  // Heurística local de sugestões de entregas para tarefas pendentes
  const pgdHeuristicSuggestions = useMemo(() => {
    if (!currentPlan?.itens || currentPlan.itens.length === 0) return {};
    return buildHeuristicPgdSuggestions(pgcTasksAguardando, currentPlan.itens);
  }, [pgcTasksAguardando, currentPlan]);

  // Combina sugestões da IA e Heurística (IA tem precedência)
  const combinedPgdSuggestions = useMemo(() => {
    const combined: Record<string, PgdMatchResult> = {};
    const items = currentPlan?.itens || [];

    // 1. Aplica heurística básica primeiro
    Object.entries(pgdHeuristicSuggestions).forEach(([taskId, heur]) => {
      if (!pgdDismissedTaskIds.has(taskId)) {
        combined[taskId] = heur;
      }
    });

    // 2. Sobrescreve com sugestões da IA se houver
    Object.entries(pgdAiSuggestions).forEach(([taskId, ai]) => {
      if (!pgdDismissedTaskIds.has(taskId) && items[ai.itemIndex]) {
        combined[taskId] = {
          item: items[ai.itemIndex],
          confidence: ai.confidence,
          motivo: ai.motivo,
          origem: 'ia',
        };
      }
    });

    return combined;
  }, [currentPlan, pgdHeuristicSuggestions, pgdAiSuggestions, pgdDismissedTaskIds]);

  // Contagem de sugestões por entrega
  const suggestedCountForDeliverable = useMemo(() => {
    const counts: Record<string, number> = {};
    Object.values(combinedPgdSuggestions).forEach((sugg) => {
      const key = sugg.item.entrega;
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [combinedPgdSuggestions]);

  // Confirmar sugestão individual
  const handleConfirmPgdSuggestion = useCallback(
    async (taskId: string, item: PlanoTrabalhoItem) => {
      try {
        setConfirmingTaskIds((prev) => new Set(prev).add(taskId));
        let targetId = pgcEntregas.find((e) => e.entrega === item.entrega)?.id;
        if (!targetId) {
          targetId = (await handleCreateEntregaFromPlan(item)) || undefined;
        }
        if (targetId) {
          await handleLinkTarefa(taskId, targetId);
        }
      } finally {
        setConfirmingTaskIds((prev) => {
          const next = new Set(prev);
          next.delete(taskId);
          return next;
        });
      }
    },
    [pgcEntregas, handleCreateEntregaFromPlan, handleLinkTarefa]
  );

  // Dispensar sugestão individual
  const handleDismissPgdSuggestion = useCallback(
    (taskId: string) => {
      setPgdDismissedTaskIds((prev) => new Set(prev).add(taskId));
      showToast('Sugestao dispensada.', 'info');
    },
    [showToast]
  );

  // Confirmar todas as sugestões em lote
  const handleBatchConfirmPgdSuggestions = useCallback(async () => {
    const entries = Object.entries(combinedPgdSuggestions);
    if (entries.length === 0) return;

    try {
      showToast(`Vinculando ${entries.length} acao(oes)...`, 'info');
      for (const [taskId, sugg] of entries) {
        setConfirmingTaskIds((prev) => new Set(prev).add(taskId));
        let targetId = pgcEntregas.find((e) => e.entrega === sugg.item.entrega)?.id;
        if (!targetId) {
          targetId = (await handleCreateEntregaFromPlan(sugg.item)) || undefined;
        }
        if (targetId) {
          const docRef = doc(db, 'tarefas', taskId);
          await updateDoc(docRef, {
            entregas_relacionadas: arrayUnion(targetId),
          });
        }
      }
      showToast(`${entries.length} acoes vinculadas com sucesso!`, 'success');
    } catch (err) {
      console.error('Erro ao vincular em lote:', err);
      showToast('Erro ao vincular algumas acoes.', 'error');
    } finally {
      setConfirmingTaskIds(new Set());
    }
  }, [combinedPgdSuggestions, pgcEntregas, handleCreateEntregaFromPlan, db, showToast]);

  // Executar IA para sugerir vínculos
  const handleRunPgdAI = useCallback(async () => {
    const items = currentPlan?.itens || [];
    if (items.length === 0) {
      showToast('Nenhum plano de trabalho cadastrado para este mes.', 'error');
      return;
    }
    if (pgcTasksAguardando.length === 0) {
      showToast('Nao ha acoes pendentes para analisar.', 'info');
      return;
    }

    try {
      setIsSuggestingPgdAI(true);
      const fn = httpsCallable(functions, 'suggestPgdTaskLinksAI');
      const payloadTasks = pgcTasksAguardando.map((t) => ({
        id: t.id,
        titulo: t.titulo,
        projeto: t.projeto || '',
        area_tematica: t.area_tematica || '',
        tags: t.tags || [],
        notas: t.notas || '',
      }));
      const payloadEntregas = items.map((it, index) => ({
        index,
        entrega: it.entrega,
        descricao: it.descricao || '',
        unidade: it.unidade || '',
        origem: it.origem || '',
      }));

      const res = await fn({ tasks: payloadTasks, entregas: payloadEntregas });
      const data = res.data as {
        matches?: Array<{
          task_id: string;
          entrega_index: number;
          confidence: number;
          motivo: string;
        }>;
      };
      const matches = data?.matches || [];

      if (matches.length === 0) {
        showToast('Nenhum novo vinculo sugerido pela IA.', 'info');
        return;
      }

      const nextAiMap: Record<string, { itemIndex: number; confidence: number; motivo: string }> = {};
      matches.forEach((m) => {
        if (m.task_id && m.entrega_index !== undefined && m.confidence >= 0.5) {
          nextAiMap[m.task_id] = {
            itemIndex: m.entrega_index,
            confidence: m.confidence,
            motivo: m.motivo,
          };
        }
      });
      setPgdAiSuggestions((prev) => ({ ...prev, ...nextAiMap }));
      showToast(`${matches.length} sugestao(oes) gerada(s) com IA!`, 'success');
    } catch (err: any) {
      console.error('Erro ao sugerir vinculos com IA:', err);
      showToast(err?.message || 'Erro ao consultar IA para sugestoes.', 'error');
    } finally {
      setIsSuggestingPgdAI(false);
    }
  }, [currentPlan, pgcTasksAguardando, functions, showToast]);

  return {
    combinedPgdSuggestions,
    suggestedCountForDeliverable,
    isSuggestingPgdAI,
    confirmingTaskIds,
    handleConfirmPgdSuggestion,
    handleDismissPgdSuggestion,
    handleBatchConfirmPgdSuggestions,
    handleRunPgdAI,
  };
}
