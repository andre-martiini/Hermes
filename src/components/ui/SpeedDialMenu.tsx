import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { HermesNotification } from '../../../types';
import { NotificationCenter } from './UIComponents';

interface SpeedDialMenuProps {
  notifications: HermesNotification[];
  isSyncing: boolean;
  isNotificationCenterOpen: boolean;
  onOpenNotes?: () => void;
  onOpenCopiloto?: () => void;
  onOpenShopping: () => void;
  onOpenTranscription: () => void;
  onOpenWhatsAppTranscription?: () => void;
  onOpenMeetingTranscription: () => void;
  onOpenBrainstorming?: () => void;
  onOpenPopManager?: () => void;
  onOpenSipacTracking?: () => void;
  onOpenMonitorPaginas?: () => void;
  onOpenLongTranscription?: () => void;
  onOpenBatchTranscription?: () => void;
  onToggleNotifications: () => void;
  onSync: () => void;
  onOpenSettings: () => void;
  onCloseNotifications: () => void;
  onMarkAsRead: (id: string) => void;
  onDismiss: (id: string) => void;
  onUpdateOverdue?: (id?: string) => void;
  onNavigate?: (link: string) => void;
  onCreateAction: () => void;
  direction?: 'up' | 'down';
  triggerClassName?: string;
  triggerIconClassName?: string;
  triggerLabel?: string;
  isDark?: boolean;
}

export const SpeedDialMenu = ({
  notifications,
  isSyncing,
  isNotificationCenterOpen,
  onOpenNotes,
  onOpenCopiloto,
  onOpenShopping,
  onOpenTranscription,
  onOpenWhatsAppTranscription,
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
  onCloseNotifications,
  onMarkAsRead,
  onDismiss,
  onUpdateOverdue,
  onNavigate,
  onCreateAction,
  direction = 'down',
  triggerClassName,
  triggerIconClassName,
  triggerLabel,
  isDark = false
}: SpeedDialMenuProps) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const actionBadgeClass = isDark ? 'border-slate-950' : 'border-white';

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        if (isNotificationCenterOpen) onCloseNotifications();
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        if (isNotificationCenterOpen) onCloseNotifications();
      }
    };
    document.addEventListener('click', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('click', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isNotificationCenterOpen, onCloseNotifications]);

  const allActions = [
    {
      code: 'SCT-001',
      label: 'Criar Ação',
      title: 'Criar Ação',
      desc: 'Crie e adicione uma nova ação ou tarefa no sistema.',
      color: 'text-blue-600',
      bgColor: 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onCreateAction(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
        </svg>
      ),
    },
    {
      code: 'ID-001',
      label: 'Brainstorming',
      title: 'Brainstorming',
      desc: 'Capture e organize ideias rápidas com IA.',
      color: 'text-blue-600',
      bgColor: 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); (onOpenBrainstorming || onOpenCopiloto)(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      ),
    },
    {
      code: 'ID-003',
      label: 'Lista de Compras',
      title: 'Lista de Compras',
      desc: 'Organize suas compras com sugestões de IA.',
      color: 'text-emerald-600',
      bgColor: 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenShopping(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      ),
    },
    {
      code: 'ID-004',
      label: 'Transcrição Rápida',
      title: 'Transcrição Rápida',
      desc: 'Transcreva e refine áudios do WhatsApp e outros.',
      color: 'text-rose-600',
      bgColor: 'bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenTranscription(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      ),
    },
    {
      code: 'ID-006',
      label: 'Reuniões em Tempo Real',
      title: 'Reuniões em Tempo Real',
      desc: 'Transcreva com áudio duplo e chat IA.',
      color: 'text-indigo-600',
      bgColor: 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenMeetingTranscription(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
        </svg>
      ),
    },
    {
      code: 'ID-007',
      label: 'Gestor de POPs',
      title: 'Gestor de POPs',
      desc: 'Procedimentos Operacionais Padrão do Hermes.',
      color: 'text-blue-600',
      bgColor: 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenPopManager?.(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      ),
    },
    {
      code: 'ID-008',
      label: 'Acompanhamento SIPAC',
      title: 'Acompanhamento SIPAC',
      desc: 'Consulte processos públicos, andamentos e documentos anexos.',
      color: 'text-emerald-600',
      bgColor: 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenSipacTracking?.(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
    },
    {
      code: 'ID-011',
      label: 'Monitor de Páginas',
      title: 'Monitor de Páginas',
      desc: 'Acompanhe URLs e seja avisado no Telegram quando o objetivo avançar.',
      color: 'text-emerald-600',
      bgColor: 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenMonitorPaginas?.(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      code: 'ID-009',
      label: 'Transcrições Longas',
      title: 'Transcrições Longas',
      desc: 'Envie áudios e vídeos pesados de qualquer tamanho e receba a transcrição.',
      color: 'text-purple-600',
      bgColor: 'bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenLongTranscription?.(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0-4a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      ),
    },
    {
      code: 'ID-010',
      label: 'Transcrição em Lote',
      title: 'Transcrição em Lote',
      desc: 'Sequencie mídias do WhatsApp em um único documento.',
      color: 'text-purple-600',
      bgColor: 'bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); (onOpenBatchTranscription || onOpenWhatsAppTranscription || onOpenTranscription)(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h7" />
        </svg>
      ),
    },

    {
      code: 'SYS-002',
      label: isSyncing ? 'Sincronizando…' : 'Sincronizar',
      title: 'Sincronização Hermes',
      desc: 'Sincronize dados locais e nuvem do Hermes.',
      color: 'text-sky-600',
      bgColor: 'bg-sky-50 dark:bg-sky-900/20 text-sky-600 dark:text-sky-400',
      badge: isSyncing
        ? <span className={`absolute right-2 top-2 h-2.5 w-2.5 border-2 bg-blue-500 rounded-full animate-ping ${actionBadgeClass}`} />
        : null as React.ReactNode,
      onClick: () => { setOpen(false); onSync(); },
      icon: (
        <svg className={`w-6 h-6 sm:w-7 sm:h-7 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ),
    },
    {
      code: 'SYS-003',
      label: 'Configurações',
      title: 'Configurações',
      desc: 'Ajuste preferências do sistema, chaves e integrações.',
      color: 'text-slate-600',
      bgColor: 'bg-slate-100 dark:bg-white/10 text-slate-700 dark:text-slate-200',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenSettings(); },
      icon: (
        <svg className="w-6 h-6 sm:w-7 sm:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      ),
    },
  ];

  const hasUrgentBadge = isSyncing;

  return (
    <div ref={ref} className="relative flex flex-col items-center">
      {/* Portal Modal de Atalhos e Ferramentas */}
      {createPortal(
        <div
          className={`fixed inset-0 z-[999999] flex items-center justify-center bg-slate-950/70 backdrop-blur-md transition-all duration-300 p-4 md:p-6 ${
            open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
          }`}
          onClick={() => setOpen(false)}
        >
          <div
            className={`w-full max-w-5xl rounded-2xl border transition-all duration-300 flex flex-col overflow-hidden max-h-[85vh] ${
              isDark ? 'bg-slate-950 border-slate-800 text-white shadow-2xl' : 'bg-white border-[#e5e7eb] text-slate-900 shadow-2xl'
            } ${open ? 'scale-100 translate-y-0' : 'scale-95 translate-y-4'}`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header da Modal */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-white/10 shrink-0">
              <div>
                <h3 className="text-base md:text-lg font-sans font-bold uppercase tracking-tight text-on-surface">
                  // ATALHOS & FERRAMENTAS DO HERMES
                </h3>
                <p className="text-xs text-slate-500 font-sans mt-0.5">
                  Central unificada de ferramentas de IA e comandos do sistema
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="px-3 py-1.5 rounded-xl text-slate-400 hover:text-on-surface hover:bg-slate-100 dark:hover:bg-white/5 transition-all text-xs font-bold font-mono"
              >
                ✕ FECHAR
              </button>
            </div>

            {/* Conteúdo da Modal (Scrollable) */}
            <div className="p-6 overflow-y-auto custom-scrollbar flex-1">

              {/* VERSÃO DESKTOP: CARDS MAIORES E DETALHADOS COM DESCRIÇÃO */}
              <div className="hidden sm:grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {allActions.map((action, i) => (
                  <button
                    key={action.code}
                    onClick={action.onClick}
                    className={`group relative p-5 rounded-xl border transition-all text-left flex flex-col justify-between gap-3 overflow-hidden ${
                      isDark
                        ? 'bg-slate-900/90 border-slate-800 hover:border-primary-tactile/60 hover:bg-slate-800/80 shadow-md'
                        : 'bg-white border-slate-200 hover:border-primary-tactile/60 hover:bg-slate-50/80 shadow-sm'
                    }`}
                    style={{
                      transform: open ? 'translateY(0) scale(1)' : 'translateY(12px) scale(0.95)',
                      opacity: open ? 1 : 0,
                      transition: `transform 300ms cubic-bezier(0.34,1.56,0.64,1) ${i * 20}ms, opacity 200ms ease ${i * 20}ms`,
                    }}
                  >
                    <div className="absolute top-0 right-0 p-2.5 opacity-20 group-hover:opacity-40 transition-opacity">
                      <span className="text-[9px] font-sans font-bold tracking-widest uppercase font-mono">{action.code}</span>
                    </div>

                    <div className="flex items-center gap-3">
                      <div className={`w-11 h-11 rounded-xl border border-slate-200/50 dark:border-white/5 flex items-center justify-center shrink-0 transition-all group-hover:scale-105 ${action.bgColor}`}>
                        {action.icon}
                        {action.badge}
                      </div>
                      <div className="min-w-0 flex-1">
                        <h4 className="text-sm font-sans font-bold uppercase tracking-tight text-on-surface group-hover:text-primary-tactile transition-colors truncate">
                          {action.title}
                        </h4>
                      </div>
                    </div>

                    <p className="text-[11px] font-medium leading-relaxed text-slate-500 dark:text-slate-400 line-clamp-2">
                      {action.desc}
                    </p>

                    <div className="w-full h-0.5 bg-transparent group-hover:bg-primary-tactile transition-all rounded-full" />
                  </button>
                ))}
              </div>

              {/* VERSÃO MOBILE: QUADRO COMPACTO APENAS COM ÍCONE E NOME */}
              <div className="grid sm:hidden grid-cols-2 gap-3">
                {allActions.map((action) => (
                  <button
                    key={action.code}
                    onClick={action.onClick}
                    className={`flex flex-col items-center justify-center gap-2 p-3.5 rounded-xl border transition-all text-center ${
                      isDark
                        ? 'bg-slate-900 border-slate-800 active:scale-95 text-white'
                        : 'bg-white border-slate-200 active:scale-95 text-slate-900'
                    }`}
                  >
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${action.bgColor}`}>
                      {action.icon}
                      {action.badge}
                    </div>
                    <span className="text-[10px] font-sans font-bold uppercase tracking-wider leading-tight text-center truncate w-full">
                      {action.label}
                    </span>
                  </button>
                ))}
              </div>

            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Trigger Button */}
      <button
        onClick={() => setOpen(prev => !prev)}
        aria-label={triggerLabel || "Ações Rápidas"}
        aria-expanded={open}
        className={`relative transition-all duration-200 active:scale-95 flex items-center justify-center gap-2 rounded-lg p-2.5 ${
          open 
            ? 'bg-slate-900 border border-slate-900 text-white shadow-md' 
            : isDark 
              ? 'bg-slate-900 border border-slate-800 text-slate-300 hover:bg-slate-800 hover:text-white' 
              : 'bg-white border border-[#e5e7eb] text-slate-700 hover:bg-slate-50 hover:border-slate-350 shadow-sm'
        } ${triggerClassName || ''}`}
      >
        <svg className={triggerIconClassName || 'w-5 h-5'} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
        
        {triggerLabel && (
          <span className="font-sans font-bold uppercase tracking-wider text-[9px] whitespace-nowrap">
            {triggerLabel}
          </span>
        )}

        {hasUrgentBadge && !open && (
          <span className={`absolute ${triggerLabel ? '-top-1 -right-1' : 'right-1.5 top-1.5'} h-2 w-2 border border-white bg-rose-500 rounded-full`} />
        )}
      </button>

    </div>
  );
};
