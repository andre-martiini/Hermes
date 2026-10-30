import { centavos, numero } from './bolsoAquisicoes';

/**
 * Perfil das metas: o esperado de hoje e o estado de cada indicador.
 *
 * **Anda junto com `functions/perfil_estrategia.py`**: a mesma regra vale na tela e no
 * MCP, e os testes dos dois lados leem o MESMO arquivo (`perfilEstrategia.fixture.json`).
 * O porquê de cada escolha (inteiros, arredondamento, por que não `healthAnalytics.ts`)
 * está no docstring do módulo Python.
 */

export type Sentido = 'menor_melhor' | 'maior_melhor';
export type FonteIndicador = 'peso' | 'cintura' | 'guardado_acumulado' | 'manual';
export type EstadoPerfil = 'adiantado' | 'no_perfil' | 'sem_dado' | 'atrasado';

export const SENTIDOS: Sentido[] = ['menor_melhor', 'maior_melhor'];
export const FONTES: FonteIndicador[] = ['peso', 'cintura', 'guardado_acumulado', 'manual'];
const UNIDADES_DINHEIRO = ['r$', 'brl', 'reais'];
export const GRAVIDADE: Record<EstadoPerfil, number> = { adiantado: 0, no_perfil: 1, sem_dado: 2, atrasado: 3 };

export interface IndicadorPerfil {
    chave: string;
    rotulo?: string;
    unidade?: string;
    sentido?: Sentido;
    fonte?: FonteIndicador;
    inicial?: number;
    alvoFinal?: number;
}

interface MarcoPerfil {
    id?: string;
    descricao?: string;
    concluido?: boolean;
    dataAlvo?: string;
    esperado?: Record<string, number>;
}

export interface MetaPerfil {
    ciclo?: { inicio?: string; fim?: string };
    linhaBase?: { data?: string; valores?: Record<string, number> };
    indicadores?: IndicadorPerfil[];
    marcos?: Array<string | MarcoPerfil>;
}

export interface IndicadorAvaliado {
    chave: string;
    rotulo: string;
    unidade: string;
    fonte: FonteIndicador;
    sentido: Sentido;
    /** Dinheiro: `atual`, `esperado_hoje` e o valor do próximo marco vêm em centavos inteiros. */
    em_centavos: boolean;
    atual: number | null;
    esperado_hoje: number | null;
    proximo_marco: { data: string; valor: number } | null;
    estado: EstadoPerfil | null;
}

export interface PerfilDaMeta {
    estado: EstadoPerfil | null;
    indicadores: IndicadorAvaliado[];
    marcos_sem_numero: Array<{ id?: string; descricao: string; dataAlvo: string | null; concluido: boolean; estado: EstadoPerfil }>;
    proximo_marco: { data: string; descricao: string } | null;
}

/** Dias desde 1970-01-01, ou null para data inválida. YYYY-MM-DD lido pelo texto (hora depois é ignorada). */
export const dia = (valor: unknown): number | null => {
    const achado = String(valor ?? '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!achado) return null;
    const [ano, mes, d] = [Number(achado[1]), Number(achado[2]), Number(achado[3])];
    const t = Date.UTC(ano, mes - 1, d);
    const data = new Date(t);
    if (data.getUTCFullYear() !== ano || data.getUTCMonth() !== mes - 1 || data.getUTCDate() !== d) return null;
    return t / 86_400_000;
};

const isoDoDia = (dias: number) => new Date(dias * 86_400_000).toISOString().slice(0, 10);

/** A data de hoje em Brasília. Às 22h de Brasília já é o dia seguinte em UTC. */
export const hojeBrasilia = (agora: Date = new Date()): string =>
    new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit' })
        .format(agora);

/** Id estável para marco ou indicador legado em texto puro (FNV-1a 32 bits de posição e texto). */
export const idLegado = (tipo: string, indice: number, descricao: string): string => {
    let h = 0x811c9dc5;
    for (const byte of new TextEncoder().encode(`${indice}|${descricao}`)) {
        h ^= byte;
        h = Math.imul(h, 0x01000193) >>> 0;
    }
    return `${tipo}-legado-${h.toString(16).padStart(8, '0')}`;
};

/** n / d arredondado meio-para-longe-do-zero, em inteiros (d > 0). */
const divArred = (n: number, d: number): number => {
    const sinal = n < 0 ? -1 : 1;
    return sinal * Math.floor((Math.abs(n) * 2 + d) / (2 * d));
};

const MAX_CENTESIMOS = 9007199254740991; // o mesmo teto de `centavos`

/** Valor em centésimos; ilegível ou fora do teto é null (sem dado), nunca zero (`centavos` devolve 0 acima do teto). */
const centesimos = (valor: unknown): number | null => {
    if (valor === null || valor === undefined || typeof valor === 'boolean') return null;
    const n = numero(valor, Number.NaN);
    return Number.isNaN(n) || Math.abs(n) * 100 > MAX_CENTESIMOS ? null : centavos(valor);
};

const diaDeHoje = (hoje: string): number => {
    const d = dia(hoje);
    if (d === null) throw new Error(`hoje deve ser YYYY-MM-DD, veio ${JSON.stringify(hoje)}.`);
    return d;
};

const eMapa = (valor: unknown): valor is Record<string, unknown> =>
    typeof valor === 'object' && valor !== null && !Array.isArray(valor);

/** Marco com valor esperado para algum indicador da meta; o resto é qualitativo. */
const numerico = (marco: MarcoPerfil, chaves: Set<string>) =>
    eMapa(marco.esperado) && Object.keys(marco.esperado).some(k => chaves.has(k));

export const eDinheiro = (indicador: IndicadorPerfil): boolean =>
    UNIDADES_DINHEIRO.includes(String(indicador.unidade ?? '').trim().toLowerCase())
    || indicador.fonte === 'guardado_acumulado';

const saida = (valor: number | null, dinheiro: boolean): number | null =>
    valor === null ? null : dinheiro ? valor : valor / 100;

const marcosDatados = (meta: MetaPerfil): MarcoPerfil[] =>
    (meta.marcos ?? [])
        .filter((m): m is MarcoPerfil => typeof m === 'object' && m !== null && dia(m.dataAlvo) !== null)
        .sort((a, b) => (dia(a.dataAlvo) as number) - (dia(b.dataAlvo) as number));

const valorDoMarco = (marco: MarcoPerfil, chave: string): number | null =>
    eMapa(marco.esperado) ? centesimos(marco.esperado[chave]) : null;

/** Trajetória do indicador: linha de base, marcos com valor e, se faltar, o alvo final no fim do ciclo. */
export const pontos = (meta: MetaPerfil, indicador: IndicadorPerfil): Array<[number, number]> => {
    const porDia = new Map<number, number>();
    const diaBase = dia(meta.linhaBase?.data) ?? dia(meta.ciclo?.inicio);
    const valorBase = centesimos(meta.linhaBase?.valores?.[indicador.chave]) ?? centesimos(indicador.inicial);
    if (diaBase !== null && valorBase !== null) porDia.set(diaBase, valorBase);

    for (const marco of marcosDatados(meta)) {
        const valor = valorDoMarco(marco, indicador.chave);
        if (valor !== null) porDia.set(dia(marco.dataAlvo) as number, valor); // marco na mesma data vence a linha de base
    }

    const fim = dia(meta.ciclo?.fim);
    const alvo = centesimos(indicador.alvoFinal);
    if (fim !== null && alvo !== null && (porDia.size === 0 || fim > Math.max(...porDia.keys()))) porDia.set(fim, alvo);
    return [...porDia.entries()].sort((a, b) => a[0] - b[0]);
};

/** Esperado (em centésimos) numa data: interpolação linear entre os pontos; fora deles, o primeiro ou o último. */
export const esperadoEm = (meta: MetaPerfil, indicador: IndicadorPerfil, quando: string): number | null => {
    const trajetoria = pontos(meta, indicador);
    const alvo = dia(quando);
    if (trajetoria.length === 0 || alvo === null) return null;
    if (alvo <= trajetoria[0][0]) return trajetoria[0][1];
    for (let i = 1; i < trajetoria.length; i++) {
        const [d0, v0] = trajetoria[i - 1];
        const [d1, v1] = trajetoria[i];
        if (alvo <= d1) return v0 + divArred((v1 - v0) * (alvo - d0), d1 - d0);
    }
    return trajetoria[trajetoria.length - 1][1];
};

const melhorOuIgual = (atual: number, referencia: number, sentido: Sentido) =>
    sentido === 'maior_melhor' ? atual >= referencia : atual <= referencia;

export const avaliarIndicador = (meta: MetaPerfil, indicador: IndicadorPerfil, atual: unknown, hoje: string): IndicadorAvaliado => {
    const sentido: Sentido = SENTIDOS.includes(indicador.sentido as Sentido) ? (indicador.sentido as Sentido) : 'menor_melhor';
    const dinheiro = eDinheiro(indicador);
    const atualC = centesimos(atual);
    const hojeDia = diaDeHoje(hoje);
    const esperado = esperadoEm(meta, indicador, hoje);
    const marcoProximo = marcosDatados(meta)
        .find(m => (dia(m.dataAlvo) as number) > hojeDia && valorDoMarco(m, indicador.chave) !== null);
    const valorProximo = marcoProximo ? valorDoMarco(marcoProximo, indicador.chave) : null;

    let estado: EstadoPerfil | null;
    if (atualC === null) estado = 'sem_dado'; // ninguém mede: nunca devolver zero no lugar
    else if (esperado === null) estado = null; // sem trajetória, não há perfil para comparar
    else if (valorProximo !== null && melhorOuIgual(atualC, valorProximo, sentido)) estado = 'adiantado';
    else if (melhorOuIgual(atualC, esperado, sentido)) estado = 'no_perfil';
    else estado = 'atrasado';

    return {
        chave: indicador.chave,
        rotulo: indicador.rotulo || indicador.chave,
        unidade: indicador.unidade || '',
        fonte: FONTES.includes(indicador.fonte as FonteIndicador) ? (indicador.fonte as FonteIndicador) : 'manual',
        sentido,
        em_centavos: dinheiro,
        atual: saida(atualC, dinheiro),
        esperado_hoje: saida(esperado, dinheiro),
        proximo_marco: marcoProximo && valorProximo !== null
            ? { data: isoDoDia(dia(marcoProximo.dataAlvo) as number), valor: saida(valorProximo, dinheiro) as number }
            : null,
        estado,
    };
};

export const avaliarMeta = (meta: MetaPerfil, atuais: Record<string, unknown>, hoje: string): PerfilDaMeta => {
    const hojeDia = diaDeHoje(hoje);
    const validos = (meta.indicadores ?? []).filter(ind => ind && typeof ind === 'object' && ind.chave);
    const chaves = new Set(validos.map(ind => ind.chave));
    const indicadores = validos.map(ind => avaliarIndicador(meta, ind, atuais[ind.chave], hoje));
    const semNumero = marcosDatados(meta)
        .filter(m => !numerico(m, chaves))
        .map(m => {
            const alvo = dia(m.dataAlvo) as number;
            return {
                id: m.id,
                descricao: m.descricao || '',
                dataAlvo: isoDoDia(alvo),
                concluido: !!m.concluido,
                estado: (alvo < hojeDia && !m.concluido ? 'atrasado' : 'no_perfil') as EstadoPerfil,
            };
        });
    const estados = [...indicadores.map(i => i.estado), ...semNumero.map(m => m.estado)]
        .filter((e): e is EstadoPerfil => e !== null);
    const proximo = marcosDatados(meta).find(m => (dia(m.dataAlvo) as number) >= hojeDia && !m.concluido);
    return {
        estado: estados.length ? estados.reduce((pior, e) => (GRAVIDADE[e] > GRAVIDADE[pior] ? e : pior)) : null,
        indicadores,
        marcos_sem_numero: semNumero,
        proximo_marco: proximo ? { data: isoDoDia(dia(proximo.dataAlvo) as number), descricao: proximo.descricao || '' } : null,
    };
};
