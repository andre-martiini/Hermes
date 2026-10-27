import React, { useState } from 'react';
import type { ResumoAvisoDoSistema } from '../../../types';

export interface SugestaoDeElevacao {
    id: string;
    titulo_acao?: string;
    ativo_possivel?: string;
    passo_que_falta?: string;
    custo_estimado?: string;
}

interface ElevacoesRodapeProps {
    /** `resumo.filas.elevacoes.total`: quantas sugestões esperam decisão. */
    total: number;
    /** `resumo.avisos_do_sistema`: o que parou de funcionar direito (antigo "Avisos do sistema"). */
    avisos: ResumoAvisoDoSistema[];
    /** Cards só são lidos quando o bloco abre. */
    sugestoes: SugestaoDeElevacao[];
    onAbrir: (aberto: boolean) => void;
    isDark?: boolean;
}

const dataCurta = (iso?: string | null) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
    return m ? `${m[3]}/${m[2]}` : '';
};

/**
 * Rodapé de Decidir: o aviso de elevações sugeridas e o que parou no sistema.
 *
 * Os cards mostram o que já existe, o que falta e o custo. A decisão
 * (aceitar, adiar, nunca) continua sendo do agente por `decidir_elevacao`:
 * aceitar cria uma ação e a vincula a um objetivo em dois passos que só ele faz.
 */
const ElevacoesRodape: React.FC<ElevacoesRodapeProps> = ({ total, avisos, sugestoes, onAbrir, isDark = false }) => {
    const [aberto, setAberto] = useState(false);
    if (total <= 0 && avisos.length === 0) return null;

    const alternar = () => {
        const proximo = !aberto;
        setAberto(proximo);
        onAbrir(proximo);
    };

    return (
        <div className={`flex flex-col gap-2.5 border-t pt-1.5 ${isDark ? 'border-[#2a313d]' : 'border-[#f0eff5]'}`}>
            <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5">
                <div className={`flex-1 basis-[280px] min-w-0 text-[12.5px] leading-snug ${isDark ? 'text-amber-200' : 'text-[#5a3300]'}`}>
                    {total > 0 && (
                        <p className="m-0">
                            <b className="font-bold">{total} {total === 1 ? 'sugestão de elevação espera' : 'sugestões de elevação esperam'} decisão.</b>
                        </p>
                    )}
                    {avisos.map(a => (
                        <p key={a.id} className="m-0" title={a.detalhe}>
                            {a.titulo}{a.desde ? ` (desde ${dataCurta(a.desde)})` : ''}.
                        </p>
                    ))}
                </div>
                {total > 0 && (
                    <button
                        type="button"
                        aria-expanded={aberto}
                        onClick={alternar}
                        className={`min-h-[44px] px-3.5 rounded-xl border text-[12.5px] font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7e22ce] ${
                            isDark ? 'border-[#8a6a1a] bg-[#3a2a0a] text-amber-200' : 'border-[#c9a24a] bg-[#fff8e6] text-[#5a3300]'
                        }`}
                    >
                        {aberto ? 'Recolher' : 'Ver sugestões'}
                    </button>
                )}
            </div>

            {aberto && (
                <div className="flex flex-col gap-2.5">
                    {sugestoes.length === 0 && (
                        <p className={`m-0 text-xs ${isDark ? 'text-slate-400' : 'text-[#5f586a]'}`}>Carregando as sugestões…</p>
                    )}
                    {sugestoes.map(s => (
                        <div
                            key={s.id}
                            data-testid="card-elevacao"
                            className={`rounded-2xl border px-4 py-3.5 ${isDark ? 'bg-[#1e293b] border-[#2a313d]' : 'bg-[#fff8e6] border-[#f0e2bd]'}`}
                        >
                            <p className="m-0 text-[13.5px] font-bold">{s.titulo_acao || 'Ação'}</p>
                            {s.ativo_possivel && (
                                <p className={`m-0 mt-1 text-[12.5px] leading-snug ${isDark ? 'text-slate-300' : 'text-[#4a4455]'}`}>
                                    <span className="font-bold">Ativo possível:</span> {s.ativo_possivel}
                                </p>
                            )}
                            {s.passo_que_falta && (
                                <p className={`m-0 mt-0.5 text-[12.5px] leading-snug ${isDark ? 'text-slate-300' : 'text-[#4a4455]'}`}>
                                    <span className="font-bold">Falta:</span> {s.passo_que_falta}
                                    {s.custo_estimado ? <span className={isDark ? 'text-slate-400' : 'text-[#5f586a]'}> · {s.custo_estimado}</span> : null}
                                </p>
                            )}
                        </div>
                    ))}
                    {sugestoes.length > 0 && (
                        <p className={`m-0 text-xs ${isDark ? 'text-slate-400' : 'text-[#5f586a]'}`}>
                            Para decidir, peça ao agente: aceitar, adiar ou descartar para sempre.
                        </p>
                    )}
                </div>
            )}
        </div>
    );
};

export default ElevacoesRodape;
