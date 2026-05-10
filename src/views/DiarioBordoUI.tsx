import React from 'react';
import { AutoExpandingTextarea, CollapsibleContainer } from '../components/ui/UIComponents';
import { formatWhatsAppText } from '../utils/helpers';
import { ensureHttpUrl, parseDiaryRichNote } from '../utils/diaryEntries';
import EmojiPicker from 'emoji-picker-react';

interface DiarioBordoUIProps {
  task: any;
  currentTaskData: any;
  newFollowUp: string;
  setNewFollowUp: (val: string) => void;
  handleAddFollowUp: () => void;
  handleCopyMessage: (text: string) => void;
  handleCopyAllHistory: () => void;
  isRecording: boolean;
  startRecording: () => void;
  stopRecording: () => void;
  isProcessingTranscription: boolean;
  showAttachMenu: boolean;
  setShowAttachMenu: (val: boolean) => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  handleFileUploadInput: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleDroppedFiles: (files: File[]) => void;
  setModalConfig: (config: any) => void;
  applyFormatting: (symbol: string) => void;
  isTimerRunning: boolean;
  diaryEndRef: React.RefObject<HTMLDivElement>;
  handleDiaryScroll: (e: React.UIEvent<HTMLDivElement>) => void;
  handleEditDiaryEntry: (idx: number) => void;
  handleDeleteDiaryEntry: (idx: number) => void;
  isUploading: boolean;
  notifications?: any[];
  handleProcessAudio?: (audioBlob: Blob) => void;
  onFocusFile?: (file: { url: string; nome: string; tipo: 'link' | 'file' | 'image'; driveFileId?: string }) => void;
}

export const DiarioBordoUI = ({
  task, currentTaskData, newFollowUp, setNewFollowUp, handleAddFollowUp, handleCopyMessage, handleCopyAllHistory,
  isRecording, startRecording, stopRecording, isProcessingTranscription, showAttachMenu, setShowAttachMenu,
  fileInputRef, handleFileUploadInput, handleDroppedFiles, setModalConfig, applyFormatting, isTimerRunning,
  diaryEndRef, handleDiaryScroll, handleEditDiaryEntry, handleDeleteDiaryEntry, isUploading,
  notifications = [], handleProcessAudio, onFocusFile
}: DiarioBordoUIProps) => {
  const [showEmojiPicker, setShowEmojiPicker] = React.useState(false);
  const [showFormattingMenu, setShowFormattingMenu] = React.useState(false);
  const [isDragActive, setIsDragActive] = React.useState(false);
  const dragCounterRef = React.useRef(0);

  const getDiaryInput = React.useCallback(() => document.getElementById('diary-input') as HTMLTextAreaElement | null, []);

  const insertIntoDiaryInput = React.useCallback((insertText: string) => {
    const input = getDiaryInput();
    const start = input?.selectionStart ?? newFollowUp.length;
    const end = input?.selectionEnd ?? newFollowUp.length;
    const nextValue = newFollowUp.slice(0, start) + insertText + newFollowUp.slice(end);
    setNewFollowUp(nextValue);
    requestAnimationFrame(() => {
      const nextInput = getDiaryInput();
      nextInput?.focus();
      const caret = start + insertText.length;
      nextInput?.setSelectionRange(caret, caret);
    });
  }, [getDiaryInput, newFollowUp, setNewFollowUp]);

  const applyDiaryFormatting = React.useCallback((symbol: string) => {
    const input = getDiaryInput();
    const start = input?.selectionStart ?? newFollowUp.length;
    const end = input?.selectionEnd ?? newFollowUp.length;
    const selected = newFollowUp.slice(start, end);
    const wrapped = selected ? `${symbol}${selected}${symbol}` : `${symbol}${symbol}`;
    const nextValue = newFollowUp.slice(0, start) + wrapped + newFollowUp.slice(end);

    setNewFollowUp(nextValue);
    setShowFormattingMenu(false);
    requestAnimationFrame(() => {
      const nextInput = getDiaryInput();
      nextInput?.focus();
      if (selected) {
        nextInput?.setSelectionRange(start, start + wrapped.length);
        return;
      }
      nextInput?.setSelectionRange(start + symbol.length, start + symbol.length);
    });
  }, [getDiaryInput, newFollowUp, setNewFollowUp]);

  const processDroppedFiles = React.useCallback((files: File[]) => {
    if (files.length === 0) return;
    const oggFile = files.find(f => f.type === 'audio/ogg' || f.name.endsWith('.ogg'));

    if (oggFile && handleProcessAudio) {
      handleProcessAudio(oggFile);
      const remainingFiles = files.filter(f => f !== oggFile);
      if (remainingFiles.length > 0) {
        handleDroppedFiles(remainingFiles);
      }
      return;
    }

    handleDroppedFiles(files);
  }, [handleDroppedFiles, handleProcessAudio]);

  const handleDragEnter = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!Array.from(e.dataTransfer.types).includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current += 1;
    setIsDragActive(true);
  }, []);

  const handleDragOver = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!Array.from(e.dataTransfer.types).includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
    setIsDragActive(true);
  }, []);

  const handleDragLeave = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!Array.from(e.dataTransfer.types).includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
    if (dragCounterRef.current === 0) {
      setIsDragActive(false);
    }
  }, []);

  const handleDrop = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!Array.from(e.dataTransfer.types).includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current = 0;
    setIsDragActive(false);
    processDroppedFiles(Array.from(e.dataTransfer.files || []));
  }, [processDroppedFiles]);


  React.useEffect(() => {
    if (diaryEndRef.current) {
      diaryEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentTaskData.acompanhamento, isUploading, diaryEndRef]);

  const renderDiaryContent = (text: string) => {
    const richEntry = parseDiaryRichNote(text);

    if (richEntry?.type === 'LINK') {
      const url = ensureHttpUrl(richEntry.value);
      const nome = richEntry.name || richEntry.value;
      return (
        <a href={url} target="_blank" rel="noreferrer"
          onClick={(e) => {
            if (onFocusFile) {
              e.preventDefault();
              const dMatch = url.match(/\/d\/([a-zA-Z0-9_-]{10,})/);
              onFocusFile({ url, nome, tipo: 'link', driveFileId: dMatch ? dMatch[1] : undefined });
            }
          }}
          className={`group flex items-center gap-2 p-2 rounded-none border transition-all ${isTimerRunning ? 'bg-white/5 border-border-grid hover:bg-white/10' : 'bg-blue-50/50 border-border-grid hover:bg-blue-50'}`}>
          <div className={`w-8 h-8 rounded-none flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-blue-200 text-blue-600'}`}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-[11px] font-bold break-all leading-snug font-mono ${isTimerRunning ? 'text-white' : 'text-blue-900'}`}>{nome || url}</p>
            <p className={`text-[8px] uppercase font-black tracking-widest mt-0.5 opacity-50 font-mono ${isTimerRunning ? 'text-white/40' : 'text-blue-400'}`}>Link</p>
          </div>
        </a>
      );
    }

    if (richEntry?.type === 'CONTACT') {
      const contact = richEntry.value;
      const nome = richEntry.name || contact;
      const num = contact.replace(/\D/g, '');
      const waNumber = num.startsWith('55') ? num : `55${num}`;
      const waLink = num.length >= 10 ? `https://wa.me/${waNumber}` : null;
      return (
        <div className={`group flex items-center gap-2 p-2 rounded-none border transition-all ${isTimerRunning ? 'bg-white/5 border-border-grid' : 'bg-emerald-50/50 border-border-grid'}`}>
          <div className={`w-8 h-8 rounded-none flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-emerald-200 text-emerald-600'}`}>
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.022-.014-.503-.245-.583-.273-.08-.027-.138-.04-.197.048-.058.088-.227.288-.278.346-.05.058-.1.066-.188.022-.088-.044-.372-.137-.708-.437-.26-.231-.437-.515-.487-.603-.05-.088-.005-.135.039-.179.04-.04.088-.103.131-.154.044-.051.059-.088.088-.146.03-.058.015-.11-.008-.154-.022-.044-.197-.474-.27-.65-.072-.172-.143-.149-.197-.151l-.168-.002c-.058 0-.154.022-.234.11-.08.088-.307.3-.307.732 0 .432.315.849.359.907.044.058.62 1.04 1.502 1.42.21.09.372.143.5.184.21.067.4.057.55.035.168-.024.503-.205.574-.403.072-.198.072-.367.051-.403-.021-.037-.08-.058-.168-.102z" /><path d="M12 2C6.477 2 2 6.477 2 12c0 1.891.524 3.66 1.434 5.168L2 22l4.958-1.412A9.957 9.957 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18a7.96 7.96 0 01-4.07-1.112l-.292-.174-3.024.863.878-2.946-.19-.302A7.957 7.957 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-[11px] font-bold break-all leading-snug font-mono ${isTimerRunning ? 'text-white' : 'text-emerald-900'}`}>{nome || contact}</p>
            <p className={`text-[8px] uppercase font-black tracking-widest mt-0.5 opacity-50 font-mono ${isTimerRunning ? 'text-white/40' : 'text-emerald-500'}`}>Contato</p>
          </div>
          {waLink && (
            <a href={waLink} target="_blank" rel="noreferrer" className={`p-1 rounded-none transition-colors ${isTimerRunning ? 'hover:bg-white/10 text-white' : 'hover:bg-emerald-200 text-emerald-600'}`} title="WhatsApp">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
            </a>
          )}
        </div>
      );
    }

    if (richEntry?.type === 'FILE') {
      const nome = richEntry.name || 'Arquivo';
      const url = richEntry.value || '#';
      const ext = nome.split('.').pop()?.toLowerCase() || '';
      const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(ext);

      // Conversão do link do Web View do Drive para Embed URL
      let embedUrl = url;
      if (isImage && url.includes('drive.google.com')) {
        const match = url.match(/\/d\/([a-zA-Z0-9_-]+)/) || url.match(/[?&]id=([a-zA-Z0-9_-]+)/);
        if (match && match[1]) {
          embedUrl = `https://drive.google.com/thumbnail?id=${match[1]}&sz=w800`;
        }
      }

      return (
        <a href={url} target="_blank" rel="noreferrer"
          onClick={(e) => {
            if (onFocusFile) {
              e.preventDefault();
              const dMatch = url.match(/\/d\/([a-zA-Z0-9_-]{10,})/) || url.match(/[?&]id=([a-zA-Z0-9_-]{10,})/);
              onFocusFile({ url, nome, tipo: isImage ? 'image' : 'file', driveFileId: dMatch ? dMatch[1] : undefined });
            }
          }}
          className={`group flex flex-col p-2 rounded-none border transition-all ${isTimerRunning ? 'bg-white/5 border-border-grid hover:bg-white/10' : 'bg-amber-50/50 border-border-grid hover:bg-amber-50'} overflow-hidden max-w-sm`}>
          {isImage && (
            <div className="w-full h-32 md:h-48 mb-2 bg-slate-900 rounded-none overflow-hidden flex items-center justify-center">
              <img src={embedUrl} alt={nome} className="w-full h-full object-cover opacity-90 group-hover:opacity-100 transition-opacity" />
            </div>
          )}
          <div className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-none flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-amber-200 text-amber-600'}`}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-[11px] font-bold break-all leading-snug font-mono ${isTimerRunning ? 'text-white' : 'text-amber-900'}`}>{nome}</p>
              <p className={`text-[8px] uppercase font-black tracking-widest mt-0.5 opacity-50 font-mono ${isTimerRunning ? 'text-white/40' : 'text-amber-600'}`}>Anexo{isImage ? ' Visual' : ''}</p>
            </div>
          </div>
        </a>
      );
    }

    return (
      <CollapsibleContainer maxLines={6}>
        <div className={`text-xs md:text-sm leading-relaxed break-words [overflow-wrap:anywhere] font-mono ${isTimerRunning ? 'text-white/90' : 'text-slate-700'}`}>{formatWhatsAppText(text, isTimerRunning)}</div>
      </CollapsibleContainer>
    );
  };

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex flex-col flex-1 min-h-0 relative rounded-none ${isTimerRunning ? 'bg-[#0f1724]' : 'bg-white'}`}
    >
      {isDragActive && (
        <div className={`pointer-events-none absolute inset-3 z-30 rounded-none border-2 border-dashed flex items-center justify-center backdrop-blur-sm ${isTimerRunning
          ? 'border-blue-400 bg-blue-500/10'
          : 'border-blue-400 bg-blue-50/90'
          }`}>
          <div className={`px-4 py-3 rounded-none text-center shadow-lg ${isTimerRunning ? 'bg-slate-950/80 text-blue-200' : 'bg-white text-blue-700'
            }`}>
            <p className="text-sm font-black uppercase tracking-widest">Solte para anexar</p>
            <p className="text-[11px] mt-1 opacity-80">O diário vai usar o mesmo fluxo do botão de upload.</p>
          </div>
        </div>
      )}
      {/* ── Área de histórico com scroll suave e scrollbar fina ── */}
      <div
        onScroll={handleDiaryScroll}
        className="diary-scroll flex-1 overflow-y-auto"
        style={{
          scrollbarWidth: 'thin',
          scrollbarColor: '#CBD5E0 transparent',
        }}
      >
        <style>{`
          .diary-scroll::-webkit-scrollbar { width: 6px; }
          .diary-scroll::-webkit-scrollbar-track { background: transparent; }
          .diary-scroll::-webkit-scrollbar-thumb { background: #CBD5E0; border-radius: 0; }
          .diary-scroll::-webkit-scrollbar-thumb:hover { background: #A0AEC0; }
        `}</style>

        {/* Wrapper interno com padding para afastar os elementos das bordas, sem tirar a barra de rolagem do limite */}
        <div className="px-3 md:px-6 pt-2 pb-2">
          <div className="flex justify-center mb-6">
            <div className={`border rounded-none px-4 py-2 text-[10px] uppercase tracking-widest font-black ${isTimerRunning ? 'bg-white/5 border-border-grid text-white/40' : 'bg-slate-100 border-border-grid text-slate-400'}`}>
              Início da Sessão • {new Date(task.data_criacao || Date.now()).toLocaleDateString()}
            </div>
          </div>



          <div className="space-y-1 pb-2">
            {(() => {
              const entries: any[] = currentTaskData.acompanhamento || [];
              const today = new Date();
              const yesterday = new Date(today);
              yesterday.setDate(today.getDate() - 1);
              const toKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
              const formatLabel = (iso: string) => {
                const d = new Date(iso);
                if (toKey(d) === toKey(today)) return 'Hoje';
                if (toKey(d) === toKey(yesterday)) return 'Ontem';
                return d.toLocaleDateString('pt-BR', { weekday: 'short', day: 'numeric', month: 'short' });
              };
              let lastKey = '';
              return entries.map((entry: any, idx: number) => {
                const entryDate = new Date(entry.data);
                const key = toKey(entryDate);
                const showHeader = key !== lastKey;
                lastKey = key;
                return (
                  <React.Fragment key={idx}>
                    {showHeader && (
                      <div className="flex justify-center py-3">
                        <span className={`text-[9px] font-black uppercase tracking-[0.2em] px-3 py-1 rounded-none border ${isTimerRunning ? 'bg-white/5 border-border-grid text-white/30' : 'bg-slate-100 border-border-grid text-slate-400'}`}>
                          {formatLabel(entry.data)}
                        </span>
                      </div>
                    )}
                    <div className="flex flex-col gap-1 items-start animate-in fade-in slide-in-from-bottom-2 duration-300 w-full mb-3">
                      <div className={`p-4 rounded-none border max-w-full md:max-w-[90%] shadow-lg relative group ${isTimerRunning ? 'bg-[#1A1A1A] border-border-grid' : 'bg-white border-border-grid shadow-slate-200'}`}>
                        {renderDiaryContent(entry.nota)}
                        <div className="flex items-center justify-between mt-2 gap-4">
                          <span className={`text-[9px] font-black uppercase tracking-wider font-mono ${isTimerRunning ? 'text-white/30' : 'text-slate-300'}`}>
                            {entryDate.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                          </span>
                          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button onClick={() => handleCopyMessage(entry.nota)} className={`transition-colors ${isTimerRunning ? 'text-white/40 hover:text-emerald-400' : 'text-slate-400 hover:text-emerald-500'}`} title="Copiar">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                              </button>
                            <button onClick={() => handleEditDiaryEntry(idx)} className={`transition-colors ${isTimerRunning ? 'text-white/40 hover:text-blue-400' : 'text-slate-400 hover:text-blue-500'}`} title="Editar">
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                            </button>
                            <button onClick={() => handleDeleteDiaryEntry(idx)} className={`transition-colors ${isTimerRunning ? 'text-white/40 hover:text-rose-500' : 'text-slate-400 hover:text-rose-500'}`} title="Excluir">
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </React.Fragment>
                );
              });
            })()}

            {isUploading && (
              <div className="flex flex-col gap-1 items-start animate-in fade-in duration-300 w-full opacity-60">
                <div className={`p-4 rounded-none border max-w-[90%] shadow-lg ${isTimerRunning ? 'bg-[#1A1A1A] border-border-grid' : 'bg-white border-border-grid shadow-slate-200'}`}>
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 rounded-none border-2 border-slate-300 border-t-blue-500 animate-spin"></div>
                    <p className={`text-xs font-bold font-mono ${isTimerRunning ? 'text-white/60' : 'text-slate-500'}`}>Enviando arquivos...</p>
                  </div>
                </div>
              </div>
            )}

            {(!currentTaskData.acompanhamento || currentTaskData.acompanhamento.length === 0) && (
              <div className="flex-1 flex flex-col items-center justify-center text-center opacity-30 mt-16">
                <p className={`text-sm font-medium mb-2 ${isTimerRunning ? 'text-white' : 'text-slate-800'}`}>Tudo pronto para começar?</p>
                <p className={`text-xs ${isTimerRunning ? 'text-white/60' : 'text-slate-500'}`}>Registre seu diário de execução abaixo.</p>
              </div>
            )}
            <div style={{ float: "left", clear: "both" }} ref={diaryEndRef}></div>
          </div>
        </div>
      </div>

      {/* ── Área de Input Compacta ── */}
      <div className="shrink-0 pt-1 px-2 md:px-6 pb-2 md:pb-6">
        <div className={`relative flex items-end gap-1 rounded-none border px-2 py-2 shadow-sm transition-all ${isTimerRunning ? 'bg-[#1A1A1A] border-border-grid focus-within:border-blue-500' : 'bg-white border-border-grid focus-within:border-blue-500'}`}>
          <div className="relative shrink-0">
            <button
              onClick={() => {
                setShowAttachMenu(!showAttachMenu);
                setShowFormattingMenu(false);
                setShowEmojiPicker(false);
              }}
              className={`flex h-9 w-9 items-center justify-center rounded-none transition-colors ${isTimerRunning ? 'text-white/55 hover:bg-white/10 hover:text-white/85' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'}`}
              title="Anexar"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v14m-7-7h14" /></svg>
            </button>
            {showAttachMenu && (
              <div className={`absolute bottom-11 left-0 w-48 rounded-none border shadow-xl overflow-hidden animate-in zoom-in-95 origin-bottom-left z-[100] ${isTimerRunning ? 'bg-[#1A1A1A] border-border-grid' : 'bg-white border-border-grid'}`}>
                <input type="file" multiple ref={fileInputRef} className="hidden" onChange={handleFileUploadInput} />
                <button onClick={() => fileInputRef.current?.click()} className={`w-full text-left px-4 py-3 text-xs font-bold flex items-center gap-2 ${isTimerRunning ? 'text-white/80 hover:bg-white/10' : 'text-slate-700 hover:bg-slate-50'}`}>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                  Carregar Arquivo
                </button>
                <button onClick={() => { setModalConfig({ type: 'link', isOpen: true }); setShowAttachMenu(false); }} className={`w-full text-left px-4 py-3 text-xs font-bold flex items-center gap-2 ${isTimerRunning ? 'text-white/80 hover:bg-white/10' : 'text-slate-700 hover:bg-slate-50'}`}>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
                  Inserir Link
                </button>
                <button onClick={() => { setModalConfig({ type: 'contact', isOpen: true }); setShowAttachMenu(false); }} className={`w-full text-left px-4 py-3 text-xs font-bold flex items-center gap-2 ${isTimerRunning ? 'text-white/80 hover:bg-white/10' : 'text-slate-700 hover:bg-slate-50'}`}>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" /></svg>
                  Inserir Contato
                </button>
              </div>
            )}
          </div>

          <div className="relative shrink-0">
            <button
              onClick={() => {
                setShowFormattingMenu(!showFormattingMenu);
                setShowAttachMenu(false);
                setShowEmojiPicker(false);
              }}
              className={`flex h-9 w-9 items-center justify-center rounded-none transition-colors ${isTimerRunning ? 'text-white/55 hover:bg-white/10 hover:text-white/85' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'}`}
              title="Formatação e emoji"
              aria-expanded={showFormattingMenu}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M4 7h16M8 7v10m8-10v10M6 17h4m4 0h4" />
              </svg>
            </button>
            {showFormattingMenu && (
              <div className={`absolute bottom-11 left-0 z-[100] w-44 rounded-none border p-1.5 shadow-2xl ${isTimerRunning ? 'bg-[#1A1A1A] border-border-grid' : 'bg-white border-border-grid'}`}>
                {[
                  { label: 'Negrito', mark: '*', icon: 'B', className: 'font-black' },
                  { label: 'Itálico', mark: '_', icon: 'I', className: 'italic' },
                  { label: 'Riscado', mark: '~', icon: 'S', className: 'line-through' },
                  { label: 'Código', mark: '`', icon: '</>', className: 'font-mono text-[10px]' },
                ].map(item => (
                  <button
                    key={item.mark}
                    onClick={() => applyDiaryFormatting(item.mark)}
                    className={`w-full flex items-center gap-3 rounded-none px-3 py-2 text-left text-xs font-bold transition-colors ${isTimerRunning ? 'text-white/80 hover:bg-white/10' : 'text-slate-700 hover:bg-slate-50'}`}
                  >
                    <span className={`flex h-6 w-6 items-center justify-center rounded-none ${isTimerRunning ? 'bg-white/10 text-white/70' : 'bg-slate-100 text-slate-500'} ${item.className}`}>{item.icon}</span>
                    {item.label}
                  </button>
                ))}
                <div className={`my-1 h-px ${isTimerRunning ? 'bg-white/10' : 'bg-slate-100'}`} />
                <button
                  onClick={() => {
                    setShowEmojiPicker(true);
                    setShowFormattingMenu(false);
                  }}
                  className={`w-full flex items-center gap-3 rounded-none px-3 py-2 text-left text-xs font-bold transition-colors ${isTimerRunning ? 'text-white/80 hover:bg-white/10' : 'text-slate-700 hover:bg-slate-50'}`}
                >
                  <span className={`flex h-6 w-6 items-center justify-center rounded-none ${isTimerRunning ? 'bg-white/10 text-white/70' : 'bg-slate-100 text-slate-500'}`}>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  </span>
                  Emoji
                </button>
              </div>
            )}
            {showEmojiPicker && (
              <div className="absolute bottom-11 left-0 z-[100] shadow-2xl rounded-none">
                <EmojiPicker
                  onEmojiClick={(emojiData) => {
                    insertIntoDiaryInput(emojiData.emoji);
                    setShowEmojiPicker(false);
                  }}
                  theme={isTimerRunning ? 'dark' as any : 'light' as any}
                />
              </div>
            )}
          </div>

          <div className="relative flex-1 min-w-0">
            <AutoExpandingTextarea
              id="diary-input"
              value={newFollowUp}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNewFollowUp(e.target.value)}
              onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                const isMobileDevice = window.innerWidth < 640;
                if (e.key === 'Enter' && !e.shiftKey && !isMobileDevice) {
                  e.preventDefault();
                  handleAddFollowUp();
                }
              }}
              onPaste={(e: React.ClipboardEvent<HTMLTextAreaElement>) => {
                const pastedText = e.clipboardData.getData('text');
                if (pastedText && /\[\d{2}:\d{2}, \d{2}\/\d{2}\/\d{4}\]/.test(pastedText)) {
                  e.preventDefault();
                  const cleaned = pastedText.replace(/\[\d{2}:\d{2}, \d{2}\/\d{2}\/\d{4}\][^:]+:\s*/g, '').trim();
                  setNewFollowUp(newFollowUp ? newFollowUp + '\n' + cleaned : cleaned);
                  return;
                }

                if (e.clipboardData.files && e.clipboardData.files.length > 0) {
                  e.preventDefault();
                  try {
                    processDroppedFiles(Array.from(e.clipboardData.files));
                  } catch (err) {
                    console.error('Erro ao processar ficheiros:', err);
                  }
                }
              }}
              placeholder="Escreva Aqui"
              rows={1}
              className={`w-full px-2 pt-2.5 pb-1.5 outline-none text-sm leading-5 font-mono font-medium transition-all min-h-9 max-h-[120px] overflow-y-auto resize-none border-0 ${isTimerRunning
                ? 'bg-transparent text-white placeholder:text-white/20'
                : 'bg-transparent text-slate-800 placeholder:text-slate-400'
                }`}
            />
          </div>

          {newFollowUp.trim() && !isRecording ? (
            <button
              onClick={handleAddFollowUp}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-none bg-blue-600 text-white shadow-md shadow-blue-600/30 transition-all hover:bg-blue-500 active:scale-95"
              title="Enviar (Enter)"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          ) : (
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isProcessingTranscription}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-none transition-all active:scale-95 ${isRecording
                ? 'bg-rose-500 text-white animate-pulse shadow-rose-500/30'
                : isTimerRunning
                  ? 'bg-white/10 text-white/60 hover:bg-white/20 hover:text-white'
                  : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700'
                } disabled:opacity-40`}
              title={isRecording ? 'Parar Gravação' : 'Gravar Áudio'}
            >
              {isProcessingTranscription ? (
                <div className="w-4 h-4 border-2 border-slate-300 border-t-blue-500 rounded-none animate-spin"></div>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 10v2a7 7 0 01-14 0v-2m14 0h2m-16 0H3m9 10v3m-3 0h6" /></svg>
              )}
            </button>
          )}
        </div>

        {/* Helper text */}
        <p className={`hidden md:block text-[11px] mt-1.5 px-2 font-mono ${isTimerRunning ? 'text-white/20' : 'text-slate-400'}`}>
          Enter para enviar · Shift+Enter para nova linha
        </p>
        <p className={`md:hidden text-[11px] mt-1.5 px-2 font-mono ${isTimerRunning ? 'text-white/20' : 'text-slate-400'}`}>
          Enter para nova linha · Botão para enviar
        </p>
      </div>
    </div>
  );
};
