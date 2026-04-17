import { httpsCallable } from 'firebase/functions';
import { functions } from '../../firebase';

export type KnowledgeIntent = 'BUSCA_SIMPLES' | 'SINTESE_PROFUNDA';

export type KnowledgeItemType = 'node' | 'artefato';

export interface KnowledgeFilters {
    area_tematica?: string;
    tags?: string[];
    data_inicio?: string;
    data_fim?: string;
    tipo?: 'all' | KnowledgeItemType;
}

export interface KnowledgeResult {
    id: string;
    type: KnowledgeItemType;
    title: string;
    snippet: string;
    resumo_semantico: string;
    tags: string[];
    date: string;
    area_tematica?: string;
    drive_url?: string;
    drive_file_id?: string;
    tipo_mime?: string;
    origem?: string;
    task_id?: string;
    task_ids?: string[];
    acervo_id?: string;
    n_tasks?: number;
}

export interface SmartSearchResponse {
    intent: KnowledgeIntent;
    synthesis?: string;
    results: KnowledgeResult[];
}

export interface RawTextResponse {
    texto_bruto: string;
    truncated: boolean;
    aviso?: string;
}

export async function smartSearchKG(
    query: string,
    filtros: KnowledgeFilters = {}
): Promise<SmartSearchResponse> {
    const fn = httpsCallable<
        { query: string; filtros?: KnowledgeFilters },
        SmartSearchResponse
    >(functions, 'smart_search_kg');
    const res = await fn({ query, filtros });
    return res.data;
}

export async function getArtefatoRawText(
    id: string,
    tipo: KnowledgeItemType
): Promise<RawTextResponse> {
    const fn = httpsCallable<
        { id: string; tipo: KnowledgeItemType },
        RawTextResponse
    >(functions, 'get_artefato_raw_text');
    const res = await fn({ id, tipo });
    return res.data;
}
