import { useState, useEffect } from 'react';
import { collection, onSnapshot, doc, updateDoc, addDoc, deleteDoc, query, setDoc } from 'firebase/firestore';
import { db, functions } from '../firebase';
import { httpsCallable } from 'firebase/functions';
import {
  Sistema, WorkItem, Unidade, PlanoTrabalho, AtividadeRealizada, Afastamento,
  PoolItem, ConhecimentoItem, GoogleCalendarEvent, EntregaInstitucional
} from '../types';

export const useSystemSync = (
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void,
  pushToUndoStack: (label: string, undo: () => Promise<void> | void) => void
) => {
  const [sistemasDetalhes, setSistemasDetalhes] = useState<Sistema[]>([]);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [planosTrabalho, setPlanosTrabalho] = useState<PlanoTrabalho[]>([]);
  const [atividadesPGC, setAtividadesPGC] = useState<AtividadeRealizada[]>([]);
  const [afastamentos, setAfastamentos] = useState<Afastamento[]>([]);
  const [sistemasAtivos, setSistemasAtivos] = useState<string[]>([]);
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState<GoogleCalendarEvent[]>([]);
  const [knowledgeItems, setKnowledgeItems] = useState<ConhecimentoItem[]>([]);
  const [entregas, setEntregas] = useState<EntregaInstitucional[]>([]);
  const [syncData, setSyncData] = useState<any>(null);
  const [isUploading, setIsUploading] = useState(false);

  useEffect(() => {
    const unsubGoogleCalendar = onSnapshot(collection(db, 'google_calendar_events'), (snapshot) => {
      setGoogleCalendarEvents(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as GoogleCalendarEvent)));
    });

    const unsubSistemas = onSnapshot(collection(db, 'sistemas_detalhes'), (snapshot) => {
      setSistemasDetalhes(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Sistema)));
    });

    const unsubWorkItems = onSnapshot(collection(db, 'sistemas_work_items'), (snapshot) => {
      setWorkItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as WorkItem)));
    });

    const unsubUnidades = onSnapshot(collection(db, 'unidades'), (snapshot) => {
      setUnidades(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Unidade)));
    });

    const unsubPlanos = onSnapshot(collection(db, 'planos_trabalho'), (snapshot) => {
      setPlanosTrabalho(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as PlanoTrabalho)));
    });

    const unsubAtividades = onSnapshot(collection(db, 'atividades_pgc'), (snapshot) => {
      setAtividadesPGC(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as AtividadeRealizada)));
    });

    const unsubAfastamentos = onSnapshot(collection(db, 'afastamentos'), (snapshot) => {
      setAfastamentos(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Afastamento)));
    });

    const unsubSistemasAtivos = onSnapshot(doc(db, 'configuracoes', 'sistemas'), (docSnap) => {
      if (docSnap.exists()) {
        setSistemasAtivos(docSnap.data().lista || []);
      }
    });

    const unsubKnowledge = onSnapshot(collection(db, 'conhecimento'), (snapshot) => {
      setKnowledgeItems(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as ConhecimentoItem)));
    });

    const unsubEntregas = onSnapshot(collection(db, 'entregas_institucionais'), (snapshot) => {
      setEntregas(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as EntregaInstitucional)));
    });

    const unsubSync = onSnapshot(doc(db, 'system', 'sync'), (docSnap) => {
      if (docSnap.exists()) {
        setSyncData(docSnap.data());
      }
    });

    return () => {
      unsubSistemas();
      unsubWorkItems();
      unsubUnidades();
      unsubPlanos();
      unsubAtividades();
      unsubAfastamentos();
      unsubSistemasAtivos();
      unsubKnowledge();
      unsubEntregas();
      unsubSync();
    };
  }, []);

  const handleCreateWorkItem = async (sistemaId: string, tipo: 'desenvolvimento' | 'ajuste' | 'log' | 'geral', descricao: string, attachments: PoolItem[] = [], suppressToast = false) => {
    const finalTipo = tipo === 'geral' ? 'ajuste' : tipo;
    try {
      if (!descricao.trim()) return;
      const docRef = await addDoc(collection(db, 'sistemas_work_items'), {
        sistema_id: sistemaId,
        tipo: finalTipo,
        descricao,
        concluido: false,
        data_criacao: new Date().toISOString(),
        pool_dados: attachments
      });

      // Mirror to Knowledge base
      if (attachments.length > 0) {
        for (const item of attachments) {
          const knowledgeItem: ConhecimentoItem = {
            id: item.id,
            titulo: item.nome || 'Sem título',
            tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
            url_drive: item.valor,
            tamanho: 0,
            data_criacao: item.data_criacao,
            origem: { modulo: 'sistemas', id_origem: docRef.id },
            categoria: 'Sistemas'
          };
          setDoc(doc(db, 'conhecimento', item.id), knowledgeItem).catch(console.error);
        }
      }

      if (!suppressToast) showToast("Log registrado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao criar log.", "error");
    }
  };

  const handleUpdateWorkItem = async (id: string, updates: Partial<WorkItem>) => {
    try {
      await updateDoc(doc(db, 'sistemas_work_items', id), {
        ...updates
      } as any);

      if (updates.pool_dados && updates.pool_dados.length > 0) {
        for (const item of updates.pool_dados) {
          const knowledgeItem: ConhecimentoItem = {
            id: item.id,
            titulo: item.nome || 'Sem título',
            tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
            url_drive: item.valor,
            tamanho: 0,
            data_criacao: item.data_criacao,
            origem: { modulo: 'sistemas', id_origem: id },
            categoria: 'Sistemas'
          };
          setDoc(doc(db, 'conhecimento', item.id), knowledgeItem).catch(console.error);
        }
      }
      showToast("Item de trabalho atualizado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar item.", "error");
    }
  };

  const handleDeleteWorkItem = async (id: string) => {
    const item = workItems.find(w => w.id === id);
    if (!item) return;

    try {
      await deleteDoc(doc(db, 'sistemas_work_items', id));

      pushToUndoStack("Excluir Log", async () => {
        const { id: _, ...data } = item;
        await setDoc(doc(db, 'sistemas_work_items', id), data);
      });

      showToast("Item de trabalho removido.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover item.", "error");
    }
  };

  const handleUpdateSistema = async (id: string, updates: Partial<Sistema>) => {
    try {
      await setDoc(doc(db, 'sistemas_detalhes', id), {
        ...updates,
        data_atualizacao: new Date().toISOString()
      }, { merge: true });
      showToast("Sistema atualizado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar sistema.", "error");
    }
  };

  const handleAddUnidade = async (nome: string) => {
    try {
      await addDoc(collection(db, 'unidades'), {
        nome: nome,
        palavras_chave: []
      });
      showToast(`Área ${nome} adicionada!`, 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao adicionar área.", 'error');
    }
  };

  const handleDeleteUnidade = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'unidades', id));
      showToast("Área removida.", 'info');
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover área.", 'error');
    }
  };

  const handleUpdateUnidade = async (id: string, updates: any) => {
    try {
      await updateDoc(doc(db, 'unidades', id), updates);
      showToast("Área atualizada!", 'success');
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar área.", 'error');
    }
  };

  const handleFileUploadToDrive = async (file: File) => {
    try {
      setIsUploading(true);
      const reader = new FileReader();
      const base64Promise = new Promise<string>((resolve, reject) => {
        reader.onload = () => resolve((reader.result as string).split(',')[1]);
        reader.onerror = reject;
      });
      const base64 = await base64Promise;

      const uploadFn = httpsCallable(functions, 'uploadFileToDrive');
      const result = await uploadFn({
        fileName: file.name,
        mimeType: file.type,
        fileBase64: base64
      });

      const data = result.data as any;
      if (!data.success) throw new Error(data.error);

      const item: PoolItem = {
        id: data.fileId,
        tipo: 'arquivo',
        valor: data.webViewLink,
        nome: file.name,
        data_criacao: new Date().toISOString(),
        drive_file_id: data.fileId
      };
      setIsUploading(false);
      return item;
    } catch (err) {
      console.error(err);
      setIsUploading(false);
      showToast("Erro no upload do arquivo.", "error");
      return null;
    }
  };

  const handleUploadKnowledgeFile = async (file: File) => {
    const item = await handleFileUploadToDrive(file);
    if (item) {
      const knowledgeItem: ConhecimentoItem = {
        id: item.id,
        titulo: item.nome || 'Sem título',
        tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
        url_drive: item.valor,
        tamanho: 0,
        data_criacao: item.data_criacao,
        origem: null
      };
      await setDoc(doc(db, 'conhecimento', item.id), knowledgeItem);
      showToast("Arquivo enviado e indexação iniciada.", "success");
    }
  };

  const handleDeleteKnowledgeItem = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'conhecimento', id));
      showToast("Arquivo removido do repositório.", "info");
    } catch (e) {
      showToast("Erro ao remover arquivo.", "error");
    }
  };

  const handleAddKnowledgeLink = async (url: string, title: string) => {
    try {
      await addDoc(collection(db, 'conhecimento'), {
        titulo: title,
        tipo_arquivo: 'link',
        url_drive: url,
        tamanho: 0,
        data_criacao: new Date().toISOString(),
        origem: null
      });
      showToast("Link salvo com sucesso.", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao salvar link.", "error");
    }
  };

  const handleSaveKnowledgeItem = async (item: Partial<ConhecimentoItem>) => {
    try {
      if (item.id) {
        await updateDoc(doc(db, 'conhecimento', item.id), item);
        showToast("Item atualizado.", "success");
      } else {
        await addDoc(collection(db, 'conhecimento'), {
          ...item,
          data_criacao: new Date().toISOString()
        });
        showToast("Item salvo.", "success");
      }
    } catch (e) {
      console.error(e);
      showToast("Erro ao salvar item.", "error");
    }
  };

  const handleProcessarIA = async (itemId: string) => {
    try {
      const processarIA = httpsCallable(functions, 'processarArquivoIA');
      showToast("Solicitando processamento à IA...", "info");

      const result = await processarIA({ itemId });
      const data = result.data as any;

      if (data.success) {
        showToast("Arquivo processado com sucesso!", "success");
      } else {
        showToast("Erro ao processar: " + (data.error || "Erro desconhecido"), "error");
      }
    } catch (err) {
      console.error(err);
      showToast("Falha na comunicação com a IA.", "error");
    }
  };

  const handleGenerateSlides = async (text: string) => {
    const gerarSlidesIA = httpsCallable(functions, 'gerarSlidesIA');
    try {
      const result = await gerarSlidesIA({ rascunho: text });
      return result.data;
    } catch (error: any) {
      console.error("Erro ao gerar slides:", error);
      throw error;
    }
  };

  return {
    sistemasDetalhes,
    workItems,
    unidades,
    planosTrabalho,
    atividadesPGC,
    afastamentos,
    sistemasAtivos,
    googleCalendarEvents,
    isUploading,
    handleCreateWorkItem,
    handleUpdateWorkItem,
    handleDeleteWorkItem,
    handleUpdateSistema,
    handleAddUnidade,
    handleDeleteUnidade,
    handleUpdateUnidade,
    handleFileUploadToDrive,
    handleUploadKnowledgeFile,
    handleDeleteKnowledgeItem,
    handleAddKnowledgeLink,
    handleSaveKnowledgeItem,
    handleProcessarIA,
    handleGenerateSlides,
    knowledgeItems,
    entregas,
    syncData
  };
};
