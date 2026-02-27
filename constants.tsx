
import { Status, Prioridade } from './types';

export const STATUS_COLORS: Record<string, string> = {
  'em andamento': 'bg-amber-300 text-amber-950 border-amber-600',
  'concluído': 'bg-emerald-500 text-white border-emerald-700',
  'concluido': 'bg-emerald-500 text-white border-emerald-700',
  'default': 'bg-slate-100 text-slate-600 border-slate-300'
};

export const PRIORITY_COLORS: Record<Prioridade, string> = {
  'alta': 'bg-rose-600 text-white shadow-sm',
  'média': 'bg-amber-600 text-white shadow-sm',
  'baixa': 'bg-emerald-600 text-white shadow-sm',
};

export const PROJECT_COLORS: Record<string, string> = {
  'MAGO': 'text-purple-700 font-black',
  'SIGEX': 'text-indigo-700 font-black',
  'PROEN': 'text-cyan-700 font-black',
  'PLS-MEC': 'text-orange-700 font-black',
  'CLC (Licitações e Compras)': 'text-rose-700 font-black',
  'Assistência Estudantil': 'text-emerald-700 font-black',
};

export const DEFAULT_JSON_URL = '/tarefas_andre.json';
export const ATIVIDADES_FEVEREIRO_URL = '/atividades_fevereiro.json';

export const SLIDES_HISTORY_KEY = 'hermes_slides_history';
