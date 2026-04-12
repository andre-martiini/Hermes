/**
 * knowledgeWrite.ts
 *
 * Canonical helper for versioned upserts of ConhecimentoItem documents.
 * Single source of truth for all write paths to the `conhecimento` collection
 * that need versioning semantics.
 *
 * Usage:
 *   await upsertKnowledgeItem(db, item);
 *   await upsertKnowledgeItem(db, item, { reason: 'system_sync', actor: 'rag_pipeline' });
 */

import { collection, doc, getDoc, addDoc, setDoc } from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { ConhecimentoItem, KnowledgeVersionEntry } from '../../types';
import { createIntakeRecord } from './intake';

// Fields whose change is considered semantically meaningful and triggers a version snapshot.
export const SIGNIFICANT_FIELDS: Array<keyof ConhecimentoItem> = [
  'titulo',
  'tipo_arquivo',
  'url_drive',
  'texto_bruto',
  'resumo_tldr',
  'tags',
  'categoria',
  'base_id',
  'parent_id',
  'origem',
];

/**
 * Djb2 hash — deterministic, fast, no dependencies.
 * Used to deduplicate version snapshots: if the content hash hasn't
 * changed since the last snapshot, we skip writing a new one.
 */
function djb2Hash(value: string): string {
  let hash = 5381;
  for (let i = 0; i < value.length; i++) {
    hash = ((hash << 5) + hash) ^ value.charCodeAt(i);
    hash = hash >>> 0; // keep unsigned 32-bit
  }
  return hash.toString(16);
}

/**
 * Computes a short content hash over the significant fields of an item.
 * Used to skip redundant history snapshots when content is identical.
 */
export function computeContentHash(item: Partial<ConhecimentoItem>): string {
  const parts = SIGNIFICANT_FIELDS.map(f => JSON.stringify((item as any)[f] ?? null));
  return djb2Hash(parts.join('|'));
}

export type KnowledgeUpdateReason = KnowledgeVersionEntry['reason'];

export interface UpsertKnowledgeOpts {
  reason?: KnowledgeUpdateReason;
  actor?: string;
}

/**
 * Upserts a ConhecimentoItem in Firestore with full versioning semantics.
 *
 * - If `item.id` is set → update path: computes a diff against the existing doc,
 *   writes a history snapshot to the `history` subcollection when meaningful
 *   fields changed, then merges the new state onto the main document.
 * - If `item.id` is absent → create path: writes a new document with version=1
 *   and a canonical intake_record.
 *
 * Does NOT call showToast — the caller is responsible for user feedback.
 */
export async function upsertKnowledgeItem(
  db: Firestore,
  item: Partial<ConhecimentoItem>,
  opts: UpsertKnowledgeOpts = {},
): Promise<void> {
  const reason: KnowledgeUpdateReason = opts.reason ?? 'human_edit';
  const actor = opts.actor ?? 'user';

  // Sanitise: remove undefined values so Firestore doesn't complain.
  const cleanItem: Partial<ConhecimentoItem> = JSON.parse(JSON.stringify(item));

  if (item.id) {
    // ── UPDATE PATH ──────────────────────────────────────────────────────────
    const docRef = doc(db, 'conhecimento', item.id);
    const existingSnap = await getDoc(docRef);
    const existing = existingSnap.exists()
      ? (existingSnap.data() as ConhecimentoItem)
      : null;

    const changedFields = existing
      ? SIGNIFICANT_FIELDS.filter((field) => {
          const next = cleanItem[field];
          if (typeof next === 'undefined') return false;
          return JSON.stringify(existing[field]) !== JSON.stringify(next);
        })
      : [];

    const hasMeaningfulChange = changedFields.length > 0;

    // Write history snapshot BEFORE updating the main document.
    // Skip if content hash matches the previous snapshot (dedup).
    if (hasMeaningfulChange && existing) {
      const incomingHash = computeContentHash(cleanItem);
      const previousHash = (existing as any).content_hash as string | undefined;
      const isDuplicate = !!previousHash && previousHash === incomingHash;

      if (!isDuplicate) {
        const historyVersion = existing.version ?? 1;
        const historyDocId = `v${historyVersion}_${reason}`;
        await setDoc(
          doc(db, 'conhecimento', item.id, 'history', historyDocId),
          {
            item_id: item.id,
            captured_at: new Date().toISOString(),
            version: historyVersion,
            reason,
            actor,
            changed_fields: changedFields,
            content_hash: incomingHash,
            titulo: existing.titulo ?? null,
            resumo_tldr: existing.resumo_tldr ?? null,
            tags: existing.tags ?? [],
            categoria: existing.categoria ?? null,
          } satisfies Omit<KnowledgeVersionEntry, 'id' | 'texto_bruto'>,
        );
      }
    }

    await setDoc(
      docRef,
      {
        ...cleanItem,
        data_atualizacao: new Date().toISOString(),
        intake_record:
          cleanItem.intake_record ??
          existing?.intake_record ??
          createIntakeRecord({
            channel:
              cleanItem.tipo_arquivo === 'link' ? 'shared_link' : 'manual_text',
            domainHint: 'captura_e_conhecimento',
            processingStatus: 'prepared',
            requestText:
              cleanItem.titulo ?? existing?.titulo ?? 'item_manual',
          }),
        artifact_role:
          cleanItem.artifact_role ?? existing?.artifact_role ?? 'source',
        artifact_origin_kind:
          cleanItem.artifact_origin_kind ??
          existing?.artifact_origin_kind ??
          (cleanItem.tipo_arquivo === 'link' ? 'link_capture' : 'file_upload'),
        source_artifact_id:
          typeof cleanItem.source_artifact_id !== 'undefined'
            ? cleanItem.source_artifact_id
            : (existing?.source_artifact_id ?? null),
        version: hasMeaningfulChange
          ? Math.max(existing?.version ?? 1, 1) + 1
          : (cleanItem.version ?? existing?.version ?? 1),
        last_update_reason: hasMeaningfulChange
          ? reason
          : (cleanItem.last_update_reason ?? existing?.last_update_reason ?? reason),
        last_updated_by: actor,
        content_hash: computeContentHash(cleanItem),
      },
      { merge: true },
    );
  } else {
    // ── CREATE PATH ───────────────────────────────────────────────────────────
    await addDoc(collection(db, 'conhecimento'), {
      ...cleanItem,
      data_criacao: new Date().toISOString(),
      intake_record:
        cleanItem.intake_record ??
        createIntakeRecord({
          channel:
            cleanItem.tipo_arquivo === 'link' ? 'shared_link' : 'manual_text',
          domainHint: 'captura_e_conhecimento',
          processingStatus: 'prepared',
          requestText: cleanItem.titulo ?? 'item_manual',
        }),
      artifact_role: cleanItem.artifact_role ?? 'source',
      artifact_origin_kind:
        cleanItem.artifact_origin_kind ??
        (cleanItem.tipo_arquivo === 'link' ? 'link_capture' : 'file_upload'),
      source_artifact_id:
        typeof cleanItem.source_artifact_id !== 'undefined'
          ? cleanItem.source_artifact_id
          : null,
      version: cleanItem.version ?? 1,
      last_update_reason: reason,
      last_updated_by: actor,
    });
  }
}
