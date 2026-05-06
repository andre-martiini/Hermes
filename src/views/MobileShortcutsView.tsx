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
  const bg = isDark ? 'bg-slate-950' : 'bg-slate-100';

  return (
    <div className={`flex flex-col gap-3 p-4 ${bg}`} style={{ height: 'calc(100svh - 56px)' }}>

      {/* ── Linha principal: Copiloto Texto + Copiloto Áudio ── */}
      <div className="flex gap-3 flex-1 min-h-0">

        {/* Copiloto — Texto */}
        <button
          onClick={onOpenCopilotoText}
          className="flex-1 flex flex-col items-center justify-center gap-5 rounded-3xl bg-indigo-600 text-white shadow-lg active:scale-[0.97] transition-transform"
        >
          <div className="w-16 h-16 bg-white/15 rounded-2xl flex items-center justify-center">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <div className="text-center px-2">
            <p className="text-base font-black uppercase tracking-widest leading-none">Hermes</p>
            <p className="text-indigo-200 text-[11px] font-bold uppercase tracking-widest mt-1.5">Texto</p>
          </div>
        </button>

        {/* Copiloto — Áudio */}
        <button
          onClick={onOpenCopilotoAudio}
          className="flex-1 flex flex-col items-center justify-center gap-5 rounded-3xl bg-violet-600 text-white shadow-lg active:scale-[0.97] transition-transform"
        >
          <div className="w-16 h-16 bg-white/15 rounded-2xl flex items-center justify-center">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
          </div>
          <div className="text-center px-2">
            <p className="text-base font-black uppercase tracking-widest leading-none">Hermes</p>
            <p className="text-violet-200 text-[11px] font-bold uppercase tracking-widest mt-1.5">Áudio</p>
          </div>
        </button>
      </div>

      {/* ── Linha secundária: Transcrição + Ações + Compras ── */}
      <div className="flex gap-3" style={{ flex: '0 0 38%' }}>

        {/* Transcrição IA */}
        <button
          onClick={onOpenTranscription}
          className="flex-1 flex flex-col items-center justify-center gap-3 rounded-3xl bg-sky-500 text-white shadow-lg active:scale-[0.97] transition-transform"
        >
          <div className="w-11 h-11 bg-white/15 rounded-xl flex items-center justify-center">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 18a6 6 0 006-6V8a6 6 0 10-12 0v4a6 6 0 006 6zm0 0v3m-4 0h8" />
            </svg>
          </div>
          <p className="text-[10px] font-black uppercase tracking-widest text-center leading-tight px-1">Transcrição</p>
        </button>

        {/* Ações */}
        <button
          onClick={onOpenActions}
          className="flex-1 flex flex-col items-center justify-center gap-3 rounded-3xl bg-blue-600 text-white shadow-lg active:scale-[0.97] transition-transform"
        >
          <div className="w-11 h-11 bg-white/15 rounded-xl flex items-center justify-center">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <p className="text-[10px] font-black uppercase tracking-widest text-center leading-tight px-1">Ações</p>
        </button>

        {/* Compras */}
        <button
          onClick={onOpenShopping}
          className="flex-1 flex flex-col items-center justify-center gap-3 rounded-3xl bg-emerald-500 text-white shadow-lg active:scale-[0.97] transition-transform"
        >
          <div className="w-11 h-11 bg-white/15 rounded-xl flex items-center justify-center">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
          </div>
          <p className="text-[10px] font-black uppercase tracking-widest text-center leading-tight px-1">Compras</p>
        </button>
      </div>

    </div>
  );
};
