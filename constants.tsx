
import { Status } from './types';

export const STATUS_COLORS: Record<string, string> = {
  'em andamento': 'bg-amber-300 text-amber-950 border-amber-600',
  'concluído': 'bg-emerald-500 text-white border-emerald-700',
  'concluido': 'bg-emerald-500 text-white border-emerald-700',
  'default': 'bg-slate-100 text-slate-600 border-slate-300'
};


export const PROJECT_COLORS: Record<string, string> = {
  'MAGO': 'text-purple-700 font-black',
  'SIGEX': 'text-indigo-700 font-black',
  'PROEN': 'text-cyan-700 font-black',
  'PLS-MEC': 'text-orange-700 font-black',
  'CLC': 'text-rose-700 font-black',
  'ASSISTÊNCIA': 'text-emerald-700 font-black',
  'SAÚDE': 'text-rose-600 font-black',
  'FINANCEIRO': 'text-violet-600 font-black',
  'SISTEMA': 'text-blue-600 font-black',
};

export const DEFAULT_JSON_URL = '/tarefas_andre.json';
export const ATIVIDADES_FEVEREIRO_URL = '/atividades_fevereiro.json';
