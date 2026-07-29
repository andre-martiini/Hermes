import { PlanoTrabalho, PlanoTrabalhoItem } from '../../types';

export const ASSISTENCIA_ENTREGA =
  'Acompanhamento de estudantes da assistência estudantil realizados';

export const NAO_VINCULADA_DESCRICAO =
  'Atividades principalmente administrativas, não vinculadas a entregas inerentes à coordenadoria.';

export const PGD_OWN_UNIT_CATALOG = [
  'Contratação de empresa de engenharia para a elaboração de projetos executivos e demais documentos concluída',
  'Contratação de empresa especializada em cobertura de estacionamento de veículos, concluída.',
  'Contratação de empresa especializada em instalação e implantação de rede elétrica, encaminhada.',
  'Contratação de empresa fornecedora de Bens Permanentes para Laboratório de Mecânica, concluída.',
  'Contratação de empresa fornecedora de cortinas, concluída.',
  'Contratação de empresa fornecedora de eletrodomésticos, concluída.',
  'Contratação de empresa fornecedora de insumos agrícolas, concluída.',
  'Contratação de empresa fornecedora de materiais de consumo para atendimento das demandas da Coordenadoria de Serviços Auxiliares e Transportes, concluída.',
  'Contratação de empresa fornecedora de materiais de enfermaria, concluída.',
  'Contratação de empresa fornecedora de materiais e equipamentos de áudio e vídeo, concluída.',
  'Contratação de empresa prestadora de serviço de vigilância patrimonial, concluída.',
  'Contratação de empresa prestadora de serviços de apoio às ações de promoção da saúde mental de servidores, estagiários e prestadores de serviços, concluída.',
  'Contratação de empresa prestadora do serviço de almoxarifado virtual, concluída.',
  'Contratação de fornecedores de materiais esportivos, concluída.',
] as const;

export const PGD_SEEDED_DESCRIPTIONS: Record<string, string> = {
  'Contratação de empresa fornecedora de materiais de enfermaria, concluída.':
    'Acompanhamento e apoio ao processo de aquisição de materiais de enfermaria.',
  'Contratação de empresa fornecedora de insumos agrícolas, concluída.':
    'Acompanhamento e suporte para a fase de planejamento da contratação.',
  'Contratação de empresa prestadora de serviço de vigilância patrimonial, encaminhada.':
    'Planejamento da contratação e acompanhamento para a devida tramitação.',
  'Contratação de empresa prestadora de serviço de vigilância patrimonial, concluída.':
    'Planejamento da contratação e acompanhamento para a devida tramitação.',
  [ASSISTENCIA_ENTREGA]:
    'Recebimento de comprovantes, gestão de dados dos alunos e emissão das folhas de pagamento dos alunos contemplados na Assistência Estudantil.',
  'Contratação de empresa prestadora de serviços de apoio às ações de promoção da saúde mental de servidores, estagiários e prestadores de serviços, concluída.':
    'Acompanhamento dos procedimentos necessários para esta contratação.',
  'Contratação de empresa fornecedora de eletrodomésticos, concluída.':
    'Acompanhamento da Intenção de Registro de Preços para Aquisição dos Eletrodomésticos, verificando a tramitação do processo.',
  'Contratação de empresa fornecedora de Bens Permanentes para Laboratório de Mecânica, concluída.':
    'Acompanhamento do processo de aquisição de bens permanentes para laboratório de mecânica, orientação e elaboração dos documentos de planejamento da contratação.',
  'Contratação de empresa fornecedora de materiais e equipamentos de áudio e vídeo, concluída.':
    'Acompanhamento da contratação de empresa fornecedora de equipamentos de áudio e vídeo, verificando a tramitação do processo.',
  'Contratação de empresa prestadora do serviço de almoxarifado virtual, concluída.':
    'Acompanhamento da contratação, verificando se há novas atualizações.',
  'Não vinculadas a entregas': NAO_VINCULADA_DESCRICAO,
};

export interface PgdPeriod {
  mesAno: string;
  dataInicio: string;
  dataFim: string;
}

export interface PgdPlanDelivery {
  origem: 'Própria Unidade' | 'Outra Unidade' | 'Não vinculadas a entregas';
  unidade: string;
  entrega: string;
  descricao: string;
  percentual: number;
  plano_entrega_codigo?: string;
  fixed?: boolean;
}

export interface CreatePgdPlanPayload {
  sessao_id: string;
  mes_ano: string;
  data_inicio: string;
  data_fim: string;
  unidade: string;
  modalidade: string;
  entregas: PgdPlanDelivery[];
}

const isoLocal = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const getPgdTargetPeriod = (today = new Date()): PgdPeriod => {
  const year = today.getFullYear();
  const month = today.getMonth() + (today.getDate() >= 16 ? 1 : 0);
  const start = new Date(year, month, 1);
  return getPgdPeriodFromMonth(
    `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}`,
  );
};

export const getPgdPeriodFromMonth = (monthValue: string): PgdPeriod => {
  if (!/^\d{4}-\d{2}$/.test(monthValue)) {
    throw new Error('Informe um mês válido para o plano de trabalho.');
  }
  const [year, month] = monthValue.split('-').map(Number);
  if (month < 1 || month > 12) {
    throw new Error('Informe um mês válido para o plano de trabalho.');
  }
  const start = new Date(year, month - 1, 1);
  const end = new Date(year, month, 0);
  return {
    mesAno: `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}`,
    dataInicio: isoLocal(start),
    dataFim: isoLocal(end),
  };
};

export const distributePgdPercentages = (count: number): number[] => {
  if (!Number.isInteger(count) || count < 1) {
    throw new Error('O plano precisa ter ao menos uma entrega.');
  }
  if (count > 20) {
    throw new Error('O plano comporta no máximo 20 entregas com blocos mínimos de 5%.');
  }
  const base = Math.floor(100 / count / 5) * 5;
  const values = Array.from({ length: count }, () => base);
  let remainder = 100 - base * count;
  let index = 0;
  while (remainder > 0) {
    values[index] += 5;
    remainder -= 5;
    index += 1;
  }
  return values;
};

const normalize = (value: string) =>
  value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLowerCase();

export const normalizePgdDeliveryIdentity = (value: string) =>
  normalize(value)
    .replace(/,\s*(concluida|encaminhada)\.?$/, '')
    .replace(/[.,;:]+$/, '');

export const findLatestDescription = (
  entrega: string,
  plans: PlanoTrabalho[],
): string => {
  const target = normalizePgdDeliveryIdentity(entrega);
  const sorted = [...plans].sort((a, b) => b.mes_ano.localeCompare(a.mes_ano));
  for (const plan of sorted) {
    const item = plan.itens.find(
      candidate => normalizePgdDeliveryIdentity(candidate.entrega) === target,
    );
    if (item?.descricao?.trim()) return item.descricao.trim();
  }
  return PGD_SEEDED_DESCRIPTIONS[entrega] || '';
};

export const suggestPgdDescription = (entrega: string): string =>
  PGD_SEEDED_DESCRIPTIONS[entrega]
  || `Acompanhamento, orientação e apoio aos procedimentos relacionados à entrega: ${entrega}`;

export const getSourcePlan = (
  plans: PlanoTrabalho[],
  targetMonth: string,
): PlanoTrabalho | undefined => {
  const [year, month] = targetMonth.split('-').map(Number);
  const previous = new Date(year, month - 2, 1);
  const previousKey = `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, '0')}`;
  return plans.find(plan => plan.mes_ano === previousKey)
    || [...plans].sort((a, b) => b.mes_ano.localeCompare(a.mes_ano))[0];
};

export const isOwnUnitItem = (item: PlanoTrabalhoItem) =>
  normalize(item.origem).includes('propria')
  || normalize(item.unidade).includes('clc-bsf');
