import React, { useCallback, useEffect, useRef, useState } from 'react';
import { httpsCallable } from 'firebase/functions';
import { ref, uploadBytesResumable } from 'firebase/storage';
import { functions, storage, auth } from '@/firebase';

// A partir deste tempo de processamento no backend (upload já concluído),
// exibimos um aviso de que o processo continua em andamento (e não travou).
const PROCESSING_STILL_RUNNING_THRESHOLD_MS = 15000;

interface BatchTranscriptionToolProps {
  onBack: () => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
  isDark?: boolean;
  onSendToCopiloto?: (text: string) => void;
}

type BatchItemKind = 'audio' | 'video' | 'text';
type BatchItemStatus = 'pendente' | 'processando' | 'concluido' | 'erro';

interface BatchItem {
  localId: string;
  dbId?: number;
  kind: BatchItemKind;
  file?: File;
  text?: string;
  label: string;
  status: BatchItemStatus;
  resultRefined?: string;
  errorMessage?: string;
  uploadProgress?: number;
  stillProcessing?: boolean;
}

const SHARE_DB_NAME = 'hermes-share-db';
const SHARE_STORE_NAME = 'shared-files';
const BATCH_HISTORY_KEY = 'hermes_batch_transcription_history';

interface BatchHistoryEntry {
  id: string;
  date: string;
  itemCount: number;
  document: string;
}

const genId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

const formatBytes = (bytes: number): string => {
  if (!bytes || bytes <= 0) return '0 MB';
  const mb = bytes / (1024 * 1024);
  if (mb < 1) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${mb.toFixed(2)} MB`;
};

const openShareDb = (): Promise<IDBDatabase> => {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(SHARE_DB_NAME, 1);
    req.onupgradeneeded = (e: any) => {
      const db = e.target.result as IDBDatabase;
      if (!db.objectStoreNames.contains(SHARE_STORE_NAME)) {
        db.createObjectStore(SHARE_STORE_NAME, { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
};

const readQueuedShareItems = async (): Promise<BatchItem[]> => {
  try {
    const db = await openShareDb();
    if (!db.objectStoreNames.contains(SHARE_STORE_NAME)) return [];
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(SHARE_STORE_NAME, 'readonly');
      const store = tx.objectStore(SHARE_STORE_NAME);
      const req = store.getAll();
      req.onsuccess = () => {
        const records = (req.result || []) as Array<{
          id: number;
          file?: File;
          fileType: BatchItemKind;
          title?: string;
          text?: string;
          timestamp: number;
        }>;
        records.sort((a, b) => a.timestamp - b.timestamp);
        const items: BatchItem[] = records.map((r) => ({
          localId: genId(),
          dbId: r.id,
          kind: r.fileType,
          file: r.file,
          text: r.fileType === 'text' ? (r.text || r.title || '') : undefined,
          label: r.fileType === 'text' ? (r.text || r.title || 'Mensagem de texto').slice(0, 60) : (r.file?.name || 'Arquivo compartilhado'),
          status: 'pendente',
        }));
        resolve(items);
      };
      req.onerror = () => reject(req.error);
    });
  } catch (e) {
    console.error('[BatchTranscriptionTool] Erro ao ler fila compartilhada:', e);
    return [];
  }
};

const deleteQueuedShareItem = async (dbId: number): Promise<void> => {
  try {
    const db = await openShareDb();
    const tx = db.transaction(SHARE_STORE_NAME, 'readwrite');
    tx.objectStore(SHARE_STORE_NAME).delete(dbId);
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch (e) {
    console.error('[BatchTranscriptionTool] Erro ao remover item da fila:', e);
  }
};

export const BatchTranscriptionTool: React.FC<BatchTranscriptionToolProps> = ({ onBack, showToast, isDark = false, onSendToCopiloto }) => {
  const [items, setItems] = useState<BatchItem[]>([]);
  const [textDraft, setTextDraft] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [finalDocument, setFinalDocument] = useState<string | null>(null);
  const [history, setHistory] = useState<BatchHistoryEntry[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    readQueuedShareItems().then((queued) => {
      if (queued.length > 0) {
        setItems((prev) => [...prev, ...queued]);
        showToast(`${queued.length} item(ns) compartilhado(s) adicionado(s) à fila.`, 'success');
      }
    });

    const saved = localStorage.getItem(BATCH_HISTORY_KEY);
    if (saved) {
      try {
        setHistory(JSON.parse(saved));
      } catch {
        /* noop */
      }
    }
  }, []);

  const saveToHistory = (document: string, itemCount: number) => {
    const entry: BatchHistoryEntry = { id: genId(), date: new Date().toISOString(), itemCount, document };
    const updated = [entry, ...history].slice(0, 30);
    setHistory(updated);
    localStorage.setItem(BATCH_HISTORY_KEY, JSON.stringify(updated));
  };

  const addFiles = useCallback((files: FileList | File[] | null) => {
    if (!files) return;
    const arr = Array.from(files).filter((f) => f.type.startsWith('audio/') || f.type.startsWith('video/'));
    if (arr.length === 0) {
      showToast('Selecione arquivos de áudio ou vídeo.', 'error');
      return;
    }
    const newItems: BatchItem[] = arr.map((f) => ({
      localId: genId(),
      kind: f.type.startsWith('video/') ? 'video' : 'audio',
      file: f,
      label: f.name,
      status: 'pendente',
    }));
    setItems((prev) => [...prev, ...newItems]);
  }, [showToast]);

  const addTextItem = () => {
    const text = textDraft.trim();
    if (!text) return;
    setItems((prev) => [...prev, { localId: genId(), kind: 'text', text, label: text.slice(0, 60), status: 'pendente' }]);
    setTextDraft('');
  };

  const removeItem = async (localId: string) => {
    const target = items.find((i) => i.localId === localId);
    if (target?.dbId) await deleteQueuedShareItem(target.dbId);
    setItems((prev) => prev.filter((i) => i.localId !== localId));
  };

  const moveItem = (localId: string, direction: -1 | 1) => {
    setItems((prev) => {
      const idx = prev.findIndex((i) => i.localId === localId);
      const newIdx = idx + direction;
      if (idx < 0 || newIdx < 0 || newIdx >= prev.length) return prev;
      const copy = [...prev];
      [copy[idx], copy[newIdx]] = [copy[newIdx], copy[idx]];
      return copy;
    });
  };

  const updateItem = (localId: string, patch: Partial<BatchItem>) => {
    setItems((prev) => prev.map((i) => (i.localId === localId ? { ...i, ...patch } : i)));
  };

  const transcribeFile = async (
    file: File,
    onUploadProgress: (pct: number | null) => void,
  ): Promise<{ raw: string; refined: string }> => {
    const uid = auth.currentUser?.uid;
    if (!uid) throw new Error('Você precisa estar autenticado para transcrever.');

    const extension = `.${file.name.split('.').pop()?.toLowerCase() || 'm4a'}`;
    const storagePath = `quick_transcriptions/${uid}/${Date.now()}_${Math.random().toString(36).slice(2)}${extension}`;

    // Upload direto pro Storage: evita o limite de 32MB de payload das Cloud Functions.
    await new Promise<void>((resolve, reject) => {
      const task = uploadBytesResumable(ref(storage, storagePath), file, { contentType: file.type || 'application/octet-stream' });
      task.on(
        'state_changed',
        (snapshot) => onUploadProgress(Math.round((snapshot.bytesTransferred / snapshot.totalBytes) * 100)),
        (error) => reject(error),
        () => resolve(),
      );
    });
    onUploadProgress(null);

    const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
    const response = await transcribeFunc({ storagePath, extension });
    return response.data as { raw: string; refined: string };
  };

  const handleProcessBatch = async () => {
    if (items.length === 0) return;
    setIsProcessing(true);
    setFinalDocument(null);
    const sections: string[] = [];
    const failed: string[] = [];
    const processedDbIds: number[] = [];

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      updateItem(item.localId, { status: 'processando', uploadProgress: undefined, stillProcessing: false });
      let stillProcessingTimer: ReturnType<typeof setTimeout> | null = null;
      try {
        if (item.kind === 'text') {
          sections.push(`[${i + 1}] Texto\n${item.text}`);
          updateItem(item.localId, { status: 'concluido' });
        } else if (item.file) {
          const result = await transcribeFile(item.file, (pct) => {
            updateItem(item.localId, { uploadProgress: pct ?? undefined });
            if (pct === null) {
              stillProcessingTimer = setTimeout(() => updateItem(item.localId, { stillProcessing: true }), PROCESSING_STILL_RUNNING_THRESHOLD_MS);
            }
          });
          sections.push(`[${i + 1}] ${item.kind === 'video' ? 'Vídeo' : 'Áudio'} — ${item.file.name}\n${result.refined}`);
          updateItem(item.localId, { status: 'concluido', resultRefined: result.refined, uploadProgress: undefined, stillProcessing: false });
          if (item.dbId) processedDbIds.push(item.dbId);
        }
      } catch (error) {
        console.error('[BatchTranscriptionTool] Erro ao processar item:', error);
        updateItem(item.localId, { status: 'erro', errorMessage: 'Falha ao transcrever.', uploadProgress: undefined, stillProcessing: false });
        failed.push(item.label);
      } finally {
        if (stillProcessingTimer) clearTimeout(stillProcessingTimer);
      }
    }

    for (const dbId of processedDbIds) {
      await deleteQueuedShareItem(dbId);
    }

    const document = sections.join('\n\n');
    setFinalDocument(document);
    saveToHistory(document, items.length);
    setIsProcessing(false);

    if (failed.length > 0) {
      showToast(`Lote concluído com falhas em: ${failed.join(', ')}`, 'error');
    } else {
      showToast('Lote transcrito com sucesso!', 'success');
    }
  };

  const copyDocument = () => {
    if (!finalDocument) return;
    navigator.clipboard.writeText(finalDocument);
    showToast('Documento copiado!', 'success');
  };

  const sendDocumentToCopiloto = () => {
    if (finalDocument && onSendToCopiloto) {
      onSendToCopiloto(finalDocument);
      showToast('Documento enviado ao Copiloto Hermes!', 'success');
    }
  };

  const cardBg = isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200';
  const textMuted = isDark ? 'text-slate-400' : 'text-slate-500';
  const headingColor = isDark ? 'text-slate-100' : 'text-slate-900';

  const statusLabel: Record<BatchItemStatus, string> = {
    pendente: 'Pendente',
    processando: 'Processando...',
    concluido: 'Concluído',
    erro: 'Erro',
  };
  const statusStyle: Record<BatchItemStatus, string> = {
    pendente: isDark ? 'bg-slate-800 text-slate-300 border-slate-600' : 'bg-slate-100 text-slate-600 border-slate-300',
    processando: isDark ? 'bg-amber-900/40 text-amber-300 border-amber-700' : 'bg-amber-50 text-amber-700 border-amber-300',
    concluido: isDark ? 'bg-emerald-900/40 text-emerald-300 border-emerald-700' : 'bg-emerald-50 text-emerald-700 border-emerald-300',
    erro: isDark ? 'bg-red-900/40 text-red-300 border-red-700' : 'bg-red-50 text-red-700 border-red-300',
  };

  return (
    <div className={`min-h-full ${isDark ? 'bg-slate-950' : 'bg-slate-50'} p-4 md:p-8`}>
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={onBack}
            className={`w-12 h-12 rounded-none-none flex items-center justify-center border transition-all ${
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
            <p className="text-[10px] font-mono font-bold text-blue-500 uppercase tracking-wider mb-0.5">MODULE: ID-010</p>
            <h2 className={`text-xl font-mono font-bold uppercase tracking-tight ${headingColor}`}>Transcrição em Lote</h2>
            <p className={`text-[11px] font-mono mt-0.5 ${textMuted}`}>Adicione áudios, vídeos e textos na ordem desejada e gere um documento único.</p>
          </div>
        </div>

        {/* Add controls */}
        <div className={`border rounded-none-none p-4 md:p-5 mb-6 ${cardBg}`}>
          <div className="flex flex-col md:flex-row gap-3 mb-3">
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*,video/*"
              multiple
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = '';
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className={`px-4 py-2.5 border rounded-none-none text-[10px] font-bold uppercase tracking-wider transition-all ${
                isDark ? 'border-slate-600 bg-slate-800 text-slate-200 hover:border-blue-400' : 'border-slate-200 bg-white text-slate-600 hover:border-blue-400 hover:text-blue-600'
              }`}
            >
              + Adicionar Áudio/Vídeo
            </button>
          </div>
          <div className="flex flex-col md:flex-row gap-3">
            <input
              type="text"
              value={textDraft}
              onChange={(e) => setTextDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') addTextItem(); }}
              onPaste={async (e) => {
                const pastedItems = e.clipboardData.items;
                let audioFile: File | null = null;
                for (let i = 0; i < pastedItems.length; i++) {
                  if (pastedItems[i].type.startsWith('audio/') || pastedItems[i].type.startsWith('video/')) {
                    audioFile = pastedItems[i].getAsFile();
                    break;
                  }
                }
                
                // Executa apenas se for desktop (ex: largura da janela >= 768px)
                if (audioFile && window.innerWidth >= 768) {
                  e.preventDefault();
                  showToast('Áudio colado! Transcrevendo automaticamente...', 'info');
                  try {
                    const result = await transcribeFile(audioFile, () => {});
                    setTextDraft((prev) => prev ? prev + '\n' + result.refined : result.refined);
                    showToast('Áudio transcrito com sucesso!', 'success');
                  } catch (error) {
                    console.error('[BatchTranscriptionTool] Erro na transcrição automática:', error);
                    showToast('Erro ao transcrever o áudio.', 'error');
                  }
                }
              }}
              placeholder="Cole aqui uma mensagem de texto da conversa..."
              className={`flex-1 px-4 py-2.5 border rounded-none-none text-sm font-medium outline-none ${
                isDark ? 'bg-slate-800 border-slate-600 text-slate-100 placeholder:text-slate-500' : 'bg-white border-slate-200 text-slate-900 placeholder:text-slate-400'
              }`}
            />
            <button
              onClick={addTextItem}
              className={`px-4 py-2.5 border rounded-none-none text-[10px] font-bold uppercase tracking-wider transition-all ${
                isDark ? 'border-slate-600 bg-slate-800 text-slate-200 hover:border-blue-400' : 'border-slate-200 bg-white text-slate-600 hover:border-blue-400 hover:text-blue-600'
              }`}
            >
              + Adicionar Texto
            </button>
          </div>
        </div>

        {/* Queue */}
        <div className="flex items-center justify-between mb-3">
          <h3 className={`text-[10px] font-mono font-bold uppercase tracking-wider ${textMuted}`}>Fila ({items.length})</h3>
          {items.length > 0 && (
            <button
              onClick={handleProcessBatch}
              disabled={isProcessing}
              className={`px-5 py-2.5 bg-slate-900 text-white rounded-none-none text-[10px] font-bold uppercase tracking-wider hover:bg-blue-600 transition-all ${isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {isProcessing ? 'Processando...' : 'Transcrever Lote'}
            </button>
          )}
        </div>

        {items.length === 0 ? (
          <div className={`border rounded-none-none p-10 text-center mb-6 ${cardBg}`}>
            <p className={`text-[10px] font-mono font-bold uppercase tracking-wider ${textMuted}`}>Nenhum item na fila</p>
            <p className={`text-[11px] font-mono mt-2 ${textMuted}`}>Adicione arquivos/textos acima, ou compartilhe mensagens do WhatsApp direto para o Hermes pelo celular.</p>
          </div>
        ) : (
          <div className="space-y-2 mb-6">
            {items.map((item, idx) => (
              <div key={item.localId} className={`border rounded-none-none p-3 md:p-4 flex items-center gap-3 ${cardBg}`}>
                <span className={`shrink-0 w-7 h-7 flex items-center justify-center rounded-none-none text-[10px] font-mono font-bold ${isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-100 text-slate-500'}`}>
                  {idx + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={`text-sm font-mono font-bold truncate ${headingColor}`}>{item.label}</p>
                  <p className={`text-[10px] font-mono ${textMuted}`}>
                    {item.kind === 'text' ? 'Texto' : item.kind === 'video' ? 'Vídeo' : 'Áudio'}
                    {item.file ? ` · ${formatBytes(item.file.size)}` : ''}
                  </p>
                  {item.errorMessage && <p className="text-[10px] font-mono text-red-500 mt-1">{item.errorMessage}</p>}
                  {item.status === 'processando' && (
                    typeof item.uploadProgress === 'number' ? (
                      <div className="mt-1.5">
                        <div className={`h-1 w-full rounded-none-none overflow-hidden ${isDark ? 'bg-slate-800' : 'bg-slate-200'}`}>
                          <div className="h-full bg-blue-500 transition-all" style={{ width: `${item.uploadProgress}%` }} />
                        </div>
                        <p className={`text-[9px] font-mono mt-1 ${textMuted}`}>Enviando... {item.uploadProgress}%</p>
                      </div>
                    ) : item.stillProcessing ? (
                      <p className="text-[10px] font-mono text-amber-500 mt-1">Ainda processando... não travou, pode levar mais alguns instantes.</p>
                    ) : null
                  )}
                </div>
                <span className={`shrink-0 text-[9px] font-mono font-bold uppercase tracking-wider px-2 py-1 border rounded-none-none ${statusStyle[item.status]}`}>
                  {statusLabel[item.status]}
                </span>
                {!isProcessing && (
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => moveItem(item.localId, -1)} disabled={idx === 0} className={`w-7 h-7 flex items-center justify-center rounded-none-none border disabled:opacity-30 ${isDark ? 'border-slate-700 text-slate-400 hover:text-slate-100' : 'border-slate-200 text-slate-400 hover:text-slate-900'}`} aria-label="Mover para cima">↑</button>
                    <button onClick={() => moveItem(item.localId, 1)} disabled={idx === items.length - 1} className={`w-7 h-7 flex items-center justify-center rounded-none-none border disabled:opacity-30 ${isDark ? 'border-slate-700 text-slate-400 hover:text-slate-100' : 'border-slate-200 text-slate-400 hover:text-slate-900'}`} aria-label="Mover para baixo">↓</button>
                    <button onClick={() => removeItem(item.localId)} className={`w-7 h-7 flex items-center justify-center rounded-none-none border hover:text-rose-500 ${isDark ? 'border-slate-700 text-slate-400' : 'border-slate-200 text-slate-400'}`} aria-label="Remover">✕</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Final document */}
        {finalDocument && (
          <div className={`border rounded-none-none p-4 md:p-5 mb-6 ${cardBg}`}>
            <div className="flex items-center justify-between gap-3 mb-3">
              <h3 className={`text-[10px] font-mono font-bold uppercase tracking-wider ${textMuted}`}>Documento Final</h3>
              <div className="flex items-center gap-2">
                {onSendToCopiloto && (
                  <button onClick={sendDocumentToCopiloto} className="px-3 py-2 bg-blue-50 text-blue-600 rounded-none-none text-[10px] font-bold uppercase tracking-wider hover:bg-blue-100 transition-all">
                    Enviar ao Copiloto
                  </button>
                )}
                <button onClick={copyDocument} className="px-3 py-2 bg-emerald-50 text-emerald-600 rounded-none-none text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-100 transition-all">
                  Copiar
                </button>
              </div>
            </div>
            <pre className={`whitespace-pre-wrap break-words font-sans text-sm leading-relaxed max-h-[400px] overflow-y-auto ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
              {finalDocument}
            </pre>
          </div>
        )}

        {/* History */}
        {history.length > 0 && (
          <div>
            <h3 className={`text-[10px] font-mono font-bold uppercase tracking-wider mb-3 ${textMuted}`}>Histórico de Lotes</h3>
            <div className="space-y-2">
              {history.map((entry) => (
                <button
                  key={entry.id}
                  onClick={() => setFinalDocument(entry.document)}
                  className={`w-full text-left border rounded-none-none p-3 transition-all hover:border-blue-400 ${cardBg}`}
                >
                  <p className={`text-sm font-mono font-bold ${headingColor}`}>{entry.itemCount} item(ns)</p>
                  <p className={`text-[10px] font-mono ${textMuted}`}>{new Date(entry.date).toLocaleString('pt-BR')}</p>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default BatchTranscriptionTool;
