import { useState, useEffect } from 'react';
import { collection, doc, addDoc, updateDoc, deleteDoc, setDoc, onSnapshot } from 'firebase/firestore';
import { db } from '../firebase';
import { HealthWeight, DailyHabits, HealthSettings, HealthExam, PoolItem, ConhecimentoItem } from '../types';

export const useHealth = (showToast: (msg: string, type: 'success' | 'error' | 'info') => void) => {
  const [healthWeights, setHealthWeights] = useState<HealthWeight[]>([]);
  const [healthDailyHabits, setHealthDailyHabits] = useState<DailyHabits[]>([]);
  const [healthSettings, setHealthSettings] = useState<HealthSettings>({ targetWeight: 0 });
  const [exams, setExams] = useState<HealthExam[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const unsubHealthWeights = onSnapshot(collection(db, 'health_weights'), (snapshot) => {
      setHealthWeights(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as HealthWeight)));
    });
    const unsubHealthHabits = onSnapshot(collection(db, 'health_daily_habits'), (snapshot) => {
      setHealthDailyHabits(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as DailyHabits)));
    });
    const unsubHealthSettings = onSnapshot(doc(db, 'health_settings', 'config'), (docSnap) => {
      if (docSnap.exists()) setHealthSettings(docSnap.data() as HealthSettings);
    });
    const unsubExams = onSnapshot(collection(db, 'exames'), (snap) => {
        const data = snap.docs.map(d => ({ id: d.id, ...d.data() } as HealthExam));
        setExams(data);
    });

    setLoading(false);

    return () => {
      unsubHealthWeights();
      unsubHealthHabits();
      unsubHealthSettings();
      unsubExams();
    };
  }, []);

  const handleUpdateHealthSettings = async (settings: HealthSettings) => {
    await setDoc(doc(db, 'health_settings', 'config'), settings);
    showToast("Meta de peso atualizada!", "success");
  };

  const handleAddHealthWeight = async (weight: number, date: string) => {
    await addDoc(collection(db, 'health_weights'), { weight, date });
    showToast("Peso registrado com sucesso!", "success");
  };

  const handleDeleteHealthWeight = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'health_weights', id));
      showToast("Registro de peso removido.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover registro.", "error");
    }
  };

  const handleUpdateHealthHabits = async (date: string, habits: Partial<DailyHabits>) => {
    await setDoc(doc(db, 'health_daily_habits', date), habits, { merge: true });
  };

  const handleAddExam = async (exam: Partial<HealthExam>, poolItems: PoolItem[] = []) => {
      try {
          const examDoc = await addDoc(collection(db, 'exames'), {
             ...exam,
             pool_dados: poolItems,
             data_criacao: new Date().toISOString()
          });

          // Mirror to Knowledge base
          if (poolItems.length > 0) {
             for (const item of poolItems) {
                const knowledgeItem: ConhecimentoItem = {
                   id: item.id,
                   titulo: item.nome || 'Sem título',
                   tipo_arquivo: item.tipo === 'link' ? 'link' : (item.nome?.split('.').pop()?.toLowerCase() || 'unknown'),
                   url_drive: item.valor,
                   tamanho: 0,
                   data_criacao: item.data_criacao,
                   origem: { modulo: 'saude', id_origem: examDoc.id },
                   categoria: 'Saúde'
                };
                await setDoc(doc(db, 'conhecimento', item.id), knowledgeItem);
             }
          }
          showToast("Registro de saúde adicionado e indexado.", "success");
      } catch (err) {
          console.error(err);
          showToast("Erro ao adicionar registro.", "error");
      }
  };

  const handleUpdateExam = async (id: string, updates: Partial<HealthExam>) => {
     try {
         await updateDoc(doc(db, 'exames', id), updates);
         showToast("Registro atualizado.", "success");
     } catch (err) {
         console.error(err);
         showToast("Erro ao atualizar.", "error");
     }
  };

  const handleDeleteExam = async (id: string) => {
    try {
      await deleteDoc(doc(db, 'exames', id));
      showToast("Registro removido.", "info");
    } catch (err) {
      console.error(err);
      showToast("Erro ao remover registro.", "error");
    }
  };

  return {
    healthWeights,
    healthDailyHabits,
    healthSettings,
    exams,
    loading,
    handleUpdateHealthSettings,
    handleAddHealthWeight,
    handleDeleteHealthWeight,
    handleUpdateHealthHabits,
    handleAddExam,
    handleUpdateExam,
    handleDeleteExam
  };
};
