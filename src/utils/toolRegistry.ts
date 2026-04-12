/**
 * toolRegistry.ts
 *
 * Registry estático de ferramentas assistidas homologadas no Hermes.
 * Cada entrada define a identidade, o risco associado e os requisitos
 * de aprovação antes de uma chamada ser disparada.
 *
 * Regra: toda função callable que executa IA ou acessa dados externos
 * deve ter uma entrada aqui antes de ser exposta ao usuário.
 *
 * Consulta rápida:
 *   import { getRegisteredTool, TOOL_REGISTRY } from './toolRegistry';
 *   const tool = getRegisteredTool('slides');
 */

import type { ApprovalMode, RiskLevel } from '../../types';

export type ToolImpactLevel = 'low' | 'medium' | 'high';
export type ToolDomain = 'captura_e_conhecimento' | 'operacoes_administrativas' | 'sistemas_e_codigo' | 'general';

export interface RegisteredTool {
  /** Identificador canônico — usado em routing_events.context_id */
  id: string;
  /** Nome legível por humanos */
  label: string;
  /** Descrição curta do que a ferramenta faz */
  description: string;
  /** Callable Firebase ou endpoint de destino */
  callable: string;
  /** Nível de risco intrínseco da ferramenta (independente do assessment dinâmico) */
  base_risk_level: RiskLevel;
  /** Modo de aprovação mínimo exigido (pode ser elevado pelo assessment dinâmico) */
  min_approval_mode: ApprovalMode;
  /** Se true, o resultado desta ferramenta pode modificar dados externos */
  has_side_effects: boolean;
  /** Impacto operacional primário da ferramenta */
  impact_level: ToolImpactLevel;
  /** Domínios autorizados para uso primário */
  allowed_domains: ToolDomain[];
  /** Pode ser executada automaticamente quando o contexto permitir */
  can_auto_execute: boolean;
  /** Frente do roadmap onde esta ferramenta se encaixa */
  roadmap_phase: string;
}

export const TOOL_REGISTRY: RegisteredTool[] = [
  {
    id: 'slides',
    label: 'Gerador de Slides',
    description: 'Transforma texto bruto em apresentação estruturada com slides.',
    callable: 'gerarSlidesIA',
    base_risk_level: 'low',
    min_approval_mode: 'automatic',
    has_side_effects: false,
    impact_level: 'low',
    allowed_domains: ['general', 'captura_e_conhecimento'],
    can_auto_execute: true,
    roadmap_phase: 'Fase 0+',
  },
  {
    id: 'whatsapp_assistant',
    label: 'Assistente WhatsApp',
    description: 'Consulta e analisa histórico de conversas do WhatsApp vinculadas.',
    callable: 'askWhatsAppAssistantSecure',
    base_risk_level: 'low',
    min_approval_mode: 'automatic',
    has_side_effects: false,
    impact_level: 'low',
    allowed_domains: ['general', 'captura_e_conhecimento', 'operacoes_administrativas'],
    can_auto_execute: true,
    roadmap_phase: 'Fase 0+',
  },
  {
    id: 'task_copilot',
    label: 'Copiloto de Ação',
    description: 'Assistente contextual de execução de tarefas — chat, resumo e geração de artefatos.',
    callable: 'askTaskAssistant',
    base_risk_level: 'medium',
    min_approval_mode: 'confirm',
    has_side_effects: false,
    impact_level: 'medium',
    allowed_domains: ['general', 'operacoes_administrativas', 'captura_e_conhecimento'],
    can_auto_execute: false,
    roadmap_phase: 'Fase 1',
  },
  {
    id: 'system_copilot',
    label: 'Copiloto de Sistema',
    description: 'Assistente contextual de sistemas em produção ou testes.',
    callable: 'askTaskAssistant',
    base_risk_level: 'high',
    min_approval_mode: 'required',
    has_side_effects: false,
    impact_level: 'high',
    allowed_domains: ['sistemas_e_codigo'],
    can_auto_execute: false,
    roadmap_phase: 'Fase 1',
  },
  {
    id: 'audio_transcription',
    label: 'Transcrição de Áudio',
    description: 'Converte áudio em texto estruturado via Whisper.',
    callable: 'transcreverAudio',
    base_risk_level: 'low',
    min_approval_mode: 'automatic',
    has_side_effects: false,
    impact_level: 'low',
    allowed_domains: ['general', 'captura_e_conhecimento', 'operacoes_administrativas', 'sistemas_e_codigo'],
    can_auto_execute: true,
    roadmap_phase: 'Fase 0+',
  },
  {
    id: 'meeting_transcription',
    label: 'Transcrição de Reunião',
    description: 'Processa gravações de reunião e extrai ata estruturada.',
    callable: 'transcreverAudio',
    base_risk_level: 'low',
    min_approval_mode: 'automatic',
    has_side_effects: false,
    impact_level: 'low',
    allowed_domains: ['general', 'captura_e_conhecimento', 'operacoes_administrativas'],
    can_auto_execute: true,
    roadmap_phase: 'Fase 0+',
  },
  {
    id: 'task_generation',
    label: 'Geração de Ação com IA',
    description: 'Classifica e estrutura nova ação a partir de entrada livre.',
    callable: 'generate_task_with_ia',
    base_risk_level: 'low',
    min_approval_mode: 'automatic',
    has_side_effects: true,
    impact_level: 'medium',
    allowed_domains: ['general', 'operacoes_administrativas', 'captura_e_conhecimento'],
    can_auto_execute: false,
    roadmap_phase: 'Fase 1',
  },
  {
    id: 'knowledge_vectorization',
    label: 'Vetorização de Conhecimento',
    description: 'Extrai texto e vetoriza um item do repositório de conhecimento.',
    callable: 'vectorizeKnowledgeItemCallable',
    base_risk_level: 'low',
    min_approval_mode: 'automatic',
    has_side_effects: true,
    impact_level: 'low',
    allowed_domains: ['general', 'captura_e_conhecimento', 'operacoes_administrativas', 'sistemas_e_codigo'],
    can_auto_execute: true,
    roadmap_phase: 'Fase 2A',
  },
  {
    id: 'extra_context_ingestion',
    label: 'Ingestão de Contexto Extra',
    description: 'Processa e indexa anexos de contexto extra para ações.',
    callable: 'processExtraContextFile',
    base_risk_level: 'low',
    min_approval_mode: 'automatic',
    has_side_effects: true,
    impact_level: 'low',
    allowed_domains: ['general', 'captura_e_conhecimento', 'operacoes_administrativas', 'sistemas_e_codigo'],
    can_auto_execute: true,
    roadmap_phase: 'Fase 1',
  },
  {
    id: 'raw_drive_ingestion',
    label: 'Ingestão RAW do Drive',
    description: 'Executa o ciclo homologado de ingestão do diretório raw.',
    callable: 'processRawDriveCycle',
    base_risk_level: 'medium',
    min_approval_mode: 'confirm',
    has_side_effects: true,
    impact_level: 'medium',
    allowed_domains: ['general', 'captura_e_conhecimento', 'operacoes_administrativas', 'sistemas_e_codigo'],
    can_auto_execute: false,
    roadmap_phase: 'Fase 1',
  },
  {
    id: 'github_repo_sync',
    label: 'Sync de Repositório',
    description: 'Sincroniza repositório GitHub e atualiza o espelho semântico.',
    callable: 'sync_github_repo',
    base_risk_level: 'medium',
    min_approval_mode: 'confirm',
    has_side_effects: true,
    impact_level: 'medium',
    allowed_domains: ['sistemas_e_codigo'],
    can_auto_execute: false,
    roadmap_phase: 'Fase 5',
  },
];

/** Busca uma ferramenta pelo id canônico. Retorna undefined se não homologada. */
export function getRegisteredTool(id: string): RegisteredTool | undefined {
  return TOOL_REGISTRY.find(t => t.id === id);
}

/** Retorna todas as ferramentas com side-effects (candidatas a controle extra). */
export function getSideEffectTools(): RegisteredTool[] {
  return TOOL_REGISTRY.filter(t => t.has_side_effects);
}

/** Retorna ferramentas que exigem ao menos confirmação antes de chamar. */
export function getToolsRequiringApproval(): RegisteredTool[] {
  return TOOL_REGISTRY.filter(
    t => t.min_approval_mode === 'confirm' || t.min_approval_mode === 'required',
  );
}

export function listAutoExecutableTools(): RegisteredTool[] {
  return TOOL_REGISTRY.filter(t => t.can_auto_execute);
}
