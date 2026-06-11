import React, { useState, useRef } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '@/firebase';
import { BrainstormIdea, formatDate, ConhecimentoItem } from '@/types';
import { AutoExpandingTextarea } from '../ui/UIComponents';
import { ShoppingListTool } from './ShoppingListTool';
import { TranscriptionTool } from './TranscriptionTool';
import { MeetingTranscriptionTool } from './MeetingTranscriptionTool';
import { PopManagerTool } from './PopManagerTool';
import { SipacTrackingTool } from './SipacTrackingTool';
import { LongTranscriptionTool } from './LongTranscriptionTool';

type FerramentaAtiva = 'brainstorming' | 'shopping' | 'transcription' | 'meeting_transcription' | 'pop_manager' | 'whatsapp_assistant' | 'sipac_tracking' | 'long_transcription' | null;

interface FerramentasViewProps {
  ideas: BrainstormIdea[];
  onDeleteIdea: (id: string) => void;
  onArchiveIdea: (id: string) => void;
  onAddTextIdea: (text: string) => void;
  onUpdateIdea: (id: string, text: string) => void;
  onConvertToTask: (idea: BrainstormIdea) => void;
  activeTool: FerramentaAtiva;
  setActiveTool: (tool: FerramentaAtiva) => void;
  isAddingText: boolean;
  setIsAddingText: (val: boolean) => void;
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
  showAlert: (title: string, msg: string) => void;
  knowledgeItems: ConhecimentoItem[];
  onUploadFile: (file: File) => Promise<ConhecimentoItem | null>;
  initialDraftId?: string;
  pendingSharedAudioFile?: File | null;
  onPendingSharedAudioFileConsumed?: () => void;
  pendingSharedVideoFile?: File | null;
  onPendingSharedVideoFileConsumed?: () => void;
  isDark?: boolean;
}

export const FerramentasView: React.FC<FerramentasViewProps> = ({
  ideas,
  onDeleteIdea,
  onArchiveIdea,
  onAddTextIdea,
  onUpdateIdea,
  onConvertToTask,
  activeTool,
  setActiveTool,
  isAddingText,
  setIsAddingText,
  showToast,
  showAlert,
  knowledgeItems,
  onUploadFile,
  initialDraftId,
  pendingSharedAudioFile,
  onPendingSharedAudioFileConsumed,
  pendingSharedVideoFile,
  onPendingSharedVideoFileConsumed,
  isDark = false,
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
  const streamRef = useRef<MediaStream | null>(null);

  // Cleanup on unmount
  React.useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
    };
  }, []);

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
      if (newSet.has(id)) newSet.delete(id);
      else newSet.add(id);
      return newSet;
    });
  };

  if (activeTool === 'shopping') {
    return <ShoppingListTool onBack={() => setActiveTool(null)} showToast={showToast} />;
  }

  if (activeTool === 'transcription') {
    return <TranscriptionTool onBack={() => setActiveTool(null)} showToast={showToast} initialFile={pendingSharedAudioFile} onInitialFileConsumed={onPendingSharedAudioFileConsumed} />;
  }



  if (activeTool === 'meeting_transcription') {
    return <MeetingTranscriptionTool onBack={() => setActiveTool(null)} showToast={showToast} />;
  }



  if (activeTool === 'sipac_tracking') {
    return <SipacTrackingTool onBack={() => setActiveTool(null)} isDark={isDark} />;
  }

  if (activeTool === 'long_transcription') {
    return <LongTranscriptionTool onBack={() => setActiveTool(null)} showToast={showToast} isDark={isDark} />;
  }

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (event) => { if (event.data.size > 0) audioChunksRef.current.push(event.data); };
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/m4a' });
        // Stop hardware immediately
        if (stream) stream.getTracks().forEach(track => track.stop());
        streamRef.current = null;
        await handleProcessAudio(audioBlob);
      };
      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Erro ao acessar microfone:", err);
      showAlert("Erro", "Permissão de microfone negada ou não disponÃ­vel.");
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
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String });
          const data = response.data as { raw: string, refined: string };
          if (data.refined) onAddTextIdea(data.refined);
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

  if (activeTool === 'pop_manager') {
    return <PopManagerTool onBack={() => setActiveTool(null)} isDark={isDark} />;
  }

  if (!activeTool) {
    const toolsList: {
      id: FerramentaAtiva;
      code: string;
      title: string;
      desc: string;
      dotColor: string;
      iconClasses: string;
      lineColor: string;
      icon: React.ReactNode;
    }[] = [
      {
        id: 'brainstorming',
        code: 'ID-001',
        title: 'Brainstorming',
        desc: 'Capture e organize ideias rápidas com IA.',
        dotColor: 'bg-blue-500',
        iconClasses: isDark ? 'text-blue-400 group-hover:bg-blue-600' : 'text-blue-600 group-hover:bg-blue-600',
        lineColor: 'group-hover:bg-blue-500',
        icon: <svg className="w-6 h-6 md:w-7 md:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
      },

      {
        id: 'shopping',
        code: 'ID-003',
        title: 'Lista de Compras',
        desc: 'Organize suas compras com sugestões de IA.',
        dotColor: 'bg-emerald-500',
        iconClasses: isDark ? 'text-emerald-400 group-hover:bg-emerald-600' : 'text-emerald-600 group-hover:bg-emerald-600',
        lineColor: 'group-hover:bg-emerald-500',
        icon: <svg className="w-6 h-6 md:w-7 md:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
      },
      {
        id: 'transcription',
        code: 'ID-004',
        title: 'Transcrição de Áudio',
        desc: 'Transcreva e refine áudios do WhatsApp e outros.',
        dotColor: 'bg-purple-500',
        iconClasses: isDark ? 'text-purple-400 group-hover:bg-purple-600' : 'text-purple-600 group-hover:bg-purple-600',
        lineColor: 'group-hover:bg-purple-500',
        icon: <svg className="w-6 h-6 md:w-7 md:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
      },

      {
        id: 'meeting_transcription',
        code: 'ID-006',
        title: 'Reuniões em Tempo Real',
        desc: 'Transcreva com áudio duplo e chat IA.',
        dotColor: 'bg-indigo-500',
        iconClasses: isDark ? 'text-indigo-400 group-hover:bg-indigo-600' : 'text-indigo-600 group-hover:bg-indigo-600',
        lineColor: 'group-hover:bg-indigo-500',
        icon: <svg className="w-6 h-6 md:w-7 md:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" /></svg>
      },
      {
        id: 'pop_manager',
        code: 'ID-007',
        title: 'Gestor de POPs',
        desc: 'Procedimentos Operacionais Padrão do Hermes.',
        dotColor: 'bg-blue-500',
        iconClasses: isDark ? 'text-blue-400 group-hover:bg-blue-600' : 'text-blue-600 group-hover:bg-blue-600',
        lineColor: 'group-hover:bg-blue-500',
        icon: <svg className="w-6 h-6 md:w-7 md:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
      },
      {
        id: 'sipac_tracking',
        code: 'ID-008',
        title: 'Acompanhamento SIPAC',
        desc: 'Consulte processos públicos, andamentos e documentos anexos.',
        dotColor: 'bg-emerald-500',
        iconClasses: isDark ? 'text-emerald-400 group-hover:bg-emerald-600' : 'text-emerald-600 group-hover:bg-emerald-600',
        lineColor: 'group-hover:bg-emerald-500',
        icon: <svg className="w-6 h-6 md:w-7 md:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
      },
      {
        id: 'long_transcription',
        code: 'ID-009',
        title: 'Transcrições Longas',
        desc: 'Envie áudios e vídeos pesados de qualquer tamanho e receba a transcrição bruta.',
        dotColor: 'bg-purple-500',
        iconClasses: isDark ? 'text-purple-400 group-hover:bg-purple-600' : 'text-purple-600 group-hover:bg-purple-600',
        lineColor: 'group-hover:bg-purple-500',
        icon: <svg className="w-6 h-6 md:w-7 md:h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0-4a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
      }
    ];

    const toolCardClass = `group relative p-6 md:p-8 rounded-none border transition-all text-left flex flex-row md:flex-col items-center md:items-start gap-4 md:gap-6 overflow-hidden ${isDark ? 'bg-slate-900 border-slate-800 hover:border-blue-500/60 shadow-lg hover:bg-slate-800/50' : 'bg-white border-slate-200 hover:border-blue-400'}`;

    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-in fade-in zoom-in-95 duration-500">
        {toolsList.map(t => (
          <button key={t.code} onClick={() => setActiveTool(t.id)} className={toolCardClass}>
            <div className="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-30 transition-opacity">
              <span className={`text-[10px] font-mono font-bold tracking-widest uppercase ${isDark ? 'text-slate-400' : ''}`}>{t.code}</span>
            </div>
            <div className={`w-12 h-12 md:w-14 md:h-14 rounded-none border flex items-center justify-center group-hover:text-white transition-all flex-shrink-0 ${t.iconClasses} ${isDark ? 'bg-slate-800 border-slate-700' : 'bg-slate-50 border-slate-100'}`}>
              {t.icon}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-1.5 h-1.5 ${t.dotColor} rounded-none`}></div>
                <h3 className={`text-sm md:text-base font-mono font-black uppercase tracking-tight ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{t.title}</h3>
              </div>
              <p className={`font-medium leading-snug text-[11px] md:text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>{t.desc}</p>
            </div>
            <div className={`absolute bottom-0 left-0 w-full h-1 bg-transparent ${t.lineColor} transition-all`}></div>
          </button>
        ))}
      </div>
    );
  }

  return (
    <>
      <div className="animate-in space-y-12 pb-40">
        <div className={`flex flex-col md:flex-row md:items-center justify-between gap-6 border-b pb-6 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setActiveTool(null)}
              className={`p-3 border rounded-none transition-colors ${isDark ? 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-100' : 'bg-white border-slate-200 text-slate-400 hover:text-slate-900'}`}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <div>
              <p className="text-[10px] font-mono font-black text-blue-500 uppercase tracking-widest mb-1">MODULE: BRAINSTORMING</p>
              <h3 className={`text-xl font-mono font-black uppercase tracking-tight ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Ferramentas / Notas Rápidas</h3>
            </div>
          </div>
        </div>

        <div className="space-y-4 max-w-4xl mx-auto w-full">
          <div className="flex flex-col md:flex-row gap-4 w-full px-0">
            <div className={`flex-1 border rounded-none px-4 py-2 flex items-center gap-3 transition-all ${isDark ? 'bg-slate-900 border-slate-800 focus-within:border-blue-500' : 'bg-white border-slate-200 focus-within:border-blue-400'}`}>
              <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
              <input
                type="text"
                placeholder="Pesquisar nas notas..."
                className={`flex-1 bg-transparent outline-none text-xs font-mono font-bold ${isDark ? 'text-slate-200 placeholder:text-slate-500' : 'text-slate-700 placeholder:text-slate-400'}`}
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>
          </div>

          <div className="w-full animate-in slide-in-from-top-2 duration-500">
            <div className={`p-1 rounded-none border flex items-center gap-2 transition-all ${isDark ? 'bg-slate-900 border-slate-800 focus-within:border-blue-500' : 'bg-white border-slate-200 focus-within:border-blue-500'}`}>
              <button
                onClick={isRecording ? stopRecording : startRecording}
                disabled={isProcessing}
                className={`p-3 rounded-none transition-all flex-shrink-0 ${isRecording
                  ? 'bg-rose-600 text-white animate-pulse shadow-lg'
                  : isProcessing
                    ? 'bg-blue-100 text-blue-600 cursor-wait'
                    : isDark
                      ? 'bg-slate-800 text-slate-400 hover:text-blue-400 hover:bg-slate-700'
                      : 'bg-slate-50 text-slate-400 hover:text-blue-600 hover:bg-blue-50'
                  }`}
              >
                {isProcessing ? (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : isRecording ? (
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                )}
              </button>

              <input
                type="text"
                disabled={isRecording || isProcessing}
                placeholder={isRecording ? "Gravando... Fale agora." : isProcessing ? "Hermes AI está processando áudio..." : "Digite ou grave uma nova nota..."}
                className={`flex-1 bg-transparent border-none outline-none px-2 py-3 text-[13px] font-mono font-bold ${isDark ? 'text-slate-100 placeholder:text-slate-500' : 'text-slate-800 placeholder:text-slate-300'} ${(isRecording || isProcessing) ? 'opacity-50' : ''}`}
                value={textInput}
                onChange={e => setTextInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && textInput.trim()) { onAddTextIdea(textInput); setTextInput(''); } }}
              />
              <button
                onClick={() => { if (textInput.trim()) { onAddTextIdea(textInput); setTextInput(''); } }}
                className="bg-blue-600 text-white h-10 px-4 flex items-center justify-center rounded-none hover:bg-blue-700 transition-all active:scale-95 shrink-0 font-mono text-[10px] font-black uppercase tracking-widest"
              >
                Salvar
              </button>
            </div>
          </div>

          <div className={`flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-0 mb-32 md:mb-0 border-l border-t ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
            {activeIdeas.map(idea => (
              <div key={idea.id} className={`p-5 md:p-6 rounded-none border-r border-b transition-all group flex flex-col relative overflow-hidden -ml-px -mt-px md:m-0 ${isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-800/50' : 'bg-white border-slate-200 hover:bg-slate-50'}`}>
                <div className="flex items-center justify-between mb-4">
                  <span className="text-[9px] font-mono font-black text-slate-400 uppercase tracking-widest">{formatDate(idea.timestamp.split('T')[0])}</span>
                  <div className="flex items-center gap-1 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all">
                    {editingId === idea.id ? (
                      <button onClick={() => { if (editText.trim()) { onUpdateIdea(idea.id, editText); setEditingId(null); } }} className="text-blue-600 hover:bg-blue-50 p-1.5 rounded-none transition-colors">
                        <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                      </button>
                    ) : (
                      <>
                        <button onClick={() => { setEditingId(idea.id); setEditText(idea.text); }} className="text-slate-300 hover:text-blue-600 p-1.5 rounded-none transition-colors" title="Editar"><svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg></button>
                        <button onClick={() => onConvertToTask(idea)} className="text-slate-300 hover:text-sky-600 p-1.5 rounded-none transition-colors" title="Converter em Ação"><svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 002 2h2a2 2 0 012-2h2a2 2 0 012 2" /></svg></button>
                        <button onClick={() => { navigator.clipboard.writeText(idea.text).then(() => { setCopiedId(idea.id); setTimeout(() => setCopiedId(null), 2000); }); }} className={`p-1.5 rounded-none transition-colors ${copiedId === idea.id ? 'text-emerald-500 bg-emerald-50' : 'text-slate-300 hover:text-blue-600'}`}>{copiedId === idea.id ? <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg> : <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>}</button>
                      </>
                    )}
                    <button onClick={() => onArchiveIdea(idea.id)} className="text-emerald-500 hover:bg-emerald-50 p-1.5 rounded-none transition-colors"><svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg></button>
                    <button onClick={() => { if (confirmDeleteId === idea.id) { onDeleteIdea(idea.id); setConfirmDeleteId(null); } else { setConfirmDeleteId(idea.id); setTimeout(() => setConfirmDeleteId(null), 3000); } }} className={`p-1.5 rounded-none transition-colors ${confirmDeleteId === idea.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-200 hover:text-rose-500'}`}>{confirmDeleteId === idea.id ? <svg className="w-3.5 h-3.5 md:w-4 md:h-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>}</button>
                  </div>
                </div>

                {editingId === idea.id ? (
                  <AutoExpandingTextarea autoFocus className={`w-full border rounded-none p-4 text-[13px] font-mono font-bold outline-none focus:ring-1 focus:ring-blue-500 min-h-[100px] ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100' : 'bg-slate-50 border-slate-200 text-slate-800'}`} value={editText} onChange={e => setEditText(e.target.value)} />
                ) : (
                  <div className="flex-1">
                    <p className={`font-mono font-bold leading-relaxed mb-4 text-[13px] ${isDark ? 'text-slate-200' : 'text-slate-800'} ${!expandedCards.has(idea.id) && idea.text.length > 150 ? 'line-clamp-3' : ''}`}>{idea.text}</p>
                    {idea.text.length > 150 && (
                      <button onClick={() => toggleCardExpansion(idea.id)} className="text-blue-600 hover:text-blue-700 text-[10px] font-mono font-black uppercase tracking-widest transition-colors flex items-center gap-1">
                        {expandedCards.has(idea.id) ? (
                          <>
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 15l7-7 7 7" /></svg>
                            Recolher
                          </>
                        ) : (
                          <>
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" /></svg>
                            Expandir
                          </>
                        )}
                      </button>
                    )}
                  </div>
                )}
                {idea.audioUrl && (
                  <div className={`mt-4 pt-4 border-t ${isDark ? 'border-slate-800' : 'border-slate-100'}`}>
                    <audio controls src={idea.audioUrl} className="w-full h-8 opacity-50 hover:opacity-100 transition-opacity" />
                  </div>
                )}
              </div>
            ))}
            {activeIdeas.length === 0 && !isProcessing && (
              <div className={`col-span-full py-16 text-center border border-dashed rounded-none ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                <p className="text-slate-300 font-mono font-black text-xs uppercase tracking-[0.2em]">SISTEMA: VAZIO</p>
                <p className="text-slate-400 text-[11px] font-medium mt-1 font-mono">Nenhuma entrada detectada no banco de dados.</p>
              </div>
            )}
          </div>
        </div>

        <div className="mt-12 space-y-6">
          <button onClick={() => setIsArchivedIdeasOpen(!isArchivedIdeasOpen)} className="w-full flex items-center gap-4 group cursor-pointer">
            <div className={`h-px flex-1 transition-colors ${isDark ? 'bg-slate-800' : 'bg-slate-200'}`}></div>
            <div className="flex items-center gap-2 text-slate-400 group-hover:text-slate-600 transition-colors">
              <h3 className="text-[10px] font-mono font-black uppercase tracking-[0.3em]">Arquivadas</h3>
              <svg className={`w-3 h-3 transition-transform duration-300 ${isArchivedIdeasOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>
            </div>
            <div className={`h-px flex-1 transition-colors ${isDark ? 'bg-slate-800' : 'bg-slate-200'}`}></div>
          </button>

          {isArchivedIdeasOpen && (
            <div className={`flex flex-col md:grid md:grid-cols-2 lg:grid-cols-3 gap-0 opacity-60 hover:opacity-100 transition-opacity animate-in slide-in-from-top-4 duration-300 border-l border-t ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              {archivedIdeas.map(idea => (
                <div key={idea.id} className={`p-5 md:p-6 rounded-none border-r border-b transition-all group flex flex-col relative overflow-hidden -ml-px -mt-px md:m-0 ${isDark ? 'bg-slate-900/50 border-slate-800' : 'bg-slate-50/50 border-slate-200'}`}>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[9px] font-mono font-black text-slate-400 uppercase tracking-widest">{formatDate(idea.timestamp.split('T')[0])}</span>
                    <div className="flex items-center gap-1 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all">
                      <button onClick={() => onArchiveIdea(idea.id)} className="text-blue-500 hover:bg-blue-50 p-1.5 rounded-none transition-colors" title="Restaurar"><svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg></button>
                      <button onClick={() => { if (confirmDeleteId === idea.id) { onDeleteIdea(idea.id); setConfirmDeleteId(null); } else { setConfirmDeleteId(idea.id); setTimeout(() => setConfirmDeleteId(null), 3000); } }} className={`p-1.5 rounded-none transition-colors ${confirmDeleteId === idea.id ? 'bg-rose-500 text-white shadow-md' : 'text-slate-300 hover:text-rose-500'}`}>{confirmDeleteId === idea.id ? <svg className="w-3.5 h-3.5 md:w-4 md:h-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg> : <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>}</button>
                    </div>
                  </div>
                  <div className="flex-1">
                    <p className={`font-mono italic leading-relaxed mb-4 text-[13px] line-clamp-3 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>"{idea.text}"</p>
                  </div>
                </div>
              ))}
              {archivedIdeas.length === 0 && (
                <div className={`col-span-full py-12 text-center border-r border-b ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                  <p className="text-slate-300 font-mono font-black text-[10px] uppercase tracking-widest italic">Vazio</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {isAddingText && (
        <div className={`fixed bottom-24 left-4 right-4 md:left-1/2 md:-translate-x-1/2 w-auto md:w-full md:max-w-2xl z-[110] flex items-center gap-2 animate-in zoom-in-95 slide-in-from-bottom-10 p-3 rounded-none shadow-2xl border ${isDark ? 'bg-slate-900 border-slate-800 shadow-black/60' : 'bg-white border-slate-200'}`}>
          <button onClick={isRecording ? stopRecording : startRecording} className={`p-4 rounded-none transition-all shadow-xl flex-shrink-0 border ${isRecording ? 'bg-rose-600 text-white animate-pulse shadow-rose-200' : isDark ? 'bg-slate-800 border-slate-700 text-slate-400 hover:text-blue-400' : 'bg-slate-50 border-slate-200 text-slate-400 hover:text-blue-600'}`}>
            {isRecording ? <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg> : <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>}
          </button>
          <input type="text" disabled={isRecording} autoFocus placeholder={isRecording ? "Gravando... Fale agora." : "Digite ou grave sua nota..."} className={`flex-1 border rounded-none px-6 py-4 text-sm font-mono font-bold outline-none transition-all ${isDark ? 'bg-slate-800 border-slate-700 text-slate-100 focus:border-blue-500 placeholder:text-slate-500' : 'bg-slate-50 border-slate-200 text-slate-800 focus:border-blue-400'} ${isRecording ? 'opacity-50' : ''}`} value={textInput} onChange={e => setTextInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && textInput.trim()) { onAddTextIdea(textInput); setTextInput(''); setEditingId(null); } }} />
          <button onClick={() => { if (textInput.trim()) { onAddTextIdea(textInput); setTextInput(''); setIsAddingText(false); } else { setIsAddingText(false); } }} className="bg-blue-600 text-white px-6 h-14 rounded-none hover:bg-blue-700 transition-all flex-shrink-0 font-mono text-[10px] font-black uppercase tracking-widest">
            Confirmar
          </button>
        </div>
      )}
    </>
  );
};

