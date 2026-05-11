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
    : 'bg-slate-100 text-slate-950';

  const panelClass = isDark
    ? 'border-slate-800 bg-slate-950 shadow-inner'
    : 'border-slate-900 bg-slate-50 shadow-inner';

  const bigButtonClass = isDark
    ? 'border-slate-600 bg-slate-900 text-slate-100 shadow-[5px_5px_0px_rgba(51,65,85,0.75)] hover:bg-slate-800 active:translate-x-[3px] active:translate-y-[3px] active:shadow-[2px_2px_0px_rgba(51,65,85,0.75)]'
    : 'border-slate-900 bg-white text-slate-950 shadow-[5px_5px_0px_rgba(15,23,42,1)] hover:bg-slate-100 active:translate-x-[3px] active:translate-y-[3px] active:shadow-[2px_2px_0px_rgba(15,23,42,1)]';

  const smallButtonClass = isDark
    ? 'border-slate-600 bg-slate-900 text-slate-100 shadow-[4px_4px_0px_rgba(51,65,85,0.75)] hover:bg-slate-800 active:translate-x-[2px] active:translate-y-[2px] active:shadow-[2px_2px_0px_rgba(51,65,85,0.75)]'
    : 'border-slate-900 bg-white text-slate-950 shadow-[4px_4px_0px_rgba(15,23,42,1)] hover:bg-slate-100 active:translate-x-[2px] active:translate-y-[2px] active:shadow-[2px_2px_0px_rgba(15,23,42,1)]';

  const iconPlateClass = isDark
    ? 'border-slate-500 bg-slate-950 text-slate-100 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.05)]'
    : 'border-slate-900 bg-slate-100 text-slate-950 shadow-[inset_2px_2px_0px_rgba(203,213,225,0.85)]';

  const subtitleClass = isDark ? 'text-slate-500' : 'text-slate-500';
  const dividerClass = isDark ? 'border-slate-800' : 'border-slate-900';

  const largeItems: ShortcutItem[] = [
    {
      label: 'Transcrição',
      subtitle: 'Processamento de Voz',
      onClick: onOpenTranscription,
      icon: (
        <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 18a6 6 0 006-6V8a6 6 0 10-12 0v4a6 6 0 006 6zm0 0v3m-4 0h8" />
        </svg>
      ),
    },
    {
      label: 'Ações',
      subtitle: 'Gestão Operacional',
      onClick: onOpenActions,
      icon: (
        <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
    },
    {
      label: 'Compras',
      subtitle: 'Logística e Suprimentos',
      onClick: onOpenShopping,
      icon: (
        <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm-8 2a2 2 0 1 1-4 0 2 2 0 0 1 4 0z" />
        </svg>
      ),
    },
  ];

  const smallItems: ShortcutItem[] = [
    {
      label: 'Hermes Texto',
      onClick: onOpenCopilotoText,
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      ),
    },
    {
      label: 'Hermes Áudio',
      onClick: onOpenCopilotoAudio,
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      ),
    },
  ];

  return (
    <div className={`flex flex-col ${shellClass} font-mono`} style={{ height: 'calc(100svh - 56px)' }}>
      <div className={`flex flex-col flex-1 border-t ${panelClass}`}>
        <div className="flex flex-col flex-[3] py-2">
          {largeItems.map((item, index) => (
            <button
              key={item.label}
              onClick={item.onClick}
              className={`mx-4 my-1.5 flex flex-1 items-center gap-5 rounded-none border-2 px-5 text-left transition-all duration-100 group ${bigButtonClass}`}
            >
              <div className={`w-14 h-14 rounded-none flex items-center justify-center border-2 transition-all duration-100 group-active:scale-95 ${iconPlateClass}`}>
                {item.icon}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-black uppercase tracking-widest leading-none">{item.label}</p>
                <p className={`text-[10px] font-bold uppercase tracking-widest mt-2 ${subtitleClass}`}>{item.subtitle}</p>
              </div>
              <div className={`hidden xs:block h-9 w-1 ${index === 1 ? 'opacity-100' : 'opacity-50'} ${isDark ? 'bg-slate-700' : 'bg-slate-900'}`} />
            </button>
          ))}
        </div>

        <div className={`flex flex-1 min-h-0 border-t ${dividerClass} px-3 py-3 gap-3`}>
          {smallItems.map(item => (
            <button
              key={item.label}
              onClick={item.onClick}
              className={`flex-1 flex flex-col items-center justify-center gap-3 rounded-none border-2 px-2 text-center transition-all duration-100 group ${smallButtonClass}`}
            >
              <div className={`w-12 h-12 rounded-none flex items-center justify-center border-2 transition-all duration-100 group-active:scale-95 ${iconPlateClass}`}>
                {item.icon}
              </div>
              <p className="text-[11px] font-black uppercase tracking-widest leading-tight">{item.label}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
