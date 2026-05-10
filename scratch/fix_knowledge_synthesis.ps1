$path = "KnowledgeView.tsx"
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)

$oldSynthesis = '(?s)const SynthesisBlock: React.FC<{.*?text: string;.*?onCitationClick: \(index: number\) => void;.*?}> = \(\{ text, onCitationClick \}\) => \{.*?(?=// ─── Card de resultado ───────────────────────────────────────────────────────)'

$newSynthesis = @'
const SynthesisBlock: React.FC<{
    text: string;
    onCitationClick: (index: number) => void;
}> = ({ text, onCitationClick }) => {
    // Divide o texto em segmentos preservando os marcadores [N]
    const parts = useMemo(() => {
        const segments: Array<{ type: 'text' | 'cite'; value: string; n?: number }> = [];
        const re = /\[(\d+)\]/g;
        let lastIndex = 0;
        let match: RegExpExecArray | null;
        while ((match = re.exec(text)) !== null) {
            if (match.index > lastIndex) {
                segments.push({ type: 'text', value: text.slice(lastIndex, match.index) });
            }
            segments.push({ type: 'cite', value: match[0], n: Number(match[1]) });
            lastIndex = re.lastIndex;
        }
        if (lastIndex < text.length) {
            segments.push({ type: 'text', value: text.slice(lastIndex) });
        }
        return segments;
    }, [text]);

    return (
        <div className="bg-slate-900 text-white rounded-none border-4 border-slate-900 p-6 md:p-8 relative overflow-hidden font-mono shadow-[8px_8px_0px_rgba(16,185,129,0.5)]">
            {/* Elemento Decorativo Industrial */}
            <div className="absolute inset-0 opacity-10 pointer-events-none" style={{ backgroundImage: 'radial-gradient(#fff 1px, transparent 1px)', backgroundSize: '15px 15px' }}></div>
            
            <div className="flex items-center gap-4 mb-6 relative z-10 border-b-2 border-slate-700 pb-4">
                <div className="w-2 h-8 bg-emerald-500 animate-pulse" />
                <div>
                    <span className="text-[10px] font-black uppercase tracking-[0.3em] text-emerald-400 block mb-1">
                        AI_SYNTHESIS
                    </span>
                    <span className="text-[8px] text-slate-400 tracking-widest">GEMINI_ENGINE // KNOWLEDGE_GRAPH</span>
                </div>
            </div>
            <p className="text-sm md:text-base leading-relaxed tracking-tight text-slate-100 whitespace-pre-wrap relative z-10">
                {parts.map((p, i) =>
                    p.type === 'text' ? (
                        <span key={i}>{p.value}</span>
                    ) : (
                        <button
                            key={i}
                            onClick={() => p.n !== undefined && onCitationClick(p.n)}
                            className="inline-flex items-center justify-center min-w-[24px] h-[24px] px-2 mx-1 rounded-none border border-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/40 text-emerald-300 hover:text-white text-[10px] font-black transition-all align-middle shadow-[1px_1px_0px_rgba(16,185,129,0.5)]"
                            title={`Abrir fonte ${p.n}`}
                        >
                            [{p.n}]
                        </button>
                    )
                )}
            </p>
        </div>
    );
};

'@

# Because the characters of the line comments might not match perfectly due to encoding, let's just use the function definition and return statement
$oldSynthesisPattern = '(?s)const SynthesisBlock: React\.FC<\{.*?text: string;.*?onCitationClick: \(index: number\) => void;.*?\}> = \(\{ text, onCitationClick \}\) => \{.*?return \(.*?<div className="bg-slate-900 text-white rounded-none border-4 border-slate-900 p-6 md:p-8 relative overflow-hidden font-mono shadow-\[8px_8px_0px_rgba\(16,185,129,0\.5\)\]">.*?</div>.*?(?=\);\s*};\s*//)'

# wait, I already changed the className of SynthesisBlock in the previous script!
# I can just replace the whole return statement of SynthesisBlock.

$oldReturnPattern = '(?s)return \(\s*<div className="bg-slate-900 text-white rounded-none border-4 border-slate-900 p-6 md:p-8 relative overflow-hidden font-mono shadow-\[8px_8px_0px_rgba\(16,185,129,0\.5\)\]">.*?</div>\s*\);'

$newReturn = @'
    return (
        <div className="bg-slate-900 text-white rounded-none border-4 border-slate-900 p-6 md:p-8 relative overflow-hidden font-mono shadow-[8px_8px_0px_rgba(16,185,129,0.5)]">
            {/* Elemento Decorativo Industrial */}
            <div className="absolute inset-0 opacity-10 pointer-events-none" style={{ backgroundImage: 'radial-gradient(#fff 1px, transparent 1px)', backgroundSize: '15px 15px' }}></div>
            
            <div className="flex items-center gap-4 mb-6 relative z-10 border-b-2 border-slate-700 pb-4">
                <div className="w-2 h-8 bg-emerald-500 animate-pulse" />
                <div>
                    <span className="text-[10px] font-black uppercase tracking-[0.3em] text-emerald-400 block mb-1">
                        AI_SYNTHESIS
                    </span>
                    <span className="text-[8px] text-slate-400 tracking-widest">GEMINI_ENGINE // KNOWLEDGE_GRAPH</span>
                </div>
            </div>
            <p className="text-sm md:text-base leading-relaxed tracking-tight text-slate-100 whitespace-pre-wrap relative z-10">
                {parts.map((p, i) =>
                    p.type === 'text' ? (
                        <span key={i}>{p.value}</span>
                    ) : (
                        <button
                            key={i}
                            onClick={() => p.n !== undefined && onCitationClick(p.n)}
                            className="inline-flex items-center justify-center min-w-[24px] h-[24px] px-2 mx-1 rounded-none border border-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/40 text-emerald-300 hover:text-white text-[10px] font-black transition-all align-middle shadow-[2px_2px_0px_rgba(16,185,129,0.5)]"
                            title={`Abrir fonte ${p.n}`}
                        >
                            [{p.n}]
                        </button>
                    )
                )}
            </p>
        </div>
    );
'@

$content = [regex]::Replace($content, $oldReturnPattern, $newReturn)

[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
