import type { IncomeEntry, Servico } from '../../types';

/**
 * Renda do mês a partir das parcelas dos contratos de serviço. O que muda no financeiro é
 * decidido aqui, sem Firestore, para ser testável; `index.tsx` só aplica o plano.
 *
 * Incidente de 30/10/2026: três rendas excluídas voltaram, cada uma duas vezes. A sincronia só
 * olhava as rendas ativas (a exclusão sumia da lista) e criava com id aleatório.
 * `functions/rendas_servico.py::fora_da_previsao` é a mesma regra do lado do servidor.
 */

export const STATUS_SEM_PREVISAO = 'sem_previsao';
export const RETIRADA_PREVISAO = 'previsao';

/** Id fixo da renda de uma parcela: duas abas ou aparelhos criando ao mesmo tempo caem no mesmo doc. */
export const idRendaServico = (serviceId: string, parcelaId: string) => `svc_${serviceId}_${parcelaId}`;

/**
 * Ano, mês (0-11) e dia lidos do texto (YYYY-MM-DD, com ou sem hora).
 * `new Date('2026-11-01')` é meia-noite UTC e `getDate()` em Brasília devolve 31/10: a renda da
 * Integrare nasceu em outubro. O servidor e a tela de serviços já leem o texto; a sincronia também.
 */
export const dataDaParcela = (valor?: string): { year: number; month: number; day: number } | null => {
    const achado = String(valor ?? '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!achado) return null;
    const year = Number(achado[1]);
    const mes = Number(achado[2]);
    const day = Number(achado[3]);
    const d = new Date(Date.UTC(year, mes - 1, day));
    const valida = d.getUTCFullYear() === year && d.getUTCMonth() === mes - 1 && d.getUTCDate() === day;
    return valida ? { year, month: mes - 1, day } : null;
};

type DadosRenda = Omit<IncomeEntry, 'id'>;

export interface PlanoRendasDeServicos {
    criar: { id: string; dados: DadosRenda & { data_criacao: string } }[];
    atualizar: { id: string; dados: Partial<DadosRenda> }[];
    /** Rendas ativas a marcar `status: 'deleted'` com `retirada_por: 'previsao'`. */
    retirar: string[];
}

const mudou = (renda: IncomeEntry, esperado: DadosRenda) =>
    renda.amount !== esperado.amount ||
    renda.description !== esperado.description ||
    renda.day !== esperado.day ||
    renda.month !== esperado.month ||
    renda.year !== esperado.year ||
    renda.category !== esperado.category ||
    renda.isReceived !== esperado.isReceived ||
    renda.status !== 'active';

/**
 * `rendas` tem de trazer também as excluídas: a exclusão do usuário é a memória de que a renda
 * não se recria. Quem excluiu a renda por sair da previsão deixa `retirada_por: 'previsao'`, e
 * essa volta quando a parcela volta.
 */
export const planejarRendasDeServicos = (
    services: Servico[],
    rendas: IncomeEntry[],
    agora: Date = new Date(),
): PlanoRendasDeServicos => {
    const plano: PlanoRendasDeServicos = { criar: [], atualizar: [], retirar: [] };
    const porParcela = new Map<string, IncomeEntry[]>();
    for (const renda of rendas) {
        if (renda.parcela_id) porParcela.set(renda.parcela_id, [...(porParcela.get(renda.parcela_id) ?? []), renda]);
    }
    const conhecidas = new Set<string>();
    const retirar = new Set<string>();

    for (const servico of services.filter(s => s.status === 'Ativo' || s.status === 'Concluído')) {
        for (const parcela of servico.parcelas || []) {
            conhecidas.add(parcela.id);
            const daParcela = porParcela.get(parcela.id) ?? [];
            const ativas = daParcela.filter(r => r.status !== 'deleted');
            const quando = dataDaParcela(parcela.data_prevista);

            if (parcela.status === STATUS_SEM_PREVISAO || (!quando && parcela.status !== 'pago')) {
                ativas.forEach(r => retirar.add(r.id));
                continue;
            }
            if (!quando) continue; // paga e sem data: não há competência para gravar, fica como está

            const esperado: DadosRenda = {
                parcela_id: parcela.id,
                service_id: servico.id,
                description: `${servico.titulo} - ${parcela.descricao}`,
                amount: parcela.valor,
                day: quando.day,
                month: quando.month,
                year: quando.year,
                category: servico.categoria_financeira || 'Serviço Particular',
                isReceived: parcela.status === 'pago',
                status: 'active',
            };
            if (ativas.length > 0) {
                ativas.filter(r => mudou(r, esperado)).forEach(r => plano.atualizar.push({ id: r.id, dados: esperado }));
            } else if (daParcela.length === 0) {
                plano.criar.push({
                    id: idRendaServico(servico.id, parcela.id),
                    dados: { ...esperado, data_criacao: agora.toISOString() },
                });
            } else {
                const tirada = daParcela.find(r => r.retirada_por === RETIRADA_PREVISAO);
                if (tirada) plano.atualizar.push({ id: tirada.id, dados: { ...esperado, retirada_por: null } });
            }
        }
    }

    // Parcela que sumiu do contrato, ou contrato que deixou de valer (pausado, cancelado).
    for (const renda of rendas) {
        if (renda.parcela_id && renda.service_id && renda.status !== 'deleted' && !conhecidas.has(renda.parcela_id)) {
            retirar.add(renda.id);
        }
    }
    plano.retirar = [...retirar];
    return plano;
};
