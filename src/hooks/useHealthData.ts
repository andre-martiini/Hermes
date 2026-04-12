import { useState, useEffect } from 'react';
import { collection, doc, onSnapshot } from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { User } from 'firebase/auth';
import type { HealthWeight, DailyHabits, HealthSettings, HealthExam } from '../../types';

const DEFAULT_HEALTH_SETTINGS: HealthSettings = { targetWeight: 0 };

export interface HealthData {
  healthWeights: HealthWeight[];
  healthDailyHabits: DailyHabits[];
  healthSettings: HealthSettings;
  exams: HealthExam[];
}

export function useHealthData(db: Firestore, user: User | null): HealthData {
  const [healthWeights, setHealthWeights] = useState<HealthWeight[]>([]);
  const [healthDailyHabits, setHealthDailyHabits] = useState<DailyHabits[]>([]);
  const [healthSettings, setHealthSettings] = useState<HealthSettings>(DEFAULT_HEALTH_SETTINGS);
  const [exams, setExams] = useState<HealthExam[]>([]);

  useEffect(() => {
    if (!user) return;

    const unsubWeights = onSnapshot(collection(db, 'health_weights'), (snapshot) => {
      setHealthWeights(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as HealthWeight)));
    });

    const unsubHabits = onSnapshot(collection(db, 'health_daily_habits'), (snapshot) => {
      setHealthDailyHabits(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as DailyHabits)));
    });

    const unsubSettings = onSnapshot(doc(db, 'health_settings', 'config'), (docSnap) => {
      if (docSnap.exists()) setHealthSettings(docSnap.data() as HealthSettings);
    });

    const unsubExams = onSnapshot(collection(db, 'exames'), (snap) => {
      setExams(snap.docs.map(d => ({ id: d.id, ...d.data() } as HealthExam)));
    });

    return () => {
      unsubWeights();
      unsubHabits();
      unsubSettings();
      unsubExams();
    };
  }, [db, user]);

  return { healthWeights, healthDailyHabits, healthSettings, exams };
}
