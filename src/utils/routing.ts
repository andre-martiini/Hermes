import type { ApprovalMode, RiskLevel, RoutingAssessment, RoutingMode, TipoAcao } from '../../types';

interface AssessRoutingParams {
  tipoAcao: TipoAcao;
  origin?: 'manual' | 'audio' | 'whatsapp' | 'google';
  inputText?: string;
  extraContext?: string;
  hasRagContext?: boolean;
  extraContextFileCount?: number;
  hasMeetingContext?: boolean;
}

const clampScore = (value: number) => Math.max(0, Math.min(1, Number(value.toFixed(2))));

export const assessTaskRouting = ({
  tipoAcao,
  origin = 'manual',
  inputText = '',
  extraContext = '',
  hasRagContext = false,
  extraContextFileCount = 0,
  hasMeetingContext = false,
}: AssessRoutingParams): RoutingAssessment => {
  const rationale: string[] = [];
  const normalizedTextLength = (inputText.trim().length + extraContext.trim().length);

  let clarity = 0.45;
  if (normalizedTextLength > 80) clarity += 0.15;
  if (normalizedTextLength > 220) clarity += 0.1;
  if (origin === 'manual') clarity += 0.1;
  if (origin === 'whatsapp' || origin === 'audio') clarity -= 0.08;
  if (tipoAcao === 'deep') clarity -= 0.07;

  let context = 0.2;
  if (hasRagContext) {
    context += 0.3;
    rationale.push('Base de conhecimento selecionada para apoiar a decisão.');
  }
  if (extraContextFileCount > 0) {
    context += Math.min(0.3, extraContextFileCount * 0.12);
    rationale.push(`Há ${extraContextFileCount} arquivo(s) extra(s) vinculados à demanda.`);
  }
  if (hasMeetingContext) {
    context += 0.2;
    rationale.push('A demanda possui contexto de reunião associado.');
  }

  let impact = tipoAcao === 'deep' ? 0.72 : 0.35;
  if (origin === 'google') impact += 0.08;
  if (extraContextFileCount > 0) impact += 0.08;
  if (hasMeetingContext) impact += 0.05;

  clarity = clampScore(clarity);
  context = clampScore(context);
  impact = clampScore(impact);

  let route: RoutingMode = 'deterministic';
  if (tipoAcao === 'deep' || clarity < 0.5 || context < 0.45 || impact > 0.65) {
    route = 'orchestrated';
  }

  let risk: RiskLevel = 'low';
  if (impact >= 0.5 || context < 0.45) risk = 'medium';
  if (impact >= 0.75 || (context < 0.35 && clarity < 0.45)) risk = 'high';

  let approval: ApprovalMode = 'automatic';
  if (route === 'orchestrated' || risk === 'medium') approval = 'confirm';
  if (risk === 'high' || (tipoAcao === 'deep' && context < 0.4)) approval = 'required';

  if (route === 'orchestrated') rationale.push('A demanda exige composição de contexto e plano multietapa.');
  else rationale.push('A demanda parece suficientemente clara para rota direta.');

  if (approval === 'required') rationale.push('Ação com impacto relevante ou contexto insuficiente exige aprovação explícita.');
  else if (approval === 'confirm') rationale.push('Uma confirmação curta reduz risco operacional antes da execução.');

  return {
    route,
    approval_mode: approval,
    risk_level: risk,
    clarity_score: clarity,
    context_score: context,
    impact_score: impact,
    rationale,
  };
};
