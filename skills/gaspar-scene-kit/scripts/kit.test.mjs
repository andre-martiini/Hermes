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
