import type { ConhecimentoItem, MemoryLocation, Tarefa } from '../../types';

const normalize = (value?: string | null) =>
  (value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '') || 'geral';

export function deriveMemoryLocation(
  item: Pick<ConhecimentoItem, 'categoria' | 'tipo_arquivo' | 'base_id' | 'origem' | 'memory_location' | 'intake_record'>,
): MemoryLocation {
  if (item.memory_location) return item.memory_location;

  const domainHint = item.intake_record?.domain_hint || '';
  let wing = 'captura';
  if (domainHint === 'sistemas_e_codigo') wing = 'sistemas';
  if (domainHint === 'operacoes_administrativas') wing = 'operacoes';

  return {
    wing,
    room: normalize(item.base_id || item.origem?.modulo || item.categoria || domainHint || 'biblioteca'),
    drawer: normalize(item.tipo_arquivo || 'documento'),
    cabinet: normalize(item.origem?.id_origem || item.base_id || 'corrente'),
    path_label: `${wing} / ${normalize(item.base_id || item.origem?.modulo || item.categoria || domainHint || 'biblioteca')} / ${normalize(item.tipo_arquivo || 'documento')}`,
  };
}

export function deriveTaskMemoryRoom(task: Pick<Tarefa, 'sistema' | 'categoria' | 'tipo_acao' | 'id'>): string {
  return normalize(task.sistema || task.categoria || task.tipo_acao || task.id || 'acao');
}

export function formatMemoryLocation(location?: MemoryLocation | null): string {
  if (!location) return 'Sem localização';
  const segments = [location.wing, location.room, location.drawer, location.cabinet].filter(Boolean);
  return segments.join(' / ');
}
