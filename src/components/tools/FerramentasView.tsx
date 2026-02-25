import React, { useState, useRef } from 'react';
import { BrainstormIdea } from '../../types';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../firebase';
import { formatDate } from '../../types';
import { AutoExpandingTextarea } from '../ui/UIComponents';
import { SlidesTool } from './SlidesTool';
import { ShoppingListTool } from './ShoppingListTool';

export const FerramentasView = ({
  ideas,
  onDeleteIdea,
  onArchiveIdea,
  onAddTextIdea,
  onUpdateIdea,
  onConvertToLog,
  onConvertToTask,
  activeTool,
  setActiveTool,
  isAddingText,
  setIsAddingText,
  showToast,
  showAlert
}: {
  ideas: BrainstormIdea[],
  onDeleteIdea: (id: string) => void,
  onArchiveIdea: (id: string) => void,
  onAddTextIdea: (text: string) => void,
  onUpdateIdea: (id: string, text: string) => void,
  onConvertToLog: (idea: BrainstormIdea) => void,
  onConvertToTask: (idea: BrainstormIdea) => void,
  activeTool: 'brainstorming' | 'slides' | 'shopping' | null,
  setActiveTool: (tool: 'brainstorming' | 'slides' | 'shopping' | null) => void,
  isAddingText: boolean,
  setIsAddingText: (val: boolean) => void,
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void,
  showAlert: (title: string, msg: string) => void
}) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [sortOrder, setSortOrder] = useState<'date-desc' | 'date-asc'>('date-desc');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isArchivedIdeasOpen, setIsArchivedIdeasOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  // Gravador
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const activeIdeas = ideas
    .filter(i => i.status !== 'archived')
    .filter(i => i.text.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => {
      if (sortOrder === 'date-desc') return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });

  const archivedIdeas = ideas
    .filter(i => i.status === 'archived')
    .filter(i => i.text.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => {
      if (sortOrder === 'date-desc') return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });

  const toggleCardExpansion = (id: string) => {
    setExpandedCards(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  if (activeTool === 'slides') {
    return <SlidesTool onBack={() => setActiveTool(null)} showToast={showToast} />;
  }

  if (activeTool === 'shopping') {
    return <ShoppingListTool onBack={() => setActiveTool(null)} showToast={showToast} />;
  }

  if (!activeTool) {
    return (
      <div className="animate-in grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 pb-20 px-0">
        <button
          onClick={() => setActiveTool('brainstorming')}
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-200 shadow-none md:shadow-xl hover:shadow-none md:hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 -ml-px -mt-px md:m-0"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-blue-50 rounded-none md:rounded-2xl flex items-center justify-center text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Notas Rápidas</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Registre notas rápidas para organizar depois.</p>
          </div>
        </button>

        <button
          onClick={() => setActiveTool('slides')}
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-200 shadow-none md:shadow-xl hover:shadow-none md:hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 -ml-px -mt-px md:m-0"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-orange-50 rounded-none md:rounded-2xl flex items-center justify-center text-orange-600 group-hover:bg-orange-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Gerador de Slides</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Crie apresentações profissionais com IA de forma rápida.</p>
          </div>
        </button>
        <button
          onClick={() => setActiveTool('shopping')}
          className="bg-white p-6 md:p-12 rounded-none md:rounded-[3rem] border border-slate-200 shadow-none md:shadow-xl hover:shadow-none md:hover:shadow-2xl transition-all group text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 -ml-px -mt-px md:m-0"
        >
          <div className="w-12 h-12 md:w-16 md:h-16 bg-emerald-50 rounded-none md:rounded-2xl flex items-center justify-center text-emerald-600 group-hover:bg-emerald-600 group-hover:text-white transition-all flex-shrink-0">
            <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>
          </div>
          <div>
            <h3 className="text-lg md:text-2xl font-black text-slate-900 tracking-tighter mb-1 md:mb-2">Lista de Compras</h3>
            <p className="text-slate-500 font-medium leading-relaxed text-xs md:text-base">Organize suas compras por estabelecimento e categorias.</p>
          </div>
        </button>


      </div>
    );
  }

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/m4a' }); // ou audio/webm
        await handleProcessAudio(audioBlob);

        // Parar todas as tracks para desligar o ícone de microfone do navegador
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      showAlert("Erro", "Permissão de microfone negada ou não disponível.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsProcessing(true);
    try {
      // Converter Blob para Base64
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];

          // Chamar a Cloud Function
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };

          // Adicionar a ideia transcrita ao banco
          if (data.refined) {
            onAddTextIdea(data.refined);
          }
        } catch (error) {
          console.error("Erro ao transcrever:", error);
          showAlert("Erro", "Erro ao processar áudio via Hermes AI.");
        } finally {
          setIsProcessing(false);
        }
      };
    } catch (error) {
      console.error("Erro ao ler áudio:", error);
      setIsProcessing(false);
    }
  };

  return (
    <>
      <div className="animate-in space-y-12 pb-40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setActiveTool(null)}
              className="p-3 bg-white border border-slate-200 rounded-none md:rounded-2xl text-slate-400 hover:text-slate-900 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <h3 className="text-2xl font-black text-slate-900 tracking-tight uppercase tracking-widest text-[10px]">Ferramentas / Notas Rápidas</h3>
          </div>
        </div>

        <div className="space-y-4 max-w-4xl mx-auto w-full">
          <div className="flex flex-col md:flex-row gap-4 w-full px-0">
            <div className="flex-1 bg-white border border-slate-200 rounded-none md:rounded-xl px-4 py-3 flex items-center gap-3 shadow-none md:shadow-sm focus-within:ring-2 focus-within:ring-blue-100 transition-all">
              <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
              <input
                type="text"
                placeholder="Pesquisar nas notas..."
                className="flex-1 bg-transparent outline-none text-xs md:text-sm font-bold text-slate-700 placeholder:text-slate-400"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>
          </div>

          {/* Inserção de Nova Ideia via Digitação */}
          <div className="w-full animate-in slide-in-from-top-2 duration-500">
            <div className="bg-white p-2 rounded-none md:rounded-[2rem] border-2 border-slate-100 shadow-none md:shadow-xl flex items-center gap-4 focus-within:border-blue-500 transition-all">
              <button
                onClick={isRecording ? stopRecording : startRecording}
                disabled={isProcessing}
                className={`p-4 rounded-none md:rounded-2xl transition-all flex-shrink-0 ${
                  isRecording
                    ? 'bg-rose-600 text-white animate-pulse shadow-lg'
                    : isProcessing
                      ? 'bg-blue-100 text-blue-600 cursor-wait'
                      : 'bg-slate-50 text-slate-400 hover:text-blue-600 hover:bg-blue-50'
                }`}
              >
                {isProcessing ? (
                  // Spinner de Carregamento
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : isRecording ? (
                  // Ícone de Parar (Quadrado)
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
                ) : (
                  // Ícone de Microfone
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                )}
              </button>

              <input
                type="text"
                disabled={isRecording || isProcessing}
                placeholder={
                  isRecording
                    ? "Gravando... Fale agora para transcrever."
                    : isProcessing
                      ? "Hermes AI está processando seu áudio..."
                      : "Digite ou grave uma nova nota..."
                }
                className={`flex-1 bg-transparent border-none outline-none px-2 py-4 text-sm font-bold text-slate-800 placeholder:text-slate-300 ${(isRecording || isProcessing) ? 'opacity-50' : ''}`}
                value={textInput}
                onChange={e => setTextInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && textInput.trim()) {
                    onAddTextIdea(textInput);
                    setTextInput('');
                  }
                }}
              />
              <button
                onClick={() => {
                  if (textInput.trim()) {
                    onAddTextIdea(textInput);
                    setTextInput('');
                  }
                }}
                className="bg-blue-600 text-white h-12 w-12 flex items-center justify-center rounded-lg md:rounded-2xl hover:bg-blue-700 transition-all shadow-lg shadow-blue-100 active:scale-95 shrink-0"
                title="Salvar Nota"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
              </button>
            </div>
          </div>
        </div>

        <div className="flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 mb-32 md:mb-0">
          {activeIdeas.map(idea => (
            <div key={idea.id} className="bg-white p-5 md:p-8 rounded-none md:rounded-[2.5rem] border border-slate-100 md:border-slate-200 shadow-none md:shadow-lg hover:shadow-none md:hover:shadow-2xl transition-all group flex flex-col relative overflow-hidden -ml-px -mt-px md:m-0">
              <div className="flex items-center justify-between mb-3 md:mb-6">
                <span className="text-[9px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest">{formatDate(idea.timestamp.split('T')[0])}</span>
                <div className="flex items-center gap-1 md:gap-2 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all">
                  {editingId === idea.id ? (
                    <button
                      onClick={() => {
                        if (editText.trim()) {
                          onUpdateIdea(idea.id, editText);
                          setEditingId(null);
                        }
                      }}
                      className="text-blue-600 hover:bg-blue-50 p-2 rounded-lg md:rounded-xl transition-colors"
                    >
                      <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => {
                          setEditingId(idea.id);
                          setEditText(idea.text);
                        }}
                        className="text-slate-400 hover:text-blue-600 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Editar"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                      </button>
                      <button
                        onClick={() => onConvertToLog(idea)}
                        className="text-slate-400 hover:text-violet-600 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Converter em Log"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                      </button>
                      <button
                        onClick={() => onConvertToTask(idea)}
                        className="text-slate-400 hover:text-sky-600 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Converter em Ação"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                      </button>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(idea.text).then(() => {
                            setCopiedId(idea.id);
                            setTimeout(() => setCopiedId(null), 2000);
                          });
                        }}
                        className={`p-2 rounded-lg md:rounded-xl transition-colors ${copiedId === idea.id ? 'text-emerald-500 bg-emerald-50' : 'text-slate-400 hover:text-blue-600'}`}
                        title="Copiar Texto"
                      >
                        {copiedId === idea.id ? (
                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                        ) : (
                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                        )}
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => onArchiveIdea(idea.id)}
                    className="text-emerald-500 hover:bg-emerald-50 p-2 rounded-lg md:rounded-xl transition-colors"
                    title="Concluir / Arquivar"
                  >
                    <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                  </button>
                  <button
                    onClick={() => {
                      if (confirmDeleteId === idea.id) {
                        onDeleteIdea(idea.id);
                        setConfirmDeleteId(null);
                      } else {
                        setConfirmDeleteId(idea.id);
                        setTimeout(() => setConfirmDeleteId(null), 3000);
                      }
                    }}
                    className={`p-2 rounded-lg md:rounded-xl transition-colors ${confirmDeleteId === idea.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-300 hover:text-rose-500'}`}
                    title="Excluir Permanentemente"
                  >
                    {confirmDeleteId === idea.id ? (
                      <svg className="w-4 h-4 md:w-5 md:h-5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                    ) : (
                      <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    )}
                  </button>
                </div>
              </div>

              {editingId === idea.id ? (
                <AutoExpandingTextarea
                  autoFocus
                  className="w-full bg-slate-50 border border-slate-200 rounded-none md:rounded-2xl p-4 text-sm md:text-lg font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 min-h-[100px]"
                  value={editText}
                  onChange={e => setEditText(e.target.value)}
                />
              ) : (
                <div className="flex-1">
                  <p
                    className={`text-slate-800 font-bold leading-relaxed mb-3 md:mb-6 text-sm md:text-lg ${!expandedCards.has(idea.id) && idea.text.length > 150 ? 'line-clamp-3' : ''
                      }`}
                  >
                    "{idea.text}"
                  </p>
                  {idea.text.length > 150 && (
                    <button
                      onClick={() => toggleCardExpansion(idea.id)}
                      className="text-blue-600 hover:text-blue-700 text-xs font-black uppercase tracking-widest transition-colors flex items-center gap-1"
                    >
                      {expandedCards.has(idea.id) ? (
                        <>
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 15l7-7 7 7" /></svg>
                          Mostrar menos
                        </>
                      ) : (
                        <>
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                          Mostrar mais
                        </>
                      )}
                    </button>
                  )}
                </div>
              )}

              {idea.audioUrl && (
                <audio controls src={idea.audioUrl} className="w-full h-10 opacity-50 hover:opacity-100 transition-opacity" />
              )}
            </div>
          ))}
          {activeIdeas.length === 0 && !isProcessing && (
            <div className="col-span-full py-20 text-center border-4 border-dashed border-slate-100 rounded-none md:rounded-none md:rounded-[3rem]">
              <p className="text-slate-300 font-black text-xl uppercase tracking-widest">Nenhuma nota ativa</p>
              <p className="text-slate-400 text-sm font-medium mt-2">Grave ou digite uma nota para começar.</p>
            </div>
          )}
        </div>

        {/* Seção Retrátil de Ideias Arquivadas */}
        <div className="mt-12 space-y-6">
          <button
            onClick={() => setIsArchivedIdeasOpen(!isArchivedIdeasOpen)}
            className="w-full flex items-center gap-4 group cursor-pointer"
          >
            <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
            <div className="flex items-center gap-2 text-slate-400 group-hover:text-slate-600 transition-colors">
              <h3 className="text-[10px] font-black uppercase tracking-[0.3em]">Notas Arquivadas</h3>
              <svg className={`w-4 h-4 transition-transform duration-300 ${isArchivedIdeasOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
            <div className="h-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
          </button>

          {isArchivedIdeasOpen && (
            <div className="flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-0 md:gap-8 opacity-60 hover:opacity-100 transition-opacity animate-in slide-in-from-top-4 duration-300">
              {archivedIdeas.map(idea => (
                <div key={idea.id} className="bg-white p-5 md:p-8 rounded-none md:rounded-[2.5rem] border border-slate-100 md:border-slate-200 shadow-none md:shadow-lg hover:shadow-none md:hover:shadow-2xl transition-all group flex flex-col relative overflow-hidden -ml-px -mt-px md:m-0">
                  <div className="flex items-center justify-between mb-3 md:mb-6">
                    <span className="text-[9px] md:text-[10px] font-black text-slate-400 uppercase tracking-widest">{formatDate(idea.timestamp.split('T')[0])}</span>
                    <div className="flex items-center gap-1 md:gap-2 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all">
                      <button
                        onClick={() => onArchiveIdea(idea.id)}
                        className="text-blue-500 hover:bg-blue-50 p-2 rounded-lg md:rounded-xl transition-colors"
                        title="Restaurar Ideia"
                      >
                        <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>
                      </button>
                      <button
                        onClick={() => {
                          if (confirmDeleteId === idea.id) {
                            onDeleteIdea(idea.id);
                            setConfirmDeleteId(null);
                          } else {
                            setConfirmDeleteId(idea.id);
                            setTimeout(() => setConfirmDeleteId(null), 3000);
                          }
                        }}
                        className={`p-2 rounded-lg md:rounded-xl transition-colors ${confirmDeleteId === idea.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-300 hover:text-rose-500'}`}
                        title="Excluir Permanentemente"
                      >
                        {confirmDeleteId === idea.id ? (
                          <svg className="w-4 h-4 md:w-5 md:h-5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                        ) : (
                          <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        )}
                      </button>
                    </div>
                  </div>

                  <div className="flex-1">
                    <p className="text-slate-500 font-bold italic leading-relaxed mb-3 md:mb-6 text-sm md:text-lg line-clamp-3">
                      "{idea.text}"
                    </p>
                  </div>
                </div>
              ))}
              {archivedIdeas.length === 0 && (
                <div className="col-span-full py-12 text-center">
                  <p className="text-slate-300 font-black text-[10px] uppercase tracking-widest italic">Nenhuma nota arquivada</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Input Flutuante Centralizado */}
      {isAddingText && (
        <div className="fixed bottom-24 left-4 right-4 md:left-1/2 md:-translate-x-1/2 w-auto md:w-full md:max-w-2xl z-[110] flex items-center gap-2 animate-in zoom-in-95 slide-in-from-bottom-10 bg-white/90 backdrop-blur-md p-4 rounded-none md:rounded-[2rem] shadow-2xl border border-slate-200">
          <button
            onClick={isRecording ? stopRecording : startRecording}
            className={`p-4 rounded-none md:rounded-2xl transition-all shadow-xl flex-shrink-0 ${
              isRecording
                ? 'bg-rose-600 text-white animate-pulse shadow-rose-200'
                : 'bg-white text-slate-400 hover:text-blue-600 border border-slate-200'
            }`}
          >
            {isRecording ? (
              // Ícone de Parar (Quadrado)
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
            ) : (
              // Ícone de Microfone
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
            )}
          </button>

          <input
            type="text"
            disabled={isRecording}
            autoFocus
            placeholder={isRecording ? "Gravando... Fale agora." : "Digite ou grave sua nota..."}
            className={`flex-1 bg-white border border-slate-200 rounded-none md:rounded-2xl px-6 py-4 text-sm font-medium focus:ring-4 focus:ring-blue-100 outline-none shadow-sm transition-all ${isRecording ? 'opacity-50' : ''}`}
            value={textInput}
            onChange={e => setTextInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && textInput.trim()) {
                onAddTextIdea(textInput);
                setTextInput('');
                setIsAddingText(false);
              }
            }}
          />
          <button
            onClick={() => {
              if (textInput.trim()) {
                onAddTextIdea(textInput);
                setTextInput('');
                setIsAddingText(false);
              } else {
                setIsAddingText(false);
              }
            }}
            className="bg-blue-600 text-white p-4 rounded-none md:rounded-2xl hover:bg-blue-700 transition-all shadow-xl shadow-blue-100 flex-shrink-0"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
          </button>
        </div>
      )}

    </>
  );
};
