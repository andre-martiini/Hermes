/**
 * O contrato da subtarefa do lado do navegador.
 *
 * Espelho de `functions/subtarefas.py`: mesma dedução de estado, mesmo espelho
 * de `completed`, mesma derivação de faixa. Existe porque até 27/08/2026 a
 * interface web só sabia escrever `completed` — o `estado` (`pendente`,
 * `em_andamento`, `aguardando_terceiro`, `feito`) era escrito apenas pelo
 * agente. Como a leitura só deduz de `completed` **quando `estado` não existe**,
 * marcar a caixinha numa etapa que o agente já tinha marcado deixava as duas
 * versões divergentes: a tela riscava a etapa, o Gantt continuava mostrando ela
 * aberta, e a faixa de execução era derivada do estado antigo.
 *
 * Aqui o estado é escrito e lido por uma definição só. Quem grava plano pela
 * tela passa por `comEstado`, que mantém `completed` espelhando `feito`.
 */

import type { ActionPlanItem, SubtarefaEstado } from '../../types';

export const ESTADOS: SubtarefaEstado[] = [
  'pendente',
  'em_andamento',
  'aguardando_terceiro',
  'feito',
];

/** Rótulos iguais aos do tooltip do Gantt — a mesma palavra nas duas telas. */
export const ROTULO_ESTADO: Record<SubtarefaEstado, string> = {
  pendente: 'pendente',
  em_andamento: 'em andamento',
  aguardando_terceiro: 'aguardando terceiro',
  feito: 'concluída',
};

/**
 * Aparência da etapa. `atrasada` não é estado gravado: é o cruzamento do estado
 * com a data prevista, e por isso vive só aqui.
 */
export type EtapaVisual = 'feito' | 'aguardando' | 'atrasada' | 'em_andamento' | 'pendente';

/**
 * Paleta compartilhada entre o Gantt e o plano de ação no detalhamento.
 *
 * Um lugar só de propósito: o pedido era que o plano conversasse com a
 * visualização, e duas tabelas de cor separadas divergem no primeiro ajuste.
 */
export const CORES_ETAPA: Record<EtapaVisual, { fundo: string; borda: string; texto: string; rotulo: string }> = {
  feito: { fundo: 'bg-emerald-500', borda: 'border-emerald-700', texto: 'text-emerald-500', rotulo: 'Etapa concluída' },
  aguardando: { fundo: 'bg-amber-400', borda: 'border-amber-600', texto: 'text-amber-500', rotulo: 'Aguardando terceiro' },
  atrasada: { fundo: 'bg-rose-500', borda: 'border-rose-700', texto: 'text-rose-500', rotulo: 'Etapa atrasada' },
  em_andamento: { fundo: 'bg-blue-500', borda: 'border-blue-700', texto: 'text-blue-500', rotulo: 'Etapa em andamento' },
  pendente: { fundo: 'bg-slate-300', borda: 'border-slate-500', texto: 'text-slate-400', rotulo: 'Etapa pendente' },
};

/** Hachura da etapa em espera — a diferença tem que sobreviver ao daltonismo. */
export const HACHURA_ETAPA = {
  backgroundImage:
    'repeating-linear-gradient(45deg, transparent 0 3px, rgba(255,255,255,0.55) 3px 6px)',
} as const;

/**
 * Estado da subtarefa, deduzido de `completed` quando ainda não existir.
 *
 * A dedução é o que dispensa migração: etapa anterior a 26/08/2026 com
 * `completed: true` lê como `feito`, com `completed: false` lê como `pendente`.
 */
export const estadoDaSubtarefa = (item: any): SubtarefaEstado => {
  const bruto = String(item?.estado || '').trim().toLowerCase();
  if ((ESTADOS as string[]).includes(bruto)) return bruto as SubtarefaEstado;
  return item?.completed ? 'feito' : 'pendente';
};

export const estaFeita = (item: any): boolean => estadoDaSubtarefa(item) === 'feito';

/** Texto da etapa, aceitando as duas chaves que circulam no sistema. */
export const textoDaSubtarefa = (item: any): string =>
  String(item?.text || item?.texto || '').trim();

/**
 * Precedência da aparência.
 *
 * `aguardando_terceiro` vem **antes** de `atrasada` de propósito: etapa parada
 * esperando outra pessoa passou da data sem que ninguém tenha procrastinado, e
 * pintá-la de atrasada seria a mesma confusão que o contador de degradação
 * fazia antes de 26/08/2026.
 */
export const visualDaEtapa = (estado: SubtarefaEstado, atrasada: boolean): EtapaVisual => {
  if (estado === 'feito') return 'feito';
  if (estado === 'aguardando_terceiro') return 'aguardando';
  if (atrasada) return 'atrasada';
  if (estado === 'em_andamento') return 'em_andamento';
  return 'pendente';
};

/**
 * Aparência da subtarefa crua, do jeito que o Gantt a desenharia.
 *
 * Só a data própria conta para o atraso. Etapa sem dia marcado num plano com
 * datas é a que ainda não foi posicionada — herdar a data da macroação a
 * pintaria de vermelho sem que ninguém tenha combinado dia nenhum.
 */
export const visualDaSubtarefa = (item: any, hoje: string): EtapaVisual => {
  const estado = estadoDaSubtarefa(item);
  const data = String(item?.data_prevista || '').trim().slice(0, 10);
  const atrasada = Boolean(data) && data < hoje;
  return visualDaEtapa(estado, atrasada);
};

/**
 * A etapa com o estado trocado, pronta para gravar.
 *
 * `completed` continua sendo gravado sempre, espelhando `estado === 'feito'`:
 * há leitores que só entendem ele (`UIComponents.tsx`, `morning_summary`), e
 * nenhum precisa mudar junto. `aguardando_de` só faz sentido enquanto a etapa
 * espera alguém — sair desse estado limpa o campo, senão sobra um nome preso a
 * uma espera que já acabou.
 */
export const comEstado = (
  item: ActionPlanItem,
  estado: SubtarefaEstado,
  aguardandoDe?: string,
): ActionPlanItem => {
  const saida: ActionPlanItem = { ...item, estado, completed: estado === 'feito' };
  if (estado === 'aguardando_terceiro') {
    const quem = String(aguardandoDe ?? item.aguardando_de ?? '').trim().slice(0, 200);
    if (quem) saida.aguardando_de = quem;
    else delete saida.aguardando_de;
  } else {
    delete saida.aguardando_de;
  }
  return saida;
};

/**
 * O mesmo item com o `estado` explícito que ele já tinha implicitamente.
 *
 * Serve para as telas que só sabem ligar/desligar `completed` (modais de criar
 * e editar ação): grava o que a leitura deduziria, em vez de deixar o campo
 * ausente e o próximo leitor deduzir de novo a partir de um espelho que pode
 * ter sido invertido no meio do caminho.
 */
export const comEstadoExplicito = (item: ActionPlanItem): ActionPlanItem =>
  comEstado(item, estadoDaSubtarefa(item));

/** (feitas, totais) — as etapas com texto, que são as que contam. */
export const contarSubtarefas = (plano?: ActionPlanItem[] | null): [number, number] => {
  const itens = (plano || []).filter(i => textoDaSubtarefa(i));
  return [itens.filter(estaFeita).length, itens.length];
};

export type ExecutionLane = 'avanco' | 'continuo' | 'aguardando_terceiro';

/**
 * Faixa de execução da macroação, a partir do estado das subtarefas.
 *
 * Espelho de `subtarefas.derivar_lane`. `continuo` fica de fora da derivação de
 * propósito — não há estado de subtarefa que o expresse, então um valor gravado
 * desses é respeitado como escolha de quem gravou.
 */
export const derivarLane = (
  plano?: ActionPlanItem[] | null,
  laneGravada?: string | null,
): ExecutionLane => {
  const gravada = String(laneGravada || '').trim();
  if (gravada === 'continuo') return 'continuo';

  const itens = (plano || []).filter(i => textoDaSubtarefa(i));
  const abertas = itens.filter(i => !estaFeita(i));
  if (!abertas.length) {
    return (gravada === 'avanco' || gravada === 'aguardando_terceiro' ? gravada : 'avanco');
  }

  if (abertas.some(i => estadoDaSubtarefa(i) === 'em_andamento')) return 'avanco';
  if (abertas.every(i => estadoDaSubtarefa(i) === 'aguardando_terceiro')) return 'aguardando_terceiro';
  return 'avanco';
};
