import React from 'react';
import { descreverDias, type LinhaAgentePrepara } from '../../utils/briefingDia';

const DIAS_SEMANA = ['domingo', 'segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado'];
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];

export const saudacaoDaHora = (agora: Date): string => {
    const h = agora.getHours();
    return h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite';
};

const caixa = (isDark: boolean, raio = 'rounded-2xl') =>
    `${raio} border ${isDark ? 'bg-[#151c27] border-[#2a313d]' : 'bg-white border-[#ececf1]'}`;

// ---------------------------------------------------------------------------

export const CabecalhoDoDia: React.FC<{
    agora: Date;
    acoesHoje: number;
    emEspera: number;
    isDark?: boolean;
}> = ({ agora, acoesHoje, emEspera, isDark = false }) => (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div>
            <p className={`m-0 text-xs font-bold uppercase tracking-[.08em] ${isDark ? 'text-slate-400' : 'text-[#5f586a]'}`}>
                {saudacaoDaHora(agora)}, André · {DIAS_SEMANA[agora.getDay()]}
            </p>
            <h1 className="m-0 mt-0.5 text-[28px] font-extrabold tracking-[-0.015em]">
                {agora.getDate()} de {MESES[agora.getMonth()]}
            </h1>
        </div>
        <p className={`m-0 text-[13px] font-semibold ${isDark ? 'text-slate-400' : 'text-[#5f586a]'}`}>
            {acoesHoje} {acoesHoje === 1 ? 'ação hoje' : 'ações hoje'} · {emEspera} em espera
        </p>
    </header>
);

// ---------------------------------------------------------------------------

export interface PrazoFinal {
    id: string;
    titulo: string;
    prazo: string;
    dias: number;
}

const corDoPrazo = (dias: number, isDark: boolean) =>
    dias <= 2 ? (isDark ? 'text-rose-300' : 'text-[#9b1c1c]') : (isDark ? 'text-amber-300' : 'text-[#8a4b00]');

export const PrazosFinais: React.FC<{
    prazos: PrazoFinal[];
    isDark?: boolean;
    /** `faixa`: uma linha só (retrato). `lista`: uma por linha (coluna lateral). */
    variante?: 'faixa' | 'lista';
}> = ({ prazos, isDark = false, variante = 'faixa' }) => {
    if (prazos.length === 0) return null;
    const lista = variante === 'lista';
    return (
        <section
            aria-label="Prazos finais"
            className={`${caixa(isDark, lista ? 'rounded-[20px]' : 'rounded-2xl')} ${lista ? 'px-[22px] py-[18px] flex flex-col gap-2' : 'px-[18px] py-2.5 flex flex-wrap items-center gap-x-[22px] gap-y-1.5'}`}
        >
            <h2 className={`m-0 text-[13px] font-extrabold ${isDark ? 'text-slate-300' : 'text-[#4a4455]'}`}>Prazos finais</h2>
            {prazos.map(p => (
                <div key={p.id} className={`flex items-center gap-2.5 ${lista ? 'py-1.5 gap-3' : 'min-h-[36px]'}`}>
                    <span className={`flex-none text-[11.5px] font-bold px-2 py-1 rounded-lg ${isDark ? 'bg-slate-700/50 text-slate-300' : 'bg-[#f0eff5] text-[#4a4455]'}`}>
                        {p.prazo.slice(8, 10)}/{p.prazo.slice(5, 7)}
                    </span>
                    <span className={`text-[13px] font-semibold leading-snug ${lista ? 'flex-1 min-w-0' : ''}`}>{p.titulo}</span>
                    <span className={`flex-none text-xs font-bold whitespace-nowrap ${corDoPrazo(p.dias, isDark)}`}>{descreverDias(p.dias)}</span>
                </div>
            ))}
        </section>
    );
};

// ---------------------------------------------------------------------------

export const AgentePreparaHoje: React.FC<{ linhas: LinhaAgentePrepara[]; isDark?: boolean }> = ({ linhas, isDark = false }) => (
    <>
        {linhas.map(l => (
            <div
                key={`${l.acaoId}-${l.texto}`}
                data-testid="agente-prepara-hoje"
                className={`flex flex-wrap items-baseline gap-x-2.5 gap-y-1 px-3.5 py-2.5 rounded-xl border ${
                    isDark ? 'bg-violet-950/40 border-violet-800/50' : 'bg-[#f3effc] border-[#e0d6f5]'
                }`}
            >
                <span className={`text-[11px] font-bold tracking-[.08em] uppercase ${isDark ? 'text-violet-300' : 'text-[#4c1d95]'}`}>O agente prepara hoje</span>
                <span className={`text-[13px] leading-snug ${isDark ? 'text-violet-100' : 'text-[#2e2447]'}`}>
                    <b className="font-bold">{l.acao}:</b> {l.texto}
                </span>
            </div>
        ))}
    </>
);

// ---------------------------------------------------------------------------

export const AvisosDoAgente: React.FC<{ avisos: Array<{ texto: string }>; isDark?: boolean }> = ({ avisos, isDark = false }) => {
    if (avisos.length === 0) return null;
    return (
        <section aria-label="Avisos do agente" className={`${caixa(isDark)} px-[18px] py-3 flex flex-col gap-0.5`}>
            <h2 className={`m-0 mb-0.5 text-[13px] font-extrabold ${isDark ? 'text-slate-300' : 'text-[#4a4455]'}`}>Avisos do agente</h2>
            {avisos.map(a => (
                <p key={a.texto} className={`m-0 text-[12.5px] leading-normal ${isDark ? 'text-slate-300' : 'text-[#4a4455]'}`}>{a.texto}</p>
            ))}
        </section>
    );
};

// ---------------------------------------------------------------------------

export const LinkDiscreto: React.FC<{
    titulo: string;
    subtitulo: string;
    onClick: () => void;
    isDark?: boolean;
}> = ({ titulo, subtitulo, onClick, isDark = false }) => (
    <button
        type="button"
        onClick={onClick}
        className={`${caixa(isDark)} w-full min-h-[44px] flex items-center gap-3.5 px-[18px] py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7e22ce]`}
    >
        <span className="flex-1 min-w-0">
            <span className="block text-sm font-bold">{titulo}</span>
            <span className={`block mt-0.5 text-[12.5px] ${isDark ? 'text-slate-400' : 'text-[#5f586a]'}`}>{subtitulo}</span>
        </span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="flex-none opacity-70">
            <path d="M9 6l6 6-6 6" />
        </svg>
    </button>
);
