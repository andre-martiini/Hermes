import { describe, expect, it } from 'vitest';
import type { POP, RoutingAssessment } from '../../types';
import { canTransitionPOPStatus } from './pop';
import { assessPOPFit, buildPOPRationale, rankPOPsForCase } from './popMatching';
import { buildInitialStepRuns, canTransitionPOPRunStatus } from './popRun';

const baseAssessment: RoutingAssessment = {
  route: 'orchestrated',
  approval_mode: 'confirm',
  risk_level: 'medium',
  clarity_score: 0.72,
  context_score: 0.68,
  impact_score: 0.61,
  rationale: ['Demanda multietapa com contexto suficiente.'],
};

const adminPOP: POP = {
  id: 'pop-admin',
  nome: 'Encaminhamento de Processo',
  slug: 'encaminhamento-de-processo',
  descricao: 'Procedimento para análise e encaminhamento administrativo.',
  dominio: 'operacoes_administrativas',
  status: 'active',
  versao: 1,
  gatilhos: ['encaminhamento', 'processo'],
  pre_condicoes: ['documento principal anexado'],
  passos: [
    {
      id: 'step-1',
      ordem: 1,
      titulo: 'Ler processo',
      descricao: 'Analisar a documentação principal.',
      tipo: 'collect',
      obrigatorio: true,
    },
    {
      id: 'step-2',
      ordem: 2,
      titulo: 'Gerar minuta',
      descricao: 'Produzir minuta de encaminhamento.',
      tipo: 'generate_artifact',
      obrigatorio: true,
    },
  ],
  excecoes: ['processo incompleto'],
  artefatos_gerados: ['minuta', 'checklist'],
  criterios_validacao: ['referenciar base documental'],
  risk_level: 'medium',
  approval_mode_default: 'confirm',
  tags: ['processo', 'encaminhamento'],
  created_at: '2026-04-12T00:00:00.000Z',
};

const techPOP: POP = {
  ...adminPOP,
  id: 'pop-tech',
  nome: 'Consolidação de Bug',
  slug: 'consolidacao-de-bug',
  descricao: 'Procedimento técnico para consolidar relatos em issue packet.',
  dominio: 'sistemas_e_codigo',
  gatilhos: ['bug', 'erro'],
  artefatos_gerados: ['issue packet'],
  tags: ['bug', 'sistema'],
};

describe('POP workflow rules', () => {
  it('enforces POP status transitions', () => {
    expect(canTransitionPOPStatus('draft', 'active')).toBe(true);
    expect(canTransitionPOPStatus('active', 'archived')).toBe(true);
    expect(canTransitionPOPStatus('archived', 'active')).toBe(false);
  });

  it('enforces POPRun status transitions', () => {
    expect(canTransitionPOPRunStatus('draft', 'proposed')).toBe(true);
    expect(canTransitionPOPRunStatus('proposed', 'approved')).toBe(true);
    expect(canTransitionPOPRunStatus('approved', 'draft')).toBe(false);
  });

  it('builds initial step runs ordered by procedure step', () => {
    const runs = buildInitialStepRuns(adminPOP);
    expect(runs).toHaveLength(2);
    expect(runs[0]).toMatchObject({ step_id: 'step-1', status: 'pending' });
    expect(runs[1]).toMatchObject({ step_id: 'step-2', status: 'pending' });
  });

  it('scores a compatible POP above an incompatible one', () => {
    const ranked = rankPOPsForCase([adminPOP, techPOP], {
      dominio: 'operacoes_administrativas',
      routing_assessment: baseAssessment,
      intake_record: {
        channel: 'manual_text',
        confidentiality: 'internal',
        processing_status: 'prepared',
        request_text: 'Preciso de encaminhamento deste processo com minuta.',
      },
      tags: ['processo'],
      expectedArtifacts: ['minuta'],
      text: 'Encaminhamento de processo com documento base.',
    });

    expect(ranked[0].pop.id).toBe('pop-admin');
    expect(ranked[0].score).toBeGreaterThan(ranked[1].score);
  });

  it('explains the rationale for the selected POP', () => {
    const assessment = assessPOPFit(adminPOP, {
      dominio: 'operacoes_administrativas',
      routing_assessment: baseAssessment,
      tags: ['encaminhamento'],
      expectedArtifacts: ['minuta'],
      text: 'Encaminhamento do processo administrativo',
    });

    expect(assessment.score).toBeGreaterThan(0.3);
    expect(buildPOPRationale(assessment).length).toBeGreaterThan(10);
  });
});
