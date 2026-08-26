/**
 * Testa o que o Gantt DESENHA depois da granularidade por subtarefa.
 *
 * `ganttLayout.test.ts` cobre a aritmética; aqui o risco é outro: a regra estar
 * certa e a tela não mostrar. Em especial as duas colunas — rótulos à esquerda,
 * barras à direita — que rolam separadas e precisam continuar alinhadas quando
 * uma ação é expandida em etapas.
 *
 * O componente não fala com Firebase: recebe as ações por prop.
 */
// @vitest-environment jsdom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { GanttView } from './GanttView';

afterEach(cleanup);

const hoje = (() => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`;
})();

const emDias = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const acao = (over: Record<string, any> = {}) => ({
  id: over.id || 't1',
  titulo: over.titulo || 'Ação',
  status: 'em andamento',
  data_limite: hoje,
  area_tematica: 'GERAL',
  ...over,
}) as any;

const planoDatado = () => [
  { id: 'e1', text: 'Congelar o escopo', completed: true, estado: 'feito', data_prevista: hoje },
  { id: 'e2', text: 'Publicar a versão', completed: false, estado: 'aguardando_terceiro',
    aguardando_de: 'colegas do MAGO', data_prevista: emDias(1) },
  { id: 'e3', text: 'Revisar minhas questões', completed: false, estado: 'em_andamento',
    data_prevista: emDias(4) },
];

const desenhar = (tasks: any[]) =>
  render(<GanttView tasks={tasks} onTaskClick={vi.fn()} />);

describe('GanttView com plano datado', () => {
  it('mostra o intervalo do plano no rótulo, não só a data de execução', () => {
    desenhar([acao({ titulo: 'Revisar Questões do Mago', plano_acao: planoDatado() })]);
    expect(screen.getByText(/3 etapas/)).toBeTruthy();
    expect(screen.getByText(/com plano datado/)).toBeTruthy();
  });

  it('conta as ações que esperam terceiro no cabeçalho', () => {
    desenhar([acao({ plano_acao: planoDatado() })]);
    expect(screen.getByText(/esperando terceiro/)).toBeTruthy();
  });

  it('expande a ação em uma linha por etapa e recolhe de volta', () => {
    desenhar([acao({ titulo: 'Mago', plano_acao: planoDatado() })]);

    expect(screen.queryByText('Congelar o escopo')).toBeNull();

    const abrir = screen.getByTitle(/Ver as 3 etapas/);
    fireEvent.click(abrir);
    expect(screen.getByText('Congelar o escopo')).toBeTruthy();
    expect(screen.getByText('Publicar a versão')).toBeTruthy();

    fireEvent.click(screen.getByTitle(/Recolher as etapas/));
    expect(screen.queryByText('Congelar o escopo')).toBeNull();
  });

  it('as duas colunas ganham o mesmo número de linhas ao expandir', () => {
    // Se rótulos e barras divergirem aqui, o gráfico inteiro desalinha.
    const { container } = desenhar([acao({ titulo: 'Mago', plano_acao: planoDatado() })]);
    fireEvent.click(screen.getByTitle(/Ver as 3 etapas/));

    const alturas = Array.from(container.querySelectorAll<HTMLElement>('[style*="height"]'))
      .map(el => el.style.height)
      .filter(Boolean);
    const acoes = alturas.filter(h => h === '44px').length;
    const etapas = alturas.filter(h => h === '30px').length;
    // Uma linha de ação e três de etapa, em cada uma das duas colunas.
    expect(acoes).toBe(2);
    expect(etapas).toBe(6);
  });

  it('o marcador da etapa em espera se identifica como tal', () => {
    desenhar([acao({ plano_acao: planoDatado() })]);
    const marcadores = screen.getAllByTitle(/aguardando terceiro/);
    expect(marcadores.length).toBeGreaterThan(0);
  });

  it('a legenda explica os símbolos novos', () => {
    desenhar([acao({ plano_acao: planoDatado() })]);
    expect(screen.getByText('Aguardando terceiro')).toBeTruthy();
    expect(screen.getByText('Prazo final')).toBeTruthy();
    expect(screen.getByText('Folga até o prazo')).toBeTruthy();
  });
});

describe('GanttView sem plano datado', () => {
  it('ação sem datas nas etapas não ganha botão de expandir', () => {
    desenhar([acao({
      titulo: 'Sem datas',
      plano_acao: [{ id: 'a', text: 'passo', completed: false }],
    })]);
    expect(screen.queryByTitle(/Ver as .* etapas/)).toBeNull();
    expect(screen.getByText(/sem prazo final/)).toBeTruthy();
  });

  it('ação com prazo final mostra a bandeira do prazo', () => {
    desenhar([acao({ titulo: 'Com prazo', prazo_final: emDias(10) })]);
    expect(screen.getAllByTitle(/Prazo final:/).length).toBeGreaterThan(0);
  });

  it('dia vazio não inventa gráfico', () => {
    desenhar([]);
    expect(screen.getByText(/Nenhuma ação com data de execução/)).toBeTruthy();
  });
});

describe('inconsistências ficam visíveis', () => {
  it('avisa quando o plano termina depois do prazo final', () => {
    desenhar([acao({
      titulo: 'Estoura',
      prazo_final: emDias(2),
      plano_acao: [{ id: 'a', text: 'passo longo', completed: false, data_prevista: emDias(20) }],
    })]);
    expect(screen.getByTitle(/termina depois do prazo final/)).toBeTruthy();
  });

  it('avisa quando o prazo final é anterior à execução', () => {
    // Existe ação assim em produção, com prazo 20 dias antes da execução.
    desenhar([acao({ titulo: 'Invertida', prazo_final: emDias(-20) })]);
    expect(screen.getByTitle(/anterior à data de execução/)).toBeTruthy();
  });
});
