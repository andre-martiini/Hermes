import { describe, it, expect } from 'vitest';
import { findBestHeuristicMatch, buildHeuristicPgdSuggestions } from './pgdLinkHeuristics';
import { PlanoTrabalhoItem, Tarefa } from '@/types';

describe('pgdLinkHeuristics', () => {
  const planItems: PlanoTrabalhoItem[] = [
    {
      entrega: 'Relatórios de Gestão e Monitoramento da Assistência Estudantil',
      descricao: 'Elaboração e acompanhamento dos relatórios do Sispnaes e bolsas da DAE',
      unidade: 'DAE',
      origem: 'Plano de Trabalho',
      meta: 10,
    },
    {
      entrega: 'Instrução e Tramitação de Processos Licitatórios',
      descricao: 'Elaboração de termos de referência, minutas de editais e compras públicas da CLC',
      unidade: 'CLC',
      origem: 'Plano de Trabalho',
      meta: 15,
    },
  ];

  it('deve vincular ação de CLC à entrega de processos licitatórios', () => {
    const task: Partial<Tarefa> = {
      id: 'task-1',
      titulo: 'Revisar termo de referência para pregão de materiais',
      area_tematica: 'CLC',
      projeto: 'Licitações',
      tags: ['pregao', 'compras'],
    };

    const match = findBestHeuristicMatch(task as Tarefa, planItems);
    expect(match).not.toBeNull();
    expect(match?.item.entrega).toContain('Processos Licitatórios');
    expect(match?.confidence).toBeGreaterThanOrEqual(0.7);
  });

  it('deve vincular ação de Assistência Estudantil à entrega da DAE', () => {
    const task: Partial<Tarefa> = {
      id: 'task-2',
      titulo: 'Compilar dados do Sispnaes para pagamento de auxílio alimentação',
      area_tematica: 'ASSISTÊNCIA ESTUDANTIL',
      projeto: 'Bolsas',
      tags: ['auxilio'],
    };

    const match = findBestHeuristicMatch(task as Tarefa, planItems);
    expect(match).not.toBeNull();
    expect(match?.item.entrega).toContain('Assistência Estudantil');
    expect(match?.confidence).toBeGreaterThanOrEqual(0.7);
  });

  it('deve retornar null para tarefas totalmente fora do escopo das entregas', () => {
    const task: Partial<Tarefa> = {
      id: 'task-3',
      titulo: 'Consertar pneu da bicicleta na oficina',
      area_tematica: 'PESSOAL',
      projeto: 'Casa',
      tags: ['saude'],
    };

    const match = findBestHeuristicMatch(task as Tarefa, planItems);
    expect(match).toBeNull();
  });

  it('buildHeuristicPgdSuggestions deve mapear múltiplas tarefas corretamente', () => {
    const tasks: Partial<Tarefa>[] = [
      {
        id: 't-clc',
        titulo: 'Minuta do edital de compras',
        area_tematica: 'CLC',
      },
      {
        id: 't-dae',
        titulo: 'Relatório do Sispnaes DAE',
        area_tematica: 'ASSISTÊNCIA ESTUDANTIL',
      },
      {
        id: 't-none',
        titulo: 'Comprar frutas na feira',
        area_tematica: 'PESSOAL',
      },
    ];

    const result = buildHeuristicPgdSuggestions(tasks as Tarefa[], planItems);
    expect(result['t-clc']).toBeDefined();
    expect(result['t-clc'].item.unidade).toBe('CLC');
    expect(result['t-dae']).toBeDefined();
    expect(result['t-dae'].item.unidade).toBe('DAE');
    expect(result['t-none']).toBeUndefined();
  });
});
