
import React, { useState, useEffect, useRef } from 'react';
import { db, functions, auth } from '@/firebase';
import { httpsCallable } from 'firebase/functions';
import { collection, onSnapshot, query, orderBy, where, addDoc, doc, updateDoc, setDoc, getDoc, getDocs, writeBatch, deleteDoc, limit, Timestamp, deleteField } from 'firebase/firestore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import MermaidBlock from './MermaidBlock';
import { formatDate, PoolItem } from '@/types';
import { ReportModal } from './ReportModal';
import { getRoutingIndex, toolsRegistry } from './toolRegistry';
import { isInternalAppHref, navigateWithinApp } from '../../utils/internalNavigation';
import { CollapsibleContainer } from '../ui/UIComponents';
import { useHermesVoiceStream } from '@/src/hooks/useHermesVoiceStream';

// URL do endpoint HTTP de upload (Node.js Functions)
const UPLOAD_ENDPOINT = 'https://us-central1-gestao-hermes.cloudfunctions.net/uploadFileForCopiloto';
const COPILOTO_CALLABLE_TIMEOUT_MS = 240000;
const COPILOTO_CLIENT_TIMEOUT_MESSAGE = 'O copiloto demorou demais para responder e a chamada foi encerrada no navegador. Tente dividir o pedido em partes menores ou pedir primeiro um levantamento dos itens pendentes.';
const COPILOTO_SUPPORTED_FILE_EXTENSIONS = [
    '.pdf',
    '.doc',
    '.docx',
    '.xls',
    '.xlsx',
    '.csv',
    '.txt',
    '.json',
    '.xml',
    '.eml',
    '.md',
    '.markdown',
    '.html',
    '.htm',
    '.pptx',
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
] as const;
const COPILOTO_FILE_ACCEPT = COPILOTO_SUPPORTED_FILE_EXTENSIONS.join(',');
const COPILOTO_SUPPORTED_FORMATS_LABEL = 'PDF, DOC/DOCX, XLS/XLSX, CSV, TXT, JSON, XML, EML, Markdown, HTML, PPTX e imagens';
const LARGE_PASTE_THRESHOLD = 1500;

const withClientTimeout = async <T,>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    try {
        return await Promise.race([
            promise,
            new Promise<T>((_, reject) => {
                timer = setTimeout(() => reject(new Error(message)), timeoutMs);
            })
        ]);
    } finally {
        if (timer) clearTimeout(timer);
    }
};

const getCopilotoErrorMessage = (err: any) => {
    const raw = err?.message || err?.details || String(err) || '';
    const code = String(err?.code || '').toLowerCase();

    if (
        code.includes('deadline-exceeded') ||
        /DEADLINE_EXCEEDED|Deadline expired|deadline|timed out|timeout/i.test(raw)
    ) {
        return 'O copiloto demorou demais para responder. Tente dividir o pedido em partes menores ou pedir primeiro um levantamento objetivo.';
    }

    if (code.includes('permission-denied')) {
        return 'O copiloto nao conseguiu acessar um dado necessario no Firestore por falta de permissao.';
    }

    if (/internal|500/i.test(raw)) {
        return 'O copiloto encontrou uma falha interna ao processar a resposta. Tente novamente com um pedido mais focado.';
    }

    return raw || 'Erro desconhecido ao consultar o copiloto.';
};

const isCopilotoFileSupported = (file: File) => {
    const fileName = file.name.toLowerCase();
    const isExtensionSupported = COPILOTO_SUPPORTED_FILE_EXTENSIONS.some((extension) => fileName.endsWith(extension));
    if (isExtensionSupported) return true;

    // Fallback para tipos MIME comuns de imagem (útil para colagem direta e blobs sem nome)
    const mimeSupported = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'].includes(file.type);
    return mimeSupported;
};

interface FormQuestion {
    tipo: 'texto_curto' | 'paragrafo' | 'multipla_escolha' | 'caixas_selecao' | 'lista_suspensa' | 'escala_linear';
    texto: string;
    opcoes?: string[];
    escala_min?: number;
    escala_max?: number;
    rotulo_min?: string;
    rotulo_max?: string;
    obrigatoria: boolean;
}

interface ProposedForm {
    titulo: string;
    descricao?: string;
    perguntas: FormQuestion[];
}

interface DiagnosisRequest {

    mode: 'repo' | 'snippet';
    sistemaId?: string;
    codeSnippet?: string;
    fileName?: string;
    descricaoProblema: string;
}

interface FieldChange {
    original: string;
    novo: string;
    novo_raw?: any;
}

interface PendingEdit {
    task_id: string;
    titulo: string;
    alteracoes: Record<string, FieldChange>;
    justificativa: string;
    snapshot_ts: string;
    status: 'pending' | 'completed' | 'invalidated' | 'cancelled' | 'error';
    errorMessage?: string;
}

interface BatchRescheduleItem {
    task_id: string;
    titulo: string;
    data_limite_original: string;
    horario_inicio_original: string | null;
    horario_fim_original: string | null;
    nova_data_limite: string;
    novo_horario_inicio: string | null;
    novo_horario_fim: string | null;
}

interface PendingBatchReschedule {
    items: BatchRescheduleItem[];
    justificativa: string;
    status: 'pending' | 'completed' | 'cancelled' | 'error';
    errorMessage?: string;
    created_at: string;
}

interface PendingMemoryConflict {
    memory_id: string;
    categoria_existente?: string;
    existing_text: string;
    proposed_text: string;
    similarity?: number;
    status?: 'conflict';
    status_ui?: 'pending' | 'resolved' | 'kept';
    decisao_final?: 'manter_existente' | 'substituir_pelo_novo';
    resolvedAt?: any;
}

interface DiagnosisBlock {
    arquivo: string;
    descricao: string;
    search: string;
    replace: string;
}

interface DiagnosisRecord {
    id: string;
    sistemaId?: string;
    nomeRepositorio?: string;
    descricaoProblema: string;
    diagnostico: string;
    arquivosAnalisados?: string[];
    blocosSR?: DiagnosisBlock[];
    alertaImpacto?: string;
    markdownContent?: string;
}

interface Message {
    id?: string;
    role: 'user' | 'assistant';
    content: string;
    subtype?: 'proactive_insight' | string;
    insightNivel?: 1 | 2 | 3;
    insightAlvo?: 'diario' | 'plano' | 'acoes';
    isArtifact?: boolean;
    toolInvocation?: { intent: string, tool_id: string, parametros: any };
    proposedPlan?: any[];
    proposedDiagnosis?: DiagnosisRequest;
    proposedForm?: ProposedForm;
    timestamp: any;
    type?: 'text' | 'plan_proposal';
    toolsUsed?: string[];
    pendingEdit?: PendingEdit;
    pendingBatchReschedule?: PendingBatchReschedule;
    pendingMemoryConflict?: PendingMemoryConflict;
    reportId?: string;
}

const TOOL_LABELS: Record<string, string> = {
    consultar_historico_acoes: 'Grafo de Execução',
    buscar_arquivos_acervo: 'Acervo de Documentos',
    obter_contexto_tela: 'Contexto da Tarefa',
    pesquisar_internet: 'Internet',
    ler_pagina_web: 'Leitura de Página',
    ler_documento_na_integra: 'Leitura de Documento',
    salvar_memoria_global: 'Memória Atualizada',
    salvar_pop_global: 'POP Atualizado',
    atualizar_personalidade: 'Personalidade Ajustada',
    resolver_conflito_procedimento: 'Resolução de Conflito',
    criar_acao_no_sistema: 'Criando Ação',
    agendar_lembrete_acao: 'Lembrete Agendado',
    editar_plano_acao: 'Ajustando Plano...',
    preparar_edicao_acao: 'Preparando Edição',
    preparar_reagendamento_em_lote: 'Planejando Reagendamento',
    gerar_relatorio: 'Gerando Relatório',
    registrar_no_diario: 'Registrado no Diário',
    buscar_e_analisar_email: 'Email Analisado',
    gerar_rascunho_formulario: 'Rascunho de Formulário',
    consultar_agenda: 'Agenda Consultada',
    encontrar_slot_livre: 'Slot Livre Encontrado',
    consultar_financas_v2: 'Dados Financeiros Consultados',
    registrar_item_financeiro_v2: 'Movimentação Financeira Registrada',
    buscar_contato: 'Busca de Contatos',
    preparar_vinculo_contatos: 'Vínculo de Pessoas',
    preparar_atualizacao_contato: 'Atualização de Contato',
    registrar_interacao_contato: 'Log de Interação',
};

const FIELD_LABELS: Record<string, string> = {
    titulo: 'Título',
    descricao: 'Descrição',
    data_limite: 'Data de Execução',
    prazo_final: 'Prazo Final',
    data_inicio: 'Data Início',
    horario_inicio: 'Horário Início',
    horario_fim: 'Horário Fim',
    status: 'Status',
    tags: 'Tags',
    area_tematica: 'Área Temática',
    tipo_acao: 'Tipo de Ação',
    notas: 'Notas',
    email_trigger: 'Gatilho de E-mail',
};

// Ferramentas de escrita/mutação — recebem estilo verde
const WRITE_TOOLS = new Set([
    'criar_acao_no_sistema',
    'agendar_lembrete_acao',
    'editar_plano_acao',
    'preparar_edicao_acao',
    'salvar_memoria_global',
    'salvar_pop_global',
    'atualizar_personalidade',
    'registrar_no_diario',
]);

// Ponto 3: exibição das ferramentas usadas, colapsada por padrão para não ocupar
// espaço no chat. Mostra um resumo de uma linha ("N ferramentas") que expande os
// chips detalhados ao clicar.
const ToolsUsedBadges: React.FC<{ tools: string[]; isDark?: boolean }> = ({ tools, isDark }) => {
    const [expanded, setExpanded] = React.useState(false);
    const unique = React.useMemo(
        () => [...new Set(tools)].filter(t => TOOL_LABELS[t]),
        [tools]
    );
    if (unique.length === 0) return null;

    return (
        <div className="mb-2">
            <button
                type="button"
                onClick={() => setExpanded(v => !v)}
                className={`inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-[0.18em] transition-colors ${isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-400 hover:text-slate-600'}`}
                title={expanded ? 'Recolher ferramentas' : 'Ver ferramentas usadas'}
            >
                <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                <span>{unique.length} {unique.length === 1 ? 'ferramenta' : 'ferramentas'}</span>
                <svg className={`w-2.5 h-2.5 shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
            </button>
            {expanded && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                    {unique.map(tool => {
                        const isWrite = WRITE_TOOLS.has(tool);
                        return (
                            <span
                                key={tool}
                                className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.08em] border ${isWrite
                                    ? isDark
                                        ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/20'
                                        : 'text-emerald-700 bg-emerald-50 border-[#e5e7eb] dark:border-white/10'
                                    : isDark
                                        ? 'text-slate-300 bg-slate-950 border-slate-700'
                                        : 'text-slate-500 bg-white/90 border-[#e5e7eb] dark:border-white/10'
                                    }`}
                            >
                                {isWrite ? (
                                    <svg className="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                                    </svg>
                                ) : (
                                    <svg className="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                )}
                                {TOOL_LABELS[tool]}
                            </span>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

const sanitizeDiagnosisFilePart = (value?: string) =>
    (value || 'diagnostico')
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, '_')
        .replace(/^_+|_+$/g, '')
        .slice(0, 40) || 'diagnostico';

const buildDiagnosisMarkdown = (diagnosis: DiagnosisRecord) => {
    if (diagnosis.markdownContent?.trim()) return diagnosis.markdownContent;

    const lines = [
        '# Hermes - Diagnostico de Codigo',
        diagnosis.nomeRepositorio ? `**Repositorio:** \`${diagnosis.nomeRepositorio}\`  ` : '',
        diagnosis.sistemaId ? `**Sistema:** \`${diagnosis.sistemaId}\`  ` : '',
        `**Problema:** ${diagnosis.descricaoProblema}`,
        '',
        '---',
        '',
        '## Diagnostico da Falha',
        '',
        diagnosis.diagnostico || '',
        '',
        '---',
        '',
        '## Arquivos Impactados',
        '',
        ...(diagnosis.arquivosAnalisados || []).map((file) => `- \`${file}\``),
        '',
        '---',
        '',
        '## Instrucoes de Refatoracao',
        '',
    ];

    (diagnosis.blocosSR || []).forEach((block, index) => {
        lines.push(
            `### Correcao ${index + 1}: ${block.descricao || 'Atualizacao'}`,
            '',
            `**Arquivo:** \`${block.arquivo || ''}\``,
            '',
            '<<<<<<< SEARCH',
            block.search || '',
            '=======',
            block.replace || '',
            '>>>>>>> REPLACE',
            '',
            '---',
            ''
        );
    });

    if (diagnosis.alertaImpacto) {
        lines.push('## Alerta de Impacto', '', diagnosis.alertaImpacto, '', '---', '');
    }

    return lines.join('\n').trim();
};

const buildDiagnosisAiPackage = (diagnosis: DiagnosisRecord) => {
    const markdown = buildDiagnosisMarkdown(diagnosis);
    return [
        '# Pacote de Aplicacao para IA',
        '',
        'Aplique as alteracoes abaixo diretamente no codigo.',
        'Priorize os blocos SEARCH/REPLACE como fonte de verdade.',
        'Se um bloco nao casar exatamente, localize o trecho equivalente no mesmo arquivo e adapte com o menor diff possivel.',
        'Nao reescreva arquivos inteiros sem necessidade.',
        '',
        '## Metadados',
        diagnosis.nomeRepositorio ? `- Repositorio: ${diagnosis.nomeRepositorio}` : null,
        diagnosis.sistemaId ? `- Sistema: ${diagnosis.sistemaId}` : null,
        `- Problema: ${diagnosis.descricaoProblema}`,
        '',
        '## Conteudo do Diagnostico',
        '',
        markdown,
        '',
        '## Instrucao Sugerida para a IA',
        '',
        'Aplique exatamente os blocos SEARCH/REPLACE acima, preserve a indentacao,',
        'faça apenas as mudancas necessarias e ao final resuma os arquivos alterados.',
    ]
        .filter(Boolean)
        .join('\n');
};

const downloadDiagnosisContent = (filename: string, content: string, mimeType = 'text/markdown;charset=utf-8') => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
};

interface Session {
    id: string;
    title: string;
    createdAt: any;
    lastMessageAt: any;
    taskId?: string;
    systemId?: string;
    isTemporary?: boolean;
    copilotStatus?: string;
}

interface HermesCopilotoDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    taskId?: string;
    systemId?: string;
    isDark?: boolean;
    variant?: 'drawer' | 'embedded';
    userId: string;
    onOpenTask?: (taskId: string) => void;
    onOpenTool?: (tool: string, id: string) => void;
    activeDocument?: { url: string; nome: string; tipo: 'link' | 'file' | 'image'; driveFileId?: string } | null;
    isTemporary?: boolean;
    sessionId?: string | null;
    autoStartMic?: boolean;
    copilotMode?: 'default' | 'finance' | 'saude';
    /** Sinaliza ao container que um turno do copiloto começou/terminou,
     *  para que mudanças subsequentes no plano/diário não disparem insight duplicado. */
    onCopilotActivity?: (phase: 'started' | 'completed' | 'failed' | 'cancelled') => void;
}

type UploadPhase = 'idle' | 'uploading' | 'processing';
const MOBILE_BREAKPOINT = 768;

export const HermesCopilotoDrawer: React.FC<HermesCopilotoDrawerProps> = ({
    isOpen, onClose, taskId, systemId, isDark = false, variant = 'drawer', userId, onOpenTask, onOpenTool, activeDocument, isTemporary, sessionId, autoStartMic = false, copilotMode = 'default' as 'default' | 'finance' | 'saude', onCopilotActivity
}) => {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [messages, setMessages] = useState<Message[]>([]);
    const [copiedMessageKey, setCopiedMessageKey] = useState<string | null>(null);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    const [sessionPendingDeleteId, setSessionPendingDeleteId] = useState<string | null>(null);
    const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
    const [confirmDeleteMessageId, setConfirmDeleteMessageId] = useState<string | null>(null);
    const chatEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const toolMenuRef = useRef<HTMLDivElement>(null);
    const isFinancialCopilot = copilotMode === 'finance';
    const isHealthCopilot = copilotMode === 'saude';

    // ── Estado do modal de relatório ─────────────────────────────────────────
    const [reportModalOpen, setReportModalOpen] = useState(false);
    const [activeReport, setActiveReport] = useState<{ id: string; titulo: string; markdown: string } | null>(null);
    const [isLoadingReport, setIsLoadingReport] = useState(false);
    const [diagnosisModalOpen, setDiagnosisModalOpen] = useState(false);
    const [activeDiagnosis, setActiveDiagnosis] = useState<DiagnosisRecord | null>(null);
    const [isLoadingDiagnosis, setIsLoadingDiagnosis] = useState(false);
    const [diagnosisCopyDone, setDiagnosisCopyDone] = useState(false);

    const handleOpenReport = async (reportId: string) => {
        setIsLoadingReport(true);
        setReportModalOpen(true);
        try {
            const reportDoc = await getDoc(doc(db, 'relatorios', reportId));
            if (reportDoc.exists()) {
                const data = reportDoc.data();
                setActiveReport({ id: reportId, titulo: data.titulo, markdown: data.markdown });
            }
        } catch (err) {
            console.error('[ReportModal] Erro ao carregar relatório:', err);
        } finally {
            setIsLoadingReport(false);
        }
    };

    const [isFocused, setIsFocused] = useState(false);
    const [showToolMenu, setShowToolMenu] = useState(false);
    const [popsList, setPopsList] = useState<{ id: string; titulo: string; gatilhos: string[] }[]>([]);

    // Estado de anexo
    const [attachedFile, setAttachedFile] = useState<File | null>(null);
    const [pastedContext, setPastedContext] = useState<{ text: string; name: string } | null>(null);
    const [uploadPhase, setUploadPhase] = useState<UploadPhase>('idle');
    // Controla a largura da barra de progresso via CSS transition
    const [progressWidth, setProgressWidth] = useState<number>(0);
    const progressTransition = useRef<string>('none');
    // Erro inline no footer (erros antes do Firestore não ficam visíveis no chat)
    const [footerError, setFooterError] = useState<string | null>(null);
    // Estado de transcrição de áudio colado
    const [isTranscribing, setIsTranscribing] = useState(false);
    const [isDragActive, setIsDragActive] = useState(false);
    const dragCounterRef = useRef(0);
    const abortControllerRef = useRef<AbortController | null>(null);
    const isCancelledRef = useRef(false);

    // Estado para rastrear qual diagnóstico está em processamento
    const [diagnosingId, setDiagnosingId] = useState<string | null>(null);

    const [creatingFormId, setCreatingFormId] = useState<string | null>(null);

    const [suggestedPrompt, setSuggestedPrompt] = useState<string | null>(null);
    const strategicSuggestions = [
        "Analise riscos e pontos cegos desta operação.",
        "Sugira o próximo passo lógico para esta tarefa.",
        "Como otimizar os recursos alocados aqui?",
        "Quais conflitos entre o manual e a execução você detecta?",
        "Gere um resumo estratégico dos últimos avanços.",
        "Crie um checklist de validação para esta entrega."
    ];

    useEffect(() => {
        const generateContextualSuggestion = async () => {
            if (messages.length > 0 || isLoading || !isOpen) return;
            
            try {
                let contextText = "Consultoria estratégica geral.";
                if (taskId) {
                    // 1. Dados da Ação Principal
                    const taskDoc = await getDoc(doc(db, 'tarefas', taskId));
                    const taskData = taskDoc.exists() ? taskDoc.data() : {};
                    
                    // 2. Plano de Ação (Sub-tarefas)
                    const planItemsArray = taskData.plano_acao || [];
                    const planItems = planItemsArray.slice(0, 10).map((d: any) => `- [${d.completed ? 'concluído' : 'pendente'}] ${d.text}`).join('\n');
                    
                    // 3. Diário de Bordo (Histórico recente)
                    const diaryLogsArray = taskData.acompanhamento || [];
                    const diaryLogs = diaryLogsArray.slice(-5).map((d: any) => `- ${d.nota}`).reverse().join('\n');

                    contextText = `
                        TAREFA: "${taskData.titulo || 'Sem título'}"
                        DATA AGENDADA PARA TRABALHO: ${taskData.data_limite || 'Não agendado'}
                        PRAZO FINAL REAL: ${taskData.prazo_final || 'Não há prazo final estrito'}
                        
                        O QUE ESTÁ PLANEJADO (PLANO DE AÇÃO):
                        ${planItems || 'Nenhum item definido no plano.'}
                        
                        O QUE JÁ FOI FEITO (DIÁRIO DE BORDO):
                        ${diaryLogs || 'Nenhum registro no diário ainda.'}
                    `;
                }

                const prompt = `Você é o Copiloto Hermes (uma IA assistente). Analise o progresso desta tarefa.
                
                DADOS DA OPERAÇÃO:
                ${contextText}
                
                SUA MISSÃO:
                O usuário vai clicar em um botão para lhe enviar um prompt. Você deve escrever ESSE PROMPT que o usuário vai te enviar.
                Este prompt deve ser um pedido de ajuda acionável que uma IA possa de fato realizar (ex: gerar rascunhos, criar checklists, analisar dados, listar riscos, pesquisar, estruturar ideias).
                Se a tarefa depender de ação física ou externa do usuário, o prompt deve pedir para você prepará-lo, guiá-lo ou revisar o que ele precisa fazer.
                Use os dados do plano ou diário (se houver) para deixar o prompt 100% contextualizado e focado no próximo passo real da tarefa.
                
                Regras:
                - Máximo 18 palavras.
                - Escrito na 1ª pessoa do singular (o usuário falando com a IA, ex: "Crie um roteiro para...", "Me ajude a estruturar...", "Analise os riscos de...").
                - Tom direto, técnico e focado em execução.
                - Responda apenas o texto do prompt, sem aspas.`;

                const fn = httpsCallable(functions, 'askTaskAssistant');
                const res = await fn({ 
                    prompt, 
                    area_tematica: systemId || 'GERAL',
                    taskId: taskId || undefined
                });
                
                const result = (res.data as any).result || '';
                if (result) {
                    setSuggestedPrompt(result.replace(/^["'“”]|["'“”]$/g, '').trim());
                } else {
                    setSuggestedPrompt("Analise o próximo passo do plano de ação.");
                }
            } catch (err) {
                console.error("Erro ao gerar sugestão profunda:", err);
                setSuggestedPrompt("Analise riscos e pontos cegos desta operação.");
            }
        };

        generateContextualSuggestion();
    }, [messages.length, isLoading, taskId, isOpen]);

    const handleFirestoreListenerError = (error: any) => {
        console.error('[Copiloto] Erro no listener do Firestore:', error);
        if (error?.code === 'permission-denied') {
            setFooterError('O copiloto não conseguiu acessar o histórico no Firestore por falta de permissão.');
            return;
        }
        setFooterError(error?.message || 'Erro ao carregar dados do copiloto.');
    };

    const touchCopilotoSession = async (sessionId: string, updates: Partial<Session> = {}) => {
        const sessionRef = doc(db, 'sessoes_copiloto', sessionId);
        const snap = await getDoc(sessionRef).catch(() => null);
        const fallback = snap?.exists()
            ? {}
            : {
                userId,
                title: isFinancialCopilot ? 'Copiloto Financeiro' : isHealthCopilot ? 'Copiloto de Saude' : 'Nova Conversa',
                createdAt: Timestamp.now(),
                taskId: taskId || null,
                systemId: systemId || null,
                copilotMode
            };

        await setDoc(sessionRef, {
            ...fallback,
            ...updates,
            lastMessageAt: updates.lastMessageAt || Timestamp.now()
        }, { merge: true });
    };

    const handleConfirmForm = async (form: ProposedForm, messageId?: string) => {
        if (!currentSessionId || creatingFormId) return;
        if (messageId) setCreatingFormId(messageId);

        try {
            const criarFormulario = httpsCallable(functions, 'criar_formulario_google', { timeout: 300000 });
            const result = await criarFormulario({
                sessionId: currentSessionId,
                form: form,
            });
            const data = result.data as any;

            // Sucesso - Injeta a mensagem no chat localmente para evitar chamar o LLM novamente (Zero-LLM Flow)
            if (data.responderUri) {
                await addDoc(collection(db, 'sessoes_copiloto', currentSessionId, 'mensagens'), {
                    role: 'assistant',
                    content: `✅ Formulário criado com sucesso! Acesse aqui: [URL do Formulário](${data.responderUri})`,
                    timestamp: Timestamp.now()
                });

                await touchCopilotoSession(currentSessionId, {
                    lastMessageAt: Timestamp.now()
                });
            }
        } catch (err: any) {
            setFooterError('Erro ao criar formulário: ' + (err?.message || 'Tente novamente.'));
        } finally {
            setCreatingFormId(null);
        }
    };


    // ── Mention (@) popup ─────────────────────────────────────────────────────
    const [taskPoolItems, setTaskPoolItems] = useState<PoolItem[]>([]);
    const [mention, setMention] = useState<{
        visible: boolean;
        query: string;
        atIndex: number;
        filtered: PoolItem[];
        selectedIndex: number;
    }>({ visible: false, query: '', atIndex: -1, filtered: [], selectedIndex: 0 });

    // ── Gravação de áudio por microfone ───────────────────────────────────────
    const [isRecording, setIsRecording] = useState(false);
    const [isProcessingMic, setIsProcessingMic] = useState(false);

    // ── Conversa por voz em tempo real (Gemini Live via hermes-voice-bridge) ──
    const [voiceStreamStatusMessage, setVoiceStreamStatusMessage] = useState('');
    const currentSessionIdRef = useRef<string | null>(null);
    currentSessionIdRef.current = currentSessionId;

    const voiceStream = useHermesVoiceStream({
        taskId,
        onUserTranscript: (text) => {
            const sId = currentSessionIdRef.current;
            if (!sId) return;
            addDoc(collection(db, 'sessoes_copiloto', sId, 'mensagens'), {
                role: 'user',
                content: text,
                timestamp: Timestamp.now(),
            }).catch(() => {});
        },
        onAssistantTranscript: (text) => {
            const sId = currentSessionIdRef.current;
            if (!sId) return;
            addDoc(collection(db, 'sessoes_copiloto', sId, 'mensagens'), {
                role: 'assistant',
                content: text,
                timestamp: Timestamp.now(),
            }).catch(() => {});
        },
        onStatus: (message) => setVoiceStreamStatusMessage(message),
        onError: (message) => { setFooterError(message); setVoiceStreamStatusMessage(''); },
    });

    const isBlocked = isLoading || uploadPhase !== 'idle' || isTranscribing || isProcessingMic;
    // Status efêmero gravado pelo backend no doc da sessão durante o processamento
    const copilotStatus = sessions.find(s => s.id === currentSessionId)?.copilotStatus;
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);
    const micStreamRef = useRef<MediaStream | null>(null);

    // ── Redimensionamento do drawer ───────────────────────────────────────────
    const DRAWER_MIN_WIDTH = 320;
    const [drawerWidth, setDrawerWidth] = useState(675);
    const [isMobileViewport, setIsMobileViewport] = useState(() => window.innerWidth < MOBILE_BREAKPOINT);
    const isDragging = useRef(false);
    const dragStartX = useRef(0);
    const dragStartWidth = useRef(0);

    const handleResizeMouseDown = (e: React.MouseEvent) => {
        if (window.innerWidth < MOBILE_BREAKPOINT) {
            return;
        }
        e.preventDefault();
        isDragging.current = true;
        dragStartX.current = e.clientX;
        dragStartWidth.current = drawerWidth;
        document.body.style.cursor = 'ew-resize';
        document.body.style.userSelect = 'none';

        const onMouseMove = (ev: MouseEvent) => {
            if (!isDragging.current) return;
            // arrastar para a esquerda aumenta a largura (drawer está à direita)
            const delta = dragStartX.current - ev.clientX;
            const newWidth = Math.min(
                Math.max(dragStartWidth.current + delta, DRAWER_MIN_WIDTH),
                Math.round(window.innerWidth * 0.5)
            );
            setDrawerWidth(newWidth);
        };

        const onMouseUp = () => {
            isDragging.current = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
    };

    useEffect(() => {
        const syncViewportState = () => {
            const mobile = window.innerWidth < MOBILE_BREAKPOINT;
            setIsMobileViewport(mobile);

            if (!mobile) {
                setDrawerWidth((currentWidth) => Math.min(
                    Math.max(currentWidth, DRAWER_MIN_WIDTH),
                    Math.round(window.innerWidth * 0.5)
                ));
            }
        };

        syncViewportState();
        window.addEventListener('resize', syncViewportState);
        return () => window.removeEventListener('resize', syncViewportState);
    }, []);

    // Auto-resize textarea logic
    useEffect(() => {
        const handleResize = () => {
            if (textareaRef.current) {
                textareaRef.current.style.height = 'auto';
                const minH = 36;
                const maxH = 176;
                const scrollH = textareaRef.current.scrollHeight;
                textareaRef.current.style.height = `${Math.max(minH, Math.min(scrollH, maxH))}px`;
                textareaRef.current.style.overflowY = scrollH > maxH ? 'auto' : 'hidden';
            }
        };

        handleResize();

        const handleClickOutside = (e: MouseEvent) => {
            if (textareaRef.current && !textareaRef.current.contains(e.target as Node)) {
                setIsFocused(false);
            }
            if (toolMenuRef.current && !toolMenuRef.current.contains(e.target as Node)) {
                setShowToolMenu(false);
            }
        };

        if (isFocused) {
            window.addEventListener('mousedown', handleClickOutside);
        }

        return () => window.removeEventListener('mousedown', handleClickOutside);
    }, [input, isFocused]);

    const insertToolShortcut = (tag: string) => {
        setInput(prev => {
            const trimmedStart = prev.trimStart();
            if (trimmedStart.startsWith(tag)) return prev;
            return prev.trim().length > 0 ? `${tag} ${prev}` : `${tag} `;
        });
        setShowToolMenu(false);
        setIsFocused(true);
        setTimeout(() => textareaRef.current?.focus(), 0);
    };

    useEffect(() => {
        if (!isOpen) return;
        const q = collection(db, 'pops_diretrizes');
        return onSnapshot(
            q,
            (snapshot) => {
                const data = snapshot.docs.map((docItem) => ({ id: docItem.id, ...docItem.data() }) as { id: string; titulo: string; gatilhos: string[] });
                setPopsList(data);
            },
            (error) => console.error('Erro ao buscar POPs no HermesCopilotoDrawer:', error),
        );
    }, [isOpen]);

    const insertPopShortcut = (pop: { titulo: string; gatilhos?: string[] }) => {
        const gatilhoPrincipal = (pop.gatilhos && pop.gatilhos.length > 0 && pop.gatilhos[0]) ? pop.gatilhos[0] : pop.titulo;
        setInput(prev => {
            const trimmedStart = prev.trimStart();
            if (trimmedStart.toLowerCase().startsWith(gatilhoPrincipal.toLowerCase())) return prev;
            return prev.trim().length > 0 ? `${gatilhoPrincipal} ${prev}` : `${gatilhoPrincipal} `;
        });
        setShowToolMenu(false);
        setIsFocused(true);
        setTimeout(() => textareaRef.current?.focus(), 0);
    };

    // Load pool_dados from active task for @ mentions
    useEffect(() => {
        if (!taskId) { setTaskPoolItems([]); return; }
        return onSnapshot(
            doc(db, 'tarefas', taskId),
            (snap) => {
                if (snap.exists()) {
                    const items = ((snap.data().pool_dados as PoolItem[]) || [])
                        .filter(item => item.tipo !== 'telefone');
                    setTaskPoolItems(items);
                }
            },
            handleFirestoreListenerError
        );
    }, [taskId]);

    // Load Sessions
    useEffect(() => {
        if (!userId) return;
        const q = query(
            collection(db, 'sessoes_copiloto'),
            where('userId', '==', userId),
            orderBy('lastMessageAt', 'desc'),
            limit(20)
        );

        return onSnapshot(
            q,
            (snapshot) => {
                const sessList = snapshot.docs.map(doc => ({
                    id: doc.id,
                    ...doc.data()
                })) as Session[];
                setSessions(sessList);
            },
            handleFirestoreListenerError
        );
    }, [userId]);

    // Auto-select session for the current task when drawer opens
    useEffect(() => {
        if (sessionId) {
            setCurrentSessionId(sessionId);
            return;
        }

        if (isOpen && taskId && sessions.length > 0) {
            // Only auto-select if no session is selected or if the current one doesn't match the taskId
            // and we haven't manually switched to another one in this "open" session.
            const latestTaskSession = sessions.find(s => s.taskId === taskId && !s.isTemporary);
            if (latestTaskSession && !currentSessionId) {
                setCurrentSessionId(latestTaskSession.id);
            }
        }
    }, [isOpen, taskId, sessions, currentSessionId, sessionId]);

    // Auto-start mic when opened via audio shortcut
    useEffect(() => {
        if (isOpen && autoStartMic) {
            const timer = setTimeout(() => startRecording(), 400);
            return () => clearTimeout(timer);
        }
    }, [isOpen, autoStartMic]);

    // Encerra a sessao de voz ao vivo se o drawer fechar (drawer costuma so
    // ficar oculto, nao desmontar, entao o cleanup de unmount nao cobre isso).
    useEffect(() => {
        if (!isOpen) voiceStream.stop();
    }, [isOpen]);

    // Load Messages for current session
    useEffect(() => {
        if (!currentSessionId) {
            setMessages([]);
            return;
        }

        const q = query(
            collection(db, 'sessoes_copiloto', currentSessionId, 'mensagens'),
            orderBy('timestamp', 'asc')
        );

        return onSnapshot(
            q,
            (snapshot) => {
                const msgList = snapshot.docs.map(d => ({ id: d.id, ...d.data() })) as Message[];
                setMessages(msgList);
            },
            handleFirestoreListenerError
        );
    }, [currentSessionId]);

    useEffect(() => {
        if (sessionPendingDeleteId && !sessions.some((session) => session.id === sessionPendingDeleteId)) {
            setSessionPendingDeleteId(null);
        }
    }, [sessions, sessionPendingDeleteId]);

    // Scroll to bottom
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // ── Helpers de progresso ──────────────────────────────────────────────────
    const startProgressAnimation = () => {
        // Reset sem transição num frame, depois anima 0 → 90% em 15 s
        progressTransition.current = 'none';
        setProgressWidth(0);
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                progressTransition.current = 'width 15s linear';
                setProgressWidth(90);
            });
        });
    };

    // Caminho de SUCESSO: salta para 100% e limpa suavemente.
    // Só deve ser chamado dentro do bloco try, após resposta confirmada.
    const completeProgress = (): Promise<void> => {
        return new Promise((resolve) => {
            progressTransition.current = 'width 0.3s ease';
            setProgressWidth(100);
            setTimeout(() => {
                progressTransition.current = 'none';
                setProgressWidth(0);
                resolve();
            }, 350);
        });
    };

    // Caminho de ERRO: zera a barra instantaneamente, sem animação de conclusão.
    // Evita que o usuário veja "100% concluído" enquanto um banner de erro aparece.
    const abortProgress = () => {
        progressTransition.current = 'none';
        setProgressWidth(0);
    };

    const handleAcceptProposedPlan = async (messageId: string, proposedPlan: any[]) => {
        if (!taskId || !currentSessionId) return;

        try {
            // Enforce unique IDs and sanitize the proposed plan items
            const seenIds = new Set<string>();
            const appliedPlan = proposedPlan.map((item, idx) => {
                let newId = item.id;
                if (!newId || String(newId).includes('uuid') || seenIds.has(newId)) {
                    newId = `plan-${Date.now()}-${idx}-${Math.random().toString(36).substring(2, 7)}`;
                }
                seenIds.add(newId);
                return {
                    id: newId,
                    text: item.text || '',
                    completed: !!item.completed
                };
            });

            // 1. Fetch current task to update history and plano_acao
            const taskDocRef = doc(db, 'tarefas', taskId);
            const taskSnap = await getDoc(taskDocRef);
            if (taskSnap.exists()) {
                const taskData = taskSnap.data();
                const currentPlan = taskData.plano_acao || [];
                const existingHistory = taskData.plano_acao_historico || [];
                const updatedHistory = currentPlan.length > 0
                    ? [...existingHistory.slice(-4), { data: new Date().toISOString(), items: currentPlan }]
                    : existingHistory;

                const allCompleted = appliedPlan.length > 0 && appliedPlan.every(i => i.completed);

                await updateDoc(taskDocRef, {
                    plano_acao: appliedPlan,
                    plano_acao_historico: updatedHistory,
                    ...(allCompleted && { status: 'concluído' })
                });
            }

            // 2. Remove proposedPlan card from the message in sessoes_copiloto/{sessionId}/mensagens/{messageId}
            const msgDocRef = doc(db, 'sessoes_copiloto', currentSessionId, 'mensagens', messageId);
            await updateDoc(msgDocRef, {
                proposedPlan: deleteField()
            });

            // 3. Add success message entry in sessoes_copiloto
            await addDoc(collection(db, 'sessoes_copiloto', currentSessionId, 'mensagens'), {
                role: 'assistant',
                content: '✅ Plano de ação atualizado com sucesso!',
                timestamp: Timestamp.now()
            });

        } catch (err) {
            console.error('[CopilotoDrawer] Erro ao aceitar plano:', err);
        }
    };

    const handleRejectProposedPlan = async (messageId: string) => {
        if (!currentSessionId) return;

        try {
            // 1. Remove proposedPlan card from the message
            const msgDocRef = doc(db, 'sessoes_copiloto', currentSessionId, 'mensagens', messageId);
            await updateDoc(msgDocRef, {
                proposedPlan: deleteField()
            });

            // 2. Add rejection message entry in sessoes_copiloto
            await addDoc(collection(db, 'sessoes_copiloto', currentSessionId, 'mensagens'), {
                role: 'assistant',
                content: '❌ Proposta de plano de ação recusada.',
                timestamp: Timestamp.now()
            });

        } catch (err) {
            console.error('[CopilotoDrawer] Erro ao recusar plano:', err);
        }
    };

    // ── Seleção de arquivo ────────────────────────────────────────────────────
    const attachFileToCopiloto = React.useCallback((file: File | null, source: 'input' | 'drop' = 'input') => {
        if (!file) {
            setAttachedFile(null);
            return;
        }

        if (!isCopilotoFileSupported(file)) {
            setAttachedFile(null);
            setFooterError(`Formato ainda não suportado no copiloto. Use ${COPILOTO_SUPPORTED_FORMATS_LABEL}.`);
            return;
        }

        setFooterError(null);
        setAttachedFile(file);
        if (source === 'drop') {
            setShowToolMenu(false);
        }
    }, []);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0] ?? null;
        attachFileToCopiloto(file, 'input');
        // Reset o input para permitir re-selecionar o mesmo arquivo
        e.target.value = '';
    };

    const handleRemoveFile = () => {
        setAttachedFile(null);
        setPastedContext(null);
    };

    const handleComposerDragEnter = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
        if (!Array.from(e.dataTransfer.types).includes('Files') || isBlocked) return;
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current += 1;
        setIsDragActive(true);
    }, [isBlocked]);

    const handleComposerDragOver = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
        if (!Array.from(e.dataTransfer.types).includes('Files') || isBlocked) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'copy';
        setIsDragActive(true);
    }, [isBlocked]);

    const handleComposerDragLeave = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
        if (!Array.from(e.dataTransfer.types).includes('Files')) return;
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
        if (dragCounterRef.current === 0) {
            setIsDragActive(false);
        }
    }, []);

    const handleComposerDrop = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
        if (!Array.from(e.dataTransfer.types).includes('Files') || isBlocked) return;
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current = 0;
        setIsDragActive(false);

        const droppedFiles = Array.from(e.dataTransfer.files || []);
        if (droppedFiles.length === 0) return;
        if (droppedFiles.length > 1) {
            setFooterError(`O copiloto aceita um arquivo por vez. Mantive apenas "${droppedFiles[0].name}".`);
        }
        attachFileToCopiloto(droppedFiles[0], 'drop');
    }, [attachFileToCopiloto, isBlocked]);

    const handleDeleteSession = async (sessionId: string) => {
        if (deletingSessionId) return;
        if (sessionPendingDeleteId !== sessionId) {
            setSessionPendingDeleteId(sessionId);
            return;
        }

        setDeletingSessionId(sessionId);
        setSessionPendingDeleteId(null);
        try {
            const messagesRef = collection(db, 'sessoes_copiloto', sessionId, 'mensagens');
            const messagesSnapshot = await getDocs(messagesRef);
            const batch = writeBatch(db);
            messagesSnapshot.docs.forEach((messageDoc) => {
                batch.delete(messageDoc.ref);
            });
            if (!messagesSnapshot.empty) {
                await batch.commit();
            }

            await deleteDoc(doc(db, 'sessoes_copiloto', sessionId));

            if (currentSessionId === sessionId) {
                const nextSession = sessions.find((session) => session.id !== sessionId);
                setCurrentSessionId(nextSession?.id ?? null);
            }
        } catch (err) {
            console.error('[Copiloto] Erro ao excluir sessão:', err);
            setFooterError('Erro ao excluir sessão do histórico. Tente novamente.');
        } finally {
            setDeletingSessionId(null);
        }
    };

    const handleOpenDiagnosis = async (diagnosisId: string) => {
        setIsLoadingDiagnosis(true);
        setDiagnosisModalOpen(true);
        try {
            const diagnosisDoc = await getDoc(doc(db, 'diagnosticos_codigo', diagnosisId));
            if (diagnosisDoc.exists()) {
                const data = diagnosisDoc.data() as Omit<DiagnosisRecord, 'id'>;
                setActiveDiagnosis({ id: diagnosisId, ...data });
            } else {
                setActiveDiagnosis(null);
                setFooterError('Diagnóstico não encontrado.');
            }
        } catch (err) {
            console.error('[DiagnosisModal] Erro ao carregar diagnóstico:', err);
            setActiveDiagnosis(null);
            setFooterError('Erro ao carregar diagnóstico.');
        } finally {
            setIsLoadingDiagnosis(false);
        }
    };

    const handleDownloadDiagnosisMarkdown = (diagnosis: DiagnosisRecord) => {
        const baseName = `hermes_diagnostico_${sanitizeDiagnosisFilePart(diagnosis.sistemaId || diagnosis.nomeRepositorio)}_${diagnosis.id.slice(0, 6)}`;
        downloadDiagnosisContent(`${baseName}.md`, buildDiagnosisMarkdown(diagnosis));
    };

    const handleDownloadDiagnosisAiPackage = (diagnosis: DiagnosisRecord) => {
        const baseName = `hermes_apply_${sanitizeDiagnosisFilePart(diagnosis.sistemaId || diagnosis.nomeRepositorio)}_${diagnosis.id.slice(0, 6)}`;
        downloadDiagnosisContent(`${baseName}.md`, buildDiagnosisAiPackage(diagnosis));
    };

    const handleCopyDiagnosisAiPackage = async (diagnosis: DiagnosisRecord) => {
        const content = buildDiagnosisAiPackage(diagnosis);
        try {
            await navigator.clipboard.writeText(content);
        } catch {
            const el = document.createElement('textarea');
            el.value = content;
            document.body.appendChild(el);
            el.select();
            document.execCommand('copy');
            document.body.removeChild(el);
        }
        setDiagnosisCopyDone(true);
        window.setTimeout(() => setDiagnosisCopyDone(false), 2000);
    };

    const handleCopyChatMessage = (messageKey: string, content: string) => {
        navigator.clipboard.writeText(content);
        setCopiedMessageKey(messageKey);
        setTimeout(() => setCopiedMessageKey(null), 2000);
    };

    const handleDeleteMessage = async (messageId?: string) => {
        if (!currentSessionId || !messageId) return;

        // Se ainda não clicou uma vez, entra no estado de confirmação
        if (confirmDeleteMessageId !== messageId) {
            setConfirmDeleteMessageId(messageId);
            // Reset automático após 3 segundos se não confirmar
            setTimeout(() => {
                setConfirmDeleteMessageId(current => current === messageId ? null : current);
            }, 3000);
            return;
        }

        try {
            await deleteDoc(doc(db, 'sessoes_copiloto', currentSessionId, 'mensagens', messageId));
            setConfirmDeleteMessageId(null);
        } catch (err) {
            console.error('[Copiloto] Erro ao excluir mensagem:', err);
            setFooterError('Erro ao excluir mensagem do histórico.');
        }
    };

    const formatMessageTimestamp = (timestamp: any) => {
        if (!timestamp) return '';

        let date: Date | null = null;
        if (timestamp instanceof Date) {
            date = timestamp;
        } else if (typeof timestamp?.toDate === 'function') {
            date = timestamp.toDate();
        } else if (typeof timestamp?.seconds === 'number') {
            date = new Date(timestamp.seconds * 1000);
        } else if (typeof timestamp === 'string' || typeof timestamp === 'number') {
            const parsed = new Date(timestamp);
            if (!Number.isNaN(parsed.getTime())) date = parsed;
        }

        if (!date || Number.isNaN(date.getTime())) return '';

        return new Intl.DateTimeFormat('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
        }).format(date);
    };

    // ── Quick replies (botões de confirmação de draft) ────────────────────────
    const handleQuickReply = (text: string) => {
        if (isLoading) return;
        if (!currentSessionId) {
            handleCreateSession(text);
        } else {
            sendMessage(text);
        }
    };

    // Detecta o tipo de draft pendente numa mensagem do assistente.
    // Só retorna não-nulo para o ÚLTIMO assistente — depois que o usuário
    // responder, o índice muda e os botões somem automaticamente.
    const handleConfirmDiagnosis = async (diagnosis: DiagnosisRequest, messageId?: string) => {
        if (!currentSessionId || diagnosingId) return;
        if (messageId) setDiagnosingId(messageId);

        try {
            const sanitize = (v?: string | null) => {
                const s = v?.trim() || '';
                return (s === 'None' || s === 'null' || s === 'undefined') ? '' : s;
            };
            let resolvedSystemId = sanitize(diagnosis.sistemaId) || sanitize(systemId) || '';
            if (diagnosis.mode === 'repo' && !resolvedSystemId && taskId) {
                try {
                    const taskSnap = await getDoc(doc(db, 'tarefas', taskId));
                    const taskSystemId = taskSnap.exists() ? String(taskSnap.data()?.sistema_id || '').trim() : '';
                    if (taskSystemId) resolvedSystemId = taskSystemId;
                } catch (lookupErr) {
                    console.warn('[HermesCopiloto] Falha ao resolver sistemaId da tarefa para diagnostico:', lookupErr);
                }
            }
            if (diagnosis.mode === 'repo' && !resolvedSystemId) {
                setFooterError('Sistema não identificado. Diga ao Copiloto o nome exato do sistema (ex: "use o sistema sispnaes") para ele encontrar o ID no catálogo.');
                return;
            }
            const diagnosticarCodigo = httpsCallable(functions, 'diagnosticar_codigo', { timeout: 300000 });
            await diagnosticarCodigo({
                sessionId: currentSessionId,
                mode: diagnosis.mode,
                descricaoProblema: diagnosis.descricaoProblema,
                taskId: taskId ?? null,
                // repo mode — usa sistemaId do diagnóstico ou, como fallback, o systemId
                // recebido via props do drawer (evita erro "sistemaId é obrigatório")
                ...(diagnosis.mode === 'repo' && {
                    sistemaId: resolvedSystemId,
                }),
                // snippet mode
                ...(diagnosis.mode === 'snippet' && {
                    codeSnippet: diagnosis.codeSnippet,
                    fileName: diagnosis.fileName ?? 'snippet',
                }),
            });
        } catch (err: any) {
            setFooterError('Erro ao iniciar diagnóstico: ' + (err?.message || 'Tente novamente.'));
        } finally {
            setDiagnosingId(null);
        }
    };

    const getDraftType = (content: string, msgIndex: number): 'action' | 'plan' | null => {
        if (isLoading) return null;
        const lastAsstIdx = messages.reduce((last, m, i) => m.role === 'assistant' ? i : last, -1);
        if (msgIndex !== lastAsstIdx) return null;
        if (/confirma a cria[çc][aã]o desta a[çc][aã]o/i.test(content)) return 'action';
        if (/confirma a atualiza[çc][aã]o do plano/i.test(content)) return 'plan';
        return null;
    };

    // Estado para rastrear qual card de edição está em processamento
    const [loadingEditId, setLoadingEditId] = useState<string | null>(null);
    const [loadingBatchRescheduleId, setLoadingBatchRescheduleId] = useState<string | null>(null);
    const [loadingMemoryConflictId, setLoadingMemoryConflictId] = useState<string | null>(null);

    const handleConfirmEdit = async (messageId: string, pendingEdit: PendingEdit) => {
        if (!currentSessionId || loadingEditId) return;
        setLoadingEditId(messageId);
        try {
            const alteracoes = Object.fromEntries(
                Object.entries(pendingEdit.alteracoes).map(([campo, change]) => [
                    campo,
                    change.novo_raw !== undefined ? change.novo_raw : change.novo
                ])
            );
            const fn = httpsCallable(functions, 'confirmarEdicaoAcao');
            const result = await fn({
                sessionId: currentSessionId,
                messageId,
                taskId: pendingEdit.task_id,
                alteracoes,
                snapshotTs: pendingEdit.snapshot_ts,
            }) as { data: { status: string; message?: string } };
            // Firestore onSnapshot atualiza o card automaticamente após o backend mudar o status
            if (result.data.status === 'invalidated') {
                // Card já foi atualizado no Firestore pelo backend — nada a fazer localmente
            }
        } catch (err: any) {
            // Em falhas transitórias o card permanece pending; erro grave → backend já gravou status error
            console.error('[EditCard] Erro ao confirmar edição:', err);
        } finally {
            setLoadingEditId(null);
        }
    };

    const handleCancelEdit = async (messageId: string) => {
        if (!currentSessionId || loadingEditId) return;
        setLoadingEditId(messageId);
        try {
            const msgRef = doc(db, 'sessoes_copiloto', currentSessionId, 'mensagens', messageId);
            await updateDoc(msgRef, { 'pendingEdit.status': 'cancelled' });
        } catch (err) {
            console.error('[EditCard] Erro ao cancelar edição:', err);
        } finally {
            setLoadingEditId(null);
        }
    };

    const handleConfirmBatchReschedule = async (messageId: string, batchReschedule: PendingBatchReschedule) => {
        if (!currentSessionId || loadingBatchRescheduleId) return;
        setLoadingBatchRescheduleId(messageId);
        try {
            const fn = httpsCallable(functions, 'confirmarReagendamentoEmLote');
            await fn({
                sessionId: currentSessionId,
                messageId,
                items: batchReschedule.items,
                justificativa: batchReschedule.justificativa,
            });
        } catch (err: any) {
            console.error('[BatchReschedule] Erro ao confirmar reagendamento:', err);
        } finally {
            setLoadingBatchRescheduleId(null);
        }
    };

    const handleCancelBatchReschedule = async (messageId: string) => {
        if (!currentSessionId || loadingBatchRescheduleId) return;
        setLoadingBatchRescheduleId(messageId);
        try {
            const msgRef = doc(db, 'sessoes_copiloto', currentSessionId, 'mensagens', messageId);
            await updateDoc(msgRef, { 'pendingBatchReschedule.status': 'cancelled' });
        } catch (err) {
            console.error('[BatchReschedule] Erro ao cancelar reagendamento:', err);
        } finally {
            setLoadingBatchRescheduleId(null);
        }
    };

    const handleResolveMemoryConflict = async (
        messageId: string,
        conflict: PendingMemoryConflict,
        decisao: 'manter_existente' | 'substituir_pelo_novo'
    ) => {
        if (!currentSessionId || loadingMemoryConflictId) return;
        setLoadingMemoryConflictId(messageId);
        try {
            const fn = httpsCallable(functions, 'confirmarConflitoMemoria');
            await fn({
                sessionId: currentSessionId,
                messageId,
                memoriaId: conflict.memory_id,
                decisao,
                fatoAtualizado: conflict.proposed_text,
                categoria: conflict.categoria_existente || 'fato_isolado',
            });
        } catch (err: any) {
            console.error('[MemoryConflict] Erro ao resolver conflito:', err);
            setFooterError('Erro ao resolver conflito de memória: ' + (err?.message || 'Tente novamente.'));
        } finally {
            setLoadingMemoryConflictId(null);
        }
    };

    // ── Seleção de item do mention popup ─────────────────────────────────────
    const selectMention = (item: PoolItem) => {
        const before = input.slice(0, mention.atIndex);
        const after = input.slice(mention.atIndex + 1 + mention.query.length);
        let ref = '';
        if (item.tipo === 'arquivo' && item.drive_file_id) {
            ref = `📎 "${item.nome || 'arquivo'}" (drive_id:${item.drive_file_id})`;
        } else if (item.tipo === 'link') {
            ref = `🔗 "${item.nome || item.valor}" (${item.valor})`;
        } else {
            ref = `"${item.nome || item.valor}"`;
        }
        setInput(before + ref + after);
        setMention(prev => ({ ...prev, visible: false }));
        setTimeout(() => textareaRef.current?.focus(), 0);
    };

    // ── Transcrição de áudio colado ───────────────────────────────────────────
    const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
        const files = Array.from(e.clipboardData.files);

        // Se houver arquivos (imagem, pdf, etc no clipboard)
        if (files.length > 0) {
            const audioFile = files.find(f => f.type.startsWith('audio/'));

            // Prioridade para o fluxo de áudio se for um arquivo de áudio
            if (audioFile) {
                e.preventDefault();
                setIsTranscribing(true);
                setFooterError(null);

                try {
                    const reader = new FileReader();
                    reader.readAsDataURL(audioFile);
                    reader.onloadend = async () => {
                        try {
                            const b64 = (reader.result as string).split(',')[1];
                            const nameParts = audioFile.name.split('.');
                            const ext = nameParts.length > 1
                                ? '.' + nameParts.pop()
                                : '.' + (audioFile.type.split('/')[1]?.split(';')[0] || 'm4a');

                            const fn = httpsCallable(functions, 'transcreverAudio');
                            const res = await fn({ audioBase64: b64, extension: ext });
                            const data = res.data as { raw: string; refined: string };

                            if (data.refined) {
                                setInput(prev => prev + (prev ? '\n' : '') + data.refined);
                            }
                        } catch (err: any) {
                            setFooterError('Erro ao transcrever áudio: ' + (err?.message || 'Tente novamente.'));
                        } finally {
                            setIsTranscribing(false);
                        }
                    };
                    reader.onerror = () => {
                        setFooterError('Não foi possível ler o arquivo de áudio colado.');
                        setIsTranscribing(false);
                    };
                } catch (err: any) {
                    setFooterError('Erro ao transcrever áudio: ' + (err?.message || 'Tente novamente.'));
                    setIsTranscribing(false);
                }
                return;
            }

            // Se não for áudio, mas houver arquivos (como imagens ou outros)
            // Filtra o primeiro arquivo suportado e anexa
            const firstSupported = files.find(f => isCopilotoFileSupported(f));
            if (firstSupported) {
                e.preventDefault();
                attachFileToCopiloto(firstSupported, 'input');
                return;
            }
        }

        // Fluxo normal para texto
        const pastedText = e.clipboardData.getData('text');
        if (pastedText.length > LARGE_PASTE_THRESHOLD) {
            e.preventDefault();
            const dateStr = new Date().toISOString().slice(0, 10);
            setPastedContext({ text: pastedText, name: `contexto-${dateStr}.txt` });
        }
    };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            micStreamRef.current = stream;
            const mr = new MediaRecorder(stream);
            mediaRecorderRef.current = mr;
            audioChunksRef.current = [];
            mr.ondataavailable = e => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
            mr.onstop = async () => {
                const blob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
                if (micStreamRef.current) { micStreamRef.current.getTracks().forEach(t => t.stop()); micStreamRef.current = null; }
                setIsProcessingMic(true);
                try {
                    const reader = new FileReader();
                    reader.readAsDataURL(blob);
                    reader.onloadend = async () => {
                        try {
                            const b64 = (reader.result as string).split(',')[1];
                            const fn = httpsCallable(functions, 'transcreverAudio');
                            const res = await fn({ audioBase64: b64, extension: '.m4a' });
                            const data = res.data as { raw: string; refined: string };
                            if (data.refined) setInput(prev => prev + (prev ? '\n' : '') + data.refined);
                        } catch { setFooterError('Erro ao transcrever áudio do microfone.'); }
                        finally { setIsProcessingMic(false); }
                    };
                } catch { setIsProcessingMic(false); }
            };
            mr.start();
            setIsRecording(true);
        } catch { setFooterError('Erro ao acessar microfone. Verifique as permissões.'); }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop();
            setIsRecording(false);
        }
    };

    useEffect(() => {
        return () => {
            if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') mediaRecorderRef.current.stop();
            if (micStreamRef.current) { micStreamRef.current.getTracks().forEach(t => t.stop()); micStreamRef.current = null; }
            voiceStream.stop();
        };
    }, []);

    // ── Criação de sessão ─────────────────────────────────────────────────────
    const handleCreateSession = async (initialPrompt?: string) => {
        setIsLoading(true);
        try {
            const sessRef = await addDoc(collection(db, 'sessoes_copiloto'), {
                userId,
                title: initialPrompt ? initialPrompt.slice(0, 40) + '...' : isFinancialCopilot ? 'Copiloto Financeiro' : 'Nova Conversa',
                createdAt: Timestamp.now(),
                lastMessageAt: Timestamp.now(),
                taskId: taskId || null,
                systemId: systemId || null,
                copilotMode
            });

            setCurrentSessionId(sessRef.id);
            currentSessionIdRef.current = sessRef.id;
            if (initialPrompt) {
                await sendMessage(initialPrompt, sessRef.id);
            }
            return sessRef.id;
        } catch (err) {
            console.error("Erro ao criar sessão:", err);
            return null;
        } finally {
            setIsLoading(false);
        }
    };

    // ── Envio de mensagem (com ou sem arquivo) ────────────────────────────────
    const sendMessage = async (text: string, sessionId?: string) => {
        const sId = sessionId || currentSessionId;
        const hasFile = !!attachedFile;
        const hasPaste = !!pastedContext;
        let copilotActivityOpen = false;
        const closeCopilotActivity = (phase: 'completed' | 'failed' | 'cancelled') => {
            if (!copilotActivityOpen) return;
            onCopilotActivity?.(phase);
            copilotActivityOpen = false;
        };

        if (!sId || (!text.trim() && !hasFile && !hasPaste)) return;

        const fileToSend = attachedFile;
        const pasteToSend = pastedContext;
        setInput('');
        setAttachedFile(null);
        setPastedContext(null);
        setFooterError(null);
        isCancelledRef.current = false;
        const abortController = new AbortController();
        abortControllerRef.current = abortController;
        setIsLoading(true);

        try {
            let driveFileId: string | null = null;
            let driveFileName: string | null = null;

            // ── FASE 1: Upload para o Drive via endpoint HTTP ─────────────────
            if (fileToSend) {
                setUploadPhase('uploading');

                const idToken = await auth.currentUser?.getIdToken();
                if (!idToken) throw new Error("Usuário não autenticado.");

                const formData = new FormData();
                formData.append('file', fileToSend, fileToSend.name);

                const uploadRes = await fetch(UPLOAD_ENDPOINT, {
                    method: 'POST',
                    headers: { Authorization: `Bearer ${idToken}` },
                    body: formData,
                    signal: abortController.signal
                });

                if (!uploadRes.ok) {
                    const errBody = await uploadRes.json().catch(() => ({}));
                    throw new Error(errBody.error || `Erro no upload: HTTP ${uploadRes.status}`);
                }

                const uploadData = await uploadRes.json();
                driveFileId = uploadData.driveFileId;
                driveFileName = uploadData.fileName || fileToSend.name;

                // Transição para Fase 2
                setUploadPhase('processing');
                startProgressAnimation();
            }

            if (isCancelledRef.current) return;

            // Constrói o conteúdo da mensagem do usuário para o histórico
            const userMessageContent = hasFile && fileToSend
                ? `📎 ${fileToSend.name}${text.trim() ? `\n\n${text.trim()}` : ''}`
                : hasPaste && pasteToSend
                ? `📎 ${pasteToSend.name}${text.trim() ? `\n\n${text.trim()}` : ''}`
                : text;

            // Marca atividade do copiloto: o container usa isto para não disparar
            // uma manifestação automática quando a mutação resultante vier daqui.
            onCopilotActivity?.('started');
            copilotActivityOpen = true;

            // 1. Salva mensagem do usuário no Firestore
            await addDoc(collection(db, 'sessoes_copiloto', sId, 'mensagens'), {
                role: 'user',
                content: userMessageContent,
                timestamp: Timestamp.now()
            });

            if (isCancelledRef.current) {
                closeCopilotActivity('cancelled');
                return;
            }

            // 2. Chama a Cloud Function
            const askCopiloto = httpsCallable(functions, 'askCopilotoHermes', { timeout: COPILOTO_CALLABLE_TIMEOUT_MS });

            const contextPrefix = activeDocument
                ? `[CONTEXTO: Visualizando ${activeDocument.tipo} "${activeDocument.nome}" em Tela Cheia]\nLocal: ${activeDocument.url}${activeDocument.driveFileId ? `\nID para leitura profunda: ${activeDocument.driveFileId}\nPara ler o arquivo e responder dúvidas técnicas ou realizar cálculos, utilize a ferramenta 'ler_documento_na_integra' com este ID.` : ''}\n\n`
                : '';

            const pastePrefix = pasteToSend
                ? `[CONTEXTO COLADO]\n${pasteToSend.text}\n[/CONTEXTO]\n\n`
                : '';

            const response = await withClientTimeout(askCopiloto({
                sessionId: sId,
                prompt: contextPrefix + pastePrefix + (text.trim() || (hasFile || hasPaste ? '' : text)),
                taskId: taskId || null,
                systemId: systemId || null,
                driveFileId: driveFileId || null,
                driveFileName: driveFileName || null,
                copilotMode,
                routingIndex: getRoutingIndex()
            }), COPILOTO_CALLABLE_TIMEOUT_MS, COPILOTO_CLIENT_TIMEOUT_MESSAGE);

            if (isCancelledRef.current) {
                closeCopilotActivity('cancelled');
                return;
            }

            const data = response.data as any;

            // Reforça a marca de atividade no retorno: é quando a mutação do
            // copiloto (plano/diário) efetivamente chega ao Firestore, momento a
            // partir do qual a janela de supressão do insight precisa valer.
            closeCopilotActivity('completed');

            // 3. Atualiza título da sessão se for a primeira mensagem
            if (messages.length === 0 && !sessionId) {
                await touchCopilotoSession(sId, {
                    title: data.suggestedTitle || userMessageContent.slice(0, 40) + '...',
                    lastMessageAt: Timestamp.now()
                });
            } else {
                await touchCopilotoSession(sId, {
                    lastMessageAt: Timestamp.now()
                });
            }

            // Caminho de sucesso: anima para 100% antes de liberar o input.
            // Só executa aqui — nunca no finally — para não colidir com erros.
            await completeProgress();

        } catch (err: any) {
            if (isCancelledRef.current || err?.name === 'AbortError') {
                closeCopilotActivity('cancelled');
                abortProgress();
                return;
            }

            console.error("Erro no Copiloto:", err);
            closeCopilotActivity('failed');

            const errMsg = getCopilotoErrorMessage(err);

            // Aborta a barra instantaneamente: impede que o usuário veja "100%"
            // enquanto um banner de erro vermelho é exibido simultaneamente.
            abortProgress();
            setFooterError(errMsg);

            // Persiste no histórico da sessão se ela já existir.
            const sId2 = sessionId || currentSessionId;
            if (sId2) {
                await addDoc(collection(db, 'sessoes_copiloto', sId2, 'mensagens'), {
                    role: 'assistant',
                    content: `⚠️ **Erro ao processar a solicitação:**\n\`${errMsg}\``,
                    timestamp: Timestamp.now()
                }).catch(() => { });
            }

        } finally {
            // O finally só faz reset de estado — nunca dispara animação.
            // A animação de sucesso já aconteceu no try; a de erro foi abortada no catch.
            setUploadPhase('idle');
            setIsLoading(false);
        }
    };

    if (!isOpen) return null;

    // ── Modal de relatório (renderizado fora do drawer, sobre tudo) ──────────
    if (reportModalOpen) {
        return (
            <ReportModal
                isOpen={reportModalOpen}
                onClose={() => { setReportModalOpen(false); setActiveReport(null); }}
                reportId={activeReport?.id ?? ''}
                titulo={activeReport?.titulo ?? (isLoadingReport ? 'Carregando...' : 'Relatório')}
                markdown={activeReport?.markdown ?? (isLoadingReport ? '' : '')}
                onOpenTask={onOpenTask}
            />
        );
    }

    // ── Labels da barra de status por fase ───────────────────────────────────
    if (diagnosisModalOpen) {
        return (
            <div className="fixed inset-0 z-[700] bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
                <div className={`w-full max-w-4xl max-h-[92vh] overflow-hidden rounded-lg shadow-lg border ${isDark ? 'bg-[#0f0f1a] border-[#e5e7eb] dark:border-white/10 text-white' : 'bg-white border-[#e5e7eb] dark:border-white/10 text-slate-900'}`}>
                    <div className={`flex items-center justify-between gap-4 px-6 py-4 border-b ${isDark ? 'border-[#e5e7eb] dark:border-white/10' : 'border-slate-100'}`}>
                        <div className="min-w-0">
                            <p className="text-[10px] font-bold uppercase tracking-wider text-blue-500">Diagnóstico de Código</p>
                            <p className="text-sm font-black truncate">{activeDiagnosis?.descricaoProblema || (isLoadingDiagnosis ? 'Carregando diagnóstico...' : 'Diagnóstico')}</p>
                        </div>
                        <button onClick={() => { setDiagnosisModalOpen(false); setActiveDiagnosis(null); }} className={`p-2 rounded-lg transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}>
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                    <div className={`overflow-y-auto max-h-[calc(92vh-88px)] p-6 space-y-5 ${isDark ? 'bg-[#0f0f1a]' : 'bg-slate-50'}`}>
                        {isLoadingDiagnosis && (
                            <div className="flex items-center justify-center py-16">
                                <div className="w-6 h-6 border-2 border-slate-300 border-t-blue-500 rounded-lg animate-spin" />
                            </div>
                        )}
                        {!isLoadingDiagnosis && !activeDiagnosis && (
                            <div className={`rounded-lg border p-5 text-sm ${isDark ? 'border-[#e5e7eb] dark:border-white/10 bg-white/5 text-white/70' : 'border-[#e5e7eb] dark:border-white/10 bg-white text-slate-500'}`}>
                                Não foi possível carregar este diagnóstico.
                            </div>
                        )}
                        {!isLoadingDiagnosis && activeDiagnosis && (
                            <>
                                <div className={`rounded-lg border p-4 ${isDark ? 'border-[#e5e7eb] dark:border-white/10 bg-white/5' : 'border-[#e5e7eb] dark:border-white/10 bg-white'}`}>
                                    <p className={`text-[10px] font-bold uppercase tracking-wider mb-3 ${isDark ? 'text-white/50' : 'text-slate-400'}`}>Ações para IA</p>
                                    <div className="flex flex-wrap gap-2">
                                        <button
                                            onClick={() => handleDownloadDiagnosisMarkdown(activeDiagnosis)}
                                            className={`px-3 py-2 rounded-lg text-[11px] font-black transition-all ${isDark ? 'bg-white/10 hover:bg-white/15 text-white' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}`}
                                        >
                                            Exportar Markdown
                                        </button>
                                        <button
                                            onClick={() => handleDownloadDiagnosisAiPackage(activeDiagnosis)}
                                            className={`px-3 py-2 rounded-lg text-[11px] font-black transition-all ${isDark ? 'bg-blue-500/20 hover:bg-blue-500/30 text-blue-100' : 'bg-blue-600 hover:bg-blue-700 text-white'}`}
                                        >
                                            Exportar Pacote IA
                                        </button>
                                        <button
                                            onClick={() => handleCopyDiagnosisAiPackage(activeDiagnosis)}
                                            className={`px-3 py-2 rounded-lg text-[11px] font-black transition-all ${isDark ? 'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-100' : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700'}`}
                                        >
                                            {diagnosisCopyDone ? 'Copiado!' : 'Copiar para IA'}
                                        </button>
                                    </div>
                                    <p className={`text-[11px] mt-3 leading-5 ${isDark ? 'text-white/55' : 'text-slate-500'}`}>
                                        O pacote para IA inclui contexto e blocos <span className="font-sans">SEARCH/REPLACE</span> em formato pronto para colar em agentes de código.
                                    </p>
                                </div>
                                <div className={`rounded-lg border p-5 ${isDark ? 'border-[#e5e7eb] dark:border-white/10 bg-white/5' : 'border-[#e5e7eb] dark:border-white/10 bg-white'}`}>
                                    <div className="flex flex-wrap items-center gap-2 mb-3">
                                        {activeDiagnosis.sistemaId && <span className="text-[10px] font-bold uppercase tracking-wider text-blue-600 bg-blue-50 px-2 py-1 rounded-lg">{activeDiagnosis.sistemaId}</span>}
                                        {activeDiagnosis.nomeRepositorio && <span className={`text-[10px] font-sans px-2 py-1 rounded-lg ${isDark ? 'bg-white/10 text-white/70' : 'bg-slate-100 text-slate-500'}`}>{activeDiagnosis.nomeRepositorio}</span>}
                                        {activeDiagnosis.arquivosAnalisados && <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-lg ${isDark ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-50 text-emerald-700'}`}>{activeDiagnosis.arquivosAnalisados.length} arquivo(s)</span>}
                                    </div>
                                    <p className={`text-[11px] font-bold uppercase tracking-wider mb-2 ${isDark ? 'text-white/50' : 'text-slate-400'}`}>Diagnóstico</p>
                                    <p className={`text-sm leading-7 whitespace-pre-wrap ${isDark ? 'text-white/80' : 'text-slate-700'}`}>{activeDiagnosis.diagnostico}</p>
                                </div>
                                {activeDiagnosis.blocosSR && activeDiagnosis.blocosSR.length > 0 && (
                                    <div className="space-y-3">
                                        {activeDiagnosis.blocosSR.map((bloco, index) => (
                                            <div key={`${activeDiagnosis.id}_${index}`} className={`rounded-lg border overflow-hidden ${isDark ? 'border-[#e5e7eb] dark:border-white/10 bg-white/5' : 'border-[#e5e7eb] dark:border-white/10 bg-white'}`}>
                                                <div className={`px-4 py-3 border-b ${isDark ? 'border-[#e5e7eb] dark:border-white/10 bg-white/5' : 'border-slate-100 bg-slate-50'}`}>
                                                    <p className="text-[11px] font-black">{index + 1}. {bloco.descricao}</p>
                                                    <p className={`text-[10px] font-sans mt-1 ${isDark ? 'text-white/50' : 'text-slate-400'}`}>{bloco.arquivo}</p>
                                                </div>
                                                <div className="p-4 grid gap-4 md:grid-cols-2">
                                                    <div>
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-rose-500 mb-2">Search</p>
                                                        <pre className={`text-[11px] leading-6 overflow-x-auto rounded-lg p-3 ${isDark ? 'bg-rose-500/10 text-white/80' : 'bg-rose-50 text-slate-700'}`}>{bloco.search}</pre>
                                                    </div>
                                                    <div>
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 mb-2">Replace</p>
                                                        <pre className={`text-[11px] leading-6 overflow-x-auto rounded-lg p-3 ${isDark ? 'bg-emerald-500/10 text-white/80' : 'bg-emerald-50 text-slate-700'}`}>{bloco.replace}</pre>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {activeDiagnosis.alertaImpacto && (
                                    <div className={`rounded-lg border p-4 ${isDark ? 'border-amber-400/20 bg-amber-500/10 text-amber-100' : 'border-[#e5e7eb] dark:border-white/10 bg-amber-50 text-amber-800'}`}>
                                        <p className="text-[10px] font-bold uppercase tracking-wider mb-2">Alerta de Impacto</p>
                                        <p className="text-sm leading-6">{activeDiagnosis.alertaImpacto}</p>
                                    </div>
                                )}
                                {activeDiagnosis.markdownContent && (
                                    <div className={`rounded-lg border p-5 ${isDark ? 'border-[#e5e7eb] dark:border-white/10 bg-white/5' : 'border-[#e5e7eb] dark:border-white/10 bg-white'}`}>
                                        <p className={`text-[10px] font-bold uppercase tracking-wider mb-3 ${isDark ? 'text-white/50' : 'text-slate-400'}`}>Relatório Completo</p>
                                        <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={(url) => url}>{activeDiagnosis.markdownContent}</ReactMarkdown>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    const uploadPhaseLabel: Record<UploadPhase, string> = {
        idle: '',
        uploading: 'Enviando arquivo seguro para o servidor...',
        processing: 'Extraindo contexto e atualizando Acervo...'
    };

    const isEmbedded = variant === 'embedded';
    const shouldAutoCloseOnNavigate = !isEmbedded;
    const effectiveDrawerWidth = isEmbedded ? '100%' : isMobileViewport ? '100%' : `${drawerWidth}px`;
    const containerClassName = isEmbedded
        ? `relative h-full min-h-0 flex flex-col break-words [overflow-wrap:anywhere] rounded-lg ${isDark ? 'bg-[#0f1724] text-white' : 'bg-white text-slate-900'}`
        : `fixed inset-y-0 right-0 z-[500] shadow-lg transition-transform duration-300 transform translate-x-0 flex flex-col break-words [overflow-wrap:anywhere] ${isDark ? 'bg-[#0f0f1a] text-white' : 'bg-white text-slate-900 border-l border-[#e5e7eb] dark:border-white/10'}`;

    return (
        <div
            onDragEnter={handleComposerDragEnter}
            onDragOver={handleComposerDragOver}
            onDragLeave={handleComposerDragLeave}
            onDrop={handleComposerDrop}
            className={containerClassName}
            style={{ width: effectiveDrawerWidth, maxWidth: isMobileViewport ? '100vw' : undefined }}
        >
            {isDragActive && (
                <div className={`pointer-events-none absolute inset-0 z-[100] flex items-center justify-center backdrop-blur-sm ${isDark
                    ? 'border-4 border-blue-400 bg-blue-500/10'
                    : 'border-4 border-blue-400 bg-blue-50/90'
                    }`}>
                    <div className={`px-8 py-6 rounded-[2.5rem] text-center shadow-lg ${isDark ? 'bg-slate-950/90 text-blue-200 border border-blue-400/30' : 'bg-white text-blue-700 border border-blue-100'
                        }`}>
                        <div className="w-16 h-16 rounded-lg bg-blue-500/10 flex items-center justify-center mx-auto mb-4">
                            <svg className="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                            </svg>
                        </div>
                        <p className="text-lg font-bold uppercase tracking-wider">Solte para anexar</p>
                        <p className="text-xs mt-2 opacity-80 max-w-[240px]">O Hermes usará este contexto para analisar documentos ou salvar no acervo.</p>
                    </div>
                </div>
            )}
            {/* Handle de redimensionamento — borda esquerda */}
            {!isEmbedded && (
                <div
                    onMouseDown={handleResizeMouseDown}
                    className={`absolute left-0 top-0 bottom-0 w-1.5 z-10 group ${isMobileViewport ? 'pointer-events-none opacity-0' : 'cursor-ew-resize'}`}
                    title="Arrastar para redimensionar"
                >
                    <div className="absolute inset-y-0 left-0 w-full bg-transparent group-hover:bg-blue-400/30 transition-colors duration-150 rounded-l" />
                    <div className="absolute top-1/2 -translate-y-1/2 left-0 w-1 h-10 rounded-lg bg-slate-300 group-hover:bg-blue-400 transition-colors duration-150" />
                </div>
            )}

            {/* Header - Unified Style */}
            <div className={`shrink-0 px-4 py-2 flex items-center justify-between border-b ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                <div className="flex items-center gap-2 min-w-0">
                    {isHealthCopilot ? (
                        <svg className={`w-4 h-4 ${isDark ? 'text-rose-400' : 'text-rose-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                        </svg>
                    ) : isFinancialCopilot ? (
                        <svg className={`w-4 h-4 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2m0-2c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                    ) : (
                        <svg className={`w-4 h-4 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                    )}
                    <div className="flex flex-col sm:flex-row sm:items-center sm:gap-2 min-w-0">
                        <span className={`text-[9px] font-bold uppercase tracking-wider font-sans ${isDark ? 'text-white/40' : 'text-slate-400'}`}>
                            {isHealthCopilot ? 'Copiloto de Saude' : isFinancialCopilot ? 'Copiloto Financeiro' : 'Copiloto Hermes'}
                        </span>
                        {taskId && (
                            <div className="flex items-center gap-1.5 shrink-0">
                                <span className="hidden sm:inline text-[9px] text-slate-300 opacity-30">•</span>
                                <span className="w-1 h-1 rounded-lg bg-emerald-500 animate-pulse" />
                                <span className="text-[8px] font-black text-emerald-500 uppercase tracking-tighter">Ativo</span>
                            </div>
                        )}
                    </div>
                </div>

                <div className="flex items-center gap-1.5">
                    {!isTemporary && (
                        <>
                            <button
                                onClick={() => setShowHistory(v => !v)}
                                className={`p-1.5 rounded-lg transition-all ${showHistory ? (isDark ? 'bg-white/10 text-white' : 'bg-slate-100 text-slate-900') : (isDark ? 'text-white/50 hover:bg-white/10 hover:text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-900')}`}
                                title="Histórico de Conversas"
                            >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                            </button>
                            <button
                                onClick={() => handleCreateSession()}
                                className={`p-1.5 rounded-lg transition-all ${isDark ? 'text-white/50 hover:bg-white/10 hover:text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-900'}`}
                                title="Nova Conversa"
                            >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                            </button>
                        </>
                    )}
                    <button
                        onClick={onClose}
                        className={`flex h-7 w-7 items-center justify-center rounded-lg border transition-all ${isDark ? 'border-white/10 text-white/50 hover:bg-white/10 hover:text-white' : 'border-[#e5e7eb] dark:border-white/10 text-slate-500 hover:bg-slate-100 hover:text-slate-900'}`}
                        title="Recolher copiloto"
                    >
                        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" />
                        </svg>
                    </button>
                </div>
            </div>

            <div className={`flex-1 min-h-0 overflow-hidden flex relative ${isDark ? 'bg-[#0f0f1a]' : 'bg-white'}`}>
                {/* History Sidebar */}
                {showHistory && (
                    <div className={`absolute inset-0 z-10 flex flex-col ${isDark ? 'border-r border-[#e5e7eb] dark:border-white/10 bg-[#0b1220]' : 'border-r border-[#e5e7eb] dark:border-white/10 bg-white'}`}>
                        <div className={`p-4 flex items-center justify-between ${isDark ? 'border-b border-[#e5e7eb] dark:border-white/10 bg-[#0b1220] text-white/70' : 'border-b border-slate-100 bg-white text-slate-900'}`}>
                            <span className="text-[10px] font-bold uppercase tracking-wider">Histórico de Sessões</span>
                            <button onClick={() => handleCreateSession()} className="text-[10px] bg-blue-600 text-white px-3 py-1.5 rounded-lg font-bold uppercase tracking-wider">+ Nova</button>
                        </div>
                        <div className={`flex-1 overflow-y-auto p-4 space-y-4 ${isDark ? 'bg-[#0b1220]' : 'bg-white'}`}>
                            {/* Sessões da Ação Atual */}
                            {taskId && (
                                <div className="space-y-2">
                                    <h4 className={`text-[9px] font-black uppercase tracking-[0.2em] px-2 mb-3 pb-1 border-b ${isDark ? 'text-emerald-400 border-emerald-500/20' : 'text-emerald-600 border-emerald-100'}`}>
                                        Conversas nesta Ação
                                    </h4>
                                    {sessions.filter(s => s.taskId === taskId).length === 0 ? (
                                        <p className={`text-[10px] px-2 italic ${isDark ? 'text-white/30' : 'text-slate-400'}`}>Nenhuma conversa anterior nesta ação.</p>
                                    ) : (
                                        sessions.filter(s => s.taskId === taskId).map(s => (
                                            <div
                                                key={s.id}
                                                className={`group flex items-center gap-2 rounded-lg border p-1.5 transition-all ${currentSessionId === s.id ? (isDark ? 'bg-emerald-500/10 border-emerald-400/30 shadow-[0_0_15px_rgba(16,185,129,0.1)]' : 'bg-emerald-50 border-[#e5e7eb] dark:border-white/10 shadow-sm') : (isDark ? 'bg-white/5 border-[#e5e7eb] dark:border-white/10 hover:border-white/20' : 'bg-white border-slate-100 hover:border-[#e5e7eb] dark:border-white/10')}`}
                                            >
                                                <button
                                                    onClick={() => { setCurrentSessionId(s.id); setShowHistory(false); }}
                                                    className="min-w-0 flex-1 text-left rounded-lg px-2 py-1.5"
                                                >
                                                    <p className={`text-xs font-bold truncate ${isDark ? (currentSessionId === s.id ? 'text-emerald-300' : 'text-white') : (currentSessionId === s.id ? 'text-emerald-700' : 'text-slate-900')}`}>{s.title}</p>
                                                    <p className={`text-[9px] mt-0.5 ${isDark ? 'text-white/45' : 'text-slate-400'}`}>{s.lastMessageAt?.toDate()?.toLocaleDateString()} · {s.lastMessageAt?.toDate()?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
                                                </button>
                                                <button
                                                    onClick={() => void handleDeleteSession(s.id)}
                                                    className={`shrink-0 opacity-0 group-hover:opacity-100 p-2 rounded-lg transition-all ${isDark ? 'hover:bg-red-500/20 text-red-400' : 'hover:bg-red-50 text-red-600'}`}
                                                >
                                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M4 7h16" /></svg>
                                                </button>
                                            </div>
                                        ))
                                    )}
                                </div>
                            )}

                            {/* Outras Sessões */}
                            <div className="space-y-2 pt-2">
                                <h4 className={`text-[9px] font-black uppercase tracking-[0.2em] px-2 mb-3 pb-1 border-b ${isDark ? 'text-slate-500 border-[#e5e7eb] dark:border-white/10' : 'text-slate-400 border-slate-100'}`}>
                                    {taskId ? 'Outras Conversas' : 'Histórico Geral'}
                                </h4>
                                {sessions.filter(s => s.taskId !== taskId).map(s => (
                                    <div
                                        key={s.id}
                                        className={`group flex items-center gap-2 rounded-lg border p-1.5 transition-all ${currentSessionId === s.id ? (isDark ? 'bg-blue-500/15 border-blue-400/30' : 'bg-blue-50 border-[#e5e7eb] dark:border-white/10') : (isDark ? 'bg-white/5 border-[#e5e7eb] dark:border-white/10 hover:border-white/20' : 'bg-white border-slate-100 hover:border-[#e5e7eb] dark:border-white/10')}`}
                                    >
                                        <button
                                            onClick={() => { setCurrentSessionId(s.id); setShowHistory(false); }}
                                            className="min-w-0 flex-1 text-left rounded-lg px-2 py-1.5"
                                        >
                                            <p className={`text-xs font-bold truncate ${isDark ? 'text-white' : 'text-slate-900'}`}>{s.title}</p>
                                            <p className={`text-[9px] mt-0.5 ${isDark ? 'text-white/45' : 'text-slate-400'}`}>{s.lastMessageAt?.toDate()?.toLocaleDateString()}</p>
                                        </button>
                                        <button
                                            onClick={() => void handleDeleteSession(s.id)}
                                            className={`shrink-0 opacity-0 group-hover:opacity-100 p-2 rounded-lg transition-all ${isDark ? 'hover:bg-red-500/20 text-red-400' : 'hover:bg-red-50 text-red-600'}`}
                                        >
                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M4 7h16" /></svg>
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {/* Chat Area */}
                <div className={`flex-1 min-h-0 flex flex-col min-w-0 overflow-hidden ${isDark ? 'bg-[#0f0f1a]' : 'bg-white'}`}>
                    <div className={`flex-1 min-h-0 overflow-y-scroll p-6 space-y-6 ${isDark ? 'bg-[#0f0f1a]' : 'bg-white'}`} style={{ scrollbarWidth: 'thin' }}>
                        {messages.length === 0 && !isLoading && (
                            <div className="h-full flex flex-col items-center justify-center pointer-events-none select-none">
                                <div className={`${isDark ? 'text-white' : 'text-slate-900'} opacity-[0.05] animate-pulse-slow`}>
                                    <svg className="w-48 h-48 sm:w-64 sm:h-64" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="0.8" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                                    </svg>
                                </div>
                            </div>
                        )}

                        {messages.map((msg, i) => {
                            const messageKey = msg.id || `${msg.role}-${i}`;
                            const messageTimestamp = formatMessageTimestamp(msg.timestamp);
                            const isProactiveInsight = msg.subtype === 'proactive_insight';
                            return (
                                <div key={messageKey} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                                    <div className={`group relative max-w-[90%] min-w-0 px-4 py-3 rounded-lg text-xs font-medium leading-relaxed shadow-sm break-words [overflow-wrap:anywhere] [&_*]:max-w-full font-sans ${msg.role === 'user'
                                        ? 'bg-blue-600 text-white rounded-br-none'
                                        : isProactiveInsight
                                            ? isDark
                                                ? 'bg-indigo-950/30 text-indigo-100 border border-indigo-500/20 rounded-bl-none'
                                                : 'bg-indigo-50 text-indigo-900 border border-indigo-100 rounded-bl-none'
                                            : isDark
                                                ? 'bg-slate-800 text-slate-100 border border-slate-700 rounded-bl-none'
                                                : 'bg-slate-100 text-slate-700 rounded-bl-none'
                                        }`}>
                                        {isProactiveInsight && (
                                            <div className={`mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}>
                                                <span aria-hidden="true">{"\uD83E\uDD16"}</span>
                                                <span>Hermes</span>
                                            </div>
                                        )}
                                        <div className={`absolute right-2 top-2 flex gap-1 opacity-0 transition-all group-hover:opacity-100`}>
                                            <button
                                                type="button"
                                                onClick={() => handleCopyChatMessage(messageKey, msg.content || '')}
                                                className={`rounded-md p-1 transition-all ${isDark ? 'bg-black/20 text-white/60 hover:text-white hover:bg-black/30' : 'bg-white/70 text-slate-400 hover:text-slate-700 hover:bg-white'}`}
                                                title={copiedMessageKey === messageKey ? 'Copiado!' : 'Copiar mensagem'}
                                            >
                                                {copiedMessageKey === messageKey ? (
                                                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                                                ) : (
                                                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V5a2 2 0 012-2h7a2 2 0 012 2v7a2 2 0 01-2 2h-2m-1 4H7a2 2 0 01-2-2V9a2 2 0 012-2h7a2 2 0 012 2v7a2 2 0 01-2 2z" /></svg>
                                                )}
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => handleDeleteMessage(msg.id)}
                                                className={`rounded-md p-1 transition-all ${confirmDeleteMessageId === msg.id
                                                    ? 'bg-red-600 text-white scale-110 shadow-lg'
                                                    : isDark
                                                        ? 'bg-black/20 text-red-400/60 hover:text-red-400 hover:bg-black/30'
                                                        : 'bg-white/70 text-red-400 hover:text-red-600 hover:bg-white'
                                                    }`}
                                                title={confirmDeleteMessageId === msg.id ? "Clique novamente para confirmar" : "Excluir mensagem"}
                                            >
                                                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M4 7h16" /></svg>
                                            </button>
                                        </div>
                                        {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                                            <ToolsUsedBadges tools={msg.toolsUsed} isDark={isDark} />
                                        )}
                                        <CollapsibleContainer maxLines={8}>
                                            <ReactMarkdown
                                                remarkPlugins={[remarkGfm]}
                                                urlTransform={(url) => url}
                                                components={{
                                                    p: ({ node, ...props }) => <p className="mb-2 last:mb-0 break-words [overflow-wrap:anywhere]" {...props} />,
                                                    ul: ({ node, ...props }) => <ul className="list-disc ml-4 mb-2 break-words [overflow-wrap:anywhere]" {...props} />,
                                                    li: ({ node, ...props }) => <li className="mb-0.5 break-words [overflow-wrap:anywhere]" {...props} />,
                                                    strong: ({ node, ...props }) => <strong className={`font-bold ${isDark ? 'text-blue-300' : 'text-blue-600'}`} {...props} />,
                                                    pre: ({ node, children, ...props }) => {
                                                        const arr = React.Children.toArray(children);
                                                        const first = arr[0] as React.ReactElement<any> | undefined;
                                                        if (first?.props?.className === 'language-mermaid') {
                                                            return <>{children}</>;
                                                        }
                                                        return (
                                                            <pre
                                                                className="max-w-full whitespace-pre-wrap break-words [overflow-wrap:anywhere] overflow-x-hidden rounded-lg"
                                                                {...props}
                                                            >
                                                                {children}
                                                            </pre>
                                                        );
                                                    },
                                                    code: ({ node, className, children, ...props }) => {
                                                        if (className === 'language-mermaid') {
                                                            return <MermaidBlock code={String(children).trim()} isDark={isDark} />;
                                                        }
                                                        return (
                                                            <code
                                                                className={`${className ?? ''} whitespace-pre-wrap break-words [overflow-wrap:anywhere]`}
                                                                {...props}
                                                            >
                                                                {children}
                                                            </code>
                                                        );
                                                    },
                                                    a: ({ node, ...props }) => {
                                                        const href = props.href || '';

                                                        if (isInternalAppHref(href)) {
                                                            return (
                                                                <a
                                                                    className={`underline break-all ${isDark ? 'text-blue-300 hover:text-blue-200' : 'text-blue-600 hover:text-blue-800'}`}
                                                                    href={href}
                                                                    onClick={(event) => {
                                                                        event.preventDefault();
                                                                        console.log("[HermesCopiloto] Link clicked:", href);
                                                                        navigateWithinApp(href);
                                                                        if (shouldAutoCloseOnNavigate) onClose?.();
                                                                    }}
                                                                >
                                                                    {props.children}
                                                                </a>
                                                            );
                                                        }

                                                        if (href.includes('task:')) {
                                                            const id = href.split('task:')[1];
                                                            return (
                                                                <button
                                                                    onClick={() => {
                                                                        console.log("[HermesCopiloto] Link clicked:", href);
                                                                        onOpenTask?.(id);
                                                                        if (shouldAutoCloseOnNavigate) onClose?.();
                                                                    }}
                                                                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all font-black text-[10px] uppercase tracking-tighter mx-1 shadow-sm group/btn ${isDark ? 'bg-blue-500/10 hover:bg-blue-600 hover:text-white text-blue-300 border-blue-400/30' : 'bg-white/10 hover:bg-blue-600 hover:text-white text-blue-400 border-blue-500/30'}`}
                                                                >
                                                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                                                    <span className="group-hover/btn:underline">{props.children}</span>
                                                                    <svg className="w-3 h-3 opacity-0 group-hover/btn:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                                                                </button>
                                                            );
                                                        }
                                                        if (href.includes('tool:diagnosis:')) {
                                                            const diagId = href.split('tool:diagnosis:')[1];
                                                            return (
                                                                <button
                                                                    onClick={() => {
                                                                        console.log("[HermesCopiloto] Link clicked:", href);
                                                                        handleOpenDiagnosis(diagId);
                                                                    }}
                                                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-all font-black text-[10px] uppercase tracking-tighter mx-1 shadow-sm"
                                                                >
                                                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                                                                    {props.children}
                                                                </button>
                                                            );
                                                        }
                                                        return (
                                                            <a
                                                                className={`underline break-all ${isDark ? 'text-blue-300 hover:text-blue-200' : 'text-blue-600 hover:text-blue-800'}`}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                onClick={() => console.log("[HermesCopiloto] Link clicked:", href)}
                                                                {...props}
                                                            />
                                                        );
                                                    },
                                                }}
                                            >
                                                {msg.content}
                                            </ReactMarkdown>
                                        </CollapsibleContainer>

                                        {msg.toolInvocation && (
                                            <div className={`mt-4 p-4 rounded-lg overflow-hidden ${isDark ? 'bg-slate-950 border border-slate-700' : 'bg-white/5 border border-[#e5e7eb] dark:border-white/10'}`}>
                                                {(() => {
                                                    const tool = toolsRegistry.find(t => t.id === msg.toolInvocation!.tool_id);
                                                    if (!tool) return <div className="text-red-400 text-sm">Erro: Ferramenta {msg.toolInvocation!.tool_id} não encontrada no catálogo.</div>;
                                                    const ToolComponent = tool.component;
                                                    return <ToolComponent {...msg.toolInvocation!.parametros} onBack={() => { }} showToast={() => { }} isEmbedded={true} isDark={isDark} />;
                                                })()}
                                            </div>
                                        )}


                                        {/* Botões de confirmação de draft */}
                                        {msg.role === 'assistant' && (() => {
                                            const draftType = getDraftType(msg.content, i);
                                            if (!draftType) return null;
                                            return (
                                                <div className={`mt-3 pt-3 border-t flex flex-wrap gap-2 ${isDark ? 'border-slate-700' : 'border-[#e5e7eb] dark:border-white/10'}`}>
                                                    <button
                                                        onClick={() => handleQuickReply('Confirmo!')}
                                                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-700 transition-all shadow-sm"
                                                    >
                                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                        Confirmar
                                                    </button>
                                                    <button
                                                        onClick={() => {
                                                            setInput('Prefiro ajustar: ');
                                                            setTimeout(() => textareaRef.current?.focus(), 50);
                                                        }}
                                                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[10px] font-bold uppercase tracking-wider transition-all shadow-sm ${isDark ? 'bg-slate-800 text-amber-300 border-amber-500/30 hover:bg-slate-700' : 'bg-white text-amber-700 border-amber-300 hover:bg-amber-50'}`}
                                                    >
                                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                        Ajustar
                                                    </button>
                                                    <button
                                                        onClick={() => handleQuickReply('Cancelar, não quero prosseguir.')}
                                                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[10px] font-bold uppercase tracking-wider transition-all shadow-sm ${isDark ? 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700 hover:text-slate-100' : 'bg-white text-slate-400 border-[#e5e7eb] dark:border-white/10 hover:bg-slate-100 hover:text-slate-600'}`}
                                                    >
                                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                        Cancelar
                                                    </button>
                                                </div>
                                            );
                                        })()}

                                        {/* Botão Abrir Relatório */}
                                        {msg.role === 'assistant' && msg.reportId && (
                                            <div className={`mt-3 pt-3 border-t ${isDark ? 'border-slate-700' : 'border-[#e5e7eb] dark:border-white/10'}`}>
                                                <button
                                                    onClick={() => handleOpenReport(msg.reportId!)}
                                                    disabled={isLoadingReport}
                                                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-[10px] font-bold uppercase tracking-wider hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm font-sans"
                                                >
                                                    {isLoadingReport ? (
                                                        <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-lg animate-spin" />
                                                    ) : (
                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                                        </svg>
                                                    )}
                                                    Abrir Relatório
                                                </button>
                                            </div>
                                        )}

                                        {msg.proposedPlan && (
                                            <div className={`mt-4 p-4 rounded-lg border shadow-sm ${isDark ? 'bg-slate-950 border-[#e5e7eb] dark:border-white/10' : 'bg-white border-[#e5e7eb] dark:border-white/10'}`}>
                                                <p className="text-[10px] font-bold uppercase tracking-wider text-blue-600 flex items-center gap-2 mb-3">
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                                                    Proposta de Ajuste de Plano
                                                </p>
                                                <div className="space-y-2 mb-4">
                                                    {msg.proposedPlan.map((item, idx) => (
                                                        <div key={idx} className={`flex gap-2 text-[11px] ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
                                                            <span className="font-black text-blue-400">{idx + 1}.</span>
                                                            <span>{item.text}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                                <div className="flex gap-2">
                                                    <button
                                                        onClick={() => msg.id && msg.proposedPlan && handleAcceptProposedPlan(msg.id, msg.proposedPlan)}
                                                        className="flex-1 bg-emerald-600 text-white py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-700 transition-all"
                                                    >
                                                        Aceitar
                                                    </button>
                                                    <button
                                                        onClick={() => msg.id && handleRejectProposedPlan(msg.id)}
                                                        className={`flex-1 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all ${isDark ? 'bg-slate-800 text-slate-300 hover:bg-slate-700' : 'bg-slate-100 text-slate-400 hover:bg-slate-200'}`}
                                                    >
                                                        Recusar
                                                    </button>
                                                </div>
                                            </div>
                                        )}

                                        {/* Card de confirmação de edição de ação */}
                                        {msg.pendingEdit && msg.id && (() => {
                                            const pe = msg.pendingEdit!;
                                            const mid = msg.id!;
                                            const isProcessing = loadingEditId === mid;

                                            if (pe.status === 'completed') {
                                                return (
                                                    <div className="mt-3 p-3 bg-emerald-50 border border-[#e5e7eb] dark:border-white/10 rounded-lg">
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 flex items-center gap-1.5 mb-2">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                            Edição confirmada
                                                        </p>
                                                        <p className="text-[10px] text-emerald-700 font-semibold truncate">{pe.titulo}</p>
                                                        <div className="mt-1.5 space-y-1">
                                                            {Object.entries(pe.alteracoes).map(([campo, change]) => (
                                                                <div key={campo} className="text-[9px] text-emerald-600 flex gap-1 flex-wrap">
                                                                    <span className="font-black">{FIELD_LABELS[campo] ?? campo}:</span>
                                                                    <span className="line-through opacity-60">{change.original || '—'}</span>
                                                                    <span>→</span>
                                                                    <span className="font-semibold">{change.novo || '—'}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                );
                                            }

                                            if (pe.status === 'invalidated' || pe.status === 'error') {
                                                return (
                                                    <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-red-600 flex items-center gap-1.5 mb-1">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                                                            {pe.status === 'error' ? 'Erro na edição' : 'Edição bloqueada'}
                                                        </p>
                                                        <p className="text-[10px] text-red-600">{pe.errorMessage ?? 'Operação indisponível.'}</p>
                                                    </div>
                                                );
                                            }

                                            if (pe.status === 'cancelled') {
                                                return (
                                                    <div className="mt-3 p-3 bg-slate-50 border border-[#e5e7eb] dark:border-white/10 rounded-lg">
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                            Edição cancelada
                                                        </p>
                                                    </div>
                                                );
                                            }

                                            // status === 'pending'
                                            return (
                                                <div className="mt-3 p-3 bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg shadow-sm">
                                                    <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700 flex items-center gap-1.5 mb-2">
                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                        Edição pendente
                                                    </p>
                                                    <p className="text-[10px] font-semibold text-slate-700 truncate mb-2">{pe.titulo}</p>
                                                    <div className="space-y-1.5 mb-3">
                                                        {Object.entries(pe.alteracoes).map(([campo, change]) => (
                                                            <div key={campo} className="grid grid-cols-[80px_1fr_1fr] gap-1 text-[9px]">
                                                                <span className="font-black text-slate-500 uppercase">{FIELD_LABELS[campo] ?? campo}</span>
                                                                <span className="text-slate-400 truncate line-through">{change.original || '—'}</span>
                                                                <span className="text-emerald-700 font-semibold truncate">{change.novo || '—'}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                    <div className="flex gap-2 pt-2 border-t border-amber-100">
                                                        <button
                                                            onClick={() => handleConfirmEdit(mid, pe)}
                                                            disabled={isProcessing}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                                                        >
                                                            {isProcessing ? (
                                                                <span className="w-2.5 h-2.5 border-2 border-white/40 border-t-white rounded-lg animate-spin" />
                                                            ) : (
                                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                            )}
                                                            Confirmar
                                                        </button>
                                                        <button
                                                            onClick={() => handleCancelEdit(mid)}
                                                            disabled={isProcessing}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white text-slate-400 border border-[#e5e7eb] dark:border-white/10 text-[10px] font-bold uppercase tracking-wider hover:bg-slate-100 hover:text-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                                                        >
                                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                            Cancelar
                                                        </button>
                                                    </div>
                                                </div>
                                            );
                                        })()}

                                        {/* Card de confirmação de reagendamento em lote */}
                                        {msg.pendingBatchReschedule && msg.id && (() => {
                                            const br = msg.pendingBatchReschedule!;
                                            const mid = msg.id!;
                                            const isProcessing = loadingBatchRescheduleId === mid;

                                            if (br.status === 'completed') {
                                                return (
                                                    <div className="mt-3 p-3 bg-emerald-50 border border-[#e5e7eb] dark:border-white/10 rounded-lg">
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 flex items-center gap-1.5 mb-2">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                            {br.items.length} ações reagendadas
                                                        </p>
                                                        <div className="space-y-1 mt-1">
                                                            {br.items.map(item => (
                                                                <div key={item.task_id} className="text-[9px] text-emerald-600 flex gap-1 flex-wrap">
                                                                    <span className="font-semibold truncate max-w-[140px]">{item.titulo}</span>
                                                                    <span className="opacity-60 line-through">{item.data_limite_original || '—'}</span>
                                                                    <span>→</span>
                                                                    <span className="font-black">{item.nova_data_limite}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                );
                                            }

                                            if (br.status === 'error') {
                                                return (
                                                    <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-red-600 flex items-center gap-1.5 mb-1">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                                                            Erro no reagendamento
                                                        </p>
                                                        <p className="text-[10px] text-red-600">{br.errorMessage ?? 'Operação indisponível.'}</p>
                                                    </div>
                                                );
                                            }

                                            if (br.status === 'cancelled') {
                                                return (
                                                    <div className="mt-3 p-3 bg-slate-50 border border-[#e5e7eb] dark:border-white/10 rounded-lg">
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                            Reagendamento cancelado
                                                        </p>
                                                    </div>
                                                );
                                            }

                                            // status === 'pending'
                                            return (
                                                <div className="mt-3 p-3 bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg shadow-sm">
                                                    <p className="text-[10px] font-bold uppercase tracking-wider text-blue-700 flex items-center gap-1.5 mb-1">
                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                                                        Reagendamento em lote — {br.items.length} ações
                                                    </p>
                                                    <p className="text-[9px] text-slate-500 mb-2 italic">{br.justificativa}</p>
                                                    <div className="space-y-1 mb-3 max-h-48 overflow-y-auto pr-1">
                                                        {br.items.map((item, idx) => (
                                                            <div key={item.task_id} className="grid grid-cols-[16px_1fr_72px_8px_72px] gap-1 items-center text-[9px]">
                                                                <span className="text-slate-300 font-sans">{idx + 1}.</span>
                                                                <span className="text-slate-600 font-semibold truncate">{item.titulo}</span>
                                                                <span className="text-slate-400 line-through text-right">{item.data_limite_original || '—'}</span>
                                                                <span className="text-slate-300">→</span>
                                                                <span className="text-blue-700 font-black">{item.nova_data_limite}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                    <div className="flex gap-2 pt-2 border-t border-blue-100">
                                                        <button
                                                            onClick={() => handleConfirmBatchReschedule(mid, br)}
                                                            disabled={isProcessing}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-[10px] font-bold uppercase tracking-wider hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                                                        >
                                                            {isProcessing ? (
                                                                <span className="w-2.5 h-2.5 border-2 border-white/40 border-t-white rounded-lg animate-spin" />
                                                            ) : (
                                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                            )}
                                                            Confirmar tudo
                                                        </button>
                                                        <button
                                                            onClick={() => handleCancelBatchReschedule(mid)}
                                                            disabled={isProcessing}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white text-slate-400 border border-[#e5e7eb] dark:border-white/10 text-[10px] font-bold uppercase tracking-wider hover:bg-slate-100 hover:text-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                                                        >
                                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                            Cancelar
                                                        </button>
                                                    </div>
                                                </div>
                                            );
                                        })()}

                                        {msg.pendingMemoryConflict && msg.id && (() => {
                                            const conflict = msg.pendingMemoryConflict!;
                                            const mid = msg.id!;
                                            const isProcessing = loadingMemoryConflictId === mid;

                                            if (conflict.status_ui === 'resolved') {
                                                return (
                                                    <div className="mt-3 p-3 bg-emerald-50 border border-[#e5e7eb] dark:border-white/10 rounded-lg">
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 flex items-center gap-1.5 mb-2">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                            Conflito resolvido
                                                        </p>
                                                        <p className="text-[10px] text-emerald-700 font-semibold">
                                                            A nova memória substituiu a versão anterior.
                                                        </p>
                                                    </div>
                                                );
                                            }

                                            if (conflict.status_ui === 'kept') {
                                                return (
                                                    <div className="mt-3 p-3 bg-slate-50 border border-[#e5e7eb] dark:border-white/10 rounded-lg">
                                                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5 mb-2">
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                            Conflito encerrado
                                                        </p>
                                                        <p className="text-[10px] text-slate-600 font-semibold">
                                                            A memória antiga foi mantida como fonte de verdade.
                                                        </p>
                                                    </div>
                                                );
                                            }

                                            return (
                                                <div className="mt-3 p-3 bg-white border border-[#e5e7eb] dark:border-white/10 rounded-lg shadow-sm">
                                                    <p className="text-[10px] font-bold uppercase tracking-wider text-violet-700 flex items-center gap-1.5 mb-2">
                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                                                        Conflito de Memória
                                                    </p>
                                                    <p className="text-[10px] text-slate-600 mb-3">
                                                        O Hermes encontrou duas versões muito parecidas e precisa de uma decisão explícita.
                                                    </p>
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                                                        <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-slate-50 p-3">
                                                            <p className="text-[9px] font-bold uppercase tracking-wider text-slate-500 mb-2">Versão Antiga</p>
                                                            <p className="text-[11px] text-slate-700 leading-relaxed whitespace-pre-wrap">{conflict.existing_text}</p>
                                                        </div>
                                                        <div className="rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-emerald-50 p-3">
                                                            <p className="text-[9px] font-bold uppercase tracking-wider text-emerald-700 mb-2">Versão Nova</p>
                                                            <p className="text-[11px] text-emerald-900 leading-relaxed whitespace-pre-wrap">{conflict.proposed_text}</p>
                                                        </div>
                                                    </div>
                                                    <div className="flex flex-wrap gap-2 pt-2 border-t border-violet-100">
                                                        <button
                                                            onClick={() => handleResolveMemoryConflict(mid, conflict, 'manter_existente')}
                                                            disabled={isProcessing}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white text-slate-700 border border-[#e5e7eb] dark:border-white/10 text-[10px] font-bold uppercase tracking-wider hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                                                        >
                                                            {isProcessing ? <span className="w-2.5 h-2.5 border-2 border-slate-300 border-t-slate-700 rounded-lg animate-spin" /> : null}
                                                            Manter Antiga
                                                        </button>
                                                        <button
                                                            onClick={() => handleResolveMemoryConflict(mid, conflict, 'substituir_pelo_novo')}
                                                            disabled={isProcessing}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                                                        >
                                                            {isProcessing ? <span className="w-2.5 h-2.5 border-2 border-white/40 border-t-white rounded-lg animate-spin" /> : null}
                                                            Manter Nova
                                                        </button>
                                                    </div>
                                                </div>
                                            );
                                        })()}

                                        {/* Proposta de Diagnóstico de Código */}
                                        {msg.proposedDiagnosis && (
                                            <div className="mt-4 p-4 bg-white rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-sm">
                                                <p className="text-[10px] font-bold uppercase tracking-wider text-blue-600 flex items-center gap-2 mb-2">
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                                                    Diagnóstico de Código
                                                    <span className={`ml-auto text-[8px] font-black uppercase px-1.5 py-0.5 rounded ${msg.proposedDiagnosis.mode === 'snippet' ? 'bg-amber-100 text-amber-600' : 'bg-blue-50 text-blue-500'}`}>
                                                        {msg.proposedDiagnosis.mode === 'snippet' ? 'Snippet' : 'Repositório'}
                                                    </span>
                                                </p>
                                                <div className="space-y-1.5 mb-4">
                                                    {msg.proposedDiagnosis.mode === 'repo' && msg.proposedDiagnosis.sistemaId && (
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-[9px] font-black text-blue-500 uppercase bg-blue-50 px-1.5 py-0.5 rounded">Sistema</span>
                                                            <span className="text-[11px] font-bold text-slate-700">{msg.proposedDiagnosis.sistemaId}</span>
                                                        </div>
                                                    )}
                                                    {msg.proposedDiagnosis.mode === 'snippet' && msg.proposedDiagnosis.fileName && (
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-[9px] font-black text-amber-600 uppercase bg-amber-50 px-1.5 py-0.5 rounded">Arquivo</span>
                                                            <span className="text-[11px] font-sans text-slate-600">{msg.proposedDiagnosis.fileName}</span>
                                                        </div>
                                                    )}
                                                    <p className="text-[11px] text-slate-600 leading-relaxed">{msg.proposedDiagnosis.descricaoProblema}</p>
                                                    {msg.proposedDiagnosis.mode === 'snippet' && msg.proposedDiagnosis.codeSnippet && (
                                                        <pre className="text-[9px] font-sans text-slate-500 bg-slate-50 border border-[#e5e7eb] dark:border-white/10 rounded p-2 max-h-24 overflow-hidden relative">
                                                            {msg.proposedDiagnosis.codeSnippet.slice(0, 300)}
                                                            {msg.proposedDiagnosis.codeSnippet.length > 300 && (
                                                                <span className="absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-slate-50 to-transparent block" />
                                                            )}
                                                        </pre>
                                                    )}
                                                </div>
                                                <div className="flex gap-2">
                                                    <button
                                                        onClick={() => handleConfirmDiagnosis(msg.proposedDiagnosis!, msg.id)}
                                                        disabled={diagnosingId === msg.id}
                                                        className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-1.5"
                                                    >
                                                        {diagnosingId === msg.id ? (
                                                            <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-lg animate-spin" />
                                                        ) : (
                                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                        )}
                                                        {diagnosingId === msg.id ? 'Analisando...' : (msg.proposedDiagnosis.mode === 'snippet' ? 'Analisar Snippet' : 'Analisar Repositório')}
                                                    </button>
                                                    <button
                                                        onClick={() => { setInput(`Ajustar diagnóstico: `); setTimeout(() => textareaRef.current?.focus(), 50); }}
                                                        className="flex-1 bg-slate-100 text-slate-500 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-slate-200 transition-all flex items-center justify-center gap-1.5"
                                                    >
                                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                        Ajustar
                                                    </button>
                                                </div>
                                            </div>
                                        )}


                                        {/* Proposta de Rascunho de Formulário */}
                                        {msg.proposedForm && (() => {
                                            // "State Lock": only enable if this is the LAST form draft in the entire session.
                                            // That means we find the last message index that has a proposedForm.
                                            const lastFormIndex = messages.reduce((acc, m, idx) => m.proposedForm ? idx : acc, -1);
                                            const isLatestForm = i === lastFormIndex;
                                            const isProcessing = creatingFormId === msg.id;

                                            return (
                                                <div className="mt-4 p-4 bg-white rounded-lg border border-[#e5e7eb] dark:border-white/10 shadow-sm">
                                                    <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 flex items-center gap-2 mb-1">
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                                                        Rascunho de Formulário
                                                    </p>
                                                    <p className="text-[11px] font-bold text-slate-700 mb-1 truncate">{msg.proposedForm.titulo}</p>
                                                    {msg.proposedForm.descricao && <p className="text-[10px] text-slate-500 mb-3">{msg.proposedForm.descricao}</p>}
                                                    <div className="space-y-2 mb-4 max-h-52 overflow-y-auto pr-1">
                                                        {msg.proposedForm.perguntas.map((q, idx) => (
                                                            <div key={idx} className="p-2 rounded-lg bg-emerald-50 border border-emerald-100">
                                                                <div className="flex items-center gap-1.5 mb-1">
                                                                    <span className="text-[9px] font-black text-emerald-500 uppercase">{q.tipo.replace('_', ' ')}</span>
                                                                    {q.obrigatoria && <span className="text-[9px] text-red-500 font-bold">*</span>}
                                                                </div>
                                                                <p className="text-[10px] font-bold text-slate-700 leading-tight">{q.texto}</p>
                                                                {q.opcoes && q.opcoes.length > 0 && (
                                                                    <ul className="mt-1 space-y-0.5">
                                                                        {q.opcoes.map((opt, optIdx) => (
                                                                            <li key={optIdx} className="text-[9px] text-slate-500 flex gap-1">
                                                                                <span className="text-emerald-400">•</span>{opt}
                                                                            </li>
                                                                        ))}
                                                                    </ul>
                                                                )}
                                                                {q.tipo === 'escala_linear' && (
                                                                    <p className="text-[9px] text-slate-500 mt-1">Escala de {q.escala_min || 1} a {q.escala_max || 5}</p>
                                                                )}
                                                            </div>
                                                        ))}
                                                    </div>
                                                    {isLatestForm ? (
                                                        <div className="flex gap-2">
                                                            <button
                                                                onClick={() => handleConfirmForm(msg.proposedForm!, msg.id)}
                                                                disabled={isProcessing}
                                                                className="flex-1 bg-emerald-600 text-white py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-1.5"
                                                            >
                                                                {isProcessing ? (
                                                                    <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-lg animate-spin" />
                                                                ) : (
                                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                                )}
                                                                Confirmar e Gerar Link
                                                            </button>
                                                            <button
                                                                onClick={() => { setInput('Ajustar formulário: '); setTimeout(() => textareaRef.current?.focus(), 50); }}
                                                                disabled={isProcessing}
                                                                className="flex-1 bg-slate-100 text-slate-500 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-slate-200 disabled:opacity-50 transition-all flex items-center justify-center gap-1.5"
                                                            >
                                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                                Ajustar
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <div className="text-center p-2 rounded-lg bg-slate-50 border border-slate-100">
                                                            <p className="text-[10px] font-bold text-slate-400">Esta versão foi superada por um rascunho mais recente.</p>
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })()}

                                        {messageTimestamp && (
                                            <div className={`mt-2 flex justify-end text-[9px] font-medium opacity-0 transition-opacity group-hover:opacity-100 ${msg.role === 'user'
                                                ? 'text-white/65'
                                                : isDark ? 'text-slate-400' : 'text-slate-400'
                                                }`}>
                                                <span>{messageTimestamp}</span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )
                        })}

                        {/* Indicador de loading com mensagem de fase */}
                        {isBlocked && (
                            <div className="flex justify-start flex-col gap-2">
                                <div className="px-4 py-3 rounded-lg rounded-bl-none bg-slate-100 flex flex-col gap-2">
                                    <div className="flex gap-1.5 items-center">
                                        <span className="w-2 h-2 bg-blue-600 rounded-lg animate-bounce" />
                                        <span className="w-2 h-2 bg-blue-600 rounded-lg animate-bounce" style={{ animationDelay: '0.1s' }} />
                                        <span className="w-2 h-2 bg-blue-600 rounded-lg animate-bounce" style={{ animationDelay: '0.2s' }} />
                                        {uploadPhase !== 'idle' && (
                                            <span className="text-[10px] font-bold text-slate-500 ml-2">
                                                {uploadPhaseLabel[uploadPhase]}
                                            </span>
                                        )}
                                        {uploadPhase === 'idle' && copilotStatus && (
                                            <span className="text-[10px] font-bold text-slate-500 ml-2">
                                                {copilotStatus}
                                            </span>
                                        )}
                                    </div>
                                    <button
                                        onClick={() => {
                                            isCancelledRef.current = true;
                                            abortControllerRef.current?.abort();
                                            setIsLoading(false);
                                            setUploadPhase('idle');
                                            setProgressWidth(0);
                                        }}
                                        className="mt-1 self-start px-2.5 py-1 rounded-lg bg-white/50 hover:bg-white text-[9px] font-bold uppercase tracking-wider text-slate-400 hover:text-red-500 transition-all flex items-center gap-1 shadow-sm"
                                    >
                                        <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                        Cancelar
                                    </button>
                                    {/* Barra de progresso — visível apenas nas fases de upload/processamento */}
                                    {uploadPhase !== 'idle' && (
                                        <div className="w-48 h-1 bg-slate-200 rounded-lg overflow-hidden">
                                            <div
                                                className="h-full bg-blue-500 rounded-lg"
                                                style={{
                                                    width: `${progressWidth}%`,
                                                    transition: progressTransition.current
                                                }}
                                            />
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                        <div ref={chatEndRef} />
                    </div>

                    {/* Footer Input */}
                    <div className={`shrink-0 border-t p-2 sm:p-4 relative ${isDark ? 'bg-[#0f1724] border-white/10' : 'bg-white border-slate-100'}`}>
                        {/* Sugestão de Prompt Proativa - Posicionada no container externo para largura total */}
                        {suggestedPrompt && !input.trim() && messages.length === 0 && (
                            <div className="absolute bottom-full left-0 mb-4 w-full px-3 z-50">
                                <button
                                    onClick={() => {
                                        if (!currentSessionId) {
                                            handleCreateSession(suggestedPrompt);
                                        } else {
                                            sendMessage(suggestedPrompt);
                                        }
                                        setSuggestedPrompt(null);
                                    }}
                                    className={`w-full group flex items-center justify-between p-4 gap-4 rounded-lg border transition-all text-left shadow-lg ${isDark
                                        ? 'bg-[#0f1724] border-blue-500/30 hover:bg-blue-500/10 hover:border-blue-500/50'
                                        : 'bg-white border-blue-200 hover:bg-blue-50 hover:border-blue-300'
                                        }`}
                                >
                                    <div className="flex-1 flex flex-col gap-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-1 h-1 rounded-lg ${isDark ? 'bg-blue-400' : 'bg-blue-600'} animate-pulse`} />
                                            <span className={`text-[7px] font-black uppercase tracking-[0.2em] font-sans ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Sugestão Estratégica IA</span>
                                        </div>
                                        <p className={`text-[11px] font-sans leading-relaxed ${isDark ? 'text-blue-100/70 group-hover:text-white' : 'text-slate-600 group-hover:text-blue-900'}`}>
                                            {suggestedPrompt}
                                        </p>
                                    </div>
                                    <svg className={`w-4 h-4 shrink-0 ${isDark ? 'text-blue-400/30' : 'text-blue-300'} group-hover:translate-x-1 transition-transform`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14 5l7 7-7 7" />
                                    </svg>
                                </button>
                            </div>
                        )}

                        {/* Banner de erro inline */}
                        {footerError && (
                            <div className="flex items-start gap-2 mb-3 px-3 py-2.5 rounded-lg text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                                <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                                </svg>
                                <span className="flex-1 leading-relaxed break-words">{footerError}</span>
                                <button
                                    onClick={() => setFooterError(null)}
                                    className="shrink-0 hover:text-red-900 transition-colors mt-0.5"
                                    title="Fechar"
                                >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>
                        )}

                        {/* Banner de transcrição de áudio */}
                        {isTranscribing && (
                            <div className="flex items-center gap-2 mb-3 px-3 py-2.5 rounded-lg text-xs font-semibold bg-violet-50 text-violet-700 border border-[#e5e7eb] dark:border-white/10">
                                <svg className="w-4 h-4 shrink-0 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m12.728 0l-.707-.707M6.343 6.343l-.707-.707" />
                                </svg>
                                <span>Transcrevendo áudio...</span>
                            </div>
                        )}

                        {/* Badge de arquivo anexado */}
                        {(attachedFile || pastedContext) && !isBlocked && (
                            <div className={`flex items-center gap-2 mb-3 px-3 py-2 rounded-lg text-xs font-semibold ${isDark ? 'bg-blue-900/40 text-blue-300' : 'bg-blue-50 text-blue-700 border border-[#e5e7eb] dark:border-white/10'}`}>
                                <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                                </svg>
                                <span className="truncate flex-1">{attachedFile?.name ?? pastedContext?.name}</span>
                                <button
                                    onClick={handleRemoveFile}
                                    className="shrink-0 hover:text-red-500 transition-colors"
                                    title="Remover arquivo"
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>
                        )}

                        <div className={`relative z-20 flex items-end gap-1 rounded-lg border px-2 py-2 shadow-sm transition-all ${
                            isDark
                                ? 'border-[#e5e7eb] dark:border-white/10 bg-[#0f0f1a] focus-within:border-blue-500'
                                : 'border-[#e5e7eb] dark:border-white/10 bg-white focus-within:border-blue-500'
                        }`}>
                            {/* Input de arquivo oculto */}
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept={COPILOTO_FILE_ACCEPT}
                                className="hidden"
                                onChange={handleFileSelect}
                            />

                            {/* Botão + (anexar) */}
                            <button
                                onClick={() => !isBlocked && fileInputRef.current?.click()}
                                disabled={isBlocked}
                                title="Anexar arquivo"
                                className={`flex h-9 w-9 items-center justify-center rounded-lg transition-all flex-shrink-0 ${
                                    (attachedFile || pastedContext)
                                        ? 'bg-blue-500/10 text-blue-500'
                                        : isDark
                                            ? 'text-white/55 hover:bg-white/10 hover:text-white/85'
                                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'
                                } disabled:opacity-30 disabled:cursor-not-allowed`}
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v14m-7-7h14" />
                                </svg>
                            </button>

                            {/* Botão de atalhos */}
                            <div className="relative flex-shrink-0" ref={toolMenuRef}>
                                <button
                                    onClick={() => setShowToolMenu(prev => !prev)}
                                    disabled={isBlocked}
                                    aria-label="POPs Cadastrados"
                                    aria-expanded={showToolMenu}
                                    title="POPs Cadastrados"
                                    className={`flex h-9 w-9 items-center justify-center rounded-lg transition-all ${isDark ? 'text-white/55 hover:bg-white/10 hover:text-white/85' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'} disabled:opacity-30 disabled:cursor-not-allowed`}
                                >
                                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                        <circle cx="5" cy="5" r="1.8" />
                                        <circle cx="12" cy="5" r="1.8" />
                                        <circle cx="19" cy="5" r="1.8" />
                                        <circle cx="5" cy="12" r="1.8" />
                                        <circle cx="12" cy="12" r="1.8" />
                                        <circle cx="19" cy="12" r="1.8" />
                                        <circle cx="5" cy="19" r="1.8" />
                                        <circle cx="12" cy="19" r="1.8" />
                                        <circle cx="19" cy="19" r="1.8" />
                                    </svg>
                                </button>
                                {showToolMenu && (
                                    <div className={`absolute bottom-full left-0 mb-2 z-[80] min-w-[280px] max-w-[min(24rem,calc(100vw-2rem))] max-h-[min(28rem,calc(100vh-14rem))] overflow-y-auto overflow-x-hidden rounded-2xl border shadow-lg ${isDark ? 'border-[#e5e7eb] dark:border-white/10 bg-[#101827]' : 'border-[#e5e7eb] dark:border-white/10 bg-white'}`}>
                                        <div className={`sticky top-0 z-10 px-3 py-2 text-[9px] font-black uppercase tracking-[0.2em] ${isDark ? 'border-b border-[#e5e7eb] dark:border-white/10 bg-[#101827] text-white/40' : 'border-b border-slate-100 bg-white text-slate-400'}`}>
                                            POPs Cadastrados
                                        </div>
                                        <div className="p-2">
                                            {popsList.length === 0 ? (
                                                <div className={`px-3 py-4 text-center text-xs font-medium ${isDark ? 'text-white/40' : 'text-slate-400'}`}>Nenhum POP cadastrado</div>
                                            ) : (
                                                popsList.map(pop => {
                                                    const gatilho = pop.gatilhos && pop.gatilhos.length > 0 ? pop.gatilhos[0] : pop.titulo;
                                                    return (
                                                        <button
                                                            key={pop.id}
                                                            type="button"
                                                            onClick={() => insertPopShortcut(pop)}
                                                            className={`w-full rounded-lg px-3 py-2 text-left transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-50'}`}
                                                        >
                                                            <div className={`text-[11px] font-black leading-normal ${isDark ? 'text-white' : 'text-slate-900'}`}>{pop.titulo}</div>
                                                            <div className="mt-1.5 flex items-center">
                                                                <span className={`inline-block max-w-full truncate rounded px-1.5 py-0.5 text-[9px] font-mono font-bold ${isDark ? 'bg-blue-500/10 text-blue-300' : 'bg-blue-50 text-blue-600'}`}>{gatilho}</span>
                                                            </div>
                                                            {pop.gatilhos && pop.gatilhos.length > 1 && (
                                                                <p className={`mt-1 text-[10px] leading-relaxed truncate ${isDark ? 'text-white/50' : 'text-slate-500'}`}>
                                                                    Gatilhos: {pop.gatilhos.join(', ')}
                                                                </p>
                                                            )}
                                                        </button>
                                                    );
                                                })
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Textarea */}
                            <div className="relative flex-1 min-w-0">
                                {/* Mention popup */}
                                {mention.visible && (
                                    <div className="absolute bottom-full left-0 mb-2 w-full max-h-52 overflow-y-auto rounded-lg border border-[#e5e7eb] dark:border-white/10 bg-white shadow-xl z-50">
                                        <div className="px-3 py-1.5 border-b border-slate-100 sticky top-0 bg-white">
                                            <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Referenciar do Diário de Bordo</span>
                                        </div>
                                        {mention.filtered.map((item, idx) => (
                                            <button
                                                key={item.id || `mention-${idx}`}
                                                onMouseDown={e => { e.preventDefault(); selectMention(item); }}
                                                className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors ${idx === mention.selectedIndex ? 'bg-blue-50' : 'hover:bg-slate-50'}`}
                                            >
                                                <span className="text-base shrink-0">
                                                    {item.tipo === 'arquivo' ? '📄' : '🔗'}
                                                </span>
                                                <div className="min-w-0 flex-1">
                                                    <p className="text-xs font-semibold text-slate-800 truncate">{item.nome || item.valor}</p>
                                                    <p className="text-[10px] text-slate-400 truncate">{item.tipo === 'arquivo' ? 'Arquivo' : item.valor}</p>
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                )}

                                <textarea
                                    ref={textareaRef}
                                    rows={1}
                                    value={input}
                                    onChange={e => {
                                        const val = e.target.value;
                                        setInput(val);
                                        if (taskPoolItems.length === 0) return;
                                        const cursor = e.target.selectionStart ?? val.length;
                                        const textBefore = val.slice(0, cursor);
                                        const atMatch = textBefore.match(/@([\w ]*)$/);
                                        if (atMatch) {
                                            const query = atMatch[1].toLowerCase().trim();
                                            const filtered = taskPoolItems.filter(item =>
                                                !query || (item.nome || item.valor || '').toLowerCase().includes(query)
                                            );
                                            if (filtered.length > 0) {
                                                setMention({ visible: true, query: atMatch[1], atIndex: cursor - atMatch[0].length, filtered, selectedIndex: 0 });
                                                return;
                                            }
                                        }
                                        setMention(prev => ({ ...prev, visible: false }));
                                    }}
                                    onFocus={() => setIsFocused(true)}
                                    onPaste={handlePaste}
                                    disabled={isBlocked}
                                    onKeyDown={e => {
                                        if (mention.visible) {
                                            if (e.key === 'ArrowDown') { e.preventDefault(); setMention(prev => ({ ...prev, selectedIndex: Math.min(prev.selectedIndex + 1, prev.filtered.length - 1) })); return; }
                                            if (e.key === 'ArrowUp') { e.preventDefault(); setMention(prev => ({ ...prev, selectedIndex: Math.max(prev.selectedIndex - 1, 0) })); return; }
                                            if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); if (mention.filtered[mention.selectedIndex]) selectMention(mention.filtered[mention.selectedIndex]); return; }
                                            if (e.key === 'Escape') { setMention(prev => ({ ...prev, visible: false })); return; }
                                        }
                                        if (e.key === 'Enter' && !e.shiftKey && window.innerWidth >= 640) {
                                            e.preventDefault();
                                            if (!currentSessionId) {
                                                handleCreateSession(input);
                                            } else {
                                                sendMessage(input);
                                            }
                                        }
                                    }}
                                    placeholder={voiceStream.status === 'live' ? `🔊 ${voiceStreamStatusMessage || 'Conversa ao vivo — pode falar'}` : voiceStream.status === 'connecting' ? '🔊 Conectando à voz ao vivo…' : isRecording ? '🎙 Gravando… clique no microfone para parar' : isProcessingMic ? 'Transcrevendo áudio...' : isTranscribing ? 'Transcrevendo áudio...' : attachedFile ? 'Pergunte sobre o arquivo ou envie sem texto…' : pastedContext ? 'Pergunte sobre o contexto ou envie sem texto…' : isFinancialCopilot ? 'Pergunte sobre gastos, fluxo, reserva ou investimentos' : 'Escreva Aqui'}
                                    className={`w-full px-2 pt-2.5 pb-1.5 text-sm leading-5 font-sans font-medium outline-none border-0 resize-none bg-transparent ${isDark ? 'text-white placeholder:text-white/20' : 'text-slate-700 placeholder:text-slate-400'} transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed`}
                                />
                            </div>

                            {/* Botão de conversa por voz ao vivo (Gemini Live) */}
                            <button
                                onClick={async () => {
                                    if (voiceStream.status === 'idle' || voiceStream.status === 'error') {
                                        if (!currentSessionIdRef.current) {
                                            await handleCreateSession();
                                        }
                                        voiceStream.start();
                                    } else {
                                        voiceStream.stop();
                                    }
                                }}
                                disabled={isRecording}
                                title={
                                    voiceStream.status === 'live' ? 'Encerrar conversa por voz'
                                        : voiceStream.status === 'connecting' ? 'Conectando…'
                                            : 'Conversar por voz (tempo real)'
                                }
                                className={`flex h-9 w-9 items-center justify-center rounded-lg transition-all active:scale-95 flex-shrink-0 ${
                                    voiceStream.status === 'live'
                                        ? 'bg-emerald-500 text-white animate-pulse hover:bg-emerald-600'
                                        : voiceStream.status === 'connecting'
                                            ? 'bg-amber-400 text-white'
                                            : isDark
                                                ? 'bg-white/10 text-white/60 hover:bg-white/20 hover:text-white'
                                                : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700'
                                } disabled:opacity-30 disabled:cursor-not-allowed`}
                            >
                                {voiceStream.status === 'connecting' ? (
                                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" /></svg>
                                ) : (
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4h16v11H7.17L4 18.17V4Zm2 2v8.17L6.17 13H18V6H6Z" />
                                    </svg>
                                )}
                            </button>

                            {/* Botão de gravação (sempre visível) */}
                            <button
                                onClick={() => isRecording ? stopRecording() : startRecording()}
                                disabled={isBlocked && !isRecording}
                                title={isRecording ? 'Parar gravação' : 'Gravar Áudio'}
                                className={`flex h-9 w-9 items-center justify-center rounded-lg transition-all active:scale-95 flex-shrink-0 ${
                                    isRecording
                                        ? 'bg-red-500 text-white animate-pulse hover:bg-red-600'
                                        : isDark
                                            ? 'bg-white/10 text-white/60 hover:bg-white/20 hover:text-white'
                                            : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700'
                                } disabled:opacity-30 disabled:cursor-not-allowed`}
                            >
                                {isProcessingMic ? (
                                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" /></svg>
                                ) : (
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 10v2a7 7 0 01-14 0v-2m14 0h2m-16 0H3m9 10v3m-3 0h6" />
                                    </svg>
                                )}
                            </button>

                            {/* Botão de envio (visível se houver texto/anexos e não gravando) */}
                            {(input.trim() || attachedFile || pastedContext) && !isRecording && (
                                <button
                                    onClick={() => {
                                        if (!currentSessionId) {
                                            handleCreateSession(input);
                                        } else {
                                            sendMessage(input);
                                        }
                                    }}
                                    disabled={isBlocked}
                                    title="Enviar"
                                    className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white shadow-lg hover:bg-blue-700 disabled:opacity-40 transition-all active:scale-95 flex-shrink-0"
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2.5">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                                    </svg>
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
