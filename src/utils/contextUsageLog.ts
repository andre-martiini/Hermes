import { addDoc, collection } from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { ContextBundle } from '../../types';

type ContextUsageKind = 'task_copilot' | 'system_copilot';

export interface ContextUsageEvent {
  context_kind: 'task' | 'system';
  context_id?: string;
  context_label?: string;
  usage_kind: ContextUsageKind;
  context_bundle: ContextBundle;
  suggested_pop_id?: string | null;
  pop_run_id?: string | null;
}

export function logContextUsageEvent(db: Firestore, event: ContextUsageEvent): void {
  const totalEntries =
    event.context_bundle.identity.length +
    event.context_bundle.session.length +
    event.context_bundle.scoped.length +
    event.context_bundle.deep.length;

  addDoc(collection(db, 'context_usage_events'), {
    context_kind: event.context_kind,
    context_id: event.context_id,
    context_label: event.context_label,
    usage_kind: event.usage_kind,
    layers: {
      L0: event.context_bundle.identity.length,
      L1: event.context_bundle.session.length,
      L2: event.context_bundle.scoped.length,
      L3: event.context_bundle.deep.length,
    },
    total_entries: totalEntries,
    suggested_pop_id: event.suggested_pop_id ?? null,
    pop_run_id: event.pop_run_id ?? null,
    ts: new Date().toISOString(),
  }).catch(() => {
    // fire-and-forget
  });
}
