import test from 'node:test';
import assert from 'node:assert/strict';
import { detectarMencao } from './mentions.js';

const TELEFONE = '5527999990000@c.us';
const LID = '144929460330697@lid';
const DONO = [TELEFONE, LID];

test('menção por lid em mentionedIds', () => {
    assert.equal(detectarMencao({ mentionedIds: [LID], body: 'oi', ownIds: DONO }), true);
});

test('menção por telefone em mentionedIds continua valendo', () => {
    assert.equal(detectarMencao({ mentionedIds: [TELEFONE], body: 'oi', ownIds: DONO }), true);
});

test('só o corpo traz o token: mentionedIds vazio', () => {
    const body = '@144929460330697 , o problema voltou';
    assert.equal(detectarMencao({ mentionedIds: [], body, ownIds: DONO }), true);
});

test('token no meio da frase e no fim', () => {
    assert.equal(detectarMencao({ body: 'Gabriela pediu @144929460330697 ver isso', ownIds: DONO }), true);
    assert.equal(detectarMencao({ body: 'ping @144929460330697', ownIds: DONO }), true);
});

test('mencionar outra pessoa não conta', () => {
    assert.equal(detectarMencao({ mentionedIds: ['999999999999999@lid'], body: '@999999999999999 oi', ownIds: DONO }), false);
});

test('número maior que contém o lid do dono não conta', () => {
    assert.equal(detectarMencao({ body: '@1449294603306971 oi', ownIds: DONO }), false);
    assert.equal(detectarMencao({ body: 'x@144929460330697 oi', ownIds: DONO }), false);
});

test('sem @ no corpo e sem ids: falso', () => {
    assert.equal(detectarMencao({ body: 'bom dia a todos', ownIds: DONO }), false);
});

test('sem ids do dono: nunca detecta, sem lançar', () => {
    assert.equal(detectarMencao({ mentionedIds: [LID], body: '@144929460330697', ownIds: [] }), false);
    assert.equal(detectarMencao({}), false);
});

test('ownIds aceita Set e ignora vazios e lixo curto', () => {
    assert.equal(detectarMencao({ body: '@123 oi', ownIds: new Set(['123@lid', '', null]) }), false);
    assert.equal(detectarMencao({ mentionedIds: [LID], ownIds: new Set([LID]) }), true);
});

test('corpo ausente ou não string não quebra', () => {
    assert.equal(detectarMencao({ mentionedIds: [], body: null, ownIds: DONO }), false);
    assert.equal(detectarMencao({ mentionedIds: [], body: undefined, ownIds: DONO }), false);
});
