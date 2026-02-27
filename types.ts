
export type Status = 'em andamento' | 'concluído';
export type Prioridade = 'alta' | 'média' | 'baixa';

export interface Acompanhamento {
    data: string;
    nota: string;
}

export type Categoria = string;

export interface PoolItem {
    id: string;
    tipo: 'link' | 'telefone' | 'arquivo';
    valor: string; // O link, o telefone ou o ID/Link do arquivo no Drive
    nome?: string; // Nome do arquivo ou rótulo do link
    data_criacao: string;
    drive_file_id?: string;
}

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
    descricao?: string;
    chat_gemini_url?: string;
    processo_sei?: string;
    tempo_total_segundos?: number;
    sync_status?: 'new' | 'updated' | 'synced' | 'pendente' | 'processando' | 'concluido' | 'erro' | null;
    last_sync_date?: string;
    horario_inicio?: string; // format "HH:mm"
    horario_fim?: string;    // format "HH:mm"
    pool_dados?: PoolItem[];
    ordem?: number;
    reminder_at?: string; // ISO date string for reminder
    reminder_sent?: boolean;
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

export interface ProcessoConhecimento {
    id: string;
    task_id: string;
    file_id: string;
    nome: string;
    texto: string;
    embedding: number[];
    data_vetorizacao: string;
}

export interface BrainstormIdea {
    id: string;
    text: string;
    audioUrl?: string;
    timestamp: string;
    status?: 'active' | 'archived';
}

export interface SlideHistoryEntry {
    id: string;
    title: string;
    createdAt: string;
    slides: any[];
    rascunho: string;
}
export interface FinanceTransaction {
    id: string;
    description: string;
    amount: number;
    date: string;
    sprint: number;
    category: string;
    originalTaskId?: string;
    google_message_id?: string;
    status?: 'active' | 'deleted';
}

export interface FinanceGoal {
    id: string;
    name: string;
    targetAmount: number;
    currentAmount: number;
    priority: number;
    status: 'active' | 'queued' | 'completed';
}

export interface FinanceSettings {
    monthlyBudget: number; // Global default (fall-back)
    monthlyBudgets: { [key: string]: number }; // Specific budgets: "2026-02": 5000
    sprintDates: { [key: number]: string };
    emergencyReserveTarget: number;
    emergencyReserveCurrent: number;
    billCategories: string[];
    incomeCategories: string[];
}


export interface FixedBill {
    id: string;
    description: string;
    amount: number;
    dueDay: number;
    month: number; // 0-11
    year: number;
    barcode?: string;
    pixCode?: string;
    category: string;
    isPaid: boolean;
    attachmentUrl?: string;
    rubricId?: string;
}

export interface BillRubric {
    id: string;
    description: string;
    dueDay: number;
    category: string;
    defaultAmount?: number;
}

export interface IncomeEntry {
    id: string;
    description: string;
    amount: number;
    day: number;
    month: number;
    year: number;
    category: string;
    isReceived: boolean;
    rubricId?: string;
    google_message_id?: string;
    status?: 'active' | 'deleted';
}

export interface IncomeRubric {
    id: string;
    description: string;
    expectedDay: number;
    category: string;
    defaultAmount?: number;
}


// Health Module Types
export interface HealthWeight {
    id: string;
    date: string;
    weight: number;
}

export interface DailyHabits {
    id: string; // date string (YYYY-MM-DD)
    noSugar: boolean;
    noAlcohol: boolean;
    noSnacks: boolean;
    workout: boolean;
    eatUntil18: boolean;
    eatSlowly: boolean;
}

export interface HealthSettings {
    targetWeight: number;
}

export interface HealthExam {
    id: string;
    titulo: string;
    data: string;
    tipo: 'exame' | 'consulta';
    doutor_local?: string;
    resultados?: string;
    pool_dados?: PoolItem[];
    data_criacao: string;
}

export interface HermesNotification {
    id: string;
    title: string;
    message: string;
    type: 'info' | 'warning' | 'success' | 'error';
    timestamp: string;
    isRead: boolean;
    link?: string;
}

export interface CustomNotification {
    id: string;
    message: string;
    frequency: 'daily' | 'weekly' | 'monthly';
    time: string; // HH:mm
    daysOfWeek?: number[]; // 0-6, for weekly
    dayOfMonth?: number; // 1-31, for monthly
    enabled: boolean;
}

export interface AppSettings {
    googleDriveFolderId?: string;
    pomodoro?: {
        enabled: boolean;
        focusTime: number; // minutes
        breakTime: number; // minutes
        enableBeep?: boolean;
    };
    notifications: {
        enablePush: boolean;
        habitsReminder: {
            enabled: boolean;
            time: string; // format "HH:mm"
        };
        weighInReminder: {
            enabled: boolean;
            frequency: 'weekly' | 'biweekly' | 'monthly';
            time: string; // format "HH:mm"
            dayOfWeek: number; // 0-6 (Sunday-Saturday)
        };
        budgetRisk: {
            enabled: boolean;
        };
        overdueTasks: {
            enabled: boolean;
        };
        pgcAudit: {
            enabled: boolean;
            daysBeforeEnd: number;
        };
        custom?: CustomNotification[];
    }
}

export const formatDate = (dateStr: string) => {
    if (!dateStr || dateStr === "-" || dateStr === "0000-00-00" || dateStr.trim() === "") return 'Sem Data';
    const parts = dateStr.split('-');
    if (parts.length !== 3) return dateStr;
    const [year, month, day] = parts.map(Number);
    const date = new Date(year, month - 1, day);
    if (isNaN(date.getTime())) return dateStr;
    const dayOfWeek = new Intl.DateTimeFormat('pt-BR', { weekday: 'long' }).format(date);
    const capitalizedDay = dayOfWeek.charAt(0).toUpperCase() + dayOfWeek.slice(1);
    return `${parts[2]}/${parts[1]}/${parts[0]} (${capitalizedDay})`;
};

export const formatDateLocalISO = (date: Date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
};

export type SistemaStatus = 'ideia' | 'prototipacao' | 'desenvolvimento' | 'testes' | 'producao';

export interface Sistema {
    id: string;
    nome: string;
    repositorio_principal?: string;
    objetivo_negocio?: string;
    status: SistemaStatus;
    link_documentacao?: string;
    link_google_ai_studio?: string;
    link_hospedado?: string;
    data_criacao: string;
    data_atualizacao: string;
}

export type WorkItemPhase = 'planejamento' | 'prototipagem' | 'desenvolvimento' | 'testes' | 'producao';
export type WorkItemPriority = 'Baixa' | 'Média' | 'Alta' | 'Crítica';
export type WorkItemOccurrenceType = 'Bug' | 'Melhoria';
export type WorkItemOccurrenceStatus = 'Pendente' | 'Corrigido' | 'Ignorado';
export type WorkItemEnvironment = 'Local' | 'Staging';

export interface QualityLog {
    id: string;
    tipo: WorkItemOccurrenceType;
    descricao: string;
    evidencia?: string;
    status: WorkItemOccurrenceStatus;
    ambiente: WorkItemEnvironment;
    data_criacao: string;
}

export interface WorkItemAudit {
    id: string;
    timestamp: string;
    usuario: string;
    fase_anterior: WorkItemPhase | 'novo';
    fase_nova: WorkItemPhase;
}

export interface WorkItem {
    id: string;
    sistema_id: string;
    tipo: 'desenvolvimento' | 'ajuste' | 'log';
    descricao: string;
    concluido: boolean;
    data_criacao: string;
    data_conclusao?: string;
    pool_dados?: PoolItem[];
}

export interface AjusteSistema {
    id: string;
    sistema_id: string;
    tarefa_id: string;
    titulo: string;
    data_criacao: string;
    status: Status;
}

export interface GoogleCalendarEvent {
    id: string;
    google_id: string;
    titulo: string;
    data_inicio: string;
    data_fim: string;
    last_sync: string;
}

export interface ConhecimentoItem {
    id: string;
    titulo: string;
    tipo_arquivo: string; // pdf, imagem, doc, link, apresentacao
    url_drive: string;
    tamanho: number;
    data_criacao: string;
    texto_bruto?: string;
    resumo_tldr?: string;
    tags?: string[];
    categoria?: string;
    origem?: {
        modulo: string;
        id_origem: string;
    } | null;
    slides_data?: any;
    parent_id?: string | null;
    is_folder?: boolean;
}

export interface UndoAction {
    id: string;
    label: string;
    undo: () => Promise<void> | void;
    timestamp: number;
}

export interface HermesModalProps {
    isOpen: boolean;
    title: string;
    message: string;
    type: 'alert' | 'confirm';
    onConfirm: () => void;
    onCancel?: () => void;
    confirmLabel?: string;
    cancelLabel?: string;
}

export interface WysiwygEditorProps {
    value: string;
    onChange: (value: string) => void;
    onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
    placeholder?: string;
    className?: string;
    id?: string;
}

export type StatusConvocacao = 'Em regularização' | 'Ativo(a)' | 'Concluído(a)' | 'Desligado(a)';

/**
 * @deprecated Use PerfilPessoa and VinculoProjeto instead. Kept for migration.
 */
export interface Bolsista {
    id?: string;
    nome: string;
    status: StatusConvocacao;
    dataInicio: string;
    dataConclusao: string;
    intersticio: number;
    funcao: string;
    modalidadeBolsa: string;
    cpf: string;
    rg: string;
    endereco: string;
    telefone: string;
    email: string;
    campus?: string;
    cursoIfes?: string;
    agenciaBanestes: string;
    contaBanestes: string;
    curriculoLattes?: string;
    termoResponsabilidadeUrl?: string;
    termoComodatoUrl?: string;
    createdAt: number;
    updatedAt: number;
}

// --- New Project Module Types ---

// 1. Separation of Entities

export interface PerfilPessoa {
    id: string;
    nome: string;
    cpf: string;
    rg: string;
    dados_bancarios: {
        banco: string;
        agencia: string;
        conta: string;
        chave_pix?: string;
    };
    lattes?: string;
    email: string;
    telefone: string;
    endereco: string;
    campus?: string;
    curso?: string;
    data_criacao: string;
    data_atualizacao: string;
}

export interface TipoBolsa {
    id: string;
    nome_modalidade: string;
    valor_integral: number;
    valor_parcial: number; // Ex: 60%
    descricao?: string;
}

export interface VinculoProjeto {
    id: string;
    pessoa_id: string; // Refers to PerfilPessoa.id
    projeto_id: string; // Refers to Projeto.id
    data_inicio: string;
    data_fim_prevista: string;
    data_desligamento_real?: string;
    tipo_bolsa_id: string; // Refers to TipoBolsa.id
    percentual_recebimento: number; // 100 or 60
    funcao?: string;
    status: StatusConvocacao;
    documentos?: {
        termo_responsabilidade?: string;
        termo_comodato?: string;
    };
    valor_bolsa_mensal_atual: number; // Snapshot of value at time of link
}

export interface Projeto {
    id: string;
    nome: string;
    descricao?: string;
    data_criacao: string;
    orcamento?: OrcamentoProjeto;
}

// 2. Master Budget Structure

export interface OrcamentoProjeto {
    custeio: number;
    capital: number;
    bolsas: number;
}

export interface ItemOrcamento {
    id: string;
    nome: string;
    rubrica: 'custeio' | 'capital' | 'bolsas';
    quantidade: number;
    valor_unitario_estimado: number;
    descricao?: string;
    status: 'planejado' | 'aprovado' | 'executado';
}

export interface RemanejamentoRecursos {
    id: string;
    projeto_id: string;
    origem: 'custeio' | 'capital' | 'bolsas';
    destino: 'custeio' | 'capital' | 'bolsas';
    valor: number;
    data: string;
    justificativa: string;
    usuario_responsavel: string;
}

// 3. Acquisitions & Expenses

export interface Cotacao {
    fornecedor?: string;
    valor: number;
    url?: string;
    screenshot_path?: string;
    data_cotacao: string;
}

export interface TransacaoProjeto {
    id: string;
    projeto_id: string;
    item_orcamento_id: string; // Link to ItemOrcamento
    descricao: string;
    valor_real: number;
    data_pagamento: string;
    comprovante_url?: string;
    nota_fiscal_url?: string;
    exige_cotacao: boolean;
    cotacoes?: Cotacao[];
    status: 'pendente' | 'pago' | 'cancelado';
    tipo: 'compra' | 'servico' | 'bolsa';
}

// Shopping List Module Types
export interface ShoppingItem {
    id: string;
    nome: string;
    categoria: string;
    quantidade: string;
    unit: string;
    isPlanned: boolean;
    isPurchased: boolean;
    ordem?: number;
}

/** @deprecated Use single-list ShoppingItem without locationId */
export interface ShoppingLocation {
    id: string;
    nome: string;
    icon?: string;
}
