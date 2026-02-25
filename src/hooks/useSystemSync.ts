import { useState, useEffect } from 'react';
import { collection, doc, onSnapshot, addDoc, updateDoc, deleteDoc } from 'firebase/firestore';
import { db } from '../firebase';
import {
  Sistema,
  WorkItem,
  GoogleCalendarEvent,
  AtividadeRealizada,
  Afastamento,
  EntregaInstitucional,
  PlanoTrabalho,
  ConhecimentoItem,
  Unidade
} from '../types';

export const useSystemSync = (showToast: (msg: string, type: 'success' | 'error' | 'info') => void) => {
  const [sistemasDetalhes, setSistemasDetalhes] = useState<Sistema[]>([]);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState<GoogleCalendarEvent[]>([]);
  const [atividadesPGC, setAtividadesPGC] = useState<AtividadeRealizada[]>([]);
  const [afastamentos, setAfastamentos] = useState<Afastamento[]>([]);
  const [entregas, setEntregas] = useState<EntregaInstitucional[]>([]);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [planosTrabalho, setPlanosTrabalho] = useState<PlanoTrabalho[]>([]);
  const [knowledgeItems, setKnowledgeItems] = useState<ConhecimentoItem[]>([]);
  const [syncData, setSyncData] = useState<any>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [sistemasAtivos, setSistemasAtivos] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);

    const unsubSistemas = onSnapshot(collection(db, 'sistemas_detalhes'), (snapshot) => {
      setSistemasDetalhes(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Sistema)));
    });

    const unsubWorkItems = onSnapshot(collection(db, 'sistemas_work_items'), (snapshot) => {
      setWorkItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as WorkItem)));
    });

    const unsubGoogleCalendar = onSnapshot(collection(db, 'google_calendar_events'), (snapshot) => {
      setGoogleCalendarEvents(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as GoogleCalendarEvent)));
    });

    const unsubAtividadesPGC = onSnapshot(collection(db, 'atividades_pgc'), (snapshot) => {
      setAtividadesPGC(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as AtividadeRealizada)));
    });

    const unsubAfastamentos = onSnapshot(collection(db, 'afastamentos'), (snapshot) => {
      setAfastamentos(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Afastamento)));
    });

    const unsubEntregas = onSnapshot(collection(db, 'atividades'), (snapshot) => {
       // Note: Collection name is 'atividades' but type is EntregaInstitucional in index.tsx logic
      setEntregas(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as EntregaInstitucional)));
    });

    const unsubUnidades = onSnapshot(collection(db, 'unidades'), (snapshot) => {
      setUnidades(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Unidade)));
    });

    const unsubPlanos = onSnapshot(collection(db, 'planos_trabalho'), (snapshot) => {
      setPlanosTrabalho(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as PlanoTrabalho)));
    });

    const unsubKnowledge = onSnapshot(collection(db, 'conhecimento'), (snapshot) => {
      setKnowledgeItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as ConhecimentoItem)));
    });

    const unsubSync = onSnapshot(doc(db, 'system', 'sync'), (snap) => {
      if (snap.exists()) {
        const data = snap.data();
        setSyncData(data);
        if (data.status === 'processing' || data.status === 'requested') setIsSyncing(true);
        if (data.status === 'completed' || data.status === 'error') setIsSyncing(false);
      }
    });

    const unsubSistemasAtivos = onSnapshot(doc(db, 'configuracoes', 'sistemas'), (docSnap) => {
      if (docSnap.exists()) {
        setSistemasAtivos(docSnap.data().lista || []);
      }
    });

    setLoading(false);

    return () => {
      unsubSistemas();
      unsubWorkItems();
      unsubGoogleCalendar();
      unsubAtividadesPGC();
      unsubAfastamentos();
      unsubEntregas();
      unsubUnidades();
      unsubPlanos();
      unsubKnowledge();
      unsubSync();
      unsubSistemasAtivos();
    };
  }, []);

  const handleUpdateSistema = async (id: string, updates: Partial<Sistema>) => {
    try {
      await updateDoc(doc(db, 'sistemas_detalhes', id), {
         ...updates,
         data_atualizacao: new Date().toISOString()
      });
      showToast("Sistema atualizado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar sistema.", "error");
    }
  };

  const handleAddUnidade = async (nome: string) => {
    try {
      await addDoc(collection(db, 'unidades'), { nome, palavras_chave: [] });
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

  const handleCreateWorkItem = async (sistemaId: string, tipo: 'desenvolvimento' | 'ajuste' | 'log' | 'ideia', descricao: string, pool_dados: any[] = []) => {
    try {
      await addDoc(collection(db, 'sistemas_work_items'), {
        sistema_id: sistemaId,
        tipo,
        descricao,
        pool_dados,
        concluido: false,
        data_criacao: new Date().toISOString()
      });
      showToast("Item registrado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao registrar item.", "error");
    }
  };

  const handleUpdateWorkItem = async (id: string, updates: Partial<WorkItem>) => {
    try {
      await updateDoc(doc(db, 'sistemas_work_items', id), updates);
      showToast("Item atualizado!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar item.", "error");
    }
  };

  const handleDeleteWorkItem = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'sistemas_work_items', id));
      showToast("Item excluído!", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao excluir item.", "error");
    }
  };

  return {
    sistemasDetalhes,
    workItems,
    googleCalendarEvents,
    atividadesPGC,
    afastamentos,
    entregas,
    unidades,
    planosTrabalho,
    knowledgeItems,
    syncData,
    isSyncing,
    sistemasAtivos,
    loading,
    handleUpdateSistema,
    handleAddUnidade,
    handleDeleteUnidade,
    handleUpdateUnidade,
    handleCreateWorkItem,
    handleUpdateWorkItem,
    handleDeleteWorkItem
  };
};
