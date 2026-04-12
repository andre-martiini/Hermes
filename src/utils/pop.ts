import {
    addDoc,
    collection,
    doc,
    getDocs,
    limit,
    orderBy,
    query,
    updateDoc,
    where,
} from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { POP, POPStatus, POPStepType, RiskLevel, ApprovalMode } from '../../types';
import { createIntakeRecord } from './intake';

export const POP_STATUS_LABELS: Record<POPStatus, string> = {
    draft: 'Rascunho',
    active: 'Ativo',
    archived: 'Arquivado',
};

export const POP_STEP_TYPE_LABELS: Record<POPStepType, string> = {
    collect: 'Coleta',
    analyze: 'Análise',
    decide: 'Decisão',
    generate_artifact: 'Geração de artefato',
    route: 'Encaminhamento',
    validate: 'Validação',
    close: 'Encerramento',
};

export const POP_STATUS_COLORS: Record<POPStatus, string> = {
    draft: 'bg-slate-100 text-slate-600',
    active: 'bg-emerald-100 text-emerald-700',
    archived: 'bg-amber-100 text-amber-700',
};

export const POP_RISK_COLORS: Record<RiskLevel, string> = {
    low: 'bg-slate-100 text-slate-600',
    medium: 'bg-amber-100 text-amber-700',
    high: 'bg-rose-100 text-rose-700',
};

export const POP_APPROVAL_LABELS: Record<ApprovalMode, string> = {
    automatic: 'Automático',
    confirm: 'Confirmação',
    required: 'Aprovação',
};

const ALLOWED_TRANSITIONS: Record<POPStatus, POPStatus[]> = {
    draft: ['active', 'archived'],
    active: ['draft', 'archived'],
    archived: ['draft'],
};

export function canTransitionPOPStatus(from: POPStatus, to: POPStatus): boolean {
    return ALLOWED_TRANSITIONS[from]?.includes(to) ?? false;
}

export async function createPOP(
    db: Firestore,
    pop: Omit<POP, 'id' | 'created_at'>,
): Promise<string> {
    const now = new Date().toISOString();
    const ref = await addDoc(collection(db, 'pops'), {
        ...pop,
        created_at: now,
        updated_at: now,
        intake_record:
            createIntakeRecord({
                channel: 'manual_text',
                domainHint: pop.dominio,
                processingStatus: 'prepared',
                requestText: pop.nome,
            }),
    });
    return ref.id;
}

export async function updatePOP(
    db: Firestore,
    popId: string,
    updates: Partial<Pick<POP, 'nome' | 'slug' | 'descricao' | 'dominio' | 'subdominio' | 'gatilhos' | 'pre_condicoes' | 'passos' | 'excecoes' | 'artefatos_gerados' | 'criterios_validacao' | 'risk_level' | 'approval_mode_default' | 'tags' | 'versao' | 'status'>>,
): Promise<void> {
    await updateDoc(doc(db, 'pops', popId), {
        ...updates,
        updated_at: new Date().toISOString(),
    });
}

export async function updatePOPStatus(
    db: Firestore,
    popId: string,
    currentStatus: POPStatus,
    newStatus: POPStatus,
): Promise<void> {
    if (!canTransitionPOPStatus(currentStatus, newStatus)) {
        throw new Error(`Transição inválida: ${currentStatus} -> ${newStatus}`);
    }
    await updateDoc(doc(db, 'pops', popId), {
        status: newStatus,
        updated_at: new Date().toISOString(),
    });
}

export async function getRecentPOPs(db: Firestore, maxResults = 100): Promise<POP[]> {
    const snap = await getDocs(
        query(
            collection(db, 'pops'),
            orderBy('updated_at', 'desc'),
            limit(maxResults),
        ),
    );
    return snap.docs.map(d => ({ id: d.id, ...d.data() } as POP));
}

export async function getPOPsByDomain(db: Firestore, dominio: string): Promise<POP[]> {
    const snap = await getDocs(
        query(
            collection(db, 'pops'),
            where('dominio', '==', dominio),
            orderBy('updated_at', 'desc'),
        ),
    );
    return snap.docs.map(d => ({ id: d.id, ...d.data() } as POP));
}
