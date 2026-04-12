import { useState, useEffect } from 'react';
import { collection, query, onSnapshot } from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { User } from 'firebase/auth';
import type {
  Tarefa,
  EntregaInstitucional,
  AtividadeRealizada,
  Afastamento,
  PlanoTrabalho,
  BrainstormIdea,
} from '../../types';

export interface TasksData {
  tarefas: Tarefa[];
  entregas: EntregaInstitucional[];
  atividadesPGC: AtividadeRealizada[];
  afastamentos: Afastamento[];
  unidades: { id: string; nome: string; palavras_chave?: string[] }[];
  planosTrabalho: PlanoTrabalho[];
  brainstormIdeas: BrainstormIdea[];
}

/**
 * Subscribes to all task-related Firestore collections.
 * Note: migration logic (legacy date normalization, overdue auto-update)
 * is intentionally left in the App component as separate useEffects watching `tarefas`,
 * keeping this hook free of side effects.
 */
export function useTasksData(db: Firestore, user: User | null): TasksData {
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [entregas, setEntregas] = useState<EntregaInstitucional[]>([]);
  const [atividadesPGC, setAtividadesPGC] = useState<AtividadeRealizada[]>([]);
  const [afastamentos, setAfastamentos] = useState<Afastamento[]>([]);
  const [unidades, setUnidades] = useState<{ id: string; nome: string; palavras_chave?: string[] }[]>([]);
  const [planosTrabalho, setPlanosTrabalho] = useState<PlanoTrabalho[]>([]);
  const [brainstormIdeas, setBrainstormIdeas] = useState<BrainstormIdea[]>([]);

  useEffect(() => {
    if (!user) return;

    const unsubTarefas = onSnapshot(query(collection(db, 'tarefas')), (snapshot) => {
      const normalized: Tarefa[] = snapshot.docs.map(taskDoc => {
        const raw = { id: taskDoc.id, ...taskDoc.data() } as Tarefa;
        const singleDate = raw.data_limite || raw.data_inicio || '';
        return { ...raw, data_limite: singleDate, data_inicio: singleDate };
      });
      setTarefas(normalized);
    });

    const unsubAtividadesPGC = onSnapshot(query(collection(db, 'atividades_pgc')), (snapshot) => {
      setAtividadesPGC(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as AtividadeRealizada)));
    });

    const unsubAfastamentos = onSnapshot(query(collection(db, 'afastamentos')), (snapshot) => {
      setAfastamentos(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Afastamento)));
    });

    // Entregas: merge from two collections (current + legacy)
    let entregasMain: EntregaInstitucional[] = [];
    let entregasLegacy: EntregaInstitucional[] = [];
    const syncEntregas = () => {
      const merged = [...entregasMain, ...entregasLegacy];
      const dedup = new Map<string, EntregaInstitucional>();
      merged.forEach(e => dedup.set(e.id, e));
      setEntregas(Array.from(dedup.values()));
    };

    const unsubEntregas = onSnapshot(query(collection(db, 'entregas')), (snapshot) => {
      entregasMain = snapshot.docs.map(d => ({ id: d.id, ...d.data() } as EntregaInstitucional));
      syncEntregas();
    });

    const unsubAtividadesLegacy = onSnapshot(query(collection(db, 'atividades')), (snapshot) => {
      entregasLegacy = snapshot.docs.map(d => ({ id: d.id, ...d.data() } as EntregaInstitucional));
      syncEntregas();
    });

    const unsubUnidades = onSnapshot(query(collection(db, 'unidades')), (snapshot) => {
      setUnidades(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as { id: string; nome: string; palavras_chave?: string[] })));
    });

    const unsubPlanos = onSnapshot(query(collection(db, 'planos_trabalho')), (snapshot) => {
      setPlanosTrabalho(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as PlanoTrabalho)));
    });

    const unsubBrainstorm = onSnapshot(query(collection(db, 'brainstorm_ideas')), (snapshot) => {
      setBrainstormIdeas(
        snapshot.docs
          .map(d => ({ id: d.id, ...d.data() } as BrainstormIdea))
          .sort((a, b) => b.timestamp.localeCompare(a.timestamp)),
      );
    });

    return () => {
      unsubTarefas();
      unsubAtividadesPGC();
      unsubAfastamentos();
      unsubEntregas();
      unsubAtividadesLegacy();
      unsubUnidades();
      unsubPlanos();
      unsubBrainstorm();
    };
  }, [db, user]);

  return { tarefas, entregas, atividadesPGC, afastamentos, unidades, planosTrabalho, brainstormIdeas };
}
