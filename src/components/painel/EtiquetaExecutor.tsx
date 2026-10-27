import React from 'react';
import type { EtapaExecutor } from '../../../types';
import { ROTULO_EXECUTOR, executorDaEtapa } from '../../utils/subtarefas';

/**
 * Selo da etapa que o agente faz ou prepara. Etapa só do André não leva selo.
 *
 * O texto é "agente", nunca o nome de um produto: qualquer IA com o conector
 * Gaspar pode executar. A cor sozinha não carrega o sentido (verde × roxo) — o
 * texto do selo diz a diferença.
 */
const ESTILO: Record<Exclude<EtapaExecutor, 'humano'>, { claro: string; escuro: string }> = {
  agente: {
    claro: 'text-[#0b5a43] bg-[#dff3ea]',
    escuro: 'text-emerald-300 bg-emerald-900/40',
  },
  agente_aprovado: {
    claro: 'text-[#4c1d95] bg-[#ece6fa]',
    escuro: 'text-violet-300 bg-violet-900/40',
  },
};

interface EtiquetaExecutorProps {
  etapa: unknown;
  isDark?: boolean;
}

const EtiquetaExecutor: React.FC<EtiquetaExecutorProps> = ({ etapa, isDark = false }) => {
  const executor = executorDaEtapa(etapa);
  if (executor === 'humano') return null;
  const estilo = ESTILO[executor];
  return (
    <span
      data-testid="etiqueta-executor"
      data-executor={executor}
      className={`flex-none text-[11px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${isDark ? estilo.escuro : estilo.claro}`}
    >
      {ROTULO_EXECUTOR[executor]}
    </span>
  );
};

export default EtiquetaExecutor;
