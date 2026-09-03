import { PlanoTrabalhoItem, Tarefa } from '@/types';

const STOP_WORDS = new Set([
  'de', 'a', 'o', 'que', 'e', 'do', 'da', 'em', 'um', 'para', 'com', 'nao',
  'uma', 'os', 'no', 'se', 'na', 'por', 'mais', 'as', 'dos', 'como', 'mas',
  'ao', 'ele', 'das', 'sua', 'seu', 'ou', 'quando', 'muito', 'nos', 'ja',
  'eu', 'tambem', 'so', 'pelo', 'pela', 'ate', 'isso', 'ela', 'entre',
  'depois', 'sem', 'mesmo', 'aos', 'seus', 'quem', 'nas', 'me', 'esse',
  'eles', 'voce', 'essa', 'num', 'nem', 'suas', 'meu', 'as', 'minha',
  'numa', 'pelos', 'elas', 'qual', 'nos', 'lhe', 'deles', 'essas', 'esses',
  'pelas', 'este', 'dele', 'tu', 'te', 'voces', 'vos', 'lhes', 'meus',
  'minhas', 'teu', 'tua', 'teus', 'tuas', 'nosso', 'nossa', 'nossos', 'nossas',
  'dela', 'delas', 'esta', 'estes', 'estas', 'aquele', 'aquela', 'aqueles',
  'aquelas', 'isto', 'aquilo', 'estou', 'esta', 'estamos', 'estao', 'estive'
]);

function normalizeText(text: string): string {
  return (text || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .trim();
}

function extractKeywords(text: string): string[] {
  const norm = normalizeText(text);
  return Array.from(
    new Set(
      norm
        .split(/\s+/)
        .map(w => w.trim())
        .filter(w => w.length >= 3 && !STOP_WORDS.has(w))
    )
  );
}

export interface PgdMatchResult {
  item: PlanoTrabalhoItem;
  confidence: number;
  motivo: string;
  origem: 'heuristica' | 'ia';
}

/**
 * Calcula a melhor correspondência heurística entre uma tarefa e as entregas disponíveis do plano.
 */
export function findBestHeuristicMatch(
  task: Tarefa,
  items: PlanoTrabalhoItem[]
): PgdMatchResult | null {
  if (!task || !items || items.length === 0) return null;

  const taskTitleNorm = normalizeText(task.titulo);
  const taskProjectNorm = normalizeText(task.projeto || '');
  const taskAreaNorm = normalizeText(task.area_tematica || '');
  const taskNotesNorm = normalizeText(task.notas || '');
  const taskKeywords = extractKeywords(`${task.titulo} ${task.projeto || ''} ${task.area_tematica || ''} ${(task.tags || []).join(' ')}`);

  let bestItem: PlanoTrabalhoItem | null = null;
  let highestScore = 0;
  let bestReasons: string[] = [];

  for (const item of items) {
    let score = 0;
    const reasons: string[] = [];

    const itemEntregaNorm = normalizeText(item.entrega);
    const itemDescNorm = normalizeText(item.descricao || '');
    const itemUnidadeNorm = normalizeText(item.unidade || '');
    const itemOrigemNorm = normalizeText(item.origem || '');
    const itemFullText = `${itemEntregaNorm} ${itemDescNorm} ${itemUnidadeNorm} ${itemOrigemNorm}`;
    const itemKeywords = new Set(extractKeywords(itemFullText));

    // 1. Afinidade com CLC / Compras / Licitações
    const isTaskClc =
      taskAreaNorm.includes('clc') ||
      taskProjectNorm.includes('clc') ||
      taskKeywords.some(k => ['licitacao', 'pregao', 'dispensa', 'contrato', 'compras'].includes(k));

    const isItemClc =
      itemUnidadeNorm.includes('clc') ||
      itemKeywords.has('clc') ||
      itemKeywords.has('licitacao') ||
      itemKeywords.has('pregao') ||
      itemKeywords.has('compras');

    if (isTaskClc && isItemClc) {
      score += 45;
      reasons.push('Afinidade com CLC / Compras');
    }

    // 2. Afinidade com Assistência Estudantil / DAE / Bolsas / SISNAES
    const isTaskAssist =
      taskAreaNorm.includes('assist') ||
      taskProjectNorm.includes('assist') ||
      taskKeywords.some(k => ['sispnaes', 'dae', 'bolsa', 'auxilio', 'alimentacao', 'moradia', 'edital'].includes(k));

    const isItemAssist =
      itemUnidadeNorm.includes('dae') ||
      itemKeywords.has('assistencia') ||
      itemKeywords.has('estudantil') ||
      itemKeywords.has('dae') ||
      itemKeywords.has('bolsa') ||
      itemKeywords.has('auxilio');

    if (isTaskAssist && isItemAssist) {
      score += 45;
      reasons.push('Afinidade com Assistência Estudantil / DAE');
    }

    // 3. Cruzamento de palavras-chave do título
    const matchingWords: string[] = [];
    for (const kw of taskKeywords) {
      if (itemKeywords.has(kw)) {
        score += 12;
        matchingWords.push(kw);
      }
    }

    if (matchingWords.length > 0) {
      reasons.push(`Termos em comum: ${matchingWords.slice(0, 3).join(', ')}`);
    }

    // 4. Bônus para correspondência exata de processo / edital / relatório
    if (taskTitleNorm.includes('edital') && itemFullText.includes('edital')) {
      score += 15;
    }
    if (taskTitleNorm.includes('relatorio') && itemFullText.includes('relatorio')) {
      score += 15;
    }

    if (score > highestScore) {
      highestScore = score;
      bestItem = item;
      bestReasons = reasons;
    }
  }

  // Ponto de corte para considerar correspondência válida
  if (!bestItem || highestScore < 35) {
    return null;
  }

  // Normalização de confiança de 0.60 a 0.95
  const confidence = Math.min(0.95, Math.max(0.6, Math.round((highestScore / 80) * 100) / 100));
  const motivo = bestReasons.join(' · ') || 'Correspondência de palavras-chave';

  return {
    item: bestItem,
    confidence,
    motivo,
    origem: 'heuristica',
  };
}

/**
 * Mapeia uma lista de tarefas pendentes gerando um dicionário de sugestões por tarefaId.
 */
export function buildHeuristicPgdSuggestions(
  tasks: Tarefa[],
  items: PlanoTrabalhoItem[]
): Record<string, PgdMatchResult> {
  const result: Record<string, PgdMatchResult> = {};
  if (!tasks || !items) return result;

  for (const task of tasks) {
    const match = findBestHeuristicMatch(task, items);
    if (match) {
      result[task.id] = match;
    }
  }

  return result;
}
