import test from 'node:test';
import assert from 'node:assert/strict';
import { ehPaginaQuebrada, criarRecuperadorDePagina } from './pagina_quebrada.js';

const silencioso = { warn() {}, error() {}, log() {} };

test('reconhece erros de página/sessão do puppeteer', () => {
    for (const msg of [
        "Attempted to use detached Frame 'A45E0D48'.",
        'Execution context was destroyed, most likely because of a navigation.',
        'Protocol error (Runtime.callFunctionOn): Target closed.',
        'Protocol error (Runtime.callFunctionOn): Session closed. Most likely the page has been closed.',
        'Protocol error (DOM.resolveNode): No target with given id found',
    ]) {
        assert.equal(ehPaginaQuebrada(new Error(msg)), true, msg);
    }
});

test('não confunde destino inválido nem erro genérico com página quebrada', () => {
    for (const msg of [
        'numero de destino invalido: "123"',
        'o numero 5527999 nao esta no WhatsApp (ou nao pode ser verificado agora)',
        'Evaluation failed: t: t',
        'Protocol error (Runtime.callFunctionOn): Invalid parameters',
        'wid error: invalid wid',
    ]) {
        assert.equal(ehPaginaQuebrada(new Error(msg)), false, msg);
    }
    assert.equal(ehPaginaQuebrada(undefined), false);
    assert.equal(ehPaginaQuebrada('Target closed'), true);
});

test('detecções simultâneas disparam uma recuperação só até o ready', async () => {
    const chamadas = [];
    const r = criarRecuperadorDePagina({
        destruir: async () => chamadas.push('destruir'),
        abrir: async (origem) => chamadas.push(origem),
        log: silencioso,
    });
    const resultados = await Promise.all([r.recuperar('outbox'), r.recuperar('outbox'), r.recuperar('chats')]);
    assert.deepEqual(resultados, [true, false, false]);
    assert.deepEqual(chamadas, ['destruir', 'recuperacao_pagina']);

    assert.equal(await r.recuperar('chats'), false, 'segue travado até o ready');
    r.liberar();
    assert.equal(await r.recuperar('chats'), true);
    assert.equal(chamadas.length, 4);
});

test('destroy que falha ou trava não impede reabrir', async () => {
    const abertos = [];
    const falha = criarRecuperadorDePagina({
        destruir: async () => { throw new Error('browser já morreu'); },
        abrir: async (o) => abertos.push(o),
        log: silencioso,
    });
    await falha.recuperar('outbox');

    const trava = criarRecuperadorDePagina({
        destruir: () => new Promise(() => {}),
        abrir: async (o) => abertos.push(o),
        prazoDestruirMs: 5,
        log: silencioso,
    });
    await trava.recuperar('outbox');
    assert.deepEqual(abertos, ['recuperacao_pagina', 'recuperacao_pagina']);
});
