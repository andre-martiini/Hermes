// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GerenciadorOuvintes, ativarPausaOciosa } from './pausaOuvintes';

function ouvinte() {
    const cancela = vi.fn();
    const inscrever = vi.fn(() => cancela);
    return { inscrever, cancela };
}

describe('GerenciadorOuvintes', () => {
    it('assina ao registrar, cancela ao pausar e assina de novo ao retomar', () => {
        const g = new GerenciadorOuvintes();
        const a = ouvinte();
        g.registrar(a.inscrever);
        expect(a.inscrever).toHaveBeenCalledTimes(1);
        g.pausar();
        g.pausar();
        expect(a.cancela).toHaveBeenCalledTimes(1);
        g.retomar();
        g.retomar();
        expect(a.inscrever).toHaveBeenCalledTimes(2);
    });

    it('cancelar enquanto pausado impede reassinar; cancelar é definitivo', () => {
        const g = new GerenciadorOuvintes();
        const a = ouvinte();
        const cancelar = g.registrar(a.inscrever);
        g.pausar();
        cancelar();
        g.retomar();
        expect(a.inscrever).toHaveBeenCalledTimes(1);
        const b = ouvinte();
        const cancelarB = g.registrar(b.inscrever);
        cancelarB();
        expect(b.cancela).toHaveBeenCalledTimes(1);
        g.pausar();
        g.retomar();
        expect(b.inscrever).toHaveBeenCalledTimes(1);
    });

    it('ouvinte que falha ao reassinar não impede os outros de voltar', () => {
        const g = new GerenciadorOuvintes();
        vi.spyOn(console, 'error').mockImplementation(() => {});
        let vez = 0;
        g.registrar(() => {
            if (vez++ > 0) throw new Error('ref inválida');
            return () => {};
        });
        const b = ouvinte();
        g.registrar(b.inscrever);
        g.pausar();
        g.retomar();
        expect(b.inscrever).toHaveBeenCalledTimes(2);
        expect(() => g.registrar(() => { throw new Error('x'); })).toThrow('x');
    });

    it('ouvinte registrado durante a pausa só assina ao retomar', () => {
        const g = new GerenciadorOuvintes();
        g.pausar();
        const a = ouvinte();
        g.registrar(a.inscrever);
        expect(a.inscrever).not.toHaveBeenCalled();
        g.retomar();
        expect(a.inscrever).toHaveBeenCalledTimes(1);
    });
});

describe('ativarPausaOciosa', () => {
    let desligar: () => void;
    let estado: 'visible' | 'hidden';
    let t: number;
    const agora = () => t;
    const mudarVisibilidade = (v: 'visible' | 'hidden') => {
        estado = v;
        document.dispatchEvent(new Event('visibilitychange'));
    };

    beforeEach(() => {
        vi.useFakeTimers();
        t = 0;
        estado = 'visible';
        Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => estado });
    });
    afterEach(() => {
        desligar?.();
        vi.useRealTimers();
    });
    const avancar = (ms: number) => {
        t += ms;
        vi.advanceTimersByTime(ms);
    };

    it('pausa depois de ficar escondida por 10 min e retoma ao reaparecer', () => {
        const g = new GerenciadorOuvintes();
        desligar = ativarPausaOciosa(g, document, { agora });
        mudarVisibilidade('hidden');
        avancar(9 * 60_000);
        expect(g.pausado).toBe(false);
        avancar(60_000);
        expect(g.pausado).toBe(true);
        mudarVisibilidade('visible');
        expect(g.pausado).toBe(false);
    });

    it('voltar antes dos 10 min cancela a pausa agendada', () => {
        const g = new GerenciadorOuvintes();
        desligar = ativarPausaOciosa(g, document, { agora });
        mudarVisibilidade('hidden');
        avancar(5 * 60_000);
        mudarVisibilidade('visible');
        avancar(30 * 60_000);
        expect(g.pausado).toBe(false);
    });

    it('visível mas sem atividade por 1 h pausa; qualquer toque retoma', () => {
        const g = new GerenciadorOuvintes();
        desligar = ativarPausaOciosa(g, document, { agora });
        avancar(59 * 60_000);
        expect(g.pausado).toBe(false);
        avancar(2 * 60_000);
        expect(g.pausado).toBe(true);
        document.dispatchEvent(new Event('pointerdown'));
        expect(g.pausado).toBe(false);
    });

    it('atividade periódica mantém os ouvintes vivos', () => {
        const g = new GerenciadorOuvintes();
        desligar = ativarPausaOciosa(g, document, { agora });
        for (let i = 0; i < 6; i++) {
            avancar(30 * 60_000);
            document.dispatchEvent(new Event('keydown'));
        }
        expect(g.pausado).toBe(false);
    });

    it('aba que já abre escondida também pausa', () => {
        estado = 'hidden';
        const g = new GerenciadorOuvintes();
        desligar = ativarPausaOciosa(g, document, { agora });
        avancar(10 * 60_000);
        expect(g.pausado).toBe(true);
    });
});
