
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
import { getFunctions } from "firebase/functions";

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
export const functions = getFunctions(app);
import { getStorage } from "firebase/storage";
export const storage = getStorage(app);
