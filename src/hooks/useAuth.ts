import { useState, useEffect } from 'react';
import { User, onAuthStateChanged } from 'firebase/auth';
import { auth, googleProvider, signInWithPopup, signOut, setPersistence, browserLocalPersistence, browserSessionPersistence } from '../firebase';

export const useAuth = (showToast: (msg: string, type: 'success' | 'error' | 'info') => void) => {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [rememberMe, setRememberMe] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setAuthLoading(false);
    });
    return () => unsubscribe();
  }, []);

  const handleLogin = async () => {
    try {
      await setPersistence(auth, rememberMe ? browserLocalPersistence : browserSessionPersistence);
      await signInWithPopup(auth, googleProvider);
      showToast("Login realizado com sucesso!", "success");
    } catch (error) {
      console.error("Erro ao fazer login:", error);
      showToast("Erro ao fazer login com Google.", "error");
    }
  };

  const handleLogout = async () => {
    try {
      await signOut(auth);
      showToast("Sessão encerrada.", "info");
    } catch (error) {
      console.error("Erro ao fazer logout:", error);
    }
  };

  return { user, authLoading, rememberMe, setRememberMe, handleLogin, handleLogout };
};
