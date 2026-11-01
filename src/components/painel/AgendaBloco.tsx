import React, { useMemo, useState } from 'react';
import {
    NivelProximidade, calcularDestaque, descreverTempo, detectarConflitos, minParaHhmm, rotuloHora,
    textoDoConflito, type EventoDoDia,
} from '../../utils/agendaProximidade';
import type { ItemPreparo } from '../../utils/briefingDia';
import { usePrefersReducedMotion } from './useRelogio';

/** Linha do tempo de 7h às 19h, como no design. */
const JANELA_INICIO_MIN = 7 * 60;
const JANELA_FIM_MIN = 19 * 60;
const MARCAS = [7, 9, 11, 13, 15, 17, 19];
const MAX_CONFLITOS_NO_AVISO = 3;

const ESTILO_NIVEL: Record<NivelProximidade, { rotulo: string; claro: string; escuro: string; animacao: string }> = {
    normal: {
        rotulo: 'Próximo',
        claro: 'bg-[#f6f6f9] border-[#ececf1] text-[#151c27]',
        escuro: 'bg-[#1e293b] border-[#2a313d] text-slate-200',
        animacao: '',
    },
    atencao: {
        rotulo: 'Em breve',
        claro: 'bg-[#fff1d6] border-[#e3b865] text-[#5a3300]',
        escuro: 'bg-[#3a2a0a] border-[#8a6a1a] text-amber-200',
        animacao: 'painel-brilho-suave',
    },
    urgente: {
        rotulo: 'Já vai começar',
        claro: 'bg-[#4c1d95] border-[#4c1d95] text-white',
        escuro: 'bg-[#4c1d95] border-[#7e22ce] text-white',
        animacao: 'painel-pulso',
    },
    agora: {
        rotulo: 'Agora',
        claro: 'bg-[#e3f4ec] border-[#9fd6c0] text-[#0b5a43]',
        escuro: 'bg-[#0b3b2c] border-[#1f7a5a] text-emerald-200',
        animacao: '',
    },
};

/** As animações vivem aqui, junto de quem as usa; `prefers-reduced-motion` corta as duas. */
const CSS_ANIMACOES = `
@keyframes painel-brilho-suave{0%,100%{box-shadow:0 0 0 0 rgba(197,134,20,.40)}50%{box-shadow:0 0 0 6px rgba(197,134,20,0)}}
@keyframes painel-pulso{0%,100%{box-shadow:0 0 0 0 rgba(76,29,149,.55)}50%{box-shadow:0 0 0 9px rgba(76,29,149,0)}}
.painel-brilho-suave{animation:painel-brilho-suave 3.2s ease-in-out infinite}
.painel-pulso{animation:painel-pulso 1.2s ease-in-out infinite}
@media (prefers-reduced-motion: reduce){.painel-brilho-suave,.painel-pulso{animation:none}}
`;

/**
 * Avisos de conflito que o André já leu e dispensou no X. Ficam só no aparelho e só no dia
 * (a chave carrega a data de Brasília): amanhã o mesmo conflito, se existir, volta a aparecer.
 * A chave é o texto do aviso (títulos e horários), não o id do evento: o id é a posição na
 * lista (`agenda-0`) e mudaria de dono quando a agenda muda, escondendo um conflito novo.
 */
const hoje = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Sao_Paulo' });
const CHAVE_OCULTOS = 'painel-agenda-conflitos-ocultos';
const chaveDoAviso = (texto: string) => `${hoje()}|${texto}`;
const lerOcultos = (): string[] => {
    try {
        const lista = JSON.parse(localStorage.getItem(CHAVE_OCULTOS) || '[]');
        return Array.isArray(lista) ? lista.filter((k: unknown) => typeof k === 'string' && k.startsWith(hoje())) : [];
    } catch {
        return [];
    }
};
const guardarOcultos = (lista: string[]) => {
    try {
        localStorage.setItem(CHAVE_OCULTOS, JSON.stringify(lista));
    } catch {
        /* sem armazenamento: o aviso some só até recarregar */
    }
};

/** Faixa (0 ou 1) de cada compromisso, para os que se sobrepõem não ficarem um sobre o outro. */
const faixas = (eventos: EventoDoDia[]): Map<string, number> => {
    const fimPorFaixa = [-1, -1];
    const mapa = new Map<string, number>();
    [...eventos].sort((a, b) => a.inicio - b.inicio).forEach(e => {
        let faixa = fimPorFaixa.findIndex(fim => fim <= e.inicio);
        if (faixa === -1) faixa = 1;
        fimPorFaixa[faixa] = Math.max(fimPorFaixa[faixa], e.fim);
        mapa.set(e.id, faixa);
    });
    return mapa;
};

const pct = (min: number) =>
    `${(Math.max(0, Math.min(100, ((min - JANELA_INICIO_MIN) / (JANELA_FIM_MIN - JANELA_INICIO_MIN)) * 100))).toFixed(2)}%`;

interface AgendaBlocoProps {
    eventos: EventoDoDia[];
    /** Compromissos de dia inteiro (marcadores), só na lista completa. */
    diaInteiro?: string[];
    agoraMin: number;
    preparo: ItemPreparo[];
    isDark?: boolean;
    /** Gravação de reunião no ar (motor de Reuniões em Tempo Real). */
    gravacao?: { gravando: boolean; titulo: string | null; claudeAcompanhando: boolean };
    /** Abre a tela da reunião já com este evento escolhido. Sem ele, não há botão Gravar. */
    onGravar?: (evento: EventoDoDia) => void;
    onParar?: () => void;
    onAbrirGravacao?: () => void;
}

const BotaoGravar: React.FC<{ evento: EventoDoDia; onGravar: (e: EventoDoDia) => void; isDark: boolean }> = ({ evento, onGravar, isDark }) => (
    <button
        type="button"
        data-testid="botao-gravar"
        onClick={() => onGravar(evento)}
        aria-label={`Gravar a reunião ${evento.titulo}`}
        title="Gravar esta reunião; o Claude pode acompanhar"
        className={`flex-none inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11.5px] font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7e22ce] ${
            isDark ? 'border-rose-400/40 text-rose-300 hover:bg-rose-500/10' : 'border-rose-200 text-rose-700 bg-white hover:bg-rose-50'
        }`}
    >
        <span className="h-2 w-2 rounded-full bg-rose-500" aria-hidden="true" />
        Gravar
    </button>
);

const AgendaBloco: React.FC<AgendaBlocoProps> = ({
    eventos, diaInteiro = [], agoraMin, preparo, isDark = false, gravacao, onGravar, onParar, onAbrirGravacao,
}) => {
    const gravando = !!gravacao?.gravando;
    const podeGravar = !!onGravar && !gravando;
    const [aberta, setAberta] = useState(false);
    const [ocultos, setOcultos] = useState<string[]>(lerOcultos);
    const reduzido = usePrefersReducedMotion();
    const destaque = useMemo(() => calcularDestaque(eventos, agoraMin), [eventos, agoraMin]);
    const conflitos = useMemo(() => detectarConflitos(eventos), [eventos]);
    const pares = useMemo(
        () => conflitos.pares.filter(par => !ocultos.includes(chaveDoAviso(textoDoConflito(par)))),
        [conflitos, ocultos],
    );
    const ocultar = (par: (typeof conflitos.pares)[number]) => {
        const novos = [...ocultos, chaveDoAviso(textoDoConflito(par))];
        setOcultos(novos);
        guardarOcultos(novos);
    };
    const faixaDe = useMemo(() => faixas(eventos), [eventos]);

    const estilo = ESTILO_NIVEL[destaque.nivel];
    const animar = !reduzido && !!estilo.animacao;
    const alvo = destaque.alvo;
    const titulo = !alvo
        ? 'Sem mais compromissos hoje'
        : destaque.nivel === 'agora' ? alvo.titulo : `${minParaHhmm(alvo.inicio)} · ${alvo.titulo}`;
    const tempo = !alvo || destaque.minutos === null
        ? ''
        : destaque.nivel === 'agora' ? `até ${minParaHhmm(alvo.fim)}` : descreverTempo(destaque.minutos);

    const texto = isDark ? 'text-slate-300' : 'text-[#4a4455]';
    const suave = isDark ? 'text-slate-500' : 'text-[#5f586a]';

    return (
        <section
            aria-label="Agenda de hoje"
            className={`rounded-[20px] border p-[18px_22px] flex flex-col gap-3 ${
                isDark ? 'bg-[#151c27] border-[#2a313d]' : 'bg-white border-[#ececf1]'
            }`}
        >
            <style>{CSS_ANIMACOES}</style>
            <div className="flex items-center justify-between gap-3">
                <div>
                    <h2 className="m-0 text-base font-extrabold">Agenda de hoje</h2>
                    <p className={`m-0 mt-0.5 text-[12.5px] font-semibold ${suave}`}>
                        {eventos.length} {eventos.length === 1 ? 'compromisso' : 'compromissos'} · agora {minParaHhmm(agoraMin)}
                    </p>
                </div>
                <button
                    type="button"
                    aria-expanded={aberta}
                    aria-label="Mostrar ou recolher a agenda completa"
                    title="Agenda completa"
                    onClick={() => setAberta(v => !v)}
                    className={`w-11 h-11 rounded-xl border inline-flex items-center justify-center focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7e22ce] ${
                        isDark ? 'border-[#2a313d] text-slate-300' : 'border-[#e1dee9] text-[#4a4455]'
                    }`}
                >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ transform: aberta ? 'rotate(180deg)' : 'none' }}>
                        <path d="M6 9l6 6 6-6" />
                    </svg>
                </button>
            </div>

            {pares.length > 0 && (
                <div
                    data-testid="aviso-conflito"
                    role="alert"
                    className={`flex gap-2.5 items-start px-3.5 py-2.5 rounded-xl border ${
                        isDark ? 'bg-[#3a2a0a] border-[#8a6a1a] text-amber-200' : 'bg-[#fff8e6] border-[#ecd49a] text-[#5a3300]'
                    }`}
                >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="flex-none mt-px">
                        <path d="M12 3 2 20h20L12 3z" /><path d="M12 10v4" /><path d="M12 17h.01" />
                    </svg>
                    <div className="flex-1 min-w-0 text-[13px] leading-snug font-semibold">
                        {pares.slice(0, MAX_CONFLITOS_NO_AVISO).map(par => (
                            <div key={`${par.a.id}-${par.b.id}`} data-testid="linha-conflito" className="flex items-start gap-2">
                                <p className="m-0 flex-1 min-w-0">{textoDoConflito(par)}</p>
                                <button
                                    type="button"
                                    onClick={() => ocultar(par)}
                                    aria-label={`Ocultar aviso: ${textoDoConflito(par)}`}
                                    title="Ocultar este aviso"
                                    className="flex-none -mt-1.5 -mr-1.5 w-9 h-9 rounded-lg inline-flex items-center justify-center bg-transparent opacity-70 hover:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7e22ce]"
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" aria-hidden="true">
                                        <path d="M6 6l12 12M18 6 6 18" />
                                    </svg>
                                </button>
                            </div>
                        ))}
                        {pares.length > MAX_CONFLITOS_NO_AVISO && (
                            <p className="m-0">e mais {pares.length - MAX_CONFLITOS_NO_AVISO}.</p>
                        )}
                    </div>
                </div>
            )}

            <div
                data-testid="caixa-proximo"
                data-nivel={destaque.nivel}
                data-animado={animar ? 'sim' : 'nao'}
                className={`flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-3.5 py-2.5 rounded-xl border ${
                    isDark ? estilo.escuro : estilo.claro
                } ${animar ? estilo.animacao : ''}`}
            >
                <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 min-w-0">
                    <span className="text-[11px] font-bold tracking-[.08em] uppercase">{estilo.rotulo}</span>
                    <span className="text-sm font-bold">{titulo}</span>
                </div>
                <div className="flex items-center gap-2.5">
                    <span className="text-[13px] font-extrabold whitespace-nowrap">{tempo}</span>
                    {podeGravar && alvo && <BotaoGravar evento={alvo} onGravar={onGravar!} isDark={isDark} />}
                </div>
            </div>

            {gravando && (
                <div
                    data-testid="selo-gravando"
                    role="status"
                    className={`flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-3.5 py-2.5 rounded-xl border ${
                        isDark ? 'bg-rose-500/10 border-rose-400/40 text-rose-200' : 'bg-rose-50 border-rose-200 text-rose-900'
                    }`}
                >
                    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 min-w-0">
                        <span className={`h-2 w-2 rounded-full bg-rose-500 ${reduzido ? '' : 'animate-pulse'}`} aria-hidden="true" />
                        <span className="text-[11px] font-bold tracking-[.08em] uppercase">Gravando</span>
                        {gravacao?.titulo && <span className="text-sm font-bold">{gravacao.titulo}</span>}
                        <span
                            data-testid="selo-claude"
                            data-ativo={gravacao?.claudeAcompanhando ? 'sim' : 'nao'}
                            className={`text-[11.5px] font-bold ${gravacao?.claudeAcompanhando ? (isDark ? 'text-emerald-300' : 'text-emerald-700') : suave}`}
                        >
                            {gravacao?.claudeAcompanhando ? '· Claude acompanhando' : '· Claude não está acompanhando'}
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        {onAbrirGravacao && (
                            <button
                                type="button"
                                onClick={onAbrirGravacao}
                                className={`rounded-lg border px-2.5 py-1 text-[11.5px] font-bold ${isDark ? 'border-rose-400/40 hover:bg-rose-500/10' : 'border-rose-200 bg-white hover:bg-rose-100'}`}
                            >
                                Abrir
                            </button>
                        )}
                        {onParar && (
                            <button
                                type="button"
                                data-testid="botao-parar"
                                onClick={onParar}
                                title="Parar a gravação; a transcrição vai sozinha para o Drive"
                                className="rounded-lg bg-rose-600 px-2.5 py-1 text-[11.5px] font-bold text-white hover:bg-rose-500"
                            >
                                Parar
                            </button>
                        )}
                    </div>
                </div>
            )}

            <div className="flex flex-col gap-1" aria-hidden="true">
                <div className={`relative h-[50px] rounded-[10px] overflow-hidden ${isDark ? 'bg-[#1e293b]' : 'bg-[#f6f6f9]'}`}>
                    {eventos
                        .filter(e => e.fim > JANELA_INICIO_MIN && e.inicio < JANELA_FIM_MIN)
                        .map(e => {
                            const marcado = alvo?.id === e.id && destaque.nivel !== 'normal';
                            const faixa = faixaDe.get(e.id) ?? 0;
                            return (
                                <div
                                    key={e.id}
                                    data-testid="bloco-agenda"
                                    data-marcado={marcado ? 'sim' : 'nao'}
                                    data-fora-da-agenda={e.foraDaAgenda ? 'sim' : 'nao'}
                                    title={`${e.titulo} · ${rotuloHora(e.inicio)}${e.fimDeclarado ? `–${rotuloHora(e.fim)}` : ''}`}
                                    className={`absolute h-5 rounded-[5px] box-border ${marcado && animar ? estilo.animacao : ''}`}
                                    style={{
                                        top: faixa === 0 ? 6 : 26,
                                        left: pct(e.inicio),
                                        width: `${(parseFloat(pct(Math.min(e.fim, JANELA_FIM_MIN))) - parseFloat(pct(Math.max(e.inicio, JANELA_INICIO_MIN)))).toFixed(2)}%`,
                                        background: e.foraDaAgenda ? '#f3d58a' : faixa === 0 ? '#7e22ce' : '#2f6f5e',
                                        border: marcado ? '2px solid #151c27' : e.foraDaAgenda ? '2px dashed #8a4b00' : '0',
                                    }}
                                />
                            );
                        })}
                    <div
                        data-testid="marcador-agora"
                        className="absolute top-0 bottom-0 w-0.5 bg-[#7e22ce]"
                        style={{ left: pct(agoraMin) }}
                    />
                </div>
                <div className={`relative h-4 text-[11px] font-semibold ${suave}`}>
                    {MARCAS.map(h => (
                        <span key={h} className="absolute" style={{ left: pct(h * 60), transform: h === 7 ? 'none' : h === 19 ? 'translateX(-100%)' : 'translateX(-50%)' }}>
                            {h}h
                        </span>
                    ))}
                </div>
            </div>

            {preparo.length > 0 && (
                <div data-testid="faixa-preparo" className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                    <span className={`text-[11px] font-bold tracking-[.08em] uppercase ${suave}`}>Preparo</span>
                    {preparo.map(p => (
                        <span
                            key={`${p.dia}-${p.texto}`}
                            title={p.data}
                            className={`text-xs leading-snug rounded-[10px] border px-2.5 py-1 ${
                                isDark ? 'bg-[#1e293b] border-[#2a313d] text-slate-300' : 'bg-[#f6f6f9] border-[#ececf1] text-[#3d3747]'
                            }`}
                        >
                            <b className="font-bold">{p.rotulo}</b> {p.texto}
                        </span>
                    ))}
                </div>
            )}

            {aberta && (
                <div className={`flex flex-col border-t ${isDark ? 'border-[#2a313d]' : 'border-[#f0eff5]'}`}>
                    {diaInteiro.map(t => (
                        <div key={`di-${t}`} className="flex gap-3 items-baseline py-2.5">
                            <span className={`flex-none w-24 text-[12.5px] font-bold ${texto}`}>Dia todo</span>
                            <p className="m-0 text-[13.5px] font-semibold leading-snug">{t}</p>
                        </div>
                    ))}
                    {eventos.map(e => (
                        <div key={e.id} className="flex gap-3 items-baseline py-2.5">
                            <span className={`flex-none w-24 text-[12.5px] font-bold ${texto}`}>
                                {minParaHhmm(e.inicio)}{e.fimDeclarado ? `–${minParaHhmm(e.fim)}` : ''}
                            </span>
                            <div className="min-w-0">
                                <p className="m-0 text-[13.5px] font-semibold leading-snug">
                                    {e.titulo}{e.foraDaAgenda ? ' (não está na agenda)' : ''}
                                </p>
                                {conflitos.ids.has(e.id) && (
                                    <p className={`m-0 mt-0.5 text-[11.5px] font-bold ${isDark ? 'text-amber-300' : 'text-[#8a4b00]'}`}>
                                        Horário sobrepõe outro compromisso
                                    </p>
                                )}
                            </div>
                            {podeGravar && <div className="ml-auto self-center"><BotaoGravar evento={e} onGravar={onGravar!} isDark={isDark} /></div>}
                        </div>
                    ))}
                    {eventos.length === 0 && diaInteiro.length === 0 && (
                        <p className={`m-0 py-2.5 text-[13px] ${suave}`}>Nenhum compromisso hoje.</p>
                    )}
                </div>
            )}
        </section>
    );
};

export default AgendaBloco;
