/**
 * O que este arquivo protege: a tela e o Gantt lendo a mesma etapa do mesmo
 * jeito.
 *
 * O bug que originou o módulo era silencioso — marcar a caixinha gravava
 * `completed: true` sem tocar em `estado`, e como a leitura só deduz de
 * `completed` quando `estado` falta, a etapa ficava concluída na tela e aberta
 * no Gantt, na faixa de execução e para o agente. Nada quebrava; só divergia.
 */
import { describe, expect, it } from 'vitest';

import {
  LIMITE_EXECUTOR_COMO,
  dataPrevistaDe,
  subtarefaCorrente,
  ROTULO_EXECUTOR,
  comEstado,
  comEstadoExplicito,
  comExecutor,
  comExecutorNoPlano,
  contarParaAgente,
  contarSubtarefas,
  derivarLane,
  eDoAgente,
  estaFeita,
  estadoDaSubtarefa,
  executorDaEtapa,
  visualDaEtapa,
  visualDaSubtarefa,
} from './subtarefas';

const etapa = (over: Record<string, any> = {}) => ({
  id: over.id || 'e1',
  text: over.text ?? 'Passo',
  completed: over.completed ?? false,
  ...over,
}) as any;

describe('estadoDaSubtarefa', () => {
  it('deduz de completed nas etapas anteriores a 26/08/2026', () => {
    expect(estadoDaSubtarefa(etapa({ completed: true }))).toBe('feito');
    expect(estadoDaSubtarefa(etapa({ completed: false }))).toBe('pendente');
  });

  it('o estado gravado manda sobre o espelho', () => {
    expect(estadoDaSubtarefa(etapa({ completed: false, estado: 'em_andamento' }))).toBe('em_andamento');
    expect(estadoDaSubtarefa(etapa({ completed: true, estado: 'aguardando_terceiro' }))).toBe('aguardando_terceiro');
  });

  it('estado inválido cai na dedução, em vez de vazar para a tela', () => {
    expect(estadoDaSubtarefa(etapa({ completed: true, estado: 'xpto' }))).toBe('feito');
  });
});

describe('comEstado', () => {
  it('mantém completed espelhando feito — é o que os leitores antigos leem', () => {
    const feito = comEstado(etapa({ estado: 'em_andamento' }), 'feito');
    expect(feito.completed).toBe(true);
    expect(feito.estado).toBe('feito');

    const reaberta = comEstado(feito, 'pendente');
    expect(reaberta.completed).toBe(false);
    expect(reaberta.estado).toBe('pendente');
  });

  it('guarda de quem se espera e limpa quando a espera acaba', () => {
    const esperando = comEstado(etapa(), 'aguardando_terceiro', 'Fulano');
    expect(esperando.aguardando_de).toBe('Fulano');

    const retomada = comEstado(esperando, 'em_andamento');
    expect(retomada.aguardando_de).toBeUndefined();
  });

  it('preserva o nome já gravado quando nenhum novo é passado', () => {
    const esperando = comEstado(etapa({ aguardando_de: 'Ciclana' }), 'aguardando_terceiro');
    expect(esperando.aguardando_de).toBe('Ciclana');
  });

  it('preserva campos que não são deste contrato', () => {
    const saida: any = comEstado(etapa({ data_prevista: '2026-09-01', degradation_count: 3 }), 'feito');
    expect(saida.data_prevista).toBe('2026-09-01');
    expect(saida.degradation_count).toBe(3);
  });

  it('comEstadoExplicito grava o estado que a leitura já deduzia', () => {
    expect(comEstadoExplicito(etapa({ completed: true })).estado).toBe('feito');
    expect(comEstadoExplicito(etapa({ completed: false })).estado).toBe('pendente');
  });
});

describe('visualDaEtapa', () => {
  it('aguardando terceiro vem antes de atrasada — espera não é procrastinação', () => {
    expect(visualDaEtapa('aguardando_terceiro', true)).toBe('aguardando');
  });

  it('concluída nunca aparece atrasada', () => {
    expect(visualDaEtapa('feito', true)).toBe('feito');
  });

  it('atrasada vence em andamento e pendente', () => {
    expect(visualDaEtapa('em_andamento', true)).toBe('atrasada');
    expect(visualDaEtapa('pendente', true)).toBe('atrasada');
  });
});

describe('visualDaSubtarefa', () => {
  const HOJE = '2026-08-27';

  it('etapa com dia vencido e aberta fica atrasada', () => {
    expect(visualDaSubtarefa(etapa({ data_prevista: '2026-08-20' }), HOJE)).toBe('atrasada');
  });

  it('etapa sem dia marcado não é atrasada — ninguém combinou dia nenhum', () => {
    expect(visualDaSubtarefa(etapa({ estado: 'em_andamento' }), HOJE)).toBe('em_andamento');
    expect(visualDaSubtarefa(etapa(), HOJE)).toBe('pendente');
  });

  it('etapa de hoje ainda não está atrasada', () => {
    expect(visualDaSubtarefa(etapa({ data_prevista: HOJE }), HOJE)).toBe('pendente');
  });
});

describe('contarSubtarefas', () => {
  it('conta pelo estado, não pelo espelho, e ignora etapa sem texto', () => {
    const plano = [
      etapa({ id: 'a', completed: true }),
      etapa({ id: 'b', completed: true, estado: 'em_andamento' }),
      etapa({ id: 'c', text: '   ' }),
    ];
    expect(contarSubtarefas(plano)).toEqual([1, 2]);
  });

  it('plano vazio não divide por zero', () => {
    expect(contarSubtarefas([])).toEqual([0, 0]);
    expect(contarSubtarefas(null)).toEqual([0, 0]);
  });
});

describe('derivarLane', () => {
  it('uma etapa em andamento põe a ação em avanço', () => {
    const plano = [
      etapa({ id: 'a', estado: 'aguardando_terceiro' }),
      etapa({ id: 'b', estado: 'em_andamento' }),
    ];
    expect(derivarLane(plano, 'avanco')).toBe('avanco');
  });

  it('só quando todas as abertas esperam terceiro a ação espera', () => {
    const plano = [
      etapa({ id: 'a', estado: 'feito', completed: true }),
      etapa({ id: 'b', estado: 'aguardando_terceiro' }),
    ];
    expect(derivarLane(plano, 'avanco')).toBe('aguardando_terceiro');
  });

  it('plano todo pendente continua em avanço — o caso comum de hoje', () => {
    expect(derivarLane([etapa({ id: 'a' })], 'avanco')).toBe('avanco');
  });

  it('contínuo é escolha de quem gravou e não é sobrescrito', () => {
    expect(derivarLane([etapa({ id: 'a', estado: 'aguardando_terceiro' })], 'continuo')).toBe('continuo');
  });

  it('sem etapa aberta mantém a faixa gravada', () => {
    const plano = [etapa({ id: 'a', estado: 'feito', completed: true })];
    expect(derivarLane(plano, 'aguardando_terceiro')).toBe('aguardando_terceiro');
    expect(derivarLane(plano, undefined)).toBe('avanco');
  });

  it('etapa sem texto não segura a faixa', () => {
    const plano = [
      etapa({ id: 'a', estado: 'feito', completed: true }),
      etapa({ id: 'b', text: '', estado: 'aguardando_terceiro' }),
    ];
    expect(derivarLane(plano, 'avanco')).toBe('avanco');
  });
});

describe('estaFeita', () => {
  it('é a mesma pergunta que o backend faz', () => {
    expect(estaFeita(etapa({ completed: true }))).toBe(true);
    expect(estaFeita(etapa({ completed: true, estado: 'em_andamento' }))).toBe(false);
  });
});

describe('executor da etapa', () => {
  const plano = () => [
    etapa({ id: 'a1', executor: 'agente', executor_como: 'Ler e resumir', executor_definido_por: 'agente' }),
    etapa({ id: 'a2', executor: 'agente_aprovado' }),
    etapa({ id: 'a3' }),
    etapa({ id: 'a4', executor: 'humano', executor_definido_por: 'usuario' }),
    etapa({ id: 'a5', executor: 'agente', completed: true, estado: 'feito' }),
  ];

  it('ausente e desconhecido leem como humano — nunca viram etiqueta', () => {
    expect(executorDaEtapa(etapa())).toBe('humano');
    expect(executorDaEtapa(etapa({ executor: 'claude' }))).toBe('humano');
    expect(executorDaEtapa(etapa({ executor: ' AGENTE ' }))).toBe('agente');
    expect(eDoAgente(etapa({ executor: 'claude' }))).toBe(false);
  });

  it('conta só etapa em aberto que o agente faz ou prepara', () => {
    expect(contarParaAgente(plano())).toBe(2);
    expect(contarParaAgente(null)).toBe(0);
    expect(contarParaAgente([etapa({ text: '', executor: 'agente' })])).toBe(0);
  });

  it('o contador acompanha a etapa concluída, sem número gravado', () => {
    const p = plano();
    p[0] = comEstado(p[0], 'feito');
    expect(contarParaAgente(p)).toBe(1);
  });

  it('comEstado preserva os três campos — marcar feita não apaga a marca', () => {
    const feita = comEstado(plano()[0], 'feito');
    expect(feita.executor).toBe('agente');
    expect(feita.executor_como).toBe('Ler e resumir');
    expect(feita.executor_definido_por).toBe('agente');
    expect(comEstadoExplicito(plano()[3]).executor_definido_por).toBe('usuario');
  });

  it('a correção do André grava executor_definido_por: usuario', () => {
    const corrigida = comExecutor(plano()[0], 'humano');
    expect(corrigida.executor).toBe('humano');
    expect(corrigida.executor_definido_por).toBe('usuario');
    // Etapa que passa a ser só do André perde a frase "como o agente faria".
    expect(corrigida.executor_como).toBeUndefined();
  });

  it('mantém e limita executor_como quando a etapa continua com o agente', () => {
    const longa = comExecutor(etapa({ executor_como: 'a'.repeat(200) }), 'agente_aprovado');
    expect(longa.executor_como).toHaveLength(LIMITE_EXECUTOR_COMO);
    expect(longa.executor).toBe('agente_aprovado');
  });

  it('comExecutorNoPlano troca só a etapa pedida', () => {
    const antes = plano();
    const depois = comExecutorNoPlano(antes, 'a3', 'agente');
    expect(depois[2].executor).toBe('agente');
    expect(depois[2].executor_definido_por).toBe('usuario');
    expect(depois[0]).toBe(antes[0]);
    expect(depois[3]).toBe(antes[3]);
    expect(depois).toHaveLength(antes.length);
  });

  it('as etiquetas dizem o que o agente faz', () => {
    expect(ROTULO_EXECUTOR.agente).toBe('Agente faz');
    expect(ROTULO_EXECUTOR.agente_aprovado).toBe('Agente prepara, você aprova');
  });
});

describe('subtarefaCorrente — mesma etapa que o backend escolhe', () => {
  const e = (id: string, extra: Record<string, any> = {}) => etapa({ id, text: `Passo ${id}`, ...extra });

  it('plano sem datas: a primeira em aberto, herdando a data da ação', () => {
    const plano = [e('a', { completed: true, estado: 'feito' }), e('b'), e('c')];
    expect(subtarefaCorrente(plano, '2026-10-27')?.id).toBe('b');
  });

  it('a de menor data ganha da primeira da lista', () => {
    const plano = [e('a', { data_prevista: '2026-10-30' }), e('b', { data_prevista: '2026-10-28' })];
    expect(subtarefaCorrente(plano, '2026-10-27')?.id).toBe('b');
  });

  it('plano misto: a etapa sem data vai para o fim, não para a frente', () => {
    const plano = [e('a'), e('b', { data_prevista: '2026-10-29' })];
    expect(subtarefaCorrente(plano, '2026-10-27')?.id).toBe('b');
    expect(dataPrevistaDe(plano[0], '2026-10-27', plano)).toBe('');
  });

  it('empate resolve pela ordem do plano', () => {
    const plano = [e('a', { data_prevista: '2026-10-28' }), e('b', { data_prevista: '2026-10-28' })];
    expect(subtarefaCorrente(plano, null)?.id).toBe('a');
  });

  it('tudo feito: nenhuma', () => {
    expect(subtarefaCorrente([e('a', { completed: true, estado: 'feito' })], '2026-10-27')).toBeNull();
    expect(subtarefaCorrente([], '2026-10-27')).toBeNull();
  });

  it('a espera decide pela etapa corrente, não pela primeira da lista', () => {
    const plano = [
      e('a', { estado: 'aguardando_terceiro', aguardando_de: 'FAPES', data_prevista: '2026-10-30' }),
      e('b', { data_prevista: '2026-10-28' }),
    ];
    expect(estadoDaSubtarefa(subtarefaCorrente(plano, '2026-10-27')!)).toBe('pendente');
  });
});
