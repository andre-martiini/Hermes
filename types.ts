import React from 'react';

export type Status = 'em andamento' | 'stand-by' | 'concluído';

export interface Toast {
    id: string;
    message: string;
    type: 'success' | 'error' | 'info' | 'warning';
    action?: { label: string | React.ReactNode, onClick: () => void };
    actions?: { label: string | React.ReactNode, onClick: () => void }[];
}

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

export type TipoAcao = 'fast' | 'deep';

export interface ActionPlanItem {
    id: string;
    text: string;
    completed: boolean;
}

export interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    subtype?: 'proactive_insight' | string;
    isArtifact?: boolean;
    proposedPlan?: ActionPlanItem[];
    timestamp?: string;
}

export interface ActionPlanHistory {
    data: string;
    items: ActionPlanItem[];
}

export interface TaskReminder {
    id: string;
    reminder_at: string; // ISO date string for reminder
    reminder_sent: boolean;
    created_at: string;
    message?: string;
}

export type FrequenciaRecorrencia = 'semanal' | 'mensal';

export interface RecorrenciaAcao {
    ativo: boolean;
    frequencia?: FrequenciaRecorrencia; // ausente = 'mensal' (retrocompatibilidade)
    dia_do_mes?: number; // 1-31, para frequência mensal (dias além do fim do mês caem no último dia)
    dia_da_semana?: number; // legado: um único dia da semana (0=domingo a 6=sábado)
    dias_da_semana?: number[]; // 0 (domingo) a 6 (sábado), um ou mais dias, para frequência semanal
    intervalo_semanas?: number; // 1 = toda semana (padrão); 2 = a cada 2 semanas; etc.
    ultima_geracao?: string; // "YYYY-MM" (mensal) ou "YYYY-MM-DD" (semanal) da última instância gerada
}

export interface WhatsappVinculo {
    chat_id: string;      // "5527999999999@c.us" ou "...@g.us" — mesma chave de whatsapp_messages.chat_id
    chat_name: string;    // nome no momento do vínculo (snapshot)
    is_group: boolean;
    data_vinculo: string; // ISO date, mesmo padrão de PoolItem.data_criacao
}

// Doc da coleção whatsapp_messages (escrito por services/whatsapp-capture/index.js;
// transcription_text/transcription_model e consolidation_ids são preenchidos depois
// pelo job de consolidação — functions/whatsapp_consolidation.py).
export interface WhatsappMessageDoc {
    id: string;              // `{chat_id}_{wa_message_id}` — idempotente
    wa_message_id: string;
    chat_id: string;
    chat_name: string;
    is_group: boolean;
    author_name: string;
    from_me: boolean;
    timestamp: any;          // Firestore Timestamp (quando a mensagem foi enviada)
    ingested_at: any;        // Firestore Timestamp (quando o worker gravou)
    message_type: string;    // 'chat' | 'ptt' | 'audio' | 'image' | ...
    content: string;
    links?: string[];
    media?: { mimeType: string; sizeBytes: number; storage_path?: string } | null;
    transcription_text?: string | null;
    transcription_model?: string | null;
    consolidation_ids?: string[]; // jobs de consolidação que incluíram esta mensagem
}

export interface WhatsappConsolidacaoItemAcao {
    descricao: string;
    responsavel?: string;
    prazo?: string | null;
}

// Doc da coleção whatsapp_consolidacoes — job assíncrono de consolidação da Caixa de
// Entrada WhatsApp (WhatsappInboxView.tsx cria via addDoc; o trigger
// on_whatsapp_consolidacao_created processa e escreve progresso/resultado).
export interface WhatsappConsolidacao {
    id: string;
    // Requisição (frontend)
    chat_id: string;
    chat_name: string;
    is_group: boolean;
    message_ids: string[];   // doc IDs de whatsapp_messages, máx. 200
    requested_at: any;       // Firestore Timestamp (serverTimestamp)
    // Ciclo de vida (backend)
    status: 'queued' | 'processing' | 'completed' | 'error';
    progress?: string;       // ex.: "Transcrevendo áudio 2/5"
    error?: string | null;
    updated_at?: any;
    // Resultado (backend, no completed)
    transcript_literal?: string; // montado por código, nunca pela IA
    resumo?: string;
    itens_de_acao?: WhatsappConsolidacaoItemAcao[];
    decisoes?: string[];
    periodo_inicio?: string; // ISO
    periodo_fim?: string;    // ISO
    n_mensagens?: number;
    n_audios_transcritos?: number;
    n_audios_ignorados?: number;
    n_videos_transcritos?: number;
    n_videos_ignorados?: number;
    attachments?: { message_id: string; mimeType: string; storage_path?: string }[];
    digest_id?: string;      // doc gravado em whatsapp_digests (consol_*)
    // Associação (frontend, ao anexar a uma ação)
    task_id?: string | null;
    task_titulo?: string | null;
    applied_at?: string | null; // ISO
}

export interface Tarefa {
    id: string;
    titulo: string;
    projeto: string;
    data_inicio: string;
    data_limite: string;
    prazo_final?: string;
    status: Status;
    area_tematica: string;
    execution_lane?: 'avanco' | 'continuo' | 'aguardando_terceiro';
    degradation_count?: number;
    tags?: string[];
    contabilizar_meta: boolean;
    data_criacao: string;
    data_atualizacao?: string;
    data_conclusao?: string | null;
    status_atualizacao?: string;
    notas?: string;
    sistema?: string;
    acompanhamento?: Acompanhamento[];
    entregas_relacionadas?: string[];
    descricao?: string;
    chat_gemini_url?: string;
    chat_history?: ChatMessage[];
    processo_sei?: string;
    whatsapp_vinculos?: WhatsappVinculo[]; // contatos/grupos de WhatsApp vinculados manualmente — matching determinístico usado por whatsapp_ingest.py (ver email_action_linker.py:_build_candidate)
    sync_status?: 'new' | 'updated' | 'synced' | 'pendente' | 'processando' | 'concluido' | 'erro' | null;
    last_sync_date?: string;
    horario_inicio?: string; // format "HH:mm"
    horario_fim?: string;    // format "HH:mm"
    pool_dados?: PoolItem[];
    ordem?: number;
    reminder_at?: string; // ISO date string for reminder
    reminder_sent?: boolean;
    reminders?: TaskReminder[];
    tipo_acao?: TipoAcao;
    plano_acao?: ActionPlanItem[];
    plano_acao_historico?: ActionPlanHistory[];
    insights_ignorados?: string[]; // opiniões proativas que o usuário pediu para não reiterar
    origem?: 'manual' | 'audio' | 'whatsapp';
    base_conhecimento?: string;
    reuniao_vinculada_id?: string;
    knowledge_item_ids?: string[];
    extra_context_id?: string;
    // Knowledge Graph fields
    concept_node_id?: string | null;     // Preenchido na Fase 2 (cristalização)
    sourceGmailMessageId?: string;       // Origem do email que gerou a tarefa (idempotência)
    sourceKnowledgeId?: string;          // Referência a um Nó de Fonte do Grafo RAG
    kg_tags?: string[];                  // Tags geradas pela Fase 1 (Retrieval-First)
    kg_crystallized?: boolean;           // true após a Fase 2 ser concluída
    artefatos_kg?: ArtefatoKG[];         // Artefatos indexados pelo módulo de artefatos
    auto_data_atualizada?: boolean;
    estrategia_objetivo_id?: string;
    estrategia_indicador_id?: string;
    recorrencia?: RecorrenciaAcao;
    email_link_optout?: boolean; // true = não sugerir vínculos de e-mail para esta ação (email_action_linker.py)
}


export interface ArtefatoKG {
    nome: string;
    url: string;
    tipo_mime: string;
    resumo_semantico: string | null;
    status_indexacao: 'pendente' | 'concluido' | 'falha_acesso' | 'falha_limite_tamanho' | 'ignorado_mime' | 'falha_embedding';
    drive_file_id?: string;
}

/** Documento da coleção acervo_global — arquivos avulsos da Pasta de Deságue. */
export interface AcervoGlobal {
    id: string;
    nome: string;
    url: string;
    tipo_mime: string;
    drive_file_id: string;
    resumo_semantico: string | null;
    tags: string[];
    status_indexacao: 'pendente' | 'concluido' | 'falha_acesso' | 'falha_limite_tamanho' | 'ignorado_mime' | 'falha_embedding' | 'falha_permanente';
    tentativas?: number;
    indexed_at: string;
    file_search?: GeminiFileSearchIndex;
}

/** Documento da coleção indice_artefatos — índice vetorial unificado (tarefas + acervo). */
export interface IndiceArtefato {
    nome: string;
    url: string;
    tipo_mime: string;
    resumo_semantico: string;
    // embedding: number[] — omitido no frontend (uso exclusivo do backend)
    tags: string[];
    origem: 'tarefa' | 'acervo';
    task_id?: string;
    acervo_id?: string;
    indexed_at: string;
    file_search?: GeminiFileSearchIndex;
}

export interface GeminiFileSearchIndex {
    store_name: string;
    document_name?: string | null;
    operation_name?: string | null;
    status: 'concluido' | 'pendente';
    metadata?: Array<{
        key: string;
        string_value?: string;
        numeric_value?: number;
    }>;
    indexed_at?: string;
}

export interface AtividadeRealizada {
    id: string;
    descricao_atividade: string;
    data_inicio: string;
    data_fim?: string;
    entrega_id: string;
    usuario: string;
    status_atividade: string;
    origem?: 'manual' | 'ia';
    task_ids?: string[];
    data_criacao?: string;
    data_atualizacao?: string;
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

export interface PaginaMonitorada {
    id: string;
    url: string;
    apelido: string;
    objetivo: string;
    seletor_css?: string;
    hash_atual?: string;
    texto_atual?: string;
    ultima_verificacao?: string;
    ultima_mudanca?: string;
    ultima_analise?: string;
    ultima_falha?: string;
    erro_ultima_verificacao?: string | null;
    ultimo_alerta_telegram?: string | null;
    erro_telegram?: string | null;
    ativo: boolean;
    userId: string;
    criado_em: string;
    task_id?: string; // se preenchido, avanço do objetivo propõe registrar no diário da ação em vez de alerta avulso
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
    origin?: 'internal' | 'external';
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
    investmentReserveTarget?: number;
    investmentReserveCurrent?: number;
    defaultPrincipalIncome?: number;
    billCategories: string[];
    incomeCategories: string[];
    externalSpendingLimit?: number;
    externalToken?: string;
}

export type EstrategiaPilar = 'carreira' | 'financas' | 'saude' | 'intelectual' | 'estilo_vida';
export type EstrategiaTipoMeta = 'absoluta' | 'relativa_qualitativa';
export type EstrategiaStatus = 'ativo' | 'concluido' | 'revisar';

export interface EstrategiaIndicadorSucesso {
    id: string;
    descricao: string;
    concluido: boolean;
    dataConclusao?: string;
    evidencia?: string;
    registros?: Array<{
        id: string;
        data: string;
        nota: string;
    }>;
}

export interface EstrategiaMarco {
    id: string;
    descricao: string;
    concluido: boolean;
    dataConclusao?: string;
    evidencia?: string;
    registros?: Array<{
        id: string;
        data: string;
        nota: string;
    }>;
}

export interface EstrategiaPessoal {
    id?: string;
    userId: string;
    pilar: EstrategiaPilar;
    objetivoMacro: string;
    tipoMeta: EstrategiaTipoMeta;
    metricaAlvo?: {
        valorInicial?: number;
        valorAtual: number;
        valorObjetivo: number;
        unidade: string;
    };
    historicoMetrica?: Array<{
        id: string;
        data: string;
        valor: number;
        nota?: string;
    }>;
    indicadoresSucesso?: Array<string | EstrategiaIndicadorSucesso>;
    marcos?: Array<string | EstrategiaMarco>;
    diretrizesDerivadas: string[];
    status: EstrategiaStatus;
    timestamp: any;
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
    pixQrCodeUrl?: string;
    rubricId?: string;
}

export interface BillRubric {
    id: string;
    description: string;
    dueDay: number;
    category: string;
    defaultAmount?: number;
    pixCode?: string;
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
    parcela_id?: string;
    service_id?: string;
}

export interface IncomeRubric {
    id: string;
    description: string;
    expectedDay: number;
    category: string;
    defaultAmount?: number;
    eventual?: boolean; // true = fonte esporádica (ex: substituição de chefia); não cobra lançamento todo mês
}


// Health Module Types
export type PullupPhase = 'dead_hang' | 'negative' | 'assisted' | 'full';

export interface WalkBlock {
    id: string;
    time?: string; // HH:mm
    distance: number; // km
    minutes?: number;
    steps?: number;
    calories?: number;
    source?: 'web' | 'telegram';
}

export interface ExerciseLog {
    id: string; // date string (YYYY-MM-DD)
    pushups?: { done: number; goal: number };
    pullups?: { done: number; goal: number; phase: PullupPhase };
    plank?: { seconds: number };
    bridge?: { reps: number };
    birdDog?: { reps: number };
    squats?: { reps: number };
    walk?: { done: number; distance?: number; steps?: number }; // minutes, km, steps
    walkBlocks?: WalkBlock[]; // blocos intermitentes de esteira registrados manualmente
    calories?: number;
    activeMinutes?: number;
    heartRate?: {
        avg: number;
        max: number;
    };
    sleep?: {
        totalMinutes: number;
        deepMinutes?: number;
        remMinutes?: number;
    };
    pain?: {
        morning?: number;
        afterWalk?: number; // N16 correção 2 — dor logo após a caminhada matinal, campo próprio (não sobrescreve morning)
        evening?: number;
        sciatica?: boolean;
        crisis?: boolean;
        notes?: string;
        telegram_checked_at?: string;
    };
    radicular?: RadicularSymptom;
    strength?: StrengthTraining;
    therapy?: TherapyModality[];
    nutrition?: NutritionAdherence;
    sleepQuality?: SleepQuality;
    meds?: DailyMedication;
    triggers?: DailyTriggers;
    note?: string;
    entrySource?: DailyEntrySource;
}

export type RadicularLocation = 'nenhum' | 'gluteo' | 'quadril' | 'coxa' | 'joelho' | 'panturrilha' | 'tornozelo' | 'pe';
export type RadicularSide = 'direito' | 'esquerdo' | 'ambos';
export type TherapyModality = 'pilates' | 'fisioterapia' | 'rpg' | 'acupuntura' | 'nenhuma';
export type TriggerType = 'espirro_crise_alergica' | 'viagem_longa_sentado' | 'dia_muito_sentado' | 'torcao_no_sono' | 'carga_assimetrica' | 'estresse' | 'outro';
export type DailyEntrySource = 'painel' | 'telegram' | 'ambos';

export interface RadicularSymptom {
    location: RadicularLocation;
    side?: RadicularSide;
    intensity?: number; // 0-10
    motorWeakness?: boolean; // sinal vermelho: fraqueza para levantar a ponta do pe
}

export interface StrengthTraining {
    done: boolean;
    block?: 'A' | 'B' | null;
    minutes?: number;
}

export interface NutritionAdherence {
    plan: 'sim' | 'parcial' | 'nao';
    proteinTarget: boolean;
}

export interface SleepQuality {
    wokeInPain: boolean;
    quality?: number; // 1-5
}

export interface DailyMedication {
    pregabalina: boolean;
    dipirona: number;
    adorlan: number;
    fexofenadina: boolean;
    outros?: string;
}

export interface DailyTriggers {
    types: TriggerType[];
    note?: string;
}

export const RADICULAR_LOCATIONS: { value: RadicularLocation; label: string }[] = [
    { value: 'nenhum', label: 'Nenhum' },
    { value: 'gluteo', label: 'Glúteo' },
    { value: 'quadril', label: 'Quadril' },
    { value: 'coxa', label: 'Coxa' },
    { value: 'joelho', label: 'Joelho' },
    { value: 'panturrilha', label: 'Panturrilha' },
    { value: 'tornozelo', label: 'Tornozelo' },
    { value: 'pe', label: 'Pé' },
];

export const THERAPY_MODALITIES: { value: TherapyModality; label: string }[] = [
    { value: 'pilates', label: 'Pilates' },
    { value: 'fisioterapia', label: 'Fisioterapia' },
    { value: 'rpg', label: 'RPG' },
    { value: 'acupuntura', label: 'Acupuntura' },
    { value: 'nenhuma', label: 'Nenhuma' },
];

export const TRIGGER_TYPES: { value: TriggerType; label: string }[] = [
    { value: 'espirro_crise_alergica', label: 'Espirro / crise alérgica' },
    { value: 'viagem_longa_sentado', label: 'Viagem longa sentado' },
    { value: 'dia_muito_sentado', label: 'Dia muito sentado' },
    { value: 'torcao_no_sono', label: 'Torção no sono' },
    { value: 'carga_assimetrica', label: 'Carga assimétrica' },
    { value: 'estresse', label: 'Estresse' },
    { value: 'outro', label: 'Outro' },
];

export interface ExerciseSettings {
    pushups?: {
        activeGoal: number;
        floor: number;
    };
    pullups?: {
        activeGoal: number;
        phase: PullupPhase;
        consecutiveGateMet: number; // 0, 1, or 2 — advance phase at 2
        floor: number;
    };
}

export interface HealthWeight {
    id: string;
    date: string;
    weight: number;
    fatPercentage?: number;
    muscleMass?: number;
}

export interface HealthWaist {
    id: string;
    date: string;
    cm: number;
}

export interface HealthWeeklySummary {
    id: string; // = weekEnd (YYYY-MM-DD)
    weekStart: string;
    weekEnd: string;
    avgWeight: number | null;
    weightDelta: number | null;
    waistCm: number | null;
    avgPainMorning: number | null;
    avgPainEvening: number | null;
    kmTotal: number;
    strengthSessions: number;
    strengthGoal: number;
    dietDays: number;
    daysWithLog: number;
    events: { date: string; label: string; type: string }[];
}

// N14 — Relatorio Semanal (placa de resultado), Fase 1: so campos calculados em
// codigo. adjustment/text/audit ficam null ate as fases 2 e 3 existirem.
export interface HealthWeeklyReportCard {
    week_start: string;
    week_end: string;
    weight_avg7: number | null;
    weight_delta: number | null;
    waist: { value: number | null; delta: number | null };
    km_total: number;
    km_days: number;
    pain_morning_avg: number | null;
    pain_evening_avg: number | null;
    radicular_trend: 'subindo' | 'estável' | 'descendo' | 'sem_dado';
    strength_done: number;
    strength_planned: number;
    therapy_done: number;
    therapy_planned: number;
    checkin_adherence: number;
    sleep_avg: number | null;
}

// Chave estavel da regra de decisao (N14 Fase 2) que gerou `adjustment` -- a
// auditoria da semana seguinte compara por esta chave, nunca reparseando a
// prosa de `adjustment`. Ausente em relatorios da Fase 1 (antes da Fase 2
// existir).
export type HealthWeeklyReportAdjustmentRule =
    | 'sinal_vermelho'
    | 'reduzir_carga'
    | 'poucos_dados'
    | 'aderencia'
    | 'cortar_kcal'
    | 'aumentar_kcal'
    | 'manter';

export interface HealthWeeklyReport {
    id: string; // = YYYY-Www (semana ISO)
    card: HealthWeeklyReportCard;
    adjustment: string | null;
    adjustment_rule?: HealthWeeklyReportAdjustmentRule;
    text: string | null;
    audit: string | null;
    prompt_version: string | null;
    generated_at: string;
}

export type HealthEventType = 'fisioterapia' | 'viagem' | 'medicacao_inicio' | 'medicacao_fim' | 'modalidade_terapeutica' | 'consulta_medica' | 'outro';

export interface HealthEvent {
    id: string;
    date: string;
    type: HealthEventType;
    label: string;
    endDate?: string;
    source?: 'manual' | 'calendar' | 'exam';
    externalId?: string;
}

export const HEALTH_EVENT_TYPES: { value: HealthEventType; label: string }[] = [
    { value: 'fisioterapia', label: 'Fisioterapia' },
    { value: 'viagem', label: 'Viagem' },
    { value: 'medicacao_inicio', label: 'Início de medicação' },
    { value: 'medicacao_fim', label: 'Fim de medicação' },
    { value: 'modalidade_terapeutica', label: 'Troca de modalidade' },
    { value: 'consulta_medica', label: 'Consulta médica' },
    { value: 'outro', label: 'Outro' },
];

export interface HealthSettings {
    targetWeight: number;
    walkingMinimumMinutes?: number;
    walkingIdealMinutes?: number;
    walkingMinimumKm?: number;
    walkingIdealKm?: number;
    ritmoAlvoKgSemana?: number; // trajetoria alvo de perda de peso, kg/semana
    marcos?: number[]; // marcos de peso (kg) para projecao de data estimada
}

export interface HealthTelegramReminder {
    id: string;
    title: string;
    message: string;
    time: string; // HH:mm
    enabled: boolean;
    daysOfWeek?: number[]; // 0-6 (Sunday-Saturday)
    category?: 'spine' | 'walking' | 'nutrition' | 'pain' | 'checkin_morning' | 'checkin_night' | 'custom';
    telegramOnly?: boolean;
    created_by_uid?: string;
    last_sent_date?: string;
    data_criacao?: string;
    data_atualizacao?: string;
}

export type HealthExamTipo = 'exame' | 'consulta' | 'cirurgia' | 'prescricao' | 'encaminhamento' | 'laudo_imagem' | 'atestado' | 'outro';

export const HEALTH_EXAM_TYPES: { value: HealthExamTipo; label: string }[] = [
    { value: 'exame', label: 'Exame' },
    { value: 'consulta', label: 'Consulta' },
    { value: 'cirurgia', label: 'Cirurgia' },
    { value: 'prescricao', label: 'Prescrição' },
    { value: 'encaminhamento', label: 'Encaminhamento' },
    { value: 'laudo_imagem', label: 'Laudo de imagem' },
    { value: 'atestado', label: 'Atestado' },
    { value: 'outro', label: 'Outro' },
];

export interface HealthExam {
    id: string;
    titulo: string;
    data: string;
    tipo: HealthExamTipo;
    doutor_local?: string;
    resultados?: string;
    pool_dados?: PoolItem[];
    data_criacao: string;
    achadosChave?: string;
    profissional?: string;
    especialidade?: string;
    proximaReavaliacao?: string;
    tags?: string[];
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
    notifications: {
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

export const formatDate = (dateStr: any) => {
    if (!dateStr || dateStr === "-" || dateStr === "0000-00-00") return 'Sem Data';

    let actualDateStr = "";
    if (typeof dateStr === 'string') {
        actualDateStr = dateStr;
    } else if (dateStr && typeof dateStr === 'object') {
        // Handle Firestore Timestamp
        if (dateStr.seconds) {
            actualDateStr = formatDateLocalISO(new Date(dateStr.seconds * 1000));
        } else if (dateStr instanceof Date) {
            actualDateStr = formatDateLocalISO(dateStr);
        } else {
            return 'Data Inválida';
        }
    } else {
        return 'Sem Data';
    }

    if (actualDateStr.trim() === "") return 'Sem Data';

    const parts = actualDateStr.split('-');
    if (parts.length !== 3) return actualDateStr;
    const [year, month, day] = parts.map(Number);
    const date = new Date(year, month - 1, day);
    if (isNaN(date.getTime())) return actualDateStr;
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

// Distancia diaria de caminhada: soma apenas os blocos registrados no Hermes
// (painel web ou comando do Telegram). O antigo campo `walk` e legado.
export const sumWalkBlocksKm = (log?: ExerciseLog | null): number => {
    if (!log?.walkBlocks) return 0;
    return log.walkBlocks.reduce((sum, block) => sum + (block.distance || 0), 0);
};



export interface GoogleCalendarEvent {
    id: string;
    google_id: string;
    calendar_id?: string;
    titulo: string;
    data_inicio: string;
    data_fim: string;
    last_sync: string;
}

export interface ConhecimentoItem {
    id: string;
    titulo: string;
    tipo_arquivo: string; // pdf, imagem, doc, link, apresentacao, nota, mensagem
    url_drive: string;
    tamanho: number;
    data_criacao: string;
    data_atualizacao?: string;
    texto_bruto?: string;
    resumo_tldr?: string;
    tags?: string[];
    categoria?: string;
    area_tematica?: string;
    base_id?: string; // Link to a specific personalized RAG base
    origem?: {
        modulo: string;
        id_origem: string;
    } | null;
    parent_id?: string | null;
    is_folder?: boolean;
    orphan_action_title?: string;
    fileHandle?: any;
}

export interface BaseConhecimento {
    id: string;
    nome: string;
    descricao?: string;
    cor?: string;
    emoji?: string;
    tipo?: string;
    data_criacao: string;
    data_atualizacao: string;
    configuracao_rag: {
        incluir_diarios: boolean;
        incluir_manual: boolean;
        categorias_vinculadas: string[];
        tags_vinculadas: string[];
    };
    contagem_elementos?: number;
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
    onPaste?: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void;
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
    cpf?: string;
    rg?: string;
    dados_bancarios?: {
        banco: string;
        agencia: string;
        conta: string;
        chave_pix?: string;
    };
    lattes?: string;
    email: string;
    telefone: string;
    endereco?: string;
    campus?: string;
    curso?: string;
    
    // --- Campos de Contatos/Histórico ---
    tags?: string[];
    origem?: 'manual' | 'google_contacts' | 'extracao_ia';
    google_contact_id?: string;
    google_etag?: string;
    whatsapp_chat_id?: string;
    observacoes?: string;
    resumo_ia?: string;
    avatar_color?: string;
    avatar_initials?: string;
    
    data_criacao: string;
    data_atualizacao: string;
}

export interface InteracaoPessoa {
    id: string;
    pessoa_id: string;
    tarefa_id?: string;
    reuniao_id?: string;
    sessao_copiloto_id?: string;
    consolidacao_id?: string;
    tipo: 'mencao_tarefa' | 'mencao_diario' | 'reuniao' | 'manual' | 'mencao_copiloto' | 'whatsapp';
    data: string;
    descricao: string;
    link_origem?: string;
    data_criacao: string;
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
    public_registration_token?: string;
    public_registration_updated_at?: string;
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

// Services Module Types
export interface ParcelaServico {
    id: string;
    descricao: string;
    valor: number;
    data_prevista: string;
    status: 'pendente' | 'pago';
}

// ─── Knowledge Graph ──────────────────────────────────────────────────────────

export interface KnowledgeNode {
    id: string;
    titulo: string;
    area_tematica: string;
    embedding: number[];
    n_tasks: number;              // contador para média vetorial incremental
    task_ids: string[];           // IDs das tarefas cristalizadas neste nó
    resumo?: string;              // Último resumo consolidado gerado pela IA
    data_criacao: string;
    data_atualizacao: string;
}

export interface KnowledgeEdge {
    task_id: string;
    node_id: string;
    peso_semantico: number;       // 0.0 – 1.0
    data_conclusao: string;       // ISO date — marco zero para time decay
}

// ─────────────────────────────────────────────────────────────────────────────

export interface Relatorio {
    id: string;
    titulo: string;
    tipo: string;
    markdown: string;
    secoes: string[];
    session_id?: string;
    task_id?: string;
    createdAt: any;
    driveFileId?: string | null;
    driveUrl?: string | null;
}

export interface Servico {
    id: string;
    titulo: string;
    descricao: string;
    cliente: string;
    papel: string;
    status: 'Prospecção' | 'Ativo' | 'Concluído' | 'Cancelado' | 'Em Pausa';
    tags: string[];
    data_inicio: string;
    data_termino: string;
    carga_horaria_semanal: number;
    tipo_contrato: 'Mensalidade' | 'Pacote Fechado';
    valor_total: number;
    parcelas: ParcelaServico[];
    categoria_financeira?: 'Bolsa' | 'Serviço Particular';
    data_criacao: string;
    data_atualizacao: string;
    base_id?: string;
}

export interface CopilotDriveFile {
    driveFileId: string;
    driveFileName?: string | null;
}


// --- RESUMO MATINAL (resumo_matinal/{YYYY-MM-DD}) ---
// Espelho tipado do dict devolvido por functions/morning_summary.py.
// Tudo aqui é calculado em Python, de forma determinística — o frontend só
// desenha. Ver o docstring do módulo para por que cada bloco existe.

export type ResumoFocoRegra =
    | 'prazo_final_iminente'
    | 'degradacao_critica'
    | 'sla_estourado'
    | 'meta_parada'
    | 'agendada'
    | 'fila_avanco';

export interface ResumoFoco {
    task_id: string;
    titulo: string;
    regra: ResumoFocoRegra;
    motivo: string;
    proximo_passo: string | null;
    horario_inicio: string | null;
}

export interface ResumoAcao {
    id: string;
    titulo: string;
    status?: string;
    area_tematica?: string;
    projeto?: string;
    horario_inicio: string | null;
    horario_fim: string | null;
    execution_lane: 'avanco' | 'continuo' | 'aguardando_terceiro';
    degradation_count: number;
    /** Arrastada para hoje pelo reset da meia-noite, não escolhida para hoje. */
    herdada: boolean;
    cobrar: boolean;
    atrasada: boolean;
    data_limite: string;
    prazo_final: string | null;
    proximo_passo: string | null;
    etapas_feitas: number;
    etapas_totais: number;
    estrategia_objetivo_id: string | null;
}

export interface ResumoEvento {
    titulo: string;
    inicio: string | null;
    fim: string | null;
    dia_inteiro: boolean;
}

export interface ResumoJanelaLivre {
    inicio: string;
    fim: string;
    minutos: number;
}

export interface ResumoPrazoDuro {
    id: string;
    titulo: string;
    prazo_final: string;
    dias: number;
}

export interface ResumoFilaItem {
    titulo: string;
    canal?: string;
    desde?: string;
    itens?: number;
    motivo?: string;
    quando?: string | null;
    valor?: number;
    vencimento?: string;
    dias?: number;
    vencida?: boolean;
}

export interface ResumoFila {
    total: number;
    amostra: ResumoFilaItem[];
    /** Destino de navegação sugerido — mapeado para viewMode em index.tsx. */
    rota: string;
}

export interface ResumoMeta {
    id: string;
    pilar?: EstrategiaPilar;
    pilar_label?: string;
    /** false para o pilar `saude`, executado pelos registros do módulo Saúde e não por ações. */
    gerida_por_acoes: boolean;
    objetivo: string;
    status?: EstrategiaStatus;
    acoes_hoje: number;
    titulos_hoje: string[];
    ultimo_movimento: string | null;
    dias_parada: number | null;
    progresso_pct: number | null;
    unidade: string | null;
    marcos_abertos: number;
    marcos_total: number;
}

export interface ResumoMatinal {
    data: string;
    dia_semana: string;
    versao: string;
    gerado_em: string;
    foco: ResumoFoco[];
    hoje: {
        avanco: ResumoAcao[];
        continuo: ResumoAcao[];
        aguardando_terceiro: ResumoAcao[];
        atrasadas: ResumoAcao[];
    };
    agenda: ResumoEvento[];
    janelas_livres: ResumoJanelaLivre[];
    prazos_duros: ResumoPrazoDuro[];
    carga_semana: Array<{ data: string; total: number }>;
    filas: Record<string, ResumoFila>;
    saude: {
        rotinas_hoje: Array<{
            titulo: string;
            hora: string | null;
            categoria?: string;
            /** Chave de verificação, ou null se a rotina é só um aviso ilustrativo. */
            verificavel: 'pesagem' | 'cintura' | 'checkin_manha' | 'checkin_noite' | null;
            /** true/false para rotina verificável; null = não verificável, não mostrar marcador. */
            feito: boolean | null;
        }>;
        pesagem_registrada: boolean;
        cintura_registrada: boolean;
        checkin_manha: boolean;
        checkin_noite: boolean;
        peso: { ultimo: number; data: string; media7: number | null; alvo?: number; falta: number | null } | null;
        dor_ontem: { manha?: number; noite?: number; ciatica: boolean; crise: boolean } | null;
        /** Registro mais recente do módulo Saúde — movimento das metas do pilar saúde. */
        ultimo_registro: string | null;
    };
    estrategia: {
        metas: ResumoMeta[];
        paradas: ResumoMeta[];
        servidas_hoje: number;
        /** Denominador honesto de "X de N metas recebem trabalho hoje". */
        total_geridas_por_acoes: number;
    };
    ontem: {
        concluidas: string[];
        diario: { data: string; texto: string; editado: boolean } | null;
    };
    perfil: {
        resumo?: string;
        rotinas: string[];
        gatilhos: string[];
        energia: string[];
    } | null;
    contadores: {
        ativas: number;
        hoje: number;
        herdadas: number;
        criticas: number;
        cobrar: number;
        sem_plano: number;
        pendencias: number;
        focos: number;
    };
    /** Gravado pela UI na primeira abertura do dia. */
    visto_em?: string;
}
