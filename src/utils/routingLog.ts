/**
 * routingLog.ts
 *
 * Emite eventos de decisão de roteamento na coleção `routing_events` do Firestore.
 * Cada vez que um RoutingAssessment é calculado e uma ação assistida é iniciada
 * (ou bloqueada), o contexto fica registrado para auditoria.
 *
 * Schema da coleção `routing_events`:
 *   {
 *     context_kind: 'task' | 'system' | 'tool'
 *     context_id?:    string   — id da tarefa / sistema / ferramenta
 *     context_label?: string   — nome legível por humanos
 *     route:          'deterministic' | 'orchestrated'
 *     approval_mode:  'automatic' | 'confirm' | 'required'
 *     risk_level:     'low' | 'medium' | 'high'
 *     clarity_score:  number
 *     context_score:  number
 *     impact_score:   number
 *     session_released: boolean  — o usuário clicou em "Liberar sessão"?
 *     ts:             string (ISO-8601)
 *   }
 */

import { addDoc, collection } from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { RoutingAssessment } from '../../types';

export type RoutingContextKind = 'task' | 'system' | 'tool';

export interface RoutingLogEvent {
  context_kind: RoutingContextKind;
  context_id?: string;
  context_label?: string;
  assessment: RoutingAssessment;
  /** true quando o usuário clicou em "Liberar sessão" nesta sessão */
  session_released?: boolean;
}

/**
 * Persiste um evento de decisão de roteamento. Fire-and-forget — não lança
 * exceção para o chamador; erros são silenciados para não degradar a UX.
 */
export function logRoutingEvent(
  db: Firestore,
  event: RoutingLogEvent,
): void {
  const { assessment, ...rest } = event;
  addDoc(collection(db, 'routing_events'), {
    ...rest,
    route: assessment.route,
    approval_mode: assessment.approval_mode,
    risk_level: assessment.risk_level,
    clarity_score: assessment.clarity_score,
    context_score: assessment.context_score,
    impact_score: assessment.impact_score,
    session_released: rest.session_released ?? false,
    ts: new Date().toISOString(),
  }).catch(() => {
    // Silently ignore — audit log must never break the main flow.
  });
}
