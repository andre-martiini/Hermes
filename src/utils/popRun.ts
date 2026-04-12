import {
    addDoc,
    collection,
    doc,
    getDoc,
    getDocs,
    limit,
    orderBy,
    query,
    updateDoc,
    where,
} from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type {
    POP,
    POPLearningEvent,
    POPLearningEventType,
    POPRun,
    POPRunStatus,
    POPStepRun,
    RoutingAssessment,
    IntakeSourceRef,
} from '../../types';

interface CreatePOPRunParams {
    pop: POP;
    caso_origem_tipo: POPRun['caso_origem_tipo'];
    caso_origem_id: string;
    assessment?: RoutingAssessment;
    input_refs?: IntakeSourceRef[];
}

interface POPRunAuditEvent {
    event_type: 'run_created' | 'run_status_changed' | 'step_resolved' | 'learning_recorded';
    pop_id: string;
    pop_run_id?: string;
    context_kind?: POPRun['caso_origem_tipo'];
    context_id?: string;
    from_status?: POPRunStatus;
    to_status?: POPRunStatus;
    step_id?: string;
    step_status?: POPStepRun['status'];
    learning_event_id?: string;
    learning_type?: POPLearningEventType;
    ts: string;
}

async function logPOPRunEvent(
    db: Firestore,
    event: POPRunAuditEvent,
): Promise<void> {
    await addDoc(collection(db, 'pop_run_events'), event);
}

const ALLOWED_RUN_TRANSITIONS: Record<POPRunStatus, POPRunStatus[]> = {
    draft: ['proposed', 'rejected'],
    proposed: ['in_review', 'approved', 'rejected'],
    in_review: ['approved', 'rejected', 'proposed'],
    approved: ['applied', 'in_review'],
    rejected: ['draft', 'proposed'],
    applied: [],
};

export function canTransitionPOPRunStatus(from: POPRunStatus, to: POPRunStatus): boolean {
    return ALLOWED_RUN_TRANSITIONS[from]?.includes(to) ?? false;
}

export function buildInitialStepRuns(pop: POP): POPStepRun[] {
    return [...pop.passos]
        .sort((a, b) => a.ordem - b.ordem)
        .map(step => ({
            step_id: step.id,
            status: 'pending',
            rationale: step.descricao,
        }));
}

export async function createPOPRunFromPOP(
    db: Firestore,
    params: CreatePOPRunParams,
): Promise<string> {
    const now = new Date().toISOString();
    const ref = await addDoc(collection(db, 'pop_runs'), {
        pop_id: params.pop.id,
        caso_origem_tipo: params.caso_origem_tipo,
        caso_origem_id: params.caso_origem_id,
        status: 'draft',
        assessment: params.assessment,
        input_refs: params.input_refs ?? [],
        steps_resolved: buildInitialStepRuns(params.pop),
        created_at: now,
        updated_at: now,
    } as Omit<POPRun, 'id'>);
    await logPOPRunEvent(db, {
        event_type: 'run_created',
        pop_id: params.pop.id,
        pop_run_id: ref.id,
        context_kind: params.caso_origem_tipo,
        context_id: params.caso_origem_id,
        ts: now,
    });
    return ref.id;
}

export async function updatePOPRunStatus(
    db: Firestore,
    popRunId: string,
    currentStatus: POPRunStatus,
    newStatus: POPRunStatus,
): Promise<void> {
    if (!canTransitionPOPRunStatus(currentStatus, newStatus)) {
        throw new Error(`Transição inválida: ${currentStatus} -> ${newStatus}`);
    }
    const existing = await getPOPRunById(db, popRunId);
    await updateDoc(doc(db, 'pop_runs', popRunId), {
        status: newStatus,
        updated_at: new Date().toISOString(),
    });
    await logPOPRunEvent(db, {
        event_type: 'run_status_changed',
        pop_id: existing?.pop_id || '',
        pop_run_id: popRunId,
        context_kind: existing?.caso_origem_tipo,
        context_id: existing?.caso_origem_id,
        from_status: currentStatus,
        to_status: newStatus,
        ts: new Date().toISOString(),
    });
}

export async function getPOPRunById(
    db: Firestore,
    popRunId: string,
): Promise<POPRun | null> {
    const snap = await getDoc(doc(db, 'pop_runs', popRunId));
    if (!snap.exists()) return null;
    return { id: snap.id, ...snap.data() } as POPRun;
}

export async function applyPOPStepResolution(
    db: Firestore,
    popRunId: string,
    steps_resolved: POPStepRun[],
): Promise<void> {
    const existing = await getPOPRunById(db, popRunId);
    await updateDoc(doc(db, 'pop_runs', popRunId), {
        steps_resolved,
        updated_at: new Date().toISOString(),
    });
    const changedStep = existing?.steps_resolved.find((previous, index) => previous.status !== steps_resolved[index]?.status);
    if (changedStep) {
        const currentStep = steps_resolved.find(item => item.step_id === changedStep.step_id);
        await logPOPRunEvent(db, {
            event_type: 'step_resolved',
            pop_id: existing?.pop_id || '',
            pop_run_id: popRunId,
            context_kind: existing?.caso_origem_tipo,
            context_id: existing?.caso_origem_id,
            step_id: changedStep.step_id,
            step_status: currentStep?.status,
            ts: new Date().toISOString(),
        });
    }
}

export async function createPOPLearningEvent(
    db: Firestore,
    popId: string,
    event: Omit<POPLearningEvent, 'id' | 'created_at' | 'pop_id'> & { tipo: POPLearningEventType },
): Promise<string> {
    const ref = await addDoc(collection(db, 'pops', popId, 'learning_events'), {
        ...event,
        pop_id: popId,
        created_at: new Date().toISOString(),
    });
    await logPOPRunEvent(db, {
        event_type: 'learning_recorded',
        pop_id: popId,
        pop_run_id: event.pop_run_id,
        learning_event_id: ref.id,
        learning_type: event.tipo,
        ts: new Date().toISOString(),
    });
    return ref.id;
}

export async function getRecentPOPLearningEvents(
    db: Firestore,
    popId: string,
    maxResults = 20,
): Promise<POPLearningEvent[]> {
    const snap = await getDocs(
        query(
            collection(db, 'pops', popId, 'learning_events'),
            orderBy('created_at', 'desc'),
            limit(maxResults),
        ),
    );
    return snap.docs.map(item => ({ id: item.id, ...item.data() } as POPLearningEvent));
}

export async function getRecentPOPRunsForPOP(
    db: Firestore,
    popId: string,
    maxResults = 20,
): Promise<POPRun[]> {
    const snap = await getDocs(
        query(
            collection(db, 'pop_runs'),
            where('pop_id', '==', popId),
            orderBy('created_at', 'desc'),
            limit(maxResults),
        ),
    );
    return snap.docs.map(item => ({ id: item.id, ...item.data() } as POPRun));
}
