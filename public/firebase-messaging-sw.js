
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyCc00Qqsa7Zgfx9NZkLoPj_gvXcuMczuxk",
  authDomain: "gestao-hermes.firebaseapp.com",
  projectId: "gestao-hermes",
  storageBucket: "gestao-hermes.firebasestorage.app",
  messagingSenderId: "1003307358410",
  appId: "1:1003307358410:web:c0726a4de406584fad7c33",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  console.log('[firebase-messaging-sw.js] Received background message ', payload);

  // If browser already renders a notification payload, skip manual display.
  if (payload.notification?.title && payload.notification?.body && !payload.data?.title && !payload.data?.message) {
    return;
  }

  const notificationTitle = payload.data?.title || payload.notification?.title || 'Hermes';
  const notificationOptions = {
    body: payload.data?.message || payload.notification?.body || '',
    icon: '/logo.png',
    data: payload.data
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const link = event.notification?.data?.link;
  if (!link) {
    event.waitUntil(clients.openWindow('/'));
    return;
  }
  event.waitUntil(clients.openWindow(link));
});
