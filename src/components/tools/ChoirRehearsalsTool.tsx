import React, { useState, useEffect } from 'react';
import { collection, addDoc, updateDoc, deleteDoc, doc, onSnapshot, query, orderBy, getDoc } from 'firebase/firestore';
import { db } from '@/firebase';
import { ConhecimentoItem } from '@/types';

export interface Musica {
  id: string;
  titulo: string;
  tags: string[];
  arquivos: {
    id: string;
    titulo: string;
    url_drive: string;
    tipo: 'audio' | 'video' | 'partitura' | 'outro';
  }[];
  observacoes?: string;
  data_criacao: string;
}

export const ChoirRehearsalsTool: React.FC<{ 
  onBack: () => void; 
  showToast: (m: string, t: 'success' | 'error' | 'info') => void;
  knowledgeItems?: ConhecimentoItem[];
  onUploadFile?: (file: File) => Promise<ConhecimentoItem | null>;
}> = ({ onBack, showToast, knowledgeItems = [], onUploadFile }) => {
  const [musicas, setMusicas] = useState<Musica[]>([]);
  const [selectedMusica, setSelectedMusica] = useState<Musica | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isAttachmentModalOpen, setIsAttachmentModalOpen] = useState(false);
  const [searchTermKB, setSearchTermKB] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  
  const [sharedVideoWizard, setSharedVideoWizard] = useState<'options' | 'pick_music' | null>(null);
  const [incomingSharedFile, setIncomingSharedFile] = useState<File | null>(null);

  // Form state
  const [titulo, setTitulo] = useState('');
  const [tagInput, setTagInput] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [observacoes, setObservacoes] = useState('');

  // Recebe via Share Intent Global Event
  useEffect(() => {
    const handleSharedVideo = (e: any) => {
      if (e.detail && e.detail instanceof File) {
        setIncomingSharedFile(e.detail);
        setSharedVideoWizard('options');
      }
    };
    window.addEventListener('hermes-shared-video', handleSharedVideo);
    return () => window.removeEventListener('hermes-shared-video', handleSharedVideo);
  }, []);

  const handleProcessSharedVideo = async (musicId: string) => {
    if (!incomingSharedFile || !onUploadFile) return showToast("Upload indisponível", "error");
    setIsUploading(true);
    setSharedVideoWizard(null);
    try {
      const newItem = await onUploadFile(incomingSharedFile);
      if (newItem) {
        const mappedTipo = 'video';
        const newArquivo = {
          id: newItem.id,
          titulo: newItem.titulo,
          url_drive: newItem.url_drive,
          tipo: mappedTipo as 'video'
        };
        const docSnap = await getDoc(doc(db, 'musicas', musicId));
        if(docSnap.exists()) {
            const currArquivos = docSnap.data().arquivos || [];
            await updateDoc(doc(db, 'musicas', musicId), {
                arquivos: [...currArquivos, newArquivo]
            });
            showToast("Vídeo recebido anexado com sucesso!", "success");
            const updatedDoc = await getDoc(doc(db, 'musicas', musicId));
            if (updatedDoc.exists()) setSelectedMusica({ id: updatedDoc.id, ...updatedDoc.data() } as Musica);
        }
      }
    } catch (e) {
      showToast("Erro ao anexar vídeo recebido", "error");
    } finally {
      setIsUploading(false);
      setIncomingSharedFile(null);
    }
  };

  useEffect(() => {
    const q = query(collection(db, 'musicas'), orderBy('data_criacao', 'desc'));
    const unsub = onSnapshot(q, (snapshot) => {
      setMusicas(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Musica)));
    });
    return () => unsub();
  }, []);

  const handleSave = async () => {
    if (!titulo.trim()) return showToast("O título é obrigatório", "error");
    try {
      let finalId = selectedMusica?.id;
      if (selectedMusica) {
        await updateDoc(doc(db, 'musicas', selectedMusica.id), {
          titulo, tags, observacoes
        });
        showToast("Música atualizada!", "success");
      } else {
        const docRef = await addDoc(collection(db, 'musicas'), {
          titulo, tags, observacoes, arquivos: [], data_criacao: new Date().toISOString()
        });
        finalId = docRef.id;
        showToast("Música criada com sucesso!", "success");
      }
      setIsModalOpen(false);

      if (incomingSharedFile && finalId) {
        handleProcessSharedVideo(finalId);
      }
    } catch (e) {
      showToast("Erro ao salvar", "error");
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("Deseja deletar esta música?")) return;
    try {
      await deleteDoc(doc(db, 'musicas', id));
      showToast("Música apagada", "info");
      if (selectedMusica?.id === id) setSelectedMusica(null);
    } catch (e) {
      showToast("Erro ao deletar", "error");
    }
  };

  const currentViewItem = selectedMusica ? musicas.find(m => m.id === selectedMusica.id) : null;

  const handleAttachItem = async (kbItem: ConhecimentoItem) => {
    if (!currentViewItem) return;
    const tipoMap: Record<string, string> = {
      'pdf': 'partitura', 'audio': 'audio', 'mp3': 'audio', 'wav': 'audio', 'm4a': 'audio', 'video': 'video', 'mp4': 'video', 'imagem': 'outro', 'link': 'outro'
    };
    const mappedTipo = (kbItem.tipo_arquivo && tipoMap[kbItem.tipo_arquivo]) ? tipoMap[kbItem.tipo_arquivo] : 'outro';
    
    const newArquivo = {
      id: kbItem.id,
      titulo: kbItem.titulo,
      url_drive: kbItem.url_drive,
      tipo: mappedTipo as 'audio' | 'video' | 'partitura' | 'outro'
    };
    
    // Prevent duplicate attach
    if (currentViewItem.arquivos?.some(a => a.id === kbItem.id)) {
      showToast('Arquivo já anexado a esta música.', 'info');
      return;
    }

    try {
      await updateDoc(doc(db, 'musicas', currentViewItem.id), {
        arquivos: [...(currentViewItem.arquivos || []), newArquivo]
      });
      showToast('Arquivo anexado com sucesso!', 'success');
      setIsAttachmentModalOpen(false);
    } catch (e) {
      showToast('Erro ao anexar arquivo', 'error');
    }
  };

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-8 pb-32">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-6">
          <button onClick={onBack} className="w-12 h-12 bg-white rounded-2xl flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-900 transition-all shadow-sm">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
          </button>
          <div className="flex-1">
            <h2 className="text-3xl font-black text-slate-900 tracking-tighter">Ensaios do Coral</h2>
            <p className="text-slate-500 font-medium">Repertório, tags e multimédia</p>
          </div>
        </div>
        <button onClick={() => { setSelectedMusica(null); setTitulo(''); setTags([]); setObservacoes(''); setIsModalOpen(true); }} className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-2xl font-black text-[10px] uppercase tracking-widest shadow-lg transition-colors flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4"/></svg>
            Nova Música
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* List */}
        <div className="bg-white p-6 rounded-[2.5rem] border border-slate-200 shadow-sm h-[600px] flex flex-col">
          <h3 className="text-lg font-black text-slate-900 mb-4 px-2">Repertório</h3>
          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2 pr-2">
             {musicas.map(m => (
               <div key={m.id} onClick={() => setSelectedMusica(m)} className={`p-4 rounded-2xl border transition-all cursor-pointer ${selectedMusica?.id === m.id ? 'border-blue-500 bg-blue-50 shadow-md' : 'border-slate-100 bg-white hover:border-blue-200 hover:shadow-sm'}`}>
                 <h4 className="font-bold text-slate-900">{m.titulo}</h4>
                 <div className="flex flex-wrap gap-1 mt-2">
                   {m.tags.slice(0,3).map(t => (
                     <span key={t} className="px-2 py-0.5 bg-slate-100 text-slate-500 rounded-md text-[9px] font-bold uppercase tracking-wider">{t}</span>
                   ))}
                   {m.tags.length > 3 && <span className="px-2 py-0.5 bg-slate-100 text-slate-500 rounded-md text-[9px] font-bold uppercase tracking-wider">+{m.tags.length - 3}</span>}
                 </div>
               </div>
             ))}
             {musicas.length === 0 && (
                 <p className="text-slate-400 text-center py-10 text-sm font-bold">Nenhuma música cadastrada.</p>
             )}
          </div>
        </div>

        {/* Details View */}
        <div className="lg:col-span-2">
           {currentViewItem ? (
             <div className="bg-white p-8 rounded-[2.5rem] border border-slate-200 shadow-xl space-y-8 h-[600px] flex flex-col">
               <div className="flex items-start justify-between">
                 <div>
                   <h3 className="text-3xl font-black text-slate-900">{currentViewItem.titulo}</h3>
                   <div className="flex flex-wrap gap-2 mt-3">
                     {currentViewItem.tags.map(t => (
                       <span key={t} className="px-3 py-1 bg-blue-50 text-blue-600 rounded-lg text-[10px] font-black uppercase tracking-widest">{t}</span>
                     ))}
                   </div>
                 </div>
                 <div className="flex gap-2">
                   <button onClick={() => {
                       setSelectedMusica(currentViewItem);
                       setTitulo(currentViewItem.titulo);
                       setTags(currentViewItem.tags);
                       setObservacoes(currentViewItem.observacoes || '');
                       setIsModalOpen(true);
                   }} className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl transition-all">
                       <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                   </button>
                   <button onClick={() => handleDelete(currentViewItem.id)} className="p-2 bg-rose-50 hover:bg-rose-100 text-rose-600 rounded-xl transition-all">
                       <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                   </button>
                 </div>
               </div>

               <div className="flex-1 overflow-y-auto custom-scrollbar pr-2 space-y-8">
                 {currentViewItem.observacoes && (
                     <div>
                         <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Observações / Letra</h4>
                         <p className="text-slate-700 whitespace-pre-wrap leading-relaxed">{currentViewItem.observacoes}</p>
                     </div>
                 )}

                 <div>
                     <div className="flex items-center justify-between mb-4">
                         <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400">Arquivos e Multimídia</h4>
                         <button onClick={() => setIsAttachmentModalOpen(true)} className="text-[10px] font-black uppercase tracking-widest text-blue-600 hover:underline flex items-center gap-1">
                             <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" /></svg>
                             Anexar Arquivo
                         </button>
                     </div>
                     
                     <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                         {currentViewItem.arquivos?.map(arquivo => (
                             <div key={arquivo.id} className="p-4 rounded-2xl bg-slate-50 border border-slate-100 flex gap-3 block hover:border-blue-300 transition-colors">
                                 <div className="w-10 h-10 bg-white rounded-xl shadow-sm flex items-center justify-center shrink-0">
                                     {arquivo.tipo === 'audio' ? <svg className="w-5 h-5 text-purple-500" fill="currentColor" viewBox="0 0 24 24"><path d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg> : <svg className="w-5 h-5 text-emerald-500" fill="currentColor" viewBox="0 0 24 24"><path d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>}
                                 </div>
                                 <div className="flex-1 min-w-0">
                                     <a href={arquivo.url_drive} target="_blank" rel="noreferrer" className="text-sm font-bold text-slate-800 hover:text-blue-600 truncate block">{arquivo.titulo}</a>
                                     <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">{arquivo.tipo}</span>
                                 </div>
                                 <button onClick={() => {
                                     if(window.confirm("Remover anexo?")) {
                                         updateDoc(doc(db, 'musicas', currentViewItem.id), {
                                             arquivos: currentViewItem.arquivos.filter(a => a.id !== arquivo.id)
                                         });
                                     }
                                 }} className="text-slate-300 hover:text-rose-500 p-2"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg></button>
                             </div>
                         ))}
                         {(!currentViewItem.arquivos || currentViewItem.arquivos.length === 0) && (
                             <div className="col-span-full p-6 rounded-2xl border-2 border-dashed border-slate-200 text-center text-slate-400">
                                 Nenhum arquivo anexado.
                             </div>
                         )}
                     </div>
                 </div>
               </div>
             </div>
           ) : (
             <div className="bg-slate-50/50 rounded-[2.5rem] border border-slate-200 flex flex-col items-center justify-center text-center p-12 h-[600px] opacity-60">
                <svg className="w-20 h-20 text-slate-300 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                <h3 className="text-2xl font-black text-slate-900 mb-2">Selecione uma Música</h3>
                <p className="text-slate-500 font-medium">Escolha uma música na lista ao lado para ver e editar detalhes, ou adicione uma nova.</p>
             </div>
           )}
        </div>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 animate-in fade-in">
          <div className="bg-white w-full max-w-2xl rounded-[2.5rem] shadow-2xl p-8 animate-in zoom-in-95">
            <h3 className="text-2xl font-black text-slate-900 mb-6">{selectedMusica ? 'Editar Música' : 'Nova Música'}</h3>
            
            <div className="space-y-6">
              <div>
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Título da Música *</label>
                <input type="text" value={titulo} onChange={e => setTitulo(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 mt-1" placeholder="Ex: Noite de Paz" />
              </div>
              
              <div>
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Tags (Aperte Enter)</label>
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-2 flex flex-wrap gap-2 focus-within:ring-2 focus-within:ring-blue-500 mt-1">
                   {tags.map(t => (
                       <span key={t} className="flex items-center gap-1 bg-white border border-slate-200 px-3 py-1 rounded-lg text-xs font-bold text-slate-700">
                           {t}
                           <button onClick={(e) => { e.preventDefault(); setTags(tags.filter(xt => xt !== t)); }} className="text-slate-400 hover:text-rose-500 text-lg leading-none">&times;</button>
                       </span>
                   ))}
                   <input type="text" value={tagInput} onChange={e => setTagInput(e.target.value)} onKeyDown={e => {
                       if(e.key === 'Enter' && tagInput.trim()) {
                           e.preventDefault();
                           if(!tags.includes(tagInput.trim())) setTags([...tags, tagInput.trim()]);
                           setTagInput('');
                       }
                   }} className="flex-1 bg-transparent min-w-[120px] outline-none text-sm font-bold text-slate-700 px-2" placeholder="Adicionar tag..." />
                </div>
              </div>

              <div>
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Observações / Letra</label>
                <textarea rows={5} value={observacoes} onChange={e => setObservacoes(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 custom-scrollbar mt-1" placeholder="Letra da música, notas sobre andamento e dinâmica..." />
              </div>
            </div>

            <div className="flex gap-4 mt-8">
                <button onClick={() => setIsModalOpen(false)} className="flex-1 py-4 text-[10px] font-black uppercase text-slate-400 hover:bg-slate-50 rounded-2xl transition-colors">Cancelar</button>
                <button onClick={handleSave} className="flex-1 bg-blue-600 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-colors">Salvar Música</button>
            </div>
          </div>
        </div>
      )}

      {/* Attachment Modal */}
      {isAttachmentModalOpen && currentViewItem && (
        <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-slate-900/60 animate-in fade-in backdrop-blur-sm">
          <div className="bg-white w-full max-w-3xl rounded-[2.5rem] shadow-2xl p-8 animate-in zoom-in-95 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-2xl font-black text-slate-900 tracking-tight">Anexar a "{currentViewItem.titulo}"</h3>
              <button onClick={() => setIsAttachmentModalOpen(false)} className="p-2 hover:bg-slate-100 rounded-full text-slate-400 hover:text-slate-600 transition-colors">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            <div className="flex flex-col md:flex-row gap-4 mb-6 shrink-0">
              <div className="flex-1 relative">
                <svg className="w-4 h-4 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                <input 
                  type="text" 
                  value={searchTermKB}
                  onChange={(e) => setSearchTermKB(e.target.value)}
                  placeholder="Pesquisar na base de conhecimento..."
                  className="w-full bg-slate-50 border border-slate-200 text-sm font-bold text-slate-900 rounded-xl pl-10 pr-4 py-3 outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              
              <label className={`shrink-0 bg-slate-900 text-white hover:bg-slate-800 px-6 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg transition-all cursor-pointer flex items-center justify-center gap-2 ${isUploading ? 'opacity-50 pointer-events-none' : ''}`}>
                <input 
                  type="file" 
                  className="hidden" 
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (file && onUploadFile) {
                       setIsUploading(true);
                       try {
                         const newItem = await onUploadFile(file);
                         if (newItem) {
                            await handleAttachItem(newItem);
                         }
                       } catch (err) {
                          showToast('Falha no upload', 'error');
                       } finally {
                          setIsUploading(false);
                          e.target.value = '';
                       }
                    } else if (file && !onUploadFile) {
                       showToast('Upload não disponível (método não fornecido)', 'error');
                    }
                  }}
                />
                {isUploading ? (
                   <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                ) : (
                   <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                )}
                {isUploading ? 'Enviando...' : 'Fazer Upload'}
              </label>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar border border-slate-100 rounded-2xl bg-slate-50 p-2">
              {knowledgeItems
                .filter(kb => !currentViewItem.arquivos?.some(a => a.id === kb.id))
                .filter(kb => !kb.is_folder)
                .filter(kb => searchTermKB ? kb.titulo.toLowerCase().includes(searchTermKB.toLowerCase()) : true)
                .map(kb => (
                <div key={kb.id} className="flex items-center justify-between p-3 bg-white border border-slate-100 rounded-xl mb-2 hover:border-blue-200 transition-colors">
                  <div className="flex items-center gap-3 overflow-hidden">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                      <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                    </div>
                    <div className="truncate">
                      <p className="text-sm font-bold text-slate-800 truncate">{kb.titulo}</p>
                      <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{kb.tipo_arquivo || 'desconhecido'}</p>
                    </div>
                  </div>
                  <button onClick={() => handleAttachItem(kb)} className="shrink-0 p-2 text-blue-600 hover:bg-blue-50 rounded-lg text-xs font-black uppercase tracking-widest transition-colors ml-4">
                    Selecionar
                  </button>
                </div>
              ))}
              {knowledgeItems.filter(kb => !currentViewItem.arquivos?.some(a => a.id === kb.id) && !kb.is_folder && (searchTermKB ? kb.titulo.toLowerCase().includes(searchTermKB.toLowerCase()) : true)).length === 0 && (
                <div className="text-center p-8 text-slate-400 text-sm font-bold">
                  Nenhum arquivo encontrado.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {sharedVideoWizard === 'options' && (
        <div className="fixed inset-0 z-[400] flex items-center justify-center p-4 bg-slate-900/80 backdrop-blur-sm animate-in fade-in">
           <div className="bg-white w-full max-w-lg rounded-[2.5rem] shadow-2xl p-10 text-center animate-in zoom-in-95">
               <div className="w-24 h-24 bg-purple-100 text-purple-600 rounded-full flex items-center justify-center mx-auto mb-6">
                 <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
               </div>
               <h3 className="text-3xl font-black text-slate-900 mb-2">Vídeo Recebido</h3>
               <p className="text-slate-500 font-bold mb-10">"{incomingSharedFile?.name}"</p>
               
               <div className="space-y-4">
                  <button onClick={() => {
                      setSharedVideoWizard(null);
                      setSelectedMusica(null); 
                      setTitulo(''); setTags([]); setObservacoes(''); 
                      setIsModalOpen(true);
                  }} className="w-full bg-blue-600 hover:bg-blue-700 text-white px-6 py-4 rounded-2xl font-black text-xs uppercase tracking-widest shadow-lg transition-colors">
                      Criar Nova Música
                  </button>
                  <button onClick={() => setSharedVideoWizard('pick_music')} className="w-full bg-slate-100 hover:bg-slate-200 text-slate-700 px-6 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-colors">
                      Vincular Música Existente
                  </button>
                  <button onClick={() => { setSharedVideoWizard(null); setIncomingSharedFile(null); }} className="w-full bg-transparent text-slate-400 hover:text-rose-500 px-6 py-4 rounded-2xl font-black text-[10px] uppercase tracking-widest transition-colors mt-4">
                      Cancelar Submissão
                  </button>
               </div>
           </div>
        </div>
      )}

      {sharedVideoWizard === 'pick_music' && (
        <div className="fixed inset-0 z-[400] flex items-center justify-center p-4 bg-slate-900/80 backdrop-blur-sm animate-in fade-in">
           <div className="bg-white w-full max-w-xl rounded-[2.5rem] shadow-2xl p-8 animate-in zoom-in-95 flex flex-col max-h-[80vh]">
               <h3 className="text-2xl font-black text-slate-900 mb-6">Selecione a Música</h3>
               <div className="flex-1 overflow-y-auto custom-scrollbar pr-2 space-y-2">
                 {musicas.map(m => (
                    <button key={m.id} onClick={() => handleProcessSharedVideo(m.id)} className="w-full text-left p-4 rounded-2xl border border-slate-100 hover:border-blue-300 hover:bg-blue-50 transition-colors flex items-center justify-between">
                       <span className="font-bold text-slate-900">{m.titulo}</span>
                       <svg className="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7"/></svg>
                    </button>
                 ))}
                 {musicas.length === 0 && <p className="text-center text-slate-400 font-bold py-10">Nenhuma música cadastrada.</p>}
               </div>
               <button onClick={() => setSharedVideoWizard('options')} className="mt-6 w-full py-4 bg-slate-100 hover:bg-slate-200 text-slate-500 rounded-2xl font-black text-[10px] uppercase tracking-widest transition-colors">Voltar</button>
           </div>
        </div>
      )}

    </div>
  );
};
