import React from 'react';
import { avaliarMeta, type EstadoPerfil, type IndicadorAvaliado, type MetaPerfil } from '../../utils/perfilEstrategia';

/**
 * Perfil de 3 meses de uma meta: por indicador, atual / esperado de hoje / próximo marco,
 * com o selo do estado e de onde veio o número; e a linha do tempo dos marcos datados.
 * O cálculo é o de `src/utils/perfilEstrategia.ts` (o mesmo do MCP). Nada aqui é digitável:
 * valor de fonte automática não se corrige na mão, e o manual entra pelo histórico.
 */

const ROTULO: Record<EstadoPerfil, string> = {
    no_perfil: 'No perfil', atrasado: 'Atrasado', adiantado: 'Adiantado', sem_dado: 'Sem dado',
};

const corDoEstado = (estado: EstadoPerfil | null, isDark: boolean) => {
    switch (estado) {
        case 'no_perfil': return isDark ? 'bg-emerald-900/40 text-emerald-200' : 'bg-emerald-50 text-emerald-800';
        case 'atrasado': return isDark ? 'bg-rose-900/40 text-rose-200' : 'bg-rose-50 text-rose-800';
        case 'adiantado': return isDark ? 'bg-violet-900/40 text-violet-200' : 'bg-violet-50 text-violet-800';
        default: return isDark ? 'bg-slate-800 text-slate-300' : 'bg-slate-100 text-slate-700';
    }
};

const dataCurta = (iso: string) => {
    const [ano, mes, dia] = iso.split('-');
    return `${dia}/${mes}/${ano.slice(2)}`;
};

/** Dinheiro vem em centavos; o resto já na unidade. */
export const formatarValor = (valor: number | null, ind: Pick<IndicadorAvaliado, 'em_centavos' | 'unidade'>) => {
    if (valor === null) return '—';
    if (ind.em_centavos) {
        return (valor / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
    }
    return `${valor.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}${ind.unidade ? ` ${ind.unidade}` : ''}`;
};

export const Selo: React.FC<{ estado: EstadoPerfil | null; isDark: boolean }> = ({ estado, isDark }) =>
    estado ? (
        <span className={`inline-flex shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${corDoEstado(estado, isDark)}`}>
            {ROTULO[estado]}
        </span>
    ) : null;

interface PerfilDaMetaProps {
    meta: MetaPerfil;
    atuais: Record<string, number | null>;
    origens: Record<string, 'automatica' | 'manual'>;
    hoje: string;
    isDark: boolean;
    /** Cartão da lista: só os indicadores, sem a linha do tempo. */
    compacto?: boolean;
}

const PerfilDaMeta: React.FC<PerfilDaMetaProps> = ({ meta, atuais, origens, hoje, isDark, compacto = false }) => {
    const perfil = avaliarMeta(meta, atuais, hoje);
    const datados = (meta.marcos ?? [])
        .filter((m): m is Exclude<typeof m, string> => typeof m === 'object' && m !== null && !!m.dataAlvo)
        .sort((a, b) => String(a.dataAlvo).localeCompare(String(b.dataAlvo)));
    if (!perfil.indicadores.length && !datados.length) return null;

    const suave = isDark ? 'text-slate-400' : 'text-slate-500';
    const caixa = isDark ? 'rounded-xl border border-slate-800 bg-slate-950/60' : 'rounded-xl border border-slate-200 bg-slate-50';
    const estadoDoMarco = new Map(perfil.marcos_sem_numero.map(m => [m.id, m.estado]));

    return (
        <section aria-label="Perfil da meta" className={`p-3 ${caixa}`} onClick={e => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between gap-2">
                <p className={`text-[10px] font-bold uppercase tracking-wider ${suave}`}>
                    Perfil{meta.ciclo?.fim ? ` até ${dataCurta(meta.ciclo.fim)}` : ''}
                </p>
                <Selo estado={perfil.estado} isDark={isDark} />
            </div>

            {perfil.indicadores.length > 0 && (
                <ul className="m-0 list-none space-y-2 p-0">
                    {perfil.indicadores.map(ind => (
                        <li key={ind.chave} data-testid="perfil-indicador" className="flex flex-col gap-1">
                            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                                <span className="text-xs font-bold">{ind.rotulo}</span>
                                <Selo estado={ind.estado} isDark={isDark} />
                            </div>
                            <dl className="m-0 grid grid-cols-3 gap-2 text-[11px]">
                                <div>
                                    <dt className={`text-[9px] font-bold uppercase tracking-wider ${suave}`}>Atual</dt>
                                    <dd className="m-0 font-bold tabular-nums">{formatarValor(ind.atual, ind)}</dd>
                                </div>
                                <div>
                                    <dt className={`text-[9px] font-bold uppercase tracking-wider ${suave}`}>Esperado hoje</dt>
                                    <dd className="m-0 font-semibold tabular-nums">{formatarValor(ind.esperado_hoje, ind)}</dd>
                                </div>
                                <div>
                                    <dt className={`text-[9px] font-bold uppercase tracking-wider ${suave}`}>Próximo marco</dt>
                                    <dd className="m-0 font-semibold tabular-nums">
                                        {ind.proximo_marco ? `${formatarValor(ind.proximo_marco.valor, ind)} em ${dataCurta(ind.proximo_marco.data)}` : '—'}
                                    </dd>
                                </div>
                            </dl>
                            <p className={`m-0 text-[10px] ${suave}`}>
                                {origens[ind.chave] === 'automatica'
                                    ? `Automático (${ind.fonte === 'guardado_acumulado' ? 'Poupança paga no ciclo' : ind.fonte})`
                                    : 'Manual (último registro do histórico)'}
                            </p>
                        </li>
                    ))}
                </ul>
            )}

            {!compacto && datados.length > 0 && (
                <ol aria-label="Marcos" className={`m-0 mt-3 list-none space-y-1.5 border-t p-0 pt-3 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                    {datados.map(m => {
                        const vencido = !m.concluido && String(m.dataAlvo) < hoje;
                        return (
                            <li key={m.id || m.dataAlvo} data-testid="perfil-marco" className="flex items-start gap-2 text-xs">
                                <span aria-hidden="true" className={`mt-1 h-2 w-2 shrink-0 rounded-full ${m.concluido ? 'bg-emerald-500' : vencido ? 'bg-rose-500' : 'bg-[#7800ce]'}`} />
                                <span className="w-16 shrink-0 font-bold tabular-nums">{dataCurta(String(m.dataAlvo))}</span>
                                <span className={`flex-1 ${m.concluido ? `line-through ${suave}` : ''}`}>{m.descricao}</span>
                                {estadoDoMarco.get(m.id) === 'atrasado' && <Selo estado="atrasado" isDark={isDark} />}
                            </li>
                        );
                    })}
                </ol>
            )}
        </section>
    );
};

export default PerfilDaMeta;
