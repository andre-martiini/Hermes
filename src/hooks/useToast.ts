import { useState } from 'react';
import { Toast } from '../types';

export const useToast = () => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'success', action?: { label: string, onClick: () => void }, actions?: { label: string | React.ReactNode, onClick: () => void }[]) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => {
      if (prev.some(t => t.message === message)) return prev;

      if (prev.length > 0) {
        const last = prev[prev.length - 1];
        const lastPrefix = last.message.split(' ')[0];
        const newPrefix = message.split(' ')[0];
        if (lastPrefix === newPrefix && last.type === type && message.length > 10) {
           return [...prev.slice(0, -1), { id, message, type, action, actions }];
        }
      }

      const base = prev.length >= 2 ? prev.slice(1) : prev;
      return [...base, { id, message, type, action, actions }];
    });

    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  };

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  return { toasts, showToast, removeToast };
};
