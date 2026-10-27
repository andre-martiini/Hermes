/**
 * Quais ações o dia tem, e quais delas estão em espera.
 *
 * O resumo matinal define o CONJUNTO de ações de hoje; a tarefa viva é a fonte
 * de tudo o mais (título, plano, etapas, status). A regra de espera é uma só em
 * todo lugar: a etapa corrente da ação (`subtarefaCorrente`, a mesma que o
 * backend usa) está `aguardando_terceiro`. Ação em espera sai da lista
 * principal e do cálculo do dia, mas continua ativa.
 */
import type { ActionPlanItem, ResumoAcao, ResumoMatinal, Tarefa } from '../../types';
import {
    contarSubtarefas, estadoDaSubtarefa, subtarefaCorrente, textoDaSubtarefa,
} from './subtarefas';

const semAcento = (s: unknown) =>
    String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export interface AcoesDoDia {
    ativas: ResumoAcao[];
    emEspera: ResumoAcao[];
}

/**
 * `resumo` + tarefas vivas -> ações ativas e em espera de `hojeId`.
 *
 * `atrasadas` não é disjunta de `avanco`/`continuo` (o backend grava a mesma
 * ação atrasada na faixa e em `atrasadas`): o dedup por id evita card duplicado
 * e a mesma ação contada duas vezes no % do dia. Ação concluída, excluída ou
 * reagendada para frente já sai da tela, sem esperar o gatilho do backend
 * persistir o mesmo resultado no resumo.
 */
export const classificarAcoesDoDia = (
    resumo: ResumoMatinal | null | undefined,
    acoesAoVivo: Record<string, Tarefa>,
    hojeId: string,
): AcoesDoDia => {
    if (!resumo) return { ativas: [], emEspera: [] };

    const porId = new Map<string, ResumoAcao>();
    for (const a of [
        ...(resumo.hoje?.avanco ?? []),
        ...(resumo.hoje?.continuo ?? []),
        ...(resumo.hoje?.atrasadas ?? []),
        ...(resumo.hoje?.aguardando_terceiro ?? []),
    ]) {
        porId.set(a.id, a);
    }

    const candidatas: ResumoAcao[] = [];
    for (const acao of porId.values()) {
        const tarefa = acoesAoVivo[acao.id];
        if (!tarefa) {
            candidatas.push(acao);
            continue;
        }
        const status = semAcento(tarefa.status);
        const dataLimite = String(tarefa.data_limite || acao.data_limite || '').slice(0, 10);
        if (status === 'concluido' || status === 'excluido' || (dataLimite && dataLimite > hojeId)) continue;

        const plano: ActionPlanItem[] = Array.isArray(tarefa.plano_acao) ? tarefa.plano_acao : [];
        const [etapasFeitas, etapasTotais] = contarSubtarefas(plano);
        const corrente = subtarefaCorrente(plano, dataLimite);
        candidatas.push({
            ...acao,
            titulo: tarefa.titulo || acao.titulo,
            status: tarefa.status,
            area_tematica: tarefa.area_tematica || acao.area_tematica,
            horario_inicio: tarefa.horario_inicio || null,
            horario_fim: tarefa.horario_fim || null,
            data_limite: dataLimite || acao.data_limite,
            prazo_final: tarefa.prazo_final || null,
            etapas_feitas: etapasFeitas,
            etapas_totais: etapasTotais,
            proximo_passo: corrente ? textoDaSubtarefa(corrente) : null,
            subtarefa_do_dia: corrente ? {
                id: corrente.id || null,
                texto: textoDaSubtarefa(corrente),
                estado: estadoDaSubtarefa(corrente),
                data_prevista: String(corrente.data_prevista || dataLimite || '').slice(0, 10) || null,
                aguardando_de: corrente.aguardando_de || null,
                degradation_count: Number(corrente.degradation_count || 0),
            } : null,
        });
    }

    const emEspera = candidatas.filter(a => a.subtarefa_do_dia?.estado === 'aguardando_terceiro');
    const ids = new Set(emEspera.map(a => a.id));
    return { ativas: candidatas.filter(a => !ids.has(a.id)), emEspera };
};
