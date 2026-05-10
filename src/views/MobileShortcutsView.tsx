import React from 'react';

interface MobileShortcutsViewProps {
  onOpenCopilotoText: () => void;
  onOpenCopilotoAudio: () => void;
  onOpenTranscription: () => void;
  onOpenActions: () => void;
  onOpenShopping: () => void;
  isDark?: boolean;
}

export const MobileShortcutsView: React.FC<MobileShortcutsViewProps> = ({
  onOpenCopilotoText,
  onOpenCopilotoAudio,
  onOpenTranscription,
  onOpenActions,
  onOpenShopping,
  isDark = false,
}) => {
  const bg = isDark ? 'bg-slate-950' : 'bg-[#f9f9f9]';
  const gridBorder = isDark ? 'border-slate-800' : 'border-[#dadada]';
  const textDark = isDark ? 'text-slate-300' : 'text-[#333333]';

  return (
    <div className={`flex flex-col ${bg} font-mono`} style={{ height: 'calc(100svh - 56px)' }}>
      
      {/* Container principal com Grid Ortogonal visível - Maximizando Espaço */}
      <div className={`flex flex-col flex-1 border-t ${gridBorder} bg-white shadow-inner`}>
        
        {/* ── SEÇÃO SUPERIOR: Transcrição, Ações, Compras (Empilhados Verticalmente) ── */}
        <div className="flex flex-col flex-[3]">
          
          {/* Transcrição IA */}
          <button
            onClick={onOpenTranscription}
            className={`flex-1 flex items-center gap-6 px-6 border-b ${gridBorder} hover:bg-slate-50 active:bg-slate-100 transition-colors group`}
          >
            <div className="w-14 h-14 bg-slate-100 rounded-xl flex items-center justify-center border border-slate-200 shadow-inner group-active:shadow-none transition-shadow">
              <svg className="w-7 h-7 text-[#333333]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 18a6 6 0 006-6V8a6 6 0 10-12 0v4a6 6 0 006 6zm0 0v3m-4 0h8" />
              </svg>
            </div>
            <div className="text-left">
              <p className={`text-sm font-black uppercase tracking-widest ${textDark} leading-none`}>Transcrição</p>
              <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mt-2">Processamento de Voz</p>
            </div>
          </button>

          {/* Ações */}
          <button
            onClick={onOpenActions}
            className={`flex-1 flex items-center gap-6 px-6 border-b ${gridBorder} hover:bg-slate-50 active:bg-slate-100 transition-colors group`}
          >
            <div className="w-14 h-14 bg-slate-100 rounded-xl flex items-center justify-center border border-slate-200 shadow-inner group-active:shadow-none transition-shadow">
              <svg className="w-7 h-7 text-[#333333]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div className="text-left">
              <p className={`text-sm font-black uppercase tracking-widest ${textDark} leading-none`}>Ações</p>
              <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mt-2">Gestão Operacional</p>
            </div>
          </button>

          {/* Compras */}
          <button
            onClick={onOpenShopping}
            className={`flex-1 flex items-center gap-6 px-6 border-b ${gridBorder} hover:bg-slate-50 active:bg-slate-100 transition-colors group`}
          >
            <div className="w-14 h-14 bg-slate-100 rounded-xl flex items-center justify-center border border-slate-200 shadow-inner group-active:shadow-none transition-shadow">
              <svg className="w-7 h-7 text-[#333333]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </div>
            <div className="text-left">
              <p className={`text-sm font-black uppercase tracking-widest ${textDark} leading-none`}>Compras</p>
              <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mt-2">Logística e Suprimentos</p>
            </div>
          </button>
        </div>

        {/* ── SEÇÃO INFERIOR: Hermes Texto + Hermes Áudio (Lado a Lado) ── */}
        <div className="flex flex-1 min-h-0 bg-slate-50/50">
          
          {/* Copiloto — Texto */}
          <button
            onClick={onOpenCopilotoText}
            className={`flex-1 flex flex-col items-center justify-center gap-3 border-r ${gridBorder} hover:bg-slate-100 active:bg-slate-200 transition-colors group`}
          >
            <div className="w-12 h-12 bg-white rounded-xl flex items-center justify-center border border-slate-200 shadow-sm group-active:shadow-none transition-shadow">
              <svg className="w-6 h-6 text-[#333333]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <div className="text-center px-2">
              <p className={`text-[11px] font-black uppercase tracking-widest ${textDark} leading-none`}>Hermes Texto</p>
            </div>
          </button>

          {/* Copiloto — Áudio */}
          <button
            onClick={onOpenCopilotoAudio}
            className={`flex-1 flex flex-col items-center justify-center gap-3 hover:bg-slate-100 active:bg-slate-200 transition-colors group`}
          >
            <div className="w-12 h-12 bg-white rounded-xl flex items-center justify-center border border-slate-200 shadow-sm group-active:shadow-none transition-shadow">
              <svg className="w-6 h-6 text-[#333333]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <div className="text-center px-2">
              <p className={`text-[11px] font-black uppercase tracking-widest ${textDark} leading-none`}>Hermes Áudio</p>
            </div>
          </button>
        </div>

      </div>
    </div>
  );
};
