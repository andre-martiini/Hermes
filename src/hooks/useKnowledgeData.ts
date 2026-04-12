import { useState, useEffect } from 'react';
import { collection, onSnapshot } from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { User } from 'firebase/auth';
import type { ConhecimentoItem, BaseConhecimento } from '../../types';

export interface KnowledgeData {
  knowledgeItems: ConhecimentoItem[];
  masterKnowledge: any[];
  knowledgeBases: BaseConhecimento[];
}

export function useKnowledgeData(db: Firestore, user: User | null): KnowledgeData {
  const [knowledgeItems, setKnowledgeItems] = useState<ConhecimentoItem[]>([]);
  const [masterKnowledge, setMasterKnowledge] = useState<any[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<BaseConhecimento[]>([]);

  useEffect(() => {
    if (!user) return;

    const unsubKnowledge = onSnapshot(collection(db, 'conhecimento'), (snapshot) => {
      setKnowledgeItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as ConhecimentoItem)));
    });

    const unsubMaster = onSnapshot(collection(db, 'conhecimento_mestre'), (snapshot) => {
      setMasterKnowledge(snapshot.docs.map(d => ({ id: d.id, ...d.data() })));
    });

    const unsubBases = onSnapshot(collection(db, 'knowledge_bases'), (snapshot) => {
      setKnowledgeBases(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as BaseConhecimento)));
    });

    return () => {
      unsubKnowledge();
      unsubMaster();
      unsubBases();
    };
  }, [db, user]);

  return { knowledgeItems, masterKnowledge, knowledgeBases };
}
