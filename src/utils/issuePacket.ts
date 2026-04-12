/**
 * issuePacket.ts
 *
 * CRUD utilities for IssuePacket documents (Fase 5 — Propostas Técnicas Revisáveis).
 * Collection: `issue_packets`
 *
 * Lifecycle: draft → review → approved | rejected → applied
 */

import {
    addDoc,
    collection,
    doc,
    getDocs,
    limit,
    orderBy,
    query,
    setDoc,
    updateDoc,
    where,
} from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type {
    IssuePacket,
    IssuePacketStatus,
    IssuePacketTipo,
    IssuePacketSeveridade,
} from '../../types';
import { createIntakeRecord } from './intake';

// ── Labels ────────────────────────────────────────────────────────────────────

export const TIPO_LABELS: Record<IssuePacketTipo, string> = {
    bug:          'Bug',
    melhoria:     'Melhoria',
    refatoracao:  'Refatoração',
    seguranca:    'Segurança',
};

export const SEVERIDADE_LABELS: Record<IssuePacketSeveridade, string> = {
    baixa:   'Baixa',
    media:   'Média',
    alta:    'Alta',
    critica: 'Crítica',
};

export const STATUS_LABELS: Record<IssuePacketStatus, string> = {
    draft:    'Rascunho',
    review:   'Em Revisão',
    approved: 'Aprovado',
    rejected: 'Rejeitado',
    applied:  'Aplicado',
};

export const SEVERIDADE_COLORS: Record<IssuePacketSeveridade, string> = {
    baixa:   'bg-slate-100 text-slate-600',
    media:   'bg-amber-100 text-amber-700',
    alta:    'bg-orange-100 text-orange-700',
    critica: 'bg-rose-100 text-rose-700',
};

export const TIPO_COLORS: Record<IssuePacketTipo, string> = {
    bug:         'bg-red-100 text-red-700',
    melhoria:    'bg-blue-100 text-blue-700',
    refatoracao: 'bg-violet-100 text-violet-700',
    seguranca:   'bg-rose-100 text-rose-800',
};

export const STATUS_COLORS: Record<IssuePacketStatus, string> = {
    draft:    'bg-slate-100 text-slate-600',
    review:   'bg-amber-100 text-amber-700',
    approved: 'bg-emerald-100 text-emerald-700',
    rejected: 'bg-rose-100 text-rose-700',
    applied:  'bg-blue-100 text-blue-700',
};

// ── Valid status transitions ──────────────────────────────────────────────────

const ALLOWED_TRANSITIONS: Record<IssuePacketStatus, IssuePacketStatus[]> = {
    draft:    ['review', 'rejected'],
    review:   ['approved', 'rejected', 'draft'],
    approved: ['applied', 'draft'],
    rejected: ['draft'],
    applied:  [],
};

export function canTransition(from: IssuePacketStatus, to: IssuePacketStatus): boolean {
    return ALLOWED_TRANSITIONS[from]?.includes(to) ?? false;
}

// ── Write operations ──────────────────────────────────────────────────────────

/**
 * Creates a new IssuePacket document. Returns the generated id.
 * `id` field on the input is ignored — Firestore auto-generates it.
 */
export async function createIssuePacket(
    db: Firestore,
    packet: Omit<IssuePacket, 'id' | 'created_at'>,
): Promise<string> {
    const now = new Date().toISOString();
    const ref = await addDoc(collection(db, 'issue_packets'), {
        ...packet,
        created_at: now,
        data_atualizacao: now,
        intake_record:
            packet.intake_record ??
            createIntakeRecord({
                channel: 'manual_text',
                domainHint: 'sistemas_dev',
                processingStatus: 'prepared',
                requestText: packet.titulo,
            }),
    });
    return ref.id;
}

/**
 * Updates the status of an existing packet, enforcing the allowed transition graph.
 * Throws if the transition is not permitted.
 */
export async function updateIssuePacketStatus(
    db: Firestore,
    packetId: string,
    currentStatus: IssuePacketStatus,
    newStatus: IssuePacketStatus,
    opts: { reviewer?: string; reviewNote?: string } = {},
): Promise<void> {
    if (!canTransition(currentStatus, newStatus)) {
        throw new Error(
            `Transição inválida: ${currentStatus} → ${newStatus}`,
        );
    }
    const now = new Date().toISOString();
    await updateDoc(doc(db, 'issue_packets', packetId), {
        status: newStatus,
        data_atualizacao: now,
        ...(opts.reviewer ? { reviewed_by: opts.reviewer, reviewed_at: now } : {}),
        ...(opts.reviewNote !== undefined ? { review_note: opts.reviewNote } : {}),
    });
}

/**
 * Partial update for editing packet fields (draft/review stage only).
 * Does not touch status or provenance fields.
 */
export async function updateIssuePacket(
    db: Firestore,
    packetId: string,
    updates: Partial<Pick<IssuePacket, 'titulo' | 'descricao' | 'tipo' | 'severidade' | 'affected_files' | 'proposed_changes' | 'rationale' | 'knowledge_item_ids' | 'suggested_pop_id' | 'pop_run_id'>>,
): Promise<void> {
    await updateDoc(doc(db, 'issue_packets', packetId), {
        ...updates,
        data_atualizacao: new Date().toISOString(),
    });
}

// ── Read operations ───────────────────────────────────────────────────────────

/** Returns all packets for a given sistema, ordered by creation date desc. */
export async function getIssuePacketsForSistema(
    db: Firestore,
    sistemaId: string,
): Promise<IssuePacket[]> {
    const snap = await getDocs(
        query(
            collection(db, 'issue_packets'),
            where('sistema_id', '==', sistemaId),
            orderBy('created_at', 'desc'),
        ),
    );
    return snap.docs.map(d => ({ id: d.id, ...d.data() } as IssuePacket));
}

/** Returns up to `maxResults` most recent packets across all sistemas. */
export async function getRecentIssuePackets(
    db: Firestore,
    maxResults = 100,
): Promise<IssuePacket[]> {
    const snap = await getDocs(
        query(
            collection(db, 'issue_packets'),
            orderBy('created_at', 'desc'),
            limit(maxResults),
        ),
    );
    return snap.docs.map(d => ({ id: d.id, ...d.data() } as IssuePacket));
}
