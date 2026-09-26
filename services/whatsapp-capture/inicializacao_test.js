import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
    criarInicializador, esperaDaTentativa, deveAvisar, ESPERA_INICIAL_MS, ESPERA_MAXIMA_MS,
} from './inicializacao.js';

const logMudo = { log() {}, error() {} };

function montar(resultados) {
    const chamadas = { inicializar: 0, destruir: 0, alertas: [], agendados: [] };
    const abrir = criarInicializador({
        inicializar: async () => {
            chamadas.inicializar += 1;
            const r = resultados.shift();
            if (r instanceof Error) throw r;
        },
        destruir: async () => { chamadas.destruir += 1; },
        alertar: (texto) => { chamadas.alertas.push(texto); },
        agendar: (fn, ms) => { chamadas.agendados.push({ fn, ms }); },
        log: logMudo,
    });
    return { abrir, chamadas };
}

const timeout = () => new Error('Page.navigate timed out. Increase the protocolTimeout setting');

test('boot que abre de primeira não avisa nem agenda nada', async () => {
    const { abrir, chamadas } = montar([undefined]);
    await abrir('boot');
    assert.equal(chamadas.inicializar, 1);
    assert.equal(chamadas.destruir, 0);
    assert.deepEqual(chamadas.alertas, []);
    assert.deepEqual(chamadas.agendados, []);
});

test('falha fecha o navegador, avisa e agenda nova tentativa', async () => {
    const { abrir, chamadas } = montar([timeout()]);
    await abrir('boot');
    assert.equal(chamadas.destruir, 1);
    assert.equal(chamadas.alertas.length, 1);
    assert.match(chamadas.alertas[0], /Page\.navigate timed out/);
    assert.match(chamadas.alertas[0], /Tento de novo sozinho em 30s/);
    assert.equal(chamadas.agendados.length, 1);
    assert.equal(chamadas.agendados[0].ms, ESPERA_INICIAL_MS);
});

test('a retentativa agendada abre o WhatsApp e avisa a recuperação', async () => {
    const { abrir, chamadas } = montar([timeout(), timeout(), undefined]);
    await abrir('boot');
    await chamadas.agendados[0].fn();
    await chamadas.agendados[1].fn();
    assert.equal(chamadas.inicializar, 3);
    assert.equal(chamadas.agendados.length, 2);
    assert.equal(chamadas.agendados[1].ms, ESPERA_INICIAL_MS * 2);
    assert.match(chamadas.alertas.at(-1), /conseguiu abrir o WhatsApp Web depois de 2 tentativa/);
});

test('falha ao fechar o navegador não impede a nova tentativa', async () => {
    const agendados = [];
    const abrir = criarInicializador({
        inicializar: async () => { throw timeout(); },
        destruir: async () => { throw new Error('browser já fechado'); },
        alertar: () => {},
        agendar: (fn, ms) => agendados.push(ms),
        log: logMudo,
    });
    await abrir('boot');
    assert.deepEqual(agendados, [ESPERA_INICIAL_MS]);
});

test('chamada durante uma abertura em andamento é ignorada', async () => {
    let liberar;
    let n = 0;
    const abrir = criarInicializador({
        inicializar: () => { n += 1; return new Promise((resolve) => { liberar = resolve; }); },
        destruir: async () => {},
        alertar: () => {},
        agendar: () => {},
        log: logMudo,
    });
    const primeira = abrir('boot');
    await abrir('reconexao');
    liberar();
    await primeira;
    assert.equal(n, 1);
});

test('espera dobra a cada falha até o teto de 10 minutos', () => {
    assert.deepEqual([1, 2, 3, 4, 5, 6].map(esperaDaTentativa),
        [30_000, 60_000, 120_000, 240_000, 480_000, ESPERA_MAXIMA_MS]);
    assert.equal(esperaDaTentativa(50), ESPERA_MAXIMA_MS);
});

test('avisa na primeira falha e depois a cada 5', () => {
    assert.deepEqual([1, 2, 3, 4, 5, 6, 10].map(deveAvisar), [true, false, false, false, true, false, true]);
});

test('index.js abre o WhatsApp só pelo inicializador com retentativa', () => {
    const fonte = fs.readFileSync(new URL('./index.js', import.meta.url), 'utf8');
    assert.doesNotMatch(fonte, /client\.initialize\(\)(?!\s*,)/m, 'client.initialize() solto fora do inicializador');
    assert.match(fonte, /inicializar: \(\) => client\.initialize\(\)/);
    assert.match(fonte, /abrirWhatsApp\('boot'\)/);
    assert.match(fonte, /abrirWhatsApp\('reconexao'\)/);
});
