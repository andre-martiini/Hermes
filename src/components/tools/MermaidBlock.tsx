import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { toPng } from 'html-to-image';
import { httpsCallable } from 'firebase/functions';
import { functions } from '@/firebase';

interface MermaidBlockProps {
    code: string;
    isDark?: boolean;
}

type RenderStatus = 'loading' | 'healing' | 'success' | 'error';

const MAX_RETRIES = 3;

export const MermaidBlock: React.FC<MermaidBlockProps> = ({ code, isDark = false }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const [status, setStatus] = useState<RenderStatus>('loading');
    const [svgContent, setSvgContent] = useState('');
    const [attempt, setAttempt] = useState(0);

    useEffect(() => {
        let cancelled = false;

        const renderDiagram = async (mermaidCode: string, currentAttempt: number): Promise<void> => {
            if (cancelled) return;

            mermaid.initialize({
                startOnLoad: false,
                theme: isDark ? 'dark' : 'default',
                securityLevel: 'loose',
            });

            try {
                const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
                const { svg } = await mermaid.render(id, mermaidCode);
                if (cancelled) return;
                setSvgContent(svg);
                setStatus('success');
            } catch (err) {
                if (cancelled) return;
                if (currentAttempt >= MAX_RETRIES) {
                    setStatus('error');
                    return;
                }

                setStatus('healing');
                setAttempt(currentAttempt + 1);

                const errorMsg = err instanceof Error ? err.message : String(err);
                try {
                    const corrigir = httpsCallable<
                        { codigoMermaid: string; erroCompilador: string },
                        { codigoCorrigido: string }
                    >(functions, 'corrigir_sintaxe_mermaid');
                    const result = await corrigir({ codigoMermaid: mermaidCode, erroCompilador: errorMsg });
                    if (cancelled) return;
                    await renderDiagram(result.data.codigoCorrigido, currentAttempt + 1);
                } catch {
                    if (!cancelled) setStatus('error');
                }
            }
        };

        setStatus('loading');
        setAttempt(0);
        renderDiagram(code, 0);

        return () => { cancelled = true; };
    }, [code, isDark]);

    const handleDownloadPng = async () => {
        if (!containerRef.current) return;
        try {
            const dataUrl = await toPng(containerRef.current);
            const link = document.createElement('a');
            link.download = 'diagrama.png';
            link.href = dataUrl;
            link.click();
        } catch (e) {
            console.error('[MermaidBlock] Erro ao exportar PNG:', e);
        }
    };

    const handleCopyImage = async () => {
        if (!containerRef.current) return;
        try {
            const dataUrl = await toPng(containerRef.current);
            const res = await fetch(dataUrl);
            const blob = await res.blob();
            await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
        } catch (e) {
            console.error('[MermaidBlock] Erro ao copiar imagem:', e);
        }
    };

    const skeletonBg = isDark ? 'bg-slate-800' : 'bg-slate-100';
    const skeletonLine = isDark ? 'bg-slate-600' : 'bg-slate-300';
    const skeletonBlock = isDark ? 'bg-slate-700' : 'bg-slate-200';

    if (status === 'loading' || status === 'healing') {
        return (
            <div className={`rounded-xl p-4 my-3 ${skeletonBg}`}>
                <div className="animate-pulse flex flex-col gap-2">
                    <div className={`h-3 rounded w-2/3 ${skeletonLine}`} />
                    <div className={`h-3 rounded w-1/2 ${skeletonLine}`} />
                    <div className={`h-28 rounded mt-2 ${skeletonBlock}`} />
                </div>
                {status === 'healing' && (
                    <p className={`text-[11px] mt-2 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                        Validando e corrigindo diagrama... (tentativa {attempt}/{MAX_RETRIES})
                    </p>
                )}
            </div>
        );
    }

    if (status === 'error') {
        return (
            <div className={`rounded-xl p-3 my-3 border flex items-center gap-2 text-sm ${
                isDark
                    ? 'bg-slate-800 border-red-800 text-red-400'
                    : 'bg-red-50 border-red-200 text-red-600'
            }`}>
                <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                        d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
                Erro: Não foi possível gerar o diagrama validado.
            </div>
        );
    }

    const btnClass = isDark
        ? 'bg-slate-700 hover:bg-slate-600 text-slate-300'
        : 'bg-slate-100 hover:bg-slate-200 text-slate-600';

    return (
        <div className="my-3">
            <div
                ref={containerRef}
                className={`rounded-xl p-4 overflow-x-auto ${
                    isDark ? 'bg-slate-800' : 'bg-white border border-slate-200'
                }`}
                dangerouslySetInnerHTML={{ __html: svgContent }}
            />
            <div className="flex gap-2 mt-2">
                <button
                    onClick={handleCopyImage}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${btnClass}`}
                >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                            d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    Copiar Imagem
                </button>
                <button
                    onClick={handleDownloadPng}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${btnClass}`}
                >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Baixar PNG
                </button>
            </div>
        </div>
    );
};

export default MermaidBlock;
