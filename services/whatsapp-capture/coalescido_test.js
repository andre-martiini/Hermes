import test from 'node:test';
import assert from 'node:assert/strict';
import { criarExecutorCoalescido } from './coalescido.js';

const pausa = () => new Promise((resolve) => setImmediate(resolve));

test('um pedido roda a tarefa uma vez', async () => {
    let n = 0;
    const solicitar = criarExecutorCoalescido(async () => { n += 1; });
    await solicitar();
    assert.equal(n, 1);
});

test('pedidos durante a execução viram uma única rodada extra', async () => {
    let n = 0;
    let liberar;
    const travada = new Promise((resolve) => { liberar = resolve; });
    const solicitar = criarExecutorCoalescido(async () => {
        n += 1;
        if (n === 1) await travada;
    });

    const primeira = solicitar();
    await pausa();
    await solicitar();
    await solicitar();
    await solicitar();
    liberar();
    await primeira;

    assert.equal(n, 2);
});

test('nunca roda duas execuções ao mesmo tempo', async () => {
    let simultaneas = 0;
    let maximo = 0;
    const solicitar = criarExecutorCoalescido(async () => {
        simultaneas += 1;
        maximo = Math.max(maximo, simultaneas);
        await pausa();
        await pausa();
        simultaneas -= 1;
    });

    await Promise.all([solicitar(), solicitar(), solicitar(), solicitar()]);
    assert.equal(maximo, 1);
});

test('pedidos em sequência, sem sobreposição, rodam um a um', async () => {
    let n = 0;
    const solicitar = criarExecutorCoalescido(async () => { n += 1; });
    await solicitar();
    await solicitar();
    await solicitar();
    assert.equal(n, 3);
});

test('erro da tarefa sobe, mas o executor volta a aceitar pedidos', async () => {
    let n = 0;
    const solicitar = criarExecutorCoalescido(async () => {
        n += 1;
        if (n === 1) throw new Error('falhou');
    });
    await assert.rejects(solicitar(), /falhou/);
    await solicitar();
    assert.equal(n, 2);
});
