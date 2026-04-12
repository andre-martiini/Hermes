/**
 * knowledgeGraph.ts
 *
 * Utilities for the Fase 2B relational graph layer.
 * Manages directed, typed edges between ConhecimentoItem nodes stored in the
 * `knowledge_edges` Firestore collection.
 *
 * Design notes:
 * - Edges are directed: source → target with a RelationKind.
 * - Temporal validity is optional: valid_from / valid_until (ISO date YYYY-MM-DD).
 *   An edge with no bounds is always active.
 * - `getEdgesForItem` returns ALL edges where the item is either source or target,
 *   so callers can render both outgoing and incoming relations.
 */

import {
    addDoc,
    collection,
    deleteDoc,
    doc,
    getDocs,
    query,
    where,
} from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { KnowledgeEdge, RelationKind } from '../../types';

// ── Labels & colours ─────────────────────────────────────────────────────────

export const RELATION_KIND_LABELS: Record<RelationKind, string> = {
    references:   'Referencia',
    derived_from: 'Derivado de',
    supersedes:   'Substitui',
    related_to:   'Relacionado a',
    part_of:      'Componente de',
};

/** Tailwind classes for the relation badge (bg + text). */
export const RELATION_KIND_COLORS: Record<RelationKind, string> = {
    references:   'bg-blue-100 text-blue-700',
    derived_from: 'bg-purple-100 text-purple-700',
    supersedes:   'bg-rose-100 text-rose-700',
    related_to:   'bg-emerald-100 text-emerald-700',
    part_of:      'bg-amber-100 text-amber-700',
};

// ── Temporal policy ───────────────────────────────────────────────────────────

/**
 * Returns true if the edge is active on the given date (defaults to today).
 * An edge is active when:
 *   - valid_from is absent OR valid_from <= date
 *   - valid_until is absent OR valid_until >= date
 */
export function isEdgeActive(edge: KnowledgeEdge, date: Date = new Date()): boolean {
    const ymd = date.toISOString().split('T')[0];
    if (edge.valid_from && edge.valid_from > ymd) return false;
    if (edge.valid_until && edge.valid_until < ymd) return false;
    return true;
}

// ── Write operations ──────────────────────────────────────────────────────────

/**
 * Persists a new directed edge to Firestore.
 * Returns the generated document id.
 */
export async function addEdge(
    db: Firestore,
    edge: Omit<KnowledgeEdge, 'id'>,
): Promise<string> {
    const ref = await addDoc(collection(db, 'knowledge_edges'), edge);
    return ref.id;
}

/** Permanently removes an edge by its document id. */
export async function removeEdge(db: Firestore, edgeId: string): Promise<void> {
    await deleteDoc(doc(db, 'knowledge_edges', edgeId));
}

// ── Read operations ───────────────────────────────────────────────────────────

/**
 * Returns all edges where `itemId` is either the source or the target.
 * Runs two parallel Firestore queries (Firestore does not support OR across
 * different fields in a single query) and deduplicates by document id.
 */
export async function getEdgesForItem(
    db: Firestore,
    itemId: string,
): Promise<KnowledgeEdge[]> {
    const [asSource, asTarget] = await Promise.all([
        getDocs(query(collection(db, 'knowledge_edges'), where('source_id', '==', itemId))),
        getDocs(query(collection(db, 'knowledge_edges'), where('target_id', '==', itemId))),
    ]);

    const seen = new Set<string>();
    const edges: KnowledgeEdge[] = [];
    for (const snap of [asSource, asTarget]) {
        snap.docs.forEach(d => {
            if (!seen.has(d.id)) {
                seen.add(d.id);
                edges.push({ id: d.id, ...d.data() } as KnowledgeEdge);
            }
        });
    }
    // Sort by creation date descending
    return edges.sort((a, b) => b.created_at.localeCompare(a.created_at));
}

/**
 * Filters a list of edges to those that are currently active.
 * Convenience wrapper over `isEdgeActive` for rendering.
 */
export function filterActiveEdges(edges: KnowledgeEdge[], date?: Date): KnowledgeEdge[] {
    return edges.filter(e => isEdgeActive(e, date));
}
