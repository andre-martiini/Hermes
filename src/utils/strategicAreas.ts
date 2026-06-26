import { EstrategiaPilar } from '../../types';

export const STRATEGIC_AREA_OPTIONS: Array<{ value: string; label: string; pillar: EstrategiaPilar }> = [
  { value: 'CARREIRA', label: 'Carreira', pillar: 'carreira' },
  { value: 'FINANCAS', label: 'Financas', pillar: 'financas' },
  { value: 'SAUDE', label: 'Saude', pillar: 'saude' },
  { value: 'INTELECTUAL', label: 'Intelectual', pillar: 'intelectual' },
  { value: 'ESTILO DE VIDA', label: 'Estilo de vida', pillar: 'estilo_vida' },
];

export const OPERATIONAL_AREA_NAMES = ['CLC', 'ASSISTENCIA ESTUDANTIL', 'SIGEX'];

export const normalizeAreaName = (value?: string) =>
  String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .trim();

export const getAreaForStrategyPillar = (pillar: EstrategiaPilar) =>
  STRATEGIC_AREA_OPTIONS.find(option => option.pillar === pillar)?.value || 'GERAL';

export const isOperationalArea = (value?: string) =>
  OPERATIONAL_AREA_NAMES.includes(normalizeAreaName(value));

export const isStrategicArea = (value?: string) =>
  STRATEGIC_AREA_OPTIONS.some(option => option.value === normalizeAreaName(value));
