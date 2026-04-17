
import React, { useState, useEffect, useRef } from 'react';
import { db, functions, auth } from '@/firebase';
import { httpsCallable } from 'firebase/functions';
import { collection, onSnapshot, query, orderBy, where, addDoc, doc, updateDoc, getDoc, getDocs, writeBatch, deleteDoc, limit, Timestamp } from 'firebase/firestore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { formatDate, PoolItem } from '@/types';
import { ReportModal } from './ReportModal';
import { isInternalAppHref, navigateWithinApp } from '../../utils/internalNavigation';

// URL do endpoint HTTP de upload (Node.js Functions)
const UPLOAD_ENDPOINT = 'https://us-central1-gestao-hermes.cloudfunctions.net/uploadFileForCopiloto';

interface SlideItem {
    ordem: number;
    tipo_layout: 'Capa' | 'Conteudo';
    titulo: string;
    subtitulo: string;
    topicos: string[];
    sugestao_imagem: string;
}

interface ProposedPresentation {
    temaGeral: string;
    slides: SlideItem[];
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
    isArtifact?: boolean;
    proposedPlan?: any[];
    proposedPresentation?: ProposedPresentation;
    proposedDiagnosis?: DiagnosisRequest;
    timestamp: any;
    type?: 'text' | 'plan_proposal';
    toolsUsed?: string[];
    pendingEdit?: PendingEdit;
    reportId?: string;
}

const TOOL_LABELS: Record<string, string> = {
    consultar_historico_acoes: 'Grafo de Execução',
    buscar_arquivos_acervo: 'Acervo de Documentos',
    obter_contexto_tela: 'Contexto da Tarefa',
    pesquisar_internet: 'Internet',
    ler_pagina_web: 'Leitura de Página',
    ler_documento_na_integra: 'Leitura de Documento',
    resolver_conflito_procedimento: 'Resolução de Conflito',
    criar_acao_no_sistema: 'Criando Ação',
    editar_plano_acao: 'Ajustando Plano...',
    preparar_edicao_acao: 'Preparando Edição',
    gerar_relatorio: 'Gerando Relatório',
};

const FIELD_LABELS: Record<string, string> = {
    titulo: 'Título',
    descricao: 'Descrição',
    data_limite: 'Prazo',
    status: 'Status',
    tags: 'Tags',
    area_tematica: 'Área Temática',
    tipo_acao: 'Tipo de Ação',
    notas: 'Notas',
};

// Ferramentas de escrita/mutação — recebem estilo verde
const WRITE_TOOLS = new Set(['criar_acao_no_sistema', 'editar_plano_acao', 'preparar_edicao_acao']);

interface Session {
    id: string;
    title: string;
    createdAt: any;
    lastMessageAt: any;
    taskId?: string;
    systemId?: string;
}

interface HermesCopilotoDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    taskId?: string;
    systemId?: string;
    isDark?: boolean;
    userId: string;
    onOpenTask?: (taskId: string) => void;
    onOpenTool?: (tool: string, id: string) => void;
}

type UploadPhase = 'idle' | 'uploading' | 'processing';
const MOBILE_BREAKPOINT = 768;

export const HermesCopilotoDrawer: React.FC<HermesCopilotoDrawerProps> = ({
    isOpen, onClose, taskId, systemId, isDark = false, userId, onOpenTask, onOpenTool
}) => {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    const [sessionPendingDeleteId, setSessionPendingDeleteId] = useState<string | null>(null);
    const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
    const chatEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // ── Estado do modal de relatório ─────────────────────────────────────────
    const [reportModalOpen, setReportModalOpen] = useState(false);
    const [activeReport, setActiveReport] = useState<{ id: string; titulo: string; markdown: string } | null>(null);
    const [isLoadingReport, setIsLoadingReport] = useState(false);
    const [diagnosisModalOpen, setDiagnosisModalOpen] = useState(false);
    const [activeDiagnosis, setActiveDiagnosis] = useState<DiagnosisRecord | null>(null);
    const [isLoadingDiagnosis, setIsLoadingDiagnosis] = useState(false);

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

    // Estado de anexo
    const [attachedFile, setAttachedFile] = useState<File | null>(null);
    const [uploadPhase, setUploadPhase] = useState<UploadPhase>('idle');
    // Controla a largura da barra de progresso via CSS transition
    const [progressWidth, setProgressWidth] = useState<number>(0);
    const progressTransition = useRef<string>('none');
    // Erro inline no footer (erros antes do Firestore não ficam visíveis no chat)
    const [footerError, setFooterError] = useState<string | null>(null);
    // Estado de transcrição de áudio colado
    const [isTranscribing, setIsTranscribing] = useState(false);

    // Estado para rastrear qual diagnóstico está em processamento
    const [diagnosingId, setDiagnosingId] = useState<string | null>(null);

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
                const minH = isFocused ? 250 : 50;
                const scrollH = textareaRef.current.scrollHeight;
                textareaRef.current.style.height = `${Math.max(minH, Math.min(scrollH, 400))}px`;
            }
        };

        handleResize();

        const handleClickOutside = (e: MouseEvent) => {
            if (textareaRef.current && !textareaRef.current.contains(e.target as Node)) {
                setIsFocused(false);
            }
        };

        if (isFocused) {
            window.addEventListener('mousedown', handleClickOutside);
        }

        return () => window.removeEventListener('mousedown', handleClickOutside);
    }, [input, isFocused]);

    // Load pool_dados from active task for @ mentions
    useEffect(() => {
        if (!taskId) { setTaskPoolItems([]); return; }
        return onSnapshot(doc(db, 'tarefas', taskId), (snap) => {
            if (snap.exists()) {
                const items = ((snap.data().pool_dados as PoolItem[]) || [])
                    .filter(item => item.tipo !== 'telefone');
                setTaskPoolItems(items);
            }
        });
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

        return onSnapshot(q, (snapshot) => {
            const sessList = snapshot.docs.map(doc => ({
                id: doc.id,
                ...doc.data()
            })) as Session[];
            setSessions(sessList);
        });
    }, [userId]);

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

        return onSnapshot(q, (snapshot) => {
            const msgList = snapshot.docs.map(d => ({ id: d.id, ...d.data() })) as Message[];
            setMessages(msgList);
        });
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

    // ── Seleção de arquivo ────────────────────────────────────────────────────
    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0] ?? null;
        setAttachedFile(file);
        // Reset o input para permitir re-selecionar o mesmo arquivo
        e.target.value = '';
    };

    const handleRemoveFile = () => {
        setAttachedFile(null);
    };

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
    const handleConfirmPresentation = async (presentation: ProposedPresentation) => {
        if (!currentSessionId) return;
        try {
            const criarApresentacao = httpsCallable(functions, 'criar_apresentacao_slides', { timeout: 300000 });
            await criarApresentacao({
                sessionId: currentSessionId,
                temaGeral: presentation.temaGeral,
                slides: presentation.slides,
            });
        } catch (err: any) {
            setFooterError('Erro ao gerar apresentação: ' + (err?.message || 'Tente novamente.'));
        }
    };

    const handleConfirmDiagnosis = async (diagnosis: DiagnosisRequest, messageId?: string) => {
        if (!currentSessionId || diagnosingId) return;
        if (messageId) setDiagnosingId(messageId);
        
        try {
            const diagnosticarCodigo = httpsCallable(functions, 'diagnosticar_codigo', { timeout: 300000 });
            await diagnosticarCodigo({
                sessionId: currentSessionId,
                mode: diagnosis.mode,
                descricaoProblema: diagnosis.descricaoProblema,
                taskId: taskId ?? null,
                // repo mode — usa sistemaId do diagnóstico ou, como fallback, o systemId
                // recebido via props do drawer (evita erro "sistemaId é obrigatório")
                ...(diagnosis.mode === 'repo' && {
                    sistemaId: diagnosis.sistemaId ?? systemId ?? '',
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
        const audioFile = files.find(f => f.type.startsWith('audio/'));
        if (!audioFile) return; // sem áudio: deixa o comportamento padrão acontecer

        e.preventDefault();
        setIsTranscribing(true);
        setFooterError(null);

        try {
            const reader = new FileReader();
            reader.readAsDataURL(audioFile);
            reader.onloadend = async () => {
                try {
                    const b64 = (reader.result as string).split(',')[1];
                    // Tenta extrair extensão do nome do arquivo, senão deriva do MIME
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
        };
    }, []);

    // ── Criação de sessão ─────────────────────────────────────────────────────
    const handleCreateSession = async (initialPrompt?: string) => {
        setIsLoading(true);
        try {
            const sessRef = await addDoc(collection(db, 'sessoes_copiloto'), {
                userId,
                title: initialPrompt ? initialPrompt.slice(0, 40) + '...' : 'Nova Conversa',
                createdAt: Timestamp.now(),
                lastMessageAt: Timestamp.now(),
                taskId: taskId || null,
                systemId: systemId || null
            });

            setCurrentSessionId(sessRef.id);
            if (initialPrompt) {
                await sendMessage(initialPrompt, sessRef.id);
            }
        } catch (err) {
            console.error("Erro ao criar sessão:", err);
        } finally {
            setIsLoading(false);
        }
    };

    // ── Envio de mensagem (com ou sem arquivo) ────────────────────────────────
    const sendMessage = async (text: string, sessionId?: string) => {
        const sId = sessionId || currentSessionId;
        const hasFile = !!attachedFile;

        if (!sId || (!text.trim() && !hasFile)) return;

        const fileToSend = attachedFile;
        setInput('');
        setAttachedFile(null);
        setFooterError(null);
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
                    body: formData
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

            // Constrói o conteúdo da mensagem do usuário para o histórico
            const userMessageContent = hasFile && fileToSend
                ? `📎 ${fileToSend.name}${text.trim() ? `\n\n${text.trim()}` : ''}`
                : text;

            // 1. Salva mensagem do usuário no Firestore
            await addDoc(collection(db, 'sessoes_copiloto', sId, 'mensagens'), {
                role: 'user',
                content: userMessageContent,
                timestamp: Timestamp.now()
            });

            // 2. Chama a Cloud Function
            const askCopiloto = httpsCallable(functions, 'askCopilotoHermes', { timeout: 300000 });
            const response = await askCopiloto({
                sessionId: sId,
                prompt: text.trim() || (hasFile ? '' : text),
                taskId: taskId || null,
                systemId: systemId || null,
                driveFileId: driveFileId || null,
                driveFileName: driveFileName || null
            });

            const data = response.data as any;

            // 3. Atualiza título da sessão se for a primeira mensagem
            if (messages.length === 0 && !sessionId) {
                await updateDoc(doc(db, 'sessoes_copiloto', sId), {
                    title: data.suggestedTitle || userMessageContent.slice(0, 40) + '...',
                    lastMessageAt: Timestamp.now()
                });
            } else {
                await updateDoc(doc(db, 'sessoes_copiloto', sId), {
                    lastMessageAt: Timestamp.now()
                });
            }

            // Caminho de sucesso: anima para 100% antes de liberar o input.
            // Só executa aqui — nunca no finally — para não colidir com erros.
            await completeProgress();

        } catch (err: any) {
            console.error("Erro no Copiloto:", err);

            const errMsg: string = err?.message || String(err) || 'Erro desconhecido.';

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
                <div className={`w-full max-w-4xl max-h-[92vh] overflow-hidden rounded-[2rem] shadow-2xl border ${isDark ? 'bg-[#0f0f1a] border-white/10 text-white' : 'bg-white border-slate-200 text-slate-900'}`}>
                    <div className={`flex items-center justify-between gap-4 px-6 py-4 border-b ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                        <div className="min-w-0">
                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-500">Diagnóstico de Código</p>
                            <p className="text-sm font-black truncate">{activeDiagnosis?.descricaoProblema || (isLoadingDiagnosis ? 'Carregando diagnóstico...' : 'Diagnóstico')}</p>
                        </div>
                        <button onClick={() => { setDiagnosisModalOpen(false); setActiveDiagnosis(null); }} className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}>
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                    <div className={`overflow-y-auto max-h-[calc(92vh-88px)] p-6 space-y-5 ${isDark ? 'bg-[#0f0f1a]' : 'bg-slate-50'}`}>
                        {isLoadingDiagnosis && (
                            <div className="flex items-center justify-center py-16">
                                <div className="w-6 h-6 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" />
                            </div>
                        )}
                        {!isLoadingDiagnosis && !activeDiagnosis && (
                            <div className={`rounded-2xl border p-5 text-sm ${isDark ? 'border-white/10 bg-white/5 text-white/70' : 'border-slate-200 bg-white text-slate-500'}`}>
                                Não foi possível carregar este diagnóstico.
                            </div>
                        )}
                        {!isLoadingDiagnosis && activeDiagnosis && (
                            <>
                                <div className={`rounded-2xl border p-5 ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-200 bg-white'}`}>
                                    <div className="flex flex-wrap items-center gap-2 mb-3">
                                        {activeDiagnosis.sistemaId && <span className="text-[10px] font-black uppercase tracking-widest text-blue-600 bg-blue-50 px-2 py-1 rounded-full">{activeDiagnosis.sistemaId}</span>}
                                        {activeDiagnosis.nomeRepositorio && <span className={`text-[10px] font-mono px-2 py-1 rounded-full ${isDark ? 'bg-white/10 text-white/70' : 'bg-slate-100 text-slate-500'}`}>{activeDiagnosis.nomeRepositorio}</span>}
                                        {activeDiagnosis.arquivosAnalisados && <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-full ${isDark ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-50 text-emerald-700'}`}>{activeDiagnosis.arquivosAnalisados.length} arquivo(s)</span>}
                                    </div>
                                    <p className={`text-[11px] font-black uppercase tracking-widest mb-2 ${isDark ? 'text-white/50' : 'text-slate-400'}`}>Diagnóstico</p>
                                    <p className={`text-sm leading-7 whitespace-pre-wrap ${isDark ? 'text-white/80' : 'text-slate-700'}`}>{activeDiagnosis.diagnostico}</p>
                                </div>
                                {activeDiagnosis.blocosSR && activeDiagnosis.blocosSR.length > 0 && (
                                    <div className="space-y-3">
                                        {activeDiagnosis.blocosSR.map((bloco, index) => (
                                            <div key={`${activeDiagnosis.id}_${index}`} className={`rounded-2xl border overflow-hidden ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-200 bg-white'}`}>
                                                <div className={`px-4 py-3 border-b ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-100 bg-slate-50'}`}>
                                                    <p className="text-[11px] font-black">{index + 1}. {bloco.descricao}</p>
                                                    <p className={`text-[10px] font-mono mt-1 ${isDark ? 'text-white/50' : 'text-slate-400'}`}>{bloco.arquivo}</p>
                                                </div>
                                                <div className="p-4 grid gap-4 md:grid-cols-2">
                                                    <div>
                                                        <p className="text-[10px] font-black uppercase tracking-widest text-rose-500 mb-2">Search</p>
                                                        <pre className={`text-[11px] leading-6 overflow-x-auto rounded-xl p-3 ${isDark ? 'bg-rose-500/10 text-white/80' : 'bg-rose-50 text-slate-700'}`}>{bloco.search}</pre>
                                                    </div>
                                                    <div>
                                                        <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600 mb-2">Replace</p>
                                                        <pre className={`text-[11px] leading-6 overflow-x-auto rounded-xl p-3 ${isDark ? 'bg-emerald-500/10 text-white/80' : 'bg-emerald-50 text-slate-700'}`}>{bloco.replace}</pre>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {activeDiagnosis.alertaImpacto && (
                                    <div className={`rounded-2xl border p-4 ${isDark ? 'border-amber-400/20 bg-amber-500/10 text-amber-100' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
                                        <p className="text-[10px] font-black uppercase tracking-widest mb-2">Alerta de Impacto</p>
                                        <p className="text-sm leading-6">{activeDiagnosis.alertaImpacto}</p>
                                    </div>
                                )}
                                {activeDiagnosis.markdownContent && (
                                    <div className={`rounded-2xl border p-5 ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-200 bg-white'}`}>
                                        <p className={`text-[10px] font-black uppercase tracking-widest mb-3 ${isDark ? 'text-white/50' : 'text-slate-400'}`}>Relatório Completo</p>
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{activeDiagnosis.markdownContent}</ReactMarkdown>
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

    const isBlocked = isLoading || uploadPhase !== 'idle' || isTranscribing || isProcessingMic;
    const effectiveDrawerWidth = isMobileViewport ? '100%' : `${drawerWidth}px`;

    return (
        <div
            className={`fixed inset-y-0 right-0 z-[500] shadow-2xl transition-transform duration-300 transform translate-x-0 flex flex-col ${isDark ? 'bg-[#0f0f1a] text-white' : 'bg-white text-slate-900 border-l border-slate-200'}`}
            style={{ width: effectiveDrawerWidth, maxWidth: isMobileViewport ? '100vw' : undefined }}
        >
            {/* Handle de redimensionamento — borda esquerda */}
            <div
                onMouseDown={handleResizeMouseDown}
                className={`absolute left-0 top-0 bottom-0 w-1.5 z-10 group ${isMobileViewport ? 'pointer-events-none opacity-0' : 'cursor-ew-resize'}`}
                title="Arrastar para redimensionar"
            >
                <div className="absolute inset-y-0 left-0 w-full bg-transparent group-hover:bg-blue-400/30 transition-colors duration-150 rounded-l" />
                <div className="absolute top-1/2 -translate-y-1/2 left-0 w-1 h-10 rounded-full bg-slate-300 group-hover:bg-blue-400 transition-colors duration-150" />
            </div>

            {/* Header */}
            <div className={`shrink-0 p-6 flex items-center justify-between border-b ${isDark ? 'border-white/10' : 'border-slate-100'}`}>
                <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-lg">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                    </div>
                    <div>
                        <h3 className="text-lg font-black tracking-tight">Copiloto Hermes</h3>
                        <div className="flex items-center gap-3">
                            <p className={`text-[10px] font-black uppercase tracking-widest ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Estrategista Sênior</p>
                            {taskId && (
                                <div className="flex items-center gap-1.5">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.6)]"></span>
                                    <span className="text-[9px] font-black text-emerald-500 uppercase tracking-tight">Contexto da Ação Ativo</span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => handleCreateSession()}
                        className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}
                        title="Nova Conversa"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                    </button>
                    <button onClick={() => setShowHistory(!showHistory)} className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </button>
                    <button onClick={onClose} className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}>
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-hidden flex relative">
                {/* History Sidebar */}
                {showHistory && (
                    <div className="absolute inset-0 z-10 flex flex-col border-r border-slate-200 bg-white">
                        <div className="p-4 border-b border-slate-100 bg-white flex items-center justify-between">
                            <span className="text-[10px] font-black uppercase tracking-widest">Histórico de Sessões</span>
                            <button onClick={() => handleCreateSession()} className="text-[10px] bg-blue-600 text-white px-3 py-1.5 rounded-lg font-black uppercase tracking-widest">+ Nova</button>
                        </div>
                        <div className="flex-1 overflow-y-auto bg-white p-4 space-y-2">
                            {sessions.map(s => (
                                <div
                                    key={s.id}
                                    className={`group flex items-center gap-2 rounded-2xl border p-2 transition-all ${currentSessionId === s.id ? 'bg-blue-50 border-blue-200' : 'bg-white border-slate-100 hover:border-slate-200'}`}
                                >
                                    <button
                                        onClick={() => { setCurrentSessionId(s.id); setShowHistory(false); }}
                                        className="min-w-0 flex-1 text-left rounded-xl px-2 py-2"
                                    >
                                        <p className="text-xs font-bold truncate">{s.title}</p>
                                        <p className="text-[9px] text-slate-400 mt-1">{s.lastMessageAt?.toDate()?.toLocaleDateString()}</p>
                                    </button>
                                    <button
                                        onClick={() => void handleDeleteSession(s.id)}
                                        disabled={Boolean(deletingSessionId && deletingSessionId !== s.id)}
                                        title={sessionPendingDeleteId === s.id ? 'Clique novamente para excluir' : 'Excluir sessão'}
                                        className={`shrink-0 rounded-xl border px-2.5 py-2 text-[9px] font-black uppercase tracking-widest transition-all ${sessionPendingDeleteId === s.id
                                                ? 'border-red-300 bg-red-50 text-red-700 hover:bg-red-100'
                                                : 'border-slate-200 bg-white text-slate-400 hover:border-slate-300 hover:text-red-600'
                                            } disabled:cursor-not-allowed disabled:opacity-40`}
                                    >
                                        {deletingSessionId === s.id ? (
                                            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                                            </svg>
                                        ) : sessionPendingDeleteId === s.id ? (
                                            <span>Excluir</span>
                                        ) : (
                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M4 7h16" />
                                            </svg>
                                        )}
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Chat Area */}
                <div className="flex-1 flex flex-col min-w-0">
                    <div className="flex-1 overflow-y-auto p-6 space-y-6" style={{ scrollbarWidth: 'thin' }}>
                        {messages.length === 0 && !isLoading && (
                            <div className="h-full flex flex-col items-center justify-center text-center opacity-30 gap-4">
                                <div className="w-20 h-20 rounded-[2.5rem] bg-slate-100 flex items-center justify-center">
                                    <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
                                </div>
                                <div>
                                    <p className="text-sm font-black uppercase tracking-widest">Inicie uma consultoria</p>
                                    <p className="text-xs mt-1">Conectando Grafo de Execução e Acervo Global</p>
                                </div>
                                <div className="flex flex-wrap gap-2 justify-center mt-4">
                                    <button onClick={() => handleCreateSession("Quais são os próximos passos estratégicos?")} className="px-4 py-2 bg-slate-100 rounded-xl text-[10px] font-bold hover:bg-slate-200 transition-all">🚀 Próximos passos</button>
                                    <button onClick={() => handleCreateSession("Analise conflitos entre o manual e a execução.")} className="px-4 py-2 bg-slate-100 rounded-xl text-[10px] font-bold hover:bg-slate-200 transition-all">🔍 Conflitos Teoria/Prática</button>
                                </div>
                            </div>
                        )}

                        {messages.map((msg, i) => (
                            <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                                <div className={`max-w-[90%] min-w-0 px-4 py-3 rounded-2xl text-xs font-medium leading-relaxed shadow-sm ${msg.role === 'user'
                                    ? 'bg-blue-600 text-white rounded-br-none'
                                    : 'bg-slate-100 text-slate-700 rounded-bl-none'
                                    }`}>
                                    {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                                        <div className="mb-2.5">
                                            <div className="mb-1 flex items-center gap-1.5 text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.75 3a.75.75 0 01.75.75V5a.75.75 0 01-1.5 0V3.75A.75.75 0 019.75 3zm4.5 0a.75.75 0 01.75.75V5a.75.75 0 01-1.5 0V3.75a.75.75 0 01.75-.75zM12 8.25A3.75 3.75 0 108.25 12 3.75 3.75 0 0012 8.25zm7.5 3a.75.75 0 010 1.5H18.25a.75.75 0 010-1.5zM5.75 12a.75.75 0 01-.75.75H3.75a.75.75 0 010-1.5H5a.75.75 0 01.75.75zm10.364 5.614a.75.75 0 011.06 0l.884.884a.75.75 0 11-1.06 1.06l-.884-.883a.75.75 0 010-1.061zm-9.288 0a.75.75 0 010 1.06l-.884.884a.75.75 0 11-1.06-1.06l.883-.884a.75.75 0 011.061 0zm11.172-11.228a.75.75 0 010 1.06l-.884.884a.75.75 0 11-1.06-1.06l.883-.884a.75.75 0 011.061 0zm-11.172 0l.884.884a.75.75 0 11-1.06 1.06l-.884-.883a.75.75 0 011.06-1.061zM9.75 19a.75.75 0 01.75.75V21a.75.75 0 01-1.5 0v-1.25a.75.75 0 01.75-.75zm4.5 0a.75.75 0 01.75.75V21a.75.75 0 01-1.5 0v-1.25a.75.75 0 01.75-.75z" /></svg>
                                                Ferramentas usadas
                                            </div>
                                            <div className="flex flex-wrap gap-1">
                                            {msg.toolsUsed.map(tool => {
                                                if (!TOOL_LABELS[tool]) return null;
                                                const isWrite = WRITE_TOOLS.has(tool);
                                                return (
                                                    <span
                                                        key={tool}
                                                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.08em] border ${isWrite
                                                                ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                                                                : 'text-slate-500 bg-white/90 border-slate-200'
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
                                        </div>
                                    )}
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm]}
                                        components={{
                                            p: ({ node, ...props }) => <p className="mb-2 last:mb-0" {...props} />,
                                            ul: ({ node, ...props }) => <ul className="list-disc ml-4 mb-2" {...props} />,
                                            li: ({ node, ...props }) => <li className="mb-0.5" {...props} />,
                                            strong: ({ node, ...props }) => <strong className="font-bold text-blue-600" {...props} />,
                                            a: ({ node, ...props }) => {
                                                const href = props.href || '';
                                                console.log("[HermesCopiloto] Link clicked:", href);

                                                if (isInternalAppHref(href)) {
                                                    return (
                                                        <a
                                                            className="text-blue-600 underline hover:text-blue-800 break-all"
                                                            href={href}
                                                            onClick={(event) => {
                                                                event.preventDefault();
                                                                navigateWithinApp(href);
                                                                onClose?.();
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
                                                                onOpenTask?.(id);
                                                                onClose?.();
                                                            }}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-blue-600 hover:text-white text-blue-400 rounded-xl border border-blue-500/30 transition-all font-black text-[10px] uppercase tracking-tighter mx-1 shadow-sm group/btn"
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                                            <span className="group-hover/btn:underline">{props.children}</span>
                                                            <svg className="w-3 h-3 opacity-0 group-hover/btn:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" /></svg>
                                                        </button>
                                                    );
                                                }
                                                if (href.includes('tool:slides:')) {
                                                    const draftId = href.split('tool:slides:')[1];
                                                    return (
                                                        <button
                                                            onClick={() => onOpenTool?.('slides', draftId)}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded-xl transition-all font-black text-[10px] uppercase tracking-tighter mx-1 shadow-sm"
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" /></svg>
                                                            {props.children}
                                                        </button>
                                                    );
                                                }
                                                if (href.includes('tool:diagnosis:')) {
                                                    const diagId = href.split('tool:diagnosis:')[1];
                                                    return (
                                                        <button
                                                            onClick={() => handleOpenDiagnosis(diagId)}
                                                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl transition-all font-black text-[10px] uppercase tracking-tighter mx-1 shadow-sm"
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                                                            {props.children}
                                                        </button>
                                                    );
                                                }
                                                return <a className="text-blue-600 underline hover:text-blue-800 break-all" target="_blank" rel="noopener noreferrer" {...props} />;
                                            },
                                        }}
                                    >
                                        {msg.content}
                                    </ReactMarkdown>

                                    {/* Botões de confirmação de draft */}
                                    {msg.role === 'assistant' && (() => {
                                        const draftType = getDraftType(msg.content, i);
                                        if (!draftType) return null;
                                        return (
                                            <div className="mt-3 pt-3 border-t border-slate-200 flex flex-wrap gap-2">
                                                <button
                                                    onClick={() => handleQuickReply('Confirmo!')}
                                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 text-white text-[10px] font-black uppercase tracking-widest hover:bg-emerald-700 transition-all shadow-sm"
                                                >
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                    Confirmar
                                                </button>
                                                <button
                                                    onClick={() => {
                                                        setInput('Prefiro ajustar: ');
                                                        setTimeout(() => textareaRef.current?.focus(), 50);
                                                    }}
                                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white text-amber-700 border border-amber-300 text-[10px] font-black uppercase tracking-widest hover:bg-amber-50 transition-all shadow-sm"
                                                >
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                    Ajustar
                                                </button>
                                                <button
                                                    onClick={() => handleQuickReply('Cancelar, não quero prosseguir.')}
                                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white text-slate-400 border border-slate-200 text-[10px] font-black uppercase tracking-widest hover:bg-slate-100 hover:text-slate-600 transition-all shadow-sm"
                                                >
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                    Cancelar
                                                </button>
                                            </div>
                                        );
                                    })()}

                                    {/* Botão Abrir Relatório */}
                                    {msg.role === 'assistant' && msg.reportId && (
                                        <div className="mt-3 pt-3 border-t border-slate-200">
                                            <button
                                                onClick={() => handleOpenReport(msg.reportId!)}
                                                disabled={isLoadingReport}
                                                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 text-white text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                                            >
                                                {isLoadingReport ? (
                                                    <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
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
                                        <div className="mt-4 p-4 bg-white rounded-xl border border-blue-200 shadow-sm">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-600 flex items-center gap-2 mb-3">
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                                                Proposta de Ajuste de Plano
                                            </p>
                                            <div className="space-y-2 mb-4">
                                                {msg.proposedPlan.map((item, idx) => (
                                                    <div key={idx} className="flex gap-2 text-[11px] text-slate-600">
                                                        <span className="font-black text-blue-400">{idx + 1}.</span>
                                                        <span>{item.text}</span>
                                                    </div>
                                                ))}
                                            </div>
                                            <div className="flex gap-2">
                                                <button className="flex-1 bg-emerald-600 text-white py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-emerald-700 transition-all">Aceitar</button>
                                                <button className="flex-1 bg-slate-100 text-slate-400 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-slate-200 transition-all">Recusar</button>
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
                                                <div className="mt-3 p-3 bg-emerald-50 border border-emerald-200 rounded-xl">
                                                    <p className="text-[10px] font-black uppercase tracking-widest text-emerald-700 flex items-center gap-1.5 mb-2">
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
                                                <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-xl">
                                                    <p className="text-[10px] font-black uppercase tracking-widest text-red-600 flex items-center gap-1.5 mb-1">
                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                                                        {pe.status === 'error' ? 'Erro na edição' : 'Edição bloqueada'}
                                                    </p>
                                                    <p className="text-[10px] text-red-600">{pe.errorMessage ?? 'Operação indisponível.'}</p>
                                                </div>
                                            );
                                        }

                                        if (pe.status === 'cancelled') {
                                            return (
                                                <div className="mt-3 p-3 bg-slate-50 border border-slate-200 rounded-xl">
                                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center gap-1.5">
                                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                        Edição cancelada
                                                    </p>
                                                </div>
                                            );
                                        }

                                        // status === 'pending'
                                        return (
                                            <div className="mt-3 p-3 bg-white border border-amber-200 rounded-xl shadow-sm">
                                                <p className="text-[10px] font-black uppercase tracking-widest text-amber-700 flex items-center gap-1.5 mb-2">
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
                                                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 text-white text-[10px] font-black uppercase tracking-widest hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                                                    >
                                                        {isProcessing ? (
                                                            <span className="w-2.5 h-2.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                                                        ) : (
                                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                        )}
                                                        Confirmar
                                                    </button>
                                                    <button
                                                        onClick={() => handleCancelEdit(mid)}
                                                        disabled={isProcessing}
                                                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white text-slate-400 border border-slate-200 text-[10px] font-black uppercase tracking-widest hover:bg-slate-100 hover:text-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                                                    >
                                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                                                        Cancelar
                                                    </button>
                                                </div>
                                            </div>
                                        );
                                    })()}

                                    {/* Proposta de Diagnóstico de Código */}
                                    {msg.proposedDiagnosis && (
                                        <div className="mt-4 p-4 bg-white rounded-xl border border-blue-200 shadow-sm">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-600 flex items-center gap-2 mb-2">
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
                                                        <span className="text-[11px] font-mono text-slate-600">{msg.proposedDiagnosis.fileName}</span>
                                                    </div>
                                                )}
                                                <p className="text-[11px] text-slate-600 leading-relaxed">{msg.proposedDiagnosis.descricaoProblema}</p>
                                                {msg.proposedDiagnosis.mode === 'snippet' && msg.proposedDiagnosis.codeSnippet && (
                                                    <pre className="text-[9px] font-mono text-slate-500 bg-slate-50 border border-slate-200 rounded p-2 max-h-24 overflow-hidden relative">
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
                                                    className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-1.5"
                                                >
                                                    {diagnosingId === msg.id ? (
                                                        <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                                                    ) : (
                                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                    )}
                                                    {diagnosingId === msg.id ? 'Analisando...' : (msg.proposedDiagnosis.mode === 'snippet' ? 'Analisar Snippet' : 'Analisar Repositório')}
                                                </button>
                                                <button
                                                    onClick={() => { setInput(`Ajustar diagnóstico: `); setTimeout(() => textareaRef.current?.focus(), 50); }}
                                                    className="flex-1 bg-slate-100 text-slate-500 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-slate-200 transition-all flex items-center justify-center gap-1.5"
                                                >
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                    Ajustar
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* Proposta de Apresentação de Slides */}
                                    {msg.proposedPresentation && (
                                        <div className="mt-4 p-4 bg-white rounded-xl border border-violet-200 shadow-sm">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-violet-600 flex items-center gap-2 mb-1">
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" /></svg>
                                                Esqueleto da Apresentação
                                            </p>
                                            <p className="text-[11px] font-bold text-slate-700 mb-3 truncate">{msg.proposedPresentation.temaGeral}</p>
                                            <div className="space-y-2 mb-4 max-h-52 overflow-y-auto pr-1">
                                                {msg.proposedPresentation.slides.map((slide, idx) => (
                                                    <div key={idx} className="p-2 rounded-lg bg-violet-50 border border-violet-100">
                                                        <div className="flex items-center gap-1.5 mb-1">
                                                            <span className="text-[9px] font-black text-violet-400 uppercase">{slide.tipo_layout}</span>
                                                            <span className="text-[9px] text-slate-400">#{slide.ordem}</span>
                                                        </div>
                                                        <p className="text-[11px] font-bold text-slate-700 leading-tight">{slide.titulo}</p>
                                                        {slide.subtitulo && <p className="text-[10px] text-slate-500 mt-0.5">{slide.subtitulo}</p>}
                                                        {slide.topicos.length > 0 && (
                                                            <ul className="mt-1 space-y-0.5">
                                                                {slide.topicos.map((t, ti) => (
                                                                    <li key={ti} className="text-[10px] text-slate-500 flex gap-1">
                                                                        <span className="text-violet-400">•</span>{t}
                                                                    </li>
                                                                ))}
                                                            </ul>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => handleConfirmPresentation(msg.proposedPresentation!)}
                                                    className="flex-1 bg-violet-600 text-white py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-violet-700 transition-all flex items-center justify-center gap-1.5"
                                                >
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                                                    Confirmar
                                                </button>
                                                <button
                                                    onClick={() => { setInput('Ajustar apresentação: '); setTimeout(() => textareaRef.current?.focus(), 50); }}
                                                    className="flex-1 bg-slate-100 text-slate-500 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-slate-200 transition-all flex items-center justify-center gap-1.5"
                                                >
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                                    Ajustar
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}

                        {/* Indicador de loading com mensagem de fase */}
                        {isBlocked && (
                            <div className="flex justify-start flex-col gap-2">
                                <div className="px-4 py-3 rounded-2xl rounded-bl-none bg-slate-100 flex flex-col gap-2">
                                    <div className="flex gap-1.5 items-center">
                                        <span className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" />
                                        <span className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                                        <span className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                                        {uploadPhase !== 'idle' && (
                                            <span className="text-[10px] font-bold text-slate-500 ml-2">
                                                {uploadPhaseLabel[uploadPhase]}
                                            </span>
                                        )}
                                    </div>
                                    {/* Barra de progresso — visível apenas nas fases de upload/processamento */}
                                    {uploadPhase !== 'idle' && (
                                        <div className="w-48 h-1 bg-slate-200 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-blue-500 rounded-full"
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
                    <div className={`shrink-0 p-6 border-t ${isDark ? 'border-white/10' : 'border-slate-100'}`}>

                        {/* Banner de erro inline */}
                        {footerError && (
                            <div className="flex items-start gap-2 mb-3 px-3 py-2.5 rounded-xl text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
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
                            <div className="flex items-center gap-2 mb-3 px-3 py-2.5 rounded-xl text-xs font-semibold bg-violet-50 text-violet-700 border border-violet-200">
                                <svg className="w-4 h-4 shrink-0 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m12.728 0l-.707-.707M6.343 6.343l-.707-.707" />
                                </svg>
                                <span>Transcrevendo áudio...</span>
                            </div>
                        )}

                        {/* Badge de arquivo anexado */}
                        {attachedFile && !isBlocked && (
                            <div className={`flex items-center gap-2 mb-3 px-3 py-2 rounded-xl text-xs font-semibold ${isDark ? 'bg-blue-900/40 text-blue-300' : 'bg-blue-50 text-blue-700 border border-blue-200'}`}>
                                <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                                </svg>
                                <span className="truncate flex-1">{attachedFile.name}</span>
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

                        <div className="flex gap-3 items-end">
                            {/* Input de arquivo oculto */}
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.png,.jpg,.jpeg,.webp"
                                className="hidden"
                                onChange={handleFileSelect}
                            />

                            {/* Textarea com botão de clipe embutido */}
                            <div className="relative flex-1">
                                {/* Mention popup */}
                                {mention.visible && (
                                    <div className="absolute bottom-full left-0 mb-2 w-full max-h-52 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl z-50">
                                        <div className="px-3 py-1.5 border-b border-slate-100 sticky top-0 bg-white">
                                            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Referenciar do Diário de Bordo</span>
                                        </div>
                                        {mention.filtered.map((item, idx) => (
                                            <button
                                                key={item.id}
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
                                        if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault();
                                            if (!currentSessionId) {
                                                handleCreateSession(input);
                                            } else {
                                                sendMessage(input);
                                            }
                                        }
                                    }}
                                    placeholder={isRecording ? '🎙 Gravando… clique no microfone para parar' : isProcessingMic ? 'Transcrevendo áudio...' : isTranscribing ? 'Transcrevendo áudio...' : attachedFile ? 'Pergunte sobre o arquivo ou envie sem texto…' : 'Estrategize com Hermes…'}
                                    className={`w-full pl-4 pr-9 py-3.5 rounded-2xl text-sm font-medium outline-none border resize-none overflow-y-auto ${isDark ? 'bg-white/5 border-white/10 text-white placeholder:text-white/20 focus:border-blue-500' : 'bg-slate-50 border-slate-200 text-slate-700 placeholder:text-slate-400 focus:border-blue-500'} transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed`}
                                />
                                <button
                                    onClick={() => !isBlocked && fileInputRef.current?.click()}
                                    disabled={isBlocked}
                                    title="Anexar arquivo"
                                    className={`absolute right-2.5 bottom-3 transition-all ${attachedFile
                                            ? 'text-blue-500'
                                            : isDark
                                                ? 'text-white/30 hover:text-white/70'
                                                : 'text-slate-300 hover:text-slate-500'
                                        } disabled:opacity-30 disabled:cursor-not-allowed`}
                                >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                                    </svg>
                                </button>
                            </div>
                            <button
                                onClick={() => isRecording ? stopRecording() : startRecording()}
                                disabled={isBlocked && !isRecording}
                                title={isRecording ? 'Parar gravação' : 'Gravar Áudio'}
                                className={`w-12 h-12 shrink-0 flex items-center justify-center rounded-2xl transition-all active:scale-90 shadow-sm ${
                                    isRecording
                                        ? 'bg-red-500 text-white animate-pulse hover:bg-red-600'
                                        : isDark
                                            ? 'bg-white/10 text-white/60 hover:bg-white/20 hover:text-white disabled:opacity-30'
                                            : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30'
                                } disabled:cursor-not-allowed`}
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
                            <button
                                onClick={() => {
                                    if (!currentSessionId) {
                                        handleCreateSession(input);
                                    } else {
                                        sendMessage(input);
                                    }
                                }}
                                disabled={isBlocked || (!input.trim() && !attachedFile)}
                                className="w-12 h-12 shrink-0 bg-blue-600 text-white rounded-2xl flex items-center justify-center shadow-lg hover:bg-blue-700 disabled:opacity-40 transition-all"
                            >
                                <svg className="w-6 h-6 rotate-45" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
