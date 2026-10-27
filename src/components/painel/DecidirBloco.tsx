import React, { useState } from 'react';
import type { LinhaDecidir } from '../../utils/briefingDia';
import { resumoDecidir } from '../../utils/briefingDia';

/** Quantas linhas aparecem antes do "Ver mais". */
export const LINHAS_VISIVEIS = 3;

interface DecidirBlocoProps {
    linhas: LinhaDecidir[];
    pendentes: number;
    /** Marca o item como feito, ou o desfaz (volta a pendente). */
    onAlternar: (linha: LinhaDecidir) => void;
    /** O que fica no rodapé do bloco (aviso de elevações). */
    rodape?: React.ReactNode;
    isDark?: boolean;
}

const corTag = (tag: string, isDark: boolean) => {
    const t = tag.toLowerCase();
    if (t.startsWith('venceu') || t.includes('atrasad')) {
        return isDark ? 'text-rose-300 bg-rose-900/40' : 'text-[#9b1c1c] bg-[#fde8e8]';
    }
    if (t === 'hoje') return isDark ? 'text-amber-200 bg-amber-900/40' : 'text-[#5a3300] bg-[#fff1d6]';
    return isDark ? 'text-slate-300 bg-slate-700/50' : 'text-[#4a4455] bg-[#f0eff5]';
};

const DecidirBloco: React.FC<DecidirBlocoProps> = ({ linhas, pendentes, onAlternar, rodape, isDark = false }) => {
    const [aberto, setAberto] = useState(false);
    if (linhas.length === 0 && !rodape) return null;

    const visiveis = aberto ? linhas : linhas.slice(0, LINHAS_VISIVEIS);
    const escondidas = linhas.length - LINHAS_VISIVEIS;
    const suave = isDark ? 'text-slate-400' : 'text-[#5f586a]';

    return (
        <section
            aria-label="Decidir"
            className={`rounded-[20px] border p-[18px_22px] flex flex-col gap-2 ${
                isDark ? 'bg-[#151c27] border-[#2a313d]' : 'bg-white border-[#e6e3ee]'
            }`}
        >
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <h2 className="m-0 text-base font-extrabold">Decidir</h2>
                <span className={`text-[12.5px] font-semibold ${suave}`}>{resumoDecidir(pendentes)} · do briefing de hoje</span>
            </div>

            <ul className="m-0 p-0 list-none flex flex-col">
                {visiveis.map(linha => {
                    const { item, feito } = linha;
                    return (
                        <li
                            key={item.id}
                            data-testid="linha-decidir"
                            data-feito={feito ? 'sim' : 'nao'}
                            className={`flex gap-3 items-start py-2.5 border-t ${isDark ? 'border-[#2a313d]' : 'border-[#f0eff5]'}`}
                        >
                            <span
                                aria-hidden="true"
                                className={`flex-none w-6 h-6 mt-px rounded-full text-xs font-extrabold inline-flex items-center justify-center ${
                                    feito
                                        ? 'bg-[#0f7a5a] text-white'
                                        : isDark ? 'bg-violet-900/50 text-violet-200' : 'bg-[#ece6fa] text-[#4c1d95]'
                                }`}
                            >
                                {linha.numero}
                            </span>
                            <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                                    <span className={`text-[13.5px] font-extrabold ${feito ? (isDark ? 'text-slate-500' : 'text-[#8b8497]') : ''}`}>{item.quem}</span>
                                    <span className={`text-[13.5px] leading-snug ${feito ? `line-through ${isDark ? 'text-slate-500' : 'text-[#8b8497]'}` : ''}`}>{item.texto}</span>
                                    {item.tag && !feito && (
                                        <span className={`flex-none text-[11px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${corTag(item.tag, isDark)}`}>{item.tag}</span>
                                    )}
                                </div>
                                {item.recomendacao && !feito && (
                                    <p className={`m-0 text-xs leading-snug ${suave}`}>{item.recomendacao}</p>
                                )}
                            </div>
                            <button
                                type="button"
                                onClick={() => onAlternar(linha)}
                                aria-label={`${feito ? 'Desfazer' : 'Marcar como feito'}: ${item.quem}`}
                                className={`flex-none min-h-[44px] px-3.5 rounded-xl border text-[12.5px] font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7e22ce] ${
                                    isDark ? 'border-[#3b3552] text-violet-300 bg-transparent' : 'border-[#d9d4e6] text-[#4c1d95] bg-white'
                                }`}
                            >
                                {feito ? 'Desfazer' : 'Feito'}
                            </button>
                        </li>
                    );
                })}
            </ul>

            {escondidas > 0 && (
                <button
                    type="button"
                    aria-expanded={aberto}
                    onClick={() => setAberto(v => !v)}
                    className={`self-start min-h-[44px] px-1 bg-transparent text-[12.5px] font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#7e22ce] ${
                        isDark ? 'text-violet-300' : 'text-[#4c1d95]'
                    }`}
                >
                    {aberto ? `Mostrar só ${LINHAS_VISIVEIS}` : `Ver mais ${escondidas}`}
                </button>
            )}

            {rodape}
        </section>
    );
};

export default DecidirBloco;
