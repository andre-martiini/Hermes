import React from 'react';

export interface DiaDeCaminhada {
    rotulo: string;
    km: number | null;
    hoje: boolean;
}

interface CaminhadaCardProps {
    km: number;
    minimoKm: number;
    idealKm: number;
    /** Dia de crise: o piso mínimo não se aplica. */
    crise: boolean;
    ontemKm: number | null;
    ontemBlocos: number;
    pesoKg: number | null;
    alvoKg: number;
    dias: DiaDeCaminhada[];
    onRegistrar: () => void;
    isDark?: boolean;
}

const fmt = (n: number) => n.toFixed(1).replace('.', ',');

/** Caminhada de hoje: o total, o registro rápido, o mínimo e a faixa normal, e os últimos 7 dias. */
const CaminhadaCard: React.FC<CaminhadaCardProps> = ({
    km, minimoKm, idealKm, crise, ontemKm, ontemBlocos, pesoKg, alvoKg, dias, onRegistrar, isDark = false,
}) => {
    const suave = isDark ? 'text-slate-400' : 'text-[#5f586a]';
    const teto = Math.max(idealKm, minimoKm, km, 1);
    const maiorDia = Math.max(idealKm, ...dias.map(d => d.km || 0), 1);
    return (
        <section
            aria-label="Caminhada"
            className={`rounded-[20px] border p-[20px_22px] flex flex-col gap-3.5 ${isDark ? 'bg-[#151c27] border-[#2a313d]' : 'bg-white border-[#ececf1]'}`}
        >
            <div className="flex items-baseline justify-between gap-3">
                <h2 className="m-0 text-base font-extrabold">Caminhada</h2>
                <span className={`text-[12.5px] font-semibold ${suave}`}>hoje</span>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-baseline gap-1.5">
                    <span data-testid="caminhada-km" className="text-[40px] font-extrabold tracking-[-0.02em] leading-none">{fmt(km)}</span>
                    <span className={`text-sm font-bold ${suave}`}>km</span>
                </div>
                <button
                    type="button"
                    onClick={onRegistrar}
                    className="min-h-[48px] px-5 rounded-[14px] bg-[#7e22ce] text-white text-sm font-bold inline-flex items-center gap-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7e22ce]"
                >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
                    Registrar caminhada
                </button>
            </div>

            {crise ? (
                <p className={`m-0 text-[12.5px] leading-normal ${suave}`}>
                    Dia de crise: caminhadas curtas e frequentes, sem meta de distância.
                </p>
            ) : (
                <div className="flex flex-col gap-1.5">
                    <div className={`relative h-2 rounded-full ${isDark ? 'bg-[#2a313d]' : 'bg-[#eeeef3]'}`}>
                        <div className="absolute inset-y-0 left-0 rounded-full bg-[#7e22ce]" style={{ width: `${Math.min((km / teto) * 100, 100)}%` }} />
                        <div className="absolute -top-[3px] w-0.5 h-3.5 bg-[#8c8697]" style={{ left: `${(minimoKm / teto) * 100}%` }} />
                    </div>
                    <div className={`relative h-4 text-[11.5px] font-semibold ${suave}`}>
                        <span className="absolute left-0">0</span>
                        <span className="absolute" style={{ left: `${(minimoKm / teto) * 100}%`, transform: 'translateX(-50%)' }}>mín. {minimoKm} km</span>
                        <span className="absolute right-0">faixa normal até {idealKm} km</span>
                    </div>
                </div>
            )}

            <p className={`m-0 text-[12.5px] leading-normal ${isDark ? 'text-slate-300' : 'text-[#4a4455]'}`}>
                {ontemKm !== null && (
                    <>Ontem <b className="font-bold">{fmt(ontemKm)} km</b>{ontemBlocos > 0 ? ` em ${ontemBlocos} ${ontemBlocos === 1 ? 'caminhada' : 'caminhadas'}` : ''}</>
                )}
                {pesoKg !== null && (
                    <>{ontemKm !== null ? ' · ' : ''}peso <b className="font-bold">{fmt(pesoKg)} kg</b>{alvoKg > 0 ? `, alvo ${fmt(alvoKg).replace(',0', '')}` : ''}</>
                )}
            </p>

            <div className="flex flex-col gap-2">
                <p className={`m-0 text-[11px] font-bold uppercase tracking-[.08em] ${suave}`}>Últimos 7 dias</p>
                <div className="grid grid-cols-7 gap-2 items-end h-[96px]" role="img" aria-label={`Quilômetros por dia: ${dias.map(d => `${d.rotulo} ${d.km === null ? 'sem registro' : fmt(d.km)}`).join(', ')}`}>
                    {dias.map(d => (
                        <div key={d.rotulo} className="flex flex-col items-center justify-end gap-1 h-full">
                            <span className={`text-[11px] font-bold ${isDark ? 'text-slate-300' : 'text-[#4a4455]'}`}>{d.km === null || d.km === 0 ? (d.hoje ? '0' : '–') : fmt(d.km)}</span>
                            <div
                                className="w-full max-w-[34px] rounded-t-md rounded-b-[3px] box-border"
                                style={{
                                    height: d.hoje && !d.km ? 6 : Math.max(4, Math.round(((d.km || 0) / maiorDia) * 64)),
                                    background: d.hoje && !d.km ? 'transparent' : (d.km || 0) >= minimoKm ? '#7e22ce' : (isDark ? '#475569' : '#cfc9dd'),
                                    border: d.hoje && !d.km ? '1.5px dashed #7e22ce' : '0',
                                }}
                            />
                        </div>
                    ))}
                </div>
                <div className="grid grid-cols-7 gap-2" aria-hidden="true">
                    {dias.map(d => (
                        <span key={d.rotulo} className={`text-center text-[11px] font-semibold ${suave}`}>{d.rotulo}</span>
                    ))}
                </div>
            </div>
        </section>
    );
};

export default CaminhadaCard;
