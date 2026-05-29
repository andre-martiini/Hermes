import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  collection,
  addDoc,
  updateDoc,
  doc,
  query,
  where,
  orderBy,
  onSnapshot,
  serverTimestamp,
  Timestamp,
} from 'firebase/firestore';
import { ref, uploadBytesResumable } from 'firebase/storage';
import { db, auth, storage } from '@/firebase';

interface LongTranscriptionToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
  isDark?: boolean;
}

type TranscriptionStatus = 'Enviando' | 'Processando' | 'Concluído' | 'Erro';

interface LongTranscription {
  id: string;
  userId: string;
  fileName: string;
  fileSize: number;
  status: TranscriptionStatus;
  storagePath?: string;
  transcriptionRaw?: string | null;
  errorMessage?: string | null;
  createdAt?: Timestamp | null;
  updatedAt?: Timestamp | null;
}

const formatBytes = (bytes: number): string => {
  if (!bytes || bytes <= 0) return '0 MB';
  const mb = bytes / (1024 * 1024);
  if (mb < 1) return `${(bytes / 1024).toFixed(0)} KB`;
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${mb.toFixed(1)} MB`;
};

const formatDate = (ts?: Timestamp | null): string => {
  if (!ts || typeof ts.toDate !== 'function') return '—';
  try {
    return ts.toDate().toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
};

const getExtension = (fileName: string): string => {
  const idx = fileName.lastIndexOf('.');
  return idx >= 0 ? fileName.slice(idx + 1).toLowerCase() : 'bin';
};

const statusStyles = (status: TranscriptionStatus, isDark: boolean): string => {
  switch (status) {
    case 'Concluído':
      return isDark ? 'bg-emerald-900/40 text-emerald-300 border-emerald-700' : 'bg-emerald-50 text-emerald-700 border-emerald-300';
    case 'Processando':
      return isDark ? 'bg-amber-900/40 text-amber-300 border-amber-700' : 'bg-amber-50 text-amber-700 border-amber-300';
    case 'Enviando':
      return isDark ? 'bg-blue-900/40 text-blue-300 border-blue-700' : 'bg-blue-50 text-blue-700 border-blue-300';
    case 'Erro':
      return isDark ? 'bg-red-900/40 text-red-300 border-red-700' : 'bg-red-50 text-red-700 border-red-300';
    default:
      return isDark ? 'bg-slate-800 text-slate-300 border-slate-600' : 'bg-slate-100 text-slate-600 border-slate-300';
  }
};

export const LongTranscriptionTool = ({ onBack, showToast, isDark = false }: LongTranscriptionToolProps) => {
  const [history, setHistory] = useState<LongTranscription[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<LongTranscription | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const uid = auth.currentUser?.uid;
    if (!uid) {
      setLoadingHistory(false);
      return;
    }
    const q = query(
      collection(db, 'long_transcriptions'),
      where('userId', '==', uid),
      orderBy('createdAt', 'desc'),
    );
    const unsub = onSnapshot(
      q,
      (snap) => {
        const items = snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<LongTranscription, 'id'>) }));
        setHistory(items);
        setLoadingHistory(false);
        setSelected((prev) => (prev ? items.find((i) => i.id === prev.id) ?? prev : prev));
      },
      (err) => {
        console.error('[LongTranscription] onSnapshot error:', err);
        setLoadingHistory(false);
        showToast('Falha ao carregar histórico de transcrições.', 'error');
      },
    );
    return () => unsub();
  }, [showToast]);

  const startUpload = useCallback(
    async (file: File) => {
      const uid = auth.currentUser?.uid;
      if (!uid) {
        showToast('Você precisa estar autenticado.', 'error');
        return;
      }
      const isMedia = file.type.startsWith('audio/') || file.type.startsWith('video/');
      if (!isMedia) {
        showToast('Selecione um arquivo de áudio ou vídeo.', 'error');
        return;
      }

      try {
        const docRef = await addDoc(collection(db, 'long_transcriptions'), {
          userId: uid,
          fileName: file.name,
          fileSize: file.size,
          status: 'Enviando' as TranscriptionStatus,
          storagePath: '',
          transcriptionRaw: '',
          errorMessage: null,
          createdAt: serverTimestamp(),
          updatedAt: serverTimestamp(),
        });

        const ext = getExtension(file.name);
        const storagePath = `long_transcriptions/${uid}/${docRef.id}.${ext}`;
        await updateDoc(doc(db, 'long_transcriptions', docRef.id), { storagePath });

        const task = uploadBytesResumable(ref(storage, storagePath), file, { contentType: file.type });
        setUploadProgress((p) => ({ ...p, [docRef.id]: 0 }));

        task.on(
          'state_changed',
          (snapshot) => {
            const pct = Math.round((snapshot.bytesTransferred / snapshot.totalBytes) * 100);
            setUploadProgress((p) => ({ ...p, [docRef.id]: pct }));
          },
          async (error) => {
            console.error('[LongTranscription] upload error:', error);
            setUploadProgress((p) => {
              const { [docRef.id]: _, ...rest } = p;
              return rest;
            });
            try {
              await updateDoc(doc(db, 'long_transcriptions', docRef.id), {
                status: 'Erro',
                errorMessage: `Falha no upload: ${error.message}`,
                updatedAt: serverTimestamp(),
              });
            } catch {
              /* noop */
            }
            showToast('Falha ao enviar o arquivo.', 'error');
          },
          () => {
            setUploadProgress((p) => {
              const { [docRef.id]: _, ...rest } = p;
              return rest;
            });
            showToast('Upload concluído. Processando transcrição...', 'success');
          },
        );
      } catch (e) {
        console.error('[LongTranscription] startUpload error:', e);
        showToast('Não foi possível iniciar o envio.', 'error');
      }
    },
    [showToast],
  );

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      Array.from(files).forEach((f) => startUpload(f));
    },
    [startUpload],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  const copyText = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        showToast('Transcrição copiada!', 'success');
      } catch {
        showToast('Não foi possível copiar.', 'error');
      }
    },
    [showToast],
  );

  const cardBg = isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200';
  const textMuted = isDark ? 'text-slate-400' : 'text-slate-500';
  const headingColor = isDark ? 'text-slate-100' : 'text-slate-900';

  return (
    <div className={`min-h-full ${isDark ? 'bg-slate-950' : 'bg-slate-50'} p-4 md:p-8`}>
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={onBack}
            className={`w-12 h-12 rounded-none flex items-center justify-center border transition-all ${
              isDark
                ? 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-100 hover:border-blue-500'
                : 'bg-white border-slate-200 text-slate-400 hover:text-slate-900 hover:border-slate-900'
            }`}
            aria-label="Voltar"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div>
            <p className="text-[10px] font-mono font-black text-blue-500 uppercase tracking-widest mb-0.5">MODULE: ID-009</p>
            <h2 className={`text-xl font-mono font-black uppercase tracking-tight ${headingColor}`}>Transcrições Longas</h2>
          </div>
        </div>

        {/* Upload area */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`cursor-pointer border-2 border-dashed rounded-none p-10 text-center transition-all mb-8 ${
            dragOver
              ? 'border-blue-500 bg-blue-500/5'
              : isDark
                ? 'border-slate-700 hover:border-blue-500/60 bg-slate-900'
                : 'border-slate-300 hover:border-blue-400 bg-white'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*,video/*"
            multiple
            className="hidden"
            onChange={(e) => {
              handleFiles(e.target.files);
              e.target.value = '';
            }}
          />
          <svg className={`w-10 h-10 mx-auto mb-3 ${isDark ? 'text-slate-600' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" />
          </svg>
          <p className={`text-sm font-mono font-black uppercase tracking-widest ${headingColor}`}>
            Arraste áudio ou vídeo aqui
          </p>
          <p className={`text-[11px] font-mono mt-1 ${textMuted}`}>
            Arquivos de qualquer tamanho — o vídeo é convertido em áudio automaticamente
          </p>
        </div>

        {/* History */}
        <div className="flex items-center justify-between mb-3">
          <h3 className={`text-[10px] font-mono font-black uppercase tracking-[0.3em] ${textMuted}`}>Histórico</h3>
        </div>

        {loadingHistory ? (
          <p className={`text-xs font-mono ${textMuted} py-8 text-center`}>Carregando...</p>
        ) : history.length === 0 ? (
          <div className={`border rounded-none p-10 text-center ${cardBg}`}>
            <p className={`text-[10px] font-mono font-black uppercase tracking-[0.2em] ${textMuted}`}>Nenhuma transcrição ainda</p>
          </div>
        ) : (
          <div className="space-y-2">
            {history.map((item) => {
              const progress = uploadProgress[item.id];
              const isDone = item.status === 'Concluído';
              return (
                <div
                  key={item.id}
                  onClick={() => isDone && setSelected(item)}
                  className={`border rounded-none p-4 transition-all ${cardBg} ${
                    isDone ? 'cursor-pointer hover:border-blue-400' : ''
                  }`}
                >
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <p className={`text-sm font-mono font-bold truncate ${headingColor}`}>{item.fileName}</p>
                      <p className={`text-[10px] font-mono ${textMuted} mt-0.5`}>
                        {formatBytes(item.fileSize)} · {formatDate(item.createdAt)}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 text-[9px] font-mono font-black uppercase tracking-widest px-2.5 py-1 border rounded-none ${statusStyles(
                        item.status,
                        isDark,
                      )}`}
                    >
                      {item.status}
                    </span>
                  </div>

                  {item.status === 'Enviando' && typeof progress === 'number' && (
                    <div className="mt-3">
                      <div className={`h-1.5 w-full rounded-none overflow-hidden ${isDark ? 'bg-slate-800' : 'bg-slate-200'}`}>
                        <div className="h-full bg-blue-500 transition-all" style={{ width: `${progress}%` }} />
                      </div>
                      <p className={`text-[9px] font-mono ${textMuted} mt-1`}>{progress}% enviado</p>
                    </div>
                  )}

                  {item.status === 'Processando' && (
                    <p className={`text-[10px] font-mono ${textMuted} mt-2`}>Transcrevendo no servidor — isso pode levar alguns minutos.</p>
                  )}

                  {item.status === 'Erro' && item.errorMessage && (
                    <p className="text-[10px] font-mono text-red-500 mt-2 break-words">{item.errorMessage}</p>
                  )}

                  {item.status === 'Concluído' && item.errorMessage && (
                    <p className="text-[10px] font-mono text-amber-500 mt-2 break-words">{item.errorMessage}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/40" onClick={() => setSelected(null)} />
          <div className={`relative w-full max-w-2xl h-full overflow-y-auto shadow-2xl ${isDark ? 'bg-slate-900' : 'bg-white'}`}>
            <div className={`sticky top-0 z-10 flex items-center justify-between gap-4 p-5 border-b ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
              <div className="min-w-0">
                <p className={`text-[9px] font-mono font-black text-blue-500 uppercase tracking-widest`}>Transcrição bruta</p>
                <h3 className={`text-sm font-mono font-bold truncate ${headingColor}`}>{selected.fileName}</h3>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => copyText(selected.transcriptionRaw || '')}
                  className="bg-blue-600 text-white h-9 px-3 flex items-center gap-1.5 rounded-none hover:bg-blue-700 transition-all font-mono text-[10px] font-black uppercase tracking-widest"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  Copiar
                </button>
                <button
                  onClick={() => setSelected(null)}
                  className={`h-9 w-9 flex items-center justify-center rounded-none border ${
                    isDark ? 'border-slate-700 text-slate-400 hover:text-slate-100' : 'border-slate-200 text-slate-400 hover:text-slate-900'
                  }`}
                  aria-label="Fechar"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <div className="p-5">
              <pre className={`whitespace-pre-wrap break-words font-sans text-sm leading-relaxed ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
                {selected.transcriptionRaw || '(vazio)'}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LongTranscriptionTool;
