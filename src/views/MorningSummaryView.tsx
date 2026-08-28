/**
 * Resumo Matinal — a primeira tela do dia (viewMode 'home').
 *
 * Lê `resumo_matinal/{YYYY-MM-DD}`, produzido às 04:30 BRT por
 * functions/morning_summary.py. Esta view NÃO calcula nada: todos os números,
 * a escolha dos focos e as contagens de fila já chegam prontos do backend, que
 * os computa em Python de forma determinística. Se algo parecer errado aqui, o
 * lugar de corrigir é lá — o objetivo é que o que se vê seja auditável.
 *
 * O que esta tela mostra e o dashboard não mostra:
 *   - a herança da madrugada (quantas ações o reset das 00:00 empurrou para hoje);
 *   - as filas de decisão que só existem dentro de outra tela;
 *   - as metas de estratégia paradas há dias.
 * O que já está no dashboard (carga semanal detalhada, gráficos financeiros,
 * telemetria de saúde) é deliberadamente deixado de fora — daí os atalhos.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { doc, onSnapshot, setDoc } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from '../../firebase';
import { ResumoAcao, ResumoFila, ResumoFocoRegra, ResumoMatinal, ResumoMeta } from '../../types';

export type MorningSummaryRoute = 'gallery' | 'finance' | 'saude' | 'diario' | 'strategy' | 'whatsapp' | 'contacts' | 'dashboard';

interface MorningSummaryViewProps {
    isDark?: boolean;
    onOpenTask?: (taskId: string) => void;
    onNavigate?: (route: MorningSummaryRoute) => void;
    onAskCopiloto?: (prompt: string) => void;
}

/** Dia local do usuário — mesma referência que o backend usa (America/Sao_Paulo). */
const localTodayStr = (): string => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
};

// "YYYY-MM-DD" -> "20 de agosto". Constrói em horário local (não via `new Date(iso)`,
// que interpreta a string como UTC e erra o dia em fusos negativos).
const formatDia = (dateStr?: string): string => {
    if (!dateStr) return '';
    const [y, m, d] = dateStr.split('-').map(Number);
    if (!y || !m || !d) return dateStr;
    return new Date(y, m - 1, d).toLocaleDateString('pt-BR', { day: '2-digit', month: 'long' });
};

const formatDiaCurto = (dateStr?: string): string => {
    if (!dateStr) return '';
    const [, m, d] = dateStr.split('-');
    return `${d}/${m}`;
};

const saudacao = (): string => {
    const h = new Date().getHours();
    if (h < 5) return 'Boa madrugada';
    if (h < 12) return 'Bom dia';
    if (h < 18) return 'Boa tarde';
    return 'Boa noite';
};

const formatDuracao = (minutos: number): string => {
    const h = Math.floor(minutos / 60);
    const m = minutos % 60;
    if (!h) return `${m}min`;
    return m ? `${h}h${String(m).padStart(2, '0')}` : `${h}h`;
};

const REGRA_LABEL: Record<ResumoFocoRegra, string> = {
    prazo_final_iminente: 'Prazo final',
    degradacao_critica: 'Adiada demais',
    sla_estourado: 'Cobrança',
    meta_parada: 'Meta parada',
    agendada: 'Hora marcada',
    fila_avanco: 'Fila de avanço',
};

const REGRA_TOM: Record<ResumoFocoRegra, 'urgente' | 'atencao' | 'neutro'> = {
    prazo_final_iminente: 'urgente',
    degradacao_critica: 'urgente',
    sla_estourado: 'atencao',
    meta_parada: 'atencao',
    agendada: 'neutro',
    fila_avanco: 'neutro',
};

// Consolidações de WhatsApp NÃO aparecem aqui: consolidar é muitas vezes um fim
// em si (ler o que foi dito), e nem anexar a uma ação nem deixar como está são
// decisões pendentes. Ver o comentário em morning_summary._coletar_filas.
const FILA_LABEL: Record<string, string> = {
    sugestoes_vinculo: 'Sugestões de vínculo',
    fusoes_contatos: 'Fusões de contato',
    notificacoes_ia: 'Notificações na fila',
    contas: 'Contas vencendo',
};

const ROTAS_VALIDAS: MorningSummaryRoute[] = ['gallery', 'finance', 'saude', 'diario', 'strategy', 'whatsapp', 'contacts', 'dashboard'];

// Fila que não tem tela precisa dizer onde a coisa acontece de verdade.
const FILA_NOTA: Record<string, string> = {
    notificacoes_ia: 'Chegam pelo Telegram no horário de cada uma — é lá que você marca útil ou dispensa.',
};

const FILA_ICONE: Record<string, string> = {
    sugestoes_vinculo: '🔗',
    fusoes_contatos: '👥',
    notificacoes_ia: '🔔',
    contas: '💸',
};

const LANE_LABEL: Record<string, string> = {
    avanco: 'Avanço',
    continuo: 'Contínuo',
    aguardando_terceiro: 'Aguardando terceiro',
};

// --------------------------------------------------------------------------- //

const Secao: React.FC<{
    titulo: string;
    isDark: boolean;
    acao?: React.ReactNode;
    children: React.ReactNode;
    className?: string;
}> = ({ titulo, isDark, acao, children, className = '' }) => (
    <section
        className={`rounded-2xl border p-5 ${
            isDark ? 'bg-[#151c27] border-[#2a313d] text-white' : 'bg-white border-[#f3f4f6] text-[#151c27]'
        } ${className}`}
        style={{
            boxShadow: isDark
                ? '0 6px 12px rgba(0,0,0,0.4), 0 4px 4px rgba(0,0,0,0.2)'
                : '0 6px 12px rgba(21,28,39,0.05), 0 4px 4px rgba(21,28,39,0.03)',
        }}
    >
        <div className="flex items-center justify-between mb-4">
            <h3 className={`text-xs font-bold uppercase tracking-[0.05em] ${isDark ? 'text-[#ebf1ff]' : 'text-[#151c27]'}`}>
                {titulo}
            </h3>
            {acao}
        </div>
        {children}
    </section>
);

const Vazio: React.FC<{ isDark: boolean; children: React.ReactNode }> = ({ isDark, children }) => (
    <p className={`text-sm ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>{children}</p>
);

const Pill: React.FC<{
    label: string;
    valor: number | string;
    tom?: 'neutro' | 'atencao' | 'urgente';
    isDark: boolean;
    onClick?: () => void;
}> = ({ label, valor, tom = 'neutro', isDark, onClick }) => {
    const cores =
        tom === 'urgente'
            ? isDark ? 'border-red-900/60 bg-red-950/40 text-red-200' : 'border-red-200 bg-red-50 text-red-800'
            : tom === 'atencao'
            ? isDark ? 'border-amber-900/60 bg-amber-950/30 text-amber-200' : 'border-amber-200 bg-amber-50 text-amber-800'
            : isDark ? 'border-[#2a313d] bg-[#0f1520] text-slate-300' : 'border-slate-200 bg-slate-50 text-slate-700';
    return (
        <div
            onClick={onClick}
            role={onClick ? 'button' : undefined}
            tabIndex={onClick ? 0 : undefined}
            onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } } : undefined}
            className={`px-3 py-2 rounded-xl border min-w-[92px] ${cores} ${onClick ? 'cursor-pointer hover:opacity-80 transition-opacity' : ''}`}
        >
            <div className="text-2xl font-black leading-none tabular-nums">{valor}</div>
            <div className="text-[10px] font-bold uppercase tracking-wider mt-1 opacity-80">{label}</div>
        </div>
    );
};

const AcaoLinha: React.FC<{
    acao: ResumoAcao;
    isDark: boolean;
    onOpen?: (id: string) => void;
}> = ({ acao, isDark, onOpen }) => (
    <button
        type="button"
        onClick={() => onOpen?.(acao.id)}
        className={`w-full text-left px-3 py-2.5 rounded-xl border transition-colors ${
            isDark
                ? 'border-[#2a313d] hover:border-[#861fdd]/50 hover:bg-[#0f1520]'
                : 'border-slate-100 hover:border-[#861fdd]/40 hover:bg-slate-50'
        }`}
    >
        <div className="flex items-start gap-2">
            {acao.horario_inicio && (
                <span className={`text-xs font-mono font-bold shrink-0 mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    {acao.horario_inicio}
                </span>
            )}
            <span className="text-sm font-medium leading-snug flex-1 min-w-0">{acao.titulo || '(sem título)'}</span>
            <div className="flex items-center gap-1 shrink-0">
                {(acao.degradation_count ?? 0) >= 3 && (
                    <span className="text-[10px] font-black px-1.5 py-0.5 rounded bg-red-500/15 text-red-500" title={`Adiada ${acao.degradation_count}x`}>
                        {acao.degradation_count}×
                    </span>
                )}
                {acao.herdada && (
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${isDark ? 'bg-amber-500/15 text-amber-300' : 'bg-amber-100 text-amber-700'}`} title="Empurrada para hoje pelo reset da meia-noite">
                        herdada
                    </span>
                )}
            </div>
        </div>
        {acao.proximo_passo && (
            <div className={`text-xs mt-1.5 flex items-start gap-1.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                <span className="shrink-0">↳</span>
                <span className="min-w-0">{acao.proximo_passo}</span>
                {(acao.etapas_totais ?? 0) > 0 && (
                    <span className="shrink-0 tabular-nums opacity-70">({acao.etapas_feitas ?? 0}/{acao.etapas_totais})</span>
                )}
            </div>
        )}
    </button>
);

const MetaLinha: React.FC<{ meta: ResumoMeta; isDark: boolean }> = ({ meta, isDark }) => (
    <div className={`px-3 py-2.5 rounded-xl border ${isDark ? 'border-[#2a313d]' : 'border-slate-100'}`}>
        <div className="flex items-baseline justify-between gap-2">
            <span className="text-sm font-medium leading-snug min-w-0">{meta.objetivo || '(sem título)'}</span>
            {meta.pilar_label && (
                <span className={`text-[10px] font-bold uppercase tracking-wider shrink-0 ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                    {meta.pilar_label}
                </span>
            )}
        </div>
        <div className={`text-xs mt-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
            {(meta.acoes_hoje ?? 0) > 0
                ? `${meta.acoes_hoje} ação(ões) hoje`
                : meta.dias_parada === null || meta.dias_parada === undefined
                ? 'Nenhum movimento registrado'
                : meta.gerida_por_acoes
                ? `Parada há ${meta.dias_parada} dia(s)`
                // Pilar saúde: o movimento vem dos registros do módulo, não de ações —
                // dizer "parada" aqui seria falso num dia em que houve pesagem.
                : meta.dias_parada === 0
                ? 'Registro de hoje já lançado'
                : `Sem registro há ${meta.dias_parada} dia(s)`}
            {meta.progresso_pct !== null && meta.progresso_pct !== undefined && <span className="ml-2 tabular-nums">· {meta.progresso_pct}%</span>}
            {(meta.marcos_total ?? 0) > 0 && <span className="ml-2 tabular-nums">· {(meta.marcos_total ?? 0) - (meta.marcos_abertos ?? 0)}/{meta.marcos_total} marcos</span>}
        </div>
        {meta.progresso_pct !== null && meta.progresso_pct !== undefined && (
            <div className={`h-1 rounded-full mt-2 overflow-hidden ${isDark ? 'bg-[#0f1520]' : 'bg-slate-100'}`}>
                <div className="h-full rounded-full bg-[#861fdd]" style={{ width: `${meta.progresso_pct}%` }} />
            </div>
        )}
    </div>
);

// --------------------------------------------------------------------------- //

export const MorningSummaryView: React.FC<MorningSummaryViewProps> = ({
    isDark = false,
    onOpenTask,
    onNavigate,
    onAskCopiloto,
}) => {
    const [resumo, setResumo] = useState<ResumoMatinal | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isRegenerating, setIsRegenerating] = useState(false);
    const [erro, setErro] = useState<string | null>(null);
    const [diarioAberto, setDiarioAberto] = useState(false);

    const hoje = localTodayStr();
    // Uma tentativa automática por dia: sem isso, um dia em que o resumo
    // legitimamente não existe (agendador falhou, coleção vazia) viraria um loop
    // de chamadas à callable a cada re-render do snapshot.
    const autoGerado = useRef<string | null>(null);

    const gerar = useCallback(async (silencioso = false) => {
        if (!silencioso) setIsRegenerating(true);
        setErro(null);
        try {
            const fn = httpsCallable<{ date?: string }, ResumoMatinal>(functions, 'gerarResumoMatinal');
            const res = await fn({ date: hoje });
            if (res?.data && res.data.versao) {
                setResumo(res.data);
            }
        } catch (e: any) {
            setErro(e?.message || 'Não foi possível gerar o resumo agora.');
        } finally {
            setIsRegenerating(false);
            setIsLoading(false);
        }
    }, [hoje]);

    useEffect(() => {
        const unsub = onSnapshot(
            doc(db, 'resumo_matinal', hoje),
            (snap) => {
                if (snap.exists()) {
                    const data = snap.data();
                    // Valida se o documento está estruturado com versão e dados mínimos
                    if (data && data.versao && data.hoje) {
                        setResumo({ id: snap.id, ...data } as ResumoMatinal);
                        setIsLoading(false);
                        return;
                    }
                }
                setIsLoading(false);
                if (autoGerado.current !== hoje) {
                    autoGerado.current = hoje;
                    void gerar(true);
                }
            },
            (e) => { setErro(e.message); setIsLoading(false); },
        );
        return () => unsub();
    }, [hoje, gerar]);

    // Marca a primeira abertura do dia — insumo para medir, depois, se o resumo
    // está sendo lido antes do dia começar ou só à noite.
    useEffect(() => {
        if (!resumo || !resumo.versao || resumo.visto_em) return;
        void setDoc(doc(db, 'resumo_matinal', hoje), { visto_em: new Date().toISOString() }, { merge: true });
    }, [resumo, hoje]);

    const c = resumo?.contadores;
    const foco = resumo?.foco || [];
    const agenda = resumo?.agenda || [];
    const janelasLivres = resumo?.janelas_livres || [];
    const hojeLanes = resumo?.hoje || { avanco: [], continuo: [], aguardando_terceiro: [], atrasadas: [] };
    const prazosDuros = resumo?.prazos_duros || [];
    const cargaSemana = resumo?.carga_semana || [];
    const filas = resumo?.filas || {};
    const saude = resumo?.saude || { rotinas_hoje: [], pesagem_registrada: false, cintura_registrada: false, checkin_manha: false, checkin_noite: false, peso: null, dor_ontem: null, ultimo_registro: null };
    const estrategia = resumo?.estrategia || { metas: [], paradas: [], servidas_hoje: 0, total_geridas_por_acoes: 0 };
    const ontem = resumo?.ontem || { concluidas: [], diario: null };
    const rotinasHoje = saude.rotinas_hoje || [];
    const metas = estrategia.metas || [];
    const paradas = estrategia.paradas || [];
    const concluidasOntem = ontem.concluidas || [];
    const diarioOntem = ontem.diario;
    const diarioTexto = diarioOntem?.texto || '';

    // `FILA_LABEL` é a allowlist, não só um dicionário de rótulos: uma chave que a
    // tela não conhece não é renderizada. Sem isso, um campo residual no documento
    // (ou uma fila nova sem rótulo) vaza para a UI com o nome cru da chave — foi
    // como `consolidacoes_whatsapp` continuou aparecendo depois de removida.
    const filasComItens = useMemo(
        () => Object.entries(filas)
            .filter(([chave, f]) => chave in FILA_LABEL && (f as ResumoFila)?.total > 0),
        [filas],
    );
    const cargaMax = useMemo(
        () => Math.max(1, ...(cargaSemana).map((d) => d.total || 0)),
        [cargaSemana],
    );

    const irPara = (rota: string) => {
        if (ROTAS_VALIDAS.includes(rota as MorningSummaryRoute)) onNavigate?.(rota as MorningSummaryRoute);
    };

    if (isLoading) {
        return (
            <div className={`p-8 text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Carregando o resumo do dia…</div>
        );
    }

    if (!resumo || !resumo.versao) {
        return (
            <div className="p-8 space-y-3">
                <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    {erro || 'O resumo de hoje ainda não foi gerado.'}
                </p>
                <button
                    type="button"
                    onClick={() => gerar()}
                    disabled={isRegenerating}
                    className="px-4 py-2 rounded-xl bg-[#861fdd] text-white text-sm font-bold disabled:opacity-50"
                >
                    {isRegenerating ? 'Gerando…' : 'Gerar agora'}
                </button>
            </div>
        );
    }

    return (
        <div className="px-4 md:px-8 py-6 max-w-[1400px] mx-auto space-y-4" style={{ fontFamily: 'Inter, sans-serif' }}>

            {/* Cabeçalho ------------------------------------------------------- */}
            <header className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <h1 className={`text-2xl md:text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-[#151c27]'}`}>
                        {saudacao()}, André.
                    </h1>
                    <p className={`text-sm mt-0.5 capitalize ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                        {resumo.dia_semana}, {formatDia(resumo.data)}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {erro && <span className="text-xs text-red-500 max-w-[240px]">{erro}</span>}
                    <button
                        type="button"
                        onClick={() => gerar()}
                        disabled={isRegenerating}
                        className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-colors disabled:opacity-50 ${
                            isDark ? 'border-[#2a313d] text-slate-300 hover:bg-[#151c27]' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                        }`}
                    >
                        {isRegenerating ? 'Atualizando…' : '↻ Atualizar'}
                    </button>
                </div>
            </header>

            {/* Estado do dia --------------------------------------------------- */}
            <div className="flex flex-wrap gap-2">
                <Pill label="hoje" valor={c?.hoje ?? 0} isDark={isDark} onClick={() => irPara('gallery')} />
                {!!c?.herdadas && <Pill label="herdadas" valor={c.herdadas} tom="atencao" isDark={isDark} onClick={() => irPara('gallery')} />}
                {!!c?.criticas && <Pill label="críticas" valor={c.criticas} tom="urgente" isDark={isDark} onClick={() => irPara('gallery')} />}
                {!!c?.cobrar && <Pill label="a cobrar" valor={c.cobrar} tom="atencao" isDark={isDark} onClick={() => irPara('gallery')} />}
                {!!prazosDuros.length && <Pill label="prazos 7d" valor={prazosDuros.length} tom="urgente" isDark={isDark} />}
                {!!c?.pendencias && <Pill label="pendências" valor={c.pendencias} tom="atencao" isDark={isDark} />}
                <Pill label="ativas" valor={c?.ativas ?? 0} isDark={isDark} onClick={() => irPara('gallery')} />
            </div>

            {c?.herdadas ? (
                <p className={`text-xs -mt-1 ${isDark ? 'text-amber-300/80' : 'text-amber-700'}`}>
                    {c.herdadas} de {c.hoje} ação(ões) de hoje não foram escolhidas para hoje — o reset da meia-noite as empurrou.
                </p>
            ) : null}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

                {/* Coluna principal ------------------------------------------- */}
                <div className="lg:col-span-2 space-y-4">

                    <Secao
                        titulo="Foco de hoje"
                        isDark={isDark}
                        acao={
                            <span className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                por regra, não por opinião
                            </span>
                        }
                    >
                        {foco.length === 0 ? (
                            <Vazio isDark={isDark}>Nenhuma ação programada para hoje. Dia livre.</Vazio>
                        ) : (
                            <ol className="space-y-2.5">
                                {foco.map((f, i) => {
                                    const tom = REGRA_TOM[f.regra] || 'neutro';
                                    const borda =
                                        tom === 'urgente' ? 'border-l-red-500'
                                        : tom === 'atencao' ? 'border-l-amber-500'
                                        : 'border-l-[#861fdd]';
                                    return (
                                        <li key={f.task_id}>
                                            <button
                                                type="button"
                                                onClick={() => onOpenTask?.(f.task_id)}
                                                className={`w-full text-left p-3.5 rounded-xl border border-l-4 ${borda} transition-colors ${
                                                    isDark ? 'border-[#2a313d] hover:bg-[#0f1520]' : 'border-slate-100 hover:bg-slate-50'
                                                }`}
                                            >
                                                <div className="flex items-start gap-3">
                                                    <span className={`text-lg font-black tabular-nums leading-none mt-0.5 ${isDark ? 'text-slate-600' : 'text-slate-300'}`}>
                                                        {i + 1}
                                                    </span>
                                                    <div className="min-w-0 flex-1">
                                                        <div className="flex flex-wrap items-baseline gap-2">
                                                            <span className="font-bold text-[15px] leading-snug">{f.titulo}</span>
                                                            <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                                                                tom === 'urgente' ? 'bg-red-500/15 text-red-500'
                                                                : tom === 'atencao' ? 'bg-amber-500/15 text-amber-600'
                                                                : isDark ? 'bg-slate-700/40 text-slate-400' : 'bg-slate-100 text-slate-500'
                                                            }`}>
                                                                {REGRA_LABEL[f.regra] || f.regra}
                                                            </span>
                                                            {f.horario_inicio && (
                                                                <span className={`text-xs font-mono font-bold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                                                    {f.horario_inicio}
                                                                </span>
                                                            )}
                                                        </div>
                                                        <p className={`text-xs mt-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>{f.motivo}</p>
                                                        {f.proximo_passo && (
                                                            <p className={`text-sm mt-2 font-medium ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>
                                                                ↳ {f.proximo_passo}
                                                            </p>
                                                        )}
                                                    </div>
                                                </div>
                                            </button>
                                        </li>
                                    );
                                })}
                            </ol>
                        )}
                    </Secao>

                    {/* Agenda */}
                    <Secao titulo="Agenda de hoje" isDark={isDark}>
                        {agenda.length === 0 ? (
                            <Vazio isDark={isDark}>Nenhum compromisso na agenda.</Vazio>
                        ) : (
                            <ul className="space-y-1.5">
                                {agenda.map((ev, i) => (
                                    <li key={i} className="flex items-baseline gap-3 text-sm">
                                        <span className={`font-mono text-xs font-bold shrink-0 w-[86px] ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                            {ev.dia_inteiro ? 'dia inteiro' : `${ev.inicio}${ev.fim ? `–${ev.fim}` : ''}`}
                                        </span>
                                        <span className="min-w-0">{ev.titulo}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                        {janelasLivres.length > 0 && (
                            <div className={`mt-4 pt-3 border-t ${isDark ? 'border-[#2a313d]' : 'border-slate-100'}`}>
                                <div className={`text-[10px] font-bold uppercase tracking-wider mb-2 ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                    Janelas livres
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {janelasLivres.map((j, i) => (
                                        <span key={i} className={`text-xs font-mono px-2 py-1 rounded-lg border ${
                                            isDark ? 'border-[#2a313d] bg-[#0f1520] text-slate-300' : 'border-slate-200 bg-slate-50 text-slate-600'
                                        }`}>
                                            {j.inicio}–{j.fim} <span className="opacity-60">({formatDuracao(j.minutos)})</span>
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </Secao>

                    {/* Ações do dia por lane */}
                    <Secao
                        titulo="Ações do dia"
                        isDark={isDark}
                        acao={
                            <button type="button" onClick={() => irPara('gallery')} className="text-[10px] font-bold uppercase tracking-wider text-[#861fdd] hover:underline">
                                ver todas
                            </button>
                        }
                    >
                        {((['avanco', 'continuo', 'aguardando_terceiro'] as const).every((l) => (hojeLanes[l] || []).length === 0)) ? (
                            <Vazio isDark={isDark}>Nada programado.</Vazio>
                        ) : (
                            <div className="space-y-4">
                                {(['avanco', 'continuo', 'aguardando_terceiro'] as const).map((lane) => {
                                    const acoesLane = hojeLanes[lane] || [];
                                    return acoesLane.length === 0 ? null : (
                                        <div key={lane}>
                                            <div className={`text-[10px] font-bold uppercase tracking-wider mb-2 ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                                {LANE_LABEL[lane]} · {acoesLane.length}
                                            </div>
                                            <div className="space-y-1.5">
                                                {acoesLane.map((a) => (
                                                    <AcaoLinha key={a.id} acao={a} isDark={isDark} onOpen={onOpenTask} />
                                                ))}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </Secao>

                    {/* Prazos duros */}
                    {prazosDuros.length > 0 && (
                        <Secao
                            titulo="Prazos finais nos próximos 7 dias"
                            isDark={isDark}
                            acao={
                                <span className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                    o reset da meia-noite não move estes
                                </span>
                            }
                        >
                            <ul className="space-y-1.5">
                                {prazosDuros.map((p) => (
                                    <li key={p.id}>
                                        <button
                                            type="button"
                                            onClick={() => onOpenTask?.(p.id)}
                                            className={`w-full text-left flex items-baseline gap-3 px-3 py-2 rounded-xl border transition-colors ${
                                                isDark ? 'border-[#2a313d] hover:bg-[#0f1520]' : 'border-slate-100 hover:bg-slate-50'
                                            }`}
                                        >
                                            <span className={`text-xs font-black tabular-nums shrink-0 w-[68px] ${
                                                p.dias <= 1 ? 'text-red-500' : p.dias <= 3 ? 'text-amber-500' : isDark ? 'text-slate-400' : 'text-slate-500'
                                            }`}>
                                                {p.dias === 0 ? 'hoje' : p.dias === 1 ? 'amanhã' : `${p.dias} dias`}
                                            </span>
                                            <span className="text-sm min-w-0 flex-1">{p.titulo}</span>
                                            <span className={`text-xs font-mono shrink-0 ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                                {formatDiaCurto(p.prazo_final)}
                                            </span>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </Secao>
                    )}
                </div>

                {/* Coluna lateral --------------------------------------------- */}
                <div className="space-y-4">

                    {/* Volume de ações — primeiro da coluna: dá a forma da semana antes do detalhe */}
                    <Secao titulo="Volume de ações nos próximos 7 dias" isDark={isDark}>
                        <div className="flex items-end justify-between gap-1.5 h-24">
                            {cargaSemana.map((d, i) => (
                                <div key={d.data} className="flex-1 flex flex-col items-center gap-1.5 min-w-0">
                                    <span className={`text-[10px] font-bold tabular-nums ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                        {d.total || ''}
                                    </span>
                                    <div
                                        className={`w-full rounded-t transition-all ${i === 0 ? 'bg-[#861fdd]' : isDark ? 'bg-slate-700' : 'bg-slate-200'}`}
                                        style={{ height: `${Math.max(3, ((d.total || 0) / cargaMax) * 58)}px` }}
                                    />
                                    <span className={`text-[9px] font-mono ${isDark ? 'text-slate-600' : 'text-slate-400'}`}>
                                        {formatDiaCurto(d.data)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </Secao>

                    {/* Pendências */}
                    <Secao titulo="Esperando você decidir" isDark={isDark}>
                        {filasComItens.length === 0 ? (
                            <Vazio isDark={isDark}>Nenhuma fila parada. Tudo decidido.</Vazio>
                        ) : (
                            <ul className="space-y-2.5">
                                {filasComItens.map(([chave, fila]) => {
                                    const amostra = fila?.amostra || [];
                                    // Fila sem rota não vira botão. Um card clicável que leva
                                    // para a tela inicial faz o usuário procurar o que não
                                    // existe — era o caso das notificações da IA, que são
                                    // entregues e decididas no Telegram, sem tela nenhuma.
                                    const temDestino = ROTAS_VALIDAS.includes(fila.rota as MorningSummaryRoute);
                                    const Wrapper = temDestino ? 'button' : 'div';
                                    return (
                                        <li key={chave}>
                                            <Wrapper
                                                {...(temDestino
                                                    ? { type: 'button' as const, onClick: () => irPara(fila.rota) }
                                                    : {})}
                                                className={`w-full text-left px-3 py-2.5 rounded-xl border transition-colors ${
                                                    isDark ? 'border-[#2a313d]' : 'border-slate-100'
                                                } ${temDestino ? (isDark ? 'hover:bg-[#0f1520]' : 'hover:bg-slate-50') : ''}`}
                                            >
                                                <div className="flex items-center gap-2">
                                                    <span className="text-base leading-none">{FILA_ICONE[chave] || '•'}</span>
                                                    <span className="text-sm font-medium flex-1 min-w-0">{FILA_LABEL[chave] || chave}</span>
                                                    <span className={`text-sm font-black tabular-nums ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                                                        {fila.total}
                                                    </span>
                                                </div>
                                                {amostra.length > 0 && (
                                                    <ul className={`mt-1.5 space-y-0.5 text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                                        {amostra.map((item, i) => (
                                                            <li key={i} className="truncate">
                                                                · {item.titulo}
                                                                {item.vencida ? ' (vencida)' : item.dias !== undefined && item.dias >= 0 ? ` (${item.dias}d)` : ''}
                                                            </li>
                                                        ))}
                                                    </ul>
                                                )}
                                                {!temDestino && FILA_NOTA[chave] && (
                                                    <p className={`mt-1.5 text-[11px] ${isDark ? 'text-slate-600' : 'text-slate-400'}`}>
                                                        {FILA_NOTA[chave]}
                                                    </p>
                                                )}
                                            </Wrapper>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </Secao>

                    {/* Estratégia */}
                    <Secao
                        titulo="O que isso constrói"
                        isDark={isDark}
                        acao={
                            <button type="button" onClick={() => irPara('strategy')} className="text-[10px] font-bold uppercase tracking-wider text-[#861fdd] hover:underline">
                                estratégia
                            </button>
                        }
                    >
                        {metas.length === 0 ? (
                            <Vazio isDark={isDark}>Nenhuma meta ativa cadastrada.</Vazio>
                        ) : (
                            <div className="space-y-3">
                                <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                    {estrategia.total_geridas_por_acoes === 0
                                        ? 'Nenhuma meta é executada por ações.'
                                        : estrategia.servidas_hoje === 0
                                        ? 'Nenhuma ação de hoje está vinculada a uma meta.'
                                        : `${estrategia.servidas_hoje} de ${estrategia.total_geridas_por_acoes} metas recebem trabalho hoje.`}
                                </p>
                                <div className="space-y-1.5">
                                    {metas.filter((m) => (m.acoes_hoje || 0) > 0).map((m) => (
                                        <MetaLinha key={m.id} meta={m} isDark={isDark} />
                                    ))}
                                </div>
                                {paradas.length > 0 && (
                                    <div className={`pt-3 border-t ${isDark ? 'border-[#2a313d]' : 'border-slate-100'}`}>
                                        <div className={`text-[10px] font-bold uppercase tracking-wider mb-2 ${isDark ? 'text-amber-300/70' : 'text-amber-700'}`}>
                                            Sem movimento
                                        </div>
                                        <div className="space-y-1.5">
                                            {paradas.map((m) => (
                                                <MetaLinha key={m.id} meta={m} isDark={isDark} />
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </Secao>

                    {/* Saúde */}
                    <Secao
                        titulo="Corpo"
                        isDark={isDark}
                        acao={
                            <button type="button" onClick={() => irPara('saude')} className="text-[10px] font-bold uppercase tracking-wider text-[#861fdd] hover:underline">
                                saúde
                            </button>
                        }
                    >
                        <div className="space-y-3 text-sm">
                            {saude.peso && (
                                <div className="flex items-baseline gap-2">
                                    <span className="text-2xl font-black tabular-nums">{saude.peso.ultimo}</span>
                                    <span className={isDark ? 'text-slate-400' : 'text-slate-500'}>kg</span>
                                    {saude.peso.media7 !== null && saude.peso.media7 !== undefined && (
                                        <span className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                            média 7d {saude.peso.media7}
                                        </span>
                                    )}
                                    {saude.peso.falta !== null && saude.peso.falta !== undefined && (
                                        <span className={`text-xs ml-auto ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                            faltam {saude.peso.falta.toFixed(1)} kg
                                        </span>
                                    )}
                                </div>
                            )}
                            {saude.dor_ontem && (
                                <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                    Dor ontem:{' '}
                                    {[
                                        saude.dor_ontem.manha !== undefined && saude.dor_ontem.manha !== null ? `manhã ${saude.dor_ontem.manha}` : null,
                                        saude.dor_ontem.noite !== undefined && saude.dor_ontem.noite !== null ? `noite ${saude.dor_ontem.noite}` : null,
                                    ].filter(Boolean).join(' · ') || 'sem registro'}
                                    {saude.dor_ontem.crise && <span className="text-red-500 font-bold"> · crise</span>}
                                    {saude.dor_ontem.ciatica && <span className="text-amber-500"> · ciática</span>}
                                </p>
                            )}
                            {rotinasHoje.length > 0 && (
                                <div className={`pt-2 border-t ${isDark ? 'border-[#2a313d]' : 'border-slate-100'}`}>
                                    <div className={`text-[10px] font-bold uppercase tracking-wider mb-1.5 ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                        Rotina de hoje
                                    </div>
                                    <ul className="space-y-1">
                                        {rotinasHoje.map((r, i) => (
                                            <li
                                                key={i}
                                                className={`text-xs flex items-baseline gap-2 ${
                                                    r.feito
                                                        ? isDark ? 'text-slate-500' : 'text-slate-400'
                                                        : isDark ? 'text-slate-400' : 'text-slate-500'
                                                }`}
                                            >
                                                {/* `feito === null` = aviso ilustrativo (almoço com calma, janela
                                                    alimentar): não é checklist, não ganha marcador. */}
                                                <span className="shrink-0 w-[14px] text-center">
                                                    {r.feito === null ? '' : r.feito ? '✓' : '○'}
                                                </span>
                                                <span className="font-mono font-bold shrink-0 w-[38px]">{r.hora}</span>
                                                <span className={`min-w-0 ${r.feito ? 'line-through opacity-70' : ''}`}>{r.titulo}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    </Secao>

                    {/* Ontem */}
                    <Secao
                        titulo="Ontem"
                        isDark={isDark}
                        acao={
                            <button type="button" onClick={() => irPara('diario')} className="text-[10px] font-bold uppercase tracking-wider text-[#861fdd] hover:underline">
                                diário
                            </button>
                        }
                    >
                        <div className="space-y-3">
                            <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                {concluidasOntem.length === 0
                                    ? 'Nenhuma ação concluída ontem.'
                                    : `${concluidasOntem.length} ação(ões) concluída(s).`}
                            </p>
                            {concluidasOntem.length > 0 && (
                                <ul className={`space-y-0.5 text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                    {concluidasOntem.slice(0, 5).map((t, i) => (
                                        <li key={i} className="truncate">✓ {t}</li>
                                    ))}
                                    {concluidasOntem.length > 5 && (
                                        <li className="opacity-70">+{concluidasOntem.length - 5} outras</li>
                                    )}
                                </ul>
                            )}
                            {diarioTexto ? (
                                <div className={`pt-3 border-t ${isDark ? 'border-[#2a313d]' : 'border-slate-100'}`}>
                                    <p className={`text-sm leading-relaxed whitespace-pre-wrap ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
                                        {diarioAberto
                                            ? diarioTexto
                                            : `${diarioTexto.slice(0, 260)}${diarioTexto.length > 260 ? '…' : ''}`}
                                    </p>
                                    {diarioTexto.length > 260 && (
                                        <button
                                            type="button"
                                            onClick={() => setDiarioAberto((v) => !v)}
                                            className="mt-2 text-[10px] font-bold uppercase tracking-wider text-[#861fdd] hover:underline"
                                        >
                                            {diarioAberto ? 'recolher' : 'ler tudo'}
                                        </button>
                                    )}
                                </div>
                            ) : null}
                        </div>
                    </Secao>

                    {onAskCopiloto && (
                        <button
                            type="button"
                            onClick={() =>
                                onAskCopiloto(
                                    `Este é o meu resumo de ${resumo.data}. Foco escolhido pelo sistema: ` +
                                    `${foco.map((f) => `${f.titulo} (${f.motivo})`).join('; ') || 'nenhum'}. ` +
                                    `${c?.herdadas ?? 0} ação(ões) herdadas do reset da meia-noite, ` +
                                    `${c?.criticas ?? 0} em degradação crítica, ` +
                                    `${c?.pendencias ?? 0} pendência(s) em fila. ` +
                                    `Me ajude a decidir por onde começar.`,
                                )
                            }
                            className={`w-full px-4 py-3 rounded-2xl text-sm font-bold border transition-colors ${
                                isDark ? 'border-[#2a313d] text-slate-300 hover:bg-[#151c27]' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                            }`}
                        >
                            Discutir o dia com o Copiloto
                        </button>
                    )}
                </div>
            </div>

            {resumo.gerado_em && (
                <p className={`text-[10px] text-center pt-2 ${isDark ? 'text-slate-600' : 'text-slate-400'}`}>
                    Gerado em {new Date(resumo.gerado_em).toLocaleString('pt-BR')} · sem IA, tudo calculado no backend
                </p>
            )}
        </div>
    );
};

export default MorningSummaryView;
