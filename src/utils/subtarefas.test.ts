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
  comEstado,
  comEstadoExplicito,
  contarSubtarefas,
  derivarLane,
  estaFeita,
  estadoDaSubtarefa,
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
