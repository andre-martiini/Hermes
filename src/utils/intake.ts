import type {
  ConhecimentoItem,
  IntakeChannel,
  IntakeConfidentiality,
  IntakeProcessingStatus,
  IntakeRecord,
  IntakeSourceRef,
  PoolItem,
} from '../../types';

type KnowledgeDestination = Pick<ConhecimentoItem, 'origem' | 'parent_id' | 'categoria' | 'base_id'>;

interface CreateIntakeRecordParams {
  channel: IntakeChannel;
  domainHint?: string;
  confidentiality?: IntakeConfidentiality;
  processingStatus?: IntakeProcessingStatus;
  requestedBy?: string;
  requestText?: string;
  sourceArtifactIds?: string[];
  sourceRefs?: IntakeSourceRef[];
}

interface BuildKnowledgeItemFromPoolItemParams extends KnowledgeDestination {
  item: PoolItem;
  fileName?: string;
  domainHint?: string;
  intakeChannel: IntakeChannel;
  sourceArtifactId?: string | null;
}

interface BuildKnowledgeLinkItemParams extends KnowledgeDestination {
  title: string;
  url: string;
  createdAt?: string;
  domainHint?: string;
  intakeChannel?: IntakeChannel;
  requestedBy?: string;
  requestText?: string;
}

const normalizeFileType = (fileName?: string, fallback = 'unknown') => {
  const normalized = (fileName || '').trim().toLowerCase();
  if (!normalized) return fallback;
  const parts = normalized.split('.');
  return parts.length > 1 ? parts.pop() || fallback : fallback;
};

const artifactOriginKindByChannel: Record<IntakeChannel, ConhecimentoItem['artifact_origin_kind']> = {
  manual_text: 'link_capture',
  audio_upload: 'audio_transcription',
  audio_recording: 'audio_transcription',
  whatsapp_messages: 'extra_context',
  file_upload: 'file_upload',
  drive_file: 'file_upload',
  uploaded_file: 'file_upload',
  shared_link: 'link_capture',
  meeting_transcript: 'meeting_transcription',
  meeting_transcription: 'meeting_transcription',
  repository_event: 'repository_sync',
};

export const createIntakeRecord = ({
  channel,
  domainHint,
  confidentiality = 'internal',
  processingStatus = 'received',
  requestedBy,
  requestText,
  sourceArtifactIds,
  sourceRefs,
}: CreateIntakeRecordParams): IntakeRecord => ({
  id: crypto.randomUUID(),
  received_at: new Date().toISOString(),
  channel,
  confidentiality,
  processing_status: processingStatus,
  ...(domainHint ? { domain_hint: domainHint } : {}),
  ...(requestedBy ? { requested_by: requestedBy } : {}),
  ...(requestText ? { request_text: requestText } : {}),
  ...(sourceArtifactIds && sourceArtifactIds.length > 0 ? { source_artifact_ids: sourceArtifactIds } : {}),
  ...(sourceRefs && sourceRefs.length > 0 ? { source_refs: sourceRefs } : {}),
});

export const inferTaskIntakeChannel = (origin?: string): IntakeChannel => {
  if (origin === 'audio') return 'audio_upload';
  if (origin === 'whatsapp') return 'whatsapp_messages';
  if (origin === 'google') return 'drive_file';
  return 'manual_text';
};

export const buildKnowledgeItemFromPoolItem = ({
  item,
  fileName,
  origem = null,
  parent_id,
  categoria,
  base_id,
  domainHint,
  intakeChannel,
  sourceArtifactId = null,
}: BuildKnowledgeItemFromPoolItemParams): ConhecimentoItem => ({
  id: item.id,
  titulo: item.nome || 'Sem titulo',
  tipo_arquivo: item.tipo === 'link' ? 'link' : normalizeFileType(fileName || item.nome),
  url_drive: item.valor,
  tamanho: 0,
  data_criacao: item.data_criacao,
  origem,
  ...(typeof parent_id !== 'undefined' ? { parent_id } : {}),
  ...(typeof categoria !== 'undefined' ? { categoria } : {}),
  ...(typeof base_id !== 'undefined' ? { base_id } : {}),
  intake_record: createIntakeRecord({
    channel: intakeChannel,
    domainHint,
    processingStatus: 'prepared',
    sourceArtifactIds: [item.id],
  }),
  artifact_role: 'source',
  artifact_origin_kind: artifactOriginKindByChannel[intakeChannel],
  source_artifact_id: sourceArtifactId,
  version: 1,
});

export const buildKnowledgeLinkItem = ({
  title,
  url,
  origem = null,
  parent_id,
  categoria,
  base_id,
  createdAt,
  domainHint,
  intakeChannel = 'shared_link',
  requestedBy,
  requestText,
}: BuildKnowledgeLinkItemParams): Omit<ConhecimentoItem, 'id'> => ({
  titulo: title,
  tipo_arquivo: 'link',
  url_drive: url,
  tamanho: 0,
  data_criacao: createdAt || new Date().toISOString(),
  origem,
  ...(typeof parent_id !== 'undefined' ? { parent_id } : {}),
  ...(typeof categoria !== 'undefined' ? { categoria } : {}),
  ...(typeof base_id !== 'undefined' ? { base_id } : {}),
  intake_record: createIntakeRecord({
    channel: intakeChannel,
    domainHint,
    processingStatus: 'prepared',
    requestedBy,
    requestText: requestText || title,
  }),
  artifact_role: 'source',
  artifact_origin_kind: artifactOriginKindByChannel[intakeChannel],
  source_artifact_id: null,
  version: 1,
});
