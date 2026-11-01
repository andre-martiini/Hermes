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
