import type { IntakeRecord, POP, RoutingAssessment } from '../../types';

interface POPMatchInput {
    dominio?: string;
    subdominio?: string;
    intake_record?: IntakeRecord;
    routing_assessment?: RoutingAssessment;
    tags?: string[];
    expectedArtifacts?: string[];
    text?: string;
}

export interface POPFitAssessment {
    pop: POP;
    score: number;
    reasons: string[];
    missing_requirements: string[];
}

const clampScore = (value: number) => Math.max(0, Math.min(1, Number(value.toFixed(2))));

const normalizeText = (value?: string) => (value || '').trim().toLowerCase();

const computeTagOverlap = (a: string[] = [], b: string[] = []) => {
    if (a.length === 0 || b.length === 0) return 0;
    const setB = new Set(b.map(item => item.toLowerCase()));
    const overlap = a.filter(item => setB.has(item.toLowerCase())).length;
    return overlap / Math.max(a.length, b.length);
};

export function assessPOPFit(pop: POP, input: POPMatchInput): POPFitAssessment {
    const reasons: string[] = [];
    const missing_requirements: string[] = [];

    let score = 0.1;

    if (input.dominio && pop.dominio === input.dominio) {
        score += 0.35;
        reasons.push('Domínio do procedimento coincide com o caso.');
    } else if (input.dominio) {
        missing_requirements.push('Domínio divergente do procedimento.');
    }

    if (input.subdominio && pop.subdominio && pop.subdominio === input.subdominio) {
        score += 0.1;
        reasons.push('Subdomínio aderente ao contexto atual.');
    }

    const requestText = normalizeText(input.intake_record?.request_text || input.text);
    if (requestText) {
        const triggerMatches = pop.gatilhos.filter(trigger => requestText.includes(normalizeText(trigger)));
        if (triggerMatches.length > 0) {
            score += Math.min(0.2, triggerMatches.length * 0.08);
            reasons.push('Há gatilhos textuais compatíveis com o procedimento.');
        }
    }

    if (input.routing_assessment) {
        if (input.routing_assessment.risk_level === pop.risk_level) {
            score += 0.08;
            reasons.push('Nível de risco compatível com o procedimento.');
        }
        if (input.routing_assessment.approval_mode === pop.approval_mode_default) {
            score += 0.07;
            reasons.push('Modo de aprovação alinhado ao procedimento.');
        }
    }

    const tagOverlap = computeTagOverlap(pop.tags, input.tags);
    if (tagOverlap > 0) {
        score += tagOverlap * 0.15;
        reasons.push('Tags do caso coincidem parcialmente com o procedimento.');
    }

    if (input.expectedArtifacts?.length) {
        const artifactOverlap = computeTagOverlap(pop.artefatos_gerados, input.expectedArtifacts);
        if (artifactOverlap > 0) {
            score += artifactOverlap * 0.15;
            reasons.push('Artefatos esperados são compatíveis com o POP.');
        } else {
            missing_requirements.push('O POP não prevê o artefato esperado para este caso.');
        }
    }

    for (const preCondicao of pop.pre_condicoes) {
        const normalized = normalizeText(preCondicao);
        if (normalized.includes('documento') && !requestText) {
            missing_requirements.push(`Pré-condição potencialmente ausente: ${preCondicao}`);
        }
    }

    return {
        pop,
        score: clampScore(score),
        reasons,
        missing_requirements,
    };
}

export function rankPOPsForCase(pops: POP[], input: POPMatchInput): POPFitAssessment[] {
    return pops
        .map(pop => assessPOPFit(pop, input))
        .sort((a, b) => b.score - a.score);
}

export function buildPOPRationale(assessment: POPFitAssessment): string {
    if (assessment.reasons.length === 0) {
        return 'O procedimento foi sugerido por compatibilidade estrutural básica.';
    }
    return assessment.reasons.join(' ');
}
