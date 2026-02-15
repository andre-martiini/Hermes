
export type Status = 'em andamento' | 'concluído';
export type Prioridade = 'alta' | 'média' | 'baixa';

export interface Acompanhamento {
    data: string;
    nota: string;
}

export type Categoria = 'CLC' | 'ASSISTÊNCIA' | 'GERAL' | 'NÃO CLASSIFICADA';

export interface Tarefa {
    id: string;
    titulo: string;
    projeto: string;
    data_inicio: string;
    data_limite: string;
    status: Status;
    prioridade: Prioridade;
    categoria: Categoria;
    contabilizar_meta: boolean;
    data_criacao: string;
    data_conclusao?: string | null;
    notas?: string;
    sistema?: string;
    acompanhamento?: Acompanhamento[];
    entregas_relacionadas?: string[];
    is_single_day?: boolean;
    chat_gemini_url?: string;
    tempo_total_segundos?: number;
}

export interface AtividadeRealizada {
    id: string;
    descricao_atividade: string;
    data_inicio: string;
    data_fim?: string;
    entrega_id: string;
    usuario: string;
    status_atividade: string;
}

export interface EntregaInstitucional {
    id: string;
    entrega: string;
    area: string;
    descricao_trabalho?: string;
    processo_sei?: string;
    mes: number;
    ano: number;
}

export interface Afastamento {
    id: string;
    usuario: string;
    data_inicio: string;
    data_fim: string;
    motivo: string;
}

export interface PlanoTrabalhoItem {
    origem: string;
    unidade: string;
    entrega: string;
    percentual: number;
    descricao: string;
}

export interface PlanoTrabalho {
    id: string;
    mes_ano: string;
    itens: PlanoTrabalhoItem[];
    data_atualizacao: string;
}

export interface BrainstormIdea {
    id: string;
    text: string;
    audioUrl?: string;
    timestamp: string;
    status?: 'active' | 'archived';
}
