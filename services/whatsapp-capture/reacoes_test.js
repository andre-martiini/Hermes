import test from 'node:test';
import assert from 'node:assert/strict';
import { montarReacao } from './reacoes.js';

const reacao = (extra = {}) => ({
    id: { fromMe: false, remote: '5527999@c.us', id: 'REACAO1' },
    msgId: { fromMe: true, remote: { _serialized: '123@lid' }, id: 'MSG1', _serialized: 'true_123@lid_MSG1' },
    senderId: '123@lid',
    reaction: '👍',
    timestamp: 1792680000,
    ...extra,
});

test('reação de contato a mensagem do André', () => {
    const r = montarReacao(reacao());
    assert.equal(r.id, '123@lid_MSG1_123@lid');
    assert.equal(r.dados.chat_id, '123@lid');
    assert.equal(r.dados.reacted_doc_id, '123@lid_MSG1');
    assert.equal(r.dados.reacted_from_me, true);
    assert.equal(r.dados.from_me, false);
    assert.equal(r.dados.emoji, '👍');
    assert.equal(r.dados.removida, false);
    assert.equal(r.dados.reacted_at_ms, 1792680000000);
});

test('reação removida grava emoji vazio, não some', () => {
    const r = montarReacao(reacao({ reaction: '' }));
    assert.equal(r.dados.emoji, '');
    assert.equal(r.dados.removida, true);
});

test('reação do próprio André: pelo id da reação ou pelos ids do dono', () => {
    assert.equal(montarReacao(reacao({ id: { fromMe: true } })).dados.from_me, true);
    assert.equal(montarReacao(reacao({ senderId: 'eu@lid' }), new Set(['eu@lid'])).dados.from_me, true);
});

test('timestamp em milissegundos é mantido', () => {
    assert.equal(montarReacao(reacao({ timestamp: 1792680000123 })).dados.reacted_at_ms, 1792680000123);
});

test('sem mensagem alvo ou sem remetente não grava', () => {
    assert.equal(montarReacao(reacao({ msgId: null })), null);
    assert.equal(montarReacao(reacao({ senderId: '' })), null);
    assert.equal(montarReacao(null), null);
});
