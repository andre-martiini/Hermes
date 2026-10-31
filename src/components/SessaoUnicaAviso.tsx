import React, { useEffect, useState } from 'react';
import { onAuthStateChanged } from 'firebase/auth';
import { doc, serverTimestamp, setDoc } from 'firebase/firestore';
import { auth, db } from '../../firebase';
import { gerenciador, onSnapshotSemPausa } from '../utils/firestoreComPausa';
import { iniciarSessaoUnica } from '../utils/sessaoUnica';

const idDestaAba = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

// Liga a sessão única depois do login e mostra o aviso quando outra cópia do Gaspar assumiu.
export const SessaoUnicaAviso: React.FC = () => {
    const [cedida, setCedida] = useState(false);

    useEffect(() => {
        let encerrar: (() => void) | null = null;
        const parar = onAuthStateChanged(auth, (usuario) => {
            encerrar?.();
            encerrar = null;
            setCedida(false);
            if (!usuario) return;
            const ref = doc(db, 'system', 'sessao_ativa');
            encerrar = iniciarSessaoUnica({
                gerenciador,
                doc: document,
                id: idDestaAba,
                escutar: (aoReceber) =>
                    onSnapshotSemPausa(
                        ref,
                        (snap) => aoReceber((snap.data()?.id as string | undefined) ?? null),
                        (erro) => console.warn('[sessao-unica] ouvinte falhou:', erro),
                    ),
                gravar: () => setDoc(ref, { id: idDestaAba, em: serverTimestamp(), aparelho: navigator.userAgent.slice(0, 120) }),
                aoMudar: setCedida,
            });
        });
        return () => {
            parar();
            encerrar?.();
        };
    }, []);

    if (!cedida) return null;

    return (
        <div
            role="status"
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                zIndex: 9998,
                padding: '10px 16px',
                background: '#151c27',
                color: '#ffffff',
                textAlign: 'center',
                fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
                fontSize: '13px',
            }}
        >
            O Gaspar foi aberto em outro aparelho ou aba e esta cópia está em pausa. Toque ou clique em qualquer lugar para usar aqui.
        </div>
    );
};
