import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../firebase';
import {
  Sistema, WorkItem, Tarefa, BaseConhecimento, ConhecimentoItem,
  PoolItem, ChatMessage, SistemaStatus,
} from '../../types';
import { normalizeStatus } from '../utils/helpers';
import { STATUS_COLORS } from '../../constants';

// ─── Types ────────────────────────────────────────────────────────────────────

type Unidade = { id: string; nome: string };
type MobileTab = 'visao-geral' | 'logs' | 'copiloto';

interface Artifact {
  id: string;
  title: string;
  content: string;
  createdAt: string;
}

interface EditingResource {
  field: string;
  label: string;
  value: string;
}

interface SistemaExecutionViewProps {
  unit: Unidade;
  sysDetails: Sistema;
  workItems: WorkItem[];
  tarefas: Tarefa[];
  knowledgeBases: BaseConhecimento[];
  knowledgeItems: ConhecimentoItem[];
  onClose: () => void;
  onUpdateSistema: (id: string, updates: Partial<Sistema>) => void;
  onCreateWorkItem: (sistemaId: string, tipo: string, text: string, attachments: PoolItem[]) => void;
  onUpdateWorkItem: (id: string, updates: Partial<WorkItem>) => void;
  onDeleteWorkItem: (id: string) => void;
  onSyncGithubRepo: (sistemaId: string, repoUrl: string) => void;
  isSyncingGithub: boolean;
  onSelectTask: (task: Tarefa) => void;
  showToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
  handleFileUploadToDrive: (file: File) => Promise<PoolItem | null>;
  isUploading: boolean;
}

// ─── Status maps ─────────────────────────────────────────────────────────────

const STEPS: SistemaStatus[] = ['ideia', 'prototipacao', 'desenvolvimento', 'testes', 'producao'];
const STEP_LABELS: Record<SistemaStatus, string> = {
  ideia: 'Ideia',
  prototipacao: 'Protótipo',
  desenvolvimento: 'Dev',
  testes: 'Testes',
  producao: 'Produção',
};
const STATUS_THEME: Record<SistemaStatus, { panel: string; pill: string; accent: string; helper: string }> = {
  ideia:        { panel: 'bg-slate-50',   pill: 'bg-slate-100 text-slate-700',   accent: 'bg-slate-500',   helper: 'Hipóteses, escopo inicial e definição do que vale perseguir.' },
  prototipacao: { panel: 'bg-amber-50',   pill: 'bg-amber-100 text-amber-700',   accent: 'bg-amber-500',   helper: 'Experimentos rápidos, prova de conceito e validação inicial.' },
  desenvolvimento: { panel: 'bg-blue-50', pill: 'bg-blue-100 text-blue-700',    accent: 'bg-blue-500',    helper: 'Construção principal, ajustes técnicos e integração com base RAG.' },
  testes:       { panel: 'bg-orange-50',  pill: 'bg-orange-100 text-orange-700', accent: 'bg-orange-500',  helper: 'Validação, correções finais e fechamento de pendências.' },
  producao:     { panel: 'bg-emerald-50', pill: 'bg-emerald-100 text-emerald-700', accent: 'bg-emerald-500', helper: 'Operação estável, documentação e manutenção evolutiva.' },
};

// ─── Component ────────────────────────────────────────────────────────────────

export const SistemaExecutionView: React.FC<SistemaExecutionViewProps> = ({
  unit,
  sysDetails,
  workItems,
  tarefas,
  knowledgeBases,
  knowledgeItems,
  onClose,
  onUpdateSistema,
  onCreateWorkItem,
  onUpdateWorkItem,
  onDeleteWorkItem,
  onSyncGithubRepo,
  isSyncingGithub,
  onSelectTask,
  showToast,
  handleFileUploadToDrive,
  isUploading,
}) => {
  const systemName = unit.nome.replace('SISTEMA:', '').trim();
  const systemWorkItems = workItems.filter(w => w.sistema_id === unit.id);
  const activeWorkItems = systemWorkItems.filter(w => !w.concluido);
  const completedWorkItems = systemWorkItems.filter(w => w.concluido);

  const systemBaseIds = knowledgeBases.filter(b => b.sistema_id === unit.id).map(b => b.id);
  const systemKnowledgeIds = new Set(
    knowledgeItems.filter(item => item.base_id && systemBaseIds.includes(item.base_id)).map(item => item.id)
  );
  const linkedTasks = tarefas.filter(t =>
    (t.base_conhecimento && systemBaseIds.includes(t.base_conhecimento)) ||
    (t.knowledge_item_ids || []).some(id => systemKnowledgeIds.has(id)) ||
    t.sistema === systemName
  );

  // ─── Local state ────────────────────────────────────────────────
  const [mobileTab, setMobileTab] = useState<MobileTab>('visao-geral');
  const [editingResource, setEditingResource] = useState<EditingResource | null>(null);

  // Log form
  const [newLogText, setNewLogText] = useState('');
  const [newLogAttachments, setNewLogAttachments] = useState<PoolItem[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessingAudio, setIsProcessingAudio] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Work item editing
  const [editingWorkItem, setEditingWorkItem] = useState<WorkItem | null>(null);
  const [editingWorkItemText, setEditingWorkItemText] = useState('');
  const [editingWorkItemAttachments, setEditingWorkItemAttachments] = useState<PoolItem[]>([]);
  const [confirmDeleteLogId, setConfirmDeleteLogId] = useState<string | null>(null);
  const [isCompletedLogsOpen, setIsCompletedLogsOpen] = useState(false);

  // Copilot
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isChatFocused, setIsChatFocused] = useState(false);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [copiedArtifactId, setCopiedArtifactId] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // ─── Audio ─────────────────────────────────────────────────────
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];
      mr.ondataavailable = e => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        await handleProcessAudio(blob);
        stream.getTracks().forEach(t => t.stop());
      };
      mr.start();
      setIsRecording(true);
    } catch {
      showToast('Erro ao acessar microfone.', 'error');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessingAudio(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const b64 = (reader.result as string).split(',')[1];
          const fn = httpsCallable(functions, 'transcreverAudio');
          const res = await fn({ audioBase64: b64 });
          const data = res.data as { raw: string; refined: string };
          if (data.refined) setNewLogText(prev => prev + (prev ? '\n' : '') + data.refined);
        } catch {
          showToast('Erro ao processar áudio.', 'error');
        } finally {
          setIsProcessingAudio(false);
        }
      };
    } catch {
      setIsProcessingAudio(false);
    }
  };

  // ─── Copilot ───────────────────────────────────────────────────
  const buildHistoryContext = () =>
    chatMessages
      .slice(-6)
      .map(m => `${m.role === 'user' ? 'Usuário' : 'Copiloto'}: ${m.content}`)
      .join('\n');

  const sendChatMessage = async (messageText: string, asArtifact = false) => {
    if (!messageText.trim() || isChatLoading) return;
    const userMsg: ChatMessage = { role: 'user', content: messageText };
    const historyWithUser = [...chatMessages, userMsg];
    setChatMessages(historyWithUser);
    setIsChatLoading(true);
    try {
      const fn = httpsCallable(functions, 'askTaskAssistant');
      const customPrompt = `Contexto: Sistema de software chamado "${systemName}" (status: ${STEP_LABELS[sysDetails.status]}).\n\nComando: ${messageText}`;
      const res = await fn({
        prompt: customPrompt,
        historyContext: buildHistoryContext(),
        categoria: 'SISTEMA',
        ragContext: unit.id,
      });
      const result = (res.data as any).result || '';
      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: asArtifact
          ? '📄 Artefato gerado e salvo no painel de Artefatos.'
          : result,
        ...(asArtifact ? { isArtifact: true } : {}),
      };
      if (asArtifact) {
        const artifact: Artifact = {
          id: Date.now().toString(),
          title: messageText.length > 60 ? messageText.substring(0, 60) + '…' : messageText,
          content: result,
          createdAt: new Date().toLocaleString('pt-BR'),
        };
        setArtifacts(prev => [...prev, artifact]);
        setShowArtifacts(true);
      }
      setChatMessages([...historyWithUser, assistantMsg]);
    } catch {
      showToast('Erro ao consultar o Copiloto.', 'error');
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleSendMessage = () => {
    const msg = chatInput.trim();
    if (!msg) return;
    setChatInput('');
    sendChatMessage(msg);
  };

  const handleCopyArtifact = (artifact: Artifact) => {
    navigator.clipboard.writeText(artifact.content);
    setCopiedArtifactId(artifact.id);
    setTimeout(() => setCopiedArtifactId(null), 2000);
  };

  // ─── Derived ───────────────────────────────────────────────────
  const theme = STATUS_THEME[sysDetails.status] ?? STATUS_THEME['ideia'];
  const resourceCount = [
    sysDetails.repositorio_principal,
    sysDetails.link_documentacao,
    sysDetails.link_google_ai_studio,
    sysDetails.link_hospedado,
  ].filter(Boolean).length;

  const latestWorkItem = [...systemWorkItems].sort(
    (a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime()
  )[0];

  // ─── Render helpers ────────────────────────────────────────────

  const renderLeftColumn = () => (
    <div className="flex-1 min-w-0 overflow-y-auto p-4 lg:p-6 space-y-6" style={{ scrollbarWidth: 'thin' }}>

      {/* Status Stepper */}
      <div className={`${theme.panel} rounded-2xl border border-slate-100 p-5 space-y-4`}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Status do sistema</p>
            <p className="text-sm font-semibold text-slate-600 mt-1">{theme.helper}</p>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-2">
              {activeWorkItems.length} demanda{activeWorkItems.length !== 1 ? 's' : ''} aberta{activeWorkItems.length !== 1 ? 's' : ''}
            </p>
          </div>
          <span className={`shrink-0 px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-widest ${theme.pill}`}>
            {STEP_LABELS[sysDetails.status]}
          </span>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: 'Ativos', value: String(activeWorkItems.length) },
            { label: 'Concluídos', value: String(completedWorkItems.length) },
            { label: 'Recursos', value: `${resourceCount}/4` },
            { label: 'Ações', value: String(linkedTasks.length) },
          ].map(item => (
            <div key={item.label} className="bg-white border border-slate-200 rounded-xl px-3 py-2.5">
              <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">{item.label}</div>
              <div className="text-sm font-black text-slate-800 mt-1">{item.value}</div>
            </div>
          ))}
        </div>

        {/* Step buttons */}
        <div className="flex flex-wrap items-center justify-center bg-slate-200/50 p-1 rounded-xl gap-1">
          {STEPS.map((step, idx) => {
            const isActive = sysDetails.status === step;
            return (
              <React.Fragment key={step}>
                <button
                  onClick={() => onUpdateSistema(unit.id, { status: step })}
                  className={`flex-1 md:flex-none px-3 py-2 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all ${
                    isActive
                      ? `${theme.accent} text-white shadow-lg`
                      : 'text-slate-500 hover:text-slate-700 hover:bg-white/50'
                  }`}
                >
                  {STEP_LABELS[step]}
                </button>
                {idx < STEPS.length - 1 && (
                  <div className="hidden md:flex items-center text-slate-300 px-0.5">
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Resources */}
      <div className="space-y-3">
        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
          <span className="w-1 h-3 bg-violet-500 rounded-full"></span>
          Recursos
        </h4>
        <div className="grid grid-cols-2 gap-2">
          {/* Repositório */}
          <button
            onClick={() => setEditingResource({ field: 'repositorio_principal', label: 'Repositório', value: sysDetails.repositorio_principal || '' })}
            className="group bg-slate-900 p-3 rounded-xl border border-slate-800 hover:border-slate-600 hover:shadow-md transition-all text-left flex items-center justify-between gap-3 relative overflow-hidden min-h-[64px]"
          >
            <div className="absolute top-0 right-0 w-20 h-20 bg-violet-500/10 rounded-full -mr-10 -mt-10 group-hover:scale-150 transition-transform duration-500" />
            <div className="relative z-10 flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 bg-white/10 text-white rounded-lg flex items-center justify-center shrink-0">
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
              </div>
              <div className="min-w-0">
                <h5 className="text-[10px] font-black text-white uppercase tracking-widest leading-none">Repo</h5>
                <p className="text-[9px] text-slate-400 mt-0.5 truncate">{sysDetails.repositorio_principal || 'Não configurado'}</p>
              </div>
            </div>
          </button>

          {/* Documentação */}
          <button
            onClick={() => setEditingResource({ field: 'link_documentacao', label: 'Documentação', value: sysDetails.link_documentacao || '' })}
            className="group bg-white p-3 rounded-xl border border-slate-200 hover:border-violet-300 hover:shadow-md transition-all text-left flex items-center gap-2.5 relative overflow-hidden min-h-[64px]"
          >
            <div className="absolute top-0 right-0 w-20 h-20 bg-violet-500/5 rounded-full -mr-10 -mt-10 group-hover:scale-150 transition-transform duration-500" />
            <div className="w-8 h-8 bg-violet-100 text-violet-600 rounded-lg flex items-center justify-center shrink-0 relative z-10">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div className="min-w-0 relative z-10">
              <h5 className="text-[10px] font-black text-slate-900 uppercase tracking-widest leading-none">Docs</h5>
              <p className="text-[9px] text-slate-500 mt-0.5 truncate">{sysDetails.link_documentacao || 'Sem documentação'}</p>
            </div>
          </button>

          {/* AI Studio */}
          <button
            onClick={() => setEditingResource({ field: 'link_google_ai_studio', label: 'AI Studio', value: sysDetails.link_google_ai_studio || '' })}
            className="group bg-white p-3 rounded-xl border border-slate-200 hover:border-blue-300 hover:shadow-md transition-all text-left flex items-center gap-2.5 relative overflow-hidden min-h-[64px]"
          >
            <div className="absolute top-0 right-0 w-20 h-20 bg-blue-500/5 rounded-full -mr-10 -mt-10 group-hover:scale-150 transition-transform duration-500" />
            <div className="w-8 h-8 bg-blue-100 text-blue-600 rounded-lg flex items-center justify-center shrink-0 relative z-10">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div className="min-w-0 relative z-10">
              <h5 className="text-[10px] font-black text-slate-900 uppercase tracking-widest leading-none">AI</h5>
              <p className="text-[9px] text-slate-500 mt-0.5 truncate">{sysDetails.link_google_ai_studio || 'Sem workspace'}</p>
            </div>
          </button>

          {/* Hospedagem */}
          <button
            onClick={() => setEditingResource({ field: 'link_hospedado', label: 'Hospedagem', value: sysDetails.link_hospedado || '' })}
            className="group bg-emerald-50 p-3 rounded-xl border border-emerald-100 hover:border-emerald-300 hover:shadow-md transition-all text-left flex items-center gap-2.5 relative overflow-hidden min-h-[64px]"
          >
            <div className="absolute top-0 right-0 w-20 h-20 bg-emerald-500/10 rounded-full -mr-10 -mt-10 group-hover:scale-150 transition-transform duration-500" />
            <div className="w-8 h-8 bg-emerald-100 text-emerald-600 rounded-lg flex items-center justify-center shrink-0 relative z-10">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
            </div>
            <div className="min-w-0 relative z-10">
              <h5 className="text-[10px] font-black text-emerald-900 uppercase tracking-widest leading-none">App</h5>
              <p className="text-[9px] text-emerald-700/70 mt-0.5 truncate">{sysDetails.link_hospedado || 'Sem link público'}</p>
            </div>
          </button>
        </div>

        {/* GitHub RAG Sync */}
        {sysDetails.repositorio_principal && (
          <button
            onClick={() => onSyncGithubRepo(unit.id, sysDetails.repositorio_principal!)}
            disabled={isSyncingGithub}
            className="w-full flex items-center justify-between gap-3 p-3 rounded-xl border border-dashed border-violet-300 hover:border-violet-500 hover:bg-violet-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed group"
          >
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 bg-violet-100 text-violet-600 rounded-lg flex items-center justify-center shrink-0">
                {isSyncingGithub ? (
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                ) : (
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                )}
              </div>
              <div className="text-left">
                <p className="text-[10px] font-black text-violet-700 uppercase tracking-widest leading-none">
                  {isSyncingGithub ? 'Sincronizando...' : 'Sincronizar RAG'}
                </p>
                <p className="text-[9px] text-slate-400 mt-0.5">
                  {sysDetails.github_rag_synced_at
                    ? `Última sync: ${new Date(sysDetails.github_rag_synced_at).toLocaleDateString('pt-BR')}`
                    : 'Nunca sincronizado'}
                </p>
              </div>
            </div>
            <svg className="w-3.5 h-3.5 text-violet-400 group-hover:text-violet-600 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        )}
      </div>

      {/* Linked Tasks */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-violet-500 pl-3">Ações vinculadas</h5>
          <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">{linkedTasks.length} ação{linkedTasks.length !== 1 ? 'ões' : ''}</span>
        </div>
        {linkedTasks.length > 0 ? (
          <div className="space-y-2">
            {linkedTasks
              .sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime())
              .slice(0, 8)
              .map(task => (
                <button
                  key={task.id}
                  onClick={() => onSelectTask(task)}
                  className="w-full text-left border border-slate-200 rounded-xl px-4 py-3 bg-white hover:border-violet-300 hover:bg-violet-50/30 transition-all"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-[8px] font-black px-2 py-0.5 rounded uppercase tracking-wider ${STATUS_COLORS[normalizeStatus(task.status)] || 'bg-slate-100 text-slate-600'}`}>
                          {task.status}
                        </span>
                        {task.base_conhecimento && (
                          <span className="text-[8px] font-black uppercase tracking-widest text-violet-600">RAG</span>
                        )}
                      </div>
                      <p className="text-sm font-semibold text-slate-800 mt-1.5 truncate">{task.titulo}</p>
                      <p className="text-[10px] text-slate-500 mt-0.5 truncate">
                        {task.data_limite ? `Prazo: ${new Date(task.data_limite).toLocaleDateString('pt-BR')}` : 'Sem prazo definido'}
                      </p>
                    </div>
                    <svg className="w-4 h-4 text-slate-300 shrink-0 mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </button>
              ))}
          </div>
        ) : (
          <div className="text-center py-10 bg-slate-50/50 rounded-xl border-2 border-dashed border-slate-100">
            <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest">Nenhuma ação vinculada</p>
            <p className="text-[10px] text-slate-400 mt-1">Ações com base RAG deste sistema aparecerão aqui.</p>
          </div>
        )}
      </div>

      {/* Work items summary */}
      {latestWorkItem && (
        <div className="border border-slate-200 rounded-xl p-4 bg-slate-50/70">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Demandas registradas</h5>
              <p className="text-sm font-semibold text-slate-700 mt-2">
                {systemWorkItems.length} demanda{systemWorkItems.length !== 1 ? 's' : ''} · {activeWorkItems.length} aberta{activeWorkItems.length !== 1 ? 's' : ''}
              </p>
              <p className="text-[10px] text-slate-500 mt-1">
                Último registro em {new Date(latestWorkItem.data_criacao).toLocaleDateString('pt-BR')}
              </p>
            </div>
            <button
              onClick={() => { setEditingWorkItem(latestWorkItem); setEditingWorkItemText(latestWorkItem.descricao); setEditingWorkItemAttachments(latestWorkItem.pool_dados || []); }}
              className="shrink-0 text-[9px] font-black uppercase tracking-widest text-violet-600 hover:text-violet-800"
            >
              Ver último
            </button>
          </div>
        </div>
      )}
    </div>
  );

  const renderLogsColumn = () => (
    <div className="flex-1 min-w-0 overflow-y-auto p-4 lg:p-6 space-y-6" style={{ scrollbarWidth: 'thin' }}>

      {/* New Log Input */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center gap-2">
          <div className="p-1.5 bg-violet-600 text-white rounded-lg">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </div>
          <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Nova Demanda</h4>
        </div>
        <div className="p-4 space-y-3">
          <div className="relative">
            <textarea
              value={newLogText}
              onChange={e => setNewLogText(e.target.value)}
              placeholder="O que foi feito ou precisa ser feito no sistema?"
              className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 pr-14 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-violet-400 transition-all resize-none min-h-[100px]"
            />
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessingAudio}
              className={`absolute right-3 top-3 p-2.5 rounded-xl transition-all ${
                isRecording
                  ? 'bg-emerald-600 text-white animate-pulse shadow-lg'
                  : isProcessingAudio
                    ? 'bg-violet-100 text-violet-600 cursor-wait'
                    : 'bg-slate-100 text-slate-400 hover:text-violet-600 hover:bg-violet-50'
              }`}
              title="Transcrever áudio"
            >
              {isProcessingAudio ? (
                <div className="w-4 h-4 border-2 border-violet-600 border-t-transparent rounded-full animate-spin" />
              ) : isRecording ? (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              )}
            </button>
          </div>

          {/* Attachments preview */}
          {newLogAttachments.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {newLogAttachments.map((at, i) => (
                <div key={i} className="relative group/at">
                  <img src={at.valor} alt="preview" className="w-14 h-14 object-cover rounded-lg border border-slate-200" />
                  <button
                    onClick={() => setNewLogAttachments(prev => prev.filter((_, idx) => idx !== i))}
                    className="absolute -top-1 -right-1 bg-rose-500 text-white rounded-full p-0.5 opacity-0 group-hover/at:opacity-100 transition-all"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            {/* File upload */}
            <label className={`flex items-center justify-center p-2.5 rounded-xl border border-slate-200 transition-all cursor-pointer ${isUploading ? 'opacity-50 pointer-events-none' : 'hover:border-violet-300 hover:bg-violet-50 text-slate-400 hover:text-violet-600'}`}>
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={async e => {
                  const file = e.target.files?.[0];
                  if (file) {
                    const item = await handleFileUploadToDrive(file);
                    if (item) setNewLogAttachments(prev => [...prev, item]);
                  }
                }}
              />
              {isUploading ? (
                <div className="w-4 h-4 border-2 border-violet-600 border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
              )}
            </label>
            <button
              onClick={() => {
                if (!newLogText.trim()) return;
                onCreateWorkItem(unit.id, 'geral', newLogText, newLogAttachments);
                setNewLogText('');
                setNewLogAttachments([]);
              }}
              disabled={!newLogText.trim()}
              className="flex-1 bg-slate-900 text-white py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50"
            >
              Registrar
            </button>
          </div>
        </div>
      </div>

      {/* Active work items */}
      <div className="space-y-3">
        <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-violet-500 pl-3">
          Em aberto ({activeWorkItems.length})
        </h5>
        {activeWorkItems.length > 0 ? (
          <div className="space-y-2">
            {activeWorkItems
              .sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime())
              .map(log => (
                <div key={log.id} className="group bg-slate-50 border border-slate-100 rounded-xl p-4 hover:border-violet-200 hover:bg-white transition-all">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 space-y-1.5 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-[8px] font-black px-2 py-0.5 rounded uppercase tracking-wider ${log.tipo === 'desenvolvimento' ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-600'}`}>
                          {log.tipo === 'ajuste' ? 'log' : log.tipo}
                        </span>
                        <span className="text-[8px] font-black text-slate-300 uppercase">
                          {new Date(log.data_criacao).toLocaleDateString('pt-BR')}
                        </span>
                        {log.pool_dados && log.pool_dados.length > 0 && (
                          <span className="text-[8px] font-black text-emerald-600 uppercase">{log.pool_dados.length} anexo{log.pool_dados.length !== 1 ? 's' : ''}</span>
                        )}
                      </div>
                      <p className="text-sm font-medium text-slate-700 leading-relaxed">{log.descricao}</p>
                      {log.pool_dados && log.pool_dados.length > 0 && (
                        <div className="flex flex-wrap gap-2 mt-2">
                          {log.pool_dados.map((at, i) => (
                            <a key={i} href={at.valor} target="_blank" rel="noopener noreferrer">
                              <img src={at.valor} alt="preview" className="w-10 h-10 object-cover rounded-lg border border-slate-100 hover:scale-105 transition-transform shadow-sm" />
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-1 items-center opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                      <button
                        onClick={() => { setEditingWorkItem(log); setEditingWorkItemText(log.descricao); setEditingWorkItemAttachments(log.pool_dados || []); }}
                        className="p-1.5 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-all"
                        title="Editar"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                      <button
                        onClick={() => {
                          if (confirmDeleteLogId === log.id) {
                            onDeleteWorkItem(log.id);
                            setConfirmDeleteLogId(null);
                          } else {
                            setConfirmDeleteLogId(log.id);
                            setTimeout(() => setConfirmDeleteLogId(null), 3000);
                          }
                        }}
                        className={`p-1.5 rounded-lg transition-colors ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white' : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50'}`}
                        title="Excluir"
                      >
                        {confirmDeleteLogId === log.id ? (
                          <svg className="w-3.5 h-3.5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        )}
                      </button>
                      <button
                        onClick={() => onUpdateWorkItem(log.id, { concluido: true, data_conclusao: new Date().toISOString() })}
                        className="w-8 h-8 rounded-full border-2 border-slate-200 flex items-center justify-center text-slate-300 hover:border-emerald-500 hover:text-emerald-500 hover:bg-emerald-50 transition-all group/check ml-1"
                        title="Concluir"
                      >
                        <svg className="w-4 h-4 opacity-0 group-hover/check:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
          </div>
        ) : (
          <div className="text-center py-10 bg-slate-50/50 rounded-xl border-2 border-dashed border-slate-100">
            <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest">Nenhuma demanda em aberto</p>
          </div>
        )}
      </div>

      {/* Completed work items */}
      {completedWorkItems.length > 0 && (
        <div className="space-y-3">
          <button
            onClick={() => setIsCompletedLogsOpen(prev => !prev)}
            className="w-full flex items-center justify-between group cursor-pointer"
          >
            <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-l-4 border-emerald-500 pl-3">
              Concluídos ({completedWorkItems.length})
            </h5>
            <svg className={`w-4 h-4 text-slate-300 transition-transform ${isCompletedLogsOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {isCompletedLogsOpen && (
            <div className="space-y-2 opacity-60 animate-in slide-in-from-top-2 duration-200">
              {completedWorkItems
                .sort((a, b) => new Date(b.data_conclusao!).getTime() - new Date(a.data_conclusao!).getTime())
                .map(log => (
                  <div key={log.id} className="bg-white border border-slate-100 rounded-xl p-3 flex items-center justify-between gap-4">
                    <div className="flex-1 flex items-center gap-3 min-w-0">
                      <div className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                      <p className="text-xs font-medium text-slate-500 line-clamp-1">{log.descricao}</p>
                    </div>
                    <div className="flex gap-2 items-center shrink-0">
                      <button
                        onClick={() => onUpdateWorkItem(log.id, { concluido: false })}
                        className="text-[9px] font-black text-slate-300 hover:text-violet-600 uppercase"
                      >
                        Reabrir
                      </button>
                      <button
                        onClick={() => {
                          if (confirmDeleteLogId === log.id) {
                            onDeleteWorkItem(log.id);
                            setConfirmDeleteLogId(null);
                          } else {
                            setConfirmDeleteLogId(log.id);
                            setTimeout(() => setConfirmDeleteLogId(null), 3000);
                          }
                        }}
                        className={`p-1 rounded-lg transition-colors ${confirmDeleteLogId === log.id ? 'bg-rose-500 text-white' : 'text-slate-300 hover:text-rose-600'}`}
                      >
                        {confirmDeleteLogId === log.id ? (
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-4v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  );

  const renderCopilot = () => (
    <div className="flex flex-col h-full overflow-hidden bg-white border-l border-slate-100">
      {/* Copilot header */}
      <div className="shrink-0 px-4 py-3 flex items-center gap-3 border-b border-blue-50">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white shrink-0 shadow-lg">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-black uppercase tracking-widest text-violet-600">Copiloto Hermes</p>
          <p className="text-[8px] text-slate-400">RAG · Repositório</p>
        </div>
        <button
          onClick={() => sendChatMessage(`Analise o sistema "${systemName}" (status: ${STEP_LABELS[sysDetails.status]}) e sugira os próximos passos com base no contexto do repositório e das demandas abertas.`)}
          disabled={isChatLoading}
          className="shrink-0 px-2.5 py-1.5 rounded-xl text-[8px] font-black uppercase tracking-widest bg-slate-100 text-slate-600 hover:bg-slate-200 transition-all disabled:opacity-40"
        >
          Próx. passos
        </button>
      </div>

      {/* Artifacts toggle */}
      {artifacts.length > 0 && (
        <div className="shrink-0 px-4 py-2 border-b border-slate-50">
          <button
            onClick={() => setShowArtifacts(prev => !prev)}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all ${showArtifacts ? 'bg-indigo-50 border border-indigo-200 text-indigo-600' : 'bg-white border border-slate-200 text-slate-400 hover:text-slate-700'}`}
          >
            <div className="flex items-center gap-2">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Artefatos
            </div>
            <span className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center text-[9px]">{artifacts.length}</span>
          </button>
          {showArtifacts && (
            <div className="mt-2 max-h-48 overflow-y-auto space-y-2" style={{ scrollbarWidth: 'thin' }}>
              {artifacts.map(artifact => (
                <div key={artifact.id} className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-3 space-y-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[10px] font-black truncate text-slate-800">{artifact.title}</p>
                      <p className="text-[8px] text-slate-400">{artifact.createdAt}</p>
                    </div>
                    <button
                      onClick={() => handleCopyArtifact(artifact)}
                      className={`shrink-0 flex items-center gap-1 px-2 py-1 rounded-lg text-[9px] font-black transition-all ${copiedArtifactId === artifact.id ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                    >
                      {copiedArtifactId === artifact.id ? (
                        <><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> Copiado</>
                      ) : (
                        <><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" /></svg> Copiar</>
                      )}
                    </button>
                  </div>
                  <p className="text-[10px] leading-relaxed line-clamp-3 text-slate-500">{artifact.content}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-3 p-3 min-h-0" style={{ scrollbarWidth: 'thin', scrollbarColor: '#CBD5E0 transparent' }}>
        {chatMessages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center p-4 opacity-30">
            <svg className="w-10 h-10 mb-2 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Pergunte sobre este sistema</p>
            {!sysDetails.github_rag_synced_at && (
              <p className="text-[9px] text-slate-400 mt-2 max-w-[180px]">Sincronize o repositório para respostas contextualizadas</p>
            )}
          </div>
        )}
        {chatMessages.map((msg, i) => (
          <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            <div className={`max-w-[100%] px-3 py-2.5 rounded-2xl text-xs font-medium leading-relaxed shadow-sm ${
              msg.role === 'user'
                ? 'bg-slate-900 text-white rounded-br-none'
                : msg.isArtifact
                  ? 'bg-indigo-50 text-indigo-800 border border-indigo-200 rounded-bl-none'
                  : 'bg-blue-50 text-slate-700 rounded-bl-none'
            }`}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ node, ...props }) => <p className="mb-2 last:mb-0" {...props} />,
                  ul: ({ node, ...props }) => <ul className="list-disc ml-4 mb-2" {...props} />,
                  ol: ({ node, ...props }) => <ol className="list-decimal ml-4 mb-2" {...props} />,
                  li: ({ node, ...props }) => <li className="mb-0.5" {...props} />,
                  a: ({ node, ...props }) => <a className="text-violet-600 underline hover:text-violet-800" target="_blank" rel="noopener noreferrer" {...props} />,
                  strong: ({ node, ...props }) => <strong className="font-bold text-violet-700" {...props} />,
                }}
              >
                {msg.content}
              </ReactMarkdown>
            </div>
          </div>
        ))}
        {isChatLoading && (
          <div className="flex justify-start">
            <div className="px-4 py-3 rounded-2xl rounded-bl-none flex gap-1 items-center bg-blue-50">
              <span className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" />
              <span className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
              <span className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Chat input */}
      <div className="shrink-0 p-3 border-t border-slate-100">
        <div className="flex gap-2">
          <textarea
            value={chatInput}
            onChange={e => setChatInput(e.target.value)}
            onFocus={() => setIsChatFocused(true)}
            onBlur={() => setIsChatFocused(false)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendMessage(); }
            }}
            onPaste={(e: React.ClipboardEvent<HTMLTextAreaElement>) => {
              const pastedText = e.clipboardData.getData('text');
              if (pastedText && /\[\d{2}:\d{2}, \d{2}\/\d{2}\/\d{4}\]/.test(pastedText)) {
                e.preventDefault();
                const cleaned = pastedText.replace(/\[\d{2}:\d{2}, \d{2}\/\d{2}\/\d{4}\][^:]+:\s*/g, '').trim();
                setChatInput(prev => prev ? prev + '\n' + cleaned : cleaned);
              }
            }}
            placeholder="Pergunte sobre este sistema…"
            className={`flex-1 px-4 py-2 rounded-xl text-xs font-medium outline-none border border-slate-200 focus:ring-2 focus:ring-violet-400 bg-slate-50 text-slate-900 placeholder:text-slate-400 transition-all resize-none ${isChatFocused ? 'h-32' : 'h-10'}`}
          />
          <button
            onClick={handleSendMessage}
            disabled={isChatLoading || !chatInput.trim()}
            className="w-9 h-9 shrink-0 bg-violet-600 text-white rounded-xl flex items-center justify-center shadow-md hover:bg-violet-700 disabled:opacity-40 transition-all"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
        <button
          onClick={() => { if (chatInput.trim()) { const msg = chatInput; setChatInput(''); sendChatMessage(msg, true); } }}
          disabled={!chatInput.trim() || isChatLoading}
          className="mt-2 w-full py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest border border-indigo-200 text-indigo-500 hover:bg-indigo-50 transition-all disabled:opacity-30"
        >
          Gerar como Artefato →
        </button>
      </div>
    </div>
  );

  // ─── Main render ──────────────────────────────────────────────────────────

  return (
    <div className="fixed inset-0 z-[200] flex flex-col bg-white overflow-hidden">

      {/* ══════ HEADER ══════════════════════════════════════════════════════ */}
      <header className="shrink-0 px-4 md:px-6 py-3 border-b border-slate-200 bg-white flex items-center gap-3">
        <button
          onClick={onClose}
          className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-all"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
          </svg>
          <span className="hidden sm:inline">Voltar</span>
        </button>

        <div className="flex-1 min-w-0">
          <p className="text-[8px] font-black uppercase tracking-[0.3em] text-violet-600">Sala de Operações</p>
          <h1 className="text-base md:text-xl font-black tracking-tight leading-tight truncate text-slate-900">
            {systemName}
          </h1>
        </div>

        <span className={`shrink-0 px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-widest ${theme.pill}`}>
          {STEP_LABELS[sysDetails.status]}
        </span>

        {sysDetails.repositorio_principal && (
          <button
            onClick={() => onSyncGithubRepo(unit.id, sysDetails.repositorio_principal!)}
            disabled={isSyncingGithub}
            className="shrink-0 hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest border border-dashed border-violet-300 text-violet-600 hover:bg-violet-50 hover:border-violet-500 transition-all disabled:opacity-50"
          >
            {isSyncingGithub ? (
              <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
            ) : (
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            )}
            Sync RAG
          </button>
        )}
      </header>

      {/* ══════ MOBILE TAB BAR ══════════════════════════════════════════════ */}
      <nav className="lg:hidden shrink-0 flex border-b border-slate-200 bg-white">
        {(['visao-geral', 'logs', 'copiloto'] as MobileTab[]).map(tab => {
          const labels: Record<MobileTab, string> = { 'visao-geral': 'Visão Geral', logs: 'Logs', copiloto: 'Copiloto' };
          const isActive = mobileTab === tab;
          return (
            <button
              key={tab}
              onClick={() => setMobileTab(tab)}
              className={`flex-1 py-2.5 text-[9px] font-black uppercase tracking-widest transition-colors border-b-2 ${
                isActive
                  ? 'border-violet-500 text-violet-600'
                  : 'border-transparent text-slate-400 hover:text-slate-600'
              }`}
            >
              {labels[tab]}
            </button>
          );
        })}
      </nav>

      {/* ══════ CONTENT AREA ════════════════════════════════════════════════ */}
      <div className="flex-1 flex overflow-hidden">

        {/* Left: Overview */}
        <div className={`${mobileTab === 'visao-geral' ? 'flex' : 'hidden'} lg:flex flex-col lg:w-[420px] xl:w-[480px] shrink-0 border-r border-slate-100 overflow-hidden`}>
          {renderLeftColumn()}
        </div>

        {/* Center: Logs */}
        <div className={`${mobileTab === 'logs' ? 'flex' : 'hidden'} lg:flex flex-1 flex-col overflow-hidden`}>
          {renderLogsColumn()}
        </div>

        {/* Right: Copilot */}
        <div className={`${mobileTab === 'copiloto' ? 'flex' : 'hidden'} lg:flex lg:w-[360px] xl:w-[400px] shrink-0 flex-col overflow-hidden`}>
          {renderCopilot()}
        </div>
      </div>

      {/* ══════ MODAL: Editar Recurso ══════════════════════════════════════ */}
      {editingResource && (
        <div className="fixed inset-0 z-[400] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in zoom-in-95 duration-200">
          <div className="bg-white w-full max-w-md rounded-3xl shadow-2xl overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-lg font-black text-slate-900 tracking-tight">Editar {editingResource.label}</h3>
              <button onClick={() => setEditingResource(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">URL do Recurso</label>
                <input
                  type="text"
                  value={editingResource.value}
                  onChange={e => setEditingResource({ ...editingResource, value: e.target.value })}
                  placeholder="https://..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-5 py-3.5 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-violet-500 transition-all"
                  autoFocus
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      onUpdateSistema(unit.id, { [editingResource.field]: editingResource.value });
                      setEditingResource(null);
                    }
                  }}
                />
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => setEditingResource(null)}
                  className="flex-1 py-3 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-2xl transition-all"
                >
                  Cancelar
                </button>
                <button
                  onClick={() => {
                    onUpdateSistema(unit.id, { [editingResource.field]: editingResource.value });
                    setEditingResource(null);
                  }}
                  className="flex-1 bg-slate-900 text-white py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
                >
                  Salvar
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══════ MODAL: Editar Work Item ════════════════════════════════════ */}
      {editingWorkItem && (
        <div className="fixed inset-0 z-[400] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in zoom-in-95 duration-200">
          <div className="bg-white w-full max-w-lg rounded-3xl shadow-2xl overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-lg font-black text-slate-900 tracking-tight">Editar Demanda</h3>
              <button onClick={() => setEditingWorkItem(null)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-4">
              <textarea
                value={editingWorkItemText}
                onChange={e => setEditingWorkItemText(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-5 py-3.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-violet-500 transition-all resize-none min-h-[120px]"
                autoFocus
              />
              {editingWorkItemAttachments.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {editingWorkItemAttachments.map((at, i) => (
                    <div key={i} className="relative group/at">
                      <img src={at.valor} alt="preview" className="w-14 h-14 object-cover rounded-lg border border-slate-200" />
                      <button
                        onClick={() => setEditingWorkItemAttachments(prev => prev.filter((_, idx) => idx !== i))}
                        className="absolute -top-1 -right-1 bg-rose-500 text-white rounded-full p-0.5 opacity-0 group-hover/at:opacity-100 transition-all"
                      >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => setEditingWorkItem(null)}
                  className="flex-1 py-3 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 rounded-2xl transition-all"
                >
                  Cancelar
                </button>
                <button
                  onClick={() => {
                    onUpdateWorkItem(editingWorkItem.id, { descricao: editingWorkItemText, pool_dados: editingWorkItemAttachments });
                    setEditingWorkItem(null);
                  }}
                  disabled={!editingWorkItemText.trim()}
                  className="flex-1 bg-slate-900 text-white py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all disabled:opacity-50"
                >
                  Salvar
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
