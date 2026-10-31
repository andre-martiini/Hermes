// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GerenciadorOuvintes } from './pausaOuvintes';
import { iniciarSessaoUnica } from './sessaoUnica';

let estado: 'visible' | 'hidden';
let parar: () => void;

function montar(id = 'eu') {
    const g = new GerenciadorOuvintes();
    const ouvinte = { inscrever: vi.fn(() => vi.fn()) };
    g.registrar(ouvinte.inscrever);
    let receber: (id: string | null) => void = () => {};
    const gravar = vi.fn(() => Promise.resolve());
    const aoMudar = vi.fn();
    parar = iniciarSessaoUnica({
        gerenciador: g, doc: document, id,
        escutar: (cb) => { receber = cb; return () => {}; },
        gravar, aoMudar,
    });
    return { g, ouvinte, gravar, aoMudar, receber: (x: string | null) => receber(x) };
}

beforeEach(() => {
    estado = 'visible';
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => estado });
});
afterEach(() => parar?.());

describe('sessão única', () => {
    it('grava o próprio id ao abrir e continua lendo quando o documento mostra o próprio id', () => {
        const s = montar();
        expect(s.gravar).toHaveBeenCalledTimes(1);
        s.receber('eu');
        expect(s.g.pausado).toBe(false);
    });

    it('cede e pausa quando outra cópia assume; avisa a tela', () => {
        const s = montar();
        s.receber('eu');
        s.receber('outra');
        expect(s.g.pausado).toBe(true);
        expect(s.aoMudar).toHaveBeenLastCalledWith(true);
    });

    it('clique, toque ou tecla retomam e tomam a sessão; mover o mouse não', () => {
        const s = montar();
        s.receber('eu');
        s.receber('outra');
        document.dispatchEvent(new Event('mousemove'));
        expect(s.g.pausado).toBe(true);
        document.dispatchEvent(new Event('pointerdown'));
        expect(s.g.pausado).toBe(false);
        expect(s.gravar).toHaveBeenCalledTimes(2);
        expect(s.aoMudar).toHaveBeenLastCalledWith(false);
    });

    it('snapshot velho de outra cópia logo após retomar não cede de novo', () => {
        const s = montar();
        s.receber('eu');
        s.receber('outra');
        document.dispatchEvent(new Event('keydown'));
        s.receber('outra');
        expect(s.g.pausado).toBe(false);
        s.receber('eu');
        s.receber('outra');
        expect(s.g.pausado).toBe(true);
    });

    it('aba aberta escondida não toma a sessão nem cede até aparecer', () => {
        estado = 'hidden';
        const s = montar();
        expect(s.gravar).not.toHaveBeenCalled();
        s.receber('outra');
        expect(s.g.pausado).toBe(false);
        estado = 'visible';
        document.dispatchEvent(new Event('visibilitychange'));
        expect(s.gravar).toHaveBeenCalledTimes(1);
    });

    it('a pausa por ociosidade não desfaz a pausa por outra sessão', () => {
        const s = montar();
        s.receber('eu');
        s.receber('outra');
        s.g.pausar('ocio');
        s.g.retomar('ocio');
        expect(s.g.pausado).toBe(true);
    });
});
