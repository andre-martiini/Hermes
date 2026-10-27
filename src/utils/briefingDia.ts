/**
 * Regras de leitura do `briefing_dia` no Painel do dia.
 *
 * O briefing é uma foto das 05:00 escrita pela IA. Quem manda no que está de
 * pé é a origem viva: ação concluída, etapa feita, item da fila resolvido. Por
 * isso nada aqui confia no `status` do documento sozinho — cada item é
 * conferido contra o que o resto do sistema sabe agora, e o que já não pede
 * nada some. Nenhum número que dá para calcular é lido do documento.
 */
import type {
    ActionPlanItem, BriefingDecidirItem, BriefingDia, BriefingEuFaco,
} from '../../types';
import { estaFeita } from './subtarefas';

/** O que a tela sabe agora sobre as origens. `undefined` = ainda não chegou. */
export interface OrigemViva {
    /** Ações por id (a lista viva `tarefas`). */
    tarefas: Record<string, { status?: string; titulo?: string; plano_acao?: ActionPlanItem[] }>;
    /** Só confie na ausência de uma ação depois que a lista chegou. */
    tarefasCarregadas: boolean;
    /** `atencao/{id}.estado` por id do item. `undefined`: não lido; `null`: documento ausente. */
    atencao: Record<string, { estado?: string } | null | undefined>;
}

const semAcento = (s: unknown) =>
    String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

export const acaoEncerrada = (status: unknown): boolean => {
    const s = semAcento(status);
    return s === 'concluido' || s === 'excluido';
};

const ESTADOS_FECHADOS_ATENCAO = ['resolvido', 'descartado'];

/**
 * A origem do item já não pede nada?
 *
 * `whatsapp` não é conferido ao vivo (a pendência de resposta é derivada no
 * servidor, não é um documento por conversa): esse item sai pelo Feito ou por
 * `resolver_item_briefing`.
 */
export const origemResolvida = (item: BriefingDecidirItem, vivo: OrigemViva): boolean => {
    if (item.origem === 'acao' || item.origem === 'etapa') {
        const acaoId = item.origem === 'acao' ? (item.acao_id || item.ref) : item.acao_id;
        if (!acaoId) return false;
        const acao = vivo.tarefas[acaoId];
        if (!acao) return vivo.tarefasCarregadas; // apagada
        if (acaoEncerrada(acao.status)) return true;
        if (item.origem === 'etapa') {
            const etapa = (acao.plano_acao || []).find(e => e.id === item.ref);
            return !etapa || estaFeita(etapa);
        }
        return false;
    }
    if (item.origem === 'fila_atencao') {
        const doc = vivo.atencao[item.ref];
        return !!doc && ESTADOS_FECHADOS_ATENCAO.includes(String(doc.estado || ''));
    }
    return false;
};

export interface LinhaDecidir {
    item: BriefingDecidirItem;
    /** Posição no briefing (1 = primeiro), a mesma depois de reordenar para baixo os feitos. */
    numero: number;
    feito: boolean;
}

export interface DecidirPronto {
    /** Pendentes na ordem do briefing, depois os feitos. */
    linhas: LinhaDecidir[];
    pendentes: number;
}

/**
 * Os itens de Decidir que a tela mostra.
 *
 * - `dispensado` e origem resolvida: somem (e não contam como pendência);
 * - `feito`: desce e fica riscado, com Desfazer;
 * - o número é o da posição no briefing, para não renumerar quando um item é feito.
 */
export const prepararDecidir = (briefing: BriefingDia | null | undefined, vivo: OrigemViva): DecidirPronto => {
    const itens = [...(briefing?.decidir || [])]
        .map((item, i) => ({ item, i }))
        .sort((x, y) => (x.item.ordem ?? x.i + 1) - (y.item.ordem ?? y.i + 1) || x.i - y.i);
    const linhas: LinhaDecidir[] = [];
    itens.forEach(({ item }, n) => {
        const status = item.status || 'pendente';
        if (status === 'dispensado') return;
        if (origemResolvida(item, vivo)) return;
        linhas.push({ item, numero: n + 1, feito: status === 'feito' });
    });
    const pendentesLista = linhas.filter(l => !l.feito);
    return { linhas: [...pendentesLista, ...linhas.filter(l => l.feito)], pendentes: pendentesLista.length };
};

export const resumoDecidir = (pendentes: number): string =>
    pendentes === 0 ? 'tudo decidido' : `${pendentes} ${pendentes === 1 ? 'pendência' : 'pendências'}`;

/** Foco por ação: `acao_id` → motivo (vazio se o agente não deu motivo). */
export const focoPorAcao = (briefing: BriefingDia | null | undefined): Map<string, string> => {
    const mapa = new Map<string, string>();
    (briefing?.hoje || []).forEach(h => {
        if (h?.acao_id) mapa.set(h.acao_id, h.motivo || '');
    });
    return mapa;
};

export interface LinhaAgentePrepara {
    acaoId: string;
    acao: string;
    texto: string;
}

/**
 * "O agente prepara hoje": o que está proposto ou aprovado e ainda faz sentido.
 * Pronto e recusado saem; ação encerrada ou apagada também.
 */
export const agentePreparaHoje = (briefing: BriefingDia | null | undefined, vivo: OrigemViva): LinhaAgentePrepara[] =>
    (briefing?.eu_faco || [])
        .filter((e: BriefingEuFaco) => ['proposto', 'aprovado', undefined].includes(e.status))
        .flatMap(e => {
            const acao = vivo.tarefas[e.acao_id];
            if (!acao ? vivo.tarefasCarregadas : acaoEncerrada(acao.status)) return [];
            return [{ acaoId: e.acao_id, acao: acao?.titulo || 'Ação', texto: e.texto }];
        });

const ABREV_DIA = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];

export interface ItemPreparo {
    dia: string;
    /** "Qua". */
    rotulo: string;
    /** "28/10", para o tooltip. */
    data: string;
    texto: string;
}

const dataLocal = (iso: string) => {
    const [a, m, d] = iso.split('-').map(Number);
    return new Date(a, m - 1, d);
};

/** Dias entre duas datas YYYY-MM-DD (calendário local, sem horário de verão no meio). */
export const diasEntre = (de: string, ate: string): number =>
    Math.round((dataLocal(ate).getTime() - dataLocal(de).getTime()) / 86_400_000);

/** "hoje", "amanhã", "em 4 dias", "venceu há 2 dias": sempre calculado, nunca gravado. */
export const descreverDias = (dias: number): string => {
    if (dias === 0) return 'hoje';
    if (dias === 1) return 'amanhã';
    if (dias === -1) return 'venceu ontem';
    if (dias < 0) return `venceu há ${-dias} dias`;
    return `em ${dias} dias`;
};

/**
 * Faixa Preparo: até `limite` itens dos próximos dias (depois de hoje).
 * O que já é de hoje ou passou deixa de ser "preparo".
 */
export const preparoDosProximosDias = (
    briefing: BriefingDia | null | undefined,
    hoje: string,
    limite = 3,
): ItemPreparo[] =>
    (briefing?.preparo || [])
        .filter(p => /^\d{4}-\d{2}-\d{2}$/.test(String(p?.dia)) && p.dia > hoje)
        .sort((a, b) => a.dia.localeCompare(b.dia))
        .slice(0, limite)
        .map(p => ({
            dia: p.dia,
            rotulo: ABREV_DIA[dataLocal(p.dia).getDay()],
            data: `${p.dia.slice(8, 10)}/${p.dia.slice(5, 7)}`,
            texto: p.texto,
        }));

/**
 * O `decidir` depois de o André marcar Feito (ou Desfazer) num item.
 *
 * Só `status` e `resolvido_em` mudam, e só desse item: o resto do array fica
 * como estava, que é o que as regras do Firestore permitem à tela. `resolvido_em`
 * é texto ISO (o Firestore não aceita o sentinela de servidor dentro de array).
 */
export const alternarItemDecidir = (
    decidir: BriefingDecidirItem[],
    itemId: string,
    agoraIso: string,
): BriefingDecidirItem[] =>
    decidir.map(item => {
        if (item.id !== itemId) return item;
        const feito = (item.status || 'pendente') === 'feito';
        return feito
            ? { ...item, status: 'pendente', resolvido_em: null }
            : { ...item, status: 'feito', resolvido_em: agoraIso };
    });
