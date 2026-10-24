import test from 'node:test';
import assert from 'node:assert/strict';
import { nomeArquivoMidia } from './nome_arquivo.js';

test('mantém nome normal', () => {
    assert.equal(nomeArquivoMidia('relatorio_final.pdf'), 'relatorio_final.pdf');
});

test('apara espaços e troca caracteres de controle', () => {
    assert.equal(nomeArquivoMidia('  a\nb\u0000c.pdf  '), 'a b c.pdf');
});

test('ausente, vazio ou não-string vira null', () => {
    for (const v of [undefined, null, '', '   ', '\n\t', 42, {}, ['a.pdf']]) {
        assert.equal(nomeArquivoMidia(v), null);
    }
});

test('limita a 255 caracteres sem partir par substituto', () => {
    const longo = '😀'.repeat(300);
    const nome = nomeArquivoMidia(longo);
    assert.equal(Array.from(nome).length, 255);
    assert.ok(!/[\ud800-\udbff]$/.test(nome));
});

test('remove marcas bidi, invisíveis e substituto solto', () => {
    assert.equal(nomeArquivoMidia('relatorio‮fdp.exe'), 'relatorio fdp.exe');
    assert.equal(nomeArquivoMidia('​‏'), null);
    assert.equal(nomeArquivoMidia('a\ud83d'), 'a�');
});
