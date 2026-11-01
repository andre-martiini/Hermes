#!/usr/bin/env node
// Lint de cena: falha se uma composição desenhar fora do kit (curva, fonte, cor ou animação própria).
//   node lint-cena.mjs projeto/index.html   → sai com 1 e lista as regras violadas
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const SCRIPTS_PERMITIDOS = /^(kit|vendor)\//;

export function lint(html) {
  const erros = [];
  const add = (regra, trecho) => erros.push(`${regra}: ${String(trecho).trim().slice(0, 80)}`);

  for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    const [, attrs, corpo] = m;
    const src = attrs.match(/src="([^"]*)"/)?.[1];
    if (src) {
      if (!SCRIPTS_PERMITIDOS.test(src)) add("script-externo", src);
      continue;
    }
    if (/type="application\/json"/.test(attrs)) {
      let dados;
      try { dados = JSON.parse(corpo); } catch { add("json-invalido", corpo); continue; }
      const tipos = new Set(dados.cenas.map((c) => c.transicao || "fade"));
      if (tipos.size > 2) add("transicoes-demais", [...tipos].join(", "));
      for (const t of tipos) if (!["fade", "wipe"].includes(t)) add("transicao-fora-do-kit", t);
      continue;
    }
    // Script de cena: só pode chamar o kit.
    const resto = corpo.replace(/Kit\.montar\([^)]*\);?/g, "").replace(/\/\/.*$/gm, "").trim();
    if (resto) add("animacao-fora-do-kit", resto);
  }

  const estilos = [...html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/gi)].map((m) => m[1])
    .concat([...html.matchAll(/\sstyle="([^"]*)"/gi)].map((m) => m[1])).join("\n");

  // Curvas: procuradas só em código e estilos (o texto da tela pode ter "linear" à vontade).
  const codigo = estilos + "\n" + [...html.matchAll(/<script\b(?![^>]*\bsrc=)(?![^>]*application\/json)[^>]*>([\s\S]*?)<\/script>/gi)]
    .map((m) => m[1]).join("\n") + "\n" + [...html.matchAll(/\son\w+="([^"]*)"/gi)].map((m) => m[1]).join("\n");
  for (const m of codigo.matchAll(/\b(ease|easing|transition|animation|transition-timing-function|animation-timing-function)\s*[:=]\s*["']?([^"';,}\s]+)/gi))
    add("curva-fora-do-kit", m[0]);
  for (const m of codigo.matchAll(/\b(linear|cubic-bezier\([^)]*\)|steps\(\d+)/gi)) add("curva-fora-do-kit", m[0]);
  for (const m of codigo.matchAll(/\b(interpolate|spring|gsap)\s*[.(]/g)) add("animacao-fora-do-kit", m[0]);
  for (const m of html.matchAll(/"(ease|easing|curva)"\s*:/g)) add("curva-fora-do-kit", m[0]);
  for (const m of estilos.matchAll(/#[0-9a-f]{3,8}\b|\b(rgba?|hsla?|oklch|color-mix)\(/gi)) add("cor-fora-do-kit", m[0]);
  for (const m of estilos.matchAll(/font-family\s*:\s*([^;"}]+)/gi))
    if (!/^var\(--font-(display|mono)\)$/.test(m[1].trim())) add("fonte-fora-do-kit", m[0]);
  for (const m of estilos.matchAll(/font-size\s*:\s*([^;"}]+)/gi))
    if (!/^var\(--tam-(numero|titulo|texto)\)$/.test(m[1].trim())) add("tamanho-fora-do-kit", m[0]);

  return erros;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const arq = process.argv[2];
  if (!arq) { console.error("uso: node lint-cena.mjs index.html"); process.exit(2); }
  const erros = lint(readFileSync(arq, "utf8"));
  if (erros.length) {
    console.error(`lint-cena: ${erros.length} problema(s) em ${arq}`);
    for (const e of erros) console.error("  ✗ " + e);
    process.exit(1);
  }
  console.log(`lint-cena: ok (${arq})`);
}
