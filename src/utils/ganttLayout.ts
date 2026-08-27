import { Tarefa, formatDateLocalISO } from '../../types';
import { hasValidTaskDate, isCompletedStatus, isStandbyStatus, normalizeStatus } from './helpers';
import { estadoDaSubtarefa, textoDaSubtarefa, visualDaEtapa } from './subtarefas';
import type { EtapaVisual } from './subtarefas';
import type { SubtarefaEstado } from '../../types';

/**
 * Layout do gráfico de Gantt das ações.
 *
 * ## De onde vem a barra
 *
 * Até 26/08/2026 a barra era o intervalo entre a DATA DE EXECUÇÃO
 * (`data_limite`) e a DATA FINAL (`prazo_final`). Como quase nada tem prazo
 * final — 589 das 603 ações que entravam no gráfico —, o resultado era um
 * campo de losangos de um dia empilhados nas mesmas colunas, não um Gantt.
 *
 * Com data por subtarefa, a barra passa a vir do **plano**: do primeiro ao
 * último dia previsto das etapas. Uma ação com sete etapas espalhadas por uma
 * semana vira uma barra de uma semana sem precisar de prazo final nenhum.
 *
 * ## Prazo final é marco, não fim de barra
 *
 * Separá-los é o que torna visível o caso em que o trabalho planejado termina
 * *depois* do prazo — que antes era normalizado. O código anterior trocava as
 * pontas quando `prazo_final` vinha antes de `data_limite`, para não desenhar
 * largura negativa; a barra saía bonita e o dado inconsistente ficava
 * invisível. Existe pelo menos uma ação assim, com prazo 20 dias antes da
 * execução. Agora a bandeira aparece onde está e a linha é sinalizada.
 *
 * ## A âncora que não desliza
 *
 * `daily_reset_job` reempurra `data_limite` para hoje toda madrugada. A borda
 * esquerda da barra, portanto, mentia: mostrava "começou hoje" para trabalho
 * arrastado há meses. `data_prevista` de subtarefa não é movida por ninguém —
 * etapa planejada para um dia que passou continua lá, atrasada à vista. É de
 * propósito: é onde a derrapagem aparece.
 *
 * Toda a aritmética de datas trabalha com strings `YYYY-MM-DD` em horário
 * local, como o resto do app (ver `formatDateLocalISO` em types.ts). Nada aqui
 * depende de React, para o cálculo poder ser testado isoladamente.
 */

export type GanttScale = 'dia' | 'semana' | 'mes';

/** O mesmo estado da subtarefa, com o nome que o Gantt usa. */
export type GanttEtapaEstado = SubtarefaEstado;

export interface GanttEtapa {
  id: string;
  texto: string;
  /** Dia previsto. Vazio quando a etapa não tem data num plano que tem. */
  data: string;
  estado: GanttEtapaEstado;
  concluida: boolean;
  /** Prevista para antes de hoje e ainda não concluída. */
  atrasada: boolean;
}

export interface GanttRow {
  task: Tarefa;
  /** Primeiro dia da linha, incluindo a bandeira de prazo quando ela vem antes. */
  inicio: string;
  /** Último dia da linha, incluindo a folga até o prazo final. */
  fim: string;
  /**
   * Extremos do trabalho planejado — do plano quando ele tem datas, senão a
   * data de execução. É a barra sólida; `inicio`/`fim` são a extensão da linha
   * inteira e podem ser maiores por causa do prazo.
   */
  inicioTrabalho: string;
  fimTrabalho: string;
  temPrazoFinal: boolean;
  /** Data do prazo final, para desenhar a bandeira. Null quando não há. */
  prazoFinal: string | null;
  /** O trabalho planejado termina depois do prazo final. */
  prazoEstourado: boolean;
  /** Prazo final anterior ao início — dado inconsistente, não é largura negativa. */
  prazoAntesDoInicio: boolean;
  /** Dias cobertos pela linha, contando as duas pontas. */
  duracaoDias: number;
  /** Um único dia e sem prazo final — desenha como marco, não como barra. */
  pontual: boolean;
  /** Etapas do plano; vazio quando o plano não tem datas próprias. */
  etapas: GanttEtapa[];
  /** A barra veio das datas do plano, e não da data de execução. */
  barraVemDoPlano: boolean;
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

/** Data válida do campo, ou string vazia. */
const dataDoCampo = (valor: unknown): string => {
  if (!hasValidTaskDate(valor as any)) return '';
  const iso = String(valor).slice(0, 10);
  return parseISO(iso) ? iso : '';
};

/**
 * Etapas posicionáveis do plano.
 *
 * Devolve vazio quando nenhuma etapa tem data própria: nesse caso todas
 * herdariam a `data_limite` e empilhariam no mesmo dia, o que é ruído e não
 * informação. Mesma distinção de `subtarefas.plano_tem_datas` no backend.
 */
export const extrairEtapas = (task: Tarefa, hoje: string): GanttEtapa[] => {
  const plano = (task as any)?.plano_acao;
  if (!Array.isArray(plano) || !plano.length) return [];
  if (!plano.some((p: any) => p && dataDoCampo(p.data_prevista))) return [];

  const etapas: GanttEtapa[] = [];
  plano.forEach((item: any, i: number) => {
    const texto = textoDaSubtarefa(item);
    if (!texto) return;
    const estado = estadoDaSubtarefa(item);
    const data = dataDoCampo(item?.data_prevista);
    etapas.push({
      id: String(item?.id || `etapa-${i}`),
      texto,
      data,
      estado,
      concluida: estado === 'feito',
      atrasada: Boolean(data) && data < hoje && estado !== 'feito',
    });
  });
  return etapas;
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

    const execucao = dataDoCampo(task.data_limite);
    if (!execucao) continue;

    const etapas = extrairEtapas(task, hoje);
    const datasDoPlano = etapas.map(e => e.data).filter(Boolean).sort();
    const barraVemDoPlano = datasDoPlano.length > 0;

    // O trabalho começa no primeiro dia previsto — incluindo a execução, para a
    // ação não sumir do dia em que ela está na lista — e termina no último.
    const inicioTrabalho = barraVemDoPlano
      ? [execucao, ...datasDoPlano].sort()[0]
      : execucao;
    const fimTrabalho = barraVemDoPlano
      ? datasDoPlano[datasDoPlano.length - 1]
      : execucao;

    const prazoValido = dataDoCampo(task.prazo_final);
    const temPrazoFinal = Boolean(prazoValido) && prazoValido !== execucao;
    const prazoFinal = temPrazoFinal ? prazoValido : null;

    // A linha se estende para cobrir o prazo, antes ou depois do trabalho. O
    // que ela NÃO faz é trocar as pontas: a barra sólida continua começando na
    // execução mesmo quando o prazo vem antes dela, e a linha é marcada como
    // inconsistente em vez de desenhar bonito e esconder o dado errado.
    const prazoAntesDoInicio = Boolean(prazoFinal) && prazoFinal! < inicioTrabalho;
    const inicioLinha = prazoAntesDoInicio ? prazoFinal! : inicioTrabalho;
    const fimLinha = prazoFinal && prazoFinal > fimTrabalho ? prazoFinal : fimTrabalho;

    const concluida = isCompletedStatus(task.status as any);
    const standby = isStandbyStatus(task.status as any);

    if (!options.incluirConcluidas && concluida) continue;
    if (options.apenasComPrazoFinal && !temPrazoFinal) continue;

    linhas.push({
      task,
      inicio: inicioLinha,
      fim: fimLinha,
      inicioTrabalho,
      fimTrabalho,
      temPrazoFinal,
      prazoFinal,
      prazoEstourado: Boolean(prazoFinal) && fimTrabalho > prazoFinal!,
      prazoAntesDoInicio,
      duracaoDias: diffDias(inicioLinha, fimLinha) + 1,
      pontual: inicioLinha === fimLinha && !temPrazoFinal,
      etapas,
      barraVemDoPlano,
      concluida,
      standby,
      atrasada: !concluida && fimLinha < hoje,
      emCurso: !concluida && inicioLinha <= hoje && fimLinha >= hoje,
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

/** Posição de um intervalo dentro da janela, em porcentagem da largura total. */
export const posicaoDoIntervalo = (inicio: string, fim: string, range: GanttRange) => {
  const offset = diffDias(range.inicio, inicio);
  const dias = diffDias(inicio, fim) + 1;
  const esquerda = (offset / range.totalDias) * 100;
  const largura = (dias / range.totalDias) * 100;
  return {
    left: `${Math.max(0, esquerda)}%`,
    width: `${Math.max(largura, 100 / range.totalDias)}%`,
  };
};

/** Posição da barra dentro da janela, em porcentagem da largura total. */
export const posicaoDaBarra = (linha: GanttRow, range: GanttRange) =>
  posicaoDoIntervalo(linha.inicio, linha.fim, range);

/**
 * Posição de um dia dentro da janela — usada para marcador de etapa e bandeira
 * de prazo. Devolve o centro da coluna do dia; `null` quando cai fora da
 * janela, para o chamador não desenhar nada em vez de desenhar na borda.
 */
export const posicaoDeData = (iso: string, range: GanttRange): string | null => {
  if (!iso || !range || iso < range.inicio || iso > range.fim) return null;
  const posicao = ((diffDias(range.inicio, iso) + 0.5) / range.totalDias) * 100;
  return `${posicao}%`;
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

export type GanttEtapaVisual = EtapaVisual;

/**
 * Aparência do marcador da etapa. A precedência mora em `visualDaEtapa`, que é
 * a mesma usada pelo plano de ação no detalhamento da ação — as duas telas
 * pintam a etapa pela mesma regra.
 */
export const statusVisualDaEtapa = (etapa: GanttEtapa): GanttEtapaVisual =>
  visualDaEtapa(etapa.estado, etapa.atrasada);
