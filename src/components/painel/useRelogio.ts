import { useEffect, useState } from 'react';
import { INTERVALO_RELOGIO_MS, minutosDoRelogio } from '../../utils/agendaProximidade';

/**
 * Minutos desde 00:00 no relógio real, relido a cada 30 s.
 *
 * `agora` é injetável para os testes fixarem o horário; sem ele usa `new Date()`.
 */
export const useMinutosAgora = (agora: () => Date = () => new Date()): number => {
    const [minutos, setMinutos] = useState(() => minutosDoRelogio(agora()));
    useEffect(() => {
        setMinutos(minutosDoRelogio(agora()));
        const id = setInterval(() => setMinutos(minutosDoRelogio(agora())), INTERVALO_RELOGIO_MS);
        return () => clearInterval(id);
        // `agora` é uma função estável do chamador; reiniciar o intervalo a cada render seria ruído.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return minutos;
};

/** `prefers-reduced-motion: reduce` — sem animação, só cor. */
export const usePrefersReducedMotion = (): boolean => {
    const consulta = () =>
        typeof window !== 'undefined' && typeof window.matchMedia === 'function'
            ? window.matchMedia('(prefers-reduced-motion: reduce)')
            : null;
    const [reduzido, setReduzido] = useState(() => !!consulta()?.matches);
    useEffect(() => {
        const mq = consulta();
        if (!mq) return;
        setReduzido(mq.matches);
        const aoMudar = (e: MediaQueryListEvent) => setReduzido(e.matches);
        mq.addEventListener?.('change', aoMudar);
        return () => mq.removeEventListener?.('change', aoMudar);
    }, []);
    return reduzido;
};
