import { useState, useEffect } from 'react';
import { doc, setDoc, onSnapshot } from 'firebase/firestore';
import { getToken, onMessage } from 'firebase/messaging';
import { db, messaging } from '../firebase';
import { HermesNotification, AppSettings, Tarefa, formatDateLocalISO } from '../types';
import { DEFAULT_APP_SETTINGS } from '../utils/helpers';

export const useNotifications = (
  tarefas: Tarefa[],
  showToast: (msg: string, type: 'success' | 'error' | 'info') => void
) => {
  const [notifications, setNotifications] = useState<HermesNotification[]>([]);
  const [appSettings, setAppSettings] = useState<AppSettings>(DEFAULT_APP_SETTINGS);
  const [activePopup, setActivePopup] = useState<HermesNotification | null>(null);
  const [isHabitsReminderOpen, setIsHabitsReminderOpen] = useState(false);

  useEffect(() => {
    const setupFCM = async () => {
      if (!messaging) return;
      try {
        const permission = await Notification.requestPermission();
        if (permission === 'granted') {
          const registration = await navigator.serviceWorker.ready;
          const token = await getToken(messaging, {
            vapidKey: 'BBXF5bMrAdRIXKGLHXMzsZSREaQoVo2VbVgcJJkA7_qu05v2GOcCqgLRjc54airIqf087t46jvggg7ZdmPzuqiE',
            serviceWorkerRegistration: registration
          }).catch(err => {
            console.error("Erro ao obter FCM Token:", err);
            return null;
          });

          if (token) {
            await setDoc(doc(db, 'fcm_tokens', token), {
              token,
              last_updated: new Date().toISOString(),
              platform: 'web_pwa',
              userAgent: navigator.userAgent
            });
          }
        }
      } catch (error) {
        console.error('Falha crítica no setup do FCM:', error);
      }
    };

    setupFCM();

    const unsubscribe = onMessage(messaging!, (payload) => {
      if (payload.notification) {
        const newNotif: HermesNotification = {
          id: Math.random().toString(36).substr(2, 9),
          title: payload.notification.title || 'Hermes',
          message: payload.notification.body || '',
          type: 'info',
          timestamp: new Date().toISOString(),
          isRead: false,
          link: (payload.data as any)?.link || ""
        };
        setNotifications(prev => [newNotif, ...prev]);
        setActivePopup(newNotif);
      }
    });

    return () => unsubscribe();
  }, []);

  const emitNotification = async (title: string, message: string, type: 'info' | 'warning' | 'success' | 'error' = 'info', link?: string, id?: string) => {
    const newNotif: HermesNotification = {
      id: id || Math.random().toString(36).substr(2, 9),
      title,
      message,
      type,
      timestamp: new Date().toISOString(),
      isRead: false,
      link: link || ""
    };

    setNotifications(prev => {
      if (prev.some(n => n.id === newNotif.id)) return prev;
      return [newNotif, ...prev];
    });
    setActivePopup(newNotif);

    try {
      const firestoreData = JSON.parse(JSON.stringify(newNotif));
      const shouldSendPush = appSettings.notifications?.enablePush !== false;

      await setDoc(doc(db, 'notificacoes', newNotif.id), {
        ...firestoreData,
        sent_to_push: !shouldSendPush
      });
    } catch (err) {
      console.error("Erro ao persistir notificação:", err);
      showToast(`Erro no sistema de notificação: ${err}`, "error");
    }
  };

  useEffect(() => {
    const unsub = onSnapshot(doc(db, 'configuracoes', 'geral'), (snap) => {
      if (snap.exists()) {
        setAppSettings(snap.data() as AppSettings);
      }
    });
    return () => unsub();
  }, []);

  const handleUpdateAppSettings = async (newSettings: AppSettings) => {
    try {
      await setDoc(doc(db, 'configuracoes', 'geral'), newSettings);
      showToast("Configurações atualizadas!", "success");
    } catch (err) {
      console.error(err);
      showToast("Erro ao salvar configurações.", "error");
    }
  };

  const handleMarkNotificationRead = (id: string) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, isRead: true } : n));
  };

  const handleDismissNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
    if (activePopup?.id === id) setActivePopup(null);
  };

  // Time-based Triggers
  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date();
      const current_time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      const todayStr = formatDateLocalISO(now);

      // Habits
      if (appSettings.notifications?.habitsReminder?.enabled && current_time === appSettings.notifications.habitsReminder.time) {
        const lastOpen = localStorage.getItem('lastHabitsReminderDate');
        if (lastOpen !== todayStr) {
          setIsHabitsReminderOpen(true);
          localStorage.setItem('lastHabitsReminderDate', todayStr);
        }
      }

      // Weigh-in
      if (appSettings.notifications?.weighInReminder?.enabled && current_time === appSettings.notifications.weighInReminder.time) {
        const lastWeighInRemind = localStorage.getItem('lastWeighInRemindDate');
        if (lastWeighInRemind !== todayStr) {
          const dayMatch = now.getDay() === appSettings.notifications.weighInReminder.dayOfWeek;
          let shouldRemind = false;

          if (appSettings.notifications.weighInReminder.frequency === 'weekly' && dayMatch) {
            shouldRemind = true;
          } else if (appSettings.notifications.weighInReminder.frequency === 'biweekly') {
            const weekRef = Math.floor(now.getTime() / (7 * 24 * 60 * 60 * 1000));
            if (dayMatch && weekRef % 2 === 0) shouldRemind = true;
          } else if (appSettings.notifications.weighInReminder.frequency === 'monthly' && now.getDate() === 1) {
            shouldRemind = true;
          }

            if (shouldRemind) {
            emitNotification(
              "Lembrete de Pesagem",
              "Hora de registrar seu peso para acompanhar sua evolução no módulo Saúde!",
              'info',
              'saude',
              `weigh_in_${todayStr}`
            );
            localStorage.setItem('lastWeighInRemindDate', todayStr);
          }
        }
      }

      // Tasks
      const currentTimeInMinutes = now.getHours() * 60 + now.getMinutes();
      tarefas.forEach(t => {
        if (t.status === 'concluído' || t.data_limite !== todayStr) return;

        if (t.horario_inicio) {
          const [h, m] = t.horario_inicio.split(':').map(Number);
          const startMin = h * 60 + m;
          const diff = startMin - currentTimeInMinutes;
          const lastReminded = localStorage.getItem(`lastStartRemind_${t.id}`);

          if (diff === 15 && lastReminded !== `${todayStr}_15`) {
             emitNotification(`Em 15 min: ${t.titulo}`, "Prepare-se para iniciar a tarefa.", 'info');
             localStorage.setItem(`lastStartRemind_${t.id}`, `${todayStr}_15`);
          }
        }
      });

    }, 30000);

    return () => clearInterval(interval);
  }, [appSettings, tarefas]);

  return {
    notifications,
    appSettings,
    activePopup,
    isHabitsReminderOpen,
    setIsHabitsReminderOpen,
    setActivePopup,
    emitNotification,
    handleMarkNotificationRead,
    handleDismissNotification,
    handleUpdateAppSettings
  };
};
