import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { httpsCallable } from 'firebase/functions';
import { functions } from '@/firebase';

interface ReportModalProps {
    isOpen: boolean;
    onClose: () => void;
    reportId: string;
    titulo: string;
    markdown: string;
    onOpenTask?: (id: string) => void;
}

export const ReportModal: React.FC<ReportModalProps> = ({
    isOpen,
    onClose,
    reportId,
    titulo,
    markdown,
    onOpenTask,
}) => {
    const [isSavingDrive, setIsSavingDrive] = useState(false);
    const [driveSaved, setDriveSaved] = useState(false);
    const [driveUrl, setDriveUrl] = useState<string | null>(null);
    const [copyDone, setCopyDone] = useState(false);

    if (!isOpen) return null;

    const handlePrint = () => {
        window.print();
    };

    const handleCopyMarkdown = async () => {
        try {
            await navigator.clipboard.writeText(markdown);
            setCopyDone(true);
            setTimeout(() => setCopyDone(false), 2000);
        } catch {
            const el = document.createElement('textarea');
            el.value = markdown;
            document.body.appendChild(el);
            el.select();
            document.execCommand('copy');
            document.body.removeChild(el);
            setCopyDone(true);
            setTimeout(() => setCopyDone(false), 2000);
        }
    };

    const handleSaveDrive = async () => {
        if (driveSaved && driveUrl) {
            window.open(driveUrl, '_blank');
            return;
        }
        setIsSavingDrive(true);
        try {
            const fn = httpsCallable(functions, 'salvarRelatorioNoDrive');
            const res = await fn({ relatorioId: reportId }) as { data: { driveUrl: string } };
            setDriveUrl(res.data.driveUrl);
            setDriveSaved(true);
            window.open(res.data.driveUrl, '_blank');
        } catch (err: any) {
            console.error('[ReportModal] Erro ao salvar no Drive:', err);
            alert('Erro ao salvar no Google Drive: ' + (err?.message || 'Tente novamente.'));
        } finally {
            setIsSavingDrive(false);
        }
    };

    return createPortal(
        <>
            {/* Print CSS — oculta tudo exceto o relatório */}
            <style>{`
                @media print {
                    body > *:not(#hermes-report-print-root) { display: none !important; }
                    #hermes-report-print-root { display: block !important; position: static !important; }
                    #hermes-report-print-root .no-print { display: none !important; }
                    #hermes-report-print-root .report-body {
                        max-width: 100% !important;
                        padding: 0 !important;
                        font-size: 11pt !important;
                    }
                }
            `}</style>

            {/* Overlay */}
            <div
                id="hermes-report-print-root"
                className="fixed inset-0 z-[9999] flex flex-col bg-white overflow-hidden"
                style={{ fontFamily: 'ui-sans-serif, system-ui, sans-serif' }}
            >
                {/* Header — no-print */}
                <div className="no-print flex items-center justify-between px-6 py-3 border-b border-slate-200 bg-white shadow-sm shrink-0">
                    <div className="flex items-center gap-3 min-w-0">
                        <div className="p-2 bg-blue-50 rounded-lg shrink-0">
                            <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                        </div>
                        <div className="min-w-0">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Relatório</p>
                            <p className="text-sm font-semibold text-slate-800 truncate">{titulo}</p>
                        </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-2 shrink-0">
                        {/* Copy Markdown */}
                        <button
                            onClick={handleCopyMarkdown}
                            title="Copiar Markdown"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 text-[10px] font-black uppercase tracking-widest hover:bg-slate-200 transition-all"
                        >
                            {copyDone ? (
                                <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                            ) : (
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                            )}
                            {copyDone ? 'Copiado!' : 'Copiar MD'}
                        </button>

                        {/* Save to Drive */}
                        <button
                            onClick={handleSaveDrive}
                            disabled={isSavingDrive}
                            title={driveSaved ? 'Abrir no Google Drive' : 'Salvar no Google Drive'}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-black uppercase tracking-widest hover:bg-emerald-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                        >
                            {isSavingDrive ? (
                                <span className="w-3.5 h-3.5 border-2 border-emerald-400/40 border-t-emerald-600 rounded-full animate-spin" />
                            ) : driveSaved ? (
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                            ) : (
                                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M6.94 4.89L2 13.5l4.94 4.94L12 9.83 6.94 4.89zM12 9.83l5.06 8.61H6.94L12 9.83zm5.06 8.61L22 13.5l-4.94-8.61L12 9.83l5.06 8.61z" />
                                </svg>
                            )}
                            {isSavingDrive ? 'Salvando...' : driveSaved ? 'Abrir Drive' : 'Salvar Drive'}
                        </button>

                        {/* Print / PDF */}
                        <button
                            onClick={handlePrint}
                            title="Imprimir / Salvar como PDF"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 text-white text-[10px] font-black uppercase tracking-widest hover:bg-slate-800 transition-all"
                        >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                            </svg>
                            Imprimir / PDF
                        </button>

                        {/* Close */}
                        <button
                            onClick={onClose}
                            title="Fechar"
                            className="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-all"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>

                {/* Report body */}
                <div className="flex-1 overflow-y-auto bg-white">
                    <div
                        className="report-body mx-auto max-w-3xl px-8 py-10"
                        style={{ fontSize: '15px', lineHeight: '1.7', color: '#1e293b' }}
                    >
                        <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            urlTransform={(url) => url}
                            components={{
                                h1: ({ node, ...props }) => (
                                    <h1 className="text-3xl font-black text-slate-900 mb-2 mt-0 pb-3 border-b-2 border-slate-200" {...props} />
                                ),
                                h2: ({ node, ...props }) => (
                                    <h2 className="text-xl font-black text-slate-800 mt-8 mb-3 pb-1 border-b border-slate-100" {...props} />
                                ),
                                h3: ({ node, ...props }) => (
                                    <h3 className="text-base font-bold text-slate-700 mt-5 mb-2" {...props} />
                                ),
                                p: ({ node, ...props }) => (
                                    <p className="mb-4 text-slate-700 leading-relaxed" {...props} />
                                ),
                                ul: ({ node, ...props }) => (
                                    <ul className="list-disc ml-6 mb-4 space-y-1 text-slate-700" {...props} />
                                ),
                                ol: ({ node, ...props }) => (
                                    <ol className="list-decimal ml-6 mb-4 space-y-1 text-slate-700" {...props} />
                                ),
                                li: ({ node, ...props }) => (
                                    <li className="leading-relaxed" {...props} />
                                ),
                                strong: ({ node, ...props }) => (
                                    <strong className="font-bold text-slate-900" {...props} />
                                ),
                                em: ({ node, ...props }) => (
                                    <em className="italic text-slate-600" {...props} />
                                ),
                                hr: ({ node, ...props }) => (
                                    <hr className="border-slate-200 my-6" {...props} />
                                ),
                                table: ({ node, ...props }) => (
                                    <div className="overflow-x-auto mb-6">
                                        <table className="w-full text-sm border-collapse border border-slate-200" {...props} />
                                    </div>
                                ),
                                th: ({ node, ...props }) => (
                                    <th className="bg-slate-50 text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200 text-xs uppercase tracking-wide" {...props} />
                                ),
                                td: ({ node, ...props }) => (
                                    <td className="px-3 py-2 text-slate-700 border border-slate-200" {...props} />
                                ),
                                code: ({ node, inline, ...props }: any) =>
                                    inline ? (
                                        <code className="bg-slate-100 text-slate-800 px-1 py-0.5 rounded text-[13px] font-mono" {...props} />
                                    ) : (
                                        <pre className="bg-slate-50 border border-slate-200 rounded-lg p-4 overflow-x-auto mb-4">
                                            <code className="text-sm font-mono text-slate-800" {...props} />
                                        </pre>
                                    ),
                                blockquote: ({ node, ...props }) => (
                                    <blockquote className="border-l-4 border-blue-300 pl-4 italic text-slate-600 my-4" {...props} />
                                ),
                                a: ({ node, ...props }) => {
                                    const href = props.href || '';
                                    if (href.startsWith('task:')) {
                                        const id = href.split(':')[1];
                                        return (
                                            <button
                                                onClick={() => {
                                                    onOpenTask?.(id);
                                                    onClose();
                                                }}
                                                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors font-bold text-[13px] border border-blue-100 align-baseline"
                                                title="Abrir Ação"
                                            >
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                                                {props.children}
                                            </button>
                                        );
                                    }
                                    return <a className="text-blue-600 underline hover:text-blue-800 break-all" target="_blank" rel="noopener noreferrer" {...props} />;
                                }
                            }}
                        >
                            {markdown}
                        </ReactMarkdown>
                    </div>
                </div>
            </div>
        </>,
        document.body
    );
};
