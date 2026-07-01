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
    file_search?: {
        store_name: string;
        document_name?: string | null;
        operation_name?: string | null;
        status: 'concluido' | 'pendente';
        indexed_at?: string;
    };
}

export interface FileSearchCitation {
    index: number;
    title?: string;
    uri?: string;
    text?: string;
    page_number?: number;
    media_id?: string;
    file_search_store?: string;
    custom_metadata?: Array<{
        key?: string;
        string_value?: string;
        numeric_value?: number;
    }>;
}

export interface SmartSearchResponse {
    intent: KnowledgeIntent;
    synthesis?: string;
    file_search?: {
        synthesis?: string;
        citations: FileSearchCitation[];
        store_name?: string;
        metadata_filter?: string;
    };
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

export interface SincronizarAcervoResponse {
    novos: number;
    reprocessados: number;
    erro: string | null;
}

/** Dispara sob demanda a varredura da Pasta de Deságue (Drop Folder), sem esperar o cron de 15 min. */
export async function sincronizarAcervoManual(): Promise<SincronizarAcervoResponse> {
    const fn = httpsCallable<Record<string, never>, SincronizarAcervoResponse>(
        functions,
        'sincronizar_acervo_manual'
    );
    const res = await fn({});
    return res.data;
}
