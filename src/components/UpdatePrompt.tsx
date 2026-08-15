import React from 'react';
import { useRegisterSW } from 'virtual:pwa-register/react';

// Unico ponto de registro do service worker no app (index.html nao registra mais nada
// em producao). registerType: 'prompt' no vite.config.ts garante que a nova versao
// so assume o controle quando o usuario clica em "Recarregar" aqui — nunca em silencio
// no meio de um preenchimento de formulario.
export const UpdatePrompt: React.FC = () => {
    const { needRefresh: [needRefresh], updateServiceWorker } = useRegisterSW({
        onRegisteredSW(swUrl, registration) {
            registration?.update();
        },
        onRegisterError(error) {
            console.error('[SW] Falha ao registrar service worker:', error);
        },
    });

    if (!needRefresh) return null;

    return (
        <div
            style={{
                position: 'fixed',
                bottom: '16px',
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 9999,
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '12px 16px',
                borderRadius: '12px',
                background: '#151c27',
                color: '#ffffff',
                boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
                fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
                fontSize: '13px',
                maxWidth: '90vw',
            }}
        >
            <span>Nova versão disponível.</span>
            <button
                type="button"
                onClick={() => updateServiceWorker(true)}
                style={{
                    padding: '6px 14px',
                    borderRadius: '8px',
                    background: '#9333ea',
                    color: '#ffffff',
                    fontWeight: 700,
                    fontSize: '13px',
                    border: 'none',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                }}
            >
                Recarregar
            </button>
        </div>
    );
};
