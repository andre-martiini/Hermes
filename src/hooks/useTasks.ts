import { useState, useEffect } from 'react';
import { collection, doc, addDoc, updateDoc, onSnapshot, query, deleteDoc } from 'firebase/firestore';
import { db } from '../firebase';
import { Tarefa, UndoAction, BrainstormIdea } from '../types';
import { formatDateLocalISO } from '../types';
import { normalizeStatus } from '../utils/helpers';

export const useTasks = (showToast: (msg: string, type: 'success' | 'error' | 'info', action?: any, actions?: any) => void) => {
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [brainstormIdeas, setBrainstormIdeas] = useState<BrainstormIdea[]>([]);
  const [undoStack, setUndoStack] = useState<UndoAction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [convertingIdea, setConvertingIdea] = useState<BrainstormIdea | null>(null);
  const [taskInitialData, setTaskInitialData] = useState<Partial<Tarefa> | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  useEffect(() => {
    setLoading(true);
    const qTarefas = query(collection(db, 'tarefas'));
    const unsubscribe = onSnapshot(qTarefas, (snapshot) => {
      const dataT = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Tarefa));
      setTarefas(dataT);
      setLoading(false);
    }, (err) => {
      console.error(err);
      setError("Erro ao conectar com o banco de dados (Tarefas).");
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    const qIdeas = collection(db, 'brainstorm_ideas');
    const unsubscribe = onSnapshot(qIdeas, (snapshot) => {
      setBrainstormIdeas(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as BrainstormIdea)));
    });
    return () => unsubscribe();
  }, []);

  const pushToUndoStack = (label: string, undo: () => Promise<void> | void) => {
    const action: UndoAction = {
      id: Math.random().toString(36).substr(2, 9),
      label,
      undo,
      timestamp: Date.now()
    };
    setUndoStack(prev => [action, ...prev].slice(0, 10));
  };

  const handleUndo = async () => {
    if (undoStack.length === 0) return;
    const [action, ...rest] = undoStack;
    await action.undo();
    setUndoStack(rest);
    showToast(`Desfeito: ${action.label}`, "info");
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        const target = e.target as HTMLElement;
        const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
        if (!isInput) {
          e.preventDefault();
          handleUndo();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undoStack]);

  const handleCreateTarefa = async (data: Partial<Tarefa>) => {
    try {
      setLoading(true);
      await addDoc(collection(db, 'tarefas'), {
        ...data,
        google_id: "",
        data_atualizacao: new Date().toISOString(),
        projeto: 'Google Tasks',
        prioridade: 'média',
        contabilizar_meta: data.categoria === 'CLC' || data.categoria === 'ASSISTÊNCIA',
        acompanhamento: [],
        entregas_relacionadas: []
      });

      if (convertingIdea) {
        await deleteDoc(doc(db, 'brainstorm_ideas', convertingIdea.id));
        setConvertingIdea(null);
        setTaskInitialData(null);
      }
      showToast("Nova ação criada!", 'success');
    } catch (err) {
      console.error("Erro ao criar tarefa:", err);
      showToast("Erro ao criar ação.", 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateTarefa = async (id: string, updates: Partial<Tarefa>, suppressToast = false) => {
    try {
      const docRef = doc(db, 'tarefas', id);
      await updateDoc(docRef, {
        ...updates,
        data_atualizacao: new Date().toISOString()
      });

      if (!suppressToast) showToast("Tarefa atualizada!", 'success');
    } catch (err) {
      console.error("Erro ao atualizar tarefa:", err);
      showToast("Erro ao salvar alterações.", 'error');
    }
  };

  const handleDeleteTarefa = async (id: string) => {
    const tarefa = tarefas.find(t => t.id === id);
    if (!tarefa) return;

    try {
      setLoading(true);
      const docRef = doc(db, 'tarefas', id);
      await updateDoc(docRef, {
        status: 'excluído' as any,
        data_atualizacao: new Date().toISOString()
      });

      pushToUndoStack("Excluir Tarefa", async () => {
        await updateDoc(docRef, {
          status: tarefa.status,
          data_atualizacao: new Date().toISOString()
        });
      });

      showToast('Tarefa excluída!', 'success');
    } catch (err) {
      console.error("Erro ao excluir tarefa:", err);
      showToast("Erro ao excluir.", 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleTarefaStatus = async (id: string, currentStatus: string) => {
    const tarefa = tarefas.find(t => t.id === id);
    if (!tarefa) return;
    const oldStatus = tarefa.status;
    const oldDataConclusao = tarefa.data_conclusao || null;

    try {
      const isConcluido = normalizeStatus(currentStatus) === 'concluido';
      const newStatus = isConcluido ? 'em andamento' : 'concluído';
      const now = new Date().toISOString();

      await updateDoc(doc(db, 'tarefas', id), {
        status: newStatus,
        data_conclusao: !isConcluido ? now : null,
        data_atualizacao: now
      });

      pushToUndoStack(isConcluido ? "Alterar Status" : "Concluir Tarefa", async () => {
        await updateDoc(doc(db, 'tarefas', id), {
          status: oldStatus,
          data_conclusao: oldDataConclusao,
          data_atualizacao: new Date().toISOString()
        });
      });

      showToast(isConcluido ? "Tarefa reaberta!" : "Tarefa concluída!", 'success');
    } catch (err) {
      showToast("Erro ao remover.", "error");
    }
  };

  const handleReorderTasks = async (taskId: string, targetTaskId: string, label?: string, tarefasAgrupadas?: {[key: string]: Tarefa[]}) => {
     if (!tarefasAgrupadas) return;

     let currentLabel = label;
    if (!currentLabel) {
      for (const [l, ts] of Object.entries(tarefasAgrupadas)) {
        if (ts.some(t => t.id === targetTaskId)) {
          currentLabel = l;
          break;
        }
      }
    }
    if (!currentLabel) return;

    const tasksInBucket = [...(tarefasAgrupadas[currentLabel] || [])];
    if (tasksInBucket.length === 0) return;

    const oldIndex = tasksInBucket.findIndex(t => t.id === taskId);
    const newIndex = tasksInBucket.findIndex(t => t.id === targetTaskId);

    if (oldIndex !== -1) {
      if (oldIndex === newIndex) return;
      const [removed] = tasksInBucket.splice(oldIndex, 1);
      tasksInBucket.splice(newIndex, 0, removed);
    } else {
      const draggedTask = tarefas.find(t => t.id === taskId);
      if (!draggedTask) return;
      const targetTask = tasksInBucket[newIndex];
      const newDate = targetTask.data_limite || formatDateLocalISO(new Date());

      await updateDoc(doc(db, 'tarefas', taskId), {
        data_limite: newDate,
        data_inicio: draggedTask.horario_inicio ? newDate : (draggedTask.data_inicio || newDate),
        data_atualizacao: new Date().toISOString()
      });
      tasksInBucket.splice(newIndex, 0, { ...draggedTask, data_limite: newDate });
    }

    const promises = tasksInBucket.map((t, i) => {
      if (t.ordem !== i) {
        return updateDoc(doc(db, 'tarefas', t.id), { ordem: i, data_atualizacao: new Date().toISOString() });
      }
      return null;
    }).filter(Boolean);

    if (promises.length > 0) {
      await Promise.all(promises);
      showToast("Ordem atualizada!", "success");
    }
  };

  const handleDeleteIdea = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'brainstorm_ideas', id));
      showToast("Nota removida.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover.", "error");
    }
  };

  const handleArchiveIdea = async (id: string) => {
    try {
      const idea = brainstormIdeas.find(i => i.id === id);
      if (!idea) return;

      const newStatus = idea.status === 'archived' ? 'active' : 'archived';
      await updateDoc(doc(db, 'brainstorm_ideas', id), {
        status: newStatus
      });
      showToast(newStatus === 'archived' ? "Nota concluída e arquivada!" : "Nota restaurada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao processar nota.", "error");
    }
  };

  const handleAddTextIdea = async (text: string) => {
    try {
      await addDoc(collection(db, 'brainstorm_ideas'), {
        text,
        timestamp: new Date().toISOString(),
        status: 'active'
      });
      showToast("Nota registrada!", "success", undefined, [
        {
          label: 'Copiar',
          onClick: () => {
            navigator.clipboard.writeText(text);
          }
        }
      ]);
    } catch (err) {
      console.error(err);
      showToast("Erro ao registrar nota.", "error");
    }
  };

  const handleUpdateIdea = async (id: string, text: string) => {
    try {
      await updateDoc(doc(db, 'brainstorm_ideas', id), { text });
      showToast("Nota atualizada!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao atualizar nota.", "error");
    }
  };

  return {
    tarefas,
    brainstormIdeas,
    undoStack,
    loading,
    error,
    convertingIdea,
    setConvertingIdea,
    taskInitialData,
    setTaskInitialData,
    isCreateModalOpen,
    setIsCreateModalOpen,
    handleCreateTarefa,
    handleUpdateTarefa,
    handleDeleteTarefa,
    handleToggleTarefaStatus,
    handleUndo,
    pushToUndoStack,
    handleReorderTasks,
    handleDeleteIdea,
    handleArchiveIdea,
    handleAddTextIdea,
    handleUpdateIdea
  };
};
