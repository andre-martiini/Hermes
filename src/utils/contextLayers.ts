import type {
  ConhecimentoItem,
  ContextBundle,
  ContextLayerEntry,
  KnowledgeEdge,
  Tarefa,
} from '../../types';
import { deriveMemoryLocation, deriveTaskMemoryRoom, formatMemoryLocation } from './memoryPalace';

type BuildContextOptions = {
  task?: Tarefa | null;
  systemName?: string | null;
  knowledgeItems?: ConhecimentoItem[];
  edges?: KnowledgeEdge[];
  sessionMessages?: { role: string; content: string }[];
};

const truncate = (value?: string | null, max = 240) => {
  const text = (value || '').trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
};

export function buildContextLayers({
  task,
  systemName,
  knowledgeItems = [],
  edges = [],
  sessionMessages = [],
}: BuildContextOptions): ContextBundle {
  const identity: ContextLayerEntry[] = [];
  const session: ContextLayerEntry[] = [];
  const scoped: ContextLayerEntry[] = [];
  const deep: ContextLayerEntry[] = [];

  if (task) {
    identity.push({
      id: `task:${task.id}`,
      level: 'L0',
      label: task.titulo,
      rationale: 'Identidade permanente da ação atual.',
      source_kind: 'task',
      source_id: task.id,
      content: truncate(task.descricao || task.notas || task.titulo),
      score: 1,
    });
    identity.push({
      id: `task-room:${task.id}`,
      level: 'L0',
      label: systemName || task.sistema || task.categoria || 'Ação',
      rationale: 'Sala/projeto principal derivado da ação.',
      source_kind: 'task',
      source_id: task.id,
      content: deriveTaskMemoryRoom(task),
      score: 0.9,
    });
  }

  sessionMessages.slice(-6).forEach((msg, index) => {
    session.push({
      id: `session:${index}`,
      level: 'L1',
      label: msg.role === 'assistant' ? 'Assistente' : 'Usuário',
      rationale: 'Histórico recente da sessão.',
      source_kind: 'session',
      content: truncate(msg.content, 200),
      score: 0.7,
    });
  });

  const scopedCandidates = knowledgeItems
    .map(item => ({
      item,
      location: deriveMemoryLocation(item),
    }))
    .filter(({ item, location }) => {
      if (task?.knowledge_item_ids?.includes(item.id)) return true;
      if (task?.sistema && item.origem?.id_origem === task.sistema) return true;
      return location.room === deriveTaskMemoryRoom(task || { id: '', categoria: '', tipo_acao: undefined, sistema: undefined } as Tarefa);
    })
    .slice(0, 8);

  scopedCandidates.forEach(({ item, location }) => {
    scoped.push({
      id: `knowledge:${item.id}`,
      level: 'L2',
      label: item.titulo,
      rationale: `Contexto localizado no quarto ${formatMemoryLocation(location)}.`,
      source_kind: 'knowledge_item',
      source_id: item.id,
      content: truncate(item.resumo_tldr || item.texto_bruto),
      score: 0.75,
    });
  });

  const taskKnowledgeIds = new Set(task?.knowledge_item_ids || []);
  edges.slice(0, 12).forEach(edge => {
    if (!taskKnowledgeIds.has(edge.source_id) && !taskKnowledgeIds.has(edge.target_id)) return;
    deep.push({
      id: `edge:${edge.id}`,
      level: 'L3',
      label: `${edge.source_id} → ${edge.target_id}`,
      rationale: `Relação ${edge.relation_kind} usada para busca profunda.`,
      source_kind: 'knowledge_edge',
      source_id: edge.id,
      content: edge.notes,
      score: 0.65,
    });
  });

  return { identity, session, scoped, deep };
}
