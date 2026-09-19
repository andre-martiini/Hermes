import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { criarOpcoesPuppeteer, SINAIS_DE_DESLIGAMENTO } from './puppeteer_opcoes.js';

test('o Puppeteer não trata sinais por conta própria (senão mata o Chromium e sai com 130 antes do desligar)', () => {
    const opcoes = criarOpcoesPuppeteer();
    assert.equal(opcoes.handleSIGINT, false);
    assert.equal(opcoes.handleSIGTERM, false);
    assert.equal(opcoes.handleSIGHUP, false);
});

test('mantém o protocolTimeout de 300s para mídias grandes', () => {
    assert.equal(criarOpcoesPuppeteer().protocolTimeout, 300000);
});

test('cada chamada devolve um objeto novo (o LocalAuth grava userDataDir nele)', () => {
    const a = criarOpcoesPuppeteer();
    a.userDataDir = 'x';
    assert.equal(criarOpcoesPuppeteer().userDataDir, undefined);
});

test('o desligamento cobre Ctrl+C, encerramento, fechar o console e Ctrl+Break', () => {
    assert.deepEqual([...SINAIS_DE_DESLIGAMENTO].sort(), ['SIGBREAK', 'SIGHUP', 'SIGINT', 'SIGTERM']);
});

test('index.js usa as opções e os sinais deste módulo (não volta a ter opções soltas)', () => {
    const fonte = fs.readFileSync(new URL('./index.js', import.meta.url), 'utf8');
    assert.match(fonte, /puppeteer:\s*criarOpcoesPuppeteer\(\)/);
    assert.match(fonte, /for \(const sinal of SINAIS_DE_DESLIGAMENTO\)/);
    assert.doesNotMatch(fonte, /puppeteer:\s*\{/);
});
