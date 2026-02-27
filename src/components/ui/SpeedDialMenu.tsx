import React, { useState, useEffect, useRef } from 'react';
import { HermesNotification } from '../../../types';
import { NotificationCenter } from './UIComponents';

interface SpeedDialMenuProps {
  notifications: HermesNotification[];
  isSyncing: boolean;
  isNotificationCenterOpen: boolean;
  onOpenNotes: () => void;
  onOpenLog: () => void;
  onOpenShopping: () => void;
  onOpenTranscription: () => void;
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
}

export const SpeedDialMenu = ({
  notifications, isSyncing, isNotificationCenterOpen,
  onOpenNotes, onOpenLog, onOpenShopping, onOpenTranscription, onToggleNotifications,
  onSync, onOpenSettings, onCloseNotifications,
  onMarkAsRead, onDismiss, onUpdateOverdue, onNavigate,
  onCreateAction,
  direction = 'down'
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
      label: 'Notas Rápidas',
      color: 'text-amber-500',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenNotes(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
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
      label: 'Transcrição IA',
      color: 'text-indigo-600',
      badge: null as React.ReactNode,
      onClick: () => { setOpen(false); onOpenTranscription(); },
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
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
            <span className="bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-lg whitespace-nowrap shadow-lg select-none pointer-events-none">
              {action.label}
            </span>
            {/* Icon button */}
            <button
              onClick={action.onClick}
              aria-label={action.label}
              className={`relative bg-white border border-slate-200 ${action.color} p-2.5 rounded-xl shadow-md hover:shadow-lg hover:scale-110 active:scale-95 transition-all`}
            >
              {action.icon}
              {action.badge}
            </button>
          </div>
        ))}
      </div>


      {/* Trigger button */}
      <button
        onClick={() => setOpen(prev => !prev)}
        aria-label="Ações Rápidas"
        aria-expanded={open}
        className={`relative p-2 rounded-xl shadow-sm transition-all duration-200 active:scale-95 ${open ? 'bg-slate-900 border border-slate-900 text-white shadow-lg scale-105' : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300'}`}
      >
        {/* 3×3 grid dots = "more actions" */}
        <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
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
        {/* Urgent badge on trigger */}
        {hasUrgentBadge && !open && (
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-rose-500 border border-white rounded-full" />
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
