import React, { useMemo, useState } from 'react';
import { Tarefa, formatDate } from '../../types';
import {
  GanttScale,
  GanttRow,
  GanttEtapa,
  buildGanttRange,
  buildGanttRows,
  buildGanttTicks,
  hojeISO,
  posicaoDaBarra,
  posicaoDeData,
  posicaoDeHoje,
  posicaoDoIntervalo,
  statusVisualDaEtapa,
  statusVisualDaLinha,
} from '../utils/ganttLayout';

/**
 * Gráfico de Gantt das ações.
 *
 * Cada linha é uma ação. A barra cobre o trabalho planejado — do primeiro ao
 * último dia previsto das subtarefas — e cada etapa aparece como um marcador
 * sobre ela. Clicar no rótulo expande a ação em uma linha por etapa.
 *
 * Quando o plano não tem datas próprias, a linha se comporta como antes: um
 * marco no dia de execução, ou uma barra até o prazo final se houver.
 *
 * O prazo final é uma **bandeira**, não o fim da barra. Assim dá para ver o
 * trabalho passar do prazo, em vez de a barra simplesmente terminar nele.
 */

const PX_POR_DIA: Record<GanttScale, number> = {
  dia: 34,
  semana: 15,
  mes: 5,
};

const ESCALAS: { valor: GanttScale; rotulo: string }[] = [
  { valor: 'dia', rotulo: 'Dia' },
  { valor: 'semana', rotulo: 'Semana' },
  { valor: 'mes', rotulo: 'Mês' },
];

const CORES = {
  concluida: { barra: 'bg-emerald-500', borda: 'border-emerald-600', texto: 'text-emerald-600', rotulo: 'Concluída' },
  atrasada: { barra: 'bg-rose-500', borda: 'border-rose-600', texto: 'text-rose-600', rotulo: 'Atrasada' },
  standby: { barra: 'bg-amber-500', borda: 'border-amber-600', texto: 'text-amber-600', rotulo: 'Stand-by' },
  andamento: { barra: 'bg-blue-500', borda: 'border-blue-600', texto: 'text-blue-600', rotulo: 'Em andamento' },
} as const;

const CORES_ETAPA = {
  feito: { fundo: 'bg-emerald-500', borda: 'border-emerald-700', rotulo: 'Etapa concluída' },
  aguardando: { fundo: 'bg-amber-400', borda: 'border-amber-600', rotulo: 'Aguardando terceiro' },
  atrasada: { fundo: 'bg-rose-500', borda: 'border-rose-700', rotulo: 'Etapa atrasada' },
  em_andamento: { fundo: 'bg-blue-500', borda: 'border-blue-700', rotulo: 'Etapa em andamento' },
  pendente: { fundo: 'bg-slate-300', borda: 'border-slate-500', rotulo: 'Etapa pendente' },
} as const;

const ROTULO_ESTADO: Record<GanttEtapa['estado'], string> = {
  feito: 'concluída',
  em_andamento: 'em andamento',
  aguardando_terceiro: 'aguardando terceiro',
  pendente: 'pendente',
};

/** Hachura da etapa em espera — a diferença tem que sobreviver ao daltonismo. */
const HACHURA = {
  backgroundImage:
    'repeating-linear-gradient(45deg, transparent 0 3px, rgba(255,255,255,0.55) 3px 6px)',
} as const;

const ALTURA_ACAO = 44;
const ALTURA_ETAPA = 30;

const dataCurta = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

type LinhaVisual =
  | { tipo: 'acao'; chave: string; linha: GanttRow }
  | { tipo: 'etapa'; chave: string; linha: GanttRow; etapa: GanttEtapa };

export const GanttView = ({
  tasks,
  onTaskClick,
  isDark = false,
}: {
  tasks: Tarefa[];
  onTaskClick: (t: Tarefa) => void;
  isDark?: boolean;
}) => {
  const [escala, setEscala] = useState<GanttScale>('semana');
  const [incluirConcluidas, setIncluirConcluidas] = useState(false);
  const [apenasComPrazoFinal, setApenasComPrazoFinal] = useState(false);
  const [expandidas, setExpandidas] = useState<Record<string, boolean>>({});

  const alternarExpansao = (id: string) =>
    setExpandidas(atual => ({ ...atual, [id]: !atual[id] }));

  const hoje = hojeISO();

  const linhas = useMemo(
    () => buildGanttRows(tasks, { hoje, incluirConcluidas, apenasComPrazoFinal }),
    [tasks, hoje, incluirConcluidas, apenasComPrazoFinal]
  );
  const range = useMemo(() => buildGanttRange(linhas, hoje), [linhas, hoje]);
  const ticks = useMemo(() => (range ? buildGanttTicks(range, escala, hoje) : []), [range, escala, hoje]);

  const pxPorDia = PX_POR_DIA[escala];
  const larguraTotal = range ? range.totalDias * pxPorDia : 0;
  const hojeLeft = range ? posicaoDeHoje(range, hoje) : null;

  const resumo = useMemo(() => ({
    total: linhas.length,
    comPrazo: linhas.filter(l => l.temPrazoFinal).length,
    atrasadas: linhas.filter(l => l.atrasada).length,
    emCurso: linhas.filter(l => l.emCurso).length,
    comPlanoDatado: linhas.filter(l => l.barraVemDoPlano).length,
    esperando: linhas.filter(l => l.etapas.some(e => e.estado === 'aguardando_terceiro')).length,
  }), [linhas]);

  // As duas colunas — rótulos e barras — percorrem esta mesma lista, senão as
  // linhas desalinham no instante em que uma ação é expandida.
  const linhasVisuais = useMemo<LinhaVisual[]>(() => {
    const saida: LinhaVisual[] = [];
    for (const linha of linhas) {
      saida.push({ tipo: 'acao', chave: linha.task.id, linha });
      if (!expandidas[linha.task.id]) continue;
      for (const etapa of linha.etapas) {
        saida.push({ tipo: 'etapa', chave: `${linha.task.id}:${etapa.id}`, linha, etapa });
      }
    }
    return saida;
  }, [linhas, expandidas]);

  // Faixa superior da régua: agrupa ticks consecutivos do mesmo mês/ano.
  const grupos = useMemo(() => {
    const acumulado: { rotulo: string; dias: number }[] = [];
    for (const tick of ticks) {
      const ultimo = acumulado[acumulado.length - 1];
      if (ultimo && ultimo.rotulo === tick.grupo) ultimo.dias += tick.dias;
      else acumulado.push({ rotulo: tick.grupo, dias: tick.dias });
    }
    return acumulado;
  }, [ticks]);

  const corBorda = isDark ? 'border-slate-700' : 'border-slate-200';
  const corFundo = isDark ? 'bg-slate-900' : 'bg-white';
  const corFundoSutil = isDark ? 'bg-slate-800/60' : 'bg-slate-50';
  const corTexto = isDark ? 'text-slate-200' : 'text-slate-800';
  const corTextoFraco = isDark ? 'text-slate-500' : 'text-slate-400';

  const botaoFiltro = (ativo: boolean) =>
    `px-3 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-all font-sans border ${
      ativo
        ? isDark
          ? 'bg-slate-600 text-white border-slate-500'
          : 'bg-slate-900 text-white border-slate-900'
        : isDark
          ? 'text-slate-400 border-slate-700 hover:text-slate-200'
          : 'text-slate-500 border-slate-200 hover:text-slate-800'
    }`;

  return (
    <div className={`gantt-view animate-in border-2 rounded-none overflow-hidden shadow-2xl ${isDark ? 'bg-slate-900 border-slate-700' : 'bg-white border-slate-900'}`}>
      {/* Cabeçalho: período, resumo e controles */}
      <div className={`p-4 md:p-6 border-b flex flex-col lg:flex-row lg:items-center justify-between gap-4 ${corBorda} ${corFundoSutil}`}>
        <div>
          <h3 className={`text-lg font-black tracking-tight flex items-center gap-3 ${corTexto}`}>
            <span className="w-2 h-7 bg-blue-600 rounded-none" />
            Gantt das Ações
          </h3>
          <p className={`mt-1 text-[10px] font-bold uppercase tracking-widest ${corTextoFraco}`}>
            {range ? `${formatDate(range.inicio).split(' ')[0]} — ${formatDate(range.fim).split(' ')[0]}` : 'Sem período'}
            {' · '}
            {resumo.total} {resumo.total === 1 ? 'ação' : 'ações'}
            {' · '}
            {resumo.comPlanoDatado} com plano datado
            {' · '}
            {resumo.comPrazo} com prazo final
            {resumo.esperando > 0 && <span className="text-amber-500"> · {resumo.esperando} esperando terceiro</span>}
            {resumo.atrasadas > 0 && <span className="text-rose-500"> · {resumo.atrasadas} atrasada(s)</span>}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setIncluirConcluidas(v => !v)} className={botaoFiltro(incluirConcluidas)} title="Mostrar também as ações concluídas">
            Concluídas
          </button>
          <button onClick={() => setApenasComPrazoFinal(v => !v)} className={botaoFiltro(apenasComPrazoFinal)} title="Mostrar apenas ações que têm data final">
            Só com prazo
          </button>
          <div className={`p-0.5 rounded-lg inline-flex border gap-0.5 ${isDark ? 'bg-slate-800 border-slate-700' : 'bg-slate-100 border-slate-200'}`}>
            {ESCALAS.map(({ valor, rotulo }) => (
              <button
                key={valor}
                onClick={() => setEscala(valor)}
                className={`px-3 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-all font-sans ${
                  escala === valor
                    ? isDark ? 'bg-slate-600 text-white' : 'bg-white text-slate-900 shadow-sm'
                    : isDark ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600'
                }`}
                title={`Zoom por ${rotulo.toLowerCase()}`}
              >
                {rotulo}
              </button>
            ))}
          </div>
        </div>
      </div>

      {!range || linhas.length === 0 ? (
        <div className={`p-16 text-center ${corTextoFraco}`}>
          <p className="text-[11px] font-black uppercase tracking-widest">Nenhuma ação com data de execução no filtro atual</p>
          <p className="mt-2 text-xs">A barra cobre o trabalho planejado — do primeiro ao último dia previsto das etapas. Ação sem data nas etapas aparece como marco no dia de execução.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <div className="flex min-w-max">
            {/* Coluna fixa com as ações */}
            <div className={`sticky left-0 z-30 shrink-0 w-44 md:w-72 border-r ${corBorda} ${corFundo}`}>
              <div className={`h-14 flex items-end px-3 pb-2 border-b ${corBorda} ${corFundoSutil}`}>
                <span className={`text-[9px] font-black uppercase tracking-widest ${corTextoFraco}`}>Ação</span>
              </div>
              {linhasVisuais.map(item => {
                if (item.tipo === 'etapa') {
                  const { etapa } = item;
                  const cor = CORES_ETAPA[statusVisualDaEtapa(etapa)];
                  return (
                    <div
                      key={item.chave}
                      style={{ height: ALTURA_ETAPA }}
                      className={`flex items-center gap-2 pl-7 pr-3 border-b ${corBorda} ${
                        isDark ? 'bg-slate-800/40' : 'bg-slate-50/70'
                      }`}
                      title={`${etapa.texto}\n${etapa.data ? formatDate(etapa.data) : 'sem dia marcado'} · ${ROTULO_ESTADO[etapa.estado]}`}
                    >
                      <span
                        className={`shrink-0 w-2 h-2 rounded-full border ${cor.fundo} ${cor.borda}`}
                        style={statusVisualDaEtapa(etapa) === 'aguardando' ? HACHURA : undefined}
                      />
                      <span className={`text-[10px] leading-tight truncate ${corTextoFraco}`}>{etapa.texto}</span>
                    </div>
                  );
                }

                const { linha } = item;
                const expansivel = linha.etapas.length > 0;
                const aberta = Boolean(expandidas[linha.task.id]);
                return (
                  <div
                    key={item.chave}
                    style={{ height: ALTURA_ACAO }}
                    className={`w-full flex items-center border-b ${corBorda} ${
                      isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-50'
                    }`}
                  >
                    {expansivel ? (
                      <button
                        onClick={() => alternarExpansao(linha.task.id)}
                        className={`shrink-0 w-6 h-full flex items-center justify-center text-[9px] font-black ${corTextoFraco}`}
                        title={aberta ? 'Recolher as etapas' : `Ver as ${linha.etapas.length} etapas`}
                        aria-expanded={aberta}
                      >
                        {aberta ? '▾' : '▸'}
                      </button>
                    ) : (
                      <span className="shrink-0 w-6" />
                    )}
                    <button
                      onClick={() => onTaskClick(linha.task)}
                      className="flex-1 min-w-0 h-full flex flex-col justify-center pr-3 text-left"
                      title={linha.task.titulo}
                    >
                      <span className={`text-[11px] font-bold leading-tight truncate ${corTexto}`}>{linha.task.titulo}</span>
                      <span className={`text-[9px] font-mono uppercase tracking-wider truncate ${corTextoFraco}`}>
                        {linha.barraVemDoPlano
                          ? `${dataCurta(linha.inicioTrabalho)} → ${dataCurta(linha.fimTrabalho)} · ${linha.etapas.length} etapas`
                          : linha.temPrazoFinal
                            ? `${dataCurta(linha.inicio)} → ${dataCurta(linha.fim)}`
                            : `${dataCurta(linha.inicio)} · sem prazo final`}
                      </span>
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Régua + barras */}
            <div style={{ width: larguraTotal }}>
              <div className={`h-14 border-b ${corBorda} ${corFundoSutil}`}>
                <div className="flex h-7">
                  {grupos.map((grupo, i) => (
                    <div
                      key={`${grupo.rotulo}-${i}`}
                      style={{ width: grupo.dias * pxPorDia }}
                      className={`flex items-center justify-center border-r overflow-hidden ${corBorda}`}
                    >
                      <span className={`text-[9px] font-black uppercase tracking-widest truncate px-1 ${corTextoFraco}`}>{grupo.rotulo}</span>
                    </div>
                  ))}
                </div>
                <div className="flex h-7">
                  {ticks.map(tick => (
                    <div
                      key={tick.iso}
                      style={{ width: tick.dias * pxPorDia }}
                      className={`flex items-center justify-center border-r overflow-hidden ${corBorda} ${
                        tick.ehHoje ? 'bg-rose-500/10' : tick.ehFimDeSemana ? (isDark ? 'bg-slate-800/60' : 'bg-slate-100') : ''
                      }`}
                    >
                      <span className={`text-[9px] font-mono truncate px-0.5 ${tick.ehHoje ? 'text-rose-500 font-black' : corTextoFraco}`}>
                        {tick.rotulo}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="relative" style={{ width: larguraTotal }}>
                {/* Grade de fundo */}
                <div className="absolute inset-0 flex pointer-events-none">
                  {ticks.map(tick => (
                    <div
                      key={`grade-${tick.iso}`}
                      style={{ width: tick.dias * pxPorDia }}
                      className={`border-r ${corBorda} ${tick.ehFimDeSemana ? (isDark ? 'bg-slate-800/40' : 'bg-slate-50') : ''}`}
                    />
                  ))}
                </div>
                {hojeLeft && (
                  <div className="absolute inset-y-0 z-20 w-px bg-rose-500 pointer-events-none" style={{ left: hojeLeft }} />
                )}

                {linhasVisuais.map(item => {
                  // Sub-linha de etapa: um marcador no dia previsto dela.
                  if (item.tipo === 'etapa') {
                    const { etapa } = item;
                    const visualEtapa = statusVisualDaEtapa(etapa);
                    const cor = CORES_ETAPA[visualEtapa];
                    const left = etapa.data ? posicaoDeData(etapa.data, range) : null;
                    return (
                      <div
                        key={item.chave}
                        style={{ height: ALTURA_ETAPA }}
                        className={`relative border-b ${corBorda} ${isDark ? 'bg-slate-800/40' : 'bg-slate-50/70'}`}
                      >
                        {left && (
                          <span
                            style={{ left, ...(visualEtapa === 'aguardando' ? HACHURA : {}) }}
                            className={`absolute top-1/2 z-10 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full border ${cor.fundo} ${cor.borda}`}
                            title={`${etapa.texto}\n${formatDate(etapa.data)} · ${ROTULO_ESTADO[etapa.estado]}`}
                          />
                        )}
                      </div>
                    );
                  }

                  const { linha } = item;
                  const visual = statusVisualDaLinha(linha);
                  const cor = CORES[visual];
                  const posicao = posicaoDaBarra(linha, range);
                  // Barra sólida = trabalho planejado. O resto da linha, até o
                  // prazo, é folga — desenhada vazada para não parecer trabalho.
                  const trabalho = posicaoDoIntervalo(linha.inicioTrabalho, linha.fimTrabalho, range);
                  const prazoLeft = linha.prazoFinal ? posicaoDeData(linha.prazoFinal, range) : null;

                  const descricao = [
                    linha.task.titulo,
                    linha.barraVemDoPlano
                      ? `Trabalho planejado: ${formatDate(linha.inicioTrabalho)} → ${formatDate(linha.fimTrabalho)} (${linha.etapas.length} etapas)`
                      : `Execução: ${formatDate(linha.inicioTrabalho)}`,
                    linha.prazoFinal ? `Prazo final: ${formatDate(linha.prazoFinal)}` : 'Sem prazo final',
                    linha.prazoEstourado ? '⚠️ O plano termina depois do prazo final' : '',
                    linha.prazoAntesDoInicio ? '⚠️ Prazo final anterior à data de execução' : '',
                    `Status: ${cor.rotulo}`,
                  ].filter(Boolean).join('\n');

                  return (
                    <div key={item.chave} style={{ height: ALTURA_ACAO }} className={`relative border-b ${corBorda}`}>
                      {/* Folga até o prazo: existe, mas não é trabalho. */}
                      {linha.temPrazoFinal && !linha.pontual && (
                        <span
                          style={posicao}
                          className={`absolute top-1/2 -translate-y-1/2 h-5 rounded-sm border border-dashed ${
                            linha.prazoEstourado ? 'border-rose-500' : cor.borda
                          } opacity-60`}
                        />
                      )}

                      <button
                        onClick={() => onTaskClick(linha.task)}
                        style={linha.pontual ? posicao : trabalho}
                        className={`absolute top-1/2 -translate-y-1/2 z-10 flex items-center transition-all hover:brightness-110 active:scale-[0.98] ${
                          linha.pontual ? 'h-11 justify-center' : `h-5 rounded-sm border ${cor.barra} ${cor.borda}`
                        }`}
                        title={descricao}
                      >
                        {linha.pontual ? (
                          <span className={`w-3 h-3 rotate-45 border ${cor.barra} ${cor.borda}`} />
                        ) : (
                          <span className="px-1.5 text-[9px] font-black text-white truncate drop-shadow">
                            {linha.duracaoDias >= 3 ? `${linha.duracaoDias}d` : ''}
                          </span>
                        )}
                      </button>

                      {/* Marcadores das etapas, sobre a barra. */}
                      {!expandidas[linha.task.id] && linha.etapas.map(etapa => {
                        const left = etapa.data ? posicaoDeData(etapa.data, range) : null;
                        if (!left) return null;
                        const visualEtapa = statusVisualDaEtapa(etapa);
                        const corEtapa = CORES_ETAPA[visualEtapa];
                        return (
                          <span
                            key={etapa.id}
                            style={{ left, ...(visualEtapa === 'aguardando' ? HACHURA : {}) }}
                            className={`absolute top-1/2 z-20 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full border ${corEtapa.fundo} ${corEtapa.borda}`}
                            title={`${etapa.texto}\n${formatDate(etapa.data)} · ${ROTULO_ESTADO[etapa.estado]}`}
                          />
                        );
                      })}

                      {/* Prazo final: bandeira, não fim de barra. */}
                      {prazoLeft && (
                        <span
                          style={{ left: prazoLeft }}
                          className="absolute inset-y-1 z-20 -translate-x-1/2 flex flex-col items-center pointer-events-none"
                          title={`Prazo final: ${formatDate(linha.prazoFinal!)}`}
                        >
                          <span className={`w-2 h-2 ${linha.prazoEstourado || linha.prazoAntesDoInicio ? 'bg-rose-500' : 'bg-slate-700'}`} />
                          <span className={`flex-1 w-px ${linha.prazoEstourado || linha.prazoAntesDoInicio ? 'bg-rose-500' : 'bg-slate-700'}`} />
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Legenda */}
      <div className={`px-4 md:px-6 py-3 border-t flex flex-wrap items-center gap-x-5 gap-y-2 ${corBorda} ${corFundoSutil}`}>
        {(Object.keys(CORES) as (keyof typeof CORES)[]).map(chave => (
          <span key={chave} className={`flex items-center gap-2 text-[9px] font-black uppercase tracking-widest ${corTextoFraco}`}>
            <span className={`w-4 h-2.5 rounded-sm ${CORES[chave].barra}`} />
            {CORES[chave].rotulo}
          </span>
        ))}
        <span className={`flex items-center gap-2 text-[9px] font-black uppercase tracking-widest ${corTextoFraco}`}>
          <span className="w-2.5 h-2.5 rotate-45 bg-slate-400" />
          Sem prazo final
        </span>
        <span className={`flex items-center gap-2 text-[9px] font-black uppercase tracking-widest ${corTextoFraco}`}>
          <span className="w-2 h-2 rounded-full border bg-slate-300 border-slate-500" />
          Etapa
        </span>
        <span className={`flex items-center gap-2 text-[9px] font-black uppercase tracking-widest ${corTextoFraco}`}>
          <span className="w-2 h-2 rounded-full border bg-amber-400 border-amber-600" style={HACHURA} />
          Aguardando terceiro
        </span>
        <span className={`flex items-center gap-2 text-[9px] font-black uppercase tracking-widest ${corTextoFraco}`}>
          <span className="flex flex-col items-center"><span className="w-1.5 h-1.5 bg-slate-700" /><span className="w-px h-2 bg-slate-700" /></span>
          Prazo final
        </span>
        <span className={`flex items-center gap-2 text-[9px] font-black uppercase tracking-widest ${corTextoFraco}`}>
          <span className={`w-4 h-2.5 rounded-sm border border-dashed ${isDark ? 'border-slate-500' : 'border-slate-400'}`} />
          Folga até o prazo
        </span>
        <span className={`flex items-center gap-2 text-[9px] font-black uppercase tracking-widest ${corTextoFraco}`}>
          <span className="w-px h-3 bg-rose-500" />
          Hoje
        </span>
      </div>
    </div>
  );
};
