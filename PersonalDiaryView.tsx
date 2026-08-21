import React, { useEffect, useState } from 'react';
import {
    arrayRemove, arrayUnion, collection, doc, getDocs, limit, onSnapshot,
    orderBy, query, setDoc, startAfter, updateDoc
} from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { db, functions } from './firebase';

interface DiaryManualNote {
    texto: string;
    em: string;
}

interface PersonalDiaryEntry {
    id: string;
    data?: string;
    texto?: string;
    texto_original?: string;
    editado?: boolean;
    sem_material?: boolean;
    notas_manuais?: DiaryManualNote[];
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

// Dia local do usuário (mesma referência que o backend usa: America/Sao_Paulo).
const localTodayStr = (): string => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
};

const PersonalDiaryView: React.FC<PersonalDiaryViewProps> = ({ isDark = false }) => {
    const [entries, setEntries] = useState<PersonalDiaryEntry[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoadingMore, setIsLoadingMore] = useState(false);
    const [hasMore, setHasMore] = useState(true);

    // Anotações do dia (entram na consolidação automática das 21h30)
    const todayStr = localTodayStr();
    const [todayEntry, setTodayEntry] = useState<PersonalDiaryEntry | null>(null);
    const [noteDraft, setNoteDraft] = useState('');
    const [isSavingNote, setIsSavingNote] = useState(false);

    // Edição de uma entrada (manual ou via IA) — no máximo uma aberta por vez
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editDraft, setEditDraft] = useState('');
    const [aiOpenId, setAiOpenId] = useState<string | null>(null);
    const [aiFeedback, setAiFeedback] = useState('');
    const [isBusy, setIsBusy] = useState(false);
    const [actionError, setActionError] = useState<{ id: string; message: string } | null>(null);

    // A primeira página fica com listener ao vivo (o registro de hoje é gerado às 21h30 e
    // pode ser ajustado pelo Telegram ou por aqui); páginas seguintes são carregadas sob demanda.
    useEffect(() => {
        const q = query(collection(db, 'diario_pessoal'), orderBy('data', 'desc'), limit(PAGE_SIZE));
        const unsubscribe = onSnapshot(q, snap => {
            const items = snap.docs.map(d => ({ id: d.id, ...(d.data() as any) })) as PersonalDiaryEntry[];
            setEntries(prev => {
                const olderPages = prev.filter(e => !items.some(i => i.id === e.id) && (e.data || '') < (items[items.length - 1]?.data || ''));
                return [...items, ...olderPages];
            });
            setHasMore(items.length === PAGE_SIZE);
            setIsLoading(false);
        });
        return () => unsubscribe();
    }, []);

    // Doc de hoje observado à parte: antes das 21h30 ele pode nem existir (ou existir
    // só com as anotações manuais), e é nele que o compositor de anotações escreve.
    useEffect(() => {
        const unsubscribe = onSnapshot(doc(db, 'diario_pessoal', todayStr), snap => {
            setTodayEntry(snap.exists() ? ({ id: snap.id, ...(snap.data() as any) } as PersonalDiaryEntry) : null);
        });
        return () => unsubscribe();
    }, [todayStr]);

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

    const addNote = async () => {
        const texto = noteDraft.trim();
        if (!texto || isSavingNote) return;
        setIsSavingNote(true);
        try {
            await setDoc(doc(db, 'diario_pessoal', todayStr), {
                data: todayStr,
                notas_manuais: arrayUnion({ texto, em: new Date().toISOString() }),
            }, { merge: true });
            setNoteDraft('');
        } finally {
            setIsSavingNote(false);
        }
    };

    const removeNote = async (note: DiaryManualNote) => {
        await updateDoc(doc(db, 'diario_pessoal', todayStr), { notas_manuais: arrayRemove(note) });
    };

    const syncEntryText = (id: string, texto: string) => {
        setEntries(prev => prev.map(e => (e.id === id ? { ...e, texto, editado: true } : e)));
    };

    const startEdit = (entry: PersonalDiaryEntry) => {
        setActionError(null);
        setAiOpenId(null);
        setEditingId(entry.id);
        setEditDraft(entry.texto || '');
    };

    const saveEdit = async (entry: PersonalDiaryEntry) => {
        const texto = editDraft.trim();
        if (!texto || isBusy) return;
        setIsBusy(true);
        setActionError(null);
        try {
            await updateDoc(doc(db, 'diario_pessoal', entry.id), {
                texto,
                texto_original: entry.texto_original || entry.texto || '',
                editado: true,
                editado_manualmente: true,
                atualizado_em: new Date().toISOString(),
            });
            syncEntryText(entry.id, texto);
            setEditingId(null);
        } catch (err: any) {
            setActionError({ id: entry.id, message: err?.message || 'Não consegui salvar a edição.' });
        } finally {
            setIsBusy(false);
        }
    };

    const startAiAdjust = (entry: PersonalDiaryEntry) => {
        setActionError(null);
        setEditingId(null);
        setAiOpenId(entry.id);
        setAiFeedback('');
    };

    const submitAiAdjust = async (entry: PersonalDiaryEntry) => {
        const feedback = aiFeedback.trim();
        if (!feedback || isBusy) return;
        setIsBusy(true);
        setActionError(null);
        try {
            const fn = httpsCallable(functions, 'ajustarDiarioPessoal');
            const res: any = await fn({ date: entry.id, feedback });
            const novoTexto = res?.data?.texto;
            if (novoTexto) syncEntryText(entry.id, novoTexto);
            setAiOpenId(null);
        } catch (err: any) {
            setActionError({ id: entry.id, message: err?.message || 'Não consegui aplicar o ajuste.' });
        } finally {
            setIsBusy(false);
        }
    };

    const withText = entries.filter(e => !!e.texto);
    const todayNotes = todayEntry?.notas_manuais || [];
    const todayAlreadyGenerated = !!todayEntry?.texto;

    const actionBtnClass = `rounded-md border px-2.5 py-1 text-[10px] font-black uppercase tracking-wider transition disabled:cursor-not-allowed disabled:opacity-50 ${
        isDark ? 'border-white/10 text-white/60 hover:bg-white/10' : 'border-slate-200 text-slate-500 hover:bg-slate-50'
    }`;
    const primaryBtnClass = `rounded-md px-2.5 py-1 text-[10px] font-black uppercase tracking-wider transition disabled:cursor-not-allowed disabled:opacity-50 bg-indigo-500 text-white hover:bg-indigo-600`;
    const textareaClass = `w-full rounded-lg border p-3 text-sm leading-relaxed outline-none focus:ring-2 focus:ring-indigo-400 ${
        isDark ? 'border-white/10 bg-white/5 text-white/90 placeholder:text-white/30' : 'border-slate-200 bg-white text-slate-700 placeholder:text-slate-400'
    }`;

    let lastMonthKey = '';

    return (
        <div className={`p-8 space-y-6 ${isDark ? 'bg-[#0f1724]' : ''}`}>
            <div>
                <h3 className={`text-xl font-black ${isDark ? 'text-white' : 'text-slate-800'}`}>Diário Pessoal</h3>
                <p className={`text-xs font-medium mt-1 font-sans ${isDark ? 'text-slate-400' : 'text-slate-550'}`}>
                    Registro diário gerado automaticamente às 21h30 a partir da sua atividade no Hermes. Você pode editar as entradas aqui (à mão ou pedindo um ajuste à IA) ou pelo Telegram ("✍️ Ajustar").
                </p>
            </div>

            {!todayAlreadyGenerated && (
                <div className={`max-w-3xl rounded-2xl border p-5 ${isDark ? 'border-indigo-400/20 bg-indigo-500/10' : 'border-indigo-100 bg-indigo-50/60'}`}>
                    <p className={`text-sm font-bold ${isDark ? 'text-white' : 'text-slate-800'}`}>Anotações para o diário de hoje</p>
                    <p className={`mt-0.5 text-xs ${isDark ? 'text-white/50' : 'text-slate-500'}`}>
                        Pontos que você quer que entrem na consolidação de hoje às 21h30 — coisas que o Hermes não registrou sozinho.
                    </p>

                    {todayNotes.length > 0 && (
                        <ul className="mt-3 space-y-2">
                            {todayNotes.map((note, i) => (
                                <li key={`${note.em}-${i}`} className={`flex items-start justify-between gap-3 rounded-lg border px-3 py-2 ${isDark ? 'border-white/10 bg-white/5' : 'border-slate-100 bg-white'}`}>
                                    <span className={`text-sm leading-relaxed whitespace-pre-line ${isDark ? 'text-white/80' : 'text-slate-700'}`}>{note.texto}</span>
                                    <button
                                        type="button"
                                        onClick={() => removeNote(note)}
                                        title="Remover anotação"
                                        className={`shrink-0 text-xs font-bold transition ${isDark ? 'text-white/30 hover:text-red-400' : 'text-slate-300 hover:text-red-500'}`}
                                    >
                                        ✕
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}

                    <div className="mt-3 flex flex-col gap-2">
                        <textarea
                            value={noteDraft}
                            onChange={e => setNoteDraft(e.target.value)}
                            rows={2}
                            placeholder="Ex.: Hoje percebi que uma caminhada lenta ajuda a reduzir a dor nas costas."
                            className={textareaClass}
                        />
                        <button
                            type="button"
                            onClick={addNote}
                            disabled={isSavingNote || !noteDraft.trim()}
                            className={`self-start ${primaryBtnClass}`}
                        >
                            {isSavingNote ? 'Salvando...' : 'Adicionar anotação'}
                        </button>
                    </div>
                </div>
            )}

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
                        const isEditing = editingId === entry.id;
                        const isAiOpen = aiOpenId === entry.id;
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
                                        <div className="flex items-center gap-1.5">
                                            {entry.editado && (
                                                <span className="shrink-0 text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-500">
                                                    Ajustado
                                                </span>
                                            )}
                                            {!isEditing && !isAiOpen && (
                                                <>
                                                    <button type="button" onClick={() => startEdit(entry)} className={actionBtnClass}>Editar</button>
                                                    <button type="button" onClick={() => startAiAdjust(entry)} className={actionBtnClass}>Ajustar com IA</button>
                                                </>
                                            )}
                                        </div>
                                    </div>

                                    {isEditing ? (
                                        <div className="mt-3 flex flex-col gap-2">
                                            <textarea
                                                value={editDraft}
                                                onChange={e => setEditDraft(e.target.value)}
                                                rows={Math.min(18, Math.max(6, editDraft.split('\n').length + 2))}
                                                className={textareaClass}
                                            />
                                            <div className="flex items-center gap-2">
                                                <button type="button" onClick={() => saveEdit(entry)} disabled={isBusy || !editDraft.trim()} className={primaryBtnClass}>
                                                    {isBusy ? 'Salvando...' : 'Salvar'}
                                                </button>
                                                <button type="button" onClick={() => setEditingId(null)} disabled={isBusy} className={actionBtnClass}>Cancelar</button>
                                            </div>
                                        </div>
                                    ) : (
                                        <p className={`mt-2 text-sm leading-relaxed whitespace-pre-line ${isDark ? 'text-white/80' : 'text-slate-700'}`}>
                                            {entry.texto}
                                        </p>
                                    )}

                                    {isAiOpen && (
                                        <div className="mt-3 flex flex-col gap-2">
                                            <textarea
                                                value={aiFeedback}
                                                onChange={e => setAiFeedback(e.target.value)}
                                                rows={2}
                                                placeholder='O que ajustar? Ex.: "O dia não foi cansativo, foi produtivo — reescreva com esse tom."'
                                                className={textareaClass}
                                            />
                                            <div className="flex items-center gap-2">
                                                <button type="button" onClick={() => submitAiAdjust(entry)} disabled={isBusy || !aiFeedback.trim()} className={primaryBtnClass}>
                                                    {isBusy ? 'Reescrevendo...' : 'Aplicar ajuste'}
                                                </button>
                                                <button type="button" onClick={() => setAiOpenId(null)} disabled={isBusy} className={actionBtnClass}>Cancelar</button>
                                            </div>
                                        </div>
                                    )}

                                    {actionError?.id === entry.id && (
                                        <p className="mt-2 text-xs font-bold text-red-500">{actionError.message}</p>
                                    )}
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
