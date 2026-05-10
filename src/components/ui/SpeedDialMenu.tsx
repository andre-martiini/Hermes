import React, { useState, useEffect, useRef } from 'react';
import { HermesNotification } from '../../../types';
import { NotificationCenter } from './UIComponents';

interface SpeedDialMenuProps {
  notifications: HermesNotification[];
  isSyncing: boolean;
  isNotificationCenterOpen: boolean;
  onOpenNotes: () => void;
  onOpenLog: () => void;
  onOpenCopiloto: () => void;
  onOpenShopping: () => void;
  onOpenTranscription: () => void;
  onOpenWhatsAppTranscription?: () => void;
  onOpenMeetingTranscription: () => void;
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
  notifications, isSyncing, isNotificationCenterOpen,
  onOpenNotes, onOpenLog, onOpenCopiloto, onOpenShopping, onOpenTranscription, onOpenWhatsAppTranscription, onOpenMeetingTranscription, onToggleNotifications,
  onSync, onOpenSettings, onCloseNotifications,
  onMarkAsRead, onDismiss, onUpdateOverdue, onNavigate,
  onCreateAction,
  direction = 'down',
  triggerClassName,
  triggerIconClassName,
  triggerLabel,
  isDark = false
}: SpeedDialMenuProps) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const actions = [
    {
      label: 'Copiloto Hermes',
      color: 'text-indigo-600',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenCopiloto(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      ),
    },
    {
      label: 'Criar Ação',
      color: 'text-blue-600',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onCreateAction(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" />
        </svg>
      ),
    },
    {
      label: 'Reunião IA',
      color: 'text-sky-600',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenMeetingTranscription(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
        </svg>
      ),
    },
    {
      label: 'Transcrição IA',
      color: 'text-indigo-600',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenTranscription(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 18a6 6 0 006-6V8a6 6 0 10-12 0v4a6 6 0 006 6zm0 0v3m-4 0h8" />
        </svg>
      ),
    },
    {
      label: 'Log de Sistema',
      color: 'text-violet-600',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenLog(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
      ),
    },
    {
      label: 'Compras IA',
      color: 'text-emerald-600',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenShopping(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      ),
    },
    {
      label: 'Transcrição WPP',
      color: 'text-green-600',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); (onOpenWhatsAppTranscription ?? onOpenTranscription)(); },
      icon: (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M19.05 4.91A9.82 9.82 0 0012.03 2C6.59 2 2.16 6.43 2.16 11.88c0 1.74.46 3.45 1.32 4.95L2 22l5.31-1.39a9.8 9.8 0 004.72 1.2h.01c5.44 0 9.87-4.43 9.87-9.88a9.8 9.8 0 00-2.86-7.02zm-7.02 15.23h-.01a8.13 8.13 0 01-4.14-1.14l-.3-.18-3.15.83.84-3.07-.2-.32a8.17 8.17 0 01-1.26-4.38c0-4.5 3.67-8.17 8.18-8.17 2.18 0 4.23.85 5.77 2.39a8.1 8.1 0 012.39 5.78c0 4.5-3.67 8.16-8.17 8.16zm4.48-6.11c-.24-.12-1.43-.7-1.65-.78-.22-.08-.38-.12-.54.12-.16.24-.62.78-.76.94-.14.16-.28.18-.52.06-.24-.12-1.01-.37-1.93-1.18-.71-.63-1.19-1.41-1.33-1.65-.14-.24-.02-.37.1-.49.11-.11.24-.28.36-.42.12-.14.16-.24.24-.4.08-.16.04-.3-.02-.42-.06-.12-.54-1.3-.74-1.78-.2-.47-.4-.4-.54-.4h-.46c-.16 0-.42.06-.64.3-.22.24-.84.82-.84 2 0 1.18.86 2.32.98 2.48.12.16 1.69 2.58 4.1 3.62.57.25 1.02.4 1.37.51.58.18 1.1.16 1.51.1.46-.07 1.43-.58 1.63-1.14.2-.56.2-1.04.14-1.14-.06-.1-.22-.16-.46-.28z" />
        </svg>
      ),
    },
    {
      label: 'Notificações',
      color: 'text-slate-700',
      badge: notifications.some(n => !n.isRead)
        ? <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-rose-500 border border-white rounded-full" />
        : null as React.ReactNode,
      onClick: () => { setOpen(false); onToggleNotifications(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
      ),
    },
    {
      label: isSyncing ? 'Sincronizando…' : 'Sincronizar',
      color: 'text-slate-700',
      badge: isSyncing
        ? <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-blue-500 border border-white rounded-full animate-ping" />
        : null as React.ReactNode,
      onClick: () => { setOpen(false); onSync(); },
      icon: (
        <svg className={`w-5 h-5 ${isSyncing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ),
    },
    {
      label: 'Configurações',
      color: 'text-slate-700',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenSettings(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      ),
    },
  ];

  const hasUrgentBadge = notifications.some(n => !n.isRead) || isSyncing;

  return (
    <div
      ref={ref}
      className="relative flex flex-col items-center"
    >
      {/* Expanded action buttons — slide down or up from trigger */}
      <div
        className={`absolute ${direction === 'up' ? 'bottom-full mb-2' : 'top-full mt-2'} right-0 flex flex-col items-end gap-2 z-50`}
        style={{ pointerEvents: open ? 'auto' : 'none' }}
      >
        {(direction === 'up' ? [...actions].reverse() : actions).map((action, i) => (
          (() => {
            const actionColor = isDark && action.color === 'text-slate-700' ? 'text-slate-300' : action.color;
            return (
          <div
            key={action.label}
            className="flex items-center gap-2"
            style={{
              transform: open ? 'translateY(0) scale(1)' : `translateY(${direction === 'up' ? '10px' : '-10px'}) scale(0.85)`,
              opacity: open ? 1 : 0,
              transition: `transform 200ms cubic-bezier(0.34,1.56,0.64,1) ${i * 50}ms, opacity 160ms ease ${i * 50}ms`,
            }}
          >
            {/* Tooltip label */}
            <span className="bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-soft-touch whitespace-nowrap shadow-soft-touch select-none pointer-events-none">
              {action.label}
            </span>
            {/* Icon button */}
            <button
              onClick={action.onClick}
              aria-label={action.label}
              className={`relative border ${isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-800' : 'bg-white border-border-grid'} ${actionColor} p-2.5 rounded-soft-touch shadow-soft-touch hover:shadow-xl hover:scale-110 active:scale-95 transition-all`}
            >
              {action.icon}
              {action.badge}
            </button>
          </div>
            );
          })()
        ))}
      </div>


      {/* Trigger button */}
      <button
        onClick={() => setOpen(prev => !prev)}
        aria-label={triggerLabel || "Ações Rápidas"}
        aria-expanded={open}
        className={`relative transition-all duration-200 active:scale-95 flex items-center justify-center gap-2 ${open ? 'bg-slate-900 border border-slate-900 text-white shadow-lg' : isDark ? 'bg-slate-900 border border-slate-800 text-slate-300 hover:bg-slate-800 hover:text-white' : 'bg-white border border-border-grid text-slate-700 hover:bg-slate-50 hover:border-slate-300'} ${triggerClassName || ''}`}
      >
        <svg className={triggerIconClassName || 'w-5 h-5'} viewBox="0 0 24 24" fill="currentColor">
          <circle cx="5" cy="5" r="1.8" />
          <circle cx="12" cy="5" r="1.8" />
          <circle cx="19" cy="5" r="1.8" />
          <circle cx="5" cy="12" r="1.8" />
          <circle cx="12" cy="12" r="1.8" />
          <circle cx="19" cy="12" r="1.8" />
          <circle cx="5" cy="19" r="1.8" />
          <circle cx="12" cy="19" r="1.8" />
          <circle cx="19" cy="19" r="1.8" />
        </svg>
        
        {triggerLabel && (
          <span className="font-mono font-black uppercase tracking-[0.16em] text-[8px] whitespace-nowrap">
            {triggerLabel}
          </span>
        )}

        {/* Urgent badge on trigger */}
        {hasUrgentBadge && !open && (
          <span className={`absolute ${triggerLabel ? '-top-1 -right-1' : 'top-1.5 right-1.5'} w-2 h-2 bg-rose-500 border border-white rounded-full`} />
        )}
      </button>

      {/* NotificationCenter panel (mounted always, visibility managed internally) */}
      <NotificationCenter
        notifications={notifications}
        onMarkAsRead={onMarkAsRead}
        onDismiss={onDismiss}
        isOpen={isNotificationCenterOpen}
        onClose={onCloseNotifications}
        onUpdateOverdue={onUpdateOverdue}
        onNavigate={onNavigate}
        direction={direction}
      />
    </div>
  );
};
