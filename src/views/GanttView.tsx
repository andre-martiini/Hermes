import React, { useMemo, useState } from 'react';
import { Tarefa, formatDate } from '../../types';
import {
  GanttScale,
  GanttRow,
  buildGanttRange,
  buildGanttRows,
  buildGanttTicks,
  hojeISO,
  posicaoDaBarra,
  posicaoDeHoje,
  statusVisualDaLinha,
} from '../utils/ganttLayout';

/**
 * Gráfico de Gantt das ações.
 *
 * Cada linha é uma ação: o rótulo traz o título e as datas, e a barra cobre o
 * intervalo entre a DATA DE EXECUÇÃO (`data_limite`) e a DATA FINAL
 * (`prazo_final`). Ação sem data final aparece como marco de um dia.
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

const dataCurta = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

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
  }), [linhas]);

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
            {resumo.comPrazo} com prazo final
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
          <p className="mt-2 text-xs">O Gantt usa a data de execução como início da barra e o prazo final como término.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <div className="flex min-w-max">
            {/* Coluna fixa com as ações */}
            <div className={`sticky left-0 z-30 shrink-0 w-44 md:w-72 border-r ${corBorda} ${corFundo}`}>
              <div className={`h-14 flex items-end px-3 pb-2 border-b ${corBorda} ${corFundoSutil}`}>
                <span className={`text-[9px] font-black uppercase tracking-widest ${corTextoFraco}`}>Ação</span>
              </div>
              {linhas.map(linha => (
                <button
                  key={linha.task.id}
                  onClick={() => onTaskClick(linha.task)}
                  className={`h-11 w-full flex flex-col justify-center px-3 border-b text-left transition-colors ${corBorda} ${
                    isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-50'
                  }`}
                  title={linha.task.titulo}
                >
                  <span className={`text-[11px] font-bold leading-tight truncate ${corTexto}`}>{linha.task.titulo}</span>
                  <span className={`text-[9px] font-mono uppercase tracking-wider truncate ${corTextoFraco}`}>
                    {dataCurta(linha.inicio)}
                    {linha.temPrazoFinal ? ` → ${dataCurta(linha.fim)}` : ' · sem prazo final'}
                  </span>
                </button>
              ))}
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

                {linhas.map(linha => {
                  const visual = statusVisualDaLinha(linha);
                  const cor = CORES[visual];
                  const posicao = posicaoDaBarra(linha, range);
                  return (
                    <div key={linha.task.id} className={`relative h-11 border-b ${corBorda}`}>
                      <button
                        onClick={() => onTaskClick(linha.task)}
                        style={posicao}
                        className={`absolute top-1/2 -translate-y-1/2 z-10 flex items-center transition-all hover:brightness-110 active:scale-[0.98] ${
                          linha.temPrazoFinal ? `h-5 rounded-sm border ${cor.barra} ${cor.borda}` : 'h-11 justify-center'
                        }`}
                        title={`${linha.task.titulo}\nExecução: ${formatDate(linha.inicio)}${
                          linha.temPrazoFinal ? `\nPrazo final: ${formatDate(linha.fim)} (${linha.duracaoDias} dias)` : '\nSem prazo final'
                        }\nStatus: ${cor.rotulo}`}
                      >
                        {linha.temPrazoFinal ? (
                          <span className="px-1.5 text-[9px] font-black text-white truncate drop-shadow">
                            {linha.duracaoDias >= 3 ? `${linha.duracaoDias}d` : ''}
                          </span>
                        ) : (
                          <span className={`w-3 h-3 rotate-45 border ${cor.barra} ${cor.borda}`} />
                        )}
                      </button>
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
          <span className="w-px h-3 bg-rose-500" />
          Hoje
        </span>
      </div>
    </div>
  );
};
