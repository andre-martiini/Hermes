import { Tarefa, formatDateLocalISO } from '../../types';
import { hasValidTaskDate, isCompletedStatus, isStandbyStatus, normalizeStatus } from './helpers';

/**
 * Layout do gráfico de Gantt das ações.
 *
 * O gráfico usa três parâmetros da ação: o título, a DATA DE EXECUÇÃO
 * (`data_limite`) e a DATA FINAL (`prazo_final`, opcional). A barra é o
 * intervalo entre as duas — ação sem prazo final vira uma barra de um dia,
 * marcada como pontual.
 *
 * Toda a aritmética de datas trabalha com strings `YYYY-MM-DD` em horário
 * local, como o resto do app (ver `formatDateLocalISO` em types.ts). Nada aqui
 * depende de React, para o cálculo poder ser testado isoladamente.
 */

export type GanttScale = 'dia' | 'semana' | 'mes';

export interface GanttRow {
  task: Tarefa;
  /** Data de execução — início da barra. */
  inicio: string;
  /** Prazo final quando existir; caso contrário, igual ao início. */
  fim: string;
  temPrazoFinal: boolean;
  /** Dias cobertos pela barra, contando as duas pontas. */
  duracaoDias: number;
  concluida: boolean;
  standby: boolean;
  /** Não concluída e com o fim já no passado. */
  atrasada: boolean;
  /** Hoje está dentro do intervalo da ação. */
  emCurso: boolean;
}

export interface GanttRange {
  inicio: string;
  fim: string;
  /** Dias do intervalo, contando as duas pontas. */
  totalDias: number;
}

export interface GanttTick {
  iso: string;
  rotulo: string;
  /** Rótulo de agrupamento (mês/ano) — usado na faixa superior da régua. */
  grupo: string;
  ehInicioDeMes: boolean;
  ehFimDeSemana: boolean;
  ehHoje: boolean;
  /** Dias representados por este tick (1 no zoom por dia, 7 por semana). */
  dias: number;
}

export interface GanttRowOptions {
  /** Data de referência para atraso/curso. Padrão: hoje. */
  hoje?: string;
  incluirConcluidas?: boolean;
  /** Mantém apenas ações que tenham prazo final além da data de execução. */
  apenasComPrazoFinal?: boolean;
}

const MS_POR_DIA = 24 * 60 * 60 * 1000;

export const hojeISO = (): string => formatDateLocalISO(new Date());

/** Converte `YYYY-MM-DD` em Date local (meio-dia evita salto por horário de verão). */
export const parseISO = (iso?: string | null): Date | null => {
  if (!hasValidTaskDate(iso)) return null;
  const partes = String(iso).slice(0, 10).split('-');
  if (partes.length !== 3) return null;
  const [ano, mes, dia] = partes.map(Number);
  if (!ano || !mes || !dia) return null;
  const data = new Date(ano, mes - 1, dia, 12, 0, 0, 0);
  return isNaN(data.getTime()) ? null : data;
};

/** Dias de `de` até `ate` (negativo quando `ate` é anterior). */
export const diffDias = (de: string, ate: string): number => {
  const inicio = parseISO(de);
  const fim = parseISO(ate);
  if (!inicio || !fim) return 0;
  return Math.round((fim.getTime() - inicio.getTime()) / MS_POR_DIA);
};

export const addDias = (iso: string, dias: number): string => {
  const data = parseISO(iso);
  if (!data) return iso;
  data.setDate(data.getDate() + dias);
  return formatDateLocalISO(data);
};

/** Segunda-feira da semana do ISO informado (semana começa no domingo no app). */
export const inicioDaSemana = (iso: string): string => {
  const data = parseISO(iso);
  if (!data) return iso;
  return addDias(iso, -data.getDay());
};

export const inicioDoMes = (iso: string): string => `${iso.slice(0, 7)}-01`;

const rotuloMes = (iso: string): string => {
  const data = parseISO(iso);
  if (!data) return '';
  const nome = new Intl.DateTimeFormat('pt-BR', { month: 'short' }).format(data).replace('.', '');
  return `${nome.charAt(0).toUpperCase()}${nome.slice(1)} ${data.getFullYear()}`;
};

/**
 * Monta uma linha por ação elegível — precisa de data de execução válida e não
 * pode estar excluída. Ordena pela data de execução e, no empate, pela ação que
 * termina antes.
 */
export const buildGanttRows = (tasks: Tarefa[], options: GanttRowOptions = {}): GanttRow[] => {
  const hoje = options.hoje || hojeISO();
  const linhas: GanttRow[] = [];

  for (const task of tasks || []) {
    if (!task) continue;
    if (normalizeStatus(task.status as any) === 'excluido') continue;

    const inicio = hasValidTaskDate(task.data_limite) ? String(task.data_limite).slice(0, 10) : '';
    if (!inicio || !parseISO(inicio)) continue;

    const prazoBruto = hasValidTaskDate(task.prazo_final) ? String(task.prazo_final).slice(0, 10) : '';
    const prazoValido = prazoBruto && parseISO(prazoBruto) ? prazoBruto : '';
    // Prazo anterior à execução é dado inconsistente: a barra usa o intervalo
    // real entre as duas datas em vez de largura negativa.
    const temPrazoFinal = Boolean(prazoValido) && prazoValido !== inicio;
    const inicioBarra = temPrazoFinal && prazoValido < inicio ? prazoValido : inicio;
    const fimBarra = temPrazoFinal ? (prazoValido < inicio ? inicio : prazoValido) : inicio;

    const concluida = isCompletedStatus(task.status as any);
    const standby = isStandbyStatus(task.status as any);

    if (!options.incluirConcluidas && concluida) continue;
    if (options.apenasComPrazoFinal && !temPrazoFinal) continue;

    linhas.push({
      task,
      inicio: inicioBarra,
      fim: fimBarra,
      temPrazoFinal,
      duracaoDias: diffDias(inicioBarra, fimBarra) + 1,
      concluida,
      standby,
      atrasada: !concluida && fimBarra < hoje,
      emCurso: !concluida && inicioBarra <= hoje && fimBarra >= hoje,
    });
  }

  return linhas.sort((a, b) => {
    if (a.inicio !== b.inicio) return a.inicio.localeCompare(b.inicio);
    if (a.fim !== b.fim) return a.fim.localeCompare(b.fim);
    return (a.task.titulo || '').localeCompare(b.task.titulo || '', 'pt-BR');
  });
};

/**
 * Janela de tempo do gráfico: cobre todas as barras e sempre inclui hoje, para
 * a linha do dia atual nunca ficar fora da tela. Arredonda para semanas cheias.
 */
export const buildGanttRange = (linhas: GanttRow[], hoje: string = hojeISO()): GanttRange | null => {
  if (!linhas.length) return null;

  let inicio = linhas[0].inicio;
  let fim = linhas[0].fim;
  for (const linha of linhas) {
    if (linha.inicio < inicio) inicio = linha.inicio;
    if (linha.fim > fim) fim = linha.fim;
  }
  if (hoje < inicio) inicio = hoje;
  if (hoje > fim) fim = hoje;

  inicio = inicioDaSemana(addDias(inicio, -1));
  fim = addDias(inicioDaSemana(addDias(fim, 1)), 6);

  return { inicio, fim, totalDias: diffDias(inicio, fim) + 1 };
};

/** Colunas da régua superior, conforme o zoom escolhido. */
export const buildGanttTicks = (range: GanttRange, escala: GanttScale, hoje: string = hojeISO()): GanttTick[] => {
  const ticks: GanttTick[] = [];
  if (!range || range.totalDias <= 0) return ticks;

  if (escala === 'mes') {
    let cursor = inicioDoMes(range.inicio);
    while (cursor <= range.fim) {
      const proximo = addDias(`${addDias(cursor, 31).slice(0, 7)}-01`, 0);
      const inicioVisivel = cursor < range.inicio ? range.inicio : cursor;
      const fimVisivel = addDias(proximo, -1) > range.fim ? range.fim : addDias(proximo, -1);
      ticks.push({
        iso: inicioVisivel,
        rotulo: rotuloMes(cursor),
        grupo: String(parseISO(cursor)?.getFullYear() || ''),
        ehInicioDeMes: true,
        ehFimDeSemana: false,
        ehHoje: hoje >= inicioVisivel && hoje <= fimVisivel,
        dias: diffDias(inicioVisivel, fimVisivel) + 1,
      });
      cursor = proximo;
    }
    return ticks;
  }

  const passo = escala === 'semana' ? 7 : 1;
  let cursor = escala === 'semana' ? inicioDaSemana(range.inicio) : range.inicio;
  while (cursor <= range.fim) {
    const data = parseISO(cursor);
    const fimDoTick = addDias(cursor, passo - 1);
    const fimVisivel = fimDoTick > range.fim ? range.fim : fimDoTick;
    ticks.push({
      iso: cursor,
      rotulo: escala === 'semana'
        ? `${cursor.slice(8, 10)}/${cursor.slice(5, 7)}`
        : String(data?.getDate() ?? ''),
      grupo: rotuloMes(cursor),
      ehInicioDeMes: cursor.slice(8, 10) === '01',
      ehFimDeSemana: escala === 'dia' && (data?.getDay() === 0 || data?.getDay() === 6),
      ehHoje: hoje >= cursor && hoje <= fimVisivel,
      dias: diffDias(cursor, fimVisivel) + 1,
    });
    cursor = addDias(cursor, passo);
  }
  return ticks;
};

/** Posição da barra dentro da janela, em porcentagem da largura total. */
export const posicaoDaBarra = (linha: GanttRow, range: GanttRange) => {
  const offset = diffDias(range.inicio, linha.inicio);
  const esquerda = (offset / range.totalDias) * 100;
  const largura = (linha.duracaoDias / range.totalDias) * 100;
  return {
    left: `${Math.max(0, esquerda)}%`,
    width: `${Math.max(largura, 100 / range.totalDias)}%`,
  };
};

/** Posição da linha de "hoje" — null quando hoje está fora da janela. */
export const posicaoDeHoje = (range: GanttRange, hoje: string = hojeISO()): string | null => {
  if (!range || hoje < range.inicio || hoje > range.fim) return null;
  // Meio do dia atual, para a linha cair no centro da coluna.
  const posicao = ((diffDias(range.inicio, hoje) + 0.5) / range.totalDias) * 100;
  return `${posicao}%`;
};

export type GanttStatusVisual = 'concluida' | 'atrasada' | 'standby' | 'andamento';

export const statusVisualDaLinha = (linha: GanttRow): GanttStatusVisual => {
  if (linha.concluida) return 'concluida';
  if (linha.atrasada) return 'atrasada';
  if (linha.standby) return 'standby';
  return 'andamento';
};
