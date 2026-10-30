import type { EstrategiaIndicadorSucesso, EstrategiaMarco } from '../../types';
import { idLegado } from './perfilEstrategia';

/**
 * Rascunho e gravação dos marcos e indicadores de sucesso da tela de estratégia.
 *
 * Antes, ler para o rascunho e gravar de volta recompunham cada item só com id, descricao,
 * concluido, registros, dataConclusao e evidencia: salvar a tela apagava em silêncio
 * `dataAlvo` e `esperado` (perfil de 3 meses) e qualquer campo futuro. Aqui os campos que
 * a tela não conhece passam intactos. O lado do MCP é `functions/strategy_tools.py::normalizar_item`.
 */

type Item = EstrategiaIndicadorSucesso | EstrategiaMarco;
type Tipo = 'indicador' | 'marco';

const novoId = (tipo: Tipo) => `${tipo}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export function paraRascunho<T extends Item>(tipo: Tipo, itens?: Array<string | T>): T[] {
    const convertidos = (itens || []).map((item, indice) => {
        if (typeof item === 'string') {
            // Mesmo id do MCP para o item legado em texto: o que a tela grava, o Claude acha.
            return { id: idLegado(tipo, indice, item), descricao: item, concluido: false } as T;
        }
        return {
            ...item,
            // Só texto entra no hash, como no Python: String(1) e str(1.0) divergem.
            id: item.id || idLegado(tipo, indice, typeof item.descricao === 'string' ? item.descricao : ''),
            descricao: item.descricao || '',
            concluido: Boolean(item.concluido),
            evidencia: item.evidencia || '',
            registros: item.registros || [],
        } as T;
    }).filter(item => item.descricao.trim() || item.evidencia?.trim());
    return convertidos.length ? convertidos : [{ id: novoId(tipo), descricao: '', concluido: false } as T];
}

export function paraGravar<T extends Item>(tipo: Tipo, itens?: T[]): T[] {
    return (itens || [])
        .map(item => {
            const { evidencia, dataConclusao, ...resto } = item;
            const gravado = {
                ...resto,
                id: item.id || novoId(tipo),
                descricao: item.descricao.trim(),
                concluido: Boolean(item.concluido),
                registros: item.registros || [],
            } as T;
            if (gravado.concluido) gravado.dataConclusao = dataConclusao || new Date().toISOString();
            if (evidencia?.trim()) gravado.evidencia = evidencia.trim();
            // O Firestore recusa `undefined` (ex.: data alvo apagada no formulário): a chave sai.
            for (const chave of Object.keys(gravado) as Array<keyof T>) {
                if (gravado[chave] === undefined) delete gravado[chave];
            }
            return gravado;
        })
        .filter(item => item.descricao);
}

/**
 * Só os campos que mudaram, antes e depois, para o histórico da estratégia
 * (`estrategia_historico`, o mesmo que o MCP grava). Campo ausente vira null.
 */
export function diferencas(antes: Record<string, unknown>, depois: Record<string, unknown>, campos: string[]) {
    const a: Record<string, unknown> = {};
    const d: Record<string, unknown> = {};
    for (const campo of campos) {
        if (!(campo in depois)) continue;
        if (JSON.stringify(antes[campo] ?? null) === JSON.stringify(depois[campo] ?? null)) continue;
        a[campo] = antes[campo] ?? null;
        d[campo] = depois[campo] ?? null;
    }
    return { antes: a, depois: d, mudou: Object.keys(d).length > 0 };
}
