import { describe, expect, it } from 'vitest';
import {
  addDias,
  buildGanttRange,
  buildGanttRows,
  buildGanttTicks,
  diffDias,
  posicaoDaBarra,
  posicaoDeData,
  posicaoDeHoje,
  statusVisualDaEtapa,
  statusVisualDaLinha,
} from './ganttLayout';

const tarefa = (over: Record<string, any> = {}) => ({
  id: over.id || 't1',
  titulo: over.titulo || 'Ação',
  status: over.status || 'em andamento',
  data_limite: over.data_limite ?? '2026-08-10',
  prazo_final: over.prazo_final,
  area_tematica: over.area_tematica || 'GERAL',
  ...over,
}) as any;

const HOJE = '2026-08-12';

describe('buildGanttRows', () => {
  it('usa data de execução e prazo final como extremos da barra', () => {
    const [linha] = buildGanttRows([tarefa({ data_limite: '2026-08-10', prazo_final: '2026-08-14' })], { hoje: HOJE });
    expect(linha.inicio).toBe('2026-08-10');
    expect(linha.fim).toBe('2026-08-14');
    expect(linha.temPrazoFinal).toBe(true);
    expect(linha.duracaoDias).toBe(5);
    expect(linha.emCurso).toBe(true);
  });

  it('ação sem prazo final vira barra de um dia', () => {
    const [linha] = buildGanttRows([tarefa({ prazo_final: undefined })], { hoje: HOJE });
    expect(linha.temPrazoFinal).toBe(false);
    expect(linha.inicio).toBe(linha.fim);
    expect(linha.duracaoDias).toBe(1);
  });

  it('ignora ação sem data de execução válida', () => {
    const linhas = buildGanttRows([
      tarefa({ id: 'a', data_limite: '' }),
      tarefa({ id: 'b', data_limite: '-' }),
      tarefa({ id: 'c', data_limite: '0000-00-00' }),
      tarefa({ id: 'd', data_limite: '2026-08-10' }),
    ], { hoje: HOJE });
    expect(linhas.map(l => l.task.id)).toEqual(['d']);
  });

  it('ignora ações excluídas e, por padrão, concluídas', () => {
    const linhas = buildGanttRows([
      tarefa({ id: 'x', status: 'excluído' }),
      tarefa({ id: 'y', status: 'concluído' }),
      tarefa({ id: 'z' }),
    ], { hoje: HOJE });
    expect(linhas.map(l => l.task.id)).toEqual(['z']);

    const comConcluidas = buildGanttRows([
      tarefa({ id: 'y', status: 'concluído' }),
      tarefa({ id: 'z' }),
    ], { hoje: HOJE, incluirConcluidas: true });
    expect(comConcluidas.map(l => l.task.id).sort()).toEqual(['y', 'z']);
  });

  it('filtra por prazo final quando pedido', () => {
    const linhas = buildGanttRows([
      tarefa({ id: 'com', prazo_final: '2026-08-20' }),
      tarefa({ id: 'sem' }),
    ], { hoje: HOJE, apenasComPrazoFinal: true });
    expect(linhas.map(l => l.task.id)).toEqual(['com']);
  });

  it('marca atraso quando o fim já passou e a ação não foi concluída', () => {
    const [atrasada] = buildGanttRows([tarefa({ data_limite: '2026-08-01', prazo_final: '2026-08-05' })], { hoje: HOJE });
    expect(atrasada.atrasada).toBe(true);
    expect(statusVisualDaLinha(atrasada)).toBe('atrasada');

    const [futura] = buildGanttRows([tarefa({ data_limite: '2026-08-20' })], { hoje: HOJE });
    expect(futura.atrasada).toBe(false);
    expect(statusVisualDaLinha(futura)).toBe('andamento');
  });

  it('não gera barra invertida quando o prazo é anterior à execução', () => {
    const [linha] = buildGanttRows([tarefa({ data_limite: '2026-08-14', prazo_final: '2026-08-10' })], { hoje: HOJE });
    expect(linha.inicio).toBe('2026-08-10');
    expect(linha.fim).toBe('2026-08-14');
    expect(linha.duracaoDias).toBe(5);
  });

  it('ordena por data de execução e depois por término', () => {
    const linhas = buildGanttRows([
      tarefa({ id: 'c', data_limite: '2026-08-20' }),
      tarefa({ id: 'a', data_limite: '2026-08-10', prazo_final: '2026-08-12' }),
      tarefa({ id: 'b', data_limite: '2026-08-10', prazo_final: '2026-08-30' }),
    ], { hoje: HOJE });
    expect(linhas.map(l => l.task.id)).toEqual(['a', 'b', 'c']);
  });

  it('prioriza stand-by sobre andamento no visual, sem esconder o atraso', () => {
    const [standby] = buildGanttRows([tarefa({ status: 'stand-by', data_limite: '2026-08-20' })], { hoje: HOJE });
    expect(statusVisualDaLinha(standby)).toBe('standby');
    const [standbyAtrasada] = buildGanttRows([tarefa({ status: 'stand-by', data_limite: '2026-08-01' })], { hoje: HOJE });
    expect(statusVisualDaLinha(standbyAtrasada)).toBe('atrasada');
  });
});

describe('buildGanttRange', () => {
  it('cobre todas as barras e sempre inclui hoje', () => {
    const linhas = buildGanttRows([
      tarefa({ id: 'a', data_limite: '2026-08-10', prazo_final: '2026-08-14' }),
      tarefa({ id: 'b', data_limite: '2026-09-01' }),
    ], { hoje: HOJE });
    const range = buildGanttRange(linhas, HOJE)!;
    expect(range.inicio <= '2026-08-10').toBe(true);
    expect(range.fim >= '2026-09-01').toBe(true);
    expect(range.totalDias).toBe(diffDias(range.inicio, range.fim) + 1);
    expect(range.totalDias % 7).toBe(0);
  });

  it('estende a janela até hoje quando todas as ações são antigas', () => {
    const linhas = buildGanttRows([tarefa({ data_limite: '2026-07-01' })], { hoje: HOJE });
    const range = buildGanttRange(linhas, HOJE)!;
    expect(range.fim >= HOJE).toBe(true);
  });

  it('devolve null sem linhas', () => {
    expect(buildGanttRange([], HOJE)).toBeNull();
  });
});

describe('buildGanttTicks', () => {
  const range = { inicio: '2026-08-02', fim: '2026-08-29', totalDias: 28 };

  it('gera um tick por dia no zoom diário', () => {
    const ticks = buildGanttTicks(range, 'dia', HOJE);
    expect(ticks).toHaveLength(28);
    expect(ticks[0].iso).toBe('2026-08-02');
    expect(ticks.filter(t => t.ehHoje)).toHaveLength(1);
    expect(ticks.filter(t => t.ehFimDeSemana).length).toBe(8);
  });

  it('agrupa por semana no zoom semanal', () => {
    const ticks = buildGanttTicks(range, 'semana', HOJE);
    expect(ticks).toHaveLength(4);
    expect(ticks.every(t => t.dias === 7)).toBe(true);
  });

  it('agrupa por mês no zoom mensal sem estourar a janela', () => {
    const ticks = buildGanttTicks({ inicio: '2026-08-02', fim: '2026-10-31', totalDias: diffDias('2026-08-02', '2026-10-31') + 1 }, 'mes', HOJE);
    expect(ticks).toHaveLength(3);
    expect(ticks[0].iso).toBe('2026-08-02');
    expect(ticks.reduce((soma, t) => soma + t.dias, 0)).toBe(diffDias('2026-08-02', '2026-10-31') + 1);
  });
});

describe('posições', () => {
  const range = { inicio: '2026-08-02', fim: '2026-08-29', totalDias: 28 };

  it('posiciona a barra proporcionalmente à janela', () => {
    const [linha] = buildGanttRows([tarefa({ data_limite: '2026-08-09', prazo_final: '2026-08-15' })], { hoje: HOJE });
    const { left, width } = posicaoDaBarra(linha, range);
    expect(left).toBe(`${(7 / 28) * 100}%`);
    expect(width).toBe(`${(7 / 28) * 100}%`);
  });

  it('garante largura mínima de um dia', () => {
    const [linha] = buildGanttRows([tarefa({ data_limite: '2026-08-09' })], { hoje: HOJE });
    const largura = parseFloat(posicaoDaBarra(linha, range).width);
    expect(largura).toBeCloseTo((1 / 28) * 100, 6);
  });

  it('marca hoje só quando está dentro da janela', () => {
    expect(posicaoDeHoje(range, HOJE)).not.toBeNull();
    expect(posicaoDeHoje(range, '2026-09-30')).toBeNull();
  });
});

describe('aritmética de datas', () => {
  it('soma dias atravessando o mês', () => {
    expect(addDias('2026-08-30', 3)).toBe('2026-09-02');
    expect(addDias('2026-03-01', -1)).toBe('2026-02-28');
  });

  it('conta a diferença em dias nos dois sentidos', () => {
    expect(diffDias('2026-08-10', '2026-08-14')).toBe(4);
    expect(diffDias('2026-08-14', '2026-08-10')).toBe(-4);
  });
});

// --------------------------------------------------------------------------
// Granularidade de subtarefa (26/08/2026)
// --------------------------------------------------------------------------

const etapa = (over: Record<string, any> = {}) => ({
  id: over.id || 'e1',
  text: over.text || 'Etapa',
  completed: over.completed ?? false,
  ...over,
});

describe('barra vinda do plano', () => {
  it('usa o primeiro e o último dia previsto das etapas', () => {
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-10',
      plano_acao: [
        etapa({ id: 'a', text: 'Congelar', data_prevista: '2026-08-10' }),
        etapa({ id: 'b', text: 'Publicar', data_prevista: '2026-08-14' }),
        etapa({ id: 'c', text: 'Revisar', data_prevista: '2026-08-12' }),
      ],
    })], { hoje: HOJE });

    expect(linha.barraVemDoPlano).toBe(true);
    expect(linha.inicioTrabalho).toBe('2026-08-10');
    expect(linha.fimTrabalho).toBe('2026-08-14');
    expect(linha.duracaoDias).toBe(5);
    expect(linha.pontual).toBe(false);
  });

  it('tira do losango uma ação sem prazo final', () => {
    // Era o caso de 589 das 603 ações: sem prazo final, tudo virava marco de
    // um dia. Com datas nas etapas a barra existe sem prazo nenhum.
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-10',
      prazo_final: undefined,
      plano_acao: [
        etapa({ id: 'a', data_prevista: '2026-08-10' }),
        etapa({ id: 'b', data_prevista: '2026-08-20' }),
      ],
    })], { hoje: HOJE });

    expect(linha.temPrazoFinal).toBe(false);
    expect(linha.pontual).toBe(false);
    expect(linha.duracaoDias).toBe(11);
  });

  it('cobre também a data de execução quando ela vem antes do plano', () => {
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-05',
      plano_acao: [etapa({ data_prevista: '2026-08-12' })],
    })], { hoje: HOJE });
    expect(linha.inicioTrabalho).toBe('2026-08-05');
  });

  it('plano sem data nenhuma continua se comportando como antes', () => {
    // Os 34 planos existentes caem aqui: nenhuma etapa tem data própria, e
    // marcar todas no mesmo dia seria ruído, não informação.
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-10',
      plano_acao: [etapa({ id: 'a' }), etapa({ id: 'b', completed: true })],
    })], { hoje: HOJE });

    expect(linha.barraVemDoPlano).toBe(false);
    expect(linha.etapas).toEqual([]);
    expect(linha.pontual).toBe(true);
    expect(linha.inicioTrabalho).toBe('2026-08-10');
  });

  it('ação sem plano segue como marco de um dia', () => {
    const [linha] = buildGanttRows([tarefa({ data_limite: '2026-08-10' })], { hoje: HOJE });
    expect(linha.pontual).toBe(true);
    expect(linha.etapas).toEqual([]);
  });

  it('a janela do gráfico cresce para caber o plano', () => {
    const linhas = buildGanttRows([tarefa({
      data_limite: '2026-08-10',
      plano_acao: [etapa({ data_prevista: '2026-09-20' })],
    })], { hoje: HOJE });
    const range = buildGanttRange(linhas, HOJE)!;
    expect(range.fim >= '2026-09-20').toBe(true);
  });
});

describe('prazo final como marco', () => {
  it('a barra é o trabalho, e o prazo fica como bandeira separada', () => {
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-10',
      prazo_final: '2026-08-25',
      plano_acao: [etapa({ data_prevista: '2026-08-14' })],
    })], { hoje: HOJE });

    expect(linha.fimTrabalho).toBe('2026-08-14');
    expect(linha.prazoFinal).toBe('2026-08-25');
    expect(linha.fim).toBe('2026-08-25');   // a linha cobre a folga
    expect(linha.prazoEstourado).toBe(false);
  });

  it('sinaliza quando o plano termina depois do prazo', () => {
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-10',
      prazo_final: '2026-08-15',
      plano_acao: [etapa({ data_prevista: '2026-08-30' })],
    })], { hoje: HOJE });

    expect(linha.prazoEstourado).toBe(true);
    expect(linha.fimTrabalho).toBe('2026-08-30');
  });

  it('prazo anterior à execução é sinalizado, não corrigido em silêncio', () => {
    // Existe ação assim em produção, com prazo 20 dias antes da execução. O
    // código anterior trocava as pontas e a barra saía bonita.
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-20',
      prazo_final: '2026-07-31',
    })], { hoje: HOJE });

    expect(linha.prazoAntesDoInicio).toBe(true);
    expect(linha.inicioTrabalho).toBe('2026-08-20');  // o trabalho não anda
    expect(linha.inicio).toBe('2026-07-31');          // a linha cobre a bandeira
  });
});

describe('etapas', () => {
  it('deduz o estado de completed quando o campo não existe', () => {
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-10',
      plano_acao: [
        etapa({ id: 'a', data_prevista: '2026-08-10', completed: true }),
        etapa({ id: 'b', data_prevista: '2026-08-11' }),
      ],
    })], { hoje: HOJE });

    expect(linha.etapas.map(e => e.estado)).toEqual(['feito', 'pendente']);
  });

  it('estado explícito manda sobre completed', () => {
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-10',
      plano_acao: [etapa({ data_prevista: '2026-08-10', estado: 'aguardando_terceiro' })],
    })], { hoje: HOJE });
    expect(linha.etapas[0].estado).toBe('aguardando_terceiro');
  });

  it('marca atrasada a etapa vencida e não concluída', () => {
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-01',
      plano_acao: [
        etapa({ id: 'a', data_prevista: '2026-08-01' }),
        etapa({ id: 'b', data_prevista: '2026-08-01', completed: true }),
        etapa({ id: 'c', data_prevista: '2026-08-30' }),
      ],
    })], { hoje: HOJE });

    expect(linha.etapas.map(e => e.atrasada)).toEqual([true, false, false]);
  });

  it('etapa sem data num plano datado entra na lista sem posição', () => {
    const [linha] = buildGanttRows([tarefa({
      data_limite: '2026-08-10',
      plano_acao: [
        etapa({ id: 'a', text: 'Publicar', data_prevista: '2026-08-12' }),
        etapa({ id: 'b', text: 'Após o retorno' }),
      ],
    })], { hoje: HOJE });

    expect(linha.etapas).toHaveLength(2);
    expect(linha.etapas[1].data).toBe('');
    // Não pode esticar a barra para um dia que ninguém marcou.
    expect(linha.fimTrabalho).toBe('2026-08-12');
  });

  it('espera vence atraso na aparência do marcador', () => {
    // Etapa parada esperando outra pessoa passou da data sem ninguém ter
    // procrastinado — pintá-la de atrasada é a confusão que o contador de
    // degradação fazia antes de 26/08/2026.
    expect(statusVisualDaEtapa({
      id: 'a', texto: 'x', data: '2026-08-01', estado: 'aguardando_terceiro',
      concluida: false, atrasada: true,
    })).toBe('aguardando');
  });

  it('etapa concluída não aparece como atrasada', () => {
    expect(statusVisualDaEtapa({
      id: 'a', texto: 'x', data: '2026-08-01', estado: 'feito',
      concluida: true, atrasada: false,
    })).toBe('feito');
  });
});

describe('posicaoDeData', () => {
  const rangeMarcador = { inicio: '2026-08-02', fim: '2026-08-29', totalDias: 28 };

  it('põe o marcador no centro da coluna do dia', () => {
    expect(posicaoDeData('2026-08-02', rangeMarcador)).toBe(`${(0.5 / 28) * 100}%`);
  });

  it('devolve null fora da janela, para não desenhar na borda', () => {
    expect(posicaoDeData('2026-07-30', rangeMarcador)).toBeNull();
    expect(posicaoDeData('2026-09-01', rangeMarcador)).toBeNull();
    expect(posicaoDeData('', rangeMarcador)).toBeNull();
  });
});
