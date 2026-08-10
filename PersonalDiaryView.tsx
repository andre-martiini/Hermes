import React, { useEffect, useState } from 'react';
import { collection, getDocs, limit, onSnapshot, orderBy, query, startAfter } from 'firebase/firestore';
import { db } from './firebase';

interface PersonalDiaryEntry {
    id: string;
    data?: string;
    texto?: string;
    editado?: boolean;
    sem_material?: boolean;
}

interface PersonalDiaryViewProps {
    isDark?: boolean;
}

const PAGE_SIZE = 20;

// "YYYY-MM-DD" -> "Domingo, 9 de agosto de 2026". Constrói a data em horário local
// (não via `new Date(iso)`, que interpreta a string como UTC e pode exibir o dia
// errado em fusos negativos como o do Brasil).
const formatDiaryDate = (dateStr?: string): string => {
    if (!dateStr) return '';
    const [y, m, d] = dateStr.split('-').map(Number);
    if (!y || !m || !d) return dateStr;
    const formatted = new Date(y, m - 1, d).toLocaleDateString('pt-BR', {
        weekday: 'long', day: '2-digit', month: 'long', year: 'numeric'
    });
    return formatted.charAt(0).toUpperCase() + formatted.slice(1);
};

const diaryMonthKey = (dateStr?: string): string => (dateStr || '').slice(0, 7);

const formatMonthLabel = (monthKey: string): string => {
    const [y, m] = monthKey.split('-').map(Number);
    if (!y || !m) return monthKey;
    const formatted = new Date(y, m - 1, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
    return formatted.charAt(0).toUpperCase() + formatted.slice(1);
};

const PersonalDiaryView: React.FC<PersonalDiaryViewProps> = ({ isDark = false }) => {
    const [entries, setEntries] = useState<PersonalDiaryEntry[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoadingMore, setIsLoadingMore] = useState(false);
    const [hasMore, setHasMore] = useState(true);

    // A primeira página fica com listener ao vivo (o registro de hoje é gerado às 21h30 e
    // pode ser ajustado pelo Telegram); páginas seguintes são carregadas sob demanda.
    useEffect(() => {
        const q = query(collection(db, 'diario_pessoal'), orderBy('data', 'desc'), limit(PAGE_SIZE));
        const unsubscribe = onSnapshot(q, snap => {
            const items = snap.docs.map(d => ({ id: d.id, ...(d.data() as any) })) as PersonalDiaryEntry[];
            setEntries(items);
            setHasMore(items.length === PAGE_SIZE);
            setIsLoading(false);
        });
        return () => unsubscribe();
    }, []);

    const loadMore = async () => {
        if (isLoadingMore || entries.length === 0) return;
        setIsLoadingMore(true);
        try {
            const cursor = entries[entries.length - 1].data;
            const q = query(collection(db, 'diario_pessoal'), orderBy('data', 'desc'), startAfter(cursor), limit(PAGE_SIZE));
            const snap = await getDocs(q);
            const items = snap.docs.map(d => ({ id: d.id, ...(d.data() as any) })) as PersonalDiaryEntry[];
            setEntries(prev => [...prev, ...items]);
            setHasMore(items.length === PAGE_SIZE);
        } finally {
            setIsLoadingMore(false);
        }
    };

    const withText = entries.filter(e => !!e.texto);

    let lastMonthKey = '';

    return (
        <div className={`p-8 space-y-6 ${isDark ? 'bg-[#0f1724]' : ''}`}>
            <div>
                <h3 className={`text-xl font-black ${isDark ? 'text-white' : 'text-slate-800'}`}>Diário Pessoal</h3>
                <p className={`text-xs font-medium mt-1 font-sans ${isDark ? 'text-slate-400' : 'text-slate-550'}`}>
                    Registro diário gerado automaticamente às 21h30 a partir da sua atividade no Hermes. Peça um ajuste no Telegram tocando "✍️ Ajustar".
                </p>
            </div>

            {isLoading ? (
                <p className={`text-xs font-mono ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Carregando diário...</p>
            ) : withText.length === 0 ? (
                <div className={`rounded-2xl border p-8 text-center ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-100 bg-slate-50'}`}>
                    <p className={`text-sm font-bold ${isDark ? 'text-white/70' : 'text-slate-600'}`}>Nenhuma entrada no diário ainda.</p>
                    <p className={`mt-1 text-xs ${isDark ? 'text-white/40' : 'text-slate-400'}`}>
                        O primeiro registro aparece aqui depois da geração automática de hoje às 21h30.
                    </p>
                </div>
            ) : (
                <div className="flex flex-col gap-4 max-w-3xl">
                    {withText.map(entry => {
                        const monthKey = diaryMonthKey(entry.data);
                        const showMonthHeader = monthKey !== lastMonthKey;
                        lastMonthKey = monthKey;
                        return (
                            <React.Fragment key={entry.id}>
                                {showMonthHeader && (
                                    <p className={`mt-2 text-[11px] font-black uppercase tracking-[0.2em] ${isDark ? 'text-white/30' : 'text-slate-400'}`}>
                                        {formatMonthLabel(monthKey)}
                                    </p>
                                )}
                                <div className={`rounded-2xl border p-5 ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-100 bg-white shadow-sm'}`}>
                                    <div className="flex items-center justify-between gap-2">
                                        <p className={`text-sm font-bold ${isDark ? 'text-white' : 'text-slate-800'}`}>
                                            {formatDiaryDate(entry.data)}
                                        </p>
                                        {entry.editado && (
                                            <span className="shrink-0 text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-500">
                                                Ajustado
                                            </span>
                                        )}
                                    </div>
                                    <p className={`mt-2 text-sm leading-relaxed whitespace-pre-line ${isDark ? 'text-white/80' : 'text-slate-700'}`}>
                                        {entry.texto}
                                    </p>
                                </div>
                            </React.Fragment>
                        );
                    })}

                    {hasMore && (
                        <button
                            type="button"
                            onClick={loadMore}
                            disabled={isLoadingMore}
                            className={`self-start rounded-lg border px-4 py-2 text-xs font-bold uppercase tracking-wider transition disabled:cursor-not-allowed disabled:opacity-50 ${
                                isDark ? 'border-white/10 text-white/60 hover:bg-white/5' : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                            }`}
                        >
                            {isLoadingMore ? 'Carregando...' : 'Carregar dias anteriores'}
                        </button>
                    )}
                </div>
            )}
        </div>
    );
};

export default PersonalDiaryView;
