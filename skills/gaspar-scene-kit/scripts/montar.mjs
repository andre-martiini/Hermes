#!/usr/bin/env node
// Roteiro de cenas (JSON) → projeto HyperFrames feito só com o kit → lint → MP4.
//
//   node montar.mjs roteiro.json SAIDA              # 9:16 e/ou 16:9 conforme "formato"
//   node montar.mjs roteiro.json SAIDA --so-html    # só gera o projeto e passa o lint (grátis, segundos)
//   node montar.mjs roteiro.json SAIDA --revisao    # + PNG de cada cena assentada em SAIDA/<formato>/revisao
//
// Saída: SAIDA/<formato>/projeto/index.html, SAIDA/<titulo> (<formato>).mp4 e SAIDA/<formato>/cenas.json
// (tempo de cada cena; os marcadores de SFX ficam em window.__sfx na página).
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { TIPOS, duracaoMinima } from "../kit/primitivas.mjs";
import { lint } from "./lint-cena.mjs";

const SKILL = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FPS = 30;
const ENTRADA = 0.45; // = Kit.T.entrada: quanto a cena anterior fica por baixo de um wipe
const DIM = { vertical: [1080, 1920], horizontal: [1920, 1080] };

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

export function planejar(roteiro) {
  let t = 0;
  return roteiro.cenas.map((c, i) => {
    if (!TIPOS[c.tipo]) throw new Error(`Cena ${i + 1}: tipo "${c.tipo}" fora do kit (${Object.keys(TIPOS).join(", ")}).`);
    const minimo = duracaoMinima(c);
    const dur = Math.max(c.duracao || 0, minimo);
    const p = { ...c, i, t0: +t.toFixed(3), fim: +(t + dur).toFixed(3), minimo };
    t += dur;
    return p;
  });
}

export function gerarHtml(roteiro, formato, imagens = {}) {
  const [w, h] = DIM[formato];
  const cenas = planejar(roteiro);
  const total = cenas.at(-1).fim;
  const secoes = cenas.map((c, i) => {
    const sobra = cenas[i + 1]?.transicao === "wipe" ? ENTRADA : 0;
    return `<section id="cena-${i}" class="cena clip" data-start="${c.t0}" data-duration="${+(c.fim - c.t0 + sobra).toFixed(3)}" data-track-index="0">` +
      TIPOS[c.tipo].html(c, imagens[i]) + `</section>`;
  }).join("\n      ");
  const dados = {
    cenas: cenas.map((c, i) => ({
      primitiva: TIPOS[c.tipo].primitiva, t0: c.t0, fim: c.fim, em: c.em, valor: c.valor,
      prefixo: c.prefixo, sufixo: c.sufixo, casas: c.casas, transicao: c.transicao, primeira: i === 0,
    })),
  };
  const html = `<!doctype html>
<html lang="pt-BR" data-formato="${formato}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=${w}, height=${h}" />
    <title>${esc(roteiro.titulo || "Gaspar Vídeo")}</title>
    <link rel="stylesheet" href="kit/tokens.css" />
    <script src="vendor/gsap.min.js"></script>
    <script src="vendor/CustomEase.min.js"></script>
    <script src="kit/kit.js"></script>
  </head>
  <body style="width: ${w}px; height: ${h}px">
    <div id="root" data-composition-id="main" data-start="0" data-duration="${total}" data-width="${w}" data-height="${h}">
      ${secoes}
    </div>
    <script type="application/json" id="dados">${JSON.stringify(dados).replace(/</g, "\\u003c")}</script>
    <script>Kit.montar("dados", "main");</script>
  </body>
</html>
`;
  return { html, cenas, total };
}

// O HyperFrames precisa de ffmpeg e ffprobe no PATH. O winget instala o FFmpeg mas o PATH só vale
// para terminais novos: procura na pasta de pacotes do winget como alternativa.
function pathComFfmpeg() {
  const sep = process.platform === "win32" ? ";" : ":";
  if (spawnSync("ffprobe", ["-version"]).status === 0) return process.env.PATH;
  const base = join(process.env.LOCALAPPDATA || "", "Microsoft", "WinGet", "Packages");
  for (const pac of existsSync(base) ? readdirSync(base).filter((d) => d.startsWith("Gyan.FFmpeg")) : []) {
    for (const v of readdirSync(join(base, pac))) {
      const bin = join(base, pac, v, "bin");
      if (existsSync(join(bin, "ffprobe.exe"))) return bin + sep + process.env.PATH;
    }
  }
  throw new Error("FFmpeg com ffprobe não encontrado. Instale: winget install --id Gyan.FFmpeg -e");
}

function hyperframes(args, cwd, env) {
  const bin = join(SKILL, "node_modules", "hyperframes", "bin", "hyperframes.mjs");
  execFileSync(process.execPath, [bin, ...args], { cwd, env, stdio: ["ignore", "inherit", "inherit"] });
}

function preparar(projeto, roteiro, base) {
  mkdirSync(join(projeto, "assets"), { recursive: true });
  cpSync(join(SKILL, "kit"), join(projeto, "kit"), { recursive: true, filter: (f) => !f.endsWith(".mjs") });
  mkdirSync(join(projeto, "vendor"), { recursive: true });
  for (const f of ["gsap.min.js", "CustomEase.min.js"])
    cpSync(join(SKILL, "node_modules", "gsap", "dist", f), join(projeto, "vendor", f));
  const imagens = {};
  roteiro.cenas.forEach((c, i) => {
    if (!c.imagem) return;
    const nome = `${i}-${basename(c.imagem)}`;
    cpSync(resolve(base, c.imagem), join(projeto, "assets", nome));
    imagens[i] = `assets/${nome}`;
  });
  return imagens;
}

function main() {
  const [arq, saida, ...flags] = process.argv.slice(2);
  if (!arq || !saida) { console.error("uso: node montar.mjs roteiro.json SAIDA [--so-html] [--revisao]"); process.exit(2); }
  const roteiro = JSON.parse(readFileSync(arq, "utf8"));
  const formatos = roteiro.formato === "ambos" ? ["vertical", "horizontal"] : [roteiro.formato || "vertical"];
  const env = flags.includes("--so-html") ? process.env : { ...process.env, PATH: pathComFfmpeg() };
  let falhou = false;

  for (const formato of formatos) {
    const pasta = resolve(saida, formato);
    const projeto = join(pasta, "projeto");
    const imagens = preparar(projeto, roteiro, dirname(resolve(arq)));
    const { html, cenas, total } = gerarHtml(roteiro, formato, imagens);
    writeFileSync(join(projeto, "index.html"), html);
    writeFileSync(join(pasta, "cenas.json"), JSON.stringify(cenas.map(({ i, tipo, t0, fim, minimo }) => ({ i, tipo, t0, fim, minimo })), null, 2));
    cenas.filter((c) => c.duracao && c.duracao < c.minimo).forEach((c) =>
      console.warn(`aviso: cena ${c.i + 1} pediu ${c.duracao} s, mas a leitura exige ${c.minimo} s (usei ${c.minimo}).`));

    const erros = lint(html);
    if (erros.length) {
      console.error(`lint-cena: ${erros.length} problema(s) em ${formato}`);
      erros.forEach((e) => console.error("  ✗ " + e));
      falhou = true;
      continue;
    }
    console.log(`${formato}: ${cenas.length} cenas, ${total.toFixed(1)} s, lint ok`);
    if (flags.includes("--so-html")) continue;

    if (flags.includes("--revisao")) {
      const tempos = cenas.map((c) => Math.max(c.t0, c.fim - 0.5).toFixed(2)).join(",");
      hyperframes(["snapshot", "--at", tempos, "--no-end", "-o", join(pasta, "revisao")], projeto, env);
    }
    const mp4 = resolve(saida, `${roteiro.titulo || "Gaspar Vídeo"} (${formato}).mp4`);
    hyperframes(["render", "-o", mp4, "-f", String(FPS), "-q", "delivery"], projeto, env);
    console.log(`→ ${mp4}`);
  }
  process.exit(falhou ? 1 : 0);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
