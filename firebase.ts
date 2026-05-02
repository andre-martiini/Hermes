import { initializeApp } from "firebase/app";
import { initializeFirestore, persistentLocalCache, persistentMultipleTabManager } from "firebase/firestore";
import { getFunctions } from "firebase/functions";
import { getMessaging, type Messaging } from "firebase/messaging";
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

let messagingPromise: Promise<Messaging | null> | null = null;

export const getFirebaseMessaging = async (): Promise<Messaging | null> => {
  if (typeof window === "undefined") return null;

  if (!messagingPromise) {
    messagingPromise = import("firebase/messaging")
      .then(async ({ isSupported }) => {
        if (!(await isSupported())) return null;
        return getMessaging(app);
      })
      .catch((e) => {
        console.warn("Firebase Messaging is not supported in this environment.", e);
        return null;
      });
  }

  return messagingPromise;
};
export const storage = getStorage(app);
