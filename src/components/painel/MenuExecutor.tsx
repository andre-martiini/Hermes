import React, { useEffect, useRef, useState } from 'react';
import type { EtapaExecutor } from '../../../types';
import { ROTULO_EXECUTOR, executorDaEtapa } from '../../utils/subtarefas';

interface MenuExecutorProps {
  etapa: unknown;
  /** Texto da etapa, só para o rótulo acessível do botão. */
  textoEtapa: string;
  onEscolher: (executor: EtapaExecutor) => void;
  isDark?: boolean;
}

const OPCOES: EtapaExecutor[] = ['agente', 'agente_aprovado', 'humano'];

/**
 * Menu pequeno para o André corrigir quem executa a etapa.
 *
 * A escolha é gravada como `executor_definido_por: 'usuario'` por quem chama; o
 * agente passa a recusar qualquer tentativa de mudar essa etapa.
 */
const MenuExecutor: React.FC<MenuExecutorProps> = ({ etapa, textoEtapa, onEscolher, isDark = false }) => {
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLSpanElement>(null);
  const atual = executorDaEtapa(etapa);

  useEffect(() => {
    if (!aberto) return;
    const fora = (ev: MouseEvent) => {
      if (raiz.current && !raiz.current.contains(ev.target as Node)) setAberto(false);
    };
    const tecla = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setAberto(false);
    };
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', tecla);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', tecla);
    };
  }, [aberto]);

  const rotulo = `Quem executa: ${textoEtapa}`;
  return (
    <span ref={raiz} className="relative flex-none">
      <button
        type="button"
        aria-label={rotulo}
        title="Quem executa esta etapa"
        aria-haspopup="menu"
        aria-expanded={aberto}
        onClick={() => setAberto(v => !v)}
        className={`w-11 h-11 -my-2 inline-flex items-center justify-center rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#7e22ce] ${
          isDark ? 'text-slate-400 hover:bg-[#1e293b]' : 'text-[#7e7386] hover:bg-[#f0f3ff]'
        }`}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="5" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="12" cy="19" r="1" />
        </svg>
      </button>
      {aberto && (
        <div
          role="menu"
          aria-label="Quem executa a etapa"
          className={`absolute right-0 top-full z-20 mt-1 min-w-[220px] rounded-xl border p-1 shadow-lg ${
            isDark ? 'bg-[#151c27] border-[#2a313d]' : 'bg-white border-[#e6e3ee]'
          }`}
        >
          {OPCOES.map(opcao => (
            <button
              key={opcao}
              type="button"
              role="menuitemradio"
              aria-checked={atual === opcao}
              onClick={() => {
                setAberto(false);
                if (opcao !== atual) onEscolher(opcao);
              }}
              className={`w-full min-h-[44px] flex items-center gap-2 px-3 rounded-lg text-left text-[12.5px] font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#7e22ce] ${
                isDark ? 'text-slate-200 hover:bg-[#1e293b]' : 'text-[#151c27] hover:bg-[#f3effc]'
              }`}
            >
              <span className="w-4 flex-none text-[#7e22ce]" aria-hidden="true">
                {atual === opcao && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
                )}
              </span>
              {ROTULO_EXECUTOR[opcao]}
            </button>
          ))}
        </div>
      )}
    </span>
  );
};

export default MenuExecutor;
