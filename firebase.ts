
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
import { getFunctions } from "firebase/functions";
import { getMessaging } from "firebase/messaging";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, browserLocalPersistence, browserSessionPersistence, setPersistence } from "firebase/auth";

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
export const db = getFirestore(app);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
export { signInWithPopup, signOut, browserLocalPersistence, browserSessionPersistence, setPersistence };
export const functions = getFunctions(app);
export const messaging = typeof window !== 'undefined' ? getMessaging(app) : null;
import { getStorage } from "firebase/storage";
export const storage = getStorage(app);
