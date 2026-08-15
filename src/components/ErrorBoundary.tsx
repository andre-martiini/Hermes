import React from 'react';

interface ErrorBoundaryState {
    error: Error | null;
}

// Qualquer excecao de render que escape daqui hoje resulta em tela branca —
// pega o erro e oferece um caminho de saida em vez de nada.
export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, ErrorBoundaryState> {
    state: ErrorBoundaryState = { error: null };

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { error };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error('[ErrorBoundary] Falha ao renderizar:', error, info.componentStack);
    }

    render() {
        if (this.state.error) {
            return (
                <div style={{
                    minHeight: '100vh',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '16px',
                    padding: '24px',
                    textAlign: 'center',
                    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
                    background: '#f9fafb',
                    color: '#151c27',
                }}>
                    <h1 style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>Falha ao carregar este módulo</h1>
                    <p style={{ fontSize: '14px', color: '#4d4354', maxWidth: '420px', margin: 0 }}>
                        Algo deu errado ao exibir esta tela. Recarregar costuma resolver — especialmente logo após uma atualização do app.
                    </p>
                    <button
                        type="button"
                        onClick={() => window.location.reload()}
                        style={{
                            padding: '10px 20px',
                            borderRadius: '10px',
                            background: '#9333ea',
                            color: '#ffffff',
                            fontWeight: 700,
                            fontSize: '14px',
                            border: 'none',
                            cursor: 'pointer',
                        }}
                    >
                        Recarregar
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}
