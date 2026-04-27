import { initializeApp } from "firebase/app";
import { initializeFirestore, persistentLocalCache, persistentMultipleTabManager } from "firebase/firestore";
import { getFunctions } from "firebase/functions";
import { getMessaging } from "firebase/messaging";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, browserLocalPersistence, browserSessionPersistence, setPersistence } from "firebase/auth";
import { getStorage } from "firebase/storage";

const firebaseConfig = {
  apiKey: "AIzaSyCc00Qqsa7Zgfx9NZkLoPj_gvXcuMczuxk",
  authDomain: "gestao-hermes.firebaseapp.com",
  projectId: "gestao-hermes",
  storageBucket: "gestao-hermes.firebasestorage.app",
  messagingSenderId: "1003307358410",
  appId: "1:1003307358410:web:c0726a4de406584fad7c33",
  measurementId: "G-ZKX16ZRTDN"
};

const app = initializeApp(firebaseConfig);

export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
export { signInWithPopup, signOut, browserLocalPersistence, browserSessionPersistence, setPersistence };

export const db = initializeFirestore(app, {
  experimentalForceLongPolling: true,
  localCache: persistentLocalCache({ tabManager: persistentMultipleTabManager() }),
});

export const functions = getFunctions(app, "us-central1");
let _messaging: ReturnType<typeof getMessaging> | null = null;
if (typeof window !== "undefined") {
  // Use a self-executing async function to check for support without blocking the export
  (async () => {
    try {
      const { isSupported } = await import("firebase/messaging");
      if (await isSupported()) {
        _messaging = getMessaging(app);
      }
    } catch (e) {
      console.warn("Firebase Messaging is not supported in this environment.", e);
    }
  })();
}
export const messaging = _messaging;
export const storage = getStorage(app);
