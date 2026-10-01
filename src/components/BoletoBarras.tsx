import React from 'react';

import { AnaliseBoleto, descreverBoleto, larguraItf } from '../utils/boleto';

const MARGEM_MODULOS = 10;
const PIXELS_POR_MODULO = 2;

/** Código de barras do boleto em Intercalado 2 de 5, para ler com a câmera do app do banco. */
export const CodigoDeBarrasItf: React.FC<{ codigo: string }> = ({ codigo }) => {
    const larguras = larguraItf(codigo);
    const total = larguras.reduce((a, b) => a + b, 0) + 2 * MARGEM_MODULOS;
    const barras: Array<{ x: number; w: number }> = [];
    let x = MARGEM_MODULOS;
    larguras.forEach((w, i) => {
        if (i % 2 === 0) barras.push({ x, w });
        x += w;
    });
    return (
        <svg
            data-testid="boleto-codigo-de-barras"
            role="img"
            aria-label={`Código de barras ${codigo}`}
            viewBox={`0 0 ${total} 60`}
            preserveAspectRatio="none"
            shapeRendering="crispEdges"
            style={{ width: '100%', maxWidth: total * PIXELS_POR_MODULO, height: 72, background: '#fff' }}
        >
            {barras.map((b) => (
                <rect key={b.x} x={b.x} y={0} width={b.w} height={60} fill="#000" />
            ))}
        </svg>
    );
};

/**
 * Resumo do que foi colado no campo de código de barras: aviso quando os
 * dígitos não conferem; tipo, valor e vencimento quando conferem; e as barras
 * só no desktop (no celular não dá para escanear a própria tela, e o botão
 * Copiar já resolve).
 */
export const BoletoBarras: React.FC<{ analise: AnaliseBoleto | null }> = ({ analise }) => {
    if (!analise) return null;
    if (!analise.valido) {
        return (
            <p data-testid="boleto-aviso" className="mt-2 text-[10px] font-sans font-semibold text-amber-600 dark:text-amber-400">
                ⚠️ {analise.erro}
            </p>
        );
    }
    return (
        <div className="mt-3 space-y-2">
            <p data-testid="boleto-resumo" className="text-[10px] font-sans font-semibold text-emerald-700 dark:text-emerald-400">
                ✓ {descreverBoleto(analise)}
            </p>
            {analise.codigoBarras && (
                <div className="hidden md:block rounded-lg bg-white p-3 border border-slate-200 dark:border-white/10">
                    <CodigoDeBarrasItf codigo={analise.codigoBarras} />
                </div>
            )}
        </div>
    );
};

export default BoletoBarras;
