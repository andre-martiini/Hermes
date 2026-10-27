/**
 * Agenda do dia: proximidade do próximo compromisso e conflito de horários.
 *
 * Tudo aqui é calculado na leitura, com o relógio que o chamador passar —
 * nenhum nível e nenhum conflito é gravado. O relógio entra como parâmetro
 * (`agoraMin`) em vez de `new Date()` dentro das funções, para os limites de 30
 * e 15 minutos poderem ser testados nos minutos exatos.
 */

/** Até quantos minutos faltam para o compromisso entrar em "atenção" (âmbar, brilho lento). */
export const LIMITE_ATENCAO_MIN = 30;
/** Até quantos minutos faltam para o compromisso ficar "urgente" (roxo forte, pulso rápido). */
export const LIMITE_URGENTE_MIN = 15;
/** De quanto em quanto tempo a tela relê o relógio. */
export const INTERVALO_RELOGIO_MS = 30_000;
/**
 * Duração assumida de compromisso sem hora de fim. Mesma convenção do resumo
 * matinal (`_calcular_janelas_livres`): melhor superestimar a ocupação.
 */
export const DURACAO_PADRAO_MIN = 60;

export type NivelProximidade = 'normal' | 'atencao' | 'urgente' | 'agora';

export interface EventoDoDia {
    id: string;
    titulo: string;
    /** Minutos desde 00:00. */
    inicio: number;
    /** Minutos desde 00:00. Sem fim declarado, `inicio + DURACAO_PADRAO_MIN`. */
    fim: number;
    fimDeclarado: boolean;
    /** Compromisso que o agente achou fora da agenda (tracejado na linha do tempo). */
    foraDaAgenda: boolean;
}

export interface EventoDaAgenda {
    titulo: string;
    inicio: string | null;
    fim: string | null;
    dia_inteiro?: boolean;
}

export interface EventoForaDaAgenda {
    titulo: string;
    inicio: string;
    fim?: string | null;
}

export const hhmmParaMin = (valor: string | null | undefined): number | null => {
    const m = /^(\d{1,2}):(\d{2})/.exec(String(valor || '').trim());
    if (!m) return null;
    const h = Number(m[1]);
    const min = Number(m[2]);
    if (h > 23 || min > 59) return null;
    return h * 60 + min;
};

export const minParaHhmm = (min: number): string =>
    `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;

/** "13h50", "9h" — o jeito que o André lê horário. */
export const rotuloHora = (min: number): string => {
    const h = Math.floor(min / 60);
    const m = min % 60;
    return m ? `${h}h${String(m).padStart(2, '0')}` : `${h}h`;
};

/** Minutos desde 00:00 no relógio local. Segundos ignorados, como na tela. */
export const minutosDoRelogio = (agora: Date): number => agora.getHours() * 60 + agora.getMinutes();

const chave = (texto: string) =>
    texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();

/**
 * Os compromissos do dia em minutos, ordenados por início.
 *
 * Dia inteiro fica de fora (é marcador, não bloqueia horário). O compromisso de
 * `fora_da_agenda` que já aparece na agenda (mesmo início e mesmo título) é
 * descartado: o agente o viu antes de alguém pô-lo na agenda, e contá-lo duas
 * vezes criaria um conflito do compromisso com ele mesmo.
 */
export const eventosDoDia = (
    agenda: EventoDaAgenda[] | null | undefined,
    foraDaAgenda: EventoForaDaAgenda[] | null | undefined,
): EventoDoDia[] => {
    const saida: EventoDoDia[] = [];
    (agenda || []).forEach((e, i) => {
        if (e.dia_inteiro) return;
        const inicio = hhmmParaMin(e.inicio);
        if (inicio === null) return;
        const fimBruto = hhmmParaMin(e.fim);
        const fimDeclarado = fimBruto !== null && fimBruto > inicio;
        saida.push({
            id: `agenda-${i}`,
            titulo: e.titulo || '(sem título)',
            inicio,
            fim: fimDeclarado ? (fimBruto as number) : inicio + DURACAO_PADRAO_MIN,
            fimDeclarado,
            foraDaAgenda: false,
        });
    });
    (foraDaAgenda || []).forEach((e, i) => {
        const inicio = hhmmParaMin(e.inicio);
        if (inicio === null) return;
        if (saida.some(s => !s.foraDaAgenda && s.inicio === inicio && chave(s.titulo) === chave(e.titulo))) return;
        const fimBruto = hhmmParaMin(e.fim);
        const fimDeclarado = fimBruto !== null && fimBruto > inicio;
        saida.push({
            id: `fora-${i}`,
            titulo: e.titulo,
            inicio,
            fim: fimDeclarado ? (fimBruto as number) : inicio + DURACAO_PADRAO_MIN,
            fimDeclarado,
            foraDaAgenda: true,
        });
    });
    return saida.sort((a, b) => a.inicio - b.inicio || a.fim - b.fim);
};

export interface DestaqueDaAgenda {
    alvo: EventoDoDia | null;
    nivel: NivelProximidade;
    /** Minutos até o início (próximos) ou até o fim (`agora`). `null` sem alvo. */
    minutos: number | null;
}

/**
 * Qual compromisso a caixa "Próximo" mostra, e em que nível.
 *
 * Quem está para começar manda sobre quem está acontecendo: se falta meia hora
 * para o próximo, a caixa avisa dele mesmo com outro compromisso em andamento
 * (é o que faz o conflito aparecer a tempo). Os limites são inclusivos:
 * exatamente 30 min já é atenção, exatamente 15 já é urgente.
 */
export const calcularDestaque = (eventos: EventoDoDia[], agoraMin: number): DestaqueDaAgenda => {
    const ordenados = [...eventos].sort((a, b) => a.inicio - b.inicio);
    const proximo = ordenados.find(e => e.inicio > agoraMin);
    const ativo = ordenados.find(e => e.inicio <= agoraMin && agoraMin < e.fim);
    const falta = proximo ? proximo.inicio - agoraMin : null;

    if (proximo && falta !== null && falta <= LIMITE_URGENTE_MIN) {
        return { alvo: proximo, nivel: 'urgente', minutos: falta };
    }
    if (proximo && falta !== null && falta <= LIMITE_ATENCAO_MIN) {
        return { alvo: proximo, nivel: 'atencao', minutos: falta };
    }
    if (ativo) return { alvo: ativo, nivel: 'agora', minutos: ativo.fim - agoraMin };
    if (proximo && falta !== null) return { alvo: proximo, nivel: 'normal', minutos: falta };
    return { alvo: null, nivel: 'normal', minutos: null };
};

/** "em 25 min", "em 1h30", "agora". */
export const descreverTempo = (min: number): string => {
    if (min <= 1) return 'agora';
    if (min < 60) return `em ${min} min`;
    const h = Math.floor(min / 60);
    const m = min % 60;
    return `em ${h}h${m ? String(m).padStart(2, '0') : ''}`;
};

export interface ParConflito {
    a: EventoDoDia;
    b: EventoDoDia;
}

export interface ConflitosDoDia {
    pares: ParConflito[];
    /** Ids dos compromissos que batem com algum outro. */
    ids: Set<string>;
}

/**
 * Pares de compromissos cujos intervalos se sobrepõem.
 *
 * Sobreposição estrita: um que termina às 10h e outro que começa às 10h não
 * conflitam. Calculado a cada leitura — um conflito gravado ficaria errado
 * assim que alguém mexesse num dos horários.
 */
export const detectarConflitos = (eventos: EventoDoDia[]): ConflitosDoDia => {
    const ordenados = [...eventos].sort((x, y) => x.inicio - y.inicio || x.fim - y.fim);
    const pares: ParConflito[] = [];
    const ids = new Set<string>();
    for (let i = 0; i < ordenados.length; i++) {
        for (let j = i + 1; j < ordenados.length; j++) {
            const a = ordenados[i];
            const b = ordenados[j];
            if (b.inicio >= a.fim) continue;
            pares.push({ a, b });
            ids.add(a.id);
            ids.add(b.id);
        }
    }
    return { pares, ids };
};

/** "Conselho de Escola 13h50 bate com Acupuntura 13h30. A reunião não está na agenda." */
export const textoDoConflito = ({ a, b }: ParConflito): string => {
    const base = `${b.titulo} ${rotuloHora(b.inicio)} bate com ${a.titulo} ${rotuloHora(a.inicio)}.`;
    return a.foraDaAgenda || b.foraDaAgenda ? `${base} Um deles não está na agenda.` : base;
};
