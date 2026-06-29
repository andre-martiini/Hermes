import React from 'react';

interface MobileShortcutsViewProps {
  onOpenCopilotoText: () => void;
  onOpenCopilotoAudio: () => void;
  onOpenTranscription: () => void;
  onOpenActions: () => void;
  onOpenShopping: () => void;
  isDark?: boolean;
}

type ShortcutItem = {
  label: string;
  subtitle?: string;
  onClick: () => void;
  icon: React.ReactNode;
  colorClass: string;
};

export const MobileShortcutsView: React.FC<MobileShortcutsViewProps> = ({
  onOpenCopilotoText,
  onOpenCopilotoAudio,
  onOpenTranscription,
  onOpenActions,
  onOpenShopping,
  isDark = false,
}) => {
  const shellClass = isDark
    ? 'bg-slate-950 text-slate-100'
    : 'bg-[#f9fafb] text-slate-950';

  const panelClass = isDark
    ? 'border-white/10 bg-slate-950'
    : 'border-[#e5e7eb] bg-[#f9fafb]';

  const bigButtonClass = isDark
    ? 'border-white/10 bg-slate-900 text-slate-100 hover:bg-slate-800 active:scale-98 shadow-sm'
    : 'border-[#e5e7eb] bg-white text-slate-950 hover:bg-slate-50 active:scale-98 shadow-sm';

  const smallButtonClass = isDark
    ? 'border-white/10 bg-slate-900 text-slate-100 hover:bg-slate-800 active:scale-98 shadow-sm'
    : 'border-[#e5e7eb] bg-white text-slate-950 hover:bg-slate-50 active:scale-98 shadow-sm';

  const subtitleClass = isDark ? 'text-slate-500' : 'text-slate-400';
  const dividerClass = isDark ? 'border-white/10' : 'border-[#e5e7eb]';

  const largeItems: ShortcutItem[] = [
    {
      label: 'Transcrição',
      subtitle: 'Processamento de Voz',
      onClick: onOpenTranscription,
      colorClass: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 18a6 6 0 006-6V8a6 6 0 10-12 0v4a6 6 0 006 6zm0 0v3m-4 0h8" />
        </svg>
      ),
    },
    {
      label: 'Ações',
      subtitle: 'Gestão Operacional',
      onClick: onOpenActions,
      colorClass: 'bg-purple-50 text-[#7800ce] dark:bg-purple-900/20 dark:text-purple-400',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
    },
    {
      label: 'Compras',
      subtitle: 'Logística e Suprimentos',
      onClick: onOpenShopping,
      colorClass: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm-8 2a2 2 0 1 1-4 0 2 2 0 0 1 4 0z" />
        </svg>
      ),
    },
  ];

  const smallItems: ShortcutItem[] = [
    {
      label: 'Hermes Texto',
      onClick: onOpenCopilotoText,
      colorClass: 'bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      ),
    },
    {
      label: 'Hermes Áudio',
      onClick: onOpenCopilotoAudio,
      colorClass: 'bg-rose-50 text-rose-600 dark:bg-rose-900/20 dark:text-rose-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      ),
    },
  ];

  return (
    <div className={`flex flex-col ${shellClass} font-sans`} style={{ height: 'calc(100svh - 56px)' }}>
      <div className={`flex flex-col flex-1 border-t ${panelClass}`}>
        <div className="flex flex-col flex-[3] py-3 gap-2">
          {largeItems.map((item) => (
            <button
              key={item.label}
              onClick={item.onClick}
              className={`mx-4 my-1 flex flex-1 items-center gap-4 rounded-2xl border px-5 text-left transition-all duration-150 group ${bigButtonClass}`}
            >
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-100 group-active:scale-95 ${item.colorClass}`}>
                {item.icon}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold uppercase tracking-wider leading-none text-slate-800 dark:text-white">{item.label}</p>
                <p className={`text-[10px] font-semibold uppercase tracking-wider mt-1.5 ${subtitleClass}`}>{item.subtitle}</p>
              </div>
            </button>
          ))}
        </div>

        <div className={`flex flex-1 min-h-0 border-t ${dividerClass} px-4 py-4 gap-4`}>
          {smallItems.map((item) => (
            <button
              key={item.label}
              onClick={item.onClick}
              className={`flex-1 flex flex-col items-center justify-center gap-2.5 rounded-2xl border px-2 text-center transition-all duration-150 group ${smallButtonClass}`}
            >
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all duration-100 group-active:scale-95 ${item.colorClass}`}>
                {item.icon}
              </div>
              <p className="text-[11px] font-bold uppercase tracking-wider leading-tight text-slate-700 dark:text-slate-200">{item.label}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
