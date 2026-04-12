import { httpsCallable } from 'firebase/functions';
import type { Functions } from 'firebase/functions';
import type { Firestore } from 'firebase/firestore';
import type { ApprovalMode, RoutingAssessment } from '../../types';
import type { RoutingContextKind } from './routingLog';
import { logRoutingEvent } from './routingLog';
import { getRegisteredTool } from './toolRegistry';

const APPROVAL_RANK: Record<ApprovalMode, number> = {
  automatic: 0,
  confirm: 1,
  required: 2,
};

function stricter(a: ApprovalMode, b: ApprovalMode): ApprovalMode {
  return APPROVAL_RANK[a] >= APPROVAL_RANK[b] ? a : b;
}

export interface CallRegisteredToolOpts {
  db: Firestore;
  functions: Functions;
  routingAssessment: RoutingAssessment;
  approvalGranted: boolean;
  onBlocked: (reason: 'not_registered' | 'approval_required') => void;
  context: {
    kind: RoutingContextKind;
    id?: string;
    label?: string;
  };
  domainHint?: string;
}

export type ToolExecutionDecision = {
  allowed: boolean;
  reason?: 'not_registered' | 'approval_required' | 'domain_not_allowed' | 'not_auto_executable';
  effectiveMode?: ApprovalMode;
};

export function evaluateRegisteredToolExecution(
  toolId: string,
  opts: Pick<CallRegisteredToolOpts, 'routingAssessment' | 'approvalGranted' | 'domainHint'>,
  mode: 'manual' | 'auto' = 'manual',
): ToolExecutionDecision {
  const tool = getRegisteredTool(toolId);
  if (!tool) return { allowed: false, reason: 'not_registered' };

  const domain = opts.domainHint || 'general';
  if (!tool.allowed_domains.includes('general') && !tool.allowed_domains.includes(domain as any)) {
    return { allowed: false, reason: 'domain_not_allowed' };
  }

  const effectiveMode = stricter(tool.min_approval_mode, opts.routingAssessment.approval_mode);
  const canExecute = effectiveMode === 'automatic' || opts.approvalGranted;
  if (!canExecute) {
    return { allowed: false, reason: 'approval_required', effectiveMode };
  }

  if (mode === 'auto' && !tool.can_auto_execute) {
    return { allowed: false, reason: 'not_auto_executable', effectiveMode };
  }

  return { allowed: true, effectiveMode };
}

export async function callRegisteredTool<TResult = unknown>(
  toolId: string,
  payload: Record<string, unknown>,
  opts: CallRegisteredToolOpts,
): Promise<TResult | null> {
  const { db, functions, routingAssessment, approvalGranted, onBlocked, context } = opts;
  const tool = getRegisteredTool(toolId);
  const decision = evaluateRegisteredToolExecution(toolId, {
    routingAssessment,
    approvalGranted,
    domainHint: opts.domainHint,
  });

  if (!tool || !decision.allowed) {
    onBlocked(decision.reason === 'not_registered' ? 'not_registered' : 'approval_required');
    return null;
  }

  logRoutingEvent(db, {
    context_kind: context.kind,
    context_id: context.id ?? toolId,
    context_label: context.label ?? tool.label,
    assessment: routingAssessment,
    session_released: approvalGranted,
  });

  const fn = httpsCallable<Record<string, unknown>, TResult>(functions, tool.callable);
  const res = await fn(payload);
  return res.data;
}
