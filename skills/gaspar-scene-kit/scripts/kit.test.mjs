import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gerarHtml } from "./montar.mjs";
import { lint } from "./lint-cena.mjs";

const exemplo = JSON.parse(readFileSync(new URL("../exemplos/cartoes.json", import.meta.url), "utf8"));

test("cena gerada pelo kit passa no lint, nos dois formatos", () => {
  for (const f of ["vertical", "horizontal"]) assert.deepEqual(lint(gerarHtml(exemplo, f).html), []);
});

test("lint recusa ease: linear e animação própria", () => {
  const { html } = gerarHtml(exemplo, "vertical");
  const ruim = html.replace('<script>Kit.montar("dados", "main");</script>',
    '<script>Kit.montar("dados", "main"); gsap.to("#cena-0", { x: 100, ease: "linear" });</script>');
  const erros = lint(ruim).join("\n");
  assert.match(erros, /curva-fora-do-kit: ease: "linear/);
  assert.match(erros, /animacao-fora-do-kit/);
});

test("lint recusa cor e fonte fora dos tokens, mas aceita 'linear' no texto da tela", () => {
  const { html } = gerarHtml({ ...exemplo, cenas: [{ tipo: "titulo", titulo: "Crescimento linear" }] }, "vertical");
  assert.deepEqual(lint(html), []);
  const ruim = html.replace('class="titulo cab"', 'class="titulo cab" style="color: #ff0000; font-family: Arial"');
  const erros = lint(ruim).join("\n");
  assert.match(erros, /cor-fora-do-kit: #ff0000/);
  assert.match(erros, /fonte-fora-do-kit/);
});

test("mais de 2 tipos de transição é recusado", () => {
  const cenas = ["fade", "wipe", "zoom"].map((t) => ({ tipo: "titulo", titulo: t, transicao: t }));
  const erros = lint(gerarHtml({ cenas }, "vertical").html).join("\n");
  assert.match(erros, /transicoes-demais/);
});

test("duração nunca fica abaixo do tempo de leitura", () => {
  const { cenas } = gerarHtml({ cenas: [{ tipo: "topicos", titulo: "Três passos", itens: ["um", "dois", "três"], duracao: 1 }] }, "vertical");
  assert.ok(cenas[0].fim >= cenas[0].minimo && cenas[0].minimo > 1);
});

import { paginar, deixa } from "./montar.mjs";

const tok = (text, startMs, endMs) => ({ text, startMs, endMs, timestampMs: (startMs + endMs) / 2, confidence: 0.9 });

test("páginas de legenda não se sobrepõem e 300 ms junta menos que 1200 ms", () => {
  const leg = [tok("Tudo", 0, 180), tok(" começa", 180, 560), tok(" na", 560, 700), tok(" demanda.", 840, 1500), tok(" Depois", 1760, 2100)];
  const curtas = paginar(leg, 300), longas = paginar(leg, 1200);
  assert.ok(curtas.length > longas.length);
  for (const p of [curtas, longas]) p.forEach((pg, k) => p[k + 1] && assert.equal(pg.endMs, p[k + 1].startMs));
  assert.equal(longas.flatMap((p) => p.tokens).map((t) => t.text).join(""), leg.map((t) => t.text).join(""));
});

test("item entra quando a fala o cita", () => {
  const leg = [tok("Depois", 0, 300), tok(" vem", 300, 500), tok(" o", 500, 560), tok(" planejamento,", 560, 1400)];
  assert.equal(deixa("Planejamento", leg), 0.25 + 0.56);
  assert.equal(deixa("Contrato", leg), null);
});

import { checkLegendas } from "./gates.mjs";

test("check-legendas: motion exige a narração inteira; sobreposição exige revisar palavra incerta", () => {
  const roteiro = { cenas: [{ tipo: "titulo", titulo: "x", narracao: "Tudo começa na demanda." }] };
  const ok = { legendas: [[tok("Tudo", 0, 1), tok(" começa", 1, 2), tok(" na", 2, 3), tok(" demanda.", 3, 4)]] };
  assert.deepEqual(checkLegendas(roteiro, ok), []);
  const falta = { legendas: [[tok("Tudo", 0, 1), tok(" começa", 1, 2)]] };
  assert.equal(checkLegendas(roteiro, falta)[0].regra, "legenda-cobertura");
  const sobre = { gravacao: "v.mp4", cenas: [] };
  const fala = { legendas: [tok("Ifes", 0, 1), tok(" ok", 1, 2)] };
  fala.legendas[0].confidence = 0.2;
  assert.equal(checkLegendas(sobre, fala)[0].regra, "legenda-nao-revisada");
  fala.legendas[0].revisado = true;
  assert.deepEqual(checkLegendas(sobre, fala), []);
});

import { achar } from "./montar.mjs";
import { filtroAudio } from "./pos.mjs";

test("correções do review: frase vazia, mix sem entradas, narração com quebra de linha", () => {
  assert.equal(achar("", [tok("Oi", 0, 100)]), null);
  assert.equal(achar("qualquer", []), null);
  assert.match(filtroAudio({ voz: false, trilha: null, sfx: [], total: 5 }).filtro, /anullsrc/);
  const roteiro = { cenas: [{ tipo: "titulo", titulo: "x", narracao: "Primeiro a demanda.\nDepois  o ETP." }] };
  const voz = { legendas: [[tok("Primeiro", 0, 1), tok(" a", 1, 2), tok(" demanda.", 2, 3), tok(" Depois", 3, 4), tok(" o", 4, 5), tok(" ETP.", 5, 6)]] };
  assert.deepEqual(checkLegendas(roteiro, voz), []);
});

// ---------------------------------------------------------------- Gaspar Vídeo v2: composição × pessoa
import { avaliarTitulo, cobertura, correlacao } from "./gates.mjs";

// Pessoa sintética: alfa 1 dentro de [x0,y0,x1,y1] (px de 1080×1920), rosto na caixa dada, 10 quadros/s.
function pessoa(caixa, rosto, n = 50) {
  const alfa = new Uint8Array(108 * 192);
  for (let y = Math.floor(caixa[1] / 10); y < Math.ceil(caixa[3] / 10); y++)
    for (let x = Math.floor(caixa[0] / 10); x < Math.ceil(caixa[2] / 10); x++) alfa[y * 108 + x] = 255;
  const quadros = Array.from({ length: n }, (_, k) => ({ t: k / 10, alfa, topo: caixa[1], rosto }));
  return { quadros, em: (t) => quadros[Math.min(n - 1, Math.max(0, Math.round(t * 10)))] };
}
const medida = (letras, painel, fonte = 200) => [1, 1.5, 2, 2.5, 3].map((t) => ({ t, letras, textos: [[letras[0][0], letras[0][1] - 60, letras.at(-1)[2], letras[0][3]]], painel, fonte }));
const cena = { i: 0, t0: 0, fim: 4 };
const cabecaGrande = pessoa([200, 300, 880, 1920], [260, 420, 820, 1150]);

test("titulo-oculto: letra atrás da cabeça no modo atras", () => {
  const letras = [[100, 350, 300, 550], [300, 350, 500, 550], [500, 350, 700, 550], [700, 350, 900, 550]];
  assert.ok(cobertura(cabecaGrande.em(1), letras[1]) > 0.9);
  const e = avaliarTitulo("atras", medida(letras, [50, 290, 1030, 560]), cabecaGrande, cena, 3);
  assert.ok(e.some((x) => x.regra === "titulo-oculto"));
  assert.ok(e.pior.oculto > 0.9);
});

test("titulo-cortado: texto que passa da borda direita", () => {
  const letras = [[300, 1250, 600, 1400], [600, 1250, 900, 1400], [900, 1250, 1180, 1400]];
  const e = avaliarTitulo("abaixo", medida(letras, [50, 1180, 1030, 1420]), cabecaGrande, cena, 3);
  assert.ok(e.some((x) => x.regra === "titulo-cortado"));
});

test("rosto-coberto: título abaixo encostando no queixo; abaixo do queixo passa", () => {
  const letras = [[300, 1200, 500, 1320], [500, 1200, 700, 1320]];
  const ruim = avaliarTitulo("abaixo", medida(letras, [50, 1100, 1030, 1340]), cabecaGrande, cena, 3);
  assert.ok(ruim.some((x) => x.regra === "rosto-coberto"));
  const bom = avaliarTitulo("abaixo", medida(letras, [50, 1180, 1030, 1340]), cabecaGrande, cena, 3);
  assert.deepEqual(bom.map((x) => x.regra), []);
});

test("modo antes recusa quando a fala começa durante o cartão", () => {
  const letras = [[300, 900, 500, 1000]];
  assert.ok(avaliarTitulo("antes", medida(letras, [50, 850, 1030, 1050]), cabecaGrande, cena, 0.3).some((x) => x.regra === "fala-no-cartao"));
  assert.deepEqual([...avaliarTitulo("antes", [{ t: 0.5, letras, textos: [[300, 900, 500, 1000]], painel: [50, 850, 1030, 1050], fonte: 120 }],
    cabecaGrande, cena, 1.4)], []);
});

test("correlação do rosto: igual = 1, coberto por painel liso < 0,6", () => {
  const w = 20, a = new Uint8Array(w * w * 3).map((_, i) => (i * 37) % 251), liso = new Uint8Array(w * w * 3).fill(40);
  liso[0] = 41;
  assert.ok(correlacao(a, a, w, [0, 0, w, w]) > 0.99);
  assert.ok(correlacao(a, liso, w, [0, 0, w, w]) < 0.6);
});

test("ambiente entra na mixagem abaixo da voz, sem graves, com ducking e só na janela pedida", () => {
  const { filtro } = filtroAudio({ voz: true, trilha: "t.m4a", ambientes: [{ arquivo: "a.wav", inicio: 2, fim: 10, nivel_db: -26 }], sfx: [], total: 12 });
  assert.match(filtro, /\[0:a\]aresample=48000,asplit=3\[voz\]\[chave0\]\[chave1\]/);
  assert.match(filtro, /\[2:a\]aresample=48000,highpass=f=120,lowpass=f=8000,volume=-26dB,atrim=0:8\.000/);
  assert.match(filtro, /adelay=2000:all=1\[am0\];\[am0\]\[chave1\]sidechaincompress/);
  assert.match(filtro, /amix=inputs=3/);
});

import { LIMITADOR, medirLoudness } from "./pos.mjs";
import { execFileSync as ef } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join as pj } from "node:path";

test("true-peak: voz com picos fortes fica ≤ −1,5 dBTP medida no AAC final", () => {
  const pasta = mkdtempSync(pj(tmpdir(), "tp-"));
  const aac = pj(pasta, "x.m4a");
  // Fala baixa com estalos: o loudnorm linear aplica ganho fixo (+10 dB) e os estalos passariam de 0 dBFS (+5,8 dBTP).
  const fonte = "aevalsrc='0.08*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*3*t))+if(lt(mod(t,0.7),0.004),0.5,0)':s=48000:d=6";
  ef("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", fonte, "-af",
    `volume=10dB,${LIMITADOR},aresample=48000`, "-c:a", "aac", "-b:a", "192k", aac]);
  const { TP } = medirLoudness(aac);
  assert.ok(TP <= -1.5, `true-peak ${TP}`);
});

test("versão em outro idioma: o número segue o locale do roteiro", () => {
  const cena = { tipo: "numero", valor: 1200, rotulo: "essays" };
  assert.match(gerarHtml({ cenas: [cena] }, "vertical").html, /"locale":"pt-BR"/);
  assert.match(gerarHtml({ idioma: "en", cenas: [cena] }, "vertical").html, /"locale":"en-US"/);
});
