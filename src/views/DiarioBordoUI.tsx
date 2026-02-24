import React from 'react';
import { AutoExpandingTextarea } from '../components/ui/UIComponents';
import { formatWhatsAppText } from '../utils/helpers';

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
  setModalConfig: (config: any) => void;
  applyFormatting: (symbol: string) => void;
  isTimerRunning: boolean;
  diaryEndRef: React.RefObject<HTMLDivElement>;
  handleDiaryScroll: (e: React.UIEvent<HTMLDivElement>) => void;
  handleEditDiaryEntry: (idx: number) => void;
  handleDeleteDiaryEntry: (idx: number) => void;
  isUploading: boolean;
}

export const DiarioBordoUI = ({
  task, currentTaskData, newFollowUp, setNewFollowUp, handleAddFollowUp, handleCopyMessage, handleCopyAllHistory,
  isRecording, startRecording, stopRecording, isProcessingTranscription, showAttachMenu, setShowAttachMenu,
  fileInputRef, handleFileUploadInput, setModalConfig, applyFormatting, isTimerRunning,
  diaryEndRef, handleDiaryScroll, handleEditDiaryEntry, handleDeleteDiaryEntry, isUploading
}: DiarioBordoUIProps) => {

  const renderDiaryContent = (text: string) => {
    if (text.startsWith('LINK::')) {
      const parts = text.split('::');
      let url = '';
      let nome = '';
      if (parts.length >= 3) { nome = parts[1]; url = parts[2]; }
      else { url = text.replace('LINK::', ''); }
      return (
        <a href={url} target="_blank" rel="noreferrer" className={`group flex items-center gap-2 p-2 rounded-xl border transition-all ${isTimerRunning ? 'bg-white/5 border-white/10 hover:bg-white/10' : 'bg-blue-50/50 border-blue-100 hover:bg-blue-50'}`}>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-blue-200 text-blue-600'}`}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-[11px] font-bold truncate ${isTimerRunning ? 'text-white' : 'text-blue-900'}`}>{nome || url}</p>
            <p className={`text-[8px] uppercase font-black tracking-widest mt-0.5 opacity-50 ${isTimerRunning ? 'text-white/40' : 'text-blue-400'}`}>Link</p>
          </div>
        </a>
      );
    }

    if (text.startsWith('CONTACT::')) {
      const parts = text.split('::');
      let contact = '';
      let nome = '';
      if (parts.length >= 3) { nome = parts[1]; contact = parts[2]; }
      else { contact = text.replace('CONTACT::', ''); }
      const num = contact.replace(/\D/g, '');
      const waLink = num.length >= 10 ? `https://wa.me/55${num}` : null;
      return (
        <div className={`group flex items-center gap-2 p-2 rounded-xl border transition-all ${isTimerRunning ? 'bg-white/5 border-white/10' : 'bg-emerald-50/50 border-emerald-100'}`}>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-emerald-200 text-emerald-600'}`}>
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.022-.014-.503-.245-.583-.273-.08-.027-.138-.04-.197.048-.058.088-.227.288-.278.346-.05.058-.1.066-.188.022-.088-.044-.372-.137-.708-.437-.26-.231-.437-.515-.487-.603-.05-.088-.005-.135.039-.179.04-.04.088-.103.131-.154.044-.051.059-.088.088-.146.03-.058.015-.11-.008-.154-.022-.044-.197-.474-.27-.65-.072-.172-.143-.149-.197-.151l-.168-.002c-.058 0-.154.022-.234.11-.08.088-.307.3-.307.732 0 .432.315.849.359.907.044.058.62 1.04 1.502 1.42.21.09.372.143.5.184.21.067.4.057.55.035.168-.024.503-.205.574-.403.072-.198.072-.367.051-.403-.021-.037-.08-.058-.168-.102z" /><path d="M12 2C6.477 2 2 6.477 2 12c0 1.891.524 3.66 1.434 5.168L2 22l4.958-1.412A9.957 9.957 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18a7.96 7.96 0 01-4.07-1.112l-.292-.174-3.024.863.878-2.946-.19-.302A7.957 7.957 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-[11px] font-bold truncate ${isTimerRunning ? 'text-white' : 'text-emerald-900'}`}>{nome || contact}</p>
            <p className={`text-[8px] uppercase font-black tracking-widest mt-0.5 opacity-50 ${isTimerRunning ? 'text-white/40' : 'text-emerald-500'}`}>Contato</p>
          </div>
          {waLink && (
            <a href={waLink} target="_blank" rel="noreferrer" className={`p-1 rounded-lg transition-colors ${isTimerRunning ? 'hover:bg-white/10 text-white' : 'hover:bg-emerald-200 text-emerald-600'}`} title="WhatsApp">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
            </a>
          )}
        </div>
      );
    }

    if (text.startsWith('FILE::')) {
      const parts = text.split('::');
      const nome = parts[1] || 'Arquivo';
      const url = parts[2] || '#';
      return (
        <a href={url} target="_blank" rel="noreferrer" className={`group flex items-center gap-2 p-2 rounded-xl border transition-all ${isTimerRunning ? 'bg-white/5 border-white/10 hover:bg-white/10' : 'bg-amber-50/50 border-amber-100 hover:bg-amber-50'}`}>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${isTimerRunning ? 'bg-white/10 text-white' : 'bg-amber-200 text-amber-600'}`}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-[11px] font-bold truncate ${isTimerRunning ? 'text-white' : 'text-amber-900'}`}>{nome}</p>
            <p className={`text-[8px] uppercase font-black tracking-widest mt-0.5 opacity-50 ${isTimerRunning ? 'text-white/40' : 'text-amber-600'}`}>Anexo</p>
          </div>
        </a>
      );
    }

    return <div className={`text-xs md:text-sm leading-relaxed ${isTimerRunning ? 'text-white/90' : 'text-slate-700'}`}>{formatWhatsAppText(text)}</div>;
  };

  return (
<div className={`flex flex-col h-full relative rounded-none md:rounded-b-2xl ${isTimerRunning ? 'bg-black/20' : 'bg-slate-50'}`}>
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
          .diary-scroll::-webkit-scrollbar-thumb { background: #CBD5E0; border-radius: 99px; }
          .diary-scroll::-webkit-scrollbar-thumb:hover { background: #A0AEC0; }
        `}</style>

        {/* Wrapper interno com padding para afastar os elementos das bordas, sem tirar a barra de rolagem do limite */}
        <div className="px-3 md:px-6 pt-2 pb-2">
          <div className="flex justify-center mb-6">
            <div className={`border rounded-full px-4 py-2 text-[10px] uppercase tracking-widest font-black ${isTimerRunning ? 'bg-white/5 border-white/5 text-white/40' : 'bg-slate-100 border-slate-200 text-slate-400'}`}>
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
                        <span className={`text-[9px] font-black uppercase tracking-[0.2em] px-3 py-1 rounded-full border ${isTimerRunning ? 'bg-white/5 border-white/10 text-white/30' : 'bg-slate-100 border-slate-200 text-slate-400'}`}>
                          {formatLabel(entry.data)}
                        </span>
                      </div>
                    )}
                    <div className="flex flex-col gap-1 items-start animate-in fade-in slide-in-from-bottom-2 duration-300 w-full mb-3">
                    <div className={`p-4 rounded-none md:rounded-2xl md:rounded-tl-none border max-w-full md:max-w-[90%] shadow-lg relative group ${isTimerRunning ? 'bg-[#1A1A1A] border-white/10' : 'bg-white border-slate-100 shadow-slate-200'}`}>
                        {renderDiaryContent(entry.nota)}
                        <div className="flex items-center justify-between mt-2 gap-4">
                          <span className={`text-[9px] font-black uppercase tracking-wider ${isTimerRunning ? 'text-white/30' : 'text-slate-300'}`}>
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
                <div className={`p-4 rounded-2xl rounded-tl-none border max-w-[90%] shadow-lg ${isTimerRunning ? 'bg-[#1A1A1A] border-white/10' : 'bg-white border-slate-100 shadow-slate-200'}`}>
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 rounded-full border-2 border-slate-300 border-t-blue-500 animate-spin"></div>
                    <p className={`text-xs font-bold ${isTimerRunning ? 'text-white/60' : 'text-slate-500'}`}>Enviando arquivos...</p>
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
        {/* Container principal do input - Agora com fundo branco e borda suave */}
        <div className={`rounded-none md:rounded-2xl border shadow-sm transition-all ${isTimerRunning ? 'bg-[#1A1A1A] border-white/10' : 'bg-white border-slate-200'}`}>

          {/* Campo de texto */}
          <div className="px-3 pt-3 pb-1">
            <AutoExpandingTextarea
              id="diary-input"
              value={newFollowUp}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNewFollowUp(e.target.value)}
              onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleAddFollowUp();
                }
              }}
              placeholder="Descreva o que foi feito agora..."
              className={`w-full outline-none text-sm leading-relaxed transition-all min-h-[40px] max-h-[120px] overflow-y-auto resize-none ${isTimerRunning
                ? 'bg-transparent text-white placeholder:text-white/20'
                : 'bg-transparent text-slate-800 placeholder:text-slate-400'
              }`}
            />
          </div>

          {/* Barra de ferramentas */}
          <div className="flex items-center justify-between px-3 pb-2 pt-1">
            {/* Esquerda: Formatação + Anexo */}
            <div className="flex items-center gap-1">
              {/* Botão Anexar */}
              <div className="relative">
                <button
                  onClick={() => setShowAttachMenu(!showAttachMenu)}
                  className={`w-[20px] h-[20px] flex items-center justify-center rounded transition-colors ${isTimerRunning ? 'text-white/30 hover:text-white/70' : 'text-slate-400 hover:text-blue-600'}`}
                  title="Anexar"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
                </button>
                {showAttachMenu && (
                  <div className={`absolute bottom-8 left-0 w-48 rounded-none md:rounded-xl border shadow-xl overflow-hidden animate-in zoom-in-95 origin-bottom-left z-[100] ${isTimerRunning ? 'bg-[#1A1A1A] border-white/10' : 'bg-white border-slate-200'}`}>
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

              {/* Separador */}
              <div className={`w-px h-4 mx-1 ${isTimerRunning ? 'bg-white/10' : 'bg-slate-300'}`}></div>

              {/* Botões de formatação */}
              <button onClick={() => applyFormatting('*')} className={`w-[20px] h-[20px] flex items-center justify-center rounded text-[10px] font-black transition-colors ${isTimerRunning ? 'text-white/30 hover:text-white/70 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-200 hover:text-slate-600'}`}>B</button>
              <button onClick={() => applyFormatting('_')} className={`w-[20px] h-[20px] flex items-center justify-center rounded text-[10px] italic transition-colors ${isTimerRunning ? 'text-white/30 hover:text-white/70 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-200 hover:text-slate-600'}`}>I</button>
              <button onClick={() => applyFormatting('~')} className={`w-[20px] h-[20px] flex items-center justify-center rounded text-[10px] line-through transition-colors ${isTimerRunning ? 'text-white/30 hover:text-white/70 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-200 hover:text-slate-600'}`}>S</button>
              <button onClick={() => applyFormatting('`')} className={`w-[20px] h-[20px] flex items-center justify-center rounded text-[8px] font-mono transition-colors ${isTimerRunning ? 'text-white/30 hover:text-white/70 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-200 hover:text-slate-600'}`}>{'</>'}</button>
            </div>

            {/* Direita: Botão Mic + Botão Enviar */}
            <div className="flex items-center gap-2">
              
              {/* Botão de Gravação de Áudio */}
              <button
                onClick={isRecording ? stopRecording : startRecording}
                disabled={isProcessingTranscription}
                className={`w-8 h-8 flex items-center justify-center rounded-full transition-all active:scale-90 shadow-sm ${
                  isRecording
                    ? 'bg-rose-500 text-white animate-pulse shadow-rose-500/30'
                    : isTimerRunning
                      ? 'bg-white/10 text-white/60 hover:bg-white/20 hover:text-white'
                      : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700'
                }`}
                title={isRecording ? 'Parar Gravação' : 'Gravar Áudio'}
              >
                {isProcessingTranscription ? (
                  <div className="w-4 h-4 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin"></div>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 10v2a7 7 0 01-14 0v-2m14 0h2m-16 0H3m9 10v3m-3 0h6" /></svg>
                )}
              </button>

              {/* Botão Enviar */}
              <button
                onClick={handleAddFollowUp}
                disabled={!newFollowUp.trim()}
                className={`w-8 h-8 flex items-center justify-center rounded-full transition-all active:scale-90 shadow-md ${newFollowUp.trim()
                  ? 'bg-blue-600 text-white hover:bg-blue-500 shadow-blue-600/30'
                  : isTimerRunning ? 'bg-white/10 text-white/20 cursor-not-allowed' : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                }`}
                title="Enviar (Enter)"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Helper text */}
        <p className={`hidden md:block text-[11px] mt-1.5 px-2 ${isTimerRunning ? 'text-white/20' : 'text-slate-400'}`}>
          Enter para enviar · Shift+Enter para nova linha
        </p>
      </div>
    </div>
  );
};