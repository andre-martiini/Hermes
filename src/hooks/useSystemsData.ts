import { useState, useEffect } from 'react';
import { collection, doc, onSnapshot } from 'firebase/firestore';
import type { Firestore } from 'firebase/firestore';
import type { User } from 'firebase/auth';
import type { Sistema, WorkItem, GoogleCalendarEvent } from '../../types';

export interface SystemsData {
  sistemasDetalhes: Sistema[];
  workItems: WorkItem[];
  googleCalendarEvents: GoogleCalendarEvent[];
  sistemasAtivos: string[];
}

export function useSystemsData(db: Firestore, user: User | null): SystemsData {
  const [sistemasDetalhes, setSistemasDetalhes] = useState<Sistema[]>([]);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState<GoogleCalendarEvent[]>([]);
  const [sistemasAtivos, setSistemasAtivos] = useState<string[]>([]);

  useEffect(() => {
    if (!user) return;

    const unsubSistemas = onSnapshot(collection(db, 'sistemas_detalhes'), (snapshot) => {
      setSistemasDetalhes(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as Sistema)));
    });

    const unsubWorkItems = onSnapshot(collection(db, 'sistemas_work_items'), (snapshot) => {
      setWorkItems(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as WorkItem)));
    });

    const unsubGoogleCalendar = onSnapshot(collection(db, 'google_calendar_events'), (snapshot) => {
      setGoogleCalendarEvents(snapshot.docs.map(d => ({ id: d.id, ...d.data() } as GoogleCalendarEvent)));
    });

    const unsubSistemasAtivos = onSnapshot(doc(db, 'configuracoes', 'sistemas'), (docSnap) => {
      if (docSnap.exists()) {
        setSistemasAtivos(docSnap.data().lista || []);
      }
    });

    return () => {
      unsubSistemas();
      unsubWorkItems();
      unsubGoogleCalendar();
      unsubSistemasAtivos();
    };
  }, [db, user]);

  return { sistemasDetalhes, workItems, googleCalendarEvents, sistemasAtivos };
}
