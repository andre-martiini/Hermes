import React from 'react';

interface MobileShortcutsViewProps {
  onOpenCopilotoText?: () => void;
  onOpenCopilotoAudio?: () => void;
  onOpenTranscription: () => void;
  onOpenActions: () => void;
  onOpenShopping: () => void;
  onOpenMeetingTranscription?: () => void;
  onOpenBrainstorming?: () => void;
  onOpenPopManager?: () => void;
  onOpenSipacTracking?: () => void;
  onOpenMonitorPaginas?: () => void;
  onOpenLongTranscription?: () => void;
  onOpenBatchTranscription?: () => void;
  onToggleNotifications?: () => void;
  onSync?: () => void;
  onOpenSettings?: () => void;
  isDark?: boolean;
}

type ShortcutItem = {
  label: string;
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
  onOpenMeetingTranscription,
  onOpenBrainstorming,
  onOpenPopManager,
  onOpenSipacTracking,
  onOpenMonitorPaginas,
  onOpenLongTranscription,
  onOpenBatchTranscription,
  onToggleNotifications,
  onSync,
  onOpenSettings,
  isDark = false,
}) => {
  const shellClass = isDark
    ? 'bg-slate-950 text-slate-100'
    : 'bg-[#f9fafb] text-slate-950';

  const items: ShortcutItem[] = [
    {
      label: 'Criar Ação',
      onClick: onOpenActions,
      colorClass: 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
        </svg>
      ),
    },
    {
      label: 'Brainstorming',
      onClick: onOpenBrainstorming || onOpenCopilotoText || (() => {}),
      colorClass: 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      ),
    },
    {
      label: 'Lista de Compras',
      onClick: onOpenShopping,
      colorClass: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      ),
    },
    {
      label: 'Transcrição de Áudio',
      onClick: onOpenTranscription,
      colorClass: 'bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      ),
    },
    {
      label: 'Reuniões Tempo Real',
      onClick: onOpenMeetingTranscription || onOpenTranscription,
      colorClass: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
        </svg>
      ),
    },
    {
      label: 'Gestor de POPs',
      onClick: onOpenPopManager || (() => {}),
      colorClass: 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      ),
    },
    {
      label: 'Acompanhamento SIPAC',
      onClick: onOpenSipacTracking || (() => {}),
      colorClass: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
    },
    {
      label: 'Monitor de Páginas',
      onClick: onOpenMonitorPaginas || (() => {}),
      colorClass: 'bg-teal-50 text-teal-600 dark:bg-teal-900/20 dark:text-teal-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      label: 'Transcrições Longas',
      onClick: onOpenLongTranscription || (() => {}),
      colorClass: 'bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0-4a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      ),
    },
    {
      label: 'Transcrição em Lote',
      onClick: onOpenBatchTranscription || (() => {}),
      colorClass: 'bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h7" />
        </svg>
      ),
    },

    {
      label: 'Sincronizar',
      onClick: onSync || (() => {}),
      colorClass: 'bg-sky-50 text-sky-600 dark:bg-sky-900/20 dark:text-sky-400',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ),
    },
    {
      label: 'Configurações',
      onClick: onOpenSettings || (() => {}),
      colorClass: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      ),
    },
  ];

  return (
    <div className={`flex flex-col p-4 ${shellClass} font-sans`} style={{ minHeight: 'calc(100svh - 56px)' }}>
      <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-200 dark:border-white/10">
        <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-500">// ATALHOS & FERRAMENTAS</h2>
      </div>

      {/* Grade Mobile: Apenas Ícone e Nome (Rótulo) da Ferramenta */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {items.map((item) => (
          <button
            key={item.label}
            onClick={item.onClick}
            className={`flex flex-col items-center justify-center gap-2.5 p-4 rounded-2xl border text-center transition-all duration-150 active:scale-95 shadow-sm ${
              isDark
                ? 'border-white/10 bg-slate-900 text-slate-100 hover:bg-slate-800'
                : 'border-[#e5e7eb] bg-white text-slate-950 hover:bg-slate-50'
            }`}
          >
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${item.colorClass}`}>
              {item.icon}
            </div>
            <p className="text-[10px] font-bold uppercase tracking-wider leading-tight text-center text-slate-800 dark:text-slate-200 truncate w-full">
              {item.label}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
};
