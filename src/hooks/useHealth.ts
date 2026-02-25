import { useState, useEffect } from 'react';
import { collection, onSnapshot, doc, setDoc, addDoc, deleteDoc, query } from 'firebase/firestore';
import { db } from '../firebase';
import { HealthWeight, DailyHabits, HealthSettings, HealthExam } from '../types';

export const useHealth = (showToast: (msg: string, type: 'success' | 'error' | 'info') => void) => {
  const [healthWeights, setHealthWeights] = useState<HealthWeight[]>([]);
  const [healthDailyHabits, setHealthDailyHabits] = useState<DailyHabits[]>([]);
  const [healthSettings, setHealthSettings] = useState<HealthSettings>({ targetWeight: 0 });
  const [exams, setExams] = useState<HealthExam[]>([]);

  useEffect(() => {
    const unsubWeights = onSnapshot(collection(db, 'health_weights'), (snapshot) => {
      setHealthWeights(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as HealthWeight)));
    });
    const unsubHabits = onSnapshot(collection(db, 'health_daily_habits'), (snapshot) => {
      setHealthDailyHabits(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as DailyHabits)));
    });
    const unsubSettings = onSnapshot(doc(db, 'health_settings', 'config'), (doc) => {
      if (doc.exists()) setHealthSettings(doc.data() as HealthSettings);
    });
    const unsubExams = onSnapshot(collection(db, 'exames'), (snapshot) => {
      setExams(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as HealthExam)));
    });

    return () => {
      unsubWeights();
      unsubHabits();
      unsubSettings();
      unsubExams();
    };
  }, []);

  const handleUpdateHealthSettings = async (settings: HealthSettings) => {
    try {
      await setDoc(doc(db, 'health_settings', 'config'), settings);
      showToast("Meta de peso atualizada!", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao atualizar meta.", "error");
    }
  };

  const handleAddHealthWeight = async (weight: number, date: string) => {
    try {
      await addDoc(collection(db, 'health_weights'), { weight, date });
      showToast("Peso registrado com sucesso!", "success");
    } catch (e) {
      console.error(e);
      showToast("Erro ao registrar peso.", "error");
    }
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
    try {
      await setDoc(doc(db, 'health_daily_habits', date), habits, { merge: true });
    } catch (e) {
      console.error(e);
      showToast("Erro ao atualizar hábito.", "error");
    }
  };

  return {
    healthWeights,
    healthDailyHabits,
    healthSettings,
    exams,
    handleUpdateHealthSettings,
    handleAddHealthWeight,
    handleDeleteHealthWeight,
    handleUpdateHealthHabits
  };
};
