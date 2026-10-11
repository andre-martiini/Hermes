import test from 'node:test';
import assert from 'node:assert/strict';
import { ehPaginaQuebrada, criarRecuperadorDePagina, jaFoiEnviada } from './pagina_quebrada.js';

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
        intervaloMinimoMs: 0, // o intervalo tem teste próprio
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

test('quebra logo depois de recuperar espera o intervalo mínimo (sem loop)', async () => {
    let t = 0;
    const agendados = [];
    const abertas = [];
    const r = criarRecuperadorDePagina({
        destruir: async () => {}, abrir: async (o) => { abertas.push(o); },
        intervaloMinimoMs: 300_000, agora: () => t,
        agendar: (fn, ms) => agendados.push({ fn, ms }), log: { warn() {}, error() {} },
    });
    assert.equal(await r.recuperar('envio'), true);
    r.liberar();
    t = 60_000; // quebrou de novo 1 min depois
    assert.equal(await r.recuperar('envio'), false);
    assert.deepEqual(abertas, ['recuperacao_pagina']);
    assert.equal(agendados.length, 1);
    assert.equal(agendados[0].ms, 240_000);
    t = 300_000;
    agendados[0].fn();
    await new Promise((res) => setImmediate(res));
    assert.equal(abertas.length, 2);
});

test('envio interrompido: acha a mensagem já entregue e não reenvia', () => {
    const desde = 1_000_000_000;
    const msgs = [
        { fromMe: true, body: 'Oi, José', timestamp: (desde - 3_600_000) / 1000, id: { id: 'antiga' } },
        { fromMe: false, body: 'Oi, José', timestamp: desde / 1000 + 5, id: { id: 'dele' } },
        { fromMe: true, body: 'Oi, José ', timestamp: desde / 1000 + 2, id: { id: 'certa' } },
    ];
    assert.equal(jaFoiEnviada(msgs, 'Oi, José', desde)?.id.id, 'certa');
    assert.equal(jaFoiEnviada(msgs, 'Outra mensagem', desde), null);
    assert.equal(jaFoiEnviada([msgs[0]], 'Oi, José', desde), null, 'a de 1h antes é outro envio');
});
